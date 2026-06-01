"""Barbican Key Manager 관리자 — 단위 테스트."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_list_project_quotas_non_admin_returns_403(non_admin_client):
    r = await non_admin_client.get("/api/admin/key-manager/project-quotas")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_project_quotas_admin_success(admin_client):
    with patch("app.api.identity.admin_secrets.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = AsyncMock(return_value=[
            {"project_id": "proj-1", "project_quotas": {"secrets": 100}}
        ])
        r = await admin_client.get("/api/admin/key-manager/project-quotas")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_set_project_quota_non_admin_returns_403(non_admin_client):
    r = await non_admin_client.put(
        "/api/admin/key-manager/project-quotas/proj-1",
        json={"secrets": 50}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_set_project_quota_admin_success(admin_client):
    with patch("app.api.identity.admin_secrets.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = AsyncMock(return_value={"project_quotas": {"secrets": 50}})
        r = await admin_client.put(
            "/api/admin/key-manager/project-quotas/proj-1",
            json={"secrets": 50}
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_set_project_quota_empty_body_returns_422(admin_client):
    r = await admin_client.put(
        "/api/admin/key-manager/project-quotas/proj-1",
        json={}
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_delete_project_quota_non_admin_returns_403(non_admin_client):
    r = await non_admin_client.delete("/api/admin/key-manager/project-quotas/proj-1")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_project_quota_admin_success(admin_client):
    with patch("app.api.identity.admin_secrets.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = AsyncMock(return_value=None)
        r = await admin_client.delete("/api/admin/key-manager/project-quotas/proj-1")
    assert r.status_code == 204
