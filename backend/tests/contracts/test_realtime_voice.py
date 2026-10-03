"""Authenticated realtime admission strips Lumen secrets; WebSockets consume one-use tickets."""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from starlette.websockets import WebSocketDisconnect

from app.api.deps import get_token_info
from app.api.lumen.realtime import router
from app.services import ws_ticket


async def _authenticated(request: Request):
    principal = {"token": "keystone-caller", "project_id": "owned-project", "user_id": "owner"}
    request.state.token_info = principal
    return principal


@pytest.mark.asyncio
async def test_realtime_admission_returns_only_project_bound_browser_ticket(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/chat")
    app.dependency_overrides[get_token_info] = _authenticated
    upstream = []
    session_id = str(uuid4())

    async def handler(request):
        upstream.append(request)
        return httpx.Response(
            201,
            json={
                "session_id": session_id,
                "status": "ready",
                "model_name": "gpt-realtime",
                "provider_type": "openai",
                "expires_in_seconds": 60,
                "connect_token": "private-lumen-ticket-should-never-reach-browser",
            },
        )

    client = AsyncClient(transport=httpx.MockTransport(handler), base_url="http://lumen.internal")
    monkeypatch.setattr("app.services.service_proxy._get_internal_endpoint", lambda *_: "http://lumen.internal")
    monkeypatch.setattr("app.api.lumen.realtime.httpx.AsyncClient", lambda **_: client)
    issue = AsyncMock(return_value="opaque-browser-ticket")
    monkeypatch.setattr(ws_ticket, "issue_ticket", issue)
    key = str(uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as browser:
        response = await browser.post(
            "/api/v1/chat/realtime/sessions",
            json={"model_id": "12", "voice": "alloy"},
            headers={"Idempotency-Key": key},
        )
    assert response.status_code == 201
    assert response.json()["ticket"] == "opaque-browser-ticket"
    assert datetime.fromisoformat(response.json()["expires_at"]).timestamp() > datetime.now().timestamp()
    assert "connect_token" not in response.json()
    assert "private-lumen-ticket" not in str(response.json())
    assert str(upstream[0].url) == "http://lumen.internal/v1/chat/realtime/sessions"
    assert upstream[0].headers["x-auth-token"] == "keystone-caller"
    assert upstream[0].headers["x-project-id"] == "owned-project"
    assert upstream[0].headers["Idempotency-Key"] == key
    issue.assert_awaited_once_with(
        "chat-realtime",
        {
            "session_id": session_id,
            "connect_token": "private-lumen-ticket-should-never-reach-browser",
            "user_id": "owner",
            "project_id": "owned-project",
        },
        ttl_seconds=60,
        revoke_scope="owned-project",
    )


def test_realtime_ws_rejects_origin_and_relay_preserves_audio_frames(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/chat")
    session_id = str(uuid4())
    consume = AsyncMock(
        return_value={
            "session_id": session_id,
            "connect_token": "private-lumen-token-1234567890123456789",
            "user_id": "owner",
            "project_id": "owned-project",
        }
    )
    monkeypatch.setattr(ws_ticket, "consume_ticket", consume)
    monkeypatch.setattr("app.api.lumen.realtime._origin_allowed", lambda value: value == "https://console.example")
    monkeypatch.setattr(
        "app.services.service_proxy.resolve_service_endpoint", AsyncMock(return_value="https://lumen.internal/v1")
    )
    sent = []

    class Upstream:
        def __init__(self):
            self.queue = asyncio.Queue()

        async def send(self, frame):
            sent.append(frame)
            await self.queue.put(json.dumps({"type": "audio.output.delta", "delta": "AAABAA=="}))

        async def __aiter__(self):
            while True:
                yield await self.queue.get()

    class Connection:
        async def __aenter__(self):
            return Upstream()

        async def __aexit__(self, *_):
            return False

    connections = []

    def connect(url, **kwargs):
        connections.append((url, kwargs))
        return Connection()

    monkeypatch.setattr("app.api.lumen.realtime.websockets.connect", connect)
    with TestClient(app) as browser:
        with pytest.raises(WebSocketDisconnect) as denied:
            with browser.websocket_connect(
                "/api/v1/chat/realtime/ws?ticket=opaque", headers={"origin": "https://evil.example"}
            ):
                pass
        assert denied.value.code == 4403
        consume.assert_not_awaited()
        with browser.websocket_connect(
            "/api/v1/chat/realtime/ws?ticket=opaque", headers={"origin": "https://console.example"}
        ) as socket:
            socket.send_text('{"type":"audio.input.append","audio":"AAABAA=="}')
            assert socket.receive_json() == {"type": "audio.output.delta", "delta": "AAABAA=="}
    assert sent == ['{"type":"audio.input.append","audio":"AAABAA=="}']
    assert connections[0][0] == f"wss://lumen.internal/v1/chat/realtime/sessions/{session_id}/ws"
    assert connections[0][1]["additional_headers"] == {"x-realtime-token": "private-lumen-token-1234567890123456789"}
    consume.assert_awaited_once_with("opaque", expected_kind="chat-realtime")
