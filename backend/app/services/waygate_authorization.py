"""Browser-facing Waygate action gates mirroring the native route dependencies.

Waygate remains authoritative for project/server ownership, assigned-client
private profiles and owner validation. This gate only refuses actions the
caller's current exact service leaves cannot perform before any transport.
Agent registration/status routes are machine-authenticated passthroughs and are
never browser actions here.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping

from fastapi import HTTPException, Request

from app.services.service_permissions import require_any_service_permission, require_service_permission

INVENTORY = "waygate-inventory_reader"
CONNECT = "waygate-connect_user"
CLIENTS_EDITOR = "waygate-clients_editor"
GATEWAYS_EDITOR = "waygate-gateways_editor"
CLIENTS_ADMIN = "waygate-clients_admin"
GATEWAYS_ADMIN = "waygate-gateways_admin"
ROUTING_ADMIN = "waygate-routing_admin"

_SEGMENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*")
_ANY = None
_SYSTEM = "system"

Check = Callable[[Request, Mapping], Awaitable[None]]


def _unknown() -> HTTPException:
    return HTTPException(status_code=403, detail="알 수 없는 Waygate 작업입니다")


def _segments(upstream_path: str) -> tuple[str, ...]:
    """Reject encoded separators, dot segments and empty segments instead of normalizing them."""
    if not upstream_path.startswith("/v1/"):
        raise _unknown()
    rest = upstream_path[len("/v1/") :]
    rest = rest[:-1] if rest.endswith("/") else rest
    if not rest:
        return ()
    parts = tuple(rest.split("/"))
    if not all(_SEGMENT.fullmatch(part) for part in parts):
        raise _unknown()
    return parts


def _all(*leaves: str) -> Check:
    async def check(_request: Request, principal: Mapping) -> None:
        require_service_permission(principal, *leaves)

    return check


async def _update_client(request: Request, principal: Mapping) -> None:
    """Native PATCH: any edited field needs clients editor; any enabled transition needs clients admin."""
    require_any_service_permission(principal, CLIENTS_EDITOR, CLIENTS_ADMIN)
    try:
        body = await request.json()
    except (ValueError, RecursionError):
        # The native schema rejects a malformed body; no action is performed.
        return
    if not isinstance(body, dict):
        return
    if set(body) - {"enabled"}:
        require_service_permission(principal, CLIENTS_EDITOR)
    if "enabled" in body:
        require_service_permission(principal, CLIENTS_ADMIN)


_ROUTES: tuple[tuple[str, tuple[str | None, ...], Check | str], ...] = (
    # Version/health metadata discovery.
    ("GET", (), _all(INVENTORY)),
    ("GET", ("health",), _all(INVENTORY)),
    # servers.py
    ("GET", ("servers",), _all(INVENTORY)),
    ("POST", ("servers",), _all(GATEWAYS_EDITOR)),
    ("GET", ("servers", _ANY), _all(INVENTORY)),
    ("PATCH", ("servers", _ANY), _all(GATEWAYS_EDITOR)),
    ("DELETE", ("servers", _ANY), _all(GATEWAYS_ADMIN)),
    ("POST", ("servers", _ANY, "agent-token", "rotate"), _all(GATEWAYS_ADMIN)),
    # clients.py
    ("GET", ("servers", _ANY, "clients"), _all(INVENTORY)),
    ("POST", ("servers", _ANY, "clients"), _all(CLIENTS_EDITOR)),
    ("PATCH", ("servers", _ANY, "clients", _ANY), _update_client),
    ("DELETE", ("servers", _ANY, "clients", _ANY), _all(CLIENTS_ADMIN)),
    ("GET", ("servers", _ANY, "clients", _ANY, "config"), _all(CONNECT)),
    # attachments.py
    ("GET", ("servers", _ANY, "networks"), _all(INVENTORY)),
    ("POST", ("servers", _ANY, "networks"), _all(ROUTING_ADMIN)),
    ("DELETE", ("servers", _ANY, "networks", _ANY), _all(ROUTING_ADMIN)),
    # migration.py: wrapped credential bundles need both client and routing administration.
    ("POST", ("servers", _ANY, "export"), _all(CLIENTS_ADMIN, ROUTING_ADMIN)),
    ("POST", ("servers", _ANY, "import"), _all(CLIENTS_ADMIN, ROUTING_ADMIN)),
    # resource_policies.py: platform policy, never a project service grade.
    ("GET", ("admin", "resource-policies"), _SYSTEM),
    ("GET", ("admin", "resource-policies", "catalog", _ANY), _SYSTEM),
    ("PUT", ("admin", "resource-policies", _ANY), _SYSTEM),
)


def _match(method: str, parts: tuple[str, ...]) -> Check | str | None:
    for route_method, pattern, check in _ROUTES:
        if (
            route_method == method
            and len(pattern) == len(parts)
            and all(expected is _ANY or expected == part for expected, part in zip(pattern, parts, strict=True))
        ):
            return check
    return None


async def authorize_waygate_request(request: Request, upstream_path: str, principal: Mapping) -> None:
    if request.method == "OPTIONS":
        return
    method = "GET" if request.method == "HEAD" else request.method
    check = _match(method, _segments(upstream_path))
    if check is None:
        raise _unknown()
    system_admin = principal.get("is_system_admin") is True
    if check == _SYSTEM:
        if not system_admin:
            raise HTTPException(status_code=403, detail="시스템 관리자 권한이 필요합니다")
        return
    if system_admin:
        return
    await check(request, principal)
