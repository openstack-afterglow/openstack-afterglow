"""Tests for the Palimpsest Hub BFF proxy router and service_proxy integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info
from app.main import app
from app.services.service_proxy import proxy


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


@pytest.mark.asyncio
async def test_palimpsest_hub_disabled_by_default(api_client, monkeypatch):
    """When service_palimpsest_enabled is False (default), router returns 503."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "service_palimpsest_enabled", False)

    response = await api_client.get("/api/v1/palimpsest/hub/layers")
    assert response.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,upstream_path,body",
    [
        ("get", "/api/v1/palimpsest/hub/layers", "/v1/layers", None),
        (
            "post",
            "/api/v1/palimpsest/hub/image-exports",
            "/v1/image-exports",
            {"image_id": "img-1", "disk_format": "qcow2"},
        ),
        ("delete", "/api/v1/palimpsest/hub/image-exports/export-1", "/v1/image-exports/export-1", None),
    ],
)
async def test_palimpsest_hub_proxy_routing(api_client, monkeypatch, method, path, upstream_path, body):
    """Authenticated Hub endpoints delegate to app.api.palimpsest.hub.proxy."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "service_palimpsest_enabled", True)
    app.dependency_overrides[get_token_info] = _authenticated

    forwarded = JSONResponse(status_code=207, content={"forwarded": True})
    with patch("app.api.palimpsest.hub.proxy", new=AsyncMock(return_value=forwarded)) as proxy_call:
        call = getattr(api_client, method)
        response = await (call(path, json=body) if body is not None else call(path))

    assert response.status_code == 207
    assert response.json() == {"forwarded": True}
    service_type, request, upstream = proxy_call.await_args.args
    assert service_type == "palimpsest"
    assert upstream == upstream_path
    assert request.state.token_info["token"] == "caller-token"


@pytest.mark.asyncio
async def test_palimpsest_hub_proxy_requires_auth(api_client, monkeypatch):
    """Protected Hub endpoints return 401 without auth when enabled."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "service_palimpsest_enabled", True)

    with patch("app.api.palimpsest.hub.proxy", new=AsyncMock()) as proxy_call:
        response = await api_client.get("/api/v1/palimpsest/hub/layers")

    assert response.status_code == 401
    proxy_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_palimpsest_token_download_unauthenticated(api_client, monkeypatch):
    """Image export download endpoint bypasses token_info and calls proxy_unauthenticated."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "service_palimpsest_enabled", True)

    forwarded = JSONResponse(status_code=200, content={"download": True})
    with patch("app.api.palimpsest.hub.proxy_unauthenticated", new=AsyncMock(return_value=forwarded)) as proxy_call:
        response = await api_client.get(
            "/api/v1/palimpsest/hub/image-exports/export-123/download?dl_token=some_token_32_chars_or_longer_token"
        )

    assert response.status_code == 200
    assert response.json() == {"download": True}
    service_type, request, upstream = proxy_call.await_args.args
    assert service_type == "palimpsest"
    assert upstream == "/v1/image-exports/export-123/download"


@pytest.mark.asyncio
async def test_service_proxy_unavailable_503():
    """When endpoint cannot be resolved, proxy returns 503."""
    req = MagicMock(spec=Request)
    req.method = "GET"
    req.url = MagicMock()
    req.url.query = ""
    req.state.token_info = {"token": "t1", "project_id": "p1"}

    with patch("app.services.service_proxy._get_internal_endpoint", return_value=None):
        resp = await proxy("palimpsest", req, "/v1/layers")

    assert resp.status_code == 503
    assert b"palimpsest" in resp.body


@pytest.mark.asyncio
async def test_service_proxy_range_and_headers_forwarding():
    """service_proxy forwards range/resume headers and streams both directions."""
    req = MagicMock(spec=Request)
    req.method = "PATCH"
    req.url = MagicMock()
    req.url.query = "dl_token=test"
    req.headers = {
        "range": "bytes=0-1023",
        "upload-offset": "1024",
        "upload-length": "2048",
        "upload-metadata": "filename bGF5ZXIuc3FzaA==",
        "tus-resumable": "1.0.0",
        "upload-checksum": "sha256 ZGlnZXN0",
        "content-length": "6",
    }
    req.state.token_info = {"token": "t1", "project_id": "p1"}

    async def fake_stream():
        yield b"upload"

    request_stream = fake_stream()
    req.stream = MagicMock(return_value=request_stream)

    mock_response = AsyncMock()
    mock_response.status_code = 206
    mock_response.headers.multi_items = MagicMock(
        return_value=[
            ("content-type", "application/octet-stream"),
            ("content-range", "bytes 0-1023/2048"),
        ]
    )

    async def fake_aiter():
        yield b"chunk1"
        yield b"chunk2"

    mock_response.aiter_raw = fake_aiter
    mock_response.aclose = AsyncMock()

    mock_client = MagicMock()
    mock_client.build_request.return_value = "outgoing-req"
    mock_client.send = AsyncMock(return_value=mock_response)
    mock_client.aclose = AsyncMock()

    with patch("app.services.service_proxy._get_internal_endpoint", return_value="http://palimpsest-hub:8013"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = await proxy("palimpsest", req, "/v1/uploads/session-1")

    assert resp.status_code == 206
    body_chunks = [chunk async for chunk in resp.body_iterator]
    assert b"".join(body_chunks) == b"chunk1chunk2"

    call_kwargs = mock_client.build_request.call_args.kwargs
    assert call_kwargs["url"] == "http://palimpsest-hub:8013/v1/uploads/session-1?dl_token=test"
    assert call_kwargs["headers"]["range"] == "bytes=0-1023"
    assert call_kwargs["headers"]["upload-offset"] == "1024"
    assert call_kwargs["headers"]["content-length"] == "6"
    assert call_kwargs["headers"]["upload-length"] == "2048"
    assert call_kwargs["headers"]["upload-metadata"] == "filename bGF5ZXIuc3FzaA=="
    assert call_kwargs["headers"]["tus-resumable"] == "1.0.0"
    assert call_kwargs["headers"]["upload-checksum"] == "sha256 ZGlnZXN0"
    assert call_kwargs["content"] is request_stream
    req.body.assert_not_called()
