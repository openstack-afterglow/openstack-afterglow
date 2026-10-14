"""Trove DB 인스턴스 자동 백업 서비스.

Redis에 인스턴스별 자동 백업 설정을 저장하고 공유 cron 슬롯을 실행한다.
Leader만 전체 설정을 읽고, 각 참여 워커는 할당된 인스턴스를 renewable lease로 처리한다.
Daily/weekly/monthly의 기존 24시간/7일/30일 간격과 설정된 보존 개수를 유지한다.

Redis 키 (동일 primary/DB/namespace를 모든 참여 프로세스가 공유해야 함):
  config:{project_id}:{instance_id}, all_configs — 기존 사용자 설정
  pending/done:{project_id}:{instance_id} — cron 슬롯과 완료 fence
  active:{project_id}:{instance_id}:{tier} — 불확실한 제출의 journal 포인터
  journal:{project_id}:{instance_id}:{tier}:{slot} — POST 이전의 영구 unknown/accepted 기록
Journal과 active는 TTL이 없다. 응답 유실/재시작 후 정확한 이름+인스턴스의 provider
백업을 관찰할 때까지 재제출하지 않는다. Redis 유실은 exactly-once 보장이 아니다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime

from apscheduler.triggers.cron import CronTrigger

from app.services import trove
from app.services.cache import _get_redis
from app.services.work_dispatcher import (
    DispatcherUnavailable,
    WorkDispatcher,
    checkpoint,
    close_connection,
    open_connection,
    run_sync,
    work_lease,
)

_logger = logging.getLogger(__name__)

_PREFIX = "afterglow:db_auto_backup"
_ALL_KEY = f"{_PREFIX}:all_configs"
_POLL_SECONDS = 15
_LEASE_SECONDS = 90

# Journal admission is atomic with the active-tier pointer. Neither key expires:
# a lost reply (or a crash before POST) must never authorize a blind resend.
_ADMIT = """
if redis.call('EXISTS', KEYS[1]) == 1 or redis.call('EXISTS', KEYS[2]) == 1 then return 0 end
redis.call('SET', KEYS[1], ARGV[1])
redis.call('SET', KEYS[2], KEYS[1])
return 1
"""
_ENQUEUE = """
local done = redis.call('GET', KEYS[2])
if done and done >= ARGV[1] then return 0 end
return redis.call('SET', KEYS[1], ARGV[1], 'NX') and 1 or 0
"""
_FINISH = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[2], ARGV[1])
redis.call('DEL', KEYS[1])
return 1
"""


# ────────────────────────────────────────────
# Config CRUD
# ────────────────────────────────────────────


async def enable_db_auto_backup(
    project_id: str, instance_id: str, max_daily: int = 7, max_weekly: int = 0, max_monthly: int = 0
) -> dict:
    """DB 인스턴스 자동 백업 활성화. 설정을 Redis에 저장."""
    config = {
        "instance_id": instance_id,
        "project_id": project_id,
        "enabled": True,
        "max_daily": max_daily,
        "max_weekly": max_weekly,
        "max_monthly": max_monthly,
        "created_at": datetime.now(UTC).isoformat(),
    }
    r = await _get_redis()
    key = f"{_PREFIX}:config:{project_id}:{instance_id}"
    await r.set(key, json.dumps(config))
    await r.sadd(_ALL_KEY, f"{project_id}:{instance_id}")
    return config


async def disable_db_auto_backup(project_id: str, instance_id: str) -> None:
    """DB 인스턴스 자동 백업 비활성화. Redis에서 설정 삭제."""
    r = await _get_redis()
    key = f"{_PREFIX}:config:{project_id}:{instance_id}"
    await r.delete(key)
    await r.srem(_ALL_KEY, f"{project_id}:{instance_id}")


async def get_db_auto_backup_config(project_id: str, instance_id: str) -> dict | None:
    """DB 인스턴스의 자동 백업 설정 조회."""
    r = await _get_redis()
    key = f"{_PREFIX}:config:{project_id}:{instance_id}"
    raw = await r.get(key)
    return json.loads(raw) if raw else None


