"""인증 API 단위 테스트."""

from unittest.mock import AsyncMock, patch

import pytest

from app.api.deps import get_token_info
from app.config import get_settings
from app.main import app
from app.services.keystone import PasswordRejected

pytestmark = pytest.mark.usefixtures("auth_directory")


def make_auth_data() -> dict:
    return {
        "token": "test-token",
        "project_id": "test-project-123",
        "project_name": "test-project",
        "default_project_id": "test-project-123",
        "user_id": "test-user-123",
        "username": "testuser",
        "expires_at": "2099-01-01T00:00:00Z",
        "roles": ["member"],
        "is_system_admin": False,
        "domain_id": "default",
        "domain_name": "Default",
        "identity_domain_id": "accounts",
        "identity_domain_name": "Accounts",
        "is_domain_manager": False,
        "email": "actual@example.test",
    }


# ────── 로그인 ──────


@pytest.mark.asyncio
async def test_login_success(client, auth_directory, native_auth, monkeypatch):
    auth_directory.users["test-user-123"]["default_project_id"] = "test-project-123"
    monkeypatch.setattr("app.api.identity.auth._prewarm_dashboard", AsyncMock())
    monkeypatch.setattr("app.api.identity.auth.record_project_access", AsyncMock())
    monkeypatch.setattr("app.api.identity.auth.activity_svc.record", AsyncMock())
    resp = await client.post("/api/v1/auth/login", json={"username": "testuser", "password": "valid"})
    assert resp.status_code == 200
    data = resp.json()
    from app.services import jwt_service, session_store

    claims = jwt_service.verify_access(data["token"])
    native_session = await session_store.get_session(claims["rjti"])
    assert (data["user_id"], data["identity_domain_id"], data["domain_id"], data["project_id"]) == (
        "test-user-123",
        "accounts",
        "personal",
        "personal-test-user-123",
    )
    assert auth_directory.users["test-user-123"]["default_project_id"] == "test-project-123"
    assert auth_directory.grants["test-user-123"] == ["test-project-123", "other-project-456", "personal-test-user-123"]
    assert (native_session["user_id"], native_session["domain_id"], native_session["project_id"]) == (
        data["user_id"],
        data["domain_id"],
        data["project_id"],
    )


@pytest.mark.asyncio
async def test_login_failure(client):
    with patch("app.api.identity.auth.keystone.authenticate", side_effect=PasswordRejected("auth failed")):
        resp = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "testuser",
                "password": "wrongpassword",
            },
        )
    assert resp.status_code == 401


# ────── /me ──────


