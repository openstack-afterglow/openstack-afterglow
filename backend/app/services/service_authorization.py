"""Action gates before browser traffic reaches extracted native services.

Native services remain the authority for resource ownership, credential scopes,
model-derived actions and machine tickets. Browser role claims are not a cache
of current authority: resolve the trusted project role-ID graph for each request.
"""

from __future__ import annotations

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
        # Only the already verified system flag bypasses project action gates.
        # Palimpsest's classifier preserves its separate protected-owner rules.
        principal = {"user_id": user_id, "project_id": project_id, "roles": [], "is_system_admin": True}
    else:
        access = await project_service.get_project_access(project_id, user_id)
        principal = {"user_id": user_id, "project_id": project_id, "roles": access["roles"], "is_system_admin": False}
    request.state.current_service_principal = (identity, principal)
    return principal


async def authorize_service_request(service_type: str, request: Request, upstream_path: str) -> None:
    """Authorize browser action only; never reinterpret machine credentials."""
    if request.method == "OPTIONS":
        return
    principal = await current_service_principal(request)
    if service_type == "lumen":
        from app.services.lumen_authorization import authorize_lumen_request

        await authorize_lumen_request(request, upstream_path, principal)
    elif service_type == "waygate":
        from app.services.waygate_authorization import authorize_waygate_request

        await authorize_waygate_request(request, upstream_path, principal)
    elif service_type == "drover":
        from app.services.drover_authorization import authorize_drover_request

        await authorize_drover_request(request, upstream_path, principal)
    elif service_type == "palimpsest":
        from app.services.palimpsest_authorization import authorize_palimpsest_request

        await authorize_palimpsest_request(request, upstream_path, principal)
    else:
        raise HTTPException(status_code=403, detail="알 수 없는 서비스 작업입니다")
