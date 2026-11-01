"""SQL-backed manual GPU quota review; no native policy writers live here."""

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from keystoneauth1.exceptions.http import Unauthorized
from sqlalchemy import and_, or_, select, update

from app.database import get_session_factory, is_db_available
from app.models.compute_pools import IDENTIFIER_PATTERN, MAX_AMOUNT
from app.models.gpu_quota_requests import GpuQuotaRequest
from app.services import compute_pools, domain_iam, flavor_automation_policy, identity_roles, keystone, session_store
from app.services.native_operation import NativeOperation

PAGE_SIZE = 50
_STORAGE_TIMEOUT_SECONDS = 15
_FIELDS = (
    "id",
    "domain_id",
    "project_id",
    "requester_id",
    "gpu_profile_name",
    "resource_class",
    "additional",
    "baseline_limit",
    "target_limit",
    "pool_revision",
    "reason",
    "status",
    "created_at",
    "reviewer_id",
    "reviewed_at",
    "note",
)


def _factory():
    factory = get_session_factory()
    if factory is None or not is_db_available():
        raise HTTPException(503, "gpu_quota_request_storage_unavailable")
    return factory


@asynccontextmanager
async def _storage():
    try:
        async with asyncio.timeout(_STORAGE_TIMEOUT_SECONDS), _factory()() as session:
            yield session
    except HTTPException:
        raise
    except Exception as exc:
        # Schema failure, transport failure and ambiguous commit are never an
        # empty queue or a successful decision. Do not expose DB/native secrets.
        raise HTTPException(503, "gpu_quota_request_storage_unavailable") from exc


def _utc(value):
    if value is None:
        return None
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)).isoformat()


def _dto(row):
    result = {field: getattr(row, field) for field in _FIELDS}
    for field in ("created_at", "reviewed_at"):
        result[field] = _utc(result[field])
    return result


async def _session_signature(info):
    if not info.get("refresh_jti"):
        return None
    try:
        session = await session_store.get_session(info["refresh_jti"])
        if (
            not session
            or session.get("blacklisted")
            or session.get("user_id") != info.get("user_id")
            or session.get("domain_id") != info.get("domain_id")
            or (session.get("identity_domain_id") or session.get("domain_id")) != info.get("identity_domain_id")
            or not isinstance(session.get("keystone_token"), str)
            or not session["keystone_token"].strip()
        ):
            raise HTTPException(401, "gpu_quota_request_session_changed")
        # The root proof is renewed in place; only identity/scope fields fence this operation.
        return tuple(
            session.get(key)
            for key in (
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
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "gpu_quota_request_session_unavailable") from exc


async def _check_session(info, signature):
    if await _session_signature(info) != signature:
        raise HTTPException(401, "gpu_quota_request_session_changed")


async def _live_session(info):
    """Fence a rotated/deleted login family and revalidate its native subject."""
    try:
        signature = await _session_signature(info)
        project_id = info.get("connection_project_id", info.get("project_id", ""))
        async with NativeOperation() as operation:
            native = await operation.run(
                keystone.validate_token, info["token"], project_id=project_id, operation=operation
            )
        if (
            native.get("user_id") != info.get("user_id")
            or native.get("identity_domain_id") != info.get("identity_domain_id")
            or native.get("project_id", "") != project_id
        ):
            raise HTTPException(403, "gpu_quota_request_session_mismatch")
        return signature
    except Unauthorized as exc:
        raise HTTPException(401, "gpu_quota_request_session_invalid") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "gpu_quota_request_session_unavailable") from exc


async def _authorize(info, *, system, domain_id=None):
    signature = await _live_session(info)
    if system:
        from app.api.deps import require_admin

        await require_admin(dict(info))
    else:
        context = await domain_iam.context(dict(info))
        if not domain_id or info.get("domain_id") != domain_id or context.get("domain_id") != domain_id:
            raise HTTPException(403, "gpu_quota_request_domain_mismatch")
    for field in ("user_id", "domain_id", "identity_domain_id"):
        if not isinstance(info.get(field), str) or not IDENTIFIER_PATTERN.fullmatch(info[field]):
            raise HTTPException(403, "gpu_quota_request_identity_invalid")
    return signature


