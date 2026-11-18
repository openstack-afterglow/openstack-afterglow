"""Authenticated realtime admission strips Lumen secrets; WebSockets consume one-use tickets."""

import asyncio
import json
from base64 import b64encode
from collections import deque
from datetime import datetime
from io import BytesIO
from random import Random
from threading import Thread
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from PIL import Image
from starlette.websockets import WebSocketDisconnect
from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve

from app.api.deps import get_token_info
from app.api.lumen.realtime import router
from app.services import ws_ticket


async def _authenticated(request: Request):
    principal = {"token": "keystone-caller", "project_id": "owned-project", "user_id": "owner"}
    request.state.token_info = principal
    return principal


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "image_hint", "frame_hint", "image_input"),
    [
        (None, None, None, False),
        ("conversation", True, 2_097_152, True),
        ("conversation", True, 65_536, False),
        ("transcription", None, None, False),
        ("translation", None, None, False),
        ("live", True, 2_097_152, False),
    ],
)
async def test_realtime_admission_returns_only_project_bound_browser_ticket(
    monkeypatch, kind, image_hint, frame_hint, image_input
):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/chat")
    app.dependency_overrides[get_token_info] = _authenticated
    authorize = AsyncMock(return_value=None)
    monkeypatch.setattr("app.api.lumen.realtime.authorize_service_request", authorize)
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
                "realtime_image_input": image_hint,
                "max_client_frame_bytes": frame_hint,
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
            json={
                "model_id": "12",
                **({"voice": "alloy"} if kind not in {"transcription", "translation"} else {}),
                **({"output_language": "pt-BR"} if kind == "translation" else {}),
                **({"instructions": "Speak slowly"} if kind == "live" else {}),
                **({"reasoning_effort": "xhigh"} if kind == "conversation" else {}),
                **({"kind": kind} if kind is not None else {}),
            },
            headers={"Idempotency-Key": key},
        )
    assert response.status_code == 201
    authorize.assert_awaited_once()
    assert authorize.await_args.args[0] == "lumen"
    assert authorize.await_args.args[2] == "/v1/chat/realtime/sessions"
    assert response.json()["ticket"] == "opaque-browser-ticket"
    assert response.json()["realtime_image_input"] is image_input
    assert datetime.fromisoformat(response.json()["expires_at"]).timestamp() > datetime.now().timestamp()
    assert "connect_token" not in response.json()
    assert "private-lumen-ticket" not in str(response.json())
    assert str(upstream[0].url) == "http://lumen.internal/v1/chat/realtime/sessions"
    assert upstream[0].headers["x-auth-token"] == "keystone-caller"
    assert upstream[0].headers["x-project-id"] == "owned-project"
    assert upstream[0].headers["Idempotency-Key"] == key
    payload = json.loads(upstream[0].content)
    assert payload["kind"] == (kind or "conversation")
    assert payload["voice"] == (None if kind in {"transcription", "translation"} else "alloy")
    if kind == "translation":
        assert payload["output_language"] == "pt-BR"
    else:
        assert "output_language" not in payload
    assert payload["instructions"] == ("Speak slowly" if kind == "live" else None)
    if kind == "conversation":
        assert payload["reasoning_effort"] == "xhigh"
    else:
        assert "reasoning_effort" not in payload
    issue.assert_awaited_once_with(
        "chat-realtime",
        {
            "session_id": session_id,
            "connect_token": "private-lumen-ticket-should-never-reach-browser",
            "user_id": "owner",
            "project_id": "owned-project",
            "realtime_image_input": image_input,
        },
        ttl_seconds=60,
        revoke_scope="owned-project",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "translation"},
        {"kind": "translation", "output_language": "Spanish"},
        {"kind": "translation", "output_language": "es", "voice": "alloy"},
        {"kind": "translation", "output_language": "es", "instructions": "Speak slowly"},
        {"kind": "live", "output_language": "es"},
        {"kind": "live", "delegation": {"type": "responses"}},
        {"kind": "live", "reasoning_effort": "low"},
        {"kind": "conversation", "reasoning_effort": "none"},
    ],
)
async def test_realtime_rejects_fields_outside_the_mode_contract(monkeypatch, payload):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/chat")
    app.dependency_overrides[get_token_info] = _authenticated
    authorize = AsyncMock()
    monkeypatch.setattr("app.api.lumen.realtime.authorize_service_request", authorize)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as browser:
        response = await browser.post(
            "/api/v1/chat/realtime/sessions",
            json={"model_id": "12", **payload},
            headers={"Idempotency-Key": str(uuid4())},
        )
    assert response.status_code == 422
    authorize.assert_not_awaited()


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


