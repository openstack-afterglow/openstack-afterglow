"""Owner-bound, read-only connectivity check of the configured public MCP resource.

The check authenticates a personal key locally first, then performs the same
Streamable HTTP handshake an MCP client performs: ``initialize``, the
``notifications/initialized`` notification and every ``tools/list`` page. It never
calls a tool. The key is sent only to the operator-configured resource URL:
redirects are never followed, environment proxies/CA overrides are ignored, and
responses, pagination and the total duration are bounded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

import anyio
import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client

from app.services.mcp_control_plane.authentication import McpAuthenticationError, verify_mcp_bearer
from app.services.mcp_control_plane.authority import PERSONAL_TOKEN_PREFIX
from app.services.mcp_control_plane.oauth import McpOAuthError
from app.services.mcp_control_plane.ssrf import _BoundedResponseStream
from app.services.mcp_control_plane.transport import _urls as configured_mcp_urls

CheckFailure = Literal["invalid_token", "not_configured", "rejected", "redirect", "unavailable", "protocol"]

MAX_TOKEN_CHARS = 128
_DEADLINE_SECONDS = 20.0
_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_TOOL_PAGES = 50
_MAX_TOOLS = 5000
_CLIENT_INFO = types.Implementation(name="afterglow-connection-check", version="1.0")


class McpConnectionCheckError(RuntimeError):
    """A connection check failed; ``reason`` is safe to show, the cause is not."""

    def __init__(self, reason: CheckFailure) -> None:
        super().__init__(reason)
        self.reason: CheckFailure = reason


@dataclass(frozen=True)
class McpConnectionCheck:
    endpoint: str
    protocol_version: str
    server_name: str
    server_version: str
    tool_count: int


class _BoundedTransport(httpx.AsyncBaseTransport):
    """Refuse compressed bodies and cap every response before the SDK parses it."""

    def __init__(self, inner: httpx.AsyncBaseTransport, maximum_bytes: int) -> None:
        self._inner = inner
        self._maximum_bytes = maximum_bytes

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request.headers["accept-encoding"] = "identity"
        response = await self._inner.handle_async_request(request)
        if response.headers.get("content-encoding", "identity").strip().lower() not in {"", "identity"}:
            await response.aclose()
            raise httpx.DecodingError("compressed MCP responses are not accepted", request=request)
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            stream=_BoundedResponseStream(response.stream, self._maximum_bytes),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


def _network_transport() -> httpx.AsyncBaseTransport:
    # Strict certificate/hostname verification against the bundled CA store; no
    # proxy or SSL_CERT_* environment influence and no transport-level retries.
    return httpx.AsyncHTTPTransport(verify=True, trust_env=False, retries=0)


def _failure_from_statuses(statuses: list[int]) -> CheckFailure:
    if any(300 <= status < 400 for status in statuses):
        return "redirect"
    if any(status in {401, 403} for status in statuses):
        return "rejected"
    if any(status >= 400 for status in statuses) or not statuses:
        return "unavailable"
    return "protocol"


async def probe_mcp_endpoint(endpoint: str, token: str) -> McpConnectionCheck:
    """Initialize and enumerate tools at ``endpoint`` with ``token``; never call a tool."""
    statuses: list[int] = []
    failure: CheckFailure | None = None
    initialized: types.InitializeResult | None = None
    tool_count = 0

    async def record_status(response: httpx.Response) -> None:
        statuses.append(response.status_code)

    client = httpx.AsyncClient(
        transport=_BoundedTransport(_network_transport(), _MAX_RESPONSE_BYTES),
        headers={"Authorization": f"Bearer {token}"},
        timeout=_HTTP_TIMEOUT,
        follow_redirects=False,
        trust_env=False,
        event_hooks={"response": [record_status]},
    )
    try:
        with anyio.fail_after(_DEADLINE_SECONDS):
            async with (
                client,
                streamable_http_client(endpoint, http_client=client, terminate_on_close=False) as (read, write, _),
                ClientSession(
                    read,
                    write,
                    read_timeout_seconds=timedelta(seconds=_DEADLINE_SECONDS),
                    client_info=_CLIENT_INFO,
                ) as session,
            ):
                initialized = await session.initialize()
                cursor: str | None = None
                seen_cursors: set[str] = set()
                for _ in range(_MAX_TOOL_PAGES):
                    params = types.PaginatedRequestParams(cursor=cursor) if cursor is not None else None
                    page = await session.list_tools(params=params)
                    tool_count += len(page.tools)
                    cursor = page.nextCursor
                    if tool_count > _MAX_TOOLS:
                        failure = "protocol"
                        break
                    if cursor is None:
                        break
                    if cursor in seen_cursors:
                        failure = "protocol"
                        break
                    seen_cursors.add(cursor)
                else:
                    failure = "protocol"
    except TimeoutError:
        classified = _failure_from_statuses(statuses)
        failure = failure or (classified if classified in {"redirect", "rejected"} else "unavailable")
    except Exception:  # noqa: BLE001 - upstream detail must never reach the browser.
        failure = _failure_from_statuses(statuses)
    if failure is None and initialized is not None:
        return McpConnectionCheck(
            endpoint=endpoint,
            protocol_version=str(initialized.protocolVersion),
            server_name=initialized.serverInfo.name,
            server_version=initialized.serverInfo.version,
            tool_count=tool_count,
        )
    raise McpConnectionCheckError(failure or _failure_from_statuses(statuses))


async def verify_personal_mcp_connection(
    raw_token: str, *, owner_user_id: str, owner_project_id: str
) -> McpConnectionCheck:
    """Check a personal key owned by exactly this user/project against the public resource."""
    if (
        not isinstance(raw_token, str)
        or len(raw_token) > MAX_TOKEN_CHARS
        or not raw_token.startswith(PERSONAL_TOKEN_PREFIX)
    ):
        raise McpConnectionCheckError("invalid_token")
    try:
        urls = configured_mcp_urls()
    except McpOAuthError:
        raise McpConnectionCheckError("not_configured") from None
    try:
        principal = await verify_mcp_bearer(raw_token, urls=urls)
    except McpAuthenticationError:
        raise McpConnectionCheckError("invalid_token") from None
    # Ownership is proven before any network request carries the key.
    if (
        principal.source != "personal_token"
        or principal.user_id != owner_user_id
        or principal.project_id != owner_project_id
    ):
        raise McpConnectionCheckError("invalid_token")
    return await probe_mcp_endpoint(urls.resource, raw_token)
