"""Administrator inventory conditions are native project identities, before paging."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.common.admin_resource_scope import page, resolve_scope


def project(pid, domain="domain-a"):
    return SimpleNamespace(id=pid, name="duplicate-name", domain_id=domain)


@pytest.fixture
def directory(mock_conn):
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="domain-a")
    mock_conn.identity.projects.side_effect = lambda **_: iter(
        [
            project("a"),
            project("b"),
            project("foreign", "domain-b"),
        ]
    )
    return mock_conn


def volume(vid, owner="a"):
    return SimpleNamespace(id=vid, name=vid, project_id=owner, status="available", size=1, created_at=None)


def response(body):
    result = MagicMock()
    result.json.return_value = body
    return result


def test_scope_uses_project_identity_not_duplicate_name(directory):
    scope = resolve_scope(directory, "domain-a", None)
    assert scope.project_ids == frozenset({"a", "b"})
    assert scope.filter([{"project_id": "a"}, {"project_id": "foreign"}, {}]) == [{"project_id": "a"}]
    directory.identity.projects.assert_called_once_with(domain_id="domain-a")


def test_domain_project_mismatch_is_empty(directory):
    assert resolve_scope(directory, "domain-a", "foreign").project_ids == frozenset()


def test_no_domain_compatibility_does_not_read_directory(directory):
    assert resolve_scope(directory, None, None).project_ids is None
    assert resolve_scope(directory, None, "foreign").project_ids == frozenset({"foreign"})
    directory.identity.projects.assert_not_called()
    directory.identity.get_domain.assert_not_called()


@pytest.mark.parametrize("failure,status", [("missing", 404), ("failed", 503), ("metadata", 503)])
def test_directory_failure_is_not_all_domain_inventory(directory, failure, status):
    if failure == "missing":
        directory.identity.get_domain.return_value = None
    elif failure == "failed":
        directory.identity.projects.side_effect = RuntimeError("private native error")
    else:
        directory.identity.projects.side_effect = None
        directory.identity.projects.return_value = [SimpleNamespace(id="a", name="same")]
    with pytest.raises(HTTPException) as raised:
        resolve_scope(directory, "domain-a", None)
    assert raised.value.status_code == status
    assert "private native error" not in str(raised.value.detail)


def test_pagination_rejects_foreign_marker():
    with pytest.raises(HTTPException, match="inventory_marker_outside_scope"):
        page([{"id": "a"}], 1, "foreign")


@pytest.mark.asyncio
async def test_volume_domain_filter_precedes_pagination(admin_client, directory):
    directory.block_storage.volumes.side_effect = lambda **_: iter(
        [
            volume("outside", "foreign"),
            volume("a1"),
            volume("b1", "b"),
            volume("a2"),
        ]
    )
    first = await admin_client.get("/api/v1/admin/all-volumes?domain_id=domain-a&limit=1")
    assert first.status_code == 200
    assert [v["id"] for v in first.json()["items"]] == ["a1"]
    assert first.json()["next_marker"] == "a1"
    second = await admin_client.get("/api/v1/admin/all-volumes?domain_id=domain-a&limit=1&marker=a1")
    assert [v["id"] for v in second.json()["items"]] == ["b1"]
    assert "limit" not in directory.block_storage.volumes.call_args.kwargs
    assert "marker" not in directory.block_storage.volumes.call_args.kwargs


@pytest.mark.asyncio
async def test_volume_domain_project_intersection(admin_client, directory):
    directory.block_storage.volumes.return_value = [volume("wrong", "foreign")]
    result = await admin_client.get("/api/v1/admin/all-volumes?domain_id=domain-a&project_id=foreign")
    assert result.status_code == 200
    assert result.json() == {"items": [], "next_marker": None, "count": 0}


@pytest.mark.asyncio
async def test_volume_no_domain_retains_native_page_contract(admin_client, directory):
    directory.block_storage.volumes.return_value = [volume("old", "foreign")]
    result = await admin_client.get("/api/v1/admin/all-volumes?limit=1&project_id=foreign")
    assert result.status_code == 200
    assert result.json()["items"][0]["id"] == "old"
    directory.block_storage.volumes.assert_called_once_with(
        details=True, all_projects=True, limit=1, project_id="foreign"
    )
    directory.identity.projects.assert_not_called()


@pytest.mark.asyncio
async def test_nova_domain_reads_every_native_page_before_slicing(admin_client, directory):
    directory.compute.get_endpoint.return_value = "http://nova/v2.1/"
    directory.session.get.side_effect = [
        response(
            {
                "servers": [{"id": "foreign", "tenant_id": "foreign"}],
                "servers_links": [{"rel": "next", "href": "http://untrusted/ignored"}],
            }
        ),
        response({"servers": [{"id": "a1", "tenant_id": "a"}, {"id": "b1", "tenant_id": "b"}]}),
    ]
    result = await admin_client.get("/api/v1/admin/all-instances?domain_id=domain-a&limit=1")
    assert result.status_code == 200
    assert [v["id"] for v in result.json()["items"]] == ["a1"]
    assert result.json()["next_marker"] == "a1"
    assert directory.session.get.call_count == 2
    assert directory.session.get.call_args.kwargs["params"]["marker"] == "foreign"
    assert "untrusted" not in directory.session.get.call_args.args[0]
    assert directory.session.get.call_args.args[0] == "http://nova/v2.1/servers/detail"


@pytest.mark.asyncio
async def test_port_domain_filter_precedes_pagination(admin_client, directory):
    def port(pid, owner):
        return SimpleNamespace(
            id=pid,
            project_id=owner,
            name=pid,
            status="ACTIVE",
            network_id="network",
            device_owner="",
            device_id="",
            mac_address="",
            fixed_ips=[],
        )

    directory.network.ports.return_value = [port("foreign", "foreign"), port("a1", "a"), port("b1", "b")]
    result = await admin_client.get("/api/v1/admin/all-ports?domain_id=domain-a&limit=1")
    assert result.status_code == 200
    assert [v["id"] for v in result.json()["items"]] == ["a1"]
    assert result.json()["next_marker"] == "a1"
    directory.network.ports.assert_called_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route",
    [
        "all-networks",
        "all-routers",
        "all-floating-ips",
        "all-loadbalancers",
        "all-containers",
        "all-file-storages",
        "overview/projects",
    ],
)
async def test_complete_cached_inventory_filtered_after_fresh_directory(admin_client, directory, route):
    rows = [{"id": "outside", "project_id": "foreign"}, {"id": "inside", "project_id": "a"}]
    with patch("app.api.identity.admin.cached_call", AsyncMock(return_value=rows)) as cached:
        result = await admin_client.get(f"/api/v1/admin/{route}?domain_id=domain-a")
    assert result.status_code == 200
    assert result.json() == [rows[1]]
    cached.assert_awaited_once()
    directory.identity.projects.assert_called_once_with(domain_id="domain-a")
    assert rows[0]["id"] == "outside"  # Filtering never mutates the cached all-domain snapshot.


@pytest.mark.asyncio
async def test_volume_status_counts_only_selected_domain(admin_client, directory):
    directory.block_storage.volumes.return_value = [volume("outside", "foreign"), volume("inside")]
    result = await admin_client.get("/api/v1/admin/volumes/status-summary?domain_id=domain-a")
    assert result.status_code == 200
    assert result.json() == {"total": 1, "statuses": [{"status": "available", "count": 1}]}


@pytest.mark.asyncio
async def test_health_counts_all_pages_in_domain(admin_client, directory):
    directory.session.get.return_value = response(
        {
            "servers": [
                {"id": "outside", "tenant_id": "foreign", "status": "ERROR"},
                {"id": "inside", "tenant_id": "a", "status": "ACTIVE"},
            ]
        }
    )
    result = await admin_client.get("/api/v1/admin/instances/health?domain_id=domain-a")
    assert result.status_code == 200
    assert result.json()["total"] == 1
    assert result.json()["active"] == 1
    assert result.json()["error"] == 0


@pytest.mark.asyncio
async def test_project_names_include_native_domain(admin_client, directory):
    result = await admin_client.get("/api/v1/admin/projects/names?domain_id=domain-a&refresh=true")
    assert result.status_code == 200
    assert result.json() == [
        {"id": "a", "name": "duplicate-name", "domain_id": "domain-a"},
        {"id": "b", "name": "duplicate-name", "domain_id": "domain-a"},
    ]


@pytest.mark.asyncio
async def test_project_quota_inventory_filters_by_domain(admin_client, directory):
    with (
        patch("app.api.identity.admin_secrets.get_admin_project_connection", return_value=MagicMock()),
        patch(
            "app.api.identity.admin_secrets.bsvc.list_project_quotas",
            return_value=[
                {"project_id": "foreign"},
                {"project_id": "a"},
            ],
        ),
    ):
        result = await admin_client.get("/api/v1/admin/key-manager/project-quotas?domain_id=domain-a")
    assert result.status_code == 200
    assert result.json() == [{"project_id": "a"}]


@pytest.mark.asyncio
async def test_trove_all_projects_requires_fresh_authority_and_intersection(admin_client, directory):
    with (
        patch("app.api.database.instances.require_admin", AsyncMock()) as guard,
        patch(
            "app.services.trove.list_instances_admin_all_projects",
            return_value=[
                {"id": "outside", "project_id": "foreign"},
                {"id": "inside", "project_id": "a"},
            ],
        ),
    ):
        result = await admin_client.get("/api/v1/database-instances?all_projects=true&domain_id=domain-a")
    assert result.status_code == 200
    assert result.json() == [{"id": "inside", "project_id": "a"}]
    guard.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["database-instances", "object-storage"])
async def test_nonadmin_cannot_supply_inventory_conditions(non_admin_client, url):
    result = await non_admin_client.get(f"/api/v1/{url}?domain_id=domain-a")
    assert result.status_code == 403


@pytest.mark.asyncio
async def test_swift_fanout_selects_only_domain_projects(admin_client, directory):
    from app.api.object_storage import containers

    with (
        patch.object(containers, "require_admin", AsyncMock()) as guard,
        patch(
            "app.services.keystone.list_system_projects",
            return_value=[
                {"id": "a", "name": "A"},
                {"id": "foreign", "name": "F"},
            ],
        ),
        patch("app.services.keystone.get_admin_connection_for_project", return_value=MagicMock()) as connection,
        patch("app.services.swift.list_containers", return_value=[{"name": "bucket"}]),
        patch.object(containers, "_get_deleted_containers", AsyncMock(return_value={})),
    ):
        result = await admin_client.get("/api/v1/object-storage?all_projects=true&domain_id=domain-a")
    assert result.status_code == 200
    assert result.json() == [{"name": "bucket", "project_id": "a", "project_name": "A"}]
    connection.assert_called_once_with("a")
    guard.assert_awaited_once()


@pytest.mark.asyncio
async def test_historical_cluster_timeseries_does_not_claim_domain_scope(admin_client):
    result = await admin_client.get("/api/v1/admin/timeseries/instances?domain_id=domain-a")
    assert result.status_code == 422
    assert result.json()["detail"] == "inventory_timeseries_scope_unsupported"


@pytest.mark.asyncio
async def test_scoped_topology_filters_cached_roots_and_subnets(admin_client, directory):
    rows = {
        "networks": [
            {
                "id": "inside",
                "name": "N",
                "status": "ACTIVE",
                "project_id": "a",
                "subnet_details": [
                    {"id": "owned-subnet", "name": "S", "cidr": "10.0.0.0/24"},
                    {"id": "foreign-subnet", "name": "F", "cidr": "10.1.0.0/24"},
                ],
            },
            {"id": "outside", "name": "N", "status": "ACTIVE", "project_id": "foreign"},
        ],
        "routers": [],
        "instances": [],
        "floating_ips": [],
        "load_balancers": [],
    }
    directory.network.subnets.return_value = [
        SimpleNamespace(id="owned-subnet", project_id="a"),
        SimpleNamespace(id="foreign-subnet", project_id="foreign"),
    ]
    with patch("app.api.identity.admin.cached_call", AsyncMock(return_value=rows)):
        result = await admin_client.get("/api/v1/admin/topology?domain_id=domain-a")
    assert result.status_code == 200
    assert [network["id"] for network in result.json()["networks"]] == ["inside"]
    assert [subnet["id"] for subnet in result.json()["networks"][0]["subnet_details"]] == ["owned-subnet"]
    assert len(rows["networks"][0]["subnet_details"]) == 2


@pytest.mark.asyncio
async def test_image_owner_filter_precedes_page_limit(admin_client, directory):
    def image(iid, owner):
        return SimpleNamespace(
            id=iid,
            name=iid,
            owner=owner,
            properties={},
            status="active",
            size=1,
            min_disk=0,
            min_ram=0,
            disk_format="raw",
            visibility="private",
            created_at=None,
        )

    directory.image.images.return_value = [image("outside", "foreign"), image("inside", "a")]
    with patch("app.api.identity.admin_images.image_verification.enrich", AsyncMock(side_effect=lambda rows: rows)):
        result = await admin_client.get("/api/v1/admin/images?domain_id=domain-a&limit=1")
    assert result.status_code == 200
    assert [item["id"] for item in result.json()["items"]] == ["inside"]


@pytest.mark.asyncio
async def test_failed_directory_precedes_cached_inventory(admin_client, directory):
    directory.identity.projects.side_effect = RuntimeError("unavailable")
    with patch("app.api.identity.admin.cached_call", AsyncMock()) as cached:
        result = await admin_client.get("/api/v1/admin/all-networks?domain_id=domain-a")
    assert result.status_code == 503
    cached.assert_not_awaited()


def test_trove_native_pages_preserve_owning_project(directory):
    from app.services import trove

    directory.database.get.side_effect = [
        response({"instances": [{"id": "one", "tenant_id": "a"}], "links": [{"rel": "next"}]}),
        response({"instances": [{"id": "two", "tenant_id": "b"}]}),
    ]
    rows = trove.list_instances_admin_all_projects(directory)
    assert [row["project_id"] for row in rows] == ["a", "b"]
    assert directory.database.get.call_args.kwargs["params"] == {"marker": "one"}


def test_zun_native_next_pages_preserve_project(directory):
    from app.services import zun

    directory.session.get.side_effect = [
        response({"containers": [{"uuid": "one", "project_id": "a"}], "next": "ignored"}),
        response({"containers": [{"uuid": "two", "project_id": "b"}]}),
    ]
    with patch.object(zun, "_get_zun_endpoint", return_value="http://zun/v1"):
        rows = zun.list_containers_admin(directory)
    assert [row.project_id for row in rows] == ["a", "b"]
    assert directory.session.get.call_args.kwargs["params"] == {"marker": "one"}


def test_manila_native_pages_are_complete(directory):
    from app.services import manila

    native = MagicMock()
    native.get.side_effect = [
        {"shares": [{"id": "one", "project_id": "a"}], "shares_links": [{"rel": "next"}]},
        {"shares": [{"id": "two", "project_id": "b"}]},
    ]
    with (
        patch.object(manila, "get_client", return_value=native),
        patch.object(manila, "_parse_file_storage", side_effect=lambda row: SimpleNamespace(**row)),
    ):
        rows = manila.list_file_storages(directory, all_tenants=True)
    assert [row.id for row in rows] == ["one", "two"]
    assert native.get.call_args.kwargs["params"] == {"all_tenants": "1", "marker": "one"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route,module,provider",
    [
        ("database-instances", "app.api.database.instances", "app.services.trove.list_instances_admin_all_projects"),
        ("object-storage", "app.api.object_storage.containers", "app.services.keystone.list_system_projects"),
    ],
)
async def test_stale_admin_claim_cannot_read_all_project_resources(admin_client, route, module, provider):
    with (
        patch(f"{module}.require_admin", AsyncMock(side_effect=HTTPException(403, "native_authority_revoked"))),
        patch(provider) as inventory,
    ):
        result = await admin_client.get(f"/api/v1/{route}?all_projects=true")
    assert result.status_code == 403
    inventory.assert_not_called()