async def _reauthorize(info, signature, *, system, domain_id=None):
    if await _authorize(info, system=system, domain_id=domain_id) != signature:
        raise HTTPException(401, "gpu_quota_request_session_changed")


def _profile(capabilities, resource_class, *, name=None, fingerprint=None):
    if capabilities.get("policy_ready") is not True:
        raise HTTPException(503, "gpu_quota_request_policy_unavailable")
    profiles = [
        profile
        for profile in capabilities.get("gpu_profiles", [])
        if (profile.get("enabled") is True and profile.get("resource_class") == resource_class)
    ]
    if len(profiles) != 1 or (name is not None and profiles[0].get("name") != name):
        raise HTTPException(409, "gpu_quota_request_profile_changed")
    profile = profiles[0]
    # Display labels are not identity. Preserve the actual approved attachment
    # contract so a deleted/replaced profile cannot fulfill an older request.
    evidence = {
        key: profile[key]
        for key in (
            "name",
            "resource_class",
            "resource_requirements",
            "extra_specs",
            "alias_resource_classes",
        )
    }
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if fingerprint is not None and digest != fingerprint:
        raise HTTPException(409, "gpu_quota_request_profile_changed")
    return profile, digest


async def _capabilities():
    try:
        async with asyncio.timeout(_STORAGE_TIMEOUT_SECONDS):
            return await flavor_automation_policy.capabilities()
    except TimeoutError as exc:
        raise HTTPException(503, "gpu_quota_request_policy_unavailable") from exc


async def _target(client, domain_id, project_id, resource_class, *, name=None, fingerprint=None, creating=False):
    project = await asyncio.to_thread(client.exact, "projects", project_id, missing_ok=True)
    if project is None or project.get("enabled") is not True:
        raise HTTPException(409, "gpu_quota_request_project_unavailable")
    if project.get("domain_id") != domain_id:
        raise HTTPException(403 if creating else 409, "gpu_quota_request_project_domain_mismatch")
    capabilities = await _capabilities()
    profile, digest = _profile(capabilities, resource_class, name=name, fingerprint=fingerprint)
    domain = await asyncio.to_thread(client.exact, "domains", domain_id)
    policy = compute_pools.parse_domain_policy(domain)
    snapshot = await compute_pools._snapshot(client, domain_id, capabilities, project_id=project_id)
    if not creating and (snapshot.get("state") != "active" or snapshot.get("enabled") is not True):
        raise HTTPException(409, "gpu_quota_request_pool_inactive")
    if snapshot.get("policy_ready") is not True:
        raise HTTPException(503, "gpu_quota_request_policy_unavailable")
    if not any(project["id"] == project_id and project["enabled"] is True for project in snapshot["projects"]):
        raise HTTPException(409, "gpu_quota_request_project_unavailable")
    if (
        snapshot["revision"] != policy["revision"]
        or snapshot["limits"] != policy["limits"]
        or snapshot["project_limits"] != policy["project_limits"].get(project_id, {})
    ):
        raise HTTPException(409, "gpu_quota_request_pool_changed")
    snapshot["_queue_policy"] = policy
    domain_limit = snapshot["limits"].get(resource_class, 0)
    effective = snapshot["project_limits"].get(resource_class, domain_limit)
    return snapshot, profile, digest, domain_limit, effective


def _policy(snapshot):
    return snapshot["_queue_policy"]


