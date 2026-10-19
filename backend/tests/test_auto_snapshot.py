"""Snapshot lane exercises the shared Redis fences, never a fake scheduler."""

import asyncio
import json
from datetime import timedelta

import pytest

from app.services import auto_backup as ab
from app.services import auto_snapshot as snapshots
from tests.test_auto_backup import PROJECT, START, VOLUME, BackupCloud, due
from tests.test_auto_backup import policy_redis as policy_redis


class SnapshotCloud(BackupCloud):
    def __init__(self):
        super().__init__()
        self.snapshot_records = {}
        self.snapshot_posts = []
        self.snapshot_deleted = []
        self.snapshot_error = None
        self._afterglow_project_id = PROJECT

    def snapshots(self, **kwargs):
        if self.read_error:
            raise self.read_error
        return list(self.snapshot_records.values())

    def get_snapshot(self, snapshot_id):
        if self.read_error:
            raise self.read_error
        return self.snapshot_records[snapshot_id]

    def create_snapshot(self, **kwargs):
        self.snapshot_posts.append(kwargs)
        point = self.add_snapshot(
            "new-snapshot",
            kwargs["name"],
            kwargs["metadata"],
            status="creating",
            created_at="2026-06-01T03:00:00+00:00",
        )
        if self.snapshot_error:
            raise self.snapshot_error
        return point

    def delete_snapshot(self, snapshot_id, **kwargs):
        self.snapshot_deleted.append(snapshot_id)
        del self.snapshot_records[snapshot_id]

    def add_snapshot(self, snapshot_id, name, metadata=None, **fields):
        point = self.add(snapshot_id, name, **fields)
        del self.records[snapshot_id]
        point.metadata = metadata or {}
        self.snapshot_records[snapshot_id] = point
        return point


@pytest.fixture
async def snapshot_redis(policy_redis, monkeypatch):
    prefix = ab._PREFIX + ":snapshots"
    monkeypatch.setattr(snapshots, "_PREFIX", prefix)
    monkeypatch.setattr(snapshots, "_ALL_KEY", prefix + ":all_configs")
    return policy_redis


async def save(**settings):
    return await snapshots.enable_auto_snapshot(PROJECT, VOLUME, now=START, **settings)


async def current():
    return await snapshots.get_auto_snapshot_config(PROJECT, VOLUME)


def metadata(config, *, day=1):
    event = due(config) - timedelta(days=day)
    return {
        "afterglow_policy_kind": "auto_snapshot",
        "afterglow_project_id": PROJECT,
        "afterglow_volume_id": VOLUME,
        "afterglow_tier": config["next_tier"],
        "afterglow_revision": config["revision"],
        "afterglow_slot": snapshots._key("slot", PROJECT, VOLUME) + ":" + event.isoformat(),
    }


def automatic(cloud, config, snapshot_id="old", *, day=1, **fields):
    event = due(config) - timedelta(days=day)
    name = f"afterglow_auto_snapshot_{PROJECT}_{VOLUME}_{config['next_tier']}_{event.strftime('%Y%m%dT%H%M%SZ')}"
    return cloud.add_snapshot(snapshot_id, name, metadata(config, day=day), **fields)


@pytest.mark.asyncio
async def test_snapshot_waits_for_provider_completion_and_prunes_only_owned_points(snapshot_redis):
    cloud = SnapshotCloud()
    config = await save(max_daily=1, max_weekly=0, max_monthly=0)
    automatic(cloud, config)
    owned_lookalike = automatic(cloud, config, "manual-lookalike")
    owned_lookalike.metadata = {}
    cloud.add_snapshot("manual", "manual")
    foreign = automatic(cloud, config, "foreign")
    foreign.project_id = "other-project"
    wrong_source = automatic(cloud, config, "wrong-source")
    wrong_source.volume_id = "other-volume"
    wrong_kind = automatic(cloud, config, "backup-marked")
    wrong_kind.metadata["afterglow_policy_kind"] = "auto_backup"
    automatic(cloud, config, "busy", status="creating")
    automatic(cloud, config, "undated", created_at=None)
    cloud.add("backup", f"auto_{VOLUME[:8]}_daily_20260501")
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert len(cloud.snapshot_posts) == 1
    assert cloud.snapshot_posts[0]["is_forced"] is False
    assert "incremental" not in cloud.snapshot_posts[0]
    assert cloud.snapshot_deleted == []
    assert (await current())["last_snapshot_id"] == "new-snapshot"
    assert "last_backup_id" not in await current()
    cloud.snapshot_records["new-snapshot"].status = "available"
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert cloud.snapshot_deleted == ["old"]
    assert set(cloud.records) == {"backup"}
    assert cloud.deleted == []
    assert (await current())["last_status"] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["foreign", "missing-owner", "busy", "in-use"])
