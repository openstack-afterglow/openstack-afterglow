"""Trove cron consumers exercise Redis ownership and real service boundaries."""

import asyncio
import json
import secrets
import threading
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta

import pytest
from apscheduler.triggers.cron import CronTrigger

from app.services import db_auto_backup as dab
from app.services import work_dispatcher as wd
from app.services.work_dispatcher import DispatcherUnavailable, WorkDispatcher

PROJECT = "project-a"
INSTANCE = "instance-12345678-a"
SLOT = datetime(2026, 10, 14, 3, tzinfo=UTC)
TRIGGER = CronTrigger.from_crontab("0 3 * * *", timezone=UTC)


class Response:
    def __init__(self, body, status=200):
        self.body = body
        self.status_code = status
        self.text = json.dumps(body)

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class TroveCloud:
    def __init__(self):
        self.records = {}
        self.posts = []
        self.deletes = []
        self.connections = []
        self.read_error = None
        self.reply_loss = False
        self.read_gate = None
        self.post_gate = None
        self.delete_gate = None
        self.lock = threading.Lock()

    def connection(self, project):
        assert project == PROJECT
        cloud = self

        class Connection:
            database = cloud
            closed = False

            def close(self):
                self.closed = True

        conn = Connection()
        self.connections.append(conn)
        return conn

    def get(self, url):
        if self.read_gate:
            entered, release = self.read_gate
            entered.set()
            assert release.wait(5)
        if self.read_error:
            raise self.read_error
        return Response({"backups": list(self.records.values())})

    def post(self, url, *, json, **kwargs):
        assert url == "/backups"
        if self.post_gate:
            entered, release = self.post_gate
            entered.set()
            assert release.wait(5)
        with self.lock:
            self.posts.append(json["backup"])
            backup_id = f"backup-{len(self.posts)}"
            record = {
                **json["backup"],
                "id": backup_id,
                "instance_id": json["backup"]["instance"],
                "created": SLOT.isoformat(),
                "status": "COMPLETED",
            }
            self.records[backup_id] = record
        if self.reply_loss:
            raise ConnectionError("provider committed but response was lost")
        return Response({"backup": record}, 202)

    def delete(self, url):
        backup_id = url.rsplit("/", 1)[-1]
        self.deletes.append(backup_id)
        if self.delete_gate:
            entered, release = self.delete_gate
            entered.set()
            assert release.wait(5)
        del self.records[backup_id]
        return Response({}, 204)

    def add(self, backup_id, instance=INSTANCE, *, days=0, tier="daily", name=None, status="COMPLETED"):
        self.records[backup_id] = {
            "id": backup_id,
            "name": name or dab._make_backup_name(instance, tier, now=SLOT - timedelta(days=days)),
            "instance_id": instance,
            "created": (SLOT - timedelta(days=days)).isoformat(),
            "status": status,
        }


@pytest.fixture
async def db_redis(monkeypatch, _fake_redis_global):
    from app.services.cache import _get_redis

    redis = await _get_redis()
    prefix = f"afterglow:test:trove:{secrets.token_hex(12)}"
    monkeypatch.setattr(dab, "_get_redis", _get_redis)
    monkeypatch.setattr(dab, "_PREFIX", prefix)
    monkeypatch.setattr(dab, "_ALL_KEY", f"{prefix}:all_configs")
    try:
        yield redis
    finally:
        keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
        if keys:
            await redis.delete(*keys)


async def enable(instance=INSTANCE, daily=1, weekly=0, monthly=0):
    await dab.enable_db_auto_backup(PROJECT, instance, daily, weekly, monthly)


async def scan(workers, clock=SLOT):
    await asyncio.gather(*(dab._schedule_tick(worker, TRIGGER, clock) for worker in workers))


async def execute(workers, cloud):
    await asyncio.gather(*(dab._execute_tick(worker, cloud.connection) for worker in workers))


async def join(stack, redis):
    return [
        await stack.enter_async_context(WorkDispatcher(redis, dab._PREFIX, worker_id=f"replica-{i}")) for i in range(3)
    ]


async def entered(event):
    assert await asyncio.to_thread(event.wait, 3), "provider boundary was not reached"


