"""Stored capacity is an advisory view, never native visibility or create authority."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import requests

from app.services import flavor_automation_policy, flavor_capacity, flavor_discovery, keystone, nova
from app.services.flavor_capacity import evaluate_flavor_capacities as native_capacity_evaluator
from tests.test_flavor_capacity import (
    CPU_SHAPE,
    ONE,
    PROJECT,
    ROOT_A,
    ROOT_B,
    ZONE,
    allocation,
    flavor,
)
from tests.test_flavor_capacity import (
    cloud as cloud,
)
from tests.test_flavor_capacity_admission import PAYLOAD
from tests.test_flavor_capacity_admission import sources as sources


@pytest.fixture
def storage(monkeypatch):
    class Store:
        def __init__(self):
            self.values = {}

        async def get(self, key):
            return self.values.get(key)

        async def set(self, key, value, ttl):
            self.values[key] = value

        async def delete(self, *keys):
            for key in keys:
                self.values.pop(key, None)

    store = Store()
    monkeypatch.setattr(flavor_discovery.cache, "get_backend", lambda: store)
    monkeypatch.setattr(
        flavor_automation_policy,
        "load_policy",
        AsyncMock(return_value={"revision": 1, "hosts": [], "gpu_profiles": []}),
    )
    return store


async def prepare(cloud, monkeypatch, flavors):
    monkeypatch.setattr(nova, "list_catalog_flavors", lambda _conn: flavors)
    conn = keystone.get_admin_project_connection()
    try:
        await flavor_discovery.refresh_once(conn)
    finally:
        conn.close()


async def project(*flavors, project_id=PROJECT, zone=ZONE, fresh=False):
    return await flavor_capacity.evaluate_flavor_capacities(
        flavors, project_id=project_id, availability_zone=zone, fresh=fresh
    )


async def test_warmed_view_reuses_observation_but_admission_sees_new_shortage(cloud, storage, monkeypatch):
    cloud.add_host(ROOT_B, vcpu=(16, 0), ram=(32768, 0))
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]
    cpu = flavor("cpu", vcpus=8, ram=8192)
    await prepare(cloud, monkeypatch, [cpu])
    raw = json.loads(storage.values[flavor_discovery._key("capacity")])
    cloud.calls.clear()
    cloud.usages[ROOT_B]["VCPU"] = 12

    first, second = await asyncio.gather(project(cpu), project(cpu))
    assert first["cpu"].status == second["cpu"].status == "available"
    assert first["cpu"].remaining_vcpus == 16
    assert first["cpu"].checked_at == datetime.fromtimestamp(raw["observed_at"], UTC).isoformat()
    assert cloud.calls == []
    admitted = (await project(cpu, fresh=True))["cpu"]
    assert admitted.status == "insufficient"
    assert admitted.remaining_vcpus == 4


async def test_warmup_does_not_freeze_an_arbitrary_tenant_or_zone(cloud, storage, monkeypatch):
    cloud.add_host(ROOT_A, vcpu=(8, 0), ram=(16384, 0), zone="restricted-zone")
    cloud.add_host(ROOT_B, vcpu=(32, 0), ram=(65536, 0), zone=ZONE)
    cloud.aggregate(ROOT_A)["metadata"]["filter_tenant_id"] = PROJECT
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE}), allocation({ROOT_B: ONE})]
    cpu = flavor("cpu", vcpus=4, ram=8192)
    await prepare(cloud, monkeypatch, [cpu])
    cloud.calls.clear()

    owner = (await project(cpu, zone="restricted-zone"))["cpu"]
    stranger = (await project(cpu, project_id="other-project", zone="restricted-zone"))["cpu"]
    ordinary = (await project(cpu))["cpu"]
    assert (owner.status, owner.remaining_vcpus) == ("available", 8)
    assert stranger.status == "insufficient"
    assert (ordinary.status, ordinary.remaining_vcpus) == ("available", 32)
    assert cloud.calls == []


@pytest.mark.parametrize("damage", ["expired", "future", "missing", "malformed", "redis-error", "profile-change"])
async def test_missing_or_untrusted_observation_is_unknown_without_foreground_native_fanout(
    cloud, storage, monkeypatch, damage
):
    cloud.add_host(ROOT_B)
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]
    cpu = flavor("cpu")
    await prepare(cloud, monkeypatch, [cpu])
    key = flavor_discovery._key("capacity")
    value = json.loads(storage.values[key])
    if damage in ("expired", "future"):
        value["observed_at"] = time.time() + (-31 if damage == "expired" else 60)
        storage.values[key] = json.dumps(value)
    elif damage == "missing":
        storage.values.pop(key)
    elif damage == "malformed":
        storage.values[key] = "not-json"
    elif damage == "redis-error":
        monkeypatch.setattr(storage, "get", AsyncMock(side_effect=ConnectionError("offline")))
    else:
        value["profiles"] = "different-approved-map"
        storage.values[key] = json.dumps(value)
    cloud.calls.clear()

    capacity = (await project(cpu))["cpu"]
    assert capacity.status == "unavailable"
    assert capacity.remaining_vcpus is None
    assert capacity.remaining_ram_mb is None
    assert cloud.calls == []


async def test_unobserved_new_shape_is_not_inferred_from_cpu_capacity(cloud, storage, monkeypatch):
    cloud.add_host(ROOT_B)
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]
    cpu = flavor("cpu")
    await prepare(cloud, monkeypatch, [cpu])
    cloud.calls.clear()
    gpu = flavor("gpu", specs={"pci_passthrough:alias": "RTX-3090ti:1"})
    assert (await project(gpu))["gpu"].status == "unavailable"
    assert cloud.calls == []


async def test_one_shape_transport_failure_preserves_other_observed_shapes(cloud, storage, monkeypatch):
    cloud.add_host(ROOT_B)
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]
    original_send = cloud.send

    def send(request, **kwargs):
        if "resources_PCI0" in request.url:
            raise requests.exceptions.ConnectionError("GPU shape connection reset")
        return original_send(request, **kwargs)

    monkeypatch.setattr(cloud, "send", send)
    cpu = flavor("cpu")
    gpu = flavor("gpu", specs={"pci_passthrough:alias": "RTX-3090ti:1"})
    await prepare(cloud, monkeypatch, [cpu, gpu])
    cloud.calls.clear()
    result = await project(cpu, gpu)
    assert result["cpu"].status == "available"
    assert result["gpu"].status == "unavailable"
    assert cloud.calls == []


async def test_newly_visible_flavor_is_not_hidden_until_background_refresh(storage, monkeypatch):
    old, new = flavor("old"), flavor("new", vcpus=8)
    await flavor_discovery._store(
        "catalog", {"schema": 1, "observed_at": time.time(), "flavors": [old.model_dump()]}, 90
    )
    monkeypatch.setattr(nova, "project_flavor_visibility", lambda _conn: {"old": True, "new": False})
    monkeypatch.setattr(nova, "list_flavors", lambda _conn: [old, new])
    result = await flavor_discovery.list_flavors(SimpleNamespace())
    assert [(row.id, row.vcpus) for row in result] == [("old", 4), ("new", 8)]


async def test_warm_catalog_does_not_preserve_a_revoked_or_formerly_public_grant(storage, monkeypatch):
    from unittest.mock import MagicMock

    rows = [flavor("revoked"), flavor("allowed")]
    await flavor_discovery._store(
        "catalog", {"schema": 1, "observed_at": time.time(), "flavors": [f.model_dump() for f in rows]}, 90
    )
    conn = MagicMock()
    conn._afterglow_project_id = "target"
    conn._afterglow_compute_admin = True
    conn.compute.flavors.return_value = [
        SimpleNamespace(id="revoked", is_public=False),
        SimpleNamespace(id="allowed", is_public=False),
    ]
    conn.compute.get_flavor_access.side_effect = lambda fid: [
        {"tenant_id": "target" if fid == "allowed" else "service-project"}
    ]
    monkeypatch.setattr(nova, "list_flavors", lambda _conn: pytest.fail("warm metadata was not used"))
    result = await flavor_discovery.list_flavors(conn)
    assert [(f.id, f.is_public) for f in result] == [("allowed", False)]


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/flavors?capacity=create",
        "/api/v1/admin/instances/flavors-for-project?project_id=target&capacity=create",
    ],
)
async def test_chooser_keeps_current_quota_blockers_when_stored_hosts_are_available(
    admin_client, mock_conn, storage, monkeypatch, endpoint
):
    from app.models.compute import FlavorCapacityInfo

    cpu = flavor("cpu", vcpus=4, ram=8192)
    await flavor_discovery._store(
        "catalog", {"schema": 1, "observed_at": time.time(), "flavors": [cpu.model_dump()]}, 90
    )
    mock_conn.compute.flavors.return_value = [SimpleNamespace(id="cpu", is_public=True)]
    monkeypatch.setattr("app.api.identity.admin_instances._make_admin_conn", lambda *_: mock_conn)
    monkeypatch.setattr(
        flavor_capacity,
        "evaluate_flavor_capacities",
        AsyncMock(return_value={"cpu": FlavorCapacityInfo(status="available", checked_at="2026-10-31T00:00:00+00:00")}),
    )
    monkeypatch.setattr(
        nova,
        "get_project_quota",
        lambda *_args, **_kwargs: {key: {"limit": 0, "in_use": 0} for key in ("instances", "cores", "ram")},
    )
    monkeypatch.setattr(
        "app.services.resource_policy_store.resolve_policies",
        AsyncMock(return_value={"nova.default_compute_availability_zone": ZONE}),
    )
    response = await admin_client.get(endpoint)
    assert response.status_code == 200
    result = response.json()[0]["eligibility"]
    assert result["capacity"]["status"] == "available"
    assert result["selectable"] is False
    assert {b["code"] for b in result["blockers"]} >= {
        "instances_insufficient",
        "cores_insufficient",
        "ram_insufficient",
    }


@pytest.mark.parametrize("method", ["POST", "DELETE"])
@pytest.mark.usefixtures("available_flavor_capacity")
async def test_manual_spec_edit_replaces_warm_chooser_metadata(admin_client, mock_conn, method):
    specs = {} if method == "POST" else {"afterglow:frontend_visible": "false"}
    native = SimpleNamespace(
        id="manual",
        name="manual-cpu",
        vcpus=4,
        ram=8192,
        disk=0,
        is_public=True,
        description="manual",
        extra_specs=specs,
    )
    cached = flavor("manual").model_copy(update={"extra_specs": dict(specs)})
    await flavor_discovery._store(
        "catalog", {"schema": 1, "observed_at": time.time(), "flavors": [cached.model_dump()]}, 90
    )
    mock_conn.compute.flavors.return_value = [native]
    mock_conn.compute.get_flavor.return_value = native
    mock_conn.compute.create_flavor_extra_specs.side_effect = lambda _fid, changes: specs.update(changes)
    mock_conn.compute.delete_flavor_extra_specs_property.side_effect = lambda _fid, key: specs.pop(key)
    endpoint = "/api/v1/admin/flavors/manual/extra-specs"
    if method == "POST":
        response = await admin_client.post(endpoint, json={"key": "afterglow:frontend_visible", "value": "false"})
    else:
        response = await admin_client.delete(endpoint + "/afterglow:frontend_visible")
    assert response.status_code == (200 if method == "POST" else 204)
    listed = await admin_client.get("/api/v1/flavors?capacity=create")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == ([] if method == "POST" else ["manual"])


async def test_manual_refresh_reads_bounded_observation_but_native_admission_still_sees_contention(
    admin_client, mock_conn, cloud, storage, monkeypatch
):
    cloud.add_host(ROOT_B, vcpu=(16, 0), ram=(32768, 0))
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]
    cpu = flavor("cpu", vcpus=8, ram=8192)
    await prepare(cloud, monkeypatch, [cpu])
    mock_conn.compute.flavors.return_value = [SimpleNamespace(id="cpu", is_public=True)]
    monkeypatch.setattr(
        nova,
        "get_project_quota",
        lambda *_args, **_kwargs: {key: {"limit": -1, "in_use": 0} for key in ("instances", "cores", "ram")},
    )
    monkeypatch.setattr(
        "app.services.resource_policy_store.resolve_policies",
        AsyncMock(return_value={"nova.default_compute_availability_zone": ZONE}),
    )
    cloud.calls.clear()
    cloud.usages[ROOT_B]["VCPU"] = 12
    response = await admin_client.get("/api/v1/flavors?capacity=create&refresh=true")
    assert response.status_code == 200
    assert response.json()[0]["eligibility"]["capacity"]["status"] == "available"
    assert cloud.calls == []
    assert (await project(cpu, fresh=True))["cpu"].status == "insufficient"


async def test_create_rejects_fresh_spec_and_capacity_shortage_despite_ready_stored_catalog(
    admin_client, mock_conn, cloud, storage, sources, monkeypatch
):
    cloud.add_host(ROOT_B, vcpu=(16, 0), ram=(32768, 0))
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]
    old = flavor("cpu", vcpus=4, ram=8192)
    await prepare(cloud, monkeypatch, [old])
    monkeypatch.setattr(flavor_capacity, "evaluate_flavor_capacities", native_capacity_evaluator)
    mock_conn.compute.flavors.return_value = [SimpleNamespace(id="cpu", is_public=True)]
    listed = await admin_client.get("/api/v1/flavors?capacity=create")
    assert listed.status_code == 200
    assert listed.json()[0]["eligibility"]["selectable"] is True

    # Either stale specs (4 units) or stale capacity (16 free units) would admit
    # this request. Only the fresh 8-unit spec AND the fresh 4-unit headroom reject it.
    changed = old.model_copy(update={"extra_specs": {"resources:VCPU": "8"}})
    monkeypatch.setattr(nova, "list_flavors", lambda _conn: [changed])
    cloud.usages[ROOT_B]["VCPU"] = 12
    with (
        patch("app.services.cinder.create_volume_from_image") as volume,
        patch("app.services.nova.create_server") as server,
    ):
        response = await admin_client.post("/api/v1/instances", json={**PAYLOAD, "flavor_id": old.id})
    assert response.status_code == 409
    assert "host_capacity_insufficient" in response.json()["detail"]
    volume.assert_not_called()
    server.assert_not_called()


@pytest.mark.parametrize("failure", ["transport", "rejected", "malformed", "inventory"])
async def test_failed_shapes_are_aggregated_with_native_read_counts_and_safe_reasons(
    cloud, storage, monkeypatch, caplog, failure
):
    from app.utils.structured_logging import JSONFormatter

    cloud.add_host(ROOT_B, pcpu=(16, 0))
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]
    flavors = [flavor(f"cpu-{index}", vcpus=index + 1) for index in range(20)] + [
        flavor("dedicated", specs={"hw:cpu_policy": "dedicated"})
    ]
    secret = "native-url-query-body-must-not-appear"
    native_reads = []
    original_send = cloud.send

    def send(request, **kwargs):
        if "/compute/v2.1/" in request.url or "/placement/" in request.url:
            native_reads.append(request.url)
        if "/allocation_candidates" in request.url and failure == "transport":
            raise requests.exceptions.ConnectionError(secret)
        return original_send(request, **kwargs)

    monkeypatch.setattr(cloud, "send", send)
    if failure == "rejected":
        cloud.failures["/placement/allocation_candidates"] = (400, secret.encode())
    elif failure == "malformed":
        cloud.failures["/placement/allocation_candidates"] = (200, json.dumps({"errors": secret}).encode())
    elif failure == "inventory":
        cloud.failures[f"/placement/resource_providers/{ROOT_B}/inventories"] = (503, secret.encode())
    with caplog.at_level(logging.WARNING, logger="app.services.flavor_discovery"):
        await prepare(cloud, monkeypatch, flavors)
    records = [record for record in caplog.records if record.name == "app.services.flavor_discovery"]
    assert len(records) == 1
    record = records[0]
    assert record.shapes_total == record.shapes_attempted == 2
    assert record.shapes_failed == (1 if failure == "inventory" else 2)
    assert record.shapes_succeeded + record.shapes_failed == record.shapes_attempted
    assert record.shapes_skipped == 0
    assert record.native_reads_attempted == len(native_reads)
    assert record.native_reads_attempted == record.native_reads_completed + record.native_reads_failed
    assert record.native_reads_failed == (0 if failure == "malformed" else record.shapes_failed)
    assert sum(group["count"] for group in record.failures) == record.shapes_failed
    assert {group["stage"] for group in record.failures} == {
        "inventories" if failure == "inventory" else "allocation_candidates"
    }
    assert {group["reason"] for group in record.failures} == {
        "transport" if failure == "transport" else "observation_rejected"
    }
    assert secret not in JSONFormatter().format(record)
    native_reads.clear()
    result = await project(*flavors)
    assert all(result[row.id].status == "unavailable" for row in flavors[:20])
    assert all(result[row.id].remaining_vcpus is None for row in flavors[:20])
    assert native_reads == []


async def test_discovery_deadline_reports_skipped_shapes_without_inventing_capacity(
    cloud, storage, monkeypatch, caplog
):
    cloud.add_host(ROOT_B)
    flavors = [flavor("cpu"), flavor("dedicated", specs={"hw:cpu_policy": "dedicated"})]
    policy = {"gpu_profiles": []}
    clock = [100.0]
    original_shape = flavor_capacity._Snapshot.shape

    def shape(snapshot, client, deadline, demand):
        result = original_shape(snapshot, client, deadline, demand)
        clock[0] = deadline
        return result

    conn = keystone.get_admin_project_connection()
    try:
        with monkeypatch.context() as context:
            context.setattr(flavor_discovery.time, "monotonic", lambda: clock[0])
            context.setattr(flavor_capacity._Snapshot, "shape", shape)
            with caplog.at_level(logging.WARNING, logger="app.services.flavor_discovery"):
                records = flavor_discovery._observe(conn, flavors, policy)
    finally:
        conn.close()
    summaries = [record for record in caplog.records if record.name == "app.services.flavor_discovery"]
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.shapes_total == 2
    assert summary.shapes_attempted == summary.shapes_succeeded == summary.shapes_skipped == 1
    assert summary.shapes_failed == 0
    assert summary.deadline_exhausted is True
    await flavor_discovery._store(
        "capacity",
        {
            "schema": 1,
            "observed_at": time.time(),
            "profiles": flavor_discovery._profile_key(policy),
            "records": records,
        },
        30,
    )
    cloud.calls.clear()
    result = await project(*flavors)
    assert sorted(row.status for row in result.values()) == ["insufficient", "unavailable"]
    assert all(row.remaining_vcpus is None for row in result.values() if row.status == "unavailable")
    assert cloud.calls == []


async def test_inventory_deadline_distinguishes_native_attempt_from_dispatched_get(cloud, storage, monkeypatch, caplog):
    cloud.add_host(ROOT_B)
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]
    cpu = flavor("cpu")
    policy = {"gpu_profiles": []}
    clock = [100.0]
    dispatched = []
    original_send = cloud.send
    original_shape = flavor_capacity._Snapshot.shape

    def send(request, **kwargs):
        if "/compute/v2.1/" in request.url or "/placement/" in request.url:
            dispatched.append(request.url)
        return original_send(request, **kwargs)

    def shape(snapshot, client, deadline, demand):
        view = original_shape(snapshot, client, deadline, demand)
        assert view.roots
        clock[0] = deadline
        return view

    monkeypatch.setattr(cloud, "send", send)
    conn = keystone.get_admin_project_connection()
    try:
        with monkeypatch.context() as context:
            context.setattr(flavor_discovery.time, "monotonic", lambda: clock[0])
            context.setattr(flavor_capacity._Snapshot, "shape", shape)
            with caplog.at_level(logging.WARNING, logger="app.services.flavor_discovery"):
                records = flavor_discovery._observe(conn, [cpu], policy)
    finally:
        conn.close()
    summaries = [record for record in caplog.records if record.name == "app.services.flavor_discovery"]
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.shapes_attempted == summary.shapes_failed == 1
    assert summary.shapes_succeeded == summary.shapes_skipped == 0
    assert summary.deadline_exhausted is True
    assert summary.native_reads_attempted == len(dispatched) + 1
    assert summary.native_reads_completed == len(dispatched)
    assert summary.native_reads_failed == 1
    assert not any("/inventories" in url for url in dispatched)
    assert {(item["stage"], item["reason"], item["count"]) for item in summary.failures} == {
        ("inventories", "deadline", 1)
    }
    await flavor_discovery._store(
        "capacity",
        {
            "schema": 1,
            "observed_at": time.time(),
            "profiles": flavor_discovery._profile_key(policy),
            "records": records,
        },
        30,
    )
    dispatched.clear()
    result = (await project(cpu))["cpu"]
    assert result.status == "unavailable"
    assert result.remaining_vcpus is result.remaining_ram_mb is None
    assert dispatched == []