@pytest.mark.asyncio
async def test_me(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "test-user-123"
    assert data["username"] == "testuser"


# ────── token/project (rescope) ──────


@pytest.mark.asyncio
async def test_scope_project(client):
    """POST /api/auth/token/project: 접근 가능한 프로젝트로 새 토큰 쌍 발급."""
    kc_info = {
        "token": "new-ks-token",
        "project_id": "other-project-456",
        "project_name": "other-project",
        "user_id": "test-user-123",
        "username": "testuser",
        "roles": ["member"],
        "is_system_admin": False,
        "domain_id": "default",
        "domain_name": "Default",
        "identity_domain_id": "default",
        "identity_domain_name": "Default",
        "is_domain_manager": False,
        "email": "actual@example.test",
    }
    with (
        patch(
            "app.api.identity.auth.keystone.validate_token",
            side_effect=lambda _token, project_id="", **_: dict(
                kc_info, project_id=project_id, roles=["member"] if project_id else []
            ),
        ),
        patch("app.api.identity.auth.record_project_access", new_callable=AsyncMock),
    ):
        resp = await client.post(
            "/api/v1/auth/token/project",
            json={"project_id": "other-project-456"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == "other-project-456"
    assert data["token"] and data["token"].count(".") == 2


@pytest.mark.asyncio
async def test_scope_project_no_access(client):
    """접근 권한 없는 프로젝트로 rescope 시 403."""
    with patch(
        "app.api.identity.auth.keystone.validate_token",
        side_effect=Exception("forbidden"),
    ):
        resp = await client.post(
            "/api/v1/auth/token/project",
            json={"project_id": "forbidden-project"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_scope_project_old_route_gone(client):
    """구 /switch-project 경로는 더 이상 처리되지 않아야 한다 (404 또는 405)."""
    resp = await client.post(
        "/api/v1/auth/switch-project",
        json={"project_id": "any-project"},
    )
    assert resp.status_code in (404, 405), f"구 /switch-project가 예상치 못한 {resp.status_code}를 반환했습니다"


# ────── logout ──────


@pytest.mark.asyncio
async def test_logout(client):
    with (
        patch("app.api.identity.auth.keystone.revoke_token", return_value=None),
        patch("app.services.cache._get_redis") as mock_redis,
    ):
        mock_r = AsyncMock()
        mock_r.delete = AsyncMock()
        mock_redis.return_value = mock_r
        resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    assert "로그아웃" in resp.json()["message"]


@pytest.mark.asyncio
async def test_jwt_logout_revokes_session_keystone_token_not_access_jwt():
    from app.api.identity import auth

    revoked: list[str] = []

    def revoke(token: str) -> None:
        revoked.append(token)

    token_info = {
        **make_auth_data(),
        "token": "afterglow-access-jwt",
        "refresh_jti": "refresh-jti",
    }
    with (
        patch(
            "app.api.identity.auth.session_store.get_session",
            AsyncMock(return_value={"user_id": "test-user-123", "keystone_token": "keystone-token"}),
        ),
        patch("app.api.identity.auth.session_store.delete_session", AsyncMock()) as delete_session,
        patch("app.api.identity.auth.asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *args: fn(*args))),
        patch("app.api.identity.auth.invalidate_token_cache", new_callable=AsyncMock),
        patch("app.api.identity.auth.keystone.revoke_token", revoke),
    ):
        response = await auth.logout(token_info)

    assert response["message"] == "로그아웃 완료"
    assert revoked == ["keystone-token"]
    delete_session.assert_awaited_once_with("refresh-jti")


@pytest.mark.asyncio
async def test_logout_invalidates_token_cache(client):
    """logout 호출 시 invalidate_token_cache 가 호출되어 검증 캐시가 즉시 비워져야 한다."""
    with (
        patch("app.api.identity.auth.keystone.revoke_token", return_value=None),
        patch(
            "app.api.identity.auth.invalidate_token_cache",
            new_callable=AsyncMock,
        ) as mock_invalidate,
    ):
        resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    # invalidate_token_cache 가 호출되어야 함 (token, project_id 인자)
    assert mock_invalidate.await_count == 1
    args, _ = mock_invalidate.await_args
    assert args[0]  # token 비어있지 않음


# ────── projects ──────


@pytest.mark.asyncio
async def test_list_projects(client):
    projects = [{"id": "proj-1", "name": "myproject", "description": "", "domain_id": "default", "enabled": True}]
    with patch("app.api.identity.auth.keystone.list_projects", return_value=projects):
        resp = await client.get("/api/v1/auth/projects")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == "proj-1"


@pytest.mark.asyncio
async def test_list_projects_cache_miss_then_hit(client):
    projects = [{"id": "proj-1", "name": "cached-project", "description": "", "domain_id": "default", "enabled": True}]
    with patch("app.api.identity.auth.keystone.list_projects", return_value=projects) as mock_list:
        first = await client.get("/api/v1/auth/projects?cache=true")
        second = await client.get("/api/v1/auth/projects?cache=true")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert mock_list.call_count == 1


@pytest.mark.asyncio
async def test_list_projects_refresh_bypasses_cache(client):
    cached_projects = [
        {"id": "proj-old", "name": "old-project", "description": "", "domain_id": "default", "enabled": True}
    ]
    refreshed_projects = [
        {"id": "proj-new", "name": "new-project", "description": "", "domain_id": "default", "enabled": True}
    ]
    with patch(
        "app.api.identity.auth.keystone.list_projects",
        side_effect=[cached_projects, refreshed_projects],
    ) as mock_list:
        cached = await client.get("/api/v1/auth/projects?cache=true")
        refreshed = await client.get("/api/v1/auth/projects?refresh=true")

    assert cached.status_code == 200
    assert refreshed.status_code == 200
    assert cached.json()[0]["id"] == "proj-old"
    assert refreshed.json()[0]["id"] == "proj-new"
    assert mock_list.call_count == 2


@pytest.mark.asyncio
async def test_list_projects_cache_is_isolated_by_user(client, _fake_redis_global):
    token_info = {
        "token": "token-a",
        "project_id": "test-project-123",
        "project_name": "test-project",
        "user_id": "user-a",
        "username": "testuser",
        "roles": ["member"],
        "is_system_admin": False,
        "domain_id": "default",
    }

    async def override_token_info():
        return token_info

    app.dependency_overrides[get_token_info] = override_token_info

    def projects_for_token(token: str, domain_id: str):
        project_id = "project-a" if token == "token-a" else "project-b"
        return [{"id": project_id, "name": project_id, "description": "", "domain_id": "default", "enabled": True}]

    with patch("app.api.identity.auth.keystone.list_projects", side_effect=projects_for_token) as mock_list:
        response_a = await client.get("/api/v1/auth/projects?cache=true")
        token_info.update(token="token-b", user_id="user-b")
        response_b = await client.get("/api/v1/auth/projects?cache=true")
        token_info.update(token="token-a", user_id="user-a")
        response_a_cached = await client.get("/api/v1/auth/projects?cache=true")

    assert response_a.json()[0]["id"] == "project-a"
    assert response_b.json()[0]["id"] == "project-b"
    assert response_a_cached.json()[0]["id"] == "project-a"
    assert response_a.status_code == response_b.status_code == response_a_cached.status_code == 200
    assert await _fake_redis_global.exists("afterglow:user:user-a:domain:default:projects")
    assert await _fake_redis_global.exists("afterglow:user:user-b:domain:default:projects")
    assert mock_list.call_count == 2


# ────── groups ──────


@pytest.mark.asyncio
async def test_list_my_groups_success(client):
    groups = [{"id": "grp-1", "name": "devteam", "description": "Dev Team", "domain_id": "default"}]
    with patch("app.api.identity.auth.keystone.list_user_groups", return_value=groups):
        resp = await client.get("/api/v1/auth/groups")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == "grp-1"
    assert resp.json()[0]["name"] == "devteam"


@pytest.mark.asyncio
async def test_list_my_groups_forbidden(client):
    with patch("app.api.identity.auth.keystone.list_user_groups", side_effect=PermissionError("forbidden")):
        resp = await client.get("/api/v1/auth/groups")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_my_groups_unexpected_error_returns_empty(client):
    # service 내부에서 어떤 예외든 PermissionError 로 변환되므로 endpoint 는 [] 반환
    with patch("app.api.identity.auth.keystone.list_user_groups", side_effect=PermissionError("unexpected")):
        resp = await client.get("/api/v1/auth/groups")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_user_groups_converts_exception_to_permission_error():
    """keystone client 가 임의 예외를 raise 해도 service 가 PermissionError 로 변환하는지 검증."""
    from unittest.mock import MagicMock

    mock_ks = MagicMock()
    mock_ks.groups.list.side_effect = RuntimeError("kaboom")

    with (
        patch("app.services.keystone.get_settings") as mock_cfg,
        patch("app.services.keystone.v3.Token"),
        patch("app.services.keystone.ks_session.Session"),
        patch("keystoneclient.v3.client.Client", return_value=mock_ks),
    ):
        mock_cfg.return_value.os_auth_url = "http://keystone:5000/v3"
        mock_cfg.return_value.ssl_verify = False
        import pytest as _pytest

        from app.services.keystone import list_user_groups

        with _pytest.raises(PermissionError):
            list_user_groups("fake-token", "fake-user-id")


@pytest.mark.asyncio
async def test_auth_preflight_allows_configured_frontend_origin(client):
    origin = get_settings().cors_origin_list[0]
    resp = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
        },
    )

    assert resp.status_code == 200
    assert resp.headers["Access-Control-Allow-Origin"] == origin
    assert resp.headers["Access-Control-Allow-Credentials"] == "true"


# ────── auth_method 필드 ──────


@pytest.mark.asyncio
async def test_me_returns_auth_method(client):
    """/me 응답에 auth_method 필드가 포함되어야 한다."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_method" in data
    assert data["auth_method"] == "password"  # 기본 로컬 로그인


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["enabled", "authorize", "callback"])
async def test_legacy_gitlab_routes_removed(client, path):
    response = await client.request("POST" if path == "callback" else "GET", f"/api/v1/auth/gitlab/{path}")
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "legacy",
    [
        {"domain_name": "Default"},
        {"project_name": "test-project"},
        {"domain_name": "Default", "project_name": "test-project"},
    ],
)
async def test_password_login_rejects_legacy_scope_without_echoing_secret(client, legacy):
    secret = "password-must-not-appear"
    with patch("app.api.identity.auth.keystone.authenticate") as authenticate:
        response = await client.post("/api/v1/auth/login", json={"username": "u", "password": secret, **legacy})
    authenticate.assert_not_called()
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid authentication input"}
    assert secret not in response.text
    assert response.headers["cache-control"] == "no-store, private"
