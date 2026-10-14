"""Distributed dispatcher consumers, real Redis Lua, and synchronous SDK boundaries."""

import asyncio
import json
import secrets
import threading
from collections import Counter
from contextlib import AsyncExitStack
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from openstack.exceptions import HttpException

from app.services import auto_backup as ab
from app.services import work_dispatcher as bd
from app.services.cache.keys import mutcount_key

START = datetime(2026, 5, 31, 12, tzinfo=UTC)
PARTICIPANT = ContextVar("backup_test_participant", default=None)
WORKERS = ("worker-a", "worker-b", "worker-c")


class ReadObserver:
    """Observe index consumers without replacing Redis commands or Lua execution."""

    def __init__(self, redis):
        self.redis = redis
        self.scans = []

    def __getattr__(self, name):
        return getattr(self.redis, name)

    async def smembers(self, key):
        if key == ab._ALL_KEY:
            self.scans.append(PARTICIPANT.get())
        return await self.redis.smembers(key)


class ProviderGate:
    """Bounded, thread-safe blocking at a genuine synchronous provider boundary."""

    def __init__(self):
        self.entered = asyncio.Event()
        self.release = threading.Event()
        self.loop = asyncio.get_running_loop()

    def wait(self):
        self.loop.call_soon_threadsafe(self.entered.set)
        if not self.release.wait(timeout=10):
            raise TimeoutError("provider gate was not released")


class BackupProvider:
    """Shared Cinder records; every factory call returns a separately owned session."""

    def __init__(self, project):
        self.project = project
        self.volumes = {}
        self.records = {}
        self.submissions = []
        self.deleted = []
        self.reads = []
        self.connections = []
        self.factory_gates = {}
        self.submit_gates = {}
        self.submit_errors = set()
        self.read_errors = set()
        self.inflight = Counter()
        self.max_inflight = Counter()
        self.lock = threading.RLock()

    def volume(self, volume_id, *, owner=None, status="available"):
        self.volumes[volume_id] = SimpleNamespace(
            id=volume_id, project_id=self.project if owner is None else owner, status=status
        )
        return volume_id

    def add(self, volume_id, backup_id, name, **fields):
        record = SimpleNamespace(
            id=backup_id,
            name=name,
            status="available",
            volume_id=volume_id,
            project_id=self.project,
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

    def factory(self, participant):
        def connect(project):
            assert project == self.project
            connection = ProviderConnection(self, participant)
            with self.lock:
                self.connections.append(connection)
            gate = self.factory_gates.get(participant)
            if gate:
                gate.wait()
            return connection

        return connect

    def unblock(self):
        for gate in (*self.factory_gates.values(), *self.submit_gates.values()):
            gate.release.set()


class ProviderConnection:
    def __init__(self, provider, participant):
        self.provider = provider
        self.participant = participant
        self.block_storage = self
        self.closed = 0

    def get_volume(self, volume_id):
        with self.provider.lock:
            self.provider.reads.append((self.participant, "volume", volume_id))
            return self.provider.volumes[volume_id]

    def backups(self, **kwargs):
        provider = self.provider
        volume_id = kwargs.get("volume_id")
        with provider.lock:
            provider.reads.append((self.participant, "list", volume_id))
            if volume_id in provider.read_errors:
                raise HttpException(message="private provider read", http_status=503)
            return [
                record
                for record in provider.records.values()
                if record.project_id == provider.project and (not volume_id or record.volume_id == volume_id)
            ]

    def get_backup(self, backup_id):
        provider = self.provider
        with provider.lock:
            record = provider.records[backup_id]
            provider.reads.append((self.participant, "backup", record.volume_id))
            if record.volume_id in provider.read_errors:
                raise HttpException(message="private provider read", http_status=503)
            return record

    def create_backup(self, **kwargs):
        provider = self.provider
        volume_id = kwargs["volume_id"]
        with provider.lock:
            provider.inflight[volume_id] += 1
            provider.max_inflight[volume_id] = max(provider.max_inflight[volume_id], provider.inflight[volume_id])
            provider.submissions.append((self.participant, dict(kwargs)))
            record = provider.add(
                volume_id,
                f"accepted-{len(provider.submissions)}",
                kwargs["name"],
                status="creating",
                created_at="2026-06-01T03:00:00+00:00",
            )
        try:
            gate = provider.submit_gates.get(volume_id)
            if gate:
                gate.wait()
            if volume_id in provider.submit_errors:
                raise HttpException(message="private provider acceptance", http_status=503)
            return record
        finally:
            with provider.lock:
                provider.inflight[volume_id] -= 1

    def delete_backup(self, backup_id, **kwargs):
        with self.provider.lock:
            self.provider.deleted.append(backup_id)
            del self.provider.records[backup_id]

    def close(self):
        with self.provider.lock:
            self.closed += 1


class DispatcherGroup:
    def __init__(self, redis, prefix, provider):
        self.redis = redis
        self.prefix = prefix
        self.provider = provider
        self.workers = {}
        self.tasks = []
        self.stack = AsyncExitStack()

    async def enter(self):
        for worker_id in WORKERS:
            dispatcher = bd.WorkDispatcher(self.redis, self.prefix, worker_id=worker_id)
            await dispatcher.__aenter__()
            self.workers[worker_id] = dispatcher
            self.stack.push_async_callback(self.leave, worker_id)
        return self

    async def leave(self, worker_id):
        dispatcher = self.workers.pop(worker_id, None)
        if dispatcher is not None:
            await dispatcher.__aexit__(None, None, None)

    async def tick(self, worker_id, clock):
        token = PARTICIPANT.set(worker_id)
        try:
            await ab.scheduler_tick(
                now=clock,
                connection_factory=self.provider.factory(worker_id),
                dispatcher=self.workers[worker_id],
            )
        finally:
            PARTICIPANT.reset(token)

    def start(self, worker_id, clock, *, leave=False):
        async def run():
            try:
                await self.tick(worker_id, clock)
            finally:
                if leave:
                    await self.leave(worker_id)

        task = asyncio.create_task(run())
        self.tasks.append(task)
        return task

    async def rounds(self, clock, count=2):
        # A follower may check its initial queue before the concurrent leader publishes.
        for _ in range(count):
            await asyncio.wait_for(
                asyncio.gather(*(self.start(worker_id, clock) for worker_id in self.workers)), timeout=8
            )

    async def close(self):
        self.provider.unblock()
        for task in self.tasks:
            if not task.done() and not task.cancelling():
                task.cancel()
        try:
            await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), timeout=10)
        finally:
            await self.stack.aclose()


