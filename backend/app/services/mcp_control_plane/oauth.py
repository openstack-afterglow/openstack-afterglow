"""OAuth 2.1 policy primitives for the inbound MCP resource server."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.services.mcp_control_plane.ssrf import SafeAsyncTransport

OAUTH_VALUE_BYTES = 32
ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
AUTHORIZATION_TICKET_LIFETIME = timedelta(minutes=10)
MAX_CIMD_BYTES = 64 * 1024
ALLOWED_SCOPE_SETS = {frozenset({"mcp:read"}), frozenset({"mcp:read", "mcp:write"})}


class McpOAuthError(ValueError):
    pass


@dataclass(frozen=True)
class McpOAuthUrls:
    public_api_base: str
    resource: str
    issuer: str
    protected_resource_metadata: str
    authorization_server_metadata: str


def canonical_public_api_base(value: str, *, production: bool) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise McpOAuthError("public_api_base must be an absolute URL") from exc
    if not parsed.scheme or not parsed.netloc or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise McpOAuthError("public_api_base must be an absolute origin without credentials, query, or fragment")
    if production and parsed.scheme != "https":
        raise McpOAuthError("MCP requires an HTTPS public_api_base in production")
    if parsed.scheme not in {"https", "http"}:
        raise McpOAuthError("public_api_base must use HTTP or HTTPS")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def canonical_mcp_resource_url(value: str, *, production: bool) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise McpOAuthError("MCP public URL must be an absolute URL") from exc
    if not parsed.scheme or not parsed.netloc or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise McpOAuthError("MCP public URL must be an absolute URL without credentials, query, or fragment")
    if production and parsed.scheme != "https":
        raise McpOAuthError("MCP requires an HTTPS public URL in production")
    if parsed.scheme not in {"https", "http"}:
        raise McpOAuthError("MCP public URL must use HTTP or HTTPS")
    # An explicit URL is the exact resource; a bare origin is served at the origin root.
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def oauth_urls(public_api_base: str, *, public_mcp_url: str = "", production: bool) -> McpOAuthUrls:
    if public_mcp_url:
        resource = canonical_mcp_resource_url(public_mcp_url, production=production)
        resource_parts = urlsplit(resource)
        base = urlunsplit((resource_parts.scheme, resource_parts.netloc, "", "", ""))
    else:
        base = canonical_public_api_base(public_api_base, production=production)
        resource = f"{base}/api/v1/mcp"
        resource_parts = urlsplit(resource)
    resource_origin = urlunsplit((resource_parts.scheme, resource_parts.netloc, "", "", ""))
    issuer = f"{resource}/oauth"
    return McpOAuthUrls(
        public_api_base=base,
        resource=resource,
        issuer=issuer,
        protected_resource_metadata=f"{resource_origin}/.well-known/oauth-protected-resource{resource_parts.path}",
        authorization_server_metadata=f"{resource_origin}/.well-known/oauth-authorization-server{resource_parts.path}/oauth",
    )


def require_exact_resource(value: str | None, urls: McpOAuthUrls) -> str:
    # RFC 3986 makes an empty HTTP(S) path equivalent to "/"; WHATWG URL clients
    # serialize an origin-root resource with the trailing slash.
    if value != urls.resource and not (urlsplit(urls.resource).path == "" and value == f"{urls.resource}/"):
        raise McpOAuthError("resource must exactly match this MCP server")
    return urls.resource


def validate_scopes(raw_scope: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    items = raw_scope.split() if isinstance(raw_scope, str) else list(raw_scope)
    scopes = frozenset(items)
    if scopes not in ALLOWED_SCOPE_SETS:
        raise McpOAuthError("scope must be mcp:read or mcp:read mcp:write")
    return tuple(sorted(scopes))


def _is_loopback_http(parsed) -> bool:
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1"}


def validate_redirect_uri(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise McpOAuthError("redirect URI is invalid") from exc
    if parsed.fragment or parsed.username or parsed.password:
        raise McpOAuthError("redirect URI must not include credentials or a fragment")
    if parsed.scheme == "https" and parsed.netloc and "*" not in parsed.hostname:
        return value
    if _is_loopback_http(parsed):
        return value
    raise McpOAuthError("redirect URI must use HTTPS or an IP-literal loopback HTTP address")


def redirect_uri_matches(registered: str, requested: str) -> bool:
    """RFC 8252 permits only the loopback TCP port to vary after registration."""
    try:
        registered_parsed = urlsplit(validate_redirect_uri(registered))
        requested_parsed = urlsplit(validate_redirect_uri(requested))
    except McpOAuthError:
        return False
    if _is_loopback_http(registered_parsed) and _is_loopback_http(requested_parsed):
        return (
            registered_parsed.hostname == requested_parsed.hostname
            and registered_parsed.path == requested_parsed.path
            and registered_parsed.query == requested_parsed.query
        )
    return registered == requested


def validate_redirect_uris(values: object) -> tuple[str, ...]:
    if not isinstance(values, list) or not 1 <= len(values) <= 10 or any(not isinstance(item, str) for item in values):
        raise McpOAuthError("redirect_uris must contain 1 to 10 URLs")
    normalized = tuple(validate_redirect_uri(item) for item in values)
    if len(set(normalized)) != len(normalized):
        raise McpOAuthError("redirect_uris must be unique")
    return normalized


def validate_pkce_s256(challenge: str | None, method: str | None) -> str:
    if method != "S256" or not isinstance(challenge, str) or not 43 <= len(challenge) <= 128:
        raise McpOAuthError("PKCE S256 is required")
    if not all(char.isalnum() or char in "-_" for char in challenge):
        raise McpOAuthError("PKCE challenge is invalid")
    return challenge


def pkce_s256(verifier: str) -> str:
    if not 43 <= len(verifier) <= 128 or not all(char.isalnum() or char in "-._~" for char in verifier):
        raise McpOAuthError("PKCE verifier is invalid")
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def new_oauth_value() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(OAUTH_VALUE_BYTES)).rstrip(b"=").decode("ascii")


def hash_oauth_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def fetch_cimd(client_id: str) -> dict:
    """Fetch exact HTTPS client metadata through the existing DNS-pinned boundary."""
    parsed = urlsplit(client_id)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise McpOAuthError("client_id metadata document must be an exact HTTPS URL")
    transport = SafeAsyncTransport(max_response_bytes=MAX_CIMD_BYTES)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(10.0),
            headers={"Accept": "application/json"},
        ) as client:
            response = await client.get(client_id)
            if response.status_code != 200 or "application/json" not in response.headers.get("content-type", ""):
                raise McpOAuthError("client metadata document is unavailable")
            payload = response.json()
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        raise McpOAuthError("client metadata document is unavailable") from exc
    if not isinstance(payload, dict) or payload.get("client_id") != client_id:
        raise McpOAuthError("client metadata document does not match client_id")
    if payload.get("token_endpoint_auth_method") != "none":
        raise McpOAuthError("MCP OAuth clients must be public")
    payload["redirect_uris"] = list(validate_redirect_uris(payload.get("redirect_uris")))
    if set(payload.get("grant_types", [])) != {"authorization_code", "refresh_token"}:
        raise McpOAuthError("client metadata must request only authorization_code and refresh_token")
    return payload
