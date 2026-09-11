"""Afterglow browser proxy contracts for the extracted Lumen service."""

import asyncio
import gzip
import importlib.util
import json
import tomllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient, Headers
from httpx import Request as HttpxRequest
from httpx import Response as HttpxResponse

from app.api.deps import get_token_info
from app.api.lumen import register_lumen
from app.main import app
from app.services.service_proxy import proxy, proxy_passthrough


@pytest.fixture
async def api_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(get_token_info, None)


async def _authenticated(request: Request) -> dict:
    token_info = {
        "token": "caller-token",
        "project_id": "project-1",
        "user_id": "user-1",
        "username": "user",
        "roles": ["member"],
    }
    request.state.token_info = token_info
    return token_info


def _make_dummy_request(
    path: str = "/api/v1/chat/conversations",
    method: str = "GET",
    headers: dict[str, str] | None = None,
    query: str = "",
) -> Request:
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": raw_headers,
        "query_string": query.encode("latin-1"),
        "client": ("203.0.113.19", 54321),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def test_lumen_feature_gate_routes_inclusion():
    enabled_app = FastAPI()
    enabled_settings = SimpleNamespace(service_chat_enabled=True)
    assert register_lumen(enabled_app, enabled_settings) is True
    enabled_paths = {getattr(r, "path", "") for r in enabled_app.routes}
    assert "/api/v1/chat/mcp-oauth/callback" in enabled_paths
    assert "/api/v1/chat/{path:path}" in enabled_paths

    disabled_app = FastAPI()
    disabled_settings = SimpleNamespace(service_chat_enabled=False)
    assert register_lumen(disabled_app, disabled_settings) is False
    disabled_paths = {getattr(r, "path", "") for r in disabled_app.routes}
    assert not any(p.startswith("/api/v1/chat") for p in disabled_paths)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,upstream_path,body",
    [
        ("get", "/api/v1/chat/conversations", "/v1/conversations", None),
        ("post", "/api/v1/chat/conversations", "/v1/conversations", {"title": "New Chat"}),
        ("get", "/api/v1/chat/agents", "/v1/agents", None),
        ("delete", "/api/v1/chat/conversations/conv-1", "/v1/conversations/conv-1", None),
        ("get", "/api/v1/chat/workspaces", "/v1/workspaces", None),
        ("get", "/api/v1/chat/models", "/v1/chat/models", None),
        ("patch", "/api/v1/chat/api-keys/7", "/v1/api-keys/7", {"name": "laptop"}),
        (
            "put",
            "/api/v1/chat/admin/quotas/user-1",
            "/v1/admin/quotas/user-1",
            {"monthly_credit_limit": "5000", "weekly_credit_limit": None},
        ),
        (
            "put",
            "/api/v1/chat/admin/quotas/defaults",
            "/v1/admin/quotas/defaults",
            {"monthly_credit_limit": "100000"},
        ),
        (
            "delete",
            "/api/v1/chat/admin/quotas/user-1",
            "/v1/admin/quotas/user-1",
            None,
        ),
        (
            "get",
            "/api/v1/chat/admin/stats/users/user-1?range=30d&source=web",
            "/v1/admin/stats/users/user-1",
            None,
        ),
        (
            "get",
            "/api/v1/chat/admin/providers/7/billing",
            "/v1/admin/providers/7/billing",
            None,
        ),
    ],
)
async def test_browser_routes_proxy_to_lumen_service(api_client, method, path, upstream_path, body):
    app.dependency_overrides[get_token_info] = _authenticated
    forwarded = JSONResponse(status_code=200, content={"forwarded": True})
    with patch("app.api.lumen.proxy.proxy", new=AsyncMock(return_value=forwarded)) as proxy_call:
        call = getattr(api_client, method)
        response = await (call(path, json=body) if body is not None else call(path))

    assert response.status_code == 200
    assert response.json() == {"forwarded": True}
    service_type, request, upstream = proxy_call.await_args.args
    assert service_type == "lumen"
    assert upstream == upstream_path
    assert request.state.token_info["token"] == "caller-token"