@pytest.fixture
async def distributed(monkeypatch, _fake_redis_global):
    from app.services.cache import _get_redis

    redis = await _get_redis()
    token = secrets.token_hex(12)
    prefix = f"afterglow:test:distributed-backup:{token}"
    provider = BackupProvider(f"backup-test-{token}")
    observer = ReadObserver(redis)

    async def observed_redis():
        return observer

    monkeypatch.setattr(ab, "_get_redis", observed_redis)
    monkeypatch.setattr(ab, "_PREFIX", prefix)
    monkeypatch.setattr(ab, "_ALL_KEY", f"{prefix}:all_configs")
    monkeypatch.setattr(bd, "MEMBER_SECONDS", 2)
    monkeypatch.setattr(bd, "LEADER_SECONDS", 2)
    monkeypatch.setattr(bd, "HEARTBEAT_SECONDS", 0.1)
    group = DispatcherGroup(observer, prefix, provider)
    try:
        await group.enter()
        yield group
    finally:
        try:
            await group.close()
            assert all(connection.closed == 1 for connection in provider.connections)
            assert not any(provider.inflight.values())
            assert not [key async for key in redis.scan_iter(match=f"{prefix}:lease:*")]
        finally:
            owned_keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
            owned_keys.append(mutcount_key("cinder", provider.project))
            await redis.delete(*owned_keys)


async def save(provider, volume_id, **fields):
    return await ab.enable_auto_backup(provider.project, volume_id, now=START, **fields)


async def current(provider, volume_id):
    return await ab.get_auto_backup_config(provider.project, volume_id)


def due(config):
    return datetime.fromisoformat(config["next_run_at"])


def submission_counts(provider):
    return Counter(fields["volume_id"] for _, fields in provider.submissions)


async def seed(provider, count=9):
    volumes = [provider.volume(f"volume-{number:02d}") for number in range(count)]
    configs = [await save(provider, volume_id, max_daily=1, max_weekly=0, max_monthly=0) for volume_id in volumes]
    return volumes, due(configs[0])


