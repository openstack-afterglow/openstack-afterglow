"""인증 및 세션 관련 통합 테스트."""

import pytest

from .conftest import password_login_payload


@pytest.mark.asyncio(loop_scope="session")
async def test_login_success(anon_client, credentials):
    resp = await anon_client.post("/api/v1/auth/login", json=password_login_payload(credentials))
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert "project_id" in data
    assert data["username"]
    assert data["domain_id"] == data["identity_domain_id"]
    me = await anon_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {data['token']}"})
    assert me.status_code == 200
    assert (me.json()["user_id"], me.json()["domain_id"], me.json()["project_id"]) == (
        data["user_id"],
        data["identity_domain_id"],
        data["project_id"],
    )
    assert len(data["roles"]) > 0


@pytest.mark.asyncio(loop_scope="session")
async def test_login_bad_password(anon_client, credentials):
    bad = password_login_payload(credentials)
    bad["password"] = "wrong-password-12345"
    resp = await anon_client.post("/api/v1/auth/login", json=bad)
    assert resp.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_me(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert "username" in data
    assert "roles" in data


@pytest.mark.asyncio(loop_scope="session")
async def test_list_projects(client):
    resp = await client.get("/api/v1/auth/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "id" in data[0]
    assert "name" in data[0]


@pytest.mark.asyncio(loop_scope="session")
async def test_no_token_returns_401(anon_client):
    resp = await anon_client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
async def test_fresh_login_starts_in_canonical_home(anon_client, credentials):
    response = await anon_client.post("/api/v1/auth/login", json=password_login_payload(credentials))
    assert response.status_code == 200
    data = response.json()
    assert data["domain_id"] == data["identity_domain_id"]
    workspace = await anon_client.get("/api/v1/auth/workspaces", headers={"Authorization": f"Bearer {data['token']}"})
    assert workspace.status_code == 200
    assert workspace.json()["domain"]["id"] == data["identity_domain_id"]
    assert data["project_id"] in {project["id"] for project in workspace.json()["projects"]}


# ─────────────────────────────────────────────────────────────────
# PR4: is_system_admin 분리 검증 — sanity check
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_login_is_system_admin(admin_auth_data):
    """admin 로그인 응답의 is_system_admin=True 확인. 실패 시 credentials.toml [admin] 확인."""
    assert admin_auth_data.get("is_system_admin") is True, (
        "admin 계정이 is_system_admin=False — credentials.toml [admin] 계정이 실제 system admin role을 보유하는지 확인"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_user_login_is_not_system_admin(user_auth_data):
    """일반 유저 로그인 응답의 is_system_admin=False 확인. 실패 시 credentials.toml [user] 확인."""
    assert user_auth_data.get("is_system_admin") is False, (
        "일반 유저가 is_system_admin=True — credentials.toml [user] 계정이 system admin role을 보유하지 않는지 확인"
    )


# ─────────────────────────────────────────────────────────────────
# admin_user 검증 (native system:all admin 할당 보유, default project ≠ admin 가능)
# credentials.toml [admin_user] 또는 AFTERGLOW_TEST_ADMIN_USER_* 환경변수 필요
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_user_login_is_system_admin(admin_user_auth_data):
    """admin_user 로그인 응답의 is_system_admin=True 확인.

    scoped token 의 project 와 무관하게 native system:all admin 할당이 있으면 True 여야 한다.
    project admin role 은 시스템 관리 권한의 근거가 아니다.
    실패 시 credentials.toml [admin_user] 계정의 system:all role 할당 확인.
    """
    assert admin_user_auth_data.get("is_system_admin") is True, (
        "admin_user 가 is_system_admin=False — "
        "credentials.toml [admin_user] 계정이 native system:all admin role 할당을 보유하는지 확인"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_user_me_returns_is_system_admin(admin_user_client):
    """/api/v1/auth/me 응답에도 is_system_admin=True 가 포함돼야 한다.

    페이지 새로고침 시 localStorage 재동기화에 사용되는 엔드포인트.
    실패 시 백엔드 UserInfo 모델 또는 /me 핸들러 is_system_admin 반환 확인.
    """
    resp = await admin_user_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("is_system_admin") is True, (
        "/api/v1/auth/me 응답에 is_system_admin=True 없음 — "
        "UserInfo 모델과 me() 핸들러가 is_system_admin 을 반환하는지 확인"
    )
