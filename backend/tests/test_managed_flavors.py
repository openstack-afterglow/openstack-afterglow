"""Managed stock Nova flavors: retained support, exact approval and fenced ACLs."""

from __future__ import annotations

import asyncio
import copy
import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import unquote

import fakeredis.aioredis
import pytest
from fastapi import HTTPException

from app.services import flavor_automation_policy as policy_svc
from app.services import managed_flavors as svc

_persist_state = svc._save
_persist_cpu_reset = svc._reset_unsent_cpu_claim
_graph_lock = svc.identity_roles._graph_lock

GPU = "CUSTOM_PCI_10DE_2208"
AUDIO = "CUSTOM_PCI_10DE_1AEB"
OTHER = "CUSTOM_PCI_10DE_2684"


def host(cpu=8, ram=65536, gpu=2, audio=2):
    return {
        "id": "root",
        "name": "compute-a",
        "removed": False,
        "observed_at": "2026-10-30T00:00:00+00:00",
        "state": "up",
        "status": "enabled",
        "cpu": {"capacity": cpu, "min": 1, "step": 1},
        "ram": {"capacity": ram, "min": 1, "step": 1},
        "gpu": {GPU: gpu, AUDIO: audio},
    }


def profile(name="3060lhr", resource=GPU):
    return {
        "name": name,
        "display_name": name.upper(),
        "enabled": True,
        "resource_class": resource,
        "resource_requirements": {resource: 1, AUDIO: 1},
        "extra_specs": {"pci_passthrough:alias": f"{name}:1,{name}-audio:1", "hw:cpu_policy": "shared"},
        "alias_resource_classes": {name: resource, f"{name}-audio": AUDIO},
    }


class Compute:
    def __init__(self):
        self.rows, self.specs, self.access, self.events = {}, {}, {}, []
        self.bad_specs = False

    def flavors(self, **kwargs):
        return list(self.rows.values())

    def get_endpoint(self):
        return "https://nova.invalid/v2.1"

    def create_flavor(self, **attrs):
        assert attrs["is_public"] is False
        if any(existing.name == attrs["name"] for existing in self.rows.values()):
            raise ValueError("Native Nova FlavorExists: flavor name must be unique")
        attrs = {"ephemeral": 0, "swap": 0, "rxtx_factor": 1.0, **attrs}
        row = SimpleNamespace(**attrs)
        self.rows[row.id], self.specs[row.id], self.access[row.id] = row, {}, set()
        self.events.append(("create", row.id))
        return row

    def get_flavor(self, fid):
        self.events.append(("read", fid))
        return self.rows[fid]

    def get(self, path, **kwargs):
        if path.startswith("/flavors/detail?"):
            payload = {"flavors": [copy.deepcopy(vars(row)) for row in self.rows.values()]}
            return SimpleNamespace(status_code=200, json=lambda: payload)
        parts = path.rstrip("/").split("/")
        fid = unquote(parts[-2] if parts[-1] in {"os-extra_specs", "os-flavor-access"} else parts[-1])
        if parts[-1] == "os-flavor-access":
            payload = {"flavor_access": self.get_flavor_access(fid)}
        elif parts[-1] == "os-extra_specs":
            self.events.append(("spec_read", fid))
            payload = {"extra_specs": copy.deepcopy(self.specs[fid])}
        else:
            row = copy.deepcopy(vars(self.rows[fid]))
            row["OS-FLV-EXT-DATA:ephemeral"] = row.pop("ephemeral")
            row["os-flavor-access:is_public"] = row.pop("is_public")
            payload = {"flavor": row}
        return SimpleNamespace(status_code=200, json=lambda: payload)

    def create_flavor_extra_specs(self, fid, specs):
        self.events.append(("spec_write", fid))
        if not self.bad_specs:
            self.specs[fid].update(specs)

    def get_flavor_access(self, fid):
        return [{"tenant_id": pid, "flavor_id": fid} for pid in sorted(self.access[fid])]

    def flavor_add_tenant_access(self, fid, pid):
        assert self.specs[fid].get(svc.MARKER) == svc.OWNER or self.specs[fid].get(svc.CPU_TOKEN)
        if self.specs[fid].get(svc.MARKER) == svc.OWNER:
            assert self.specs[fid]["afterglow:frontend_visible"] == "true"
        self.events.append(("grant", fid, pid))
        self.access[fid].add(pid)

    def flavor_remove_tenant_access(self, fid, pid):
        self.events.append(("revoke", fid, pid))
        self.access[fid].remove(pid)

    def delete_flavor(self, *args, **kwargs):
        pytest.fail("managed lifecycle must NEVER physically delete native shapes")


@pytest.fixture
def environment(monkeypatch):
    state = {**svc._default(), "enabled": True, "revision": 1}
    policy = {"revision": 0, "hosts": [host(cpu=1, ram=2048)], "gpu_profiles": []}
    compute = Compute()
    lease = SimpleNamespace(assert_owned=AsyncMock(), waiters_pending=AsyncMock(return_value=False))
    inventory = {"hosts": [host(cpu=1, ram=2048)], "complete": True, "error": None}
    projects = {"p1": {"domain_id": "d1", "limits": {"CPU": 64, "MEMORY_MB": 131072, GPU: 8}}}

    async def load():
        return copy.deepcopy(state)

    async def save(value, **kwargs):
        state.clear()
        state.update(copy.deepcopy(value))

    async def reset_unsent(flavor_id, token):
        claim = state["claims"].get(flavor_id)
        if isinstance(claim, dict) and claim.get("token") == token and claim.get("dispatched") is True:
            state["claims"][flavor_id]["dispatched"] = False

    async def reset_unsent_cpu(flavor_id, expected_claim):
        claim = state["cpu_claims"].get(flavor_id)
        if claim != expected_claim or not isinstance(claim, dict) or not claim.get("pending", {}).get("dispatched"):
            return False
        claim["pending"]["dispatched"] = False
        return True

    async def load_policy():
        return copy.deepcopy(policy)

    async def save_policy(value, **kwargs):
        assert policy["revision"] == kwargs["expected_revision"]
        policy.clear()
        policy.update(copy.deepcopy(value))

    async def call(function, *args, **kwargs):
        return function(*args, **kwargs)

    @asynccontextmanager
    async def lock(conn):
        yield lease

    def observe(conn):
        if inventory["error"]:
            raise inventory["error"]
        return copy.deepcopy(inventory["hosts"]), inventory["complete"]

    monkeypatch.setattr(svc, "_load", load)
    monkeypatch.setattr(svc, "_save", save)
    monkeypatch.setattr(svc, "_reset_unsent_claim", reset_unsent)
    monkeypatch.setattr(svc, "_reset_unsent_cpu_claim", reset_unsent_cpu)
    monkeypatch.setattr(svc, "run_sync", call)
    monkeypatch.setattr(policy_svc, "run_sync", call)
    monkeypatch.setattr(policy_svc, "load_policy", load_policy)
    monkeypatch.setattr(policy_svc, "_save", save_policy)
    monkeypatch.setattr(svc, "_compute", lambda conn: compute)
    monkeypatch.setattr(svc, "supported_hosts", observe)
    monkeypatch.setattr(svc, "_pool_projects", AsyncMock(side_effect=lambda: copy.deepcopy(projects)))
    monkeypatch.setattr(svc, "_pool_projects_sync", lambda: copy.deepcopy(projects))
    monkeypatch.setattr(svc.identity_roles, "_graph_lock", lock)
    monkeypatch.setattr("app.services.cache.invalidate", AsyncMock())
    return SimpleNamespace(
        state=state, policy=policy, compute=compute, lease=lease, inventory=inventory, projects=projects
    )


def test_shape_is_single_host_and_not_aggregate_capacity():
    shapes = svc.standard_shapes([host(cpu=128, ram=2048), host(cpu=1, ram=1048576)], [])
    assert {(row["vcpus"], row["ram"]) for row in shapes} == {(1, 2048), (1, 4096), (1, 8192), (1, 16384)}


@pytest.mark.parametrize("minimum,step", [(16384, 8192), (8192, 16384)])
def test_memory_shapes_obey_native_min_max_and_step_without_gpu_inventory(minimum, step):
    supported = host(cpu=16, ram=262144)
    supported["gpu"] = {}
    supported["cpu"] = svc._supported(
        {"total": 16, "reserved": 0, "allocation_ratio": 1, "min_unit": 2, "max_unit": 6, "step_size": 2},
        "VCPU",
    )
    supported["ram"] = svc._supported(
        {
            "total": 262144,
            "reserved": 0,
            "allocation_ratio": 1,
            "min_unit": minimum,
            "max_unit": 65536,
            "step_size": step,
        },
        "MEMORY_MB",
    )
    shapes = svc.standard_shapes([supported], [profile()])
    assert {(row["vcpus"], row["ram"]) for row in shapes} == {
        (2, 16384),
        (2, 32768),
        (4, 16384),
        (4, 32768),
        (4, 65536),
    }
    assert all(row["name"].startswith("mem.") and row["gpu_count"] == 0 for row in shapes)
    assert all(
        row["resource_requirements"] == {} and "pci_passthrough:alias" not in row["extra_specs"] for row in shapes
    )


