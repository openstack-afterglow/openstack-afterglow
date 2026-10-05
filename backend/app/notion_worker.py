"""Notion Sync Worker — 별도 파드/프로세스로 실행.

사용법:
  uv run python -m app.notion_worker

Notion 다중 타겟 + 레거시 NotionConfig 동기화를 1분 간격으로 수행.
메인 API(app.main)에서 분리되어 독립 프로세스로 실행 가능.
"""

import asyncio
import logging
import os
import signal
from datetime import UTC, datetime

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

_logger = logging.getLogger("notion.worker")

_CHECK_INTERVAL = 60  # 1분마다 타겟 확인


async def _run_notion_target_sync(target: dict) -> None:
    """단일 NotionTarget에 대해 전체 동기화를 실행한다."""
    from app.services import notion_sync
    from app.services.gpu_inventory import (
        build_alias_to_device_name_map,
        get_gpu_spec_list,
    )
    from app.services.openstack_inventory import (
        collect_hypervisor_data,
        collect_instance_data,
    )

    target_id = target["id"]
    api_key = target["api_key"]
    database_id = target["database_id"]
    users_db_id = target.get("users_database_id", "")
    hypervisors_db_id = target.get("hypervisors_database_id", "")
    gpu_spec_db_id = target.get("gpu_spec_database_id", "")

    gpu_name_to_page_id: dict[str, str] = {}
    if gpu_spec_db_id:
        try:
            gpu_specs = get_gpu_spec_list()
            await notion_sync.sync_gpu_specs_to_notion(api_key, gpu_spec_db_id, gpu_specs)
            gpu_name_to_page_id = await notion_sync.fetch_gpu_spec_page_ids_by_name(api_key, gpu_spec_db_id)
        except Exception:
            _logger.warning("Notion target %d GPU spec 동기화 오류", target_id, exc_info=True)

    host_to_page_id: dict[str, str] = {}
    hypervisors: list[dict] = []
    if hypervisors_db_id:
        try:
            hypervisors = await collect_hypervisor_data(gpu_name_to_page_id=gpu_name_to_page_id)
            await notion_sync.sync_hypervisors_to_notion(api_key, hypervisors_db_id, hypervisors)
            host_to_page_id = await notion_sync.fetch_hypervisor_page_ids_by_name(api_key, hypervisors_db_id)
        except Exception:
            _logger.warning("Notion target %d 하이퍼바이저 동기화 오류", target_id, exc_info=True)

    email_to_page_id: dict[str, str] = {}
    if users_db_id:
        email_to_page_id = await notion_sync.fetch_user_page_ids_by_email(api_key, users_db_id)

    instances = await collect_instance_data(
        email_to_page_id=email_to_page_id,
        host_to_page_id=host_to_page_id,
        gpu_name_to_page_id=gpu_name_to_page_id,
    )

    # GPU 사용량 집계
    alias_to_device_name = build_alias_to_device_name_map()
    usage_by_gpu = notion_sync.build_gpu_usage_by_gpu(hypervisors, instances, alias_to_device_name)

    if gpu_spec_db_id and usage_by_gpu:
        try:
            gpu_specs = get_gpu_spec_list()
            await notion_sync.sync_gpu_specs_to_notion(api_key, gpu_spec_db_id, gpu_specs, usage_by_gpu=usage_by_gpu)
        except Exception:
            _logger.warning("Notion target %d GPU spec 집계 업데이트 오류", target_id, exc_info=True)

    await notion_sync.sync_to_notion(api_key, database_id, instances)

    now_iso = datetime.now(UTC).isoformat()
    await notion_sync.update_notion_target(
        target_id,
        {
            "last_sync": now_iso,
            "hypervisors_last_sync": now_iso if hypervisors_db_id else None,
            "gpu_spec_last_sync": now_iso if gpu_spec_db_id else None,
        },
    )
    _logger.info("Notion target %d 동기화 완료 (instances=%d)", target_id, len(instances))


