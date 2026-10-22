"""관리자 Flavor 관리 엔드포인트."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_admin_os_conn, require_admin
from app.services.cache import invalidate
from app.services.flavor_eligibility import (
    AFTERGLOW_FRONTEND_VISIBLE_SPEC,
    is_flavor_frontend_visible,
    parse_gpu_demand,
)

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


class FlavorFrontendVisibilityRequest(BaseModel):
    visible: bool


def _flavor_to_dict(f) -> dict:
    extra_specs = {}
    try:
        if hasattr(f, "extra_specs") and f.extra_specs:
            extra_specs = dict(f.extra_specs)
    except Exception:
        pass
    gpu_count = sum(parse_gpu_demand({"name": f.name or "", "extra_specs": extra_specs}).values())
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
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
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
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
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
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
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


@router.put("/flavors/{flavor_id}/frontend-visibility", dependencies=[Depends(require_admin)])
async def set_flavor_frontend_visibility(
    flavor_id: str,
    req: FlavorFrontendVisibilityRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
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


@router.get("/flavors/{flavor_id}/access", dependencies=[Depends(require_admin)])
async def list_flavor_access(
    flavor_id: str,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """Flavor 접근 권한이 있는 프로젝트 목록 (프로젝트 이름 포함)."""

    def _list():
        try:
            endpoint = conn.compute.get_endpoint()
            resp = conn.session.get(f"{endpoint}/flavors/{flavor_id}/os-flavor-access")
            if resp.status_code == 409:
                # public flavor — no access list
                return []
            resp.raise_for_status()
            accesses = resp.json().get("flavor_access", [])
            result = []
            for a in accesses:
                pid = a.get("tenant_id") or a.get("project_id") or ""
                project_name = ""
                domain_id = ""
                domain_name = ""
                try:
                    proj = conn.identity.get_project(pid)
                    project_name = proj.name or ""
                    domain_id = proj.domain_id or ""
                    if domain_id:
                        domain_name = conn.identity.get_domain(domain_id).name or ""
                except Exception:
                    pass
                result.append(
                    {
                        "flavor_id": a.get("flavor_id", flavor_id),
                        "project_id": pid,
                        "project_name": project_name,
                        "domain_id": domain_id,
                        "domain_name": domain_name,
                    }
                )
            return result
        except Exception as e:
            _logger.warning("Flavor 접근 목록 조회 실패 (flavor_id=%s): %s", flavor_id, e)
            raise HTTPException(status_code=503, detail="Flavor 접근 목록 조회 실패") from None

    try:
        return await asyncio.to_thread(_list)
    except HTTPException:
        raise


@router.post("/flavors/{flavor_id}/extra-specs", dependencies=[Depends(require_admin)])
async def set_flavor_extra_spec(
    flavor_id: str,
    req: ExtraSpecRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
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
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
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
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
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
        result = await asyncio.to_thread(_add)
        await invalidate(f"afterglow:nova:{req.project_id}:flavors")
        return result
    except HTTPException:
        raise


@router.delete("/flavors/{flavor_id}/access/{project_id}", dependencies=[Depends(require_admin)], status_code=204)
async def remove_flavor_access(
    flavor_id: str,
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
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
        await invalidate(f"afterglow:nova:{project_id}:flavors")
    except HTTPException:
        raise
