"""Policy consumers exercise real Redis scripts and Cinder wrapper state transitions."""

import asyncio
import json
import secrets
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services import auto_backup as ab
from app.services import cinder

PROJECT = "project-a"
VOLUME = "volume-12345678-a"
START = datetime(2026, 5, 31, 12, tzinfo=UTC)


class BackupCloud:
    """Provider boundary state, not a fake scheduler or optimistic completed result."""

    def __init__(self):
        self.volume = SimpleNamespace(id=VOLUME, project_id=PROJECT, status="available")
        self.records = {}
        self.submissions = []
        self.deleted = []
        self.submit_error = None
        self.read_error = None
        self.closed = 0
        self.block_storage = self

    def get_volume(self, volume_id):
        return self.volume

    def backups(self, **kwargs):
        if self.read_error:
            raise self.read_error
        return list(self.records.values())

    def get_backup(self, backup_id):
        if self.read_error:
            raise self.read_error
        return self.records[backup_id]

    def create_backup(self, **kwargs):
        self.submissions.append(kwargs)
        record = self.add("new-backup", kwargs["name"], status="creating", created_at="2026-06-01T03:00:00+00:00")
        if self.submit_error:
            raise self.submit_error
        return record

    def delete_backup(self, backup_id, **kwargs):
        self.deleted.append(backup_id)
        del self.records[backup_id]

    def close(self):
        self.closed += 1

    def add(self, backup_id, name, **fields):
        record = SimpleNamespace(
            id=backup_id,
            name=name,
            status="available",
            volume_id=VOLUME,
            project_id=PROJECT,
            size=10,
            is_incremental=False,
            has_dependent_backups=False,
            description="",
            created_at="2026-05-01T03:00:00+00:00",
        )
        for key, value in fields.items():
            setattr(record, key, value)
        self.records[backup_id] = record
        return record


@pytest.fixture
async def policy_redis(monkeypatch, _fake_redis_global):
    # The global fixture can also opt into a disposable real Redis run.
    from app.services.cache import _get_redis

    redis = await _get_redis()
    monkeypatch.setattr(ab, "_get_redis", _get_redis)
    prefix = f"afterglow:test:scheduled-backup:{secrets.token_hex(12)}"
    monkeypatch.setattr(ab, "_PREFIX", prefix)
    monkeypatch.setattr(ab, "_ALL_KEY", f"{prefix}:all_configs")
    try:
        yield redis
    finally:
        owned_keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
        if owned_keys:
            await redis.delete(*owned_keys)


async def save(**fields):
    return await ab.enable_auto_backup(PROJECT, VOLUME, now=START, **fields)


async def current():
    return await ab.get_auto_backup_config(PROJECT, VOLUME)


def due(config):
    return datetime.fromisoformat(config["next_run_at"])


@pytest.mark.asyncio
async def test_save_starts_future_calendar_collision_then_single_full_submission(policy_redis):
    cloud = BackupCloud()
    config = await save()
    assert due(config) == datetime(2026, 6, 1, 3, tzinfo=UTC)
    assert config["next_tier"] == "monthly"  # Monday and day1 coincide.
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=START)
    assert cloud.submissions == []
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert len(cloud.submissions) == 1
    assert cloud.submissions[0]["is_incremental"] is False
    assert cloud.submissions[0]["force"] is False
    result = await current()
    assert result["last_status"] == "creating"
    assert result["last_backup_id"] == "new-backup"
    assert due(result) > due(config)
    assert cloud.deleted == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tier,counts,expected",
    [
        ("daily", (1, 0, 0), datetime(2026, 6, 1, 3, tzinfo=UTC)),
        ("weekly", (0, 1, 0), datetime(2026, 6, 1, 3, tzinfo=UTC)),
        ("monthly", (0, 0, 1), datetime(2026, 6, 1, 3, tzinfo=UTC)),
    ],
)
async def test_zero_tiers_do_not_create_or_delete_recovery_points(policy_redis, tier, counts, expected):
    cloud = BackupCloud()
    for other in ("daily", "weekly", "monthly"):
        cloud.add(other, f"auto_{VOLUME[:8]}_{other}_20260501")
    config = await save(max_daily=counts[0], max_weekly=counts[1], max_monthly=counts[2])
    assert config["next_tier"] == tier
    assert due(config) == expected
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=expected)
    assert len(cloud.submissions) == 1
    cloud.records["new-backup"].status = "available"
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=expected)
    assert cloud.deleted == [tier]
    assert set(cloud.records) == {"new-backup", *({"daily", "weekly", "monthly"} - {tier})}


