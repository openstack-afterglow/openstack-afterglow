"""Opt-in, fenced creation of private standard Nova flavors from supported inventory.

Transient Placement usage is deliberately never consulted. Native Nova project
quotas and scheduling remain independent; publication follows Afterglow policy.
"""

from __future__ import annotations

import asyncio
import copy
import functools
import hashlib
import json
import logging
import math
import re
import secrets
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from urllib.parse import parse_qs, quote, urlsplit

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_session_factory, is_db_available
from app.models.compute import CPU_CONTROL_SPEC
from app.models.db import RuntimeSetting
from app.services import flavor_automation_policy, flavor_capacity, identity_roles
from app.services.flavor_presentation import canonical_cpu_display_name
from app.services.nova import native_flavor_extra_specs
from app.services.work_dispatcher import checkpoint, checkpoint_sync, close_connection, open_connection, run_sync

KEY = "compute.managed_flavors"
OWNER = "domain-compute-v1"
MARKER = "afterglow:managed_by"
CPU_TOKEN = CPU_CONTROL_SPEC
_NAMESPACE = uuid.UUID("dd6df1c2-c410-4e7e-a329-5f13451476d3")
_RC = re.compile(r"^CUSTOM_PCI_[0-9A-F]{4}_[0-9A-F]{4}$")
_logger = logging.getLogger(__name__)
_publication_authority = ContextVar("flavor_publication_authority", default=None)
MAX_CUSTOM_INTENTS = 4096
MAX_HISTORY_ACTORS = 4096
MAX_HISTORY_ITEMS = 20


class _ReconciliationDeferred(Exception):
    """A settled full pass releases its graph lease for foreground IAM."""


async def _yield_to_foreground(lease, enabled):
    if enabled and await lease.waiters_pending():
        raise _ReconciliationDeferred


def _now():
    return datetime.now(UTC).isoformat()


def _default():
    return {
        "enabled": False,
        "revision": 0,
        "last_run": None,
        "status": "disabled",
        "error": None,
        "items": [],
        "diagnostics": [],
        "claims": {},
        "cpu_claims": {},
        "custom_intents": {},
        "composition_history": {},
        "composition_operations": {},
    }