@pytest.mark.asyncio
async def test_three_live_workers_submit_balanced_batches_and_only_leader_scans(distributed):
    group, provider = distributed, distributed.provider
    volumes, clock = await seed(provider)
    gates = [ProviderGate() for _ in WORKERS]
    for number, volume_id in enumerate(volumes):
        provider.submit_gates[volume_id] = gates[number % len(WORKERS)]

    # Start the followers once a provider consequence proves publication happened.
    first = group.start("worker-a", clock)
    await asyncio.wait_for(gates[0].entered.wait(), timeout=5)
    others = [group.start(worker_id, clock) for worker_id in WORKERS[1:]]
    await asyncio.wait_for(asyncio.gather(*(gate.entered.wait() for gate in gates)), timeout=5)
    assert {worker_id for worker_id, _ in provider.submissions} == set(WORKERS)
    assert all(connection.closed == 0 for connection in provider.connections)
    provider.unblock()
    await asyncio.wait_for(asyncio.gather(first, *others), timeout=8)

    assert submission_counts(provider) == Counter({volume_id: 1 for volume_id in volumes})
    assert Counter(worker_id for worker_id, _ in provider.submissions) == Counter(dict.fromkeys(WORKERS, 3))
    assert group.redis.scans and set(group.redis.scans) == {"worker-a"}
    assert all([(await current(provider, volume_id))["last_status"] == "creating" for volume_id in volumes])
    assert all(connection.closed == 1 for connection in provider.connections)

    for record in provider.records.values():
        record.status = "available"
    async with asyncio.timeout(5):
        while not all([(await current(provider, volume_id))["last_status"] == "available" for volume_id in volumes]):
            await group.rounds(clock, count=1)
    assert all([(await current(provider, volume_id))["last_status"] == "available" for volume_id in volumes])
    assert submission_counts(provider) == Counter({volume_id: 1 for volume_id in volumes})
    assert set(worker_id for worker_id, kind, _ in provider.reads if kind == "backup") == set(WORKERS)
    assert group.redis.scans and set(group.redis.scans) == {"worker-a"}
    assert set(provider.max_inflight.values()) == {1}
    assert not [key async for key in group.redis.scan_iter(match=f"{group.prefix}:active:*")]


@pytest.mark.asyncio
@pytest.mark.parametrize("departing", ["worker-a", "worker-b"])
async def test_graceful_leader_or_worker_exit_hands_due_work_to_survivors(distributed, departing):
    group, provider = distributed, distributed.provider
    volumes, clock = await seed(provider)
    await group.tick("worker-a", clock)
    assert submission_counts(provider) == Counter({volume_id: 1 for volume_id in volumes[::3]})
    await group.leave(departing)
    await group.workers[next(iter(group.workers))]._heartbeat()
    group.redis.scans.clear()
    async with asyncio.timeout(5):
        while submission_counts(provider) != Counter({volume_id: 1 for volume_id in volumes}):
            assert all(count == 1 for count in submission_counts(provider).values())
            await group.rounds(clock, count=1)

    assert submission_counts(provider) == Counter({volume_id: 1 for volume_id in volumes})
    assert all(
        worker_id != departing for worker_id, fields in provider.submissions if fields["volume_id"] not in volumes[::3]
    )
    assert group.redis.scans and departing not in group.redis.scans
    assert len(set(group.redis.scans)) == 1
    assert all(connection.closed == 1 for connection in provider.connections)
    for record in provider.records.values():
        record.status = "available"
    async with asyncio.timeout(5):
        while not all([(await current(provider, volume_id))["last_status"] == "available" for volume_id in volumes]):
            await group.rounds(clock, count=1)
    assert all([(await current(provider, volume_id))["last_status"] == "available" for volume_id in volumes])
    assert submission_counts(provider) == Counter({volume_id: 1 for volume_id in volumes})


@pytest.mark.asyncio
async def test_idle_paused_all_zero_policies_never_open_provider_connections(distributed):
    group, provider = distributed, distributed.provider
    await group.rounds(START + timedelta(days=365))
    assert provider.connections == []
    for number in range(9):
        volume_id = provider.volume(f"paused-{number:02d}")
        await save(provider, volume_id, enabled=False, max_daily=0, max_weekly=0, max_monthly=0)
        provider.add(volume_id, f"manual-{number}", "manual recovery point")
    await group.rounds(START + timedelta(days=365))
    assert provider.connections == []
    assert provider.submissions == []
    assert provider.deleted == []
    assert len(provider.records) == 9


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "owner,status,force,submitted",
    [
        ("owned", "available", False, True),
        ("owned", "in-use", True, True),
        ("owned", "in-use", False, False),
        ("owned", "backing-up", True, False),
        ("owned", "error", True, False),
        ("foreign", "available", True, False),
        (None, "available", True, False),
    ],
)
async def test_distributed_cycles_preserve_source_and_force_fences(distributed, owner, status, force, submitted):
    group, provider = distributed, distributed.provider
    volume_id = provider.volume("source-volume", status=status)
    provider.volumes[volume_id].project_id = provider.project if owner == "owned" else owner
    config = await save(provider, volume_id, force=force)
    await group.rounds(due(config))
    assert submission_counts(provider) == (Counter({volume_id: 1}) if submitted else Counter())
    assert (await current(provider, volume_id))["last_status"] == ("creating" if submitted else "skipped")
    assert provider.deleted == []
    assert all(connection.closed == 1 for connection in provider.connections)


