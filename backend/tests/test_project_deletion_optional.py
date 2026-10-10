"""Optional-service deletion gates through the real FastAPI error boundary.

Core pagination/native SDK transport is covered by test_project_deletion.py.
Here provider responses model each optional REST envelope and its own paging
protocol; no collector or endpoint is patched into returning an empty report.
"""

import json
from urllib.parse import urlparse

import pytest
from requests import Response

_TARGET = "target-project"
_SECRET = "never-expose-provider-payload"
_RAW = {
    "shares": ("shared_file_system", "/shares/detail", "shares"),
    "share_snapshots": ("shared_file_system", "/snapshots/detail", "snapshots"),
    "share_networks": ("shared_file_system", "/share-networks/detail", "share_networks"),
    "security_services": ("shared_file_system", "/security-services/detail", "security_services"),
    "secrets": ("key_manager", "/secrets", "secrets"),
    "secret_containers": ("key_manager", "/containers", "containers"),
    "secret_orders": ("key_manager", "/orders", "orders"),
    "database_instances": ("database", "/mgmt/instances", "instances"),
    "database_backups": ("database", "/backups", "backups"),
    "database_configurations": ("database", "/configurations", "configurations"),
    "containers": ("session", "/v1/containers", "containers"),
    "clusters": ("container_infrastructure_management", "/clusters/detail", "clusters"),
    "cluster_templates": ("container_infrastructure_management", "/clustertemplates", "clustertemplates"),
    "stacks": ("orchestration", "/stacks", "stacks"),
}
_OPTIONAL = ("load_balancers", "object_containers", *_RAW)


def _response(body, status=200):
    response = Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    return response


@pytest.fixture
def optional_inventory(mock_conn):
    """All catalog-present optional services, a verified token, and empty reads."""
    for proxy, methods in (
        (mock_conn.compute, ("servers",)),
        (mock_conn.block_storage, ("volumes", "snapshots", "backups")),
        (mock_conn.network, ("networks", "subnets", "routers", "ports", "ips", "security_groups")),
        (mock_conn.image, ("images",)),
    ):
        for method in methods:
            getattr(proxy, method).side_effect = lambda **kwargs: iter([])
    mock_conn.compute.get.side_effect = lambda *args, **kwargs: _response({"server_groups": []})
    mock_conn.current_project_id = _TARGET
    catalog = [
        {"type": service, "endpoints": []}
        for service in (
            "load-balancer",
            "sharev2",
            "object-store",
            "key-manager",
            "database",
            "container",
            "container-infra",
            "orchestration",
        )
    ]
    mock_conn.session.auth.get_access.return_value.service_catalog.catalog = catalog
    access = mock_conn.session.auth.get_access.return_value
    access.role_names = ["admin"]
    access.is_admin_project = True
    mock_conn.session.get_endpoint.return_value = "https://zun.example/v1"
    mock_conn.object_store.get_endpoint.return_value = f"https://swift.example/v1/AUTH_{_TARGET}"
    mock_conn.database.get_endpoint.return_value = f"https://trove.example/v1.0/{_TARGET}"
    mock_conn.orchestration.get_endpoint.return_value = f"https://heat.example/v1/{_TARGET}"
    rows = {kind: [] for kind in _OPTIONAL}
    failure = {"kind": None}

    def iterate(kind):
        for index, row in enumerate(rows[kind]):
            if failure["kind"] == kind and index == 2:
                raise RuntimeError(_SECRET)
            yield row.copy()

    mock_conn.load_balancer.load_balancers.side_effect = lambda **kwargs: iterate("load_balancers")
    mock_conn.object_store.containers.side_effect = lambda **kwargs: iterate("object_containers")

    def page(proxy_name, path, **kwargs):
        path = urlparse(path).path
        kind, (_, _, key) = next(
            (kind, spec) for kind, spec in _RAW.items() if spec[0] == proxy_name and spec[1] == path
        )
        params = kwargs["params"]
        provider_rows = rows[kind]
        if kind == "database_backups":
            if not params.get("all_projects"):
                provider_rows = [row for row in provider_rows if row.get("project_id") == mock_conn.current_project_id]
            if params.get("project_id"):
                provider_rows = [row for row in provider_rows if row.get("project_id") in (params["project_id"], None)]
        if kind == "stacks":
            if params.get("global_tenant"):
                # Heat's stacks:global_index default is deny_everybody.
                return _response({"error": {"message": _SECRET}}, 403)
            if not ("admin" in access.role_names and access.is_admin_project):
                provider_rows = [
                    {k: v for k, v in row.items() if k != "project"}
                    for row in provider_rows
                    if row.get("project") == mock_conn.current_project_id
                ]
            if params.get("tenant"):
                provider_rows = [row for row in provider_rows if row.get("project") in (params["tenant"], None)]
            if not params.get("show_nested"):
                provider_rows = [row for row in provider_rows if not row.get("nested")]
            if not params.get("show_hidden"):
                provider_rows = [row for row in provider_rows if not row.get("hidden")]
        offset = int(params.get("offset", 0))
        marker = params.get("marker")
        if marker:
            offset = next(index + 1 for index, row in enumerate(provider_rows) if row["id"] == marker)
        if failure["kind"] == kind and offset >= 2:
            raise RuntimeError(_SECRET)
        return _response({key: provider_rows[offset : offset + 2]})

    for proxy_name in {spec[0] for spec in _RAW.values()}:
        getattr(mock_conn, proxy_name).get.side_effect = lambda path, proxy_name=proxy_name, **kwargs: page(
            proxy_name, path, **kwargs
        )
    return rows, failure