@pytest.mark.asyncio
async def test_browser_proxy_requires_authentication(api_client):
    with patch("app.api.lumen.proxy.proxy", new=AsyncMock()) as proxy_call:
        response = await api_client.get("/api/v1/chat/conversations")

    assert response.status_code == 401
    proxy_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_lumen_mcp_oauth_callback_proxies_unauthenticated_with_cookies():
    req = _make_dummy_request(
        path="/api/v1/chat/mcp-oauth/callback",
        query="state=state-123&code=code-456",
        headers={"Cookie": "mcp_oauth_initiator_nonce=nonce-789"},
    )

    sent_requests: list[tuple[HttpxRequest, bool]] = []

    async def mock_send(outgoing_req: HttpxRequest, stream: bool = False):
        sent_requests.append((outgoing_req, stream))
        resp_headers = Headers(
            [
                ("location", "http://test/dashboard/chat?mcp_oauth=connected"),
                ("set-cookie", "cookie1=val1; Path=/"),
                ("set-cookie", "cookie2=val2; Path=/"),
            ]
        )
        resp = MagicMock(spec=HttpxResponse)
        resp.status_code = 303
        resp.headers = resp_headers
        resp.aiter_raw = MagicMock()
        resp.aclose = AsyncMock()
        return resp

    mock_client = MagicMock()
    mock_client.build_request.side_effect = lambda method, url, headers, content: HttpxRequest(
        method, url, headers=headers, content=content
    )
    mock_client.send = AsyncMock(side_effect=mock_send)
    mock_client.aclose = AsyncMock()

    with patch("app.services.service_proxy.resolve_service_endpoint", return_value="http://lumen.internal"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            response = await proxy_passthrough("lumen", req, "/v1/mcp-oauth/callback", forward_cookie=True)

    assert len(sent_requests) == 1
    sent_req, stream = sent_requests[0]
    assert str(sent_req.url) == "http://lumen.internal/v1/mcp-oauth/callback?state=state-123&code=code-456"
    assert sent_req.headers.get("cookie") == "mcp_oauth_initiator_nonce=nonce-789"
    assert sent_req.headers.get("x-forwarded-for") == "203.0.113.19"
    assert stream is True

    assert response.status_code == 303
    set_cookies = [val.decode("latin-1") for name, val in response.raw_headers if name.lower() == b"set-cookie"]
    assert set_cookies == ["cookie1=val1; Path=/", "cookie2=val2; Path=/"]


@pytest.mark.asyncio
async def test_lumen_proxy_sse_streaming_non_buffering():
    req = _make_dummy_request(
        path="/api/v1/chat/runs/run-123/events",
        headers={"X-Auth-Token": "token-1", "X-Project-Id": "proj-1"},
    )
    req.state.token_info = {"token": "token-1", "project_id": "proj-1"}

    chunk2_released = asyncio.Event()

    async def mock_aiter_raw():
        yield b"data: chunk 1\n\n"
        await chunk2_released.wait()
        yield b"data: chunk 2\n\n"

    sent_requests: list[tuple[HttpxRequest, bool]] = []

    async def mock_send(outgoing_req: HttpxRequest, stream: bool = False):
        sent_requests.append((outgoing_req, stream))
        resp_headers = Headers([("content-type", "text/event-stream")])
        resp = MagicMock(spec=HttpxResponse)
        resp.status_code = 200
        resp.headers = resp_headers
        resp.aiter_raw = mock_aiter_raw
        resp.aclose = AsyncMock()
        return resp

    mock_client = MagicMock()
    mock_client.build_request.side_effect = lambda method, url, headers, content: HttpxRequest(
        method, url, headers=headers, content=content
    )
    mock_client.send = AsyncMock(side_effect=mock_send)
    mock_client.aclose = AsyncMock()

    with patch("app.services.service_proxy._get_internal_endpoint", return_value="http://lumen.internal"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            response = await proxy("lumen", req, "/v1/runs/run-123/events")

    assert len(sent_requests) == 1
    _, stream = sent_requests[0]
    assert stream is True

    iterator = response.body_iterator
    chunk1 = await anext(iterator)
    assert chunk1 == b"data: chunk 1\n\n"

    assert not chunk2_released.is_set()

    chunk2_released.set()
    chunk2 = await anext(iterator)
    assert chunk2 == b"data: chunk 2\n\n"


@pytest.mark.asyncio
async def test_lumen_proxy_streams_owned_asset_download_without_redirect():
    req = _make_dummy_request(path="/api/v1/chat/assets/asset-1/download")
    req.state.token_info = {"token": "caller-token", "project_id": "project-1"}

    async def mock_aiter_raw():
        yield b"name,value\n"
        yield b"latency,12\n"

    upstream_response = MagicMock(spec=HttpxResponse)
    upstream_response.status_code = 200
    upstream_response.headers = Headers(
        {
            "content-type": "text/csv",
            "content-disposition": "attachment; filename=\"download\"; filename*=UTF-8''report.csv",
            "cache-control": "private, no-store",
        }
    )
    upstream_response.aiter_raw = mock_aiter_raw
    upstream_response.aclose = AsyncMock()

    mock_client = MagicMock()
    mock_client.build_request.side_effect = lambda method, url, headers, content: HttpxRequest(
        method, url, headers=headers, content=content
    )
    mock_client.send = AsyncMock(return_value=upstream_response)
    mock_client.aclose = AsyncMock()

    with patch("app.services.service_proxy._get_internal_endpoint", return_value="http://lumen.internal"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            response = await proxy("lumen", req, "/v1/assets/asset-1/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv"
    assert response.headers["content-disposition"].endswith("filename*=UTF-8''report.csv")
    assert "location" not in response.headers
    assert b"".join([chunk async for chunk in response.body_iterator]) == b"name,value\nlatency,12\n"
    upstream_response.aclose.assert_awaited_once()
    mock_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_lumen_proxy_preserves_compressed_stream_bytes():
    original = b"data: compressed first delta\n\n"
    encoded = gzip.compress(original)
    req = _make_dummy_request(path="/api/v1/chat/runs/run-1/events")
    req.state.token_info = {"token": "caller-token", "project_id": "project-1"}
    upstream = AsyncClient(
        transport=httpx.MockTransport(
            lambda request: HttpxResponse(
                200,
                headers={"content-type": "text/event-stream", "content-encoding": "gzip"},
                stream=httpx.ByteStream(encoded),
            )
        )
    )
    with (
        patch("app.services.service_proxy._get_internal_endpoint", return_value="http://isolated.test"),
        patch("app.services.service_proxy.httpx.AsyncClient", return_value=upstream),
    ):
        response = await proxy("lumen", req, "/v1/runs/run-1/events")
        body = b"".join([chunk async for chunk in response.body_iterator])
    assert dict(response.raw_headers)[b"content-encoding"] == b"gzip"
    assert body == encoded
    assert gzip.decompress(body) == original
    assert upstream.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["conversations/42", "temp-threads/thread-1"])
@pytest.mark.parametrize("operation", ["context-preview", "compactions"])
async def test_context_routes_preserve_post_body_and_idempotency(api_client, resource, operation):
    app.dependency_overrides[get_token_info] = _authenticated
    request_body = {"model_id": "configured-model"}
    if operation == "context-preview":
        request_body["parts"] = [{"type": "text", "text": "unsent draft"}]
    else:
        request_body["expected_context_revision"] = "revision-1"
    key = "29b9c011-b273-423c-9e8b-0848a36c052e"
    expected_status = 200 if operation == "context-preview" else 202
    received = []

    async def handler(request):
        received.append((request.method, request.url.path, json.loads(await request.aread()), request.headers))
        return HttpxResponse(
            expected_status,
            headers={"content-type": "application/json"},
            stream=httpx.ByteStream(b'{"state":"accepted"}'),
        )

    upstream = AsyncClient(transport=httpx.MockTransport(handler))
    with (
        patch("app.services.service_proxy._get_internal_endpoint", return_value="http://isolated.test/v1"),
        patch("app.services.service_proxy.httpx.AsyncClient", return_value=upstream),
    ):
        response = await api_client.post(
            f"/api/v1/chat/{resource}/{operation}",
            json=request_body,
            headers={"Idempotency-Key": key},
        )
    assert response.status_code == expected_status
    assert response.json() == {"state": "accepted"}
    method, path, body, headers = received.pop()
    assert (method, path, body) == ("POST", f"/v1/{resource}/{operation}", request_body)
    assert headers["idempotency-key"] == key
    assert headers["x-auth-token"] == "caller-token"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "body", "status_code", "response_body"),
    [
        (
            "POST",
            "/api/v1/chat/admin/providers/7/auth/device",
            {},
            201,
            {
                "attempt_id": "opaque-attempt",
                "status": "pending",
                "verification_uri": "https://auth.openai.com/device",
                "user_code": "ABCD-EFGH",
                "expires_at": "2030-01-01T00:00:00Z",
                "interval_seconds": 5,
            },
        ),
        (
            "POST",
            "/api/v1/chat/admin/providers/7/auth/device/opaque-attempt/poll",
            {},
            200,
            {
                "attempt_id": "opaque-attempt",
                "status": "connected",
                "expires_at": "2030-01-01T00:00:00Z",
                "interval_seconds": 5,
            },
        ),
        (
            "DELETE",
            "/api/v1/chat/admin/providers/7/auth/device/opaque-attempt",
            None,
            204,
            None,
        ),
        (
            "PUT",
            "/api/v1/chat/admin/providers/8/auth/token",
            {"token": "sk-ant-oat01-contract-fixture-token", "expires_at": None},
            200,
            {
                "id": 8,
                "auth_mode": "anthropic_subscription",
                "has_credentials": True,
                "auth_status": "configured",
            },
        ),
        (
            "DELETE",
            "/api/v1/chat/admin/providers/8/auth",
            None,
            204,
            None,
        ),
    ],
)
async def test_subscription_auth_routes_preserve_method_body_response_and_no_store(
    api_client,
    method,
    path,
    body,
    status_code,
    response_body,
):
    app.dependency_overrides[get_token_info] = _authenticated
    received = []

    async def handler(request):
        raw_body = await request.aread()
        received.append(
            (
                request.method,
                request.url.path,
                json.loads(raw_body) if raw_body else None,
                request.headers,
            )
        )
        content = b"" if response_body is None else json.dumps(response_body).encode()
        return HttpxResponse(
            status_code,
            headers={"content-type": "application/json", "cache-control": "no-store"},
            stream=httpx.ByteStream(content),
        )

    upstream = AsyncClient(transport=httpx.MockTransport(handler))
    with (
        patch("app.services.service_proxy._get_internal_endpoint", return_value="http://isolated.test/v1"),
        patch("app.services.service_proxy.httpx.AsyncClient", return_value=upstream),
    ):
        request_kwargs = {"json": body} if body is not None else {}
        response = await api_client.request(method, path, **request_kwargs)

    assert response.status_code == status_code
    assert response.headers["cache-control"] == "no-store"
    if response_body is not None:
        assert response.json() == response_body
    else:
        assert response.content == b""
    forwarded_method, forwarded_path, forwarded_body, forwarded_headers = received.pop()
    assert forwarded_method == method
    assert forwarded_path == f"/v1{path.removeprefix('/api/v1/chat')}"
    assert forwarded_body == body
    assert forwarded_headers["x-auth-token"] == "caller-token"
    assert forwarded_headers["x-project-id"] == "project-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (429, "subscription_rate_limited"),
        (503, "subscription_upstream_unavailable"),
    ],
)
async def test_subscription_auth_proxy_preserves_safe_error_and_no_store(api_client, status_code, code):
    app.dependency_overrides[get_token_info] = _authenticated
    error_body = {"detail": {"code": code, "message": "구독 인증 요청을 계속할 수 없습니다"}}

    def handler(_request):
        return HttpxResponse(
            status_code,
            headers={"content-type": "application/json", "cache-control": "no-store"},
            stream=httpx.ByteStream(json.dumps(error_body).encode()),
        )

    upstream = AsyncClient(transport=httpx.MockTransport(handler))
    with (
        patch("app.services.service_proxy._get_internal_endpoint", return_value="http://isolated.test/v1"),
        patch("app.services.service_proxy.httpx.AsyncClient", return_value=upstream),
    ):
        response = await api_client.post("/api/v1/chat/admin/providers/7/auth/device", json={})

    assert response.status_code == status_code
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == error_body


