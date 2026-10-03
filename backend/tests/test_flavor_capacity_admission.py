"""Consumer-visible create discovery/admission boundaries, independent of scheduling."""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.compute import FlavorCapacityInfo, FlavorInfo
from app.services.flavor_eligibility import (
    FlavorEligibilityUnavailable,
    evaluate_project_flavors,
    require_flavor_eligible,
)
from app.services.resource_policies import ResourcePolicyValidationError

FLAVOR = FlavorInfo(
    id="gpu-large",
    name="gpu.3090ti_24c_64g",
    vcpus=24,
    ram=65536,
    disk=100,
    extra_specs={"pci_passthrough:alias": "RTX3090Ti:1"},
)
CPU_FLAVOR = FlavorInfo(id="cpu-small", name="cpu.2c_4g", vcpus=2, ram=4096, disk=20, extra_specs={})
QUOTA = {
    "instances": {"limit": 10, "in_use": 1},
    "cores": {"limit": 64, "in_use": 8},
    "ram": {"limit": 262144, "in_use": 8192},
}
GPU_STATUS = [{"gpu_type": "RTX3090TI", "limit": 2, "available": 1, "in_use": 1}]
PAYLOAD = {"name": "capacity-check", "image_id": "image-a", "flavor_id": FLAVOR.id, "network_id": "net-a"}
WIZARD_LIST = "/api/v1/flavors?capacity=create"
ADMIN_WIZARD_LIST = "/api/v1/admin/instances/flavors-for-project?project_id=target-project&capacity=create"


def capacity(status="available"):
    return FlavorCapacityInfo(
        status=status,
        checked_at="2026-10-01T00:00:00+00:00",
        cpu_resource_class="VCPU",
        candidate_hosts=1 if status == "available" else 0,
        remaining_vcpus=32 if status == "available" else 16,
        remaining_ram_mb=98304,
    )


@pytest.fixture
def sources(monkeypatch, mock_conn):
    monkeypatch.setattr("app.services.nova.list_flavors", lambda _conn: [FLAVOR])
    monkeypatch.setattr("app.services.nova.get_project_quota", lambda _conn, _pid: QUOTA)
    monkeypatch.setattr("app.services.gpu_quota.get_effective_gpu_quota_status", AsyncMock(return_value=GPU_STATUS))
    monkeypatch.setattr(
        "app.services.resource_policy_store.resolve_policies",
        AsyncMock(return_value={"nova.default_compute_availability_zone": "gpu-zone"}),
    )
    monkeypatch.setattr("app.services.gpu_inventory.require_gpu_quota", AsyncMock(return_value=True))
    monkeypatch.setattr("app.services.instance_names.ensure_unique_instance_name", lambda _conn, name: name)
    monkeypatch.setattr(
        "app.services.instance_orchestration.resolve_availability_zones",
        AsyncMock(return_value=("gpu-zone", "storage-zone")),
    )
    monkeypatch.setattr("app.api.identity.admin_instances._make_admin_conn", lambda *_args: mock_conn)
    authority = AsyncMock(return_value={FLAVOR.id: capacity()})
    monkeypatch.setattr("app.services.flavor_capacity.evaluate_flavor_capacities", authority)
    return authority


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected_status", [("insufficient", 409), ("unavailable", 503)])
@pytest.mark.parametrize("flavor", [FLAVOR, CPU_FLAVOR], ids=["gpu", "cpu"])
@pytest.mark.parametrize("endpoint", ["/api/v1/instances", "/api/v1/instances/async", "/api/v1/admin/instances/async"])
async def test_create_rechecks_changed_capacity_before_any_mutation(
    admin_client, sources, monkeypatch, status, expected_status, flavor, endpoint
):
    # A previously available list cannot authorize a create after another VM took capacity or the check failed.
    monkeypatch.setattr("app.services.nova.list_flavors", lambda _conn: [flavor])
    sources.return_value = {flavor.id: capacity()}
    discovered = await admin_client.get(WIZARD_LIST)
    assert discovered.status_code == 200
    assert discovered.json()[0]["eligibility"]["selectable"] is True
    assert sources.await_args.kwargs["fresh"] is False  # wizard discovery may share a short-lived snapshot
    sources.return_value = {flavor.id: capacity(status)}
    payload = {**PAYLOAD, "flavor_id": flavor.id, **({"project_id": "target-project"} if "/admin/" in endpoint else {})}
    with (
        patch("app.services.cinder.create_volume_from_image") as volume,
        patch("app.services.nova.create_server") as server,
        patch("app.services.gpu_quota.reserve_gpu_quota", AsyncMock()) as reserve,
    ):
        response = await admin_client.post(endpoint, json=payload)
    assert response.status_code == expected_status
    assert sources.await_args.kwargs["fresh"] is True  # admission never reuses the discovery snapshot
    volume.assert_not_called()
    server.assert_not_called()
    reserve.assert_not_awaited()
    if status == "insufficient":
        assert "host_capacity_insufficient" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["/api/v1/flavors", "/api/v1/admin/instances/flavors-for-project?project_id=p"])
async def test_default_lists_stay_quota_only_without_operator_reads(admin_client, sources, monkeypatch, endpoint):
    # K3s and Drover share these lists: no capacity gating and no operator Keystone/Placement traffic.
    monkeypatch.setattr(
        "app.services.keystone.get_admin_project_connection",
        lambda: (_ for _ in ()).throw(AssertionError("default list opened an operator connection")),
    )
    sources.side_effect = AssertionError("default list evaluated create capacity")
    response = await admin_client.get(endpoint)
    assert response.status_code == 200
    eligibility = response.json()[0]["eligibility"]
    assert (eligibility["selectable"], eligibility["blockers"], eligibility["capacity"]) == (True, [], None)
    sources.assert_not_awaited()