@pytest.mark.asyncio
async def test_zero_tiers_and_paused_accepted_work_keep_recovery_points(distributed):
    group, provider = distributed, distributed.provider
    volumes, clock = await seed(provider, count=3)
    for volume_id in volumes:
        for tier in ("daily", "weekly", "monthly"):
            for number in range(2):
                provider.add(
                    volume_id,
                    f"old-{volume_id}-{tier}-{number}",
                    f"auto_{volume_id[:8]}_{tier}_2026050{number + 1}",
                    created_at=f"2026-05-0{number + 1}T03:00:00+00:00",
                )
    await group.rounds(clock)
    await ab.enable_auto_backup(
        provider.project, volumes[1], enabled=False, max_daily=0, max_weekly=0, max_monthly=0, now=clock
    )
    for record in provider.records.values():
        if record.id.startswith("accepted-"):
            record.status = "available"
    await group.rounds(clock)

    assert submission_counts(provider) == Counter({volume_id: 1 for volume_id in volumes})
    assert set(provider.deleted) == {
        f"old-{volume_id}-daily-{number}" for volume_id in (volumes[0], volumes[2]) for number in range(2)
    }
    assert all(
        f"old-{volumes[1]}-{tier}-{number}" in provider.records
        for tier in ("daily", "weekly", "monthly")
        for number in range(2)
    )
    assert all([(await current(provider, volume_id))["last_status"] == "available" for volume_id in volumes])
    paused = await current(provider, volumes[1])
    assert paused["enabled"] is False and paused["next_run_at"] is None
    before = len(provider.connections)
    await group.rounds(clock)
    assert len(provider.connections) == before


@pytest.mark.asyncio
async def test_dead_owner_reassignment_waits_volume_lease_and_reconciles_unknown_without_reissue(distributed):
    group, provider = distributed, distributed.provider
    volumes, clock = await seed(provider)
    volume_id = volumes[0]
    provider.submit_errors.add(volume_id)
    await group.tick("worker-a", clock)
    assert (await current(provider, volume_id))["last_status"] == "unknown"
    active_key = ab._key("active", provider.project, volume_id)
    operation = json.loads(await group.redis.get(active_key))
    assert operation["backup_id"] is None
    assert await group.redis.exists(operation["slot"])

    # A crashed process leaves its durable unknown journal and its unexpired lock.
    lease_key = ab._key("lease", provider.project, volume_id)
    await group.redis.set(lease_key, "dead-owner-volume-token", ex=90)
    dead = group.workers["worker-a"]
    dead._heartbeat_task.cancel()
    await asyncio.gather(dead._heartbeat_task, return_exceptions=True)
    seconds, microseconds = await group.redis.time()
    await group.redis.zadd(f"{group.prefix}:dispatch:members", {dead.worker_id: seconds + microseconds / 1_000_000 - 1})
    await group.workers["worker-b"]._heartbeat()

    before = len(provider.connections)
    await group.tick("worker-a", clock)
    assert len(provider.connections) == before
    # The expired coordinator does not shorten the independent live volume lock.
    provider.reads.clear()
    await group.tick("worker-b", clock)
    await group.tick("worker-c", clock)
    assert await group.redis.get(lease_key) == "dead-owner-volume-token"
    assert not any(read_volume == volume_id for _, _, read_volume in provider.reads)
    assert submission_counts(provider)[volume_id] == 1

    await group.redis.expire(lease_key, 0)
    provider.read_errors.add(volume_id)
    await group.tick("worker-b", clock)
    await group.tick("worker-c", clock)
    assert any(worker_id != "worker-a" and read_volume == volume_id for worker_id, _, read_volume in provider.reads)
    assert (await current(provider, volume_id))["last_status"] == "unknown"
    assert await group.redis.exists(active_key)
    assert submission_counts(provider)[volume_id] == 1

    # An unresolved slot blocks later calendar slots too, not only its first retry.
    await group.tick("worker-b", clock + timedelta(days=30))
    await group.tick("worker-c", clock + timedelta(days=30))
    assert submission_counts(provider)[volume_id] == 1
    provider.read_errors.remove(volume_id)
    for record in provider.records.values():
        if record.volume_id == volume_id:
            record.status = "available"
    await group.tick("worker-b", clock + timedelta(days=30))
    await group.tick("worker-c", clock + timedelta(days=30))
    assert (await current(provider, volume_id))["last_status"] == "available"
    assert not await group.redis.exists(active_key)
    assert await group.redis.exists(operation["slot"])
    assert submission_counts(provider)[volume_id] == 1
    assert provider.deleted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["factory", "submission"])
