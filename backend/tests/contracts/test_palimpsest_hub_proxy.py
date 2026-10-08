"""Palimpsest BFF contracts with real proxy gates and in-memory HTTP transports.

Only validated identity, current directory access and native Hub/provider responses
are synthetic; Request parsing, httpx streaming and authorization run unchanged.
"""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException, Request
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app
from app.services.service_proxy import proxy

BASE = "/api/v1/palimpsest/hub"
SESSION = "44444444444444448444444444444444"
DIGEST = "sha256:" + "a" * 64


@pytest.fixture
async def api_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", trust_env=False) as client:
        yield client


@pytest.fixture
def validated_identity():
    return {"token": "caller-token", "project_id": "caller-project", "user_id": "caller-user"}


@pytest.fixture
def current_access(monkeypatch):
    """Substitute the directory boundary, never the service action classifier."""
    access = {"roles": ["member", "palimpsest-inventory_reader"]}
    monkeypatch.setattr("app.services.project_service.get_project_access", AsyncMock(return_value=access))
    return access


def _make_request(*, method="GET", path="/layers", headers=None, body_chunks=(), token_info=None):
    chunks = iter(body_chunks)

    async def receive():
        try:
            return {"type": "http.request", "body": next(chunks), "more_body": True}
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": method,
            "path": BASE + path,
            "query_string": b"",
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1")) for name, value in (headers or {}).items()
            ],
            "client": ("127.0.0.1", 12345),
        },
        receive,
    )
    if token_info is not None:
        request.state.token_info = token_info
    return request


class _UnreadStream(httpx.AsyncByteStream):
    def __init__(self, *chunks):
        self.chunks = chunks
        self.read_chunks = []
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.read_chunks.append(chunk)
            yield chunk

    async def aclose(self):
        self.closed = True


def _use_transport(monkeypatch, transport):
    client = AsyncClient(transport=transport, trust_env=False)
    monkeypatch.setattr("app.services.service_proxy.httpx.AsyncClient", lambda **_kwargs: client)
    monkeypatch.setattr("app.services.service_proxy._get_internal_endpoint", lambda *_args: "http://127.0.0.1:8013")
    return client


def _unexpected_catalog(*_args):
    pytest.fail("Denied request must not reach catalog discovery")


@pytest.mark.asyncio
async def test_palimpsest_hub_disabled_by_default(api_client, monkeypatch):
    """When service_palimpsest_enabled is False (default), router returns 503."""
    monkeypatch.setattr(get_settings(), "service_palimpsest_enabled", False)

    response = await api_client.get("/api/v1/palimpsest/hub/layers")
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_palimpsest_hub_proxy_requires_auth(api_client, monkeypatch):
    """Protected Hub endpoints return 401 without auth when enabled."""
    monkeypatch.setattr(get_settings(), "service_palimpsest_enabled", True)
    monkeypatch.setattr("app.services.service_proxy._get_internal_endpoint", _unexpected_catalog)

    response = await api_client.get(BASE + "/layers")

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ticket,status,body",
    [
        ("valid-ticket", 206, b"chunk1chunk2"),
        ("invalid-ticket", 401, b"invalid ticket"),
        ("expired-ticket", 410, b"expired ticket"),
    ],
)
async def test_palimpsest_token_download_native_authority(api_client, monkeypatch, ticket, status, body):
    """The native ticket result is preserved without importing browser authority."""
    monkeypatch.setattr(get_settings(), "service_palimpsest_enabled", True)
    monkeypatch.setattr(
        "app.services.service_proxy.resolve_service_endpoint",
        AsyncMock(return_value="http://127.0.0.1:8013"),
    )
    monkeypatch.setattr(
        "app.services.project_service.get_project_access",
        AsyncMock(side_effect=AssertionError("Tickets must not resolve browser membership")),
    )
    monkeypatch.setattr(
        "app.api.palimpsest.hub.get_token_info",
        AsyncMock(side_effect=AssertionError("Tickets must not validate browser credentials")),
    )
    stream = _UnreadStream(body[:6], body[6:])

    def upstream(request):
        assert request.url.path == f"/v1/image-exports/{SESSION}/download"
        assert request.url.params["dl_token"] == ticket
        assert request.headers["range"] == "bytes=0-11"
        for credential in ("authorization", "cookie", "x-auth-token", "x-project-id", "x-target-project-id"):
            assert credential not in request.headers
        headers = {"content-range": "bytes 0-11/24"} if status == 206 else {}
        return httpx.Response(status, stream=stream, headers=headers)

    client = _use_transport(monkeypatch, httpx.MockTransport(upstream))
    response = await api_client.get(
        f"{BASE}/image-exports/{SESSION}/download",
        params={"dl_token": ticket},
        headers={
            "Range": "bytes=0-11",
            "Authorization": "Bearer untrusted-browser",
            "Cookie": "session=untrusted",
            "X-Auth-Token": "forged-keystone",
            "X-Project-Id": "forged-project",
            "X-Target-Project-Id": "forged-target",
        },
    )

    assert response.status_code == status
    assert response.content == body
    if status == 206:
        assert response.headers["content-range"] == "bytes 0-11/24"
    assert stream.closed
    assert client.is_closed


