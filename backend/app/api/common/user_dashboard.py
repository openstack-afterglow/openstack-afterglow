"""Read-only caller inventory across current project memberships."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import CacheMode, cache_mode, get_os_conn
from app.services import keystone, user_inventory

if TYPE_CHECKING:
    import openstack

router = APIRouter()


@router.get("/summary")
async def get_user_dashboard_summary(
    request: Request,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    """Return 25 independent inventories, never an additive unique-resource sum."""
    token = conn._afterglow_token
    user_id = conn._afterglow_user_id
    current_project_id = conn._afterglow_project_id
    try:
        # This is Keystone's caller-membership list, not an administrative list.
        memberships = await asyncio.to_thread(keystone.list_projects, token)
        projects, seen = [], set()
        if not isinstance(memberships, list):
            raise ValueError("Invalid membership collection")
        for project in memberships:
            if not isinstance(project, dict):
                raise ValueError("Invalid membership")
            project_id, name = project.get("id"), project.get("name")
            if not isinstance(project_id, str) or not project_id or not isinstance(name, str):
                raise ValueError("Invalid membership identity")
            if project_id not in seen:
                seen.add(project_id)
                projects.append({"id": project_id, "name": name})
    except Exception as exc:
        state = user_inventory.failure(exc)["state"]
        raise HTTPException(403 if state == "denied" else 503, "Project memberships unavailable") from None

    results = await asyncio.gather(
        *(user_inventory.query_project(request, token, user_id, project, cm) for project in projects)
    )
    return {
        "user_id": user_id,
        "current_project_id": current_project_id,
        "projects": results,
        "totals": user_inventory.totals(results),
    }
