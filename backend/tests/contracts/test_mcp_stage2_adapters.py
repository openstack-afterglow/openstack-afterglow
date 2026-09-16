from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.services.mcp_control_plane.authentication import McpPrincipal
from app.services.mcp_control_plane.file_storage import (
    McpFileStorageError,
    get_project_share_quota,
)
from app.services.mcp_control_plane.k3s import (
    McpK3sError,
    get_project_k3s_cluster,
    list_project_k3s_clusters,
)
from app.services.mcp_control_plane.key_manager import (
    McpKeyManagerError,
    list_project_secret_metadata,
)
from app.services.mcp_control_plane.object_storage import (
    McpObjectStorageError,
    get_project_swift_account,
)
from app.services.mcp_control_plane.registry import (
    FileStorageQuotaGetArguments,
    KeyManagerSecretListArguments,
    ObjectStorageAccountGetArguments,
    WaygateServerGetArguments,
    WaygateServerListArguments,
    dispatch,
    enabled_entries,
    entry_by_name,
    registry_entries,
    validate_registry_inventory,
)
from app.services.mcp_control_plane.waygate import (
    McpWaygateError,
    get_project_waygate_server,
    list_project_waygate_servers,
)

# --- File Storage Tests ---


@pytest.mark.asyncio
async def test_get_project_share_quota_success(monkeypatch):
    def fake_get_file_storage_quota(conn, *, strict):
        assert strict is True
        return {
            "shares": {"limit": 10, "in_use": 2},
            "gigabytes": {"limit": 500, "in_use": 100},
            "snapshots": {"limit": 5, "in_use": 1},
        }

    monkeypatch.setattr(
        "app.services.mcp_control_plane.file_storage.manila_service.get_file_storage_quota",
        fake_get_file_storage_quota,
    )

    res = await get_project_share_quota(object())
    assert res == {
        "shares": {"limit": 10, "in_use": 2},
        "gigabytes": {"limit": 500, "in_use": 100},
    }


@pytest.mark.asyncio
async def test_get_project_share_quota_error(monkeypatch):
    def fake_fail(*_args, **_kwargs):
        raise RuntimeError("Manila down")

    monkeypatch.setattr(
        "app.services.mcp_control_plane.file_storage.manila_service.get_file_storage_quota",
        fake_fail,
    )

    with pytest.raises(McpFileStorageError, match="unavailable"):
        await get_project_share_quota(object())


@pytest.mark.asyncio
async def test_registry_file_storage_quota_get_dispatch(monkeypatch):
    entry = entry_by_name("afterglow_file_storage_quota_get")
    assert entry is not None

    async def fake_quota(_conn):
        return {
            "shares": {"limit": 5, "in_use": 1},
            "gigabytes": {"limit": 200, "in_use": 50},
        }

    monkeypatch.setattr("app.services.mcp_control_plane.registry.get_project_share_quota", fake_quota)

    class DummyConnCtx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            pass

    ctx = SimpleNamespace(
        principal=McpPrincipal(
            grant_id="g1",
            user_id="u1",
            project_id="p1",
            credential_epoch=1,
            scopes=frozenset({"mcp:read"}),
            source="personal_token",
        ),
        project_id="p1",
        openstack_connection=lambda: DummyConnCtx(),
    )

    out = await dispatch(ctx, entry=entry, arguments=FileStorageQuotaGetArguments())
    assert out.shares.limit == 5
    assert out.shares.in_use == 1
    assert out.gigabytes.limit == 200
    assert out.gigabytes.in_use == 50


# --- K3s Tests ---


@pytest.mark.asyncio
async def test_list_project_k3s_clusters_uses_catalog_sdk_and_redacts(monkeypatch):
    conn = object()
    observed = {}

    class Proxy:
        def clusters(self, **query):
            observed.update(query)
            return [
                {
                    "id": "c1",
                    "name": "k3s-demo",
                    "status": "ACTIVE",
                    "project_id": "proj-1",
                    "agent_count": 3,
                    "k3s_version": "v1.34.6+k3s1",
                    "created_at": None,
                    "updated_at": None,
                    "master_count": 1,
                    "stampede_enabled": False,
                    "occm_enabled": True,
                    "kubeconfig_encrypted": "must-not-leak",
                }
            ]

    monkeypatch.setattr(
        "app.services.mcp_control_plane.k3s.get_drover_proxy",
        lambda actual_conn: Proxy() if actual_conn is conn else None,
    )

    clusters = await list_project_k3s_clusters(conn, "proj-1", limit=10)

    assert observed == {"limit": 10}
    assert clusters == [
        {
            "id": "c1",
            "name": "k3s-demo",
            "status": "ACTIVE",
            "agent_count": 3,
            "k3s_version": "v1.34.6+k3s1",
            "created_at": None,
            "updated_at": None,
            "master_count": 1,
            "stampede_enabled": False,
            "occm_enabled": True,
        }
    ]


