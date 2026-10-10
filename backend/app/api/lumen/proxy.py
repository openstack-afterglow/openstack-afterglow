"""Authenticated proxy for browser-facing Lumen API routes."""

from contextlib import aclosing

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.api.deps import get_os_conn, get_token_info
from app.config import get_settings
from app.services.mcp_control_plane import authority, defaults, lumen, registry
from app.services.service_authorization import authorize_service_request, current_service_principal
from app.services.service_permissions import require_service_permission
from app.services.service_proxy import proxy

router = APIRouter(dependencies=[Depends(get_token_info)])

_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


@router.get("/cloud-tools")
async def cloud_tools(request: Request) -> Response:
    """Describe built-in cloud access; listing never creates a delegation."""
    principal = await current_service_principal(request)
    require_service_permission(principal, "lumen-tools_user")
    info = request.state.token_info
    settings = get_settings()
    enabled = settings.service_mcp_enabled and bool(settings.lumen_mcp_service_token)
    access_level = "read"
    tool_count = 0
    metadata = {
        "source": "lumen",
        "allowed_projects": [{"id": info["project_id"], "name": info.get("project_name") or info["project_id"]}],
        "selection_name": None,
    }
    if enabled:
        try:
            selected = await lumen.selected_lumen_snapshot(user_id=info["user_id"], project_id=info["project_id"])
            if selected is not None:
                cloud_principal = await lumen.resolve_lumen_principal(selected)
                access_level = "manage" if cloud_principal.can_write else "read"
                tool_count = len(registry.enabled_entries(cloud_principal))
                metadata = await lumen.selected_lumen_metadata(selected)
            else:
                # This is catalogue availability, not an execution principal.
                tool_count = sum(entry.enabled() and entry.minimum_scope == "mcp:read" for entry in registry._ENTRIES)
        except lumen.McpLumenAuthorityError as exc:
            raise HTTPException(status_code=503, detail="Lumen cloud authority is unavailable") from exc
    return JSONResponse(
        {
            **metadata,
            "enabled": enabled,
            "access_level": access_level,
            "project_id": info["project_id"],
            "project_name": info.get("project_name") or info["project_id"],
            "tool_count": tool_count,
        },
        headers={"Cache-Control": "no-store"},
    )


async def _prepare_cloud_tools(path: str, request: Request, upstream_path: str) -> None:
    settings = get_settings()
    if request.method != "POST" or not settings.service_mcp_enabled or not settings.lumen_mcp_service_token:
        return
    parts = path.strip("/").split("/")
    native = path == "temp-completions" or (
        len(parts) == 3 and parts[0] == "conversations" and parts[2] in {"completions", "regenerate"}
    )
    if not native:
        return
    try:
        body = await request.json()
    except ValueError:
        return  # Native schema owns malformed request errors.
    if not isinstance(body, dict):
        return
    features = body.get("features")
    policy = features.get("tool_policy") if isinstance(features, dict) else None
    if isinstance(policy, dict) and policy.get("mode") == "none":
        return
    # Current service authority must pass before creating any cloud credential.
    await authorize_service_request("lumen", request, upstream_path)
    info = request.state.token_info
    try:
        async with aclosing(get_os_conn(info)) as connections:
            conn = await anext(connections)
            await defaults.ensure_default_lumen_grant(conn=conn, token_info=info)
    except authority.McpAuthorityError as exc:
        raise HTTPException(status_code=503, detail="Lumen cloud delegation could not be prepared") from exc


@router.api_route("", methods=_PROXY_METHODS)
@router.api_route("/{path:path}", methods=_PROXY_METHODS)
async def proxy_lumen(path: str = "", *, request: Request) -> Response:
    if path == "models":
        upstream_path = "/v1/chat/models"
    elif path in {
        "images/generations",
        "images/edits",
        "audio/speech",
        "audio/transcriptions",
    }:
        upstream_path = f"/v1/chat/{path}"
    else:
        upstream_path = "/v1" if not path else f"/v1/{path}"
    await _prepare_cloud_tools(path, request, upstream_path)
    if path in {"audio/speech", "audio/transcriptions"}:
        # Native audio waits for a durable run before its first response byte.
        return await proxy("lumen", request, upstream_path, read_timeout=310.0)
    return await proxy("lumen", request, upstream_path)
