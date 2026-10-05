"""notion_worker 워커 동작 + 기본값 30분 + FastAPI-free 회귀 가드 테스트."""

import select
import signal
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _enable_global_notion_sync(monkeypatch):
    monkeypatch.setattr(
        "app.services.resource_policy_store.get_runtime_setting",
        AsyncMock(return_value=True),
    )


# ---------------------------------------------------------------------------
# 1. 기본값 30분 검증
# ---------------------------------------------------------------------------


def test_notion_target_create_request_default_interval():
    """NotionTargetCreateRequest의 interval_minutes 기본값이 30이어야 한다."""
    from app.api.identity.admin_notion import NotionTargetCreateRequest

    req = NotionTargetCreateRequest(api_key="k", database_id="d")
    assert req.interval_minutes == 30


def test_notion_config_request_default_interval():
    """NotionConfigRequest의 interval_minutes 기본값이 30이어야 한다."""
    from app.api.identity.admin_notion import NotionConfigRequest

    req = NotionConfigRequest(api_key="k", database_id="d")
    assert req.interval_minutes == 30


# ---------------------------------------------------------------------------
# 2. 워커 사이클이 interval_minutes를 존중하는지 검증
# ---------------------------------------------------------------------------


@pytest.fixture
def make_target():
    """테스트용 NotionTarget dict 생성 헬퍼."""

    def _make(
        target_id: int = 1,
        enabled: bool = True,
        interval_minutes: int = 30,
        last_sync: str | None = None,
    ) -> dict:
        return {
            "id": target_id,
            "enabled": enabled,
            "interval_minutes": interval_minutes,
            "last_sync": last_sync,
            "api_key": "test-api-key",
            "database_id": "test-db-id",
            "users_database_id": "",
            "hypervisors_database_id": "",
            "gpu_spec_database_id": "",
        }

    return _make


@pytest.mark.asyncio
async def test_worker_cycle_skips_disabled_target(make_target):
    """enabled=False 타겟은 동기화를 건너뛴다."""
    from app.notion_worker import _run_sync_cycle

    target = make_target(enabled=False)

    with (
        patch("app.notion_worker._run_notion_target_sync", new_callable=AsyncMock) as mock_sync,
        patch("app.services.notion_sync.list_notion_targets", new_callable=AsyncMock, return_value=[target]),
        patch("app.services.notion_sync.get_notion_config", new_callable=AsyncMock, return_value=None),
    ):
        await _run_sync_cycle()

    mock_sync.assert_not_called()


@pytest.mark.asyncio
async def test_worker_cycle_skips_target_within_interval(make_target):
    """마지막 동기화 경과 시간이 interval_minutes 미만이면 건너뛴다."""
    from app.notion_worker import _run_sync_cycle

    # 방금 동기화됨 (5분 전) — 30분 간격이므로 아직 스킵
    recent = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    target = make_target(interval_minutes=30, last_sync=recent)

    with (
        patch("app.notion_worker._run_notion_target_sync", new_callable=AsyncMock) as mock_sync,
        patch("app.services.notion_sync.list_notion_targets", new_callable=AsyncMock, return_value=[target]),
        patch("app.services.notion_sync.get_notion_config", new_callable=AsyncMock, return_value=None),
    ):
        await _run_sync_cycle()

    mock_sync.assert_not_called()


@pytest.mark.asyncio
async def test_worker_cycle_syncs_target_after_interval(make_target):
    """마지막 동기화 경과 시간이 interval_minutes 이상이면 동기화한다."""
    from app.notion_worker import _run_sync_cycle

    # 45분 전 동기화 — 30분 간격이므로 실행해야 함
    old = (datetime.now(UTC) - timedelta(minutes=45)).isoformat()
    target = make_target(interval_minutes=30, last_sync=old)

    with (
        patch("app.notion_worker._run_notion_target_sync", new_callable=AsyncMock) as mock_sync,
        patch("app.services.notion_sync.list_notion_targets", new_callable=AsyncMock, return_value=[target]),
        patch("app.services.notion_sync.get_notion_config", new_callable=AsyncMock, return_value=None),
    ):
        await _run_sync_cycle()

    mock_sync.assert_called_once_with(target)


