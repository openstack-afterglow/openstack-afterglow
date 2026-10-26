from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from openstack.exceptions import HttpException
from pydantic import BaseModel, Field, field_validator

from app.api.common.activity_recorder import rec
from app.api.common.owner_check import assert_project_resource_owner, assert_resource_owner
from app.api.deps import (
    CacheMode,
    cache_mode,
    get_os_conn,
    get_os_conn_write,
    get_token_info,
    require_admin,
    require_project_write,
)
from app.models.storage import CreateVolumeRequest, ExtendVolumeRequest, VolumeInfo
from app.rate_limit import limiter
from app.services import cinder, volume_transfers
from app.services.cache import cached_call, invalidate, invalidate_project, invalidation, ttl_fast

logger = logging.getLogger(__name__)


class VolumeTransferRoute(APIRoute):
    """Protect transfer keys without changing other volume route behavior."""

    def get_route_handler(self):
        handler = super().get_route_handler()
        if (
            not self.path.endswith("/transfers")
            and "/transfer/" not in self.path
            and not self.path.endswith("/transfer")
        ):
            return handler

        async def guarded(request):
            try:
                response = await handler(request)
            except RequestValidationError:
                response = JSONResponse({"detail": "볼륨 이전 입력을 확인해 주세요"}, status_code=422)
            except HTTPException as exc:
                if exc.status_code < 500:
                    request.state.audit_error = exc.detail
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
            except Exception:
                # A transfer POST may already have committed. Never reflect
                # provider bodies/keys or lose no-store on unexpected failures.
                response = JSONResponse({"detail": "볼륨 이전 요청 결과를 확인할 수 없습니다"}, status_code=502)
            response.headers.update({"Cache-Control": "no-store, private", "Pragma": "no-cache"})
            return response

        return guarded


router = APIRouter(route_class=VolumeTransferRoute)


async def _assert_volume_owner(
    conn: openstack.connection.Connection,
    volume_id: str,
    token_info: dict,
    *,
    strict: bool = False,
):
    try:
        v = await asyncio.to_thread(conn.block_storage.get_volume, volume_id)
    except Exception:
        raise HTTPException(status_code=404, detail="볼륨을 찾을 수 없습니다")
    check_owner = assert_project_resource_owner if strict else assert_resource_owner
    check_owner(v, conn, token_info, not_found_detail="볼륨을 찾을 수 없습니다")


