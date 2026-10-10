"""Consumer-visible authorization and availability boundaries for cloud tools."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info
from app.api.lumen import proxy as proxy_module
from app.services.mcp_control_plane import lumen


@pytest.fixture
def cloud_app(monkeypatch):
    app = FastAPI()
    app.include_router(proxy_module.router, prefix="/api/v1/chat")

    async def token_info(request: Request):
        info = {
            "user_id": "user-a",
            "project_id": "project-a",
            "project_name": "Project A",
            "token": "synthetic-caller-token",
            "roles": ["member"],
        }
        request.state.token_info = info
        return info

    app.dependency_overrides[get_token_info] = token_info
    monkeypatch.setattr(
        proxy_module,
        "get_settings",
        lambda: SimpleNamespace(service_mcp_enabled=True, lumen_mcp_service_token="synthetic-workload-token"),
    )
    return app


@pytest.mark.asyncio
async def test_cloud_catalogue_requires_current_tool_permission_not_token_member(cloud_app, monkeypatch):
    current = AsyncMock(return_value={"roles": ["member", "lumen-chat_user"], "is_manager": False})
    monkeypatch.setattr("app.services.project_service.get_project_access", current)
    storage = AsyncMock()
    monkeypatch.setattr(lumen, "selected_lumen_snapshot", storage)
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        denied = await client.get("/api/v1/chat/cloud-tools")
    assert denied.status_code == 403
    storage.assert_not_awaited()


@pytest.mark.asyncio
async def test_cloud_authority_outage_does_not_claim_available_catalogue(cloud_app, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_service.get_project_access",
        AsyncMock(return_value={"roles": ["member", "lumen-tools_user"], "is_manager": False}),
    )
    monkeypatch.setattr(
        lumen, "selected_lumen_snapshot", AsyncMock(side_effect=lumen.McpLumenAuthorityError("storage failed"))
    )
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        unavailable = await client.get("/api/v1/chat/cloud-tools")
    assert unavailable.status_code == 503
    assert "enabled" not in unavailable.json()


@pytest.mark.asyncio
async def test_denied_native_chat_does_not_create_cloud_credential(cloud_app, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_service.get_project_access",
        AsyncMock(return_value={"roles": ["member", "lumen-chat_user", "lumen-history_reader"], "is_manager": False}),
    )
    issuance = AsyncMock()
    monkeypatch.setattr(proxy_module.defaults, "ensure_default_lumen_grant", issuance)
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        denied = await client.post(
            "/api/v1/chat/conversations/conversation-a/completions",
            json={"features": {"tool_policy": {"mode": "agent_default"}}},
        )
    assert denied.status_code == 403
    issuance.assert_not_awaited()
