"""Afterglow pool policy supplements stock native quotas and replaces the old GPU ledger."""

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.compute import FlavorInfo
from app.services import compute_pools, flavor_eligibility, gpu_inventory, gpu_quota

GPU = "CUSTOM_PCI_10DE_2204"


def pool_snapshot():
    return {
        "domain_id": "org",
        "project_id": "project-a",
        "enabled": True,
        "state": "active",
        "limits": {"CPU": 32, "MEMORY_MB": 65536, GPU: 4},
        "usage": {"CPU": 24, "MEMORY_MB": 49152, GPU: 3},
        "available": {"CPU": 8, "MEMORY_MB": 16384, GPU: 1},
        "project_limits": {},
        "project_usage": {"CPU": 2, "MEMORY_MB": 4096, GPU: 0},
        "project_available": {"CPU": 30, "MEMORY_MB": 61440, GPU: 4},
        "policy_ready": True,
        "control_scope": "afterglow",
        "_aliases": [{"name": "RTX3090", "resource_class": GPU}],
        "_pci_aliases": [{"name": "RTX3090", "resource_class": GPU, "is_gpu": True, "classification_verified": True}],
        "_resource_kinds": {GPU: "gpu"},
    }


def flavor(gpus=1, cores=4):
    return FlavorInfo(
        id=f"g{gpus}-c{cores}",
        name="gpu.profile",
        vcpus=cores,
        ram=8192,
        disk=0,
        extra_specs={"pci_passthrough:alias": f"RTX3090:{gpus}"},
    )


def legacy_quota():
    return {
        "instances": {"limit": 10, "in_use": 1},
        "cores": {"limit": 32, "in_use": 2},
        "ram": {"limit": 65536, "in_use": 4096},
    }