async def _fence(client, domain_id, project_id, resource_class, snapshot, name, digest, *, creating=False):
    """Fresh exact policy/project/approval just before the short SQL transaction."""
    await _target_identity(client, domain_id, project_id, creating=creating)
    domain = await asyncio.to_thread(client.exact, "domains", domain_id)
    if domain["enabled"] is not True or compute_pools.parse_domain_policy(domain) != _policy(snapshot):
        raise HTTPException(409, "gpu_quota_request_pool_changed")
    _profile(await _capabilities(), resource_class, name=name, fingerprint=digest)


async def _target_identity(client, domain_id, project_id, *, creating=False):
    project = await asyncio.to_thread(client.exact, "projects", project_id, missing_ok=True)
    if project is None or project.get("enabled") is not True:
        raise HTTPException(409, "gpu_quota_request_project_unavailable")
    if project.get("domain_id") != domain_id:
        raise HTTPException(403 if creating else 409, "gpu_quota_request_project_domain_mismatch")


@identity_roles._complete_mutation
async def create(info, request):
    domain_id = info.get("domain_id")
    _factory()  # No native observations or fake success when persistence is absent.
    try:
        async with compute_pools._operator() as operator, identity_roles._graph_lock(operator) as lease:
            signature = await _authorize(info, system=False, domain_id=domain_id)
            client = compute_pools._Native(operator)
            snapshot, profile, digest, _, baseline = await _target(
                client, domain_id, request.project_id, request.resource_class, creating=True
            )
            if baseline == -1:
                raise HTTPException(409, "gpu_quota_request_already_unlimited")
            if baseline < 0 or baseline > MAX_AMOUNT - request.additional:
                raise HTTPException(409, "gpu_quota_request_target_overflow")
            row = GpuQuotaRequest(
                id=uuid4().hex,
                domain_id=domain_id,
                project_id=request.project_id,
                requester_id=info["user_id"],
                gpu_profile_name=profile["name"],
                resource_class=request.resource_class,
                gpu_profile_fingerprint=digest,
                additional=request.additional,
                baseline_limit=baseline,
                target_limit=baseline + request.additional,
                pool_revision=snapshot["revision"],
                reason=request.reason,
                status="pending",
                note="",
                created_at=datetime.now(UTC),
                reviewer_id=None,
                reviewed_at=None,
            )
            await _reauthorize(info, signature, system=False, domain_id=domain_id)
            await _fence(
                client,
                domain_id,
                row.project_id,
                row.resource_class,
                snapshot,
                row.gpu_profile_name,
                digest,
                creating=True,
            )
            await _reauthorize(info, signature, system=False, domain_id=domain_id)
            await lease.assert_owned()
            async with _storage() as session:
                session.add(row)
                await session.flush()
                try:
                    await lease.assert_owned()
                    await _check_session(info, signature)
                    await lease.assert_owned()
                except Exception:
                    await session.rollback()
                    raise
                # Capture before commit: ordinary async factories may expire ORM attributes.
                result = _dto(row)
                await session.commit()
            return result
    except compute_pools.ComputePoolUnavailable as exc:
        raise HTTPException(503, "gpu_quota_request_native_unavailable") from exc


async def list_requests(info, *, system=False, status="pending", cursor=None):
    domain_id = None if system else info.get("domain_id")
    signature = await _authorize(info, system=system, domain_id=domain_id)
    scope_filters = [] if system else [GpuQuotaRequest.domain_id == domain_id]
    filters = list(scope_filters)
    if status != "all":
        filters.append(GpuQuotaRequest.status == status)
    async with _storage() as session:
        if cursor:
            anchor = (
                await session.execute(
                    select(GpuQuotaRequest).where(
                        GpuQuotaRequest.id == cursor,
                        *scope_filters,
                    )
                )
            ).scalar_one_or_none()
            if anchor is None:
                raise HTTPException(400, "gpu_quota_request_cursor_invalid")
            filters.append(
                or_(
                    GpuQuotaRequest.created_at < anchor.created_at,
                    and_(GpuQuotaRequest.created_at == anchor.created_at, GpuQuotaRequest.id < anchor.id),
                )
            )
        rows = (
            (
                await session.execute(
                    select(GpuQuotaRequest)
                    .where(*filters)
                    .order_by(
                        GpuQuotaRequest.created_at.desc(),
                        GpuQuotaRequest.id.desc(),
                    )
                    .limit(PAGE_SIZE + 1)
                )
            )
            .scalars()
            .all()
        )
        result = {
            "items": [_dto(row) for row in rows[:PAGE_SIZE]],
            "next_cursor": rows[PAGE_SIZE - 1].id if len(rows) > PAGE_SIZE else None,
        }
    await _reauthorize(info, signature, system=system, domain_id=domain_id)
    return result


