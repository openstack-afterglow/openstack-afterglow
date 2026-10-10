"""Inbound MCP OAuth discovery and public-client authorization routes.

The Streamable HTTP transport is mounted here later; OAuth endpoints deliberately
parse their own bodies so cross-origin requests are rejected before parsing.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.deps import get_os_conn, get_token_info
from app.api.identity.mcp_access import _mark_transactional_audit, _require_browser_mutation
from app.config import get_settings
from app.database import get_session_factory
from app.rate_limit import limiter
from app.services.mcp_control_plane.oauth import McpOAuthError, oauth_urls
from app.services.mcp_control_plane.oauth_authority import (
    McpOAuthAuthorityError,
    approve_consent_ticket,
    create_authorization_ticket,
    deny_consent_ticket,
    exchange_authorization_code,
    load_consent_ticket,
    refresh_tokens,
    register_public_client,
    revoke_oauth_token,
)

router = APIRouter()
root_router = APIRouter()
auth_router = APIRouter()

_OAUTH_NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
_MAX_PUBLIC_BODY = 64 * 1024


def _require_enabled() -> None:
    if not get_settings().service_mcp_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _urls():
    settings = get_settings()
    production = os.environ.get("AFTERGLOW_ENV", "development").strip().lower() == "production"
    return oauth_urls(
        settings.public_api_base,
        public_mcp_url=getattr(settings, "mcp_public_url", ""),
        production=production,
    )


def _oauth_consent_url() -> str:
    settings = get_settings()
    return (
        getattr(settings, "mcp_oauth_consent_url", "")
        or f"{settings.frontend_base_url.rstrip('/')}/oauth/mcp/authorize"
    )


def _matches_metadata_path(path: str, url: str) -> bool:
    return path == urlsplit(url).path.lstrip("/")


def _require_public_mcp_path(path: str) -> None:
    try:
        resource = _urls().resource
    except McpOAuthError:
        resource = None
    if resource is None or not _matches_metadata_path(path, resource):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _oauth_authorization_error(detail: str) -> JSONResponse:
    return JSONResponse(
        {"error": "invalid_client", "error_description": detail},
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={**_OAUTH_NO_STORE, "WWW-Authenticate": 'Basic realm="MCP OAuth"'},
    )


def _oauth_error(detail: str, *, error: str = "invalid_request", status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": error, "error_description": detail}, status_code=status_code, headers=_OAUTH_NO_STORE)


def _reject_public_origin(request: Request) -> None:
    if request.method == "OPTIONS" or request.headers.get("origin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Cross-origin OAuth requests are not supported"
        )


async def _public_json(request: Request) -> dict[str, Any]:
    _reject_public_origin(request)
    body = await request.body()
    if len(body) > _MAX_PUBLIC_BODY:
        raise McpOAuthAuthorityError("request body is too large")
    if "application/json" not in request.headers.get("content-type", ""):
        raise McpOAuthAuthorityError("request must use application/json")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise McpOAuthAuthorityError("request JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise McpOAuthAuthorityError("request JSON must be an object")
    return payload


async def _public_form(request: Request) -> dict[str, str]:
    _reject_public_origin(request)
    body = await request.body()
    if len(body) > _MAX_PUBLIC_BODY:
        raise McpOAuthAuthorityError("request body is too large")
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/x-www-form-urlencoded":
        raise McpOAuthAuthorityError("request must use application/x-www-form-urlencoded")
    try:
        from urllib.parse import parse_qsl

        pairs = parse_qsl(body.decode("utf-8", "strict"), keep_blank_values=True, strict_parsing=True)
    except (UnicodeDecodeError, ValueError) as exc:
        raise McpOAuthAuthorityError("request form is invalid") from exc
    values: dict[str, str] = {}
    for key, value in pairs:
        if key in values or len(key) > 128 or len(value) > 4096:
            raise McpOAuthAuthorityError("request form is invalid")
        values[key] = value
    return values


def _session_factory():
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="MCP authority storage is unavailable"
        )
    return factory


def _redirect_with_code(result) -> str:
    pairs = [("code", result.code)]
    if result.state is not None:
        pairs.append(("state", result.state))
    separator = "&" if "?" in result.redirect_uri else "?"
    return f"{result.redirect_uri}{separator}{urlencode(pairs)}"


@root_router.get("/.well-known/oauth-protected-resource/{resource_path:path}")
async def oauth_protected_resource_metadata(resource_path: str):
    _require_enabled()
    urls = _urls()
    if not _matches_metadata_path(resource_path, urls.resource):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return JSONResponse(
        {
            "resource": urls.resource,
            "authorization_servers": [urls.issuer],
            "scopes_supported": ["mcp:read", "mcp:write"],
        },
        headers=_OAUTH_NO_STORE,
    )


@root_router.get("/.well-known/oauth-protected-resource")
async def oauth_root_protected_resource_metadata():
    """RFC 9728 metadata location for a resource served at the origin root."""
    return await oauth_protected_resource_metadata("")


@root_router.get("/.well-known/oauth-authorization-server/{issuer_path:path}")
async def oauth_authorization_server_metadata(issuer_path: str):
    _require_enabled()
    urls = _urls()
    if not _matches_metadata_path(issuer_path, urls.issuer):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return JSONResponse(
        {
            "issuer": urls.issuer,
            "authorization_endpoint": f"{urls.issuer}/authorize",
            "token_endpoint": f"{urls.issuer}/token",
            "registration_endpoint": f"{urls.issuer}/register",
            "revocation_endpoint": f"{urls.issuer}/revoke",
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "response_types_supported": ["code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": ["mcp:read", "mcp:write"],
        },
        headers=_OAUTH_NO_STORE,
    )


@router.post("/oauth/register")
@limiter.limit("10/minute")
async def oauth_register(request: Request):
    _require_enabled()
    try:
        client = await register_public_client(_session_factory(), metadata=await _public_json(request))
    except HTTPException:
        raise
    except McpOAuthAuthorityError as exc:
        return _oauth_error(str(exc))
    return JSONResponse(
        {
            "client_id": client.client_id,
            "client_id_issued_at": int(client.client_id_issued_at.timestamp()),
            "client_id_expires_at": int(client.expires_at.timestamp()) if client.expires_at is not None else 0,
            "redirect_uris": client.redirect_uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "none",
        },
        status_code=status.HTTP_201_CREATED,
        headers=_OAUTH_NO_STORE,
    )


@root_router.post("/{mcp_path:path}/oauth/register")
async def oauth_register_alias(mcp_path: str, request: Request):
    _require_public_mcp_path(mcp_path)
    return await oauth_register(request)


@root_router.post("/oauth/register")
async def oauth_root_register_alias(request: Request):
    _require_public_mcp_path("")
    return await oauth_register(request)


@router.get("/oauth/authorize")
@limiter.limit("10/minute")
async def oauth_authorize(request: Request):
    _require_enabled()
    if request.headers.get("origin"):
        return _oauth_error("Cross-origin authorization requests are not supported", status_code=403)
    query = request.query_params
    try:
        ticket = await create_authorization_ticket(
            _session_factory(),
            client_id=query.get("client_id", ""),
            redirect_uri=query.get("redirect_uri", ""),
            response_type=query.get("response_type", ""),
            resource=query.get("resource"),
            urls=_urls(),
            scope=query.get("scope", ""),
            code_challenge=query.get("code_challenge"),
            code_challenge_method=query.get("code_challenge_method"),
            state=query.get("state"),
        )
    except (McpOAuthAuthorityError, McpOAuthError) as exc:
        return _oauth_error(str(exc))
    location = f"{_oauth_consent_url()}?{urlencode({'ticket': ticket.ticket})}"
    return RedirectResponse(location, status_code=status.HTTP_303_SEE_OTHER, headers=_OAUTH_NO_STORE)


@root_router.get("/{mcp_path:path}/oauth/authorize")
async def oauth_authorize_alias(mcp_path: str, request: Request):
    _require_public_mcp_path(mcp_path)
    return await oauth_authorize(request)


@root_router.get("/oauth/authorize")
async def oauth_root_authorize_alias(request: Request):
    _require_public_mcp_path("")
    return await oauth_authorize(request)


@router.post("/oauth/token")
@limiter.limit("30/minute")
async def oauth_token(request: Request):
    _require_enabled()
    try:
        form = await _public_form(request)
        if request.headers.get("authorization"):
            return _oauth_authorization_error("public clients must not use HTTP Authorization")
        if "client_secret" in form:
            return _oauth_error("public clients must not send client_secret", error="invalid_client")
        grant_type = form.get("grant_type")
        if grant_type == "authorization_code":
            result = await exchange_authorization_code(
                _session_factory(),
                code=form.get("code", ""),
                client_id=form.get("client_id", ""),
                redirect_uri=form.get("redirect_uri", ""),
                resource=form.get("resource"),
                urls=_urls(),
                code_verifier=form.get("code_verifier", ""),
            )
        elif grant_type == "refresh_token":
            result = await refresh_tokens(
                _session_factory(),
                refresh_token=form.get("refresh_token", ""),
                client_id=form.get("client_id"),
                resource=form.get("resource"),
                urls=_urls(),
                scope=form.get("scope"),
            )
        else:
            return _oauth_error("grant_type is unsupported", error="unsupported_grant_type")
    except HTTPException:
        raise
    except (McpOAuthAuthorityError, McpOAuthError) as exc:
        return _oauth_error(str(exc), error="invalid_grant")
    return JSONResponse(
        {
            "access_token": result.access_token,
            "refresh_token": result.refresh_token,
            "token_type": "Bearer",
            "expires_in": result.expires_in,
            "scope": result.scope,
        },
        headers=_OAUTH_NO_STORE,
    )


@root_router.post("/{mcp_path:path}/oauth/token")
async def oauth_token_alias(mcp_path: str, request: Request):
    _require_public_mcp_path(mcp_path)
    return await oauth_token(request)


@root_router.post("/oauth/token")
async def oauth_root_token_alias(request: Request):
    _require_public_mcp_path("")
    return await oauth_token(request)


@router.post("/oauth/revoke", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def oauth_revoke(request: Request):
    _require_enabled()
    try:
        form = await _public_form(request)
        if request.headers.get("authorization"):
            return _oauth_authorization_error("public clients must not use HTTP Authorization")
        if "client_secret" in form:
            return _oauth_error("public clients must not send client_secret", error="invalid_client")
        await revoke_oauth_token(_session_factory(), token=form.get("token", ""))
    except HTTPException:
        raise
    except McpOAuthAuthorityError as exc:
        return _oauth_error(str(exc))
    return Response(status_code=status.HTTP_200_OK, headers=_OAUTH_NO_STORE)


@root_router.post("/{mcp_path:path}/oauth/revoke", status_code=status.HTTP_200_OK)
async def oauth_revoke_alias(mcp_path: str, request: Request):
    _require_public_mcp_path(mcp_path)
    return await oauth_revoke(request)


@root_router.post("/oauth/revoke", status_code=status.HTTP_200_OK)
async def oauth_root_revoke_alias(request: Request):
    _require_public_mcp_path("")
    return await oauth_revoke(request)


@auth_router.get("/mcp-oauth/consents/{ticket}")
async def get_oauth_consent(ticket: str, token_info: dict = Depends(get_token_info)):
    _require_enabled()
    try:
        consent = await load_consent_ticket(
            _session_factory(),
            ticket=ticket,
            owner_user_id=token_info["user_id"],
            owner_project_id=token_info["project_id"],
        )
    except McpOAuthAuthorityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return JSONResponse(
        {
            "client_id": consent.client_id,
            "client_name": consent.client_name,
            "redirect_uri": consent.redirect_uri,
            "scopes": consent.scopes,
            "grant_deadline": consent.grant_deadline.isoformat(),
        },
        headers=_OAUTH_NO_STORE,
    )


@auth_router.post("/mcp-oauth/consents/{ticket}/approve")
async def approve_oauth_consent(
    ticket: str,
    request: Request,
    token_info: dict = Depends(get_token_info),
    conn=Depends(get_os_conn),
):
    _require_browser_mutation(request)
    try:
        result = await approve_consent_ticket(
            _session_factory(),
            ticket=ticket,
            owner_user_id=token_info["user_id"],
            owner_project_id=token_info["project_id"],
            username=token_info.get("username", token_info["user_id"]),
            roles=token_info.get("roles", []),
            conn=conn,
        )
    except McpOAuthAuthorityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _mark_transactional_audit()
    return JSONResponse({"redirect_uri": _redirect_with_code(result)}, headers=_OAUTH_NO_STORE)


@auth_router.post("/mcp-oauth/consents/{ticket}/deny")
async def deny_oauth_consent(ticket: str, request: Request, token_info: dict = Depends(get_token_info)):
    _require_browser_mutation(request)
    try:
        result = await deny_consent_ticket(
            _session_factory(),
            ticket=ticket,
            owner_user_id=token_info["user_id"],
            owner_project_id=token_info["project_id"],
        )
    except McpOAuthAuthorityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _mark_transactional_audit()
    return JSONResponse(
        {
            "redirect_uri": f"{result.redirect_uri}{'&' if '?' in result.redirect_uri else '?'}{urlencode({'error': 'access_denied', **({'state': result.state} if result.state else {})})}"
        },
        headers=_OAUTH_NO_STORE,
    )


@router.options("/oauth/{path:path}")
async def oauth_options(path: str):
    _require_enabled()
    return Response(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, headers=_OAUTH_NO_STORE)