def test_memory_ratio_extension_keeps_cpu_and_gpu_families_bounded():
    shapes = svc.standard_shapes([host(cpu=128, ram=2097152, gpu=8, audio=8)], [profile()])
    plain = [row for row in shapes if not row["gpu_count"]]
    gpu = [row for row in shapes if row["gpu_count"]]
    assert len(plain) == 8 * 4
    assert len({row["id"] for row in shapes}) == len(shapes)
    assert svc.standard_shapes([host(cpu=128, ram=2097152, gpu=8, audio=8)], [profile()]) == shapes
    assert {row["ram"] // (1024 * row["vcpus"]) for row in gpu} == {2, 4, 8}
    assert {row["gpu_count"] for row in gpu} == {1, 2, 4, 8}
    assert {(row["vcpus"], row["ram"]) for row in plain if row["ram"] == 16384 * row["vcpus"]} == {
        (cpu, cpu * 16384) for cpu in (1, 2, 4, 8, 16, 32, 64, 128)
    }
    assert all(
        row["name"] == f"{'mem' if row['ram'] >= row['vcpus'] * 4096 else 'cpu'}.{row['vcpus']}c_{row['ram'] // 1024}g"
        for row in plain
    )


@pytest.mark.parametrize("cpu", [1, 2, 4, 8, 16, 32, 64, 128])
@pytest.mark.parametrize("ratio", [2, 4, 8])
def test_existing_non_gpu_hardware_uuid_ignores_memory_family(cpu, ratio):
    ram = cpu * ratio * 1024
    specs = {
        "afterglow:managed_by": "domain-compute-v1",
        "afterglow:access_mode": "domain_quota",
        "afterglow:frontend_visible": "true",
    }
    old_identity = json.dumps([cpu, ram, None, 0, specs], sort_keys=True, separators=(",", ":"))
    # Fixed pre-memory-cutover IDs also catch namespace/identity changes.
    expected_id = {
        (1, 4): "889ff98e-26cd-5282-bb45-cc7930ac94fd",
        (1, 8): "27c5449f-0c8b-5dd6-869f-d0d0b72db404",
    }.get((cpu, ratio), str(uuid.uuid5(svc._NAMESPACE, old_identity)))
    shape = next(
        row
        for row in svc.standard_shapes([host(cpu=128, ram=2097152)], [])
        if row["vcpus"] == cpu and row["ram"] == ram
    )
    assert shape["id"] == expected_id
    assert shape["extra_specs"] == specs


def test_exact_profiles_gpu_and_companion_same_host_scaling():
    approved = profile()
    shapes = svc.standard_shapes([host(gpu=8, audio=1), host(gpu=1, audio=8)], [approved])
    gpu = [shape for shape in shapes if shape["gpu_count"]]
    assert gpu and {shape["gpu_count"] for shape in gpu} == {1}
    assert all(shape["name"] == f"gpu.3060lhrx1_{shape['vcpus']}c_{shape['ram'] // 1024}g" for shape in gpu)
    assert all(shape["extra_specs"]["pci_passthrough:alias"] == "3060lhr:1,3060lhr-audio:1" for shape in gpu)
    shapes = svc.standard_shapes([host(gpu=8, audio=8)], [approved])
    four = next(shape for shape in shapes if shape["gpu_count"] == 4)
    assert four["extra_specs"]["pci_passthrough:alias"] == "3060lhr:4,3060lhr-audio:4"
    assert four["name"] == f"gpu.3060lhrx4_{four['vcpus']}c_{four['ram'] // 1024}g"
    assert four["extra_specs"]["hw:cpu_policy"] == "shared"
    assert four["resource_requirements"] == {GPU: 4, AUDIO: 4}


def test_grouped_placement_counts_without_native_attachment_aliases_cannot_generate_shapes():
    approved = profile()
    approved["extra_specs"] = {f"resources1:{GPU}": "1", f"resources1:{AUDIO}": "1", "hw:cpu_policy": "shared"}
    approved["alias_resource_classes"] = {}
    with pytest.raises(ValueError, match="attachment alias"):
        svc.standard_shapes([host(gpu=4, audio=4)], [approved])


def test_unapproved_or_disabled_gpu_never_generates_gpu_flavors():
    assert all(not shape["gpu_count"] for shape in svc.standard_shapes([host()], []))
    approved = {**profile(), "enabled": False}
    assert all(not shape["gpu_count"] for shape in svc.standard_shapes([host()], [approved]))


@pytest.mark.parametrize(
    "field,value", [("total", True), ("reserved", -1), ("allocation_ratio", float("nan")), ("max_unit", 0)]
)
def test_supported_inventory_rejects_malformed_authority(field, value):
    inventory = {"total": 8, "reserved": 0, "allocation_ratio": 1, "min_unit": 1, "max_unit": 8, "step_size": 1}
    inventory[field] = value
    with pytest.raises(ValueError):
        svc._supported(inventory, "VCPU")


def test_supported_inventory_does_not_use_allocated_counts():
    inventory = {
        "total": 8,
        "reserved": 1,
        "allocation_ratio": 2,
        "min_unit": 1,
        "max_unit": 10,
        "step_size": 1,
        "used": 99999,
    }
    assert svc._supported(inventory, "VCPU")["capacity"] == 10
    with pytest.raises(ValueError, match="overcommit"):
        svc._supported(inventory, GPU)


@pytest.mark.asyncio
async def test_private_staging_readback_before_publication_and_idempotence(environment):
    env = environment
    first = await svc.reconcile(object())
    assert first["status"] == "complete" and first["items"][0]["status"] == "created"
    assert first["readiness"] == {"verified": True, "reason": "afterglow_policy_ready"}
    fid = first["items"][0]["id"]
    assert env.compute.access[fid] == {"p1"}
    events = env.compute.events
    assert events.index(("spec_write", fid)) < events.index(("grant", fid, "p1"))
    assert ("spec_read", fid) in events[events.index(("spec_write", fid)) + 1 : events.index(("grant", fid, "p1"))]
    second = await svc.reconcile(object())
    assert second["items"][0]["status"] == "unchanged"
    assert sum(event[0] == "create" for event in events) == 1
    assert sum(event[0] == "grant" for event in events) == 1
    assert "claims" not in first


@pytest.mark.asyncio
@pytest.mark.parametrize("observation", ["down", "disabled", "missing", "error", "shrink"])
async def test_host_liveness_and_partial_hardware_never_withdraw_supported_catalog(environment, observation):
    env = environment
    env.policy["gpu_profiles"] = [profile()]
    first = await svc.reconcile(object())
    before = {item["id"] for item in first["items"]}
    if observation in {"down", "disabled"}:
        env.inventory["hosts"][0]["state" if observation == "down" else "status"] = observation
    elif observation == "missing":
        env.inventory["hosts"] = []
    elif observation == "error":
        env.inventory["error"] = RuntimeError("Placement unavailable")
    else:
        env.inventory["hosts"][0]["gpu"] = {}
    result = await svc.reconcile(object())
    assert result["status"] == "complete"
    assert {item["id"] for item in result["items"]} == before
    assert all(env.compute.access[fid] == {"p1"} for fid in before)
    assert all(env.compute.specs[fid]["afterglow:frontend_visible"] == "true" for fid in before)


@pytest.mark.asyncio
async def test_explicit_host_removal_withdraws_without_delete_and_rediscovery_never_reactivates(environment):
    env = environment
    first = await svc.reconcile(object())
    fid = first["items"][0]["id"]
    env.policy["hosts"][0]["removed"] = True
    result = await svc.reconcile(object())
    assert result["items"][0]["status"] == "retired"
    assert env.policy["hosts"][0]["removed"] is True
    assert fid in env.compute.rows and not env.compute.access[fid]
    env.policy["hosts"][0]["removed"] = False
    await svc.reconcile(object())
    assert env.compute.access[fid] == {"p1"}
    assert sum(event[0] == "create" for event in env.compute.events) == 1


@pytest.mark.asyncio
async def test_per_model_shape_allocation_all_domain_projects_and_new_project_convergence(environment):
    env = environment
    env.inventory["hosts"][0]["gpu"][OTHER] = 4
    env.policy["gpu_profiles"] = [profile(), profile("4090", OTHER)]
    env.projects.clear()
    env.projects.update(
        {
            "lhr-a": {"domain_id": "d1", "limits": {GPU: 1}},
            "lhr-b": {"domain_id": "d1", "limits": {GPU: 1}},
            "4090": {"domain_id": "d2", "limits": {OTHER: -1}},
            "none": {"domain_id": "d3", "limits": {}},
            "zero": {"domain_id": "d4", "limits": {GPU: 0}},
        }
    )
    first = await svc.reconcile(object())
    for item in first["items"]:
        if item["gpu_resource_class"] == GPU:
            assert env.compute.access[item["id"]] == ({"lhr-a", "lhr-b"} if item["gpu_count"] == 1 else set())
        elif item["gpu_resource_class"] == OTHER:
            assert env.compute.access[item["id"]] == {"4090"}
    env.projects["new-lhr"] = {"domain_id": "d1", "limits": {GPU: 1}}
    del env.projects["lhr-a"]
    await svc.reconcile(object())
    one = next(item for item in first["items"] if item["gpu_resource_class"] == GPU and item["gpu_count"] == 1)
    assert env.compute.access[one["id"]] == {"lhr-b", "new-lhr"}


@pytest.mark.asyncio
async def test_profile_hardware_change_has_unique_names_and_retains_old_native_ids(environment):
    env = environment
    env.policy["gpu_profiles"] = [profile()]
    env.inventory["hosts"][0]["pcpu"] = {"capacity": 1, "min": 1, "step": 1}
    first = await svc.reconcile(object())
    old = {item["id"] for item in first["items"] if item["gpu_count"]}
    old_names = {fid: env.compute.rows[fid].name for fid in old}
    old_claims = {fid: copy.deepcopy(env.state["claims"][fid]) for fid in old}
    assert all("_1c_2g" in name and not name.endswith(fid.replace("-", "")[:12]) for fid, name in old_names.items())
    env.policy["gpu_profiles"][0]["extra_specs"]["hw:cpu_policy"] = "dedicated"
    result = await svc.reconcile(object())
    new = {item["id"] for item in result["items"] if item["gpu_count"]}
    assert old and new and old.isdisjoint(new)
    assert old.issubset(env.compute.rows)
    assert all(env.compute.rows[fid].name == old_names[fid] for fid in old)
    assert all(env.state["claims"][fid] == old_claims[fid] for fid in old)
    assert all(env.compute.rows[fid].name.endswith("." + fid.replace("-", "")[:12]) for fid in new)
    assert len({row.name for row in env.compute.rows.values()}) == len(env.compute.rows)
    assert all(not env.compute.access[fid] for fid in old)
    assert all(env.compute.access[fid] == {"p1"} for fid in new)


@pytest.mark.asyncio
async def test_missing_spec_readback_and_manual_id_never_publish(environment):
    env = environment
    env.compute.bad_specs = True
    result = await svc.reconcile(object())
    assert result["status"] == "unavailable"
    assert not any(event[0] == "grant" for event in env.compute.events)
    env.compute.bad_specs = False
    fid = result["items"][0]["id"]
    env.compute.rows[fid].description = "manual"
    env.compute.specs[fid] = {svc.MARKER: svc.OWNER}
    env.compute.events.clear()
    result = await svc.reconcile(object())
    assert result["items"][0]["status"] == "conflict" and env.compute.events == []


@pytest.mark.asyncio
async def test_owned_immutable_spec_drift_not_repaired_or_granted_new_access(environment):
    env = environment
    first = await svc.reconcile(object())
    fid = first["items"][0]["id"]
    env.compute.specs[fid]["hw:cpu_policy"] = "dedicated"
    env.projects["new"] = {"domain_id": "d1", "limits": {"CPU": 64, "MEMORY_MB": 131072}}
    result = await svc.reconcile(object())
    assert result["status"] == "unavailable" and result["items"][0]["status"] == "conflict"
    assert env.compute.access[fid] == {"p1"}


@pytest.mark.asyncio
@pytest.mark.parametrize("annotation", ["true", "false"])
async def test_usage_annotation_survives_visibility_reactivation(environment, annotation):
    env = environment
    first = await svc.reconcile(object())
    fid = first["items"][0]["id"]
    env.compute.specs[fid]["afterglow:usage_schedule_required"] = annotation
    env.compute.specs[fid]["afterglow:frontend_visible"] = "false"
    await svc.reconcile(object())
    assert env.compute.specs[fid]["afterglow:usage_schedule_required"] == annotation
    assert env.compute.specs[fid]["afterglow:frontend_visible"] == "true"


@pytest.mark.asyncio
async def test_complete_directory_failure_precedes_every_acl_mutation(environment, monkeypatch):
    env = environment
    first = await svc.reconcile(object())
    fid = first["items"][0]["id"]
    env.compute.events.clear()
    monkeypatch.setattr(svc, "_pool_projects", AsyncMock(side_effect=ValueError("partial directory")))
    result = await svc.reconcile(object())
    assert result["status"] == "unavailable"
    assert env.compute.access[fid] == {"p1"} and env.compute.events == []


@pytest.mark.asyncio
async def test_revision_and_lost_lease_fence_native_mutations(environment):
    env = environment
    await svc.configure(object(), revision=1, enabled=False, user_id="admin")
    with pytest.raises(HTTPException) as error:
        await svc._write(env.lease, 1, env.compute.create_flavor, id="never")
    assert error.value.status_code == 409
    with pytest.raises(HTTPException):
        await svc.configure(object(), revision=1, enabled=True, user_id="admin")
    await svc.configure(object(), revision=2, enabled=True, user_id="admin")
    env.lease.assert_owned.side_effect = HTTPException(409, "lease lost")
    with pytest.raises(HTTPException):
        await svc.reconcile(object())
    assert env.compute.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/v1/admin/flavor-automation", None),
        ("put", "/api/v1/admin/flavor-automation", {"revision": 0, "enabled": True}),
        ("post", "/api/v1/admin/flavor-automation/reconcile", None),
    ],
)
async def test_automation_routes_require_fresh_admin(non_admin_client, method, path, body):
    response = await non_admin_client.request(method, path, **({"json": body} if body else {}))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_automation_routes_and_strict_request(admin_client, environment):
    response = await admin_client.get("/api/v1/admin/flavor-automation")
    assert response.status_code == 200 and response.json()["readiness"]["reason"] == "afterglow_policy_ready"
    response = await admin_client.put("/api/v1/admin/flavor-automation", json={"revision": 1, "enabled": True})
    assert response.status_code == 200 and response.json()["revision"] == 2
    response = await admin_client.post("/api/v1/admin/flavor-automation/reconcile")
    assert response.status_code == 200 and response.json()["status"] == "complete"
    assert (
        await admin_client.put("/api/v1/admin/flavor-automation", json={"revision": True, "enabled": "yes"})
    ).status_code == 422