@pytest.mark.parametrize(
    "fields",
    [
        {"max_daily": 0, "max_weekly": 0, "max_monthly": 0},
        {"max_daily": -1},
        {"max_weekly": 31},
        {"max_monthly": True},
        {"schedule_time": "24:00"},
        {"schedule_time": "3:00"},
        {"timezone": "Mars/Olympus"},
        {"weekly_day": 7},
        {"monthly_day": 29},
        {"force": "true"},
    ],
)
def test_invalid_policy_is_rejected(fields):
    with pytest.raises(ValidationError):
        ab.PolicySettings(**fields)


@pytest.mark.parametrize(
    "fields,clock,expected,tier",
    [
        (
            {"max_daily": 0, "max_weekly": 0, "max_monthly": 1},
            datetime(2026, 2, 1, 3, tzinfo=UTC),
            datetime(2026, 3, 1, 3, tzinfo=UTC),
            "monthly",
        ),
        (
            {"max_daily": 1, "max_weekly": 0, "max_monthly": 0, "timezone": "America/New_York"},
            datetime(2026, 3, 7, 9, tzinfo=UTC),
            datetime(2026, 3, 8, 7, tzinfo=UTC),
            "daily",
        ),
        (
            {
                "max_daily": 0,
                "max_weekly": 1,
                "max_monthly": 0,
                "weekly_day": 4,
                "timezone": "Asia/Seoul",
                "schedule_time": "14:30",
            },
            datetime(2026, 6, 1, 0, tzinfo=UTC),
            datetime(2026, 6, 5, 5, 30, tzinfo=UTC),
            "weekly",
        ),
    ],
)
def test_calendar_month_week_timezone_and_dst(fields, clock, expected, tier):
    event, actual_tier = ab.next_event(ab.PolicySettings(**fields).model_dump(), clock)
    assert datetime.fromisoformat(event) == expected
    assert actual_tier == tier


@pytest.mark.asyncio
async def test_restart_preserves_due_event_and_paused_all_zero_is_idle(policy_redis):
    config = await save(max_daily=1, max_weekly=0, max_monthly=0)
    restored = await ab.get_auto_backup_config(PROJECT, VOLUME, now=due(config) + timedelta(days=3))
    assert restored["next_run_at"] == config["next_run_at"]
    calls = []
    await ab.enable_auto_backup(PROJECT, VOLUME, enabled=False, max_daily=0, max_weekly=0, max_monthly=0)
    await ab.scheduler_tick(now=due(config) + timedelta(days=10), connection_factory=lambda pid: calls.append(pid))
    assert calls == []
    assert (await current())["next_run_at"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,counts", [(True, (0, 3, 0)), (False, (0, 0, 0))])
async def test_legacy_normalization_preserves_user_data_and_converges(policy_redis, enabled, counts):
    old = {
        "project_id": PROJECT,
        "volume_id": VOLUME,
        "enabled": enabled,
        "max_daily": counts[0],
        "max_weekly": counts[1],
        "max_monthly": counts[2],
        "created_at": "2020-01-01T00:00:00+00:00",
        "operator_note": "keep me",
    }
    key = ab._key("config", PROJECT, VOLUME)
    await policy_redis.set(key, json.dumps(old))
    migrated = await ab.get_auto_backup_config(PROJECT, VOLUME, now=START)
    assert migrated["enabled"] is enabled
    assert tuple(migrated[f"max_{tier}"] for tier in ("daily", "weekly", "monthly")) == counts
    assert migrated["operator_note"] == "keep me"
    assert migrated["created_at"] == old["created_at"]
    assert migrated["schema_version"] == 2
    assert await ab.get_auto_backup_config(PROJECT, VOLUME, now=START + timedelta(days=10)) == migrated


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw", ["broken-json", '["not-policy"]', json.dumps({"project_id": PROJECT, "volume_id": VOLUME, "max_daily": -1})]
)
async def test_malformed_policy_fails_closed_without_erasing_saved_bytes(policy_redis, raw):
    key = ab._key("config", PROJECT, VOLUME)
    await policy_redis.set(key, raw)
    await policy_redis.sadd(ab._ALL_KEY, f"{PROJECT}:{VOLUME}")
    calls = []
    config = await current()
    assert config["enabled"] is False
    assert config["last_status"] == "error"
    await ab.scheduler_tick(now=START, connection_factory=lambda pid: calls.append(pid))
    assert calls == []
    assert await policy_redis.get(key) == raw


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "owner,status,force,submitted",
    [
        (PROJECT, "available", False, True),
        (PROJECT, "in-use", True, True),
        (PROJECT, "in-use", False, False),
        (PROJECT, "backing-up", True, False),
        (PROJECT, "error", True, False),
        ("other-project", "available", True, False),
        (None, "available", True, False),
    ],
)
async def test_fresh_source_ownership_status_and_force_consent(policy_redis, owner, status, force, submitted):
    cloud = BackupCloud()
    cloud.volume.project_id, cloud.volume.status = owner, status
    config = await save(force=force)
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert bool(cloud.submissions) is submitted
    assert (await current())["last_status"] == ("creating" if submitted else "skipped")
    assert cloud.deleted == []