@pytest.mark.asyncio
async def test_three_workers_divide_targets_and_only_leader_scans(db_redis, monkeypatch):
    cloud = TroveCloud()
    for index in range(9):
        await enable(f"instance-{index:08}")
    scans = []
    original = dab.list_all_db_auto_backup_configs

    async def counted():
        scans.append(True)
        return await original()

    monkeypatch.setattr(dab, "list_all_db_auto_backup_configs", counted)
    async with AsyncExitStack() as stack:
        workers = await join(stack, db_redis)
        await scan(workers)
        assert len(scans) == 1
        assert [await worker.pending() for worker in workers] == [3, 3, 3]
        await execute(workers, cloud)
        assert {post["instance"] for post in cloud.posts} == {f"instance-{i:08}" for i in range(9)}
        assert len(cloud.posts) == 9
        assert all(conn.closed for conn in cloud.connections)
        await scan(workers, SLOT + timedelta(seconds=15))
        await execute(workers, cloud)
        assert len(cloud.posts) == 9


@pytest.mark.asyncio
@pytest.mark.parametrize("tier,days", [("daily", 1), ("weekly", 7)])
@pytest.mark.parametrize("status", ["FAILED", "ERROR"])
async def test_terminal_failure_finishes_slot_without_pruning_and_allows_later_slot(
    db_redis, monkeypatch, tier, days, status
):
    cloud = TroveCloud()
    await enable(daily=int(tier == "daily"), weekly=int(tier == "weekly"))
    cloud.add("old-good", days=10, tier=tier)
    original = cloud.post

    def building(*args, **kwargs):
        response = original(*args, **kwargs)
        response.body["backup"]["status"] = "BUILDING"
        return response

    monkeypatch.setattr(cloud, "post", building)
    member = f"{PROJECT}:{INSTANCE}"
    async with WorkDispatcher(db_redis, dab._PREFIX) as worker:
        await scan([worker])
        await execute([worker], cloud)
        assert len(cloud.posts) == 1
        assert await db_redis.exists(dab._key("pending", member))
        cloud.records["backup-1"]["status"] = status
        await scan([worker], SLOT + timedelta(seconds=15))
        await execute([worker], cloud)
        assert len(cloud.posts) == 1
        assert cloud.deletes == []
        assert "old-good" in cloud.records
        assert not await db_redis.exists(dab._key("pending", member), dab._key("active", f"{member}:{tier}"))
        journal = json.loads(await db_redis.get(dab._key("journal", f"{member}:{tier}:{SLOT.isoformat()}")))
        assert journal["state"] == "failed" and journal["backup_id"] == "backup-1"
        monkeypatch.setattr(cloud, "post", original)
        for day in range(1, days + 1):
            await scan([worker], SLOT + timedelta(days=day))
            await execute([worker], cloud)
        assert len(cloud.posts) == 2
        assert cloud.posts[1]["name"] != cloud.posts[0]["name"]
        assert all(conn.closed for conn in cloud.connections)


@pytest.mark.asyncio
async def test_reply_loss_journal_precedes_post_and_recovers_without_resend(db_redis):
    cloud = TroveCloud()
    cloud.reply_loss = True
    gate = (threading.Event(), threading.Event())
    cloud.post_gate = gate
    await enable()
    async with AsyncExitStack() as stack:
        workers = await join(stack, db_redis)
        await scan(workers)
        execution = asyncio.create_task(execute(workers, cloud))
        try:
            await entered(gate[0])
            key = dab._key("journal", f"{PROJECT}:{INSTANCE}:daily:{SLOT.isoformat()}")
            assert json.loads(await db_redis.get(key))["state"] == "unknown"
            assert await db_redis.get(dab._key("active", f"{PROJECT}:{INSTANCE}:daily")) == key
        finally:
            gate[1].set()
        await execution
        assert len(cloud.posts) == 1
        assert json.loads(await db_redis.get(key))["state"] == "unknown"
        await scan(workers, SLOT + timedelta(seconds=15))
        await execute(workers, cloud)
        assert json.loads(await db_redis.get(key))["state"] == "accepted"
        assert len(cloud.posts) == 1
        assert all(conn.closed for conn in cloud.connections)


@pytest.mark.asyncio
async def test_unknown_absence_and_listing_error_never_authorize_second_post(db_redis):
    cloud = TroveCloud()
    cloud.reply_loss = True
    await enable()
    async with AsyncExitStack() as stack:
        workers = await join(stack, db_redis)
        await scan(workers)
        await execute(workers, cloud)
        cloud.records.clear()  # eventual-consistency absence is not rejection
        for read_error in (None, RuntimeError("listing unavailable")):
            cloud.read_error = read_error
            await scan(workers, SLOT + timedelta(days=1))
            await execute(workers, cloud)
            assert len(cloud.posts) == 1
        assert all(conn.closed for conn in cloud.connections)


