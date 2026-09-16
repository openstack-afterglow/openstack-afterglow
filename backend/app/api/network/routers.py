from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.common.activity_recorder import rec
from app.api.common.owner_check import assert_project_resource_owner
from app.api.deps import CacheMode, cache_mode, get_os_conn, get_token_info
from app.models.storage import (
    CreateRouterRequest,
    RouterDetail,
    RouterGatewayRequest,
    RouterInfo,
    RouterInterfaceRequest,
)
from app.rate_limit import limiter
from app.services import neutron
from app.services.cache import cached_call, invalidate, ttl_normal

router = APIRouter()


@router.get("", response_model=list[RouterInfo])
async def list_routers(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    pid = conn._afterglow_project_id
    try:
        return await cached_call(
            f"afterglow:neutron:{pid}:routers",
            ttl_normal(),
            lambda: [r.model_dump() for r in neutron.list_routers(conn, project_id=pid)],
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="라우터 목록 조회 실패")


@router.post("", response_model=RouterInfo, status_code=201)
@limiter.limit("10/minute")
async def create_router(
    request: Request,
    req: CreateRouterRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        result = await asyncio.to_thread(neutron.create_router, conn, req.name, req.external_network_id)
        await invalidate(f"afterglow:neutron:{pid}:routers")
        await rec(token_info, conn, resource_type="router", action="create", resource_name=req.name)
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="router",
            action="create",
            status="failed",
            resource_name=req.name,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="라우터 생성 실패")


async def _get_router_with_owner_check(conn: openstack.connection.Connection, router_id: str, token_info: dict):
    try:
        r = await asyncio.to_thread(conn.network.get_router, router_id)
    except Exception:
        raise HTTPException(status_code=404, detail="라우터를 찾을 수 없습니다")
    assert_project_resource_owner(r, conn, token_info, not_found_detail="라우터를 찾을 수 없습니다")
    return r


async def _get_subnet_with_owner_check(conn: openstack.connection.Connection, subnet_id: str, token_info: dict):
    try:
        subnet = await asyncio.to_thread(conn.network.get_subnet, subnet_id)
    except Exception:
        raise HTTPException(status_code=404, detail="서브넷을 찾을 수 없습니다")
    assert_project_resource_owner(subnet, conn, token_info, not_found_detail="서브넷을 찾을 수 없습니다")
    return subnet


@router.get("/{router_id}", response_model=RouterDetail)
async def get_router(
    router_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _get_router_with_owner_check(conn, router_id, token_info)
    try:
        return await asyncio.to_thread(neutron.get_router_detail, conn, router_id)
    except Exception:
        raise HTTPException(status_code=404, detail="라우터 조회 실패")


@router.delete("/{router_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_router(
    request: Request,
    router_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    await _get_router_with_owner_check(conn, router_id, token_info)
    try:
        await asyncio.to_thread(neutron.delete_router, conn, router_id)
        await invalidate(f"afterglow:neutron:{pid}:routers")
        await rec(token_info, conn, resource_type="router", action="delete", resource_id=router_id)
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="router",
            action="delete",
            status="failed",
            resource_id=router_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="라우터 삭제 실패")


@router.post("/{router_id}/interfaces", status_code=201)
@limiter.limit("10/minute")
async def add_interface(
    request: Request,
    router_id: str,
    req: RouterInterfaceRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _get_router_with_owner_check(conn, router_id, token_info)
    await _get_subnet_with_owner_check(conn, req.subnet_id, token_info)
    try:
        result = await asyncio.to_thread(neutron.add_router_interface, conn, router_id, req.subnet_id, req.auto_gateway)
        await rec(
            token_info,
            conn,
            resource_type="router",
            action="add_interface",
            resource_id=router_id,
            extra={"subnet_id": req.subnet_id},
        )
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="router",
            action="add_interface",
            status="failed",
            resource_id=router_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="인터페이스 추가 실패")


@router.delete("/{router_id}/interfaces/{subnet_id}", status_code=204)
@limiter.limit("10/minute")
async def remove_interface(
    request: Request,
    router_id: str,
    subnet_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _get_router_with_owner_check(conn, router_id, token_info)
    await _get_subnet_with_owner_check(conn, subnet_id, token_info)
    try:
        await asyncio.to_thread(neutron.remove_router_interface, conn, router_id, subnet_id)
        await rec(token_info, conn, resource_type="router", action="remove_interface", resource_id=router_id)
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="router",
            action="remove_interface",
            status="failed",
            resource_id=router_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="인터페이스 제거 실패")


@router.post("/{router_id}/gateway", status_code=204)
@limiter.limit("10/minute")
async def set_gateway(
    request: Request,
    router_id: str,
    req: RouterGatewayRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _get_router_with_owner_check(conn, router_id, token_info)
    try:
        await asyncio.to_thread(neutron.set_router_gateway, conn, router_id, req.external_network_id)
        await rec(token_info, conn, resource_type="router", action="set_gateway", resource_id=router_id)
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="router",
            action="set_gateway",
            status="failed",
            resource_id=router_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="게이트웨이 설정 실패")


@router.delete("/{router_id}/gateway", status_code=204)
@limiter.limit("10/minute")
async def remove_gateway(
    request: Request,
    router_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _get_router_with_owner_check(conn, router_id, token_info)
    try:
        await asyncio.to_thread(neutron.remove_router_gateway, conn, router_id)
        await rec(token_info, conn, resource_type="router", action="remove_gateway", resource_id=router_id)
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="router",
            action="remove_gateway",
            status="failed",
            resource_id=router_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="게이트웨이 제거 실패")