async def list_db_auto_backup_configs(project_id: str) -> list[dict]:
    """프로젝트의 모든 DB 자동 백업 설정 조회."""
    r = await _get_redis()
    members = await r.smembers(_ALL_KEY)
    configs = []
    for member in members:
        pid, iid = member.split(":", 1)
        if pid != project_id:
            continue
        cfg = await get_db_auto_backup_config(pid, iid)
        if cfg:
            configs.append(cfg)
    return configs


async def list_all_db_auto_backup_configs() -> list[dict]:
    """전체 프로젝트의 모든 DB 자동 백업 설정 조회 (백그라운드 워커용)."""
    r = await _get_redis()
    members = await r.smembers(_ALL_KEY)
    configs = []
    for member in members:
        pid, iid = member.split(":", 1)
        cfg = await get_db_auto_backup_config(pid, iid)
        if cfg:
            configs.append(cfg)
    return configs


# ────────────────────────────────────────────
# Backup 이름 파싱 / 분류
# ────────────────────────────────────────────


def _make_backup_name(instance_id: str, tier: str, *, now: datetime | None = None) -> str:
    """Retain the existing UTC day-based provider name and calendar intervals."""
    date = (now or datetime.now(UTC)).strftime("%Y%m%d")
    return f"auto_{instance_id[:8]}_{tier}_{date}"


def _is_auto_backup(backup: dict, instance_id: str, tier: str) -> bool:
    name = backup.get("name", "")
    prefix = f"auto_{instance_id[:8]}_{tier}_"
    return name.startswith(prefix)


def _backup_date(backup: dict) -> datetime | None:
    """백업의 created 또는 updated 타임스탬프를 datetime으로 반환."""
    ts = backup.get("created_at") or backup.get("updated_at")
    if not ts:
        return None
    try:
        value = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    except Exception:
        return None


# ────────────────────────────────────────────
# Backup Cycle
# ────────────────────────────────────────────
def _text(raw) -> str:
    return raw.decode() if isinstance(raw, bytes) else raw or ""


def _key(kind: str, member: str) -> str:
    return f"{_PREFIX}:{kind}:{member}"


async def _policy(redis, member: str) -> dict | None:
    await checkpoint()
    raw = await redis.get(_key("config", member))
    await checkpoint()
    config = json.loads(raw) if raw else None
    return config if config and config.get("enabled") else None


async def _listing(conn, instance_id: str) -> list[dict]:
    # The optional Trove UI API normally returns [] on error. That is never
    # evidence of absence for submission or retention.
    backups = await run_sync(trove.list_backups, conn, instance_id, strict=True)
    return [backup for backup in backups if backup.get("instance_id") == instance_id]


async def _observe(redis, conn, instance_id: str, journal_key: str, operation: dict) -> dict | None:
    matches = [
        backup
        for backup in await _listing(conn, instance_id)
        if backup.get("name") == operation["name"] and backup.get("id")
    ]
    if len(matches) != 1:
        return None
    backup = matches[0]
    # Recording an accepted late reply/read is safe even when ownership was
    # revoked; only provider mutation and slot completion require the fence.
    operation.update(state="accepted", backup_id=backup["id"])
    await redis.set(journal_key, json.dumps(operation))
    return backup


async def _finish_failed(redis, active_key: str, journal_key: str, operation: dict) -> None:
    # A definite terminal failure is not an unknown submission: retain its
    # non-replay receipt, but let future cron slots run without pruning backups.
    operation["state"] = "failed"
    await redis.set(journal_key, json.dumps(operation))
    await checkpoint()
    await redis.delete(active_key)