@pytest.mark.asyncio
async def test_unknown_native_create_is_not_replayed_in_same_pass(environment, monkeypatch):
    env = environment
    calls = []

    def uncertain(**kwargs):
        calls.append(kwargs)
        raise TimeoutError("native create may have succeeded")

    monkeypatch.setattr(env.compute, "create_flavor", uncertain)
    result = await svc.reconcile(object())
    assert result["status"] == "unavailable" and len(calls) == 1
    assert len(env.state["claims"]) == 1
    result = await svc.reconcile(object())
    assert result["status"] == "unavailable" and len(calls) == 1
    assert result["items"][0]["status"] == "conflict"


def test_three_approved_variant_names_are_preserved_without_model_inference():
    variants = [("3060", "CUSTOM_PCI_10DE_2504"), ("3060lhr", GPU), ("4090", OTHER)]
    supported = host(gpu=8, audio=8)
    supported["gpu"].update({resource: 8 for _, resource in variants})
    shapes = svc.standard_shapes([supported], [profile(name, resource) for name, resource in variants])
    gpu_names = {shape["name"].split(".")[1].split("_")[0].rsplit("x", 1)[0] for shape in shapes if shape["gpu_count"]}
    assert gpu_names == {"3060", "3060lhr", "4090"}


@pytest.mark.asyncio
@pytest.mark.parametrize("ram", [2048, 4096, 8192, 16384])
async def test_unknown_create_later_exact_owned_readback_converges_without_create_replay(environment, monkeypatch, ram):
    env = environment
    supported = host(cpu=1, ram=ram)
    supported["ram"]["min"] = ram
    env.policy["hosts"] = [copy.deepcopy(supported)]
    env.inventory["hosts"] = [supported]
    native_create = env.compute.create_flavor
    calls = []

    def accepted_but_timeout(**kwargs):
        calls.append(kwargs)
        native_create(**kwargs)
        raise TimeoutError("response lost after native commit")

    monkeypatch.setattr(env.compute, "create_flavor", accepted_but_timeout)
    first = await svc.reconcile(object())
    assert first["status"] == "unavailable" and len(calls) == 1
    second = await svc.reconcile(object())
    assert second["status"] == "complete" and len(calls) == 1
    assert env.compute.access[second["items"][0]["id"]] == {"p1"}
    expected = f"{'mem' if ram >= 4096 else 'cpu'}.1c_{ram // 1024}g"
    assert second["items"][0]["name"] == calls[0]["name"] == expected


@pytest.mark.asyncio
async def test_private_staged_claim_accepts_independent_usage_annotation(environment):
    env = environment
    shape = svc.standard_shapes(env.inventory["hosts"], [])[0]
    env.state["claims"][shape["id"]] = "owned"
    env.compute.create_flavor(
        **{key: shape[key] for key in ("id", "name", "vcpus", "ram", "disk")},
        is_public=False,
        description=f"afterglow:{svc.OWNER}:owned",
    )
    env.compute.specs[shape["id"]] = {"afterglow:usage_schedule_required": "true"}
    result = await svc.reconcile(object())
    assert result["status"] == "complete"
    assert env.compute.specs[shape["id"]] == {**shape["extra_specs"], "afterglow:usage_schedule_required": "true"}


@pytest.mark.asyncio
async def test_final_predispatch_fence_rejection_does_not_permanently_block_creation(environment, monkeypatch):
    env = environment
    original_fence = svc._fence
    calls = 0

    async def fail_final_fence(lease, revision):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise HTTPException(409, "lease lost before native dispatch")
        return await original_fence(lease, revision)

    monkeypatch.setattr(svc, "_fence", fail_final_fence)
    with pytest.raises(HTTPException):
        await svc.reconcile(object())
    assert not env.compute.events
    assert len(env.state["claims"]) == 1
    fid, claim = next(iter(env.state["claims"].items()))
    assert claim["dispatched"] is False
    token = claim["token"]
    monkeypatch.setattr(svc, "_fence", original_fence)
    result = await svc.reconcile(object())
    assert result["status"] == "complete"
    assert env.compute.rows[fid].description == f"afterglow:{svc.OWNER}:{token}"
    assert sum(event[0] == "create" for event in env.compute.events) == 1


@pytest.mark.asyncio
async def test_existing_full_version_name_remains_immutable_during_short_name_cutover(environment):
    env = environment
    first = await svc.reconcile(object())
    fid = first["items"][0]["id"]
    native = env.compute.rows[fid]
    old_name = f"cpu.ag.{native.vcpus}c.{native.ram // 1024}g." + fid.replace("-", "")
    native.name = old_name
    second = await svc.reconcile(object())
    assert second["status"] == "complete" and second["items"][0]["name"] == old_name
    assert native.name == old_name


def test_gpu_readable_and_canonical_cpu_names_keep_existing_identity():
    shapes = svc.standard_shapes([host()], [profile()])
    for shape in shapes:
        identity = [shape["vcpus"], shape["ram"], shape["gpu_resource_class"], shape["gpu_count"], shape["extra_specs"]]
        if shape["gpu_count"]:
            identity.append("3060lhr")
            assert shape["name"] == f"gpu.3060lhrx{shape['gpu_count']}_{shape['vcpus']}c_{shape['ram'] // 1024}g"
        else:
            family = "mem" if shape["ram"] >= 4096 * shape["vcpus"] else "cpu"
            assert shape["name"] == f"{family}.{shape['vcpus']}c_{shape['ram'] // 1024}g"
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        assert shape["id"] == str(uuid.uuid5(svc._NAMESPACE, encoded))


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["cpu", "legacy-short", "legacy-full"])
@pytest.mark.parametrize("durable_name", [False, True])
async def test_owned_memory_names_keep_native_ids_claims_and_acl_on_repeated_reconcile(
    environment, style, durable_name
):
    env = environment
    env.inventory["hosts"] = [host(cpu=1, ram=16384, gpu=0, audio=0)]
    env.policy["hosts"] = copy.deepcopy(env.inventory["hosts"])
    old = {}
    for shape in svc.standard_shapes(env.inventory["hosts"], []):
        if shape["ram"] not in {4096, 8192}:
            continue
        fid = shape["id"]
        name = f"cpu.1c_{shape['ram'] // 1024}g"
        if style.startswith("legacy"):
            suffix = fid.replace("-", "")
            name = f"cpu.ag.1c.{shape['ram'] // 1024}g." + (suffix[:12] if style.endswith("short") else suffix)
        claim = {"token": "owned", "dispatched": True, "name": name} if durable_name else "owned"
        env.state["claims"][fid] = copy.deepcopy(claim)
        env.compute.create_flavor(
            id=fid,
            name=name,
            vcpus=1,
            ram=shape["ram"],
            disk=0,
            is_public=False,
            description=f"afterglow:{svc.OWNER}:owned",
        )
        env.compute.specs[fid] = copy.deepcopy(shape["extra_specs"])
        env.compute.access[fid] = {"p1"}
        old[fid] = (
            copy.deepcopy(vars(env.compute.rows[fid])),
            copy.deepcopy(claim),
            copy.deepcopy(shape["extra_specs"]),
        )
    env.compute.events.clear()
    first = await svc.reconcile(object())
    assert first["status"] == "complete"
    assert {(item["name"], item["status"]) for item in first["items"] if item["id"] not in old} == {
        ("cpu.1c_2g", "created"),
        ("mem.1c_16g", "created"),
    }
    for fid, (snapshot, claim, specs) in old.items():
        assert vars(env.compute.rows[fid]) == snapshot
        assert env.state["claims"][fid] == claim
        assert env.compute.specs[fid] == specs and env.compute.access[fid] == {"p1"}
        assert not any(
            event[0] in {"create", "spec_write", "grant", "revoke"} and event[1] == fid for event in env.compute.events
        )
    env.compute.events.clear()
    second = await svc.reconcile(object())
    assert second["status"] == "complete" and all(item["status"] == "unchanged" for item in second["items"])
    assert len(env.compute.rows) == len({(row.vcpus, row.ram) for row in env.compute.rows.values()}) == 4
    assert all(access == {"p1"} for access in env.compute.access.values())
    assert not any(event[0] in {"create", "spec_write", "grant", "revoke"} for event in env.compute.events)


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["cpu", "legacy-short", "legacy-full"])
@pytest.mark.parametrize("dispatched", [False, True])
async def test_memory_name_reservation_survives_cutover_without_replaying_unknown_dispatch(
    environment, style, dispatched
):
    env = environment
    env.inventory["hosts"] = [host(cpu=1, ram=4096)]
    shape = next(row for row in svc.standard_shapes(env.inventory["hosts"], []) if row["ram"] == 4096)
    fid = shape["id"]
    name = "cpu.1c_4g"
    if style.startswith("legacy"):
        suffix = fid.replace("-", "")
        name = "cpu.ag.1c.4g." + (suffix[:12] if style.endswith("short") else suffix)
    reservation = {"token": "owned", "dispatched": dispatched, "name": name}
    env.state["claims"][fid] = copy.deepcopy(reservation)
    first = await svc.reconcile(object())
    item = next(item for item in first["items"] if item["id"] == fid)
    assert item["name"] == name
    if dispatched:
        assert item["status"] == "conflict" and fid not in env.compute.rows
        assert env.state["claims"][fid] == reservation
    else:
        assert item["status"] == "created" and env.compute.rows[fid].name == name
        assert env.compute.access[fid] == {"p1"}
    env.compute.events.clear()
    second = await svc.reconcile(object())
    assert next(item for item in second["items"] if item["id"] == fid)["status"] == (
        "conflict" if dispatched else "unchanged"
    )
    assert not any(event[0] == "create" for event in env.compute.events)


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["unowned", "hardware", "historical-suffix"])
async def test_historical_memory_name_never_overrides_exact_ownership_or_hardware_proof(environment, mismatch):
    env = environment
    env.inventory["hosts"] = [host(cpu=1, ram=4096)]
    shape = next(row for row in svc.standard_shapes(env.inventory["hosts"], []) if row["ram"] == 4096)
    fid = shape["id"]
    env.compute.create_flavor(
        id=fid,
        name="cpu.ag.1c.4g.wrong-identity" if mismatch == "historical-suffix" else "cpu.1c_4g",
        vcpus=2 if mismatch == "hardware" else 1,
        ram=4096,
        disk=0,
        is_public=False,
        description="manual" if mismatch == "unowned" else f"afterglow:{svc.OWNER}:owned",
    )
    env.state["claims"][fid] = "owned"
    env.compute.specs[fid] = copy.deepcopy(shape["extra_specs"])
    env.compute.access[fid] = {"existing-project"}
    snapshot = copy.deepcopy(vars(env.compute.rows[fid]))
    env.compute.events.clear()
    result = await svc.reconcile(object())
    assert next(item for item in result["items"] if item["id"] == fid)["status"] == "conflict"
    assert vars(env.compute.rows[fid]) == snapshot
    assert env.compute.access[fid] == {"existing-project"}
    assert not any(event[0] in {"spec_write", "grant", "revoke"} and event[1] == fid for event in env.compute.events)


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["legacy-short", "legacy-full", "canonical", "canonical-short", "canonical-full"])
async def test_owned_gpu_names_and_claims_survive_name_cutover(environment, style):
    env = environment
    env.policy["gpu_profiles"] = [profile()]
    first = await svc.reconcile(object())
    shape = next(item for item in first["items"] if item["gpu_count"])
    fid = shape["id"]
    native = env.compute.rows[fid]
    base = (
        f"gpu.3060lhr.{shape['gpu_count']}gpu.{shape['vcpus']}c.{shape['ram'] // 1024}g"
        if style.startswith("legacy")
        else native.name
    )
    suffix = fid.replace("-", "")
    if style.endswith("short"):
        native.name = base + "." + suffix[:12]
    elif style.endswith("full"):
        native.name = base + "." + suffix
    else:
        native.name = base
    expected_name = native.name
    before_claim = copy.deepcopy(env.state["claims"][fid])
    before_specs = copy.deepcopy(env.compute.specs[fid])
    before_access = set(env.compute.access[fid])
    env.compute.events.clear()
    second = await svc.reconcile(object())
    item = next(item for item in second["items"] if item["id"] == fid)
    assert second["status"] == "complete" and item["status"] == "unchanged"
    assert native.name == item["name"] == expected_name
    assert env.state["claims"][fid] == before_claim
    assert env.compute.specs[fid] == before_specs and env.compute.access[fid] == before_access
    assert not any(event[0] in {"create", "spec_write", "grant", "revoke"} for event in env.compute.events)


