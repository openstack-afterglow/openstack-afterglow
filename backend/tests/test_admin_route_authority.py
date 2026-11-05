"""Inventory every mounted administrator endpoint and its native executor boundary."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute

from app.api.deps import get_admin_os_conn, get_os_conn, require_admin
from app.api.palimpsest.catalog import admin_identity
from app.main import app


def dependency_calls(dependant):
    yield dependant.call
    for dependency in dependant.dependencies:
        yield from dependency_calls(dependency)


def admin_routes():
    return [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and (route.path.startswith("/api/v1/admin") or "/admin/" in route.path)
    ]


# These browser-JWT-only Hub proxy endpoints reject package/native tokens and
# resolve the ORIGINAL human token before calling require_admin explicitly inside
# admin_identity. A separate get_token_info dependency would lose that transport
# contract. The focused test below proves delegation to the fresh guard; there
# is no cached-admin exception.
EXPLICIT_HUMAN_GUARDS = {
    ("GET", "/api/v1/admin/palimpsest/catalog"),
    ("GET", "/api/v1/admin/palimpsest/catalog/{identity}"),
}


def test_every_admin_route_requires_fresh_system_administrator():
    routes = admin_routes()
    assert routes, "The application administrator routers must be mounted"
    exceptions = set()
    missing = []
    for route in routes:
        calls = set(dependency_calls(route.dependant))
        for method in route.methods:
            key = (method, route.path)
            if key in EXPLICIT_HUMAN_GUARDS:
                assert admin_identity in calls
                exceptions.add(key)
            elif require_admin not in calls:
                missing.append(key)
    assert not missing, f"Administrator routes missing fresh require_admin: {sorted(missing)}"
    assert exceptions == EXPLICIT_HUMAN_GUARDS, "Remove obsolete administrator exceptions"


# These caller transports do NOT execute administrator OpenStack inventory:
# Drover validates the original human itself; application-credential creation
# must derive its native owner/project/role ceiling from that owner's token;
# library build/consume/import writes retain caller-project trust and ledgers.
# Aodh mutations retain the human trustor/owner: trust+ actions must never
# delegate the configured service account's admin-project authority.
# Service-versions observes advertised native API versions with the caller's own
# token/catalog, so it must not borrow the fixed admin-project executor.
CALLER_TRANSPORTS = {
    ("GET", "/api/v1/admin/notifications"),
    ("GET", "/api/v1/admin/monitoring/summary"),
    ("GET", "/api/v1/admin/application-credentials/context"),
    ("POST", "/api/v1/admin/application-credentials"),
    ("POST", "/api/v1/admin/libraries/imports/dockerfile"),
    ("POST", "/api/v1/admin/libraries/build"),
    ("POST", "/api/v1/admin/libraries/consume"),
    ("POST", "/api/v1/admin/telemetry/aodh/alarms"),
    ("PUT", "/api/v1/admin/telemetry/aodh/alarms/{alarm_id}"),
    ("DELETE", "/api/v1/admin/telemetry/aodh/alarms/{alarm_id}"),
    ("GET", "/api/v1/admin/service-versions"),
}


def test_admin_caller_connections_are_explicit_native_identity_exceptions():
    found = set()
    for route in admin_routes():
        calls = set(dependency_calls(route.dependant))
        if get_os_conn not in calls:
            continue
        for method in route.methods:
            key = (method, route.path)
            assert key in CALLER_TRANSPORTS, f"Administrator provider reads must use get_admin_os_conn: {key}"
            found.add(key)
        if route.path in {"/api/v1/admin/notifications", "/api/v1/admin/monitoring/summary"}:
            assert get_admin_os_conn in calls, "OpenStack inventory must not use the Drover human transport"
    assert found == CALLER_TRANSPORTS, "Remove obsolete caller-transport exceptions"


@pytest.mark.asyncio
async def test_catalog_original_human_guard_propagates_current_authority_denial(monkeypatch):
    from app.api import deps
    from app.api.palimpsest import catalog

    original = {"token": "original-human", "is_system_admin": True}
    resolve = AsyncMock(return_value=original)
    guard = AsyncMock(side_effect=HTTPException(403, "Current system administrator authority is required"))
    monkeypatch.setattr(deps, "_resolve_jwt_token_info", resolve)
    monkeypatch.setattr(catalog, "require_admin", guard)
    request = Request({"type": "http", "headers": [(b"authorization", b"Bearer browser-jwt")]})
    with pytest.raises(HTTPException) as denied:
        await catalog.admin_identity(request)
    assert denied.value.status_code == 403
    resolve.assert_awaited_once_with(request, "browser-jwt", None, preserve_original=True)
    guard.assert_awaited_once_with(original)
