"""Fail-closed policy fences for every Afterglow schedule writer.

The native identity graph lease serializes policy, grants and review; the usage
lease serializes Nova lifecycle metadata. SQL intent commits precede native
mutation. Applying/uncertain intents are deliberately never replayed.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app import database
from app.models.instance_usage import UsageScheduleUpdate, aware_timestamp
from app.models.instance_usage_governance import InstanceUsageExtensionRequest as Extension
from app.models.instance_usage_governance import InstanceUsagePolicy as Policy
from app.services import domain_projects, domain_scope, identity_roles, keystone, project_service
from app.services import instance_usage as usage

DEFAULT_REVISION = "0" * 32
WRITE_ROLES = {"admin", "manager", "member", "project_owner", "project_admin", "project_member"}
REVIEW_ROLES = {"admin", "project_owner", "project_admin"}


@asynccontextmanager
async def session_scope():
    factory = database.get_session_factory()
    if factory is None or not database.is_db_available():
        raise HTTPException(503, "Usage extension policy storage is unavailable")
    try:
        async with factory() as session:
            yield session
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            503, "Usage extension policy storage is unavailable; do not retry an uncertain write"
        ) from exc


async def _commit_request(session):
    try:
        await session.commit()
    except StaleDataError as exc:
        await session.rollback()
        raise HTTPException(409, "Usage extension request changed; reload and reconcile before retrying") from exc


async def cloud_id(conn):
    return hashlib.sha256((await usage._cloud_scope(conn)).encode()).hexdigest()


async def project_domain(project_id):
    ks = await project_service._provider_call(keystone._get_admin_ks_client)
    project = await project_service._provider_call(ks.projects.get, project_id)
    did = identity_roles._field(project, "domain_id")
    if identity_roles._field(project, "id") != project_id or not isinstance(did, str) or not did:
        raise HTTPException(503, "Native project domain cannot be verified")
    await project_service._provider_call(domain_scope.assert_project_domain, did, project_id)
    resolved = await project_service._provider_call(domain_scope.resolve_domain, did)
    domain_scope.assert_domain_resource(did, resolved["id"])
    return did


async def live_access(user_id, domain_id, project_id=None):
    # Native identity and effective assignments, never session role/name flags.
    await project_service._provider_call(keystone.get_identity_user, user_id)
    domain = await project_service._provider_call(domain_scope.resolve_domain, domain_id)
    domain_scope.assert_domain_resource(domain_id, domain["id"])
    manager = await project_service._provider_call(domain_projects.has_manager, user_id, domain_id)
    roles = set()
    if project_id:
        domain_scope.assert_domain_resource(domain_id, await project_domain(project_id))
        roles = {row["name"] for row in await project_service.get_project_delegation_roles(project_id, user_id)}
        if roles and not manager:
            await project_service._provider_call(domain_projects.assert_project_membership, user_id, project_id)
    return {
        "manager": manager,
        "write": bool(roles & WRITE_ROLES),
        "review": manager or bool(roles & REVIEW_ROLES),
        "read": bool(roles),
    }


async def policy_row(session, cloud, domain):
    return await session.get(Policy, (cloud, domain), populate_existing=True)


def policy_dto(row, domain_id, can_manage):
    return {
        "domain_id": domain_id,
        "review_required": bool(row and row.review_required),
        "revision": row.revision if row else DEFAULT_REVISION,
        "can_manage": can_manage,
    }


def request_dto(row, can_review=False):
    result = {
        key: getattr(row, key)
        for key in (
            "id",
            "domain_id",
            "project_id",
            "instance_id",
            "instance_name",
            "requested_by",
            "requested_at",
            "expires_at",
            "reason",
            "schedule_revision",
            "policy_revision",
            "revision",
            "status",
            "reviewed_by",
            "reviewed_at",
        )
    }
    for key in ("requested_at", "expires_at", "reviewed_at"):
        value = result[key]
        if value is not None:
            result[key] = (value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)).isoformat()
    result["can_review"] = can_review and row.status == "pending"
    return result


@asynccontextmanager
async def governance_lock():
    conn = await project_service._provider_call(keystone.get_admin_project_connection)
    try:
        async with identity_roles._graph_lock(conn, wait=True) as lease:
            yield lease
    finally:
        await usage.sdk_call(conn.close)


def require_working_domain(token_info, target_domain):
    domain_scope.assert_domain_resource(token_info.get("domain_id"), target_domain)


async def selected_scope(conn, token_info, *, domain_id=None, project_id=None):
    selected = getattr(conn, "_afterglow_project_id", None)
    if domain_id is not None:
        if project_id is not None:
            raise HTTPException(422, "Choose a domain or project scope, not both")
        require_working_domain(token_info, domain_id)
        access = await live_access(token_info["user_id"], domain_id)
        if not access["manager"]:
            raise HTTPException(403, "Exact domain manager authority is required")
        return domain_id, None, access
    target = project_id or selected
    if not target:
        raise HTTPException(403, "An exact project is required")
    domain = await project_domain(target)
    require_working_domain(token_info, domain)
    access = await live_access(token_info["user_id"], domain, target)
    if not access["read"] and not access["manager"]:
        # Global operational administrators may inspect target policy but cannot
        # edit it or decide requests without native scoped review authority.
        system = await project_service._provider_call(domain_scope.has_scope_authority, token_info["user_id"])
        if not system:
            raise HTTPException(403, "Native project membership is required")
    return domain, target, access


async def get_policy(conn, token_info, *, domain_id=None, project_id=None):
    domain, _, access = await selected_scope(conn, token_info, domain_id=domain_id, project_id=project_id)
    async with session_scope() as session:
        return policy_dto(await policy_row(session, await cloud_id(conn), domain), domain, access["manager"])


async def set_policy(conn, token_info, req, *, domain_id=None, project_id=None):
    async with governance_lock() as lease:
        domain, _, access = await selected_scope(conn, token_info, domain_id=domain_id, project_id=project_id)
        if not access["manager"]:
            raise HTTPException(403, "Exact domain manager authority is required")
        async with session_scope() as session:
            cloud = await cloud_id(conn)
            row = await policy_row(session, cloud, domain)
            if req.revision != (row.revision if row else DEFAULT_REVISION):
                raise HTTPException(409, "Usage extension policy changed; reload")
            values = {
                "review_required": req.review_required,
                "revision": secrets.token_hex(16),
                "updated_by": token_info["user_id"],
                "updated_at": datetime.now(UTC),
            }
            await lease.assert_owned()
            try:
                if row is None:
                    # The composite primary key fences racing default-row
                    # insertions even when the Redis owner has expired.
                    session.add(Policy(cloud_id=cloud, domain_id=domain, **values))
                else:
                    changed = await session.execute(
                        update(Policy)
                        .where(
                            Policy.cloud_id == cloud,
                            Policy.domain_id == domain,
                            Policy.revision == req.revision,
                        )
                        .values(**values)
                        .execution_options(synchronize_session=False)
                    )
                    if changed.rowcount != 1:
                        await session.rollback()
                        raise HTTPException(409, "Usage extension policy changed; reload")
                await lease.assert_owned()
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise HTTPException(409, "Usage extension policy changed; reload") from exc
            return {
                "domain_id": domain,
                "review_required": values["review_required"],
                "revision": values["revision"],
                "can_manage": True,
            }


async def unresolved(session, cloud, project, instance):
    return (
        (
            await session.execute(
                select(Extension).where(
                    Extension.cloud_id == cloud,
                    Extension.project_id == project,
                    Extension.instance_id == instance,
                    Extension.status.in_(["applying", "uncertain"]),
                )
            )
        )
        .scalars()
        .first()
    )


class _GovernedUsageLease:
    """Carry both ownership fences through Nova's final pre-dispatch read."""

    def __init__(self, usage_lease, graph_lease):
        self._usage = usage_lease
        self._graph = graph_lease
        self.project_id = usage_lease.project_id
        self.instance_id = usage_lease.instance_id
        self.cloud = usage_lease.cloud

    async def current(self):
        if not await self._usage.current():
            return False
        await self._graph.assert_owned()
        return True


