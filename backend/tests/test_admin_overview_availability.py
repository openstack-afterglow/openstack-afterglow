"""Overview source failures must remain unknown, independently of real zero."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.identity import admin
from tests.conftest import patch_redis_cache_miss


def _sources(monkeypatch):
    monkeypatch.setattr(
        admin,
        "get_settings",
        lambda: SimpleNamespace(
            service_zun_enabled=True,
            service_manila_enabled=True,
            service_trove_enabled=True,
            service_swift_enabled=True,
        ),
    )
    values = {
        "hypervisors": {
            "host_count": 0,
            "used_vcpus": 0,
            "total_ram_mb": 0,
            "used_ram_mb": 0,
            "running_vms": 0,
            "total_vcpus": 0,
        },
        "disk": {"total_disk": 0, "used_disk": 0, "volume_gb": 0, "image_gb": 0},
        "placement": {"physical_vcpus": 0, "allowed_vcpus": 0},
        "servers": {
            "gpu_instances": 0,
            "instance_stats": {"total": 0, "active": 0, "shutoff": 0, "error": 0, "other": 0},
        },
        "containers": 0,
        "file_storage": 0,
        "database_instances": 0,
        "object_storage": 0,
    }
    for name, value in values.items():
        monkeypatch.setattr(admin, f"_fetch_overview_{name}", lambda conn, value=value: value)
    return values


@pytest.mark.asyncio
async def test_overview_successful_empty_inventory_is_zero(admin_client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    _sources(monkeypatch)
    response = await admin_client.get("/api/v1/admin/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["hypervisor_count"] == 0
    assert data["vcpus"] == {"total": 0, "allowed": 0, "used": 0}
    assert data["disk_gb"] == {"total": 0, "used": 0, "volumes": 0, "images": 0}
    assert data["instance_stats"]["total"] == 0
    assert data["containers_count"] == 0
    assert data["unavailable_sections"] == []
    assert data["disabled_sections"] == []
    assert data["collected_at"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("collector", "section", "field"),
    [
        ("hypervisors", "hypervisors", "hypervisor_count"),
        ("placement", "placement", None),
        ("servers", "instances", "instance_stats"),
        ("containers", "containers", "containers_count"),
        ("file_storage", "file_storage", "file_storage_count"),
        ("database_instances", "database", "database_instances_count"),
        ("object_storage", "object_storage", "object_storage_containers_count"),
    ],
)
async def test_overview_failed_source_is_null_not_zero(admin_client, monkeypatch, collector, section, field):
    patch_redis_cache_miss(monkeypatch)
    _sources(monkeypatch)

    def fail(conn):
        raise RuntimeError("source unavailable")

    monkeypatch.setattr(admin, f"_fetch_overview_{collector}", fail)
    response = await admin_client.get("/api/v1/admin/overview")
    assert response.status_code == 200
    data = response.json()
    assert section in data["unavailable_sections"]
    if field:
        assert data[field] is None
    if collector == "placement":
        assert data["vcpus"] == {"total": None, "allowed": None, "used": 0}
    elif collector == "hypervisors":
        assert data["vcpus"]["used"] is None
        assert data["ram_gb"] == {"total": None, "used": None}
        assert data["running_vms"] is None
    assert data["disk_gb"]["volumes"] == 0


@pytest.mark.asyncio
async def test_overview_storage_retains_independent_known_sources(admin_client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    values = _sources(monkeypatch)
    values["disk"].update(total_disk=1000, used_disk=None, volume_gb=256, image_gb=None)
    data = (await admin_client.get("/api/v1/admin/overview")).json()
    assert data["disk_gb"] == {"total": 1000, "used": None, "volumes": 256, "images": None}
    assert data["unavailable_sections"] == ["storage.image_gb"]


@pytest.mark.asyncio
async def test_overview_overcommit_preserves_raw_denominators(admin_client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    values = _sources(monkeypatch)
    values["hypervisors"]["used_vcpus"] = 256
    values["placement"].update(physical_vcpus=212, allowed_vcpus=424)
    data = (await admin_client.get("/api/v1/admin/overview")).json()
    assert data["vcpus"] == {"total": 212, "allowed": 424, "used": 256}
    assert data["unavailable_sections"] == []


def test_native_empty_hypervisors_are_not_a_synthetic_host():
    conn = MagicMock()
    conn.session.get.return_value.json.return_value = {"hypervisors": []}
    assert admin._fetch_overview_hypervisors(conn)["host_count"] == 0


def test_native_missing_hypervisor_envelope_is_not_empty():
    conn = MagicMock()
    conn.session.get.return_value.json.return_value = {}
    with pytest.raises(RuntimeError):
        admin._fetch_overview_hypervisors(conn)


def test_native_missing_hypervisor_quantity_is_not_zero():
    conn = MagicMock()
    conn.session.get.return_value.json.return_value = {"hypervisors": [{"vcpus": 4}]}
    with pytest.raises(ValueError):
        admin._fetch_overview_hypervisors(conn)


def test_storage_volume_read_failure_retains_image_bytes(monkeypatch):
    from app.services import cinder, glance

    conn = MagicMock()
    monkeypatch.setattr(cinder, "list_storage_pools", lambda conn, **kwargs: [{"total_capacity_gb": 100}])
    monkeypatch.setattr(glance, "get_total_image_bytes", lambda conn, **kwargs: 2**30)
    conn.block_storage.volumes.side_effect = RuntimeError("denied")
    assert admin._fetch_overview_disk(conn) == {"total_disk": 100, "used_disk": None, "volume_gb": None, "image_gb": 1}


def test_strict_image_collection_does_not_hide_provider_failure():
    from app.services.glance import get_total_image_bytes

    conn = MagicMock()
    conn.image.images.side_effect = RuntimeError("denied")
    with pytest.raises(RuntimeError):
        get_total_image_bytes(conn, strict=True)


def test_strict_swift_collection_does_not_hide_auth_failure(monkeypatch):
    from app.services import swift

    monkeypatch.setattr(swift, "_apply_endpoint_override", lambda conn: None)
    conn = MagicMock()
    conn.object_store.head.side_effect = RuntimeError("denied")
    with pytest.raises(RuntimeError):
        swift.count_containers(conn, strict=True)


def test_disabled_collectors_are_not_empty_inventories(monkeypatch):
    monkeypatch.setattr(
        admin,
        "get_settings",
        lambda: SimpleNamespace(
            service_zun_enabled=False,
            service_manila_enabled=False,
            service_trove_enabled=False,
            service_swift_enabled=False,
        ),
    )
    conn = MagicMock()
    assert admin._fetch_overview_containers(conn) is None
    assert admin._fetch_overview_file_storage(conn) is None
    assert admin._fetch_overview_database_instances(conn) is None
    assert admin._fetch_overview_object_storage(conn) is None
    assert conn.mock_calls == []


@pytest.mark.parametrize("body", [{}, {"resource_providers": None}, {"resource_providers": {}}])
def test_native_missing_placement_inventory_is_not_zero(body):
    conn = MagicMock()
    conn.session.get.return_value.json.return_value = body
    with pytest.raises((ValueError, KeyError, TypeError)):
        admin._fetch_overview_placement(conn)


def test_native_server_overview_consumes_every_page():
    conn = MagicMock()
    first = MagicMock()
    first.json.return_value = {
        "servers": [{"id": "one", "status": "ACTIVE", "flavor": {}}],
        "servers_links": [{"rel": "next", "href": "https://not-trusted.invalid/next"}],
    }
    second = MagicMock()
    second.json.return_value = {"servers": [{"id": "two", "status": "ERROR", "flavor": {}}]}
    conn.session.get.side_effect = [first, second]
    result = admin._fetch_overview_servers(conn)
    assert result["instance_stats"]["total"] == 2
    assert result["instance_stats"]["error"] == 1
    assert conn.session.get.call_args_list[1].kwargs["params"]["marker"] == "one"
    assert "not-trusted.invalid" not in conn.session.get.call_args_list[1].args[0]


def test_native_strict_swift_fanout_rejects_partial_count(monkeypatch):
    from app.services import keystone, swift

    monkeypatch.setattr(swift, "_apply_endpoint_override", lambda conn: None)
    monkeypatch.setattr(keystone, "list_system_projects", lambda token: [{"id": "ok"}, {"id": "failed"}])
    known = MagicMock()
    known.object_store.head.return_value.headers = {"X-Account-Container-Count": "2"}

    def connection(project_id):
        if project_id == "failed":
            raise RuntimeError("scope unavailable")
        return known

    monkeypatch.setattr(keystone, "get_admin_connection_for_project", connection)
    with pytest.raises(RuntimeError):
        swift.count_containers_all_projects("admin", strict=True)


@pytest.mark.asyncio
async def test_overview_disabled_source_has_explicit_availability(admin_client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    _sources(monkeypatch)
    monkeypatch.setattr(
        admin,
        "get_settings",
        lambda: SimpleNamespace(
            service_zun_enabled=False,
            service_manila_enabled=True,
            service_trove_enabled=True,
            service_swift_enabled=True,
        ),
    )
    monkeypatch.setattr(admin, "_fetch_overview_containers", lambda conn: None)
    data = (await admin_client.get("/api/v1/admin/overview")).json()
    assert data["containers_count"] is None
    assert data["disabled_sections"] == ["containers"]
    assert "containers" not in data["unavailable_sections"]


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["groups", "domains"])
async def test_identity_summary_marks_failed_sections(admin_client, mock_conn, monkeypatch, section):
    patch_redis_cache_miss(monkeypatch)
    for name in ("users", "projects", "roles", "groups", "domains"):
        getattr(mock_conn.identity, name).return_value = []
    getattr(mock_conn.identity, section).side_effect = RuntimeError("source unavailable")
    response = await admin_client.get("/api/v1/admin/identity/summary")
    assert response.status_code == 200
    assert response.json()["partial"] is True
    assert any(reason.startswith(f"{section}:") for reason in response.json()["partial_reasons"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("collector", "section"), [("servers", "instances"), ("containers", "containers"), ("file_storage", "file_storage")]
)
async def test_monitoring_preserves_known_sections_after_optional_failure(
    admin_client, monkeypatch, collector, section
):
    patch_redis_cache_miss(monkeypatch)
    _sources(monkeypatch)
    monkeypatch.setattr(admin, "_fetch_hypervisors_raw", lambda conn: [])
    monkeypatch.setattr(admin, "_collect_storage_block", lambda conn: {"volume_count": 1})
    monkeypatch.setattr(admin, "_collect_network_block", lambda conn: {"network_count": 2})
    for name in (
        "_count_volume_snapshots",
        "_count_volume_backups",
        "_count_share_snapshots",
        "_count_images",
        "_count_subnets",
        "_count_security_groups",
        "_count_database_instances_admin",
    ):
        monkeypatch.setattr(admin, name, lambda conn: 0)
    monkeypatch.setattr(admin, "_count_load_balancers", lambda conn: (0, 0))
    monkeypatch.setattr(admin, "_count_identity_users_projects", lambda: (0, 0))
    monkeypatch.setattr(admin, "get_drover_proxy", lambda conn: SimpleNamespace(admin_clusters=lambda: []))
    telemetry = {"status": "available", "source": "gnocchi", "resources": [{"id": "known-native-sample"}]}
    monkeypatch.setattr(admin.native_telemetry, "system_series", AsyncMock(return_value=telemetry))

    def fail(conn):
        raise RuntimeError("optional source unavailable")

    monkeypatch.setattr(admin, f"_fetch_overview_{collector}", fail)
    response = await admin_client.get("/api/v1/admin/monitoring/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["unavailable_sections"] == [section]
    assert data["telemetry"] == telemetry
    assert data["network"]["network_count"] == 2
    assert data["storage"]["volume_count"] == 1
    if section == "instances":
        assert data["compute"]["instance_stats"] is None
        assert data["compute"]["gpu_instances"] is None
    elif section == "containers":
        assert data["containers"]["zun_count"] is None
    else:
        assert data["storage"]["file_storage_count"] is None


def test_placement_overview_normalizes_discovered_trailing_slash():
    conn = MagicMock()
    conn.placement.get_endpoint.return_value = "http://placement.fixture/placement/"
    providers = MagicMock()
    providers.json.return_value = {"resource_providers": [{"uuid": "provider-a"}]}
    inventories = MagicMock()
    inventories.json.return_value = {"inventories": {"VCPU": {"total": 212, "allocation_ratio": 2}}}
    conn.session.get.side_effect = [providers, inventories]
    assert admin._fetch_overview_placement(conn) == {"physical_vcpus": 212, "allowed_vcpus": 424}
    assert [call.args[0] for call in conn.session.get.call_args_list] == [
        "http://placement.fixture/placement/resource_providers",
        "http://placement.fixture/placement/resource_providers/provider-a/inventories",
    ]


@pytest.mark.asyncio
async def test_old_cached_overview_cannot_break_new_response_schema(admin_client, monkeypatch):
    _sources(monkeypatch)
    entries = {
        "afterglow:admin:overview": json.dumps(
            {
                "hypervisor_count": 99,
                "running_vms": 99,
                "vcpus": {"total": 99, "allowed": 99, "used": 99},
                "ram_gb": {"total": 99, "used": 99},
                "disk_gb": {"total": 99, "used": 99},
            }
        )
    }

    async def save(key, value, ttl):
        entries[key] = value

    backend = SimpleNamespace(
        get=AsyncMock(side_effect=lambda key: entries.get(key)),
        set=AsyncMock(side_effect=save),
    )
    monkeypatch.setattr("app.services.cache._get_backend", lambda: backend)
    response = await admin_client.get("/api/v1/admin/overview?cache=true")
    assert response.status_code == 200
    data = response.json()
    assert data["hypervisor_count"] == 0
    assert data["disk_gb"] == {"total": 0, "used": 0, "volumes": 0, "images": 0}
    assert data["unavailable_sections"] == []
