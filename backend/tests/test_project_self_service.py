"""셀프서비스 프로젝트 생성 + 이메일 초대 시스템 단위 테스트."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info
from app.main import app
from app.rate_limit import limiter as _rate_limiter

_rate_limiter.enabled = False

PROJECT_ID = "proj-selfservice-123"


def make_token_info(is_manager=False, is_admin=False, user_id="user-abc", email="user@example.com"):
    return {
        "token": "test-token",
        "project_id": PROJECT_ID,
        "project_name": "test-project",
        "user_id": user_id,
        "username": "testuser",
        "email": email,
        "roles": ["member"],
        "is_system_admin": is_admin,
    }


# ─── /api/projects ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_project_requires_auth():
    """인증 없이 프로젝트 생성 불가."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/projects", json={"name": "MyProject"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_project_success():
    """프로젝트 생성 성공: Keystone 프로젝트 생성 + DB manager 등록."""
    mock_ks = MagicMock()
    mock_project = MagicMock()
    mock_project.id = "new-proj-id"
    mock_project.name = "MyProject"
    mock_project.description = ""
    mock_ks.projects.create.return_value = mock_project
    mock_ks.roles.list.return_value = [MagicMock(id="role-member-id")]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.add = MagicMock()

    async def override_token():
        return make_token_info()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_token_info] = override_token
    from app.database import get_session

    app.dependency_overrides[get_session] = override_session

    with (
        patch("app.services.keystone._get_admin_ks_client", return_value=mock_ks),
        patch("app.services.keystone.get_admin_connection_for_project", side_effect=Exception("no monitoring")),
        patch("app.services.activity.record", new_callable=AsyncMock),
        patch("app.services.project_service.cache.invalidate", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Auth-Token": "test-token"},
        ) as ac:
            resp = await ac.post("/api/v1/projects", json={"name": "MyProject"})

    app.dependency_overrides.clear()
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "new-proj-id"
    assert data["name"] == "MyProject"


@pytest.mark.asyncio
async def test_create_project_empty_name_rejected():
    """빈 이름으로 프로젝트 생성 거부."""
    mock_session = AsyncMock()

    async def override_token():
        return make_token_info()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_token_info] = override_token
    from app.database import get_session

    app.dependency_overrides[get_session] = override_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Auth-Token": "test-token"},
    ) as ac:
        resp = await ac.post("/api/v1/projects", json={"name": "   "})
    app.dependency_overrides.clear()
    assert resp.status_code == 422


