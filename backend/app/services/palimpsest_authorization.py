"""Current original-subject scope for custom package I/O outside the proxy.

Palimpsest's native oslo.policy owns actions and operator overrides. The BFF
never exchanges the original subject or converts grade roles into leaf roles.
"""

from __future__ import annotations

import asyncio

from fastapi import HTTPException, Request


async def authorize_current_package_request(
    request: Request, upstream_path: str, info: dict, *, method: str | None = None
) -> None:
    """Revalidate current project/system scope before original-subject transport."""
    from app.services import keystone
    from app.services.project_service import get_project_access

    system_admin = await asyncio.to_thread(keystone._has_system_admin_role, info["user_id"])
    if system_admin:
        from app.api.deps import require_admin

        # Human authority, original credential and target are independently
        # checked even after a previous preflight in the same request.
        await require_admin({**info, "is_system_admin": True})
        info["_live_system_admin"] = True
    else:
        access = await get_project_access(info["project_id"], info["user_id"])
        if not access["roles"]:
            raise HTTPException(status_code=403, detail="Current project membership is required")
        info.pop("_live_system_admin", None)
