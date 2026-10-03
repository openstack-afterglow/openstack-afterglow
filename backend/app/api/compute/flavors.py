from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, Query

from app.api.deps import CacheMode, cache_mode, get_os_conn
from app.models.compute import FlavorInfo
from app.services import cache, nova
from app.services.cache import keys

router = APIRouter()


@router.get("", response_model=list[FlavorInfo])
async def list_flavors(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
    availability_zone: str | None = None,
    capacity: Literal["create"] | None = Query(
        None, description="create: 단일 VM 생성용 같은 호스트 용량을 함께 평가 (VM 생성 마법사 전용)"
    ),
):
    pid = conn._afterglow_project_id
    key = keys.project_key("nova", pid, "flavors")

    async def _load() -> list[FlavorInfo]:
        return await asyncio.to_thread(nova.list_flavors, conn)

    all_flavors = await cache.cached_call(key, cache.ttl_static(), _load, enabled=cm.enabled, refresh=cm.refresh)
    # A Redis cache hit returns JSON-decoded dicts; eligibility needs typed models.
    all_flavors = [FlavorInfo.model_validate(f) if isinstance(f, dict) else f for f in all_flavors]
    from app.services.flavor_eligibility import evaluate_project_flavors, is_flavor_frontend_visible

    visible_flavors = [flavor for flavor in all_flavors if is_flavor_frontend_visible(flavor)]

    # Shared consumers (K3s, Drover prefetch) stay quota-only and never touch operator Placement reads.
    return await evaluate_project_flavors(
        conn,
        pid,
        visible_flavors,
        check_capacity=capacity == "create",
        availability_zone=availability_zone,
        fresh_capacity=False,
    )
