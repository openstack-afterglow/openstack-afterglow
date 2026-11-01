"""관리자 Flavor 관리 엔드포인트."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack
import asyncio
import copy
import functools
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from openstack.exceptions import ResourceNotFound
from pydantic import BaseModel, ConfigDict, StrictBool

from app.api.deps import get_admin_os_conn, require_admin
from app.models.compute import CPU_CONTROL_SPEC
from app.services import compute_pools, flavor_automation_policy, identity_roles
from app.services.cache import invalidate
from app.services.flavor_eligibility import (
    AFTERGLOW_FRONTEND_VISIBLE_SPEC,
    is_flavor_frontend_visible,
    parse_gpu_demand,
)
from app.services.flavor_presentation import canonical_cpu_display_name
from app.services.instance_usage import requires_schedule
from app.services.nova import flavor_extra_specs, native_flavor_extra_specs

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


class FlavorUsageScheduleRequirementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: StrictBool


_USAGE_SCHEDULE_SPEC = "afterglow:usage_schedule_required"
_CPU_CONTROL_SPEC = CPU_CONTROL_SPEC


def _is_managed_flavor(extra_specs, description):
    return extra_specs.get("afterglow:managed_by") == "domain-compute-v1" or (
        isinstance(description, str) and description.startswith("afterglow:domain-compute-v1:")
    )


def _flavor_to_dict(f, compute=None) -> dict:
    verified_specs = None
    try:
        verified_specs = flavor_extra_specs(compute, f)
    except Exception:
        # Presentation uncertainty must not turn an SDK's absent-field default into CPU proof.
        pass
    extra_specs = verified_specs if verified_specs is not None else {}
    description = getattr(f, "description", None) or ""
    managed = _is_managed_flavor(extra_specs, description)
    gpu_count = None if managed else sum(parse_gpu_demand({"name": f.name or "", "extra_specs": extra_specs}).values())
    return {
        "id": f.id,
        "name": f.name or "",
        "display_name": canonical_cpu_display_name(f.name, f.vcpus, f.ram, verified_specs),
        "vcpus": f.vcpus,
        "ram": f.ram,
        "disk": f.disk,
        "is_public": getattr(f, "is_public", True),
        "description": description,
        "extra_specs": {key: value for key, value in extra_specs.items() if key != _CPU_CONTROL_SPEC},
        "cpu_automation_managed": _CPU_CONTROL_SPEC in extra_specs,
        "is_gpu": gpu_count > 0 if gpu_count is not None else None,
        "gpu_count": gpu_count,
        **({"gpu_primary_aliases": None} if managed else {}),
        "frontend_visible": is_flavor_frontend_visible({"extra_specs": extra_specs}),
        "usage_schedule_required": requires_schedule(
            {"name": f.name, "vcpus": f.vcpus, "ram": f.ram, "extra_specs": extra_specs}
        ),
    }


async def _approved_gpu_projection(item, capabilities):
    specs = item["extra_specs"]
    if specs.get("afterglow:managed_by") != "domain-compute-v1":
        return
    item.update(await compute_pools.approved_gpu_projection(specs, capabilities))


async def _require_manual_flavor(conn, flavor_id: str):
    """Managed specifications and ACLs have one reconciliation owner."""

    def check():
        flavor = conn.compute.get_flavor(flavor_id)
        if flavor is None:
            raise HTTPException(404, "Flavor를 찾을 수 없습니다")
        description = getattr(flavor, "description", None)
        if isinstance(description, str) and description.startswith("afterglow:domain-compute-v1:"):
            raise HTTPException(409, "managed_flavor_owned_by_automation")
        specs = flavor_extra_specs(conn.compute, flavor)
        if specs.get("afterglow:managed_by") == "domain-compute-v1" or _CPU_CONTROL_SPEC in specs:
            raise HTTPException(409, "managed_flavor_owned_by_automation")

    try:
        await identity_roles._to_completion(asyncio.to_thread(check))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "flavor_ownership_unavailable") from exc


async def _manual_flavor_guard(flavor_id: str, conn=Depends(get_admin_os_conn)):
    async with identity_roles._graph_lock(conn) as lease:
        await _require_manual_flavor(conn, flavor_id)
        await lease.assert_owned()
        yield lease


async def _manual_write(lease, fn):
    await lease.assert_owned()
    loop = asyncio.get_running_loop()

    def check_owned():
        # The worker may have waited after the async preflight. Verify the
        # current Redis owner on the event loop immediately before dispatch.
        asyncio.run_coroutine_threadsafe(lease.assert_owned(), loop).result()

    def submit():
        check_owned()
        return fn(check_owned)

    return await identity_roles._to_completion(asyncio.to_thread(submit))


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
        items = [_flavor_to_dict(f, conn.compute) for f in flavors[:limit]]
        next_marker = items[-1]["id"] if len(items) == limit else None
        return {"items": items, "next_marker": next_marker, "count": len(items)}

    try:
        result = await asyncio.to_thread(_list)
        managed = [item for item in result["items"] if "gpu_primary_aliases" in item]
        if managed:
            try:
                capabilities = await flavor_automation_policy.capabilities()
            except Exception:
                _logger.warning("Flavor GPU approval unavailable", exc_info=True)
            else:
                for item in managed:
                    try:
                        await _approved_gpu_projection(item, capabilities)
                    except Exception:
                        _logger.warning("Flavor GPU mapping unavailable for %s", item["id"], exc_info=True)
        return result
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
            return _flavor_to_dict(flavor, conn.compute)
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
    lease=Depends(_manual_flavor_guard),
):
    """Flavor 삭제."""

    def _delete(_check_owned):
        try:
            conn.compute.delete_flavor(flavor_id, ignore_missing=True)
        except Exception as e:
            _logger.warning("Flavor 삭제 실패: %s", e)

            raise HTTPException(status_code=404, detail="Flavor 삭제 실패")

    try:
        await _manual_write(lease, _delete)
    except HTTPException:
        raise


@router.put("/flavors/{flavor_id}/frontend-visibility", dependencies=[Depends(require_admin)])
async def set_flavor_frontend_visibility(
    flavor_id: str,
    req: FlavorFrontendVisibilityRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    lease=Depends(_manual_flavor_guard),
):
    """Control ordinary Afterglow flavor discovery without changing Nova access."""

    def _set(check_owned):
        flavor = conn.compute.get_flavor(flavor_id)
        if flavor is None:
            raise HTTPException(status_code=404, detail="Flavor를 찾을 수 없습니다")
        value = "true" if req.visible else "false"
        check_owned()
        conn.compute.create_flavor_extra_specs(
            flavor_id,
            {AFTERGLOW_FRONTEND_VISIBLE_SPEC: value},
        )
        return {"flavor_id": flavor_id, "frontend_visible": req.visible}

    try:
        result = await _manual_write(lease, _set)
        await invalidate("afterglow:nova:*:flavors")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        _logger.warning("Afterglow Flavor 노출 설정 실패: %s", exc)
        raise HTTPException(status_code=400, detail="Afterglow Flavor 노출 설정 실패") from exc


@router.put("/flavors/{flavor_id}/usage-schedule-requirement", dependencies=[Depends(require_admin)])
async def set_flavor_usage_schedule_requirement(
    flavor_id: str,
    req: FlavorUsageScheduleRequirementRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    """Edit only the additive application annotation, including automated flavors."""

    def read(compute, *, missing_status=404):
        try:
            flavor = compute.get_flavor(flavor_id)
        except ResourceNotFound as exc:
            raise HTTPException(missing_status, "Flavor를 찾을 수 없습니다") from exc
        if flavor is None:
            raise HTTPException(missing_status, "Flavor를 찾을 수 없습니다")
        if getattr(flavor, "id", None) != flavor_id:
            raise ValueError("native flavor identity mismatch")
        specs = native_flavor_extra_specs(compute, flavor_id)
        return flavor, specs

    async with identity_roles._graph_lock(conn) as lease:
        compute = copy.copy(conn.compute)
        compute.request = functools.partial(
            compute.request, redirect=False, allow_reauth=False, connect_retries=0, status_code_retries=0
        )
        try:
            _, before = await identity_roles._to_completion(asyncio.to_thread(read, compute))
            await lease.assert_owned()

            def write_and_read():
                if req.required:
                    compute.create_flavor_extra_specs(flavor_id, {_USAGE_SCHEDULE_SPEC: "true"})
                elif _USAGE_SCHEDULE_SPEC in before:
                    compute.delete_flavor_extra_specs_property(flavor_id, _USAGE_SCHEDULE_SPEC)
                flavor, after = read(compute, missing_status=502)
                expected = {key: value for key, value in before.items() if key != _USAGE_SCHEDULE_SPEC}
                if req.required:
                    expected[_USAGE_SCHEDULE_SPEC] = "true"
                if after != expected:
                    raise ValueError("native usage annotation readback mismatch")
                return {
                    "flavor_id": flavor_id,
                    "usage_schedule_required": requires_schedule(
                        {"name": flavor.name, "vcpus": flavor.vcpus, "ram": flavor.ram, "extra_specs": after}
                    ),
                    "additional_requirement": req.required,
                }

            try:
                return await identity_roles._to_completion(asyncio.to_thread(write_and_read))
            finally:
                # An ambiguous native write may already have changed every project's catalog.
                await invalidate("afterglow:nova:*:flavors")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, "flavor_usage_requirement_unavailable") from exc


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
    lease=Depends(_manual_flavor_guard),
):
    """Flavor extra_spec 추가/수정."""
    if req.key == _USAGE_SCHEDULE_SPEC:
        raise HTTPException(409, "use_flavor_usage_schedule_requirement")
    if req.key == _CPU_CONTROL_SPEC:
        raise HTTPException(409, "managed_flavor_owned_by_automation")

    def _set(_check_owned):
        try:
            conn.compute.create_flavor_extra_specs(flavor_id, {req.key: req.value})
            return {"key": req.key, "value": req.value}
        except Exception as e:
            _logger.warning("extra_spec 설정 실패: %s", e)

            raise HTTPException(status_code=400, detail="extra_spec 설정 실패")

    try:
        result = await _manual_write(lease, _set)
        await invalidate("afterglow:nova:*:flavors")
        return result
    except HTTPException:
        raise


@router.delete(
    "/flavors/{flavor_id}/extra-specs/{key}",
    dependencies=[Depends(require_admin)],
    status_code=204,
)
async def delete_flavor_extra_spec(
    flavor_id: str,
    key: str,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    lease=Depends(_manual_flavor_guard),
):
    """Flavor extra_spec 삭제."""
    if key == _USAGE_SCHEDULE_SPEC:
        raise HTTPException(409, "use_flavor_usage_schedule_requirement")
    if key == _CPU_CONTROL_SPEC:
        raise HTTPException(409, "managed_flavor_owned_by_automation")

    def _delete(_check_owned):
        try:
            conn.compute.delete_flavor_extra_specs_property(flavor_id, key)
        except Exception as e:
            _logger.warning("extra_spec 삭제 실패: %s", e)

            raise HTTPException(status_code=404, detail="extra_spec 삭제 실패")

    try:
        await _manual_write(lease, _delete)
        await invalidate("afterglow:nova:*:flavors")
    except HTTPException:
        raise


@router.post("/flavors/{flavor_id}/access", dependencies=[Depends(require_admin)])
async def add_flavor_access(
    flavor_id: str,
    req: FlavorAccessRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    lease=Depends(_manual_flavor_guard),
):
    """Flavor에 프로젝트 접근 권한 추가 (Nova raw API)."""

    def _add(check_owned):
        try:
            endpoint = conn.compute.get_endpoint()
            check_owned()
            resp = conn.session.post(
                f"{endpoint}/flavors/{flavor_id}/action",
                json={"addTenantAccess": {"tenant": req.project_id}},
            )
            if resp.status_code >= 400:
                raise Exception(f"HTTP {resp.status_code}")
            return {"flavor_id": flavor_id, "project_id": req.project_id}
        except HTTPException:
            raise
        except Exception as e:
            _logger.warning("접근 권한 추가 실패: %s", e)

            raise HTTPException(status_code=400, detail="접근 권한 추가 실패")

    try:
        result = await _manual_write(lease, _add)
        await invalidate(f"afterglow:nova:{req.project_id}:flavors")
        return result
    except HTTPException:
        raise


@router.delete(
    "/flavors/{flavor_id}/access/{project_id}",
    dependencies=[Depends(require_admin)],
    status_code=204,
)
async def remove_flavor_access(
    flavor_id: str,
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    lease=Depends(_manual_flavor_guard),
):
    """Flavor에서 프로젝트 접근 권한 제거 (Nova raw API)."""

    def _remove(check_owned):
        try:
            endpoint = conn.compute.get_endpoint()
            check_owned()
            resp = conn.session.post(
                f"{endpoint}/flavors/{flavor_id}/action",
                json={"removeTenantAccess": {"tenant": project_id}},
            )
            if resp.status_code >= 400:
                raise Exception(f"HTTP {resp.status_code}")
        except HTTPException:
            raise
        except Exception as e:
            _logger.warning("접근 권한 제거 실패: %s", e)

            raise HTTPException(status_code=404, detail="접근 권한 제거 실패")

    try:
        await _manual_write(lease, _remove)
        await invalidate(f"afterglow:nova:{project_id}:flavors")
    except HTTPException:
        raise
