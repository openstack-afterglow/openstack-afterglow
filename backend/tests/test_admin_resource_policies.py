from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.api.identity import admin_resource_policies


def _admin_conn():
    return SimpleNamespace(close=lambda: None)


@pytest.mark.asyncio
async def test_resource_policy_routes_require_admin(non_admin_client):
    response = await non_admin_client.get("/api/v1/admin/resource-policies")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_resource_policy_catalog_uses_backend_admin_connection(admin_client, monkeypatch):
    admin_conn = _admin_conn()

    async def discover(conn, key):
        assert conn is admin_conn
        assert key == "builder.flavor"
        return [{"id": "flavor-1", "name": "builder"}]

    monkeypatch.setattr(admin_resource_policies, "get_admin_project_connection", lambda: admin_conn)
    monkeypatch.setattr(admin_resource_policies.resource_policies, "discover_options", discover)

    response = await admin_client.get("/api/v1/admin/resource-policies/catalog/builder.flavor")

    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "builder.flavor"
    assert body["resource_kind"] == "flavor"
    assert body["execution_scope"] == "service"
    assert body["options"] == [{"id": "flavor-1", "name": "builder"}]


@pytest.mark.asyncio
async def test_resource_policy_list_merges_waygate_service_and_filters_local_duplicates(admin_client, monkeypatch):
    async def inspect(_conn):
        return [
            {"key": "builder.flavor", "state": "configured"},
            {"key": "waygate.image", "state": "stale-local"},
        ]

    async def remote(service_type, _request, upstream_path):
        assert service_type == "waygate"
        assert upstream_path == "/v1/admin/resource-policies"
        return [{"key": "waygate.image", "state": "configured"}]

    monkeypatch.setattr(admin_resource_policies, "get_admin_project_connection", _admin_conn)
    monkeypatch.setattr(admin_resource_policies.store, "inspect_policies", inspect)
    monkeypatch.setattr(admin_resource_policies, "get_json", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=True, service_k3s_enabled=False),
    )

    response = await admin_client.get("/api/v1/admin/resource-policies")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "policies": [
            {"key": "builder.flavor", "state": "configured"},
            {"key": "waygate.image", "state": "configured"},
        ],
        "errors": [],
    }


@pytest.mark.asyncio
async def test_resource_policy_list_merges_drover_service_and_filters_local_duplicates(admin_client, monkeypatch):
    async def inspect(_conn):
        return [
            {"key": "builder.flavor", "state": "configured"},
            {"key": "k3s.server_image", "state": "stale-local"},
        ]

    async def remote(service_type, _request, upstream_path):
        assert service_type == "drover"
        assert upstream_path == "/v1/admin/resource-policies"
        return [{"key": "k3s.server_image", "state": "configured"}]

    monkeypatch.setattr(admin_resource_policies, "get_admin_project_connection", _admin_conn)
    monkeypatch.setattr(admin_resource_policies.store, "inspect_policies", inspect)
    monkeypatch.setattr(admin_resource_policies, "get_json", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=False, service_k3s_enabled=True),
    )

    response = await admin_client.get("/api/v1/admin/resource-policies")

    assert response.status_code == 200
    assert response.json() == {
        "policies": [
            {"key": "builder.flavor", "state": "configured"},
            {"key": "k3s.server_image", "state": "configured"},
        ],
        "errors": [],
    }


@pytest.mark.asyncio
async def test_drover_policy_catalog_proxies_without_backend_admin_connection(admin_client, monkeypatch):
    async def remote(service_type, _request, upstream_path):
        assert service_type == "drover"
        assert upstream_path == "/v1/admin/resource-policies/catalog/k3s.server_image"
        return {"key": "k3s.server_image", "options": []}

    monkeypatch.setattr(
        admin_resource_policies,
        "get_admin_project_connection",
        lambda: pytest.fail("Drover policy must not open the Afterglow admin connection"),
    )
    monkeypatch.setattr(admin_resource_policies, "get_json", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=False, service_k3s_enabled=True),
    )

    response = await admin_client.get("/api/v1/admin/resource-policies/catalog/k3s.server_image")

    assert response.status_code == 200
    assert response.json() == {"key": "k3s.server_image", "options": []}


