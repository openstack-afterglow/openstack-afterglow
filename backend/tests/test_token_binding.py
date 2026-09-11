"""토큰 출처 바인딩 · 블랙리스트 · 전체 로그아웃 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ──────────────────────────────────────────────
# token_binding 모듈 순수 함수 테스트
# ──────────────────────────────────────────────


def _make_request(ua: str = "TestAgent/1.0", al: str = "ko-KR", ae: str = "gzip"):
    req = MagicMock()
    req.headers = {"User-Agent": ua, "Accept-Language": al, "Accept-Encoding": ae}
    return req


def test_get_origin_returns_ip_and_fingerprint():
    from app.services.token_binding import get_origin

    req = _make_request()
    with patch("app.rate_limit._get_real_ip", return_value="10.0.0.1"):
        ip, fp = get_origin(req)
    assert ip == "10.0.0.1"
    assert len(fp) == 32  # sha256[:32]


def test_same_fingerprint_for_same_headers():
    from app.services.token_binding import get_origin

    req = _make_request()
    with patch("app.rate_limit._get_real_ip", return_value="10.0.0.1"):
        _, fp1 = get_origin(req)
        _, fp2 = get_origin(req)
    assert fp1 == fp2


def test_different_ua_gives_different_fingerprint():
    from app.services.token_binding import get_origin

    with patch("app.rate_limit._get_real_ip", return_value="10.0.0.1"):
        _, fp1 = get_origin(_make_request(ua="BrowserA/1.0"))
        _, fp2 = get_origin(_make_request(ua="BrowserB/2.0"))
    assert fp1 != fp2


class TestSameSubnet:
    def test_ipv4_same_24(self):
        from app.services.token_binding import _same_subnet

        assert _same_subnet("192.168.1.10", "192.168.1.200")

    def test_ipv4_different_24(self):
        from app.services.token_binding import _same_subnet

        assert not _same_subnet("192.168.1.10", "192.168.2.10")

    def test_ipv6_same_64(self):
        from app.services.token_binding import _same_subnet

        assert _same_subnet("2001:db8::1", "2001:db8::ff")

    def test_ipv6_different_64(self):
        from app.services.token_binding import _same_subnet

        assert not _same_subnet("2001:db8:0:1::1", "2001:db8:0:2::1")

    def test_ipv4_ipv6_never_match(self):
        from app.services.token_binding import _same_subnet

        assert not _same_subnet("192.168.1.1", "::ffff:192.168.1.1")


class TestCheckBinding:
    def _sess(self, origin_ip="10.0.0.1", origin_fp="aabbccdd" * 4):
        return {"origin_ip": origin_ip, "origin_fp": origin_fp}

    def test_off_mode_always_ok(self):
        from app.services.token_binding import check_binding

        action, _ = check_binding(self._sess(), "1.2.3.4", "different_fp", "off")
        assert action == "ok"

    def test_legacy_session_always_ok(self):
        from app.services.token_binding import check_binding

        action, reason = check_binding({"origin_ip": "", "origin_fp": ""}, "1.2.3.4", "fp", "strict")
        assert action == "ok"
        assert reason == "legacy_session"

    def test_log_mode_same_ip_fp_ok(self):
        from app.services.token_binding import check_binding

        sess = self._sess("10.0.0.1", "fp123")
        action, _ = check_binding(sess, "10.0.0.1", "fp123", "log")
        assert action == "ok"

    def test_log_mode_different_ip_returns_log(self):
        from app.services.token_binding import check_binding

        action, reason = check_binding(self._sess(), "99.99.99.99", "different", "log")
        assert action == "log"
        assert "99.99.99.99" in reason

    def test_subnet_mode_same_subnet_ok(self):
        from app.services.token_binding import check_binding

        sess = self._sess("192.168.1.10", "fp")
        action, _ = check_binding(sess, "192.168.1.200", "fp", "subnet")
        assert action == "ok"

    def test_subnet_mode_different_subnet_block(self):
        from app.services.token_binding import check_binding

        sess = self._sess("192.168.1.10", "fp")
        action, reason = check_binding(sess, "10.0.0.1", "fp", "subnet")
        assert action == "block"
        assert "10.0.0.1" in reason

    def test_subnet_mode_same_subnet_different_fp_log(self):
        from app.services.token_binding import check_binding

        sess = self._sess("192.168.1.10", "fp_origin")
        action, _ = check_binding(sess, "192.168.1.50", "fp_other", "subnet")
        assert action == "log"

    def test_strict_mode_exact_ip_fp_ok(self):
        from app.services.token_binding import check_binding

        sess = self._sess("10.0.0.1", "fp_exact")
        action, _ = check_binding(sess, "10.0.0.1", "fp_exact", "strict")
        assert action == "ok"

    def test_strict_mode_different_ip_block(self):
        from app.services.token_binding import check_binding

        action, _ = check_binding(self._sess(), "10.0.0.2", "aabbccdd" * 4, "strict")
        assert action == "block"

    def test_strict_mode_different_fp_block(self):
        from app.services.token_binding import check_binding

        sess = self._sess("10.0.0.1", "fp_a")
        action, _ = check_binding(sess, "10.0.0.1", "fp_b", "strict")
        assert action == "block"


# ──────────────────────────────────────────────
# session_store 헬퍼 테스트
# ──────────────────────────────────────────────


def _make_redis_mock(stored: dict[str, bytes]):
    """Redis 모의 객체. get/set/setex/ttl/delete/smembers/srem/sadd/expire/pipeline."""
    r = MagicMock()

    async def _get(key):
        return stored.get(key)

    async def _set(key, val):
        stored[key] = val if isinstance(val, bytes) else val.encode()

    async def _setex(key, ttl, val):
        stored[key] = val if isinstance(val, bytes) else val.encode()

    async def _ttl(key):
        return 3600 if key in stored else -2

    async def _delete(*keys):
        for k in keys:
            stored.pop(k, None)

    async def _smembers(key):
        return stored.get(key, set())

    async def _srem(key, *members):
        s = stored.get(key, set())
        for m in members:
            s.discard(m)
        stored[key] = s

    r.get = _get
    r.set = _set
    r.setex = _setex
    r.ttl = _ttl
    r.delete = _delete
    r.smembers = _smembers
    r.srem = _srem

    # pipeline (used only in store_session)
    class _Pipe:
        def __init__(self):
            self._cmds = []

        def setex(self, key, ttl, val):
            stored[key] = val if isinstance(val, bytes) else val.encode()

        def sadd(self, key, *vals):
            s = stored.get(key, set())
            s.update(v.encode() if isinstance(v, str) else v for v in vals)
            stored[key] = s

        def expire(self, key, ttl):
            pass

        async def execute(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    r.pipeline = lambda: _Pipe()
    return r


@pytest.mark.asyncio
async def test_store_session_persists_origin():
    import json

    from app.services.session_store import store_session

    store: dict = {}
    with patch("app.services.session_store._get_redis", AsyncMock(return_value=_make_redis_mock(store))):
        await store_session(
            jti="jti1",
            keystone_token="ks",
            project_id="proj",
            user_id="user1",
            exp=9999999999,
            origin_ip="10.0.0.1",
            origin_fp="fp_test",
        )
    key = "afterglow:refresh:jti1"
    assert key in store
    sess = json.loads(store[key])
    assert sess["origin_ip"] == "10.0.0.1"
    assert sess["origin_fp"] == "fp_test"
    assert sess["last_ip"] == "10.0.0.1"  # last_* 초기화 = origin
    assert sess["blacklisted"] is False


@pytest.mark.asyncio
async def test_blacklist_session_sets_flag():
    import fakeredis.aioredis as fakeredis

    from app.services.session_store import blacklist_session, get_session, store_session

    fake = fakeredis.FakeRedis()
    with patch("app.services.session_store._get_redis", AsyncMock(return_value=fake)):
        await store_session(
            jti="jti1",
            keystone_token="ks",
            project_id="proj",
            user_id="user1",
            exp=9999999999,
            origin_ip="10.0.0.1",
            origin_fp="fp_test",
        )
        await blacklist_session("jti1", "test_reason")
        sess = await get_session("jti1")

    assert sess is not None
    assert sess["blacklisted"] is True
    assert sess["blacklist_reason"] == "test_reason"


@pytest.mark.asyncio
async def test_touch_session_seen_updates_last():
    import fakeredis.aioredis as fakeredis

    from app.services.session_store import get_session, store_session, touch_session_seen

    fake = fakeredis.FakeRedis()
    with patch("app.services.session_store._get_redis", AsyncMock(return_value=fake)):
        await store_session(
            jti="jti1",
            keystone_token="ks",
            project_id="proj",
            user_id="user1",
            exp=9999999999,
            origin_ip="10.0.0.1",
            origin_fp="fp_old",
        )
        await touch_session_seen("jti1", "10.0.0.2", "fp_new")
        sess = await get_session("jti1")

    assert sess is not None
    assert sess["last_ip"] == "10.0.0.2"
    assert sess["last_fp"] == "fp_new"


@pytest.mark.asyncio
async def test_touch_session_seen_throttle_skips():
    import fakeredis.aioredis as fakeredis

    from app.services.session_store import get_session, store_session, touch_session_seen

    fake = fakeredis.FakeRedis()
    with patch("app.services.session_store._get_redis", AsyncMock(return_value=fake)):
        await store_session(
            jti="jti1",
            keystone_token="ks",
            project_id="proj",
            user_id="user1",
            exp=9999999999,
            origin_ip="10.0.0.1",
            origin_fp="fp_same",
        )
        initial_sess = await get_session("jti1")
        assert initial_sess is not None
        initial_seen = initial_sess.get("last_seen")

        # Same IP and FP within throttle window (60s) -> touch_session_seen skips
        await touch_session_seen("jti1", "10.0.0.1", "fp_same")
        sess = await get_session("jti1")

    assert sess is not None
    assert sess["last_ip"] == "10.0.0.1"
    assert sess["last_fp"] == "fp_same"
    assert sess.get("last_seen") == initial_seen


def test_session_seen_precheck_skips_fresh_redis_write():
    """이미 조회한 최신 세션은 매 요청마다 touch EVAL을 만들지 않는다."""
    from app.services.session_store import session_seen_needs_touch

    session = {
        "last_ip": "10.0.0.1",
        "last_fp": "fp_same",
        "last_seen": 1_000,
    }

    assert session_seen_needs_touch(session, "10.0.0.1", "fp_same", now=1_059) is False
    assert session_seen_needs_touch(session, "10.0.0.1", "fp_same", now=1_060) is True
    assert session_seen_needs_touch(session, "10.0.0.2", "fp_same", now=1_001) is True


@pytest.mark.asyncio
async def test_revoke_user_sessions_calls_keystone():
    """revoke_user_sessions(revoke_keystone=True)가 Keystone revoke_token을 호출하는지 확인."""
    import json

    from app.services.session_store import revoke_user_sessions

    sess_data = {"keystone_token": "ks-token-abc", "user_id": "user1"}
    store = {
        "afterglow:refresh:jti1": json.dumps(sess_data).encode(),
        "afterglow:user-sessions:user1": {b"jti1"},
    }
    mock_revoke = MagicMock()
    with (
        patch("app.services.session_store._get_redis", AsyncMock(return_value=_make_redis_mock(store))),
        patch("app.services.session_store.asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *a: fn(*a))),
        patch("app.services.keystone.revoke_token", mock_revoke),
    ):
        count = await revoke_user_sessions("user1", revoke_keystone=True)
    assert count == 1
    mock_revoke.assert_called_once_with("ks-token-abc")


@pytest.mark.asyncio
async def test_revoke_user_sessions_skip_keystone():
    """revoke_keystone=False이면 Keystone 폐기 없이 세션만 삭제."""
    import json

    from app.services.session_store import revoke_user_sessions

    sess_data = {"keystone_token": "ks-token", "user_id": "user1"}
    store = {
        "afterglow:refresh:jti1": json.dumps(sess_data).encode(),
        "afterglow:user-sessions:user1": {b"jti1"},
    }
    mock_revoke = MagicMock()
    with (
        patch("app.services.session_store._get_redis", AsyncMock(return_value=_make_redis_mock(store))),
        patch("app.services.keystone.revoke_token", mock_revoke),
    ):
        count = await revoke_user_sessions("user1", revoke_keystone=False)
    assert count == 1
    mock_revoke.assert_not_called()


# ──────────────────────────────────────────────
# 엔드포인트 통합 테스트
# ──────────────────────────────────────────────


def _make_sess(blacklisted=False, origin_ip="10.0.0.1", origin_fp="fp"):
    return {
        "keystone_token": "ks",
        "project_id": "proj",
        "user_id": "user1",
        "exp": 9999999999,
        "auth_method": "password",
        "origin_ip": origin_ip,
        "origin_fp": origin_fp,
        "last_ip": origin_ip,
        "last_fp": origin_fp,
        "last_seen": 0,
        "blacklisted": blacklisted,
        "blacklist_reason": "",
    }


@pytest.mark.asyncio
async def test_blacklisted_session_returns_401():
    """블랙리스트 세션 — _resolve_jwt_token_info 직접 호출 시 HTTPException(401)."""
    from fastapi import HTTPException

    from app.api.deps import _resolve_jwt_token_info
    from app.services import jwt_service

    _, r_jti, _ = jwt_service.sign_refresh("user1")
    access_str, _, _ = jwt_service.sign_access(
        user_id="user1",
        username="testuser",
        project_id="proj",
        project_name="Test",
        refresh_jti=r_jti,
    )
    blacklisted_sess = _make_sess(blacklisted=True)
    mock_req = MagicMock()
    mock_req.headers = {"User-Agent": "Test/1.0", "Accept-Language": "ko", "Accept-Encoding": "gzip"}

    with patch("app.services.session_store.get_session", AsyncMock(return_value=blacklisted_sess)):
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_jwt_token_info(mock_req, access_str, None)
    assert exc_info.value.status_code == 401
    assert "차단" in exc_info.value.detail


@pytest.mark.asyncio
async def test_subnet_mismatch_returns_401():
    """subnet 모드에서 다른 대역 IP 요청은 HTTPException(401)."""
    from fastapi import HTTPException

    from app.api.deps import _resolve_jwt_token_info
    from app.services import jwt_service

    _, r_jti, _ = jwt_service.sign_refresh("user1")
    access_str, _, _ = jwt_service.sign_access(
        user_id="user1",
        username="testuser",
        project_id="proj",
        project_name="Test",
        refresh_jti=r_jti,
    )
    sess = _make_sess(origin_ip="192.168.1.1", origin_fp="fp_origin")
    mock_req = MagicMock()
    mock_req.headers = {"User-Agent": "Test/1.0", "Accept-Language": "ko", "Accept-Encoding": "gzip"}

    with (
        patch("app.services.session_store.get_session", AsyncMock(return_value=sess)),
        patch("app.api.deps.get_settings") as mock_settings,
        patch("app.rate_limit._get_real_ip", return_value="10.99.99.99"),
        patch("app.services.session_store.blacklist_session", AsyncMock()),
        patch("app.services.activity.record", AsyncMock()),
    ):
        mock_settings.return_value.token_ip_binding_mode = "subnet"
        mock_settings.return_value.session_timeout_seconds = 3600
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_jwt_token_info(mock_req, access_str, None)
    assert exc_info.value.status_code == 401
    assert "출처" in exc_info.value.detail


@pytest.mark.asyncio
async def test_logout_all_revokes_sessions(client):
    """POST /api/auth/logout-all 이 revoke_user_sessions를 호출한다."""
    from tests.conftest import make_token_info

    with (
        patch("app.api.identity.auth.get_token_info", return_value=make_token_info()),
        patch("app.api.identity.auth.session_store.revoke_user_sessions", AsyncMock(return_value=3)) as mock_revoke,
        patch("app.api.identity.auth.invalidate_token_cache", AsyncMock()),
    ):
        resp = await client.post("/api/v1/auth/logout-all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["revoked_count"] == 3
    mock_revoke.assert_called_once_with("test-user-123", revoke_keystone=True)


@pytest.mark.asyncio
async def test_list_sessions_returns_sessions(client):
    """GET /api/auth/sessions 가 세션 목록을 반환한다."""
    from tests.conftest import make_token_info

    mock_sessions = [_make_sess()]
    with (
        patch("app.api.identity.auth.get_token_info", return_value=make_token_info()),
        patch("app.api.identity.auth.session_store.list_user_sessions", AsyncMock(return_value=mock_sessions)),
    ):
        resp = await client.get("/api/v1/auth/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert "sessions" in data


@pytest.mark.asyncio
async def test_admin_revoke_sessions(admin_client):
    """POST /api/admin/users/{id}/revoke-sessions 가 관리자 권한으로 호출된다."""
    with (
        patch(
            "app.api.identity.admin_identity.session_store.revoke_user_sessions", AsyncMock(return_value=2)
        ) as mock_r,
        patch("app.api.identity.admin_identity.activity.record", AsyncMock()),
    ):
        resp = await admin_client.post("/api/v1/admin/users/target-user-id/revoke-sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["revoked_count"] == 2
    mock_r.assert_called_once_with("target-user-id", revoke_keystone=True)


@pytest.mark.asyncio
async def test_admin_revoke_sessions_forbidden_for_non_admin(client):
    """일반 사용자가 revoke-sessions 호출 시 403."""
    from tests.conftest import make_token_info

    normal_info = make_token_info(is_system_admin=False)
    with patch("app.api.identity.admin_identity.get_token_info", return_value=normal_info):
        resp = await client.post("/api/v1/admin/users/target-user-id/revoke-sessions")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_refresh_carries_origin(client):
    """refresh 토큰 회전 시 origin_ip/origin_fp가 새 세션으로 그대로 운반된다."""
    from app.services import jwt_service

    refresh_str, r_jti, r_exp = jwt_service.sign_refresh("user1")

    sess = _make_sess(origin_ip="10.1.1.1", origin_fp="fp_carried")
    kc_info = {
        "token": "new-ks",
        "project_id": "proj",
        "project_name": "Test",
        "user_id": "user1",
        "username": "testuser",
        "roles": ["member"],
        "is_system_admin": False,
    }
    stored_sessions = {}

    async def _mock_store(
        jti, keystone_token, project_id, user_id, exp, auth_method="password", origin_ip="", origin_fp="", **kwargs
    ):
        stored_sessions["origin_ip"] = origin_ip
        stored_sessions["origin_fp"] = origin_fp

    with (
        patch("app.api.identity.auth.session_store.get_session", AsyncMock(return_value=sess)),
        patch("app.api.identity.auth.session_store.delete_session", AsyncMock()),
        patch("app.api.identity.auth.session_store.store_session", side_effect=_mock_store),
        patch("app.api.identity.auth.asyncio.to_thread", new=AsyncMock(return_value=kc_info)),
    ):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_str},
        )
    assert resp.status_code == 200
    assert stored_sessions.get("origin_ip") == "10.1.1.1"
    assert stored_sessions.get("origin_fp") == "fp_carried"


@pytest.mark.asyncio
async def test_refresh_blocked_for_blacklisted_session(client):
    """블랙리스트 세션으로 refresh 시도 시 401."""
    from app.services import jwt_service

    refresh_str, r_jti, _ = jwt_service.sign_refresh("user1")
    blacklisted = _make_sess(blacklisted=True)
    with patch("app.api.identity.auth.session_store.get_session", AsyncMock(return_value=blacklisted)):
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_str})
    assert resp.status_code == 401
    assert "차단" in resp.json()["detail"]
