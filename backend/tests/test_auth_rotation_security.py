"""HTTP regressions for absolute browser sessions and atomic refresh consumption.

The real FastAPI routes, JWT signatures and Redis Lua scripts run; Keystone is
synthetic and no OpenStack resource or production credential is used.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.identity import auth
from app.main import app
from app.services import jwt_service, session_store

_IDENTITY = {
    "token": "synthetic-keystone-token",
    "project_id": "security-project",
    "project_name": "Security Project",
    "user_id": "security-user",
    "username": "security-user",
    "roles": ["member"],
    "is_system_admin": False,
}
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/124.0"


@pytest.fixture
async def security_client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "synthetic-test-key-" * 4)
    monkeypatch.setenv("SESSION_TIMEOUT_SECONDS", "3600")
    monkeypatch.setenv("TOKEN_IP_BINDING_MODE", "strict")
    conn = MagicMock()
    conn.identity.get_user.return_value.default_project_id = ""

    def validate(_token, project_id=""):
        return dict(_IDENTITY, project_id=project_id or _IDENTITY["project_id"])

    with (
        patch.object(auth.keystone, "authenticate", return_value=dict(_IDENTITY)),
        patch.object(auth.keystone, "get_openstack_connection", return_value=conn),
        patch.object(auth.keystone, "validate_token", side_effect=validate),
        patch.object(auth, "_prewarm_dashboard", AsyncMock()),
        patch.object(auth, "record_project_access", AsyncMock()),
        patch.object(auth.activity_svc, "record", AsyncMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers={"User-Agent": _UA}
        ) as client:
            yield client


async def _login(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "security-user", "password": "synthetic-password", "project_name": "Security Project"},
    )
    assert response.status_code == 200
    return response.json()


async def _session(tokens):
    jti = jwt_service.verify_refresh(tokens["refresh_token"])["jti"]
    return jti, await session_store.get_session(jti)


async def _write_session(redis, jti, session):
    await redis.setex(session_store._key(jti), 36000, json.dumps(session))


@pytest.mark.asyncio
async def test_expired_session_retries_remain_denied(security_client, _fake_redis_global):
    tokens = await _login(security_client)
    jti, session = await _session(tokens)
    session["started_at"] = time.time() - 3601
    await _write_session(_fake_redis_global, jti, session)
    headers = {"Authorization": f"Bearer {tokens['token']}"}

    first = await security_client.get("/api/v1/auth/me", headers=headers)
    retry = await security_client.get("/api/v1/auth/me", headers=headers)
    refresh = await security_client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert [first.status_code, retry.status_code, refresh.status_code] == [401, 401, 401]
    assert await session_store.get_session(jti) is None


@pytest.mark.asyncio
async def test_legacy_session_with_lost_marker_uses_signed_issue_time(security_client, _fake_redis_global):
    tokens = await _login(security_client)
    jti, session = await _session(tokens)
    del session["started_at"]
    await _write_session(_fake_redis_global, jti, session)
    # The old timeout+60 marker has disappeared after a long idle interval.
    marker = f"afterglow:session_start:{hashlib.sha256(jti.encode()).hexdigest()}:security-project"
    await _fake_redis_global.delete(marker)
    issued = jwt_service.verify_access(tokens["token"])["iat"]
    with patch("app.api.deps.time.time", return_value=issued + 3661):
        first = await security_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['token']}"})
        retry = await security_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['token']}"})
    assert [first.status_code, retry.status_code] == [401, 401]


@pytest.mark.asyncio
async def test_legacy_marker_is_preserved_during_migration(security_client, _fake_redis_global):
    tokens = await _login(security_client)
    jti, session = await _session(tokens)
    del session["started_at"]
    await _write_session(_fake_redis_global, jti, session)
    marker = f"afterglow:session_start:{hashlib.sha256(jti.encode()).hexdigest()}:security-project"
    old_start = int(time.time()) - 300
    await _fake_redis_global.setex(marker, 600, str(old_start))
    result = await security_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['token']}"})
    assert result.status_code == 200
    assert (await session_store.get_session(jti))["started_at"] == old_start


@pytest.mark.asyncio
async def test_refresh_and_rescope_preserve_original_lifetime_and_origin(security_client, _fake_redis_global):
    tokens = await _login(security_client)
    jti, original = await _session(tokens)
    original["started_at"] -= 3500
    await _write_session(_fake_redis_global, jti, original)
    refreshed = await security_client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    r_jti, rotated = await _session(refreshed.json())
    scoped = await security_client.post(
        "/api/v1/auth/token/project",
        json={"project_id": "second-project"},
        headers={"Authorization": f"Bearer {refreshed.json()['token']}"},
    )
    assert scoped.status_code == 200
    _, rescope = await _session(scoped.json())
    for field in ("started_at", "origin_ip", "origin_fp", "device_type", "os", "auth_method"):
        assert original[field] == rotated[field] == rescope[field]
    assert rescope["project_id"] == "second-project"
    assert await session_store.get_session(jti) is None
    assert await session_store.get_session(r_jti) is None
    with patch("app.api.deps.time.time", return_value=original["started_at"] + 3600):
        expired = await security_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": scoped.json()["refresh_token"]}
        )
    assert expired.status_code == 401


@pytest.mark.asyncio
async def test_same_refresh_concurrent_http_has_one_success_and_one_live_session(security_client, _fake_redis_global):
    tokens = await _login(security_client)
    old_jti, original = await _session(tokens)
    barrier = threading.Barrier(2)

    def simultaneous_validation(_token, project_id=""):
        barrier.wait(timeout=5)
        return dict(_IDENTITY)

    with patch.object(auth.keystone, "validate_token", side_effect=simultaneous_validation):
        responses = await asyncio.gather(
            security_client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}),
            security_client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}),
        )
    assert sorted(response.status_code for response in responses) == [200, 401]
    winner = next(response.json() for response in responses if response.status_code == 200)
    new_jti, new_session = await _session(winner)
    assert new_session["started_at"] == original["started_at"]
    assert await session_store.get_session(old_jti) is None
    members = await _fake_redis_global.smembers(session_store._user_index_key(_IDENTITY["user_id"]))
    assert members == {new_jti}
    assert len(await _fake_redis_global.keys("afterglow:refresh:*")) == 1
    stale_access = await security_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['token']}"})
    live_access = await security_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {winner['token']}"})
    assert [stale_access.status_code, live_access.status_code] == [401, 200]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["blacklist", "logout", "expiry"])
async def test_session_revoked_during_keystone_validation_is_not_rotated(security_client, _fake_redis_global, change):
    tokens = await _login(security_client)
    jti, _ = await _session(tokens)
    started = threading.Event()
    release = threading.Event()

    def validation(_token, project_id=""):
        started.set()
        assert release.wait(timeout=5)
        return dict(_IDENTITY)

    with patch.object(auth.keystone, "validate_token", side_effect=validation):
        request = asyncio.create_task(
            security_client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        )
        assert await asyncio.to_thread(started.wait, 5)
        try:
            if change == "blacklist":
                await session_store.blacklist_session(jti, "concurrent revocation")
            elif change == "logout":
                await session_store.delete_session(jti)
            else:
                session = await session_store.get_session(jti)
                session["started_at"] -= 3601
                await _write_session(_fake_redis_global, jti, session)
        finally:
            release.set()
        result = await request
    assert result.status_code == 401
    keys = await _fake_redis_global.keys("afterglow:refresh:*")
    assert len(keys) == (1 if change == "blacklist" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/auth/refresh", "/api/v1/auth/token/project"])
async def test_rotation_store_outage_reports_503_and_preserves_original_session(security_client, path):
    tokens = await _login(security_client)
    jti, original = await _session(tokens)
    body = {"refresh_token": tokens["refresh_token"]} if path.endswith("refresh") else {"project_id": "second-project"}
    with patch.object(session_store, "store_session", AsyncMock(side_effect=ConnectionError("synthetic Redis outage"))):
        result = await security_client.post(path, json=body, headers={"Authorization": f"Bearer {tokens['token']}"})
    assert result.status_code == 503
    stored = await session_store.get_session(jti)
    for field in ("started_at", "origin_ip", "origin_fp", "project_id", "user_id"):
        assert stored[field] == original[field]


@pytest.mark.asyncio
async def test_strict_refresh_binding_rejects_different_device(security_client):
    tokens = await _login(security_client)
    response = await security_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}, headers={"User-Agent": "stolen-device"}
    )
    assert response.status_code == 401
    _, session = await _session(tokens)
    assert session["blacklisted"] is True


@pytest.mark.asyncio
async def test_legacy_missing_origin_cannot_bypass_strict_refresh(security_client, _fake_redis_global):
    tokens = await _login(security_client)
    jti, session = await _session(tokens)
    session["origin_ip"] = ""
    session["origin_fp"] = ""
    await _write_session(_fake_redis_global, jti, session)
    response = await security_client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401
    assert (await session_store.get_session(jti))["blacklisted"] is True


@pytest.mark.asyncio
async def test_gitlab_callback_records_origin_and_enforces_binding(security_client, monkeypatch):
    monkeypatch.setenv("GITLAB_OIDC_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    security_client.cookies.set(
        "afterglow_gitlab_oidc_state", "security-state", domain="test.local", path=auth._GITLAB_OIDC_STATE_COOKIE_PATH
    )
    with patch("app.services.gitlab_oidc.exchange_code", AsyncMock(return_value=dict(_IDENTITY))):
        callback = await security_client.post(
            "/api/v1/auth/gitlab/callback", json={"code": "synthetic-code", "state": "security-state"}
        )
    assert callback.status_code == 200
    _, session = await _session(callback.json())
    assert session["auth_method"] == "federated"
    assert session["origin_ip"] == "127.0.0.1"
    assert len(session["origin_fp"]) == 32
    assert session["device_type"] == "desktop"
    assert session["os"] == "macOS"
    assert "afterglow_gitlab_oidc_state" not in security_client.cookies
    denied = await security_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {callback.json()['token']}", "User-Agent": "stolen-device"},
    )
    assert denied.status_code == 401


@pytest.mark.asyncio
async def test_logout_session_delete_failure_is_observable(security_client):
    tokens = await _login(security_client)
    jti, _ = await _session(tokens)
    with patch.object(
        session_store, "delete_session", AsyncMock(side_effect=ConnectionError("synthetic Redis outage"))
    ):
        logout = await security_client.post(
            "/api/v1/auth/logout", headers={"Authorization": f"Bearer {tokens['token']}"}
        )
    assert logout.status_code == 503
    assert await session_store.get_session(jti) is not None


@pytest.mark.asyncio
async def test_logout_keystone_revoke_failure_reports_503_and_still_removes_session(security_client):
    tokens = await _login(security_client)
    jti, _ = await _session(tokens)
    with patch.object(auth.keystone, "revoke_token", side_effect=ConnectionError("synthetic Keystone outage")):
        logout = await security_client.post(
            "/api/v1/auth/logout", headers={"Authorization": f"Bearer {tokens['token']}"}
        )
    assert logout.status_code == 503
    assert await session_store.get_session(jti) is None