@pytest.mark.asyncio
async def test_drover_policy_update_proxies_to_service(admin_client, monkeypatch):
    observed = {}

    async def remote(service_type, request, upstream_path):
        observed.update(service_type=service_type, upstream_path=upstream_path, body=await request.json())
        return JSONResponse({"key": "k3s.server_image", "resource_id": "image-1"})

    monkeypatch.setattr(admin_resource_policies, "proxy", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=False, service_k3s_enabled=True),
    )

    response = await admin_client.put(
        "/api/v1/admin/resource-policies/k3s.server_image",
        json={"resource_id": "image-1"},
    )

    assert response.status_code == 200
    assert response.json() == {"key": "k3s.server_image", "resource_id": "image-1"}
    assert observed == {
        "service_type": "drover",
        "upstream_path": "/v1/admin/resource-policies/k3s.server_image",
        "body": {"resource_id": "image-1"},
    }


@pytest.mark.asyncio
async def test_waygate_policy_catalog_proxies_without_backend_admin_connection(admin_client, monkeypatch):
    async def remote(service_type, _request, upstream_path):
        assert service_type == "waygate"
        assert upstream_path == "/v1/admin/resource-policies/catalog/waygate.image"
        return {"key": "waygate.image", "options": []}

    monkeypatch.setattr(
        admin_resource_policies,
        "get_admin_project_connection",
        lambda: pytest.fail("Waygate policy must not open the Afterglow admin connection"),
    )
    monkeypatch.setattr(admin_resource_policies, "get_json", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=True, service_k3s_enabled=False),
    )

    response = await admin_client.get("/api/v1/admin/resource-policies/catalog/waygate.image")

    assert response.status_code == 200
    assert response.json() == {"key": "waygate.image", "options": []}


@pytest.mark.asyncio
async def test_waygate_policy_update_proxies_to_service(admin_client, monkeypatch):
    observed = {}

    async def remote(service_type, request, upstream_path):
        observed.update(service_type=service_type, upstream_path=upstream_path, body=await request.json())
        return JSONResponse({"key": "waygate.image", "resource_id": "image-1"})

    monkeypatch.setattr(admin_resource_policies, "proxy", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=True, service_k3s_enabled=False),
    )

    response = await admin_client.put(
        "/api/v1/admin/resource-policies/waygate.image",
        json={"resource_id": "image-1"},
    )

    assert response.status_code == 200
    assert response.json() == {"key": "waygate.image", "resource_id": "image-1"}
    assert observed == {
        "service_type": "waygate",
        "upstream_path": "/v1/admin/resource-policies/waygate.image",
        "body": {"resource_id": "image-1"},
    }


@pytest.mark.asyncio
async def test_resource_policy_update_validates_then_persists(admin_client, monkeypatch):
    saved = {}

    async def set_policy(**kwargs):
        saved.update(kwargs)
        return {"key": kwargs["key"], "resource_id": kwargs["resource_id"]}

    monkeypatch.setattr(admin_resource_policies, "get_admin_project_connection", _admin_conn)
    monkeypatch.setattr(admin_resource_policies.store, "set_policy", set_policy)

    response = await admin_client.put(
        "/api/v1/admin/resource-policies/builder.flavor",
        json={"resource_id": "flavor-1"},
    )

    assert response.status_code == 200
    assert response.json() == {"key": "builder.flavor", "resource_id": "flavor-1"}
    assert saved["key"] == "builder.flavor"
    assert saved["resource_id"] == "flavor-1"
    assert saved["updated_by_user_id"]


