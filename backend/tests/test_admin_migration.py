"""마이그레이션 관련 백엔드 단위 테스트.

CPU 호환 호스트 필터링, 마이그레이션 상태 추적, 제어(abort/force-complete),
실패 메시지 노출, 엔드포인트 권한 검사를 검증한다.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services import nova

# ───────────────────────────────────────────────
# helpers
# ───────────────────────────────────────────────


def _make_hypervisor(hostname: str, cpu_model: str | None, state: str = "up", status: str = "enabled") -> dict:
    cpu_info: dict = {}
    if cpu_model:
        cpu_info = {"arch": "x86_64", "model": cpu_model, "vendor": "Intel"}
    return {
        "hypervisor_hostname": hostname,
        "state": state,
        "status": status,
        "cpu_info": cpu_info,
    }


def _mock_session_get(hypervisors: list[dict]):
    resp = MagicMock()
    resp.json.return_value = {"hypervisors": hypervisors}
    session = MagicMock()
    session.get.return_value = resp
    return session


# ───────────────────────────────────────────────
# list_compute_hosts — CPU 필터링
# ───────────────────────────────────────────────


def _conn_with_hypervisors(hypervisors: list[dict]) -> MagicMock:
    conn = MagicMock()
    conn.compute.get_endpoint.return_value = "http://nova:8774/v2.1"
    conn.session = _mock_session_get(hypervisors)
    return conn


def test_list_compute_hosts_no_filter():
    """source_host 없으면 up/enabled 호스트 전부 반환."""
    hypervisors = [
        _make_hypervisor("compute1", "Skylake-Server"),
        _make_hypervisor("compute2", "Cascadelake-Server"),
        _make_hypervisor("compute3", "Skylake-Server", state="down"),  # 제외
    ]
    conn = _conn_with_hypervisors(hypervisors)
    result = nova.list_compute_hosts(conn)
    names = [r["name"] for r in result]
    assert "compute1" in names
    assert "compute2" in names
    assert "compute3" not in names  # state=down 제외


def test_list_compute_hosts_cpu_filter_same_model():
    """source_host 지정 시 동일 CPU 모델만 반환하고 source 자신 제외."""
    hypervisors = [
        _make_hypervisor("src-host", "Skylake-Server"),
        _make_hypervisor("same-cpu-1", "Skylake-Server"),
        _make_hypervisor("same-cpu-2", "Skylake-Server"),
        _make_hypervisor("diff-cpu", "Cascadelake-Server"),
    ]
    conn = _conn_with_hypervisors(hypervisors)
    result = nova.list_compute_hosts(conn, source_host="src-host")
    names = [r["name"] for r in result]
    assert "src-host" not in names, "소스 호스트 자신은 제외"
    assert "same-cpu-1" in names
    assert "same-cpu-2" in names
    assert "diff-cpu" not in names, "CPU 불일치 호스트 제외"


def test_list_compute_hosts_cpu_model_in_result():
    """반환 dict에 cpu_model 필드가 포함된다."""
    hypervisors = [_make_hypervisor("compute1", "Skylake-Server")]
    conn = _conn_with_hypervisors(hypervisors)
    result = nova.list_compute_hosts(conn)
    assert result[0]["cpu_model"] == "Skylake-Server"


def test_list_compute_hosts_fail_open_no_source_cpu_info():
    """소스 호스트의 cpu_info가 비어있으면 fail-open — 소스 제외 후 전체 반환."""
    hypervisors = [
        _make_hypervisor("src-host", None),  # cpu_info 없음
        _make_hypervisor("other-1", "Skylake-Server"),
        _make_hypervisor("other-2", "Cascadelake-Server"),
    ]
    conn = _conn_with_hypervisors(hypervisors)
    result = nova.list_compute_hosts(conn, source_host="src-host")
    names = [r["name"] for r in result]
    assert "src-host" not in names
    assert "other-1" in names
    assert "other-2" in names


def test_list_compute_hosts_cpu_info_as_json_string():
    """cpu_info가 JSON 문자열로 반환되는 Nova 구버전 환경 처리."""
    h = _make_hypervisor("compute1", "IvyBridge")
    h["cpu_info"] = json.dumps({"arch": "x86_64", "model": "IvyBridge", "vendor": "Intel"})
    hypervisors = [h, _make_hypervisor("src", "IvyBridge")]
    conn = _conn_with_hypervisors(hypervisors)
    result = nova.list_compute_hosts(conn, source_host="src")
    names = [r["name"] for r in result]
    assert "compute1" in names


def test_list_compute_hosts_disabled_excluded():
    """status=disabled 호스트는 항상 제외."""
    hypervisors = [
        _make_hypervisor("compute1", "Skylake-Server"),
        _make_hypervisor("disabled-host", "Skylake-Server", status="disabled"),
    ]
    conn = _conn_with_hypervisors(hypervisors)
    result = nova.list_compute_hosts(conn, source_host="compute1")
    assert not any(r["name"] == "disabled-host" for r in result)


def test_list_compute_hosts_cpu_filter_false_all_models():
    """cpu_filter=False이면 CPU 모델이 달라도 enabled 전체 반환(소스 제외)."""
    hypervisors = [
        _make_hypervisor("src-host", "Skylake-Server"),
        _make_hypervisor("same-cpu", "Skylake-Server"),
        _make_hypervisor("diff-cpu", "Cascadelake-Server"),
        _make_hypervisor("no-cpu", None),
    ]
    conn = _conn_with_hypervisors(hypervisors)
    result = nova.list_compute_hosts(conn, source_host="src-host", cpu_filter=False)
    names = [r["name"] for r in result]
    assert "src-host" not in names, "소스 호스트는 cpu_filter=False여도 제외"
    assert "same-cpu" in names
    assert "diff-cpu" in names
    assert "no-cpu" in names


def test_list_compute_hosts_cpu_filter_false_no_source():
    """cpu_filter=False이고 source_host=None이면 전체 enabled 반환."""
    hypervisors = [
        _make_hypervisor("compute1", "Skylake-Server"),
        _make_hypervisor("compute2", "Cascadelake-Server"),
        _make_hypervisor("down", "Skylake-Server", state="down"),
    ]
    conn = _conn_with_hypervisors(hypervisors)
    result = nova.list_compute_hosts(conn, cpu_filter=False)
    names = [r["name"] for r in result]
    assert "compute1" in names
    assert "compute2" in names
    assert "down" not in names


# ───────────────────────────────────────────────
# extract_cpu_model
# ───────────────────────────────────────────────


def test_extract_cpu_model_from_dict():
    """cpu_info가 dict이면 model 반환."""
    h = {"cpu_info": {"arch": "x86_64", "model": "Skylake-Server", "vendor": "Intel"}}
    assert nova.extract_cpu_model(h) == "Skylake-Server"


def test_extract_cpu_model_from_json_string():
    """cpu_info가 JSON 문자열이면 파싱 후 model 반환."""
    h = {"cpu_info": json.dumps({"arch": "x86_64", "model": "Broadwell-IBRS", "vendor": "Intel"})}
    assert nova.extract_cpu_model(h) == "Broadwell-IBRS"


def test_extract_cpu_model_none_cpu_info():
    """cpu_info=None이면 None 반환."""
    assert nova.extract_cpu_model({"cpu_info": None}) is None


def test_extract_cpu_model_missing_model_key():
    """cpu_info가 model 키 없는 dict이면 None 반환."""
    assert nova.extract_cpu_model({"cpu_info": {"arch": "x86_64"}}) is None


def test_extract_cpu_model_invalid_json_string():
    """cpu_info가 파싱 불가 문자열이면 None 반환."""
    assert nova.extract_cpu_model({"cpu_info": "not-json"}) is None


def test_extract_cpu_model_empty_dict():
    """cpu_info={} 이면 None 반환."""
    assert nova.extract_cpu_model({"cpu_info": {}}) is None


# ───────────────────────────────────────────────
# cold_migrate_server — host 지정 / 자동 배치
# ───────────────────────────────────────────────


def test_cold_migrate_server_with_host_uses_microversion_2_56():
    """host 지정 시 microversion 2.56 헤더와 함께 migrate action을 POST한다."""
    conn = MagicMock()
    conn.compute.get_endpoint.return_value = "http://nova:8774/v2.1"
    nova.cold_migrate_server(conn, "server-1", host="compute2")
    conn.session.post.assert_called_once()
    call_kwargs = conn.session.post.call_args
    assert "compute 2.56" in call_kwargs.kwargs.get("headers", {}).get("OpenStack-API-Version", "")
    body = call_kwargs.kwargs.get("json", {})
    assert body == {"migrate": {"host": "compute2"}}


def test_cold_migrate_server_no_host_uses_sdk():
    """host 미지정 시 기존 SDK 경로(migrate_server)를 사용한다."""
    conn = MagicMock()
    nova.cold_migrate_server(conn, "server-1", host=None)
    conn.compute.migrate_server.assert_called_once_with("server-1")
    conn.session.post.assert_not_called()


# ───────────────────────────────────────────────
# cold-migrate 엔드포인트 — host body 전달
# ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cold_migrate_with_host_body(admin_client, mock_conn):
    """cold-migrate에 host body를 전달하면 nova.cold_migrate_server에 host가 넘어간다."""
    with patch("app.api.identity.admin.nova.cold_migrate_server") as mock_fn:
        resp = await admin_client.post(
            "/api/v1/admin/instances/inst-1/cold-migrate",
            json={"host": "compute2"},
        )
    assert resp.status_code == 200
    mock_fn.assert_called_once()
    _, kwargs = mock_fn.call_args
    assert kwargs.get("host") == "compute2" or mock_fn.call_args.args[2] == "compute2"


@pytest.mark.asyncio
async def test_cold_migrate_without_host_body(admin_client, mock_conn):
    """cold-migrate에 body={}를 전달해도 host=None으로 처리된다(하위 호환)."""
    with patch("app.api.identity.admin.nova.cold_migrate_server") as mock_fn:
        resp = await admin_client.post(
            "/api/v1/admin/instances/inst-1/cold-migrate",
            json={},
        )
    assert resp.status_code == 200
    mock_fn.assert_called_once()


# ───────────────────────────────────────────────
# /compute-hosts?cpu_filter=false 엔드포인트
# ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compute_hosts_cpu_filter_false_passes_param(admin_client, mock_conn):
    """cpu_filter=false 쿼리 파라미터가 nova.list_compute_hosts에 cpu_filter=False로 전달된다."""
    with patch("app.api.identity.admin.nova.list_compute_hosts", return_value=[]) as mock_fn:
        resp = await admin_client.get("/api/v1/admin/compute-hosts?cpu_filter=false")
    assert resp.status_code == 200
    mock_fn.assert_called_once()
    _, kwargs = mock_fn.call_args
    passed = kwargs.get("cpu_filter", mock_fn.call_args.args[2] if len(mock_fn.call_args.args) > 2 else True)
    assert passed is False


# ───────────────────────────────────────────────
# _extract_os_error
# ───────────────────────────────────────────────


def test_extract_os_error_from_message_attr():
    """message 속성이 있는 예외에서 메시지 추출."""
    e = Exception("raw")
    e.message = "No valid host was found"  # type: ignore[attr-defined]
    assert nova._extract_os_error(e) == "No valid host was found"


def test_extract_os_error_from_response_json():
    """response 객체의 JSON faultstring에서 추출."""
    resp = MagicMock()
    resp.json.return_value = {"faultstring": "No valid host was found"}
    e = Exception("raw")
    e.response = resp  # type: ignore[attr-defined]
    assert "No valid host was found" in nova._extract_os_error(e)


def test_extract_os_error_fallback_to_str():
    """message/response 모두 없으면 str(e) 사용."""
    e = ValueError("something went wrong")
    assert "something went wrong" in nova._extract_os_error(e)


# ───────────────────────────────────────────────
# get_server_migration_status
# ───────────────────────────────────────────────


def _make_server_migration(
    *,
    id: str = "mig-1",
    source_compute: str = "src",
    dest_compute: str = "dst",
    dest_host: str | None = None,
    status: str = "running",
    migration_type: str = "live-migration",
    memory_total_bytes: int = 1000,
    memory_processed_bytes: int = 400,
) -> MagicMock:
    m = MagicMock()
    m.id = id
    m.source_compute = source_compute
    m.dest_compute = dest_compute
    m.dest_host = dest_host
    m.status = status
    m.migration_type = migration_type
    m.memory_total_bytes = memory_total_bytes
    m.memory_processed_bytes = memory_processed_bytes
    m.memory_remaining_bytes = memory_total_bytes - memory_processed_bytes
    return m


def test_get_server_migration_status_active():
    """MIGRATING 중 source→dest + 메모리 진행률 반환."""
    conn = MagicMock()
    srv = MagicMock()
    srv.compute_host = "src-host"
    conn.compute.get_server.return_value = srv
    conn.compute.server_migrations.return_value = [
        _make_server_migration(
            source_compute="src-host", dest_compute="dst-host", memory_total_bytes=1000, memory_processed_bytes=450
        )
    ]

    result = nova.get_server_migration_status(conn, "server-1")

    assert result["host"] == "src-host"
    assert result["migration"] is not None
    assert result["migration"]["source"] == "src-host"
    assert result["migration"]["dest"] == "dst-host"
    assert result["migration"]["memory_percent"] == 45.0
    assert result["error"] is None


def test_get_server_migration_status_dest_host_priority():
    """dest_host가 있으면 dest_compute보다 우선한다."""
    conn = MagicMock()
    srv = MagicMock()
    srv.compute_host = "src"
    conn.compute.get_server.return_value = srv
    conn.compute.server_migrations.return_value = [
        _make_server_migration(dest_compute="dst-compute", dest_host="dst-host.example.com")
    ]

    result = nova.get_server_migration_status(conn, "server-1")
    assert result["migration"]["dest"] == "dst-host.example.com"


def test_get_server_migration_status_no_active():
    """진행 중 마이그레이션 없으면 migration=None."""
    conn = MagicMock()
    srv = MagicMock()
    srv.compute_host = "compute1"
    srv.fault = None
    conn.compute.get_server.return_value = srv
    conn.compute.server_migrations.return_value = []
    conn.compute.migrations.return_value = []

    result = nova.get_server_migration_status(conn, "server-1")
    assert result["migration"] is None
    assert result["host"] == "compute1"


def test_get_server_migration_status_separates_fault_from_failed_migration():
    """A recent console fault must not suppress a prior failed migration record."""
    conn = MagicMock()
    srv = MagicMock()
    srv.compute_host = "compute1"
    srv.fault = {"message": "Guest does not have a console available.", "created": "2026-11-18T13:29:41Z"}
    conn.compute.get_server.return_value = srv
    conn.compute.server_migrations.return_value = []
    conn.compute.migrations.return_value = [
        MagicMock(
            id="migration-1",
            status="error",
            migration_type="live-migration",
            source_compute="compute1",
            dest_compute="compute2",
            created_at="2026-11-12T09:19:25Z",
            updated_at="2026-11-12T09:20:05Z",
        )
    ]

    result = nova.get_server_migration_status(conn, "server-1")
    assert result["server_id"] == "server-1"
    assert result["error"] == srv.fault["message"]
    assert result["migration"] == {
        "id": "migration-1",
        "source": "compute1",
        "dest": "compute2",
        "status": "error",
        "type": "live-migration",
        "memory_percent": None,
        "created_at": "2026-11-12T09:19:25Z",
        "updated_at": "2026-11-12T09:20:05Z",
    }


def test_get_server_migration_status_memory_zero_total():
    """memory_total_bytes=0 이면 memory_percent=None (ZeroDivision 방지)."""
    conn = MagicMock()
    srv = MagicMock()
    srv.compute_host = "src"
    conn.compute.get_server.return_value = srv
    conn.compute.server_migrations.return_value = [
        _make_server_migration(memory_total_bytes=0, memory_processed_bytes=0)
    ]

    result = nova.get_server_migration_status(conn, "server-1")
    assert result["migration"]["memory_percent"] is None


# ───────────────────────────────────────────────
# abort_live_migration / force_complete_live_migration
# ───────────────────────────────────────────────


def test_abort_live_migration_with_id():
    """migration_id 명시 시 바로 abort 호출."""
    conn = MagicMock()
    nova.abort_live_migration(conn, "server-1", migration_id="mig-99")
    conn.compute.abort_server_migration.assert_called_once_with("mig-99", "server-1")


def test_abort_live_migration_auto_resolve():
    """migration_id 생략 시 server_migrations에서 자동 해석."""
    conn = MagicMock()
    active = MagicMock()
    active.id = "mig-auto"
    conn.compute.server_migrations.return_value = [active]

    nova.abort_live_migration(conn, "server-1")
    conn.compute.abort_server_migration.assert_called_once_with("mig-auto", "server-1")


def test_abort_live_migration_no_active_raises():
    """진행 중 마이그레이션 없으면 ValueError."""
    conn = MagicMock()
    conn.compute.server_migrations.return_value = []
    with pytest.raises(ValueError, match="진행 중인"):
        nova.abort_live_migration(conn, "server-1")


def test_force_complete_live_migration_with_id():
    conn = MagicMock()
    nova.force_complete_live_migration(conn, "server-1", migration_id="mig-77")
    conn.compute.force_complete_server_migration.assert_called_once_with("mig-77", "server-1")


def test_force_complete_live_migration_auto_resolve():
    conn = MagicMock()
    active = MagicMock()
    active.id = "mig-fc"
    conn.compute.server_migrations.return_value = [active]

    nova.force_complete_live_migration(conn, "server-1")
    conn.compute.force_complete_server_migration.assert_called_once_with("mig-fc", "server-1")


# ───────────────────────────────────────────────
# 엔드포인트 권한 검사 (non_admin → 403)
# ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compute_hosts_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/compute-hosts")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_migration_status_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/instances/inst-1/migration-status")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_abort_migration_requires_admin(non_admin_client):
    resp = await non_admin_client.post("/api/v1/admin/instances/inst-1/live-migrate/abort")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_force_complete_migration_requires_admin(non_admin_client):
    resp = await non_admin_client.post("/api/v1/admin/instances/inst-1/live-migrate/force-complete")
    assert resp.status_code == 403


# ───────────────────────────────────────────────
# 엔드포인트 — 실패 시 실제 에러 메시지 노출
# ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_live_migrate_error_message_exposed(admin_client, mock_conn):
    """라이브 마이그레이션 실패 시 Nova 실제 에러 메시지가 400 detail에 포함된다."""
    err = Exception("live migrate failure")
    err.message = "No valid host was found"  # type: ignore[attr-defined]

    with patch("app.api.identity.admin.nova.live_migrate_server", side_effect=err):
        resp = await admin_client.post(
            "/api/v1/admin/instances/inst-1/live-migrate",
            json={"host": None, "block_migration": "auto"},
        )

    assert resp.status_code == 400
    assert "No valid host was found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cold_migrate_error_message_exposed(admin_client, mock_conn):
    """콜드 마이그레이션 실패 시 Nova 실제 에러 메시지가 400 detail에 포함된다."""
    err = Exception("cold migrate failure")
    err.message = "Instance is not running"  # type: ignore[attr-defined]

    with patch("app.api.identity.admin.nova.cold_migrate_server", side_effect=err):
        resp = await admin_client.post("/api/v1/admin/instances/inst-1/cold-migrate", json={})

    assert resp.status_code == 400
    assert "Instance is not running" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_migration_status_admin_ok(admin_client, mock_conn):
    """admin은 migration-status에 접근 가능하다 (403이 아님)."""
    with patch(
        "app.api.identity.admin.nova.get_server_migration_status",
        return_value={"host": "compute1", "migration": None, "error": None},
    ):
        resp = await admin_client.get("/api/v1/admin/instances/inst-1/migration-status")
    assert resp.status_code != 403
    assert resp.json()["host"] == "compute1"


# ───────────────────────────────────────────────
# evacuate_server — nova 서비스 단위 테스트
# ───────────────────────────────────────────────


def test_evacuate_server_no_host():
    """host 미지정 시 evacuate body에 host 없이 onSharedStorage=False로 POST."""
    conn = MagicMock()
    conn.compute.get_endpoint.return_value = "http://nova:8774/v2.1"
    nova.evacuate_server(conn, "server-1")
    conn.session.post.assert_called_once()
    body = conn.session.post.call_args.kwargs.get("json", {})
    assert body == {"evacuate": {"onSharedStorage": False}}


def test_evacuate_server_with_host():
    """host 지정 시 evacuate body에 host 포함."""
    conn = MagicMock()
    conn.compute.get_endpoint.return_value = "http://nova:8774/v2.1"
    nova.evacuate_server(conn, "server-1", host="compute3")
    body = conn.session.post.call_args.kwargs.get("json", {})
    assert body["evacuate"]["host"] == "compute3"


def test_evacuate_server_shared_storage():
    """on_shared_storage=True이면 body에 onSharedStorage=True."""
    conn = MagicMock()
    conn.compute.get_endpoint.return_value = "http://nova:8774/v2.1"
    nova.evacuate_server(conn, "server-1", on_shared_storage=True)
    body = conn.session.post.call_args.kwargs.get("json", {})
    assert body["evacuate"]["onSharedStorage"] is True


# ───────────────────────────────────────────────
# evacuate 엔드포인트
# ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evacuate_requires_admin(non_admin_client):
    resp = await non_admin_client.post("/api/v1/admin/instances/inst-1/evacuate", json={})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_evacuate_default_body(admin_client, mock_conn):
    """body={}이면 host=None, on_shared_storage=False로 nova.evacuate_server 호출."""
    with patch("app.api.identity.admin.nova.evacuate_server") as mock_fn:
        resp = await admin_client.post("/api/v1/admin/instances/inst-1/evacuate", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "evacuating"
    mock_fn.assert_called_once()
    _, _, host, shared = mock_fn.call_args.args
    assert host is None
    assert shared is False


@pytest.mark.asyncio
async def test_evacuate_with_host(admin_client, mock_conn):
    """host 지정 시 nova.evacuate_server에 전달된다."""
    with patch("app.api.identity.admin.nova.evacuate_server") as mock_fn:
        resp = await admin_client.post(
            "/api/v1/admin/instances/inst-1/evacuate",
            json={"host": "compute3"},
        )
    assert resp.status_code == 200
    _, _, host, _ = mock_fn.call_args.args
    assert host == "compute3"


@pytest.mark.asyncio
async def test_evacuate_error_exposed(admin_client, mock_conn):
    """Nova 에러 메시지가 400 detail에 노출된다."""
    err = Exception("evacuate failure")
    err.message = "No valid host was found"  # type: ignore[attr-defined]
    with patch("app.api.identity.admin.nova.evacuate_server", side_effect=err):
        resp = await admin_client.post("/api/v1/admin/instances/inst-1/evacuate", json={})
    assert resp.status_code == 400
    assert "No valid host was found" in resp.json()["detail"]