async def test_snapshot_preflight_skips_unsafe_source_without_submission(snapshot_redis, change):
    cloud = SnapshotCloud()
    if change == "foreign":
        cloud.volume.project_id = "other-project"
    elif change == "missing-owner":
        cloud.volume.project_id = None
    else:
        cloud.volume.status = "in-use" if change == "in-use" else "creating"
    config = await save()
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert cloud.snapshot_posts == []
    assert (await current())["last_status"] == "skipped"


@pytest.mark.asyncio
async def test_snapshot_force_consent_and_backup_lane_remain_independent(snapshot_redis, monkeypatch):
    cloud = SnapshotCloud()
    cloud.volume.status = "in-use"
    backup = await ab.enable_auto_backup(PROJECT, VOLUME, now=START, force=True)
    snapshot = await save(force=True)
    # Both workers pass the peer precheck before either claims its due slot.
    # Only the Redis claim can prevent their two native submissions racing.
    original_sdk = ab._sdk
    ready = asyncio.Event()
    reads = 0

    async def simultaneous_source_read(fn, *args, **kwargs):
        nonlocal reads
        if fn == cloud.get_volume:
            reads += 1
            if reads == 2:
                ready.set()
            await ready.wait()
        return await original_sdk(fn, *args, **kwargs)

    monkeypatch.setattr(ab, "_sdk", simultaneous_source_read)
    await asyncio.gather(
        snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(snapshot)),
        ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(backup)),
    )
    assert len(cloud.snapshot_posts) + len(cloud.submissions) == 1
    if not cloud.snapshot_posts:
        assert await current() == snapshot
    else:
        assert await ab.get_auto_backup_config(PROJECT, VOLUME) == backup
    monkeypatch.setattr(ab, "_sdk", original_sdk)
    # A completion read releases the shared-volume submission boundary; the
    # unsubmitted peer retains the original due slot and is subsequently sent.
    for _ in range(4):
        for point in (*cloud.records.values(), *cloud.snapshot_records.values()):
            point.status = "available"
        await asyncio.gather(
            snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(snapshot)),
            ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(backup)),
        )
    assert len(cloud.snapshot_posts) == len(cloud.submissions) == 1
    assert cloud.snapshot_posts[0]["is_forced"] is True
    assert cloud.submissions[0]["force"] is True
    assert (await ab.get_auto_backup_config(PROJECT, VOLUME))["last_backup_id"] == "new-backup"
    assert (await current())["last_snapshot_id"] == "new-snapshot"
    for kind in ("config", "active", "lease"):
        assert ab._key(kind, PROJECT, VOLUME) != snapshots._key(kind, PROJECT, VOLUME)
    await snapshots.disable_auto_snapshot(PROJECT, VOLUME)
    assert await current() is None
    assert await ab.get_auto_backup_config(PROJECT, VOLUME) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted", [False, True])
async def test_uncertain_snapshot_is_never_replayed_and_requires_exact_metadata(snapshot_redis, accepted):
    cloud = SnapshotCloud()
    cloud.snapshot_error = TimeoutError("lost response")
    config = await save()
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert (await current())["last_status"] == "unknown"
    if not accepted:
        cloud.snapshot_records.clear()
    else:
        cloud.snapshot_records["new-snapshot"].metadata["afterglow_revision"] = "not-the-operation"
    for offset in (1, 10):
        await snapshots.scheduler_tick(
            now=due(config) + timedelta(days=offset),
            connection_factory=lambda pid: cloud,
        )
    assert len(cloud.snapshot_posts) == 1
    assert (await current())["last_status"] == "unknown"
    if accepted:
        cloud.snapshot_records["new-snapshot"].metadata["afterglow_revision"] = config["revision"]
        cloud.snapshot_records["new-snapshot"].status = "available"
        await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
        assert (await current())["last_status"] == "available"
    assert cloud.snapshot_deleted == []


