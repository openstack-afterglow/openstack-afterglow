"""JWT timeout enforcement using real signed tokens and stored Redis sessions.

Only native Keystone I/O and unrelated login background work are synthetic;
unscoped login still runs domain preparation and native scope validation.
"""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.services import jwt_service, session_store

pytestmark = pytest.mark.usefixtures("auth_directory")

# ──────────────────────────────────────────────────────────────────
# 공통 상수 / 헬퍼
# ──────────────────────────────────────────────────────────────────

_KEYSTONE_TOKEN = "ks-token-timeout-test"
_KS_DATA = {
    "token": _KEYSTONE_TOKEN,
    "project_id": "proj-timeout",
    "project_name": "timeout-project",
    "default_project_id": "proj-timeout",
    "user_id": "user-timeout",
    "username": "bob",
    "expires_at": "2099-01-01T00:00:00+00:00",
    "roles": ["member"],
    "is_system_admin": False,
    "domain_id": "default",
    "domain_name": "Default",
    "identity_domain_id": "default",
    "identity_domain_name": "Default",
    "is_domain_manager": False,
    "email": "actual@example.test",
}


@pytest.fixture
def _ks_authenticate(auth_directory, monkeypatch):
    monkeypatch.setenv("SESSION_TIMEOUT_SECONDS", "3600")
    auth_directory.projects["proj-timeout"] = {
        "id": "proj-timeout",
        "name": "timeout-project",
        "domain_id": "default",
        "enabled": True,
    }
    auth_directory.grants["user-timeout"] = ["proj-timeout"]
    auth_directory.users["user-timeout"]["default_project_id"] = "proj-timeout"
    with (
        patch(
            "app.api.identity.auth.keystone.authenticate",
            return_value=dict(_KS_DATA, project_id="", project_name="", roles=[]),
        ) as authenticate,
        patch(
            "app.api.identity.auth.keystone.validate_token",
            side_effect=lambda _token, project_id="", **_: dict(
                _KS_DATA,
                project_id=project_id,
                project_name=_KS_DATA["project_name"] if project_id else "",
                roles=_KS_DATA["roles"] if project_id else [],
            ),
        ),
        patch(
            "app.api.identity.auth.keystone.list_projects",
            side_effect=lambda _token, domain_id=None, **_: [
                dict(auth_directory.projects[pid])
                for pid in auth_directory.grants[_KS_DATA["user_id"]]
                if domain_id is None or auth_directory.projects[pid]["domain_id"] == domain_id
            ],
        ),
        patch("app.api.identity.auth._prewarm_dashboard", AsyncMock()),
        patch("app.api.identity.auth.record_project_access", AsyncMock()),
        patch("app.api.identity.auth.activity_svc.record", AsyncMock()),
    ):
        yield authenticate


@pytest.fixture
def _ks_get_user():
    from unittest.mock import MagicMock

    user_mock = MagicMock()
    user_mock.default_project_id = ""
    conn_mock = MagicMock()
    conn_mock.identity.get_user.return_value = user_mock
    with patch("app.api.identity.auth.keystone.get_openstack_connection", return_value=conn_mock):
        yield conn_mock


async def _expire_session(redis, refresh_token):
    """Age the original login while leaving both JWT and Redis TTLs valid."""
    from app.config import get_settings

    jti = jwt_service.verify_refresh(refresh_token)["jti"]
    session = await session_store.get_session(jti)
    assert session is not None
    session["started_at"] = time.time() - get_settings().session_timeout_seconds - 1
    await redis.set(session_store._key(jti), json.dumps(session), keepttl=True)
    return jti


# ──────────────────────────────────────────────────────────────────
# JWT 경로 세션 타임아웃 테스트
# ──────────────────────────────────────────────────────────────────


class TestJwtSessionTimeout:
    """JWT 경로에서 세션 타임아웃이 올바르게 적용되는지 확인."""

    @pytest.mark.asyncio
    async def test_expired_session_raises_401(self, _ks_authenticate, _ks_get_user, _fake_redis_global):
        """An expired login denies access repeatedly and removes its refresh record."""
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            login = await ac.post(
                "/api/v1/auth/login",
                json={"username": "bob", "password": "pw"},
            )
            assert login.status_code == 200
            credentials = login.json()
            headers = {"Authorization": f"Bearer {credentials['token']}"}
            assert (await ac.get("/api/v1/auth/me", headers=headers)).status_code == 200

            jti = await _expire_session(_fake_redis_global, credentials["refresh_token"])
            first = await ac.get("/api/v1/auth/me", headers=headers)
            retry = await ac.get("/api/v1/auth/me", headers=headers)
            refresh = await ac.post("/api/v1/auth/refresh", json={"refresh_token": credentials["refresh_token"]})

        assert [first.status_code, retry.status_code, refresh.status_code] == [401, 401, 401]
        assert await session_store.get_session(jti) is None

    @pytest.mark.asyncio
    async def test_refresh_blocked_when_session_timed_out(self, _ks_authenticate, _ks_get_user, _fake_redis_global):
        """Refresh cannot rotate or recreate an expired login, nor keep access alive."""
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            login = await ac.post(
                "/api/v1/auth/login",
                json={"username": "bob", "password": "pw"},
            )
            assert login.status_code == 200
            credentials = login.json()
            jti = await _expire_session(_fake_redis_global, credentials["refresh_token"])

            first = await ac.post("/api/v1/auth/refresh", json={"refresh_token": credentials["refresh_token"]})
            retry = await ac.post("/api/v1/auth/refresh", json={"refresh_token": credentials["refresh_token"]})
            me = await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {credentials['token']}"})

        assert [first.status_code, retry.status_code, me.status_code] == [401, 401, 401]
        assert await session_store.get_session(jti) is None
