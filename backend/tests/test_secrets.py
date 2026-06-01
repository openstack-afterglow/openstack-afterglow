"""Barbican Key Manager — 단위 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_list_secrets_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/secrets")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_secrets_success(client):
    with patch("app.api.secrets.secrets.cached_call", new=AsyncMock(return_value=[
        {"id": "abc", "name": "my-pass", "secret_type": "passphrase",
         "status": "ACTIVE", "system_managed": False,
         "algorithm": None, "bit_length": None, "mode": None,
         "created": None, "expires": None, "content_types": None}
    ])):
        r = await client.get("/api/secrets")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "my-pass"


@pytest.mark.asyncio
async def test_create_secret_success(client):
    with patch("app.api.secrets.secrets.asyncio") as mock_asyncio, \
         patch("app.api.secrets.secrets.invalidate", new=AsyncMock()), \
         patch("app.api.secrets.secrets.rec", new=AsyncMock()):
        mock_asyncio.to_thread = AsyncMock(return_value={
            "id": "new-id", "name": "test-secret", "secret_ref": "http://barbican/v1/secrets/new-id"
        })
        r = await client.post("/api/secrets", json={
            "name": "test-secret",
            "secret_type": "passphrase",
            "payload": "mypassword",
        })
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_delete_system_managed_secret_forbidden(client):
    """afterglow- prefix secret은 삭제 불가."""
    with patch("app.api.secrets.secrets.asyncio") as mock_asyncio, \
         patch("app.api.secrets.secrets.rec", new=AsyncMock()):
        mock_asyncio.to_thread = AsyncMock(
            side_effect=ValueError("시스템 관리 secret은 삭제할 수 없습니다: afterglow-k8s-kek")
        )
        r = await client.delete("/api/secrets/some-id")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_effective_quota_success(client):
    with patch("app.api.secrets.secrets.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = AsyncMock(return_value={
            "secrets": -1, "orders": -1, "containers": -1, "consumers": -1, "cas": -1
        })
        r = await client.get("/api/secrets/quota/effective")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_payload_not_cached(client):
    """payload 엔드포인트는 cached_call을 사용하지 않아야 한다."""
    import app.api.secrets.secrets as mod
    import inspect
    src = inspect.getsource(mod.get_secret_payload)
    assert "cached_call" not in src