@pytest.mark.asyncio
async def test_completion_prunes_only_verified_owned_managed_full_backups(policy_redis):
    cloud = BackupCloud()
    config = await save(max_daily=1, max_weekly=0, max_monthly=0)
    managed = f"auto_{VOLUME[:8]}_daily_20260501"
    cloud.add("old-full", managed)
    cloud.add("manual", "manual")
    for backup_id, fields in (
        ("foreign", {"project_id": "other"}),
        ("other-source", {"volume_id": "other"}),
        ("pending", {"status": "creating"}),
        ("failed", {"status": "error"}),
        ("incremental", {"is_incremental": True}),
        ("dependent", {"has_dependent_backups": True}),
        ("unknown-dependencies", {"has_dependent_backups": None}),
        ("unknown-full", {"is_incremental": None}),
        ("unknown-owner", {"project_id": None}),
    ):
        cloud.add(backup_id, managed, **fields)
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert cloud.deleted == []
    cloud.records["new-backup"].status = "available"
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert cloud.deleted == ["old-full"]
    assert (await current())["last_status"] == "available"
    assert not await policy_redis.exists(ab._key("active", PROJECT, VOLUME))


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["error", "deleting", "creating"])
async def test_failed_pending_unknown_are_not_retention_replacements(policy_redis, status):
    cloud = BackupCloud()
    config = await save(max_daily=1, max_weekly=0, max_monthly=0)
    cloud.add("old", f"auto_{VOLUME[:8]}_daily_20260501")
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    cloud.records["new-backup"].status = status
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert cloud.deleted == []
    assert (await current())["last_status"] == {"error": "error", "deleting": "unknown", "creating": "creating"}[status]


@pytest.mark.asyncio
async def test_pause_after_acceptance_observes_completion_without_more_submits_or_prune(policy_redis):
    cloud = BackupCloud()
    config = await save(max_daily=1, max_weekly=0, max_monthly=0)
    cloud.add("old", f"auto_{VOLUME[:8]}_daily_20260501")
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    paused = await ab.enable_auto_backup(PROJECT, VOLUME, enabled=False, force=False, now=due(config))
    assert paused["last_backup_id"] == "new-backup"
    cloud.records["new-backup"].status = "available"
    await ab.scheduler_tick(now=due(config) + timedelta(days=40), connection_factory=lambda pid: cloud)
    await ab.scheduler_tick(now=due(config) + timedelta(days=41), connection_factory=lambda pid: cloud)
    assert len(cloud.submissions) == 1
    assert cloud.closed == 1
    assert cloud.deleted == []
    result = await current()
    assert result["enabled"] is False and result["last_status"] == "available"


@pytest.mark.asyncio
async def test_removed_policy_reconciles_accepted_operation_without_recreation(policy_redis):
    cloud = BackupCloud()
    config = await save()
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    await ab.disable_auto_backup(PROJECT, VOLUME)
    cloud.records["new-backup"].status = "available"
    await ab.scheduler_tick(now=due(config), connection_factory=lambda pid: cloud)
    assert await current() is None
    assert cloud.records["new-backup"].status == "available"
    assert cloud.deleted == []
    assert not await policy_redis.sismember(ab._ALL_KEY, f"{PROJECT}:{VOLUME}")


@pytest.mark.asyncio
@pytest.mark.parametrize("visible", [True, False])
async def test_ambiguous_submit_is_reconciled_or_unknown_but_never_reissued(policy_redis, visible):
    cloud = BackupCloud()
    cloud.submit_error = TimeoutError("secret upstream credential must not appear")
    config = await save()
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    if not visible:
        cloud.records.clear()
    for days in (0, 1, 30):
        await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config) + timedelta(days=days))
    result = await current()
    assert len(cloud.submissions) == 1
    assert result["last_status"] == ("creating" if visible else "unknown")
    assert "secret" not in (result["last_error"] or "")
    assert cloud.deleted == []


