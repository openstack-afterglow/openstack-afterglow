"""관리자 Flavor 관리 엔드포인트."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import openstack
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.common.dashboard import _gpu_count_from_flavor
from app.api.deps import get_os_conn, require_admin
from app.services.cache import invalidate
from app.services.flavor_eligibility import AFTERGLOW_FRONTEND_VISIBLE_SPEC, is_flavor_frontend_visible

_logger = logging.getLogger(__name__)

router = APIRouter()


class CreateFlavorRequest(BaseModel):
    name: str
    vcpus: int
    ram: int  # MB
    disk: int  # GB
    is_public: bool = True
    description: str | None = None


class FlavorAccessRequest(BaseModel):
    project_id: str


class ExtraSpecRequest(BaseModel):
    key: str
    value: str


class FlavorAccessModeRequest(BaseModel):
    mode: Literal["manual", "gpu_quota"]


class FlavorFrontendVisibilityRequest(BaseModel):
    visible: bool


class FlavorAccessReconcileRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    apply: bool = False
    gpu_limits: dict[str, int] | None = None


def _flavor_to_dict(f) -> dict:
    extra_specs = {}
    try:
        if hasattr(f, "extra_specs") and f.extra_specs:
            extra_specs = dict(f.extra_specs)
    except Exception:
        pass
    gpu_count = _gpu_count_from_flavor(f.name or "", extra_specs)
    return {
        "id": f.id,
        "name": f.name or "",
        "vcpus": f.vcpus,
        "ram": f.ram,
        "disk": f.disk,
        "is_public": getattr(f, "is_public", True),
        "description": getattr(f, "description", None) or "",
        "extra_specs": extra_specs,
        "is_gpu": gpu_count > 0,
        "gpu_count": gpu_count,
        "frontend_visible": is_flavor_frontend_visible(f),
    }


@router.get("/flavors", dependencies=[Depends(require_admin)])
async def list_admin_flavors(
    limit: int = Query(default=20, ge=1, le=1000),
    marker: str | None = Query(default=None),
    is_public: bool | None = Query(default=None),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """전체 flavor 목록 (공개+비공개)."""

    def _list():
        kwargs: dict = {"details": True}
        if is_public is not None:
            kwargs["is_public"] = is_public
        else:
            kwargs["is_public"] = None  # 모든 flavor 조회
        if marker:
            kwargs["marker"] = marker
        flavors = list(conn.compute.flavors(**kwargs))
        items = [_flavor_to_dict(f) for f in flavors[:limit]]
        next_marker = items[-1]["id"] if len(items) == limit else None
        return {"items": items, "next_marker": next_marker, "count": len(items)}

    try:
        return await asyncio.to_thread(_list)
    except Exception:
        raise HTTPException(status_code=500, detail="Flavor 목록 조회 실패")


@router.post("/flavors", dependencies=[Depends(require_admin)], status_code=201)
async def create_flavor(
    req: CreateFlavorRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """Flavor 생성."""

    def _create():
        try:
            flavor = conn.compute.create_flavor(
                name=req.name,
                vcpus=req.vcpus,
                ram=req.ram,
                disk=req.disk,
                is_public=req.is_public,
                description=req.description,
            )
            return _flavor_to_dict(flavor)
        except Exception as e:
            _logger.warning("Flavor 생성 실패: %s", e)

            raise HTTPException(status_code=400, detail="Flavor 생성 실패")

    try:
        return await asyncio.to_thread(_create)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Flavor 생성 실패")


@router.delete("/flavors/{flavor_id}", dependencies=[Depends(require_admin)], status_code=204)
async def delete_flavor(
    flavor_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """Flavor 삭제."""

    def _delete():
        try:
            conn.compute.delete_flavor(flavor_id, ignore_missing=True)
        except Exception as e:
            _logger.warning("Flavor 삭제 실패: %s", e)

            raise HTTPException(status_code=404, detail="Flavor 삭제 실패")

    try:
        await asyncio.to_thread(_delete)
    except HTTPException:
        raise


def _strict_flavor_access_ids(conn, flavor_id: str) -> set[str]:
    endpoint = conn.compute.get_endpoint()
    resp = conn.session.get(f"{endpoint}/flavors/{flavor_id}/os-flavor-access")
    resp.raise_for_status()
    return {
        str(item.get("tenant_id") or item.get("project_id"))
        for item in resp.json().get("flavor_access", [])
        if item.get("tenant_id") or item.get("project_id")
    }


@router.put("/flavors/{flavor_id}/access-mode", dependencies=[Depends(require_admin)])
async def set_flavor_access_mode(
    flavor_id: str,
    req: FlavorAccessModeRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """Mark a private GPU flavor as manually or quota managed."""
    from app.services.flavor_eligibility import parse_gpu_demand

    def _set():
        flavor = conn.compute.get_flavor(flavor_id)
        if flavor is None:
            raise HTTPException(status_code=404, detail="Flavor를 찾을 수 없습니다")
        if getattr(flavor, "is_public", True):
            raise HTTPException(status_code=409, detail="Public Flavor는 quota 연동 access를 사용할 수 없습니다")
        if req.mode == "gpu_quota" and not parse_gpu_demand(flavor):
            raise HTTPException(status_code=409, detail="GPU 요청 extra spec이 없는 Flavor입니다")
        conn.compute.create_flavor_extra_specs(
            flavor_id,
            {"afterglow:access_mode": req.mode},
        )
        return {"flavor_id": flavor_id, "mode": req.mode}

    try:
        return await asyncio.to_thread(_set)
    except HTTPException:
        raise
    except Exception as exc:
        _logger.warning("Flavor access mode 저장 실패: %s", exc)
        raise HTTPException(status_code=400, detail="Flavor access mode 저장 실패") from exc


@router.put("/flavors/{flavor_id}/frontend-visibility", dependencies=[Depends(require_admin)])
async def set_flavor_frontend_visibility(
    flavor_id: str,
    req: FlavorFrontendVisibilityRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """Control ordinary Afterglow flavor discovery without changing Nova access."""

    def _set():
        flavor = conn.compute.get_flavor(flavor_id)
        if flavor is None:
            raise HTTPException(status_code=404, detail="Flavor를 찾을 수 없습니다")
        value = "true" if req.visible else "false"
        conn.compute.create_flavor_extra_specs(
            flavor_id,
            {AFTERGLOW_FRONTEND_VISIBLE_SPEC: value},
        )
        return {"flavor_id": flavor_id, "frontend_visible": req.visible}

    try:
        result = await asyncio.to_thread(_set)
        await invalidate("afterglow:nova:*:flavors")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        _logger.warning("Afterglow Flavor 노출 설정 실패: %s", exc)
        raise HTTPException(status_code=400, detail="Afterglow Flavor 노출 설정 실패") from exc


@router.post("/flavors/access-reconcile", dependencies=[Depends(require_admin)])
async def reconcile_quota_managed_flavor_access(
    req: FlavorAccessReconcileRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """Preview or apply target-project access implied by configured GPU limits."""
    from app.services.flavor_eligibility import parse_gpu_demand
    from app.services.gpu_quota import get_effective_gpu_quotas

    try:
        effective = await get_effective_gpu_quotas(conn, req.project_id)
        if req.gpu_limits:
            from app.services.gpu_quota import normalize_gpu_alias

            effective.update(
                {
                    normalized: limit
                    for alias, limit in req.gpu_limits.items()
                    if (normalized := normalize_gpu_alias(alias)) and limit >= -1
                }
            )
        flavors = await asyncio.to_thread(lambda: list(conn.compute.flavors(details=True, is_public=None)))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Flavor access 정책을 계산할 수 없습니다") from exc

    operations: list[dict] = []
    errors: list[dict] = []
    for flavor in flavors:
        details = _flavor_to_dict(flavor)
        if details["extra_specs"].get("afterglow:access_mode") != "gpu_quota":
            continue
        if details["is_public"]:
            errors.append(
                {
                    "flavor_id": details["id"],
                    "flavor_name": details["name"],
                    "code": "managed_flavor_is_public",
                }
            )
            continue
        demand = parse_gpu_demand(details)
        if not demand:
            errors.append(
                {
                    "flavor_id": details["id"],
                    "flavor_name": details["name"],
                    "code": "managed_flavor_has_no_gpu_demand",
                }
            )
            continue
        try:
            access_ids = await asyncio.to_thread(
                _strict_flavor_access_ids,
                conn,
                details["id"],
            )
        except Exception:
            errors.append(
                {
                    "flavor_id": details["id"],
                    "flavor_name": details["name"],
                    "code": "flavor_access_unavailable",
                }
            )
            continue
        desired = all(
            effective.get(alias, 0) == -1 or effective.get(alias, 0) >= amount for alias, amount in demand.items()
        )
        present = req.project_id in access_ids
        action = "add" if desired and not present else "remove" if present and not desired else "none"
        operation = {
            "flavor_id": details["id"],
            "flavor_name": details["name"],
            "gpu_demand": demand,
            "desired_access": desired,
            "current_access": present,
            "action": action,
        }
        operations.append(operation)
        if not req.apply or action == "none":
            continue
        try:
            endpoint = conn.compute.get_endpoint()
            payload = (
                {"addTenantAccess": {"tenant": req.project_id}}
                if action == "add"
                else {"removeTenantAccess": {"tenant": req.project_id}}
            )
            response = await asyncio.to_thread(
                conn.session.post,
                f"{endpoint}/flavors/{details['id']}/action",
                json=payload,
            )
            response.raise_for_status()
            operation["applied"] = True
        except Exception:
            operation["applied"] = False
            errors.append(
                {
                    "flavor_id": details["id"],
                    "flavor_name": details["name"],
                    "code": "flavor_access_apply_failed",
                    "action": action,
                }
            )

    if req.apply:
        await invalidate(f"afterglow:nova:{req.project_id}:flavors")
    return {
        "project_id": req.project_id,
        "applied": req.apply,
        "status": "partial" if errors else "ok",
        "operations": operations,
        "errors": errors,
        "enforcement_scope": "afterglow_admissions_only",
    }


@router.get("/flavors/{flavor_id}/access", dependencies=[Depends(require_admin)])
async def list_flavor_access(
    flavor_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """Flavor 접근 권한이 있는 프로젝트 목록 (프로젝트 이름 포함)."""

    def _list():
        try:
            endpoint = conn.compute.get_endpoint()
            resp = conn.session.get(f"{endpoint}/flavors/{flavor_id}/os-flavor-access")
            if resp.status_code in (404, 403):
                return []
            if resp.status_code == 409:
                # public flavor — no access list
                return []
            accesses = resp.json().get("flavor_access", [])
            result = []
            for a in accesses:
                pid = a.get("tenant_id") or a.get("project_id") or ""
                project_name = ""
                try:
                    proj = conn.identity.get_project(pid)
                    project_name = proj.name or ""
                except Exception:
                    pass
                result.append(
                    {
                        "flavor_id": a.get("flavor_id", flavor_id),
                        "project_id": pid,
                        "project_name": project_name,
                    }
                )
            return result
        except Exception as e:
            _logger.warning("Flavor 접근 목록 조회 실패 (flavor_id=%s): %s", flavor_id, e)
            return []

    try:
        return await asyncio.to_thread(_list)
    except HTTPException:
        raise


@router.post("/flavors/{flavor_id}/extra-specs", dependencies=[Depends(require_admin)])
async def set_flavor_extra_spec(
    flavor_id: str,
    req: ExtraSpecRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """Flavor extra_spec 추가/수정."""

    def _set():
        try:
            conn.compute.create_flavor_extra_specs(flavor_id, {req.key: req.value})
            return {"key": req.key, "value": req.value}
        except Exception as e:
            _logger.warning("extra_spec 설정 실패: %s", e)

            raise HTTPException(status_code=400, detail="extra_spec 설정 실패")

    try:
        return await asyncio.to_thread(_set)
    except HTTPException:
        raise


@router.delete("/flavors/{flavor_id}/extra-specs/{key}", dependencies=[Depends(require_admin)], status_code=204)
async def delete_flavor_extra_spec(
    flavor_id: str,
    key: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """Flavor extra_spec 삭제."""

    def _delete():
        try:
            conn.compute.delete_flavor_extra_specs_property(flavor_id, key)
        except Exception as e:
            _logger.warning("extra_spec 삭제 실패: %s", e)

            raise HTTPException(status_code=404, detail="extra_spec 삭제 실패")

    try:
        await asyncio.to_thread(_delete)
    except HTTPException:
        raise


@router.post("/flavors/{flavor_id}/access", dependencies=[Depends(require_admin)])
async def add_flavor_access(
    flavor_id: str,
    req: FlavorAccessRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """Flavor에 프로젝트 접근 권한 추가 (Nova raw API)."""

    def _add():
        try:
            endpoint = conn.compute.get_endpoint()
            resp = conn.session.post(
                f"{endpoint}/flavors/{flavor_id}/action",
                json={"addTenantAccess": {"tenant": req.project_id}},
            )
            if resp.status_code >= 400:
                raise Exception(f"HTTP {resp.status_code}")
            return {"flavor_id": flavor_id, "project_id": req.project_id}
        except Exception as e:
            _logger.warning("접근 권한 추가 실패: %s", e)

            raise HTTPException(status_code=400, detail="접근 권한 추가 실패")

    try:
        return await asyncio.to_thread(_add)
    except HTTPException:
        raise


@router.delete("/flavors/{flavor_id}/access/{project_id}", dependencies=[Depends(require_admin)], status_code=204)
async def remove_flavor_access(
    flavor_id: str,
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """Flavor에서 프로젝트 접근 권한 제거 (Nova raw API)."""

    def _remove():
        try:
            endpoint = conn.compute.get_endpoint()
            resp = conn.session.post(
                f"{endpoint}/flavors/{flavor_id}/action",
                json={"removeTenantAccess": {"tenant": project_id}},
            )
            if resp.status_code >= 400:
                raise Exception(f"HTTP {resp.status_code}")
        except Exception as e:
            _logger.warning("접근 권한 제거 실패: %s", e)

            raise HTTPException(status_code=404, detail="접근 권한 제거 실패")

    try:
        await asyncio.to_thread(_remove)
    except HTTPException:
        raise