@pytest.mark.asyncio
async def test_runtime_settings_persist_typed_values(admin_client, monkeypatch):
    saved = {}

    async def list_runtime_settings():
        return [{"key": "notion.sync_enabled", "value": True, "state": "configured"}]

    async def set_runtime_setting(**kwargs):
        saved.update(kwargs)
        return {"key": kwargs["key"], "value": kwargs["value"]}

    monkeypatch.setattr(admin_resource_policies.store, "list_runtime_settings", list_runtime_settings)
    monkeypatch.setattr(admin_resource_policies.store, "set_runtime_setting", set_runtime_setting)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=False, service_k3s_enabled=False),
    )

    response = await admin_client.get("/api/v1/admin/runtime-settings")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "settings": [{"key": "notion.sync_enabled", "value": True, "state": "configured"}],
        "errors": [],
    }

    response = await admin_client.put("/api/v1/admin/runtime-settings/notion.sync_enabled", json={"value": False})
    assert response.status_code == 200
    assert response.json() == {"key": "notion.sync_enabled", "value": False}
    assert saved["key"] == "notion.sync_enabled"
    assert saved["value"] is False


@pytest.mark.asyncio
async def test_runtime_settings_merge_and_update_drover_k3s_version(admin_client, monkeypatch):
    async def local_settings():
        return [
            {"key": "notion.sync_enabled", "value": True, "state": "configured"},
            {"key": "k3s.version", "value": "stale-local", "state": "configured"},
        ]

    async def remote_json(service_type, _request, upstream_path):
        assert service_type == "drover"
        assert upstream_path == "/v1/admin/runtime-settings"
        return [{"key": "k3s.version", "value": "v1.31.5+k3s1", "state": "configured"}]

    observed = {}

    async def remote_proxy(service_type, request, upstream_path):
        observed.update(service_type=service_type, upstream_path=upstream_path, body=await request.json())
        return JSONResponse({"key": "k3s.version", "value": "v1.31.6+k3s1"})

    monkeypatch.setattr(admin_resource_policies.store, "list_runtime_settings", local_settings)
    monkeypatch.setattr(admin_resource_policies, "get_json", remote_json)
    monkeypatch.setattr(admin_resource_policies, "proxy", remote_proxy)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=False, service_k3s_enabled=True),
    )

    response = await admin_client.get("/api/v1/admin/runtime-settings")
    assert response.status_code == 200
    assert response.json() == {
        "settings": [
            {"key": "notion.sync_enabled", "value": True, "state": "configured"},
            {"key": "k3s.version", "value": "v1.31.5+k3s1", "state": "configured"},
        ],
        "errors": [],
    }

    response = await admin_client.put(
        "/api/v1/admin/runtime-settings/k3s.version",
        json={"value": "v1.31.6+k3s1"},
    )
    assert response.status_code == 200
    assert response.json() == {"key": "k3s.version", "value": "v1.31.6+k3s1"}
    assert observed == {
        "service_type": "drover",
        "upstream_path": "/v1/admin/runtime-settings/k3s.version",
        "body": {"value": "v1.31.6+k3s1"},
    }