@router.get("", response_model=list[VolumeInfo])
async def list_volumes(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    pid = conn._afterglow_project_id
    try:
        return await cached_call(
            f"afterglow:cinder:{pid}:volumes:v2",
            ttl_fast(),
            lambda: [v.model_dump() for v in cinder.list_volumes(conn)],
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="볼륨 목록 조회 실패")


@router.get("/transfers")
async def list_volume_transfers(token_info: dict = Depends(get_token_info)):
    """Current genuinely authenticated project's pending transfers only."""
    return await _transfer_call(volume_transfers.own_list, token_info)


@router.get("/{volume_id}", response_model=VolumeInfo)
async def get_volume(
    volume_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _assert_volume_owner(conn, volume_id, token_info)
    try:
        return await asyncio.to_thread(cinder.get_volume, conn, volume_id)
    except Exception:
        raise HTTPException(status_code=404, detail="볼륨을 찾을 수 없습니다")


class RenameVolumeRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("볼륨 이름을 입력해 주세요")
        return name


@router.patch("/{volume_id}", response_model=VolumeInfo)
async def rename_volume(
    volume_id: str,
    req: RenameVolumeRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    await _assert_volume_owner(conn, volume_id, token_info, strict=True)
    try:
        await asyncio.to_thread(cinder.rename_volume, conn, volume_id, req.name)
        await invalidate(f"afterglow:cinder:{conn._afterglow_project_id}:volumes:v2")
        result = await asyncio.to_thread(cinder.get_volume, conn, volume_id)
    except Exception as exc:
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.rename",
            status="failed",
            resource_id=volume_id,
            resource_name=req.name,
            error_message=str(exc)[:500],
        )
        if isinstance(exc, HttpException):
            status = exc.status_code
            if status == 404:
                raise HTTPException(status_code=404, detail="볼륨을 찾을 수 없습니다") from exc
            if status in (400, 403, 409):
                raise HTTPException(status_code=status, detail="볼륨 이름 변경이 거부되었습니다") from exc
            raise HTTPException(status_code=502, detail="볼륨 서비스 오류") from exc
        logger.warning("볼륨 이름 변경 실패 (volume=%s)", volume_id, exc_info=True)
        raise HTTPException(status_code=500, detail="볼륨 이름 변경 실패") from exc

    await rec(
        token_info,
        conn,
        resource_type="volume",
        action="volume.rename",
        status="success",
        resource_id=volume_id,
        resource_name=req.name,
    )
    return result


@router.post("", response_model=VolumeInfo, status_code=201)
@limiter.limit("10/minute")
async def create_volume(
    request: Request,
    req: CreateVolumeRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    pid = conn._afterglow_project_id
    try:
        result = await asyncio.to_thread(cinder.create_empty_volume, conn, req.name, req.size_gb, req.availability_zone)
        await invalidate(f"afterglow:cinder:{pid}:volumes:v2")
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.create",
            status="success",
            resource_name=req.name,
            extra={"size_gb": req.size_gb},
        )
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.create",
            status="failed",
            resource_name=req.name,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="볼륨 생성 실패")


class ProjectExtendVolumeRequest(ExtendVolumeRequest):
    # Keep strict project-write validation local; the global admin API uses the
    # shared request model and retains its existing privileged contract.
    new_size: int = Field(..., strict=True, gt=0, le=cinder.MAX_VOLUME_SIZE)


@router.post("/{volume_id}/extend", response_model=VolumeInfo)
@limiter.limit("10/minute")
async def extend_volume(
    request: Request,
    volume_id: str,
    req: ProjectExtendVolumeRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    """소유 볼륨 확장. 연결된 모든 인스턴스의 전원 종료를 확인한다."""
    pid = conn._afterglow_project_id
    try:
        result = await asyncio.to_thread(cinder.extend_volume, conn, volume_id, req.new_size)
        await invalidate(f"afterglow:cinder:{pid}:volumes:v2")
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.extend",
            status="success",
            resource_id=volume_id,
            resource_name=result.name,
            extra={"new_size": req.new_size, "observed_size": result.size},
        )
        return result
    except cinder.VolumeExtensionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as e:
        logger.warning("볼륨 확장 실패: %s", e, exc_info=True)
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.extend",
            status="failed",
            resource_id=volume_id,
            error_message=str(e)[:500],
        )
        if isinstance(e, HttpException):
            status = e.status_code
            if status == 404:
                raise HTTPException(status_code=404, detail="볼륨을 찾을 수 없습니다") from e
            if status in (400, 403, 409, 413):
                raise HTTPException(status_code=status, detail="볼륨 확장이 거부되었습니다") from e
        raise HTTPException(status_code=502, detail="볼륨 서비스 오류") from e


@router.delete("/{volume_id}", status_code=204)
async def delete_volume(
    volume_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    pid = conn._afterglow_project_id
    await _assert_volume_owner(conn, volume_id, token_info)
    try:
        await asyncio.to_thread(cinder.delete_volume, conn, volume_id)
        await invalidate(f"afterglow:cinder:{pid}:volumes:v2")
        await rec(
            token_info, conn, resource_type="volume", action="volume.delete", status="success", resource_id=volume_id
        )
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.delete",
            status="failed",
            resource_id=volume_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="볼륨 삭제 실패")


