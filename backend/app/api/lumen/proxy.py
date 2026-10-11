"""Authenticated proxy for browser-facing Lumen API routes."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.api.deps import get_token_info
from app.api.identity.mcp_access import _require_browser_mutation
from app.config import get_settings
from app.services.mcp_control_plane import authority, defaults, lumen, registry
from app.services.service_authorization import current_service_principal
from app.services.service_permissions import require_service_permission
from app.services.service_proxy import proxy

router = APIRouter(dependencies=[Depends(get_token_info)])

_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class ApproveCloudToolsRequest(BaseModel):
    access_level: Literal["read", "manage"]


async def _require_cloud_tools_permission(request: Request) -> None:
    try:
        principal = await current_service_principal(request)
        require_service_permission(principal, "lumen-tools_user")
    except HTTPException as exc:
        exc.headers = {**(exc.headers or {}), **_NO_STORE}
        raise


@router.get("/cloud-tools")
async def cloud_tools(request: Request) -> Response:
    """Describe built-in cloud access; listing never creates a delegation."""
    await _require_cloud_tools_permission(request)
    info = request.state.token_info
    settings = get_settings()
    available = settings.service_mcp_enabled and bool(settings.lumen_mcp_service_token)
    enabled = False
    access_level = "read"
    tool_count = 0
    metadata = {
        "project_id": info["project_id"],
        "project_name": info.get("project_name") or info["project_id"],
        "source": "lumen",
        "allowed_projects": [],
        "selection_name": None,
        "expires_at": None,
    }
    if available:
        try:
            selected = await lumen.selected_lumen_snapshot(user_id=info["user_id"], project_id=info["project_id"])
            if selected is not None:
                cloud_principal = await lumen.resolve_lumen_principal(selected)
                access_level = "manage" if cloud_principal.can_write else "read"
                tool_count = len(registry.enabled_entries(cloud_principal))
                metadata = await lumen.selected_lumen_metadata(selected)
                enabled = True
        except lumen.McpLumenAuthorityError as exc:
            raise HTTPException(
                status_code=503, detail="Lumen cloud authority is unavailable", headers=_NO_STORE
            ) from exc
    return JSONResponse(
        {
            **metadata,
            "enabled": enabled,
            "available": available,
            "access_level": access_level,
            "tool_count": tool_count,
        },
        headers=_NO_STORE,
    )


def _require_cloud_tools_mutation(request: Request) -> None:
    settings = get_settings()
    if not settings.service_mcp_enabled or not settings.lumen_mcp_service_token:
        raise HTTPException(status_code=503, detail="Lumen cloud tools are unavailable", headers=_NO_STORE)
    try:
        _require_browser_mutation(request)
    except HTTPException as exc:
        exc.headers = {**(exc.headers or {}), **_NO_STORE}
        raise


def _raise_cloud_tools_error(exc: authority.McpAuthorityError) -> None:
    if isinstance(exc, authority.McpGrantPrivilegeError):
        raise HTTPException(
            status_code=403, detail="Lumen cloud management is not permitted", headers=_NO_STORE
        ) from exc
    if isinstance(exc, (authority.McpGrantStateError, authority.McpGrantLimitError)):
        raise HTTPException(
            status_code=409, detail="Lumen cloud authority changed or is pending", headers=_NO_STORE
        ) from exc
    raise HTTPException(status_code=503, detail="Lumen cloud authority is unavailable", headers=_NO_STORE) from exc


@router.post("/cloud-tools")
async def approve_cloud_tools(body: ApproveCloudToolsRequest, request: Request) -> Response:
    """Explicitly delegate cloud access for the caller's current project."""
    await _require_cloud_tools_permission(request)
    _require_cloud_tools_mutation(request)
    try:
        await defaults.approve_lumen_grant(token_info=request.state.token_info, access_level=body.access_level)
    except authority.McpAuthorityError as exc:
        _raise_cloud_tools_error(exc)
    return await cloud_tools(request)


@router.delete("/cloud-tools")
async def disable_cloud_tools(request: Request) -> Response:
    """Clear selection and revoke built-in Lumen access without deleting a PAT."""
    await _require_cloud_tools_permission(request)
    _require_cloud_tools_mutation(request)
    try:
        await defaults.disable_lumen_grant(token_info=request.state.token_info)
    except authority.McpAuthorityError as exc:
        _raise_cloud_tools_error(exc)
    return await cloud_tools(request)


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
    if path in {"audio/speech", "audio/transcriptions"}:
        # Native audio waits for a durable run before its first response byte.
        return await proxy("lumen", request, upstream_path, read_timeout=310.0)
    return await proxy("lumen", request, upstream_path)
