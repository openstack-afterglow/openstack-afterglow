from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Literal
from uuid import UUID

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, Query

from app.api.deps import CacheMode, cache_mode, get_os_conn, get_token_info, require_project_write
from app.models.compute import FlavorInfo
from app.models.flavor_composition import ComposerOptions, FlavorComposition, SavedCompositions
from app.services import cache, nova
from app.services.cache import keys

router = APIRouter()


@router.get("/composer-options", response_model=ComposerOptions)
async def composer_options(
    availability_zone: str | None = None,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    from app.services import flavor_composition

    return await flavor_composition.options(conn, conn._afterglow_project_id, availability_zone=availability_zone)


@router.get("/compositions", response_model=SavedCompositions)
async def saved_compositions(
    availability_zone: str | None = None,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    from app.services import flavor_composition

    return await flavor_composition.history(
        conn, conn._afterglow_project_id, token_info, availability_zone=availability_zone
    )


@router.get("/compositions/operations/{operation_id}", response_model=FlavorInfo | None)
async def composition_operation(
    operation_id: UUID,
    availability_zone: str | None = None,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(require_project_write),
):
    from app.services import flavor_composition

    return await flavor_composition.resolve(
        conn, conn._afterglow_project_id, token_info, operation_id, availability_zone=availability_zone
    )


@router.post("/compositions", response_model=FlavorInfo)
async def save_composition(
    request: FlavorComposition,
    availability_zone: str | None = None,
    operation_id: UUID | None = None,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(require_project_write),
):
    from app.services import flavor_composition

    return await flavor_composition.save(
        conn,
        conn._afterglow_project_id,
        token_info,
        request,
        operation_id=operation_id,
        availability_zone=availability_zone,
    )


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

    if capacity == "create":
        from app.services.flavor_discovery import list_flavors as discovery_flavors

        all_flavors = await discovery_flavors(conn)
    else:
        all_flavors = await cache.cached_call(key, cache.ttl_static(), _load, enabled=cm.enabled, refresh=cm.refresh)
        # A Redis cache hit returns JSON-decoded dicts; eligibility needs typed models.
        all_flavors = [FlavorInfo.model_validate(f) if isinstance(f, dict) else f for f in all_flavors]
        if cm.enabled:
            # Metadata never authorizes a public/private transition or revoked grant.
            visibility = await asyncio.to_thread(nova.project_flavor_visibility, conn)
            all_flavors = [
                flavor.model_copy(update={"is_public": visibility[flavor.id]})
                for flavor in all_flavors
                if flavor.id in visibility
            ]
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
        include_gpu_projection=True,
    )