@router.post("/{volume_id}/force-delete", status_code=204)
async def force_delete_volume(
    volume_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    _: None = Depends(require_admin),
    token_info: dict = Depends(get_token_info),
):
    """error/error_deleting 상태 볼륨을 강제 삭제한다. 관리자 전용."""
    pid = conn._afterglow_project_id
    try:
        # reset_status → error 상태로 전환 후 force delete
        await asyncio.to_thread(cinder.reset_volume_status, conn, volume_id, "error")
        await asyncio.to_thread(cinder.force_delete_volume, conn, volume_id)
        await invalidate(f"afterglow:cinder:{pid}:volumes:v2")
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.force_delete",
            status="success",
            resource_id=volume_id,
        )
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.force_delete",
            status="failed",
            resource_id=volume_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="볼륨 강제 삭제 실패")


# ---------------------------------------------------------------------------
# Native volume transfers: exact readback, caller-scoped writes, one-time key.
# ---------------------------------------------------------------------------


class CreateVolumeTransferRequest(BaseModel):
    name: str | None = Field(None, max_length=255)


class AcceptVolumeTransferRequest(BaseModel):
    auth_key: str = Field(..., min_length=1, max_length=512)

    @field_validator("auth_key")
    @classmethod
    def nonblank_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("인증 키를 입력해 주세요")
        return value


async def _invalidate_transfer_accept(project_id: str):
    # Native acceptance also moves snapshots and changes both projects' quotas.
    await invalidate_project(project_id, "cinder")
    await invalidate(f"afterglow:dashboard:{project_id}:quotas*")
    await invalidation.invalidate_mutation_count("cinder", project_id)


async def _transfer_call(function, *args, accepting: bool = False):
    try:
        return await asyncio.to_thread(function, *args)
    except volume_transfers.TransferError as exc:
        for project_id in exc.affected_projects:
            await _invalidate_transfer_accept(project_id)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    except Exception as exc:
        error = volume_transfers.provider_error(exc, accepting=accepting)
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None


@router.get("/transfer/{transfer_id}")
async def get_volume_transfer(transfer_id: str, _token_info: dict = Depends(get_token_info)):
    """Read exactly one pending transfer without its key or private metadata."""
    return await _transfer_call(volume_transfers.lookup, transfer_id)


@router.post("/{volume_id}/transfer", status_code=201)
async def create_volume_transfer(
    volume_id: str,
    req: CreateVolumeTransferRequest | None = None,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    """Issue a transfer only for an owned, available and unattached volume."""
    result = await _transfer_call(volume_transfers.create, token_info, volume_id, req.name if req else None)
    await invalidate(f"afterglow:cinder:{token_info['project_id']}:volumes*")
    await rec(
        token_info,
        conn,
        resource_type="volume",
        action="volume.transfer_create",
        status="success",
        resource_id=volume_id,
    )
    return result


@router.post("/transfer/{transfer_id}/accept", status_code=200)
async def accept_volume_transfer(
    transfer_id: str,
    req: AcceptVolumeTransferRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    """Native key authorization using a verified destination-scoped caller."""
    result, source = await _transfer_call(
        volume_transfers.accept, token_info, transfer_id, req.auth_key, accepting=True
    )
    await _invalidate_transfer_accept(source)
    await _invalidate_transfer_accept(token_info["project_id"])
    await rec(
        token_info,
        conn,
        resource_type="volume",
        action="volume.transfer_accept",
        status="success",
        resource_id=transfer_id,
    )
    return result


@router.delete("/transfer/{transfer_id}", status_code=204)
async def delete_volume_transfer(
    transfer_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    """Cancel only a pending transfer whose actual source is this project."""
    source = await _transfer_call(volume_transfers.cancel, token_info, transfer_id)
    await invalidate(f"afterglow:cinder:{source}:volumes*")
    await rec(
        token_info,
        conn,
        resource_type="volume",
        action="volume.transfer_delete",
        status="success",
        resource_id=transfer_id,
    )
