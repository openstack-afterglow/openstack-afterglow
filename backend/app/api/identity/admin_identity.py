"""관리자 Identity 관리 엔드포인트 (사용자, 프로젝트, 쿼터, 그룹, 역할)."""

from __future__ import annotations

from copy import copy
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    import openstack
import asyncio
import logging

from anyio import CancelScope
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common.errors import public_service_error
from app.api.deps import CacheMode, cache_mode, get_admin_os_conn, get_token_info, require_admin
from app.database import get_session
from app.services import (
    account_identity,
    account_spaces,
    activity,
    domain_iam,
    domain_projects,
    domain_quotas,
    identity_roles,
    keystone,
    project_cleanup,
    project_ownership_journal,
    project_service,
    quota_native,
    session_store,
)
from app.services import login_guard as _login_guard
from app.services.cache import cached_call, invalidate, ttl_slow
from app.services.domain_scope import invalidate_authority
from app.services.project_deletion import inspect_project_resources
from app.services.service_permissions import normalize_role_name, preset_preview

_logger = logging.getLogger(__name__)

router = APIRouter()


def _identity_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    if status in (401, 403):
        return HTTPException(403, "identity_native_denied")
    if status == 404:
        return HTTPException(404, "identity_not_found")
    if status in (400, 409, 422):
        return HTTPException(status, "identity_native_invalid")
    return public_service_error(503, "identity_unavailable")


def _selected_domain(conn, domain_id: str):
    try:
        domain = conn.identity.get_domain(domain_id)
        if domain is None:
            raise HTTPException(404, "identity_domain_not_found")
        if getattr(domain, "id", None) != domain_id:
            raise public_service_error(503, "identity_domain_unverified")
        return domain
    except Exception as exc:
        raise _identity_error(exc) from exc


def _domain_object(conn, domain_id: str, kind: str, object_id: str):
    try:
        obj = getattr(conn.identity, f"get_{kind}")(object_id)
        if obj is None:
            raise HTTPException(404, "identity_not_found")
        if getattr(obj, "id", None) != object_id:
            raise public_service_error(503, "identity_object_unverified")
        if getattr(obj, "domain_id", None) != domain_id:
            raise HTTPException(403, "identity_domain_mismatch")
        return obj
    except Exception as exc:
        raise _identity_error(exc) from exc


async def _selected_objects(
    request: Request,
    domain_id: str | None = Query(None, min_length=1),
    conn=Depends(get_admin_os_conn),
):
    """Fresh native boundaries before any object read, mutation or cache lookup.

    Both these checks and the handler use the verified fixed admin-project
    executor; the caller's Personal member transport cannot read this directory.

    Single-object credential/profile routes remain identity-domain bound.
    Membership relations anchor the selected domain to the target project/group;
    their exact native user/group principal may belong to another identity domain.
    """
    identifiers = dict(request.path_params)
    if request.url.path.endswith(("/roles/assign", "/roles/assign-group")):
        identifiers.update(dict(request.query_params))
        if request.method == "POST":
            payload = await request.json()
            if isinstance(payload, dict):
                identifiers.update(payload)
    objects = {kind: identifiers.get(f"{kind}_id") for kind in ("user", "project", "group")}
    objects = {kind: value for kind, value in objects.items() if isinstance(value, str) and value}
    role_id = identifiers.get("role_id")
    if domain_id is None:
        # Removing a pre-existing cross-domain grant/membership only narrows
        # access, so system-wide cleanup stays possible without a selection.
        if len(objects) < 2 or request.method == "DELETE":
            return
        anchor_kind = "project" if "project" in objects else "group"
        anchor = await asyncio.to_thread(_native_object, conn, anchor_kind, objects[anchor_kind])
        domain_id = getattr(anchor, "domain_id", None)
        if not isinstance(domain_id, str) or not domain_id:
            raise public_service_error(503, "identity_object_unverified")
    else:
        await asyncio.to_thread(_selected_domain, conn, domain_id)
    anchor_kind = "project" if "project" in objects else "group" if "group" in objects else "user"
    for kind, object_id in objects.items():
        if len(objects) >= 2 and kind != anchor_kind:
            await asyncio.to_thread(_native_object, conn, kind, object_id)
        else:
            await asyncio.to_thread(_domain_object, conn, domain_id, kind, object_id)
    if isinstance(role_id, str) and role_id:
        await asyncio.to_thread(_assignable_role, conn, domain_id, role_id)


def _native_object(conn, kind: str, object_id: str):
    try:
        obj = getattr(conn.identity, f"get_{kind}")(object_id)
        if obj is None:
            raise HTTPException(404, "identity_not_found")
        if getattr(obj, "id", None) != object_id:
            raise public_service_error(503, "identity_object_unverified")
        return obj
    except Exception as exc:
        raise _identity_error(exc) from exc


def _assignable_role(conn, domain_id: str, role_id: str):
    """Global roles or roles owned by the selected domain; never another domain's role."""
    try:
        role = conn.identity.get_role(role_id)
        if role is None:
            raise HTTPException(404, "identity_not_found")
        if getattr(role, "id", None) != role_id:
            raise public_service_error(503, "identity_object_unverified")
        if getattr(role, "domain_id", None) not in (None, domain_id):
            raise HTTPException(403, "identity_domain_mismatch")
        return role
    except Exception as exc:
        raise _identity_error(exc) from exc


# ============================================================================
# Users
# ============================================================================


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=1024)
    enabled: bool = True
    domain_id: str = Field(min_length=1)


class UpdateUserRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    enabled: bool | None = None
    password: str | None = None