async def _run_sync_cycle() -> None:
    """1회 동기화 사이클: 다중 타겟 → fallback NotionConfig."""
    from app.database import is_db_available
    from app.services import notion_sync
    from app.services.gpu_inventory import (
        build_alias_to_device_name_map,
        get_gpu_spec_list,
    )
    from app.services.openstack_inventory import (
        collect_hypervisor_data,
        collect_instance_data,
    )
    from app.services.resource_policy_store import ResourcePolicyStorageUnavailable, get_runtime_setting

    try:
        enabled = await get_runtime_setting("notion.sync_enabled")
    except ResourcePolicyStorageUnavailable:
        _logger.warning("Notion synchronization skipped: runtime setting storage is unavailable")
        return
    if enabled is not True:
        _logger.info("Notion synchronization is disabled by the global runtime setting")
        return

    if is_db_available():
        try:
            from app.services import gpu_catalog

            await gpu_catalog.refresh_device_map_from_db()
        except Exception:
            _logger.warning("GPU 카탈로그 DB overlay 갱신 실패 — 기존 device map으로 Notion sync 진행", exc_info=True)

    targets = await notion_sync.list_notion_targets(include_api_key=True)
    if targets:
        now = datetime.now(UTC)
        for target in targets:
            if not target.get("enabled"):
                continue
            last_sync_str = target.get("last_sync")
            interval_min = target.get("interval_minutes", 5)
            if last_sync_str:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync_str.replace("Z", "+00:00"))
                    # MySQL/aiomysql는 timezone-naive datetime을 반환하므로 UTC로 명시
                    if last_sync_dt.tzinfo is None:
                        last_sync_dt = last_sync_dt.replace(tzinfo=UTC)
                    elapsed_min = (now - last_sync_dt).total_seconds() / 60
                    if elapsed_min < interval_min:
                        continue
                except Exception:
                    pass
            try:
                await _run_notion_target_sync(target)
            except Exception:
                _logger.warning("Notion target %d 동기화 오류", target["id"], exc_info=True)
        return

    # ── fallback: NotionConfig (싱글톤 레거시 설정) ──
    config = await notion_sync.get_notion_config()
    if not config or not config.get("enabled"):
        return

    api_key = config["api_key"]
    users_db_id = config.get("users_database_id", "")
    hypervisors_db_id = config.get("hypervisors_database_id", "")
    gpu_spec_db_id = config.get("gpu_spec_database_id", "")

    gpu_name_to_page_id: dict[str, str] = {}
    if gpu_spec_db_id:
        try:
            gpu_specs = get_gpu_spec_list()
            await notion_sync.sync_gpu_specs_to_notion(api_key, gpu_spec_db_id, gpu_specs)
            config["gpu_spec_last_sync"] = datetime.now(UTC).isoformat()
            gpu_name_to_page_id = await notion_sync.fetch_gpu_spec_page_ids_by_name(api_key, gpu_spec_db_id)
        except Exception:
            _logger.warning("Notion GPU spec 동기화 오류", exc_info=True)

    host_to_page_id: dict[str, str] = {}
    hypervisors: list[dict] = []
    if hypervisors_db_id:
        try:
            hypervisors = await collect_hypervisor_data(gpu_name_to_page_id=gpu_name_to_page_id)
            await notion_sync.sync_hypervisors_to_notion(api_key, hypervisors_db_id, hypervisors)
            config["hypervisors_last_sync"] = datetime.now(UTC).isoformat()
            host_to_page_id = await notion_sync.fetch_hypervisor_page_ids_by_name(api_key, hypervisors_db_id)
        except Exception:
            _logger.warning("Notion 하이퍼바이저 동기화 오류", exc_info=True)

    email_to_page_id: dict[str, str] = {}
    if users_db_id:
        email_to_page_id = await notion_sync.fetch_user_page_ids_by_email(api_key, users_db_id)

    instances = await collect_instance_data(
        email_to_page_id=email_to_page_id,
        host_to_page_id=host_to_page_id,
        gpu_name_to_page_id=gpu_name_to_page_id,
    )

    alias_to_device_name = build_alias_to_device_name_map()
    usage_by_gpu = notion_sync.build_gpu_usage_by_gpu(hypervisors, instances, alias_to_device_name)

    if gpu_spec_db_id:
        try:
            gpu_specs = get_gpu_spec_list()
            await notion_sync.sync_gpu_specs_to_notion(api_key, gpu_spec_db_id, gpu_specs, usage_by_gpu=usage_by_gpu)
            config["gpu_spec_last_sync"] = datetime.now(UTC).isoformat()
        except Exception:
            _logger.warning("Notion GPU spec 집계 업데이트 오류", exc_info=True)

    await notion_sync.sync_to_notion(api_key, config["database_id"], instances)
    config["last_sync"] = datetime.now(UTC).isoformat()
    await notion_sync.save_notion_config(config)

    try:
        await notion_sync.migrate_instance_db_to_korean(api_key, config["database_id"])
    except Exception:
        _logger.warning("Notion DB 한국어 마이그레이션 오류", exc_info=True)


