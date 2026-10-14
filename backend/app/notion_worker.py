"""Standalone, FastAPI-free Notion and Trove target workers.

Only the elected scanner reads the registry. Execution and membership heartbeat
are independent of discovery; each target and every shared output are leased.
"""

import asyncio
import logging
import os
import re
import secrets
import signal
from contextlib import asynccontextmanager
from datetime import UTC, datetime

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
_logger = logging.getLogger("notion.worker")
_CHECK_INTERVAL = 60
_POLL_INTERVAL = 2
_PREFIX = "afterglow:notion:work"
_LEASE_SECONDS = 90
_OUTPUT_FIELDS = ("database_id", "hypervisors_database_id", "gpu_spec_database_id")

# Acquire the entire output set atomically: a partially acquired set would allow
# two targets sharing multiple databases to deadlock or overlap.
_OUTPUT_ACQUIRE = """
for _, key in ipairs(KEYS) do
  if redis.call('EXISTS', key) == 1 then return 0 end
end
for _, key in ipairs(KEYS) do redis.call('SET', key, ARGV[1], 'EX', ARGV[2]) end
return 1
"""
_OUTPUT_RENEW = """
for _, key in ipairs(KEYS) do
  if redis.call('GET', key) ~= ARGV[1] then return 0 end
end
for _, key in ipairs(KEYS) do redis.call('EXPIRE', key, ARGV[2]) end
return 1
"""
_OUTPUT_RELEASE = """
for _, key in ipairs(KEYS) do
  if redis.call('GET', key) == ARGV[1] then redis.call('DEL', key) end
end
return 1
"""


def _output_identity(value: str) -> str:
    """Notion UUID, dashed UUID and copied URL identify the same database."""
    match = re.search(r"[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}", value)
    return match.group().replace("-", "").lower() if match else value.strip().lower()


def _due(config: dict | None, now: datetime | None = None) -> bool:
    if not config or not config.get("enabled"):
        return False
    last = config.get("last_sync")
    if not last:
        return True
    try:
        stamp = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        return ((now or datetime.now(UTC)) - stamp).total_seconds() >= float(config.get("interval_minutes", 5)) * 60
    except (ValueError, TypeError):
        return True


async def _enabled() -> bool:
    from app.services.resource_policy_store import ResourcePolicyStorageUnavailable, get_runtime_setting

    try:
        return await get_runtime_setting("notion.sync_enabled") is True
    except ResourcePolicyStorageUnavailable:
        return False


async def _discover_targets() -> list[str]:
    from app.services import notion_sync

    if not await _enabled():
        return []
    targets = await notion_sync.list_notion_targets()
    if targets:
        return [str(target["id"]) for target in targets if _due(target)]
    return ["legacy"] if _due(await notion_sync.get_notion_config()) else []


async def _current_target(member: str) -> dict | None:
    from app.services import notion_sync

    if not await _enabled():
        return None
    if member == "legacy":
        return await notion_sync.get_notion_config()
    return await notion_sync.get_notion_target(int(member), include_api_key=True)


async def _drain(tasks) -> None:
    tasks = list(tasks)
    for task in tasks:
        if not task.cancelling():
            task.cancel()
    drained = asyncio.gather(*tasks, return_exceptions=True)
    cancelled = False
    while not drained.done():
        try:
            await asyncio.shield(drained)
        except asyncio.CancelledError:
            cancelled = True
    drained.result()
    if cancelled:
        raise asyncio.CancelledError


async def _inventory_read(fn, **kwargs):
    from app.services import notion_sync

    await notion_sync.worker_checkpoint()
    # Inventory owns its connection and closes in finally. Do not cancel its
    # async wrapper while its underlying SDK thread is still using that handle.
    operation = asyncio.create_task(fn(**kwargs))
    try:
        result = await asyncio.shield(operation)
    except asyncio.CancelledError:
        drained = asyncio.gather(operation, return_exceptions=True)
        while not drained.done():
            try:
                await asyncio.shield(drained)
            except asyncio.CancelledError:
                continue
        drained.result()
        raise
    await notion_sync.worker_checkpoint()
    return result


