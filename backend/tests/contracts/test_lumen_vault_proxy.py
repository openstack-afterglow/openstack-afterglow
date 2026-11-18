"""Vault browser authority and wire contract; no live network or credentials."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api.deps import get_token_info
from app.api.lumen.proxy import router

BASE = "/api/v1/chat/vault"


@pytest.fixture
async def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/chat")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield app, http


@pytest.fixture
def authenticated(client, monkeypatch):
    app, _ = client

    async def session(request: Request):
        request.state.token_info = {
            "token": "native-session",
            "user_id": "user-1",
            "project_id": "selected-project",
            "domain_id": "domain-1",
        }
        return request.state.token_info

    app.dependency_overrides[get_token_info] = session
    access = AsyncMock(return_value={"roles": ["member"]})
    monkeypatch.setattr("app.services.project_service.get_project_access", access)
    return access


@pytest.fixture
def policy(monkeypatch):
    resolve = AsyncMock(return_value={"capabilities": ["lumen-history_reader", "lumen-history_editor"]})
    monkeypatch.setattr("app.api.lumen.proxy.get_policy_capabilities", resolve)
    return resolve


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer " + "sk-afgl-" + "synthetic-key"}, {"X-Api-Key": "test-only"}],
)
async def test_vault_requires_dashboard_session(client, policy, headers):
    _, http = client
    response = await http.get(f"{BASE}/notes", headers=headers)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    policy.assert_not_awaited()


@pytest.mark.parametrize(
    ("method", "path", "opposite_leaf"),
    [("GET", "notes/7/revisions", "editor"), ("POST", "notes", "reader"), ("PUT", "profile", "reader")],
)
async def test_vault_read_and_write_require_distinct_native_leaves(
    client, authenticated, policy, monkeypatch, method, path, opposite_leaf
):
    _, http = client
    policy.return_value = {"capabilities": [f"lumen-history_{opposite_leaf}"]}
    forward = AsyncMock()
    monkeypatch.setattr("app.api.lumen.proxy.proxy", forward)
    response = await http.request(method, f"{BASE}/{path}")
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    authenticated.assert_awaited_once_with("selected-project", "user-1")
    forward.assert_not_awaited()


@pytest.mark.parametrize(
    ("method", "path", "status", "request_body", "response_body"),
    [
        ("GET", "notes?kind=log&limit=2&before=3", 200, b"", b"[]"),
        ("GET", "search?query=hello%20world&kind=user_note", 200, b"", b"[]"),
        ("GET", "document", 200, b"", b'{"filename":"memory.md","content_type":"text/markdown","content":"# Memory"}'),
        ("GET", "notes/7", 404, b"", b'{"detail":"note_not_found"}'),
        ("GET", "notes/7/revisions?before=3", 200, b"", b"[]"),
        ("GET", "profile", 200, b"", b'{"exists":false}'),
        ("GET", "coding-standards", 200, b"", b'{"exists":false}'),
        ("GET", "short-term?scope=global", 200, b"", b'{"exists":false}'),
        ("PUT", "profile", 200, b'{"content":"Profile"}', b'{"id":8}'),
        ("PUT", "coding-standards", 422, b'{"content":"test secret"}', b'{"detail":"secret_detected"}'),
        ("PUT", "short-term", 503, b'{"content":"Working memory"}', b'{"detail":"vault_unavailable"}'),
        ("POST", "notes", 201, b'{"kind":"user_note","scope":"domain","content":"New note"}', b'{"id":8}'),
        ("PATCH", "notes/7", 409, b'{"content":"edit","expectedHash":"test-hash"}', b'{"detail":"hash_mismatch"}'),
        ("GET", "notes?workspace_id=31", 200, b"", b'[{"id":7,"workspace_id":31}]'),
        ("GET", "search?workspace_id=31&query=memory", 200, b"", b'[{"id":7,"workspace_id":31}]'),
        ("GET", "notes/7?workspace_id=31", 200, b"", b'{"id":7,"workspace_id":31}'),
        ("GET", "notes/7/revisions?workspace_id=31&before=3", 200, b"", b"[]"),
        ("PATCH", "notes/7?workspace_id=31", 200, b'{"content":"edit","expectedHash":"test-hash"}', b'{"id":7}'),
        (
            "POST",
            "notes",
            201,
            b'{"kind":"user_note","scope":"domain","workspace_id":31}',
            b'{"id":7,"workspace_id":31}',
        ),
    ],
)
async def test_vault_forwards_exact_request_and_native_response(
    client, authenticated, policy, monkeypatch, method, path, status, request_body, response_body
):
    _, http = client
    received = []

    async def handle(request):
        received.append((request, await request.aread()))
        return httpx.Response(
            status,
            headers={"Content-Type": "application/json", "Cache-Control": "public"},
            stream=httpx.ByteStream(response_body),
        )

    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr("app.services.service_proxy._get_internal_endpoint", lambda *_: "http://native.invalid/v1")
    monkeypatch.setattr("app.services.service_proxy.httpx.AsyncClient", lambda **_: upstream)
    response = await http.request(
        method,
        f"{BASE}/{path}",
        content=request_body or None,
        headers={
            "Authorization": "Bearer browser-jwt",
            "X-Auth-Token": "untrusted",
            "X-Project-Id": "untrusted",
            "X-Domain-Id": "untrusted",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == status
    assert response.content == response_body
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    [(request, body)] = received
    assert (request.method, str(request.url), body) == (method, f"http://native.invalid/v1/vault/{path}", request_body)
    assert request.headers["x-auth-token"] == "native-session"
    assert request.headers["x-project-id"] == "selected-project"
    assert not {"authorization", "x-domain-id"} & request.headers.keys()
    policy.assert_awaited_once()


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [("GET", "internal", 404), ("DELETE", "notes/1", 405), ("POST", "search", 405)],
)
async def test_vault_rejects_unlisted_routes_and_methods(client, authenticated, policy, method, path, status):
    _, http = client
    response = await http.request(method, f"{BASE}/{path}")
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    policy.assert_not_awaited()
