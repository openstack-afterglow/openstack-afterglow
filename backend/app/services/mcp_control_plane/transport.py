"""Stateless Streamable-HTTP MCP transport with fail-closed request context."""

from __future__ import annotations

import base64
import binascii
import contextvars
import hashlib
import hmac
import json
import os
from contextlib import AbstractAsyncContextManager
from typing import Any, Literal
from urllib.parse import urlsplit

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Match
from starlette.types import Message, Receive, Scope, Send

from app.config import get_settings
from app.services.mcp_control_plane.authentication import McpAuthenticationError, McpPrincipal, verify_mcp_bearer
from app.services.mcp_control_plane.ledger import (
    McpInvocationError,
    authorize_mutation_dispatch,
    claim_mutation,
    complete_mutation,
    fail_pre_dispatch,
    record_read_invocation,
    validate_idempotency_key,
)
from app.services.mcp_control_plane.limits import (
    McpRateLimitExceeded,
    McpRateLimitUnavailable,
    grant_call_slot,
)
from app.services.mcp_control_plane.oauth import McpOAuthError, oauth_urls
from app.services.mcp_control_plane.registry import (
    REGISTRY_VERSION,
    ConsumerCloudContext,
    build_mutation_preview,
    dispatch,
    enabled_entries,
    enabled_service_fingerprint,
    entry_by_name,
    output_payload,
    parse_entry_arguments,
)

MCP_PATH = "/api/v1/mcp"
MCP_PROTOCOL_VERSION = "2025-11-25"

_current_principal: contextvars.ContextVar[McpPrincipal | None] = contextvars.ContextVar(
    "afterglow_mcp_principal", default=None
)

_server = Server("afterglow-consumer-mcp", version="1.0")
_manager: StreamableHTTPSessionManager | None = None
_manager_context: AbstractAsyncContextManager[None] | None = None


def current_principal() -> McpPrincipal:
    principal = _current_principal.get()
    if principal is None:
        raise RuntimeError("MCP request principal is unavailable")
    return principal


