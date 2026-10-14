from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from openstack.exceptions import HttpException, ResourceNotFound
from pydantic import BaseModel

from app.api.common.activity_recorder import rec
from app.api.common.owner_check import assert_resource_owner
from app.api.deps import CacheMode, cache_mode, get_os_conn, get_os_conn_write, get_token_info
from app.services import auto_backup, cinder
from app.services.cache import cached_call, invalidate, invalidation, keys, ttl_slow

router = APIRouter()


async def _assert_backup_owner(conn, backup_id: str, token_info: dict):
    try:
        b = await asyncio.to_thread(conn.block_storage.get_backup, backup_id)
    except Exception:
        raise HTTPException(status_code=404, detail="백업을 찾을 수 없습니다")
    assert_resource_owner(b, conn, token_info, not_found_detail="백업을 찾을 수 없습니다")


async def _assert_volume_owner_local(conn, volume_id: str, token_info: dict):
    try:
        v = await asyncio.to_thread(conn.block_storage.get_volume, volume_id)
    except Exception:
        raise HTTPException(status_code=404, detail="볼륨을 찾을 수 없습니다")
    assert_resource_owner(v, conn, token_info, not_found_detail="볼륨을 찾을 수 없습니다")
    return v


class CreateBackupRequest(BaseModel):
    volume_id: str
    name: str
    description: str | None = None
    incremental: bool = False
    force: bool = False


class RestoreBackupRequest(BaseModel):
    volume_id: str | None = None


