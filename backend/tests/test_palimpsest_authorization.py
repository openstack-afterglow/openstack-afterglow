"""Current subject validation failures remain errors before package I/O."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request

from app.api.palimpsest import package_keys, packages
from app.config import get_settings
from app.services import keystone, project_service

PROJECT = "11111111111141118111111111111111"
USER = "33333333333343338333333333333333"
IDENTIFIER = "44444444444444448444444444444444"
DIGEST = "sha256:" + "a" * 64
NAMESPACE = "p-" + PROJECT
INVENTORY = "palimpsest-inventory_reader"
DOWNLOAD = "palimpsest-download_user"
PUBLISH = "palimpsest-publish_editor"
KEYS_EDITOR = "palimpsest-keys_editor"
KEYS_ADMIN = "palimpsest-keys_admin"
BASE = "/api/v1/palimpsest"


@pytest.fixture
async def custom_client(monkeypatch):
    app = FastAPI()
    app.include_router(packages.router, prefix=BASE + "/packages")
    app.include_router(package_keys.router, prefix=BASE + "/package-keys")
    # No Hub is configured: current authority failures must be propagated
    # before transport configuration can replace them with a different error.
    monkeypatch.setattr(get_settings(), "service_palimpsest_enabled", True)
    monkeypatch.setattr(get_settings(), "service_palimpsest_internal_url", "")
    current = {"roles": ["member", INVENTORY]}
    monkeypatch.setattr(project_service, "get_project_access", AsyncMock(side_effect=lambda *_: dict(current)))
    monkeypatch.setattr(keystone, "_has_system_admin_role", lambda *_: False)

    async def identity(request: Request):
        info = {
            "project_id": PROJECT,
            "user_id": USER,
            "token": "original-subject",
            "roles": ["member", INVENTORY, DOWNLOAD, PUBLISH, KEYS_EDITOR, KEYS_ADMIN],
        }
        request.state.token_info = info
        return info

    app.dependency_overrides[packages.package_browser_identity] = identity
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, current


async def test_current_provider_outage_has_no_session_role_fallback(custom_client, monkeypatch):
    client, _ = custom_client
    monkeypatch.setattr(
        project_service,
        "get_project_access",
        AsyncMock(side_effect=HTTPException(503, "Current authority unavailable")),
    )
    response = await client.post(BASE + "/package-keys", json={"name": "ci"})
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Current authority unavailable"