@pytest.mark.parametrize("image_input", [True, False])
def test_realtime_relay_preserves_admitted_large_messages_and_rejects_overflow(monkeypatch, image_input):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/chat")
    session_id = str(uuid4())
    token = "private-lumen-token-1234567890123456789"
    received = deque()
    cap = 2 * 1024 * 1024 if image_input else 64 * 1024
    reply = json.dumps({"type": "transcript.output.delta", "delta": "a" * (80_000 if image_input else 2)})
    png = BytesIO()
    with Image.frombytes("RGB", (560, 560), Random(786).randbytes(560 * 560 * 3)) as image:
        image.save(png, format="PNG")
    assert 900 * 1024 < png.tell() < 1024 * 1024
    image_frame = json.dumps(
        {"type": "conversation.input_image", "image_url": "data:image/png;base64," + b64encode(png.getvalue()).decode()}
    )

    def lumen(websocket):
        received.append((websocket.request.path, websocket.request.headers["x-realtime-token"]))
        received.append(websocket.recv(timeout=5))
        websocket.send(reply)
        with pytest.raises(ConnectionClosed):
            websocket.recv(timeout=5)

    with serve(lumen, "127.0.0.1", 0, max_size=2 * 1024 * 1024) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            monkeypatch.setattr(
                ws_ticket,
                "consume_ticket",
                AsyncMock(
                    return_value={"session_id": session_id, "connect_token": token, "realtime_image_input": image_input}
                ),
            )
            monkeypatch.setattr(
                "app.api.lumen.realtime._origin_allowed", lambda origin: origin == "https://console.example"
            )
            monkeypatch.setattr(
                "app.services.service_proxy.resolve_service_endpoint",
                AsyncMock(return_value=f"http://127.0.0.1:{server.socket.getsockname()[1]}"),
            )
            accepted = image_frame if image_input else '{"type":"session.close"}'
            with (
                TestClient(app) as browser,
                browser.websocket_connect(
                    "/api/v1/chat/realtime/ws?ticket=opaque", headers={"origin": "https://console.example"}
                ) as socket,
            ):
                socket.send_text(accepted)
                assert socket.receive_text() == reply
                # Character count stays below the cap, but UTF-8 exceeds it by one byte.
                socket.send_text("é" * (cap // 2) + " ")
                with pytest.raises(WebSocketDisconnect) as rejected:
                    socket.receive_text()
                assert rejected.value.code == 1009
            assert list(received) == [(f"/v1/chat/realtime/sessions/{session_id}/ws", token), accepted]
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["voice", "unknown", "", None])
async def test_realtime_admission_rejects_invalid_kind_before_native_request(monkeypatch, kind):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/chat")
    app.dependency_overrides[get_token_info] = _authenticated
    authorize = AsyncMock(side_effect=AssertionError("invalid kind must not reach service authorization"))
    monkeypatch.setattr("app.api.lumen.realtime.authorize_service_request", authorize)
    endpoint = AsyncMock(side_effect=AssertionError("invalid kind must not reach Lumen"))
    monkeypatch.setattr("app.services.service_proxy._get_internal_endpoint", endpoint)
    issue = AsyncMock()
    monkeypatch.setattr(ws_ticket, "issue_ticket", issue)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as browser:
        response = await browser.post(
            "/api/v1/chat/realtime/sessions",
            json={"model_id": "12", "kind": kind},
            headers={"Idempotency-Key": str(uuid4())},
        )
    assert response.status_code == 422
    authorize.assert_not_awaited()
    endpoint.assert_not_called()
    issue.assert_not_awaited()