@router.get("/users", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def list_users(
    limit: int = Query(default=20, ge=1, le=100),
    marker: str | None = Query(default=None),
    domain_id: str = Query(..., min_length=1),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """사용자 목록 (페이지네이션).

    Keystone은 created_at을 제공하지 않으므로 ActivityLog 기반 최초/최근 활동일로 대체한다.
    (per-user Keystone GET 폴백은 항상 None을 반환하는 낭비 왕복이므로 제거됨)
    """

    def _list():

        users = []
        for u in conn.identity.users(domain_id=domain_id):
            if getattr(u, "domain_id", None) != domain_id:
                continue
            users.append(
                {
                    "id": u.id,
                    "name": u.name or "",
                    "email": getattr(u, "email", "") or "",
                    "enabled": u.is_enabled,
                    "domain_id": getattr(u, "domain_id", None),
                    "default_project_id": getattr(u, "default_project_id", None),
                }
            )
        users.sort(key=lambda u: u["id"])
        start = 0
        if marker:
            start = next((i + 1 for i, u in enumerate(users) if u["id"] == marker), None)
            if start is None:
                raise HTTPException(400, "identity_invalid_marker")
        page = users[start : start + limit]
        return {
            "items": page,
            "next_marker": page[-1]["id"] if start + limit < len(users) else None,
            "count": len(page),
        }

    try:
        result = await asyncio.to_thread(_list)
    except Exception as exc:
        raise _identity_error(exc) from exc

    # ActivityLog 기반 최초·최근 활동일 배치 조회 (1쿼리)
    user_ids = [u["id"] for u in result["items"]]
    bounds = await activity.get_user_activity_bounds(user_ids)
    for u in result["items"]:
        b = bounds.get(u["id"], {})
        u["first_seen"] = b.get("first_seen")
        u["last_seen"] = b.get("last_seen")
        # 하위호환: created_at → first_seen 값으로 매핑 (프론트 기존 참조 동작)
        u["created_at"] = u["first_seen"]

    return result


@router.get("/users/stats", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def get_users_stats(
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    domain_id: str = Query(..., min_length=1),
):
    """사용자 현황 집계 통계 (전체/활성/비활성 수). 통계 카드용."""

    def _stats():

        total = enabled = disabled = 0
        for u in conn.identity.users(domain_id=domain_id):
            if getattr(u, "domain_id", None) != domain_id:
                continue
            total += 1
            if u.is_enabled:
                enabled += 1
            else:
                disabled += 1
        return {"total": total, "enabled": enabled, "disabled": disabled}

    try:
        return await asyncio.to_thread(_stats)
    except Exception as exc:
        raise _identity_error(exc) from exc


@router.get("/users/activity", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def get_users_activity(
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(None),
    domain_id: str = Query(..., min_length=1),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """사용자 변경 로그 (생성·수정·삭제, 시간 역순). 변경 로그 카드용."""

    def users():

        return [u.id for u in conn.identity.users(domain_id=domain_id) if getattr(u, "domain_id", None) == domain_id]

    try:
        user_ids = await asyncio.to_thread(users)
    except Exception as exc:
        raise _identity_error(exc) from exc
    return await activity.list_user_management_events(limit=limit, before_id=before_id, user_ids=user_ids)


@router.post("/users", dependencies=[Depends(require_admin)], status_code=201)
async def create_user(
    req: CreateUserRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    token_info: dict = Depends(get_token_info),
    session: AsyncSession = Depends(get_session),
):
    """Create an accounts identity and member-only personal project, without joining the selected domain."""
    await asyncio.to_thread(_selected_domain, conn, req.domain_id)
    result = await domain_iam.create_managed_user(
        req.model_dump(exclude={"domain_id"}), req.domain_id, token_info, session
    )
    await invalidate("afterglow:admin:users:*")
    return result


@router.patch("/users/{user_id}", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def update_user(
    user_id: str,
    req: UpdateUserRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """사용자 수정."""
    email = req.email
    if email is not None:
        from app.services.domain_auth import DomainAuthError, normalize_email

        try:
            email = normalize_email(email)
        except DomainAuthError as exc:
            raise HTTPException(exc.status_code, exc.detail) from exc

    def _update():
        kwargs: dict = {}
        if req.name is not None:
            kwargs["name"] = req.name
        if req.email is not None:
            kwargs["email"] = email
        if req.enabled is not None:
            kwargs["enabled"] = req.enabled
        if req.password is not None:
            kwargs["password"] = req.password
            kwargs["afterglow_local_password"] = True
        try:
            u = conn.identity.update_user(user_id, **kwargs)
            return {
                "id": u.id,
                "name": u.name or "",
                "email": getattr(u, "email", "") or "",
                "enabled": u.is_enabled,
            }
        except Exception as e:
            _logger.warning("User update failed (%s)", type(e).__name__)

            raise _identity_error(e) from e

    try:
        if req.enabled is not None or req.email is not None or req.password is not None:
            # Account status, canonical email and credential writes share one lease.
            async with identity_roles._graph_lock(conn) as lease:
                if email is not None and any(
                    identity_roles._field(user, "id") != user_id
                    for user in await domain_iam._find_accounts(None, email=email)
                ):
                    raise HTTPException(409, "Email belongs to another account")
                try:
                    if req.enabled is False:
                        await project_ownership_journal.assert_user_resolved(user_id)
                        await asyncio.to_thread(identity_roles.assert_system_admin_remains, users={user_id})
                        await asyncio.to_thread(project_service.assert_user_ownership_mutation_safe, user_id)
                    affected = await asyncio.to_thread(
                        domain_projects.assert_managers_remain,
                        user_id=user_id,
                        disabled_user_ids={user_id} if req.enabled is False else (),
                    )
                    await identity_roles._session_ready({user_id})
                except Exception as exc:
                    raise _identity_error(exc) from exc
                succeeded = False
                try:
                    result = await identity_roles._write(lease, _update)
                    succeeded = True
                finally:
                    try:
                        await identity_roles._sync_domain_managers(conn, lease, affected)
                    finally:
                        await identity_roles._applied(
                            None,
                            [],
                            None,
                            {user_id},
                            token_info,
                            "admin_user_update",
                            {"user_id": user_id},
                            status="success" if succeeded else "failed",
                        )
        else:
            result = await asyncio.to_thread(_update)
        await invalidate_authority()
        return result
    except HTTPException:
        raise


def _assert_user_deletion_identity(conn, user_id, actor_id):
    """Protect exact actor and configured executor before any native deletion."""
    if user_id == actor_id:
        raise HTTPException(409, "identity_self_delete_forbidden")
    access = conn.session.auth.get_access(conn.session)
    executor_id = getattr(access, "user_id", None)
    if not isinstance(executor_id, str) or not executor_id:
        raise public_service_error(503, "identity_executor_unverified")
    if user_id == executor_id:
        raise HTTPException(409, "identity_service_delete_forbidden")


@router.delete("/users/{user_id}", dependencies=[Depends(require_admin)], status_code=204)
@identity_roles._complete_mutation
async def delete_user(
    user_id: str,
    domain_id: str = Query(..., min_length=1),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """Delete one exact native account; never cascade to projects or resources."""
    try:
        async with identity_roles._graph_lock(conn) as lease:
            # Keep exact-home proof inside the mutation lease for deletion.
            await asyncio.to_thread(_selected_domain, conn, domain_id)
            target = await asyncio.to_thread(_domain_object, conn, domain_id, "user", user_id)
            ks = await asyncio.to_thread(keystone._get_admin_ks_client)
            catalog = await asyncio.to_thread(identity_roles.load_catalog, conn)
            await asyncio.to_thread(_assert_user_deletion_identity, conn, user_id, token_info["user_id"])
            await project_ownership_journal.assert_user_resolved(user_id)
            await account_identity.assert_user_transfer_resolved(user_id)
            # openstacksdk User drops undeclared extras; keystoneclient keeps the marker.
            native_target = await asyncio.to_thread(ks.users.get, user_id)
            await account_spaces.assert_user_deletion_safe(
                user_id, ks=ks, enrollment_id=identity_roles._field(native_target, "afterglow_enrollment_id")
            )
            await asyncio.to_thread(identity_roles.assert_system_admin_remains, users={user_id})
            # Native automation may carry only admin on a service project, not
            # a service role. Privileged identities require guarded grant removal
            # first; never infer account safety from names or federation alone.
            if await domain_iam.protected_user(target, domain_id, credentials=False, system_services=True):
                raise HTTPException(409, "identity_service_delete_forbidden")
            await asyncio.to_thread(project_service.assert_user_ownership_mutation_safe, user_id, ks=ks)
            affected = await asyncio.to_thread(
                domain_projects.assert_managers_remain,
                ks=ks,
                catalog=catalog,
                user_id=user_id,
                disabled_user_ids={user_id},
            )
            await identity_roles._session_ready({user_id})
            await require_admin(token_info)

            def native_delete():
                try:
                    conn.identity.delete_user(user_id, ignore_missing=False)
                except Exception as exc:
                    raise _identity_error(exc) from exc

            succeeded = False
            try:
                await identity_roles._write(lease, native_delete)
                succeeded = True
            finally:
                # A failed/lost response may have committed. Do not replay;
                # revoke durable caller families and clear every identity view.
                try:
                    await session_store.revoke_user_sessions(user_id, revoke_keystone=True)
                finally:
                    try:
                        await identity_roles._sync_domain_managers(conn, lease, affected, ks=ks)
                    finally:
                        await invalidate("afterglow:admin:*")
                        await invalidate(f"afterglow:user:{user_id}:*")
                        await identity_roles._applied(
                            None,
                            [],
                            None,
                            {user_id},
                            token_info,
                            "admin_user_delete",
                            {"user_id": user_id, "domain_id": domain_id},
                            status="success" if succeeded else "failed",
                        )
    except Exception as exc:
        raise _identity_error(exc) from exc


@router.post("/users/{user_id}/revoke-sessions", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def revoke_user_sessions_admin(
    user_id: str,
    token_info: dict = Depends(get_token_info),
):
    """관리자가 특정 사용자의 모든 세션을 강제 폐기 (Keystone 직접 폐기 포함).

    요구사항 A(Keystone 직접 폐기) + B(관리자 강제 전체 로그아웃)를 동시 충족.
    best-effort: Keystone revoke 실패해도 Redis 세션은 삭제된다.
    """
    count = await session_store.revoke_user_sessions(user_id, revoke_keystone=True)
    await activity.record(
        project_id=token_info.get("project_id", ""),
        user_id=token_info["user_id"],
        username=token_info["username"],
        resource_type="auth",
        action="admin_revoke_sessions",
        status="success",
        resource_id=user_id,
        extra={"target_user_id": user_id, "revoked_count": count},
    )
    return {"message": f"세션 {count}개가 폐기되었습니다.", "revoked_count": count}


@router.get("/users/{user_id}/sessions", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def list_user_sessions_admin(user_id: str):
    """관리자가 특정 사용자의 활성 세션 목록을 조회 (keystone_token 제외).

    The user object (and selected domain, when given) is already proven; legacy
    sessions without stored domain metadata remain visible and revocable.
    """
    sessions = await session_store.list_user_sessions(user_id)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/users/{user_id}/permissions", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def get_user_permissions_admin(
    user_id: str,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    domain_id: str | None = Query(None, min_length=1),
):
    """관리자가 사용자별 현재 유효 역할을 실제 project/domain/system 범위로 조회한다."""

    def fetch():
        result = identity_roles.user_permissions(conn, user_id)
        if domain_id is None:
            return result
        projects = {
            p.id for p in conn.identity.projects(domain_id=domain_id) if getattr(p, "domain_id", None) == domain_id
        }
        result["items"] = [
            row
            for row in result["items"]
            if row["scope_type"] == "system"
            or (row["scope_type"] == "domain" and row["scope_id"] == domain_id)
            or (row["scope_type"] == "project" and row["scope_id"] in projects)
        ]
        result["count"] = len(result["items"])
        return result

    return await asyncio.to_thread(fetch)


class UnlockAccountRequest(BaseModel):
    username: str
    domain_id: str = Field(min_length=1)


@router.post("/users/unlock-account", dependencies=[Depends(require_admin)])
async def admin_unlock_account(
    req: UnlockAccountRequest,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """계정 로그인 잠금 강제 해제 (관리자 전용)."""
    domain = await asyncio.to_thread(_selected_domain, conn, req.domain_id)
    await _login_guard.admin_unlock(req.username, domain.id)
    await activity.record(
        project_id=token_info["project_id"],
        user_id=token_info["user_id"],
        username=token_info.get("username", ""),
        resource_type="identity",
        action="account_unlock",
        status="success",
        extra={"target_username": req.username, "domain_id": domain.id},
    )
    return {"status": "unlocked", "username": req.username, "domain_id": domain.id}


@router.get("/users/lock-status", dependencies=[Depends(require_admin)])
async def admin_get_lock_status(
    username: str = Query(...),
    domain_id: str = Query(..., min_length=1),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """계정 잠금 상태 조회 (관리자 전용)."""
    domain = await asyncio.to_thread(_selected_domain, conn, domain_id)
    return await _login_guard.get_lock_status(username, domain.id)


# ============================================================================
# Projects
# ============================================================================


class CreateProjectRequest(BaseModel):
    name: str
    description: str | None = None
    domain_id: str = Field(min_length=1)
    enabled: bool = True


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None


@router.get("/projects/names", dependencies=[Depends(require_admin)])
async def list_project_names(
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    cm: CacheMode = Depends(cache_mode),
    domain_id: str | None = Query(None, min_length=1),
):
    """Project id/name picker; system-wide unless a domain is selected."""
    if domain_id is not None:
        await asyncio.to_thread(_selected_domain, conn, domain_id)

    def _list():
        query = {"domain_id": domain_id} if domain_id else {}
        result = []
        seen = set()
        for p in conn.identity.projects(**query):
            pid, did = getattr(p, "id", None), getattr(p, "domain_id", None)
            if not isinstance(pid, str) or not pid or not isinstance(did, str) or not did or pid in seen:
                raise public_service_error(503, "identity_project_metadata_unavailable")
            seen.add(pid)
            if domain_id is None or did == domain_id:
                result.append({"id": pid, "name": p.name or "", "domain_id": did})
        return result

    try:
        return await cached_call(
            f"afterglow:admin:project_names:{domain_id or '*all'}",
            ttl_slow(),
            _list,
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception as exc:
        raise _identity_error(exc) from exc


def _identity_created_at(value: object) -> str | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds")


async def _identity_creation_dates(items: list[dict], resource_type: str) -> list[dict]:
    # Do not mutate the cached Keystone inventory or substitute first activity.
    result = [{**item, "created_at": _identity_created_at(item.get("created_at"))} for item in items]
    missing = [item["id"] for item in result if item["created_at"] is None]
    if missing:
        try:
            dates = await activity.get_resource_creation_times(resource_type, missing)
        except Exception:
            _logger.warning("Identity 생성 기록 조회 실패 (%s)", resource_type, exc_info=True)
            dates = {}
        for item in result:
            if item["created_at"] is None:
                item["created_at"] = _identity_created_at(dates.get(item["id"]))
    result.sort(key=lambda item: (item["created_at"] or "", item["id"]), reverse=True)
    return result


@router.get("/projects", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def list_projects(
    limit: int = Query(default=20, ge=1, le=100),
    marker: str | None = Query(default=None),
    search: str = Query(default=""),
    enabled: bool | None = Query(default=None),
    domain_id: str = Query(..., min_length=1),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    """Filter and sort the complete inventory before slicing a marker page."""

    def _list():

        return [
            {
                "id": p.id,
                "name": p.name or "",
                "description": getattr(p, "description", "") or "",
                "enabled": p.is_enabled,
                "domain_id": getattr(p, "domain_id", None),
                "created_at": _identity_created_at(getattr(p, "created_at", None)),
            }
            for p in conn.identity.projects(domain_id=domain_id)
            if getattr(p, "domain_id", None) == domain_id
        ]

    try:
        inventory = await cached_call(
            f"afterglow:admin:projects:{domain_id}", ttl_slow(), _list, enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception as exc:
        raise _identity_error(exc) from exc

    projects = await _identity_creation_dates(inventory, "project")
    domains = sorted({p["domain_id"] for p in projects if p["domain_id"]})
    query = search.strip().casefold()
    projects = [
        p
        for p in projects
        if (enabled is None or p["enabled"] == enabled)
        and (domain_id is None or p["domain_id"] == domain_id)
        and (not query or any(query in p[field].casefold() for field in ("name", "id", "description")))
    ]
    start = 0
    if marker:
        start = next((index + 1 for index, p in enumerate(projects) if p["id"] == marker), None)
        if start is None:
            raise HTTPException(status_code=400, detail="페이지 기준 프로젝트가 없습니다. 목록을 새로고침하세요.")
    items = projects[start : start + limit]
    return {
        "items": items,
        "next_marker": items[-1]["id"] if start + limit < len(projects) else None,
        "count": len(items),
        "total": len(projects),
        "domain_ids": domains,
    }


@router.post("/projects", dependencies=[Depends(require_admin)], status_code=201)
@identity_roles._complete_mutation
async def create_project(
    req: CreateProjectRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    provider_conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """프로젝트 생성."""
    await asyncio.to_thread(_selected_domain, conn, req.domain_id)
    from app.services import account_spaces

    native_ks = await asyncio.to_thread(keystone._get_admin_ks_client)
    native_domain = await asyncio.to_thread(native_ks.domains.get, req.domain_id)
    if identity_roles._field(native_domain, "id") != req.domain_id:
        raise HTTPException(503, "Native domain identity is unavailable")
    kind = account_spaces.domain_kind(native_domain)
    if kind == "account":
        raise HTTPException(403, "Identity-only domain cannot contain projects")
    if kind == "personal":
        raise HTTPException(403, "personal_project_user_creation_required")
    if req.name.casefold() == "default":
        raise HTTPException(409, "Default is reserved for the domain authority project")

    def _create():
        try:
            kwargs = {"name": req.name, "enabled": False}
            if req.description:
                kwargs["description"] = req.description
            kwargs["domain_id"] = req.domain_id
            proxy = copy(conn.identity)
            proxy.request = partial(proxy.request, connect_retries=0, status_code_retries=0)
            p = proxy.create_project(**kwargs)
            return {
                "id": p.id,
                "name": p.name or "",
                "description": getattr(p, "description", "") or "",
                "enabled": p.is_enabled,
            }
        except Exception as e:
            _logger.warning("프로젝트 생성 실패: %s", e)

            raise _identity_error(e) from e

    try:
        from app.config import get_settings
        from app.services import neutron

        async with identity_roles._graph_lock(conn) as lease:
            ks = await asyncio.to_thread(keystone._get_admin_ks_client)
            catalog = await asyncio.to_thread(identity_roles.load_catalog, conn)
            authority = await asyncio.to_thread(domain_projects.managers, req.domain_id, ks=ks, catalog=catalog)
            if authority["default_project_id"] is None:
                raise HTTPException(409, "domain_default_bootstrap_required")
            if not authority["items"]:
                raise HTTPException(409, "domain_default_manager_required")
            await domain_projects.sync_manager_access(req.domain_id, mutation=(lease, ks, catalog))
            previous_projects = await asyncio.to_thread(lambda: list(ks.projects.list(domain=req.domain_id)))
            existing = set()
            for project in previous_projects:
                pid = identity_roles._field(project, "id")
                if not isinstance(pid, str) or not pid or identity_roles._field(project, "domain_id") != req.domain_id:
                    raise public_service_error(503, "created_project_unverified")
                existing.add(pid)
            result = await identity_roles._write(lease, _create)
            project_id = identity_roles._created_id(result)
            if project_id in existing:
                raise public_service_error(503, "created_project_unverified")
            try:
                checked = await asyncio.to_thread(_native_object, conn, "project", project_id)
                enabled = identity_roles._field(checked, "is_enabled", identity_roles._field(checked, "enabled"))
                if (
                    identity_roles._field(checked, "domain_id") != req.domain_id
                    or identity_roles._field(checked, "name") != req.name
                    or enabled is not False
                ):
                    raise public_service_error(503, "created_project_unverified")
                await project_service.initialize_system_project_owner(
                    project_id,
                    token_info["user_id"],
                    req.domain_id,
                    lease=lease,
                    ks=ks,
                    catalog=catalog,
                    previous_project_ids=existing,
                )
                await domain_quotas.apply_project_defaults(provider_conn, req.domain_id, project_id, lease=lease)
                await domain_projects.sync_manager_access(req.domain_id, mutation=(lease, ks, catalog))
                staged = await asyncio.to_thread(_native_object, conn, "project", project_id)
                if (
                    identity_roles._field(staged, "domain_id") != req.domain_id
                    or identity_roles._field(staged, "is_enabled", identity_roles._field(staged, "enabled"))
                    is not False
                ):
                    raise public_service_error(503, "created_project_unverified")
                await project_service._verify_unique_owner(ks, catalog, project_id, token_info["user_id"])
                if req.enabled:
                    await identity_roles._write(lease, ks.projects.update, project_id, enabled=True)
                checked = await asyncio.to_thread(ks.projects.get, project_id)
                if identity_roles._field(checked, "enabled") is not req.enabled:
                    raise public_service_error(503, "created_project_unverified")
                result.update(enabled=req.enabled, domain_id=req.domain_id)
            except Exception:
                # Only the fresh native ID returned by this attempt is eligible
                # for compensation; unknown creates are never retried or guessed.
                try:
                    staged = await asyncio.to_thread(ks.projects.get, project_id)
                    if identity_roles._field(staged, "domain_id") != req.domain_id:
                        raise public_service_error(503, "created_project_cleanup_unavailable")
                    await identity_roles._write(lease, ks.projects.update, project_id, enabled=False)
                    if (
                        identity_roles._field(await asyncio.to_thread(ks.projects.get, project_id), "enabled")
                        is not False
                    ):
                        raise public_service_error(503, "created_project_cleanup_unavailable")
                    if not (await project_service.inspect_project_empty(project_id))["can_delete"]:
                        raise public_service_error(503, "created_project_cleanup_unavailable")
                    await identity_roles._write(lease, conn.identity.delete_project, project_id, ignore_missing=False)
                except Exception as cleanup_error:
                    raise public_service_error(503, "created_project_cleanup_unavailable") from cleanup_error
                raise
        await activity.record(
            project_id=token_info["project_id"],
            user_id=token_info["user_id"],
            username=token_info.get("username", ""),
            resource_type="project",
            action="project.create",
            status="success",
            resource_id=result["id"],
            resource_name=result["name"],
        )
        await invalidate("afterglow:admin:projects:*")
        await invalidate("afterglow:admin:project_names:*")
        _settings = get_settings()
        if _settings.monitoring_auto_sg_enabled and _settings.monitoring_scrape_cidr:
            try:
                await asyncio.to_thread(
                    neutron.ensure_node_exporter_sg,
                    provider_conn,
                    result["id"],
                    _settings.node_exporter_sg_name,
                    _settings.monitoring_scrape_cidr,
                )
            except Exception:
                _logger.warning("신규 프로젝트 node_exporter SG 자동 생성 실패, 계속 진행", exc_info=True)
            try:
                await asyncio.to_thread(
                    neutron.ensure_dcgm_exporter_sg,
                    provider_conn,
                    result["id"],
                    _settings.dcgm_exporter_sg_name,
                    _settings.monitoring_scrape_cidr,
                )
            except Exception:
                _logger.warning("신규 프로젝트 dcgm_exporter SG 자동 생성 실패, 계속 진행", exc_info=True)
        return result
    except HTTPException:
        raise


@router.get("/projects/{project_id}", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def get_project(
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """프로젝트 상세 조회."""

    def _get():
        try:
            p = conn.identity.get_project(project_id)
            created_at = getattr(p, "created_at", None)
            return {
                "id": p.id,
                "name": p.name or "",
                "description": getattr(p, "description", "") or "",
                "enabled": p.is_enabled,
                "domain_id": getattr(p, "domain_id", None),
                "created_at": str(created_at) if created_at else None,
            }
        except Exception as e:
            _logger.warning("프로젝트 조회 실패: %s", e)
            raise _identity_error(e) from e

    try:
        result = await asyncio.to_thread(_get)
        return (await _identity_creation_dates([result], "project"))[0]
    except HTTPException:
        raise


@router.patch("/projects/{project_id}", dependencies=[Depends(require_admin), Depends(_selected_objects)])
@identity_roles._complete_mutation
async def update_project(
    project_id: str,
    req: UpdateProjectRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    provider_conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """프로젝트 수정."""

    def _update():
        kwargs: dict = {}
        if req.name is not None:
            kwargs["name"] = req.name
        if req.description is not None:
            kwargs["description"] = req.description
        if req.enabled is not None:
            kwargs["enabled"] = req.enabled
        try:
            p = conn.identity.update_project(project_id, **kwargs)
            return {
                "id": p.id,
                "name": p.name or "",
                "description": getattr(p, "description", "") or "",
                "enabled": p.is_enabled,
            }
        except Exception as e:
            _logger.warning("프로젝트 수정 실패: %s", e)

            raise _identity_error(e) from e

    try:
        async with identity_roles._graph_lock(conn) as lease:
            project = await asyncio.to_thread(_native_object, conn, "project", project_id)
            domain_projects.assert_default_immutable(
                project_id, attrs=req.model_dump(exclude_none=True), project=project
            )
            await project_ownership_journal.assert_resolved(project_id)
            if req.enabled is True:
                await project_service.assert_project_activation_safe(project_id)
                await domain_quotas.assert_project_allocation(
                    provider_conn, identity_roles._field(project, "domain_id"), project_id, lease=lease
                )
            try:
                result = await identity_roles._write(lease, _update)
            finally:
                await invalidate_authority()
                await invalidate("afterglow:admin:projects:*")
                await invalidate("afterglow:admin:project_names:*")
        return result
    except HTTPException:
        raise


async def _settled_project_deletion_call(call, *args):
    # get_admin_os_conn closes the request connection in finally. Let read-only
    # workers settle before cancellation unwinds that dependency. In DELETE,
    # cancellation during inspection must never schedule a Keystone mutation.
    worker = asyncio.create_task(asyncio.to_thread(call, *args))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        # FastAPI middleware uses AnyIO level cancellation, so a second
        # asyncio.shield alone can be cancelled again before the worker settles.
        with CancelScope(shield=True):
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not worker.cancelled():
                worker.exception()
        raise


def _project_deletion_inventory(conn, project_id):
    check = inspect_project_resources(conn, project_id)
    ks = keystone._get_admin_ks_client()
    check["resources"].append(project_service.inspect_child_projects(ks, project_id))
    check["can_delete"] = all(
        row["status"] == "skipped" or (row["status"] == "ok" and row["count"] == 0) for row in check["resources"]
    )
    return check


@router.get("/projects/{project_id}/resources", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def list_project_cleanup_resources(
    project_id: str,
    response: Response,
    domain_id: str = Query(..., min_length=1),
    kind: str = Query(..., min_length=1),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """Complete exact-project metadata; never submit resource cleanup on GET."""
    response.headers["Cache-Control"] = "no-store, private"
    project_cleanup.require_kind(kind)
    target = None
    try:
        if project_cleanup.requires_project_scope(kind):
            from app.services.volume_transfers import admin_destination

            target = await _settled_project_deletion_call(admin_destination, conn, token_info, domain_id, project_id)
        return await _settled_project_deletion_call(project_cleanup.list_resources, target or conn, project_id, kind)
    except Exception as exc:
        raise project_cleanup._error(exc) from None
    finally:
        if target is not None:
            await _settled_project_deletion_call(target.close)


@router.delete(
    "/projects/{project_id}/resources/{kind}/{resource_id}",
    dependencies=[Depends(require_admin), Depends(_selected_objects)],
    status_code=204,
)
@identity_roles._complete_mutation
async def delete_project_cleanup_resource(
    project_id: str,
    kind: str,
    resource_id: str,
    response: Response,
    domain_id: str = Query(..., min_length=1),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """Accept one normal deletion; asynchronous provider completion is not implied."""
    response.headers["Cache-Control"] = "no-store, private"
    project_cleanup.require_kind(kind)
    if kind == "child_projects":
        project_cleanup.identifier(resource_id)
        async with identity_roles._graph_lock(conn) as lease:
            parent = await _settled_project_deletion_call(_domain_object, conn, domain_id, "project", project_id)
            child = await _settled_project_deletion_call(_domain_object, conn, domain_id, "project", resource_id)
            if resource_id == project_id or identity_roles._field(child, "parent_id") != project_id:
                raise HTTPException(403, "project_resource_parent_mismatch")
            if identity_roles._field(parent, "id") != project_id:
                raise HTTPException(503, "project_resource_parent_unverified")
            await _delete_project_under_lease(
                conn, conn, resource_id, lease, expected_parent=project_id, expected_domain=domain_id
            )
        return
    target = None
    try:
        if project_cleanup.requires_project_scope(kind):
            from app.services.volume_transfers import admin_destination

            target = await _settled_project_deletion_call(admin_destination, conn, token_info, domain_id, project_id)
        provider = target or conn
        await project_cleanup.assert_deletion_safe(provider, project_id, kind, resource_id)
        await _settled_project_deletion_call(project_cleanup.delete_resource, provider, project_id, kind, resource_id)
    except Exception as exc:
        raise project_cleanup._error(exc) from None
    finally:
        if target is not None:
            await _settled_project_deletion_call(target.close)


async def _delete_project_under_lease(
    conn, provider_conn, project_id, lease, *, expected_parent=None, expected_domain=None
):
    project = await _settled_project_deletion_call(_native_object, conn, "project", project_id)
    if expected_parent is not None and (
        identity_roles._field(project, "parent_id") != expected_parent
        or identity_roles._field(project, "domain_id") != expected_domain
    ):
        raise HTTPException(403, "project_resource_parent_mismatch")
    domain_projects.assert_default_immutable(project_id, delete=True, project=project)
    await project_ownership_journal.assert_resolved(project_id)
    check = await _settled_project_deletion_call(_project_deletion_inventory, provider_conn, project_id)
    if any(item["status"] == "unavailable" for item in check["resources"]):
        error = HTTPException(
            status_code=503,
            detail={
                "code": "project_resource_check_failed",
                "message": "Project resource inventory could not be verified. No project was deleted.",
                "check": check,
            },
        )
        error._afterglow_safe_public_detail = True
        raise error
    if not check["can_delete"]:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "project_has_resources",
                "message": "The project still owns cloud resources or child projects. No project was deleted.",
                "check": check,
            },
        )
    try:
        if expected_parent is None:
            await identity_roles._write(lease, conn.identity.delete_project, project_id, ignore_missing=False)
        else:
            await identity_roles._write(lease, project_cleanup.delete_project_native, conn.identity, project_id)
    except Exception as exc:
        raise (project_cleanup._error(exc) if expected_parent is not None else _identity_error(exc)) from exc
    finally:
        await invalidate_authority()
        await invalidate("afterglow:admin:projects:*")
        await invalidate("afterglow:admin:project_names:*")


@router.get("/projects/{project_id}/deletion-check", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def get_project_deletion_check(
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    provider_conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """Fresh resource proof, never backed by cached counts or quota usage."""
    project = await _settled_project_deletion_call(_native_object, conn, "project", project_id)
    domain_projects.assert_default_immutable(project_id, delete=True, project=project)
    await project_ownership_journal.assert_resolved(project_id)
    return await _settled_project_deletion_call(_project_deletion_inventory, provider_conn, project_id)


@router.delete(
    "/projects/{project_id}", dependencies=[Depends(require_admin), Depends(_selected_objects)], status_code=204
)
async def delete_project(
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    provider_conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """Delete only after fresh complete resource and child-project inspection."""
    async with identity_roles._graph_lock(conn) as lease:
        await _delete_project_under_lease(conn, provider_conn, project_id, lease)


@router.get("/projects/{project_id}/members", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def list_project_members(
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    domain_id: str | None = Query(None, min_length=1),
):
    """프로젝트의 사용자-역할 할당 목록 조회."""

    def _list():
        try:
            users, groups = {}, {}
            assignments = []
            for ra in conn.identity.role_assignments(scope_project_id=project_id, include_names=True):
                scope = identity_roles._field(ra, "scope", {})
                if not isinstance(scope, dict) or scope.get("project", {}).get("id") != project_id:
                    continue
                user = identity_roles._field(ra, "user", {}) or {}
                group = identity_roles._field(ra, "group", {}) or {}
                role = identity_roles._field(ra, "role", {}) or {}
                role_fields = {"role_id": role.get("id", ""), "role_name": role.get("name", "")}
                if user.get("id"):
                    uid = user["id"]
                    if uid not in users:
                        users[uid] = _native_object(conn, "user", uid)
                    principal = users[uid]
                    assignments.append(
                        {
                            "user_id": uid,
                            "user_name": principal.name or "",
                            **role_fields,
                            "type": "user",
                            "domain_id": principal.domain_id,
                            "identity_read_only": domain_id is not None and principal.domain_id != domain_id,
                        }
                    )
                elif group.get("id"):
                    gid = group["id"]
                    if gid not in groups:
                        groups[gid] = _native_object(conn, "group", gid)
                    name = groups[gid].name or ""
                    assignments.append(
                        {
                            "user_id": f"group:{group['id']}",
                            "user_name": name,
                            **role_fields,
                            "type": "group",
                            "group_id": group["id"],
                        }
                    )
            return assignments
        except Exception as e:
            _logger.warning("멤버 목록 조회 실패: %s", e)

            raise _identity_error(e) from e

    try:
        return await asyncio.to_thread(_list)
    except HTTPException:
        raise


# ============================================================================
# Quotas
# ============================================================================


QuotaLimit = Annotated[int, Field(strict=True, ge=-1)]


class ComputeQuotaRequest(BaseModel):
    instances: QuotaLimit | None = None
    cores: QuotaLimit | None = None
    ram: QuotaLimit | None = None


class QuotaUpdateRequest(ComputeQuotaRequest):
    model_config = ConfigDict(extra="forbid")

    key_pairs: QuotaLimit | None = None
    server_groups: QuotaLimit | None = None
    server_group_members: QuotaLimit | None = None
    injected_files: QuotaLimit | None = None
    injected_file_content_bytes: QuotaLimit | None = None
    injected_file_path_bytes: QuotaLimit | None = None
    metadata_items: QuotaLimit | None = None
    volumes: QuotaLimit | None = None
    snapshots: QuotaLimit | None = None
    gigabytes: QuotaLimit | None = None
    network: QuotaLimit | None = None
    subnet: QuotaLimit | None = None
    port: QuotaLimit | None = None
    router: QuotaLimit | None = None
    floatingip: QuotaLimit | None = None
    security_group: QuotaLimit | None = None
    security_group_rule: QuotaLimit | None = None
    shares: QuotaLimit | None = None
    share_gigabytes: QuotaLimit | None = None
    share_snapshots: QuotaLimit | None = None
    share_snapshot_gigabytes: QuotaLimit | None = None
    share_networks: QuotaLimit | None = None
    share_groups: QuotaLimit | None = None
    share_group_snapshots: QuotaLimit | None = None


class ComputePolicyUpdateRequest(ComputeQuotaRequest):
    model_config = ConfigDict(extra="forbid")
    gpu_quotas: dict[str, int | None] = Field(default_factory=dict)


@router.put("/compute-policy/{project_id}", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def update_project_compute_policy(
    project_id: str,
    req: ComputePolicyUpdateRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """Apply compute and GPU quotas without changing native flavor access."""
    from app.services.gpu_quota import (
        delete_project_gpu_quota,
        set_project_gpu_quota,
    )

    compute_kwargs = {
        key: value
        for key, value in {
            "instances": req.instances,
            "cores": req.cores,
            "ram": req.ram,
        }.items()
        if value is not None
    }
    from app.services import domain_quotas

    native_quotas = None
    if compute_kwargs:
        native_quotas = await domain_quotas.update_project(conn, project_id, compute_kwargs)
        if native_quotas["status"] != "updated":
            # Native services and the GPU ledger are not one transaction. Do
            # not continue subsequent policy effects after uncertain Nova.
            return {
                "project_id": project_id,
                "status": "partial",
                "errors": [{"code": "compute_quota_not_verified"}],
                "native_quotas": native_quotas,
                "enforcement_scope": "afterglow_admissions_only",
            }

    errors: list[dict] = []
    for gpu_type, limit in req.gpu_quotas.items():
        try:
            if limit is None:
                await delete_project_gpu_quota(conn, project_id, gpu_type)
            else:
                await set_project_gpu_quota(conn, project_id, gpu_type, limit)
        except Exception:
            errors.append({"gpu_type": gpu_type, "code": "gpu_quota_apply_failed"})

    await invalidate(f"afterglow:nova:{project_id}:flavors")
    await invalidate(f"afterglow:dashboard:{project_id}:quotas")
    return {
        "project_id": project_id,
        "status": "partial" if errors else "ok",
        "errors": errors,
        "native_quotas": native_quotas,
        "enforcement_scope": "afterglow_admissions_only",
    }


@router.get("/quotas/{project_id}", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def get_project_quotas(
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """Read the target project's usage-bearing quota sets independently."""
    return await quota_native.read_project(conn, project_id)


@router.put("/quotas/{project_id}", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def update_project_quotas(
    project_id: str,
    req: QuotaUpdateRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """All first-party native quota writers share the domain allocation fence."""
    from app.services import domain_quotas

    supplied = req.model_dump(exclude_unset=True)
    return await domain_quotas.update_project(conn, project_id, supplied)


# ============================================================================
# Groups
# ============================================================================


@router.get("/groups", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def list_groups(
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    cm: CacheMode = Depends(cache_mode),
    domain_id: str = Query(..., min_length=1),
):
    """일반 관리 그룹 목록, 확인된 생성일 내림차순. 내부 manager projection 제외."""

    def _list():

        return [
            {
                "id": g.id,
                "name": g.name or "",
                "description": getattr(g, "description", "") or "",
                "domain_id": getattr(g, "domain_id", None),
                "created_at": _identity_created_at(getattr(g, "created_at", None)),
            }
            for g in conn.identity.groups(domain_id=domain_id)
            if getattr(g, "domain_id", None) == domain_id
        ]

    try:
        inventory = await cached_call(
            f"afterglow:admin:groups:{domain_id}", ttl_slow(), _list, enabled=cm.enabled, refresh=cm.refresh
        )
        # Filter after cache reads too: pre-fix snapshots may contain private groups.
        inventory = [group for group in inventory if not domain_projects._is_projection_group(group)]
        return await _identity_creation_dates(inventory, "group")
    except Exception as exc:
        raise _identity_error(exc) from exc


class CreateGroupRequest(BaseModel):
    name: str
    description: str | None = None
    domain_id: str = Field(min_length=1)


class UpdateGroupRequest(BaseModel):
    name: str | None = None
    description: str | None = None


@router.post("/groups", dependencies=[Depends(require_admin)], status_code=201)
async def create_group(
    req: CreateGroupRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """그룹 생성."""
    domain_projects.assert_projection_attributes(req.model_dump(exclude_none=True))
    await asyncio.to_thread(_selected_domain, conn, req.domain_id)

    def _create():
        try:
            kwargs = {"name": req.name}
            if req.description:
                kwargs["description"] = req.description
            kwargs["domain_id"] = req.domain_id
            g = conn.identity.create_group(**kwargs)
            return {
                "id": g.id,
                "name": g.name or "",
                "description": getattr(g, "description", "") or "",
                "domain_id": getattr(g, "domain_id", None),
            }
        except Exception as e:
            _logger.warning("그룹 생성 실패: %s", e)

            raise _identity_error(e) from e

    try:
        result = await asyncio.to_thread(_create)
        await activity.record(
            project_id=token_info["project_id"],
            user_id=token_info["user_id"],
            username=token_info.get("username", ""),
            resource_type="group",
            action="group.create",
            status="success",
            resource_id=result["id"],
            resource_name=result["name"],
            service="keystone",
        )
        await invalidate("afterglow:admin:groups:*")
        return result
    except HTTPException:
        raise


@router.patch("/groups/{group_id}", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def update_group(
    group_id: str,
    req: UpdateGroupRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """그룹 수정."""
    domain_projects.assert_projection_attributes(req.model_dump(exclude_none=True))

    def _update():
        kwargs: dict = {}
        if req.name is not None:
            kwargs["name"] = req.name
        if req.description is not None:
            kwargs["description"] = req.description
        try:
            g = conn.identity.update_group(group_id, **kwargs)
            return {
                "id": g.id,
                "name": g.name or "",
                "description": getattr(g, "description", "") or "",
            }
        except Exception as e:
            _logger.warning("그룹 수정 실패: %s", e)

            raise _identity_error(e) from e

    try:
        async with identity_roles._graph_lock(conn) as lease:
            await asyncio.to_thread(domain_projects.assert_not_projection_group, group_id)
            await lease.assert_owned()
            result = await asyncio.to_thread(_update)
        await invalidate("afterglow:admin:groups:*")
        return result
    except HTTPException:
        raise


@router.delete("/groups/{group_id}", dependencies=[Depends(require_admin), Depends(_selected_objects)], status_code=204)
async def delete_group(
    group_id: str,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    await identity_roles.change_group_membership(conn, token_info, group_id, delete=True)
    await invalidate("afterglow:admin:groups:*")


@router.get("/groups/{group_id}/users", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def list_group_users(
    group_id: str,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    domain_id: str | None = Query(None, min_length=1),
):
    """그룹 멤버 목록."""

    def _list():
        users = []
        try:
            for u in conn.identity.group_users(group_id):
                users.append(
                    {
                        "id": u.id,
                        "name": u.name or "",
                        "email": getattr(u, "email", "") or "",
                        "domain_id": getattr(u, "domain_id", None),
                        "identity_read_only": domain_id is not None and getattr(u, "domain_id", None) != domain_id,
                        "enabled": getattr(u, "is_enabled", True),
                    }
                )
        except Exception as e:
            _logger.warning("그룹 멤버 조회 실패: %s", e)

            raise _identity_error(e) from e
        return users

    try:
        return await asyncio.to_thread(_list)
    except HTTPException:
        raise


@router.get("/groups/{group_id}/candidates", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def list_group_candidates(
    group_id: str,
    response: Response,
    domain_id: str = Query(..., min_length=1),
    user_domain_id: str = Query(..., min_length=1),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """List-time identity-home candidates; admission revalidates under the graph lease."""
    response.headers["Cache-Control"] = "no-store, private"

    def _list():
        ks = keystone._get_admin_ks_client()
        identity_roles._group_identity_home(ks, group_id, domain_id, user_domain_id)
        ids = set()
        items = []
        for user in ks.users.list(domain=user_domain_id):
            uid = identity_roles._field(user, "id")
            if not isinstance(uid, str) or not uid or uid in ids:
                raise public_service_error(503, "identity_object_unverified")
            if identity_roles._field(user, "domain_id") != user_domain_id:
                raise public_service_error(503, "identity_object_unverified")
            ids.add(uid)
            if not domain_projects._enabled(user):
                continue
            name, email = identity_roles._field(user, "name"), identity_roles._field(user, "email", "")
            if not isinstance(name, str) or (email is not None and not isinstance(email, str)):
                raise public_service_error(503, "identity_object_unverified")
            items.append({"id": uid, "name": name, "email": email or "", "enabled": True, "domain_id": user_domain_id})
        items.sort(key=lambda item: item["id"])
        return {"domain_id": domain_id, "user_domain_id": user_domain_id, "items": items}

    try:
        return await asyncio.to_thread(_list)
    except Exception as exc:
        raise _identity_error(exc) from exc


@router.put(
    "/groups/{group_id}/users/{user_id}",
    dependencies=[Depends(require_admin), Depends(_selected_objects)],
    status_code=204,
)
async def add_user_to_group(
    group_id: str,
    user_id: str,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    user_domain_id: str | None = Query(None, min_length=1),
    domain_id: str | None = Query(None, min_length=1),
):
    if user_domain_id is not None:
        if domain_id is None:
            raise HTTPException(422, "Explicit group admission requires a selected domain")
        await identity_roles.change_group_membership(
            conn, token_info, group_id, user_id=user_id, user_domain_id=user_domain_id, domain_id=domain_id
        )
    else:
        await identity_roles.change_group_membership(conn, token_info, group_id, user_id=user_id)


@router.delete(
    "/groups/{group_id}/users/{user_id}",
    dependencies=[Depends(require_admin), Depends(_selected_objects)],
    status_code=204,
)
async def remove_user_from_group(
    group_id: str,
    user_id: str,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    await identity_roles.change_group_membership(conn, token_info, group_id, user_id=user_id, remove=True)


# ============================================================================
# Roles
# ============================================================================


@router.get("/roles", dependencies=[Depends(require_admin)])
async def list_roles(conn: openstack.connection.Connection = Depends(get_admin_os_conn)):
    """Fresh real implication graph; provider failures must never become an empty list."""
    return await asyncio.to_thread(identity_roles.load_catalog, conn)


@router.get("/roles/presets", dependencies=[Depends(require_admin)])
async def role_presets():
    """Read-only requested hierarchy; preview never seeds Keystone roles."""
    return preset_preview()


@router.post("/roles/presets/apply", dependencies=[Depends(require_admin)])
async def apply_role_presets(
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    return await identity_roles.apply_role_presets(conn, token_info)


class AssignRoleRequest(BaseModel):
    user_id: str
    project_id: str
    role_id: str


@router.post("/roles/assign", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def assign_role(
    req: AssignRoleRequest,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    return await identity_roles.change_project_assignment(
        conn, token_info, req.project_id, req.role_id, user_id=req.user_id
    )


@router.delete("/roles/assign", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def revoke_role(
    user_id: str = Query(...),
    project_id: str = Query(...),
    role_id: str = Query(...),
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    return await identity_roles.change_project_assignment(
        conn, token_info, project_id, role_id, user_id=user_id, remove=True
    )


class AssignGroupRoleRequest(BaseModel):
    group_id: str
    project_id: str
    role_id: str


@router.post("/roles/assign-group", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def assign_group_role(
    req: AssignGroupRoleRequest,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    return await identity_roles.change_project_assignment(
        conn, token_info, req.project_id, req.role_id, group_id=req.group_id
    )


@router.delete("/roles/assign-group", dependencies=[Depends(require_admin), Depends(_selected_objects)])
async def revoke_group_role(
    group_id: str = Query(...),
    project_id: str = Query(...),
    role_id: str = Query(...),
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    return await identity_roles.change_project_assignment(
        conn, token_info, project_id, role_id, group_id=group_id, remove=True
    )


def _normalize_role_input(value):
    # Normalize before ConfigDict strips strings, retaining boundary whitespace
    # as hyphens. Legacy unchanged names are handled by the service after lookup.
    if isinstance(value, str) and "_" in value:
        return normalize_role_name(value)
    return value


class CreateRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4096)
    domain_id: str | None = Field(default=None, min_length=1, max_length=255)

    _normalize_name = field_validator("name", mode="before")(_normalize_role_input)


class UpdateRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)

    _normalize_name = field_validator("name", mode="before")(_normalize_role_input)


@router.post("/roles", dependencies=[Depends(require_admin)], status_code=201)
async def create_identity_role(
    req: CreateRoleRequest,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    return await identity_roles.create_role(conn, token_info, req.model_dump(exclude_none=True))


# Keep these dynamic role routes after /roles/assign and /roles/assign-group.
@router.patch("/roles/{role_id}", dependencies=[Depends(require_admin)])
async def update_identity_role(
    role_id: str,
    req: UpdateRoleRequest,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    attrs = req.model_dump(exclude_unset=True)
    if not attrs or any(value is None for value in attrs.values()):
        raise HTTPException(status_code=422, detail="Supply non-null role metadata")
    return await identity_roles.update_role(conn, token_info, role_id, attrs)


@router.delete("/roles/{role_id}", dependencies=[Depends(require_admin)])
async def delete_identity_role(
    role_id: str,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    return await identity_roles.delete_role(conn, token_info, role_id)


@router.put("/roles/{prior_role_id}/implies/{implied_role_id}", dependencies=[Depends(require_admin)])
async def create_role_implication(
    prior_role_id: str,
    implied_role_id: str,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    return await identity_roles.change_edge(conn, token_info, prior_role_id, implied_role_id)


@router.delete("/roles/{prior_role_id}/implies/{implied_role_id}", dependencies=[Depends(require_admin)])
async def delete_role_implication(
    prior_role_id: str,
    implied_role_id: str,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    return await identity_roles.change_edge(conn, token_info, prior_role_id, implied_role_id, remove=True)


# ============================================================================
# System Roles (Keystone system:all scope)
# ============================================================================


class SystemRoleRequest(BaseModel):
    user_id: str


@router.get("/identity/system-roles", dependencies=[Depends(require_admin)])
async def list_system_roles():
    """system:all scope에서 admin role을 보유한 사용자 목록 조회."""

    def _list():
        try:
            admin_role_id = keystone._resolve_admin_role_id()
            ks = keystone._get_admin_ks_client()
            assignments = ks.role_assignments.list(role=admin_role_id, system="all")
            user_ids = [a.user["id"] for a in assignments if hasattr(a, "user")]
            result = []
            for uid in user_ids:
                try:
                    u = ks.users.get(uid)
                    result.append(
                        {
                            "user_id": uid,
                            "name": getattr(u, "name", ""),
                            "email": getattr(u, "email", ""),
                            "enabled": getattr(u, "enabled", False),
                        }
                    )
                except Exception:
                    result.append({"user_id": uid, "name": "", "email": "", "enabled": False})
            return result
        except HTTPException:
            raise
        except Exception as e:
            _logger.warning("system role 목록 조회 실패: %s", e)
            raise HTTPException(status_code=500, detail="system role 목록 조회 실패")

    return await asyncio.to_thread(_list)


async def _system_admin_change(conn, user_id: str, *, revoke: bool) -> dict:
    # The shared native role-graph lease serializes this with every other grant,
    # role and implication mutation, so two concurrent revokes cannot both pass.
    async with identity_roles._graph_lock(conn) as lease:
        try:
            admin_role_id = await asyncio.to_thread(keystone._resolve_admin_role_id)
            ks = await asyncio.to_thread(keystone._get_admin_ks_client)
            if revoke:

                def check():
                    direct = list(ks.role_assignments.list(role=admin_role_id, system="all", user=user_id))
                    if not direct:
                        raise HTTPException(404, "system_admin_grant_not_found")
                    identity_roles.assert_system_admin_remains(users={user_id})

                await asyncio.to_thread(check)
        except Exception as exc:
            raise _identity_error(exc) from exc
        await identity_roles._session_ready({user_id})
        method = ks.roles.revoke if revoke else ks.roles.grant
        try:
            await identity_roles._write(lease, method, role=admin_role_id, user=user_id, system="all")
        finally:
            # A failed reply may follow a committed native authority change.
            try:
                await invalidate_authority()
            finally:
                await session_store.revoke_user_sessions(user_id)
    return {"status": "revoked" if revoke else "granted"}


@router.post("/identity/system-roles/grant", dependencies=[Depends(require_admin)])
@identity_roles._complete_mutation
async def grant_system_role(
    req: SystemRoleRequest,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """사용자에게 Keystone system:all admin role 부여."""
    result = await _system_admin_change(conn, req.user_id, revoke=False)
    await activity.record(
        project_id=token_info["project_id"],
        user_id=token_info["user_id"],
        username=token_info.get("username", ""),
        resource_type="identity",
        action="admin_system_role_grant",
        status="success",
        resource_id=req.user_id,
    )
    return result


@router.post("/identity/system-roles/revoke", dependencies=[Depends(require_admin)])
@identity_roles._complete_mutation
async def revoke_system_role(
    req: SystemRoleRequest,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """사용자로부터 Keystone system:all admin role 회수 (마지막 유효 관리자 보호)."""
    result = await _system_admin_change(conn, req.user_id, revoke=True)
    await activity.record(
        project_id=token_info["project_id"],
        user_id=token_info["user_id"],
        username=token_info.get("username", ""),
        resource_type="identity",
        action="admin_system_role_revoke",
        status="success",
        resource_id=req.user_id,
    )
    return result


@router.get("/identity/security-policy", dependencies=[Depends(require_admin)])
async def get_security_policy():
    """Only actual system:all administrator grants; provider failure is not zero."""
    return {"system_admin_count": len(await list_system_roles())}


# ============================================================================
# Monitoring SG 동기화
# ============================================================================


@router.post(
    "/projects/{project_id}/sync-monitoring-sg", dependencies=[Depends(require_admin), Depends(_selected_objects)]
)
async def sync_monitoring_sg(
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """프로젝트에 Monitoring ingress SG를 idempotent하게 동기화한다. 관리자 전용."""
    from app.config import get_settings
    from app.services import neutron

    settings = get_settings()
    if not settings.monitoring_scrape_cidr:
        raise HTTPException(status_code=422, detail="monitoring_scrape_cidr 설정이 필요합니다")

    try:
        ne_name = await asyncio.to_thread(
            neutron.ensure_node_exporter_sg,
            conn,
            project_id,
            settings.node_exporter_sg_name,
            settings.monitoring_scrape_cidr,
        )
        dc_name = await asyncio.to_thread(
            neutron.ensure_dcgm_exporter_sg,
            conn,
            project_id,
            settings.dcgm_exporter_sg_name,
            settings.monitoring_scrape_cidr,
        )
        return {
            "status": "ok",
            "project_id": project_id,
            "sg_names": {"node_exporter": ne_name, "dcgm_exporter": dc_name},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Monitoring SG 동기화 실패: {e}")


# ---------------------------------------------------------------------------
# A-7  GET /admin/identity/summary  (Phase 50c)
# ---------------------------------------------------------------------------


@router.get("/identity/summary", dependencies=[Depends(require_admin)])
async def get_identity_summary(
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """users / projects / roles / groups / domains 카운트 + 최근 변경 요약."""

    def _classify_exc(exc: Exception) -> str:
        s = str(exc).lower()
        if "403" in s or "forbidden" in s:
            return "insufficient_privileges"
        if "401" in s or "unauthorized" in s:
            return "unauthorized"
        if "connection" in s or "timeout" in s:
            return "connection_error"
        return f"error:{type(exc).__name__}"

    def _collect():
        partial = False
        partial_reasons: list[str] = []
        users: list = []
        try:
            users = list(conn.identity.users(limit=1000))
        except Exception as exc:
            _logger.warning("identity summary partial: users failed: %s", exc, exc_info=True)
            partial = True
            partial_reasons.append(f"users:{_classify_exc(exc)}")
        projects: list = []
        try:
            projects = list(conn.identity.projects(limit=1000))
        except Exception as exc:
            _logger.warning("identity summary partial: projects failed: %s", exc, exc_info=True)
            partial = True
            partial_reasons.append(f"projects:{_classify_exc(exc)}")
        roles: list = []
        try:
            roles = list(conn.identity.roles())
        except Exception as exc:
            _logger.warning("identity summary partial: roles failed: %s", exc, exc_info=True)
            partial = True
            partial_reasons.append(f"roles:{_classify_exc(exc)}")
        groups: list = []
        try:
            groups = list(conn.identity.groups(limit=500))
        except Exception:
            pass
        domains: list = []
        try:
            domains = list(conn.identity.domains(limit=50))
        except Exception:
            pass

        recent_enabled = sum(1 for u in users if getattr(u, "is_enabled", True))

        def _sort_key(obj):
            val = getattr(obj, "created_at", None)
            return val if isinstance(val, str) else ""

        recent_users_raw = sorted(users, key=_sort_key, reverse=True)[:5]
        recent_projects_raw = sorted(projects, key=_sort_key, reverse=True)[:5]

        counts = {
            "users": len(users),
            "users_enabled": recent_enabled,
            "projects": len(projects),
            "roles": len(roles),
            "groups": len(groups),
            "domains": len(domains),
        }

        return {
            "partial": partial,
            "partial_reasons": partial_reasons,
            "counts": counts,
            # 프론트 IdentitySummary 인터페이스 flat alias
            "user_count": counts["users"],
            "project_count": counts["projects"],
            "role_count": counts["roles"],
            "group_count": counts["groups"],
            "domain_count": counts["domains"],
            "top_roles": [{"id": r.id, "name": r.name} for r in roles[:10]],
            "recent_users": [
                {
                    "id": u.id,
                    "name": getattr(u, "name", ""),
                    "email": getattr(u, "email", "") or "",
                    "enabled": getattr(u, "is_enabled", True),
                }
                for u in recent_users_raw
            ],
            "recent_projects": [
                {
                    "id": p.id,
                    "name": getattr(p, "name", ""),
                    "description": getattr(p, "description", "") or "",
                    "enabled": getattr(p, "is_enabled", True),
                }
                for p in recent_projects_raw
            ],
        }

    try:
        summary = await cached_call(
            "afterglow:admin:identity:summary",
            ttl_slow(),
            _collect,
        )
    except Exception as exc:
        _logger.exception("admin identity summary 조회 실패: %s", exc)
        raise HTTPException(status_code=500, detail="Identity 요약 조회 실패")

    return summary


class SettleTopologyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    native_calls_settled: bool = Field(strict=True)


@router.get("/account-topology/operations", dependencies=[Depends(require_admin)])
async def account_topology_operations(
    cursor: str | None = Query(None, min_length=64, max_length=64), token_info: dict = Depends(get_token_info)
):
    from app.services import account_spaces

    return await account_spaces.topology_operations(token_info, cursor=cursor)


@router.post("/account-topology/shared-domains/{kind}/settle", dependencies=[Depends(require_admin)])
async def settle_shared_account_domain(
    kind: str, req: SettleTopologyRequest, token_info: dict = Depends(get_token_info)
):
    from app.services import account_spaces

    return await account_spaces.settle_shared_domain(kind, token_info, native_calls_settled=req.native_calls_settled)


@router.post("/account-topology/personal-projects/{operation_id}/settle", dependencies=[Depends(require_admin)])
async def settle_personal_account_project(
    operation_id: str, req: SettleTopologyRequest, token_info: dict = Depends(get_token_info)
):
    from app.services import account_spaces

    return await account_spaces.settle_personal_project(
        operation_id, token_info, native_calls_settled=req.native_calls_settled
    )
