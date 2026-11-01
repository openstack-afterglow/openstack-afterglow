"""Consumer-facing shared headroom and installed-SDK metadata boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.common import dashboard
from app.services import compute_pools, flavor_automation_policy, gpu_quota
from tests.compute_pool_provider import unmanaged_pool_operator
from tests.conftest import patch_redis_cache_miss, patch_usage_report_deps
from tests.test_domain_pool_flavor_eligibility import GPU, pool_snapshot


@pytest.mark.asyncio
async def test_lossy_installed_sdk_domain_cannot_be_treated_as_unmanaged(_unmanaged_compute_pool_native):
    document = {
        "schema": 1,
        "revision": 1,
        "enabled": True,
        "limits": {"CPU": 8, "MEMORY_MB": 16384},
        "project_limits": {},
    }
    _unmanaged_compute_pool_native["org"] = document
    async with unmanaged_pool_operator(_unmanaged_compute_pool_native) as connection:
        domain = connection.identity.get_domain("org")
        assert "afterglow_compute_pool" not in domain.to_dict()
        with pytest.raises(compute_pools.ComputePoolUnavailable, match="raw_domain_metadata"):
            compute_pools.parse_domain_policy(domain)
        raw = compute_pools._Native(connection).exact("domains", "org")
        assert compute_pools.parse_domain_policy(raw)["limits"] == document["limits"]
        assert compute_pools.domain_pool_state(raw) == "active"


@pytest.mark.asyncio
async def test_usage_report_keeps_shared_consumption_and_optional_cap_headroom(client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    snapshot = pool_snapshot()
    snapshot["project_limits"] = {"CPU": 2, GPU: 0}
    snapshot["project_available"].update(CPU=0, **{GPU: 0})
    monkeypatch.setattr(compute_pools, "project_pool_snapshot", AsyncMock(return_value=snapshot))
    gpu = [
        {
            "gpu_type": "RTX3090",
            "limit": 4,
            "in_use": 3,
            "available": 0,
            "quota_scope": "domain",
            "domain_id": "org",
            "project_limit": 0,
            "project_in_use": 0,
        }
    ]
    with patch_usage_report_deps(
        quota={
            "instances": {"limit": 10, "in_use": 1},
            "cores": {"limit": 32, "in_use": 2},
            "ram": {"limit": 65536, "in_use": 4096},
        },
        volume_quota={"gigabytes": {"limit": 100, "in_use": 10}},
        gpu=gpu,
    ):
        response = await client.get("/api/v1/dashboard/usage-report")
    assert response.status_code == 200
    data = response.json()
    assert data["quota"]["vcpus"]["in_use"] == 24
    assert data["quota"]["vcpus"]["available"] == 0
    assert data["quota"]["gpu"][0]["available"] == 0
    assert data["quota"]["gpu"][0]["project_limit"] == 0
    assert data["quota"]["compute_pool"]["domain_id"] == "org"
    assert "projects" not in data["quota"]["compute_pool"]
    assert data["forecast"]["vcpus"]["trend_available"] is False
    assert data["forecast"]["vcpus"]["series"] == []
    assert data["forecast"]["gpu"]["RTX3090"]["available"] == 0
    assert data["forecast"]["gpu"]["RTX3090"]["trend_available"] is False
    assert response.headers["cache-control"] == "no-store, private"


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["paused", "unavailable"])
async def test_pool_unknown_or_paused_masks_compute_but_preserves_storage(client, monkeypatch, state):
    patch_redis_cache_miss(monkeypatch)
    if state == "unavailable":
        native = AsyncMock(side_effect=compute_pools.ComputePoolUnavailable("native outage"))
    else:
        native = AsyncMock(return_value={**pool_snapshot(), "state": "paused", "enabled": False})
    monkeypatch.setattr(compute_pools, "project_pool_snapshot", native)
    with patch_usage_report_deps(
        quota={"cores": {"limit": 32, "in_use": 2}, "ram": {"limit": 65536, "in_use": 4096}},
        volume_quota={"gigabytes": {"limit": 100, "in_use": 10}},
    ):
        response = await client.get("/api/v1/dashboard/usage-report")
    assert response.status_code == 200
    data = response.json()
    assert data["quota"]["compute_available"] is False
    assert data["quota"]["gpu_available"] is False
    assert data["quota"]["compute_pool"]["state"] == state
    assert data["quota"]["volume_gb"] == {"limit": 100, "in_use": 10}
    assert data["forecast"]["vcpus"]["trend_available"] is False


@pytest.mark.asyncio
async def test_overview_quota_projection_never_confuses_own_usage_with_domain_headroom(monkeypatch):
    snapshot = pool_snapshot()
    snapshot["project_limits"] = {"CPU": 2}
    snapshot["project_available"]["CPU"] = 0
    monkeypatch.setattr(compute_pools, "project_pool_snapshot", AsyncMock(return_value=snapshot))
    native = {
        "instances": {"limit": 10, "in_use": 1},
        "cores": {"limit": 32, "in_use": 2},
        "ram": {"limit": 65536, "in_use": 4096},
    }
    projected, summary = await dashboard._with_compute_pool(None, "project-a", native)
    assert projected["cores"]["in_use"] == 24
    assert projected["cores"]["available"] == 0
    assert projected["cores"]["pool_available"] == 0
    assert projected["cores"]["native_project_in_use"] == 2
    assert projected["instances"] == native["instances"]
    assert summary["usage"]["CPU"] == 24
    assert summary["control_scope"] == "afterglow"
    assert summary["policy_ready"] is True


@pytest.mark.asyncio
async def test_native_project_exhaustion_is_not_replaced_by_pool_headroom():
    native = {"cores": {"limit": 2, "in_use": 2}, "ram": {"limit": 4096, "in_use": 4096}}
    projected, summary = await dashboard._with_compute_pool(None, "project-a", native, snapshot=pool_snapshot())
    assert projected["cores"]["available"] == projected["ram"]["available"] == 0
    assert projected["cores"]["pool_available"] == 8
    assert summary["available"]["CPU"] == 8


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["active", "paused", "unavailable"])
@pytest.mark.parametrize("cpu_limits", [{}, {"CPU": -1, "MEMORY_MB": -1}], ids=["gpu-only", "unlimited"])
async def test_full_quotas_preserve_native_project_usage_independently_of_pool(
    client, mock_conn, monkeypatch, state, cpu_limits
):
    patch_redis_cache_miss(monkeypatch)
    snapshot = pool_snapshot()
    snapshot.update(state=state, enabled=state == "active", limits={GPU: 4, **cpu_limits})
    snapshot["available"].update(CPU=-1, MEMORY_MB=-1)
    snapshot["project_available"].update(CPU=-1, MEMORY_MB=-1)
    pool = AsyncMock(
        side_effect=compute_pools.ComputePoolUnavailable("native outage") if state == "unavailable" else None,
        return_value=snapshot,
    )
    monkeypatch.setattr(compute_pools, "project_pool_snapshot", pool)
    monkeypatch.setattr(
        dashboard,
        "get_settings",
        lambda: SimpleNamespace(service_manila_enabled=False, service_trove_enabled=False, service_swift_enabled=False),
    )
    native = {
        "instances": {"limit": -1, "in_use": 1, "reserved": 0},
        "cores": {"limit": -1, "in_use": 2, "reserved": 1},
        "ram": {"limit": -1, "in_use": 4096, "reserved": 1024},
    }
    mock_conn.compute.get_endpoint.return_value = "http://nova.invalid/v2.1"
    mock_conn.session.get.return_value.json.return_value = {"quota_set": native}
    mock_conn.session.get.return_value.raise_for_status.return_value = None
    monkeypatch.setattr(dashboard.cinder, "get_volume_quota", MagicMock(return_value={}))
    monkeypatch.setattr(dashboard.neutron_svc, "get_network_quota", MagicMock(return_value={}))
    monkeypatch.setattr(gpu_quota, "get_effective_gpu_quota_status", AsyncMock(return_value=[]))

    response = await client.get("/api/v1/dashboard/quotas?cache=false")

    assert response.status_code == 200
    data = response.json()
    assert data["native_compute"] == native
    assert data["compute_pool"]["state"] == state
    if state == "active":
        assert data["compute"]["cores"]["limit"] == data["compute"]["ram"]["limit"] == -1
        assert data["compute"]["cores"]["in_use"] == 24
        assert data["compute"]["ram"]["in_use"] == 49152
        assert data["compute"]["cores"]["quota_scope"] == "domain"
    else:
        assert data["compute"]["cores"] is data["compute"]["ram"] is None
        assert data["gpu_available"] is False
    mock_conn.session.get.assert_called_once_with(
        f"http://nova.invalid/v2.1/os-quota-sets/{mock_conn._afterglow_project_id}/detail"
    )
    pool.assert_awaited_once_with(mock_conn, mock_conn._afterglow_project_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_cores", [None, {"limit": -1}])
async def test_full_quotas_do_not_invent_native_observations_from_domain_pool(
    client, mock_conn, monkeypatch, raw_cores
):
    patch_redis_cache_miss(monkeypatch)
    mock_conn.compute.get_endpoint.return_value = "http://nova.invalid/v2.1"
    mock_conn.session.get.return_value.json.return_value = {
        "quota_set": {"cores": raw_cores, "ram": {"limit": -1, "in_use": 8192}}
    }
    mock_conn.session.get.return_value.raise_for_status.return_value = None
    monkeypatch.setattr(
        dashboard,
        "get_settings",
        lambda: SimpleNamespace(service_manila_enabled=False, service_trove_enabled=False, service_swift_enabled=False),
    )
    monkeypatch.setattr(dashboard.cinder, "get_volume_quota", MagicMock(return_value={}))
    monkeypatch.setattr(dashboard.neutron_svc, "get_network_quota", MagicMock(return_value={}))
    monkeypatch.setattr(compute_pools, "project_pool_snapshot", AsyncMock(return_value=pool_snapshot()))
    monkeypatch.setattr(gpu_quota, "get_effective_gpu_quota_status", AsyncMock(return_value=[]))

    response = await client.get("/api/v1/dashboard/quotas?cache=false")

    assert response.status_code == 200
    data = response.json()
    assert "cores" not in data["native_compute"]
    assert data["native_compute"]["ram"] == {"limit": -1, "in_use": 8192}
    assert data["compute"]["cores"]["in_use"] == 24
    assert data["compute"]["ram"]["in_use"] == 49152
    mock_conn.session.get.assert_called_once()


def approved_capabilities():
    companion = "CUSTOM_PCI_ABCD_0002"
    return {
        "policy_ready": True,
        "resource_kinds": {GPU: "gpu", companion: "companion"},
        "pci_aliases": [
            {"name": "graphics", "resource_class": GPU, "is_gpu": True, "classification_verified": True},
            {"name": "sound", "resource_class": companion, "is_audio": True, "classification_verified": True},
        ],
    }


@pytest.mark.asyncio
async def test_pooled_gpu_quota_projects_approved_group_name_without_changing_native_alias_or_rc(monkeypatch):
    from copy import deepcopy

    from tests.test_managed_flavors import AUDIO, profile

    approved = profile("render-group", GPU)
    approved["display_name"] = "Artist workstation"
    approved["extra_specs"]["pci_passthrough:alias"] = "RTX-3090:1,RTX-3090-audio:1"
    approved["alias_resource_classes"] = {"RTX-3090": GPU, "RTX-3090-audio": AUDIO}
    monkeypatch.setattr(
        flavor_automation_policy, "load_policy", AsyncMock(return_value={"revision": 0, "gpu_profiles": [approved]})
    )
    capabilities = await flavor_automation_policy.capabilities()
    snapshot = pool_snapshot()
    snapshot.update(
        _aliases=capabilities["aliases"],
        _pci_aliases=capabilities["pci_aliases"],
        gpu_profiles=capabilities["gpu_profiles"],
        project_limits={GPU: 2},
        project_usage={GPU: 1},
        project_available={GPU: 1},
    )
    before = deepcopy(snapshot)
    legacy = AsyncMock(side_effect=AssertionError("pooled GPU must not read legacy project quota authority"))
    monkeypatch.setattr(gpu_quota, "get_effective_gpu_quotas", legacy)
    monkeypatch.setattr(gpu_quota, "get_project_gpu_usage", legacy)
    rows = await gpu_quota.get_effective_gpu_quota_status(object(), "project-a", pool_snapshot=snapshot)
    assert rows == [
        {
            "project_id": "project-a",
            "domain_id": "org",
            "quota_scope": "domain",
            "control_scope": "afterglow",
            "gpu_type": "render-group",
            "resource_class": GPU,
            "limit": 4,
            "in_use": 3,
            "available": 1,
            "project_in_use": 1,
            "project_limit": 2,
        }
    ]
    assert capabilities["aliases"][0]["name"] == "RTX-3090"
    assert capabilities["aliases"][0]["profile_name"] == "render-group"
    assert snapshot == before
    legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_pool_snapshot_without_profile_name_retains_alias_identity():
    rows = await gpu_quota.get_effective_gpu_quota_status(object(), "project-a", pool_snapshot=pool_snapshot())
    assert len(rows) == 1
    assert rows[0]["gpu_type"] == "RTX3090" and rows[0]["resource_class"] == GPU
    assert rows[0]["available"] == 1 and rows[0]["in_use"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["graphics", "GRAPHICS", "fresh-custom"])
async def test_gpu_available_joins_pooled_quota_by_physical_identity_not_alias(client, monkeypatch, alias):
    monkeypatch.setattr(dashboard, "get_settings", lambda: SimpleNamespace(gpu_available_visible=True))
    inventory = {
        "gpu_types": [
            {
                "device_name": "Builtin display unrelated to approval",
                "resource_class": GPU,
                "vendor": "NVIDIA",
                "total": 4,
                "used": 0,
                "available": 4,
            }
        ],
        "summary": {"total": 4, "used": 0, "available": 4},
    }
    monkeypatch.setattr(dashboard, "cached_call", AsyncMock(return_value=inventory))
    monkeypatch.setattr(
        gpu_quota,
        "get_effective_gpu_quota_status",
        AsyncMock(
            return_value=[
                {
                    "gpu_type": alias,
                    "resource_class": GPU,
                    "quota_scope": "domain",
                    "limit": 3,
                    "in_use": 1,
                    "available": 2,
                }
            ]
        ),
    )
    response = await client.get("/api/v1/dashboard/gpu-available")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert len(data["gpu_types"]) == 1
    assert data["gpu_types"][0]["resource_class"] == GPU
    assert data["gpu_types"][0]["available"] == 2


@pytest.mark.asyncio
async def test_managed_gpu_metrics_count_primary_not_arbitrarily_named_companions():
    specs = {"afterglow:managed_by": "domain-compute-v1", "pci_passthrough:alias": "graphics:2,sound:2"}
    assert await dashboard._gpu_count_from_flavor("not-a-gpu-name", specs, approved_capabilities()) == 2
    specs["pci_passthrough:alias"] = "GRAPHICS:2,sound:2"
    with pytest.raises(HTTPException) as denied:
        await dashboard._gpu_count_from_flavor("gpu.guessed", specs, approved_capabilities())
    assert denied.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["usage-stats", "summary"])
@pytest.mark.parametrize(("alias", "status"), [("graphics", 200), ("GRAPHICS", 503)])
async def test_dashboard_present_managed_flavor_uses_exact_group_not_name_fallback(
    client, mock_conn, monkeypatch, endpoint, alias, status
):
    patch_redis_cache_miss(monkeypatch)
    mock_conn.block_storage.volumes.return_value = []
    managed = {
        "id": "managed",
        "name": "gpu.renderx4_8c_16g",
        "extra_specs": {
            "afterglow:managed_by": "domain-compute-v1",
            "pci_passthrough:alias": f"{alias}:2,sound:2",
        },
    }
    monkeypatch.setattr(flavor_automation_policy, "capabilities", AsyncMock(return_value=approved_capabilities()))
    monkeypatch.setattr(dashboard, "_list_flavors_as_dicts", lambda conn: [managed])
    monkeypatch.setattr(
        dashboard,
        "_list_servers_as_dicts",
        lambda conn: [{"id": "vm", "status": "ACTIVE", "flavor_name": managed["name"]}],
    )
    monkeypatch.setattr(dashboard.nova, "get_project_usage", lambda *args: {})
    monkeypatch.setattr(
        dashboard.native_telemetry,
        "project_series",
        AsyncMock(return_value={"status": "unavailable", "instances": {}}),
    )
    monkeypatch.setattr(dashboard.prom_query, "query_instant_multi", AsyncMock(return_value=[]))
    response = await client.get(f"/api/v1/dashboard/{endpoint}")
    assert response.status_code == status
    if status == 200:
        data = response.json()
        assert (data["gpu_used"] if endpoint == "summary" else data["top_instances"][0]["gpu"]) == 2


@pytest.mark.asyncio
async def test_managed_usage_report_gpu_hours_use_exact_approved_classification(client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    monkeypatch.setattr(flavor_automation_policy, "capabilities", AsyncMock(return_value=approved_capabilities()))
    managed = {
        "id": "managed",
        "name": "gpu.approved.2gpu.4c.8g",
        "vcpus": 4,
        "ram": 8192,
        "extra_specs": {"afterglow:managed_by": "domain-compute-v1", "pci_passthrough:alias": "graphics:2,sound:2"},
    }
    with patch_usage_report_deps(
        usage={
            "server_usages": [
                {
                    "instance_id": "vm",
                    "flavor": managed["name"],
                    "hours": 3,
                    "vcpus": 4,
                    "memory_mb": 8192,
                    "state": "active",
                }
            ]
        },
        quota={"cores": {"limit": 32, "in_use": 4}, "ram": {"limit": 65536, "in_use": 8192}},
        flavors=[managed],
    ):
        response = await client.get("/api/v1/dashboard/usage-report")
    assert response.status_code == 200
    data = response.json()
    assert data["stats"]["gpu_hours"] == 6
    assert data["flavor_hours"][0]["gpu_count"] == 2
    assert data["flavor_hours"][0]["gpu_hours"] == 6
    assert data["instance_usage"][0]["gpu_count"] == 2


@pytest.mark.asyncio
async def test_unmanaged_gpu_available_keeps_legacy_canonical_alias_join(client, monkeypatch):
    monkeypatch.setattr(dashboard, "get_settings", lambda: SimpleNamespace(gpu_available_visible=True))
    monkeypatch.setattr("app.api.identity.admin_gpu.build_device_name_to_alias_map", lambda: {"Legacy GPU": "LEGACY"})
    monkeypatch.setattr(
        dashboard,
        "cached_call",
        AsyncMock(
            return_value={
                "gpu_types": [{"device_name": "Legacy GPU", "vendor": "NVIDIA", "total": 4, "used": 0, "available": 4}],
                "summary": {"total": 4, "used": 0, "available": 4},
            }
        ),
    )
    monkeypatch.setattr(
        gpu_quota,
        "get_effective_gpu_quota_status",
        AsyncMock(
            return_value=[
                {
                    "gpu_type": "LEGACY",
                    "limit": 2,
                    "in_use": 1,
                    "available": 1,
                }
            ]
        ),
    )
    response = await client.get("/api/v1/dashboard/gpu-available")
    assert response.status_code == 200
    assert response.json()["gpu_types"][0]["available"] == 1
