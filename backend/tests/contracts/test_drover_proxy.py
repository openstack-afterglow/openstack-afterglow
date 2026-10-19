"""Afterglow compatibility contracts for the extracted Drover service."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info, require_admin
from app.main import app
from tests.admin_gate import synthetic_verified_admin


@pytest.fixture
async def api_client():
    app.dependency_overrides[require_admin] = synthetic_verified_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(get_token_info, None)
    app.dependency_overrides.pop(require_admin, None)


async def _member(request: Request) -> dict:
    token_info = {
        "token": "caller-token",
        "project_id": "project-1",
        "user_id": "user-1",
        "username": "user",
        "roles": ["member"],
        "domain_id": "default",
        "is_system_admin": False,
    }
    request.state.token_info = token_info
    return token_info


async def _admin(request: Request) -> dict:
    token_info = await _member(request)
    token_info["roles"] = ["admin"]
    token_info["is_system_admin"] = True
    return token_info


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,upstream_path,body",
    [
        ("get", "/api/v1/k3s/clusters", "/v1/clusters", None),
        ("post", "/api/v1/k3s/clusters", "/v1/clusters", {"name": "cluster"}),
        ("patch", "/api/v1/k3s/clusters/cluster-1/scale", "/v1/clusters/cluster-1/scale", {"agent_count": 2}),
        ("delete", "/api/v1/k3s/clusters/cluster-1", "/v1/clusters/cluster-1", None),
        ("get", "/api/v1/k3s/cluster-templates", "/v1/cluster-templates", None),
    ],
)
async def test_tenant_routes_proxy_to_drover(api_client, method, path, upstream_path, body):
    app.dependency_overrides[get_token_info] = _member
    forwarded = JSONResponse(status_code=207, content={"forwarded": True})
    with patch("app.api.drover.proxy.proxy", new=AsyncMock(return_value=forwarded)) as proxy_call:
        call = getattr(api_client, method)
        response = await (call(path, json=body) if body is not None else call(path))

    assert response.status_code == 207
    assert proxy_call.await_args.args[0] == "drover"
    assert proxy_call.await_args.args[2] == upstream_path
    assert proxy_call.await_args.args[1].state.token_info["project_id"] == "project-1"


@pytest.mark.asyncio
async def test_tenant_proxy_requires_authentication(api_client):
    with patch("app.api.drover.proxy.proxy", new=AsyncMock()) as proxy_call:
        response = await api_client.get("/api/v1/k3s/clusters")

    assert response.status_code == 401
    proxy_call.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,upstream_path",
    [
        ("get", "/api/v1/admin/k3s-clusters", "/v1/admin/clusters"),
        ("get", "/api/v1/admin/k3s-clusters/cluster-1/kubeconfig", "/v1/admin/clusters/cluster-1/kubeconfig"),
        ("post", "/api/v1/admin/k3s-clusters/cluster-1/delete-async", "/v1/admin/clusters/cluster-1/delete-async"),
        ("get", "/api/v1/admin/k3s-cluster-templates", "/v1/admin/cluster-templates"),
    ],
)
async def test_admin_routes_preserve_paths_and_system_admin_gate(api_client, method, path, upstream_path):
    app.dependency_overrides[get_token_info] = _admin
    forwarded = JSONResponse(status_code=206, content={"admin": True})
    with patch("app.api.drover.admin.proxy", new=AsyncMock(return_value=forwarded)) as proxy_call:
        response = await getattr(api_client, method)(path)

    assert response.status_code == 206
    assert proxy_call.await_args.args[0] == "drover"
    assert proxy_call.await_args.args[2] == upstream_path

    app.dependency_overrides[get_token_info] = _member
    with patch("app.api.drover.admin.proxy", new=AsyncMock()) as denied_call:
        denied = await api_client.get("/api/v1/admin/k3s-clusters")
    assert denied.status_code == 403
    denied_call.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/k3s/callback", "/api/k3s/callback"])
async def test_baked_callback_proxies_without_browser_auth(api_client, path):
    forwarded = JSONResponse(status_code=202, content={"accepted": True})
    with patch("app.api.drover.callback.proxy_passthrough", new=AsyncMock(return_value=forwarded)) as proxy_call:
        response = await api_client.post(
            path,
            json={"token": "one-time-token"},
            headers={"Authorization": "Bearer callback-token"},
        )

    assert response.status_code == 202
    assert proxy_call.await_args.args[0] == "drover"
    assert proxy_call.await_args.args[2] == "/v1/callback"
    assert proxy_call.await_args.args[1].headers["authorization"] == "Bearer callback-token"
