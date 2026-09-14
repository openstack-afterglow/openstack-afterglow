"""Focused backend unit tests for service proxy layer."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from app.api.deps import get_token_info
from app.main import app
from app.services.service_proxy import (
    _get_internal_endpoint,
    _get_service_internal_endpoint,
    get_json,
    proxy,
    proxy_passthrough,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment_endpoint", "toml_endpoint", "expected_source"),
    [
        (None, "", "catalog"),
        (None, "https://toml.test/v1", "toml"),
        ("https://environment.test/v1", "https://toml.test/v1", "environment"),
        ("", "https://toml.test/v1", "catalog"),
        ("https://unavailable.test/v1", "https://toml.test/v1", None),
    ],
)
async def test_configured_endpoint_precedence_reaches_selected_service(
    monkeypatch, environment_endpoint, toml_endpoint, expected_source
):
    from app import config as app_config

    # get_settings seeds os.environ from TOML. Isolate that mutation as well as
    # the explicitly supplied environment value between requests/test cases.
    monkeypatch.setattr(app_config.os, "environ", dict(app_config.os.environ))
    monkeypatch.delenv("SERVICE_LUMEN_INTERNAL_URL", raising=False)
    if environment_endpoint is not None:
        monkeypatch.setenv("SERVICE_LUMEN_INTERNAL_URL", environment_endpoint)
    monkeypatch.setattr(app_config, "_load_toml", lambda: {"service_lumen_internal_url": toml_endpoint})
    settings = app_config.get_settings.__wrapped__()
    connection = MagicMock()
    connection.session.get_endpoint.return_value = "https://catalog.test/v1"
    models = {
        "https://catalog.test/v1/models": {"models": [{"id": "catalog-model"}]},
        "https://toml.test/v1/models": {"models": [{"id": "toml-model"}]},
        "https://environment.test/v1/models": {"models": [{"id": "environment-model"}]},
    }

    def upstream(request):
        payload = models.get(str(request.url))
        return httpx.Response(200, json=payload) if payload else httpx.Response(503)

    request = _make_request(token_info={"token": "caller-token", "project_id": "caller-project"})
    with (
        patch("app.services.service_proxy.get_settings", return_value=settings),
        patch("app.services.keystone.get_openstack_connection", return_value=connection),
        patch(
            "app.services.service_proxy.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=httpx.MockTransport(upstream)),
        ),
    ):
        if expected_source is None:
            # A broken explicit test endpoint must not silently reach the
            # healthy catalog service and expose production data instead.
            with pytest.raises(HTTPException) as failure:
                await get_json("lumen", request, "/models")
            assert failure.value.status_code == 503
        else:
            assert await get_json("lumen", request, "/models") == models[f"https://{expected_source}.test/v1/models"]


def _make_request(
    method: str = "GET",
    path: str = "/api/v1/waygate/servers",
    query_string: str = "",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
    token_info: dict | None = None,
) -> Request:
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    async def _receive():
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string.encode("utf-8"),
        "headers": raw_headers,
        "client": ("203.0.113.10", 12345),
    }
    req = Request(scope, _receive)
    if token_info:
        req.state.token_info = token_info
    return req


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/waygate", "/api/v1/k3s"])
async def test_service_discovery_returns_json_without_internal_redirect(path, monkeypatch):
    upstream = FastAPI()

    @upstream.get("/v1/")
    async def discovery():
        return {"version": "1.0.0"}

    async def authenticated(request: Request):
        info = {"token": "caller-token", "project_id": "project-1", "user_id": "user-1"}
        request.state.token_info = info
        return info

    monkeypatch.setitem(app.dependency_overrides, get_token_info, authenticated)
    monkeypatch.setattr(
        "app.services.service_proxy._get_internal_endpoint", lambda *_args: "http://service.internal/v1"
    )
    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        "app.services.service_proxy.httpx.AsyncClient",
        lambda **kwargs: client_type(transport=httpx.ASGITransport(app=upstream), **kwargs),
    )
    async with client_type(transport=httpx.ASGITransport(app=app), base_url="http://bff") as client:
        response = await client.get(path)

    assert response.status_code == 200
    assert response.json() == {"version": "1.0.0"}


def test_get_internal_endpoint_success():
    mock_conn = MagicMock()
    mock_conn.session.get_endpoint.return_value = "http://10.0.0.1:8010/v1/"
    with patch("app.services.keystone.get_openstack_connection", return_value=mock_conn) as mock_get_conn:
        ep = _get_internal_endpoint("token-123", "proj-456", "waygate")
        assert ep == "http://10.0.0.1:8010/v1"
        mock_get_conn.assert_called_once_with("token-123", "proj-456")
        mock_conn.session.get_endpoint.assert_called_once_with(service_type="waygate", interface="internal")
        mock_conn.close.assert_called_once()


def test_get_internal_endpoint_prefers_trusted_configured_override():
    settings = SimpleNamespace(
        service_waygate_internal_url="",
        service_drover_internal_url="",
        service_lumen_internal_url="http://lumen-api:8012",
    )
    with patch("app.services.service_proxy.get_settings", return_value=settings):
        with patch("app.services.keystone.get_openstack_connection") as mock_get_conn:
            endpoint = _get_internal_endpoint("token-123", "proj-456", "lumen")

    assert endpoint == "http://lumen-api:8012"
    mock_get_conn.assert_not_called()


def test_get_service_internal_endpoint_prefers_trusted_configured_override():
    settings = SimpleNamespace(
        service_waygate_internal_url="http://waygate-api:8010",
        service_drover_internal_url="",
        service_lumen_internal_url="",
    )
    with patch("app.services.service_proxy.get_settings", return_value=settings):
        with patch("app.services.keystone.get_admin_project_connection") as mock_get_conn:
            endpoint = _get_service_internal_endpoint("waygate")

    assert endpoint == "http://waygate-api:8010"
    mock_get_conn.assert_not_called()


def test_get_internal_endpoint_lumen_override_precedence_and_catalog_fallback():
    # 1. Non-empty Lumen override skips catalog lookup and returns override directly
    override_settings = SimpleNamespace(
        service_waygate_internal_url="",
        service_drover_internal_url="",
        service_lumen_internal_url="http://lumen-api:8012",
        service_palimpsest_internal_url="",
    )
    with patch("app.services.service_proxy.get_settings", return_value=override_settings):
        with patch("app.services.keystone.get_openstack_connection") as mock_get_conn:
            endpoint = _get_internal_endpoint("token-123", "proj-456", "lumen")
            assert endpoint == "http://lumen-api:8012"
            mock_get_conn.assert_not_called()

    # 2. Empty Lumen override falls through to the caller-scoped Keystone internal catalog
    empty_settings = SimpleNamespace(
        service_waygate_internal_url="",
        service_drover_internal_url="",
        service_lumen_internal_url="",
        service_palimpsest_internal_url="",
    )
    mock_conn = MagicMock()
    mock_conn.session.get_endpoint.return_value = "http://10.0.0.12:8012/"
    with patch("app.services.service_proxy.get_settings", return_value=empty_settings):
        with patch("app.services.keystone.get_openstack_connection", return_value=mock_conn) as mock_get_conn:
            endpoint = _get_internal_endpoint("token-123", "proj-456", "lumen")
            assert endpoint == "http://10.0.0.12:8012"
            mock_get_conn.assert_called_once_with("token-123", "proj-456")
            mock_conn.session.get_endpoint.assert_called_once_with(service_type="lumen", interface="internal")
            mock_conn.close.assert_called_once()


def test_get_internal_endpoint_none_and_exception_closes_conn():
    mock_conn = MagicMock()
    mock_conn.session.get_endpoint.side_effect = Exception("Catalog lookup failed")
    with patch("app.services.keystone.get_openstack_connection", return_value=mock_conn):
        ep = _get_internal_endpoint("token-123", "proj-456", "drover")
        assert ep is None
        mock_conn.close.assert_called_once()


def test_get_service_internal_endpoint_uses_service_account_catalog():
    mock_conn = MagicMock()
    mock_conn.session.get_endpoint.return_value = "http://10.0.0.2:8010/"
    with patch("app.services.keystone.get_admin_project_connection", return_value=mock_conn) as mock_get_conn:
        endpoint = _get_service_internal_endpoint("waygate")

    assert endpoint == "http://10.0.0.2:8010"
    mock_get_conn.assert_called_once_with()
    mock_conn.session.get_endpoint.assert_called_once_with(service_type="waygate", interface="internal")
    mock_conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_proxy_forwarding():
    req = _make_request(
        method="POST",
        path="/api/v1/waygate/servers",
        query_string="filter=active&sort=asc",
        headers={
            "Content-Type": "application/json",
            "Cookie": "session_id=abc123",
            "Idempotency-Key": "ik-888",
            "Last-Event-ID": "evt-999",
            "X-Project-Id": "attacker-project",
            "X-Target-Project-Id": "attacker-target",
        },
        body=b'{"name": "gateway-1"}',
        token_info={"token": "ks-token-secret", "project_id": "proj-uuid-1"},
    )

    upstream_response = httpx.Response(
        201,
        stream=httpx.ByteStream(b'{"id": "srv-1", "status": "ACTIVE"}'),
        headers={"Content-Type": "application/json"},
    )

    with patch("app.services.service_proxy._get_internal_endpoint", return_value="http://waygate.internal:8010"):
        with patch.object(httpx.AsyncClient, "send", return_value=upstream_response) as mock_send:
            resp = await proxy("waygate", req, "/v1/servers")
            assert resp.status_code == 201

            body_chunks = [chunk async for chunk in resp.body_iterator]
            body_bytes = b"".join(body_chunks)
            assert json.loads(body_bytes) == {"id": "srv-1", "status": "ACTIVE"}

            sent_req = mock_send.call_args[0][0]
            assert sent_req.method == "POST"
            assert str(sent_req.url) == "http://waygate.internal:8010/v1/servers?filter=active&sort=asc"
            assert sent_req.headers.get("x-auth-token") == "ks-token-secret"
            assert sent_req.headers.get("x-project-id") == "proj-uuid-1"
            assert sent_req.headers.get("cookie") is None
            assert sent_req.headers.get("x-target-project-id") is None
            assert sent_req.headers.get("idempotency-key") == "ik-888"
            assert sent_req.headers.get("last-event-id") == "evt-999"


@pytest.mark.asyncio
async def test_lumen_proxy_separates_connection_and_logical_projects():
    req = _make_request(
        path="/api/v1/chat/models",
        headers={"X-Target-Project-Id": "attacker-target"},
        token_info={
            "token": "home-scoped-token",
            "project_id": "logical-project",
            "connection_project_id": "home-project",
        },
    )
    upstream_response = httpx.Response(200, json=[])

    with patch(
        "app.services.service_proxy._get_internal_endpoint",
        return_value="http://lumen.internal:8012",
    ) as mock_endpoint:
        with patch.object(httpx.AsyncClient, "send", return_value=upstream_response) as mock_send:
            response = await proxy("lumen", req, "/v1/chat/models")

    assert response.status_code == 200
    mock_endpoint.assert_called_once_with("home-scoped-token", "home-project", "lumen")
    sent_request = mock_send.call_args.args[0]
    assert sent_request.headers["x-auth-token"] == "home-scoped-token"
    assert sent_request.headers["x-project-id"] == "home-project"
    assert sent_request.headers["x-target-project-id"] == "logical-project"


@pytest.mark.asyncio
async def test_non_lumen_proxy_preserves_logical_project_contract():
    req = _make_request(
        token_info={
            "token": "home-scoped-token",
            "project_id": "logical-project",
            "connection_project_id": "home-project",
        },
    )
    upstream_response = httpx.Response(200, json={})

    with patch(
        "app.services.service_proxy._get_internal_endpoint",
        return_value="http://waygate.internal:8010",
    ) as mock_endpoint:
        with patch.object(httpx.AsyncClient, "send", return_value=upstream_response) as mock_send:
            response = await proxy("waygate", req, "/v1/servers")

    assert response.status_code == 200
    mock_endpoint.assert_called_once_with("home-scoped-token", "logical-project", "waygate")
    sent_request = mock_send.call_args.args[0]
    assert sent_request.headers["x-project-id"] == "logical-project"
    assert sent_request.headers.get("x-target-project-id") is None


@pytest.mark.asyncio
async def test_proxy_rejects_unvalidated_auth_headers():
    req = _make_request(
        headers={
            "X-Auth-Token": "unvalidated-token",
            "X-Project-Id": "unvalidated-project",
        },
    )

    with patch("app.services.service_proxy._get_internal_endpoint") as mock_endpoint:
        with pytest.raises(HTTPException) as exc_info:
            await proxy("waygate", req, "/v1/servers")

    assert exc_info.value.status_code == 401
    mock_endpoint.assert_not_called()


@pytest.mark.asyncio
async def test_get_json_uses_caller_catalog_and_keystone_headers():
    req = _make_request(
        path="/api/v1/admin/resource-policies",
        headers={"X-Project-Id": "attacker-project"},
        token_info={"token": "ks-token-secret", "project_id": "proj-uuid-1"},
    )
    upstream_response = httpx.Response(200, json=[{"key": "waygate.image"}])

    with patch("app.services.service_proxy._get_internal_endpoint", return_value="http://waygate.internal:8010"):
        with patch.object(httpx.AsyncClient, "get", return_value=upstream_response) as mock_get:
            result = await get_json("waygate", req, "/v1/admin/resource-policies")

    assert result == [{"key": "waygate.image"}]
    url = mock_get.await_args.args[0]
    headers = mock_get.await_args.kwargs["headers"]
    assert url == "http://waygate.internal:8010/v1/admin/resource-policies"
    assert headers["x-auth-token"] == "ks-token-secret"
    assert headers["x-project-id"] == "proj-uuid-1"


@pytest.mark.asyncio
async def test_lumen_get_json_separates_connection_and_logical_projects():
    req = _make_request(
        path="/api/v1/chat/usage",
        token_info={
            "token": "home-scoped-token",
            "project_id": "logical-project",
            "connection_project_id": "home-project",
        },
    )
    upstream_response = httpx.Response(200, json={"balance": 0})

    with patch(
        "app.services.service_proxy._get_internal_endpoint",
        return_value="http://lumen.internal:8012",
    ) as mock_endpoint:
        with patch.object(httpx.AsyncClient, "get", return_value=upstream_response) as mock_get:
            result = await get_json("lumen", req, "/v1/usage")

    assert result == {"balance": 0}
    mock_endpoint.assert_called_once_with("home-scoped-token", "home-project", "lumen")
    headers = mock_get.await_args.kwargs["headers"]
    assert headers["x-project-id"] == "home-project"
    assert headers["x-target-project-id"] == "logical-project"


async def test_proxy_same_project_unchanged_behavior():
    """Verify same-project requests pass connection_project_id as X-Project-Id with no X-Target-Project-Id header."""
    req = _make_request(
        token_info={
            "token": "ks-token-home",
            "project_id": "proj-home-123",
            "connection_project_id": "proj-home-123",
        },
    )
    upstream_response = httpx.Response(200, json={"status": "ok"})

    with patch(
        "app.services.service_proxy._get_internal_endpoint", return_value="http://lumen.internal:8000"
    ) as mock_ep:
        with patch.object(httpx.AsyncClient, "send", return_value=upstream_response) as mock_send:
            resp = await proxy("lumen", req, "/v1/chat/completions")
            assert resp.status_code == 200
            mock_ep.assert_called_once_with("ks-token-home", "proj-home-123", "lumen")
            sent_req = mock_send.call_args[0][0]
            assert sent_req.headers.get("x-auth-token") == "ks-token-home"
            assert sent_req.headers.get("x-project-id") == "proj-home-123"
            assert sent_req.headers.get("x-target-project-id") is None

    with patch(
        "app.services.service_proxy._get_internal_endpoint", return_value="http://lumen.internal:8000"
    ) as mock_ep:
        with patch.object(httpx.AsyncClient, "get", return_value=upstream_response) as mock_get:
            res = await get_json("lumen", req, "/v1/models")
            assert res == {"status": "ok"}
            mock_ep.assert_called_once_with("ks-token-home", "proj-home-123", "lumen")
            headers = mock_get.call_args[1]["headers"]
            assert headers.get("x-auth-token") == "ks-token-home"
            assert headers.get("x-project-id") == "proj-home-123"
            assert headers.get("x-target-project-id") is None


@pytest.mark.asyncio
async def test_proxy_foreign_system_admin_header_split():
    """System admin requesting foreign logical project sends connection project as X-Project-Id and target as X-Target-Project-Id."""
    req = _make_request(
        token_info={
            "token": "admin-ks-token",
            "project_id": "target-tenant-789",
            "connection_project_id": "admin-home-456",
            "is_system_admin": True,
        },
    )
    upstream_response = httpx.Response(200, json={"status": "ok"})

    with patch(
        "app.services.service_proxy._get_internal_endpoint", return_value="http://lumen.internal:8000"
    ) as mock_ep:
        with patch.object(httpx.AsyncClient, "send", return_value=upstream_response) as mock_send:
            resp = await proxy("lumen", req, "/v1/chat/completions")
            assert resp.status_code == 200
            mock_ep.assert_called_once_with("admin-ks-token", "admin-home-456", "lumen")
            sent_req = mock_send.call_args[0][0]
            assert sent_req.headers.get("x-auth-token") == "admin-ks-token"
            assert sent_req.headers.get("x-project-id") == "admin-home-456"
            assert sent_req.headers.get("x-target-project-id") == "target-tenant-789"

    with patch(
        "app.services.service_proxy._get_internal_endpoint", return_value="http://lumen.internal:8000"
    ) as mock_ep:
        with patch.object(httpx.AsyncClient, "get", return_value=upstream_response) as mock_get:
            res = await get_json("lumen", req, "/v1/models")
            assert res == {"status": "ok"}
            mock_ep.assert_called_once_with("admin-ks-token", "admin-home-456", "lumen")
            headers = mock_get.call_args[1]["headers"]
            assert headers.get("x-auth-token") == "admin-ks-token"
            assert headers.get("x-project-id") == "admin-home-456"
            assert headers.get("x-target-project-id") == "target-tenant-789"


@pytest.mark.asyncio
async def test_proxy_drops_browser_supplied_target_headers():
    """Malicious browser-supplied X-Target / X-Target-Project-Id / X-Project-Id headers are ignored and never forwarded."""
    from app.services.service_proxy import FORWARDED_REQUEST_HEADERS

    lowered_forwarded = {h.lower() for h in FORWARDED_REQUEST_HEADERS}
    assert "x-target-project-id" not in lowered_forwarded
    assert "x-target" not in lowered_forwarded
    assert "x-project-id" not in lowered_forwarded

    req = _make_request(
        headers={
            "X-Target-Project-Id": "attacker-target-proj",
            "X-Target": "attacker-target",
            "X-Project-Id": "attacker-proj",
            "X-Auth-Token": "attacker-token",
        },
        token_info={
            "token": "legit-ks-token",
            "project_id": "home-proj",
            "connection_project_id": "home-proj",
        },
    )
    upstream_response = httpx.Response(200, json={"ok": True})

    with patch("app.services.service_proxy._get_internal_endpoint", return_value="http://service.internal:8000"):
        with patch.object(httpx.AsyncClient, "send", return_value=upstream_response) as mock_send:
            await proxy("waygate", req, "/v1/servers")
            sent_req = mock_send.call_args[0][0]
            assert sent_req.headers.get("x-auth-token") == "legit-ks-token"
            assert sent_req.headers.get("x-project-id") == "home-proj"
            assert sent_req.headers.get("x-target-project-id") is None
            assert "x-target" not in sent_req.headers


@pytest.mark.asyncio
async def test_machine_proxy_forwards_authorization_without_keystone_interpretation():
    req = _make_request(
        method="POST",
        path="/api/v1/waygate/servers/server-1/agent/status",
        headers={
            "Authorization": "Bearer durable-agent-token",
            "Content-Type": "application/json",
            "Cookie": "session_id=secret",
            "X-Project-Id": "attacker-project",
        },
        body=b'{"peers": []}',
    )
    upstream_response = httpx.Response(204)

    with patch(
        "app.services.service_proxy._get_service_internal_endpoint",
        return_value="http://waygate.internal:8010",
    ):
        with patch.object(httpx.AsyncClient, "send", return_value=upstream_response) as mock_send:
            response = await proxy_passthrough(
                "waygate",
                req,
                "/v1/servers/server-1/agent/status",
            )

    assert response.status_code == 204
    sent_request = mock_send.call_args[0][0]
    assert sent_request.headers["authorization"] == "Bearer durable-agent-token"
    assert sent_request.headers.get("x-auth-token") is None
    assert sent_request.headers["x-forwarded-for"] == "203.0.113.10"
    assert sent_request.headers.get("cookie") is None
    assert sent_request.headers.get("x-project-id") is None


@pytest.mark.asyncio
async def test_proxy_streaming_response():
    req = _make_request(
        method="GET",
        path="/api/v1/chat/runs/run-1/events",
        token_info={"token": "ks-token-secret", "project_id": "proj-uuid-1"},
    )

    sse_data = b"event: message\ndata: hello\n\nevent: done\ndata: ok\n\n"
    upstream_response = httpx.Response(
        200,
        stream=httpx.ByteStream(sse_data),
        headers={"Content-Type": "text/event-stream"},
    )

    with patch("app.services.service_proxy._get_internal_endpoint", return_value="http://lumen.internal:8012"):
        with patch.object(httpx.AsyncClient, "send", return_value=upstream_response):
            resp = await proxy("lumen", req, "/v1/runs/run-1/events")
            assert resp.status_code == 200

            body_chunks = [chunk async for chunk in resp.body_iterator]
            body_bytes = b"".join(body_chunks)
            assert body_bytes == sse_data
            assert dict(resp.raw_headers).get(b"content-type") == b"text/event-stream"


@pytest.mark.asyncio
async def test_proxy_upstream_error_verbatim():
    req = _make_request(
        method="DELETE",
        path="/api/v1/drover/clusters/c1",
        token_info={"token": "ks-token-secret", "project_id": "proj-uuid-1"},
        body=b'{"force": true}',
    )

    upstream_response = httpx.Response(
        404,
        stream=httpx.ByteStream(b'{"detail": "Cluster not found"}'),
        headers={"Content-Type": "application/json"},
    )

    with patch("app.services.service_proxy._get_internal_endpoint", return_value="http://drover.internal:8011"):
        with patch.object(httpx.AsyncClient, "send", return_value=upstream_response) as mock_send:
            resp = await proxy("drover", req, "/v1/clusters/c1")
            assert resp.status_code == 404

            body_chunks = [chunk async for chunk in resp.body_iterator]
            body_bytes = b"".join(body_chunks)
            assert json.loads(body_bytes) == {"detail": "Cluster not found"}
    sent_request = mock_send.call_args.args[0]
    sent_body = b"".join([chunk async for chunk in sent_request.stream])
    assert sent_body == b'{"force": true}'


@pytest.mark.asyncio
async def test_proxy_missing_endpoint_503():
    req = _make_request(
        method="GET",
        path="/api/v1/waygate/servers",
        token_info={"token": "ks-token-secret", "project_id": "proj-uuid-1"},
    )

    with patch("app.services.service_proxy._get_internal_endpoint", return_value=None):
        resp = await proxy("waygate", req, "/v1/servers")
        assert resp.status_code == 503
        assert json.loads(resp.body.decode()) == {"detail": "waygate 서비스를 사용할 수 없습니다"}


@pytest.mark.asyncio
async def test_proxy_upstream_connection_failure_503():
    req = _make_request(
        method="GET",
        path="/api/v1/drover/clusters",
        token_info={"token": "ks-token-secret", "project_id": "proj-uuid-1"},
    )

    with patch("app.services.service_proxy._get_internal_endpoint", return_value="http://drover.internal:8011"):
        with patch.object(httpx.AsyncClient, "send", side_effect=httpx.ConnectError("Connection refused")):
            resp = await proxy("drover", req, "/v1/clusters")
            assert resp.status_code == 503
            assert json.loads(resp.body.decode()) == {"detail": "drover 서비스를 사용할 수 없습니다"}


def test_join_version_aware_url_variants():
    from app.services.service_proxy import _append_query, join_version_aware_url

    assert (
        join_version_aware_url("https://drover.local/v1", "/v1/admin/clusters")
        == "https://drover.local/v1/admin/clusters"
    )
    assert (
        join_version_aware_url("https://drover.local/v1/", "/v1/admin/clusters")
        == "https://drover.local/v1/admin/clusters"
    )
    assert (
        join_version_aware_url("https://drover.local/api/v2.1/project", "/v1/admin/clusters")
        == "https://drover.local/api/v2.1/project/admin/clusters"
    )
    assert (
        join_version_aware_url("https://drover.local", "/v1/admin/clusters") == "https://drover.local/v1/admin/clusters"
    )
    assert join_version_aware_url("http://10.0.0.1:9517", "/v1/containers") == "http://10.0.0.1:9517/v1/containers"
    assert (
        join_version_aware_url(
            "https://zun.local:9517/v1",
            "/v1/containers/c1/logs?stdout=true&stderr=true#top",
        )
        == "https://zun.local:9517/v1/containers/c1/logs?stdout=true&stderr=true#top"
    )
    assert (
        _append_query(
            "https://drover.local/v1/clusters?source=cache#section",
            "refresh=true",
        )
        == "https://drover.local/v1/clusters?source=cache&refresh=true#section"
    )

    with pytest.raises(ValueError, match="must be relative"):
        join_version_aware_url("http://zun.local", "https://evil.example/v1/containers")
    with pytest.raises(ValueError, match="must be relative"):
        join_version_aware_url("http://zun.local", "//evil.example/v1/containers")
    with pytest.raises(ValueError, match="cannot contain"):
        join_version_aware_url("http://zun.local/v1?foo=bar", "/v1/containers")
    with pytest.raises(ValueError, match="cannot contain"):
        join_version_aware_url("http://zun.local/v1#section", "/v1/containers")
