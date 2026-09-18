"""프로젝트 RBAC (역할별 권한 차이 및 reader 쓰기 차단) 테스트."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_caller_project_permissions, get_os_conn, get_token_info, require_project_write
from app.main import app
from tests.conftest import make_token_info


def test_require_project_write_direct():
    # 1. member 권한 -> 성공
    token_member = make_token_info(roles=["member"])
    assert require_project_write(token_member) == token_member

    # 2. admin 권한 -> 성공
    token_admin = make_token_info(roles=["admin"])
    assert require_project_write(token_admin) == token_admin

    # 3. system_admin 플래그 -> role 상관없이 성공
    token_sys_admin = make_token_info(roles=["reader"], is_system_admin=True)
    assert require_project_write(token_sys_admin) == token_sys_admin

    # 4. reader 단독 권한 -> 403 차단
    token_reader = make_token_info(roles=["reader"])
    with pytest.raises(HTTPException) as exc_info:
        require_project_write(token_reader)
    assert exc_info.value.status_code == 403
    assert "읽기 전용(reader)" in exc_info.value.detail

    # 5. 역할 없음 (빈 리스트) -> 403 차단
    token_empty = dict(token_reader)
    token_empty["roles"] = []
    with pytest.raises(HTTPException) as exc_info:
        require_project_write(token_empty)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_caller_project_permissions_direct():
    # reader
    token_reader = make_token_info(roles=["reader"])
    perms_reader = await get_caller_project_permissions(token_info=token_reader)
    assert perms_reader["can_read"] is True
    assert perms_reader["can_write"] is False
    assert perms_reader["is_reader"] is True
    assert perms_reader["is_system_admin"] is False

    # member
    token_member = make_token_info(roles=["member"])
    perms_member = await get_caller_project_permissions(token_info=token_member)
    assert perms_member["can_read"] is True
    assert perms_member["can_write"] is True
    assert perms_member["is_reader"] is False
    assert perms_member["is_system_admin"] is False


@pytest.fixture
async def reader_client(mock_conn):
    """reader 역할을 가진 AsyncClient."""

    async def override_get_os_conn():
        yield mock_conn

    async def override_get_token_info():
        return make_token_info(roles=["reader"], is_system_admin=False)

    app.dependency_overrides[get_os_conn] = override_get_os_conn
    app.dependency_overrides[get_token_info] = override_get_token_info
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-token", "X-Project-Id": "test-project-123"},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_get_current_permissions_reader(reader_client):
    """GET /api/v1/projects/current/permissions endpoint reader 테스트."""
    resp = await reader_client.get("/api/v1/projects/current/permissions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["can_read"] is True
    assert data["can_write"] is False
    assert data["is_reader"] is True
    assert "reader" in data["roles"]


@pytest.mark.asyncio
async def test_api_get_current_permissions_member(client):
    """GET /api/v1/projects/current/permissions endpoint member 테스트."""
    resp = await client.get("/api/v1/projects/current/permissions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["can_read"] is True
    assert data["can_write"] is True
    assert data["is_reader"] is False
    assert "member" in data["roles"]


@pytest.mark.asyncio
async def test_api_keypairs_mutation_blocked_for_reader(reader_client, mock_conn):
    """reader 역할 사용자의 키페어 생성/삭제 차단 검증."""
    # 1. 생성 시도 -> 403 차단
    resp_create = await reader_client.post(
        "/api/v1/keypairs",
        json={"name": "test-key", "public_key": "ssh-rsa AAAA..."},
    )
    assert resp_create.status_code == 403
    assert "읽기 전용" in resp_create.json()["detail"]

    # 2. 삭제 시도 -> 403 차단
    resp_delete = await reader_client.delete("/api/v1/keypairs/test-key")
    assert resp_delete.status_code == 403
    assert "읽기 전용" in resp_delete.json()["detail"]

    # 3. 조회 시도 -> 정상 허용 (200)
    async def _mock_cached(key, ttl, fn, **kw):
        return fn()

    with (
        patch("app.api.compute.keypairs.nova.list_keypairs", return_value=[]),
        patch("app.api.compute.keypairs.cached_call", new=_mock_cached),
    ):
        resp_list = await reader_client.get("/api/v1/keypairs")
    assert resp_list.status_code == 200


@pytest.mark.asyncio
async def test_api_volumes_mutation_blocked_for_reader(reader_client):
    """reader 역할 사용자의 볼륨 생성/삭제 차단 검증."""
    # 생성 시도 -> 403 차단
    resp_create = await reader_client.post(
        "/api/v1/volumes",
        json={"name": "test-vol", "size_gb": 10},
    )
    assert resp_create.status_code == 403
    assert "읽기 전용" in resp_create.json()["detail"]

    # 삭제 시도 -> 403 차단
    resp_delete = await reader_client.delete("/api/v1/volumes/vol-123")
    assert resp_delete.status_code == 403
    assert "읽기 전용" in resp_delete.json()["detail"]


@pytest.mark.asyncio
async def test_api_instances_mutation_blocked_for_reader(reader_client):
    """reader 역할 사용자의 인스턴스 생성/삭제/액션 차단 검증."""
    # 생성 시도 -> 403 차단
    resp_create = await reader_client.post(
        "/api/v1/instances",
        json={
            "name": "test-vm",
            "flavor_id": "f-1",
            "image_id": "img-1",
            "network_id": "net-1",
        },
    )
    assert resp_create.status_code == 403
    assert "읽기 전용" in resp_create.json()["detail"]

    # 삭제 시도 -> 403 차단
    resp_delete = await reader_client.delete("/api/v1/instances/inst-123")
    assert resp_delete.status_code == 403
    assert "읽기 전용" in resp_delete.json()["detail"]

    # 액션 시도 -> 403 차단
    resp_start = await reader_client.post("/api/v1/instances/inst-123/start")
    assert resp_start.status_code == 403
    assert "읽기 전용" in resp_start.json()["detail"]