@pytest.mark.asyncio
async def test_reconciliation_outage_keeps_unknown_and_closes_dispatcher_connection(policy_redis):
    cloud = BackupCloud()
    config = await save()
    await ab.scheduler_tick(now=due(config), connection_factory=lambda pid: cloud)
    cloud.read_error = RuntimeError("private provider message")
    await ab.scheduler_tick(now=due(config) + timedelta(days=2), connection_factory=lambda pid: cloud)
    assert cloud.closed == 2
    assert len(cloud.submissions) == 1
    assert (await current())["last_status"] == "unknown"


@pytest.mark.asyncio
async def test_two_replicas_share_durable_claim_before_provider_acceptance(policy_redis, monkeypatch):
    cloud = BackupCloud()
    config = await save()
    entered, release = asyncio.Event(), asyncio.Event()
    original = ab._sdk

    async def delayed(fn, *args, **kwargs):
        if fn is cinder.create_backup:
            entered.set()
            await release.wait()
        return await original(fn, *args, **kwargs)

    monkeypatch.setattr(ab, "_sdk", delayed)
    first = asyncio.create_task(ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config)))
    await entered.wait()
    assert await policy_redis.exists(ab._key("active", PROJECT, VOLUME))
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    release.set()
    await first
    assert len(cloud.submissions) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["pause", "edit", "lease"])
async def test_pause_edit_or_lease_loss_before_mutation_fences_submission(policy_redis, monkeypatch, change):
    cloud = BackupCloud()
    config = await save()
    original = ab.VolumeLease.current

    async def intervene(lease, project_id, volume_id, revision):
        if change == "lease":
            await policy_redis.set(lease.key, "another-replica")
        else:
            await ab.enable_auto_backup(
                PROJECT, VOLUME, enabled=change != "pause", now=due(config), schedule_time="04:00"
            )
        return await original(lease, project_id, volume_id, revision)

    monkeypatch.setattr(ab.VolumeLease, "current", intervene)
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert cloud.submissions == []
    assert cloud.deleted == []


@pytest.mark.asyncio
async def test_lease_loss_after_provider_acceptance_is_not_a_retry_authority(policy_redis, monkeypatch):
    cloud = BackupCloud()
    config = await save()
    original = ab._sdk

    async def lost_after_submit(fn, *args, **kwargs):
        result = await original(fn, *args, **kwargs)
        if fn is cinder.create_backup:
            await policy_redis.delete(ab._key("lease", PROJECT, VOLUME))
        return result

    monkeypatch.setattr(ab, "_sdk", lost_after_submit)
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    monkeypatch.setattr(ab, "_sdk", original)
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config) + timedelta(days=1))
    assert len(cloud.submissions) == 1
    assert (await current())["last_backup_id"] == "new-backup"


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [{"has_dependent_backups": True}, {"project_id": "other"}, {"status": "creating"}])
async def test_retention_rereads_deletion_candidate_and_keeps_changed_backup(policy_redis, monkeypatch, changed):
    cloud = BackupCloud()
    config = await save(max_daily=1, max_weekly=0, max_monthly=0)
    cloud.add("old", f"auto_{VOLUME[:8]}_daily_20260501")
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    cloud.records["new-backup"].status = "available"
    original = cloud.get_backup

    def reread(backup_id):
        record = original(backup_id)
        if backup_id == "old":
            for field, value in changed.items():
                setattr(record, field, value)
        return record

    monkeypatch.setattr(cloud, "get_backup", reread)
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert cloud.deleted == []


def test_backup_projection_preserves_unknown_ownership_and_dependency():
    backup = BackupCloud().add("b", "manual", project_id=None, has_dependent_backups=None, is_incremental=None)
    projected = cinder._backup_to_dict(backup)
    assert projected["project_id"] is None
    assert projected["has_dependent_backups"] is None
    assert projected["is_incremental"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["pause", "edit", "owner", "lease"])
async def test_retention_fences_latest_policy_source_and_lease(policy_redis, monkeypatch, change):
    cloud = BackupCloud()
    config = await save(max_daily=1, max_weekly=0, max_monthly=0)
    cloud.add("old", f"auto_{VOLUME[:8]}_daily_20260501")
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    cloud.records["new-backup"].status = "available"
    original = ab._sdk

    async def changed_before_delete(fn, *args, **kwargs):
        result = await original(fn, *args, **kwargs)
        if fn is cinder.get_backup and args[1] == "old":
            if change == "owner":
                cloud.volume.project_id = "other-project"
            elif change == "lease":
                await policy_redis.set(ab._key("lease", PROJECT, VOLUME), "other-replica")
            else:
                await ab.enable_auto_backup(
                    PROJECT, VOLUME, enabled=change != "pause", now=due(config), schedule_time="05:00"
                )
        return result

    monkeypatch.setattr(ab, "_sdk", changed_before_delete)
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert cloud.deleted == []
    assert "old" in cloud.records