def _decided(row, status):
    if row.status == "pending":
        return None
    if row.status != status:
        raise HTTPException(409, "gpu_quota_request_already_decided")
    return _dto(row)


@identity_roles._complete_mutation
async def resolve(info, request_id, request):
    _factory()
    try:
        async with compute_pools._operator() as operator, identity_roles._graph_lock(operator) as lease:
            signature = await _authorize(info, system=True)
            async with _storage() as session:
                row = await session.get(GpuQuotaRequest, request_id)
                if row is None:
                    raise HTTPException(404, "gpu_quota_request_not_found")
                existing = _decided(row, request.status)
                if existing is None:
                    # Detached immutable target; no SQL connection held across native waits.
                    session.expunge_all()
            if existing is not None:
                await _reauthorize(info, signature, system=True)
                return existing
            if request.status == "fulfilled":
                client = compute_pools._Native(operator)
                snapshot, _, digest, domain_limit, effective = await _target(
                    client,
                    row.domain_id,
                    row.project_id,
                    row.resource_class,
                    name=row.gpu_profile_name,
                    fingerprint=row.gpu_profile_fingerprint,
                )
                if any(value != -1 and value < row.target_limit for value in (domain_limit, effective)):
                    raise HTTPException(409, "gpu_quota_request_target_not_met")
                await _reauthorize(info, signature, system=True)
                await _fence(
                    client, row.domain_id, row.project_id, row.resource_class, snapshot, row.gpu_profile_name, digest
                )
                await _reauthorize(info, signature, system=True)
            else:
                await _reauthorize(info, signature, system=True)
            await lease.assert_owned()
            reviewed_at = datetime.now(UTC)
            async with _storage() as session:
                result = await session.execute(
                    update(GpuQuotaRequest)
                    .where(
                        GpuQuotaRequest.id == request_id,
                        GpuQuotaRequest.status == "pending",
                        GpuQuotaRequest.domain_id == row.domain_id,
                        GpuQuotaRequest.project_id == row.project_id,
                        GpuQuotaRequest.resource_class == row.resource_class,
                        GpuQuotaRequest.gpu_profile_fingerprint == row.gpu_profile_fingerprint,
                        GpuQuotaRequest.target_limit == row.target_limit,
                    )
                    .values(
                        status=request.status, reviewer_id=info["user_id"], reviewed_at=reviewed_at, note=request.note
                    )
                )
                try:
                    await lease.assert_owned()
                    await _check_session(info, signature)
                    await lease.assert_owned()
                except Exception:
                    await session.rollback()
                    raise
                if result.rowcount != 1:
                    await session.rollback()
                    winner = await session.get(GpuQuotaRequest, request_id)
                    if winner is None:
                        raise HTTPException(409, "gpu_quota_request_changed")
                    existing = _decided(winner, request.status)
                    if existing is None:
                        raise HTTPException(409, "gpu_quota_request_changed")
                else:
                    await session.commit()
            if existing is not None:
                await _reauthorize(info, signature, system=True)
                return existing
            result = _dto(row)
            result.update(
                status=request.status, reviewer_id=info["user_id"], reviewed_at=_utc(reviewed_at), note=request.note
            )
            return result
    except compute_pools.ComputePoolUnavailable as exc:
        raise HTTPException(503, "gpu_quota_request_native_unavailable") from exc