@pytest.mark.asyncio
@pytest.mark.parametrize("occupied", [1, 2, 3])
async def test_gpu_name_collisions_never_adopt_or_mutate_manual_flavors(environment, occupied):
    env = environment
    env.policy["gpu_profiles"] = [profile()]
    shape = next(shape for shape in svc.standard_shapes(env.inventory["hosts"], [profile()]) if shape["gpu_count"])
    suffix = shape["id"].replace("-", "")
    names = [shape["name"], shape["name"] + "." + suffix[:12], shape["name"] + "." + suffix]
    for index, name in enumerate(names[:occupied]):
        fid = f"manual-{index}"
        env.compute.create_flavor(id=fid, name=name, vcpus=1, ram=2048, disk=0, is_public=False, description="manual")
        env.compute.specs[fid] = {svc.MARKER: svc.OWNER, "pci_passthrough:alias": "manual-only:1"}
        env.compute.access[fid] = {"manual-project"}
    env.compute.events.clear()
    result = await svc.reconcile(object())
    item = next(item for item in result["items"] if item["id"] == shape["id"])
    if occupied == 3:
        assert item["status"] == "conflict"
        assert shape["id"] not in env.compute.rows and shape["id"] not in env.state["claims"]
    else:
        assert item["status"] == "created" and item["name"] == names[occupied]
        assert env.compute.access[shape["id"]] == {"p1"}
        env.compute.events.clear()
        again = await svc.reconcile(object())
        assert next(item for item in again["items"] if item["id"] == shape["id"])["name"] == names[occupied]
        assert not any(event[0] == "create" for event in env.compute.events)
    for index, name in enumerate(names[:occupied]):
        fid = f"manual-{index}"
        assert env.compute.rows[fid].name == name
        assert env.compute.access[fid] == {"manual-project"}
        assert env.compute.specs[fid] == {svc.MARKER: svc.OWNER, "pci_passthrough:alias": "manual-only:1"}
        assert not any(
            event[0] in {"spec_write", "grant", "revoke"} and event[1] == fid for event in env.compute.events
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("dispatched", [False, True])
async def test_reserved_or_unknown_gpu_name_cannot_collide_with_new_version(environment, dispatched):
    env = environment
    env.policy["gpu_profiles"] = [profile()]
    shape = next(shape for shape in svc.standard_shapes(env.inventory["hosts"], [profile()]) if shape["gpu_count"])
    reservation = {"token": "previous-version", "dispatched": dispatched, "name": shape["name"]}
    env.state["claims"]["previous-version-id"] = copy.deepcopy(reservation)
    result = await svc.reconcile(object())
    item = next(item for item in result["items"] if item["id"] == shape["id"])
    assert item["status"] == "created"
    assert item["name"] == shape["name"] + "." + shape["id"].replace("-", "")[:12]
    assert env.state["claims"]["previous-version-id"] == reservation


@pytest.mark.asyncio
@pytest.mark.parametrize("matching_claim", [False, True])
async def test_gpu_legacy_name_cannot_override_unowned_id_or_shape_drift(environment, matching_claim):
    env = environment
    env.policy["gpu_profiles"] = [profile()]
    shape = next(shape for shape in svc.standard_shapes(env.inventory["hosts"], [profile()]) if shape["gpu_count"])
    fid = shape["id"]
    env.compute.create_flavor(
        id=fid,
        name=f"gpu.3060lhr.{shape['gpu_count']}gpu.{shape['vcpus']}c.{shape['ram'] // 1024}g." + fid.replace("-", ""),
        vcpus=shape["vcpus"] + (1 if matching_claim else 0),
        ram=shape["ram"],
        disk=0,
        is_public=False,
        description=f"afterglow:{svc.OWNER}:owned" if matching_claim else "manual",
    )
    env.state["claims"][fid] = "owned"
    env.compute.specs[fid] = copy.deepcopy(shape["extra_specs"])
    env.compute.access[fid] = {"existing-project"}
    env.compute.events.clear()
    result = await svc.reconcile(object())
    item = next(item for item in result["items"] if item["id"] == fid)
    assert item["status"] == "conflict"
    assert env.compute.access[fid] == {"existing-project"}
    assert not any(event[0] in {"spec_write", "grant", "revoke"} and event[1] == fid for event in env.compute.events)


def test_exact_native_gpu_and_audio_aliases_scale_without_slug_substitution():
    approved = profile("render-group")
    approved["extra_specs"]["pci_passthrough:alias"] = "RTX-3090:1,RTX-3090-audio:1"
    approved["alias_resource_classes"] = {"RTX-3090": GPU, "RTX-3090-audio": AUDIO}
    shapes = svc.standard_shapes([host(gpu=8, audio=8)], [approved])
    for shape in shapes:
        count = shape["gpu_count"]
        if count:
            assert shape["name"] == f"gpu.render-groupx{count}_{shape['vcpus']}c_{shape['ram'] // 1024}g"
            assert shape["extra_specs"]["pci_passthrough:alias"] == f"RTX-3090:{count},RTX-3090-audio:{count}"
            assert shape["resource_requirements"] == {GPU: count, AUDIO: count}


@pytest.mark.asyncio
async def test_lease_revoked_inside_dispatch_save_prevents_create_and_releases_unsent_claim(environment, monkeypatch):
    env = environment
    original_save = svc._save
    revoked = False

    async def save_then_revoke(value, **kwargs):
        nonlocal revoked
        await original_save(value, **kwargs)
        if not revoked and any(
            isinstance(claim, dict) and claim.get("dispatched") for claim in value["claims"].values()
        ):
            revoked = True
            env.lease.assert_owned.side_effect = HTTPException(409, "lease revoked during SQL commit")

    monkeypatch.setattr(svc, "_save", save_then_revoke)
    with pytest.raises(HTTPException):
        await svc.reconcile(object())
    assert revoked and not env.compute.rows and not env.compute.events
    assert len(env.state["claims"]) == 1
    assert next(iter(env.state["claims"].values()))["dispatched"] is False
    env.lease.assert_owned.side_effect = None
    result = await svc.reconcile(object())
    assert result["status"] == "complete"
    assert sum(event[0] == "create" for event in env.compute.events) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("same_claim", [True, False])
@pytest.mark.parametrize("named", [False, True])
async def test_unsent_claim_reset_preserves_concurrent_revision_and_other_claims(monkeypatch, same_claim, named):
    token = "our-token" if same_claim else "other-token"
    current = {
        **svc._default(),
        "enabled": False,
        "revision": 9,
        "status": "disabled",
        "claims": {"ours": {"token": token, "dispatched": True}, "other": "preserved"},
    }
    if named:
        current["claims"]["ours"]["name"] = "gpu.render-groupx1_1c_2g"
    row = SimpleNamespace(value_json=copy.deepcopy(current))

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def begin(self):
            return self

        async def get(self, *args, **kwargs):
            assert kwargs["with_for_update"] is True
            return row

    monkeypatch.setattr(svc, "_factory", lambda: Session)
    await svc._reset_unsent_claim("ours", "our-token")
    expected = copy.deepcopy(current)
    if same_claim:
        expected["claims"]["ours"]["dispatched"] = False
    assert row.value_json == expected


def test_pcpu_only_host_generates_dedicated_gpu_but_never_shared_cpu_shapes():
    physical = host(cpu=0)
    physical["pcpu"] = {"capacity": 8, "min": 1, "step": 1}
    approved = profile()
    approved["extra_specs"]["hw:cpu_policy"] = "dedicated"
    shapes = svc.standard_shapes([physical], [approved])
    assert shapes and all(shape["gpu_count"] > 0 for shape in shapes)
    assert all(shape["extra_specs"]["hw:cpu_policy"] == "dedicated" for shape in shapes)
    assert max(shape["vcpus"] for shape in shapes) == 8
    approved["extra_specs"]["hw:cpu_policy"] = "shared"
    assert svc.standard_shapes([physical], [approved]) == []


def test_virtual_cpu_inventory_cannot_authorize_dedicated_gpu_shapes():
    approved = profile()
    approved["extra_specs"]["hw:cpu_policy"] = "dedicated"
    shapes = svc.standard_shapes([host(cpu=128)], [approved])
    assert shapes and all(shape["gpu_count"] == 0 for shape in shapes)


@pytest.mark.parametrize("spec", [{"hw:cpu_policy": "mixed"}, {"hw:emulator_threads_policy": "isolate"}])
def test_unrepresentable_cpu_templates_never_generate_managed_shapes(spec):
    approved = profile()
    approved["extra_specs"].update(spec)
    with pytest.raises(ValueError, match="CPU policy"):
        svc.standard_shapes([host()], [approved])


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["async-admission", "worker-entry"])
async def test_dispatcher_rejection_before_native_submit_releases_claim_for_retry(environment, monkeypatch, stage):
    from app.services.work_dispatcher import DispatcherUnavailable

    env = environment
    rejected = False
    checkpoints = 0

    async def checkpoint():
        nonlocal checkpoints, rejected
        checkpoints += 1
        if stage == "async-admission" and checkpoints == 3:
            rejected = True
            raise DispatcherUnavailable("dispatcher revoked after durable dispatch save")

    def checkpoint_sync():
        nonlocal rejected
        if stage == "worker-entry" and not rejected:
            rejected = True
            raise DispatcherUnavailable("dispatcher revoked while native create was queued")

    monkeypatch.setattr(svc, "checkpoint", checkpoint)
    monkeypatch.setattr(svc, "checkpoint_sync", checkpoint_sync)
    first = await svc.reconcile(object())
    assert rejected and first["status"] == "unavailable"
    assert not env.compute.rows and not env.compute.events
    claim = next(iter(env.state["claims"].values()))
    assert claim["dispatched"] is False
    second = await svc.reconcile(object())
    assert second["status"] == "complete"
    assert sum(event[0] == "create" for event in env.compute.events) == 1


def manual_cpu(env, *, fid="manual-cpu", name="m1.medium", public=False, specs=None):
    row = env.compute.create_flavor(
        id=fid,
        name=name,
        vcpus=3,
        ram=1536,
        disk=40,
        ephemeral=8,
        swap=512,
        is_public=False,
        description="Operator description: retain verbatim",
    )
    row.is_public = public
    env.compute.specs[fid] = copy.deepcopy(
        specs if specs is not None else {"hw:cpu_policy": "dedicated", "hw:mem_page_size": "large"}
    )
    env.compute.access[fid] = {"outside-project"} if not public else set()
    env.compute.events.clear()
    return row


def manual_item(result, fid="manual-cpu"):
    return next(item for item in result["items"] if item["id"] == fid)


@pytest.mark.asyncio
async def test_manual_private_cpu_automatically_adopts_exact_id_preserves_hardware_specs_and_unknown_acl(environment):
    env = environment
    row = manual_cpu(env)
    before = copy.deepcopy(vars(row))
    specs = copy.deepcopy(env.compute.specs[row.id])
    result = await svc.reconcile(object())
    item = manual_item(result)
    assert item["status"] == "unchanged" and item["control_state"] == "controlled"
    assert item["display_name"] == "cpu.3c_1.5g" and item["name"] == "m1.medium"
    assert vars(row) == before
    assert env.compute.specs[row.id] == {**specs, svc.CPU_TOKEN: svc._cpu_marker(env.state["cpu_claims"][row.id])}
    assert env.compute.specs[row.id][svc.CPU_TOKEN] != env.state["cpu_claims"][row.id]["token"]
    assert env.compute.access[row.id] == {"outside-project", "p1"}
    claim = copy.deepcopy(env.state["cpu_claims"][row.id])
    assert claim["original_access"] == ["outside-project"] and claim["extra_specs"] == specs
    env.compute.events.clear()
    again = await svc.reconcile(object())
    assert manual_item(again)["status"] == "unchanged" and env.state["cpu_claims"][row.id] == claim
    assert not any(event[0] in {"spec_write", "grant", "revoke", "create"} for event in env.compute.events)
    assert "cpu_claims" not in result and "claims" not in result


