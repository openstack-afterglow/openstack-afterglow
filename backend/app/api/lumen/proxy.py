"""Authenticated proxy for browser-facing Lumen API routes."""

import re
from collections.abc import AsyncIterator, Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.api.deps import get_token_info, require_domain_manager
from app.api.identity.mcp_access import _require_browser_mutation
from app.config import get_settings
from app.services.mcp_control_plane import authority, credential_state, defaults, lumen, registry
from app.services.service_authorization import current_service_principal
from app.services.service_permissions import require_service_permission
from app.services.service_proxy import get_policy_capabilities, proxy

_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}
_DOMAIN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_DECISIONS_MAX_BODY_BYTES = 20 * 1024 * 1024
_VAULT_METHODS = {
    "notes": ("GET", "POST"),
    "search": ("GET",),
    "document": ("GET",),
    "short-term": ("GET", "PUT"),
    "profile": ("GET", "PUT"),
    "coding-standards": ("GET", "PUT"),
}


def _credential_or_pool_route(parts: list[str]) -> tuple[str, ...] | None:
    """Allowed browser methods; an empty tuple denies unknown descendants."""
    if parts[:1] in (["api-keys"], ["service-keys"]):
        if len(parts) == 1:
            return ("GET", "POST")
        if parts[1:] == ["issuance-policy"]:
            return ("GET",)
        if parts[1].isascii() and parts[1].isdecimal():
            if len(parts) == 2:
                return ("PATCH", "DELETE") if parts[0] == "api-keys" else ("DELETE",)
            if parts[2:] == ["limits"]:
                return ("PATCH",)
        return ()
    if parts[:1] == ["domain-pool"]:
        return ("GET", "PATCH") if len(parts) == 1 else ()
    if parts[:2] == ["admin", "domain-pools"]:
        if len(parts) == 2:
            return ("GET",)
        if _DOMAIN_ID.fullmatch(parts[2]):
            if len(parts) == 3:
                return ("PATCH",)
            if parts[3:] == ["topups"]:
                return ("POST",)
        return ()
    if parts[:2] == ["admin", "service-keys"]:
        return ("GET",) if len(parts) == 2 else ()
    return None


async def _bounded_decisions_body(request: Request) -> AsyncIterator[bytes]:
    """Admit the complete opaque body before opening the upstream request."""
    limit_error = HTTPException(status_code=413, detail="decision_request_too_large")
    declared = request.headers.get("content-length", "")
    if declared.isascii() and declared.isdecimal():
        # Compare normalized digits first; never parse an unbounded integer.
        digits = declared.lstrip("0")
        limit = str(_DECISIONS_MAX_BODY_BYTES)
        if (len(digits), digits) > (len(limit), limit):
            raise limit_error

    principal = await current_service_principal(request)
    native = await get_policy_capabilities("lumen", principal, timeout=5.0)
    require_service_permission(
        {**principal, "service_permissions": {"lumen": native["capabilities"]}}, "lumen-chat_user"
    )

    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > _DECISIONS_MAX_BODY_BYTES:
            raise limit_error
        if chunk:
            chunks.append(chunk)

    async def replay() -> AsyncIterator[bytes]:
        for chunk in chunks:
            yield chunk

    return replay()


def _noncanonical_path(parts: list[str]) -> bool:
    return any(part in {"", ".", ".."} or any(char in part for char in "?#\\") for part in parts)


class _PrivateLumenRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def private_response(request: Request) -> Response:
            path = request.path_params.get("path", "")
            parts = path.split("/") if path else []
            source_response = (len(parts) == 3 and parts[0] == "assets" and parts[2] == "download-link") or (
                len(parts) == 4 and parts[0] == "runs" and parts[2] == "sources"
            )
            private = (
                _noncanonical_path(parts)
                or source_response
                or parts == ["usage"]
                or _credential_or_pool_route(parts) is not None
                or parts[:1] in (["embeddings"], ["decisions"], ["vault"])
                or parts[:3] == ["admin", "models", "native-catalog"]
                or (bool(parts) and parts[0].startswith("mcp-"))
                or parts[:2] == ["admin", "providers"]
                or (len(parts) >= 2 and parts[0] == "admin" and parts[1].startswith("mcp-"))
                or parts[:1] == ["archived-connections"]
                or (len(parts) >= 3 and parts[0] == "domains"
                    and parts[2] in {"mcp-connections", "archived-connections"})
            )
            try:
                response = await handler(request)
            except HTTPException as exc:
                if private:
                    exc.headers = {**(exc.headers or {}), **_NO_STORE}
                raise
            if private:
                response.headers.update(_NO_STORE)
            return response

        return private_response