def _resource(kind, index, owner=_TARGET):
    return {
        "id": f"{kind}-{index}",
        "name": f"resource-{index}",
        "status": "ERROR" if index % 2 else "STOPPED",
        "project" if kind == "stacks" else "project_id": owner,
        "deleted": "0",
        "password": _SECRET,
        "payload": _SECRET,
    }


def _kind(check, kind):
    return next(item for item in check["resources"] if item["kind"] == kind)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", _OPTIONAL)
async def test_catalog_present_owned_optional_resources_block_delete(admin_client, mock_conn, optional_inventory, kind):
    rows, _ = optional_inventory
    rows[kind] = [_resource(kind, index) for index in range(3)]
    response = await admin_client.get(f"/api/v1/admin/projects/{_TARGET}/deletion-check")
    assert response.status_code == 200
    check = response.json()
    assert not check["can_delete"]
    assert _kind(check, kind)["status"] == "ok"
    assert _kind(check, kind)["count"] == 3
    assert len(_kind(check, kind)["samples"]) == 3
    assert _SECRET not in response.text
    response = await admin_client.delete(f"/api/v1/admin/projects/{_TARGET}")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "project_has_resources"
    assert _kind(response.json()["detail"]["check"], kind)["count"] == 3
    mock_conn.identity.delete_project.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", _OPTIONAL)
async def test_optional_later_page_failure_is_unknown_not_partial_count(
    admin_client, mock_conn, optional_inventory, kind
):
    rows, failure = optional_inventory
    rows[kind] = [_resource(kind, index) for index in range(3)]
    failure["kind"] = kind
    response = await admin_client.delete(f"/api/v1/admin/projects/{_TARGET}")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "project_resource_check_failed"
    resource = _kind(detail["check"], kind)
    assert resource["status"] == "unavailable"
    assert resource["count"] is None
    assert resource["samples"] == []
    assert not detail["check"]["can_delete"]
    assert _SECRET not in response.text
    mock_conn.identity.delete_project.assert_not_called()


