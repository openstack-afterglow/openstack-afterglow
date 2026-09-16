"""JWT access+refresh 토큰 통합 단위 테스트."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis as fakeredis
import pytest

# ──────────────────────────────────────────────────────────────────
# 공통 픽스처 / 헬퍼
# ──────────────────────────────────────────────────────────────────

_KEYSTONE_TOKEN = "ks-token-abcdefg"
_KS_DATA = {
    "token": _KEYSTONE_TOKEN,
    "project_id": "proj-1",
    "project_name": "myproject",
    "user_id": "user-1",
    "username": "alice",
    "expires_at": "2099-01-01T00:00:00+00:00",
    "roles": ["member"],
    "is_system_admin": False,
}


def _make_fake_redis():
    return fakeredis.FakeRedis()


@pytest.fixture(autouse=True)
def patch_redis(monkeypatch):
    """모든 테스트에서 fakeredis를 사용하도록 패치."""
    fake = _make_fake_redis()

    async def _get_fake():
        return fake

    monkeypatch.setattr("app.services.cache._get_redis", _get_fake)
    return fake


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    """테스트용 짧은 TTL 설정."""
    from app.config import Settings

    s = Settings.model_construct(
        secret_key="test-secret-key-for-jwt-tests",
        jwt_access_ttl=900,
        jwt_refresh_ttl=604800,
        session_timeout_seconds=3600,
        session_warning_before_seconds=300,
        session_absolute_timeout=14400,
    )
    monkeypatch.setattr("app.config.get_settings", lambda: s)
    monkeypatch.setattr("app.services.jwt_service.get_settings", lambda: s)
    monkeypatch.setattr("app.services.session_store.get_settings", lambda: s, raising=False)


# ──────────────────────────────────────────────────────────────────
# jwt_service 단위 테스트
# ──────────────────────────────────────────────────────────────────


class TestJwtService:
    def test_access_roundtrip(self):
        from app.services.jwt_service import sign_access, verify_access

        token, jti, exp = sign_access(
            user_id="u1",
            username="alice",
            project_id="p1",
            project_name="proj",
            refresh_jti="rjti-123",
        )
        payload = verify_access(token)
        assert payload["sub"] == "u1"
        assert payload["project_id"] == "p1"
        assert payload["rjti"] == "rjti-123"
        assert payload["jti"] == jti
        assert payload["exp"] == exp

    def test_access_payload_no_auth_claims(self):
        """JWT payload에 권한 정보(roles, is_system_admin)가 포함되지 않아야 한다."""
        from app.services.jwt_service import sign_access, verify_access

        token, _, _ = sign_access(
            user_id="u1",
            username="alice",
            project_id="p1",
            project_name="proj",
            refresh_jti="rjti-1",
        )
        payload = verify_access(token)
        assert "roles" not in payload
        assert "is_system_admin" not in payload

    def test_refresh_roundtrip(self):
        from app.services.jwt_service import sign_refresh, verify_refresh

        token, jti, exp = sign_refresh("u1")
        payload = verify_refresh(token)
        assert payload["sub"] == "u1"
        assert payload["jti"] == jti
        assert payload["type"] == "refresh"

    def test_verify_access_expired(self, monkeypatch):
        import jwt

        from app.services.jwt_service import sign_access, verify_access

        token, _, _ = sign_access("u1", "alice", "p1", "proj", "rjti")
        # 만료 강제: exp를 과거로 덮어쓰기
        payload = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
        payload["exp"] = int(time.time()) - 10
        tampered = jwt.encode(payload, "test-secret-key-for-jwt-tests", algorithm="HS256")
        with pytest.raises(jwt.ExpiredSignatureError):
            verify_access(tampered)

    def test_verify_refresh_wrong_type(self):
        import jwt

        from app.services.jwt_service import sign_access, verify_refresh

        # access 토큰을 refresh 경로로 검증하면 실패
        token, _, _ = sign_access("u1", "alice", "p1", "proj", "rjti")
        with pytest.raises(jwt.InvalidTokenError):
            verify_refresh(token)


# ──────────────────────────────────────────────────────────────────
# session_store 단위 테스트
# ──────────────────────────────────────────────────────────────────


class TestSessionStore:
    @pytest.mark.asyncio
    async def test_store_and_get(self):
        from app.services.session_store import get_session, store_session

        exp = int(time.time()) + 600
        await store_session("jti-abc", "ks-tok", "proj-1", "user-1", exp)
        sess = await get_session("jti-abc")
        assert sess is not None
        assert sess["keystone_token"] == "ks-tok"
        assert sess["project_id"] == "proj-1"

    @pytest.mark.asyncio
    async def test_delete_session(self):
        from app.services.session_store import delete_session, get_session, store_session

        exp = int(time.time()) + 600
        await store_session("jti-del", "ks-tok", "proj-1", "user-1", exp)
        await delete_session("jti-del")
        assert await get_session("jti-del") is None

    @pytest.mark.asyncio
    async def test_missing_returns_none(self):
        from app.services.session_store import get_session

        assert await get_session("nonexistent-jti") is None

    @pytest.mark.asyncio
    async def test_revoke_user_sessions(self):
        """revoke_user_sessions는 해당 유저의 모든 세션을 삭제하고 다른 유저는 건드리지 않는다."""
        from app.services.session_store import get_session, revoke_user_sessions, store_session

        exp = int(time.time()) + 600
        await store_session("jti-rev-1", "ks-tok-1", "proj-1", "user-42", exp)
        await store_session("jti-rev-2", "ks-tok-2", "proj-1", "user-42", exp)
        await store_session("jti-other", "ks-tok-3", "proj-1", "user-99", exp)

        count = await revoke_user_sessions("user-42")
        assert count == 2
        assert await get_session("jti-rev-1") is None
        assert await get_session("jti-rev-2") is None
        assert await get_session("jti-other") is not None

    @pytest.mark.asyncio
    async def test_revoke_user_sessions_empty(self):
        """세션이 없는 유저에 대한 revoke는 0을 반환해야 한다."""
        from app.services.session_store import revoke_user_sessions

        count = await revoke_user_sessions("user-nonexistent")
        assert count == 0


# ──────────────────────────────────────────────────────────────────
# HTTP 엔드포인트 통합 테스트
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def _ks_authenticate():
    with patch("app.api.identity.auth.keystone.authenticate", return_value=dict(_KS_DATA)) as m:
        yield m


@pytest.fixture
def _ks_get_user():
    user_mock = MagicMock()
    user_mock.default_project_id = ""
    conn_mock = MagicMock()
    conn_mock.identity.get_user.return_value = user_mock
    with patch("app.api.identity.auth.keystone.get_openstack_connection", return_value=conn_mock):
        yield conn_mock


@pytest.fixture
def _ks_validate_ok():
    with patch(
        "app.api.identity.auth.keystone.validate_token",
        return_value=dict(_KS_DATA),
    ) as m:
        yield m


@pytest.fixture
def _rate_limiter_off():
    with patch("app.rate_limit.limiter.limit", return_value=lambda f: f):
        yield


@pytest.mark.asyncio
async def test_login_returns_access_and_refresh(_ks_authenticate, _ks_get_user, _rate_limiter_off):
    """로그인 응답에 token(access JWT)과 refresh_token이 모두 포함되어야 한다."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pw", "project_name": "myproject"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["refresh_token"]
    assert body["expires_at"]
    # token은 JWT 형식 (점 3개)
    assert body["token"].count(".") == 2
    assert body["refresh_token"].count(".") == 2