@pytest.mark.asyncio
async def test_worker_cycle_syncs_target_with_no_last_sync(make_target):
    """last_sync가 None(한 번도 동기화 안 됨)이면 즉시 동기화한다."""
    from app.notion_worker import _run_sync_cycle

    target = make_target(last_sync=None)

    with (
        patch("app.notion_worker._run_notion_target_sync", new_callable=AsyncMock) as mock_sync,
        patch("app.services.notion_sync.list_notion_targets", new_callable=AsyncMock, return_value=[target]),
        patch("app.services.notion_sync.get_notion_config", new_callable=AsyncMock, return_value=None),
    ):
        await _run_sync_cycle()

    mock_sync.assert_called_once_with(target)


@pytest.mark.asyncio
async def test_worker_cycle_respects_custom_interval(make_target):
    """interval_minutes가 5분으로 설정된 타겟은 5분이 지나면 동기화한다."""
    from app.notion_worker import _run_sync_cycle

    # 6분 전 동기화 — 5분 간격이므로 실행해야 함
    old = (datetime.now(UTC) - timedelta(minutes=6)).isoformat()
    target = make_target(interval_minutes=5, last_sync=old)

    with (
        patch("app.notion_worker._run_notion_target_sync", new_callable=AsyncMock) as mock_sync,
        patch("app.services.notion_sync.list_notion_targets", new_callable=AsyncMock, return_value=[target]),
        patch("app.services.notion_sync.get_notion_config", new_callable=AsyncMock, return_value=None),
    ):
        await _run_sync_cycle()

    mock_sync.assert_called_once_with(target)


@pytest.mark.asyncio
async def test_run_sync_cycle_refreshes_gpu_catalog_before_fallback_mapping_calls():
    from app.notion_worker import _run_sync_cycle

    instances = [
        {
            "name": "alias-vm",
            "instance_id": "inst-1",
            "status": "ACTIVE",
            "project_name": "proj",
            "flavor_name": "gpu.3060lhr_8c_16g",
            "vcpus": 8,
            "ram_gb": 16,
            "gpu_name": "RTX 3060 LHR",
            "gpu_count": 1,
            "gpu_spec_page_id": "page-3060",
            "fixed_ip": "",
            "floating_ip": "",
            "created_at": "2026-07-08T00:00:00Z",
            "compute_host": "",
            "user_page_id": "",
            "hypervisor_page_id": "",
        }
    ]
    call_order: list[str] = []

    async def _refresh():
        call_order.append("refresh")

    async def _collect_instance_data(**kwargs):
        call_order.append("collect")
        assert kwargs["gpu_name_to_page_id"] == {"RTX 3060 LHR": "page-3060"}
        return instances

    with (
        patch("app.database.is_db_available", return_value=True),
        patch("app.services.gpu_catalog.refresh_device_map_from_db", new=AsyncMock(side_effect=_refresh)) as refresh,
        patch("app.services.notion_sync.list_notion_targets", new=AsyncMock(return_value=[])),
        patch(
            "app.services.notion_sync.get_notion_config",
            new=AsyncMock(
                return_value={
                    "enabled": True,
                    "api_key": "test-api-key",
                    "database_id": "test-db-id",
                    "users_database_id": "",
                    "hypervisors_database_id": "",
                    "gpu_spec_database_id": "gpu-spec-db-id",
                }
            ),
        ),
        patch(
            "app.services.gpu_inventory.get_gpu_spec_list",
            side_effect=lambda: call_order.append("gpu_specs") or [{"name": "RTX 3060 LHR"}],
        ),
        patch(
            "app.services.gpu_inventory.build_alias_to_device_name_map",
            side_effect=lambda: call_order.append("alias_map") or {"RTX-3060-LHR": "RTX 3060 LHR"},
        ),
        patch(
            "app.services.openstack_inventory.collect_instance_data", new=AsyncMock(side_effect=_collect_instance_data)
        ),
        patch(
            "app.services.notion_sync.sync_gpu_specs_to_notion",
            new=AsyncMock(return_value={"created": 0, "updated": 0}),
        ),
        patch(
            "app.services.notion_sync.fetch_gpu_spec_page_ids_by_name",
            new=AsyncMock(return_value={"RTX 3060 LHR": "page-3060"}),
        ),
        patch("app.services.notion_sync.build_gpu_usage_by_gpu", return_value={}),
        patch("app.services.notion_sync.sync_to_notion", new=AsyncMock(return_value={"created": 1, "updated": 0})),
        patch("app.services.notion_sync.save_notion_config", new=AsyncMock()),
        patch("app.services.notion_sync.migrate_instance_db_to_korean", new=AsyncMock(return_value=False)),
    ):
        await _run_sync_cycle()

    refresh.assert_awaited_once()
    assert call_order.index("refresh") < call_order.index("gpu_specs")
    assert call_order.index("refresh") < call_order.index("collect")
    assert call_order.index("refresh") < call_order.index("alias_map")