@asynccontextmanager
async def _output_lease(redis, target: dict):
    from app.services.work_dispatcher import DispatcherUnavailable

    keys = sorted(
        {f"{_PREFIX}:output:{_output_identity(target[field])}" for field in _OUTPUT_FIELDS if target.get(field)}
    )
    owner = secrets.token_hex(24)
    if not keys or not await redis.eval(_OUTPUT_ACQUIRE, len(keys), *keys, owner, _LEASE_SECONDS):
        yield None
        return
    revoked = asyncio.Event()

    async def check():
        if revoked.is_set():
            raise DispatcherUnavailable("Notion output ownership lost")
        started = asyncio.get_running_loop().time()
        try:
            retained = await redis.eval(_OUTPUT_RENEW, len(keys), *keys, owner, _LEASE_SECONDS)
        except Exception as exc:
            revoked.set()
            raise DispatcherUnavailable("Notion output coordination unavailable") from exc
        if not retained or asyncio.get_running_loop().time() >= started + _LEASE_SECONDS:
            revoked.set()
            raise DispatcherUnavailable("Notion output ownership lost")

    async def renew():
        # Loss cancels the executor; renewal remains independent of HTTP work.
        try:
            while True:
                await asyncio.sleep(_LEASE_SECONDS / 3)
                await check()
        except Exception:
            revoked.set()

    renewal = asyncio.create_task(renew())
    try:
        yield check, revoked
    finally:
        try:
            await _drain([renewal])
        finally:
            # Cleanup remains permitted after loss and finishes before cancel
            # propagates, including a cancel first received during release.
            cleanup = asyncio.create_task(redis.eval(_OUTPUT_RELEASE, len(keys), *keys, owner))
            cancelled = False
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    cancelled = True
            cleanup.result()
            if cancelled:
                raise asyncio.CancelledError


def _checked(stats):
    if stats and stats.get("errors", 0):
        raise RuntimeError("Notion synchronization was partial; success timestamp withheld")


async def _run_notion_target_sync(target: dict) -> None:
    from app.database import is_db_available
    from app.services import gpu_catalog, notion_sync
    from app.services.gpu_inventory import build_alias_to_device_name_map, get_gpu_spec_list
    from app.services.openstack_inventory import collect_hypervisor_data, collect_instance_data
    from app.services.work_dispatcher import DispatcherUnavailable

    # Catalog overlays are process-local, so refresh in the executor, not scanner.
    if is_db_available():
        try:
            await gpu_catalog.refresh_device_map_from_db()
        except Exception:
            _logger.warning("GPU catalog overlay refresh failed; retaining current device map", exc_info=True)
    api_key = target["api_key"]
    gpu_db = target.get("gpu_spec_database_id", "")
    hypervisor_db = target.get("hypervisors_database_id", "")
    users_db = target.get("users_database_id", "")
    gpu_pages = {}
    gpu_ok = False
    hypervisor_ok = False
    if gpu_db:
        try:
            _checked(await notion_sync.sync_gpu_specs_to_notion(api_key, gpu_db, get_gpu_spec_list()))
            gpu_pages = await notion_sync.fetch_gpu_spec_page_ids_by_name(api_key, gpu_db)
            gpu_ok = True
        except DispatcherUnavailable:
            raise
        except Exception:
            _logger.warning("Notion GPU section failed; continuing instance sync", exc_info=True)
    hypervisors = []
    host_pages = {}
    if hypervisor_db:
        try:
            hypervisors = await _inventory_read(collect_hypervisor_data, gpu_name_to_page_id=gpu_pages)
            _checked(await notion_sync.sync_hypervisors_to_notion(api_key, hypervisor_db, hypervisors))
            host_pages = await notion_sync.fetch_hypervisor_page_ids_by_name(api_key, hypervisor_db)
            hypervisor_ok = True
        except DispatcherUnavailable:
            raise
        except Exception:
            _logger.warning("Notion hypervisor section failed; continuing instance sync", exc_info=True)
    emails = await notion_sync.fetch_user_page_ids_by_email(api_key, users_db) if users_db else {}
    instances = await _inventory_read(
        collect_instance_data, email_to_page_id=emails, host_to_page_id=host_pages, gpu_name_to_page_id=gpu_pages
    )
    usage = notion_sync.build_gpu_usage_by_gpu(hypervisors, instances, build_alias_to_device_name_map())
    if gpu_db and (usage or "id" not in target):
        try:
            _checked(
                await notion_sync.sync_gpu_specs_to_notion(api_key, gpu_db, get_gpu_spec_list(), usage_by_gpu=usage)
            )
        except DispatcherUnavailable:
            raise
        except Exception:
            gpu_ok = False
            _logger.warning("Notion GPU aggregate section failed; continuing instance sync", exc_info=True)
    _checked(await notion_sync.sync_to_notion(api_key, target["database_id"], instances))
    if "id" not in target:
        await notion_sync.migrate_instance_db_to_korean(api_key, target["database_id"])
    await notion_sync.worker_checkpoint()
    stamp = datetime.now(UTC).isoformat()
    timestamps = {"last_sync": stamp}
    if hypervisor_ok:
        timestamps["hypervisors_last_sync"] = stamp
    if gpu_ok:
        timestamps["gpu_spec_last_sync"] = stamp
    if "id" in target:
        await notion_sync.update_notion_target(target["id"], timestamps)
    else:
        await notion_sync.update_notion_config_timestamps(timestamps)


