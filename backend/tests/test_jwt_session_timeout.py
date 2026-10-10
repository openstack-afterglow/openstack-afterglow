"""B2: JWT 경로 세션 타임아웃 적용 테스트."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

# ──────────────────────────────────────────────────────────────────
# 공통 상수 / 헬퍼
# ──────────────────────────────────────────────────────────────────

_KEYSTONE_TOKEN = "ks-token-timeout-test"
_KS_DATA = {
    "token": _KEYSTONE_TOKEN,
    "project_id": "proj-timeout",
    "project_name": "timeout-project",
    "user_id": "user-timeout",
    "username": "bob",
    "expires_at": "2099-01-01T00:00:00+00:00",
    "roles": ["member"],
    "is_system_admin": False,
}


@pytest.fixture
def _ks_authenticate():
    with patch("app.api.identity.auth.keystone.authenticate", return_value=dict(_KS_DATA)) as m:
        yield m


@pytest.fixture
def _ks_get_user():
    from unittest.mock import MagicMock

    user_mock = MagicMock()
    user_mock.default_project_id = ""
    conn_mock = MagicMock()
    conn_mock.identity.get_user.return_value = user_mock
    with patch("app.api.identity.auth.keystone.get_openstack_connection", return_value=conn_mock):
        yield conn_mock


@pytest.fixture
def _ks_validate_ok():
    with patch(
        "app.api.deps._cached_validate",
        new=AsyncMock(return_value=dict(_KS_DATA)),
    ) as m:
        yield m


# ──────────────────────────────────────────────────────────────────
# JWT 경로 세션 타임아웃 테스트
# ──────────────────────────────────────────────────────────────────


class TestJwtSessionTimeout:
    """JWT 경로에서 세션 타임아웃이 올바르게 적용되는지 확인."""

    @pytest.mark.asyncio
    async def test_jwt_path_calls_session_timeout(self, _ks_authenticate, _ks_get_user, _ks_validate_ok):
        """`_resolve_jwt_token_info`가 `_check_session_timeout`을 호출하는지 확인.

        로그인 후 /me 에 Bearer JWT로 접근할 때 타임아웃 검증 함수가 호출되어야 한다.
        로그인 자체는 타임아웃을 호출하지 않으므로 /me 호출 시 count==1 이어야 한다.
        """
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        timeout_mock = AsyncMock()
        with patch("app.api.deps._check_session_timeout", timeout_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                login = await ac.post(
                    "/api/v1/auth/login",
                    json={"username": "bob", "password": "pw", "project_name": "timeout-project"},
                )
                assert login.status_code == 200
                access = login.json()["token"]

                # 로그인 단계에서는 타임아웃 함수가 호출되지 않아야 한다
                assert timeout_mock.await_count == 0

                me = await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
                assert me.status_code == 200

        # /me 접근 1회 → _check_session_timeout 1회 호출
        assert timeout_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_expired_session_raises_401(self, _ks_authenticate, _ks_get_user, _ks_validate_ok):
        """타임아웃된 세션으로 JWT 인증 시 401을 반환해야 한다."""
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            login = await ac.post(
                "/api/v1/auth/login",
                json={"username": "bob", "password": "pw", "project_name": "timeout-project"},
            )
            assert login.status_code == 200
            access = login.json()["token"]

        # 타임아웃 발생을 시뮬레이션: HTTPException(401) 발생
        timeout_expired = AsyncMock(
            side_effect=HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해 주세요.")
        )
        with patch("app.api.deps._check_session_timeout", timeout_expired):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                me = await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})

        assert me.status_code == 401
        assert "만료" in me.json()["detail"]

    @pytest.mark.asyncio
    async def test_refresh_endpoint_checks_timeout(self, _ks_authenticate, _ks_get_user):
        """refresh 엔드포인트도 타임아웃 검증을 수행해야 한다."""
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        # Keystone validate_token은 asyncio.to_thread로 호출되므로 동기 mock 사용
        with patch(
            "app.api.identity.auth.keystone.validate_token",
            return_value=dict(_KS_DATA),
        ):
            timeout_mock = AsyncMock(return_value=time.time())
            with patch("app.api.identity.auth._check_session_timeout", timeout_mock):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    login = await ac.post(
                        "/api/v1/auth/login",
                        json={"username": "bob", "password": "pw", "project_name": "timeout-project"},
                    )
                    assert login.status_code == 200
                    refresh_token = login.json()["refresh_token"]

                    # 로그인 시 refresh 엔드포인트는 호출되지 않으므로 count == 0
                    assert timeout_mock.await_count == 0

                    r = await ac.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
                    assert r.status_code == 200

            # /refresh 호출 1회 → _check_session_timeout 1회 호출
            assert timeout_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_refresh_blocked_when_session_timed_out(self, _ks_authenticate, _ks_get_user):
        """타임아웃된 세션으로 refresh 시도 시 401을 반환해야 한다."""
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            login = await ac.post(
                "/api/v1/auth/login",
                json={"username": "bob", "password": "pw", "project_name": "timeout-project"},
            )
            assert login.status_code == 200
            refresh_token = login.json()["refresh_token"]

        timeout_expired = AsyncMock(
            side_effect=HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해 주세요.")
        )
        with patch("app.api.identity.auth._check_session_timeout", timeout_expired):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                r = await ac.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

        assert r.status_code == 401
        assert "만료" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_jwt_timeout_uses_refresh_jti_hash(self, _ks_authenticate, _ks_get_user, _ks_validate_ok):
        """JWT 경로 타임아웃 키가 refresh_jti의 SHA-256 해시임을 확인.

        X-Auth-Token 경로(Keystone 토큰 해시)와 독립적 네임스페이스를 가진다.
        """
        import hashlib

        from app.services import jwt_service

        captured_args: list[tuple[str, str]] = []

        async def _capture_timeout(token_hash: str, project_id: str, **_kwargs) -> None:
            captured_args.append((token_hash, project_id))

        with patch("app.api.deps._check_session_timeout", side_effect=_capture_timeout):
            from httpx import ASGITransport, AsyncClient

            from app.main import app

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                login = await ac.post(
                    "/api/v1/auth/login",
                    json={"username": "bob", "password": "pw", "project_name": "timeout-project"},
                )
                assert login.status_code == 200
                access = login.json()["token"]

                await ac.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})

        # 호출 인자 검증: token_hash는 refresh_jti의 sha256이어야 한다
        assert len(captured_args) == 1
        used_hash, used_project = captured_args[0]

        # access JWT에서 rjti 추출해 hash 비교
        payload = jwt_service.verify_access(access)
        rjti = payload["rjti"]
        expected_hash = hashlib.sha256(rjti.encode()).hexdigest()

        assert used_hash == expected_hash
        assert used_project == "proj-timeout"
