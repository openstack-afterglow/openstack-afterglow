"""Browser-only management routes for project-bound inbound MCP authority."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_os_conn, get_token_info
from app.config import get_settings
from app.database import get_session_factory
from app.rate_limit import limiter
from app.services import activity
from app.services.activity import _audit_ctx
from app.services.mcp_control_plane.authority import (
    McpAuthorityError,
    McpGrantLimitError,
    McpGrantNotFoundError,
    confirm_keystone_cleanup,
    issue_personal_token,
    list_oauth_grants,
    list_personal_tokens,
    personal_token_grant_id,
    revoke_grant,
    set_lumen_selection,
)
from app.services.mcp_control_plane.verification import (
    McpConnectionCheckError,
    verify_personal_mcp_connection,
)

router = APIRouter()


class CreateMcpTokenRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    access_level: str = Field(pattern="^(read|manage)$")
    expires_at: datetime | None = None


class McpTokenView(BaseModel):
    id: str
    grant_id: str
    name: str
    source: str
    access_level: str
    status: str
    visible_prefix: str | None
    issued_at: datetime | None
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    is_lumen_default: bool


class CreateMcpTokenResponse(McpTokenView):
    token: str


class McpLumenSelectionResponse(BaseModel):
    lumen_selection_generation: int


def _normalized_origin(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _require_mcp_enabled() -> None:
    if not get_settings().service_mcp_enabled:
        raise HTTPException(status_code=404, detail="Not Found")


def _require_browser_mutation(request: Request) -> None:
    _require_mcp_enabled()
    settings = get_settings()
    request_origin = _normalized_origin(request.headers.get("origin", ""))
    fetch_site = request.headers.get("sec-fetch-site")
    allowed = {
        normalized
        for candidate in (settings.frontend_base_url, settings.public_api_base, *settings.cors_origin_list)
        if (normalized := _normalized_origin(candidate))
    }
    if request_origin not in allowed or fetch_site not in {"same-origin", "same-site"}:
        raise HTTPException(status_code=403, detail="MCP access management requires a same-site browser request")


def _mark_transactional_audit() -> None:
    if (holder := _audit_ctx.get()) is not None:
        holder["logged"] = True


def _session_factory() -> async_sessionmaker[AsyncSession]:
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="MCP authority storage is unavailable")
    return factory


def _raise_authority_error(exc: McpAuthorityError) -> None:
    if isinstance(exc, McpGrantNotFoundError):
        raise HTTPException(status_code=404, detail="MCP grant was not found") from exc
    if isinstance(exc, McpGrantLimitError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/mcp-tokens", response_model=list[McpTokenView])
async def get_mcp_tokens(request: Request, token_info: dict = Depends(get_token_info)):
    _require_mcp_enabled()
    async with _session_factory()() as session:
        return await list_personal_tokens(
            session, owner_user_id=token_info["user_id"], owner_project_id=token_info["project_id"]
        )


@router.post("/mcp-tokens", response_model=CreateMcpTokenResponse, status_code=status.HTTP_201_CREATED)
async def create_mcp_token(
    body: CreateMcpTokenRequest,
    request: Request,
    token_info: dict = Depends(get_token_info),
    conn=Depends(get_os_conn),
):
    _require_browser_mutation(request)
    try:
        issued = await issue_personal_token(
            _session_factory(),
            conn=conn,
            owner_user_id=token_info["user_id"],
            owner_project_id=token_info["project_id"],
            username=token_info.get("username", token_info["user_id"]),
            roles=token_info.get("roles", []),
            display_name=body.name,
            access_level=body.access_level,
            expires_at=body.expires_at,
        )
    except McpAuthorityError as exc:
        _raise_authority_error(exc)
    response = CreateMcpTokenResponse(
        token=issued.token,
        id=issued.token_id,
        grant_id=issued.grant_id,
        name=body.name.strip(),
        source="personal_token",
        access_level=issued.access_level,
        status="active",
        visible_prefix=issued.token[:20],
        issued_at=datetime.now(UTC),
        expires_at=issued.expires_at,
        last_used_at=None,
        revoked_at=None,
        is_lumen_default=False,
    )
    _mark_transactional_audit()
    return response


class McpConnectionCheckView(BaseModel):
    endpoint: str
    protocol_version: str
    server_name: str
    server_version: str
    tool_count: int


_VERIFY_MAX_BODY_BYTES = 1024
_VERIFY_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}
_VERIFY_FAILURES: dict[str, tuple[int, str]] = {
    "invalid_request": (400, "MCP connection check request is invalid"),
    "invalid_token": (400, "MCP personal key is invalid, expired, revoked, or not owned by this project"),
    "not_configured": (503, "MCP public endpoint is not configured"),
    "rejected": (502, "MCP endpoint rejected the personal key"),
    "redirect": (502, "MCP endpoint redirected; redirects are not followed"),
    "unavailable": (504, "MCP endpoint is unreachable or did not respond in time"),
    "protocol": (502, "MCP endpoint returned an invalid MCP response"),
}


async def _verification_token(request: Request) -> str | None:
    """Parse ``{"token": str}`` without ever echoing the submitted value."""
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        return None
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > _VERIFY_MAX_BODY_BYTES:
            return None
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or set(payload) != {"token"} or not isinstance(payload["token"], str):
        return None
    return payload["token"]


async def _audit_verification(token_info: dict, *, status_code: int, failure: str | None) -> None:
    holder = _audit_ctx.get() or {}
    await activity.record(
        project_id=token_info["project_id"],
        user_id=token_info["user_id"],
        username=token_info.get("username", ""),
        resource_type="mcp_grant",
        action="mcp_grant.verify",
        status="failed" if failure else "success",
        error_message=_VERIFY_FAILURES[failure][1] if failure else None,
        request_id=holder.get("request_id"),
        service=holder.get("service"),
        source="afterglow",
        page=holder.get("page"),
        http_status=status_code,
    )


@router.post("/mcp-tokens/verify", response_model=McpConnectionCheckView)
@limiter.limit("6/minute")
async def verify_mcp_token_connection(request: Request, token_info: dict = Depends(get_token_info)):
    """Prove a saved personal key works at the public MCP resource (read-only handshake)."""
    try:
        _require_browser_mutation(request)
        _session_factory()
    except HTTPException as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=_VERIFY_NO_STORE)
    raw_token = await _verification_token(request)
    failure: str | None = "invalid_request" if raw_token is None else None
    result = None
    if raw_token is not None:
        try:
            result = await verify_personal_mcp_connection(
                raw_token, owner_user_id=token_info["user_id"], owner_project_id=token_info["project_id"]
            )
        except McpConnectionCheckError as exc:
            failure = exc.reason
    if failure is not None or result is None:
        failure = failure or "protocol"
        status_code, detail = _VERIFY_FAILURES[failure]
        await _audit_verification(token_info, status_code=status_code, failure=failure)
        # Returned directly: the global handler would replace 5xx details and drop no-store.
        return JSONResponse({"detail": detail, "code": failure}, status_code=status_code, headers=_VERIFY_NO_STORE)
    await _audit_verification(token_info, status_code=200, failure=None)
    view = McpConnectionCheckView(
        endpoint=result.endpoint,
        protocol_version=result.protocol_version,
        server_name=result.server_name,
        server_version=result.server_version,
        tool_count=result.tool_count,
    )
    return JSONResponse(view.model_dump(), headers=_VERIFY_NO_STORE)


@router.delete("/mcp-tokens/lumen-default", response_model=McpLumenSelectionResponse)
async def clear_mcp_lumen_default(request: Request, token_info: dict = Depends(get_token_info)):
    _require_browser_mutation(request)
    try:
        generation = await set_lumen_selection(
            _session_factory(),
            owner_user_id=token_info["user_id"],
            owner_project_id=token_info["project_id"],
            username=token_info.get("username", token_info["user_id"]),
            grant_id=None,
        )
    except McpAuthorityError as exc:
        _raise_authority_error(exc)
    _mark_transactional_audit()
    return McpLumenSelectionResponse(lumen_selection_generation=generation)


@router.delete("/mcp-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_token(
    token_id: str,
    request: Request,
    token_info: dict = Depends(get_token_info),
    conn=Depends(get_os_conn),
):
    _require_browser_mutation(request)
    factory = _session_factory()
    try:
        async with factory() as session:
            grant_id = await personal_token_grant_id(
                session,
                token_id=token_id,
                owner_user_id=token_info["user_id"],
                owner_project_id=token_info["project_id"],
            )
        credential_id, _ = await revoke_grant(
            factory,
            grant_id=grant_id,
            owner_user_id=token_info["user_id"],
            owner_project_id=token_info["project_id"],
            username=token_info.get("username", token_info["user_id"]),
        )
        await confirm_keystone_cleanup(
            factory,
            conn=conn,
            grant_id=grant_id,
            owner_user_id=token_info["user_id"],
            owner_project_id=token_info["project_id"],
            username=token_info.get("username", token_info["user_id"]),
            application_credential_id=credential_id,
        )
    except McpAuthorityError as exc:
        _raise_authority_error(exc)
    _mark_transactional_audit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/mcp-tokens/{token_id}/lumen-default", response_model=McpLumenSelectionResponse)
async def set_mcp_lumen_default(
    token_id: str,
    request: Request,
    token_info: dict = Depends(get_token_info),
):
    _require_browser_mutation(request)
    factory = _session_factory()
    try:
        async with factory() as session:
            grant_id = await personal_token_grant_id(
                session,
                token_id=token_id,
                owner_user_id=token_info["user_id"],
                owner_project_id=token_info["project_id"],
            )
        generation = await set_lumen_selection(
            factory,
            owner_user_id=token_info["user_id"],
            owner_project_id=token_info["project_id"],
            username=token_info.get("username", token_info["user_id"]),
            grant_id=grant_id,
        )
    except McpAuthorityError as exc:
        _raise_authority_error(exc)
    _mark_transactional_audit()
    return McpLumenSelectionResponse(lumen_selection_generation=generation)


@router.get("/mcp-oauth/grants", response_model=list[McpTokenView])
async def get_mcp_oauth_grants(request: Request, token_info: dict = Depends(get_token_info)):
    _require_mcp_enabled()
    async with _session_factory()() as session:
        return await list_oauth_grants(
            session, owner_user_id=token_info["user_id"], owner_project_id=token_info["project_id"]
        )


@router.delete("/mcp-oauth/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_oauth_grant(
    grant_id: str,
    request: Request,
    token_info: dict = Depends(get_token_info),
    conn=Depends(get_os_conn),
):
    _require_browser_mutation(request)
    factory = _session_factory()
    try:
        credential_id, _ = await revoke_grant(
            factory,
            grant_id=grant_id,
            owner_user_id=token_info["user_id"],
            owner_project_id=token_info["project_id"],
            username=token_info.get("username", token_info["user_id"]),
        )
        await confirm_keystone_cleanup(
            factory,
            conn=conn,
            grant_id=grant_id,
            owner_user_id=token_info["user_id"],
            owner_project_id=token_info["project_id"],
            username=token_info.get("username", token_info["user_id"]),
            application_credential_id=credential_id,
        )
    except McpAuthorityError as exc:
        _raise_authority_error(exc)
    _mark_transactional_audit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