async def test_cancellation_drains_sdk_before_membership_volume_lease_and_connection_release(
    distributed, monkeypatch, boundary
):
    group, provider = distributed, distributed.provider
    volumes, clock = await seed(provider, count=1)
    volume_id = volumes[0]
    monkeypatch.setattr(ab, "_LEASE_SECONDS", 1)
    gate = ProviderGate()
    if boundary == "factory":
        provider.factory_gates["worker-a"] = gate
    else:
        provider.submit_gates[volume_id] = gate
    task = group.start("worker-a", clock, leave=True)
    await asyncio.wait_for(gate.entered.wait(), timeout=5)
    lease_key = ab._key("lease", provider.project, volume_id)
    lease_owner = await group.redis.get(lease_key)
    assert lease_owner
    task.cancel()

    # Cross both the shortened coordinator TTL and volume TTL during SDK drain.
    await asyncio.sleep(2.2)
    assert not task.done()
    assert await group.workers["worker-a"].is_leader()
    assert await group.redis.get(lease_key) == lease_owner
    assert await group.redis.ttl(lease_key) > 0
    assert len(provider.connections) == 1 and provider.connections[0].closed == 0
    await group.tick("worker-b", clock)
    await group.tick("worker-c", clock)
    assert len(provider.connections) == 1
    assert len(provider.submissions) == (0 if boundary == "factory" else 1)

    gate.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)
    assert provider.connections[0].closed == 1
    assert not await group.redis.exists(lease_key)
    assert "worker-a" not in group.workers
    await group.workers["worker-b"]._heartbeat()
    await group.rounds(clock)
    assert submission_counts(provider) == Counter({volume_id: 1})
    assert (await current(provider, volume_id))["last_status"] == "creating"
    assert all(connection.closed == 1 for connection in provider.connections)


@pytest.mark.asyncio
async def test_redis_coordination_fault_never_opens_provider_or_scans_policies(distributed, monkeypatch):
    group, provider = distributed, distributed.provider
    volumes, clock = await seed(provider)
    original = group.redis.eval

    async def unavailable(*args, **kwargs):
        raise ConnectionError("isolated test Redis unavailable")

    monkeypatch.setattr(group.redis, "eval", unavailable)
    for worker_id in WORKERS:
        with pytest.raises(bd.DispatcherUnavailable):
            await group.tick(worker_id, clock)
    assert provider.connections == []
    assert provider.submissions == []
    assert group.redis.scans == []
    monkeypatch.setattr(group.redis, "eval", original)
    for worker_id in WORKERS:
        with pytest.raises(bd.DispatcherUnavailable):
            await group.tick(worker_id, clock)
    assert provider.connections == []
    assert provider.submissions == []
    assert all([(await current(provider, volume_id))["last_status"] == "never" for volume_id in volumes])


def production_clock(monkeypatch, clock, provider):
    from app.services import keystone

    original = ab._now
    monkeypatch.setattr(ab, "_now", lambda value: clock if value is None else original(value))
    monkeypatch.setattr(ab, "_POLL_SECONDS", 0.05)
    monkeypatch.setattr(keystone, "get_admin_connection_for_project", provider.factory("loop-leader"))


async def live_members(group):
    seconds, microseconds = await group.redis.time()
    return await group.redis.zrangebyscore(
        f"{group.prefix}:dispatch:members", f"({seconds + microseconds / 1_000_000}", "+inf"
    )


async def first_member(group):
    async def wait():
        while True:
            members = await live_members(group)
            if members:
                return members[0]
            await asyncio.sleep(0.01)

    return await asyncio.wait_for(wait(), timeout=5)