@pytest.mark.asyncio
async def test_shared_pool_replaces_only_legacy_gpu_ledger_not_native_quotas(monkeypatch):
    snapshot = pool_snapshot()
    monkeypatch.setattr(compute_pools, "project_pool_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(flavor_eligibility.nova, "get_project_quota", lambda *a, **kw: legacy_quota())
    legacy = AsyncMock(side_effect=AssertionError("retired project GPU authority used"))
    monkeypatch.setattr(gpu_quota, "get_effective_gpu_quota_status", legacy)
    result = await flavor_eligibility.evaluate_project_flavors(MagicMock(), "project-a", [flavor(), flavor(2)])
    assert result[0].eligibility.selectable is True
    assert result[0].eligibility.quota_scope == "domain"
    assert result[0].eligibility.remaining.cores == 8
    assert result[0].eligibility.remaining.gpus == {GPU: 1}
    assert result[1].eligibility.selectable is False
    assert [(b.code, b.resource) for b in result[1].eligibility.blockers] == [("domain_pool_exhausted", GPU)]


@pytest.mark.asyncio
async def test_domain_gpu_admission_preserves_gpu_initialization_without_legacy_reservation(monkeypatch):
    from app.models.compute import FlavorCapacityInfo
    from app.services import flavor_capacity

    snapshot = pool_snapshot()
    monkeypatch.setattr(compute_pools, "project_pool_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(flavor_eligibility.nova, "get_project_quota", lambda *a, **kw: legacy_quota())
    monkeypatch.setattr(
        flavor_capacity,
        "evaluate_flavor_capacities",
        AsyncMock(return_value={"g1-c4": FlavorCapacityInfo(status="available", checked_at="2026-10-30T00:00:00Z")}),
    )
    reserve = AsyncMock(side_effect=AssertionError("domain pool must not reserve through the legacy ledger"))
    monkeypatch.setattr(gpu_quota, "reserve_gpu_quota", reserve)

    admitted = await flavor_eligibility.admit_flavor(MagicMock(), "project-a", flavor(), availability_zone="nova")

    assert admitted.gpu_requested == {GPU: 1}
    assert admitted.reservation_id is None
    reserve.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_subcap_does_not_hide_free_domain_pool(monkeypatch):
    snapshot = pool_snapshot()
    snapshot["project_limits"] = {GPU: 0}
    snapshot["project_available"][GPU] = 0
    monkeypatch.setattr(compute_pools, "project_pool_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(flavor_eligibility.nova, "get_project_quota", lambda *a, **kw: legacy_quota())
    result = await flavor_eligibility.evaluate_project_flavors(MagicMock(), "project-a", [flavor()])
    assert not result[0].eligibility.selectable
    assert [b.code for b in result[0].eligibility.blockers] == ["project_pool_ceiling_exhausted"]
    assert snapshot["available"][GPU] == 1


@pytest.mark.asyncio
async def test_resize_reuses_current_gpu_without_charging_it_twice(monkeypatch):
    snapshot = pool_snapshot()
    snapshot["usage"][GPU] = 4
    snapshot["available"][GPU] = 0
    monkeypatch.setattr(compute_pools, "project_pool_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(flavor_eligibility.nova, "get_project_quota", lambda *a, **kw: legacy_quota())
    current, target = flavor(), flavor(cores=8)
    result = await flavor_eligibility.evaluate_project_flavors(
        MagicMock(), "project-a", [target], current_flavor=current
    )
    assert result[0].eligibility.selectable is True
    assert result[0].eligibility.requirements.cores == 4
    assert result[0].eligibility.requirements.gpus == {}


@pytest.mark.asyncio
async def test_pool_inventory_failure_cannot_fall_back_to_legacy_authority(monkeypatch):
    monkeypatch.setattr(
        compute_pools, "project_pool_snapshot", AsyncMock(side_effect=compute_pools.ComputePoolUnavailable("denied"))
    )
    monkeypatch.setattr(flavor_eligibility.nova, "get_project_quota", lambda *a, **kw: legacy_quota())
    monkeypatch.setattr(gpu_quota, "get_effective_gpu_quota_status", AsyncMock(return_value=[]))
    result = await flavor_eligibility.evaluate_project_flavors(MagicMock(), "project-a", [flavor()])
    assert not result[0].eligibility.selectable
    assert "domain_pool_unavailable" in [b.code for b in result[0].eligibility.blockers]
    with pytest.raises(gpu_quota.GpuQuotaUnavailable):
        await gpu_inventory.require_gpu_quota(MagicMock(), flavor(), project_id="project-a")


@pytest.mark.asyncio
async def test_gpu_status_reports_domain_usage_but_project_limited_headroom(monkeypatch):
    snapshot = pool_snapshot()
    snapshot["project_limits"] = {GPU: 0}
    snapshot["project_available"][GPU] = 0
    original = deepcopy(snapshot)
    monkeypatch.setattr(compute_pools, "project_pool_snapshot", AsyncMock(return_value=snapshot))
    rows = await gpu_quota.get_effective_gpu_quota_status(MagicMock(), "project-a")
    assert rows[0]["limit"] == 4
    assert rows[0]["in_use"] == 3
    assert rows[0]["available"] == 0
    assert rows[0]["project_limit"] == 0
    assert snapshot == original


@pytest.mark.asyncio
async def test_legacy_gpu_write_cannot_create_competing_policy(monkeypatch):
    monkeypatch.setattr(compute_pools, "project_pool_snapshot", AsyncMock(return_value=pool_snapshot()))
    with pytest.raises(ValueError, match="domain compute pool"):
        await gpu_quota.set_project_gpu_quota(MagicMock(), "project-a", "RTX3090", 99)
    with pytest.raises(ValueError, match="domain compute pool"):
        await gpu_quota.delete_project_gpu_quota(MagicMock(), "project-a", "RTX3090")


@pytest.mark.asyncio
async def test_paused_pool_never_restores_legacy_cpu_or_gpu_authority(monkeypatch):
    snapshot = {**pool_snapshot(), "enabled": False, "state": "paused"}
    monkeypatch.setattr(compute_pools, "project_pool_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(flavor_eligibility.nova, "get_project_quota", lambda *a, **kw: legacy_quota())
    monkeypatch.setattr(
        gpu_quota, "get_effective_gpu_quota_status", AsyncMock(side_effect=AssertionError("legacy used"))
    )
    result = await flavor_eligibility.evaluate_project_flavors(MagicMock(), "project-a", [flavor()])
    assert not result[0].eligibility.selectable
    assert result[0].eligibility.quota_scope == "domain"
    assert "domain_pool_paused" in {blocker.code for blocker in result[0].eligibility.blockers}
    with pytest.raises(gpu_quota.GpuQuotaDenied, match="paused"):
        await gpu_inventory.require_gpu_quota(MagicMock(), flavor(), project_id="project-a")


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["cores", "ram"])
async def test_native_project_exhaustion_blocks_despite_large_domain_headroom(monkeypatch, resource):
    snapshot = pool_snapshot()
    quota = legacy_quota()
    quota[resource] = {"limit": 0, "in_use": 0}
    monkeypatch.setattr(compute_pools, "project_pool_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(flavor_eligibility.nova, "get_project_quota", lambda *a, **kw: quota)
    result = await flavor_eligibility.evaluate_project_flavors(MagicMock(), "project-a", [flavor()])
    eligibility = result[0].eligibility
    assert not eligibility.selectable
    assert f"{resource}_insufficient" in {blocker.code for blocker in eligibility.blockers}
    assert getattr(eligibility.remaining, "cores" if resource == "cores" else "ram_mb") == 0