@pytest.mark.asyncio
async def test_long_submission_renews_lease_and_blocks_second_replica(policy_redis, monkeypatch):
    cloud = BackupCloud()
    config = await save()
    monkeypatch.setattr(ab, "_LEASE_SECONDS", 1)
    entered, release = asyncio.Event(), asyncio.Event()
    original = ab._sdk

    async def long_submit(fn, *args, **kwargs):
        if fn is cinder.create_backup:
            entered.set()
            await release.wait()
        return await original(fn, *args, **kwargs)

    monkeypatch.setattr(ab, "_sdk", long_submit)
    first = asyncio.create_task(ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config)))
    try:
        await entered.wait()
        # Cross the real one-second TTL while the installed Redis Lua renewals run.
        await asyncio.sleep(1.2)
        assert await policy_redis.exists(ab._key("lease", PROJECT, VOLUME))
        await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    finally:
        release.set()
        await first
    assert len(cloud.submissions) == 1


@pytest.mark.asyncio
async def test_expired_claim_survives_worker_restart_without_submit_replay(policy_redis):
    cloud = BackupCloud()
    config = await save()
    when = due(config)
    operation = {
        "slot": ab._key("slot", PROJECT, VOLUME) + ":" + config["next_run_at"],
        "revision": config["revision"],
        "tier": config["next_tier"],
        "name": "provider-submission-may-have-happened",
        "submitted_at": when.isoformat(),
        "backup_id": None,
        "status": "unknown",
        "error": None,
    }
    # Simulate a process dying after durable claim and before any known SDK response.
    await policy_redis.set(operation["slot"], json.dumps(operation))
    await policy_redis.set(ab._key("active", PROJECT, VOLUME), json.dumps(operation))
    await ab.scheduler_tick(now=when + timedelta(days=10), connection_factory=lambda pid: cloud)
    assert cloud.submissions == []
    assert (await current())["last_status"] == "unknown"
    assert await policy_redis.exists(operation["slot"])


@pytest.mark.asyncio
@pytest.mark.parametrize("broken", [{"schema_version": 99}, {"next_run_at": None}, {"max_monthly": 0}])
async def test_invalid_persisted_calendar_fields_fail_closed(policy_redis, broken):
    config = await save()
    config.update(broken)
    raw = json.dumps(config)
    await policy_redis.set(ab._key("config", PROJECT, VOLUME), raw)
    result = await current()
    assert result["enabled"] is False
    assert result["last_status"] == "error"
    assert await policy_redis.get(ab._key("config", PROJECT, VOLUME)) == raw


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "http_status,expected", [(400, "error"), (403, "error"), (409, "error"), (500, "unknown"), (408, "unknown")]
)
async def test_sdk_rejection_or_uncertain_failure_never_prunes_without_replacement(
    policy_redis, monkeypatch, http_status, expected
):
    from openstack.exceptions import HttpException

    cloud = BackupCloud()
    config = await save(max_daily=1, max_weekly=0, max_monthly=0)
    cloud.add("old-one", f"auto_{VOLUME[:8]}_daily_20260501")
    cloud.add("old-two", f"auto_{VOLUME[:8]}_daily_20260502")

    def rejected(**kwargs):
        cloud.submissions.append(kwargs)
        raise HttpException(message="private quota/provider detail", http_status=http_status)

    monkeypatch.setattr(cloud, "create_backup", rejected)
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert len(cloud.submissions) == 1
    assert cloud.deleted == []
    assert (await current())["last_status"] == expected
    assert "private" not in (await current())["last_error"]
    assert bool(await policy_redis.exists(ab._key("active", PROJECT, VOLUME))) is (expected == "unknown")


@pytest.mark.asyncio
async def test_dispatcher_cancel_during_blocked_factory_closes_returned_connection(policy_redis):
    cloud = BackupCloud()
    config = await save()
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def blocked_factory(project_id):
        loop.call_soon_threadsafe(entered.set)
        if not release.wait(timeout=5):
            raise TimeoutError("test factory release was not signalled")
        return cloud

    task = asyncio.create_task(ab.scheduler_tick(now=due(config), connection_factory=blocked_factory))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert cloud.closed == 1
    assert cloud.submissions == []
    assert not await policy_redis.exists(ab._key("lease", PROJECT, VOLUME))
    assert (await current())["last_status"] == "never"
