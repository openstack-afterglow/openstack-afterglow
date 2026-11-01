"""인증 보안 테스트 — 토큰 만료/변조/형식 오류, 비밀번호 제약."""

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.main import app


@pytest.mark.asyncio
async def test_missing_token_returns_401():
    """X-Auth-Token 헤더 없으면 401을 반환해야 한다."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/k3s/clusters")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_empty_token_returns_401():
    """빈 X-Auth-Token 헤더는 401을 반환해야 한다."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/k3s/clusters", headers={"X-Auth-Token": ""})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_malformed_token_returns_401():
    """무작위 문자열 토큰은 401을 반환해야 한다."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/k3s/clusters", headers={"X-Auth-Token": "totally-invalid-token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sql_injection_in_token_returns_401():
    """SQL injection 형식의 토큰은 401을 반환해야 한다."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/k3s/clusters",
            headers={"X-Auth-Token": "' OR '1'='1"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_oversized_token_returns_401():
    """매우 긴 토큰은 401을 반환해야 한다 (DoS 방지 확인)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/k3s/clusters",
            headers={"X-Auth-Token": "A" * 10000},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoints_without_token():
    """주요 보호 엔드포인트들이 인증 없이 401을 반환하는지 일괄 확인."""
    protected_paths = [
        ("GET", "/api/v1/k3s/clusters"),
        ("GET", "/api/v1/instances"),
        ("GET", "/api/v1/volumes"),
        ("GET", "/api/v1/networks"),
        ("GET", "/api/v1/flavors"),
        ("GET", "/api/v1/keypairs"),
        ("GET", "/api/v1/images"),
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for method, path in protected_paths:
            resp = await ac.request(method, path)
            assert resp.status_code == 401, f"{method} {path} should return 401, got {resp.status_code}"


class TestChangePasswordRequestValidation:
    def test_oversized_new_password_rejected(self):
        """1024자 초과 새 비밀번호는 Pydantic에서 거부되어야 한다."""
        from app.api.identity.profile import ChangePasswordRequest

        with pytest.raises(ValidationError):
            ChangePasswordRequest(current_password="correct", new_password="A" * 1025)

    def test_oversized_current_password_rejected(self):
        """1024자 초과 현재 비밀번호도 거부되어야 한다."""
        from app.api.identity.profile import ChangePasswordRequest

        with pytest.raises(ValidationError):
            ChangePasswordRequest(current_password="A" * 1025, new_password="newpass")

    def test_empty_new_password_rejected(self):
        """빈 새 비밀번호는 거부되어야 한다."""
        from app.api.identity.profile import ChangePasswordRequest

        with pytest.raises(ValidationError):
            ChangePasswordRequest(current_password="correct", new_password="")

    def test_valid_password_accepted(self):
        """유효한 비밀번호 조합은 통과해야 한다."""
        from app.api.identity.profile import ChangePasswordRequest

        req = ChangePasswordRequest(current_password="old-pass-123", new_password="new-pass-456")
        assert req.new_password == "new-pass-456"

    def test_max_length_password_accepted(self):
        """정확히 1024자 비밀번호는 허용되어야 한다."""
        from app.api.identity.profile import ChangePasswordRequest

        req = ChangePasswordRequest(current_password="A" * 1024, new_password="B" * 1024)
        assert len(req.new_password) == 1024


@pytest.mark.asyncio
async def test_admin_endpoint_non_admin_returns_403(client):
    """일반 사용자가 admin 엔드포인트에 접근하면 403을 반환해야 한다."""
    resp = await client.get("/api/v1/admin/overview")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_change_password_oversized_payload_returns_422(client):
    """매우 큰 비밀번호 payload는 422 검증 오류를 반환해야 한다."""
    resp = await client.post(
        "/api/v1/profile/password",
        json={"current_password": "A" * 1025, "new_password": "valid"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_change_password_empty_new_password_returns_422(client):
    """빈 new_password는 422를 반환해야 한다."""
    resp = await client.post(
        "/api/v1/profile/password",
        json={"current_password": "correct", "new_password": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_change_password_validation_does_not_return_credentials(client):
    current = "current-secret-do-not-echo"
    new = "new-secret-do-not-echo-" * 60
    response = await client.post("/api/v1/profile/password", json={"current_password": current, "new_password": new})
    assert response.status_code == 422
    assert current not in response.text
    assert new not in response.text