@pytest.mark.asyncio
async def test_listing_failure_before_admission_is_fail_closed(db_redis):
    cloud = TroveCloud()
    cloud.read_error = RuntimeError("listing unavailable")
    await enable()
    async with WorkDispatcher(db_redis, dab._PREFIX) as worker:
        await scan([worker])
        await execute([worker], cloud)
        assert cloud.posts == []
        assert cloud.deletes == []
        assert cloud.connections[0].closed


@pytest.mark.asyncio
async def test_current_disable_after_listing_prevents_create_and_prune(db_redis):
    cloud = TroveCloud()
    gate = (threading.Event(), threading.Event())
    cloud.read_gate = gate
    cloud.add("old", days=5)
    await enable()
    async with WorkDispatcher(db_redis, dab._PREFIX) as worker:
        await scan([worker])
        execution = asyncio.create_task(execute([worker], cloud))
        try:
            await entered(gate[0])
            await dab.disable_db_auto_backup(PROJECT, INSTANCE)
        finally:
            gate[1].set()
        await execution
        assert cloud.posts == []
        assert cloud.deletes == []
        assert cloud.connections[0].closed


@pytest.mark.asyncio
async def test_revoked_token_after_first_post_prevents_later_tier_mutations(db_redis, monkeypatch):
    monkeypatch.setattr(wd, "HEARTBEAT_SECONDS", 0.01)
    cloud = TroveCloud()
    gate = (threading.Event(), threading.Event())
    cloud.post_gate = gate
    await enable(weekly=1, monthly=1)
    async with WorkDispatcher(db_redis, dab._PREFIX) as worker:
        await scan([worker])
        execution = asyncio.create_task(dab._execute_tick(worker, cloud.connection))
        try:
            await entered(gate[0])
            await db_redis.set(dab._key("lease", f"{PROJECT}:{INSTANCE}"), "successor", ex=90)
            await asyncio.sleep(0.05)
            assert not execution.done()  # ownership loss still drains the actual POST
            assert not cloud.connections[0].closed
        finally:
            gate[1].set()
        with pytest.raises(DispatcherUnavailable):
            await execution
        assert len(cloud.posts) == 1
        assert cloud.deletes == []
        assert cloud.connections[0].closed
        assert await db_redis.get(dab._key("lease", f"{PROJECT}:{INSTANCE}")) == "successor"


@pytest.mark.asyncio
async def test_scan_continues_while_submission_blocks_and_cancellation_drains(db_redis):
    cloud = TroveCloud()
    gate = (threading.Event(), threading.Event())
    cloud.post_gate = gate
    await enable()
    async with WorkDispatcher(db_redis, dab._PREFIX) as worker:
        await scan([worker])
        execution = asyncio.create_task(dab._execute_tick(worker, cloud.connection))
        try:
            await entered(gate[0])
            await asyncio.wait_for(dab._schedule_tick(worker, TRIGGER, SLOT + timedelta(seconds=15)), 1)
            execution.cancel()
            await asyncio.sleep(0)
            assert not execution.done()
            assert not cloud.connections[0].closed
        finally:
            gate[1].set()
        with pytest.raises(asyncio.CancelledError):
            await execution
        assert cloud.connections[0].closed
        assert not await db_redis.exists(dab._key("lease", f"{PROJECT}:{INSTANCE}"))


@pytest.mark.asyncio
async def test_cancellation_during_connection_acquisition_closes_late_connection(db_redis):
    cloud = TroveCloud()
    gate = (threading.Event(), threading.Event())
    await enable()

    def factory(project):
        gate[0].set()
        assert gate[1].wait(5)
        return cloud.connection(project)

    async with WorkDispatcher(db_redis, dab._PREFIX) as worker:
        await scan([worker])
        execution = asyncio.create_task(dab._execute_tick(worker, factory))
        try:
            await entered(gate[0])
            execution.cancel()
            await asyncio.sleep(0)
            assert not execution.done()
            execution.cancel()  # drain survives repeated cancellation
        finally:
            gate[1].set()
        with pytest.raises(asyncio.CancelledError):
            await execution
        assert cloud.posts == []
        assert cloud.connections[0].closed