@pytest.mark.asyncio
async def test_list_project_k3s_clusters_catalog_unavailable(monkeypatch):
    monkeypatch.setattr(
        "app.services.mcp_control_plane.k3s.get_drover_proxy",
        lambda _conn: (_ for _ in ()).throw(RuntimeError("catalog unavailable")),
    )

    with pytest.raises(McpK3sError, match="list query failed"):
        await list_project_k3s_clusters(object(), "proj-1")


@pytest.mark.asyncio
async def test_get_project_k3s_cluster_ownership_proof(monkeypatch):
    conn = object()

    class Proxy:
        def get_cluster(self, cluster_id):
            return {
                "id": cluster_id,
                "name": "foreign-cluster",
                "status": "ACTIVE",
                "project_id": "other-project",
            }

    monkeypatch.setattr(
        "app.services.mcp_control_plane.k3s.get_drover_proxy",
        lambda actual_conn: Proxy() if actual_conn is conn else None,
    )

    with pytest.raises(McpK3sError, match="ownership cannot be proven"):
        await get_project_k3s_cluster(conn, "proj-1", "c2")


# --- Object Storage Tests ---


@pytest.mark.asyncio
async def test_get_project_swift_account_success(monkeypatch):
    def fake_get_account_metadata(conn, *, strict):
        assert strict is True
        return {"container_count": 4, "object_count": 120, "bytes_used": 1048576}

    monkeypatch.setattr(
        "app.services.mcp_control_plane.object_storage.swift_service.get_account_metadata",
        fake_get_account_metadata,
    )

    res = await get_project_swift_account(object())
    assert res == {
        "container_count": 4,
        "object_count": 120,
        "bytes_used": 1048576,
    }


@pytest.mark.asyncio
async def test_get_project_swift_account_error(monkeypatch):
    def fake_fail(*_args, **_kwargs):
        raise RuntimeError("Swift unreachable")

    monkeypatch.setattr(
        "app.services.mcp_control_plane.object_storage.swift_service.get_account_metadata",
        fake_fail,
    )

    with pytest.raises(McpObjectStorageError, match="unavailable"):
        await get_project_swift_account(object())


@pytest.mark.asyncio
async def test_registry_object_storage_account_get_dispatch(monkeypatch):
    entry = entry_by_name("afterglow_object_storage_account_get")
    assert entry is not None

    async def fake_swift(_conn):
        return {"container_count": 2, "object_count": 50, "bytes_used": 2048}

    monkeypatch.setattr("app.services.mcp_control_plane.registry.get_project_swift_account", fake_swift)

    class DummyConnCtx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            pass

    ctx = SimpleNamespace(
        principal=McpPrincipal(
            grant_id="g1",
            user_id="u1",
            project_id="p1",
            credential_epoch=1,
            scopes=frozenset({"mcp:read"}),
            source="personal_token",
        ),
        project_id="p1",
        openstack_connection=lambda: DummyConnCtx(),
    )

    out = await dispatch(ctx, entry=entry, arguments=ObjectStorageAccountGetArguments())
    assert out.container_count == 2
    assert out.object_count == 50
    assert out.bytes_used == 2048


# --- Key Manager Tests ---


@pytest.mark.asyncio
async def test_list_project_secret_metadata_redacts_payload_and_bounds_results(monkeypatch):
    observed: dict[str, object] = {}

    def fake_list_secrets(_conn, **filters):
        max_items = filters["max_items"]
        observed.update(filters)
        return [
            {
                "id": "secret-1",
                "name": "app-key",
                "secret_type": "opaque",
                "status": "ACTIVE",
                "algorithm": "aes",
                "bit_length": 256,
                "mode": "gcm",
                "created": "2026-07-31T00:00:00+00:00",
                "expires": None,
                "system_managed": False,
                "content_types": {"default": "application/octet-stream"},
                "payload": "must-not-leak",
                "secret_ref": "https://barbican.example/v1/secrets/secret-1",
            },
            {
                "id": "secret-2",
                "name": "second",
                "secret_type": "opaque",
                "status": "ACTIVE",
                "system_managed": False,
            },
        ][:max_items]

    monkeypatch.setattr(
        "app.services.mcp_control_plane.key_manager.barbican_service.list_secrets",
        fake_list_secrets,
    )

    secrets = await list_project_secret_metadata(object(), limit=1)

    assert observed == {"max_items": 1}
    assert secrets == [
        {
            "id": "secret-1",
            "name": "app-key",
            "secret_type": "opaque",
            "status": "ACTIVE",
            "algorithm": "aes",
            "bit_length": 256,
            "mode": "gcm",
            "created": "2026-07-31T00:00:00+00:00",
            "expires": None,
            "system_managed": False,
        }
    ]
    assert "payload" not in secrets[0]
    assert "secret_ref" not in secrets[0]
    assert "content_types" not in secrets[0]