@pytest.mark.asyncio
async def test_future_manual_cpu_flavors_are_included_on_next_reconciliation(environment):
    env = environment
    await svc.reconcile(object())
    row = manual_cpu(env, fid="future-cpu")
    result = await svc.reconcile(object())
    assert manual_item(result, row.id)["control_state"] == "controlled"
    assert row.id in env.state["cpu_claims"]


@pytest.mark.asyncio
async def test_public_manual_cpu_remains_public_and_reports_native_bypass(environment):
    env = environment
    row = manual_cpu(env, public=True)
    result = await svc.reconcile(object())
    item = manual_item(result)
    assert item["status"] == "retained" and item["control_state"] == "public_external_bypass"
    assert item["enforcement"] == "afterglow_only" and "bypass" in item["reason"]
    assert row.is_public is True and not env.compute.access[row.id]
    assert not any(event[0] in {"grant", "revoke"} and event[1] == row.id for event in env.compute.events)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "specs",
    [
        {"pci_passthrough:alias": "display:1"},
        {"resources:CUSTOM_PCI_10DE_2208": "1"},
        {"capabilities:opaque_scheduler": "true"},
        {"resources:VCPU": "8"},
        {"resources:MEMORY_MB": "4096"},
        {"resources:VCPU": "3", "resources:PCPU": "3"},
    ],
)
async def test_accelerator_unknown_and_non_nominal_resource_cpu_are_never_adopted(environment, specs):
    env = environment
    row = manual_cpu(env, specs=specs)
    result = await svc.reconcile(object())
    if svc._accelerator_specs(specs):
        assert not any(item["id"] == row.id for item in result["items"])
    else:
        assert manual_item(result)["status"] == "retained" and manual_item(result)["gpu_count"] is None
    assert row.id not in env.state["cpu_claims"] and env.compute.specs[row.id] == specs
    assert env.compute.access[row.id] == {"outside-project"}
    assert not any(event[0] in {"spec_write", "grant", "revoke"} and event[1] == row.id for event in env.compute.events)


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["name", "shape", "specs", "acl", "token", "privacy", "description"])
async def test_adopted_cpu_drift_never_repairs_native_state_or_grants_new_projects(environment, drift):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    claim = copy.deepcopy(env.state["cpu_claims"][row.id])
    if drift == "name":
        row.name = "operator-renamed"
    elif drift == "shape":
        row.ram += 1024
    elif drift == "specs":
        env.compute.specs[row.id]["hw:mem_page_size"] = "small"
    elif drift == "acl":
        env.compute.access[row.id].add("external-new-grant")
    elif drift == "token":
        env.compute.specs[row.id].pop(svc.CPU_TOKEN)
    elif drift == "privacy":
        row.is_public = True
    else:
        row.description = "external change"
    env.projects["new"] = copy.deepcopy(env.projects["p1"])
    env.compute.events.clear()
    result = await svc.reconcile(object())
    assert manual_item(result)["status"] == "conflict" and result["status"] == "unavailable"
    assert env.state["cpu_claims"][row.id] == claim
    assert not any(event[0] in {"spec_write", "grant", "revoke"} and event[1] == row.id for event in env.compute.events)


@pytest.mark.asyncio
async def test_cpu_claim_survives_missing_id_and_detects_reused_native_id(environment):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    claim = copy.deepcopy(env.state["cpu_claims"][row.id])
    del env.compute.rows[row.id]
    assert manual_item(await svc.reconcile(object()))["status"] == "conflict"
    assert env.state["cpu_claims"][row.id] == claim
    manual_cpu(env)
    result = await svc.reconcile(object())
    assert manual_item(result)["status"] == "conflict"
    assert svc.CPU_TOKEN not in env.compute.specs[row.id]


@pytest.mark.asyncio
async def test_managed_cpu_legacy_short_full_and_canonical_names_preserve_ids_and_claims(environment):
    env = environment
    first = await svc.reconcile(object())
    fid = first["items"][0]["id"]
    row = env.compute.rows[fid]
    claim = copy.deepcopy(env.state["claims"][fid])
    for name in (f"cpu.ag.1c.2g.{fid.replace('-', '')[:12]}", f"cpu.ag.1c.2g.{fid.replace('-', '')}", "cpu.1c_2g"):
        row.name = name
        result = await svc.reconcile(object())
        assert manual_item(result, fid)["name"] == name and manual_item(result, fid)["status"] == "unchanged"
        assert env.state["claims"][fid] == claim and fid not in env.state["cpu_claims"]


@pytest.mark.asyncio
@pytest.mark.parametrize("equivalent", [False, True])
async def test_cpu_canonical_name_collision_never_creates_duplicate_or_adopts_by_name(environment, equivalent):
    env = environment
    shape = svc.standard_shapes(env.inventory["hosts"], [])[0]
    row = manual_cpu(env, name=shape["name"])
    if equivalent:
        row.vcpus, row.ram, row.disk, row.ephemeral, row.swap = 1, 2048, 0, 0, 0
    result = await svc.reconcile(object())
    assert manual_item(result, shape["id"])["status"] == "conflict"
    assert manual_item(result)["control_state"] == "controlled"
    assert shape["id"] not in env.compute.rows and shape["id"] not in env.state["claims"]
    assert len({item["id"] for item in result["items"]}) == len(result["items"])
    assert env.state["cpu_claims"][row.id]["snapshot"]["disk"] == row.disk


@pytest.mark.asyncio
async def test_manual_cpu_controls_only_known_pool_projects_and_preserves_directory_unknown_grants(environment):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    env.projects["p1"]["active"] = False
    env.projects["p1"]["pool"] = False
    result = await svc.reconcile(object())
    assert manual_item(result)["status"] == "unchanged" and env.compute.access[row.id] == {"outside-project"}
    env.projects["p1"].update(active=True, pool=True)
    await svc.reconcile(object())
    del env.projects["p1"]
    await svc.reconcile(object())
    assert env.compute.access[row.id] == {"outside-project", "p1"}


@pytest.mark.asyncio
async def test_manual_cpu_incomplete_directory_never_revokes_or_claims(environment, monkeypatch):
    env = environment
    row = manual_cpu(env)
    monkeypatch.setattr(svc, "_pool_projects", AsyncMock(side_effect=ValueError("directory truncated")))
    result = await svc.reconcile(object())
    assert result["status"] == "unavailable" and row.id not in env.state["cpu_claims"]
    assert env.compute.events == [] and env.compute.access[row.id] == {"outside-project"}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["marker", "grant", "revoke"])
@pytest.mark.parametrize("committed", [False, True])
async def test_unknown_manual_cpu_native_outcomes_not_replayed_but_exact_commits_resolve(
    environment, monkeypatch, kind, committed
):
    env = environment
    row = manual_cpu(env)
    if kind != "marker":
        await svc.reconcile(object())
        if kind == "grant":
            env.projects["new"] = copy.deepcopy(env.projects["p1"])
        else:
            env.projects["p1"]["active"] = False
    method = {
        "marker": "create_flavor_extra_specs",
        "grant": "flavor_add_tenant_access",
        "revoke": "flavor_remove_tenant_access",
    }[kind]
    native = getattr(env.compute, method)
    calls = []

    def uncertain(fid, *args):
        if fid != row.id:
            return native(fid, *args)
        calls.append(args)
        if committed:
            native(fid, *args)
        raise TimeoutError("native mutation response lost")

    monkeypatch.setattr(env.compute, method, uncertain)
    first = await svc.reconcile(object())
    assert manual_item(first)["status"] == "conflict" and len(calls) == 1
    assert env.state["cpu_claims"][row.id]["pending"]["dispatched"] is True
    second = await svc.reconcile(object())
    assert len(calls) == 1
    assert manual_item(second)["status"] == ("unchanged" if committed else "conflict")
    if committed:
        assert env.state["cpu_claims"][row.id]["pending"] is None


@pytest.mark.asyncio
async def test_controlled_cpu_independent_usage_annotation_does_not_trigger_spec_drift(environment):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    env.compute.specs[row.id]["afterglow:usage_schedule_required"] = "true"
    env.projects["new"] = copy.deepcopy(env.projects["p1"])
    result = await svc.reconcile(object())
    assert manual_item(result)["control_state"] == "controlled"
    assert env.compute.specs[row.id]["afterglow:usage_schedule_required"] == "true"
    assert "new" in env.compute.access[row.id]


@pytest.mark.asyncio
async def test_cpu_storage_claims_are_redacted_and_malformed_protocol_fails_closed(environment):
    env = environment
    manual_cpu(env)
    await svc.reconcile(object())
    state = svc._state(copy.deepcopy(env.state))
    assert "cpu_claims" not in svc._public(state, {"policy_ready": True})
    for corrupt in (None, [], {"manual-cpu": {}}, {"manual-cpu": "legacy-not-supported"}):
        with pytest.raises(HTTPException) as error:
            svc._state({**state, "cpu_claims": corrupt})
        assert error.value.status_code == 503
    legacy = svc._default()
    del legacy["cpu_claims"]
    assert svc._state(legacy)["cpu_claims"] == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing", ["os-flavor-access:is_public", "OS-FLV-EXT-DATA:ephemeral", "swap", "description", "rxtx_factor"]
)
async def test_native_sdk_defaults_never_prove_manual_immutable_fields(environment, monkeypatch, missing):
    env = environment
    row = manual_cpu(env)
    native = env.compute.get

    def incomplete(path, **kwargs):
        response = native(path, **kwargs)
        body = copy.deepcopy(response.json())
        if path == f"/flavors/{row.id}":
            del body["flavor"][missing]
        return SimpleNamespace(status_code=200, json=lambda: body)

    monkeypatch.setattr(env.compute, "get", incomplete)
    result = await svc.reconcile(object())
    assert manual_item(result)["status"] == "conflict" and row.id not in env.state["cpu_claims"]
    assert env.compute.access[row.id] == {"outside-project"}


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["flavors", "acl"])
async def test_partial_native_catalog_or_acl_never_triggers_manual_adoption_or_revocation(
    environment, monkeypatch, source
):
    env = environment
    row = manual_cpu(env)
    native = env.compute.get

    def partial(path, **kwargs):
        response = native(path, **kwargs)
        body = copy.deepcopy(response.json())
        if (
            source == "flavors"
            and path.startswith("/flavors/detail")
            or source == "acl"
            and path.endswith("/os-flavor-access")
        ):
            body["links"] = {"next": "https://native.invalid/next"}
        return SimpleNamespace(status_code=200, json=lambda: body)

    monkeypatch.setattr(env.compute, "get", partial)
    result = await svc.reconcile(object())
    assert result["status"] == "unavailable" and row.id not in env.state["cpu_claims"]
    assert not any(event[0] in {"spec_write", "grant", "revoke"} and event[1] == row.id for event in env.compute.events)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["graph", "managed_revision", "policy_revision", "directory"])
async def test_manual_final_dispatch_fences_stop_native_mutations(environment, monkeypatch, changed):
    env = environment
    row = manual_cpu(env)
    original_save = svc._save

    async def revoke_after_dispatch_journal(value, **kwargs):
        await original_save(value, **kwargs)
        claim = value["cpu_claims"].get(row.id)
        if not claim or not claim.get("pending") or not claim["pending"]["dispatched"]:
            return
        if changed == "graph":
            env.lease.assert_owned.side_effect = HTTPException(409, "graph lease revoked")
        elif changed == "managed_revision":
            env.state["revision"] += 1
        elif changed == "policy_revision":
            env.policy["revision"] += 1
        else:
            env.projects["p1"]["domain_id"] = "different-domain"

    monkeypatch.setattr(svc, "_save", revoke_after_dispatch_journal)
    with pytest.raises(HTTPException) as error:
        await svc.reconcile(object())
    assert error.value.status_code == 409
    assert svc.CPU_TOKEN not in env.compute.specs[row.id] and env.compute.access[row.id] == {"outside-project"}
    assert not any(event[0] in {"spec_write", "grant", "revoke"} and event[1] == row.id for event in env.compute.events)
    assert env.state["cpu_claims"][row.id]["pending"]["dispatched"] is False
    monkeypatch.setattr(svc, "_save", original_save)
    env.lease.assert_owned.side_effect = None
    recovered = await svc.reconcile(object())
    assert manual_item(recovered)["control_state"] == "controlled"
    assert env.state["cpu_claims"][row.id]["pending"] is None