async def main() -> None:
    from app.config import get_settings
    from app.database import close_db, init_db, is_db_available

    _logger.info("Notion Sync Worker 시작")

    settings = get_settings()
    if settings.database_url:
        try:
            init_db(
                settings.database_url,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                connect_timeout=settings.database_connect_timeout,
                pool_timeout=settings.database_pool_timeout,
                unhealthy_seconds=settings.database_unhealthy_seconds,
            )
            _logger.info("DB 연결 완료")
        except Exception:
            _logger.warning("DB 연결 실패 — Notion 동기화 비활성화", exc_info=True)
            return

    if not is_db_available():
        _logger.warning("DB 미사용 환경 — Notion 워커 종료")
        return

    # DB 자동 백업 스케줄러 (APScheduler cron)
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler()
    try:
        from app.services import db_auto_backup as _dab
        from app.services.keystone import get_admin_connection_for_project

        async def _run_db_backup_job() -> None:
            """APScheduler에서 호출되는 DB 자동 백업 사이클."""
            import asyncio as _asyncio

            try:
                configs = await _dab.list_all_db_auto_backup_configs()
                if configs:
                    _logger.info("db_auto_backup: %d개 DB 인스턴스 자동 백업 시작", len(configs))
                for cfg in configs:
                    project_id = cfg.get("project_id")
                    instance_id = cfg.get("instance_id")
                    if not project_id or not instance_id:
                        continue
                    try:
                        conn = await _asyncio.to_thread(get_admin_connection_for_project, project_id)
                        await _dab.run_db_backup_cycle(conn, project_id, instance_id, cfg)
                    except Exception:
                        _logger.warning(
                            "db_auto_backup: 백업 사이클 실패 (instance=%s)",
                            instance_id,
                            exc_info=True,
                        )
            except Exception:
                _logger.warning("db_auto_backup: 잡 실행 오류", exc_info=True)

        cron_expr = settings.database_db_auto_backup_cron
        scheduler.add_job(
            _run_db_backup_job,
            CronTrigger.from_crontab(cron_expr),
            id="db_auto_backup",
            replace_existing=True,
            misfire_grace_time=300,
        )
        scheduler.start()
        _logger.info("DB 자동 백업 스케줄러 등록 완료 (cron=%s)", cron_expr)
    except Exception:
        _logger.warning("DB 자동 백업 스케줄러 등록 실패", exc_info=True)

    try:
        await asyncio.sleep(30)  # 초기 대기

        while True:
            try:
                await _run_sync_cycle()
            except Exception:
                _logger.exception("Notion 동기화 사이클 오류")
            await asyncio.sleep(_CHECK_INTERVAL)
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            await asyncio.sleep(0)
        await close_db()
        _logger.info("Notion Sync Worker 종료")


async def _main_async() -> None:
    loop = asyncio.get_running_loop()
    task = asyncio.create_task(main())
    for shutdown_signal in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(shutdown_signal, task.cancel)
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        for shutdown_signal in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(shutdown_signal)


if __name__ == "__main__":
    asyncio.run(_main_async())