@pytest.mark.asyncio
async def test_slow_production_leader_keeps_assigning_new_due_work_to_followers(distributed, monkeypatch):
    group, provider = distributed, distributed.provider
    for worker_id in tuple(group.workers):
        await group.leave(worker_id)
    volumes, clock = await seed(provider, count=1)
    production_clock(monkeypatch, clock, provider)
    factory_gate = ProviderGate()
    provider.factory_gates["loop-leader"] = factory_gate
    loop_task = asyncio.create_task(ab.scheduler_loop())
    group.tasks.append(loop_task)
    await asyncio.wait_for(factory_gate.entered.wait(), timeout=5)
    leader_id = await first_member(group)

    for suffix in ("~follower-1", "~follower-2"):
        worker_id = leader_id + suffix
        dispatcher = bd.WorkDispatcher(group.redis, group.prefix, worker_id=worker_id)
        await dispatcher.__aenter__()
        group.workers[worker_id] = dispatcher
        group.stack.push_async_callback(group.leave, worker_id)
    new_volume = provider.volume("volume-01")
    new_gate = ProviderGate()
    new_gate.release.set()
    provider.submit_gates[new_volume] = new_gate
    await save(provider, new_volume, max_daily=1, max_weekly=0, max_monthly=0)

    async def followers():
        while not new_gate.entered.is_set():
            await group.rounds(clock, count=1)
            await asyncio.sleep(0.01)

    follower_task = asyncio.create_task(followers())
    group.tasks.append(follower_task)
    await asyncio.wait_for(new_gate.entered.wait(), timeout=5)
    await asyncio.wait_for(follower_task, timeout=5)
    assert not factory_gate.release.is_set()
    assert not loop_task.done()
    assert provider.connections[0].closed == 0
    assert submission_counts(provider) == Counter({new_volume: 1})
    assert provider.submissions[0][0] in group.workers
    assert (await current(provider, new_volume))["last_status"] == "creating"

    loop_task.cancel()
    await asyncio.sleep(0.05)
    assert not loop_task.done()
    factory_gate.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(loop_task, timeout=5)
    # The drained factory is closed on cancellation, without ever submitting its volume.
    assert provider.connections[0].closed == 1
    assert submission_counts(provider)[volumes[0]] == 0
    assert not await group.redis.exists(ab._key("lease", provider.project, volumes[0]))


@pytest.mark.asyncio
async def test_production_loop_replaces_lost_incarnation_instead_of_stalling(distributed, monkeypatch):
    group, provider = distributed, distributed.provider
    for worker_id in tuple(group.workers):
        await group.leave(worker_id)
    clock = datetime(2026, 6, 1, 3, tzinfo=UTC)
    production_clock(monkeypatch, clock, provider)
    loop_task = asyncio.create_task(ab.scheduler_loop())
    group.tasks.append(loop_task)
    old_worker = await first_member(group)
    original = group.redis.eval
    faults = []

    async def one_incarnation_fault(*args, **kwargs):
        if old_worker in args and not faults:
            faults.append(old_worker)
            raise ConnectionError("one coordinator response lost")
        return await original(*args, **kwargs)

    monkeypatch.setattr(group.redis, "eval", one_incarnation_fault)
    volume_id = provider.volume("new-after-coordination-loss")
    submitted = ProviderGate()
    submitted.release.set()
    provider.submit_gates[volume_id] = submitted
    await save(provider, volume_id, max_daily=1, max_weekly=0, max_monthly=0)
    await asyncio.wait_for(submitted.entered.wait(), timeout=5)
    members = await live_members(group)
    assert faults == [old_worker]
    assert members and old_worker not in members
    assert submission_counts(provider) == Counter({volume_id: 1})
    assert not loop_task.done()
    loop_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(loop_task, timeout=5)
    assert all(connection.closed == 1 for connection in provider.connections)
    assert await live_members(group) == []


@pytest.mark.asyncio
async def test_early_completion_does_not_move_other_live_workers_pending_volume_ownership(distributed):
    group, provider = distributed, distributed.provider
    volumes, clock = await seed(provider)
    await group.tick("worker-a", clock)
    for record in provider.records.values():
        record.status = "available"
    await group.tick("worker-a", clock)

    # The leader has finished its three jobs before its followers poll. Shrinking
    # runnable work must not let it take their still-live assigned submissions.
    await group.rounds(clock, count=2)
    assert submission_counts(provider) == Counter({volume_id: 1 for volume_id in volumes})
    assert Counter(worker_id for worker_id, _ in provider.submissions) == Counter(dict.fromkeys(WORKERS, 3))