@pytest.mark.asyncio
async def test_snapshot_disable_preserves_journal_and_prevents_retention(snapshot_redis):
    cloud = SnapshotCloud()
    config = await save(max_daily=1, max_weekly=0, max_monthly=0)
    automatic(cloud, config)
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    active_key = snapshots._key("active", PROJECT, VOLUME)
    operation = json.loads(await snapshot_redis.get(active_key))
    await snapshots.disable_auto_snapshot(PROJECT, VOLUME)
    assert await snapshot_redis.exists(active_key)
    cloud.snapshot_records["new-snapshot"].status = "available"
    await snapshots.scheduler_tick(now=due(config), connection_factory=lambda pid: cloud)
    assert await current() is None
    assert not await snapshot_redis.exists(active_key)
    assert json.loads(await snapshot_redis.get(operation["slot"]))["status"] == "available"
    assert cloud.snapshot_deleted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["policy", "ownership", "metadata"])
async def test_snapshot_retention_revalidates_before_delete(snapshot_redis, monkeypatch, change):
    cloud = SnapshotCloud()
    config = await save(max_daily=1, max_weekly=0, max_monthly=0)
    old = automatic(cloud, config)
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    cloud.snapshot_records["new-snapshot"].status = "available"
    original = cloud.get_snapshot

    def reread(snapshot_id):
        point = original(snapshot_id)
        if snapshot_id == "old":
            if change == "metadata":
                old.metadata = {}
            elif change == "ownership":
                cloud.volume.project_id = "other-project"
        return point

    monkeypatch.setattr(cloud, "get_snapshot", reread)
    if change == "policy":
        await snapshots.enable_auto_snapshot(PROJECT, VOLUME, enabled=False, now=START)
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert cloud.snapshot_deleted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["pause", "edit", "lease"])
async def test_snapshot_submission_honors_revision_and_lease_fence(snapshot_redis, monkeypatch, change):
    cloud = SnapshotCloud()
    config = await save()
    original = ab.VolumeLease.current

    async def intervene(lease, project_id, volume_id, revision):
        if change == "lease":
            await snapshot_redis.set(lease.key, "another-worker")
        else:
            await snapshots.enable_auto_snapshot(
                PROJECT,
                VOLUME,
                enabled=change != "pause",
                now=START,
                schedule_time="04:00",
            )
        return await original(lease, project_id, volume_id, revision)

    monkeypatch.setattr(ab.VolumeLease, "current", intervene)
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert cloud.snapshot_posts == []
    assert cloud.snapshot_deleted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("http_status,expected", [(403, "error"), (409, "error"), (500, "unknown")])
async def test_snapshot_rejection_and_uncertainty_never_authorize_prune(
    snapshot_redis, monkeypatch, http_status, expected
):
    from openstack.exceptions import HttpException

    cloud = SnapshotCloud()
    config = await save(max_daily=1, max_weekly=0, max_monthly=0)
    automatic(cloud, config, "old-one")
    automatic(cloud, config, "old-two", day=2)

    def reject(**kwargs):
        cloud.snapshot_posts.append(kwargs)
        raise HttpException(message="private provider detail", http_status=http_status)

    monkeypatch.setattr(cloud, "create_snapshot", reject)
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert len(cloud.snapshot_posts) == 1
    assert cloud.snapshot_deleted == []
    result = await current()
    assert result["last_status"] == expected
    assert "private" not in result["last_error"]


@pytest.mark.asyncio
async def test_snapshot_restart_never_replays_a_claim_without_known_provider_result(snapshot_redis):
    cloud = SnapshotCloud()
    config = await save()
    operation = {
        "slot": snapshots._key("slot", PROJECT, VOLUME) + ":" + config["next_run_at"],
        "revision": config["revision"],
        "tier": config["next_tier"],
        "name": "submission-may-have-happened",
        "submitted_at": due(config).isoformat(),
        "snapshot_id": None,
        "status": "unknown",
        "error": None,
    }
    await snapshot_redis.set(operation["slot"], json.dumps(operation))
    await snapshot_redis.set(snapshots._key("active", PROJECT, VOLUME), json.dumps(operation))
    await snapshots.scheduler_tick(now=due(config) + timedelta(days=10), connection_factory=lambda pid: cloud)
    assert cloud.snapshot_posts == []
    assert (await current())["last_status"] == "unknown"
    assert await snapshot_redis.exists(operation["slot"])