@pytest.mark.asyncio
async def test_list_project_secret_metadata_rejects_missing_id(monkeypatch):
    monkeypatch.setattr(
        "app.services.mcp_control_plane.key_manager.barbican_service.list_secrets",
        lambda *_args, **_kwargs: [{"name": "missing-id"}],
    )

    with pytest.raises(McpKeyManagerError, match="missing an id"):
        await list_project_secret_metadata(object(), limit=1)


# --- Waygate Tests ---


@pytest.mark.asyncio
async def test_list_project_waygate_servers_uses_catalog_sdk_and_redacts(monkeypatch):
    conn = object()
    observed: dict[str, object] = {}

    class Proxy:
        def servers(self):
            return [
                {
                    "id": "1f521da3-2524-4d0a-bb6a-68fbac7a25bd",
                    "project_id": "project-1",
                    "name": "gateway",
                    "status": "ACTIVE",
                    "created_at": "2026-07-31T00:00:00+00:00",
                    "updated_at": "2026-07-31T01:00:00+00:00",
                    "endpoint_ip": "203.0.113.10",
                    "server_public_key": "public-key",
                    "agent_token_encrypted": "ciphertext",
                    "provider_network_id": "network-id",
                },
                {
                    "id": "second",
                    "project_id": "project-1",
                    "name": "bounded-out",
                    "status": "ACTIVE",
                },
            ]

    def fake_register(actual_conn):
        observed["conn"] = actual_conn
        return Proxy()

    monkeypatch.setattr("app.services.mcp_control_plane.waygate.get_waygate_proxy", fake_register)

    servers = await list_project_waygate_servers(conn, "project-1", limit=1)

    assert observed["conn"] is conn
    assert servers == [
        {
            "id": "1f521da3-2524-4d0a-bb6a-68fbac7a25bd",
            "name": "gateway",
            "status": "ACTIVE",
            "created_at": "2026-07-31T00:00:00+00:00",
            "updated_at": "2026-07-31T01:00:00+00:00",
        }
    ]


@pytest.mark.asyncio
async def test_get_project_waygate_server_rejects_foreign_catalog_record(monkeypatch):
    conn = object()

    class Proxy:
        def get_server(self, server_id):
            return {
                "id": server_id,
                "project_id": "other-project",
                "name": "foreign",
                "status": "ACTIVE",
            }

    monkeypatch.setattr(
        "app.services.mcp_control_plane.waygate.get_waygate_proxy",
        lambda actual_conn: Proxy() if actual_conn is conn else None,
    )

    with pytest.raises(McpWaygateError, match="ownership cannot be proven"):
        await get_project_waygate_server(
            conn,
            "project-1",
            "1f521da3-2524-4d0a-bb6a-68fbac7a25bd",
        )


# --- Inventory and Feature Flag Gate Tests ---


def test_registry_inventory_includes_stage2_tools():
    all_entries = registry_entries()
    names = {e.name for e in all_entries}
    assert "afterglow_file_storage_quota_get" in names
    assert "afterglow_k3s_cluster_list" in names
    assert "afterglow_k3s_cluster_get" in names
    assert "afterglow_object_storage_account_get" in names
    assert "afterglow_key_manager_secret_list" in names
    assert "afterglow_waygate_server_list" in names
    assert "afterglow_waygate_server_get" in names

    # Must pass inventory classification validation
    validate_registry_inventory(all_entries)


