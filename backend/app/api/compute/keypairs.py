from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.common.activity_recorder import rec
from app.api.deps import CacheMode, cache_mode, get_os_conn, get_token_info
from app.rate_limit import limiter
from app.services import nova
from app.services.cache import cached_call, invalidation, keys, patch_list, ttl_slow

router = APIRouter()


class CreateKeypairRequest(BaseModel):
    name: str
    public_key: str | None = None
    key_type: str = "ssh"


@router.get("")
async def list_keypairs(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
    cm: CacheMode = Depends(cache_mode),
):
    uid = token_info.get("user_id") or getattr(conn, "_afterglow_user_id", "")
    key = keys.user_key(uid, "keypairs")
    try:
        return await cached_call(
            key, ttl_slow(), lambda: nova.list_keypairs(conn), enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        raise HTTPException(status_code=500, detail="작업 실패")


@router.post("", status_code=201)
@limiter.limit("10/minute")
async def create_keypair(
    request: Request,
    req: CreateKeypairRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    uid = token_info.get("user_id") or getattr(conn, "_afterglow_user_id", "")
    try:
        result = await asyncio.to_thread(nova.create_keypair, conn, req.name, req.public_key, req.key_type)
        # terminal mutation — list 캐시에 신규 엔트리 직접 추가 (origin 재조회 없음)
        list_entry = {"name": result["name"], "fingerprint": result["fingerprint"], "type": result["type"]}
        await patch_list(keys.user_key(uid, "keypairs"), ttl_slow(), add=list_entry)
        await invalidation.invalidate_mutation_count("nova", pid)
        await rec(
            token_info, conn, resource_type="keypair", action="keypair.create", status="success", resource_name=req.name
        )
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="keypair",
            action="keypair.create",
            status="failed",
            resource_name=req.name,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="키페어 생성 실패")


@router.delete("/{keypair_name}", status_code=204)
@limiter.limit("10/minute")
async def delete_keypair(
    request: Request,
    keypair_name: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    uid = token_info.get("user_id") or getattr(conn, "_afterglow_user_id", "")
    try:
        await asyncio.to_thread(nova.delete_keypair, conn, keypair_name)
        # terminal mutation — list 캐시에서 해당 엔트리 직접 제거 (origin 재조회 없음)
        _kn = keypair_name
        await patch_list(
            keys.user_key(uid, "keypairs"),
            ttl_slow(),
            match=lambda x: x.get("name") == _kn,
            remove=True,
        )
        await invalidation.invalidate_mutation_count("nova", pid)
        await rec(
            token_info,
            conn,
            resource_type="keypair",
            action="keypair.delete",
            status="success",
            resource_id=keypair_name,
            resource_name=keypair_name,
        )
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="keypair",
            action="keypair.delete",
            status="failed",
            resource_id=keypair_name,
            resource_name=keypair_name,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="키페어 삭제 실패")