# ---------------------------------------------------------------------------
# 3. FastAPI-free 회귀 가드
#    서브프로세스로 격리 실행해 fastapi/starlette가 워커 import 경로에
#    끌려들어오지 않음을 확인한다. Phase 2 리팩토링의 핵심 보장.
# ---------------------------------------------------------------------------

_FASTAPI_FREE_SCRIPT = """
import sys

# Afterglow-owned worker entry point and its runtime dependencies.
import app.notion_worker
import app.services.gpu_inventory
import app.services.openstack_inventory
import app.services.notion_sync

leaked = [m for m in sys.modules if m in ("fastapi", "starlette", "uvicorn")]
if leaked:
    print("FAIL: leaked modules:", leaked, file=sys.stderr)
    sys.exit(1)
print("OK")
"""

# 테스트 파일 기준 backend/ 루트 경로 (CI/CD 환경 호환)
_BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_worker_imports_are_fastapi_free():
    """Afterglow-owned worker imports must not load FastAPI, Starlette, or Uvicorn."""
    result = subprocess.run(
        [sys.executable, "-c", _FASTAPI_FREE_SCRIPT],
        capture_output=True,
        text=True,
        cwd=str(_BACKEND_DIR),
    )
    assert result.returncode == 0, (
        f"워커 import 경로에 FastAPI/starlette/uvicorn가 포함됨:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert result.stdout.strip() == "OK"


@pytest.mark.asyncio
async def test_worker_cycle_skips_all_external_work_when_global_gate_is_disabled(monkeypatch):
    from app.notion_worker import _run_sync_cycle

    get_setting = AsyncMock(return_value=False)
    list_targets = AsyncMock()
    monkeypatch.setattr("app.services.resource_policy_store.get_runtime_setting", get_setting)
    monkeypatch.setattr("app.services.notion_sync.list_notion_targets", list_targets)

    await _run_sync_cycle()

    get_setting.assert_awaited_once_with("notion.sync_enabled")
    list_targets.assert_not_awaited()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX worker shutdown signals")
@pytest.mark.parametrize("shutdown_signal", [signal.SIGTERM, signal.SIGINT])
def test_worker_shutdown_signals_cancel_pending_work_cleanly(shutdown_signal):
    script = """
import asyncio
from app import notion_worker

async def pending_work():
    print("READY", flush=True)
    try:
        await asyncio.Future()
    finally:
        print("CLEANED", flush=True)

notion_worker.main = pending_work
asyncio.run(notion_worker._main_async())
"""
    with subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=_BACKEND_DIR,
    ) as process:
        try:
            assert select.select([process.stdout], [], [], 10)[0], "worker did not become ready"
            assert process.stdout.readline().strip() == "READY"
            process.send_signal(shutdown_signal)
            stdout, stderr = process.communicate(timeout=5)
            assert process.returncode == 0, stderr
            assert stdout.strip() == "CLEANED"
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