def _state(value):
    if value is None:
        return _default()
    if (
        not isinstance(value, dict)
        or type(value.get("enabled")) is not bool
        or type(value.get("revision")) is not int
        or value["revision"] < 0
    ):
        raise HTTPException(503, "flavor_automation_policy_unavailable")
    state = {**_default(), **value}
    if not isinstance(state["claims"], dict):
        raise HTTPException(503, "flavor_automation_policy_unavailable")
    if not isinstance(state["cpu_claims"], dict):
        raise HTTPException(503, "flavor_automation_policy_unavailable")
    for fid, claim in state["cpu_claims"].items():
        if (
            not isinstance(fid, str)
            or not fid
            or not isinstance(claim, dict)
            or type(claim.get("version")) is not int
            or claim["version"] != 1
            or not isinstance(claim.get("token"), str)
            or not re.fullmatch(r"[0-9a-f]{48}", claim["token"])
            or not isinstance(claim.get("snapshot"), dict)
            or claim["snapshot"].get("id") != fid
            or not isinstance(claim.get("extra_specs"), dict)
            or any(
                not isinstance(key, str) or not isinstance(value, str) for key, value in claim["extra_specs"].items()
            )
            or CPU_TOKEN in claim["extra_specs"]
            or MARKER in claim["extra_specs"]
            or not isinstance(claim.get("project_domains"), dict)
            or any(
                not isinstance(pid, str) or not pid or not isinstance(did, str) or not did
                for pid, did in claim["project_domains"].items()
            )
            or any(
                not isinstance(claim.get(key), list)
                or any(not isinstance(pid, str) or not pid for pid in claim[key])
                or len(claim[key]) != len(set(claim[key]))
                for key in ("access", "original_access")
            )
            or "pending" not in claim
        ):
            raise HTTPException(503, "flavor_automation_policy_unavailable")
        snapshot = claim["snapshot"]
        if set(snapshot) != {
            "id",
            "name",
            "vcpus",
            "ram",
            "disk",
            "OS-FLV-EXT-DATA:ephemeral",
            "swap",
            "description",
            "os-flavor-access:is_public",
            "rxtx_factor",
        }:
            raise HTTPException(503, "flavor_automation_policy_unavailable")
        if (
            not isinstance(snapshot["name"], str)
            or not snapshot["name"]
            or any(type(snapshot[key]) is not int or snapshot[key] <= 0 for key in ("vcpus", "ram"))
            or any(type(snapshot[key]) is not int or snapshot[key] < 0 for key in ("disk", "OS-FLV-EXT-DATA:ephemeral"))
            or snapshot["swap"] not in (0, "")
            and (type(snapshot["swap"]) is not int or snapshot["swap"] < 0)
            or snapshot["description"] is not None
            and not isinstance(snapshot["description"], str)
            or type(snapshot["swap"]) is bool
            or type(snapshot["os-flavor-access:is_public"]) is not bool
            or type(snapshot["rxtx_factor"]) not in (int, float)
            or not math.isfinite(snapshot["rxtx_factor"])
            or snapshot["rxtx_factor"] < 0
        ):
            raise HTTPException(503, "flavor_automation_policy_unavailable")
        pending = claim["pending"]
        if pending is not None and (
            not isinstance(pending, dict)
            or pending.get("kind") not in {"marker", "grant", "revoke"}
            or type(pending.get("dispatched")) is not bool
            or pending["kind"] != "marker"
            and (not isinstance(pending.get("project_id"), str) or not pending["project_id"])
            or (pending["dispatched"] or "operation_id" in pending)
            and (
                not isinstance(pending.get("operation_id"), str)
                or re.fullmatch(r"[0-9a-f]{32}", pending["operation_id"]) is None
            )
        ):
            raise HTTPException(503, "flavor_automation_policy_unavailable")
    from app.models.flavor_composition import StoredFlavorComposition

    intents, history = state["custom_intents"], state["composition_history"]
    if not isinstance(intents, dict) or len(intents) > MAX_CUSTOM_INTENTS:
        raise HTTPException(503, "flavor_automation_policy_unavailable")
    try:
        for fid, coordinates in intents.items():
            if not isinstance(fid, str) or str(uuid.UUID(fid)) != fid:
                raise ValueError("invalid saved identity")
            StoredFlavorComposition.model_validate(coordinates)
        if not isinstance(history, dict) or len(history) > MAX_HISTORY_ACTORS:
            raise ValueError("invalid composition history")
        for actor, ids in history.items():
            if (
                not isinstance(actor, str)
                or re.fullmatch(r"[0-9a-f]{64}", actor) is None
                or not isinstance(ids, list)
                or len(ids) > MAX_HISTORY_ITEMS
                or any(not isinstance(fid, str) or fid not in intents for fid in ids)
                or len(set(ids)) != len(ids)
            ):
                raise ValueError("invalid composition history")
        operations = state["composition_operations"]
        if not isinstance(operations, dict) or len(operations) > MAX_HISTORY_ACTORS:
            raise ValueError("invalid composition operations")
        for operation_id, receipt in operations.items():
            if str(uuid.UUID(operation_id)) != operation_id or not isinstance(receipt, dict):
                raise ValueError("invalid composition operation")
            if (
                set(receipt) != {"actor", "authority", "composition", "flavor_id", "shape", "expires_at"}
                or any(re.fullmatch(r"[0-9a-f]{64}", receipt[key]) is None for key in ("actor", "authority", "shape"))
                or str(uuid.UUID(receipt["flavor_id"])) != receipt["flavor_id"]
                or type(receipt["expires_at"]) is not int
            ):
                raise ValueError("invalid composition receipt")
            StoredFlavorComposition.model_validate(receipt["composition"])
    except (ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(503, "flavor_automation_policy_unavailable") from None
    return state


def _claim_token(state, flavor_id):
    claim = state["claims"].get(flavor_id)
    return claim.get("token") if isinstance(claim, dict) else claim


def _claim_dispatched(state, flavor_id):
    claim = state["claims"].get(flavor_id)
    # Legacy claims predate dispatch distinction and remain conservatively unknown.
    return claim.get("dispatched") is True if isinstance(claim, dict) else bool(claim)


_CLAIM_TOKEN = re.compile(r"[0-9a-f]{48}")


def _adoptable_claim(flavor, shape):
    """Return the native ownership token of an exact wanted managed flavor, else None."""
    description = _field(flavor, "description")
    prefix = f"afterglow:{OWNER}:"
    if not isinstance(description, str) or not description.startswith(prefix):
        return None
    token = description.removeprefix(prefix)
    if (
        not _CLAIM_TOKEN.fullmatch(token)
        or _field(flavor, "id") != shape["id"]
        or _field(flavor, "is_public") is not False
        or _field(flavor, "name") not in _immutable_names(shape)
    ):
        return None
    return token


async def _reset_unsent_claim(flavor_id, token):
    """Release only our exact claim after positively rejecting pre-submit work.

    Lease loss may have allowed another writer to update status or configuration;
    preserve that row, including its new revision, rather than saving stale state.
    """
    try:
        async with _factory()() as session, session.begin():
            row = await session.get(RuntimeSetting, KEY, with_for_update=True)
            if row is None:
                return
            current = copy.deepcopy(_state(row.value_json))
            claim = current["claims"].get(flavor_id)
            if not isinstance(claim, dict) or claim.get("token") != token or claim.get("dispatched") is not True:
                return
            current["claims"][flavor_id]["dispatched"] = False
            row.value_json = current
    except SQLAlchemyError:
        raise HTTPException(503, "flavor_automation_storage_unavailable") from None


async def _reset_unsent_cpu_claim(flavor_id, expected_claim):
    """Reset only this exact unsubmitted dispatch, preserving every newer writer."""
    pending = expected_claim.get("pending") if isinstance(expected_claim, dict) else None
    if (
        not isinstance(pending, dict)
        or pending.get("dispatched") is not True
        or not isinstance(pending.get("operation_id"), str)
        or re.fullmatch(r"[0-9a-f]{32}", pending["operation_id"]) is None
    ):
        return False
    try:
        async with _factory()() as session, session.begin():
            row = await session.get(RuntimeSetting, KEY, with_for_update=True)
            if row is None:
                return False
            current = copy.deepcopy(_state(row.value_json))
            claim = current["cpu_claims"].get(flavor_id)
            if (
                claim != expected_claim
                or not isinstance(claim, dict)
                or claim.get("pending", {}).get("dispatched") is not True
            ):
                return False
            claim["pending"]["dispatched"] = False
            row.value_json = current
            return True
    except SQLAlchemyError:
        raise HTTPException(503, "flavor_automation_storage_unavailable") from None


def _readiness(capability):
    ready = capability.get("policy_ready") is True
    return {
        "verified": ready,
        "reason": "afterglow_policy_ready" if ready else "afterglow_policy_unavailable",
    }


def _public(state, capability):
    return {
        **{
            key: value
            for key, value in state.items()
            if key not in {"claims", "cpu_claims", "custom_intents", "composition_history", "composition_operations"}
        },
        "readiness": _readiness(capability),
    }


def _factory():
    factory = get_session_factory()
    if not is_db_available() or factory is None:
        raise HTTPException(503, "flavor_automation_storage_unavailable")
    return factory


async def _load():
    try:
        async with _factory()() as session:
            row = await session.get(RuntimeSetting, KEY)
            return _state(row.value_json if row else None)
    except SQLAlchemyError:
        raise HTTPException(503, "flavor_automation_storage_unavailable") from None


async def _save(state, *, user_id=None, expected_revision=None):
    try:
        async with _factory()() as session, session.begin():
            row = await session.get(RuntimeSetting, KEY, with_for_update=True)
            expected = state["revision"] if expected_revision is None else expected_revision
            current = _state(row.value_json if row else None)
            if current["revision"] != expected:
                raise HTTPException(409, "flavor_automation_revision_conflict")
            # The graph lease and SQL commit are separate authorities. A stale
            # whole-state writer must neither replace an existing operation's
            # identity nor erase another operation recorded at this revision.
            now = datetime.now(UTC).timestamp()
            operations = {
                key: receipt
                for key, receipt in current["composition_operations"].items()
                if receipt["expires_at"] > now
            }
            for key, receipt in state["composition_operations"].items():
                previous = current["composition_operations"].get(key)
                if previous is not None and previous != receipt:
                    raise HTTPException(409, "flavor_composition_operation_conflict")
                if receipt["expires_at"] > now:
                    operations[key] = receipt
            if len(operations) > MAX_HISTORY_ACTORS:
                raise HTTPException(409, "flavor_composition_operation_limit")
            state["composition_operations"] = operations
            if row is None:
                row = RuntimeSetting(setting_key=KEY)
                session.add(row)
            row.value_json = copy.deepcopy(state)
            if user_id is not None:
                row.updated_by_user_id = user_id
    except SQLAlchemyError:
        raise HTTPException(503, "flavor_automation_storage_unavailable") from None


async def status():
    """Read stored opt-in/history and Afterglow policy readiness without writes."""
    state = await _load()
    capability = await flavor_automation_policy.capabilities()
    return _public(state, capability)


async def configure(conn, *, revision, enabled, user_id):
    async with identity_roles._graph_lock(conn) as lease:
        state = await _load()
        if state["revision"] != revision:
            raise HTTPException(409, "flavor_automation_revision_conflict")
        capability = await flavor_automation_policy.capabilities()
        if enabled and not _readiness(capability)["verified"]:
            raise HTTPException(503, "flavor_automation_policy_unavailable")
        await lease.assert_owned()
        state.update(enabled=enabled, revision=revision + 1, status="idle" if enabled else "disabled", error=None)
        await _save(state, user_id=user_id, expected_revision=revision)
        return _public(state, capability)


def _number(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("malformed supported inventory")
    return value


def _supported(inventory, resource_class):
    """Maximum one request can consume, independent of current allocations."""
    total = _number(inventory.get("total"))
    reserved = _number(inventory.get("reserved"))
    minimum = _number(inventory.get("min_unit"), 1)
    maximum = _number(inventory.get("max_unit"), 1)
    step = _number(inventory.get("step_size"), 1)
    ratio = inventory.get("allocation_ratio")
    if type(ratio) not in (int, float) or not math.isfinite(ratio) or ratio <= 0 or reserved > total:
        raise ValueError("malformed supported inventory")
    if (resource_class.startswith("CUSTOM_PCI_") or resource_class == "PCPU") and ratio != 1:
        raise ValueError("PCI/PCPU overcommit is unsupported")
    capacity = min(maximum, math.floor((total - reserved) * ratio))
    return {"capacity": capacity, "min": minimum, "step": step}


def _fits(inventory, amount):
    return inventory["min"] <= amount <= inventory["capacity"] and amount % inventory["step"] == 0


def supported_hosts(conn):
    """Complete Nova service/tree join plus stable Placement inventory, not free usage."""
    client = flavor_capacity._Client(conn)
    deadline = time.monotonic() + 120
    facts = flavor_capacity._HostFacts.fetch(client, deadline)
    body = client.placement("/resource_providers", None, deadline)
    if body.get("resource_providers_links"):
        raise ValueError("incomplete resource provider directory")
    roots = flavor_capacity._provider_roots(body)
    if len(roots) > 4096:
        raise ValueError("resource provider directory exceeds bound")
    hosts = {}
    complete = True
    seen_nodes, seen_services = set(), set()
    for hypervisor in facts.hypervisors:
        node = hypervisor.get("id")
        if not isinstance(node, str) or node not in roots or roots[node] != node or node in seen_nodes:
            raise ValueError("unmapped or duplicate compute node")
        seen_nodes.add(node)
        service_ref = hypervisor.get("service")
        if not isinstance(service_ref, dict):
            raise ValueError("missing compute service")
        service = facts.services.get(service_ref.get("id"))
        if not service or service.get("host") != service_ref.get("host"):
            raise ValueError("unmapped compute service")
        seen_services.add(service_ref["id"])
        if (
            service.get("status") not in ("enabled", "disabled")
            or service.get("state") not in ("up", "down")
            or type(service.get("forced_down")) is not bool
        ):
            raise ValueError("unknown compute service state")
        if hypervisor.get("status") not in ("enabled", "disabled") or hypervisor.get("state") not in ("up", "down"):
            raise ValueError("unknown hypervisor state")
        inventories = client.placement(f"/resource_providers/{node}/inventories", None, deadline).get("inventories")
        if not isinstance(inventories, dict):
            raise ValueError("missing root inventories")
        if not ({"VCPU", "PCPU"} & inventories.keys()) or "MEMORY_MB" not in inventories:
            complete = False
            continue
        host = {
            "id": node,
            "name": service["host"],
            "observed_at": _now(),
            "state": "up" if service["state"] == hypervisor["state"] == "up" and not service["forced_down"] else "down",
            "status": service["status"],
            "cpu": _supported(inventories["VCPU"], "VCPU")
            if "VCPU" in inventories
            else {"capacity": 0, "min": 1, "step": 1},
            "ram": _supported(inventories["MEMORY_MB"], "MEMORY_MB"),
            "gpu": {},
        }
        if "PCPU" in inventories:
            host["pcpu"] = _supported(inventories["PCPU"], "PCPU")
        for provider, root in roots.items():
            if root != node:
                continue
            values = (
                inventories
                if provider == node
                else client.placement(f"/resource_providers/{provider}/inventories", None, deadline).get("inventories")
            )
            if not isinstance(values, dict):
                raise ValueError("missing child inventories")
            for rc, value in values.items():
                if _RC.fullmatch(rc):
                    supported = _supported(value, rc)
                    # Nova creates one numbered request group per PCI function.
                    if _fits(supported, 1):
                        host["gpu"][rc] = host["gpu"].get(rc, 0) + value["total"] - value["reserved"]
        hosts[node] = host
    if set(facts.services) != seen_services:
        complete = False
    return list(hosts.values()), complete


def _scaled_specs(profile, count):
    from app.models.flavor_automation import RESOURCE_SPEC_PATTERN, alias_counts

    specs = dict(profile["extra_specs"])
    aliases = alias_counts(specs)
    if aliases:
        specs["pci_passthrough:alias"] = ",".join(f"{name}:{amount * count}" for name, amount in aliases.items())
    for key, value in list(specs.items()):
        if RESOURCE_SPEC_PATTERN.fullmatch(key):
            specs[key] = str(int(value) * count)
    return specs


def compose_shape(hosts, profiles, *, vcpus, ram_mb, gpu_profile_id=None, gpu_count=0):
    """Build one exact supported shape from untrusted resource coordinates."""
    from app.models.flavor_automation import validate_profiles

    approved = [profile for profile in validate_profiles(profiles) if profile["enabled"]]
    return _compose_shape(
        hosts,
        approved,
        vcpus=vcpus,
        ram_mb=ram_mb,
        gpu_profile_id=gpu_profile_id,
        gpu_count=gpu_count,
    )


def _compose_shape(hosts, approved, *, vcpus, ram_mb, gpu_profile_id=None, gpu_count=0):
    """Internal batch helper; approved profiles have already been validated once."""
    if type(vcpus) is not int or not 1 <= vcpus <= 128:
        raise ValueError("invalid vCPU count")
    if type(ram_mb) is not int or not 1024 <= ram_mb <= 2097152 or ram_mb % 1024:
        raise ValueError("invalid memory amount")
    if type(gpu_count) is not int or not 0 <= gpu_count <= 16:
        raise ValueError("invalid GPU count")
    profile = None
    if gpu_profile_id is not None:
        profile = next((p for p in approved if p["name"] == gpu_profile_id), None)
        if profile is None or not gpu_count:
            raise ValueError("GPU profile unavailable")
    elif gpu_count:
        raise ValueError("GPU count requires an approved profile")
    requirements = (
        {resource: amount * gpu_count for resource, amount in profile["resource_requirements"].items()}
        if profile
        else {}
    )
    specs = _scaled_specs(profile, gpu_count) if profile else {}
    alias_request = specs.get("pci_passthrough:alias", "")
    if alias_request and sum(int(pair.rsplit(":", 1)[1]) for pair in alias_request.split(",")) > 16:
        return None
    cpu_inventory = "pcpu" if specs.get("hw:cpu_policy") == "dedicated" else "cpu"
    if not any(
        _fits(host.get(cpu_inventory, {"capacity": 0, "min": 1, "step": 1}), vcpus)
        and _fits(host["ram"], ram_mb)
        and all(host["gpu"].get(resource, 0) >= amount for resource, amount in requirements.items())
        for host in hosts
    ):
        return None
    specs.update(
        {
            MARKER: OWNER,
            "afterglow:access_mode": "gpu_quota" if profile else "domain_quota",
            "afterglow:frontend_visible": "true",
        }
    )
    rc = profile["resource_class"] if profile else None
    slug = profile["name"] if profile else None
    identity = json.dumps(
        [vcpus, ram_mb, rc, gpu_count, specs] + ([slug] if profile else []), sort_keys=True, separators=(",", ":")
    )
    flavor_id = str(uuid.uuid5(_NAMESPACE, identity))
    if profile:
        name = f"gpu.{slug}x{gpu_count}_{vcpus}c_{ram_mb // 1024}g"
    else:
        family = "mem" if ram_mb >= vcpus * 4096 else "cpu"
        name = f"{family}.{vcpus}c_{ram_mb // 1024}g"
    return {
        "id": flavor_id,
        "name": name,
        "vcpus": vcpus,
        "ram": ram_mb,
        "disk": 0,
        "gpu_resource_class": rc,
        "gpu_count": gpu_count,
        "resource_requirements": requirements,
        "extra_specs": specs,
    }


def standard_shapes(hosts, profiles):
    """Bounded standards share exactly the same identity as explicit compositions."""
    from app.models.flavor_automation import validate_profiles

    approved = [profile for profile in validate_profiles(profiles) if profile["enabled"]]
    shapes = []
    for cpu in (1, 2, 4, 8, 16, 32, 64, 128):
        for ratio in (2, 4, 8, 16):
            for profile, count in [(None, 0), *((p, count) for p in approved for count in (1, 2, 4, 8))]:
                if profile and ratio == 16:
                    continue
                shape = _compose_shape(
                    hosts,
                    approved,
                    vcpus=cpu,
                    ram_mb=cpu * ratio * 1024,
                    gpu_profile_id=profile["name"] if profile else None,
                    gpu_count=count,
                )
                if shape is not None:
                    shapes.append(shape)
    return shapes


def _directory_projects(ks):
    from app.services.compute_pools import normalize_policy
    from app.services.domain_membership import _complete_rows

    def complete(manager, path, key, **query):
        try:
            return _complete_rows(manager, path, key, **query)
        except HTTPException as exc:
            # This shared reader's API-specific eviction error is provider
            # evidence failure here, not a policy/lease cancellation fence.
            raise ValueError("incomplete managed flavor project directory") from exc

    projects, seen_domains, seen_projects = {}, set(), set()
    for domain in complete(ks.domains, "/domains", "domains"):
        info = domain if isinstance(domain, dict) else getattr(domain, "_info", None)
        if not isinstance(info, dict):
            raise ValueError("invalid domain directory")
        did = info.get("id")
        if not isinstance(did, str) or not did or did in seen_domains or type(info.get("enabled")) is not bool:
            raise ValueError("invalid domain directory")
        seen_domains.add(did)
        policy = normalize_policy(info.get("afterglow_compute_pool"))
        pool = policy["enabled"] and info["enabled"]
        path = f"/projects?domain_id={quote(did, safe='')}"
        for project in complete(ks.projects, path, "projects", domain=did):
            pi = project if isinstance(project, dict) else getattr(project, "_info", None)
            if not isinstance(pi, dict):
                raise ValueError("invalid project directory")
            pid = pi.get("id")
            if (
                not isinstance(pid, str)
                or not pid
                or pid in seen_projects
                or pi.get("domain_id") != did
                or type(pi.get("enabled")) is not bool
            ):
                raise ValueError("invalid project directory")
            seen_projects.add(pid)
            projects[pid] = {
                "domain_id": did,
                "limits": dict(policy["limits"]),
                "pool": pool,
                "active": pool and pi["enabled"],
            }
    return projects


def _shape_projects(directory, shape):
    requirements = {"CPU": shape["vcpus"], "MEMORY_MB": shape["ram"]}
    if shape["gpu_resource_class"]:
        # GPU catalog visibility follows its model allocation alone, not CPU/RAM,
        # companion device accounting, transient usage or optional project caps.
        requirements = {shape["gpu_resource_class"]: shape["gpu_count"]}
    return {
        project
        for project, policy in directory.items()
        if policy.get("active", True)
        and all(
            policy["limits"].get(resource, 0 if shape["gpu_resource_class"] else -1) == -1
            or policy["limits"].get(resource, 0) >= amount
            for resource, amount in requirements.items()
        )
    }


def _pool_projects_sync():
    """Read and close a complete configured-operator directory in this worker."""
    from app.services.native_operation import NativeOperation

    with NativeOperation() as operation:
        return _directory_projects(operation.ks)


async def _pool_projects():
    return await run_sync(_pool_projects_sync)


def _compute(conn):
    # Invocation-local transport: no POST reauthentication/redirect/retry replay.
    proxy = copy.copy(conn.compute)
    proxy.default_microversion = "2.61"
    proxy.request = functools.partial(
        proxy.request, timeout=5, connect_retries=0, status_code_retries=0, allow_reauth=False, redirect=False
    )
    return proxy


def _field(value, key, default=None):
    attr = getattr(value, key, None)
    if attr is not None:
        return attr
    return value.get(key, default) if isinstance(value, dict) else default


def _specs(compute, flavor):
    return native_flavor_extra_specs(compute, _field(flavor, "id"))


def _immutable_names(shape):
    """Accept historical names only for the same immutable hardware identity."""
    suffix = shape["id"].replace("-", "")
    if not shape["gpu_count"]:
        legacy = f"cpu.ag.{shape['vcpus']}c.{shape['ram'] // 1024}g."
        cpu_name = f"cpu.{shape['vcpus']}c_{shape['ram'] // 1024}g"
        return {shape["name"], cpu_name, legacy + suffix[:12], legacy + suffix}
    base = shape["name"]
    hardware = f"x{shape['gpu_count']}_{shape['vcpus']}c_{shape['ram'] // 1024}g"
    legacy = base.removesuffix(hardware) + f".{shape['gpu_count']}gpu.{shape['vcpus']}c.{shape['ram'] // 1024}g"
    return {base} | {name + "." + version for name in (base, legacy) for version in (suffix[:12], suffix)}


def _verify_shape(flavor, shape):
    if (
        _field(flavor, "id") != shape["id"]
        or _field(flavor, "is_public") is not False
        or any(_field(flavor, key) != shape[key] for key in ("name", "vcpus", "ram", "disk"))
        or _field(flavor, "ephemeral", 0) != 0
        or _field(flavor, "swap", 0) not in (0, "")
    ):
        raise ValueError("managed flavor shape or privacy mismatch")


def _acl(compute, flavor_id):
    entries = compute.get_flavor_access(flavor_id)
    projects = set()
    for entry in entries:
        pid = _field(entry, "tenant_id") or _field(entry, "project_id")
        if not isinstance(pid, str) or not pid or pid in projects or _field(entry, "flavor_id", flavor_id) != flavor_id:
            raise ValueError("invalid flavor access readback")
        projects.add(pid)
    return projects


async def _fence(lease, revision):
    await checkpoint()
    await lease.assert_owned()
    state = await _load()
    if state["enabled"] is not True or state["revision"] != revision:
        raise HTTPException(409, "flavor_automation_policy_changed")
    authority = _publication_authority.get()
    if authority is not None:
        await authority()


async def _write(lease, revision, function, *args, **kwargs):
    await _fence(lease, revision)
    return await run_sync(function, *args, **kwargs)


def _native_body(compute, path, key):
    response = compute.get(path, microversion="2.61")
    body = response.json()
    if (
        response.status_code != 200
        or not isinstance(body, dict)
        or key not in body
        or body.get("truncated")
        or body.get("limited")
        or body.get("links", {}).get("next")
        or body.get(key + "_links")
    ):
        raise ValueError("incomplete native CPU control evidence")
    return body[key]


def _native_flavors(compute):
    """Consume marker pages without ever requesting a provider-supplied URL."""
    normalized, seen, markers = [], set(), set()
    path = "/flavors/detail?is_public=None"
    for _ in range(1000):
        response = compute.get(path, microversion="2.61")
        body = response.json()
        if (
            response.status_code != 200
            or not isinstance(body, dict)
            or not isinstance(body.get("flavors"), list)
            or body.get("truncated")
            or body.get("limited")
            or body.get("links", {}).get("next")
        ):
            raise ValueError("incomplete native flavor directory")
        rows = body["flavors"]
        for row in rows:
            fid = row.get("id") if isinstance(row, dict) else None
            if not isinstance(fid, str) or not fid or fid in seen:
                raise ValueError("invalid or repeated native flavor directory ID")
            seen.add(fid)
            value = dict(row)
            for native, field in (
                ("os-flavor-access:is_public", "is_public"),
                ("OS-FLV-EXT-DATA:ephemeral", "ephemeral"),
            ):
                if native in row:
                    value[field] = row[native]
            normalized.append(value)
        links = body.get("flavors_links", [])
        if not isinstance(links, list) or any(not isinstance(link, dict) for link in links):
            raise ValueError("invalid native flavor pagination")
        next_links = [link for link in links if link.get("rel") == "next"]
        if not next_links:
            return normalized
        if len(next_links) != 1 or not rows:
            raise ValueError("invalid native flavor pagination")
        href = next_links[0].get("href")
        if not isinstance(href, str):
            raise ValueError("invalid native flavor next link")
        target = urlsplit(href)
        endpoint = urlsplit(compute.get_endpoint())
        expected_path = endpoint.path.rstrip("/") + "/flavors/detail"
        if (
            target.fragment
            or target.username
            or target.password
            or target.netloc
            and (target.scheme, target.netloc) != (endpoint.scheme, endpoint.netloc)
            or target.path not in {"/flavors/detail", expected_path}
        ):
            raise ValueError("untrusted native flavor next link")
        query = parse_qs(target.query, keep_blank_values=True)
        marker = query.get("marker")
        if (
            not marker
            or len(marker) != 1
            or marker[0] != rows[-1]["id"]
            or marker[0] in markers
            or query.get("is_public", ["None"]) != ["None"]
        ):
            raise ValueError("invalid or repeated native flavor marker")
        markers.add(marker[0])
        path = "/flavors/detail?is_public=None&marker=" + quote(marker[0], safe="")
    raise ValueError("native flavor pagination did not terminate")


def _manual_native(compute, fid):
    """Use native envelopes, not SDK defaults, to prove identity and privacy."""
    native = _native_body(compute, f"/flavors/{quote(fid, safe='')}", "flavor")
    keys = (
        "id",
        "name",
        "vcpus",
        "ram",
        "disk",
        "OS-FLV-EXT-DATA:ephemeral",
        "swap",
        "description",
        "os-flavor-access:is_public",
        "rxtx_factor",
    )
    if not isinstance(native, dict) or any(key not in native for key in keys):
        raise ValueError("manual CPU immutable native evidence unavailable")
    snapshot = {key: native[key] for key in keys}
    if (
        snapshot["id"] != fid
        or not isinstance(snapshot["name"], str)
        or not snapshot["name"]
        or any(type(snapshot[key]) is not int or snapshot[key] <= 0 for key in ("vcpus", "ram"))
        or any(type(snapshot[key]) is not int or snapshot[key] < 0 for key in ("disk", "OS-FLV-EXT-DATA:ephemeral"))
        or snapshot["swap"] not in (0, "")
        and (type(snapshot["swap"]) is not int or snapshot["swap"] < 0)
        or snapshot["description"] is not None
        and not isinstance(snapshot["description"], str)
        or type(snapshot["os-flavor-access:is_public"]) is not bool
        or type(snapshot["swap"]) is bool
        or type(snapshot["rxtx_factor"]) not in (int, float)
        or not math.isfinite(snapshot["rxtx_factor"])
        or snapshot["rxtx_factor"] < 0
    ):
        raise ValueError("manual CPU malformed immutable native evidence")
    specs = native_flavor_extra_specs(compute, fid)
    access = set()
    if not snapshot["os-flavor-access:is_public"]:
        entries = _native_body(compute, f"/flavors/{quote(fid, safe='')}/os-flavor-access", "flavor_access")
        if not isinstance(entries, list):
            raise ValueError("incomplete native CPU access evidence")
        for entry in entries:
            pid = _field(entry, "tenant_id")
            if not isinstance(pid, str) or not pid or pid in access or _field(entry, "flavor_id") != fid:
                raise ValueError("invalid native CPU access evidence")
            access.add(pid)
    return snapshot, specs, access


async def _manual_dispatch_fence(lease, state, policy_revision):
    """Async-only final check: safe while the SDK occupies an executor worker."""
    await _fence(lease, state["revision"])
    if (await flavor_automation_policy.load_policy())["revision"] != policy_revision:
        raise HTTPException(409, "flavor_automation_policy_changed")
    await lease.assert_owned()


async def _manual_fence(lease, state, policy_revision, directory):
    await _manual_dispatch_fence(lease, state, policy_revision)
    if await _pool_projects() != directory:
        raise HTTPException(409, "flavor_automation_project_directory_changed")
    await lease.assert_owned()


def _manual_specs_equal(actual, expected):
    # Usage schedule is independent application policy, not hardware/ACL identity.
    annotation = "afterglow:usage_schedule_required"
    return {key: value for key, value in actual.items() if key != annotation} == {
        key: value for key, value in expected.items() if key != annotation
    }


def _cpu_marker(claim):
    # Native extra_specs are user-readable; the durable secret stays in the DB.
    return hashlib.sha256(claim["token"].encode("ascii")).hexdigest()


def _manual_readback(claim, snapshot, specs, access):
    if snapshot != claim["snapshot"]:
        raise ValueError("manual CPU immutable identity drift")
    expected = {**claim["extra_specs"], CPU_TOKEN: _cpu_marker(claim)}
    pending = claim.get("pending")
    target = set(claim["access"])
    if pending and pending["kind"] == "grant":
        target.add(pending["project_id"])
    elif pending and pending["kind"] == "revoke":
        target.discard(pending["project_id"])
    if _manual_specs_equal(specs, expected) and access == target:
        claim.update(access=sorted(target), pending=None)
        return
    if not pending:
        raise ValueError("manual CPU ownership, scheduling specs or ACL drift")
    if pending["dispatched"]:
        raise ValueError("previous native CPU mutation outcome remains unknown; not replayed")
    before = claim["extra_specs"] if pending["kind"] == "marker" else expected
    if not _manual_specs_equal(specs, before) or access != set(claim["access"]):
        raise ValueError("manual CPU changed before pending native mutation")


async def _manual_write(compute, lease, state, policy_revision, directory, fid, claim, intent):
    """Journal before dispatch; only exact desired readback resolves uncertainty."""
    claim["pending"] = {**intent, "operation_id": secrets.token_hex(16), "dispatched": False}
    await _manual_fence(lease, state, policy_revision, directory)
    await _save(state)
    await _manual_fence(lease, state, policy_revision, directory)
    _manual_readback(claim, *(await run_sync(_manual_native, compute, fid)))
    if claim.get("pending") is None:
        await _manual_fence(lease, state, policy_revision, directory)
        await _save(state)
        return
    submitted = False
    claim["pending"] = {**claim["pending"], "dispatched": True}
    dispatched_claim = copy.deepcopy(claim)
    loop = asyncio.get_running_loop()

    def submit():
        nonlocal submitted
        checkpoint_sync()
        snapshot, specs, access = _manual_native(compute, fid)
        before = (
            claim["extra_specs"]
            if intent["kind"] == "marker"
            else {**claim["extra_specs"], CPU_TOKEN: _cpu_marker(claim)}
        )
        if snapshot != claim["snapshot"] or not _manual_specs_equal(specs, before) or access != set(claim["access"]):
            raise ValueError("manual CPU native baseline changed at dispatch")
        # Fetch the complete directory in this worker: an async re-list here
        # would recursively occupy the same executor and can deadlock.
        if _pool_projects_sync() != directory:
            raise HTTPException(409, "flavor_automation_project_directory_changed")
        asyncio.run_coroutine_threadsafe(_manual_dispatch_fence(lease, state, policy_revision), loop).result()
        checkpoint_sync()
        submitted = True
        if intent["kind"] == "marker":
            return compute.create_flavor_extra_specs(fid, {CPU_TOKEN: _cpu_marker(claim)})
        method = compute.flavor_add_tenant_access if intent["kind"] == "grant" else compute.flavor_remove_tenant_access
        return method(fid, intent["project_id"])

    try:
        await _save(state)
        await _manual_fence(lease, state, policy_revision, directory)
        await identity_roles._to_completion(asyncio.to_thread(submit))
    except (Exception, asyncio.CancelledError):
        if not submitted:
            reset = await identity_roles._to_completion(_reset_unsent_cpu_claim(fid, dispatched_claim))
            if not reset:
                raise HTTPException(409, "flavor_automation_cpu_claim_changed") from None
            claim["pending"]["dispatched"] = False
        raise
    _manual_readback(claim, *(await run_sync(_manual_native, compute, fid)))
    if claim.get("pending"):
        raise ValueError("manual CPU native mutation readback failed")
    await _manual_fence(lease, state, policy_revision, directory)
    await _save(state)


def _accelerator_specs(specs):
    alias = specs.get("pci_passthrough:alias")
    if (
        isinstance(alias, str)
        and alias
        and all(re.fullmatch(r"[^,:]+:[1-9][0-9]*", pair.strip()) for pair in alias.split(","))
    ):
        return True
    return any(
        (
            key in {"resources:VGPU", "resources:PGPU", "resources:SRIOV_NET_VF"}
            or re.fullmatch(r"resources:CUSTOM_PCI_[0-9A-F]{4}_[0-9A-F]{4}", key)
        )
        and re.fullmatch(r"[1-9][0-9]*", value)
        for key, value in specs.items()
    )


def _manual_resources_match(snapshot, specs):
    cpu = "PCPU" if specs.get("hw:cpu_policy") == "dedicated" else "VCPU"
    expected = {"resources:" + cpu: snapshot["vcpus"], "resources:MEMORY_MB": snapshot["ram"]}
    # Disk demand also depends on ephemeral/root-image semantics; leave explicit
    # overrides unqualified rather than equating them with the nominal disk.
    return all(
        key in expected and re.fullmatch(r"[0-9]+", value) and int(value) == expected[key]
        for key, value in specs.items()
        if key.startswith("resources:")
    )


async def _manual_cpu_flavors(
    compute, lease, state, policy, directory, existing, reserved_ids, *, cooperative_yield=False, report=None
):
    report = [] if report is None else report
    for fid in sorted(set(existing) | set(state["cpu_claims"])):
        if fid in reserved_ids or fid in state["claims"]:
            continue
        await _yield_to_foreground(lease, cooperative_yield)
        flavor, claim = existing.get(fid), state["cpu_claims"].get(fid)
        item = {
            "id": fid,
            "name": _field(flavor, "name"),
            "vcpus": _field(flavor, "vcpus"),
            "ram": _field(flavor, "ram"),
            "disk": _field(flavor, "disk"),
            "gpu_resource_class": None,
            "gpu_count": None,
            "projects": 0,
            "origin": "native",
            "status": "conflict",
            "control_state": "unknown",
        }
        if flavor is None and isinstance(claim, dict):
            item.update({key: claim["snapshot"][key] for key in ("name", "vcpus", "ram", "disk")})
        try:
            if flavor is None:
                raise ValueError("claimed CPU native ID missing; claim retained against ID reuse")
            if claim is None:
                observed_specs = await run_sync(_specs, compute, flavor)
                if (
                    canonical_cpu_display_name(
                        _field(flavor, "name"), _field(flavor, "vcpus"), _field(flavor, "ram"), observed_specs
                    )
                    is None
                ):
                    if _accelerator_specs(observed_specs):
                        continue
                    item.update(
                        status="retained",
                        control_state="unqualified",
                        reason="CPU classification unverified; native flavor retained without adoption",
                    )
                    report.append(item)
                    continue
            snapshot, specs, access = await run_sync(_manual_native, compute, fid)
            if claim is None and specs.get(MARKER) == OWNER and CPU_TOKEN not in specs:
                # A generated managed flavor outside the current wanted set is
                # handled (and left unclaimed, hence retained) by the unsupported
                # managed-flavor path, never adopted as a manual CPU flavor.
                continue
            if claim is None and (MARKER in specs or CPU_TOKEN in specs):
                # Another or lost Afterglow database owns this marker. Its original
                # token cannot be recovered, so never adopt or mutate it; report it
                # as ignored instead of blocking the whole reconciliation status.
                item.update(
                    status="retained",
                    control_state="foreign_marker",
                    reason="Ownership marker without a durable claim; ignored without adoption",
                )
                report.append(item)
                continue
            label = canonical_cpu_display_name(snapshot["name"], snapshot["vcpus"], snapshot["ram"], specs)
            # Only the CPU class implied by native CPU policy and exact nominal
            # CPU/RAM demand are supported; cross-class/grouped requests are not.
            if (
                label is None
                or not _manual_resources_match(snapshot, specs)
                or specs.get("hw:cpu_policy") == "mixed"
                or specs.get("hw:emulator_threads_policy") == "isolate"
            ):
                item.update(reason="CPU classification or native resource demand unverified; native flavor unchanged")
                item["status"] = "retained" if claim is None else "conflict"
                item["control_state"] = "unqualified" if claim is None else "unknown"
                report.append(item)
                continue
            item["display_name"] = label
            item["origin"] = "adopted_cpu"
            item["gpu_count"] = 0
            if claim is None:
                claim = {
                    "version": 1,
                    "token": secrets.token_hex(24),
                    "snapshot": snapshot,
                    "extra_specs": specs,
                    "original_access": sorted(access),
                    "access": sorted(access),
                    "project_domains": {},
                    "pending": {"kind": "marker", "dispatched": False},
                }
                state["cpu_claims"][fid] = claim
                await _manual_fence(lease, state, policy["revision"], directory)
                await _save(state)
            if not isinstance(claim, dict) or claim.get("version") != 1:
                raise ValueError("unsupported durable CPU claim protocol")
            pending = claim.get("pending")
            if pending and pending["dispatched"] is False and pending["kind"] in {"grant", "revoke"}:
                # A prepared ACL request has no native authority after a crash.
                # Validate its untouched before-state, then replan from CURRENT
                # eligibility and exact tracked project/domain identities below.
                _manual_readback({**claim, "pending": None}, snapshot, specs, access)
                claim["pending"] = None
                await _manual_fence(lease, state, policy["revision"], directory)
                await _save(state)
            _manual_readback(claim, snapshot, specs, access)
            if claim.get("pending"):
                await _manual_write(compute, lease, state, policy["revision"], directory, fid, claim, claim["pending"])
            if snapshot["os-flavor-access:is_public"]:
                item.update(
                    status="retained",
                    control_state="public_external_bypass",
                    enforcement="afterglow_only",
                    reason="Public Nova flavor preserved; direct native access bypasses domain-pool private ACLs",
                )
            else:
                shape = {"vcpus": snapshot["vcpus"], "ram": snapshot["ram"], "gpu_resource_class": None}
                desired = _shape_projects(directory, shape)
                tracked = claim["project_domains"]
                for pid, project in directory.items():
                    if project.get("pool", True) and (pid not in tracked or tracked[pid] == project["domain_id"]):
                        tracked[pid] = project["domain_id"]
                controlled = {
                    pid for pid, did in tracked.items() if pid in directory and directory[pid]["domain_id"] == did
                }
                desired &= controlled
                target = (set(claim["access"]) - controlled) | desired
                for kind, pids in (("revoke", set(claim["access"]) - target), ("grant", target - set(claim["access"]))):
                    for pid in sorted(pids):
                        await _manual_write(
                            compute,
                            lease,
                            state,
                            policy["revision"],
                            directory,
                            fid,
                            claim,
                            {"kind": kind, "project_id": pid},
                        )
                item.update(
                    status="unchanged",
                    control_state="controlled",
                    projects=len(desired),
                    enforcement="native_private_acl",
                )
                if set(claim["access"]) - controlled:
                    item["reason"] = "Unmanaged or unknown project grants preserved"
            await _manual_fence(lease, state, policy["revision"], directory)
            await _save(state)
        except (HTTPException, asyncio.CancelledError):
            raise
        except Exception as exc:
            reason = (
                str(exc)
                if type(exc) is ValueError
                else "Native CPU evidence or mutation unavailable; pending ownership intent retained"
            )
            item.update(status="conflict", reason=reason)
        report.append(item)
    await _yield_to_foreground(lease, cooperative_yield)
    return report


async def _reconcile(
    conn, lease, state, capability, *, requested_shapes=None, policy=None, cooperative_yield=False, staged_facts=None
):
    cooperative_yield = cooperative_yield and requested_shapes is None
    report = []
    state["items"] = report
    await _yield_to_foreground(lease, cooperative_yield)
    policy = (
        policy
        if policy is not None
        else await flavor_automation_policy.discover_locked(conn, lease, staged_facts=staged_facts)
    )
    await _yield_to_foreground(lease, cooperative_yield)
    hosts = [host for host in policy["hosts"] if not host["removed"]]
    narrow = requested_shapes is not None
    shapes = requested_shapes if narrow else standard_shapes(hosts, policy["gpu_profiles"])
    if not narrow:
        approved = [profile for profile in policy["gpu_profiles"] if profile["enabled"]]
        wanted = {shape["id"] for shape in shapes}
        for fid, coordinates in state["custom_intents"].items():
            try:
                shape = _compose_shape(hosts, approved, **coordinates)
            except ValueError:
                continue
            # A saved slug is not authority after its approved specs change.
            if shape is not None and shape["id"] == fid and fid not in wanted:
                shapes.append(shape)
                wanted.add(fid)
    # Materialize and validate the COMPLETE directory before any native mutation.
    directory = await _pool_projects()
    compute = _compute(conn)
    flavors = await run_sync(_native_flavors, compute)
    existing = {}
    for flavor in flavors:
        fid = _field(flavor, "id")
        if not isinstance(fid, str) or not fid or fid in existing:
            raise ValueError("invalid native flavor directory")
        existing[fid] = flavor
    native_names = {_field(flavor, "name") for flavor in flavors}
    reserved_names = {
        (claim["name"], fid)
        for fid, claim in state["claims"].items()
        if isinstance(claim, dict) and isinstance(claim.get("name"), str)
    }
    await _yield_to_foreground(lease, cooperative_yield)
    # Manual flavors are reconciled independently by exact native ID/evidence;
    # occupying a generated name never grants generated-flavor ownership.
    if not narrow:
        await _manual_cpu_flavors(
            compute,
            lease,
            state,
            policy,
            directory,
            existing,
            {shape["id"] for shape in shapes},
            cooperative_yield=cooperative_yield,
            report=report,
        )
    for shape in shapes:
        await _yield_to_foreground(lease, cooperative_yield)
        projects = _shape_projects(directory, shape)
        fid = shape["id"]
        occupied_names = native_names | {name for name, owner in reserved_names if owner != fid}
        flavor = existing.get(fid)
        if flavor is not None and fid not in state["claims"]:
            # A shared or replaced Afterglow database may lose the durable claim
            # while native Nova still carries this exact deterministic identity.
            # Re-adopt ONLY current wanted shapes: unsupported marked flavors stay
            # unclaimed so the retirement path below cannot strip their grants.
            adopted = _adoptable_claim(flavor, shape)
            if adopted is not None:
                state["claims"][fid] = {"token": adopted, "dispatched": True, "name": _field(flavor, "name")}
                reserved_names.add((_field(flavor, "name"), fid))
                await _fence(lease, state["revision"])
                await _save(state)
        claim = _claim_token(state, fid)
        if (
            flavor is not None
            and claim
            and _field(flavor, "description") == f"afterglow:{OWNER}:{claim}"
            and _field(flavor, "name") in _immutable_names(shape)
        ):
            shape["name"] = _field(flavor, "name")
        elif flavor is None and not shape["gpu_count"]:
            reservation = state["claims"].get(fid)
            if isinstance(reservation, dict) and reservation.get("name") in _immutable_names(shape):
                shape["name"] = reservation["name"]
        elif flavor is None and shape["gpu_count"] and shape["name"] in occupied_names:
            base = shape["name"]
            version = fid.replace("-", "")
            shape["name"] = base + "." + version[:12]
            if shape["name"] in occupied_names:
                shape["name"] = base + "." + version
        item = {key: value for key, value in shape.items() if key != "extra_specs"}
        item.update(projects=len(projects), status="unchanged")
        if flavor is None:
            if shape["name"] in occupied_names:
                item.update(status="conflict", reason="native name is occupied; manual flavor left unchanged")
                report.append(item)
                continue
            if _claim_dispatched(state, fid):
                item.update(status="conflict", reason="previous native create outcome remains unknown; not replayed")
                report.append(item)
                continue
            claim = _claim_token(state, fid) or secrets.token_hex(24)
            state["claims"][fid] = {"token": claim, "dispatched": False, "name": shape["name"]}
            reserved_names.add((shape["name"], fid))
            await _fence(lease, state["revision"])
            await _save(state)
            # A rejected final fence must not turn an unsent request into an
            # unknown outcome. Mark dispatch only after that fence succeeds.
            await _fence(lease, state["revision"])
            state["claims"][fid]["dispatched"] = True
            await _save(state)
            submitted = False

            def submit_create(fid=fid, shape=shape, claim=claim):
                nonlocal submitted
                # Preserve the dispatcher fence at actual worker entry, not
                # merely when the operation was queued on the event loop.
                checkpoint_sync()
                submitted = True
                return compute.create_flavor(
                    id=fid,
                    name=shape["name"],
                    vcpus=shape["vcpus"],
                    ram=shape["ram"],
                    disk=0,
                    ephemeral=0,
                    swap=0,
                    is_public=False,
                    description=f"afterglow:{OWNER}:{claim}",
                )

            try:
                # SQL persistence is an await boundary: recheck graph, policy
                # and dispatcher authority AFTER it, immediately before submit.
                await _fence(lease, state["revision"])
                await identity_roles._to_completion(asyncio.to_thread(submit_create))
            except (Exception, asyncio.CancelledError):
                if not submitted:
                    state["claims"][fid]["dispatched"] = False
                    await identity_roles._to_completion(_reset_unsent_claim(fid, claim))
                raise
            flavor = await run_sync(compute.get_flavor, fid)
            native_names.add(shape["name"])
            item["status"] = "created"
        claim = _claim_token(state, fid)
        if not claim or _field(flavor, "description") != f"afterglow:{OWNER}:{claim}":
            item.update(status="conflict", reason="native ID is not owned; manual flavor left unchanged")
            report.append(item)
            continue
        try:
            _verify_shape(flavor, shape)
        except ValueError:
            item.update(status="conflict", reason="managed shape drift; immutable native flavor left unchanged")
            report.append(item)
            continue
        specs = await run_sync(_specs, compute, flavor)
        if specs.get(MARKER) != OWNER:
            claim = _claim_token(state, fid)
            if (
                any(key != "afterglow:usage_schedule_required" for key in specs)
                or not claim
                or _field(flavor, "description") != f"afterglow:{OWNER}:{claim}"
            ):
                item.update(status="conflict", reason="native ID is not owned; manual flavor left unchanged")
                report.append(item)
                continue
            await _write(lease, state["revision"], compute.create_flavor_extra_specs, fid, shape["extra_specs"])
            specs = await run_sync(_specs, compute, flavor)
        expected = dict(shape["extra_specs"])
        # This application annotation is independent of immutable hardware/ACL ownership.
        annotation = specs.pop("afterglow:usage_schedule_required", None)
        if annotation is not None:
            expected["afterglow:usage_schedule_required"] = annotation
        visibility = specs.pop("afterglow:frontend_visible", None)
        if (
            specs
            != {
                key: value
                for key, value in expected.items()
                if key not in ("afterglow:frontend_visible", "afterglow:usage_schedule_required")
            }
            or visibility not in ("true", "false")
            or (annotation is not None and not isinstance(annotation, str))
        ):
            item.update(
                status="conflict", reason="managed specs drift or failed readback; native flavor left unpublished"
            )
            report.append(item)
            continue
        if visibility == "false":
            await _write(
                lease, state["revision"], compute.create_flavor_extra_specs, fid, {"afterglow:frontend_visible": "true"}
            )
            if await run_sync(_specs, compute, flavor) != expected:
                raise ValueError("managed visibility reactivation readback failed")
        # Specs and immutable shape are positively read back BEFORE the first ACL.
        try:
            _verify_shape(await run_sync(compute.get_flavor, fid), shape)
        except ValueError:
            item.update(
                status="conflict", reason="managed shape changed during readback; native flavor left unpublished"
            )
            report.append(item)
            continue
        access = await run_sync(_acl, compute, fid)
        for pid in sorted(access - projects):
            await _write(lease, state["revision"], compute.flavor_remove_tenant_access, fid, pid)
        for pid in sorted(projects - access):
            await _write(lease, state["revision"], compute.flavor_add_tenant_access, fid, pid)
        if await run_sync(_acl, compute, fid) != projects:
            item.update(status="conflict", reason="native project visibility readback failed")
        report.append(item)
    await _yield_to_foreground(lease, cooperative_yield)
    if narrow:
        return report, []
    wanted = {shape["id"] for shape in shapes}
    reported_ids = {item["id"] for item in report}
    unsupported = []
    for fid, flavor in existing.items():
        await _yield_to_foreground(lease, cooperative_yield)
        if (
            fid not in wanted
            and fid not in reported_ids
            and fid not in state["cpu_claims"]
            and (await run_sync(_specs, compute, flavor)).get(MARKER) == OWNER
        ):
            unsupported.append(flavor)
    diagnostics = []
    if unsupported:
        for flavor in unsupported:
            await _yield_to_foreground(lease, cooperative_yield)
            fid, name = _field(flavor, "id"), _field(flavor, "name")
            claim = _claim_token(state, fid)
            retired = (
                bool(claim)
                and _field(flavor, "description") == f"afterglow:{OWNER}:{claim}"
                and _field(flavor, "is_public") is False
            )
            if retired:
                # Withdraw publication only. Native IDs/specs remain valid for
                # existing VMs and in-flight direct native requests; never DELETE.
                for pid in sorted(await run_sync(_acl, compute, fid)):
                    await _write(lease, state["revision"], compute.flavor_remove_tenant_access, fid, pid)
                await _write(
                    lease,
                    state["revision"],
                    compute.create_flavor_extra_specs,
                    fid,
                    {"afterglow:frontend_visible": "false"},
                )
                if (
                    await run_sync(_acl, compute, fid)
                    or (await run_sync(_specs, compute, flavor)).get("afterglow:frontend_visible") != "false"
                ):
                    raise ValueError("managed flavor retirement publication readback failed")
            report.append(
                {
                    "id": fid,
                    "name": name,
                    "vcpus": _field(flavor, "vcpus"),
                    "ram": _field(flavor, "ram"),
                    "disk": _field(flavor, "disk"),
                    "gpu_resource_class": None,
                    "gpu_count": 0,
                    "projects": 0,
                    "status": "retired" if retired else "retained",
                }
            )
    await _yield_to_foreground(lease, cooperative_yield)
    if not hosts:
        diagnostics.append(
            {"code": "supported_inventory_empty", "message": "No verified supported same-host CPU/RAM inventory."}
        )
    return report, diagnostics


async def reconcile(conn):
    staged_facts = (None, False)
    if (await _load())["enabled"]:
        try:
            staged_facts = await run_sync(supported_hosts, conn)
        except Exception:
            # Current policy under the lease decides whether retained support
            # is sufficient; never replace it with this pre-lock snapshot.
            staged_facts = (None, False)
    async with identity_roles._graph_lock(conn) as lease:
        state = await _load()
        capability = await flavor_automation_policy.capabilities()
        if not state["enabled"]:
            return _public(state, capability)
        if not _readiness(capability)["verified"]:
            raise HTTPException(503, "flavor_automation_policy_unavailable")
        state.update(last_run=_now(), status="running", error=None, diagnostics=[])
        await _save(state)
        try:
            items, diagnostics = await _reconcile(
                conn, lease, state, capability, cooperative_yield=True, staged_facts=staged_facts
            )
            conflicted = any(item["status"] == "conflict" for item in items)
            state.update(
                items=items,
                diagnostics=diagnostics,
                status="unavailable" if conflicted else "complete",
                error="flavor_automation_shape_conflict" if conflicted else None,
            )
        except _ReconciliationDeferred:
            state.update(
                status="idle",
                error=None,
                diagnostics=[
                    {
                        "code": "foreground_iam_waiting",
                        "message": "Reconciliation paused at a settled boundary for foreground IAM; the next pass revalidates current authority.",
                    }
                ],
            )
        except (asyncio.CancelledError, HTTPException):
            raise
        except Exception:
            _logger.exception("Managed flavor reconciliation unavailable")
            state.update(
                status="unavailable",
                error="flavor_automation_native_evidence_unavailable",
                diagnostics=[
                    {
                        "code": "native_evidence_unavailable",
                        "message": "Native inventory, policy, ownership or publication readback is unavailable; no destructive cleanup was authorized.",
                    }
                ],
            )
        await _fence(lease, state["revision"])
        await _save(state)
        from app.services.cache import invalidate

        await invalidate("afterglow:nova:*:flavors")
        return _public(state, capability)


async def reconciliation_loop():
    """Dispatcher owns this role; persisted opt-in is checked before opening Nova."""
    from app.services.keystone import get_admin_project_connection

    while True:
        try:
            await checkpoint()
            if (await _load())["enabled"]:
                conn = await open_connection(get_admin_project_connection)
                try:
                    await reconcile(conn)
                finally:
                    await close_connection(conn)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.warning("Managed flavor background reconciliation unavailable", exc_info=True)
        await asyncio.sleep(60)
