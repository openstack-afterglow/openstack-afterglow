"""Browser namespace and verified system boundaries around native Drover policy."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api import deps
from app.api.drover.admin import router as drover_admin_router
from app.api.drover.proxy import router as drover_proxy_router
from app.services import project_service, service_proxy
from tests.admin_gate import synthetic_verified_admin

PROJECT = "11111111111141118111111111111111"
USER = "33333333333343338333333333333333"
CLUSTER = "44444444-4444-4444-8444-444444444444"
INVENTORY = "drover-inventory_reader"
ACCESS_USER = "drover-access_user"
CLUSTERS_EDITOR = "drover-clusters_editor"
WORKLOADS_EDITOR = "drover-workloads_editor"
CLUSTERS_ADMIN = "drover-clusters_admin"
ACCESS_ADMIN = "drover-access_admin"
USER_GRADE = [INVENTORY, ACCESS_USER]
EDITOR_GRADE = [*USER_GRADE, CLUSTERS_EDITOR, WORKLOADS_EDITOR]
ADMIN_GRADE = [*EDITOR_GRADE, CLUSTERS_ADMIN, ACCESS_ADMIN]
C = f"/v1/clusters/{CLUSTER}"
NS = f"{C}/namespaces/drover-workload-abc"


@pytest.fixture
async def bff(monkeypatch):
    """The registered Drover BFF routes; only the Keystone/upstream boundaries are synthetic."""
    real_client = httpx.AsyncClient
    upstream: list[httpx.Request] = []
    current = {"roles": ["member"]}
    session = {"system": False}

    async def handler(request: httpx.Request) -> httpx.Response:
        upstream.append(request)
        # Network responses stay unread until the BFF's aiter_raw bridge consumes them.
        return httpx.Response(
            200, stream=httpx.ByteStream(b'{"ok":true}'), headers={"content-type": "application/json"}
        )

    def upstream_client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    async def identity(request: Request):
        # Stale session claims carry every leaf; only CURRENT access may authorize.
        info = {
            "token": "keystone-token",
            "project_id": PROJECT,
            "user_id": USER,
            "roles": ["member", *ADMIN_GRADE],
            "is_system_admin": session["system"],
        }
        request.state.token_info = info
        return info

    app = FastAPI()
    app.include_router(drover_proxy_router, prefix="/api/v1/k3s")
    app.include_router(drover_admin_router, prefix="/api/v1/admin")
    app.dependency_overrides[deps.get_token_info] = identity
    app.dependency_overrides[deps.require_admin] = synthetic_verified_admin
    monkeypatch.setattr(project_service, "get_project_access", AsyncMock(side_effect=lambda *_: dict(current)))
    monkeypatch.setattr(service_proxy, "_get_internal_endpoint", lambda *_: "http://drover.internal")
    monkeypatch.setattr(httpx, "AsyncClient", upstream_client)
    async with real_client(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, current, upstream, session


async def test_tenant_catch_all_cannot_reach_admin_or_callback_routes(bff):
    client, current, upstream, _ = bff
    current["roles"] = ["member", *ADMIN_GRADE]
    assert (await client.get("/api/v1/k3s/admin/clusters")).status_code == 403
    assert (await client.get(f"/api/v1/k3s/admin/clusters/{CLUSTER}/kubeconfig")).status_code == 403
    assert (await client.put("/api/v1/k3s/admin/runtime-settings/k3s.version", json={})).status_code == 403
    assert (await client.post("/api/v1/k3s/callback", json={})).status_code == 403
    assert (await client.get(f"/api/v1/k3s/clusters/{CLUSTER}/%252E%252E/admin/clusters")).status_code == 403
    assert upstream == []


async def test_verified_system_admin_router_reaches_global_admin_route(bff):
    client, _, upstream, session = bff
    session["system"] = True
    response = await client.get(f"/api/v1/admin/k3s-clusters/{CLUSTER}/kubeconfig")
    assert response.status_code == 200
    assert upstream[-1].url.path == f"/v1/admin/clusters/{CLUSTER}/kubeconfig"
    project_service.get_project_access.assert_not_called()
