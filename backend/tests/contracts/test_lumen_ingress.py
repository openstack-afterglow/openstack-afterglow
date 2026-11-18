"""Exercise the browser-to-Lumen wire boundary with synthetic credentials only."""

import hashlib
import hmac
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from pydantic import SecretStr, ValidationError

from app import config
from app.api.deps import get_token_info
from app.api.lumen import proxy as lumen_proxy
from app.services import lumen_ingress, service_proxy
from app.utils.log import mask_dict, mask_str

KEY = bytes(range(65, 97))
STAMP = 1781234567
NATIVE_TOKEN = "fixture-keystone-token"
INGRESS_ENV = "SERVICE_LUMEN_INGRESS_SECRET"


def test_signer_known_vector_preserves_percent_encoding_and_all_authority_fields():
    marker = lumen_ingress.sign_lumen_ingress(
        KEY,
        timestamp=STAMP,
        method="patch",
        path=b"/edge/v1/vault/notes/%31",
        token=NATIVE_TOKEN,
        project="connection-project",
        target_project="target-project",
    )
    assert marker == f"v1:{STAMP}:71378ecd2c3525ff2aee85514f5925dc8f47394b1545b38717cf8dd7725707fc"


@pytest.mark.parametrize("source", ["toml", "environment", "compose-empty-environment"])
def test_ingress_secret_source_and_trusted_settings_representation(monkeypatch, source):
    monkeypatch.setattr(config.os, "environ", dict(config.os.environ))
    monkeypatch.delenv(INGRESS_ENV, raising=False)
    toml_value = KEY.decode() if source != "environment" else ""
    monkeypatch.setattr(config, "load_raw_toml", lambda: {"services": {"lumen_ingress_secret": toml_value}})
    if source != "toml":
        monkeypatch.setenv(INGRESS_ENV, KEY.decode() if source == "environment" else "")

    settings = config.get_settings.__wrapped__()
    assert settings.service_lumen_ingress_secret.get_secret_value() == KEY.decode()
    assert "service_lumen_ingress_secret" not in settings.model_dump()
    assert KEY.decode() not in repr(settings)
    assert KEY.decode() not in settings.model_dump_json()


def test_ingress_secret_uses_utf8_byte_count_and_hides_validation_input(caplog):
    assert config.Settings(service_lumen_ingress_secret="ø" * 16).service_lumen_ingress_secret.get_secret_value()
    with pytest.raises(ValidationError, match="at least 32 UTF-8 bytes") as exc:
        config.Settings(service_lumen_ingress_secret="private-short-test-value")
    assert "private-short-test-value" not in str(exc.value)
    assert "private-short-test-value" not in caplog.text
    assert mask_dict({"X-Lumen-Ingress": "synthetic-proof"}) == {"X-Lumen-Ingress": "***"}
    assert "synthetic-proof" not in mask_str("X-Lumen-Ingress: synthetic-proof")


def assert_signed_request(request):
    # Construct the signed bytes only from the mock upstream's observation.
    raw_path = request.url.raw_path.split(b"?", 1)[0]
    headers = request.headers
    message = b"\n".join(
        (
            b"v1",
            str(STAMP).encode(),
            request.method.encode(),
            raw_path,
            hashlib.sha256(headers["x-auth-token"].encode()).hexdigest().encode(),
            headers.get("x-project-id", "").encode(),
            headers.get("x-target-project-id", "").encode(),
        )
    )
    signature = hmac.new(KEY, message, hashlib.sha256).hexdigest()
    assert headers.get_list("X-Lumen-Ingress") == [f"v1:{STAMP}:{signature}"]


@pytest.fixture
def signed_settings(monkeypatch):
    settings = config.get_settings().model_copy(update={"service_lumen_ingress_secret": SecretStr(KEY.decode())})
    monkeypatch.setattr(service_proxy, "get_settings", lambda: settings)
    monkeypatch.setattr(lumen_ingress.time, "time", lambda: STAMP)
    monkeypatch.setattr(service_proxy, "_get_internal_endpoint", lambda *_: "https://lumen.invalid/deploy/v1")
    return settings