@pytest.mark.asyncio
async def test_runtime_settings_require_admin(non_admin_client):
    response = await non_admin_client.get("/api/v1/admin/runtime-settings")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_batch_catalog_requires_admin(non_admin_client):
    response = await non_admin_client.get(
        "/api/v1/admin/resource-policies/catalog", params=[("keys", "nova.default_network")]
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_batch_catalog_bounds_keys(admin_client):
    response = await admin_client.get(
        "/api/v1/admin/resource-policies/catalog", params=[("keys", "nova.default_network")] * 33
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_batch_catalog_preserves_scope_metadata_and_partial_errors(admin_client, monkeypatch):
    from unittest.mock import MagicMock

    conn = _admin_conn()
    connect = MagicMock(return_value=conn)
    monkeypatch.setattr(admin_resource_policies, "get_admin_project_connection", connect)
    local_keys = ["nova.default_network", "manila.nfs_share_type", "unknown"]

    async def discover(actual_conn, keys):
        assert actual_conn is conn
        assert keys == local_keys
        return {
            "nova.default_network": [{"id": "shared", "name": "Shared"}],
            "manila.nfs_share_type": RuntimeError("private URL token body"),
            "unknown": admin_resource_policies.resource_policies.ResourcePolicyValidationError("unknown"),
        }

    monkeypatch.setattr(admin_resource_policies.resource_policies, "discover_options_batch", discover)
    keys = local_keys
    response = await admin_client.get(
        "/api/v1/admin/resource-policies/catalog",
        params=[("keys", key) for key in [*keys, "nova.default_network"]],
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    catalogs = response.json()["catalogs"]
    assert [row["key"] for row in catalogs] == keys
    by_key = {row["key"]: row for row in catalogs}
    assert by_key["nova.default_network"]["execution_scope"] == "tenant"
    assert by_key["nova.default_network"]["constraints"]["shared_only"] is True
    assert by_key["manila.nfs_share_type"]["error"]["status"] == 503
    assert by_key["unknown"]["error"]["status"] == 404
    assert "private" not in response.text
    connect.assert_called_once()


@pytest.mark.asyncio
async def test_local_batch_rejects_remote_keys_without_upstream_or_admin_discovery(admin_client, monkeypatch):
    monkeypatch.setattr(
        admin_resource_policies,
        "get_admin_project_connection",
        lambda: pytest.fail("remote catalog must retain native service authority"),
    )
    monkeypatch.setattr(
        admin_resource_policies,
        "get_json",
        lambda *_args: pytest.fail("local batch must not forward its query to remote catalogs"),
    )
    response = await admin_client.get(
        "/api/v1/admin/resource-policies/catalog", params=[("keys", "waygate.image"), ("keys", "k3s.server_image")]
    )
    assert response.status_code == 200
    assert [row["error"]["status"] for row in response.json()["catalogs"]] == [404, 404]


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_service", ["waygate", "drover"])
@pytest.mark.parametrize("status", [503, 401, 403])
async def test_resource_policy_list_preserves_independent_rows_on_native_failure(
    admin_client, monkeypatch, failed_service, status
):
    local = {"key": "builder.flavor", "resource_id": "builder-small", "state": "configured"}
    native = {
        "drover": {"key": "k3s.server_image", "resource_id": "k3s-image", "state": "configured"},
        "waygate": {"key": "waygate.image", "resource_id": "waygate-image", "state": "configured"},
    }
    observed = []

    async def inspect(_conn):
        return [
            local,
            {"key": "k3s.server_image", "resource_id": "obsolete-local"},
            {"key": "waygate.image", "resource_id": "obsolete-local"},
        ]

    async def remote(service, request, path):
        observed.append(service)
        assert request.headers["x-auth-token"] == "test-token"
        assert request.headers["x-project-id"] == "test-project-123"
        assert path == "/v1/admin/resource-policies"
        if service == failed_service:
            raise HTTPException(
                status_code=status,
                detail={"message": "private-native-detail", "url": "https://private-native", "token": "secret"},
                headers={"X-Native-Secret": "secret"},
            )
        return [native[service]]

    monkeypatch.setattr(admin_resource_policies, "get_admin_project_connection", _admin_conn)
    monkeypatch.setattr(admin_resource_policies.store, "inspect_policies", inspect)
    monkeypatch.setattr(admin_resource_policies, "get_json", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=True, service_k3s_enabled=True),
    )

    response = await admin_client.get("/api/v1/admin/resource-policies")

    healthy_service = "drover" if failed_service == "waygate" else "waygate"
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "x-native-secret" not in response.headers
    assert response.json() == {
        "policies": [local, native[healthy_service]],
        "errors": [{"service": failed_service, "status": status}],
    }
    assert observed == ["drover", "waygate"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_service", ["waygate", "drover"])
@pytest.mark.parametrize("malformed", [{"policies": []}, None, "not-a-list"])
async def test_resource_policy_list_localizes_malformed_native_response(
    admin_client, monkeypatch, failed_service, malformed
):
    local = {"key": "nova.default_network", "resource_id": "private-net", "state": "configured"}
    native = {
        "drover": {"key": "k3s.server_image", "resource_id": "k3s-image", "state": "configured"},
        "waygate": {"key": "waygate.image", "resource_id": "waygate-image", "state": "configured"},
    }

    async def inspect(_conn):
        return [local]

    async def remote(service, _request, _path):
        return malformed if service == failed_service else [native[service]]

    monkeypatch.setattr(admin_resource_policies, "get_admin_project_connection", _admin_conn)
    monkeypatch.setattr(admin_resource_policies.store, "inspect_policies", inspect)
    monkeypatch.setattr(admin_resource_policies, "get_json", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=True, service_k3s_enabled=True),
    )

    response = await admin_client.get("/api/v1/admin/resource-policies")

    healthy_service = "drover" if failed_service == "waygate" else "waygate"
    assert response.status_code == 200
    assert response.json() == {
        "policies": [local, native[healthy_service]],
        "errors": [{"service": failed_service, "status": 502}],
    }


@pytest.mark.asyncio
async def test_resource_policy_list_reports_both_native_failures_without_hiding_local_rows(admin_client, monkeypatch):
    local = {"key": "builder.flavor", "resource_id": "builder-small", "state": "configured"}

    async def inspect(_conn):
        return [local]

    async def remote(service, _request, _path):
        raise HTTPException(status_code=503 if service == "waygate" else 403, detail="private-native-detail")

    monkeypatch.setattr(admin_resource_policies, "get_admin_project_connection", _admin_conn)
    monkeypatch.setattr(admin_resource_policies.store, "inspect_policies", inspect)
    monkeypatch.setattr(admin_resource_policies, "get_json", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=True, service_k3s_enabled=True),
    )

    response = await admin_client.get("/api/v1/admin/resource-policies")

    assert response.status_code == 200
    assert response.json() == {
        "policies": [local],
        "errors": [{"service": "drover", "status": 403}, {"service": "waygate", "status": 503}],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [503, 401, 403])
async def test_runtime_settings_preserve_notion_on_drover_failure(admin_client, monkeypatch, status):
    local = {"key": "notion.sync_enabled", "value": True, "state": "configured"}

    async def local_settings():
        return [local, {"key": "k3s.version", "value": "obsolete-local", "state": "configured"}]

    async def remote(service, request, path):
        assert service == "drover"
        assert request.headers["x-auth-token"] == "test-token"
        assert request.headers["x-project-id"] == "test-project-123"
        assert path == "/v1/admin/runtime-settings"
        raise HTTPException(status_code=status, detail="private-native-detail", headers={"X-Native-Secret": "secret"})

    monkeypatch.setattr(admin_resource_policies.store, "list_runtime_settings", local_settings)
    monkeypatch.setattr(admin_resource_policies, "get_json", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=True, service_k3s_enabled=True),
    )

    response = await admin_client.get("/api/v1/admin/runtime-settings")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "x-native-secret" not in response.headers
    assert response.json() == {"settings": [local], "errors": [{"service": "drover", "status": status}]}


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", [{"settings": []}, None, "not-a-list"])
async def test_runtime_settings_localize_malformed_drover_response(admin_client, monkeypatch, malformed):
    local = {"key": "notion.sync_enabled", "value": False, "state": "configured"}

    async def local_settings():
        return [local]

    async def remote(_service, _request, _path):
        return malformed

    monkeypatch.setattr(admin_resource_policies.store, "list_runtime_settings", local_settings)
    monkeypatch.setattr(admin_resource_policies, "get_json", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=False, service_k3s_enabled=True),
    )

    response = await admin_client.get("/api/v1/admin/runtime-settings")

    assert response.status_code == 200
    assert response.json() == {"settings": [local], "errors": [{"service": "drover", "status": 502}]}


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["resource-policies", "runtime-settings"])
async def test_admin_lists_do_not_mask_local_storage_failure_with_native_results(admin_client, monkeypatch, endpoint):
    async def unavailable(*_args):
        raise admin_resource_policies.store.ResourcePolicyStorageUnavailable("private-storage-detail")

    async def remote(*_args):
        pytest.fail("Native reads must not hide a failed local policy/settings store")

    monkeypatch.setattr(admin_resource_policies, "get_admin_project_connection", _admin_conn)
    monkeypatch.setattr(admin_resource_policies.store, "inspect_policies", unavailable)
    monkeypatch.setattr(admin_resource_policies.store, "list_runtime_settings", unavailable)
    monkeypatch.setattr(admin_resource_policies, "get_json", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=True, service_k3s_enabled=True),
    )

    response = await admin_client.get(f"/api/v1/admin/{endpoint}")

    assert response.status_code == 503
    assert "private-storage-detail" not in response.text
    assert "errors" not in response.json()


