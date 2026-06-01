from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.common.activity_recorder import rec
from app.api.deps import get_os_conn, get_token_info
from app.models.barbican import (
    AclSetRequest,
    SecretCreateRequest,
    SecretInfo,
)
from app.rate_limit import limiter
from app.services import barbican as bsvc
from app.services.cache import cached_call, invalidate, ttl_normal

router = APIRouter()


@router.get("", response_model=list[SecretInfo])
async def list_secrets(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    refresh: bool = False,
):
    pid = conn._afterglow_project_id
    try:
        return await cached_call(
            f"afterglow:barbican:{pid}:secrets",
            ttl_normal(),
            lambda: bsvc.list_secrets(conn),
            refresh=refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="비밀 목록 조회 실패")


@router.post("", response_model=SecretInfo, status_code=201)
@limiter.limit("20/minute")
async def create_secret(
    request: Request,
    req: SecretCreateRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        result = await asyncio.to_thread(
            bsvc.create_secret, conn,
            name=req.name, secret_type=req.secret_type,
            payload=req.payload, payload_content_type=req.payload_content_type,
            algorithm=req.algorithm, bit_length=req.bit_length,
            mode=req.mode, expiration=req.expiration,
        )
        await invalidate(f"afterglow:barbican:{pid}:secrets*")
        await rec(token_info, conn, resource_type="secret", action="secret.create",
                  status="success", resource_name=req.name)
        return result
    except Exception as e:
        await rec(token_info, conn, resource_type="secret", action="secret.create",
                  status="failed", resource_name=req.name, error_message=str(e)[:500])
        raise HTTPException(status_code=500, detail="비밀 생성 실패")


@router.get("/{secret_id}/meta", response_model=SecretInfo)
async def get_secret_meta(
    secret_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        return bsvc.get_secret_meta(conn, secret_id)
    except Exception:
        raise HTTPException(status_code=404, detail="비밀을 찾을 수 없습니다")


@router.get("/{secret_id}/payload")
async def get_secret_payload(
    secret_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """payload 복호화 — 캐시/로그 금지."""
    try:
        data = await asyncio.to_thread(bsvc.get_secret_payload, conn, secret_id)
        return Response(content=data, media_type="application/octet-stream")
    except Exception:
        raise HTTPException(status_code=404, detail="payload 조회 실패")


@router.delete("/{secret_id}", status_code=204)
@limiter.limit("20/minute")
async def delete_secret(
    request: Request,
    secret_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        await asyncio.to_thread(bsvc.delete_secret, conn, secret_id)
        await invalidate(f"afterglow:barbican:{pid}:secrets*")
        await rec(token_info, conn, resource_type="secret", action="secret.delete",
                  status="success", resource_id=secret_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        await rec(token_info, conn, resource_type="secret", action="secret.delete",
                  status="failed", resource_id=secret_id, error_message=str(e)[:500])
        raise HTTPException(status_code=500, detail="비밀 삭제 실패")


# ── ACL ──────────────────────────────────────────────────────────────────────

@router.get("/{secret_id}/acl")
async def get_secret_acl(
    secret_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        return await asyncio.to_thread(bsvc.get_acl, conn, "secrets", secret_id)
    except Exception:
        raise HTTPException(status_code=500, detail="ACL 조회 실패")


@router.put("/{secret_id}/acl")
@limiter.limit("20/minute")
async def set_secret_acl(
    request: Request,
    secret_id: str,
    req: AclSetRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        return await asyncio.to_thread(
            bsvc.set_acl, conn, "secrets", secret_id, req.users, req.project_access
        )
    except Exception:
        raise HTTPException(status_code=500, detail="ACL 설정 실패")


@router.delete("/{secret_id}/acl", status_code=204)
@limiter.limit("20/minute")
async def delete_secret_acl(
    request: Request,
    secret_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        await asyncio.to_thread(bsvc.delete_acl, conn, "secrets", secret_id)
    except Exception:
        raise HTTPException(status_code=500, detail="ACL 초기화 실패")


# ── Consumers ────────────────────────────────────────────────────────────────

@router.get("/{secret_id}/consumers")
async def list_secret_consumers(
    secret_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        return await asyncio.to_thread(bsvc.list_secret_consumers, conn, secret_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Consumers 조회 실패")


# ── Quota ────────────────────────────────────────────────────────────────────

@router.get("/quota/effective")
async def get_effective_quota(
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        return await asyncio.to_thread(bsvc.get_effective_quota, conn)
    except Exception:
        raise HTTPException(status_code=500, detail="쿼터 조회 실패")