@pytest.mark.parametrize(
    ("method", "path", "connection_project", "enabled"),
    [
        ("GET", "vault/notes?workspace_id=4", "project-a", True),
        ("POST", "conversations/9/completions", "connection-project", True),
        ("GET", "vault/notes", "project-a", False),
    ],
)
async def test_proxy_uses_forwarded_native_headers_not_client_headers(
    monkeypatch, signed_settings, method, path, connection_project, enabled
):
    app = FastAPI()
    app.include_router(lumen_proxy.router, prefix="/api/v1/chat")

    async def session(request: Request):
        info = {
            "token": NATIVE_TOKEN,
            "user_id": "user",
            "project_id": "project-a",
            "connection_project_id": connection_project,
            "is_system_admin": connection_project != "project-a",
            "_live_system_admin": True,
        }
        request.state.token_info = info
        return info

    app.dependency_overrides[get_token_info] = session
    monkeypatch.setattr(
        "app.services.project_service.get_project_access", AsyncMock(return_value={"roles": ["member"]})
    )
    monkeypatch.setattr(
        lumen_proxy, "get_policy_capabilities", AsyncMock(return_value={"capabilities": ["lumen-history_reader"]})
    )
    if not enabled:
        signed_settings.service_lumen_ingress_secret = SecretStr("")
    seen = []

    async def upstream(request):
        seen.append(request)
        await request.aread()
        return httpx.Response(
            200, headers={"X-Lumen-Ingress": "never-echo-native-proof"}, stream=httpx.ByteStream(b"[]")
        )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        mock = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
        monkeypatch.setattr(service_proxy.httpx, "AsyncClient", lambda **_: mock)
        response = await client.request(
            method,
            f"/api/v1/chat/{path}",
            headers={
                "X-Lumen-Ingress": "never-forward-client-value",
                "X-Auth-Token": "client-token",
                "X-Project-Id": "client-project",
                "X-Target-Project-Id": "client-target",
            },
        )
    assert response.status_code == 200
    assert "X-Lumen-Ingress" not in response.headers
    [request] = seen
    assert request.url.raw_path == f"/deploy/v1/{path}".encode()
    assert request.headers["x-auth-token"] == NATIVE_TOKEN
    assert request.headers["x-project-id"] == connection_project
    assert request.headers.get("x-target-project-id") == ("project-a" if connection_project != "project-a" else None)
    if enabled:
        assert_signed_request(request)
    else:
        assert "X-Lumen-Ingress" not in request.headers


async def test_native_policy_request_uses_same_ingress_proof(monkeypatch, signed_settings):
    seen = []

    async def upstream(request):
        seen.append(request)
        return httpx.Response(200, json={"service": "lumen", "capabilities": [], "actions": []})

    mock = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    monkeypatch.setattr(service_proxy.httpx, "AsyncClient", lambda **_: mock)
    await service_proxy.get_policy_capabilities("lumen", {"project_id": "project-a", "token": NATIVE_TOKEN})
    [request] = seen
    assert request.url.raw_path == b"/deploy/v1/policy/capabilities"
    assert_signed_request(request)


async def test_json_transport_redacts_private_upstream_failure(monkeypatch, signed_settings, caplog):
    seen = []

    async def upstream(request):
        seen.append(request)
        raise httpx.ConnectError(f"upstream echoed {request.headers['X-Lumen-Ingress']}", request=request)

    mock = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    monkeypatch.setattr(service_proxy.httpx, "AsyncClient", lambda **_: mock)
    monkeypatch.setattr(
        "app.services.project_service.get_project_access", AsyncMock(return_value={"roles": ["member"]})
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/chat/vault/search",
            "headers": [],
            "query_string": b"query=private-note-search",
        }
    )
    request.state.token_info = {"project_id": "project-a", "token": NATIVE_TOKEN, "user_id": "user"}
    with pytest.raises(HTTPException) as error:
        await service_proxy.get_json("lumen", request, "/v1/vault/search")
    assert error.value.status_code == 503
    [outgoing] = seen
    assert_signed_request(outgoing)
    assert outgoing.headers["X-Lumen-Ingress"] not in caplog.text
    assert "private-note-search" not in caplog.text