async def _cycle(conn, redis, member: str, slot: str) -> bool:
    _, instance_id = member.split(":", 1)
    clock = datetime.fromisoformat(slot)
    complete = True
    for tier, default, min_interval in (("daily", 2, 86400), ("weekly", 2, 7 * 86400), ("monthly", 1, 30 * 86400)):
        config = await _policy(redis, member)
        if config is None:
            return True
        max_count = config.get(f"max_{tier}", default)
        if max_count <= 0:
            continue

        active_key = _key("active", f"{member}:{tier}")
        journal_key = _text(await redis.get(active_key))
        if journal_key:
            operation_raw = await redis.get(journal_key)
            if not operation_raw:
                raise RuntimeError("Trove active submission has no journal")
            operation = json.loads(operation_raw)
            observed = await _observe(redis, conn, instance_id, journal_key, operation)
            if not observed:
                complete = False
                continue
            if str(observed.get("status", "")).upper() in ("FAILED", "ERROR"):
                await _finish_failed(redis, active_key, journal_key, operation)
                continue
            # Do not delete older recovery backups while the replacement is
            # merely accepted, in progress, or failed.
            if observed.get("status") not in ("COMPLETED", "available"):
                complete = False
                continue
            await checkpoint()
            await redis.delete(active_key)

        all_backups = await _listing(conn, instance_id)
        config = await _policy(redis, member)
        if config is None:
            return True
        max_count = config.get(f"max_{tier}", default)
        if max_count <= 0:
            continue
        tier_backups = [backup for backup in all_backups if _is_auto_backup(backup, instance_id, tier)]
        tier_backups.sort(key=lambda b: b.get("created_at", b.get("updated_at", "")), reverse=True)
        last_date = _backup_date(tier_backups[0]) if tier_backups else None
        should_create = not last_date or (clock - last_date).total_seconds() >= min_interval
        if should_create:
            name = _make_backup_name(instance_id, tier, now=clock)
            journal_key = _key("journal", f"{member}:{tier}:{slot}")
            operation = {"state": "accepted", "name": name, "slot": slot, "instance_id": instance_id}
            existing = await redis.get(journal_key)
            if existing:
                operation = json.loads(existing)
                observed = await _observe(redis, conn, instance_id, journal_key, operation)
            else:
                # Exact provider identity also prevents duplication if Redis
                # hints were discarded but a provider backup remains visible.
                matches = [b for b in all_backups if b.get("name") == name and b.get("id")]
                if len(matches) > 1:
                    complete = False
                    continue
                observed = matches[0] if matches else None
                if not observed:
                    operation = {"state": "unknown", "name": name, "slot": slot, "instance_id": instance_id}
                    if not await redis.eval(_ADMIT, 2, journal_key, active_key, json.dumps(operation)):
                        complete = False
                        continue
                    config = await _policy(redis, member)
                    if not config or config.get(f"max_{tier}", default) <= 0:
                        return True
                    try:
                        result = await run_sync(
                            trove.create_backup,
                            conn,
                            instance_id,
                            name,
                            f"자동 백업 ({tier})",
                            no_retry=True,
                        )
                    except DispatcherUnavailable:
                        raise
                    except Exception:
                        _logger.warning(
                            "db_auto_backup: submission uncertain (instance=%s, tier=%s)",
                            instance_id,
                            tier,
                            exc_info=True,
                        )
                        complete = False
                        continue
                    operation.update(state="accepted", backup_id=result["id"])
                    await redis.set(journal_key, json.dumps(operation))
                    observed = await _observe(redis, conn, instance_id, journal_key, operation)
            if observed and str(observed.get("status", "")).upper() in ("FAILED", "ERROR"):
                operation["backup_id"] = observed["id"]
                await _finish_failed(redis, active_key, journal_key, operation)
                continue
            if not observed or observed.get("status") not in ("COMPLETED", "available"):
                complete = False
                continue
            if observed not in tier_backups:
                tier_backups.insert(0, observed)

        # Every awaited boundary above may have changed policy or ownership.
        config = await _policy(redis, member)
        if config is None:
            return True
        max_count = config.get(f"max_{tier}", default)
        if max_count <= 0:
            continue
        for backup in tier_backups[max_count:]:
            if not backup.get("id") or backup.get("status") not in ("COMPLETED", "available", None):
                continue
            latest = await _policy(redis, member)
            if latest is None:
                return True
            if latest.get(f"max_{tier}", default) != max_count:
                break
            await run_sync(trove.delete_backup, conn, backup["id"])
    return complete