async def change_schedule(conn, server, request, token_info, *, extension_only=False):
    project = usage.require_server_scope(conn, server)
    instance = identity_roles._field(server, "id")
    update = (
        UsageScheduleUpdate(expires_at=request.expires_at, reason=request.reason, revision=request.revision)
        if extension_only
        else request
    )
    async with governance_lock() as graph:
        domain = await project_domain(project)
        async with usage.usage_lease(conn, project, instance) as lease:
            if lease is None:
                raise HTTPException(409, "Usage schedule is busy or coordination is unavailable")
            fresh = await usage.sdk_call(usage.safe_compute_proxy(conn).get_server, instance)
            usage.require_server_scope(conn, fresh, instance)
            schedule = usage.parse_schedule(fresh)
            expiry = usage.validate_schedule_update(schedule, update, extension_only=extension_only)
            async with session_scope() as session:
                cloud = await cloud_id(conn)
                row = await policy_row(session, cloud, domain)
                if await unresolved(session, cloud, project, instance):
                    raise HTTPException(409, "An uncertain extension requires explicit operator reconciliation")
                extending = expiry > aware_timestamp(schedule.expires_at)
                if extending and row is not None and row.review_required:
                    access = await live_access(token_info["user_id"], domain, project)
                    if not access["write"]:
                        raise HTTPException(403, "Native project write authority is required to request an extension")
                    # A pending request changes only expiry. Never silently bundle
                    # destructive action/volume consent changes into approval.
                    if (
                        "expiry_action" in update.model_fields_set and update.expiry_action != schedule.expiry_action
                    ) or (
                        "delete_volumes" in update.model_fields_set and update.delete_volumes != schedule.delete_volumes
                    ):
                        raise HTTPException(422, "Save expiry action changes separately before requesting an extension")
                    pending = (
                        (
                            await session.execute(
                                select(Extension).where(
                                    Extension.cloud_id == cloud,
                                    Extension.project_id == project,
                                    Extension.instance_id == instance,
                                    Extension.status == "pending",
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    for previous in pending:
                        if previous.schedule_revision == schedule.revision and previous.policy_revision == row.revision:
                            raise HTTPException(409, "An extension request is already pending for this schedule")
                        previous.status = "stale"
                        previous.revision = secrets.token_hex(16)
                    intent = Extension(
                        id=secrets.token_hex(16),
                        cloud_id=cloud,
                        domain_id=domain,
                        project_id=project,
                        instance_id=instance,
                        instance_name=identity_roles._field(fresh, "name"),
                        requested_by=token_info["user_id"],
                        requested_at=datetime.now(UTC),
                        expires_at=expiry,
                        reason=update.reason,
                        schedule_revision=schedule.revision,
                        policy_revision=row.revision,
                        revision=secrets.token_hex(16),
                        status="pending",
                    )
                    session.add(intent)
                    await graph.assert_owned()
                    await usage._assert_lease(conn, fresh, lease)
                    await _commit_request(session)
                    return {
                        "status": "pending",
                        "request": request_dto(intent, access["review"]),
                        "schedule": schedule.model_dump(),
                    }
                intent = None
                if extending:
                    intent = Extension(
                        id=secrets.token_hex(16),
                        cloud_id=cloud,
                        domain_id=domain,
                        project_id=project,
                        instance_id=instance,
                        instance_name=identity_roles._field(fresh, "name"),
                        requested_by=token_info["user_id"],
                        requested_at=datetime.now(UTC),
                        expires_at=expiry,
                        reason=update.reason,
                        schedule_revision=schedule.revision,
                        policy_revision=row.revision if row else DEFAULT_REVISION,
                        revision=secrets.token_hex(16),
                        status="applying",
                    )
                    session.add(intent)
                    await graph.assert_owned()
                    await usage._assert_lease(conn, fresh, lease)
                    await _commit_request(session)
                try:
                    await graph.assert_owned()
                    result = await usage._update_locked(
                        conn,
                        fresh,
                        update,
                        user_id=token_info["user_id"],
                        now=None,
                        lease=_GovernedUsageLease(lease, graph),
                        extension_only=extension_only,
                    )
                except Exception:
                    if intent is not None:
                        intent.status, intent.revision = "uncertain", secrets.token_hex(16)
                        await _commit_request(session)
                    raise
                if intent is not None:
                    intent.status, intent.revision = "approved", secrets.token_hex(16)
                    intent.applied_schedule = result.model_dump()
                    await graph.assert_owned()
                    await _commit_request(session)
                return result


def _queue_cursor(row):
    stamp = row.requested_at
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    payload = [0 if row.status == "pending" else 1, stamp.isoformat(), row.id]
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")


def _read_cursor(value):
    try:
        if not isinstance(value, str) or not value or len(value) > 512:
            raise ValueError("Invalid cursor")
        payload = json.loads(base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True))
        if (
            not isinstance(payload, list)
            or len(payload) != 3
            or type(payload[0]) is not int
            or payload[0] not in {0, 1}
            or not isinstance(payload[2], str)
            or not re.fullmatch(r"[0-9a-f]{32}", payload[2])
        ):
            raise ValueError("Invalid cursor")
        return payload[0], aware_timestamp(payload[1]), payload[2]
    except (ValueError, TypeError, binascii.Error) as exc:
        raise HTTPException(422, "Invalid usage extension queue cursor") from exc


async def list_requests(conn, token_info, *, domain_id=None, project_id=None, limit=50, cursor=None):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise HTTPException(422, "Usage extension queue limit must be between 1 and 100")
    domain, project, access = await selected_scope(conn, token_info, domain_id=domain_id, project_id=project_id)
    rank = case((Extension.status == "pending", 0), else_=1)
    async with session_scope() as session:
        query = select(Extension).where(Extension.cloud_id == await cloud_id(conn), Extension.domain_id == domain)
        if project:
            query = query.where(Extension.project_id == project)
        if cursor is not None:
            previous_rank, stamp, identifier = _read_cursor(cursor)
            query = query.where(
                or_(
                    rank > previous_rank,
                    and_(rank == previous_rank, Extension.requested_at < stamp),
                    and_(rank == previous_rank, Extension.requested_at == stamp, Extension.id < identifier),
                )
            )
        rows = (
            (
                await session.execute(
                    query.order_by(rank.asc(), Extension.requested_at.desc(), Extension.id.desc()).limit(limit + 1)
                )
            )
            .scalars()
            .all()
        )
        page = rows[:limit]
        return {
            "items": [request_dto(row, access["review"]) for row in page],
            "next_cursor": _queue_cursor(page[-1]) if len(rows) > limit else None,
        }


async def review_request(conn, token_info, request_id, req):
    async with governance_lock() as graph, session_scope() as session:
        row = await session.get(Extension, request_id, populate_existing=True)
        if row is None or row.cloud_id != await cloud_id(conn):
            raise HTTPException(404, "Extension request not found")
        require_working_domain(token_info, row.domain_id)
        access = await live_access(token_info["user_id"], row.domain_id, row.project_id)
        if not access["review"]:
            raise HTTPException(403, "Exact domain manager or project administrator authority is required")
        if row.revision != req.revision or row.status != "pending":
            raise HTTPException(409, "Extension request changed or is not pending")
        policy = await policy_row(session, row.cloud_id, row.domain_id)
        if policy is None or not policy.review_required or policy.revision != row.policy_revision:
            row.status, row.revision = "stale", secrets.token_hex(16)
            await _commit_request(session)
            raise HTTPException(409, "Extension policy changed; submit a new request")
        if req.decision == "reject":
            row.status, row.revision = "rejected", secrets.token_hex(16)
            row.reviewed_by, row.reviewed_at = token_info["user_id"], datetime.now(UTC)
            await graph.assert_owned()
            await _commit_request(session)
            return request_dto(row)
        requester = await live_access(row.requested_by, row.domain_id, row.project_id)
        if not requester["write"]:
            raise HTTPException(403, "The requester no longer has native project write authority")

        target = await usage.sdk_call(keystone.get_admin_project_connection)
        try:
            await usage.sdk_call(usage.bind_operator_scope, target, row.project_id)
            if await cloud_id(target) != row.cloud_id:
                raise HTTPException(503, "Native review executor cloud does not match the request")
            async with usage.usage_lease(target, row.project_id, row.instance_id) as lease:
                if lease is None:
                    raise HTTPException(409, "Usage schedule is busy or coordination is unavailable")
                fresh = await usage.sdk_call(usage.safe_compute_proxy(target).get_server, row.instance_id)
                usage.require_server_scope(target, fresh, row.instance_id)
                update = UsageScheduleUpdate(
                    expires_at=aware_timestamp(
                        row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at
                    ),
                    reason=row.reason,
                    revision=row.schedule_revision,
                )
                try:
                    usage.validate_schedule_update(usage.parse_schedule(fresh), update, extension_only=True)
                except HTTPException:
                    row.status, row.revision = "stale", secrets.token_hex(16)
                    await _commit_request(session)
                    raise
                # This durable non-replayable state survives cancellation,
                # process death, lost Nova responses, and SQL finalization loss.
                row.status, row.revision = "applying", secrets.token_hex(16)
                row.reviewed_by, row.reviewed_at = token_info["user_id"], datetime.now(UTC)
                await graph.assert_owned()
                await usage._assert_lease(target, fresh, lease)
                await _commit_request(session)
                try:
                    await graph.assert_owned()
                    result = await usage._update_locked(
                        target,
                        fresh,
                        update,
                        user_id=row.requested_by,
                        now=None,
                        lease=_GovernedUsageLease(lease, graph),
                        extension_only=True,
                    )
                except Exception:
                    row.status, row.revision = "uncertain", secrets.token_hex(16)
                    await _commit_request(session)
                    raise
                row.status, row.revision = "approved", secrets.token_hex(16)
                row.applied_schedule = result.model_dump()
                await graph.assert_owned()
                await _commit_request(session)
                return request_dto(row)
        finally:
            await usage.sdk_call(target.close)
