"""FIFO graph admission against real fakeredis transactions; no native IAM calls."""

import asyncio
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services import identity_roles, session_store


class PollGate:
    """Park admission polls explicitly without changing renewal or asyncio globally."""

    def __init__(self):
        self.polls = asyncio.Queue()

    def __getattr__(self, name):
        return getattr(asyncio, name)

    async def sleep(self, delay):
        if delay > identity_roles._GRAPH_WAIT_POLL_SECONDS:
            await asyncio.sleep(delay)
            return
        resume = asyncio.get_running_loop().create_future()
        await self.polls.put(resume)
        await resume

    async def parked(self):
        return await asyncio.wait_for(self.polls.get(), timeout=2)


@pytest.fixture
async def graph_env(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    endpoint = "https://identity.invalid/v3"
    key = "afterglow:identity-role-graph:" + hashlib.sha256(endpoint.encode()).hexdigest()
    conn = SimpleNamespace(endpoint_for=lambda service: endpoint)
    monkeypatch.setattr(session_store, "_get_redis", AsyncMock(return_value=redis))
    gate = PollGate()
    monkeypatch.setattr(identity_roles, "asyncio", gate)
    env = SimpleNamespace(redis=redis, conn=conn, key=key, queue=key + ":waiters", gate=gate)
    try:
        yield env
    finally:
        await redis.close()


async def _one_write(env, entered=None, release=None):
    async with identity_roles._graph_lock(env.conn, wait=True) as lease:
        await lease.assert_owned()
        if entered is not None:
            entered.set()
        if release is not None:
            await release.wait()
        return lease.owner


async def _cancel(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_foreground_waits_for_existing_owner_without_stealing(graph_env):
    env = graph_env
    task = None
    try:
        async with identity_roles._graph_lock(env.conn) as holder:
            task = asyncio.create_task(_one_write(env))
            resume = await env.gate.parked()
            assert not task.done()
            assert await env.redis.get(env.key) == holder.owner
            assert await env.redis.zcard(env.queue) == 1
            assert await env.redis.ttl(env.queue) > identity_roles._GRAPH_WAIT_SECONDS
            assert await holder.waiters_pending()
        resume.set_result(None)
        owner = await asyncio.wait_for(task, timeout=2)
        assert owner != holder.owner
        assert await env.redis.get(env.key) is None
        assert await env.redis.zcard(env.queue) == 0
    finally:
        if task is not None and not task.done():
            await _cancel(task)


@pytest.mark.asyncio
async def test_fifo_and_failfast_writer_cannot_jump_live_queue(graph_env, monkeypatch):
    env = graph_env
    # Identical Redis timestamps must still order by registration, not random owner.
    seconds, microseconds = await env.redis.time()
    original_pipeline = env.redis.pipeline

    def pipeline(*args, **kwargs):
        pipe = original_pipeline(*args, **kwargs)
        pipe.time = AsyncMock(return_value=(seconds, microseconds))
        return pipe

    monkeypatch.setattr(env.redis, "pipeline", pipeline)
    first_entered, second_entered, release_first = asyncio.Event(), asyncio.Event(), asyncio.Event()
    tasks = []
    try:
        async with identity_roles._graph_lock(env.conn):
            first = asyncio.create_task(_one_write(env, first_entered, release_first))
            tasks.append(first)
            first_poll = await env.gate.parked()
            first_owner = (await env.redis.zrange(env.queue, 0, 0))[0]
            second = asyncio.create_task(_one_write(env, second_entered))
            tasks.append(second)
            second_poll = await env.gate.parked()
            queued = await env.redis.zrange(env.queue, 0, -1, withscores=True)
            assert len(queued) == 2
            assert queued[0][0] == first_owner
            assert queued[0][1] < queued[1][1]
        with pytest.raises(HTTPException) as error:
            async with identity_roles._graph_lock(env.conn):
                pytest.fail("fail-fast writer jumped the foreground queue")
        assert error.value.status_code == 409
        assert await env.redis.get(env.key) is None
        second_poll.set_result(None)
        second_poll = await env.gate.parked()
        assert not second_entered.is_set()
        first_poll.set_result(None)
        await asyncio.wait_for(first_entered.wait(), timeout=2)
        assert await env.redis.get(env.key) == first_owner
        assert not second_entered.is_set()
        release_first.set()
        assert await asyncio.wait_for(first, timeout=2) == first_owner
        second_poll.set_result(None)
        await asyncio.wait_for(second, timeout=2)
        assert second_entered.is_set()
        assert await env.redis.zcard(env.queue) == 0
    finally:
        release_first.set()
        for task in tasks:
            if not task.done():
                await _cancel(task)


@pytest.mark.asyncio
async def test_expired_holder_and_stale_queue_do_not_block_admission(graph_env):
    env = graph_env
    await env.redis.set(env.key, "expired-holder")
    task = asyncio.create_task(_one_write(env))
    try:
        resume = await env.gate.parked()
        await env.redis.zadd(env.queue, {"stale-waiter": 0})
        await env.redis.pexpire(env.key, 0)
        resume.set_result(None)
        await asyncio.wait_for(task, timeout=2)
        assert await env.redis.get(env.key) is None
        assert await env.redis.zcard(env.queue) == 0
    finally:
        if not task.done():
            await _cancel(task)


@pytest.mark.asyncio
async def test_waiter_expiry_cannot_reenter_or_delete_other_owner(graph_env):
    env = graph_env
    await env.redis.set(env.key, "other-owner")
    task = asyncio.create_task(_one_write(env))
    try:
        resume = await env.gate.parked()
        owner = (await env.redis.zrange(env.queue, 0, 0))[0]
        await env.redis.zadd(env.queue, {owner: 0})
        resume.set_result(None)
        with pytest.raises(HTTPException) as error:
            await asyncio.wait_for(task, timeout=2)
        assert error.value.status_code == 409
        assert await env.redis.zcard(env.queue) == 0
        assert await env.redis.get(env.key) == "other-owner"
    finally:
        if not task.done():
            await _cancel(task)


@pytest.mark.asyncio
async def test_monotonic_deadline_times_out_and_removes_only_own_waiter(graph_env, monkeypatch):
    env = graph_env
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(identity_roles, "time", SimpleNamespace(monotonic=lambda: clock.now))
    await env.redis.set(env.key, "other-owner")
    task = asyncio.create_task(_one_write(env))
    try:
        resume = await env.gate.parked()
        seconds, microseconds = await env.redis.time()
        await env.redis.zadd(env.queue, {"other-waiter": seconds + microseconds / 1_000_000 + 30})
        clock.now += identity_roles._GRAPH_WAIT_SECONDS + 1
        resume.set_result(None)
        with pytest.raises(HTTPException) as error:
            await asyncio.wait_for(task, timeout=2)
        assert error.value.status_code == 409
        assert await env.redis.zrange(env.queue, 0, -1) == ["other-waiter"]
        assert await env.redis.get(env.key) == "other-owner"
    finally:
        if not task.done():
            await _cancel(task)


@pytest.mark.asyncio
async def test_cancelled_waiter_cleans_own_entry_not_other_owner(graph_env):
    env = graph_env
    await env.redis.set(env.key, "other-owner")
    task = asyncio.create_task(_one_write(env))
    try:
        await env.gate.parked()
        seconds, microseconds = await env.redis.time()
        await env.redis.zadd(env.queue, {"other-waiter": seconds + microseconds / 1_000_000 + 30})
        await _cancel(task)
        assert await env.redis.zrange(env.queue, 0, -1) == ["other-waiter"]
        assert await env.redis.get(env.key) == "other-owner"
    finally:
        if not task.done():
            await _cancel(task)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["acquire", "register", "successor"])
async def test_cancellation_after_commit_releases_only_own_state(graph_env, monkeypatch, phase):
    env = graph_env
    committed = asyncio.Event()
    original_pipeline = env.redis.pipeline
    intercept = True
    if phase == "register":
        await env.redis.set(env.key, "other-owner")

    def pipeline(*args, **kwargs):
        pipe = original_pipeline(*args, **kwargs)
        original_execute = pipe.execute

        async def execute(*execute_args, **execute_kwargs):
            nonlocal intercept
            result = await original_execute(*execute_args, **execute_kwargs)
            if intercept:
                intercept = False
                committed.set()
                await asyncio.Event().wait()
            return result

        pipe.execute = execute
        return pipe

    monkeypatch.setattr(env.redis, "pipeline", pipeline)
    task = asyncio.create_task(_one_write(env))
    try:
        await asyncio.wait_for(committed.wait(), timeout=2)
        assert await env.redis.get(env.key) is not None
        if phase == "successor":
            await env.redis.set(env.key, "successor")
        await _cancel(task)
        expected = {"acquire": None, "register": "other-owner", "successor": "successor"}[phase]
        assert await env.redis.get(env.key) == expected
        assert await env.redis.zcard(env.queue) == 0
    finally:
        if not task.done():
            await _cancel(task)


@pytest.mark.asyncio
async def test_member_role_write_queues_behind_background_lease(graph_env, monkeypatch):
    """Domain IAM member edits wait for a background holder instead of failing 409."""
    from app.services import keystone, project_service

    env = graph_env
    env.conn.close = lambda: None
    monkeypatch.setattr(keystone, "get_admin_project_connection", lambda: env.conn)
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: object())
    monkeypatch.setattr(identity_roles, "load_catalog", lambda conn: [])
    monkeypatch.setattr(project_service, "_assignment_rows", lambda ks, project_id, effective=False: [])

    async def member_write():
        async with project_service._membership_write("project-a") as (lease, *_):
            await lease.assert_owned()
            return lease.owner

    task = None
    try:
        async with identity_roles._graph_lock(env.conn) as holder:
            task = asyncio.create_task(member_write())
            resume = await env.gate.parked()
            assert not task.done()
            assert await holder.waiters_pending()
        resume.set_result(None)
        owner = await asyncio.wait_for(task, timeout=2)
        assert owner != holder.owner
        assert await env.redis.zcard(env.queue) == 0
    finally:
        if task is not None and not task.done():
            await _cancel(task)