router = APIRouter(dependencies=[Depends(get_token_info)], route_class=_PrivateLumenRoute)


class ApproveCloudToolsRequest(BaseModel):
    access_level: Literal["read", "manage"]


async def _require_cloud_tools_permission(request: Request) -> None:
    try:
        principal = await current_service_principal(request)
        native = await get_policy_capabilities("lumen", principal)
        principal = {**principal, "service_permissions": {"lumen": native["capabilities"]}}
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
    state = "ok"
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
                state = "invalid" if await credential_state.is_invalid(selected.grant_id) else "ok"
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
            "credential_state": state,
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


async def _proxy_vault(parts: list[str], request: Request) -> Response:
    """Limit the browser surface to dashboard Vault operations."""
    tail = parts[1:]
    allowed = _VAULT_METHODS.get(tail[0]) if len(tail) == 1 else None
    if len(tail) >= 2 and tail[0] == "notes" and tail[1].isascii() and tail[1].isdecimal():
        if len(tail) == 2:
            allowed = ("GET", "PATCH")
        elif tail[2:] == ["revisions"]:
            allowed = ("GET",)
    if allowed is None:
        raise HTTPException(status_code=404, detail="Lumen browser route not found")
    if request.method not in allowed:
        raise HTTPException(status_code=405, detail="Method not allowed", headers={"Allow": ", ".join(allowed)})

    principal = await current_service_principal(request)
    native = await get_policy_capabilities("lumen", principal)
    leaf = "lumen-history_reader" if request.method == "GET" else "lumen-history_editor"
    require_service_permission({**principal, "service_permissions": {"lumen": native["capabilities"]}}, leaf)
    return await proxy("lumen", request, "/v1/" + "/".join(parts))


@router.api_route("", methods=_PROXY_METHODS)
@router.api_route("/{path:path}", methods=_PROXY_METHODS)
async def proxy_lumen(path: str = "", *, request: Request) -> Response:
    parts = path.split("/") if path else []
    if _noncanonical_path(parts):
        # Authorization and forwarding must interpret the exact same namespace.
        raise HTTPException(status_code=400, detail="Non-canonical Lumen API path", headers=_NO_STORE)
    if parts[:1] == ["vault"]:
        return await _proxy_vault(parts, request)
    if parts[:4] == ["admin", "models", "pricing", "models-dev"]:
        raise HTTPException(status_code=404, detail="Lumen browser route not found", headers=_NO_STORE)
    credential_or_pool = _credential_or_pool_route(parts)
    if credential_or_pool == ():
        raise HTTPException(status_code=404, detail="Lumen browser route not found")
    if credential_or_pool is not None and request.method not in credential_or_pool:
        raise HTTPException(
            status_code=405, detail="Method not allowed", headers={"Allow": ", ".join(credential_or_pool)}
        )
    if parts[:1] in (["service-keys"], ["domain-pool"]):
        await require_domain_manager(request.state.token_info)
    expected_method = {"decisions": "POST", "admin/models/native-catalog": "GET"}.get(path)
    if expected_method is not None and request.method != expected_method:
        raise HTTPException(
            status_code=405,
            detail="Method not allowed",
            headers={**_NO_STORE, "Allow": expected_method},
        )
    if path == "models":
        upstream_path = "/v1/chat/models"
    elif path in {
        "images/generations",
        "images/edits",
        "audio/speech",
        "audio/transcriptions",
        "embeddings",
        "decisions",
    }:
        upstream_path = f"/v1/chat/{path}"
    else:
        upstream_path = "/v1" if not path else f"/v1/{path}"
    if path in {"audio/speech", "audio/transcriptions"}:
        # Native audio waits for a durable run before its first response byte.
        return await proxy("lumen", request, upstream_path, read_timeout=310.0)
    if path == "decisions":
        return await proxy("lumen", request, upstream_path, read_timeout=125.0, prepare_body=_bounded_decisions_body)
    if credential_or_pool is not None:
        return await proxy("lumen", request, upstream_path, sensitive=True)
    return await proxy("lumen", request, upstream_path)
