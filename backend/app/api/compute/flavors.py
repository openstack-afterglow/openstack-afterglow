from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends

from app.api.deps import CacheMode, cache_mode, get_os_conn
from app.models.compute import FlavorInfo
from app.services import cache, nova
from app.services.cache import keys

router = APIRouter()


@router.get("", response_model=list[FlavorInfo])
async def list_flavors(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    pid = conn._afterglow_project_id
    key = keys.project_key("nova", pid, "flavors")

    async def _load() -> list[FlavorInfo]:
        return await asyncio.to_thread(nova.list_flavors, conn)

    all_flavors = await cache.cached_call(key, cache.ttl_static(), _load, enabled=cm.enabled, refresh=cm.refresh)
    from app.services.flavor_eligibility import evaluate_project_flavors, is_flavor_frontend_visible
    from app.services.gpu_inventory import is_gpu_flavor

    visible_flavors = [flavor for flavor in all_flavors if is_flavor_frontend_visible(flavor)]

    try:
        evaluated = await evaluate_project_flavors(conn, pid, visible_flavors)
        has_gpu_authority_error = any(
            any(b.code == "gpu_quota_unavailable" for b in (f.eligibility.blockers if f.eligibility else []))
            for f in evaluated
            if is_gpu_flavor(f)
        )
        if has_gpu_authority_error:
            return [f for f in visible_flavors if not is_gpu_flavor(f)]
        return evaluated
    except Exception:
        return [f for f in visible_flavors if not is_gpu_flavor(f)]