@pytest.mark.asyncio
@pytest.mark.parametrize("wait", [False, True])
async def test_redis_admission_failure_is_unavailable(graph_env, monkeypatch, wait):
    env = graph_env
    monkeypatch.setattr(env.redis, "pipeline", lambda: (_ for _ in ()).throw(RedisConnectionError("offline")))
    with pytest.raises(HTTPException) as error:
        async with identity_roles._graph_lock(env.conn, wait=wait):
            pytest.fail("Redis outage admitted a writer")
    assert error.value.status_code == 503
    assert await env.redis.get(env.key) is None


@pytest.mark.asyncio
async def test_concurrent_queue_registration_fences_failfast_admission(graph_env, monkeypatch):
    env = graph_env
    original_pipeline = env.redis.pipeline
    intercept = True

    def pipeline(*args, **kwargs):
        pipe = original_pipeline(*args, **kwargs)
        original_execute = pipe.execute

        async def execute(*execute_args, **execute_kwargs):
            nonlocal intercept
            if intercept:
                intercept = False
                seconds, microseconds = await env.redis.time()
                await env.redis.zadd(env.queue, {"older-waiter": seconds + microseconds / 1_000_000 + 30})
            return await original_execute(*execute_args, **execute_kwargs)

        pipe.execute = execute
        return pipe

    monkeypatch.setattr(env.redis, "pipeline", pipeline)
    with pytest.raises(HTTPException) as error:
        async with identity_roles._graph_lock(env.conn):
            pytest.fail("writer admitted after the queue changed during WATCH")
    assert error.value.status_code == 409
    assert await env.redis.get(env.key) is None
    assert await env.redis.zrange(env.queue, 0, -1) == ["older-waiter"]