@pytest.mark.asyncio
async def test_multi_vm_admin_list_does_not_claim_single_vm_capacity(admin_client, sources):
    response = await admin_client.get(f"{ADMIN_WIZARD_LIST}&count=5")
    assert response.json()[0]["eligibility"]["capacity"] is None
    sources.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", [WIZARD_LIST, ADMIN_WIZARD_LIST])
async def test_unknown_capacity_blocks_every_flavor(admin_client, mock_conn, sources, monkeypatch, endpoint):
    # An unverified snapshot never admits a VM: an operator or Placement outage blocks CPU and GPU flavors alike.
    monkeypatch.setattr("app.services.nova.list_flavors", lambda _conn: [FLAVOR, CPU_FLAVOR])
    sources.side_effect = RuntimeError("provider-private-id in failed authority")
    response = await admin_client.get(endpoint)
    assert response.status_code == 200
    rows = {row["id"]: row["eligibility"] for row in response.json()}
    for flavor in (FLAVOR, CPU_FLAVOR):
        assert rows[flavor.id]["selectable"] is False
        assert [blocker["code"] for blocker in rows[flavor.id]["blockers"]] == ["host_capacity_unavailable"]
        assert rows[flavor.id]["capacity"]["status"] == "unavailable"
        assert rows[flavor.id]["capacity"]["remaining_vcpus"] is None
    assert "provider-private-id" not in response.text

    for flavor in (FLAVOR, CPU_FLAVOR):
        with pytest.raises(FlavorEligibilityUnavailable):
            await require_flavor_eligible(mock_conn, "project-a", flavor, check_capacity=True)


@pytest.mark.asyncio
async def test_missing_default_zone_blocks_every_flavor(client, sources, monkeypatch):
    # The create precheck rejects an unconfigured default zone, so discovery must not offer any flavor either.
    monkeypatch.setattr("app.services.nova.list_flavors", lambda _conn: [FLAVOR, CPU_FLAVOR])
    monkeypatch.setattr(
        "app.services.resource_policy_store.resolve_policies",
        AsyncMock(
            side_effect=ResourcePolicyValidationError(
                "required resource policies are not configured: nova.default_compute_availability_zone"
            )
        ),
    )
    response = await client.get(WIZARD_LIST)
    assert response.status_code == 200
    rows = {row["id"]: row["eligibility"] for row in response.json()}
    for flavor in (FLAVOR, CPU_FLAVOR):
        assert rows[flavor.id]["selectable"] is False
        assert [blocker["code"] for blocker in rows[flavor.id]["blockers"]] == ["host_capacity_unavailable"]
        assert rows[flavor.id]["capacity"]["status"] == "unavailable"
    sources.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_zone_does_not_require_default_policy(client, sources, monkeypatch):
    monkeypatch.setattr(
        "app.services.resource_policy_store.resolve_policies", AsyncMock(side_effect=RuntimeError("missing policy"))
    )
    response = await client.get(f"{WIZARD_LIST}&availability_zone=gpu-zone")
    assert response.status_code == 200
    assert response.json()[0]["eligibility"]["selectable"] is True


@pytest.mark.asyncio
async def test_numa_unverified_host_fit_is_listed_and_admitted(client, mock_conn, sources):
    # Host totals fit and only the NUMA cell is left to Nova: neither discovery nor admission blocks it.
    sources.return_value = {FLAVOR.id: capacity().model_copy(update={"numa_unverified": True})}
    listed = (await client.get(WIZARD_LIST)).json()[0]["eligibility"]
    assert (listed["selectable"], listed["blockers"], listed["capacity"]["numa_unverified"]) == (True, [], True)
    admitted = await require_flavor_eligible(
        mock_conn, "project-a", FLAVOR, check_capacity=True, availability_zone="gpu-zone"
    )
    assert admitted.capacity is not None and admitted.capacity.numa_unverified is True


@pytest.mark.asyncio
async def test_host_capacity_does_not_override_target_project_quota(admin_client, sources, monkeypatch):
    monkeypatch.setattr(
        "app.services.nova.get_project_quota",
        lambda _conn, pid: {**QUOTA, "cores": {"limit": 16 if pid == "target-project" else 64, "in_use": 8}},
    )
    response = await admin_client.get(ADMIN_WIZARD_LIST)
    eligibility = response.json()[0]["eligibility"]
    assert eligibility["capacity"]["status"] == "available"
    assert eligibility["selectable"] is False
    assert eligibility["remaining"]["cores"] == 8
    assert [blocker["code"] for blocker in eligibility["blockers"]] == ["cores_insufficient"]


@pytest.mark.asyncio
async def test_resize_keeps_incremental_quota_contract_without_create_capacity(mock_conn, sources):
    sources.side_effect = AssertionError("Create capacity must not gate resize")
    current = FLAVOR.model_copy(update={"vcpus": 16, "ram": 32768})
    result = await evaluate_project_flavors(
        mock_conn, "project-a", [FLAVOR], current_flavor=current, check_capacity=True
    )
    eligibility = result[0].eligibility
    assert eligibility is not None
    assert eligibility.selectable is True
    assert eligibility.requirements.instances == 0
    assert eligibility.requirements.cores == 8
    assert eligibility.requirements.ram_mb == 32768
    assert eligibility.capacity is None
    sources.assert_not_awaited()
