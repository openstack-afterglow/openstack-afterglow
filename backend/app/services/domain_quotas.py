"""Afterglow allocation budgets, not a universal native domain usage cap.

The existing renewable graph lease is always outermost. SQL intent is committed
before each native call; verified provider sections are not rolled back as if
independent cloud services formed a transaction. Crashed in-flight operations
fence later writers until an operator resolves the durable journal.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.api.common.errors import public_service_error
from app.database import get_session_factory
from app.models.domain_quotas import DomainQuotaOperation, DomainQuotaPolicy
from app.services import domain_iam, identity_roles, keystone, quota_native
from app.services.cache import invalidate


def validate_limits(values: dict, *, allow_empty=True) -> dict[str, int]:
    keys = {key for fields in quota_native.QUOTA_FIELDS.values() for key in fields}
    if not isinstance(values, dict) or (not values and not allow_empty):
        raise HTTPException(422, "quota_values_required")
    if any(key not in keys or type(value) is not int or value < -1 for key, value in values.items()):
        raise HTTPException(422, "quota_values_invalid")
    return dict(values)


@asynccontextmanager
async def _session():
    factory = get_session_factory()
    if factory is None:
        raise public_service_error(503, "quota_policy_storage_unavailable")
    try:
        async with factory() as session:
            yield session
    except HTTPException:
        raise
    except Exception as exc:
        raise public_service_error(503, "quota_policy_storage_unavailable") from exc


async def _call(fn, *args, **kwargs):
    return await identity_roles._to_completion(asyncio.to_thread(fn, *args, **kwargs))


def _directory(conn, domain_id):
    try:
        domain = conn.identity.get_domain(domain_id)
        if domain is None:
            raise HTTPException(404, "domain_not_found")
        if getattr(domain, "id", None) != domain_id:
            raise public_service_error(503, "quota_domain_unverified")
        projects = {}
        for project in conn.identity.projects(domain_id=domain_id):
            if getattr(project, "domain_id", None) != domain_id:
                raise public_service_error(503, "quota_project_directory_unverified")
            pid = getattr(project, "id", None)
            if not isinstance(pid, str) or not pid:
                raise public_service_error(503, "quota_project_directory_unverified")
            projects[pid] = {
                "id": pid,
                "name": getattr(project, "name", "") or "",
                "enabled": bool(getattr(project, "is_enabled", False)),
            }
        return list(projects.values())
    except HTTPException:
        raise
    except Exception as exc:
        raise public_service_error(503, "quota_project_directory_unavailable") from exc


async def project_domain(conn, project_id: str) -> str:
    try:
        obj = await _call(conn.identity.get_project, project_id)
        if obj is None:
            raise HTTPException(404, "project_not_found")
        domain_id = getattr(obj, "domain_id", None)
        if getattr(obj, "id", None) != project_id or not isinstance(domain_id, str) or not domain_id:
            raise public_service_error(503, "quota_project_unverified")
        return domain_id
    except HTTPException:
        raise
    except Exception as exc:
        status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
        if status == 404:
            raise HTTPException(404, "project_not_found") from exc
        raise public_service_error(503, "quota_project_unavailable") from exc


async def _policy(session, domain_id, *, create=False):
    row = (
        await session.execute(
            select(DomainQuotaPolicy).where(DomainQuotaPolicy.domain_id == domain_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None and create:
        row = DomainQuotaPolicy(domain_id=domain_id, revision=0, ceilings={}, defaults={})
        session.add(row)
        await session.flush()
    return row


async def _commit(session, lease):
    await lease.assert_owned()
    await session.commit()
    await lease.assert_owned()


def _section_values(section, values):
    return {native: values[key] for key, native in quota_native.QUOTA_FIELDS[section].items() if key in values}


async def _measure(conn, projects, keys):
    """Read only relevant services, but every exact project including disabled."""
    sections = {section for section, fields in quota_native.QUOTA_FIELDS.items() if set(fields) & set(keys)}
    gate = asyncio.Semaphore(8)

    async def read(project, section):
        async with gate:
            try:
                return project["id"], section, await _call(quota_native.get_section, conn, project["id"], section)
            except Exception:
                return project["id"], section, None

    rows = await asyncio.gather(*(read(project, section) for project in projects for section in sections))
    native = {(pid, section): value for pid, section, value in rows}
    result = {}
    per_project = {}
    for key in keys:
        section, native_key = next((s, fields[key]) for s, fields in quota_native.QUOTA_FIELDS.items() if key in fields)
        values = []
        for project in projects:
            entries = native.get((project["id"], section))
            entry = entries.get(native_key) if isinstance(entries, dict) else None
            value = entry.get("limit") if isinstance(entry, dict) else None
            value = value if type(value) is int and value >= -1 else None
            per_project[project["id"], key] = value
            values.append(value)
        if any(value is None for value in values):
            result[key] = {"limit": None, "status": "unavailable", "error": "quota_unavailable"}
        elif -1 in values:
            result[key] = {"limit": -1, "status": "unlimited"}
        else:
            result[key] = {"limit": sum(values), "status": "ready"}
    return result, per_project


def _check_budget(ceilings, allocations):
    for key, ceiling in ceilings.items():
        if ceiling == -1:
            continue
        current = allocations[key]
        # A replaced target can repair unknown/unlimited values only when all
        # other projects were measurable; _proposal measures those separately.
        if current["status"] != "ready":
            raise HTTPException(409, f"quota_budget_unverifiable:{key}")
        if current["limit"] > ceiling:
            raise HTTPException(409, f"quota_budget_exceeded:{key}")


async def _proposal(conn, projects, ceilings, project_id, proposed, *, allow_decreasing_repair=True):
    """Substitute requested limits BEFORE summing; never confuse limits/use."""
    keys = set(ceilings) | set(proposed)
    allocations, actual = await _measure(conn, projects, keys)
    if any(actual.get((project_id, key)) is None for key in proposed):
        # Unsupported/disabled services and omitted native fields must fail
        # before the first effect, even when no ceiling constrains that key.
        raise public_service_error(503, "quota_native_preflight_unavailable")
    for key, ceiling in ceilings.items():
        if ceiling == -1:
            continue
        values = [
            proposed[key] if p["id"] == project_id and key in proposed else actual[p["id"], key] for p in projects
        ]
        if None in values or -1 in values:
            raise HTTPException(409, f"quota_budget_unverifiable:{key}")
        total = sum(values)
        if total > ceiling:
            # Permit a strictly decreasing repair of externally introduced
            # drift, never growth or an unrelated unchanged over-budget key.
            before = actual.get((project_id, key))
            repaired = (
                allow_decreasing_repair
                and key in proposed
                and before is not None
                and (before == -1 or proposed[key] < before)
            )
            if not repaired:
                raise HTTPException(409, f"quota_budget_exceeded:{key}")
    return allocations


async def _operations(session, domain_id):
    query = (
        select(DomainQuotaOperation)
        .where(DomainQuotaOperation.domain_id == domain_id)
        .order_by(
            DomainQuotaOperation.status.in_(("applying", "unknown")).desc(),
            DomainQuotaOperation.created_at.desc(),
        )
        .limit(50)
    )
    return list((await session.execute(query)).scalars())


async def _assert_settled(session, domain_id):
    # A transport timeout does not prove a native controller stopped working.
    # Only an explicit system-admin settlement acknowledgement plus readback
    # may release this fence; never retry the original provider mutation.
    query = (
        select(DomainQuotaOperation.id)
        .where(
            DomainQuotaOperation.domain_id == domain_id,
            DomainQuotaOperation.status.in_(("applying", "unknown")),
        )
        .limit(1)
    )
    if (await session.execute(query)).first() is not None:
        raise HTTPException(409, "quota_native_operation_unresolved")


async def _invalidate(project_id):
    for suffix in (
        f"afterglow:dashboard:{project_id}:quotas",
        f"afterglow:dashboard:{project_id}:quotas:overview",
        f"afterglow:nova:{project_id}:quota:strict",
        f"afterglow:cinder:{project_id}:quota:strict",
    ):
        await invalidate(suffix)


async def _apply(conn, domain_id, project_id, values, *, lease, require_disabled=False):
    await lease.assert_owned()
    projects = await _call(_directory, conn, domain_id)
    target = next((project for project in projects if project["id"] == project_id), None)
    if target is None or await project_domain(conn, project_id) != domain_id:
        raise HTTPException(403, "quota_project_domain_mismatch")
    if require_disabled and target["enabled"]:
        raise HTTPException(409, "quota_defaults_require_disabled_project")
    async with _session() as session:
        policy = await _policy(session, domain_id)
        ceilings = validate_limits(policy.ceilings) if policy else {}
        await _assert_settled(session, domain_id)
        await _proposal(conn, projects, ceilings, project_id, values, allow_decreasing_repair=not require_disabled)
        if not values:
            return {
                "project_id": project_id,
                "domain_id": domain_id,
                "status": "updated",
                "updated": [],
                "errors": {},
                "operation_id": None,
            }
        requested = validate_limits(values, allow_empty=False)
        sections = {
            section: {"status": "pending"}
            for section in quota_native.QUOTA_FIELDS
            if _section_values(section, requested)
        }
        operation = DomainQuotaOperation(
            id=str(uuid4()),
            domain_id=domain_id,
            project_id=project_id,
            status="applying",
            requested=requested,
            sections=sections,
        )
        session.add(operation)
        await _commit(session, lease)
        updated, errors = [], {}
        try:
            for section in sections:
                kwargs = _section_values(section, requested)
                operation.sections = {**operation.sections, section: {"status": "writing"}}
                await _commit(session, lease)
                failure = False
                await lease.assert_owned()
                try:
                    await _call(quota_native.update_section, conn, project_id, section, kwargs)
                except Exception:
                    failure = True
                # Even an exception may follow a committed native effect. Read
                # back this service instead of declaring failure or retrying.
                await lease.assert_owned()
                try:
                    entries = await _call(quota_native.get_section, conn, project_id, section)
                    observed = {key: entries[key]["limit"] for key in kwargs}
                    if failure:
                        # A timed-out native controller may still complete
                        # after this read. Matching current limits are useful
                        # evidence, not proof the original call has settled.
                        errors[section] = "native_outcome_unknown"
                        state = {"status": "unknown", "error": errors[section], "observed": observed}
                    elif observed == kwargs:
                        state = {"status": "verified", "observed": observed}
                        updated.append(section)
                    else:
                        errors[section] = "native_readback_mismatch"
                        state = {"status": "partial", "error": errors[section], "observed": observed}
                except Exception:
                    errors[section] = "native_readback_unavailable"
                    state = {"status": "unknown", "error": errors[section]}
                operation.sections = {**operation.sections, section: state}
                operation.updated_at = datetime.now(UTC)
                await _commit(session, lease)
                if state["status"] == "unknown":
                    # Stop new effects when the current provider result cannot
                    # be bounded. Unattempted services remain explicit pending.
                    break
            operation.status = (
                "unknown"
                if any(s["status"] == "unknown" for s in operation.sections.values())
                else "partial"
                if errors
                else "updated"
            )
            for section, state in operation.sections.items():
                if state["status"] == "pending":
                    errors[section] = "not_attempted"
            await _commit(session, lease)
        finally:
            await _invalidate(project_id)
        return {
            "project_id": project_id,
            "domain_id": domain_id,
            "operation_id": operation.id,
            "status": operation.status,
            "updated": updated,
            "errors": errors,
        }


@identity_roles._complete_mutation
async def update_project(conn, project_id, values, *, domain_id=None, token_info=None):
    values = validate_limits(values, allow_empty=False)
    async with identity_roles._graph_lock(conn) as lease:
        if token_info is not None:
            context = await domain_iam.context(token_info)
            if context["domain_id"] != domain_id:
                raise HTTPException(403, "quota_domain_mismatch")
        native_domain = await project_domain(conn, project_id)
        if domain_id is not None and domain_id != native_domain:
            raise HTTPException(403, "quota_project_domain_mismatch")
        return await _apply(conn, native_domain, project_id, values, lease=lease)


async def apply_project_defaults(conn, domain_id: str, project_id: str, *, lease) -> dict:
    """Caller holds graph lease and must not enable project before success."""
    await lease.assert_owned()
    async with _session() as session:
        row = await _policy(session, domain_id)
        defaults = validate_limits(row.defaults) if row else {}
    result = await _apply(conn, domain_id, project_id, defaults, lease=lease, require_disabled=True)
    if result["status"] != "updated":
        raise public_service_error(503, "quota_defaults_not_verified")
    return result


async def assert_project_allocation(conn, domain_id: str, project_id: str, *, lease) -> dict:
    """Verify an existing project's allocation before enable, without defaults.

    Caller holds the shared graph lease across this read and native enable.
    Unlike creation, re-enabling must never reapply future-project defaults.
    """
    await lease.assert_owned()
    projects = await _call(_directory, conn, domain_id)
    if not any(project["id"] == project_id for project in projects):
        raise HTTPException(403, "quota_project_domain_mismatch")
    if await project_domain(conn, project_id) != domain_id:
        raise HTTPException(403, "quota_project_domain_mismatch")
    async with _session() as session:
        row = await _policy(session, domain_id)
        ceilings = validate_limits(row.ceilings) if row else {}
        await _assert_settled(session, domain_id)
        allocations, _ = await _measure(conn, projects, ceilings)
        _check_budget(ceilings, allocations)
        await lease.assert_owned()
        return {"domain_id": domain_id, "project_id": project_id, "status": "verified"}


async def snapshot(conn, domain_id):
    projects = await _call(_directory, conn, domain_id)
    async with _session() as session:
        row = await _policy(session, domain_id)
        ceilings, defaults = (validate_limits(row.ceilings), validate_limits(row.defaults)) if row else ({}, {})
        keys = {key for fields in quota_native.QUOTA_FIELDS.values() for key in fields}
        allocations, _ = await _measure(conn, projects, keys)
        for key, metric in allocations.items():
            ceiling = ceilings.get(key, -1)
            metric["within_budget"] = (
                None
                if metric["status"] == "unavailable"
                else ceiling == -1 or (metric["status"] == "ready" and metric["limit"] <= ceiling)
            )
        operations = [
            {
                "id": op.id,
                "project_id": op.project_id,
                "status": op.status,
                "requested": op.requested,
                "sections": op.sections,
                "created_at": op.created_at.isoformat(),
            }
            for op in await _operations(session, domain_id)
        ]
        blocking = next((op["id"] for op in operations if op["status"] in {"applying", "unknown"}), None)
        return {
            "domain_id": domain_id,
            "revision": row.revision if row else 0,
            "ceilings": ceilings,
            "defaults": defaults,
            "enforcement_scope": "afterglow_project_allocations",
            "allocations": allocations,
            "projects": projects,
            "operations": operations,
            "allocation_blocked": blocking is not None,
            "blocking_operation_id": blocking,
            "drift": any(metric["within_budget"] is False for metric in allocations.values()),
            "defaults_future_only": True,
        }


@identity_roles._complete_mutation
async def update_policy(conn, domain_id, revision, values, *, defaults=False, token_info=None):
    values = validate_limits(values)
    async with identity_roles._graph_lock(conn) as lease:
        if token_info is not None:
            context = await domain_iam.context(token_info)
            if context["domain_id"] != domain_id:
                raise HTTPException(403, "quota_domain_mismatch")
        projects = await _call(_directory, conn, domain_id)
        async with _session() as session:
            row = await _policy(session, domain_id, create=True)
            if row.revision != revision:
                raise HTTPException(409, "quota_policy_revision_conflict")
            await _assert_settled(session, domain_id)
            if defaults:
                for key, value in values.items():
                    ceiling = row.ceilings.get(key, -1)
                    if ceiling != -1 and (value == -1 or value > ceiling):
                        raise HTTPException(409, f"quota_default_exceeds_ceiling:{key}")
                row.defaults = values
            else:
                allocations, _ = await _measure(conn, projects, values)
                _check_budget(values, allocations)
                for key, value in row.defaults.items():
                    if values.get(key, -1) != -1 and (value == -1 or value > values[key]):
                        raise HTTPException(409, f"quota_default_exceeds_ceiling:{key}")
                row.ceilings = values
            row.revision += 1
            row.updated_at = datetime.now(UTC)
            await _commit(session, lease)
        return await snapshot(conn, domain_id)


@asynccontextmanager
async def manager_connection(token_info):
    context = await domain_iam.context(token_info)
    conn = await _call(keystone.get_admin_project_connection)
    try:
        yield conn, context["domain_id"]
    finally:
        await _call(conn.close)


@identity_roles._complete_mutation
async def reconcile_operation(conn, domain_id, operation_id):
    """Admin has confirmed the original native calls are no longer in flight.

    This accepts current measured limits, not the original requested outcome.
    Drift remains visible and future growth remains budget-checked. No provider
    write or automatic replay is performed by recovery.
    """
    async with identity_roles._graph_lock(conn) as lease:
        projects = await _call(_directory, conn, domain_id)
        async with _session() as session:
            operation = (
                await session.execute(
                    select(DomainQuotaOperation)
                    .where(DomainQuotaOperation.id == operation_id, DomainQuotaOperation.domain_id == domain_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if operation is None:
                raise HTTPException(404, "quota_operation_not_found")
            deleted = False
            try:
                native_domain = await project_domain(conn, operation.project_id)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                # Creation compensation may remove a disabled project after
                # defaults fail. Prove both native GET absence and directory
                # absence; do not strand that domain's durable safety fence.
                if any(project["id"] == operation.project_id for project in projects):
                    raise public_service_error(503, "quota_project_directory_unverified") from exc
                deleted = True
            else:
                if native_domain != domain_id:
                    raise HTTPException(403, "quota_project_domain_mismatch")
            sections = {}
            for section, state in operation.sections.items():
                if deleted:
                    sections[section] = {"status": "project_deleted"}
                    continue
                if state["status"] == "pending":
                    sections[section] = {"status": "not_attempted"}
                    continue
                try:
                    entries = await _call(quota_native.get_section, conn, operation.project_id, section)
                    observed = {key: entries[key]["limit"] for key in _section_values(section, operation.requested)}
                except Exception as exc:
                    raise public_service_error(503, "quota_native_readback_unavailable") from exc
                sections[section] = {"status": "observed", "observed": observed}
            operation.sections = sections
            operation.status = "reconciled"
            operation.updated_at = datetime.now(UTC)
            await _commit(session, lease)
            await _invalidate(operation.project_id)
        return await snapshot(conn, domain_id)
