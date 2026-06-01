from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.common.activity_recorder import rec
from app.api.deps import get_os_conn, get_token_info
from app.models.barbican import AclSetRequest, ContainerCreateRequest, ContainerInfo
from app.rate_limit import limiter
from app.services import barbican as bsvc
from app.services.cache import cached_call, invalidate, ttl_normal

router = APIRouter()


@router.get("", response_model=list[ContainerInfo])
async def list_containers(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    refresh: bool = False,
):
    pid = conn._afterglow_project_id
    try:
        return await cached_call(
            f"afterglow:barbican:{pid}:containers",
            ttl_normal(),
            lambda: bsvc.list_containers(conn),
            refresh=refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="컨테이너 목록 조회 실패")


@router.post("", response_model=ContainerInfo, status_code=201)
@limiter.limit("20/minute")
async def create_container(
    request: Request,
    req: ContainerCreateRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        result = await asyncio.to_thread(
            bsvc.create_container, conn,
            name=req.name, container_type=req.container_type, secret_refs=req.secret_refs,
        )
        await invalidate(f"afterglow:barbican:{pid}:containers*")
        await rec(token_info, conn, resource_type="secret_container", action="container.create",
                  status="success", resource_name=req.name)
        return result
    except Exception as e:
        await rec(token_info, conn, resource_type="secret_container", action="container.create",
                  status="failed", resource_name=req.name, error_message=str(e)[:500])
        raise HTTPException(status_code=500, detail="컨테이너 생성 실패")


@router.delete("/{container_id}", status_code=204)
@limiter.limit("20/minute")
async def delete_container(
    request: Request,
    container_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        await asyncio.to_thread(bsvc.delete_container, conn, container_id)
        await invalidate(f"afterglow:barbican:{pid}:containers*")
        await rec(token_info, conn, resource_type="secret_container", action="container.delete",
                  status="success", resource_id=container_id)
    except Exception as e:
        await rec(token_info, conn, resource_type="secret_container", action="container.delete",
                  status="failed", resource_id=container_id, error_message=str(e)[:500])
        raise HTTPException(status_code=500, detail="컨테이너 삭제 실패")


@router.get("/{container_id}/acl")
async def get_container_acl(
    container_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        return await asyncio.to_thread(bsvc.get_acl, conn, "containers", container_id)
    except Exception:
        raise HTTPException(status_code=500, detail="ACL 조회 실패")


@router.put("/{container_id}/acl")
@limiter.limit("20/minute")
async def set_container_acl(
    request: Request,
    container_id: str,
    req: AclSetRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        return await asyncio.to_thread(
            bsvc.set_acl, conn, "containers", container_id, req.users, req.project_access
        )
    except Exception:
        raise HTTPException(status_code=500, detail="ACL 설정 실패")


@router.get("/{container_id}/consumers")
async def list_container_consumers(
    container_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        return await asyncio.to_thread(bsvc.list_container_consumers, conn, container_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Consumers 조회 실패")
