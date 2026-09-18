from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.common.activity_recorder import rec
from app.api.common.owner_check import assert_resource_owner
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
from app.services import cinder, nova
from app.services.cache import cached_call, invalidate, ttl_fast

logger = logging.getLogger(__name__)
router = APIRouter()


async def _assert_volume_owner(
    conn: openstack.connection.Connection,
    volume_id: str,
    token_info: dict,
):
    try:
        v = await asyncio.to_thread(conn.block_storage.get_volume, volume_id)
    except Exception:
        raise HTTPException(status_code=404, detail="볼륨을 찾을 수 없습니다")
    assert_resource_owner(v, conn, token_info, not_found_detail="볼륨을 찾을 수 없습니다")


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


@router.post("/{volume_id}/extend", response_model=VolumeInfo)
@limiter.limit("10/minute")
async def extend_volume(
    request: Request,
    volume_id: str,
    req: ExtendVolumeRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    """볼륨 용량 확장. available 및 in-use 볼륨 모두 지원 (Ceph online extend)."""
    await _assert_volume_owner(conn, volume_id, token_info)
    try:
        current = await asyncio.to_thread(conn.block_storage.get_volume, volume_id)
    except Exception:
        raise HTTPException(status_code=404, detail="볼륨을 찾을 수 없습니다")
    if req.new_size <= current.size:
        raise HTTPException(
            status_code=400,
            detail=f"새 크기({req.new_size}GB)는 현재 크기({current.size}GB)보다 커야 합니다",
        )
    pid = conn._afterglow_project_id
    try:
        await asyncio.to_thread(cinder.extend_volume, conn, volume_id, req.new_size)
        await invalidate(f"afterglow:cinder:{pid}:volumes:v2")
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.extend",
            status="success",
            resource_id=volume_id,
            resource_name=current.name or "",
            extra={"old_size": current.size, "new_size": req.new_size},
        )
        return await asyncio.to_thread(cinder.get_volume, conn, volume_id)
    except HTTPException:
        raise
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
        raise HTTPException(status_code=400, detail=f"볼륨 확장 실패: {e}")


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
# 볼륨 Transfer (프로젝트 간 마이그레이션)
# ---------------------------------------------------------------------------


class CreateVolumeTransferRequest(BaseModel):
    name: str | None = None


class AcceptVolumeTransferRequest(BaseModel):
    auth_key: str = Field(..., min_length=1)


@router.get("/transfers")
async def list_volume_transfers(conn: openstack.connection.Connection = Depends(get_os_conn)):
    """볼륨 이전(transfer) 목록 조회."""
    try:
        return await asyncio.to_thread(cinder.list_volume_transfers, conn)
    except Exception:
        raise HTTPException(status_code=500, detail="볼륨 이전 목록 조회 실패")


@router.post("/{volume_id}/transfer", status_code=201)
async def create_volume_transfer(
    volume_id: str,
    req: CreateVolumeTransferRequest | None = None,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """볼륨 이전(transfer) 생성.

    VM에 부착된 경우 자동으로 detach한 뒤 transfer를 생성한다.
    transfer 생성 실패 시 detach한 서버에 볼륨을 다시 attach(rollback)한다.
    """
    await _assert_volume_owner(conn, volume_id, token_info)
    try:
        vol = await asyncio.to_thread(cinder.get_volume, conn, volume_id)
    except Exception:
        raise HTTPException(status_code=404, detail="볼륨을 찾을 수 없습니다")

    # 부착된 VM에서 detach — 성공한 서버 ID를 rollback용으로 보관
    detached_server_ids: list[str] = []
    for attachment in vol.attachments:
        server_id = attachment.get("server_id")
        if not server_id:
            continue
        try:
            await asyncio.to_thread(nova.detach_volume, conn, server_id, volume_id)
            detached_server_ids.append(server_id)
        except Exception as ex:
            logger.warning("volume detach 실패 server=%s volume=%s: %s", server_id, volume_id, ex)
            raise HTTPException(
                status_code=409,
                detail=f"볼륨 detach 실패 (인스턴스 {server_id}) — 수동으로 분리 후 재시도 해주세요",
            )

    # detach 후 available 상태 대기
    if detached_server_ids:
        try:
            await asyncio.to_thread(cinder.wait_volume_available, conn, volume_id)
        except Exception:
            raise HTTPException(status_code=409, detail="볼륨 detach 대기 시간 초과")

    # transfer 생성 — 실패 시 detach한 서버에 rollback
    try:
        name = req.name if req else None
        result = await asyncio.to_thread(cinder.create_volume_transfer, conn, volume_id, name)
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.transfer_create",
            status="success",
            resource_id=volume_id,
        )
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.transfer_create",
            status="failed",
            resource_id=volume_id,
            error_message=str(e)[:500],
        )
        for server_id in detached_server_ids:
            try:
                await asyncio.to_thread(nova.attach_volume, conn, server_id, volume_id)
            except Exception as rb_ex:
                logger.error("rollback attach 실패 server=%s volume=%s: %s", server_id, volume_id, rb_ex)
        raise HTTPException(status_code=500, detail="볼륨 이전 생성 실패")


@router.post("/transfer/{transfer_id}/accept", status_code=200)
async def accept_volume_transfer(
    transfer_id: str,
    req: AcceptVolumeTransferRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """볼륨 이전 수락."""
    try:
        result = await asyncio.to_thread(cinder.accept_volume_transfer, conn, transfer_id, req.auth_key)
        await invalidate(f"afterglow:cinder:{conn._afterglow_project_id}:volumes:v2")
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.transfer_accept",
            status="success",
            resource_id=transfer_id,
        )
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.transfer_accept",
            status="failed",
            resource_id=transfer_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="볼륨 이전 수락 실패")


@router.delete("/transfer/{transfer_id}", status_code=204)
async def delete_volume_transfer(
    transfer_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """볼륨 이전 취소."""
    try:
        await asyncio.to_thread(cinder.delete_volume_transfer, conn, transfer_id)
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.transfer_delete",
            status="success",
            resource_id=transfer_id,
        )
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="volume",
            action="volume.transfer_delete",
            status="failed",
            resource_id=transfer_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="볼륨 이전 취소 실패")