@pytest.mark.asyncio
async def test_package_key_cannot_use_export_ticket(api_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "service_palimpsest_enabled", True)
    monkeypatch.setattr(
        "app.services.service_proxy.resolve_service_endpoint",
        AsyncMock(side_effect=AssertionError("Package key must not reach ticket transport")),
    )

    response = await api_client.get(
        f"{BASE}/image-exports/{SESSION}/download?dl_token=valid-ticket",
        headers={"Authorization": "Bearer ppk_v1_package-key"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACTION_DENIED"


@pytest.mark.asyncio
async def test_service_proxy_unavailable_503(monkeypatch, validated_identity, current_access):
    """An authorized caller sees 503 when trusted discovery has no endpoint."""
    request = _make_request(token_info=validated_identity)
    monkeypatch.setattr("app.services.service_proxy._get_internal_endpoint", lambda *_args: None)

    response = await proxy("palimpsest", request, "/v1/layers")

    assert response.status_code == 503
    assert b"palimpsest" in response.body


@pytest.mark.asyncio
async def test_service_proxy_range_download_stream(monkeypatch, validated_identity, current_access):
    current_access["roles"] = ["member", "palimpsest-download_user"]
    request = _make_request(
        path=f"/layers/{DIGEST}/blob",
        headers={
            "Range": "bytes=6-17",
            "Authorization": "Bearer browser-jwt",
            "Cookie": "session=private",
            "X-Auth-Token": "forged-token",
            "X-Project-Id": "forged-project",
            "X-Target-Project-Id": "forged-target",
        },
        token_info=validated_identity,
    )
    stream = _UnreadStream(b"chunk1", b"chunk2")

    def upstream(outgoing):
        assert outgoing.headers["range"] == "bytes=6-17"
        assert outgoing.headers["x-auth-token"] == validated_identity["token"]
        assert outgoing.headers["x-project-id"] == validated_identity["project_id"]
        for credential in ("authorization", "cookie", "x-target-project-id"):
            assert credential not in outgoing.headers
        return httpx.Response(
            206,
            stream=stream,
            headers={
                "content-type": "application/octet-stream",
                "content-range": "bytes 6-17/24",
                "content-length": "12",
                "connection": "keep-alive",
            },
        )

    client = _use_transport(monkeypatch, httpx.MockTransport(upstream))
    response = await proxy("palimpsest", request, f"/v1/layers/{DIGEST}/blob")

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 6-17/24"
    assert response.headers["content-type"] == "application/octet-stream"
    assert "content-length" not in response.headers
    assert "connection" not in response.headers
    assert stream.read_chunks == []
    assert not stream.closed
    assert not client.is_closed
    iterator = response.body_iterator
    assert await anext(iterator) == b"chunk1"
    assert stream.read_chunks == [b"chunk1"]
    assert await anext(iterator) == b"chunk2"
    with pytest.raises(StopAsyncIteration):
        await anext(iterator)
    assert stream.closed
    assert client.is_closed


@pytest.mark.asyncio
async def test_service_proxy_resumable_upload_stream(monkeypatch, validated_identity, current_access):
    current_access["roles"] = ["member", "palimpsest-publish_editor"]
    request = _make_request(
        method="PATCH",
        path=f"/uploads/{SESSION}",
        headers={
            "Upload-Offset": "1024",
            "Upload-Length": "2048",
            "Upload-Metadata": "filename bGF5ZXIuc3FzaA==",
            "Tus-Resumable": "1.0.0",
            "Upload-Checksum": "sha256 ZGlnZXN0",
            "Content-Length": "6",
        },
        body_chunks=(b"up", b"load"),
        token_info=validated_identity,
    )
    received = []
    stream = _UnreadStream()

    class UploadTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, outgoing):
            assert outgoing.url.path == f"/v1/uploads/{SESSION}"
            assert outgoing.method == "PATCH"
            assert outgoing.headers["upload-offset"] == "1024"
            assert outgoing.headers["content-length"] == "6"
            assert outgoing.headers["upload-length"] == "2048"
            assert outgoing.headers["upload-metadata"] == "filename bGF5ZXIuc3FzaA=="
            assert outgoing.headers["tus-resumable"] == "1.0.0"
            assert outgoing.headers["upload-checksum"] == "sha256 ZGlnZXN0"
            async for chunk in outgoing.stream:
                if chunk:
                    received.append(chunk)
            # Unlike MockTransport, this transport does not pre-buffer the
            # request; the native offset advances after consuming both chunks.
            assert received == [b"up", b"load"]
            return httpx.Response(204, stream=stream, headers={"upload-offset": "1030", "tus-resumable": "1.0.0"})

    client = _use_transport(monkeypatch, UploadTransport())
    response = await proxy("palimpsest", request, f"/v1/uploads/{SESSION}")

    assert response.status_code == 204
    assert response.headers["upload-offset"] == "1030"
    assert response.headers["tus-resumable"] == "1.0.0"
    assert not hasattr(request, "_body")
    assert [chunk async for chunk in response.body_iterator] == []
    assert stream.closed
    assert client.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing-identity", "current-downgrade", "provider-outage"])
async def test_browser_authority_fails_closed_before_discovery(
    monkeypatch, validated_identity, current_access, failure
):
    validated_identity["roles"] = ["member", "palimpsest-inventory_reader"]
    expected = 403
    if failure == "missing-identity":
        validated_identity.pop("user_id")
        expected = 401
    elif failure == "current-downgrade":
        current_access["roles"] = ["member"]
    else:
        monkeypatch.setattr(
            "app.services.project_service.get_project_access",
            AsyncMock(side_effect=HTTPException(503, "Current access unavailable")),
        )
        expected = 503
    monkeypatch.setattr("app.services.service_proxy._get_internal_endpoint", _unexpected_catalog)
    request = _make_request(token_info=validated_identity)

    with pytest.raises(HTTPException) as failure:
        await proxy("palimpsest", request, "/v1/layers")

    assert failure.value.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("protected", ["admin", "manager", "service", "system-admin"])
async def test_protected_identities_cannot_publish(monkeypatch, validated_identity, current_access, protected):
    current_access["roles"] = ["member", "palimpsest-publish_editor"]
    if protected == "system-admin":
        validated_identity["is_system_admin"] = True
    else:
        current_access["roles"].append(protected)
    monkeypatch.setattr("app.services.service_proxy._get_internal_endpoint", _unexpected_catalog)
    request = _make_request(method="PATCH", path=f"/uploads/{SESSION}", token_info=validated_identity)

    with pytest.raises(HTTPException) as failure:
        await proxy("palimpsest", request, f"/v1/uploads/{SESSION}")

    assert failure.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["projects/current", "projects/owner-namespace/keys"])
async def test_native_owner_routes_reject_ordinary_browser_credentials(api_client, monkeypatch, path):
    monkeypatch.setattr(get_settings(), "service_palimpsest_enabled", True)
    monkeypatch.setattr("app.services.service_proxy._get_internal_endpoint", _unexpected_catalog)

    response = await api_client.get(BASE + "/" + path, headers={"Authorization": "Bearer browser-jwt"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACTION_DENIED"


@pytest.mark.asyncio
async def test_native_upstream_failure_returns_unavailable(monkeypatch, validated_identity, current_access):
    def unavailable(outgoing):
        raise httpx.ConnectError("native Hub unavailable", request=outgoing)

    client = _use_transport(monkeypatch, httpx.MockTransport(unavailable))
    response = await proxy("palimpsest", _make_request(token_info=validated_identity), "/v1/layers")

    assert response.status_code == 503
    assert b"palimpsest" in response.body
    assert client.is_closed