@pytest.mark.asyncio
async def test_bearer_access_protects_me_endpoint(_ks_authenticate, _ks_get_user, _ks_validate_ok, _rate_limiter_off):
    """Bearer access JWT로 /me 엔드포인트에 접근 가능해야 한다."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pw", "project_name": "myproject"},
        )
        access = login.json()["token"]
        me = await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


@pytest.mark.asyncio
async def test_legacy_x_auth_token_rejected(_rate_limiter_off):
    """X-Auth-Token 레거시 헤더는 더 이상 허용되지 않으며 401을 반환해야 한다."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        me = await ac.get(
            "/api/v1/auth/me",
            headers={"X-Auth-Token": _KEYSTONE_TOKEN, "X-Project-Id": "proj-1"},
        )
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_expired_access_jwt_returns_401(_rate_limiter_off):
    """만료된 access JWT로 요청 시 401을 반환해야 한다."""
    import jwt as pyjwt
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    payload = {
        "sub": "user-1",
        "jti": "test-jti",
        "rjti": "rjti-x",
        "exp": int(time.time()) - 10,
        "iat": int(time.time()) - 920,
        "username": "alice",
        "project_id": "proj-1",
        "project_name": "myproject",
        "roles": ["member"],
        "is_system_admin": False,
    }
    expired_token = pyjwt.encode(payload, "test-secret-key-for-jwt-tests", algorithm="HS256")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_tokens(_ks_authenticate, _ks_get_user, _ks_validate_ok, _rate_limiter_off):
    """refresh 호출 시 새 토큰 쌍이 발급되고, 기존 refresh로 재호출 시 401."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pw", "project_name": "myproject"},
        )
        old_refresh = login.json()["refresh_token"]
        old_access = login.json()["token"]

        # 첫 refresh → 성공
        r1 = await ac.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert r1.status_code == 200
        new_access = r1.json()["token"]
        new_refresh = r1.json()["refresh_token"]
        assert new_access != old_access
        assert new_refresh != old_refresh

        # 같은 refresh 재사용 → 401 (토큰 회전)
        r2 = await ac.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert r2.status_code == 401


@pytest.mark.asyncio
async def test_refresh_keystone_transient_failure_returns_503_and_preserves_session(
    _ks_authenticate, _ks_get_user, _rate_limiter_off
):
    """Keystone 일시적 장애 시 refresh는 503을 반환하고 세션을 유지하여, 장애 복구 후 재시도 시 성공해야 한다."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pw", "project_name": "myproject"},
        )
        refresh_token = login.json()["refresh_token"]

        # Keystone 일시적 장애 (연결 실패 / 네트워크 예외) 발생
        with patch(
            "app.api.identity.auth.keystone.validate_token",
            side_effect=ConnectionError("Keystone transient connection failure"),
        ):
            r_transient = await ac.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

        # 503 Service Unavailable 이어야 하며 세션이 삭제되지 않아야 함
        assert r_transient.status_code == 503

        # Keystone 장애 복구 후 동일한 refresh_token으로 재시도 → 성공 (200) 및 토큰 회전
        with patch("app.api.identity.auth.keystone.validate_token", return_value=dict(_KS_DATA)):
            r_recovered = await ac.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

        assert r_recovered.status_code == 200
        assert "token" in r_recovered.json()
        assert r_recovered.json()["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_logout_revokes_refresh_session(_ks_authenticate, _ks_get_user, _ks_validate_ok, _rate_limiter_off):
    """로그아웃 후 refresh 토큰으로 갱신 시도 시 401을 반환해야 한다."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    with patch("app.api.identity.auth.keystone.revoke_token"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            login = await ac.post(
                "/api/v1/auth/login",
                json={"username": "alice", "password": "pw", "project_name": "myproject"},
            )
            access = login.json()["token"]
            refresh = login.json()["refresh_token"]

            logout = await ac.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {access}"},
            )
            assert logout.status_code == 200

            # 로그아웃 후 refresh 사용 → 401
            r = await ac.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
            assert r.status_code == 401


@pytest.mark.asyncio
async def test_no_auth_header_returns_401(_rate_limiter_off):
    """인증 헤더 없이 protected 엔드포인트 접근 시 401."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bearer_jwt_uses_cached_validate_not_payload(_ks_authenticate, _ks_get_user, _rate_limiter_off):
    """Bearer JWT 요청은 JWT payload가 아닌 _cached_validate(Keystone live)에서 권한 정보를 읽어야 한다."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    # 로그인: JWT payload에 권한 정보 없음
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pw", "project_name": "myproject"},
        )
    access = login.json()["token"]

    # Keystone이 is_system_admin=True를 반환하도록 모킹
    elevated_ks_data = dict(_KS_DATA, is_system_admin=True, roles=["admin", "member"])
    with patch("app.api.deps._cached_validate", new=AsyncMock(return_value=elevated_ks_data)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            me = await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})

    assert me.status_code == 200
    # JWT payload에는 is_system_admin이 없지만 Keystone mock이 True를 반환하므로 True여야 함
    assert me.json()["is_system_admin"] is True


@pytest.mark.asyncio
async def test_protected_request_cached_validate_transient_failure_yields_503_and_preserves_session(
    _ks_authenticate, _ks_get_user, _rate_limiter_off
):
    """보호된 엔드포인트 요청 중 _cached_validate 일시적 장애 발생 시 503을 반환하고 refresh 세션을 유지해야 한다."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pw", "project_name": "myproject"},
        )
        assert login.status_code == 200
        access = login.json()["token"]
        refresh_token = login.json()["refresh_token"]

        # _cached_validate 일시적 네트워크/연결 장애 발생
        with patch(
            "app.api.deps._cached_validate", side_effect=ConnectionError("Keystone validation connection failed")
        ):
            resp = await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})

        # session 401이 아닌 503 Service Unavailable을 반환해야 함
        assert resp.status_code == 503

        # 세션이 유지되어 복구 후 refresh가 성공해야 함 (200)
        with patch("app.api.identity.auth.keystone.validate_token", return_value=dict(_KS_DATA)):
            r_refresh = await ac.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

        assert r_refresh.status_code == 200