@pytest.mark.asyncio
async def test_catalog_present_foreign_optional_resources_do_not_block(admin_client, mock_conn, optional_inventory):
    rows, _ = optional_inventory
    for kind in _OPTIONAL:
        rows[kind] = [_resource(kind, index, owner="foreign-project") for index in range(3)]
    response = await admin_client.get(f"/api/v1/admin/projects/{_TARGET}/deletion-check")
    assert response.status_code == 200
    assert response.json()["can_delete"]
    assert all(resource["count"] == 0 for resource in response.json()["resources"])
    response = await admin_client.delete(f"/api/v1/admin/projects/{_TARGET}")
    assert response.status_code == 204
    mock_conn.identity.delete_project.assert_called_once_with(_TARGET, ignore_missing=True)


@pytest.mark.asyncio
async def test_wrong_token_scope_never_proves_optional_empty(admin_client, mock_conn, optional_inventory):
    mock_conn.current_project_id = "caller-project"
    response = await admin_client.delete(f"/api/v1/admin/projects/{_TARGET}")
    assert response.status_code == 503
    check = response.json()["detail"]["check"]
    for kind in ("object_containers", "secrets", "secret_containers", "secret_orders"):
        assert _kind(check, kind)["reason"] == "project_scope_unverified"
    for kind in ("database_backups", "database_configurations", "clusters", "cluster_templates", "stacks"):
        assert _kind(check, kind)["status"] == "ok"
        assert _kind(check, kind)["count"] == 0
    mock_conn.identity.delete_project.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "proxy_name,kind,endpoint",
    (("object_store", "object_containers", "https://swift.example/v1/AUTH_foreign-project"),),
)
async def test_wrong_account_endpoint_never_proves_empty(
    admin_client, mock_conn, optional_inventory, proxy_name, kind, endpoint
):
    getattr(mock_conn, proxy_name).get_endpoint.return_value = endpoint
    response = await admin_client.delete(f"/api/v1/admin/projects/{_TARGET}")
    assert response.status_code == 503
    assert _kind(response.json()["detail"]["check"], kind)["reason"] == "project_scope_unverified"
    mock_conn.identity.delete_project.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    (
        "database_instances",
        "database_backups",
        "database_configurations",
        "clusters",
        "cluster_templates",
        "stacks",
    ),
)
async def test_admin_home_scope_checks_target_optional_allocations_and_final_race(
    admin_client,
    mock_conn,
    optional_inventory,
    kind,
):
    rows, _ = optional_inventory
    mock_conn.current_project_id = "admin-project"
    mock_conn.session.auth.get_access.return_value.service_catalog.catalog = [
        {"type": service, "endpoints": []} for service in ("database", "container-infra", "orchestration")
    ]
    rows[kind] = [_resource(kind, index, owner="foreign-project") for index in range(3)]
    preflight = await admin_client.get(f"/api/v1/admin/projects/{_TARGET}/deletion-check")
    assert preflight.status_code == 200
    assert preflight.json()["can_delete"]
    assert _kind(preflight.json(), kind)["count"] == 0
    rows[kind].extend(_resource(kind, index) for index in range(3, 6))
    response = await admin_client.delete(f"/api/v1/admin/projects/{_TARGET}")
    assert response.status_code == 409
    check = response.json()["detail"]["check"]
    assert not check["can_delete"]
    resource = _kind(check, kind)
    assert resource["status"] == "ok"
    assert resource["count"] == 3
    assert [sample["id"] for sample in resource["samples"]] == [f"{kind}-{index}" for index in range(3, 6)]
    mock_conn.identity.delete_project.assert_not_called()


