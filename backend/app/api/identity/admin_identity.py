"""관리자 Identity 관리 엔드포인트 (사용자, 프로젝트, 쿼터, 그룹, 역할)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import CacheMode, cache_mode, get_os_conn, get_token_info, require_admin
from app.services import activity, keystone, session_store
from app.services import login_guard as _login_guard
from app.services.cache import cached_call, invalidate, ttl_slow

_logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Users
# ============================================================================


class CreateUserRequest(BaseModel):
    name: str
    email: str | None = None
    password: str | None = None
    enabled: bool = True
    domain_id: str | None = None


class UpdateUserRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    enabled: bool | None = None
    password: str | None = None


@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users(
    limit: int = Query(default=20, ge=1, le=100),
    marker: str | None = Query(default=None),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """사용자 목록 (페이지네이션).

    Keystone은 created_at을 제공하지 않으므로 ActivityLog 기반 최초/최근 활동일로 대체한다.
    (per-user Keystone GET 폴백은 항상 None을 반환하는 낭비 왕복이므로 제거됨)
    """

    def _list():
        kwargs: dict = {"limit": limit}
        if marker:
            kwargs["marker"] = marker
        users = []
        for u in conn.identity.users(**kwargs):
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
            if len(users) >= limit:
                break
        next_marker = users[-1]["id"] if len(users) == limit else None
        return {"items": users, "next_marker": next_marker, "count": len(users)}

    try:
        result = await asyncio.to_thread(_list)
    except Exception:
        raise HTTPException(status_code=500, detail="사용자 목록 조회 실패")

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


@router.get("/users/stats", dependencies=[Depends(require_admin)])
async def get_users_stats(
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """사용자 현황 집계 통계 (전체/활성/비활성 수). 통계 카드용."""

    def _stats():
        total = enabled = disabled = 0
        for u in conn.identity.users():
            total += 1
            if u.is_enabled:
                enabled += 1
            else:
                disabled += 1
        return {"total": total, "enabled": enabled, "disabled": disabled}

    try:
        return await asyncio.to_thread(_stats)
    except Exception:
        raise HTTPException(status_code=500, detail="사용자 통계 조회 실패")


@router.get("/users/activity", dependencies=[Depends(require_admin)])
async def get_users_activity(
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(None),
):
    """사용자 변경 로그 (생성·수정·삭제, 시간 역순). 변경 로그 카드용."""
    return await activity.list_user_management_events(limit=limit, before_id=before_id)


@router.post("/users", dependencies=[Depends(require_admin)], status_code=201)
async def create_user(
    req: CreateUserRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """사용자 생성."""

    def _create():
        try:
            kwargs = {"name": req.name, "enabled": req.enabled}
            if req.email:
                kwargs["email"] = req.email
            if req.password:
                kwargs["password"] = req.password
            if req.domain_id:
                kwargs["domain_id"] = req.domain_id
            u = conn.identity.create_user(**kwargs)
            return {
                "id": u.id,
                "name": u.name or "",
                "email": getattr(u, "email", "") or "",
                "enabled": u.is_enabled,
            }
        except Exception as e:
            _logger.warning("사용자 생성 실패: %s", e)

            raise HTTPException(status_code=400, detail="사용자 생성 실패")

    try:
        return await asyncio.to_thread(_create)
    except HTTPException:
        raise


@router.patch("/users/{user_id}", dependencies=[Depends(require_admin)])
async def update_user(
    user_id: str,
    req: UpdateUserRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """사용자 수정."""

    def _update():
        kwargs: dict = {}
        if req.name is not None:
            kwargs["name"] = req.name
        if req.email is not None:
            kwargs["email"] = req.email
        if req.enabled is not None:
            kwargs["enabled"] = req.enabled
        if req.password is not None:
            kwargs["password"] = req.password
        try:
            u = conn.identity.update_user(user_id, **kwargs)
            return {
                "id": u.id,
                "name": u.name or "",
                "email": getattr(u, "email", "") or "",
                "enabled": u.is_enabled,
            }
        except Exception as e:
            _logger.warning("사용자 수정 실패: %s", e)

            raise HTTPException(status_code=400, detail="사용자 수정 실패")

    try:
        return await asyncio.to_thread(_update)
    except HTTPException:
        raise


@router.post("/users/{user_id}/revoke-sessions", dependencies=[Depends(require_admin)])
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


@router.get("/users/{user_id}/sessions", dependencies=[Depends(require_admin)])
async def list_user_sessions_admin(user_id: str):
    """관리자가 특정 사용자의 활성 세션 목록을 조회 (keystone_token 제외)."""
    sessions = await session_store.list_user_sessions(user_id)
    return {"sessions": sessions, "count": len(sessions)}


class UnlockAccountRequest(BaseModel):
    username: str
    domain: str = "Default"


@router.post("/users/unlock-account", dependencies=[Depends(require_admin)])
async def admin_unlock_account(
    req: UnlockAccountRequest,
    token_info: dict = Depends(get_token_info),
):
    """계정 로그인 잠금 강제 해제 (관리자 전용)."""
    await _login_guard.admin_unlock(req.username, req.domain)
    await activity.record(
        project_id=token_info["project_id"],
        user_id=token_info["user_id"],
        username=token_info.get("username", ""),
        resource_type="identity",
        action="account_unlock",
        status="success",
        extra={"target_username": req.username, "domain": req.domain},
    )
    return {"status": "unlocked", "username": req.username, "domain": req.domain}


@router.get("/users/lock-status", dependencies=[Depends(require_admin)])
async def admin_get_lock_status(
    username: str = Query(...),
    domain: str = Query(default="Default"),
):
    """계정 잠금 상태 조회 (관리자 전용)."""
    return await _login_guard.get_lock_status(username, domain)


# ============================================================================
# Projects
# ============================================================================


class CreateProjectRequest(BaseModel):
    name: str
    description: str | None = None
    domain_id: str | None = None
    enabled: bool = True


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None


@router.get("/projects/names", dependencies=[Depends(require_admin)])
async def list_project_names(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """모든 프로젝트의 id/name 목록 (페이지네이션 없이)."""

    def _list():
        return [{"id": p.id, "name": p.name or ""} for p in conn.identity.projects()]

    try:
        return await cached_call(
            "afterglow:admin:project_names", ttl_slow(), _list, enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        raise HTTPException(status_code=500, detail="프로젝트 이름 목록 조회 실패")


@router.get("/projects", dependencies=[Depends(require_admin)])
async def list_projects(
    limit: int = Query(default=20, ge=1, le=100),
    marker: str | None = Query(default=None),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """프로젝트 목록 (페이지네이션)."""

    def _list():
        kwargs: dict = {"limit": limit}
        if marker:
            kwargs["marker"] = marker
        projects = []
        for p in conn.identity.projects(**kwargs):
            created_at = getattr(p, "created_at", None)
            if not created_at:
                try:
                    detail = conn.identity.get_project(p.id)
                    created_at = getattr(detail, "created_at", None)
                except Exception:
                    pass
            projects.append(
                {
                    "id": p.id,
                    "name": p.name or "",
                    "description": getattr(p, "description", "") or "",
                    "enabled": p.is_enabled,
                    "domain_id": getattr(p, "domain_id", None),
                    "created_at": str(created_at) if created_at else None,
                }
            )
            if len(projects) >= limit:
                break
        next_marker = projects[-1]["id"] if len(projects) == limit else None
        return {"items": projects, "next_marker": next_marker, "count": len(projects)}

    try:
        return await asyncio.to_thread(_list)
    except Exception:
        raise HTTPException(status_code=500, detail="프로젝트 목록 조회 실패")


@router.post("/projects", dependencies=[Depends(require_admin)], status_code=201)
async def create_project(
    req: CreateProjectRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """프로젝트 생성."""

    def _create():
        try:
            kwargs = {"name": req.name, "enabled": req.enabled}
            if req.description:
                kwargs["description"] = req.description
            if req.domain_id:
                kwargs["domain_id"] = req.domain_id
            p = conn.identity.create_project(**kwargs)
            return {
                "id": p.id,
                "name": p.name or "",
                "description": getattr(p, "description", "") or "",
                "enabled": p.is_enabled,
            }
        except Exception as e:
            _logger.warning("프로젝트 생성 실패: %s", e)

            raise HTTPException(status_code=400, detail="프로젝트 생성 실패")

    try:
        from app.config import get_settings
        from app.services import neutron

        result = await asyncio.to_thread(_create)
        _settings = get_settings()
        if _settings.monitoring_auto_sg_enabled and _settings.monitoring_scrape_cidr:
            try:
                await asyncio.to_thread(
                    neutron.ensure_node_exporter_sg,
                    conn,
                    result["id"],
                    _settings.node_exporter_sg_name,
                    _settings.monitoring_scrape_cidr,
                )
            except Exception:
                _logger.warning("신규 프로젝트 node_exporter SG 자동 생성 실패, 계속 진행", exc_info=True)
            try:
                await asyncio.to_thread(
                    neutron.ensure_dcgm_exporter_sg,
                    conn,
                    result["id"],
                    _settings.dcgm_exporter_sg_name,
                    _settings.monitoring_scrape_cidr,
                )
            except Exception:
                _logger.warning("신규 프로젝트 dcgm_exporter SG 자동 생성 실패, 계속 진행", exc_info=True)
        return result
    except HTTPException:
        raise


@router.get("/projects/{project_id}", dependencies=[Depends(require_admin)])
async def get_project(
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
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
            raise HTTPException(status_code=404, detail="프로젝트 조회 실패")

    try:
        return await asyncio.to_thread(_get)
    except HTTPException:
        raise


@router.patch("/projects/{project_id}", dependencies=[Depends(require_admin)])
async def update_project(
    project_id: str,
    req: UpdateProjectRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
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

            raise HTTPException(status_code=400, detail="프로젝트 수정 실패")

    try:
        return await asyncio.to_thread(_update)
    except HTTPException:
        raise


@router.delete("/projects/{project_id}", dependencies=[Depends(require_admin)], status_code=204)
async def delete_project(
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """프로젝트 삭제."""

    def _delete():
        try:
            conn.identity.delete_project(project_id, ignore_missing=True)
        except Exception as e:
            _logger.warning("프로젝트 삭제 실패: %s", e)

            raise HTTPException(status_code=400, detail="프로젝트 삭제 실패")

    try:
        await asyncio.to_thread(_delete)
    except HTTPException:
        raise


@router.get("/projects/{project_id}/members", dependencies=[Depends(require_admin)])
async def list_project_members(
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """프로젝트의 사용자-역할 할당 목록 조회."""

    def _list():
        try:
            import re as _re

            raw_ep = conn.session.get_endpoint(service_type="identity", interface="public").rstrip("/")
            # /v3 또는 /v3/{project_id}를 제거 후 명시적으로 /v3 추가
            base_ep = _re.sub(r"/v[0-9.]+(?:/[a-f0-9\-]+)?$", "", raw_ep)
            endpoint = base_ep + "/v3"
            resp = conn.session.get(
                f"{endpoint}/role_assignments",
                params={"scope.project.id": project_id, "include_names": "true"},
            )
            raw = resp.json().get("role_assignments", [])
            assignments = []
            for ra in raw:
                user = ra.get("user", {})
                group = ra.get("group", {})
                role = ra.get("role", {})
                if user.get("id"):
                    assignments.append(
                        {
                            "user_id": user["id"],
                            "user_name": user.get("name", ""),
                            "role_id": role.get("id", ""),
                            "role_name": role.get("name", ""),
                            "type": "user",
                        }
                    )
                elif group.get("id"):
                    assignments.append(
                        {
                            "user_id": f"group:{group['id']}",
                            "user_name": f"[그룹] {group.get('name', '')}",
                            "role_id": role.get("id", ""),
                            "role_name": role.get("name", ""),
                            "type": "group",
                            "group_id": group["id"],
                        }
                    )
            return assignments
        except Exception as e:
            _logger.warning("멤버 목록 조회 실패: %s", e)

            raise HTTPException(status_code=500, detail="멤버 목록 조회 실패")

    try:
        return await asyncio.to_thread(_list)
    except HTTPException:
        raise


# ============================================================================
# Quotas
# ============================================================================


class QuotaUpdateRequest(BaseModel):
    instances: int | None = None
    cores: int | None = None
    ram: int | None = None
    volumes: int | None = None
    gigabytes: int | None = None


class ComputePolicyUpdateRequest(QuotaUpdateRequest):
    gpu_quotas: dict[str, int | None] = Field(default_factory=dict)
    reconcile_flavor_access: bool = True


@router.put("/compute-policy/{project_id}", dependencies=[Depends(require_admin)])
async def update_project_compute_policy(
    project_id: str,
    req: ComputePolicyUpdateRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """Apply staged Nova compute and Afterglow GPU policy, then reconcile managed access."""
    from app.api.identity.admin_flavors import (
        FlavorAccessReconcileRequest,
        reconcile_quota_managed_flavor_access,
    )
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
    try:
        if compute_kwargs:
            await asyncio.to_thread(
                conn.compute.update_quota_set,
                project_id,
                **compute_kwargs,
            )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Compute quota 수정 실패") from exc

    errors: list[dict] = []
    for gpu_type, limit in req.gpu_quotas.items():
        try:
            if limit is None:
                await delete_project_gpu_quota(conn, project_id, gpu_type)
            else:
                await set_project_gpu_quota(conn, project_id, gpu_type, limit)
        except Exception:
            errors.append({"gpu_type": gpu_type, "code": "gpu_quota_apply_failed"})

    reconcile = None
    if req.reconcile_flavor_access:
        reconcile = await reconcile_quota_managed_flavor_access(
            FlavorAccessReconcileRequest(project_id=project_id, apply=True),
            conn,
        )
        errors.extend(reconcile.get("errors", []))

    await invalidate(f"afterglow:nova:{project_id}:flavors")
    await invalidate(f"afterglow:dashboard:{project_id}:quotas")
    return {
        "project_id": project_id,
        "status": "partial" if errors else "ok",
        "errors": errors,
        "access_reconcile": reconcile,
        "enforcement_scope": "afterglow_admissions_only",
    }


@router.get("/quotas/{project_id}", dependencies=[Depends(require_admin)])
async def get_project_quotas(
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """프로젝트 쿼터 조회 (Compute + Volume, 실제 사용량 포함)."""

    def _get():
        result: dict = {"compute": {}, "volume": {}}
        compute_endpoint = conn.compute.get_endpoint()
        bs_endpoint = conn.block_storage.get_endpoint()
        try:
            cq = conn.session.get(f"{compute_endpoint}/os-quota-sets/{project_id}/detail")
            qs = cq.json().get("quota_set", {})
            for key in ("instances", "cores", "ram"):
                q = qs.get(key, {})
                result["compute"][key] = {"limit": q.get("limit", 0), "in_use": q.get("in_use", 0)}
        except Exception:
            result["compute"] = {}
        try:
            bq = conn.session.get(f"{bs_endpoint}/os-quota-sets/{project_id}", params={"usage": "true"})
            bqs = bq.json().get("quota_set", {})
            for key in ("volumes", "gigabytes"):
                q = bqs.get(key, {})
                if isinstance(q, dict):
                    result["volume"][key] = {"limit": q.get("limit", 0), "in_use": q.get("in_use", 0)}
                else:
                    result["volume"][key] = {"limit": q, "in_use": 0}
        except Exception:
            result["volume"] = {}
        return result

    try:
        return await asyncio.to_thread(_get)
    except Exception:
        raise HTTPException(status_code=500, detail="쿼터 조회 실패")


@router.put("/quotas/{project_id}", dependencies=[Depends(require_admin)])
async def update_project_quotas(
    project_id: str,
    req: QuotaUpdateRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """프로젝트 쿼터 수정."""

    def _update():
        try:
            # Compute quotas
            compute_kwargs: dict = {}
            if req.instances is not None:
                compute_kwargs["instances"] = req.instances
            if req.cores is not None:
                compute_kwargs["cores"] = req.cores
            if req.ram is not None:
                compute_kwargs["ram"] = req.ram
            if compute_kwargs:
                conn.compute.update_quota_set(project_id, **compute_kwargs)

            # Volume quotas
            volume_kwargs: dict = {}
            if req.volumes is not None:
                volume_kwargs["volumes"] = req.volumes
            if req.gigabytes is not None:
                volume_kwargs["gigabytes"] = req.gigabytes
            if volume_kwargs:
                conn.block_storage.update_quota_set(project_id, **volume_kwargs)

            return {"status": "updated"}
        except Exception as e:
            _logger.warning("쿼터 수정 실패: %s", e)

            raise HTTPException(status_code=400, detail="쿼터 수정 실패")

    try:
        return await asyncio.to_thread(_update)
    except HTTPException:
        raise


# ============================================================================
# Groups
# ============================================================================


@router.get("/groups", dependencies=[Depends(require_admin)])
async def list_groups(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """그룹 목록."""

    def _list():
        groups = []
        try:
            for g in conn.identity.groups():
                groups.append(
                    {
                        "id": g.id,
                        "name": g.name or "",
                        "description": getattr(g, "description", "") or "",
                        "domain_id": getattr(g, "domain_id", None),
                    }
                )
        except Exception:
            pass
        return groups

    try:
        return await cached_call("afterglow:admin:groups", ttl_slow(), _list, enabled=cm.enabled, refresh=cm.refresh)
    except Exception:
        raise HTTPException(status_code=500, detail="그룹 목록 조회 실패")


class CreateGroupRequest(BaseModel):
    name: str
    description: str | None = None
    domain_id: str | None = None


class UpdateGroupRequest(BaseModel):
    name: str | None = None
    description: str | None = None


@router.post("/groups", dependencies=[Depends(require_admin)], status_code=201)
async def create_group(
    req: CreateGroupRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """그룹 생성."""

    def _create():
        try:
            kwargs = {"name": req.name}
            if req.description:
                kwargs["description"] = req.description
            if req.domain_id:
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

            raise HTTPException(status_code=400, detail="그룹 생성 실패")

    try:
        result = await asyncio.to_thread(_create)
        await invalidate("afterglow:admin:groups")
        return result
    except HTTPException:
        raise


@router.patch("/groups/{group_id}", dependencies=[Depends(require_admin)])
async def update_group(
    group_id: str,
    req: UpdateGroupRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """그룹 수정."""

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

            raise HTTPException(status_code=400, detail="그룹 수정 실패")

    try:
        return await asyncio.to_thread(_update)
    except HTTPException:
        raise


@router.delete("/groups/{group_id}", dependencies=[Depends(require_admin)], status_code=204)
async def delete_group(
    group_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """그룹 삭제."""

    def _delete():
        try:
            conn.identity.delete_group(group_id, ignore_missing=True)
        except Exception as e:
            _logger.warning("그룹 삭제 실패: %s", e)

            raise HTTPException(status_code=400, detail="그룹 삭제 실패")

    try:
        await asyncio.to_thread(_delete)
        await invalidate("afterglow:admin:groups")
    except HTTPException:
        raise


@router.get("/groups/{group_id}/users", dependencies=[Depends(require_admin)])
async def list_group_users(
    group_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
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
                        "enabled": getattr(u, "is_enabled", True),
                    }
                )
        except Exception as e:
            _logger.warning("그룹 멤버 조회 실패: %s", e)

            raise HTTPException(status_code=500, detail="그룹 멤버 조회 실패")
        return users

    try:
        return await asyncio.to_thread(_list)
    except HTTPException:
        raise


@router.put("/groups/{group_id}/users/{user_id}", dependencies=[Depends(require_admin)], status_code=204)
async def add_user_to_group(
    group_id: str,
    user_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """그룹에 사용자 추가."""

    def _add():
        try:
            conn.identity.add_user_to_group(user_id, group_id)
        except Exception as e:
            _logger.warning("그룹 멤버 추가 실패: %s", e)

            raise HTTPException(status_code=400, detail="그룹 멤버 추가 실패")

    try:
        await asyncio.to_thread(_add)
    except HTTPException:
        raise


@router.delete("/groups/{group_id}/users/{user_id}", dependencies=[Depends(require_admin)], status_code=204)
async def remove_user_from_group(
    group_id: str,
    user_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """그룹에서 사용자 제거."""

    def _remove():
        try:
            conn.identity.remove_user_from_group(user_id, group_id)
        except Exception as e:
            _logger.warning("그룹 멤버 제거 실패: %s", e)

            raise HTTPException(status_code=400, detail="그룹 멤버 제거 실패")

    try:
        await asyncio.to_thread(_remove)
        # 그룹 멤버십 변경 시 해당 사용자의 모든 세션 무효화
        await session_store.revoke_user_sessions(user_id)
    except HTTPException:
        raise


# ============================================================================
# Roles
# ============================================================================


@router.get("/roles", dependencies=[Depends(require_admin)])
async def list_roles(conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)):
    """역할 목록."""

    def _list():
        roles = []
        try:
            for r in conn.identity.roles():
                roles.append(
                    {
                        "id": r.id,
                        "name": r.name or "",
                        "domain_id": getattr(r, "domain_id", None),
                    }
                )
        except Exception:
            pass
        return roles

    try:
        return await cached_call("afterglow:admin:roles", ttl_slow(), _list, enabled=cm.enabled, refresh=cm.refresh)
    except Exception:
        raise HTTPException(status_code=500, detail="역할 목록 조회 실패")


class AssignRoleRequest(BaseModel):
    user_id: str
    project_id: str
    role_id: str


@router.post("/roles/assign", dependencies=[Depends(require_admin)])
async def assign_role(
    req: AssignRoleRequest,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """역할 할당."""

    def _assign():
        try:
            conn.identity.assign_project_role_to_user(req.project_id, req.user_id, req.role_id)
            return {"status": "assigned"}
        except Exception as e:
            _logger.warning("역할 할당 실패: %s", e)
            raise HTTPException(status_code=400, detail="역할 할당 실패")

    try:
        result = await asyncio.to_thread(_assign)
    except HTTPException:
        raise

    _, admin_role_id = await asyncio.to_thread(keystone._resolve_admin_ids)
    is_admin_role = admin_role_id is not None and req.role_id == admin_role_id
    if is_admin_role:
        await session_store.revoke_user_sessions(req.user_id)
    await activity.record(
        project_id=token_info["project_id"],
        user_id=token_info["user_id"],
        username=token_info.get("username", ""),
        resource_type="identity",
        action="admin_role_grant" if is_admin_role else "role_grant",
        status="success",
        resource_id=req.user_id,
        extra={"role_id": req.role_id, "target_project_id": req.project_id},
    )
    return result


@router.delete("/roles/assign", dependencies=[Depends(require_admin)])
async def revoke_role(
    user_id: str = Query(...),
    project_id: str = Query(...),
    role_id: str = Query(...),
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """역할 회수."""

    def _revoke():
        try:
            conn.identity.unassign_project_role_from_user(project_id, user_id, role_id)
            return {"status": "revoked"}
        except Exception as e:
            _logger.warning("역할 회수 실패: %s", e)
            raise HTTPException(status_code=400, detail="역할 회수 실패")

    try:
        result = await asyncio.to_thread(_revoke)
    except HTTPException:
        raise

    _, admin_role_id = await asyncio.to_thread(keystone._resolve_admin_ids)
    is_admin_role = admin_role_id is not None and role_id == admin_role_id
    if is_admin_role:
        await session_store.revoke_user_sessions(user_id)
    await activity.record(
        project_id=token_info["project_id"],
        user_id=token_info["user_id"],
        username=token_info.get("username", ""),
        resource_type="identity",
        action="admin_role_revoke" if is_admin_role else "role_revoke",
        status="success",
        resource_id=user_id,
        extra={"role_id": role_id, "target_project_id": project_id},
    )
    return result


class AssignGroupRoleRequest(BaseModel):
    group_id: str
    project_id: str
    role_id: str


@router.post("/roles/assign-group", dependencies=[Depends(require_admin)])
async def assign_group_role(
    req: AssignGroupRoleRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """그룹에 프로젝트 역할 할당."""

    def _assign():
        try:
            conn.identity.assign_project_role_to_group(req.project_id, req.group_id, req.role_id)
            return {"status": "assigned"}
        except Exception as e:
            _logger.warning("그룹 역할 할당 실패: %s", e)

            raise HTTPException(status_code=400, detail="그룹 역할 할당 실패")

    try:
        return await asyncio.to_thread(_assign)
    except HTTPException:
        raise


@router.delete("/roles/assign-group", dependencies=[Depends(require_admin)])
async def revoke_group_role(
    group_id: str = Query(...),
    project_id: str = Query(...),
    role_id: str = Query(...),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """그룹에서 프로젝트 역할 회수."""

    def _revoke():
        try:
            conn.identity.unassign_project_role_from_group(project_id, group_id, role_id)
            return {"status": "revoked"}
        except Exception as e:
            _logger.warning("그룹 역할 회수 실패: %s", e)

            raise HTTPException(status_code=400, detail="그룹 역할 회수 실패")

    try:
        return await asyncio.to_thread(_revoke)
    except HTTPException:
        raise


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
            _, admin_role_id = keystone._resolve_admin_ids()
            if not admin_role_id:
                return []
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
        except Exception as e:
            _logger.warning("system role 목록 조회 실패: %s", e)
            raise HTTPException(status_code=500, detail="system role 목록 조회 실패")

    return await asyncio.to_thread(_list)


@router.post("/identity/system-roles/grant", dependencies=[Depends(require_admin)])
async def grant_system_role(
    req: SystemRoleRequest,
    token_info: dict = Depends(get_token_info),
):
    """사용자에게 Keystone system:all admin role 부여."""

    def _grant():
        try:
            _, admin_role_id = keystone._resolve_admin_ids()
            if not admin_role_id:
                raise HTTPException(status_code=500, detail="admin role ID 조회 실패")
            ks = keystone._get_admin_ks_client()
            ks.roles.grant(role=admin_role_id, user=req.user_id, system="all")
            return {"status": "granted"}
        except HTTPException:
            raise
        except Exception as e:
            _logger.warning("system role grant 실패: %s", e)
            raise HTTPException(status_code=500, detail="system role grant 실패")

    result = await asyncio.to_thread(_grant)
    await session_store.revoke_user_sessions(req.user_id)
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
async def revoke_system_role(
    req: SystemRoleRequest,
    token_info: dict = Depends(get_token_info),
):
    """사용자로부터 Keystone system:all admin role 회수."""

    def _revoke():
        try:
            _, admin_role_id = keystone._resolve_admin_ids()
            if not admin_role_id:
                raise HTTPException(status_code=500, detail="admin role ID 조회 실패")
            ks = keystone._get_admin_ks_client()
            assignments = ks.role_assignments.list(role=admin_role_id, system="all")
            current_admins = [a.user["id"] for a in assignments if hasattr(a, "user")]
            if len(current_admins) <= 1 and req.user_id in current_admins:
                raise HTTPException(status_code=422, detail="마지막 system admin은 회수할 수 없습니다")
            ks.roles.revoke(role=admin_role_id, user=req.user_id, system="all")
            return {"status": "revoked"}
        except HTTPException:
            raise
        except Exception as e:
            _logger.warning("system role revoke 실패: %s", e)
            raise HTTPException(status_code=500, detail="system role revoke 실패")

    result = await asyncio.to_thread(_revoke)
    await session_store.revoke_user_sessions(req.user_id)
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
    """호환 모드 상태 + system admin/admin project 멤버 수 반환."""

    def _get():
        from app.config import get_settings

        settings = get_settings()
        legacy_compat = settings.admin_legacy_project_policy
        try:
            admin_project_id, admin_role_id = keystone._resolve_admin_ids()
            ks = keystone._get_admin_ks_client()
            if admin_role_id:
                sys_assignments = ks.role_assignments.list(role=admin_role_id, system="all")
                system_admin_count = len([a for a in sys_assignments if hasattr(a, "user")])
            else:
                system_admin_count = 0
            if admin_role_id and admin_project_id:
                proj_assignments = ks.role_assignments.list(role=admin_role_id, project=admin_project_id)
                admin_project_member_count = len([a for a in proj_assignments if hasattr(a, "user")])
            else:
                admin_project_member_count = 0
        except Exception as e:
            _logger.warning("security-policy 조회 실패: %s", e)
            system_admin_count = 0
            admin_project_member_count = 0
        return {
            "legacy_compat": legacy_compat,
            "system_admin_count": system_admin_count,
            "admin_project_member_count": admin_project_member_count,
        }

    return await asyncio.to_thread(_get)


@router.post("/identity/system-roles/migrate-from-project", dependencies=[Depends(require_admin)])
async def migrate_from_project(token_info: dict = Depends(get_token_info)):
    """admin project 멤버 중 system admin이 아닌 사용자에게 system:all admin role 일괄 부여."""

    def _migrate():
        try:
            admin_project_id, admin_role_id = keystone._resolve_admin_ids()
            if not admin_role_id or not admin_project_id:
                raise HTTPException(status_code=500, detail="admin role/project ID 조회 실패")
            ks = keystone._get_admin_ks_client()
            sys_assignments = ks.role_assignments.list(role=admin_role_id, system="all")
            system_admin_ids = {a.user["id"] for a in sys_assignments if hasattr(a, "user")}
            proj_assignments = ks.role_assignments.list(role=admin_role_id, project=admin_project_id)
            project_member_ids = [a.user["id"] for a in proj_assignments if hasattr(a, "user")]
            migrated = 0
            skipped = 0
            errors = []
            grant_uids = []
            for uid in project_member_ids:
                if uid in system_admin_ids:
                    skipped += 1
                else:
                    try:
                        ks.roles.grant(role=admin_role_id, user=uid, system="all")
                        migrated += 1
                        grant_uids.append(uid)
                    except Exception as e:
                        errors.append({"user_id": uid, "reason": str(e)})
            return {"migrated": migrated, "skipped": skipped, "errors": errors, "_grant_uids": grant_uids}
        except HTTPException:
            raise
        except Exception as e:
            _logger.warning("migrate-from-project 실패: %s", e)
            raise HTTPException(status_code=500, detail="마이그레이션 실패")

    result = await asyncio.to_thread(_migrate)
    grant_uids = result.pop("_grant_uids", [])
    for uid in grant_uids:
        await session_store.revoke_user_sessions(uid)
        await activity.record(
            project_id=token_info["project_id"],
            user_id=token_info["user_id"],
            username=token_info.get("username", ""),
            resource_type="identity",
            action="admin_system_role_grant",
            status="success",
            resource_id=uid,
        )
    return result


# ============================================================================
# Monitoring SG 동기화
# ============================================================================


@router.post("/projects/{project_id}/sync-monitoring-sg", dependencies=[Depends(require_admin)])
async def sync_monitoring_sg(
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
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
    conn: openstack.connection.Connection = Depends(get_os_conn),
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
