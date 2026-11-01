"""Advisory conditional choices and narrowly published, durable native compositions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import HTTPException
from keystoneauth1.exceptions.http import Unauthorized
from openstack.exceptions import ResourceNotFound

from app.models.compute import FlavorInfo, FlavorQuotaBlocker
from app.models.flavor_composition import (
    ComposerOptions,
    ComposerProfile,
    ComposerVariant,
    FlavorComposition,
    SavedCompositions,
)
from app.services import (
    flavor_automation_policy,
    flavor_eligibility,
    identity_roles,
    instance_resize,
    keystone,
    managed_flavors,
    nova,
    session_store,
)
from app.services.native_operation import NativeOperation
from app.services.work_dispatcher import close_connection, open_connection, run_sync

_SESSION_FIELDS = (
    "user_id",
    "domain_id",
    "identity_domain_id",
    "project_id",
    "target_project_id",
    "family_id",
    "scope_revision",
    "provider_id",
    "provider_revision",
    "provider_domain_id",
)
_OPTIONS_TIMEOUT = 45
_OPERATION_TTL = 86400


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _operation_authority(signature, info, *, admin):
    # Stable login/scope identity, never bearer credentials or native token bytes.
    return _digest([admin, signature, [info.get(field) for field in _SESSION_FIELDS]])


def _actor(info, project_id):
    user_id, home = info.get("user_id"), info.get("identity_domain_id")
    if not all(isinstance(value, str) and value for value in (user_id, home, project_id)):
        raise HTTPException(403, "flavor_composition_identity_unavailable")
    return hashlib.sha256(json.dumps([home, user_id, project_id], separators=(",", ":")).encode()).hexdigest()


async def _session(info):
    if not info.get("refresh_jti"):
        return None, info.get("token")
    try:
        session = await session_store.get_session(info["refresh_jti"])
    except Exception as exc:
        raise HTTPException(503, "flavor_composition_session_unavailable") from exc
    if (
        not session
        or session.get("blacklisted")
        or session.get("user_id") != info.get("user_id")
        or session.get("domain_id") != info.get("domain_id")
        or (session.get("identity_domain_id") or session.get("domain_id")) != info.get("identity_domain_id")
        or not isinstance(session.get("keystone_token"), str)
        or not session["keystone_token"].strip()
    ):
        raise HTTPException(401, "flavor_composition_session_changed")
    return tuple(session.get(field) for field in _SESSION_FIELDS), session["keystone_token"]


async def _authorize(info, project_id, *, admin=False, write=False, expected=None):
    """Fresh login, native subject/roles and exact enabled target at each write fence."""
    from app.api.deps import require_admin, require_project_write
    from app.services.domain_scope import assert_token_context, resolve_domain

    signature, token = await _session(info)
    if expected is not None and signature != expected:
        raise HTTPException(401, "flavor_composition_session_changed")
    if not admin and (not project_id or info.get("project_id") != project_id):
        raise HTTPException(403, "flavor_composition_project_mismatch")
    try:
        if admin:
            await require_admin(dict(info, token=token))
        async with NativeOperation() as operation:
            native_project = info.get("connection_project_id", info.get("project_id", "")) if admin else project_id
            native = await operation.run(keystone.validate_token, token, project_id=native_project, operation=operation)
            await operation.run(
                assert_token_context,
                native,
                user_id=info["user_id"],
                domain_id=native.get("domain_id"),
                project_id=native_project,
                identity_domain_id=info["identity_domain_id"],
                operation=operation,
            )
            target = await operation.run(operation.get, "projects", project_id)
            domain_id = identity_roles._field(target, "domain_id")
            if identity_roles._field(target, "enabled") is not True or not domain_id:
                raise HTTPException(403, "flavor_composition_project_disabled")
            await operation.run(resolve_domain, domain_id, operation=operation)
            if not admin:
                if domain_id != info.get("domain_id") or native.get("domain_id") != domain_id:
                    raise HTTPException(403, "flavor_composition_project_mismatch")
                if write:
                    require_project_write({**native, "is_system_admin": False})
    except Unauthorized as exc:
        raise HTTPException(401, "flavor_composition_native_session_invalid") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "flavor_composition_authority_unavailable") from exc
    # Native reads are await boundaries too; never continue a changed logical login.
    after, _ = await _session(info)
    if after != signature:
        raise HTTPException(401, "flavor_composition_session_changed")
    return signature


def _verify_operator(conn):
    access = conn.session.auth.get_access(conn.session)
    native = access._data.get("token", {})
    if (
        access.project_scoped is not True
        or access.system_scoped is not False
        or not isinstance(access.project_id, str)
        or not access.project_id.strip()
        or not isinstance(access.auth_token, str)
        or not access.auth_token.strip()
        or access.is_admin_project is not True
        or native.get("is_admin_project", True) is not True
        or not any(isinstance(role, str) and role.lower() == "admin" for role in access.role_names or [])
    ):
        raise HTTPException(503, "flavor_composition_executor_scope_invalid")
    conn._afterglow_authenticated_project_id = access.project_id


@asynccontextmanager
async def _operator(project_id, info):
    try:
        conn = await open_connection(keystone.get_admin_project_connection)
    except Exception as exc:
        raise HTTPException(503, "flavor_composition_executor_unavailable") from exc
    try:
        try:
            await run_sync(_verify_operator, conn)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, "flavor_composition_executor_unavailable") from exc
        conn._afterglow_project_id = project_id
        conn._afterglow_user_id = info["user_id"]
        yield conn
    finally:
        await close_connection(conn)


def _approved(policy):
    return [profile for profile in policy["gpu_profiles"] if profile["enabled"]]


def _shape(policy, coordinates):
    return managed_flavors._compose_shape(
        [host for host in policy["hosts"] if not host["removed"]], _approved(policy), **coordinates
    )


def _flavor(shape, coordinates=None):
    return FlavorInfo(
        id=shape["id"],
        name=shape["name"],
        vcpus=shape["vcpus"],
        ram=shape["ram"],
        disk=0,
        is_public=False,
        extra_specs=dict(shape["extra_specs"]),
        composition=coordinates,
    )


def _status(flavor):
    if flavor is None:
        return "unavailable"
    eligibility = flavor.eligibility
    if eligibility is None or eligibility.capacity is None:
        return "unavailable"
    if eligibility.capacity.status == "unavailable" or any(
        "unavailable" in blocker.code for blocker in eligibility.blockers
    ):
        return "unavailable"
    return "available" if eligibility.selectable else "insufficient"


async def _evaluate(
    conn,
    project_id,
    flavors,
    availability_zone,
    *,
    supported_hosts=None,
    capacity_regions=None,
    resize: instance_resize.ResizeTarget | None = None,
    same_flavor=True,
):
    # All variants share tenant quotas, domain pool and one bounded native snapshot.
    composer = (
        {"supported_hosts": supported_hosts, "capacity_regions": capacity_regions}
        if capacity_regions is not None
        else {}
    )
    evaluated = await flavor_eligibility.evaluate_project_flavors(
        conn,
        project_id,
        flavors,
        current_flavor=resize.current if resize else None,
        resize_capacity=resize is not None,
        check_capacity=True,
        availability_zone=availability_zone,
        fresh_capacity=True,
        include_gpu_projection=True,
        **composer,
    )
    # Resize demand is the increase over the replaced allocation; the same flavor
    # and image-backed root disk shrink remain native resize impossibilities.
    return instance_resize.apply_target_blockers(evaluated, resize, same_flavor=same_flavor) if resize else evaluated


async def options(conn, project_id, *, availability_zone=None, resize: instance_resize.ResizeTarget | None = None):
    try:
        async with asyncio.timeout(_OPTIONS_TIMEOUT):
            return await _options(
                conn,
                project_id,
                availability_zone=availability_zone,
                deadline=asyncio.get_running_loop().time() + _OPTIONS_TIMEOUT - 1,
                resize=resize,
            )
    except (TimeoutError, HTTPException):
        return ComposerOptions(
            gpu_profiles=[], variants=[], checked_at=datetime.now(UTC).isoformat(), status="unavailable"
        )


def _prune_regions(regions):
    """Pareto-prune equal discrete lattices without losing min/step distinctions."""
    groups = {}
    for region in regions:
        key = tuple(region[axis][field] for axis in ("vcpus", "ram_mb") for field in ("min", "step"))
        groups.setdefault(key, []).append(region)
    result = []
    for group in groups.values():
        best_ram = -1
        for region in sorted(group, key=lambda row: (row["vcpus"]["max"], row["ram_mb"]["max"]), reverse=True):
            if region["ram_mb"]["max"] > best_ram:
                result.append(region)
                best_ram = region["ram_mb"]["max"]
    return result


def _base_shape(hosts, profiles, profile, count):
    """One supported probe per fixed PCI shape; never assume 1CPU/1GiB support."""
    cpu_key = "pcpu" if profile and profile["extra_specs"].get("hw:cpu_policy") == "dedicated" else "cpu"
    if profile:
        aliases = managed_flavors._scaled_specs(profile, count).get("pci_passthrough:alias", "")
        if aliases and sum(int(pair.rsplit(":", 1)[1]) for pair in aliases.split(",")) > 16:
            return None
    for host in hosts:
        values = {}
        for key, inventory, floor, ceiling, step in (
            ("vcpus", host.get(cpu_key, {"capacity": 0, "min": 1, "step": 1}), 2, 128, 2),
            ("ram_mb", host["ram"], 1024, 2097152, 1024),
        ):
            stride = math.lcm(inventory["step"], step)
            value = ((max(inventory["min"], floor) + stride - 1) // stride) * stride
            if value > min(inventory["capacity"], ceiling):
                break
            values[key] = value
        if len(values) != 2:
            continue
        values.update(gpu_profile_id=profile["name"] if profile else None, gpu_count=count)
        shape = managed_flavors._compose_shape([host], profiles, **values)
        if shape is not None:
            return _flavor(shape, values)
    return None


def _variant(profile_id, count, flavor, regions, policy, *, enabled, publication_limits=None, credit=None):
    values = {"gpu_profile_id": profile_id, "gpu_count": count, "regions": [], "preview": None}
    if not enabled:
        return ComposerVariant(**values, status="unavailable")
    if flavor is None:
        return ComposerVariant(**values, status="insufficient")
    preview = flavor.model_copy(update={"id": "composer-preview"})
    values["preview"] = preview
    eligibility = flavor.eligibility
    if eligibility is None or eligibility.capacity is None:
        return ComposerVariant(**values, status="unavailable")
    # The exemplar may need more CPU/RAM than another root's supported minimum.
    # Fit each rectangle to quota separately, including both domain/project caps.
    variable_codes = {"cores_insufficient", "ram_insufficient", "host_capacity_insufficient"}
    if regions:
        variable_codes.add("host_capacity_unavailable")
    blockers = [
        blocker
        for blocker in eligibility.blockers
        if blocker.code not in variable_codes
        and not (
            blocker.code in {"domain_pool_exhausted", "project_pool_ceiling_exhausted"}
            and blocker.resource in {"CPU", "MEMORY_MB"}
        )
    ]
    if any("unavailable" in blocker.code for blocker in blockers):
        return ComposerVariant(**values, status="unavailable")
    clipped = []
    if not blockers:
        for region in regions:
            region = {key: dict(value) for key, value in region.items()}
            for key, remaining in (("vcpus", eligibility.remaining.cores), ("ram_mb", eligibility.remaining.ram_mb)):
                if remaining != -1:
                    # A resize returns the replaced allocation to the same quota.
                    remaining += (credit or {}).get(key, 0)
                    bound = remaining // region[key]["step"] * region[key]["step"]
                    region[key]["max"] = min(region[key]["max"], bound)
            if profile_id is None and publication_limits is not None:
                for key, resource in (("vcpus", "CPU"), ("ram_mb", "MEMORY_MB")):
                    bound = publication_limits.get(resource, -1)
                    if bound != -1:
                        region[key]["max"] = min(region[key]["max"], bound // region[key]["step"] * region[key]["step"])
            if all(value["max"] >= value["min"] for value in region.values()):
                clipped.append(region)
    clipped = _prune_regions(clipped)
    if not clipped:
        if not blockers:
            blockers = [FlavorQuotaBlocker(code="host_capacity_insufficient")]
        values["preview"] = preview.model_copy(
            update={"eligibility": eligibility.model_copy(update={"selectable": False, "blockers": blockers})}
        )
        return ComposerVariant(**values, status="insufficient")
    base = clipped[0]
    coordinates = {
        "vcpus": base["vcpus"]["min"],
        "ram_mb": base["ram_mb"]["min"],
        "gpu_profile_id": profile_id,
        "gpu_count": count,
    }
    preview = _flavor(_shape(policy, coordinates), coordinates).model_copy(
        update={
            "id": "composer-preview",
            "gpu_primary_aliases": flavor.gpu_primary_aliases,
        }
    )
    capacity = eligibility.capacity.model_copy(
        update={
            "status": "available",
            "remaining_vcpus": base["vcpus"]["max"],
            "remaining_ram_mb": base["ram_mb"]["max"],
        }
    )
    eligibility = eligibility.model_copy(
        update={
            "selectable": True,
            "blockers": [],
            "capacity": capacity,
            "requirements": eligibility.requirements.model_copy(
                update={
                    "cores": coordinates["vcpus"],
                    "ram_mb": coordinates["ram_mb"],
                }
            ),
        }
    )
    values.update(regions=clipped, preview=preview.model_copy(update={"eligibility": eligibility}))
    return ComposerVariant(**values, status="available")


async def _options(conn, project_id, *, availability_zone=None, deadline=None, resize=None):
    policy = await flavor_automation_policy.load_policy()
    try:
        directory = await managed_flavors._pool_projects()
    except (ValueError, HTTPException, TimeoutError):
        return ComposerOptions(
            gpu_profiles=[], variants=[], checked_at=datetime.now(UTC).isoformat(), status="unavailable"
        )
    target = directory.get(project_id)
    active = bool(target and target.get("active", True))
    limits = target["limits"] if target else {}
    profiles = [
        profile
        for profile in _approved(policy)
        if active and (limits.get(profile["resource_class"], 0) == -1 or limits.get(profile["resource_class"], 0) >= 1)
    ]
    hosts = [host for host in policy["hosts"] if not host["removed"]]
    variants = [(None, 0), *((profile, count) for count in range(1, 17) for profile in profiles)]
    try:
        state_deadline = deadline if deadline is not None else asyncio.get_running_loop().time() + _OPTIONS_TIMEOUT - 1
        async with asyncio.timeout_at(state_deadline):
            state = await managed_flavors._load()
    except (TimeoutError, HTTPException):
        return ComposerOptions(
            gpu_profiles=[ComposerProfile(id=profile["name"], name=profile["display_name"]) for profile in profiles],
            variants=[
                ComposerVariant(
                    gpu_profile_id=profile["name"] if profile else None,
                    gpu_count=count,
                    status="unavailable",
                    regions=[],
                    preview=None,
                )
                for profile, count in variants
            ],
            checked_at=datetime.now(UTC).isoformat(),
            status="unavailable",
        )
    probes = [
        _base_shape(hosts, profiles, profile, count)
        if active
        and (
            profile is None
            or limits.get(profile["resource_class"], 0) == -1
            or limits.get(profile["resource_class"], 0) >= count
        )
        else None
        for profile, count in variants
    ]
    regions = {}
    evaluated = {}
    evaluation_failed = False
    if state["enabled"]:
        try:
            remaining = (
                max(0, deadline - asyncio.get_running_loop().time()) if deadline is not None else _OPTIONS_TIMEOUT - 1
            )
            async with asyncio.timeout(remaining):
                evaluated = {
                    flavor.id: flavor
                    for flavor in await _evaluate(
                        conn,
                        project_id,
                        [probe for probe in probes if probe is not None],
                        availability_zone,
                        supported_hosts=hosts,
                        capacity_regions=regions,
                        resize=resize,
                        # A minimal probe equal to the current shape still bounds larger tuples.
                        same_flavor=False,
                    )
                }
        except (TimeoutError, HTTPException):
            evaluation_failed = True
    results = [
        _variant(
            profile["name"] if profile else None,
            count,
            evaluated.get(probe.id) if probe else None,
            regions.get(probe.id, []) if probe else [],
            policy,
            enabled=state["enabled"] and not evaluation_failed,
            publication_limits=limits,
            credit={"vcpus": resize.current.vcpus, "ram_mb": resize.current.ram} if resize else None,
        )
        for (profile, count), probe in zip(variants, probes, strict=True)
    ]
    statuses = {variant.status for variant in results}
    return ComposerOptions(
        gpu_profiles=[ComposerProfile(id=profile["name"], name=profile["display_name"]) for profile in profiles],
        variants=results,
        checked_at=datetime.now(UTC).isoformat(),
        status="available"
        if "available" in statuses
        else "unavailable"
        if "unavailable" in statuses
        else "insufficient",
    )


async def history(conn, project_id, info, *, admin=False, availability_zone=None, resize=None):
    await _authorize(info, project_id, admin=admin)
    state = await managed_flavors._load()
    ids = state["composition_history"].get(_actor(info, project_id), [])
    if not ids:
        return SavedCompositions(items=[])
    policy = await flavor_automation_policy.load_policy()
    # Native visibility is read on every request; history is not a visibility grant.
    visible = {flavor.id: flavor for flavor in await asyncio.to_thread(nova.list_flavors, conn)}
    items = []
    for fid in ids:
        coordinates = state["custom_intents"][fid]
        try:
            shape = _shape(policy, coordinates)
        except ValueError:
            continue
        if shape is None or shape["id"] != fid or fid not in visible:
            continue
        flavor = visible[fid]
        if not flavor_eligibility.is_flavor_frontend_visible(flavor):
            continue
        items.append(flavor.model_copy(update={"composition": dict(coordinates)}))
    return SavedCompositions(items=await _evaluate(conn, project_id, items, availability_zone, resize=resize))


async def resolve(conn, project_id, info, operation_id, *, admin=False, availability_zone=None, resize=None):
    """GET-only recovery of this exact dispatch, never a tuple/history guess or replay."""
    signature = await _authorize(info, project_id, admin=admin, write=True)
    state = await managed_flavors._load()
    receipt = state["composition_operations"].get(str(operation_id))
    if not receipt or receipt["expires_at"] <= time.time():
        return None  # The original request can still be waiting for the graph lease.
    receipt = dict(receipt)
    if receipt["actor"] != _actor(info, project_id) or receipt["authority"] != _operation_authority(
        signature, info, admin=admin
    ):
        raise HTTPException(403, "flavor_composition_operation_mismatch")
    if state["custom_intents"].get(receipt["flavor_id"]) != receipt["composition"] or receipt["flavor_id"] not in state[
        "composition_history"
    ].get(receipt["actor"], []):
        return None  # Native visibility alone cannot promise durable reconciliation retention.
    if not state["enabled"]:
        raise HTTPException(409, "flavor_automation_disabled")
    policy = await flavor_automation_policy.load_policy()
    try:
        shape = _shape(policy, receipt["composition"])
    except ValueError as exc:
        raise HTTPException(409, "flavor_composition_policy_changed") from exc
    if shape is None or shape["id"] != receipt["flavor_id"] or _digest(shape) != receipt["shape"]:
        raise HTTPException(409, "flavor_composition_policy_changed")
    directory = await managed_flavors._pool_projects()
    projects = managed_flavors._shape_projects(directory, shape)
    if project_id not in projects:
        raise HTTPException(403, "flavor_composition_publication_denied")
    claim = managed_flavors._claim_token(state, shape["id"])
    if not claim:
        return None
    # A durable dispatch receipt is not proof of publication. Read back ownership,
    # immutable shape, full scheduling specs and ACL even if POST lost its response.
    async with _operator(project_id, info) as operator:
        compute = managed_flavors._compute(operator)
        try:
            native = await run_sync(compute.get_flavor, shape["id"])
        except ResourceNotFound:
            return None
        if native is None:
            return None
        if identity_roles._field(native, "description") != f"afterglow:{managed_flavors.OWNER}:{claim}":
            raise HTTPException(409, "flavor_composition_native_conflict")
        native_name = identity_roles._field(native, "name")
        if native_name not in managed_flavors._immutable_names(shape):
            raise HTTPException(409, "flavor_composition_native_conflict")
        native_shape = {**shape, "name": native_name}
        try:
            managed_flavors._verify_shape(native, native_shape)
        except ValueError as exc:
            raise HTTPException(409, "flavor_composition_native_conflict") from exc
        specs = dict(await run_sync(managed_flavors._specs, compute, native))
        specs.pop("afterglow:usage_schedule_required", None)
        if specs != shape["extra_specs"] or await run_sync(managed_flavors._acl, compute, shape["id"]) != projects:
            return None  # The original executor may still be publishing; no writes here.
    visible = {flavor.id: flavor for flavor in await asyncio.to_thread(nova.list_flavors, conn)}
    item = visible.get(shape["id"])
    if item is None or not flavor_eligibility.is_flavor_frontend_visible(item):
        return None
    evaluated = await _evaluate(
        conn,
        project_id,
        [item.model_copy(update={"composition": receipt["composition"]})],
        availability_zone,
        resize=resize,
    )
    if not evaluated or _status(evaluated[0]) != "available":
        raise HTTPException(409, "flavor_composition_not_selectable")
    await _authorize(info, project_id, admin=admin, write=True, expected=signature)
    current = await managed_flavors._load()
    if (
        not current["enabled"]
        or current["composition_operations"].get(str(operation_id)) != receipt
        or current["custom_intents"].get(receipt["flavor_id"]) != receipt["composition"]
        or receipt["flavor_id"] not in current["composition_history"].get(receipt["actor"], [])
        or managed_flavors._claim_token(current, shape["id"]) != claim
        or receipt["expires_at"] <= time.time()
        or await flavor_automation_policy.load_policy() != policy
        or await managed_flavors._pool_projects() != directory
    ):
        raise HTTPException(409, "flavor_composition_publication_changed")
    return evaluated[0]


@identity_roles._complete_mutation
async def save(
    conn,
    project_id,
    info,
    request: FlavorComposition,
    *,
    operation_id=None,
    admin=False,
    availability_zone=None,
    resize=None,
):
    signature = await _authorize(info, project_id, admin=admin, write=True)
    actor = _actor(info, project_id)
    coordinates = request.model_dump()
    operation_id = str(operation_id or uuid.uuid4())
    async with _operator(project_id, info) as operator, identity_roles._graph_lock(operator, wait=True) as lease:
        state = await managed_flavors._load()
        if not state["enabled"]:
            raise HTTPException(409, "flavor_automation_disabled")
        policy = await flavor_automation_policy.load_policy()
        try:
            shape = _shape(policy, coordinates)
        except ValueError as exc:
            raise HTTPException(422, "flavor_composition_profile_unavailable") from exc
        if shape is None:
            raise HTTPException(409, "flavor_composition_unsupported")
        fid = shape["id"]
        operations = state["composition_operations"]
        previous = operations.get(operation_id)
        receipt = {
            "actor": actor,
            "authority": _operation_authority(signature, info, admin=admin),
            "composition": coordinates,
            "flavor_id": fid,
            "shape": _digest(shape),
            "expires_at": int(time.time()) + _OPERATION_TTL,
        }
        if previous is not None:
            # A repeated POST is never an instruction to repeat an uncertain write.
            raise HTTPException(409, "flavor_composition_operation_exists")
        state["composition_operations"] = {
            key: value for key, value in operations.items() if value["expires_at"] > time.time()
        }
        if len(state["composition_operations"]) >= managed_flavors.MAX_HISTORY_ACTORS:
            raise HTTPException(409, "flavor_composition_operation_limit")
        if fid not in state["custom_intents"] and len(state["custom_intents"]) >= managed_flavors.MAX_CUSTOM_INTENTS:
            raise HTTPException(409, "flavor_composition_intent_limit")
        if (
            actor not in state["composition_history"]
            and len(state["composition_history"]) >= managed_flavors.MAX_HISTORY_ACTORS
        ):
            raise HTTPException(409, "flavor_composition_history_limit")
        evaluated = await _evaluate(conn, project_id, [_flavor(shape, coordinates)], availability_zone, resize=resize)
        if resize and evaluated and any(blocker.code == "same_flavor" for blocker in evaluated[0].eligibility.blockers):
            # Before any native write: publishing the current shape cannot change the VM.
            raise HTTPException(409, "flavor_composition_same_as_current")
        if not evaluated or _status(evaluated[0]) != "available":
            raise HTTPException(
                409 if evaluated and _status(evaluated[0]) == "insufficient" else 503,
                "flavor_composition_not_selectable",
            )
        directory = await managed_flavors._pool_projects()
        if project_id not in managed_flavors._shape_projects(directory, shape):
            raise HTTPException(403, "flavor_composition_publication_denied")

        async def authority():
            await _authorize(info, project_id, admin=admin, write=True, expected=signature)
            current = await flavor_automation_policy.load_policy()
            if current != policy:
                raise HTTPException(409, "flavor_composition_policy_changed")
            current_directory = await managed_flavors._pool_projects()
            if current_directory != directory or project_id not in managed_flavors._shape_projects(
                current_directory, shape
            ):
                raise HTTPException(409, "flavor_composition_publication_changed")
            await lease.assert_owned()

        token = managed_flavors._publication_authority.set(authority)
        try:
            await managed_flavors._fence(lease, state["revision"])
            # Persist exact operation/spec/login identity before any native dispatch.
            state["composition_operations"][operation_id] = receipt
            await managed_flavors._save(state)
            items, _ = await managed_flavors._reconcile(
                operator, lease, state, {}, requested_shapes=[shape], policy=policy
            )
            if len(items) != 1 or items[0]["status"] not in {"created", "unchanged"}:
                raise HTTPException(409, "flavor_composition_native_conflict")
            # Re-prove native visibility and capacity before recording personal history.
            visible = {flavor.id: flavor for flavor in await asyncio.to_thread(nova.list_flavors, conn)}
            if fid not in visible:
                raise HTTPException(503, "flavor_composition_readback_unavailable")
            item = visible[fid].model_copy(update={"composition": coordinates})
            evaluated = await _evaluate(conn, project_id, [item], availability_zone, resize=resize)
            if not evaluated or _status(evaluated[0]) != "available":
                raise HTTPException(409, "flavor_composition_not_selectable")
            await managed_flavors._fence(lease, state["revision"])
            # Only positively read-back publication becomes a durable reusable intent.
            # Failed or fenced requests retain private claims, never personal history.
            state["custom_intents"][fid] = coordinates
            ids = state["composition_history"].get(actor, [])
            state["composition_history"][actor] = [fid, *(old for old in ids if old != fid)][
                : managed_flavors.MAX_HISTORY_ITEMS
            ]
            await managed_flavors._save(state)
        except HTTPException:
            raise
        except Exception as exc:
            # The native write may already have committed. Preserve its durable
            # claim and never turn an uncertain outcome into a retryable create.
            raise HTTPException(503, "flavor_composition_native_outcome_unknown") from exc
        finally:
            managed_flavors._publication_authority.reset(token)
    from app.services.cache import invalidate

    await invalidate("afterglow:nova:*:flavors")
    return evaluated[0]