@pytest.mark.asyncio
async def test_manual_project_id_in_another_domain_is_not_reconciled_under_old_ownership(environment):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    env.projects["p1"].update(domain_id="foreign-domain", active=False, pool=False)
    env.compute.events.clear()
    result = await svc.reconcile(object())
    assert manual_item(result)["status"] == "unchanged"
    assert env.compute.access[row.id] == {"outside-project", "p1"}
    assert not any(event[0] == "revoke" and event[1] == row.id for event in env.compute.events)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["1", " YES ", "on", "0", " OFF ", "false", ""])
async def test_manual_hidden_visibility_and_usage_annotation_values_preserved(environment, value):
    env = environment
    row = manual_cpu(env, specs={"afterglow:frontend_visible": value, "afterglow:usage_schedule_required": value})
    result = await svc.reconcile(object())
    assert manual_item(result)["control_state"] == "controlled"
    assert env.compute.specs[row.id]["afterglow:frontend_visible"] == value
    assert env.compute.specs[row.id]["afterglow:usage_schedule_required"] == value


@pytest.mark.asyncio
async def test_cpu_claim_journal_persists_full_snapshot_without_returning_ownership_secret(environment, monkeypatch):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    saved = SimpleNamespace(value_json=None)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def begin(self):
            return self

        async def get(self, *args, **kwargs):
            assert kwargs["with_for_update"] is True
            return saved

    # Exercise the real transaction/deep-copy implementation without a database.
    monkeypatch.setattr(svc, "_factory", lambda: Session)
    saved.value_json = copy.deepcopy(env.state)
    before = copy.deepcopy(env.state["cpu_claims"][row.id])
    source = copy.deepcopy(env.state)
    await _persist_state(source)
    source["cpu_claims"][row.id]["access"].append("must-not-alias-persisted-state")
    assert svc._state(saved.value_json)["cpu_claims"][row.id] == before
    assert "cpu_claims" not in svc._public(svc._state(saved.value_json), {"policy_ready": True})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "specs",
    [
        {"hw:cpu_policy": "dedicated", "resources:VCPU": "3"},
        {"hw:cpu_policy": "shared", "resources:PCPU": "3"},
        {"resources:PCPU": "3"},
        {"resources:VCPU": "3", "resources:PCPU": "3"},
        {"resources:DISK_GB": "80"},
        {"resources:DISK_GB": "40"},
    ],
)
async def test_explicit_base_resource_demand_is_not_inferred_from_nominal_shape(environment, specs):
    env = environment
    row = manual_cpu(env, specs=specs)
    result = await svc.reconcile(object())
    assert manual_item(result)["status"] == "retained"
    assert row.id not in env.state["cpu_claims"] and env.compute.specs[row.id] == specs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "specs",
    [
        {"pci_passthrough:alias": "graphics:1,audio:1"},
        {"resources:VGPU": "1"},
        {"resources:CUSTOM_PCI_10DE_2208": "1"},
        {"resources:CUSTOM_OPERATOR_ACCELERATOR": "1"},
    ],
)
async def test_existing_gpu_coexists_without_acl_lookup_or_cpu_reconciliation_failure(environment, monkeypatch, specs):
    env = environment
    gpu = manual_cpu(env, fid="manual-gpu", name="operator-rendering", specs=specs)
    manual_cpu(env)
    native = env.compute.get

    def broken_gpu_detail(path, **kwargs):
        if path in {f"/flavors/{gpu.id}", f"/flavors/{gpu.id}/os-flavor-access"}:
            pytest.fail("out-of-scope GPU hardware/ACL must not be read by CPU adoption")
        return native(path, **kwargs)

    monkeypatch.setattr(env.compute, "get", broken_gpu_detail)
    result = await svc.reconcile(object())
    assert result["status"] == "complete"
    if svc._accelerator_specs(specs):
        assert not any(item["id"] == gpu.id for item in result["items"])
    else:
        assert manual_item(result, gpu.id)["status"] == "retained"
        assert manual_item(result, gpu.id)["gpu_count"] is None
    assert manual_item(result)["control_state"] == "controlled" and gpu.id not in env.state["cpu_claims"]


@pytest.mark.asyncio
async def test_previously_adopted_cpu_accelerator_drift_is_conflict_not_excluded(environment):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    claim = copy.deepcopy(env.state["cpu_claims"][row.id])
    env.compute.specs[row.id]["pci_passthrough:alias"] = "gpu:1"
    result = await svc.reconcile(object())
    assert manual_item(result)["status"] == "conflict" and result["status"] == "unavailable"
    assert env.state["cpu_claims"][row.id] == claim


def test_native_flavor_marker_pages_are_consumed_without_following_next_urls():
    calls = []

    class Pages:
        def get_endpoint(self):
            return "https://nova.invalid/v2.1"

        def get(self, path, **kwargs):
            calls.append(path)
            if len(calls) == 1:
                body = {
                    "flavors": [{"id": f"id-{index}"} for index in range(1001)],
                    "flavors_links": [
                        {
                            "rel": "next",
                            "href": "https://nova.invalid/v2.1/flavors/detail?marker=id-1000&is_public=None",
                        }
                    ],
                }
            else:
                assert path == "/flavors/detail?is_public=None&marker=id-1000"
                body = {"flavors": [{"id": "last"}], "flavors_links": []}
            return SimpleNamespace(status_code=200, json=lambda: body)

    assert len(svc._native_flavors(Pages())) == 1002
    assert len(calls) == 2 and all(path.startswith("/flavors/detail?") for path in calls)


@pytest.mark.parametrize(
    "href",
    [
        "https://evil.invalid/v2.1/flavors/detail?marker=first",
        "https://nova.invalid/v2.1/flavors/detail?marker=other",
        "https://nova.invalid/v2.1/servers?marker=first",
        "https://nova.invalid/v2.1/flavors/detail?marker=first&is_public=true",
        "https://user:secret@nova.invalid/v2.1/flavors/detail?marker=first",
    ],
)
def test_native_flavor_paging_rejects_untrusted_destinations_and_wrong_markers(href):
    class Pages:
        def get_endpoint(self):
            return "https://nova.invalid/v2.1"

        def get(self, path, **kwargs):
            body = {"flavors": [{"id": "first"}], "flavors_links": [{"rel": "next", "href": href}]}
            return SimpleNamespace(status_code=200, json=lambda: body)

    with pytest.raises(ValueError):
        svc._native_flavors(Pages())


def test_native_flavor_paging_repeated_rows_fail_closed():
    class Pages:
        def get_endpoint(self):
            return "https://nova.invalid/v2.1"

        def get(self, path, **kwargs):
            body = {
                "flavors": [{"id": "first"}],
                "flavors_links": [{"rel": "next", "href": "/flavors/detail?marker=first"}],
            }
            return SimpleNamespace(status_code=200, json=lambda: body)

    with pytest.raises(ValueError, match="repeated"):
        svc._native_flavors(Pages())


@pytest.mark.asyncio
async def test_orphaned_native_cpu_token_is_not_reclaimed_by_new_durable_owner(environment):
    env = environment
    row = manual_cpu(env, specs={svc.CPU_TOKEN: "another-owner"})
    result = await svc.reconcile(object())
    assert manual_item(result)["status"] == "conflict"
    assert row.id not in env.state["cpu_claims"]
    assert env.compute.specs[row.id] == {svc.CPU_TOKEN: "another-owner"}


@pytest.mark.asyncio
async def test_orphaned_legacy_marker_is_one_conflict_without_mutating_native_flavor(environment):
    env = environment
    row = manual_cpu(env, specs={svc.MARKER: svc.OWNER, "afterglow:access_mode": "domain_quota"})
    original_specs = copy.deepcopy(env.compute.specs[row.id])
    original_access = set(env.compute.access[row.id])
    env.compute.events.clear()
    result = await svc.reconcile(object())
    matches = [item for item in result["items"] if item["id"] == row.id]
    assert result["status"] == "unavailable"
    assert len(matches) == 1 and matches[0]["status"] == "conflict"
    assert env.compute.specs[row.id] == original_specs
    assert env.compute.access[row.id] == original_access
    assert not any(event[0] in {"spec_write", "grant", "revoke"} and event[1] == row.id for event in env.compute.events)


@pytest.mark.asyncio
async def test_cpu_snapshot_storage_types_and_pending_intent_are_validated(environment):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    for field, value in (
        ("ram", True),
        ("disk", -1),
        ("swap", False),
        ("os-flavor-access:is_public", None),
        ("rxtx_factor", float("inf")),
    ):
        state = copy.deepcopy(env.state)
        state["cpu_claims"][row.id]["snapshot"][field] = value
        with pytest.raises(HTTPException) as error:
            svc._state(state)
        assert error.value.status_code == 503
    for pending in (
        {"kind": "delete", "dispatched": True},
        {"kind": "grant", "dispatched": "true", "project_id": "p1"},
        {"kind": "revoke", "dispatched": True},
    ):
        state = copy.deepcopy(env.state)
        state["cpu_claims"][row.id]["pending"] = pending
        with pytest.raises(HTTPException):
            svc._state(state)


@pytest.mark.asyncio
async def test_manual_marker_pre_submit_native_drift_prevents_dispatch(environment, monkeypatch):
    env = environment
    row = manual_cpu(env)
    native_save = svc._save

    async def race_after_journal(value, **kwargs):
        await native_save(value, **kwargs)
        claim = value["cpu_claims"].get(row.id)
        if claim and claim.get("pending") and claim["pending"]["dispatched"]:
            row.description = "Concurrent operator edit before worker entry"

    monkeypatch.setattr(svc, "_save", race_after_journal)
    result = await svc.reconcile(object())
    assert manual_item(result)["status"] == "conflict"
    assert svc.CPU_TOKEN not in env.compute.specs[row.id]
    assert env.state["cpu_claims"][row.id]["pending"]["dispatched"] is False


@pytest.mark.asyncio
async def test_manual_cpu_provider_read_cannot_dispatch_after_graph_lease_expires(environment, monkeypatch):
    env = environment
    row = manual_cpu(env)
    read_native = svc._manual_native
    expired = False

    def expire_after_native_read(compute, fid):
        nonlocal expired
        observed = read_native(compute, fid)
        claim = env.state["cpu_claims"].get(fid)
        if claim and claim.get("pending") and claim["pending"]["dispatched"] and not expired:
            expired = True
            env.lease.assert_owned.side_effect = HTTPException(409, "graph lease expired during native read")
        return observed

    monkeypatch.setattr(svc, "_manual_native", expire_after_native_read)
    with pytest.raises(HTTPException) as error:
        await svc.reconcile(object())
    assert expired and error.value.status_code == 409
    assert svc.CPU_TOKEN not in env.compute.specs[row.id]
    assert env.state["cpu_claims"][row.id]["pending"]["dispatched"] is False
    assert not any(event[0] in {"spec_write", "grant", "revoke"} and event[1] == row.id for event in env.compute.events)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["removed", "moved", "disabled", "ineligible"])