@pytest.mark.asyncio
async def test_waiters_pending_prunes_expiry_and_requires_live_owner(graph_env):
    env = graph_env
    async with identity_roles._graph_lock(env.conn) as lease:
        await env.redis.zadd(env.queue, {"expired": 0})
        assert not await lease.waiters_pending()
        assert await env.redis.zcard(env.queue) == 0
        seconds, microseconds = await env.redis.time()
        await env.redis.zadd(env.queue, {"live": seconds + microseconds / 1_000_000 + 30})
        assert await lease.waiters_pending()
        await env.redis.set(env.key, "successor")
        with pytest.raises(HTTPException) as error:
            await lease.waiters_pending()
        assert error.value.status_code == 409
    assert await env.redis.get(env.key) == "successor"
    assert await env.redis.zrange(env.queue, 0, -1) == ["live"]


@pytest.mark.asyncio
async def test_waiters_pending_redis_error_is_not_no_demand(graph_env, monkeypatch):
    env = graph_env
    async with identity_roles._graph_lock(env.conn) as lease:
        monkeypatch.setattr(env.redis, "pipeline", lambda: (_ for _ in ()).throw(RedisConnectionError("offline")))
        with pytest.raises(HTTPException) as error:
            await lease.waiters_pending()
        assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_waiters_pending_repeats_after_own_renewal_touches_watched_key(graph_env, monkeypatch):
    env = graph_env
    async with identity_roles._graph_lock(env.conn) as lease:
        seconds, microseconds = await env.redis.time()
        await env.redis.zadd(env.queue, {"live": seconds + microseconds / 1_000_000 + 30})
        original = env.redis.pipeline
        renewed = []

        def pipeline(*args, **kwargs):
            pipe = original(*args, **kwargs)
            get = pipe.get

            async def get_then_renew(key):
                value = await get(key)
                if not renewed:
                    # The lease's own renewal EXPIRE lands between WATCH and EXEC.
                    renewed.append(await env.redis.expire(env.key, 60))
                return value

            pipe.get = get_then_renew
            return pipe

        monkeypatch.setattr(env.redis, "pipeline", pipeline)
        assert await lease.waiters_pending()
        assert renewed == [True]


