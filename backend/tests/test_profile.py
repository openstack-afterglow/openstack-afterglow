"""프로필 API 단위 테스트."""

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from keystoneauth1.exceptions.http import Unauthorized

from app.main import app
from app.services.keystone import PasswordRejected


def make_user_obj(user_id: str = "test-user-123", name: str = "testuser") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.name = name
    u.email = "test@example.com"
    u.description = "test user"
    u.default_project_id = "test-project-123"
    return u


@pytest.fixture
def password_native():
    session = MagicMock()
    session.post.return_value.status_code = 204
    proof = {"user_id": "test-user-123", "identity_domain_id": "default", "token": "exact-current-proof"}
    with (
        patch("app.api.identity.profile.keystone.authenticate", return_value=proof) as authenticate,
        patch("app.api.identity.profile.keystone.native_transport.create_session", return_value=session) as create,
        patch("app.api.identity.profile.keystone.get_settings") as settings,
    ):
        settings.return_value.os_auth_url = "https://native.test/v3"
        settings.return_value.ssl_verify = True
        yield authenticate, create, session


@pytest.mark.asyncio
async def test_get_profile(client, mock_conn):
    mock_conn.identity.get_user.return_value = make_user_obj()
    resp = await client.get("/api/v1/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "test-user-123"
    assert data["name"] == "testuser"


@pytest.mark.asyncio
async def test_profile_email_change_requires_owner_verification(client, mock_conn):
    current = make_user_obj()
    mock_conn.identity.get_user.return_value = current
    response = await client.patch("/api/v1/profile", json={"email": "other-owner@example.com"})
    assert response.status_code == 409
    assert response.json()["detail"] == "email_verification_required"
    mock_conn.identity.update_user.assert_not_called()


@pytest.mark.asyncio
async def test_update_profile_no_fields(client, mock_conn):
    """수정할 항목 없으면 400."""
    resp = await client.patch("/api/v1/profile", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_change_password_wrong_current(client, mock_conn):
    """현재 패스워드 불일치 시 401."""
    with patch("app.api.identity.profile.keystone.authenticate", side_effect=PasswordRejected()):
        resp = await client.post(
            "/api/v1/profile/password",
            json={
                "current_password": "WrongPass",
                "new_password": "NewPass456!",
            },
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "proof",
    [
        {"user_id": "other-account", "identity_domain_id": "default", "token": "proof"},
        {"user_id": "test-user-123", "identity_domain_id": "other-home", "token": "proof"},
    ],
)
async def test_password_change_rejects_foreign_authenticated_subject(client, mock_conn, password_native, proof):
    authenticate, create, _ = password_native
    authenticate.return_value = proof
    response = await client.post(
        "/api/v1/profile/password", json={"current_password": "valid", "new_password": "replacement"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "password_identity_mismatch"
    create.assert_not_called()
    mock_conn.identity.update_user.assert_not_called()


@pytest.mark.asyncio
async def test_password_verifier_outage_does_not_modify_account(client, mock_conn):
    with patch("app.api.identity.profile.keystone.authenticate", side_effect=ConnectionError("directory down")):
        response = await client.post(
            "/api/v1/profile/password", json={"current_password": "valid", "new_password": "replacement"}
        )
    assert response.status_code == 503
    mock_conn.identity.update_user.assert_not_called()


@pytest.mark.asyncio
async def test_get_profile_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/profile")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_profile_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch("/api/v1/profile", json={"email": "x@x.com"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_change_password_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/profile/password", json={"current_password": "a", "new_password": "b"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_password_change_requires_native_proof_token(client, password_native):
    password_native[0].return_value.pop("token")
    response = await client.post(
        "/api/v1/profile/password", json={"current_password": "valid", "new_password": "replacement"}
    )
    assert response.status_code == 503
    password_native[1].assert_not_called()


@pytest.mark.asyncio
async def test_password_change_rejects_non_password_unauthorized_proof(client, password_native):
    password_native[0].side_effect = Unauthorized("Scoped authentication proof")
    response = await client.post(
        "/api/v1/profile/password", json={"current_password": "valid", "new_password": "replacement"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "password_identity_mismatch"
    password_native[1].assert_not_called()
