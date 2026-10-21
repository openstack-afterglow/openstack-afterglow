"""Current browser scope and native-service policy capability boundaries.

Extracted services own action policy, including operator YAML overrides. BFF
session/project validation never reconstructs service permissions from roles.
"""

from __future__ import annotations

import asyncio
import re

from fastapi import HTTPException, Request

from app.services import project_service


async def current_service_principal(request: Request) -> dict:
    token_info = getattr(request.state, "token_info", None)
    if not isinstance(token_info, dict):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    user_id, project_id = token_info.get("user_id"), token_info.get("project_id")
    if not isinstance(user_id, str) or not user_id or not isinstance(project_id, str) or not project_id:
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    identity = (user_id, project_id, token_info.get("is_system_admin") is True)
    cached = getattr(request.state, "current_service_principal", None)
    if cached is not None and cached[0] == identity:
        return cached[1]
    if identity[2]:
        from app.api.deps import require_admin

        if token_info.get("_live_system_admin") is not True:
            await require_admin(token_info)
        # Verified human system authority is scoped separately from service
        # policy, native credential ceilings and resource ownership.
        principal = {**token_info, "user_id": user_id, "project_id": project_id, "is_system_admin": True}
    else:
        access = await project_service.get_project_access(project_id, user_id)
        if not access["roles"]:
            raise HTTPException(status_code=403, detail="Current project membership is required")
        principal = {**token_info, "roles": access["roles"], "is_system_admin": False}
    request.state.current_service_principal = (identity, principal)
    return principal


async def authorize_service_request(service_type: str, request: Request, upstream_path: str) -> None:
    """Validate current browser scope; the native action handler enforces policy."""
    from app.services.service_permissions import SERVICE_ROLE_GRADES

    if service_type not in SERVICE_ROLE_GRADES:
        raise HTTPException(status_code=403, detail="알 수 없는 서비스 작업입니다")
    if request.method == "OPTIONS":
        return
    principal = await current_service_principal(request)
    if (
        service_type == "lumen"
        and upstream_path.startswith("/v1/admin/")
        and principal.get("is_system_admin") is not True
    ):
        raise HTTPException(status_code=403, detail="시스템 관리자 권한이 필요합니다")
    if service_type in {"drover", "waygate"}:
        if not upstream_path.startswith("/v1/"):
            raise HTTPException(status_code=403, detail="Unknown native browser namespace")
        path = upstream_path[4:].removesuffix("/")
        parts = path.split("/") if path else []
        if any(not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._-]*", part) for part in parts):
            raise HTTPException(status_code=403, detail="Unknown native browser namespace")
        if (service_type == "drover" and parts and (parts[0] == "callback" or parts[-1] == "shell")) or (
            service_type == "waygate" and "agent" in parts
        ):
            raise HTTPException(status_code=403, detail="Machine route is not a browser operation")
        system_route = parts and (
            parts[0] == "admin"
            or (service_type == "drover" and parts[0] == "cluster-templates" and request.method not in {"GET", "HEAD"})
        )
        if system_route and principal.get("is_system_admin") is not True:
            raise HTTPException(status_code=403, detail="시스템 관리자 권한이 필요합니다")


async def service_permission_snapshot(token_info: dict) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Project native decisions for UI, preserving unavailable versus denied."""
    from app.config import get_settings
    from app.services.service_proxy import get_policy_capabilities

    settings = get_settings()
    enabled = {
        "lumen": settings.service_chat_enabled,
        "drover": settings.service_k3s_enabled,
        "waygate": settings.service_waygate_enabled,
        "palimpsest": settings.service_palimpsest_enabled,
    }

    async def evaluate(service):
        if not enabled[service]:
            return service, [], None
        try:
            result = await get_policy_capabilities(service, token_info)
        except HTTPException:
            return service, [], "permission_check_unavailable"
        return service, sorted(set(result["capabilities"])), None

    results = await asyncio.gather(*(evaluate(service) for service in enabled))
    return (
        {service: leaves for service, leaves, _ in results},
        {service: error for service, _, error in results if error is not None},
    )