def test_stage2_tools_gated_by_service_feature_flags(monkeypatch):
    principal = McpPrincipal(
        grant_id="g1",
        user_id="u1",
        project_id="p1",
        credential_epoch=1,
        scopes=frozenset({"mcp:read"}),
        source="personal_token",
    )

    # When disabled
    disabled_settings = get_settings().model_copy(
        update={
            "service_manila_enabled": False,
            "service_k3s_enabled": False,
            "service_swift_enabled": False,
            "service_barbican_enabled": False,
            "service_waygate_enabled": False,
        }
    )
    monkeypatch.setattr(
        "app.services.mcp_control_plane.registry.get_settings",
        lambda: disabled_settings,
    )

    active_names = {e.name for e in enabled_entries(principal)}
    assert "afterglow_file_storage_quota_get" not in active_names
    assert "afterglow_k3s_cluster_list" not in active_names
    assert "afterglow_k3s_cluster_get" not in active_names
    assert "afterglow_object_storage_account_get" not in active_names
    assert "afterglow_key_manager_secret_list" not in active_names
    assert "afterglow_waygate_server_list" not in active_names
    assert "afterglow_waygate_server_get" not in active_names

    # When enabled
    enabled_settings = get_settings().model_copy(
        update={
            "service_manila_enabled": True,
            "service_k3s_enabled": True,
            "service_swift_enabled": True,
            "service_barbican_enabled": True,
            "service_waygate_enabled": True,
        }
    )
    monkeypatch.setattr(
        "app.services.mcp_control_plane.registry.get_settings",
        lambda: enabled_settings,
    )

    active_names_on = {e.name for e in enabled_entries(principal)}
    assert "afterglow_file_storage_quota_get" in active_names_on
    assert "afterglow_k3s_cluster_list" in active_names_on
    assert "afterglow_k3s_cluster_get" in active_names_on
    assert "afterglow_object_storage_account_get" in active_names_on
    assert "afterglow_key_manager_secret_list" in active_names_on
    assert "afterglow_waygate_server_list" in active_names_on
    assert "afterglow_waygate_server_get" in active_names_on


@pytest.mark.asyncio
async def test_registry_key_manager_and_waygate_dispatch_redacted_results(monkeypatch):
    key_manager_entry = entry_by_name("afterglow_key_manager_secret_list")
    waygate_list_entry = entry_by_name("afterglow_waygate_server_list")
    waygate_get_entry = entry_by_name("afterglow_waygate_server_get")
    assert key_manager_entry is not None
    assert waygate_list_entry is not None
    assert waygate_get_entry is not None

    async def fake_secrets(_conn, *, limit):
        assert limit == 1
        return [
            {
                "id": "secret-1",
                "name": "app-key",
                "secret_type": "opaque",
                "status": "ACTIVE",
                "system_managed": False,
            }
        ]

    async def fake_waygate_list(_conn, _project_id, *, limit):
        assert limit == 1
        return [
            {
                "id": "1f521da3-2524-4d0a-bb6a-68fbac7a25bd",
                "name": "gateway",
                "status": "ACTIVE",
                "created_at": None,
                "updated_at": None,
            }
        ]

    async def fake_waygate_get(_conn, _project_id, server_id):
        return {
            "id": server_id,
            "name": "gateway",
            "status": "ACTIVE",
            "created_at": None,
            "updated_at": None,
        }

    monkeypatch.setattr(
        "app.services.mcp_control_plane.registry.list_project_secret_metadata",
        fake_secrets,
    )
    monkeypatch.setattr(
        "app.services.mcp_control_plane.registry.list_project_waygate_servers",
        fake_waygate_list,
    )
    monkeypatch.setattr(
        "app.services.mcp_control_plane.registry.get_project_waygate_server",
        fake_waygate_get,
    )

    class DummyConnCtx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            pass

    ctx = SimpleNamespace(
        principal=McpPrincipal(
            grant_id="g1",
            user_id="u1",
            project_id="p1",
            credential_epoch=1,
            scopes=frozenset({"mcp:read"}),
            source="personal_token",
        ),
        project_id="p1",
        openstack_connection=lambda: DummyConnCtx(),
    )
    key_manager_output = await dispatch(
        ctx,
        entry=key_manager_entry,
        arguments=KeyManagerSecretListArguments(limit=1),
    )
    waygate_list_output = await dispatch(
        ctx,
        entry=waygate_list_entry,
        arguments=WaygateServerListArguments(limit=1),
    )
    waygate_get_output = await dispatch(
        ctx,
        entry=waygate_get_entry,
        arguments=WaygateServerGetArguments(server_id="1f521da3-2524-4d0a-bb6a-68fbac7a25bd"),
    )

    assert key_manager_output.secrets[0].model_dump() == {
        "id": "secret-1",
        "name": "app-key",
        "secret_type": "opaque",
        "status": "ACTIVE",
        "algorithm": None,
        "bit_length": None,
        "mode": None,
        "created": None,
        "expires": None,
        "system_managed": False,
    }
    assert waygate_list_output.servers[0].model_dump() == {
        "id": "1f521da3-2524-4d0a-bb6a-68fbac7a25bd",
        "name": "gateway",
        "status": "ACTIVE",
        "created_at": None,
        "updated_at": None,
    }
    assert waygate_get_output.model_dump() == waygate_list_output.servers[0].model_dump()