# ─── 초대 생성 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_invitation_requires_manager():
    """manager가 아닌 사용자는 초대 불가 (403)."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    async def override_token():
        return make_token_info(is_manager=False, is_admin=False)

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_token_info] = override_token
    from app.database import get_session

    app.dependency_overrides[get_session] = override_session

    with patch("app.database.get_session_factory", return_value=None):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Auth-Token": "test-token"},
        ) as ac:
            resp = await ac.post(
                f"/api/v1/projects/{PROJECT_ID}/invitations",
                json={"email": "invite@example.com"},
            )
    app.dependency_overrides.clear()
    assert resp.status_code in (403, 503)


@pytest.mark.asyncio
async def test_create_invitation_success():
    """manager가 초대 생성 성공 — 이메일 미발송(SMTP 비활성) 시에도 201."""
    mock_ks = MagicMock()
    mock_user = MagicMock()
    mock_user.id = "invited-user-id"
    mock_user.name = "invite_user"
    mock_user.email = "invite@example.com"
    mock_ks.users.list.return_value = [mock_user]
    mock_ks.projects.get.return_value = MagicMock(name="TestProject", id=PROJECT_ID)

    mock_session = AsyncMock()
    mock_invitation = MagicMock()
    mock_invitation.id = 1
    mock_invitation.created_at = datetime.now(UTC)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    async def override_token():
        return make_token_info(is_admin=True)

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_token_info] = override_token
    from app.database import get_session

    app.dependency_overrides[get_session] = override_session

    with (
        patch("app.services.keystone._get_admin_ks_client", return_value=mock_ks),
        patch("app.services.activity.record", new_callable=AsyncMock),
        patch("app.services.project_service.is_project_manager", new_callable=AsyncMock, return_value=True),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Auth-Token": "test-token"},
        ) as ac:
            resp = await ac.post(
                f"/api/v1/projects/{PROJECT_ID}/invitations",
                json={"email": "invite@example.com"},
            )
    app.dependency_overrides.clear()
    assert resp.status_code == 201


# ─── 초대 수락/거절 ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_accept_invitation_email_mismatch():
    """수락자 이메일 != invited_email → 403."""
    from app.services.project_service import accept_invitation

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    mock_inv = MagicMock()
    mock_inv.token_hash = token_hash
    mock_inv.status = "pending"
    mock_inv.invited_email = "other@example.com"
    mock_inv.expires_at = datetime.now(UTC) + timedelta(days=7)

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_inv)))

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await accept_invitation(
            plaintext_token=token,
            accepting_user_id="user-xyz",
            accepting_email="wrong@example.com",
            session=mock_session,
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_accept_invitation_expired():
    """만료된 초대 수락 시 410 반환."""
    from app.services.project_service import accept_invitation

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    mock_inv = MagicMock()
    mock_inv.token_hash = token_hash
    mock_inv.status = "pending"
    mock_inv.invited_email = "user@example.com"
    expired = datetime.now(UTC) - timedelta(days=1)
    mock_inv.expires_at = expired

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_inv)))
    mock_session.commit = AsyncMock()

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await accept_invitation(
            plaintext_token=token,
            accepting_user_id="user-abc",
            accepting_email="user@example.com",
            session=mock_session,
        )
    assert exc_info.value.status_code == 410


@pytest.mark.asyncio
async def test_accept_invitation_invalid_token():
    """존재하지 않는 토큰 → 404."""
    from app.services.project_service import accept_invitation

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await accept_invitation("nonexistent-token", "user", "user@example.com", mock_session)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_decline_invitation_success():
    """정상 거절 — status가 declined로 변경."""
    from app.services.project_service import decline_invitation

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    mock_inv = MagicMock()
    mock_inv.token_hash = token_hash
    mock_inv.status = "pending"

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_inv)))
    mock_session.commit = AsyncMock()

    result = await decline_invitation(token, mock_session)
    assert result["status"] == "declined"
    assert mock_inv.status == "declined"


@pytest.mark.asyncio
async def test_decline_invitation_idempotent():
    """이미 수락된 초대 거절 시도 → 현재 상태 반환 (오류 없음)."""
    from app.services.project_service import decline_invitation

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    mock_inv = MagicMock()
    mock_inv.token_hash = token_hash
    mock_inv.status = "accepted"

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_inv)))

    result = await decline_invitation(token, mock_session)
    assert result["status"] == "accepted"


# ─── 매니저 관리 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demote_last_manager_blocked():
    """마지막 manager 해제 시도 → 409."""
    from app.services.project_service import demote_manager

    last_manager = MagicMock()
    last_manager.user_id = "user-abc"

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[last_manager]))))
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await demote_manager(PROJECT_ID, "user-abc", mock_session)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_system_admin_can_invite():
    """system admin은 manager가 아니어도 초대 가능."""
    mock_ks = MagicMock()
    mock_ks.users.list.return_value = []
    mock_ks.projects.get.return_value = MagicMock(name="TestProject")

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    async def override_token():
        return make_token_info(is_admin=True)

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_token_info] = override_token
    from app.database import get_session

    app.dependency_overrides[get_session] = override_session

    with (
        patch("app.services.keystone._get_admin_ks_client", return_value=mock_ks),
        patch("app.services.activity.record", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Auth-Token": "test-token"},
        ) as ac:
            resp = await ac.post(
                f"/api/v1/projects/{PROJECT_ID}/invitations",
                json={"email": "new@example.com"},
            )
    app.dependency_overrides.clear()
    assert resp.status_code == 201


# ─── 이메일 서비스 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_email_skipped_when_smtp_disabled(monkeypatch):
    """SMTP 비활성 시 이메일 전송 건너뜀 — False 반환."""
    from app.services.email_service import send_email

    monkeypatch.setenv("SMTP_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()

    result = await send_email("user@example.com", "Test", "<p>hi</p>", "hi")
    assert result is False
    get_settings.cache_clear()
