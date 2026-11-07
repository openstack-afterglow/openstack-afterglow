"""Read-only caller inventory across current project memberships."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import CacheMode, cache_mode, get_os_conn
from app.services import keystone, user_inventory

if TYPE_CHECKING:
    import openstack

router = APIRouter()


@router.get("/summary")
async def get_user_dashboard_summary(
    request: Request,
    response: Response,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    """Return 25 independent inventories, never an additive unique-resource sum."""
    token = conn._afterglow_token
    user_id = conn._afterglow_user_id
    current_project_id = conn._afterglow_project_id
    domain_id = getattr(conn, "_afterglow_domain_id", None)
    if not isinstance(domain_id, str) or not domain_id:
        raise HTTPException(403, "Authenticated domain is required")
    t0 = time.perf_counter()
    try:
        # This is Keystone's caller-membership list, not an administrative list.
        memberships = await asyncio.to_thread(keystone.list_projects, token, domain_id)
        t_memberships = (time.perf_counter() - t0) * 1000
        projects, seen = [], set()
        if not isinstance(memberships, list):
            raise ValueError("Invalid membership collection")
        for project in memberships:
            if not isinstance(project, dict):
                raise ValueError("Invalid membership")
            project_id, name = project.get("id"), project.get("name")
            if not isinstance(project_id, str) or not project_id or not isinstance(name, str):
                raise ValueError("Invalid membership identity")
            if project.get("domain_id") != domain_id:
                continue
            if project_id not in seen:
                seen.add(project_id)
                projects.append({"id": project_id, "name": name})
    except Exception as exc:
        state = user_inventory.failure(exc)["state"]
        raise HTTPException(403 if state == "denied" else 503, "Project memberships unavailable") from None
    t1 = time.perf_counter()
    ks, catalog = None, None
    try:
        from app.services import identity_roles

        ks = await keystone._provider_call(keystone._get_admin_ks_client)
        catalog = await identity_roles._provider_call(identity_roles._trusted_catalog)
    except Exception:
        pass
    results = await asyncio.gather(
        *(
            user_inventory.query_project(request, token, user_id, project, cm, ks=ks, catalog=catalog)
            for project in projects
        )
    )
    t_inventories = (time.perf_counter() - t1) * 1000
    response.headers["Server-Timing"] = f"memberships;dur={t_memberships:.1f}, inventories;dur={t_inventories:.1f}"
    return {
        "user_id": user_id,
        "current_project_id": current_project_id,
        "domain_id": domain_id,
        "projects": results,
        "totals": user_inventory.totals(results),
    }