async def _schedule_tick(dispatcher: WorkDispatcher, trigger: CronTrigger, clock: datetime) -> None:
    if not await dispatcher.is_leader():
        return
    redis = dispatcher.redis
    next_key = _key("cron_next", str(trigger))
    raw = await redis.get(next_key)
    event = (
        datetime.fromisoformat(_text(raw))
        if raw
        else trigger.get_next_fire_time(
            None,
            clock.replace(second=0, microsecond=0),
        )
    )
    if event is not None:
        event = event.astimezone(UTC)
    due = event is not None and event <= clock
    configs = await list_all_db_auto_backup_configs()
    runnable = []
    for config in configs:
        if not config.get("enabled"):
            continue
        member = f"{config['project_id']}:{config['instance_id']}"
        pending_key = _key("pending", member)
        if due:
            await redis.eval(_ENQUEUE, 2, pending_key, _key("done", member), event.isoformat())
        if await redis.exists(pending_key):
            runnable.append(member)
    # A slow provider POST belongs to the independent execution child, not to
    # this leader scan. Catch up to the next future cron event without a burst.
    if await dispatcher.publish(runnable):
        if due:
            event = trigger.get_next_fire_time(None, clock.replace(microsecond=0))
            if event == clock.replace(microsecond=0):
                event = trigger.get_next_fire_time(event, clock)
        if event is not None:
            await redis.set(next_key, event.astimezone(UTC).isoformat())


async def _drain(task):
    # Repeated cancellation must not orphan a live SDK thread or close its
    # connection while it is still using it.
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


async def _execute_tick(dispatcher: WorkDispatcher, connection_factory=None) -> None:
    if connection_factory is None:
        from app.services.keystone import get_admin_connection_for_project

        connection_factory = get_admin_connection_for_project
    redis = dispatcher.redis
    for _ in range(await dispatcher.pending()):
        claimed = await dispatcher.claim(_LEASE_SECONDS)
        if claimed is None:
            break
        member, owner = claimed
        try:
            async with work_lease(dispatcher, member, owner, seconds=_LEASE_SECONDS) as lease:
                slot = _text(await redis.get(_key("pending", member)))
                if not slot or not await _policy(redis, member):
                    continue
                target = asyncio.create_task(_execute_target(redis, member, slot, connection_factory))
                revoked = asyncio.create_task(lease.revoked.wait())
                try:
                    done, _ = await asyncio.wait((target, revoked), return_when=asyncio.FIRST_COMPLETED)
                    if revoked in done:
                        if not target.done() and not target.cancelling():
                            target.cancel()
                        with suppress(asyncio.CancelledError):
                            await _drain(target)
                        raise DispatcherUnavailable("Trove target lease was revoked")
                    target.result()
                finally:
                    if not target.done() and not target.cancelling():
                        target.cancel()
                    revoked.cancel()
                    drain = asyncio.ensure_future(asyncio.gather(target, revoked, return_exceptions=True))
                    await _drain(drain)
                    if asyncio.current_task().cancelling():
                        raise asyncio.CancelledError
        except DispatcherUnavailable:
            raise
        except Exception:
            _logger.warning("db_auto_backup: owned cycle failed (target=%s)", member, exc_info=True)


async def _execute_target(redis, member, slot, connection_factory):
    conn = await open_connection(connection_factory, member.split(":", 1)[0])
    try:
        if await _cycle(conn, redis, member, slot):
            await checkpoint()
            await redis.eval(_FINISH, 2, _key("pending", member), _key("done", member), slot)
    finally:
        await close_connection(conn)


async def _scan_loop(dispatcher, trigger):
    while True:
        try:
            await _schedule_tick(dispatcher, trigger, datetime.now(UTC))
        except DispatcherUnavailable:
            raise
        except Exception:
            _logger.warning("db_auto_backup: leader scan failed", exc_info=True)
        await asyncio.sleep(_POLL_SECONDS)


async def _execution_loop(dispatcher):
    while True:
        await _execute_tick(dispatcher)
        await asyncio.sleep(_POLL_SECONDS)


async def run_scheduler(cron_expr: str) -> None:
    """Parent-callable shared cron consumer with independently owned children."""
    trigger = CronTrigger.from_crontab(cron_expr)
    while True:
        try:
            async with WorkDispatcher(await _get_redis(), _PREFIX) as dispatcher:
                tasks = [
                    asyncio.create_task(_scan_loop(dispatcher, trigger)),
                    asyncio.create_task(_execution_loop(dispatcher)),
                ]
                try:
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                finally:
                    for task in tasks:
                        if not task.done() and not task.cancelling():
                            task.cancel()
                    drain = asyncio.ensure_future(asyncio.gather(*tasks, return_exceptions=True))
                    await _drain(drain)
        except Exception:
            _logger.warning("db_auto_backup: coordination unavailable", exc_info=True)
        await asyncio.sleep(_POLL_SECONDS)
