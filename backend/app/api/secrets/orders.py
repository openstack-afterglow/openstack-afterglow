from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.common.activity_recorder import rec
from app.api.deps import get_os_conn, get_token_info
from app.models.barbican import OrderCreateRequest, OrderInfo
from app.rate_limit import limiter
from app.services import barbican as bsvc
from app.services.cache import cached_call, invalidate, ttl_normal

router = APIRouter()


@router.get("", response_model=list[OrderInfo])
async def list_orders(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    refresh: bool = False,
):
    pid = conn._afterglow_project_id
    try:
        return await cached_call(
            f"afterglow:barbican:{pid}:orders",
            ttl_normal(),
            lambda: bsvc.list_orders(conn),
            refresh=refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Order 목록 조회 실패")


@router.post("", response_model=OrderInfo, status_code=201)
@limiter.limit("10/minute")
async def create_order(
    request: Request,
    req: OrderCreateRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        result = await asyncio.to_thread(bsvc.create_order, conn, order_type=req.order_type, meta=req.meta)
        await invalidate(f"afterglow:barbican:{pid}:orders*")
        await rec(token_info, conn, resource_type="secret_order", action="order.create",
                  status="success", resource_name=req.meta.get("name", ""))
        return result
    except Exception as e:
        await rec(token_info, conn, resource_type="secret_order", action="order.create",
                  status="failed", error_message=str(e)[:500])
        raise HTTPException(status_code=500, detail="Order 생성 실패")


@router.get("/{order_id}", response_model=OrderInfo)
async def get_order(
    order_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        return await asyncio.to_thread(bsvc.get_order, conn, order_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Order를 찾을 수 없습니다")


@router.delete("/{order_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_order(
    request: Request,
    order_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        await asyncio.to_thread(bsvc.delete_order, conn, order_id)
        await invalidate(f"afterglow:barbican:{pid}:orders*")
        await rec(token_info, conn, resource_type="secret_order", action="order.delete",
                  status="success", resource_id=order_id)
    except Exception as e:
        await rec(token_info, conn, resource_type="secret_order", action="order.delete",
                  status="failed", resource_id=order_id, error_message=str(e)[:500])
        raise HTTPException(status_code=500, detail="Order 삭제 실패")
