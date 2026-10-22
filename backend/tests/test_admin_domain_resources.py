"""Complete native domain attribution, filtering and marker boundaries."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def resource_directory(mock_conn):
    projects = [
        SimpleNamespace(id="a1", name="same-project", domain_id="a"),
        SimpleNamespace(id="a2", name="same-project", domain_id="a"),
        SimpleNamespace(id="a-empty", name="empty", domain_id="a"),
        SimpleNamespace(id="b1", name="same-project", domain_id="b"),
        SimpleNamespace(id="orphan-domain-project", name="old", domain_id="removed"),
    ]
    mock_conn.identity.projects.side_effect = lambda **_: iter(projects)
    mock_conn.identity.domains.side_effect = lambda: iter(
        [
            SimpleNamespace(id="a", name="duplicate"),
            SimpleNamespace(id="b", name="duplicate"),
            SimpleNamespace(id="empty", name="Empty"),
        ]
    )
    mock_conn.identity.get_domain.side_effect = lambda did: (
        SimpleNamespace(id=did) if did in {"a", "b", "empty"} else None
    )
    mock_conn.block_storage.volumes.side_effect = lambda **_: iter([])
    return mock_conn


@pytest.mark.asyncio
async def test_native_missing_domain_is_404_not_directory_outage(admin_client, mock_conn):
    from openstack.exceptions import ResourceNotFound

    mock_conn.identity.get_domain.side_effect = ResourceNotFound("native domain absent")
    response = await admin_client.get("/api/v1/admin/all-instances?domain_id=absent")
    assert response.status_code == 404
    assert response.json()["detail"] == "inventory_domain_not_found"


def server(sid, project_id, **kwargs):
    return {
        "id": sid,
        "name": sid,
        "tenant_id": project_id,
        "user_id": "foreign-home-human",
        "status": "ACTIVE",
        "flavor": {"original_name": "cpu", "vcpus": 2, "ram": 4096},
        **kwargs,
    }


def volume(vid, project_id="a1", size=10, status="available", **kwargs):
    return SimpleNamespace(
        id=vid,
        name=kwargs.pop("name", vid),
        project_id=project_id,
        size=size,
        status=status,
        volume_type=kwargs.pop("volume_type", "ssd"),
        created_at=None,
        attachments=kwargs.pop("attachments", []),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_domain_overview_counts_all_projects_zero_domains_and_distinct_unknowns(admin_client, resource_directory):
    rows = [
        server("3", "a1"),
        server("1", "a2"),
        server("2", "b1"),
        server("4", "deleted"),
        server("5", None),
        server("6", "orphan-domain-project"),
    ]
    resource_directory.block_storage.volumes.side_effect = lambda **_: iter(
        [
            volume("v1", "a1", 10),
            volume("v2", "a2", 20, "in-use"),
            volume("v3", "b1", 40),
        ]
    )
    with patch("app.services.openstack_inventory.list_servers_complete", return_value=rows):
        response = await admin_client.get("/api/v1/admin/overview/domains")
    assert response.status_code == 200
    groups = response.json()
    a = next(row for row in groups if row["domain_id"] == "a")
    b = next(row for row in groups if row["domain_id"] == "b")
    assert a["domain_name"] == b["domain_name"] == "duplicate"
    assert (a["project_count"], a["instances"], a["vcpus"], a["ram_mb"]) == (3, 2, 4, 8192)
    assert (a["volumes"], a["volume_gb"], a["attached_gb"], a["available_gb"]) == (2, 30, 20, 10)
    assert next(row for row in groups if row["domain_id"] == "empty")["instances"] == 0
    assert next(row for row in groups if row["owner_status"] == "deleted_project")["project_ids"] == ["deleted"]
    assert next(row for row in groups if row["owner_status"] == "unknown_owner")["project_ids"] == []
    assert next(row for row in groups if row["owner_status"] == "deleted_domain")["domain_id"] == "removed"


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["overview/domains", "all-instances", "all-volumes", "volumes/status-summary"])
async def test_directory_outage_is_unavailable_never_zero(admin_client, resource_directory, route):
    resource_directory.identity.domains.side_effect = RuntimeError("private directory failure")
    response = await admin_client.get(f"/api/v1/admin/{route}")
    assert response.status_code == 503
    assert response.json()["detail"] == "inventory_directory_unavailable"


@pytest.mark.asyncio
async def test_domain_overview_missing_flavor_capacity_is_not_zero(admin_client, resource_directory):
    with patch(
        "app.services.openstack_inventory.list_servers_complete",
        return_value=[server("vm", "a1", flavor={"id": "removed-flavor"})],
    ):
        response = await admin_client.get("/api/v1/admin/overview/domains?domain_id=a")
    assert response.status_code == 200
    assert response.json()[0]["vcpus"] is None
    assert response.json()[0]["ram_mb"] is None


@pytest.mark.asyncio
async def test_instance_full_text_domain_intersection_precedes_stable_marker(admin_client, resource_directory):
    rows = [
        server("z-match", "a2"),
        server("outside-match", "b1"),
        server("a-match", "a1"),
        server("not-selected", "a1"),
    ]
    with patch("app.services.openstack_inventory.list_servers_complete", return_value=rows):
        first = await admin_client.get("/api/v1/admin/all-instances?domain_id=a&name=match&limit=1")
        second = await admin_client.get("/api/v1/admin/all-instances?domain_id=a&name=match&limit=1&marker=a-match")
        incompatible = await admin_client.get("/api/v1/admin/all-instances?domain_id=a&project_id=b1")
        invalid_marker = await admin_client.get("/api/v1/admin/all-instances?domain_id=a&marker=outside-match")
    assert first.status_code == second.status_code == 200
    assert [row["id"] for row in first.json()["items"]] == ["a-match"]
    assert first.json()["next_marker"] == "a-match"
    assert [row["id"] for row in second.json()["items"]] == ["z-match"]
    assert second.json()["items"][0]["domain_id"] == "a"
    assert second.json()["next_marker"] is None
    assert incompatible.json()["items"] == []
    assert invalid_marker.status_code == 400


@pytest.mark.asyncio
async def test_volume_summary_is_complete_but_filter_totals_match_full_filtered_inventory(
    admin_client, resource_directory
):
    rows = [
        volume("z-match", "a2", 20),
        volume("a-match", "a1", 10),
        volume("outside-match", "b1", 80),
        volume("hdd", "a1", 40, volume_type="hdd"),
    ]
    resource_directory.block_storage.volumes.side_effect = lambda **_: iter(rows)
    query = "domain_id=a&name=match&volume_type=ssd&min_size=10&max_size=20"
    summary = await admin_client.get(f"/api/v1/admin/volumes/status-summary?{query}")
    first = await admin_client.get(f"/api/v1/admin/all-volumes?{query}&limit=1")
    second = await admin_client.get(f"/api/v1/admin/all-volumes?{query}&limit=1&marker=a-match")
    assert summary.status_code == first.status_code == second.status_code == 200
    assert (summary.json()["total"], summary.json()["total_gb"]) == (3, 70)
    assert (summary.json()["filtered_total"], summary.json()["filtered_gb"]) == (2, 30)
    assert summary.json()["domains"][0]["project_count"] == 3
    assert [v["id"] for v in first.json()["items"]] == ["a-match"]
    assert [v["id"] for v in second.json()["items"]] == ["z-match"]
    assert second.json()["items"][0]["volume_type"] == "ssd"
    assert (await admin_client.get("/api/v1/admin/all-volumes?min_size=20&max_size=10")).status_code == 422


@pytest.mark.asyncio
async def test_hypervisor_vm_uses_project_owner_and_native_flavor_uuid_fallback(admin_client, resource_directory):
    resource_directory.compute.get_endpoint.return_value = "http://nova"
    resource_directory.compute.flavors.return_value = []
    response = MagicMock()
    response.json.return_value = {"hypervisor": {}, "inventories": {}}
    resource_directory.session.get.return_value = response
    with (
        patch(
            "app.api.identity.admin.nova_hosts.get_hypervisor",
            return_value={"id": "host", "hypervisor_hostname": "host"},
        ),
        patch(
            "app.api.identity.admin.nova_hosts.get_compute_service",
            return_value={"id": "svc", "host": "host", "status": "enabled"},
        ),
        patch(
            "app.api.identity.admin.nova_hosts.host_servers",
            return_value=[server("vm", "a2", flavor={"id": "removed-flavor"}, **{"OS-EXT-SRV-ATTR:host": "host"})],
        ),
    ):
        result = await admin_client.get("/api/v1/admin/hypervisors/host")
    assert result.status_code == 200
    vm = result.json()["servers"][0]
    assert (vm["domain_id"], vm["project_id"], vm["project_name"]) == ("a", "a2", "same-project")
    assert vm["flavor"] == vm["flavor_id"] == "removed-flavor"
    assert vm["flavor_name"] is None