@router.get("")
async def list_backups(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    pid = conn._afterglow_project_id
    try:
        return await cached_call(
            keys.project_key("cinder", pid, "backups"),
            ttl_slow(),
            lambda: cinder.list_backups(conn),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="백업 목록 조회 실패")


@router.post("", status_code=201)
async def create_backup(
    req: CreateBackupRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    volume = await _assert_volume_owner_local(conn, req.volume_id, token_info)
    if volume.status == "in-use" and not req.force:
        raise HTTPException(status_code=400, detail="사용 중인 볼륨을 백업하려면 강제 백업(force)을 활성화해야 합니다")
    try:
        result = await asyncio.to_thread(
            cinder.create_backup, conn, req.volume_id, req.name, req.description, req.incremental, force=req.force
        )
        pid = conn._afterglow_project_id
        await invalidate(f"afterglow:cinder:{pid}:backups*")
        await invalidation.invalidate_mutation_count("cinder", pid)
        await rec(
            token_info,
            conn,
            resource_type="volume_backup",
            action="volume_backup.create",
            status="success",
            resource_name=req.name,
            extra={"volume_id": req.volume_id, "force": req.force},
        )
        return result
    except HttpException as e:
        await rec(
            token_info,
            conn,
            resource_type="volume_backup",
            action="volume_backup.create",
            status="failed",
            resource_name=req.name,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=e.status_code or 500, detail=e.message or str(e))
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="volume_backup",
            action="volume_backup.create",
            status="failed",
            resource_name=req.name,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="백업 생성 실패")


@router.get("/{backup_id}")
async def get_backup(
    backup_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
    cm: CacheMode = Depends(cache_mode),
):
    await _assert_backup_owner(conn, backup_id, token_info)
    pid = conn._afterglow_project_id
    key = keys.project_key("cinder", pid, "backups", sub=backup_id)
    try:
        return await cached_call(
            key, ttl_slow(), lambda: cinder.get_backup(conn, backup_id), enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        raise HTTPException(status_code=404, detail="백업을 찾을 수 없습니다")


@router.delete("/{backup_id}", status_code=204)
async def delete_backup(
    backup_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _assert_backup_owner(conn, backup_id, token_info)
    try:
        await asyncio.to_thread(cinder.delete_backup, conn, backup_id)
        pid = conn._afterglow_project_id
        await invalidate(f"afterglow:cinder:{pid}:backups*")
        await invalidation.invalidate_mutation_count("cinder", pid)
        await rec(
            token_info,
            conn,
            resource_type="volume_backup",
            action="volume_backup.delete",
            status="success",
            resource_id=backup_id,
        )
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="volume_backup",
            action="volume_backup.delete",
            status="failed",
            resource_id=backup_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="백업 삭제 실패")


@router.post("/{backup_id}/restore")
async def restore_backup(
    backup_id: str,
    req: RestoreBackupRequest = RestoreBackupRequest(),
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _assert_backup_owner(conn, backup_id, token_info)
    if req.volume_id:
        await _assert_volume_owner_local(conn, req.volume_id, token_info)
    try:
        result = await asyncio.to_thread(cinder.restore_backup, conn, backup_id, req.volume_id)
        pid = conn._afterglow_project_id
        await invalidate(f"afterglow:cinder:{pid}:backups*")
        await invalidation.invalidate_mutation_count("cinder", pid)
        await rec(
            token_info,
            conn,
            resource_type="volume_backup",
            action="volume_backup.restore",
            status="success",
            resource_id=backup_id,
            extra={"target_volume_id": req.volume_id},
        )
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="volume_backup",
            action="volume_backup.restore",
            status="failed",
            resource_id=backup_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="백업 복원 실패")


# ────────── 자동 백업 설정 엔드포인트 ──────────


class AutoBackupRequest(auto_backup.PolicySettings):
    pass


async def _read_schedule_source(conn, volume_id: str):
    try:
        return await asyncio.to_thread(conn.block_storage.get_volume, volume_id)
    except ResourceNotFound:
        return None
    except HttpException as exc:
        if exc.status_code == 404:
            return None
        if exc.status_code in (401, 403):
            raise HTTPException(status_code=exc.status_code, detail="볼륨 조회 권한을 확인할 수 없습니다") from None
        raise HTTPException(status_code=503, detail="원본 볼륨을 조회할 수 없습니다") from None
    except Exception:
        raise HTTPException(status_code=503, detail="원본 볼륨을 조회할 수 없습니다") from None


def _assert_schedule_scope(conn, volume):
    # Scheduling is strictly bound to the effective project, including system admins.
    project_id = getattr(conn, "_afterglow_project_id", None)
    if not project_id or volume is None or getattr(volume, "project_id", None) != project_id:
        raise HTTPException(status_code=404, detail="볼륨을 찾을 수 없습니다")


async def _assert_schedule_source(conn, volume_id: str):
    volume = await _read_schedule_source(conn, volume_id)
    _assert_schedule_scope(conn, volume)
    return volume


@router.post("/auto-backup/configs")
async def list_auto_backup_configs(
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """현재 프로젝트의 모든 자동 백업 설정 목록."""
    try:
        configs = await auto_backup.list_auto_backup_configs(conn._afterglow_project_id)
        for config in configs:
            if config.get("project_id") != conn._afterglow_project_id or config.get("identity_verified") is False:
                raise HTTPException(status_code=503, detail="저장된 자동 백업 정책 소유권을 확인할 수 없습니다")
            try:
                volume = await _read_schedule_source(conn, config["volume_id"])
                if volume is None:
                    status, available, error = "missing", False, "Source volume no longer exists."
                else:
                    _assert_schedule_scope(conn, volume)
                    continue
            except HTTPException as exc:
                if exc.status_code in (401, 403, 404):
                    status, available, error = "not_owned", False, "Source volume ownership could not be confirmed."
                else:
                    status, available, error = (
                        "unavailable",
                        None,
                        "Source volume could not be checked; try again later.",
                    )
            # Response-only observation. Never silently pause or rewrite the saved policy.
            config.update(source_status=status, source_available=available, source_error=error)
            config["last_error"] = config.get("last_error") or error
        return configs
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="자동 백업 설정 목록 조회 실패") from None


@router.get("/auto-backup/{volume_id}")
async def get_auto_backup_config(
    volume_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    await _assert_schedule_source(conn, volume_id)
    try:
        config = await auto_backup.get_auto_backup_config(conn._afterglow_project_id, volume_id)
    except Exception:
        raise HTTPException(status_code=503, detail="자동 백업 설정 조회 실패") from None
    if config is None:
        raise HTTPException(status_code=404, detail="자동 백업 설정이 없습니다")
    return config


@router.post("/auto-backup/{volume_id}", status_code=201)
async def enable_auto_backup(
    volume_id: str,
    req: AutoBackupRequest = AutoBackupRequest(),
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(get_token_info),
):
    """Save/edit/pause a calendar policy; no backup is submitted by this request."""
    volume = await _assert_schedule_source(conn, volume_id)
    if req.enabled:
        if volume.status not in ("available", "in-use"):
            raise HTTPException(status_code=400, detail="현재 볼륨 상태에서는 자동 백업을 활성화할 수 없습니다")
        if volume.status == "in-use" and not req.force:
            raise HTTPException(
                status_code=400, detail="사용 중인 볼륨의 자동 백업에는 별도의 강제 백업(force) 동의가 필요합니다"
            )
    try:
        result = await auto_backup.enable_auto_backup(conn._afterglow_project_id, volume_id, **req.model_dump())
        await rec(
            token_info,
            conn,
            resource_type="volume_backup",
            action="volume.auto_backup_enable",
            status="success",
            resource_id=volume_id,
            extra={"enabled": req.enabled, "force": req.force},
        )
        return result
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="자동 백업 설정 저장 실패") from None


@router.delete("/auto-backup/{volume_id}", status_code=204)
async def disable_auto_backup(
    volume_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(get_token_info),
):
    """Remove the policy only; existing and already submitted backups are retained."""
    volume = await _read_schedule_source(conn, volume_id)
    if volume is not None:
        _assert_schedule_scope(conn, volume)
    try:
        if volume is None:
            config = await auto_backup.get_auto_backup_config(conn._afterglow_project_id, volume_id)
            if (
                not config
                or config.get("project_id") != conn._afterglow_project_id
                or config.get("volume_id") != volume_id
                or config.get("identity_verified") is False
            ):
                raise HTTPException(status_code=404, detail="자동 백업 설정이 없습니다")
        await auto_backup.disable_auto_backup(conn._afterglow_project_id, volume_id)
        await rec(
            token_info,
            conn,
            resource_type="volume_backup",
            action="volume.auto_backup_disable",
            status="success",
            resource_id=volume_id,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="자동 백업 설정 삭제 실패") from None
