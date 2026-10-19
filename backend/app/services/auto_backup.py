"""Calendar-based Cinder backups with durable submission fences.

Policies and operation journals are authoritative Redis data, not expiring cache.
A slot is claimed before contacting Cinder and is never replayed after an ambiguous
submission. All scheduled backups are full; retention runs only after completion.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
from contextlib import asynccontextmanager, contextmanager, nullcontext, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger
from openstack.exceptions import HttpException
from pydantic import BaseModel, Field, field_validator, model_validator

from app.services import cinder
from app.services.cache import _get_redis, invalidate, invalidation
from app.services.work_dispatcher import DispatcherUnavailable, WorkDispatcher

_logger = logging.getLogger(__name__)
_PREFIX = "afterglow:auto_backup"
_ALL_KEY = f"{_PREFIX}:all_configs"
_POLL_SECONDS = 15
_LEASE_SECONDS = 90


@dataclass(frozen=True)
class RecoveryPointEngine:
    """Immutable provider lane; task-local binding keeps concurrent lanes isolated."""

    prefix: str
    resource: str


_ENGINE: ContextVar[RecoveryPointEngine | None] = ContextVar("cinder_recovery_engine", default=None)


@contextmanager
def using_engine(engine: RecoveryPointEngine):
    token = _ENGINE.set(engine)
    try:
        yield
    finally:
        _ENGINE.reset(token)


def _resource() -> str:
    engine = _ENGINE.get()
    return engine.resource if engine else "backup"


def _prefix() -> str:
    engine = _ENGINE.get()
    return engine.prefix if engine else _PREFIX


def _all_key() -> str:
    return f"{_prefix()}:all_configs" if _ENGINE.get() else _ALL_KEY


def _id_field() -> str:
    return f"{_resource()}_id"


def _provider(action: str):
    return getattr(cinder, f"{action}_{_resource()}{'s' if action == 'list' else ''}")


# Compare/renew/release follows hypervisor_review's renewable operation lease.
_RENEW = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""
_SAVE = """
if (redis.call('get', KEYS[1]) or '') ~= ARGV[1] then return 0 end
redis.call('set', KEYS[1], ARGV[2])
redis.call('sadd', KEYS[2], ARGV[3])
return 1
"""
_REMOVE = """
redis.call('del', KEYS[1])
if not redis.call('get', KEYS[3]) then redis.call('srem', KEYS[2], ARGV[1]) end
return 1
"""
_CLAIM = """
if redis.call('get', KEYS[1]) ~= ARGV[1] then return 0 end
if redis.call('get', KEYS[2]) ~= ARGV[2] then return 0 end
if redis.call('exists', KEYS[3]) == 1 or redis.call('exists', KEYS[4]) == 1 then return 0 end
if redis.call('exists', KEYS[5]) == 1 then return 0 end
redis.call('set', KEYS[3], ARGV[3])
redis.call('set', KEYS[4], ARGV[3])
redis.call('set', KEYS[1], ARGV[4])
return 1
"""
_RESULT = """
if redis.call('get', KEYS[2]) ~= ARGV[1] then return 0 end
if (redis.call('get', KEYS[1]) or '') ~= ARGV[2] then return 0 end
if redis.call('get', KEYS[3]) ~= ARGV[3] then return 0 end
if ARGV[4] ~= '' then redis.call('set', KEYS[1], ARGV[4]) end
redis.call('set', KEYS[4], ARGV[5])
if ARGV[6] == 'done' then
  redis.call('del', KEYS[3])
  if ARGV[4] == '' then redis.call('srem', KEYS[5], ARGV[7]) end
