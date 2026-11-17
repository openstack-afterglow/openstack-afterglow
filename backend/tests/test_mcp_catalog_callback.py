"""Callback privacy uses the real register_lumen ordering, never the generic proxy."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.api.deps import get_token_info
from app.api.lumen import register_lumen
from app.services import service_proxy


@pytest.fixture
async def callback_proxy(monkeypatch):
    state = SimpleNamespace(status=303, failure=None, browser_auth_calls=0, forwarded=[])
    app = FastAPI()
    assert register_lumen(app, SimpleNamespace(service_chat_enabled=True)) is True

    async def unexpected_browser_auth():
        state.browser_auth_calls += 1
        raise AssertionError("The native state-bound callback must not require a browser bearer")

    app.dependency_overrides[get_token_info] = unexpected_browser_auth

    async def endpoint(service):
        assert service == "lumen"
        if state.failure == "endpoint":
            return None
        if state.failure == "exception":
            raise HTTPException(status_code=503, detail="Native callback endpoint is unavailable")
        return "http://lumen.test/v1"

    async def upstream(request):
        state.forwarded.append(request)
        if state.failure == "transport":
            raise httpx.ConnectError("Synthetic callback transport failure", request=request)
        return httpx.Response(
            state.status,
            headers=[
                ("content-type", "text/html; charset=utf-8"),
                ("cache-control", "public, max-age=3600"),
                ("location", "https://browser.test/dashboard/chat?mcp_oauth=connected"),
                ("set-cookie", "mcp_oauth_initiator_nonce=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax"),
                ("set-cookie", "another_callback_cookie=; Max-Age=0; Path=/; HttpOnly"),
            ],
            stream=httpx.ByteStream(b"Native callback response"),
        )

    monkeypatch.setattr(service_proxy, "resolve_service_endpoint", endpoint)
    monkeypatch.setattr(service_proxy, "get_settings", lambda: SimpleNamespace(ssl_verify=True))
    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        service_proxy.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(upstream), **kwargs),
    )
    async with client_type(transport=httpx.ASGITransport(app=app), base_url="https://browser.test") as client:
        yield state, client


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [303, 400, 403, 503])
async def test_actual_callback_route_preserves_native_response_and_is_private(callback_proxy, status):
    state, client = callback_proxy
    state.status = status
    response = await client.get(
        "/api/v1/chat/mcp-oauth/callback?state=synthetic-state&code=synthetic-code",
        headers={"Cookie": "mcp_oauth_initiator_nonce=synthetic-nonce"},
    )

    assert response.status_code == status
    assert response.content == b"Native callback response"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["location"] == "https://browser.test/dashboard/chat?mcp_oauth=connected"
    assert response.headers.get_list("set-cookie") == [
        "mcp_oauth_initiator_nonce=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax",
        "another_callback_cookie=; Max-Age=0; Path=/; HttpOnly",
    ]
    assert state.browser_auth_calls == 0
    assert len(state.forwarded) == 1
    upstream = state.forwarded[0]
    assert upstream.method == "GET"
    assert str(upstream.url) == "http://lumen.test/v1/mcp-oauth/callback?state=synthetic-state&code=synthetic-code"
    assert upstream.headers["cookie"] == "mcp_oauth_initiator_nonce=synthetic-nonce"
    assert "authorization" not in upstream.headers
    assert "x-auth-token" not in upstream.headers


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["endpoint", "transport", "exception"])
async def test_actual_callback_route_failures_are_private_without_browser_auth(callback_proxy, failure):
    state, client = callback_proxy
    state.failure = failure
    response = await client.get("/api/v1/chat/mcp-oauth/callback?state=synthetic-state&error=access_denied")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert state.browser_auth_calls == 0
    assert len(state.forwarded) == (1 if failure == "transport" else 0)
