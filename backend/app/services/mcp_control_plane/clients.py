"""Bounded self-reported MCP initialization evidence, never authorization identity."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.database import get_session_factory

if TYPE_CHECKING:
    from app.services.mcp_control_plane.authentication import McpPrincipal

MAX_CLIENT_OBSERVATIONS = 10
_PRODUCTS = {
    "Claude Code": "agent",
    "Claude": "agent",
    "Codex": "agent",
    "Cursor": "agent",
    "VS Code": "agent",
    "Chrome": "browser",
    "Firefox": "browser",
    "Safari": "browser",
    "Edge": "browser",
    "Googlebot": "bot",
    "Bingbot": "bot",
    "MCP Python SDK": "sdk",
    "MCP TypeScript SDK": "sdk",
}
_BROWSERS = {"Chrome", "Firefox", "Safari", "Edge", "Chromium"}
_OSES = {"Windows", "macOS", "Linux", "Android", "iOS"}
_KINDS = {"agent", "browser", "bot", "sdk", "unknown"}
_SOURCES = {"client_info", "user_agent", "unknown"}
_SECRET = re.compile(
    r"bearer|authorization|password|secret|token[=: ]|api[ _-]?key|mcp-afgl-|sk-afgl-|sk-[a-z0-9]|"
    r"eyJ[a-zA-Z0-9_-]+\.|https?://|[a-z0-9_-]{40,}",
    re.IGNORECASE,
)


class McpClientObservationUnavailable(RuntimeError):
    """Required initialization evidence could not be committed."""


def _safe_text(value, *, version: bool = False) -> str | None:
    maximum = 32 if version else 100
    if not isinstance(value, str) or not value or len(value) > maximum:
        return None
    # Reject rather than truncate: controls, credentials and payload fragments must
    # not become display names or a fingerprint input that retains hidden secrets.
    pattern = r"[A-Za-z0-9][A-Za-z0-9.+_-]*" if version else r"[A-Za-z0-9][A-Za-z0-9 ._()+-]*"
    if not re.fullmatch(pattern, value) or _SECRET.search(value):
        return None
    return value.strip() or None


def _recognize(value: str) -> tuple[str | None, str]:
    if re.search(r"(?<![a-z0-9])(?:[a-z_-]*bot|crawler|spider)(?![a-z0-9])", value, re.IGNORECASE):
        for product in ("Googlebot", "Bingbot"):
            if re.search(r"(?<![a-z0-9])" + product + r"(?![a-z0-9])", value, re.IGNORECASE):
                return product, "bot"
        return None, "bot"
    aliases = (
        (r"claude[ _-]?code", "Claude Code"),
        (r"claude", "Claude"),
        (r"codex(?:[ _-]cli)?", "Codex"),
        (r"cursor", "Cursor"),
        (r"(?:vscode|vs[ _-]code|visual studio code)", "VS Code"),
        (r"(?:mcp[ _-]python[ _-]sdk|python[ _-]mcp)", "MCP Python SDK"),
        (r"(?:mcp[ _-]typescript[ _-]sdk|typescript[ _-]mcp)", "MCP TypeScript SDK"),
        (r"(?:edg|edge)", "Edge"),
        (r"firefox", "Firefox"),
        (r"chrome", "Chrome"),
        (r"safari", "Safari"),
    )
    for pattern, product in aliases:
        if re.search(r"(?<![a-z0-9])" + pattern + r"(?![a-z0-9])", value, re.IGNORECASE):
            return product, _PRODUCTS[product]
    return None, "unknown"


def client_observation(client_info: dict, user_agent: str | None) -> dict:
    """Extract only safe names and fixed inference labels; discard raw UA/payload."""
    name = _safe_text(client_info.get("name"))
    version = _safe_text(client_info.get("version"), version=True)
    ua = user_agent if isinstance(user_agent, str) and len(user_agent) <= 2048 else ""
    if any(ord(char) < 32 or ord(char) == 127 for char in ua):
        ua = ""
    browser = None
    for marker, label in (
        ("Edg/", "Edge"),
        ("Firefox/", "Firefox"),
        ("Chrome/", "Chrome"),
        ("Chromium/", "Chromium"),
        ("Safari/", "Safari"),
    ):
        if marker.casefold() in ua.casefold():
            browser = label
            break
    os_name = None
    for marker, label in (
        ("Android", "Android"),
        ("iPhone", "iOS"),
        ("iPad", "iOS"),
        ("Windows", "Windows"),
        ("Macintosh", "macOS"),
        ("Mac OS", "macOS"),
        ("Linux", "Linux"),
    ):
        if marker.casefold() in ua.casefold():
            os_name = label
            break
    name_product, name_kind = _recognize(name or "")
    ua_product, ua_kind = _recognize(ua)
    if client_info.get("name") and name is None:
        # Poisoned self-reports are not repaired into a plausible browser identity.
        product, kind, source = None, "unknown", "unknown"
    elif name_kind == "bot":
        product, kind, source = name_product, name_kind, "client_info"
    elif ua_kind == "bot":
        product, kind, source = ua_product, ua_kind, "user_agent"
    elif name_kind != "unknown":
        product, kind, source = name_product, name_kind, "client_info"
    elif ua_kind != "unknown":
        product, kind, source = ua_product, ua_kind, "user_agent"
    elif browser:
        product, kind, source = (browser if browser in _PRODUCTS else None), "browser", "user_agent"
    else:
        product, kind, source = None, "unknown", "client_info" if name else "unknown"
    return {
        "client_name": name,
        "client_version": version,
        "product": product,
        "kind": kind,
        "identity_source": source,
        "browser": browser,
        "os": os_name,
    }


def _timestamp(value) -> str | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC).isoformat()


def public_client_observations(value) -> list[dict]:
    """Project persisted evidence through an exact privacy allowlist (legacy NULL → [])."""
    if not isinstance(value, list):
        return []
    result = []
    for item in value[-MAX_CLIENT_OBSERVATIONS:]:
        if not isinstance(item, dict):
            continue
        first, last = _timestamp(item.get("first_seen_at")), _timestamp(item.get("last_seen_at"))
        if first is None or last is None or first > last:
            continue
        product = item.get("product")
        kind = item.get("kind")
        source = item.get("identity_source")
        result.append(
            {
                "client_name": _safe_text(item.get("client_name")),
                "client_version": _safe_text(item.get("client_version"), version=True),
                "product": product if isinstance(product, str) and product in _PRODUCTS else None,
                "kind": kind if isinstance(kind, str) and kind in _KINDS else "unknown",
                "identity_source": source if isinstance(source, str) and source in _SOURCES else "unknown",
                "browser": item.get("browser")
                if isinstance(item.get("browser"), str) and item["browser"] in _BROWSERS
                else None,
                "os": item.get("os") if isinstance(item.get("os"), str) and item["os"] in _OSES else None,
                "first_seen_at": first,
                "last_seen_at": last,
            }
        )
    return result


def _signature(item: dict) -> str:
    evidence = {key: value for key, value in item.items() if key not in {"first_seen_at", "last_seen_at"}}
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def merge_client_observation(value, observation: dict, *, now: datetime) -> list[dict]:
    """Recent distinct sanitized signatures, with original first-seen retained."""
    records = public_client_observations(value)
    stamp = now.astimezone(UTC).isoformat()
    candidate = public_client_observations([{**observation, "first_seen_at": stamp, "last_seen_at": stamp}])[0]
    signature = _signature(candidate)
    first = stamp
    retained = []
    for record in records:
        if _signature(record) == signature:
            first = min(first, record["first_seen_at"])
        else:
            retained.append(record)
    return (retained + [{**candidate, "first_seen_at": first}])[-MAX_CLIENT_OBSERVATIONS:]


async def record_client_observation(principal: McpPrincipal, observation: dict) -> None:
    """Commit only under the existing owner/grant/token fence, including epoch."""
    # Lazy imports keep the authority public projection independent of auth loading.
    from app.services.mcp_control_plane.authentication import McpAuthenticationError, lock_principal_grant
    from app.services.mcp_control_plane.authority import McpAuthorityError, McpGrantNotFoundError

    try:
        factory = get_session_factory()
        if factory is None:
            raise McpClientObservationUnavailable("MCP client observation storage is unavailable")
        async with factory() as session, session.begin():
            grant = await lock_principal_grant(session, principal)
            grant.client_observations = merge_client_observation(
                grant.client_observations, observation, now=datetime.now(UTC)
            )
    except McpAuthenticationError:
        raise
    except (McpAuthorityError, McpGrantNotFoundError) as exc:
        raise McpAuthenticationError("MCP grant changed before initialization completed") from exc
    except Exception as exc:
        raise McpClientObservationUnavailable("MCP client observation storage is unavailable") from exc
