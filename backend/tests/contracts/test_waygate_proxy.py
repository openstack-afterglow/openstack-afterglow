"""Afterglow browser proxy contract for the extracted Waygate service."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info
from app.main import app


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
@pytest.mark.parametrize(
    "method,path,upstream_path,body",
    [
        ("get", "/api/v1/waygate/servers", "/v1/servers", None),
        ("post", "/api/v1/waygate/servers", "/v1/servers", {"name": "gateway"}),
        (
            "patch",
            "/api/v1/waygate/servers/server-1/clients/client-1",
            "/v1/servers/server-1/clients/client-1",
            {"enabled": False},
        ),
        ("delete", "/api/v1/waygate/servers/server-1", "/v1/servers/server-1", None),
        (
            "post",
            "/api/v1/waygate/servers/server-1/networks",
            "/v1/servers/server-1/networks",
            {"network_id": "network-1", "subnet_id": "subnet-1", "nat_mode": "snat"},
        ),
        (
            "get",
            "/api/v1/waygate/servers/server-1/networks",
            "/v1/servers/server-1/networks",
            None,
        ),
        (
            "delete",
            "/api/v1/waygate/servers/server-1/networks/7",
            "/v1/servers/server-1/networks/7",
            None,
        ),
    ],
)
async def test_browser_routes_proxy_to_catalog_service(api_client, method, path, upstream_path, body):
    app.dependency_overrides[get_token_info] = _authenticated
    forwarded = JSONResponse(status_code=207, content={"forwarded": True})
    observed: dict[str, object] = {}

    async def capture_request(service_type: str, request: Request, upstream: str):
        observed["service_type"] = service_type
        observed["upstream"] = upstream
        observed["authorization"] = request.headers.get("authorization")
        observed["project_header"] = request.headers.get("x-project-id")
        observed["token_info"] = request.state.token_info
        observed["body"] = await request.json() if body is not None else None
        return forwarded

    with patch("app.api.waygate.proxy.proxy", new=AsyncMock(side_effect=capture_request)) as proxy_call:
        call = getattr(api_client, method)
        request_headers = {"Authorization": "Bearer caller-token", "X-Project-Id": "project-1"}
        response = await (
            call(path, json=body, headers=request_headers) if body is not None else call(path, headers=request_headers)
        )

    assert response.status_code == 207
    assert response.json() == {"forwarded": True}
    proxy_call.assert_awaited_once()
    assert observed == {
        "service_type": "waygate",
        "upstream": upstream_path,
        "authorization": "Bearer caller-token",
        "project_header": "project-1",
        "token_info": {
            "token": "caller-token",
            "project_id": "project-1",
            "user_id": "user-1",
            "username": "user",
            "roles": ["member"],
        },
        "body": body,
    }


@pytest.mark.asyncio
async def test_browser_proxy_requires_authentication(api_client):
    with patch("app.api.waygate.proxy.proxy", new=AsyncMock()) as proxy_call:
        response = await api_client.get("/api/v1/waygate/servers")

    assert response.status_code == 401
    proxy_call.assert_not_awaited()