@pytest.mark.asyncio
async def test_lumen_proxy_unavailable_catalog_503(api_client):
    app.dependency_overrides[get_token_info] = _authenticated
    with patch("app.services.service_proxy._get_internal_endpoint", return_value=None):
        response = await api_client.get("/api/v1/chat/conversations")

    assert response.status_code == 503
    assert response.json() == {"detail": "lumen 서비스를 사용할 수 없습니다"}


@pytest.mark.asyncio
async def test_external_v1_openai_anthropic_unmounted(api_client):
    resps = [
        await api_client.post("/v1/chat/completions", json={"model": "gpt-4"}),
        await api_client.post("/v1/messages", json={"model": "claude-3"}),
        await api_client.get("/v1/models"),
    ]
    for r in resps:
        assert r.status_code == 404


def test_afterglow_chat_boundary_no_ai_runtime_dependencies_or_secrets():
    # 1. Verify app.chat_worker entry point does not exist
    assert importlib.util.find_spec("app.chat_worker") is None

    # 2. Verify install metadata has no AI execution packages.
    repo_root = Path(__file__).resolve().parents[3]
    pyproject = tomllib.loads((repo_root / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    dependency_specs = [
        *pyproject["project"]["dependencies"],
        *pyproject["dependency-groups"]["worker"],
    ]
    dependency_names = {
        spec.split("@", 1)[0].split("[", 1)[0].split("=", 1)[0].split("<", 1)[0].strip().lower()
        for spec in dependency_specs
    }
    forbidden_deps = {
        "litellm",
        "langgraph",
        "langchain-core",
        "langgraph-checkpoint-postgres",
        "langchain-mcp-adapters",
        "pgvector",
        "psycopg",
        "lumen-sdk",
    }
    assert dependency_names.isdisjoint(forbidden_deps)

    # 3. Verify deployment templates contain no chat runtime secrets.
    forbidden_secrets = [
        "CHAT_CHECKPOINTER_POSTGRES_URL",
        "CHAT_MEMORY_PGVECTOR_URL",
        "CHAT_ASSET_S3_ACCESS_KEY",
        "CHAT_ASSET_S3_SECRET_KEY",
        "CHAT_SANDBOX_API_KEY",
    ]
    deploy_paths = [
        repo_root / "docker-compose.yml",
        repo_root / "docker-compose.prod.yml",
        repo_root / "deploy" / "k8s-template" / "base" / "backend" / "deployment.yaml",
        repo_root / "helm" / "afterglow" / "templates" / "backend" / "deployment.yaml",
        repo_root / "helm" / "afterglow" / "values.yaml",
    ]
    for path in deploy_paths:
        if path.exists():
            txt = path.read_text(encoding="utf-8")
            for secret in forbidden_secrets:
                assert secret not in txt, f"Forbidden secret {secret} found in {path}"
            assert "chat-worker" not in txt, f"Stale chat-worker reference found in {path}"

    assert not (repo_root / "helm" / "afterglow" / "templates" / "backend" / "chat-worker-deployment.yaml").exists()

    development_compose = yaml.safe_load((repo_root / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "pgvector" not in development_compose["services"]
    production_compose = yaml.safe_load((repo_root / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    for service_name in ("lumen-migrate", "lumen-api", "lumen-worker"):
        service = development_compose["services"][service_name]
        assert service["environment"]["LUMEN_ENCRYPTION_KEY"] == "${LUMEN_ENCRYPTION_KEY:-}"
        assert all("/etc/afterglow/" not in volume for volume in service.get("volumes", []))
    for service_name in ("lumen-api", "lumen-worker"):
        service = production_compose["services"][service_name]
        assert service["environment"]["LUMEN_ENCRYPTION_KEY"] == "${LUMEN_ENCRYPTION_KEY:-}"


def test_lumen_compose_keystone_auth_configuration():
    repo_root = Path(__file__).resolve().parents[3]
    compose_path = repo_root / "docker-compose.yml"
    compose_raw = compose_path.read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_raw)

    command = "--env-file .env --env-file docker-compose.services.env --profile services"
    assert command in compose_raw

    expected = {
        "KEYSTONE_AUTH_URL": "${LUMEN_KEYSTONE_AUTH_URL:-${OS_AUTH_URL:-}}",
        "KEYSTONE_ADMIN_USERNAME": "${LUMEN_KEYSTONE_ADMIN_USERNAME:-${OS_USERNAME:-}}",
        "KEYSTONE_ADMIN_PASSWORD": "${LUMEN_KEYSTONE_ADMIN_PASSWORD:-${OS_PASSWORD:-}}",
        "KEYSTONE_ADMIN_PROJECT": "${LUMEN_KEYSTONE_ADMIN_PROJECT:-${OS_PROJECT_NAME:-}}",
        "KEYSTONE_DOMAIN": "${LUMEN_KEYSTONE_DOMAIN:-${OS_USER_DOMAIN_NAME:-Default}}",
        "KEYSTONE_REGION_NAME": "${LUMEN_KEYSTONE_REGION_NAME:-${OS_REGION_NAME:-RegionOne}}",
        "KEYSTONE_INTERFACE": "${LUMEN_KEYSTONE_INTERFACE:-${OS_INTERFACE:-internal}}",
    }
    for service_name in ("lumen-migrate", "lumen-api", "lumen-worker"):
        service = compose["services"][service_name]
        assert service["env_file"] == [{"path": ".env", "required": False}]
        assert {key: service["environment"][key] for key in expected} == expected
        assert "localhost:5000" not in str(service["environment"])

    example = (repo_root / ".env.example").read_text(encoding="utf-8")
    for name in (
        "LUMEN_KEYSTONE_AUTH_URL",
        "LUMEN_KEYSTONE_ADMIN_USERNAME",
        "LUMEN_KEYSTONE_ADMIN_PASSWORD",
        "LUMEN_KEYSTONE_ADMIN_PROJECT",
        "LUMEN_KEYSTONE_DOMAIN",
        "LUMEN_KEYSTONE_REGION_NAME",
        "LUMEN_KEYSTONE_INTERFACE",
    ):
        assert f"{name}=" in example