def _tool_cursor(principal: McpPrincipal, offset: int) -> str:
    payload = {
        "grant_id": principal.grant_id,
        "registry_version": REGISTRY_VERSION,
        "services": enabled_service_fingerprint(),
        "offset": offset,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(get_settings().secret_key.encode("utf-8"), encoded, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(encoded + signature).rstrip(b"=").decode("ascii")


def _tool_cursor_offset(principal: McpPrincipal, cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        packed = base64.urlsafe_b64decode(padded.encode("ascii"))
        encoded, signature = packed[:-32], packed[-32:]
        expected = hmac.new(get_settings().secret_key.encode("utf-8"), encoded, hashlib.sha256).digest()
        payload = json.loads(encoded)
        if (
            not hmac.compare_digest(signature, expected)
            or payload
            != {
                "grant_id": principal.grant_id,
                "registry_version": REGISTRY_VERSION,
                "services": enabled_service_fingerprint(),
                "offset": payload.get("offset"),
            }
            or type(payload["offset"]) is not int
            or payload["offset"] < 0
        ):
            raise ValueError
        return payload["offset"]
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError):
        raise ValueError("MCP tools cursor is invalid") from None


@_server.list_tools()
async def _list_tools(request: types.ListToolsRequest) -> types.ListToolsResult:
    principal = current_principal()
    entries = enabled_entries(principal)
    if request is None:
        # SDK 1.28 refreshes call_tool schemas with None, not a public list request.
        # Its wrapper requires the exact ListToolsRequest annotation above.
        page = entries
        next_cursor = None
    else:
        offset = _tool_cursor_offset(principal, request.params.cursor if request.params else None)
        page_size = get_settings().mcp_default_page_size
        page = entries[offset : offset + page_size]
        next_offset = offset + len(page)
        next_cursor = _tool_cursor(principal, next_offset) if next_offset < len(entries) else None
    tools = [
        types.Tool(
            name=entry.name,
            description=entry.description,
            inputSchema=entry.mcp_input_schema(),
            outputSchema=entry.output_schema(),
            annotations=types.ToolAnnotations(readOnlyHint=entry.effect == "read", destructiveHint=False),
        )
        for entry in page
    ]
    return types.ListToolsResult(
        tools=tools,
        nextCursor=next_cursor,
    )


@_server.call_tool(validate_input=True)
async def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    principal = current_principal()
    entry = entry_by_name(name)
    if entry is None or not entry.allowed_for(principal):
        raise ValueError("MCP tool is unavailable")
    domain_arguments = dict(arguments)
    idempotency_key = domain_arguments.pop("idempotency_key", None)
    try:
        parsed = parse_entry_arguments(entry, domain_arguments)
    except Exception:
        if entry.effect == "read":
            await record_read_invocation(principal, entry=entry, arguments=domain_arguments, status="failed")
        raise
    normalized = parsed.model_dump(mode="json")
    if entry.effect == "read":
        try:
            result = await dispatch(ConsumerCloudContext(principal=principal), entry=entry, arguments=parsed)
        except Exception as exc:
            await record_read_invocation(
                principal,
                entry=entry,
                arguments=normalized,
                status="failed",
                error=str(exc),
            )
            raise
        await record_read_invocation(principal, entry=entry, arguments=normalized, status="succeeded")
        return output_payload(entry, result)

    idempotency_key = validate_idempotency_key(idempotency_key)

    claim = await claim_mutation(
        principal,
        entry=entry,
        arguments=normalized,
        idempotency_key=idempotency_key,
    )
    if claim.state == "replay":
        assert claim.result is not None
        return claim.result
    if claim.state in {"in_progress", "unknown", "failed"}:
        raise McpInvocationError(claim.error or f"MCP mutation is {claim.state}")
    try:
        await build_mutation_preview(ConsumerCloudContext(principal=principal), entry=entry, arguments=parsed)
    except Exception:
        await fail_pre_dispatch(
            principal,
            invocation_id=claim.invocation_id,
            error="MCP pre-dispatch validation failed",
        )
        raise
    await authorize_mutation_dispatch(principal, invocation_id=claim.invocation_id)
    try:
        result = await dispatch(ConsumerCloudContext(principal=principal), entry=entry, arguments=parsed)
        serialized = output_payload(entry, result)
        await complete_mutation(principal, invocation_id=claim.invocation_id, result=serialized)
        return serialized
    except Exception as exc:
        try:
            await complete_mutation(
                principal,
                invocation_id=claim.invocation_id,
                error="MCP mutation outcome is unknown after dispatch authorization",
            )
        except McpInvocationError:
            pass
        raise exc


def _headers(scope: Scope) -> dict[str, str]:
    return {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope["headers"]}


def _request_effect(messages: list[Message]) -> Literal["read", "external_mutation"]:
    """Classify only the closed registry call surface before touching Redis."""
    try:
        raw = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.request")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("method") != "tools/call":
            return "read"
        params = payload.get("params")
        name = params.get("name") if isinstance(params, dict) else None
        entry = entry_by_name(name) if isinstance(name, str) else None
        return entry.effect if entry is not None else "read"
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return "read"


async def _send_response(response: Response, scope: Scope, receive: Receive, send: Send) -> None:
    await response(scope, receive, send)


async def _reject(
    scope: Scope, receive: Receive, send: Send, *, status_code: int, detail: str, headers: dict[str, str] | None = None
) -> None:
    await _send_response(
        JSONResponse({"error": detail}, status_code=status_code, headers=headers), scope, receive, send
    )


async def _buffer_limited_request(receive: Receive, *, maximum: int) -> tuple[list[Message], int]:
    messages: list[Message] = []
    total = 0
    while True:
        message = await receive()
        messages.append(message)
        if message["type"] == "http.request":
            total += len(message.get("body", b""))
            if total > maximum:
                return messages, total
            if not message.get("more_body", False):
                return messages, total
        elif message["type"] == "http.disconnect":
            return messages, total


def _replay_receive(messages: list[Message]) -> Receive:
    async def receive() -> Message:
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    return receive


def _urls():
    settings = get_settings()
    production = os.environ.get("AFTERGLOW_ENV", "development").strip().lower() == "production"
    return oauth_urls(
        settings.public_api_base,
        public_mcp_url=getattr(settings, "mcp_public_url", ""),
        production=production,
    )


def mcp_paths() -> frozenset[str]:
    try:
        configured_path = urlsplit(_urls().resource).path or "/"
    except McpOAuthError:
        # The feature is disabled by default, so an unset public API URL must not
        # prevent application import before the rollout gate is enabled.
        return frozenset((MCP_PATH,))
    return frozenset((MCP_PATH, configured_path))


def _canonical_origin() -> tuple[str, str]:
    parsed = urlsplit(_urls().resource)
    return f"{parsed.scheme}://{parsed.netloc}", parsed.netloc.lower()


async def mcp_asgi_app(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http" or scope["path"] not in mcp_paths():
        await _reject(scope, receive, send, status_code=404, detail="Not Found")
        return
    if not get_settings().service_mcp_enabled:
        await _reject(scope, receive, send, status_code=404, detail="Not Found")
        return
    headers = _headers(scope)
    if scope["method"] != "POST":
        await _reject(
            scope,
            receive,
            send,
            status_code=405,
            detail="Method Not Allowed",
            headers={"Allow": "POST"},
        )
        return
    try:
        origin, expected_host = _canonical_origin()
    except McpOAuthError:
        await _reject(scope, receive, send, status_code=503, detail="MCP public origin is unavailable")
        return
    if headers.get("host", "").lower() != expected_host:
        await _reject(scope, receive, send, status_code=400, detail="MCP host is invalid")
        return
    if headers.get("origin") not in {None, origin}:
        await _reject(scope, receive, send, status_code=403, detail="MCP origin is invalid")
        return
    content_length = headers.get("content-length")
    try:
        if content_length is not None and int(content_length) > get_settings().mcp_request_max_bytes:
            await _reject(scope, receive, send, status_code=413, detail="MCP request is too large")
            return
    except ValueError:
        await _reject(scope, receive, send, status_code=400, detail="MCP content length is invalid")
        return
    if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        await _reject(scope, receive, send, status_code=415, detail="MCP requests must use JSON")
        return
    accept = headers.get("accept", "")
    if "application/json" not in accept or "text/event-stream" not in accept:
        await _reject(scope, receive, send, status_code=406, detail="MCP Accept negotiation is invalid")
        return
    authorization = headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or not authorization.removeprefix("Bearer "):
        metadata = _urls().protected_resource_metadata
        await _reject(
            scope,
            receive,
            send,
            status_code=401,
            detail="MCP bearer token is required",
            headers={"WWW-Authenticate": f'Bearer resource_metadata="{metadata}"'},
        )
        return
    messages, body_size = await _buffer_limited_request(receive, maximum=get_settings().mcp_request_max_bytes)
    if body_size > get_settings().mcp_request_max_bytes:
        await _reject(scope, receive, send, status_code=413, detail="MCP request is too large")
        return
    try:
        principal = await verify_mcp_bearer(authorization.removeprefix("Bearer "), urls=_urls())
    except McpAuthenticationError:
        metadata = _urls().protected_resource_metadata
        await _reject(
            scope,
            receive,
            send,
            status_code=401,
            detail="MCP bearer token is invalid",
            headers={"WWW-Authenticate": f'Bearer resource_metadata="{metadata}"'},
        )
        return
    if _manager is None:
        await _reject(scope, receive, send, status_code=503, detail="MCP transport is unavailable")
        return
    token = _current_principal.set(principal)
    try:
        try:
            async with grant_call_slot(principal, effect=_request_effect(messages)):
                await _manager.handle_request(scope, _replay_receive(messages), send)
        except McpRateLimitUnavailable:
            await _reject(scope, receive, send, status_code=503, detail="MCP rate limiting is unavailable")
        except McpRateLimitExceeded:
            await _reject(scope, receive, send, status_code=429, detail="MCP request limit exceeded")
    finally:
        _current_principal.reset(token)


class ExactMcpRoute(BaseRoute):
    """An ASGI route that never redirects to or accepts a trailing slash."""

    def __init__(self, path: str):
        self.path = path

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        if scope["type"] == "http" and scope["path"] in {self.path, f"{self.path}/"}:
            return Match.FULL, {}
        return Match.NONE, {}

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        await mcp_asgi_app(scope, receive, send)


async def start_mcp_transport() -> None:
    global _manager, _manager_context
    if _manager_context is None:
        _manager = StreamableHTTPSessionManager(_server, json_response=True, stateless=True)
        _manager_context = _manager.run()
        await _manager_context.__aenter__()


async def stop_mcp_transport() -> None:
    global _manager, _manager_context
    if _manager_context is not None:
        await _manager_context.__aexit__(None, None, None)
        _manager_context = None
        _manager = None


def install_mcp_route(app: Any) -> None:
    existing_paths = {route.path for route in app.router.routes if isinstance(route, ExactMcpRoute)}
    for path in mcp_paths() - existing_paths:
        app.router.routes.insert(0, ExactMcpRoute(path))