async def test_manual_cpu_does_not_grant_if_project_changes_during_native_read(environment, monkeypatch, change):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    env.projects["candidate"] = copy.deepcopy(env.projects["p1"])
    original_read = svc._manual_native
    changed = False

    def change_directory_after_native_read(compute, fid):
        nonlocal changed
        observed = original_read(compute, fid)
        claim = env.state["cpu_claims"].get(fid)
        pending = claim.get("pending") if claim else None
        if pending and pending.get("kind") == "grant" and pending.get("dispatched") and not changed:
            changed = True
            if change == "removed":
                del env.projects["candidate"]
            elif change == "moved":
                env.projects["candidate"]["domain_id"] = "different-domain"
            elif change == "disabled":
                env.projects["candidate"]["active"] = False
            else:
                env.projects["candidate"]["limits"] = {"CPU": 0, "MEMORY_MB": 0}
        return observed

    monkeypatch.setattr(svc, "_manual_native", change_directory_after_native_read)
    with pytest.raises(HTTPException) as error:
        await svc.reconcile(object())
    assert changed and error.value.status_code == 409
    assert "candidate" not in env.compute.access[row.id]
    assert env.state["cpu_claims"][row.id]["pending"]["dispatched"] is False
    assert not any(event == ("grant", row.id, "candidate") for event in env.compute.events)


@pytest.mark.asyncio
async def test_manual_acl_postreadback_drift_does_not_retry_or_start_later_grants(environment, monkeypatch):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    env.projects["new-a"] = copy.deepcopy(env.projects["p1"])
    env.projects["new-b"] = copy.deepcopy(env.projects["p1"])
    native_grant = env.compute.flavor_add_tenant_access

    def drift_after_grant(fid, pid):
        native_grant(fid, pid)
        if fid == row.id:
            env.compute.access[fid].add("concurrent-external-grant")

    monkeypatch.setattr(env.compute, "flavor_add_tenant_access", drift_after_grant)
    result = await svc.reconcile(object())
    assert manual_item(result)["status"] == "conflict"
    assert "new-a" in env.compute.access[row.id] and "new-b" not in env.compute.access[row.id]
    again = await svc.reconcile(object())
    assert manual_item(again)["status"] == "conflict" and "new-b" not in env.compute.access[row.id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "specs",
    [
        {"resources:VCPU": "3"},
        {"hw:cpu_policy": "shared", "resources:VCPU": "3"},
        {"resources:MEMORY_MB": "1536"},
        {"resources:VCPU": "3", "resources:MEMORY_MB": "1536"},
        {"hw:cpu_policy": "dedicated", "resources:PCPU": "3"},
        {"hw:cpu_policy": "dedicated", "resources:PCPU": "3", "resources:MEMORY_MB": "1536"},
    ],
)
async def test_exact_cpu_policy_class_and_matching_native_resources_automatically_enroll(environment, specs):
    env = environment
    row = manual_cpu(env, specs=specs)
    result = await svc.reconcile(object())
    assert manual_item(result)["control_state"] == "controlled"
    assert env.compute.access[row.id] == {"outside-project", "p1"}
    assert env.state["cpu_claims"][row.id]["extra_specs"] == specs
    assert env.compute.specs[row.id] == {**specs, svc.CPU_TOKEN: svc._cpu_marker(env.state["cpu_claims"][row.id])}


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing", "moved", "disabled", "ineligible"])
async def test_prepared_unsent_grant_replans_current_project_authority_without_foreign_grant(environment, change):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    claim = env.state["cpu_claims"][row.id]
    claim["project_domains"]["prepared"] = "d1"
    claim["pending"] = {"kind": "grant", "project_id": "prepared", "dispatched": False}
    if change != "missing":
        env.projects["prepared"] = copy.deepcopy(env.projects["p1"])
        if change == "moved":
            env.projects["prepared"]["domain_id"] = "foreign-domain"
        elif change == "disabled":
            env.projects["prepared"]["active"] = False
        else:
            env.projects["prepared"]["limits"] = {"CPU": 0, "MEMORY_MB": 0}
    env.compute.events.clear()
    result = await svc.reconcile(object())
    assert manual_item(result)["control_state"] == "controlled"
    assert "prepared" not in env.compute.access[row.id]
    assert env.state["cpu_claims"][row.id]["pending"] is None
    assert not any(event == ("grant", row.id, "prepared") for event in env.compute.events)


@pytest.mark.asyncio
async def test_prepared_unsent_revoke_is_cancelled_after_eligibility_policy_reversal(environment):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    env.state["cpu_claims"][row.id]["pending"] = {"kind": "revoke", "project_id": "p1", "dispatched": False}
    env.compute.events.clear()
    result = await svc.reconcile(object())
    assert manual_item(result)["control_state"] == "controlled"
    assert env.compute.access[row.id] == {"outside-project", "p1"}
    assert env.state["cpu_claims"][row.id]["pending"] is None
    assert ("revoke", row.id, "p1") not in env.compute.events


@pytest.mark.asyncio
async def test_submitted_unknown_grant_is_not_cancelled_or_replayed_after_project_moves(environment):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    claim = env.state["cpu_claims"][row.id]
    claim["project_domains"]["prepared"] = "d1"
    claim["pending"] = {"kind": "grant", "project_id": "prepared", "dispatched": True, "operation_id": "a" * 32}
    env.projects["prepared"] = {**copy.deepcopy(env.projects["p1"]), "domain_id": "foreign-domain"}
    before = copy.deepcopy(claim)
    env.compute.events.clear()
    result = await svc.reconcile(object())
    assert manual_item(result)["status"] == "conflict"
    assert env.state["cpu_claims"][row.id] == before
    assert "prepared" not in env.compute.access[row.id]
    assert not any(event[0] in {"grant", "revoke"} and event[1] == row.id for event in env.compute.events)


@pytest.mark.asyncio
async def test_cpu_worker_entry_rejection_resets_exact_unsent_claim_and_next_reconcile_recovers(
    environment, monkeypatch
):
    from app.services.work_dispatcher import DispatcherUnavailable

    env = environment
    row = manual_cpu(env)
    rejected = False

    def reject_once():
        nonlocal rejected
        if not rejected:
            rejected = True
            raise DispatcherUnavailable("worker admission rejected")

    monkeypatch.setattr(svc, "checkpoint_sync", reject_once)
    first = await svc.reconcile(object())
    assert manual_item(first)["status"] == "conflict" and rejected
    assert env.state["cpu_claims"][row.id]["pending"]["dispatched"] is False
    assert svc.CPU_TOKEN not in env.compute.specs[row.id]
    second = await svc.reconcile(object())
    assert manual_item(second)["control_state"] == "controlled"
    assert env.state["cpu_claims"][row.id]["pending"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("newer_claim", [False, True])
async def test_exact_unsent_cpu_reset_preserves_newer_configuration_and_ownership(
    environment, monkeypatch, newer_claim
):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    expected = copy.deepcopy(env.state["cpu_claims"][row.id])
    expected["pending"] = {"kind": "grant", "project_id": "prepared", "dispatched": True, "operation_id": "a" * 32}
    current = {**copy.deepcopy(env.state), "enabled": False, "revision": 99, "status": "disabled"}
    current["cpu_claims"][row.id] = copy.deepcopy(expected)
    if newer_claim:
        # Same kind/project/token but a later dispatch attempt: ABA must not reset.
        current["cpu_claims"][row.id]["pending"]["operation_id"] = "b" * 32
    saved = SimpleNamespace(value_json=copy.deepcopy(current))

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def begin(self):
            return self

        async def get(self, *args, **kwargs):
            assert kwargs["with_for_update"] is True
            return saved

    monkeypatch.setattr(svc, "_factory", lambda: Session)
    reset = await _persist_cpu_reset(row.id, expected)
    assert reset is (not newer_claim)
    if not newer_claim:
        current["cpu_claims"][row.id]["pending"]["dispatched"] = False
    assert saved.value_json == current


def test_native_cpu_marker_is_only_a_nonsecret_digest_of_private_claim_token():
    claim = {"token": "a" * 48}
    marker = svc._cpu_marker(claim)
    assert marker != claim["token"] and len(marker) == 64
    assert marker == svc._cpu_marker(copy.deepcopy(claim))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        {"truncated": True},
        {"limited": True},
        {"links": {"next": "https://nova.invalid/v2.1/flavors/manual-cpu/os-extra_specs?marker=next"}},
        {"extra_specs_links": [{"rel": "next", "href": "https://nova.invalid/next"}]},
        {"links": [{"rel": "next", "href": "https://nova.invalid/next"}]},
    ],
)
async def test_partial_extra_specs_omitting_gpu_alias_never_authorizes_cpu_adoption(environment, monkeypatch, metadata):
    env = environment
    row = manual_cpu(env, specs={"hw:cpu_policy": "shared", "pci_passthrough:alias": "gpu:1,audio:1"})
    original_specs = copy.deepcopy(env.compute.specs[row.id])
    native_get = env.compute.get

    def partial_specs(path, **kwargs):
        if path == f"/flavors/{row.id}/os-extra_specs":
            # Provider omits the accelerator-bearing part of the same flavor.
            payload = {"extra_specs": {"hw:cpu_policy": "shared"}, **metadata}
            return SimpleNamespace(status_code=200, json=lambda: payload)
        return native_get(path, **kwargs)

    monkeypatch.setattr(env.compute, "get", partial_specs)
    with pytest.raises(HTTPException) as error:
        await svc.reconcile(object())
    assert error.value.status_code == 503
    assert row.id not in env.state["cpu_claims"]
    assert svc.CPU_TOKEN not in env.compute.specs[row.id] and env.compute.specs[row.id] == original_specs
    assert env.compute.access[row.id] == {"outside-project"}
    assert not any(event[0] in {"spec_write", "grant", "revoke"} and event[1] == row.id for event in env.compute.events)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation_id", [None, "", "not-hex", "a" * 31, "a" * 33, "g" * 32])
async def test_dispatched_cpu_intent_requires_valid_durable_operation_nonce(environment, operation_id):
    env = environment
    row = manual_cpu(env)
    await svc.reconcile(object())
    state = copy.deepcopy(env.state)
    pending = {"kind": "grant", "project_id": "next", "dispatched": True}
    if operation_id is not None:
        pending["operation_id"] = operation_id
    state["cpu_claims"][row.id]["pending"] = pending
    with pytest.raises(HTTPException) as error:
        svc._state(state)
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_cpu_dispatch_attempts_use_distinct_durable_nonces(environment, monkeypatch):
    env = environment
    row = manual_cpu(env)
    native_save = svc._save
    attempts = []

    async def capture_dispatched(value, **kwargs):
        await native_save(value, **kwargs)
        claim = value["cpu_claims"].get(row.id)
        pending = claim.get("pending") if claim else None
        if pending and pending["dispatched"]:
            attempts.append((pending["kind"], pending["operation_id"]))

    monkeypatch.setattr(svc, "_save", capture_dispatched)
    result = await svc.reconcile(object())
    assert manual_item(result)["control_state"] == "controlled"
    assert {kind for kind, _ in attempts} == {"marker", "grant"}
    assert len({operation for _, operation in attempts}) == len(attempts) == 2
    assert all(len(operation) == 32 for _, operation in attempts)


@pytest.mark.asyncio
async def test_unsent_cpu_reset_mismatch_does_not_overwrite_newer_writer_on_final_save(environment, monkeypatch):
    from app.services.work_dispatcher import DispatcherUnavailable

    env = environment
    row = manual_cpu(env)
    concurrent = None

    def reject_worker():
        raise DispatcherUnavailable("worker rejected before native submit")

    async def mismatched_reset(fid, expected_claim):
        nonlocal concurrent
        newer = copy.deepcopy(expected_claim)
        newer["pending"]["operation_id"] = "f" * 32
        env.state["cpu_claims"][fid] = newer
        env.state["revision"] += 1
        env.state["status"] = "newer-writer"
        concurrent = copy.deepcopy(env.state)
        return False

    monkeypatch.setattr(svc, "checkpoint_sync", reject_worker)
    monkeypatch.setattr(svc, "_reset_unsent_cpu_claim", mismatched_reset)
    with pytest.raises(HTTPException) as error:
        await svc.reconcile(object())
    assert error.value.status_code == 409
    assert concurrent is not None and env.state == concurrent
    assert svc.CPU_TOKEN not in env.compute.specs[row.id]
    assert not any(event[0] in {"spec_write", "grant", "revoke"} and event[1] == row.id for event in env.compute.events)