@pytest.mark.asyncio
async def test_calendar_intervals_retention_and_exact_instance_identity(db_redis):
    cloud = TroveCloud()
    await enable(daily=2, weekly=1, monthly=1)
    cloud.add("daily-recent", days=0)
    cloud.add("daily-old-1", days=3)
    cloud.add("daily-old-2", days=4)
    cloud.add("weekly-recent", days=6, tier="weekly")
    cloud.add("monthly-recent", days=29, tier="monthly")
    cloud.add("other-instance", instance="instance-12345678-b", days=0)
    async with WorkDispatcher(db_redis, dab._PREFIX) as worker:
        await scan([worker])
        await execute([worker], cloud)
        assert cloud.posts == []
        assert cloud.deletes == ["daily-old-2"]
        await scan([worker], SLOT + timedelta(days=2))
        await execute([worker], cloud)
        assert {post["name"].split("_")[2] for post in cloud.posts} == {"daily", "weekly", "monthly"}
        assert len(cloud.posts) == 3
        assert "other-instance" in cloud.records


@pytest.mark.asyncio
async def test_scheduler_owns_and_drains_both_children(db_redis, monkeypatch):
    started = set()
    drained = set()
    ready = asyncio.Event()
    release = asyncio.Event()

    async def child(name):
        started.add(name)
        if len(started) == 2:
            ready.set()
        try:
            await asyncio.Event().wait()
        finally:
            await release.wait()
            drained.add(name)

    monkeypatch.setattr(dab, "_scan_loop", lambda *_: child("scan"))
    monkeypatch.setattr(dab, "_execution_loop", lambda *_: child("execute"))
    scheduler = asyncio.create_task(dab.run_scheduler("0 3 * * *"))
    await asyncio.wait_for(ready.wait(), 2)
    scheduler.cancel()
    await asyncio.sleep(0)
    scheduler.cancel()
    await asyncio.sleep(0)
    assert not scheduler.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await scheduler
    assert drained == {"scan", "execute"}


@pytest.mark.asyncio
async def test_crash_before_post_survives_handoff_without_blind_retry(db_redis):
    cloud = TroveCloud()
    await enable()
    member = f"{PROJECT}:{INSTANCE}"
    key = dab._key("journal", f"{member}:daily:{SLOT.isoformat()}")
    operation = {
        "state": "unknown",
        "name": dab._make_backup_name(INSTANCE, "daily", now=SLOT),
        "slot": SLOT.isoformat(),
        "instance_id": INSTANCE,
    }
    async with WorkDispatcher(db_redis, dab._PREFIX, worker_id="crashed") as worker:
        await scan([worker])
        # Durable admission is the crash boundary immediately before SDK POST.
        assert await db_redis.eval(dab._ADMIT, 2, key, dab._key("active", f"{member}:daily"), json.dumps(operation))
    async with WorkDispatcher(db_redis, dab._PREFIX, worker_id="successor") as successor:
        await scan([successor], SLOT + timedelta(seconds=15))
        await execute([successor], cloud)
        assert cloud.posts == []
        assert await db_redis.get(dab._key("pending", member)) == SLOT.isoformat()
        # An exact provider observation resolves uncertainty; a colliding name
        # on another instance must not resolve it.
        cloud.add("wrong-instance", instance="instance-12345678-b", name=operation["name"])
        await scan([successor], SLOT + timedelta(seconds=30))
        await execute([successor], cloud)
        assert json.loads(await db_redis.get(key))["state"] == "unknown"
        cloud.add("accepted-before-crash", name=operation["name"])
        await scan([successor], SLOT + timedelta(seconds=45))
        await execute([successor], cloud)
        assert json.loads(await db_redis.get(key))["backup_id"] == "accepted-before-crash"
        assert cloud.posts == []
        assert not await db_redis.exists(dab._key("pending", member))


@pytest.mark.asyncio
async def test_disable_between_retention_deletes_stops_remaining_mutations(db_redis):
    cloud = TroveCloud()
    cloud.add("newest", days=0)
    cloud.add("old-1", days=2)
    cloud.add("old-2", days=3)
    gate = (threading.Event(), threading.Event())
    cloud.delete_gate = gate
    await enable()
    async with WorkDispatcher(db_redis, dab._PREFIX) as worker:
        await scan([worker])
        execution = asyncio.create_task(execute([worker], cloud))
        try:
            await entered(gate[0])
            await dab.disable_db_auto_backup(PROJECT, INSTANCE)
        finally:
            gate[1].set()
        await execution
        assert cloud.deletes == ["old-1"]
        assert "old-2" in cloud.records
        assert cloud.connections[0].closed