async def _execute_target(dispatcher, member: str, owner: str) -> None:
    from app.services import notion_sync
    from app.services.work_dispatcher import DispatcherUnavailable, work_lease

    async with work_lease(dispatcher, member, owner, seconds=_LEASE_SECONDS) as lease:
        target = await _current_target(member)
        if not _due(target):
            return
        async with _output_lease(dispatcher.redis, target) as output:
            if output is None:
                return
            output_check, output_revoked = output
            fields = (*_OUTPUT_FIELDS, "users_database_id", "api_key")

            async def policy_check():
                await lease.check()
                current = await _current_target(member)
                if not _due(current) or any(current.get(field) != target.get(field) for field in fields):
                    raise DispatcherUnavailable("Notion target policy changed")
                await output_check()
                await lease.check()

            with notion_sync.worker_policy(policy_check):
                await notion_sync.worker_checkpoint()
                execution = asyncio.create_task(_run_notion_target_sync(target))
                watchers = [asyncio.create_task(lease.revoked.wait()), asyncio.create_task(output_revoked.wait())]
                try:
                    done, _ = await asyncio.wait([execution, *watchers], return_when=asyncio.FIRST_COMPLETED)
                    if execution in done:
                        execution.result()
                    else:
                        raise DispatcherUnavailable("Notion execution ownership revoked")
                finally:
                    await _drain([execution, *watchers])


async def _scan(dispatcher) -> None:
    from app.services.work_dispatcher import DispatcherUnavailable

    while True:
        try:
            if await dispatcher.is_leader():
                await dispatcher.publish(await _discover_targets())
        except DispatcherUnavailable:
            raise
        except Exception:
            _logger.exception("Notion target discovery failed; retaining execution incarnation")
        await asyncio.sleep(_CHECK_INTERVAL)


async def _execute(dispatcher) -> None:
    from app.services.work_dispatcher import DispatcherUnavailable

    while True:
        claimed = await dispatcher.claim(_LEASE_SECONDS)
        if claimed:
            try:
                await _execute_target(dispatcher, *claimed)
            except DispatcherUnavailable:
                if dispatcher.lost:
                    raise
            except Exception:
                _logger.exception("Notion target %s synchronization failed", claimed[0])
        else:
            await asyncio.sleep(_POLL_INTERVAL)


async def _run_target_worker() -> None:
    from app.services.cache import _get_redis
    from app.services.work_dispatcher import WorkDispatcher

    await asyncio.sleep(30)
    while True:
        try:
            async with WorkDispatcher(await _get_redis(), _PREFIX) as dispatcher:
                tasks = [asyncio.create_task(_scan(dispatcher)), asyncio.create_task(_execute(dispatcher))]
                try:
                    await asyncio.gather(*tasks)
                finally:
                    await _drain(tasks)
        except Exception:
            _logger.exception("Notion coordination unavailable; rejoining")
            await asyncio.sleep(_POLL_INTERVAL)


async def main() -> None:
    from app.config import get_settings
    from app.database import close_db, init_db, is_db_available
    from app.services.db_auto_backup import run_scheduler

    settings = get_settings()
    if settings.database_url:
        init_db(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            connect_timeout=settings.database_connect_timeout,
            pool_timeout=settings.database_pool_timeout,
            unhealthy_seconds=settings.database_unhealthy_seconds,
        )
    if not is_db_available():
        _logger.warning("DB unavailable; Notion worker exiting")
        return
    tasks = [
        asyncio.create_task(_run_target_worker()),
        asyncio.create_task(run_scheduler(settings.database_db_auto_backup_cron)),
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        try:
            await _drain(tasks)
        finally:
            closing = asyncio.create_task(close_db())
            cancelled = False
            while not closing.done():
                try:
                    await asyncio.shield(closing)
                except asyncio.CancelledError:
                    cancelled = True
            closing.result()
            if cancelled:
                raise asyncio.CancelledError


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