@pytest.mark.asyncio
async def test_trove_admin_configuration_without_owner_cannot_inherit_token_project(
    admin_client,
    mock_conn,
    optional_inventory,
):
    rows, _ = optional_inventory
    rows["database_configurations"] = [{"id": "configuration-without-owner", "name": "shared-defaults"}]
    response = await admin_client.delete(f"/api/v1/admin/projects/{_TARGET}")
    assert response.status_code == 503
    resource = _kind(response.json()["detail"]["check"], "database_configurations")
    assert resource["reason"] == "resource_ownership_unverified"
    assert resource["count"] is None
    mock_conn.identity.delete_project.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,reference",
    (
        ("secrets", "secret_ref"),
        ("secret_containers", "container_ref"),
        ("secret_orders", "order_ref"),
    ),
)
async def test_barbican_token_scope_and_safe_reference_samples(
    admin_client,
    mock_conn,
    optional_inventory,
    kind,
    reference,
):
    rows, _ = optional_inventory
    rows[kind] = [
        {
            reference: "https://barbican.example/v1/resources/resource-uuid",
            "name": "key-material",
            "status": "ACTIVE",
            "payload": _SECRET,
        }
    ]
    response = await admin_client.delete(f"/api/v1/admin/projects/{_TARGET}")
    assert response.status_code == 409
    resource = _kind(response.json()["detail"]["check"], kind)
    assert resource["count"] == 1
    assert resource["samples"] == [{"id": "resource-uuid", "name": "key-material", "status": "ACTIVE"}]
    assert "barbican.example" not in response.text
    assert _SECRET not in response.text
    mock_conn.identity.delete_project.assert_not_called()


@pytest.mark.asyncio
async def test_swift_native_container_name_is_counted_without_owner_field(
    admin_client,
    mock_conn,
    optional_inventory,
):
    rows, _ = optional_inventory
    rows["object_containers"] = [{"name": "trash_segments", "count": 0, "bytes": 0}]
    response = await admin_client.delete(f"/api/v1/admin/projects/{_TARGET}")
    assert response.status_code == 409
    resource = _kind(response.json()["detail"]["check"], "object_containers")
    assert resource["count"] == 1
    assert resource["samples"] == [{"id": "trash_segments", "name": "trash_segments"}]
    mock_conn.identity.delete_project.assert_not_called()


@pytest.mark.asyncio
async def test_shared_cluster_template_missing_owner_is_unknown(
    admin_client,
    mock_conn,
    optional_inventory,
):
    rows, _ = optional_inventory
    rows["cluster_templates"] = [{"uuid": "shared-template", "name": "shared", "public": True}]
    response = await admin_client.delete(f"/api/v1/admin/projects/{_TARGET}")
    assert response.status_code == 503
    resource = _kind(response.json()["detail"]["check"], "cluster_templates")
    assert resource["reason"] == "resource_ownership_unverified"
    assert resource["count"] is None
    mock_conn.identity.delete_project.assert_not_called()


@pytest.mark.asyncio
async def test_heat_nested_stacks_are_not_hidden_from_deletion_inventory(
    admin_client,
    mock_conn,
    optional_inventory,
):
    rows, _ = optional_inventory
    rows["stacks"] = [{**_resource("stacks", 0), "nested": True, "hidden": True}]
    response = await admin_client.delete(f"/api/v1/admin/projects/{_TARGET}")
    assert response.status_code == 409
    assert _kind(response.json()["detail"]["check"], "stacks")["count"] == 1
    mock_conn.identity.delete_project.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_owned_default_named_groups_cannot_all_be_exempted(
    admin_client,
    mock_conn,
    optional_inventory,
):
    mock_conn.network.security_groups.side_effect = lambda **kwargs: iter(
        [
            {"id": "automatic-default", "name": "default", "project_id": _TARGET},
            {"id": "custom-default", "name": "default", "project_id": _TARGET},
        ]
    )
    response = await admin_client.delete(f"/api/v1/admin/projects/{_TARGET}")
    assert response.status_code == 503
    resource = _kind(response.json()["detail"]["check"], "security_groups")
    assert resource["status"] == "unavailable"
    assert resource["reason"] == "resource_ownership_unverified"
    mock_conn.identity.delete_project.assert_not_called()