@pytest.mark.asyncio
async def test_protected_request_cached_validate_unauthorized_yields_401(
    _ks_authenticate, _ks_get_user, _rate_limiter_off
):
    """보호된 엔드포인트 요청 중 _cached_validate에서 keystoneauth Unauthorized 발생 시 401을 반환해야 한다."""
    from httpx import ASGITransport, AsyncClient
    from keystoneauth1.exceptions.http import Unauthorized

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pw", "project_name": "myproject"},
        )
        assert login.status_code == 200
        access = login.json()["token"]

        with patch("app.api.deps._cached_validate", side_effect=Unauthorized("Keystone token unauthorized")):
            resp = await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})

        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_os_conn_constructor_failure_yields_503(
    _ks_authenticate, _ks_get_user, _ks_validate_ok, _rate_limiter_off
):
    """get_os_conn에서 OpenStack connection 생성 실패 시 401이 아닌 503을 반환해야 한다."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pw", "project_name": "myproject"},
        )
        assert login.status_code == 200
        access = login.json()["token"]

        with patch(
            "app.api.deps.keystone.get_openstack_connection", side_effect=Exception("OpenStack SDK connection failed")
        ):
            resp = await ac.get("/api/v1/flavors", headers={"Authorization": f"Bearer {access}"})

        assert resp.status_code == 503
        assert "detail" in resp.json()


@pytest.mark.asyncio
async def test_admin_connection_request_resolves_auth_once(_ks_authenticate, _ks_get_user, _rate_limiter_off):
    """관리자 연결 endpoint의 중첩 의존성은 요청당 Keystone 검증을 한 번만 수행한다."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pw", "project_name": "myproject"},
        )
        assert login.status_code == 200
        access = login.json()["token"]

    admin_info = dict(_KS_DATA, is_system_admin=True, roles=["admin", "member"])
    validate = AsyncMock(return_value=admin_info)
    fake_response = MagicMock()
    fake_response.json.return_value = {"servers": []}
    fake_conn = MagicMock()
    fake_conn.compute.get_endpoint.return_value = "https://nova.example.test/v2.1"
    fake_conn.session.get.return_value = fake_response

    with (
        patch("app.api.deps._cached_validate", new=validate),
        patch("app.api.deps.keystone.get_openstack_connection", return_value=fake_conn),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/admin/all-instances",
                headers={"Authorization": f"Bearer {access}"},
            )

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_marker": None, "count": 0}
    assert validate.await_count == 1