@pytest.mark.asyncio
async def test_lost_lease_cannot_report_no_waiters_or_write(graph_env):
    env = graph_env
    async with identity_roles._graph_lock(env.conn) as lease:
        lease.lost = True
        with pytest.raises(HTTPException) as error:
            await lease.waiters_pending()
        assert error.value.status_code == 409
        operation = AsyncMock()
        with pytest.raises(HTTPException) as error:
            await identity_roles._write(lease, operation)
        assert error.value.status_code == 409
        operation.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("redis_error", [False, True])
async def test_renewal_loss_fences_further_lease_observations(graph_env, monkeypatch, redis_error):
    env = graph_env
    monkeypatch.setattr(identity_roles, "_GRAPH_LOCK_TTL_SECONDS", 0.03)
    await env.redis.set(env.key, "original")
    lease = identity_roles._GraphLease(env.redis, env.key, "original")
    renewal = asyncio.create_task(lease.renew())
    try:
        resume = await env.gate.parked()
        if redis_error:
            monkeypatch.setattr(env.redis, "pipeline", lambda: (_ for _ in ()).throw(RedisConnectionError("offline")))
        else:
            await env.redis.set(env.key, "successor")
        resume.set_result(None)
        await asyncio.wait_for(renewal, timeout=2)
        assert lease.lost
        with pytest.raises(HTTPException) as error:
            await lease.waiters_pending()
        assert error.value.status_code == 409
        assert await env.redis.get(env.key) == ("original" if redis_error else "successor")
    finally:
        if not renewal.done():
            await _cancel(renewal)


@pytest.mark.asyncio
async def test_redis_failure_while_waiting_is_unavailable_and_cleans_entry(graph_env, monkeypatch):
    env = graph_env
    await env.redis.set(env.key, "other-owner")
    task = asyncio.create_task(_one_write(env))
    try:
        resume = await env.gate.parked()
        assert await env.redis.zcard(env.queue) == 1
        monkeypatch.setattr(env.redis, "pipeline", lambda: (_ for _ in ()).throw(RedisConnectionError("offline")))
        resume.set_result(None)
        with pytest.raises(HTTPException) as error:
            await asyncio.wait_for(task, timeout=2)
        assert error.value.status_code == 503
        assert await env.redis.zcard(env.queue) == 0
        assert await env.redis.get(env.key) == "other-owner"
    finally:
        if not task.done():
            await _cancel(task)