@pytest.mark.asyncio
async def test_foreground_waiter_defers_before_locked_discovery_with_final_save_and_invalidation(
    environment, monkeypatch
):
    from app.services.cache import invalidate

    env = environment
    env.lease.waiters_pending.return_value = True
    discovery = AsyncMock(side_effect=AssertionError("queued IAM precedes discovery"))
    monkeypatch.setattr(policy_svc, "discover_locked", discovery)
    result = await svc.reconcile(object())
    assert result["status"] == env.state["status"] == "idle"
    assert result["error"] is None and result["items"] == []
    assert [item["code"] for item in result["diagnostics"]] == ["foreground_iam_waiting"]
    discovery.assert_not_awaited()
    env.lease.assert_owned.assert_awaited()
    invalidate.assert_awaited_once_with("afterglow:nova:*:flavors")
    assert env.compute.events == [] and not env.state["claims"]


@pytest.mark.asyncio
async def test_foreground_waiter_settles_generated_flavor_then_next_pass_rereads_authority(environment):
    env = environment
    env.inventory["hosts"] = [host(cpu=1, ram=4096)]
    env.lease.waiters_pending.side_effect = lambda: any(event[0] == "create" for event in env.compute.events)
    first = await svc.reconcile(object())
    assert first["status"] == "idle" and len(first["items"]) == 1
    fid = first["items"][0]["id"]
    assert first["items"][0]["status"] == "created"
    assert env.compute.access[fid] == {"p1"}
    assert env.compute.specs[fid]["afterglow:frontend_visible"] == "true"
    assert env.state["claims"][fid]["dispatched"] is True
    assert len(env.compute.rows) == 1
    env.projects["p1"]["limits"]["CPU"] = 0
    env.lease.waiters_pending.side_effect = None
    second = await svc.reconcile(object())
    assert second["status"] == "complete" and len(second["items"]) == 2
    assert all(not access for access in env.compute.access.values())
    assert sum(event[0] == "create" for event in env.compute.events) == 2


@pytest.mark.asyncio
async def test_foreground_waiter_never_interrupts_manual_claim_or_readback(environment):
    env = environment
    first = manual_cpu(env, fid="a-manual")
    later = manual_cpu(env, fid="z-manual", name="operator-later")
    env.lease.waiters_pending.side_effect = lambda: any(event[0] == "spec_write" for event in env.compute.events)
    result = await svc.reconcile(object())
    assert result["status"] == "idle"
    assert [item["id"] for item in result["items"]] == [first.id]
    assert manual_item(result, first.id)["control_state"] == "controlled"
    assert env.state["cpu_claims"][first.id]["pending"] is None
    assert env.compute.access[first.id] == {"outside-project", "p1"}
    assert later.id not in env.state["cpu_claims"] and svc.CPU_TOKEN not in env.compute.specs[later.id]
    assert not env.state["claims"]


@pytest.mark.asyncio
async def test_foreground_waiter_settles_one_retirement_before_releasing_graph(environment):
    env = environment
    env.inventory["hosts"] = [host(cpu=1, ram=4096)]
    initial = await svc.reconcile(object())
    ids = [item["id"] for item in initial["items"]]
    env.policy["hosts"][0]["removed"] = True
    env.compute.events.clear()
    env.lease.waiters_pending.side_effect = lambda: any(
        event[0] == "spec_write" and env.compute.specs[event[1]].get("afterglow:frontend_visible") == "false"
        for event in env.compute.events
    )
    result = await svc.reconcile(object())
    assert result["status"] == "idle" and len(result["items"]) == 1
    retired = result["items"][0]
    assert retired["status"] == "retired" and not env.compute.access[retired["id"]]
    assert env.compute.specs[retired["id"]]["afterglow:frontend_visible"] == "false"
    untouched = next(fid for fid in ids if fid != retired["id"])
    assert env.compute.access[untouched] == {"p1"}
    assert env.compute.specs[untouched]["afterglow:frontend_visible"] == "true"


@pytest.mark.asyncio
async def test_requested_shape_publication_never_yields_even_when_cooperative_flag_is_set(environment):
    env = environment
    env.lease.waiters_pending.return_value = True
    state = copy.deepcopy(env.state)
    shapes = svc.standard_shapes(env.policy["hosts"], [])
    items, diagnostics = await svc._reconcile(
        object(), env.lease, state, {}, requested_shapes=shapes, policy=env.policy, cooperative_yield=True
    )
    assert len(items) == 1 and items[0]["status"] == "created" and not diagnostics
    assert env.compute.access[items[0]["id"]] == {"p1"}
    env.lease.waiters_pending.assert_not_awaited()


@pytest.mark.asyncio
async def test_supported_observation_occurs_outside_graph_and_fresh_disable_prevents_writes(environment, monkeypatch):
    env = environment
    locked = False
    observed = False

    def observe(conn):
        nonlocal observed
        assert not locked
        observed = True
        return copy.deepcopy(env.inventory["hosts"]), True

    @asynccontextmanager
    async def lock(conn):
        nonlocal locked
        assert observed
        locked = True
        env.state["enabled"] = False
        try:
            yield env.lease
        finally:
            locked = False

    monkeypatch.setattr(svc, "supported_hosts", observe)
    monkeypatch.setattr(svc.identity_roles, "_graph_lock", lock)
    result = await svc.reconcile(object())
    assert observed and result["enabled"] is False
    assert not env.compute.events and not env.state["claims"]


@pytest.mark.asyncio
async def test_staged_discovery_merges_latest_retirement_and_gpu_approval_without_observing_again(
    environment, monkeypatch
):
    env = environment
    staged = copy.deepcopy(env.inventory["hosts"]), True
    env.policy["hosts"][0]["removed"] = True
    env.policy["gpu_profiles"] = [profile()]
    env.policy["revision"] = 7
    monkeypatch.setattr(svc, "supported_hosts", lambda conn: pytest.fail("must reuse staged read-only evidence"))
    result = await policy_svc.discover_locked(object(), env.lease, staged_facts=staged)
    assert result["revision"] == 7 and result["hosts"][0]["removed"] is True
    assert result["gpu_profiles"] == [profile()]


@pytest.mark.asyncio
@pytest.mark.parametrize("retained", [False, True])
async def test_failed_staged_discovery_uses_latest_retained_policy_or_fails_closed(environment, retained):
    env = environment
    if not retained:
        env.policy["hosts"] = []
        with pytest.raises(HTTPException) as error:
            await policy_svc.discover_locked(object(), env.lease, staged_facts=(None, False))
        assert error.value.status_code == 503
        assert error.value.detail == "flavor_automation_inventory_unavailable"
    else:
        result = await policy_svc.discover_locked(object(), env.lease, staged_facts=(None, False))
        assert result["hosts"][0]["cpu"] == env.inventory["hosts"][0]["cpu"]
        assert result["hosts"][0]["state"] == "unknown"
        assert result["hosts"][0]["status"] == "observation_unavailable"


@pytest.mark.asyncio
async def test_waiter_detection_failure_is_not_successful_deferral(environment):
    env = environment
    env.lease.waiters_pending.side_effect = HTTPException(503, "identity_role_graph_lock_unavailable")
    with pytest.raises(HTTPException) as error:
        await svc.reconcile(object())
    assert error.value.status_code == 503
    assert not env.compute.events and not env.state["claims"]


@pytest.mark.asyncio
async def test_real_graph_waiter_acquires_only_after_generated_unit_is_settled(environment, monkeypatch):
    env = environment
    env.inventory["hosts"] = [host(cpu=1, ram=4096)]
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(svc.identity_roles.session_store, "_get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(svc.identity_roles, "_graph_lock", _graph_lock)
    conn = SimpleNamespace(endpoint_for=lambda service: "https://keystone.test/v3")
    save = svc._save
    waiter = None
    settled = []

    async def foreground():
        async with _graph_lock(conn, wait=True):
            assert len(env.compute.rows) == 1
            fid = next(iter(env.compute.rows))
            assert env.compute.access[fid] == {"p1"}
            assert env.compute.specs[fid]["afterglow:frontend_visible"] == "true"
            assert env.state["status"] == "idle"
            settled.append(fid)
            env.projects["p1"]["limits"]["CPU"] = 0

    async def save_then_queue(value, **kwargs):
        nonlocal waiter
        await save(value, **kwargs)
        if waiter is None and any(claim.get("dispatched") is True for claim in value["claims"].values()):
            waiter = asyncio.create_task(foreground())
            # Wait until the actual FIFO registration is visible, without
            # releasing the background lease or interrupting the native unit.
            async with asyncio.timeout(2):
                while not await redis.keys("afterglow:identity-role-graph:*:waiters"):
                    await asyncio.sleep(0.001)

    monkeypatch.setattr(svc, "_save", save_then_queue)
    try:
        result = await svc.reconcile(conn)
        assert result["status"] == "idle" and len(result["items"]) == 1
        assert result["diagnostics"][0]["code"] == "foreground_iam_waiting"
        assert waiter is not None
        await asyncio.wait_for(waiter, 2)
        assert settled == [result["items"][0]["id"]]
        assert not await redis.keys("afterglow:identity-role-graph:*")
        resumed = await svc.reconcile(conn)
        assert resumed["status"] == "complete" and len(resumed["items"]) == 2
        assert all(not access for access in env.compute.access.values())
    finally:
        if waiter is not None and not waiter.done():
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
        await redis.close()


def test_composition_operation_state_roundtrip_is_bounded_and_private():
    operation_id = "4a59a4b0-0d0a-489d-97f8-8f73f009e2ce"
    receipt = {
        "actor": "a" * 64,
        "authority": "b" * 64,
        "shape": "c" * 64,
        "composition": {"vcpus": 4, "ram_mb": 12288, "gpu_profile_id": None, "gpu_count": 0},
        "flavor_id": "98d1b806-798f-4543-843b-8c98de51ea29",
        "expires_at": 1793664000,
    }
    state = {**svc._default(), "composition_operations": {operation_id: receipt}}
    normalized = svc._state(copy.deepcopy(state))
    assert normalized["composition_operations"] == state["composition_operations"]
    assert "composition_operations" not in svc._public(normalized, {"policy_ready": True})
    legacy = svc._default()
    del legacy["composition_operations"]
    assert svc._state(legacy)["composition_operations"] == {}
    for corrupt in (None, [], {"not-a-uuid": receipt}, {operation_id: {**receipt, "authority": "bearer-secret"}}):
        with pytest.raises(HTTPException) as error:
            svc._state({**state, "composition_operations": corrupt})
        assert error.value.status_code == 503
    oversized = {str(uuid.UUID(int=index + 1)): receipt for index in range(svc.MAX_HISTORY_ACTORS + 1)}
    with pytest.raises(HTTPException):
        svc._state({**state, "composition_operations": oversized})


@pytest.mark.asyncio
async def test_operation_receipt_sql_lock_preserves_other_intents_and_rejects_collision(monkeypatch):
    operation_id = "4a59a4b0-0d0a-489d-97f8-8f73f009e2ce"
    receipt = {
        "actor": "a" * 64,
        "authority": "b" * 64,
        "shape": "c" * 64,
        "composition": {"vcpus": 4, "ram_mb": 12288, "gpu_profile_id": None, "gpu_count": 0},
        "flavor_id": "98d1b806-798f-4543-843b-8c98de51ea29",
        "expires_at": 4102444800,
    }
    saved = SimpleNamespace(value_json={**svc._default(), "composition_operations": {operation_id: receipt}})

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def begin(self):
            return self

        async def get(self, *args, **kwargs):
            assert kwargs["with_for_update"] is True
            return saved

    monkeypatch.setattr(svc, "_factory", lambda: Session)
    stale = svc._default()
    await _persist_state(stale)
    assert saved.value_json["composition_operations"][operation_id] == receipt
    collision = copy.deepcopy(saved.value_json)
    collision["composition_operations"][operation_id]["composition"]["vcpus"] = 8
    with pytest.raises(HTTPException, match="operation_conflict"):
        await _persist_state(collision)
    assert saved.value_json["composition_operations"][operation_id] == receipt
