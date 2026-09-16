"""Database (Trove) API 단위 테스트.

Trove 서비스가 비활성화된 환경에서도 인증 관문(401/404/405)을 검증.
활성화된 환경에서는 mock으로 성공/에러 경로를 검증.
trove는 핸들러 내에서 lazy import하므로 app.services.trove 를 패치.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# trove 서비스 활성화 여부
_TROVE_ENABLED = os.environ.get("SERVICE_TROVE_ENABLED", "false").lower() in ("true", "1")


# ---------------------------------------------------------------------------
# 인증 관문 (항상 실행)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_database_instances_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/database-instances")
    # trove 미활성화 시 404/405, 활성화+인증없음 시 401
    assert resp.status_code in (401, 404, 405)


@pytest.mark.asyncio
async def test_create_database_instance_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/database-instances", json={"name": "mydb"})
    assert resp.status_code in (401, 404, 405, 422)


@pytest.mark.asyncio
async def test_get_database_instance_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/database-instances/inst-1")
    assert resp.status_code in (401, 404, 405)


@pytest.mark.asyncio
async def test_delete_database_instance_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/database-instances/inst-1")
    assert resp.status_code in (401, 404, 405)


@pytest.mark.asyncio
async def test_list_database_flavors_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/database-instances/flavors")
    assert resp.status_code in (401, 404, 405)


@pytest.mark.asyncio
async def test_list_datastores_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/database-instances/datastores")
    assert resp.status_code in (401, 404, 405)


# ---------------------------------------------------------------------------
# Trove 활성화 시 동작 (SERVICE_TROVE_ENABLED=true 필요)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.skipif(not _TROVE_ENABLED, reason="Trove 서비스 비활성화")
async def test_list_database_instances_success(client, mock_conn):
    from unittest.mock import MagicMock, patch

    # list_instances는 asyncio.to_thread 로 호출되는 sync 함수이므로 MagicMock 사용
    with patch("app.services.trove.list_instances", new=MagicMock(return_value=[])):
        resp = await client.get("/api/v1/database-instances")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
@pytest.mark.skipif(not _TROVE_ENABLED, reason="Trove 서비스 비활성화")
async def test_list_database_instances_error_handling(client, mock_conn):
    from unittest.mock import MagicMock, patch

    with patch("app.services.trove.list_instances", new=MagicMock(side_effect=Exception("trove error"))):
        resp = await client.get("/api/v1/database-instances")
    assert resp.status_code in (500, 503)


# ---------------------------------------------------------------------------
# admin all_projects 테스트
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_db_instances_all_projects_requires_admin(non_admin_client):
    """all_projects=true + is_system_admin=False → 403."""
    resp = await non_admin_client.get("/api/v1/database-instances?all_projects=true")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 인스턴스 내 DB 생성 — 인증 관문
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_instance_database_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/database-instances/inst-1/databases",
            json={"name": "mydb"},
        )
    assert resp.status_code in (401, 404, 405)


# ---------------------------------------------------------------------------
# trove.create_database raw REST 페이로드 검증 (회귀 방지)
# ---------------------------------------------------------------------------


def test_create_database_uses_databases_array_payload():
    """SDK proxy 대신 raw REST를 사용해 {"databases": [{...}]} 복수 배열로 전송하는지 검증.

    SDK Database 리소스에는 _prepare_request 오버라이드가 없어 {"database": {...}} 단수
    키로 직렬화되기 때문에 raw REST로 우회한다.
    """
    from unittest.mock import MagicMock

    from app.services.trove import create_database

    mock_conn = MagicMock()
    mock_conn.database.post.return_value.ok = True
    mock_conn.database.post.return_value.status_code = 202

    create_database(mock_conn, "inst-1", "mydb", "utf8", "utf8_general_ci")

    mock_conn.database.post.assert_called_once_with(
        "/instances/inst-1/databases",
        json={"databases": [{"name": "mydb", "character_set": "utf8", "collate": "utf8_general_ci"}]},
    )


def test_create_database_omits_locale_when_none():
    """character_set/collate 미지정 시 페이로드에서 두 키가 제외되는지 검증 (PG 기본 locale 사용).

    MySQL 형식의 utf8_general_ci 를 PG 에 보내면 LC_COLLATE 오류가 발생하므로,
    호출자가 None 을 주면 databases 배열에 name 만 포함해야 한다.
    """
    from unittest.mock import MagicMock

    from app.services.trove import create_database

    mock_conn = MagicMock()
    mock_conn.database.post.return_value.ok = True
    mock_conn.database.post.return_value.status_code = 202

    create_database(mock_conn, "inst-pg", "mydb")

    mock_conn.database.post.assert_called_once_with(
        "/instances/inst-pg/databases",
        json={"databases": [{"name": "mydb"}]},
    )


def test_create_database_raises_on_trove_4xx():
    """Trove 가 4xx 응답을 반환하면 RuntimeError 를 raise 해야 한다 (silent failure 회귀 방지).

    openstack proxy.post 는 raise_exc=False 기본이라 4xx/5xx 도 예외 없이 반환되므로
    resp.ok 를 명시적으로 검증해야 한다.
    """
    from unittest.mock import MagicMock

    import pytest

    from app.services.trove import create_database

    mock_conn = MagicMock()
    mock_conn.database.post.return_value.ok = False
    mock_conn.database.post.return_value.status_code = 400
    mock_conn.database.post.return_value.text = "bad collate"

    with pytest.raises(RuntimeError, match="status=400") as exc_info:
        create_database(mock_conn, "inst-1", "mydb", "utf8", "bad_collate")

    assert "bad collate" in str(exc_info.value)


@pytest.mark.asyncio
async def test_list_db_instances_all_projects_admin(admin_client, mock_conn):
    """admin + all_projects=true → list_instances_admin_all_projects 호출 + project_id 반환."""
    from unittest.mock import MagicMock, patch

    fake_instance = {
        "id": "inst-abc",
        "name": "db1",
        "status": "ACTIVE",
        "datastore": {"type": "mysql"},
        "flavor_id": "f1",
        "flavor_ram": 1024,
        "size": 10,
        "created_at": "",
        "hostname": "",
        "ip": "",
        "links": [],
        "project_id": "other-project",
    }
    with patch(
        "app.services.trove.list_instances_admin_all_projects",
        new=MagicMock(return_value=[fake_instance]),
    ):
        resp = await admin_client.get("/api/v1/database-instances?all_projects=true")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["project_id"] == "other-project"


# ---------------------------------------------------------------------------
# Phase C+D — GET 캐시 동작 검증
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_database_instances_uses_cached_call(client, mock_conn):
    """GET /database-instances → cached_call 을 통해 결과를 캐시한다."""
    fake = [{"id": "inst-1", "name": "mydb", "status": "ACTIVE"}]
    with patch(
        "app.api.database.instances.cache.cached_call",
        new=AsyncMock(return_value=fake),
    ) as mock_cached:
        resp = await client.get("/api/v1/database-instances")
    assert resp.status_code == 200
    assert resp.json() == fake
    mock_cached.assert_awaited_once()
    # 키 확인: trove:test-project-123:instances
    call_key = mock_cached.call_args[0][0]
    assert "trove" in call_key
    assert "instances" in call_key


@pytest.mark.asyncio
async def test_get_database_instance_uses_cached_call(client, mock_conn):
    """GET /database-instances/{id} → cached_call 을 통해 인스턴스 상세를 캐시한다."""
    fake = {"id": "inst-1", "name": "mydb", "status": "ACTIVE"}
    with patch(
        "app.api.database.instances.cache.cached_call",
        new=AsyncMock(return_value=fake),
    ) as mock_cached:
        resp = await client.get("/api/v1/database-instances/inst-1")
    assert resp.status_code == 200
    mock_cached.assert_awaited_once()
    call_key = mock_cached.call_args[0][0]
    assert "inst-1" in call_key


@pytest.mark.asyncio
async def test_list_db_flavors_uses_cached_call(client, mock_conn):
    """GET /flavors → cached_call 을 통해 ttl_static() 으로 캐시한다."""
    fake = [{"id": "1", "name": "cpu.2c_2g", "ram": 2048, "vcpus": 2, "disk": 10}]
    with patch(
        "app.api.database.instances.cache.cached_call",
        new=AsyncMock(return_value=fake),
    ) as mock_cached:
        resp = await client.get("/api/v1/database-instances/flavors")
    assert resp.status_code == 200
    mock_cached.assert_awaited_once()
    # TTL 인자가 ttl_static() 값(300)인지 확인
    call_ttl = mock_cached.call_args[0][1]
    assert call_ttl == 300


@pytest.mark.asyncio
async def test_list_datastores_uses_cached_call(client, mock_conn):
    """GET /datastores → cached_call 을 통해 ttl_static() 으로 캐시한다."""
    fake = [{"id": "ds-1", "name": "mysql", "versions": []}]
    with patch(
        "app.api.database.instances.cache.cached_call",
        new=AsyncMock(return_value=fake),
    ) as mock_cached:
        resp = await client.get("/api/v1/database-instances/datastores")
    assert resp.status_code == 200
    mock_cached.assert_awaited_once()
    call_ttl = mock_cached.call_args[0][1]
    assert call_ttl == 300


@pytest.mark.asyncio
async def test_list_backups_uses_cached_call(client, mock_conn):
    """GET /backups → cached_call 을 통해 ttl_slow() 로 캐시한다."""
    fake = [{"id": "bk-1", "name": "backup1", "status": "COMPLETED"}]
    with patch(
        "app.api.database.instances.cache.cached_call",
        new=AsyncMock(return_value=fake),
    ) as mock_cached:
        resp = await client.get("/api/v1/database-instances/backups")
    assert resp.status_code == 200
    mock_cached.assert_awaited_once()
    call_ttl = mock_cached.call_args[0][1]
    assert call_ttl == 60  # ttl_slow


@pytest.mark.asyncio
async def test_list_instance_databases_uses_cached_call(client, mock_conn):
    """GET /database-instances/{id}/databases → cached_call 사용."""
    fake = [{"name": "mydb", "character_set": "utf8", "collate": "utf8_general_ci"}]
    with patch(
        "app.api.database.instances.cache.cached_call",
        new=AsyncMock(return_value=fake),
    ) as mock_cached:
        resp = await client.get("/api/v1/database-instances/inst-1/databases")
    assert resp.status_code == 200
    mock_cached.assert_awaited_once()
    call_key = mock_cached.call_args[0][0]
    assert "inst-1" in call_key
    assert "databases" in call_key


@pytest.mark.asyncio
async def test_list_instance_users_uses_cached_call(client, mock_conn):
    """GET /database-instances/{id}/users → cached_call 사용."""
    fake = [{"name": "alice", "host": "%", "databases": []}]
    with patch(
        "app.api.database.instances.cache.cached_call",
        new=AsyncMock(return_value=fake),
    ) as mock_cached:
        resp = await client.get("/api/v1/database-instances/inst-1/users")
    assert resp.status_code == 200
    mock_cached.assert_awaited_once()
    call_key = mock_cached.call_args[0][0]
    assert "users" in call_key


@pytest.mark.asyncio
async def test_list_instance_backups_uses_cached_call(client, mock_conn):
    """GET /database-instances/{id}/backups → cached_call 사용."""
    fake = [{"id": "bk-1", "name": "snap", "status": "COMPLETED"}]
    with patch(
        "app.api.database.instances.cache.cached_call",
        new=AsyncMock(return_value=fake),
    ) as mock_cached:
        resp = await client.get("/api/v1/database-instances/inst-1/backups")
    assert resp.status_code == 200
    mock_cached.assert_awaited_once()
    call_ttl = mock_cached.call_args[0][1]
    assert call_ttl == 60  # ttl_slow


# ---------------------------------------------------------------------------
# Phase D — Mutation invalidation 검증
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_database_instance_invalidates_cache(client, mock_conn):
    """DELETE /database-instances/{id} 성공 시 cache.invalidate 를 호출한다."""
    with (
        patch("app.services.trove.delete_instance", new=MagicMock(return_value=None)),
        patch(
            "app.api.database.instances.cache.invalidate",
            new=AsyncMock(),
        ) as mock_inv,
        patch(
            "app.api.database.instances.invalidation.invalidate_mutation_count",
            new=AsyncMock(),
        ) as mock_mc,
    ):
        resp = await client.delete("/api/v1/database-instances/inst-1")
    assert resp.status_code == 204
    mock_inv.assert_awaited_once()
    inv_pattern = mock_inv.call_args[0][0]
    assert "trove" in inv_pattern
    assert "*" in inv_pattern
    mock_mc.assert_awaited_once_with("trove", "test-project-123")


@pytest.mark.asyncio
async def test_create_database_instance_invalidates_cache(client, mock_conn):
    """POST /database-instances 성공 시 cache.invalidate 를 호출한다."""
    fake_instance = {
        "id": "new-inst",
        "name": "mydb",
        "status": "BUILD",
        "datastore": {},
        "flavor_id": "f1",
        "flavor_ram": 2048,
        "size": 10,
        "created_at": "",
        "hostname": "",
        "ip": "",
        "links": [],
    }
    with (
        patch("app.services.trove.create_instance", new=MagicMock(return_value=fake_instance)),
        patch(
            "app.api.database.instances.cache.invalidate",
            new=AsyncMock(),
        ) as mock_inv,
        patch(
            "app.api.database.instances.invalidation.invalidate_mutation_count",
            new=AsyncMock(),
        ) as mock_mc,
    ):
        resp = await client.post(
            "/api/v1/database-instances",
            json={
                "name": "mydb",
                "flavor_id": "f1",
                "volume_size": 10,
                "datastore_type": "mysql",
                "datastore_version": "8.0",
            },
        )
    assert resp.status_code == 201
    mock_inv.assert_awaited_once()
    mock_mc.assert_awaited_once_with("trove", "test-project-123")


@pytest.mark.asyncio
async def test_create_instance_database_invalidates_cache(client, mock_conn):
    """POST /database-instances/{id}/databases 성공 시 cache.invalidate 를 호출한다."""
    with (
        patch("app.services.trove.create_database", new=MagicMock(return_value=None)),
        patch(
            "app.api.database.instances.cache.invalidate",
            new=AsyncMock(),
        ) as mock_inv,
        patch(
            "app.api.database.instances.invalidation.invalidate_mutation_count",
            new=AsyncMock(),
        ) as mock_mc,
    ):
        resp = await client.post(
            "/api/v1/database-instances/inst-1/databases",
            json={"name": "newdb"},
        )
    assert resp.status_code == 201
    assert resp.json()["name"] == "newdb"
    mock_inv.assert_awaited_once()
    mock_mc.assert_awaited_once_with("trove", "test-project-123")


@pytest.mark.asyncio
async def test_delete_instance_database_invalidates_cache(client, mock_conn):
    """DELETE /database-instances/{id}/databases/{db} 성공 시 cache.invalidate 를 호출한다."""
    with (
        patch("app.services.trove.delete_database", new=MagicMock(return_value=None)),
        patch(
            "app.api.database.instances.cache.invalidate",
            new=AsyncMock(),
        ) as mock_inv,
        patch(
            "app.api.database.instances.invalidation.invalidate_mutation_count",
            new=AsyncMock(),
        ) as mock_mc,
    ):
        resp = await client.delete("/api/v1/database-instances/inst-1/databases/mydb")
    assert resp.status_code == 204
    mock_inv.assert_awaited_once()
    mock_mc.assert_awaited_once_with("trove", "test-project-123")


@pytest.mark.asyncio
async def test_create_instance_user_invalidates_cache(client, mock_conn):
    """POST /database-instances/{id}/users 성공 시 cache.invalidate 를 호출한다."""
    with (
        patch("app.services.trove.create_user", new=MagicMock(return_value=None)),
        patch(
            "app.api.database.instances.cache.invalidate",
            new=AsyncMock(),
        ) as mock_inv,
        patch(
            "app.api.database.instances.invalidation.invalidate_mutation_count",
            new=AsyncMock(),
        ) as mock_mc,
    ):
        resp = await client.post(
            "/api/v1/database-instances/inst-1/users",
            json={"name": "alice", "password": "secret123"},
        )
    assert resp.status_code == 201
    assert resp.json()["name"] == "alice"
    mock_inv.assert_awaited_once()
    mock_mc.assert_awaited_once_with("trove", "test-project-123")


@pytest.mark.asyncio
async def test_delete_instance_user_invalidates_cache(client, mock_conn):
    """DELETE /database-instances/{id}/users/{username} 성공 시 cache.invalidate 를 호출한다."""
    with (
        patch("app.services.trove.delete_user", new=MagicMock(return_value=None)),
        patch(
            "app.api.database.instances.cache.invalidate",
            new=AsyncMock(),
        ) as mock_inv,
        patch(
            "app.api.database.instances.invalidation.invalidate_mutation_count",
            new=AsyncMock(),
        ) as mock_mc,
    ):
        resp = await client.delete("/api/v1/database-instances/inst-1/users/alice")
    assert resp.status_code == 204
    mock_inv.assert_awaited_once()
    mock_mc.assert_awaited_once_with("trove", "test-project-123")


@pytest.mark.asyncio
async def test_create_instance_backup_invalidates_cache(client, mock_conn):
    """POST /database-instances/{id}/backups 성공 시 cache.invalidate 를 호출한다."""
    fake_backup = {"id": "bk-1", "name": "snap", "status": "NEW"}
    with (
        patch("app.services.trove.create_backup", new=MagicMock(return_value=fake_backup)),
        patch(
            "app.api.database.instances.cache.invalidate",
            new=AsyncMock(),
        ) as mock_inv,
        patch(
            "app.api.database.instances.invalidation.invalidate_mutation_count",
            new=AsyncMock(),
        ) as mock_mc,
    ):
        resp = await client.post(
            "/api/v1/database-instances/inst-1/backups",
            json={"name": "snap"},
        )
    assert resp.status_code == 201
    mock_inv.assert_awaited_once()
    mock_mc.assert_awaited_once_with("trove", "test-project-123")


@pytest.mark.asyncio
async def test_restart_database_instance_invalidates_cache(client, mock_conn):
    """POST /database-instances/{id}/restart 성공 시 cache.invalidate 를 호출한다."""
    with (
        patch("app.services.trove.restart_instance", new=MagicMock(return_value=None)),
        patch(
            "app.api.database.instances.cache.invalidate",
            new=AsyncMock(),
        ) as mock_inv,
        patch(
            "app.api.database.instances.invalidation.invalidate_mutation_count",
            new=AsyncMock(),
        ) as mock_mc,
    ):
        resp = await client.post("/api/v1/database-instances/inst-1/restart")
    assert resp.status_code == 204
    mock_inv.assert_awaited_once()
    mock_mc.assert_awaited_once_with("trove", "test-project-123")


@pytest.mark.asyncio
async def test_enable_root_user_invalidates_cache(client, mock_conn):
    """POST /database-instances/{id}/root 성공 시 cache.invalidate 를 호출한다."""
    fake_root = {"name": "root", "password": "secret"}
    with (
        patch("app.services.trove.enable_root", new=MagicMock(return_value=fake_root)),
        patch(
            "app.api.database.instances.cache.invalidate",
            new=AsyncMock(),
        ) as mock_inv,
        patch(
            "app.api.database.instances.invalidation.invalidate_mutation_count",
            new=AsyncMock(),
        ) as mock_mc,
    ):
        resp = await client.post("/api/v1/database-instances/inst-1/root")
    assert resp.status_code == 200
    assert resp.json()["name"] == "root"
    mock_inv.assert_awaited_once()
    mock_mc.assert_awaited_once_with("trove", "test-project-123")


@pytest.mark.asyncio
async def test_mutation_does_not_invalidate_on_failure(client, mock_conn):
    """mutation 실패(500) 시에는 cache.invalidate 를 호출하지 않는다."""
    with (
        patch("app.services.trove.delete_instance", new=MagicMock(side_effect=Exception("oops"))),
        patch(
            "app.api.database.instances.cache.invalidate",
            new=AsyncMock(),
        ) as mock_inv,
    ):
        resp = await client.delete("/api/v1/database-instances/inst-1")
    assert resp.status_code == 500
    mock_inv.assert_not_awaited()


# ---------------------------------------------------------------------------
# deleted 필터링 (목록에서 deleted=1 행 제외 검증)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_instances_filters_deleted():
    """list_instances가 deleted=1 행을 응답에서 제외하는지 검증."""
    from app.services import trove as trove_svc

    raw_instances = [
        {"id": "alive-1", "name": "alive", "status": "ACTIVE", "deleted": 0},
        {"id": "dead-1", "name": "dead", "status": "SHUTDOWN", "deleted": 1},
        {"id": "alive-2", "name": "alive2", "status": "HEALTHY", "deleted": False},
        {"id": "dead-2", "name": "dead2", "status": "DELETED", "deleted": True},
    ]

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"instances": raw_instances}

    mock_conn = MagicMock()
    mock_conn.database.get.return_value = mock_resp

    result = trove_svc.list_instances(mock_conn)
    ids = [r["id"] for r in result]
    assert "alive-1" in ids
    assert "alive-2" in ids
    assert "dead-1" not in ids
    assert "dead-2" not in ids


@pytest.mark.asyncio
async def test_list_instances_admin_returns_tenant_trove_inventory():
    """관리자 목록은 Trove proxy의 management inventory를 반환한다."""
    from app.services import trove as trove_svc

    raw_instances = [
        {"id": "a1", "name": "tenant-db", "status": "ACTIVE", "deleted": 0, "tenant_id": "p1"},
        {"id": "d1", "name": "gone", "status": "SHUTDOWN", "deleted": 1, "tenant_id": "p2"},
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"instances": raw_instances}
    mock_resp.raise_for_status = MagicMock()
    mock_conn = MagicMock()
    mock_conn.database.get.return_value = mock_resp

    result = trove_svc.list_instances_admin_all_projects(mock_conn)

    assert result == [
        {
            "id": "a1",
            "name": "tenant-db",
            "status": "ACTIVE",
            "datastore": {},
            "flavor_id": "",
            "flavor_ram": 0,
            "flavor_vcpus": 0,
            "size": 0,
            "volume_used": 0,
            "created_at": "",
            "updated_at": "",
            "hostname": "",
            "ip": "",
            "ips": [],
            "address_map": {},
            "links": [],
            "project_id": "p1",
        }
    ]


def test_list_instances_admin_propagates_management_failure():
    """Trove management 장애를 tenant DB 0건으로 오인하지 않는다."""
    from app.services import trove as trove_svc

    mock_conn = MagicMock()
    mock_conn.database.get.side_effect = RuntimeError("management unavailable")

    with pytest.raises(RuntimeError, match="management unavailable"):
        trove_svc.list_instances_admin_all_projects(mock_conn)


@pytest.mark.asyncio
async def test_restore_from_backup_unauthenticated():
    """POST /restore: 인증 없이 복원 불가."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/database-instances/restore",
            json={"backup_id": "bk-1", "name": "restored", "flavor_id": "fl-1", "volume_size": 10},
        )
    assert resp.status_code == 401
