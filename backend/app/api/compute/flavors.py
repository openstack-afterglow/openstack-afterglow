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


async def _rehydrate_cached_flavor(conn: openstack.connection.Connection, flavor: object) -> FlavorInfo:
    """Restore authoritative flavor metadata lost by JSON cache deserialization."""
    if not isinstance(flavor, dict):
        return flavor

    flavor_id = flavor.get("id")
    if not flavor_id:
        return FlavorInfo.model_validate(flavor)
    try:
        detail = await asyncio.to_thread(conn.compute.get_flavor, flavor_id)
    except Exception:
        return FlavorInfo.model_validate(flavor)

    def _value(name: str, default=None):
        if isinstance(detail, dict):
            return detail.get(name, flavor.get(name, default))
        return getattr(detail, name, flavor.get(name, default))

    return FlavorInfo(
        id=str(_value("id", flavor_id)),
        name=str(_value("name", "")),
        vcpus=int(_value("vcpus", 0)),
        ram=int(_value("ram", 0)),
        disk=int(_value("disk", 0)),
        is_public=bool(_value("is_public", True)),
        extra_specs=dict(_value("extra_specs", {}) or {}),
    )


async def _rehydrate_cached_flavors(conn: openstack.connection.Connection, flavors: list[object]) -> list[FlavorInfo]:
    return list(await asyncio.gather(*(_rehydrate_cached_flavor(conn, flavor) for flavor in flavors)))


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
    all_flavors = await _rehydrate_cached_flavors(conn, all_flavors)
    from app.services.flavor_eligibility import evaluate_project_flavors, is_flavor_frontend_visible
    from app.services.gpu_inventory import is_gpu_flavor

    visible_flavors = [flavor for flavor in all_flavors if is_flavor_frontend_visible(flavor)]

    try:
        return await evaluate_project_flavors(conn, pid, visible_flavors)
    except Exception:
        return [f for f in visible_flavors if not is_gpu_flavor(f)]