@pytest.mark.asyncio
async def test_disabled_snapshot_tier_never_authorizes_deletion(snapshot_redis):
    cloud = SnapshotCloud()
    config = await save(max_daily=1, max_weekly=0, max_monthly=0)
    other = dict(config, next_tier="weekly")
    automatic(cloud, other, "weekly-one")
    automatic(cloud, other, "weekly-two", day=2)
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    cloud.snapshot_records["new-snapshot"].status = "available"
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert cloud.snapshot_deleted == []
    assert {"weekly-one", "weekly-two"}.issubset(cloud.snapshot_records)


@pytest.mark.asyncio
async def test_uncertain_snapshot_delete_is_durably_fenced_not_replayed(snapshot_redis, monkeypatch):
    cloud = SnapshotCloud()
    config = await save(max_daily=1, max_weekly=0, max_monthly=0)
    automatic(cloud, config)
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    cloud.snapshot_records["new-snapshot"].status = "available"
    attempts = []

    def uncertain_delete(snapshot_id, **kwargs):
        attempts.append(snapshot_id)
        raise TimeoutError("provider may have accepted DELETE")

    monkeypatch.setattr(cloud, "delete_snapshot", uncertain_delete)
    with pytest.raises(TimeoutError):
        await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    deletion_key = snapshots._key("prune", PROJECT, VOLUME) + ":old"
    assert json.loads(await snapshot_redis.get(deletion_key))["status"] == "unknown"
    await snapshots.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert attempts == ["old"]
    assert (await current())["last_status"] == "available"
    assert cloud.deleted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["backup", "snapshot"])
@pytest.mark.parametrize("status", ["backing-up", "creating-snapshot"])
async def test_paired_busy_source_keeps_unsubmitted_slot_due(snapshot_redis, kind, status):
    cloud = SnapshotCloud()
    enable = ab.enable_auto_backup if kind == "backup" else snapshots.enable_auto_snapshot
    get_config = ab.get_auto_backup_config if kind == "backup" else snapshots.get_auto_snapshot_config
    cycle = ab.run_backup_cycle if kind == "backup" else snapshots.run_snapshot_cycle
    config = await enable(PROJECT, VOLUME, now=START, force=True)
    if kind == "backup":
        await snapshots.enable_auto_snapshot(PROJECT, VOLUME, now=START, force=True)
    cloud.volume.status = status
    await cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert await get_config(PROJECT, VOLUME) == config
    assert cloud.submissions == cloud.snapshot_posts == []
    cloud.volume.status = "in-use"
    await cycle(cloud, PROJECT, VOLUME, now=due(config))
    await cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert len(cloud.submissions) + len(cloud.snapshot_posts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("first_kind", ["backup", "snapshot"])
async def test_uncertain_peer_is_not_replayed_and_other_slot_survives_until_completion(snapshot_redis, first_kind):
    cloud = SnapshotCloud()
    backup = await ab.enable_auto_backup(PROJECT, VOLUME, now=START, force=True)
    snapshot = await save(force=True)
    first_cycle = ab.run_backup_cycle if first_kind == "backup" else snapshots.run_snapshot_cycle
    peer_cycle = snapshots.run_snapshot_cycle if first_kind == "backup" else ab.run_backup_cycle
    peer_get = snapshots.get_auto_snapshot_config if first_kind == "backup" else ab.get_auto_backup_config
    peer_original = snapshot if first_kind == "backup" else backup
    if first_kind == "backup":
        cloud.submit_error = TimeoutError("accepted response lost")
    else:
        cloud.snapshot_error = TimeoutError("accepted response lost")
    await first_cycle(cloud, PROJECT, VOLUME, now=due(backup))
    for _ in range(3):
        await peer_cycle(cloud, PROJECT, VOLUME, now=due(backup))
        await first_cycle(cloud, PROJECT, VOLUME, now=due(backup))
    assert len(cloud.submissions) + len(cloud.snapshot_posts) == 1
    assert await peer_get(PROJECT, VOLUME) == peer_original
    for point in (*cloud.records.values(), *cloud.snapshot_records.values()):
        point.status = "available"
    await first_cycle(cloud, PROJECT, VOLUME, now=due(backup))
    await peer_cycle(cloud, PROJECT, VOLUME, now=due(backup))
    await peer_cycle(cloud, PROJECT, VOLUME, now=due(backup))
    assert len(cloud.submissions) == len(cloud.snapshot_posts) == 1