@pytest.mark.asyncio
async def test_system_admin_foreign_target_succeeds_and_never_validates_target(
    _ks_authenticate, _ks_get_user, _rate_limiter_off
):
    """system_admin이 foreign X-Project-Id 요청 시 target rescope를 검증하지 않고 home 권한으로 성공해야 한다."""
    from unittest.mock import AsyncMock

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pw", "project_name": "myproject"},
        )
        assert login.status_code == 200
        access = login.json()["token"]

    admin_home_data = dict(_KS_DATA, is_system_admin=True, project_id="home-proj-id", roles=["admin"])
    cached_validate_mock = AsyncMock(return_value=admin_home_data)

    with patch("app.api.deps._cached_validate", new=cached_validate_mock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access}", "X-Project-Id": "foreign-target-proj-id"},
            )

    assert resp.status_code == 200
    assert resp.json()["project_id"] == "foreign-target-proj-id"
    assert cached_validate_mock.call_count == 1
    assert cached_validate_mock.call_args[0][1] == "proj-1"


@pytest.mark.asyncio
async def test_valid_non_admin_target_unauthorized_yields_403(_ks_authenticate, _ks_get_user, _rate_limiter_off):
    """유효한 세션의 비관리자가 접근 불가 target X-Project-Id로 요청 시 403을 반환해야 한다."""
    from httpx import ASGITransport, AsyncClient
    from keystoneauth1.exceptions.http import Unauthorized

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pw", "project_name": "myproject"},
        )
        assert login.status_code == 200
        access = login.json()["token"]

    non_admin_home_data = dict(_KS_DATA, is_system_admin=False, project_id="home-proj-id")

    async def side_effect(token, project_id):
        if project_id == "foreign-target-proj-id":
            raise Unauthorized("Target project unauthorized")
        return non_admin_home_data

    with patch("app.api.deps._cached_validate", side_effect=side_effect):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access}", "X-Project-Id": "foreign-target-proj-id"},
            )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_foreign_target_invalid_home_yields_401(_ks_authenticate, _ks_get_user, _rate_limiter_off):
    """foreign X-Project-Id 요청 시 home project 검증 실패(Unauthorized)는 401을 반환해야 한다."""
    from httpx import ASGITransport, AsyncClient
    from keystoneauth1.exceptions.http import Unauthorized

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pw", "project_name": "myproject"},
        )
        assert login.status_code == 200
        access = login.json()["token"]

    with patch("app.api.deps._cached_validate", side_effect=Unauthorized("Home session unauthorized")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access}", "X-Project-Id": "foreign-target-proj-id"},
            )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_os_conn_system_admin_foreign_target_scope_and_close(
    _ks_authenticate, _ks_get_user, _rate_limiter_off
):
    """get_os_conn이 system_admin foreign target 시 SDK에는 authenticated home scope를 전달하고 conn에는 target logical scope 및 메타데이터를 설정하며 종료 시 connection을 닫아야 한다."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "pw", "project_name": "myproject"},
        )
        assert login.status_code == 200
        access = login.json()["token"]

    admin_home_data = dict(_KS_DATA, is_system_admin=True, project_id="home-proj-id")
    fake_conn = MagicMock()
    fake_conn.close = MagicMock()

    with (
        patch("app.api.deps._cached_validate", new=AsyncMock(return_value=admin_home_data)),
        patch("app.api.deps.keystone.get_openstack_connection", return_value=fake_conn) as mock_get_conn,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/flavors",
                headers={"Authorization": f"Bearer {access}", "X-Project-Id": "foreign-target-proj-id"},
            )

    assert resp.status_code == 200
    mock_get_conn.assert_called_once()
    assert mock_get_conn.call_args[0][1] == "home-proj-id"
    assert fake_conn._afterglow_project_id == "foreign-target-proj-id"
    assert fake_conn._afterglow_authenticated_project_id == "home-proj-id"
    assert fake_conn._afterglow_is_system_admin is True
    fake_conn.close.assert_called_once()