@pytest.mark.asyncio
async def test_resource_policy_list_admin_connection_failure_remains_top_level(admin_client, monkeypatch):
    def unavailable():
        raise RuntimeError("private-admin-connection-detail")

    async def remote(*_args):
        pytest.fail("Native reads must not hide an unavailable local admin connection")

    monkeypatch.setattr(admin_resource_policies, "get_admin_project_connection", unavailable)
    monkeypatch.setattr(admin_resource_policies, "get_json", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=True, service_k3s_enabled=True),
    )

    response = await admin_client.get("/api/v1/admin/resource-policies")

    assert response.status_code == 503
    assert "private-admin-connection-detail" not in response.text
    assert "errors" not in response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "collection", "local"),
    [
        ("resource-policies", "policies", {"key": "builder.flavor", "resource_id": "builder-small"}),
        ("runtime-settings", "settings", {"key": "notion.sync_enabled", "value": True}),
    ],
)
async def test_admin_lists_return_envelopes_without_disabled_native_rows(
    admin_client, monkeypatch, endpoint, collection, local
):
    async def local_rows(*_args):
        return [local, {"key": "k3s.version" if collection == "settings" else "k3s.server_image"}]

    async def remote(*_args):
        pytest.fail("Disabled services must not be contacted")

    monkeypatch.setattr(admin_resource_policies, "get_admin_project_connection", _admin_conn)
    monkeypatch.setattr(admin_resource_policies.store, "inspect_policies", local_rows)
    monkeypatch.setattr(admin_resource_policies.store, "list_runtime_settings", local_rows)
    monkeypatch.setattr(admin_resource_policies, "get_json", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=False, service_k3s_enabled=False),
    )

    response = await admin_client.get(f"/api/v1/admin/{endpoint}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {collection: [local], "errors": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["resource-policies", "runtime-settings"])
async def test_admin_lists_do_not_turn_unexpected_native_errors_into_partial_success(
    admin_client, monkeypatch, endpoint
):
    async def local_rows(*_args):
        return []

    async def remote(*_args):
        raise RuntimeError("unexpected-native-programming-error")

    monkeypatch.setattr(admin_resource_policies, "get_admin_project_connection", _admin_conn)
    monkeypatch.setattr(admin_resource_policies.store, "inspect_policies", local_rows)
    monkeypatch.setattr(admin_resource_policies.store, "list_runtime_settings", local_rows)
    monkeypatch.setattr(admin_resource_policies, "get_json", remote)
    monkeypatch.setattr(
        admin_resource_policies,
        "get_settings",
        lambda: SimpleNamespace(service_waygate_enabled=True, service_k3s_enabled=True),
    )

    with pytest.raises(RuntimeError, match="unexpected-native-programming-error"):
        await admin_client.get(f"/api/v1/admin/{endpoint}")
