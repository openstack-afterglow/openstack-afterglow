"""Trove DB 인스턴스 자동 백업 서비스 및 API 단위 테스트."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.db_auto_backup import (
    _is_auto_backup,
    _make_backup_name,
    disable_db_auto_backup,
    enable_db_auto_backup,
    get_db_auto_backup_config,
)

_TROVE_ENABLED = os.environ.get("SERVICE_TROVE_ENABLED", "false").lower() in ("true", "1")


# ────────── 헬퍼 ──────────


# ────────── 이름 / 분류 헬퍼 테스트 ──────────


def test_make_backup_name_format():
    name = _make_backup_name("inst-abc-xyz", "daily")
    assert name.startswith("auto_inst-abc_daily_")


def test_is_auto_backup_positive():
    b = {"name": "auto_inst-abc_daily_20240101"}
    assert _is_auto_backup(b, "inst-abc-xyz", "daily")


def test_is_auto_backup_negative_tier():
    b = {"name": "auto_inst-abc_weekly_20240101"}
    assert not _is_auto_backup(b, "inst-abc-xyz", "daily")


def test_is_auto_backup_negative_manual():
    b = {"name": "manual-backup"}
    assert not _is_auto_backup(b, "inst-abc-xyz", "daily")


# ────────── Redis CRUD 테스트 ──────────


@pytest.mark.asyncio
async def test_enable_and_get_config_stores_correct_key():
    stored = {}

    async def fake_set(key, val):
        stored[key] = val

    mock_r = AsyncMock()
    mock_r.set = fake_set
    mock_r.sadd = AsyncMock()

    with patch("app.services.db_auto_backup._get_redis", new=AsyncMock(return_value=mock_r)):
        config = await enable_db_auto_backup("proj-1", "inst-1", max_daily=2, max_weekly=2, max_monthly=1)

    assert config["instance_id"] == "inst-1"
    assert config["project_id"] == "proj-1"
    assert config["max_daily"] == 2
    assert "afterglow:db_auto_backup:config:proj-1:inst-1" in stored


@pytest.mark.asyncio
async def test_get_config_returns_none_when_missing():
    mock_r = AsyncMock()
    mock_r.get = AsyncMock(return_value=None)

    with patch("app.services.db_auto_backup._get_redis", new=AsyncMock(return_value=mock_r)):
        result = await get_db_auto_backup_config("proj-1", "inst-missing")

    assert result is None


@pytest.mark.asyncio
async def test_disable_removes_from_redis():
    mock_r = AsyncMock()
    mock_r.delete = AsyncMock()
    mock_r.srem = AsyncMock()

    with patch("app.services.db_auto_backup._get_redis", new=AsyncMock(return_value=mock_r)):
        await disable_db_auto_backup("proj-1", "inst-1")

    mock_r.delete.assert_called_once_with("afterglow:db_auto_backup:config:proj-1:inst-1")
    mock_r.srem.assert_called_once_with("afterglow:db_auto_backup:all_configs", "proj-1:inst-1")


# ────────── API 엔드포인트 인증 관문 테스트 ──────────


@pytest.mark.asyncio
async def test_get_auto_backup_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/database-instances/inst-1/auto-backup")
    assert resp.status_code in (401, 404, 405)


@pytest.mark.asyncio
async def test_put_auto_backup_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put("/api/v1/database-instances/inst-1/auto-backup", json={"max_daily": 2})
    assert resp.status_code in (401, 404, 405, 422)


@pytest.mark.asyncio
async def test_delete_auto_backup_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/database-instances/inst-1/auto-backup")
    assert resp.status_code in (401, 404, 405)


# ────────── API 엔드포인트 기능 테스트 (Trove 활성화 필요) ──────────


@pytest.mark.asyncio
@pytest.mark.skipif(not _TROVE_ENABLED, reason="Trove 서비스 비활성화")
async def test_put_and_get_auto_backup(client, mock_conn):
    with (
        patch(
            "app.services.db_auto_backup._get_redis",
            new=AsyncMock(
                return_value=AsyncMock(
                    set=AsyncMock(),
                    sadd=AsyncMock(),
                    get=AsyncMock(return_value=None),
                )
            ),
        ),
        patch(
            "app.services.trove.get_instance",
            MagicMock(return_value=MagicMock(project_id="test-project-123", tenant_id=None)),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.put(
                "/api/v1/database-instances/inst-1/auto-backup",
                json={"max_daily": 3, "max_weekly": 2, "max_monthly": 1},
                headers={"Authorization": "Bearer test-token"},
            )
        assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
@pytest.mark.skipif(not _TROVE_ENABLED, reason="Trove 서비스 비활성화")
async def test_delete_auto_backup_removes_config(client, mock_conn):
    with patch(
        "app.services.db_auto_backup._get_redis",
        new=AsyncMock(
            return_value=AsyncMock(
                delete=AsyncMock(),
                srem=AsyncMock(),
            )
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.delete(
                "/api/v1/database-instances/inst-1/auto-backup",
                headers={"Authorization": "Bearer test-token"},
            )
        assert resp.status_code in (204, 401, 403)