else redis.call('set', KEYS[3], ARGV[5]) end
return 1
"""
_FENCE = """
if redis.call('get', KEYS[1]) ~= ARGV[1] then return 0 end
local raw = redis.call('get', KEYS[2])
if not raw then return 0 end
local cfg = cjson.decode(raw)
if cfg.revision ~= ARGV[2] or cfg.enabled ~= true then return 0 end
return 1
"""


class PolicySettings(BaseModel):
    max_daily: int = Field(default=2, ge=0, le=30, strict=True)
    max_weekly: int = Field(default=2, ge=0, le=30, strict=True)
    max_monthly: int = Field(default=1, ge=0, le=30, strict=True)
    enabled: bool = Field(default=True, strict=True)
    schedule_time: str = "03:00"
    timezone: str = "UTC"
    weekly_day: int = Field(default=0, ge=0, le=6, strict=True)
    monthly_day: int = Field(default=1, ge=1, le=28, strict=True)
    force: bool = Field(default=False, strict=True)

    @field_validator("schedule_time")
    @classmethod
    def valid_time(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("schedule_time must be HH:mm")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("timezone must be an IANA timezone") from None
        return value

    @model_validator(mode="after")
    def positive_enabled_tier(self):
        if self.enabled and not (self.max_daily or self.max_weekly or self.max_monthly):
            raise ValueError("An enabled policy needs at least one positive retention tier")
        return self


def _now(now: datetime | None) -> datetime:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("The scheduler clock must be timezone-aware")
    return value.astimezone(UTC)


def _time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Schedule timestamp must be a string")
    return _now(datetime.fromisoformat(value.replace("Z", "+00:00")))


def next_event(config: dict, now: datetime) -> tuple[str | None, str | None]:
    """Next strictly future UTC calendar event; monthly > weekly > daily on ties."""
    if not config["enabled"]:
        return None, None
    hour, minute = map(int, config["schedule_time"].split(":"))
    events = []
    for priority, tier in enumerate(("monthly", "weekly", "daily")):
        if config[f"max_{tier}"] == 0:
            continue
        args = (
            {"day": config["monthly_day"]}
            if tier == "monthly"
            else ({"day_of_week": config["weekly_day"]} if tier == "weekly" else {})
        )
        trigger = CronTrigger(hour=hour, minute=minute, timezone=ZoneInfo(config["timezone"]), **args)
        event = trigger.get_next_fire_time(None, _now(now) + timedelta(microseconds=1))
        if event is not None:
            events.append((event.astimezone(UTC), priority, tier))
    if not events:
        return None, None
    event, _, tier = min(events)
    return event.isoformat(), tier


def _key(kind: str, project_id: str, volume_id: str) -> str:
    return f"{_prefix()}:{kind}:{project_id}:{volume_id}"


def _dump(value: dict) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _text(raw) -> str:
    return raw.decode() if isinstance(raw, bytes) else raw or ""


def _normalize(raw: str, project_id: str, volume_id: str, now: datetime) -> dict:
    config = json.loads(raw)
    if not isinstance(config, dict) or config.get("project_id") != project_id or config.get("volume_id") != volume_id:
        raise ValueError("Policy identity is invalid")
    if config.get("schema_version") not in (None, 1, 2):
        raise ValueError("Policy schema version is not supported")
    settings = PolicySettings.model_validate(config).model_dump()
    config.update(settings)
    if config.get("schema_version") != 2:
        config.update(schema_version=2, revision=secrets.token_hex(16), updated_at=now.isoformat())
        config["next_run_at"], config["next_tier"] = next_event(config, now)
    config.setdefault("created_at", now.isoformat())
    config.setdefault("last_run_at", None)
    config.setdefault("last_status", "never")
    config.setdefault(f"last_{_id_field()}", None)
    config.setdefault("last_error", None)
    if not isinstance(config.get("revision"), str) or not config["revision"]:
        raise ValueError("Policy revision is invalid")
    if config["enabled"]:
        _time(config["next_run_at"])
        if config.get("next_tier") not in ("daily", "weekly", "monthly"):
            raise ValueError("Policy next tier is invalid")
        if config[f"max_{config['next_tier']}"] == 0:
            raise ValueError("Policy next tier is disabled")
    return config


def build_policy(project_id: str, volume_id: str, *, now: datetime | None = None, **settings) -> dict:
    """Build a fresh durable policy without writing; registration can atomically save both lanes."""
    clock = _now(now)
    config = PolicySettings(**settings).model_dump()
    config.update(
        project_id=project_id,
        volume_id=volume_id,
        schema_version=2,
        revision=secrets.token_hex(16),
        created_at=clock.isoformat(),
        updated_at=clock.isoformat(),
        last_run_at=None,
        last_status="never",
        last_error=None,
    )
    config[f"last_{_id_field()}"] = None
    config["next_run_at"], config["next_tier"] = next_event(config, clock)
    return config


async def get_auto_backup_config(project_id: str, volume_id: str, *, now: datetime | None = None) -> dict | None:
    redis = await _get_redis()
    key = _key("config", project_id, volume_id)
    while True:
        raw = _text(await redis.get(key))
        if not raw:
            return None
        try:
            config = _normalize(raw, project_id, volume_id, _now(now))
        except (ValueError, TypeError, KeyError):
            # Preserve the original bytes. A corrupt policy must not execute or disappear.
            try:
                saved = json.loads(raw)
            except ValueError:
                saved = {}
            config = PolicySettings().model_dump()
            if isinstance(saved, dict):
                config.update(saved)
            for field, default in (
                ("created_at", None),
                ("updated_at", None),
                ("last_run_at", None),
                (f"last_{_id_field()}", None),
            ):
                config.setdefault(field, default)
            config["identity_verified"] = (
                isinstance(saved, dict)
                and saved.get("project_id") == project_id
                and saved.get("volume_id") == volume_id
            )
            config.update(
                project_id=project_id,
                volume_id=volume_id,
                enabled=False,
                next_run_at=None,
                next_tier=None,
                last_status="error",
                last_error=f"Saved {_resource()} policy is invalid; edit it before resuming.",
            )
            return config
        normalized = _dump(config)
        if normalized == raw:
            return config
        if await redis.eval(_SAVE, 2, key, _all_key(), raw, normalized, f"{project_id}:{volume_id}"):
            return config


async def enable_auto_backup(
    project_id: str,
    volume_id: str,
    max_daily: int = 2,
    max_weekly: int = 2,
    max_monthly: int = 1,
    *,
    enabled: bool = True,
    schedule_time: str = "03:00",
    timezone: str = "UTC",
    weekly_day: int = 0,
    monthly_day: int = 1,
    force: bool = False,
    now: datetime | None = None,
) -> dict:
    """Upsert a policy, preserving history and beginning at the next future event."""
    settings = PolicySettings(
        max_daily=max_daily,
        max_weekly=max_weekly,
        max_monthly=max_monthly,
        enabled=enabled,
        schedule_time=schedule_time,
        timezone=timezone,
        weekly_day=weekly_day,
        monthly_day=monthly_day,
        force=force,
    ).model_dump()
    clock = _now(now)
    redis = await _get_redis()
    key = _key("config", project_id, volume_id)
    while True:
        raw = _text(await redis.get(key))
        try:
            saved = json.loads(raw) if raw else {}
        except ValueError:
            # Explicit edits can repair corrupt data without losing the original payload.
            saved = {"invalid_legacy_payload": raw}
        config = dict(saved) if isinstance(saved, dict) else {"invalid_legacy_payload": saved}
        # An explicit policy edit supersedes instance-creation compensation ownership.
        config.pop("registration_id", None)
        config.update(
            settings,
            volume_id=volume_id,
            project_id=project_id,
            schema_version=2,
            revision=secrets.token_hex(16),
            updated_at=clock.isoformat(),
        )
        config.setdefault("created_at", clock.isoformat())
        for field, default in (
            ("last_run_at", None),
            ("last_status", "never"),
            (f"last_{_id_field()}", None),
            ("last_error", None),
        ):
            config.setdefault(field, default)
        config["next_run_at"], config["next_tier"] = next_event(config, clock)
        if await redis.eval(_SAVE, 2, key, _all_key(), raw, _dump(config), f"{project_id}:{volume_id}"):
            return config


async def disable_auto_backup(project_id: str, volume_id: str) -> None:
    """Remove only the policy, never Cinder backups or a submission journal."""
    redis = await _get_redis()
    await redis.eval(
        _REMOVE,
        3,
        _key("config", project_id, volume_id),
        _all_key(),
        _key("active", project_id, volume_id),
        f"{project_id}:{volume_id}",
    )


async def list_auto_backup_configs(project_id: str) -> list[dict]:
    redis = await _get_redis()
    configs = []
    for member in await redis.smembers(_all_key()):
        pid, separator, vid = _text(member).partition(":")
        if separator and pid == project_id:
            config = await get_auto_backup_config(pid, vid)
            if config is not None:
                configs.append(config)
    return configs


class VolumeLease:
    def __init__(self, redis, key: str, owner: str):
        self.redis, self.key, self.owner = redis, key, owner
        self.lost = False

    async def renew(self):
        while True:
            await asyncio.sleep(_LEASE_SECONDS / 3)
            try:
                if not await self.redis.eval(_RENEW, 1, self.key, self.owner, _LEASE_SECONDS):
                    self.lost = True
                    return
            except Exception:
                self.lost = True
                return

    async def current(self, project_id: str, volume_id: str, revision: str) -> bool:
        return not self.lost and bool(
            await self.redis.eval(_FENCE, 2, self.key, _key("config", project_id, volume_id), self.owner, revision)
        )


@asynccontextmanager
async def _volume_lease(redis, project_id: str, volume_id: str, *, owner: str | None = None):
    lease = VolumeLease(redis, _key("lease", project_id, volume_id), owner or secrets.token_hex(24))
    acquired = (
        _text(await redis.get(lease.key)) == owner
        if owner is not None
        else await redis.set(lease.key, lease.owner, nx=True, ex=_LEASE_SECONDS)
    )
    if not acquired:
        yield None
        return
    renewal = asyncio.create_task(lease.renew())
    try:
        yield lease
    finally:
        renewal.cancel()
        with suppress(asyncio.CancelledError):
            await renewal
        await redis.eval(_RELEASE, 1, lease.key, lease.owner)


async def _sdk(fn, *args, **kwargs):
    # Do not close a connection or release its lease while a worker thread is submitting.
    work = asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        with suppress(Exception):
            await work
        raise


async def _result(redis, lease, project_id, volume_id, operation, *, done=False) -> bool:
    active_key = _key("active", project_id, volume_id)
    active_raw = _text(await redis.get(active_key))
    if not active_raw or json.loads(active_raw)["slot"] != operation["slot"] or lease.lost:
        return False
    config_key = _key("config", project_id, volume_id)
    while True:
        raw = _text(await redis.get(config_key))
        config = json.loads(raw) if raw else None
        if config is not None:
            config.update(
                last_run_at=operation["submitted_at"],
                last_status=operation["status"],
                **{f"last_{_id_field()}": operation.get(_id_field())},
                last_error=operation.get("error"),
            )
        if await redis.eval(
            _RESULT,
            5,
            config_key,
            lease.key,
            active_key,
            operation["slot"],
            _all_key(),
            lease.owner,
            raw,
            active_raw,
            _dump(config) if config is not None else "",
            _dump(operation),
            "done" if done else "active",
            f"{project_id}:{volume_id}",
        ):
            return True
        if _text(await redis.get(lease.key)) != lease.owner or _text(await redis.get(active_key)) != active_raw:
            return False


def _owned(backup: dict, project_id: str, volume_id: str) -> bool:
    if _resource() == "snapshot":
        metadata = backup.get("metadata")
        return (
            bool(project_id and volume_id)
            and backup.get("project_id") == project_id
            and backup.get("volume_id") == volume_id
            and isinstance(metadata, dict)
            and metadata.get("afterglow_policy_kind") == "auto_snapshot"
            and metadata.get("afterglow_project_id") == project_id
            and metadata.get("afterglow_volume_id") == volume_id
            and metadata.get("afterglow_tier") in ("daily", "weekly", "monthly")
            and bool(metadata.get("afterglow_revision"))
            and bool(metadata.get("afterglow_slot"))
        )
    return (
        bool(project_id and volume_id)
        and backup.get("project_id") == project_id
        and backup.get("volume_id") == volume_id
    )


def _tier(backup: dict, project_id: str, volume_id: str) -> str | None:
    if not _owned(backup, project_id, volume_id):
        return None
    if _resource() == "snapshot":
        metadata = backup["metadata"]
        tier = metadata["afterglow_tier"]
        slot_prefix = _key("slot", project_id, volume_id) + ":"
        slot = metadata["afterglow_slot"]
        if not isinstance(slot, str) or not slot.startswith(slot_prefix):
            return None
        try:
            due = _time(slot[len(slot_prefix) :])
        except ValueError:
            return None
        return tier if backup.get("name") == _point_name(project_id, volume_id, tier, due) else None
    name = backup.get("name") or ""
    for tier in ("monthly", "weekly", "daily"):
        # Legacy names are considered only with exact source/project metadata, never prefix alone.
        if re.fullmatch(rf"auto_{re.escape(volume_id[:8])}_{tier}_\d{{8}}", name):
            return tier
        prefix = re.escape(f"afterglow_auto_{project_id}_{volume_id}_{tier}_")
        if re.fullmatch(rf"{prefix}\d{{8}}T\d{{6}}Z", name):
            return tier
    return None


def _created_time(backup: dict) -> datetime | None:
    value = backup.get("created_at")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Cinder's offset-free created_at representation is UTC.
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        return None


def _point_name(project_id, volume_id, tier, due):
    kind = "afterglow_auto_snapshot" if _resource() == "snapshot" else "afterglow_auto"
    return f"{kind}_{project_id}_{volume_id}_{tier}_{due.strftime('%Y%m%dT%H%M%SZ')}"


def _snapshot_metadata(project_id, volume_id, operation):
    return {
        "afterglow_policy_kind": "auto_snapshot",
        "afterglow_project_id": project_id,
        "afterglow_volume_id": volume_id,
        "afterglow_tier": operation["tier"],
        "afterglow_revision": operation["revision"],
        "afterglow_slot": operation["slot"],
    }


def _matches_operation(point, project_id, volume_id, operation):
    if not _owned(point, project_id, volume_id) or point.get("name") != operation["name"]:
        return False
    return _resource() != "snapshot" or all(
        point["metadata"].get(key) == value
        for key, value in _snapshot_metadata(project_id, volume_id, operation).items()
    )


def _source_owned(source, project_id):
    if _resource() == "snapshot":
        return cinder._extension_owned(source, project_id)
    return getattr(source, "project_id", None) == project_id


def _safe_completed(backup: dict) -> bool:
    return (
        backup.get("status") == "available"
        and (_resource() == "snapshot" or backup.get("is_incremental") is False)
        and (_resource() == "snapshot" or backup.get("has_dependent_backups") is False)
        and bool(backup.get("id"))
        and _created_time(backup) is not None
    )


async def _invalidate_backups(project_id):
    await invalidate(f"afterglow:cinder:{project_id}:{_resource()}s*")
    await invalidation.invalidate_mutation_count("cinder", project_id)


async def _prune(conn, redis, lease, project_id, volume_id, config):
    backups = await _sdk(_provider("list"), conn, volume_id=volume_id)
    for tier in ("monthly", "weekly", "daily"):
        count = config[f"max_{tier}"]
        if count == 0:
            continue  # A disabled tier is not consent to delete its recovery points.
        completed = [b for b in backups if _tier(b, project_id, volume_id) == tier and _safe_completed(b)]
        completed.sort(key=_created_time, reverse=True)
        for old in completed[count:]:
            fresh = await _sdk(_provider("get"), conn, old["id"])
            if _tier(fresh, project_id, volume_id) != tier or not _safe_completed(fresh):
                continue
            source = await _sdk(conn.block_storage.get_volume, volume_id)
            if not _source_owned(source, project_id):
                return
            if not await lease.current(project_id, volume_id, config["revision"]):
                return
            deletion_key = None
            if _resource() == "snapshot":
                # A lost DELETE response is not permission to replay a mutation.
                # This non-expiring fence also survives a crash before submission.
                deletion_key = _key("prune", project_id, volume_id) + ":" + old["id"]
                deletion = {
                    "snapshot_id": old["id"],
                    "revision": config["revision"],
                    "status": "unknown",
                }
                if not await redis.set(deletion_key, _dump(deletion), nx=True):
                    continue
                if not await lease.current(project_id, volume_id, config["revision"]):
                    return
            await _sdk(_provider("delete"), conn, old["id"])
            if deletion_key is not None:
                deletion["status"] = "submitted"
                await redis.set(deletion_key, _dump(deletion))
            await _invalidate_backups(project_id)


async def _reconcile(conn, redis, lease, project_id, volume_id, operation):
    try:
        if operation.get(_id_field()):
            backup = await _sdk(_provider("get"), conn, operation[_id_field()])
        else:
            backups = await _sdk(_provider("list"), conn, volume_id=volume_id)
            matches = [b for b in backups if _matches_operation(b, project_id, volume_id, operation)]
            backup = matches[0] if len(matches) == 1 else None
        if not backup or not _matches_operation(backup, project_id, volume_id, operation):
            raise ValueError(f"{_resource().title()} identity is not confirmed")
        operation[_id_field()] = backup["id"]
        status = backup.get("status")
        operation["status"] = (
            "available"
            if status == "available"
            else "error"
            if status == "error"
            else ("creating" if status in ("creating", "restoring") else "unknown")
        )
        operation["error"] = (
            f"Cinder {_resource()} failed."
            if status == "error"
            else (
                f"{_resource().title()} completion is not yet confirmed." if operation["status"] == "unknown" else None
            )
        )
    except Exception:
        operation.update(
            status="unknown",
            error=f"{_resource().title()} acceptance or completion could not be confirmed; it will not be resubmitted.",
        )
    if not await _result(redis, lease, project_id, volume_id, operation):
        return
    if operation["status"] in ("available", "error"):
        await _invalidate_backups(project_id)
    if operation["status"] == "available" and _safe_completed(backup):
        config = await get_auto_backup_config(project_id, volume_id)
        if config and await lease.current(project_id, volume_id, operation["revision"]):
            await _prune(conn, redis, lease, project_id, volume_id, config)
    if operation["status"] in ("available", "error"):
        await _result(redis, lease, project_id, volume_id, operation, done=True)


def _peer_active_key(project_id: str, volume_id: str) -> str:
    if _resource() == "snapshot":
        prefix = _PREFIX
    else:
        from app.services import auto_snapshot

        prefix = auto_snapshot._PREFIX
    return f"{prefix}:active:{project_id}:{volume_id}"


async def _cycle(conn, redis, lease, project_id, volume_id, now):
    active = _text(await redis.get(_key("active", project_id, volume_id)))
    if active:
        await _reconcile(conn, redis, lease, project_id, volume_id, json.loads(active))
        return
    config = await get_auto_backup_config(project_id, volume_id, now=now)
    if not config or not config["enabled"] or _time(config["next_run_at"]) > now:
        return
    peer_active_key = _peer_active_key(project_id, volume_id)
    if await redis.exists(peer_active_key):
        # A claimed peer may already have reached Cinder even when its response
        # was lost. Keep this unsubmitted slot due until that operation resolves.
        return
    raw = _text(await redis.get(_key("config", project_id, volume_id)))
    if not raw or json.loads(raw).get("revision") != config["revision"]:
        return
    volume = await _sdk(conn.block_storage.get_volume, volume_id)
    if _source_owned(volume, project_id) and getattr(volume, "status", None) in ("backing-up", "creating-snapshot"):
        defer = _resource() == "snapshot"
        if not defer:
            from app.services.auto_snapshot import get_auto_snapshot_config

            peer_config = await get_auto_snapshot_config(project_id, volume_id, now=now)
            defer = bool(peer_config and peer_config["enabled"])
        if defer:
            # Preserve standalone backup skip semantics; only new snapshot or
            # paired policies defer an unsubmitted slot on a transient source.
            return
    if not _source_owned(volume, project_id):
        reason = "Source volume ownership could not be confirmed."
    elif getattr(volume, "status", None) not in ("available", "in-use"):
        reason = f"Source volume is not in a safe {_resource()} state."
    elif volume.status == "in-use" and not config["force"]:
        reason = f"Scheduled in-use {_resource()}s require explicit force consent."
    else:
        reason = None
    tier = config["next_tier"]
    due = config["next_run_at"]
    slot = _key("slot", project_id, volume_id) + ":" + due
    operation = {
        "slot": slot,
        "revision": config["revision"],
        "tier": tier,
        "name": _point_name(project_id, volume_id, tier, _time(due)),
        "submitted_at": now.isoformat(),
        _id_field(): None,
        "status": "skipped" if reason else "unknown",
        "error": reason,
    }
    advanced = dict(config)
    advanced["next_run_at"], advanced["next_tier"] = next_event(config, now)
    advanced.update(
        last_run_at=now.isoformat(),
        last_status=operation["status"],
        **{f"last_{_id_field()}": None},
        last_error=reason or f"{_resource().title()} submission is awaiting confirmation.",
    )
    claimed = await redis.eval(
        _CLAIM,
        5,
        _key("config", project_id, volume_id),
        lease.key,
        _key("active", project_id, volume_id),
        slot,
        peer_active_key,
        raw,
        lease.owner,
        _dump(operation),
        _dump(advanced),
    )
    if not claimed:
        return
    if reason:
        await _result(redis, lease, project_id, volume_id, operation, done=True)
        return
    if not await lease.current(project_id, volume_id, config["revision"]):
        operation.update(status="skipped", error=f"Policy changed before {_resource()} submission.")
        await _result(redis, lease, project_id, volume_id, operation, done=True)
        return
    try:
        options = (
            {"metadata": _snapshot_metadata(project_id, volume_id, operation)}
            if _resource() == "snapshot"
            else {"incremental": False}
        )
        backup = await _sdk(
            _provider("create"),
            conn,
            volume_id,
            operation["name"],
            f"Scheduled {'full backup' if _resource() == 'backup' else 'snapshot'} ({tier})",
            force=config["force"],
            **options,
        )
        if not backup.get("id"):
            raise ValueError(f"Cinder did not return a {_resource()} ID")
        operation.update({_id_field(): backup["id"], "status": "creating", "error": None})
    except HttpException as exc:
        if exc.status_code in (400, 401, 403, 404, 405, 409, 413, 422, 429):
            operation.update(status="error", error=f"Cinder rejected the scheduled {_resource()} request.")
        else:
            operation.update(
                status="unknown",
                error=f"{_resource().title()} acceptance could not be confirmed; it will not be resubmitted.",
            )
    except Exception:
        operation.update(
            status="unknown",
            error=f"{_resource().title()} acceptance could not be confirmed; it will not be resubmitted.",
        )
    await _result(redis, lease, project_id, volume_id, operation, done=operation["status"] == "error")
    if operation["status"] in ("creating", "unknown"):
        await _invalidate_backups(project_id)
    # SDK acceptance is not completion; only a subsequent provider read can authorize pruning.


async def run_backup_cycle(conn, project_id: str, volume_id: str, *, now: datetime | None = None) -> None:
    """Consumer hook: one leased cycle using a caller-owned SDK connection and UTC clock."""
    redis = await _get_redis()
    async with _volume_lease(redis, project_id, volume_id) as lease:
        if lease:
            await _cycle(conn, redis, lease, project_id, volume_id, _now(now))


async def scheduler_tick(
    *, now: datetime | None = None, connection_factory=None, dispatcher: WorkDispatcher | None = None
) -> None:
    """One leader-only schedule scan and this worker's assigned execution batch.

    Production retains its participant across ticks. Standalone consumers join
    for this tick only. Every acquired project SDK connection is closed, including
    cancellation while its synchronous factory is still running.
    A supplied participant must belong to this configured recovery-point lane.
    """
    if dispatcher is not None and dispatcher.prefix != _prefix():
        raise ValueError("Work dispatcher namespace does not match the recovery-point lane")
    clock = _now(now)
    context = WorkDispatcher(await _get_redis(), _prefix()) if dispatcher is None else nullcontext(dispatcher)
    async with context as participant:
        await _schedule_tick(participant, clock)
        await _execute_tick(participant, clock, connection_factory)


async def _schedule_tick(dispatcher: WorkDispatcher, clock: datetime) -> None:
    redis = dispatcher.redis
    if await dispatcher.is_leader():
        runnable = []
        for member in await redis.smembers(_all_key()):
            member = _text(member)
            project_id, separator, volume_id = member.partition(":")
            if not separator or not project_id or not volume_id:
                continue
            try:
                config = await get_auto_backup_config(project_id, volume_id, now=clock)
                active = await redis.exists(_key("active", project_id, volume_id))
                if active or (
                    config and config["enabled"] and config["next_run_at"] and _time(config["next_run_at"]) <= clock
                ):
                    runnable.append(member)
            except Exception:
                _logger.warning("Scheduled %s policy scan failed (volume=%s)", _resource(), volume_id, exc_info=True)
        await dispatcher.publish(runnable)


async def _execute_tick(dispatcher: WorkDispatcher, clock: datetime, connection_factory=None) -> None:
    if connection_factory is None:
        from app.services.keystone import get_admin_connection_for_project

        connection_factory = get_admin_connection_for_project
    redis = dispatcher.redis

    # A later leader scan may refill queues during a slow SDK call. Bound this
    # tick to its initial batch so active reconciliation cannot monopolize it.
    for _ in range(await dispatcher.pending()):
        claimed = await dispatcher.claim(_LEASE_SECONDS)
        if claimed is None:
            break
        member, owner = claimed
        project_id, _, volume_id = member.partition(":")
        try:
            async with _volume_lease(redis, project_id, volume_id, owner=owner) as lease:
                if not lease:
                    continue
                config = await get_auto_backup_config(project_id, volume_id, now=clock)
                active = await redis.exists(_key("active", project_id, volume_id))
                if not active and (
                    not config
                    or not config["enabled"]
                    or not config["next_run_at"]
                    or _time(config["next_run_at"]) > clock
                ):
                    continue
                creation = asyncio.create_task(asyncio.to_thread(connection_factory, project_id))
                conn = None
                try:
                    conn = await asyncio.shield(creation)
                    await _cycle(conn, redis, lease, project_id, volume_id, clock)
                except asyncio.CancelledError:
                    if conn is None:
                        # A cancelled shield does not cancel its factory thread.
                        # Drain it before SDK close, lease release and worker leave.
                        with suppress(Exception):
                            conn = await creation
                    raise
                finally:
                    if conn is not None:
                        await _sdk(conn.close)
        except Exception:
            _logger.warning("Scheduled %s cycle failed (volume=%s)", _resource(), volume_id, exc_info=True)


async def _schedule_loop(dispatcher: WorkDispatcher) -> None:
    while True:
        try:
            await _schedule_tick(dispatcher, _now(None))
        except DispatcherUnavailable:
            raise
        except Exception:
            _logger.warning("%s: schedule scan failed", _prefix(), exc_info=True)
        await asyncio.sleep(_POLL_SECONDS)


async def _execution_loop(dispatcher: WorkDispatcher) -> None:
    while True:
        try:
            await _execute_tick(dispatcher, _now(None))
        except DispatcherUnavailable:
            raise
        except Exception:
            _logger.warning("%s: assigned execution failed", _prefix(), exc_info=True)
        await asyncio.sleep(_POLL_SECONDS)


async def scheduler_loop() -> None:
    """Supervise independent scheduling/execution until drained shutdown or rejoin."""
    while True:
        try:
            redis = await _get_redis()
            async with WorkDispatcher(redis, _prefix()) as dispatcher:
                tasks = (
                    asyncio.create_task(_schedule_loop(dispatcher)),
                    asyncio.create_task(_execution_loop(dispatcher)),
                )
                try:
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                finally:
                    # wait() does not propagate cancellation to children. Cancel
                    # each once; a second cancellation could interrupt SDK drain.
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            _logger.warning("%s: dispatcher coordination unavailable", _prefix(), exc_info=True)
        await asyncio.sleep(_POLL_SECONDS)
