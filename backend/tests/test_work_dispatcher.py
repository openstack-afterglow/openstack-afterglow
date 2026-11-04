"""Assigned consumers exercise Redis membership, claim and failover fences."""

import asyncio
import secrets
import threading
from contextlib import AsyncExitStack, suppress

import pytest

from app.services import work_dispatcher as bd


@pytest.fixture
async def coordination(_fake_redis_global, monkeypatch):
    from app.services.cache import _get_redis

    redis = await _get_redis()
    prefix = f"afterglow:test:work-dispatcher:{secrets.token_hex(12)}"
    # Deterministic tests explicitly renew or expire server-time membership.
    monkeypatch.setattr(bd, "HEARTBEAT_SECONDS", 3600)
    try:
        yield redis, prefix
    finally:
        keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
        if keys:
            await redis.delete(*keys)


async def server_now(redis):
    seconds, micros = await redis.time()
    return int(seconds) + int(micros) / 1_000_000


async def expire_member(redis, worker):
    await redis.zadd(worker._members_key, {worker.worker_id: await server_now(redis) - 1})


async def join_three(stack, redis, prefix):
    return [
        await stack.enter_async_context(bd.WorkDispatcher(redis, prefix, worker_id=f"worker-{letter}"))
        for letter in "abc"
    ]


async def drain(worker, lease_seconds=90):
    claims = []
    for _ in range(await worker.pending()):
        claim = await worker.claim(lease_seconds)
        if claim is None:
            break
        claims.append(claim)
    return claims


@pytest.mark.asyncio
async def test_three_live_workers_claim_balanced_disjoint_volume_leases(coordination):
    redis, prefix = coordination
    runnable = [f"project:volume-{index:02}" for index in range(11)]
    async with AsyncExitStack() as stack:
        workers = await join_three(stack, redis, prefix)
        assert [await worker.is_leader() for worker in workers] == [True, False, False]
        assert not await workers[1].publish(runnable)
        assert await workers[0].publish([*reversed(runnable), runnable[0]])
        claims = await asyncio.gather(*(drain(worker) for worker in workers))
        assert [len(batch) for batch in claims] == [4, 4, 3]
        assert [set(member for member, _ in batch) for batch in claims] == [
            set(runnable[index::3]) for index in range(3)
        ]
        all_claims = [claim for batch in claims for claim in batch]
        assert len({member for member, _ in all_claims}) == len(runnable)
        assert len({owner for _, owner in all_claims}) == len(runnable)
        for member, owner in all_claims:
            assert await redis.get(f"{prefix}:lease:{member}") == owner
            assert 0 < await redis.ttl(f"{prefix}:lease:{member}") <= 90
        assert [await worker.pending() for worker in workers] == [0, 0, 0]
        # Republishing executing policies cannot produce a second claim.
        assert await workers[0].publish(runnable)
        assert await asyncio.gather(*(worker.claim(90) for worker in workers)) == [None, None, None]
        for member, owner in all_claims:
            assert await redis.get(f"{prefix}:lease:{member}") == owner


@pytest.mark.asyncio
async def test_busy_hint_is_bounded_and_rebuilt_without_touching_existing_lease(coordination):
    redis, prefix = coordination
    member = "project:volume-busy"
    lease_key = f"{prefix}:lease:{member}"
    await redis.set(lease_key, "existing-sdk-operation", ex=90)
    async with bd.WorkDispatcher(redis, prefix, worker_id="worker-a") as worker:
        assert await worker.publish([member])
        assert await worker.pending() == 1
        assert await worker.claim(90) is None
        assert await worker.pending() == 0
        assert await redis.get(lease_key) == "existing-sdk-operation"
        await redis.expire(lease_key, 0)
        assert await worker.claim(90) is None  # No invented local retry queue.
        assert await worker.publish([member])
        claimed_member, owner = await worker.claim(90)
        assert claimed_member == member
        assert owner != "existing-sdk-operation"
        assert await redis.get(lease_key) == owner


@pytest.mark.asyncio
async def test_stale_assignment_cannot_claim_another_workers_volume(coordination):
    redis, prefix = coordination
    members = ["project:volume-a", "project:volume-b"]
    async with AsyncExitStack() as stack:
        workers = await join_three(stack, redis, prefix)
        assert await workers[0].publish(members)
        # A leftover hint does not grant execution authority.
        await redis.sadd(workers[2]._ready_key, *members)
        assert await workers[2].claim(90) is None
        assert await workers[2].pending() == 0
        assert not await redis.exists(*(f"{prefix}:lease:{member}" for member in members))
        assert {claim[0] for worker in workers[:2] for claim in await drain(worker)} == set(members)


@pytest.mark.asyncio
async def test_member_expiry_denies_old_publish_claim_and_renewal(coordination):
    redis, prefix = coordination
    async with AsyncExitStack() as stack:
        leader, follower, _ = await join_three(stack, redis, prefix)
        assert await leader.publish(["project:volume-a", "project:volume-b"])
        before = await redis.hgetall(leader._assignments_key)
        await expire_member(redis, leader)
        assert not await leader.is_leader()
        assert not await leader.publish(["project:unauthorized"])
        assert await leader.pending() == 0
        assert await leader.claim(90) is None
        assert not await leader._heartbeat()  # Expired incarnations cannot revive.
        assert await redis.hgetall(leader._assignments_key) == before
        assert await follower._heartbeat()
        assert await follower.is_leader()
        assert not await leader.publish(["project:unauthorized"])
        assert await redis.zscore(leader._members_key, leader.worker_id) is None


@pytest.mark.asyncio
async def test_leader_ttl_expiry_hands_off_without_expiring_member(coordination):
    redis, prefix = coordination
    async with AsyncExitStack() as stack:
        old, successor, _ = await join_three(stack, redis, prefix)
        assert await old.publish(["project:original"])
        await redis.expire(old._leader_key, 0)
        assert not await old.publish(["project:stale"])
        assert await successor._heartbeat()
        assert await successor.is_leader()
        assert not await old.is_leader()
        assert not await old.publish(["project:stale"])
        assert await old._heartbeat()  # Member renewal cannot steal a live leader.
        assert not await old.is_leader()
        assert await successor.publish(["project:new"])
        assert {claim[0] for worker in (old, successor) for claim in await drain(worker)} == {"project:new"}


@pytest.mark.asyncio
async def test_absent_owner_reassignment_preserves_old_ninety_second_volume_lease(coordination):
    redis, prefix = coordination
    runnable = [f"project:volume-{index}" for index in range(6)]
    async with AsyncExitStack() as stack:
        leader, absent, survivor = await join_three(stack, redis, prefix)
        assert await leader.publish(runnable)
        claimed_member, old_owner = await absent.claim(90)
        await expire_member(redis, absent)
        assert await leader.publish(runnable)
        assert not await redis.exists(absent._ready_key)
        claims = await asyncio.gather(drain(leader), drain(survivor))
        assert {member for batch in claims for member, _ in batch} == set(runnable) - {claimed_member}
        assert await redis.get(f"{prefix}:lease:{claimed_member}") == old_owner
        assert await redis.ttl(f"{prefix}:lease:{claimed_member}") > bd.LEADER_SECONDS
        assert await absent.claim(90) is None
        await redis.expire(f"{prefix}:lease:{claimed_member}", 0)
        assert await leader.publish(runnable)
        recovered = [*await drain(leader), *await drain(survivor)]
        assert [member for member, _ in recovered] == [claimed_member]
        assert recovered[0][1] != old_owner


@pytest.mark.asyncio
async def test_replacement_publish_and_empty_publish_remove_prior_ready_hints(coordination):
    redis, prefix = coordination
    async with AsyncExitStack() as stack:
        workers = await join_three(stack, redis, prefix)
        assert await workers[0].publish([f"project:volume-{index}" for index in range(9)])
        assert await workers[0].publish(["project:replacement"])
        assert [await worker.pending() for worker in workers] == [1, 0, 0]
        assert await workers[0].publish([])
        assert not await redis.exists(workers[0]._assignments_key)
        assert not await redis.exists(*(worker._ready_key for worker in workers))
        assert await asyncio.gather(*(worker.claim(90) for worker in workers)) == [None, None, None]


@pytest.mark.asyncio
async def test_graceful_exit_removes_only_self_and_never_releases_volume_leases(coordination):
    redis, prefix = coordination
    async with AsyncExitStack() as stack:
        leader, follower, survivor = await join_three(stack, redis, prefix)
        assert await leader.publish(["project:volume-a", "project:volume-b", "project:volume-c"])
        member, owner = await leader.claim(90)
        follower_ready = await redis.smembers(follower._ready_key)
        await leader.__aexit__(None, None, None)
        assert leader._heartbeat_task.done()
        assert await redis.zscore(leader._members_key, leader.worker_id) is None
        assert not await redis.exists(leader._ready_key, leader._leader_key)
        assert await redis.get(f"{prefix}:lease:{member}") == owner
        assert await redis.smembers(follower._ready_key) == follower_ready
        assert await follower._heartbeat()
        assert await follower.is_leader()
        # Repeated stale cleanup does not erase the successor's leader lease.
        await leader.__aexit__(None, None, None)
        assert await follower.is_leader()
        assert await survivor.pending() == 1


@pytest.mark.asyncio
async def test_live_worker_label_collision_cannot_remove_existing_membership(coordination):
    redis, prefix = coordination
    async with bd.WorkDispatcher(redis, prefix, worker_id="shared-label") as owner:
        assert await owner.publish(["project:volume"])
        duplicate = bd.WorkDispatcher(redis, prefix, worker_id=owner.worker_id)
        with pytest.raises(bd.DispatcherUnavailable):
            await duplicate.__aenter__()
        assert duplicate._heartbeat_task is None
        assert await owner.is_leader()
        assert await owner.pending() == 1
        assert (await owner.claim(90))[0] == "project:volume"


@pytest.mark.asyncio
async def test_old_context_exit_cannot_remove_replacement_with_same_label(coordination):
    redis, prefix = coordination
    old = bd.WorkDispatcher(redis, prefix, worker_id="worker-label")
    async with old:
        await expire_member(redis, old)
        async with bd.WorkDispatcher(redis, prefix, worker_id=old.worker_id) as replacement:
            assert not await old.publish(["project:old"])
            await old.__aexit__(None, None, None)
            assert await replacement.is_leader()
            assert await replacement.publish(["project:replacement"])
            assert (await replacement.claim(90))[0] == "project:replacement"
            with pytest.raises(bd.DispatcherUnavailable):
                await old.publish(["project:old"])


class RedisFault:
    def __init__(self, redis):
        self.redis = redis
        self.unavailable = False

    async def eval(self, *args):
        if self.unavailable:
            raise ConnectionError("Redis unavailable")
        return await self.redis.eval(*args)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["is_leader", "publish", "pending", "claim", "available_roles", "is_assigned"])
async def test_coordination_fault_requires_new_context_and_leaves_ttl_fallback(coordination, method):
    redis, prefix = coordination
    boundary = RedisFault(redis)
    worker = bd.WorkDispatcher(boundary, prefix, worker_id="worker-a")
    async with worker:
        assert await worker.publish(["project:volume"])
        boundary.unavailable = True
        args = {"publish": (["project:volume"],), "claim": (90,), "is_assigned": ("project:volume",)}.get(method, ())
        with pytest.raises(bd.DispatcherUnavailable):
            await getattr(worker, method)(*args)
        assert worker.lost
        boundary.unavailable = False
        with pytest.raises(bd.DispatcherUnavailable):
            await worker.claim(90)
        assert not await redis.exists(f"{prefix}:lease:project:volume")
        boundary.unavailable = True
    assert worker._heartbeat_task.done()
    assert await redis.zscore(worker._members_key, worker.worker_id) is not None
    assert 0 < await redis.ttl(worker._members_key) <= bd.MEMBER_SECONDS * 2
    assert 0 < await redis.ttl(worker._leader_key) <= bd.LEADER_SECONDS


@pytest.mark.asyncio
async def test_cleanup_fault_preserves_original_cancellation_and_stops_heartbeat(coordination):
    redis, prefix = coordination
    boundary = RedisFault(redis)
    worker = bd.WorkDispatcher(boundary, prefix, worker_id="worker-a")
    entered = asyncio.Event()

    async def cancelled_consumer():
        async with worker:
            entered.set()
            await asyncio.Event().wait()

    consumer = asyncio.create_task(cancelled_consumer())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        boundary.unavailable = True
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer
        assert worker._heartbeat_task.done()
        assert await redis.get(worker._leader_key) == worker.worker_id
    finally:
        consumer.cancel()
        with suppress(asyncio.CancelledError):
            await consumer


@pytest.mark.asyncio
async def test_independent_heartbeat_renews_server_time_membership_and_leader(coordination, monkeypatch):
    redis, prefix = coordination
    renewed = asyncio.Event()
    observe = {"renewal": False}

    class RenewalBoundary:
        async def eval(self, *args):
            result = await redis.eval(*args)
            if args[-1] == "renew" and observe["renewal"]:
                renewed.set()
            return result

    monkeypatch.setattr(bd, "HEARTBEAT_SECONDS", 0.01)
    worker = bd.WorkDispatcher(RenewalBoundary(), prefix, worker_id="worker-a")
    async with worker:
        near_expiry = await server_now(redis) + 10
        await redis.zadd(worker._members_key, {worker.worker_id: near_expiry})
        await redis.expire(worker._leader_key, 10)
        observe["renewal"] = True
        await asyncio.wait_for(renewed.wait(), 2)
        assert await redis.zscore(worker._members_key, worker.worker_id) > near_expiry
        assert await redis.ttl(worker._leader_key) > 10
        assert await worker.is_leader()
    assert worker._heartbeat_task.done()
    assert not await redis.exists(worker._leader_key)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["expiry", "redis"])
async def test_background_heartbeat_loss_terminates_incarnation(coordination, monkeypatch, failure):
    redis, prefix = coordination
    boundary = RedisFault(redis)
    monkeypatch.setattr(bd, "HEARTBEAT_SECONDS", 0.01)
    worker = bd.WorkDispatcher(boundary, prefix, worker_id="worker-a")
    async with worker:
        assert await worker.publish(["project:volume"])
        if failure == "expiry":
            await expire_member(redis, worker)
        else:
            boundary.unavailable = True
        await asyncio.wait_for(asyncio.shield(worker._heartbeat_task), 2)
        assert worker.lost
        boundary.unavailable = False
        with pytest.raises(bd.DispatcherUnavailable):
            await worker.claim(90)
        assert not await redis.exists(f"{prefix}:lease:project:volume")


@pytest.mark.asyncio
async def test_registration_redis_fault_never_starts_background_work(coordination):
    redis, prefix = coordination
    boundary = RedisFault(redis)
    boundary.unavailable = True
    worker = bd.WorkDispatcher(boundary, prefix, worker_id="worker-a")
    with pytest.raises(bd.DispatcherUnavailable):
        await worker.__aenter__()
    assert worker._heartbeat_task is None
    assert not await redis.exists(worker._members_key, worker._leader_key)


@pytest.mark.asyncio
async def test_cancelled_registration_reply_cleans_owned_membership(coordination):
    redis, prefix = coordination
    registered = asyncio.Event()

    class InterruptedRegistration:
        async def eval(self, *args):
            result = await redis.eval(*args)
            if args[-1] == "join":
                registered.set()
                await asyncio.Event().wait()
            return result

    worker = bd.WorkDispatcher(InterruptedRegistration(), prefix, worker_id="worker-a")
    entering = asyncio.create_task(worker.__aenter__())
    try:
        await asyncio.wait_for(registered.wait(), 2)
        assert await redis.get(worker._leader_key) == worker.worker_id
        entering.cancel()
        with pytest.raises(asyncio.CancelledError):
            await entering
        assert worker._heartbeat_task is None
        assert await redis.zscore(worker._members_key, worker.worker_id) is None
        assert not await redis.exists(worker._leader_key)
    finally:
        entering.cancel()
        with suppress(asyncio.CancelledError):
            await entering


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["heartbeat", "exit"])
async def test_delayed_claim_reply_is_rejected_after_incarnation_revocation(coordination, monkeypatch, revocation):
    redis, prefix = coordination
    claimed = asyncio.Event()
    release_reply = asyncio.Event()

    class DelayedClaim(RedisFault):
        async def eval(self, *args):
            result = await super().eval(*args)
            if isinstance(result, (list, tuple)) and len(result) == 2:
                claimed.set()
                await release_reply.wait()
            return result

    boundary = DelayedClaim(redis)
    monkeypatch.setattr(bd, "HEARTBEAT_SECONDS", 0.01)
    worker = bd.WorkDispatcher(boundary, prefix, worker_id="worker-a")
    async with worker:
        assert await worker.publish(["project:volume"])
        claiming = asyncio.create_task(worker.claim(90))
        try:
            await asyncio.wait_for(claimed.wait(), 2)
            assert await redis.get(f"{prefix}:lease:project:volume")
            if revocation == "heartbeat":
                boundary.unavailable = True
                await asyncio.wait_for(asyncio.shield(worker._heartbeat_task), 2)
                assert worker.lost
                boundary.unavailable = False
            else:
                await worker.__aexit__(None, None, None)
            release_reply.set()
            with pytest.raises(bd.DispatcherUnavailable):
                await claiming
            # The accepted-but-unusable token never reaches SDK work. Preserve
            # its lease until TTL rather than risk another owner executing early.
            assert 0 < await redis.ttl(f"{prefix}:lease:project:volume") <= 90
            with pytest.raises(bd.DispatcherUnavailable):
                await worker.claim(90)
        finally:
            boundary.unavailable = False
            release_reply.set()
            claiming.cancel()
            with suppress(asyncio.CancelledError, bd.DispatcherUnavailable):
                await claiming


async def eventually(predicate):
    async with asyncio.timeout(3):
        while not await predicate():
            await asyncio.sleep(0.005)


@pytest.mark.asyncio
async def test_late_role_members_rebalance_and_mixed_capabilities_never_receive_foreign_roles(coordination):
    redis, prefix = coordination
    roles = ["cleanup", "health", "snapshot"]
    async with AsyncExitStack() as stack:
        first = await stack.enter_async_context(bd.WorkDispatcher(redis, prefix, worker_id="a", roles=tuple(roles)))
        assert await first.available_roles() == roles
        assert await first.publish(roles, rebalance=True)
        assert [await first.is_assigned(role) for role in roles] == [True, True, True]
        second = await stack.enter_async_context(bd.WorkDispatcher(redis, prefix, worker_id="b", roles=tuple(roles)))
        third = await stack.enter_async_context(bd.WorkDispatcher(redis, prefix, worker_id="c", roles=("snapshot",)))
        assert await first.publish(roles, rebalance=True)
        claims = [await drain(worker) for worker in (first, second, third)]
        assert [[member for member, _ in batch] for batch in claims] == [["cleanup"], ["health"], ["snapshot"]]
        assert not await third.is_assigned("cleanup")
        # Same topology does not churn long-running roles between publications.
        original = await redis.hgetall(first._assignments_key)
        assert await first.publish(list(reversed(roles)), rebalance=True)
        assert await redis.hgetall(first._assignments_key) == original
        await third.__aexit__(None, None, None)
        assert await first.publish(roles, rebalance=True)
        assert not await third._heartbeat()
        assert await redis.hget(first._assignments_key, "snapshot") in {first.worker_id, second.worker_id}
        # A removed capability is no longer advertised or assignable.
        await second.__aexit__(None, None, None)
        await first.__aexit__(None, None, None)
        restricted = await stack.enter_async_context(bd.WorkDispatcher(redis, prefix, worker_id="d", roles=("health",)))
        assert await restricted.available_roles() == ["health"]
        assert await restricted.publish(roles, rebalance=True)
        assert await restricted.pending() == 1
        assert not await restricted.is_assigned("cleanup")


@pytest.mark.asyncio
async def test_default_target_publication_keeps_live_pending_owner_after_late_join(coordination):
    redis, prefix = coordination
    async with AsyncExitStack() as stack:
        first = await stack.enter_async_context(bd.WorkDispatcher(redis, prefix, worker_id="a"))
        targets = [f"project:volume-{index}" for index in range(6)]
        assert await first.publish(targets)
        await stack.enter_async_context(bd.WorkDispatcher(redis, prefix, worker_id="b"))
        await stack.enter_async_context(bd.WorkDispatcher(redis, prefix, worker_id="c"))
        assert await first.publish(targets[1:])
        assert await redis.hgetall(first._assignments_key) == {member: "a" for member in targets[1:]}


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["assignment", "membership", "token", "redis"])
async def test_owned_checkpoint_denies_new_sdk_work_after_revocation(coordination, revocation):
    redis, prefix = coordination
    boundary = RedisFault(redis)
    calls = []
    async with bd.WorkDispatcher(boundary, prefix, worker_id="owner") as worker:
        assert await worker.publish(["target"])
        member, token = await worker.claim(90)
        async with bd.work_lease(worker, member, token) as lease:
            assert await bd.run_sync(lambda: calls.append("before")) is None
            if revocation == "assignment":
                await redis.hset(worker._assignments_key, member, "successor")
            elif revocation == "membership":
                await expire_member(redis, worker)
            elif revocation == "token":
                await redis.set(lease.key, "successor-token", ex=90)
            else:
                boundary.unavailable = True
            with pytest.raises(bd.DispatcherUnavailable):
                await bd.run_sync(lambda: calls.append("forbidden"))
            assert lease.revoked.is_set()
            boundary.unavailable = False
            # Restoring Redis/assignment cannot restore this task's authority.
            await redis.hset(worker._assignments_key, member, worker.worker_id)
            with pytest.raises(bd.DispatcherUnavailable):
                await bd.checkpoint()
        assert calls == ["before"]
        if revocation == "token":
            assert await redis.get(lease.key) == "successor-token"
        else:
            assert not await redis.exists(lease.key)
    # An unrelated request is not bound to the old background task's fence.
    await bd.checkpoint()


@pytest.mark.asyncio
async def test_claim_cannot_be_adopted_twice_or_renew_replacement_token(coordination):
    redis, prefix = coordination
    async with bd.WorkDispatcher(redis, prefix) as worker:
        assert await worker.publish(["target"])
        member, token = await worker.claim(90)
        async with bd.work_lease(worker, member, token) as lease:
            with pytest.raises(bd.DispatcherUnavailable):
                async with bd.work_lease(worker, member, token):
                    pytest.fail("same claim executed twice")
            await redis.set(lease.key, "other-owner", ex=7)
            await lease._renew_once()
            assert lease.revoked.is_set()
            assert await redis.get(lease.key) == "other-owner"
            assert 0 < await redis.ttl(lease.key) <= 7
        assert await redis.get(lease.key) == "other-owner"


@pytest.mark.asyncio
async def test_cancelled_factory_drains_actual_thread_and_closes_before_lease_release(coordination):
    redis, prefix = coordination
    entered = asyncio.Event()
    release = threading.Event()
    closed = threading.Event()
    loop = asyncio.get_running_loop()

    class Connection:
        def close(self):
            closed.set()

    def factory():
        loop.call_soon_threadsafe(entered.set)
        release.wait(5)
        return Connection()

    async with bd.WorkDispatcher(redis, prefix) as worker:
        assert await worker.publish(["target"])
        member, token = await worker.claim(90)

        async def consumer():
            async with bd.work_lease(worker, member, token):
                await bd.open_connection(factory)
                pytest.fail("cancelled factory result transferred to consumer")

        task = asyncio.create_task(consumer())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()  # Repeated shutdown must not abandon the factory.
            await asyncio.sleep(0)
            assert not task.done()
            assert await redis.get(f"{prefix}:lease:{member}") == token
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
            assert closed.is_set()
            assert not await redis.exists(f"{prefix}:lease:{member}")
        finally:
            release.set()
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
@pytest.mark.parametrize("native", [False, True])
async def test_repeated_cancel_during_diagnostic_keeps_thread_connection_and_lease(coordination, monkeypatch, native):
    from app.services import experience_context

    redis, prefix = coordination
    entered = asyncio.Event()
    diagnostic_entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    sequence = []
    call_contexts = []
    parent_span = "00000000-0000-4000-8000-000000000001"

    def sdk_call():
        loop.call_soon_threadsafe(entered.set)
        release.wait(5)
        sequence.append("sdk-returned")

    async def diagnostic(_context, _type, *, stage, status, **_kwargs):
        sequence.append((stage, status))
        if stage != "cleanup":
            call_contexts.append(_context)
        if status == "cancel_requested":
            diagnostic_entered.set()
            await asyncio.sleep(0.02)

    monkeypatch.setattr(experience_context, "emit_experience", diagnostic)
    async with bd.WorkDispatcher(redis, prefix) as worker:
        assert await worker.publish(["target"])
        member, token = await worker.claim(90)

        async def consumer():
            async with bd.work_lease(worker, member, token):
                bd.bind_worker_experience({"actor": {}, "span_id": parent_span}, "operation")
                try:
                    await (bd.run_native if native else bd.run_sync)(sdk_call)
                finally:
                    sequence.append("connection-closed")

        task = asyncio.create_task(consumer())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            await asyncio.wait_for(diagnostic_entered.wait(), 2)
            task.cancel()
            await asyncio.sleep(0.03)
            assert not task.done()
            assert "connection-closed" not in sequence
            assert await redis.get(f"{prefix}:lease:{member}") == token
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
            stage = "native" if native else "blocking"
            assert sequence.index("sdk-returned") < sequence.index((stage + ".drain", "observed"))
            assert sequence.index((stage + ".drain", "observed")) < sequence.index("connection-closed")
            assert not await redis.exists(f"{prefix}:lease:{member}")
            assert len(call_contexts) == 3
            assert len({context["span_id"] for context in call_contexts}) == 1
            assert call_contexts[0]["span_id"] != parent_span
            assert all(context["parent_span_id"] == parent_span for context in call_contexts)
        finally:
            release.set()
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
async def test_delivery_binding_restores_role_or_job_context_after_error(coordination, monkeypatch):
    from app.services import experience_context

    redis, prefix = coordination
    observed = []

    async def diagnostic(context, _type, **fields):
        observed.append((context, fields.get("operation_id")))

    monkeypatch.setattr(experience_context, "emit_experience", diagnostic)
    original = {"source": "worker", "actor": {"user_id": "job-owner"}}
    async with bd.WorkDispatcher(redis, prefix) as worker:
        assert await worker.publish(["target"])
        member, token = await worker.claim(90)
        async with bd.work_lease(worker, member, token) as lease:
            bd.bind_worker_experience(original, "job")
            for actor in ("first-owner", "second-owner"):
                delivery = {"source": "worker", "actor": {"user_id": actor}}
                with pytest.raises(ValueError), bd.worker_experience_scope(delivery, actor):
                    await bd.run_sync(lambda: None)
                    assert lease.experience_context == delivery
                    raise ValueError("delivery stopped")
                assert lease.experience_context == original
                assert lease.experience_operation_id == "job"
        assert observed[-1] == (original, "job")


@pytest.mark.asyncio
async def test_cancel_during_failure_diagnostic_does_not_start_consumer_compensation(coordination, monkeypatch):
    from app.services import experience_context

    redis, prefix = coordination
    logging_failure = asyncio.Event()
    sequence = []

    def native():
        sequence.append("native-returned-error")
        raise ValueError("provider rejected")

    async def diagnostic(context, _type, *, stage, status, **fields):
        if status == "outcome_unknown":
            logging_failure.set()
            await asyncio.sleep(0.02)
        sequence.append((stage, status))

    monkeypatch.setattr(experience_context, "emit_experience", diagnostic)
    async with bd.WorkDispatcher(redis, prefix) as worker:
        assert await worker.publish(["target"])
        member, token = await worker.claim(90)

        async def consumer():
            async with bd.work_lease(worker, member, token):
                bd.bind_worker_experience({"actor": {}}, "operation")
                try:
                    await bd.run_native(native)
                except Exception:
                    sequence.append("consumer-compensation")

        task = asyncio.create_task(consumer())
        await asyncio.wait_for(logging_failure.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert "consumer-compensation" not in sequence
        assert ("native", "cancel_requested") in sequence
        assert ("native.drain", "observed") in sequence
        assert not await redis.exists(f"{prefix}:lease:{member}")


@pytest.mark.asyncio
@pytest.mark.parametrize("logging_phase", ["start", "return"])
@pytest.mark.parametrize("leased", [False, True])
async def test_cancelled_diagnostic_delivers_already_completed_native_result_before_cancellation(
    coordination, monkeypatch, logging_phase, leased
):
    from app.services import experience_context

    redis, prefix = coordination
    native_returned = threading.Event()
    logging_entered = asyncio.Event()
    tracked_ids = []
    statuses = []
    second_commands = []
    closed = []
    after_close = []

    class Connection:
        def close(self):
            closed.append(True)

    def second_native():
        second_commands.append(True)

    def native():
        native_returned.set()
        return "actual-native-id"

    async def diagnostic(context, _type, *, stage, status, **fields):
        statuses.append((stage, status))
        target = "running" if logging_phase == "start" else "observed"
        if stage == "native" and status == target:
            assert await asyncio.to_thread(native_returned.wait, 2)
            # Let the completed thread's Future callbacks reach its owned task.
            await asyncio.sleep(0.02)
            logging_entered.set()
            await asyncio.sleep(0.02)

    monkeypatch.setattr(experience_context, "emit_experience", diagnostic)
    async with bd.WorkDispatcher(redis, prefix) as worker:
        assert await worker.publish(["target"])
        member, token = await worker.claim(90)

        async def consumer():
            async with AsyncExitStack() as stack:
                if leased:
                    await stack.enter_async_context(bd.work_lease(worker, member, token))
                    bd.bind_worker_experience({"actor": {}}, "operation")
                try:
                    resource_id = await bd.run_native(native, experience={"actor": {}})
                    tracked_ids.append(resource_id)
                    await bd.run_native(second_native, experience={"actor": {}})
                finally:
                    await bd.close_connection(Connection())
                    after_close.append(True)

        task = asyncio.create_task(consumer())
        await asyncio.wait_for(logging_entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert tracked_ids == ["actual-native-id"]
        assert second_commands == []
        assert closed == [True]
        assert after_close == [True]
        assert ("native", "observed") in statuses
        assert ("native", "cancel_requested") not in statuses
        assert ("native.drain", "observed") not in statuses
        if leased:
            assert not await redis.exists(f"{prefix}:lease:{member}")


@pytest.mark.asyncio
async def test_consumed_deferred_cancellation_does_not_fence_later_request_work(monkeypatch):
    from app.services import experience_context

    logging_entered = asyncio.Event()
    seen = []

    async def diagnostic(context, _type, *, stage, status, **fields):
        if stage == "native" and status == "observed" and not logging_entered.is_set():
            logging_entered.set()
            await asyncio.sleep(0.02)

    monkeypatch.setattr(experience_context, "emit_experience", diagnostic)

    async def consumer():
        seen.append(await bd.run_native(lambda: "first", experience={"actor": {}}))
        with suppress(asyncio.CancelledError):
            await asyncio.sleep(0)
        seen.append(await bd.run_native(lambda: "later", experience={"actor": {}}))

    task = asyncio.create_task(consumer())
    await asyncio.wait_for(logging_entered.wait(), 2)
    task.cancel()
    await asyncio.wait_for(task, 2)
    assert seen == ["first", "later"]
    assert task.cancelling() > 0  # An old count is not a pending cancellation.


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["asyncio_timeout", "anyio_cancel_scope"])
async def test_scoped_owner_cancelled_during_completion_diagnostic_never_starts_next_native_call(monkeypatch, owner):
    """진단 shield에 가려진 소유 scope 취소도 반환된 ID는 기록하고 다음 SDK 호출은 시작하지 않는다."""
    import anyio

    from app.services import experience_context

    cancel_owner = []
    fired = []
    tracked_ids = []
    second_commands = []
    closed = []

    class Connection:
        def close(self):
            closed.append(True)

    async def diagnostic(context, _type, *, stage, status, **fields):
        if stage == "native" and status == "observed" and not fired:
            fired.append(True)
            cancel_owner[0]()
            await asyncio.sleep(0.05)

    monkeypatch.setattr(experience_context, "emit_experience", diagnostic)

    async def owned_calls():
        try:
            tracked_ids.append(await bd.run_native(lambda: "actual-native-id", experience={"actor": {}}))
            await bd.run_native(lambda: second_commands.append(True), experience={"actor": {}})
        finally:
            await bd.close_connection(Connection())

    async def consumer():
        if owner == "asyncio_timeout":
            async with asyncio.timeout(None) as scope:
                cancel_owner.append(lambda: scope.reschedule(asyncio.get_running_loop().time()))
                await owned_calls()
        else:
            with anyio.CancelScope() as scope:
                cancel_owner.append(scope.cancel)
                await owned_calls()

    task = asyncio.create_task(consumer())
    _, pending = await asyncio.wait({task}, timeout=3)
    assert not pending
    assert tracked_ids == ["actual-native-id"]
    assert second_commands == []
    assert closed == [True]


@pytest.mark.asyncio
async def test_role_runner_late_three_members_distribute_then_recover_graceful_departure(coordination, monkeypatch):
    redis, prefix = coordination
    monkeypatch.setattr(bd, "HEARTBEAT_SECONDS", 0.01)
    active = {}
    duplicate = []
    tasks = []
    names = tuple("abcdef")

    def factories(worker):
        def factory(role):
            async def run():
                if role in active:
                    duplicate.append((role, active[role], worker))
                active[role] = worker
                try:
                    await asyncio.Event().wait()
                finally:
                    active.pop(role, None)

            return run

        return {role: factory(role) for role in names}

    async def one_member():
        return active == dict.fromkeys(names, "a")

    async def three_members():
        return len(active) == 6 and [list(active.values()).count(worker) for worker in "abc"] == [2, 2, 2]

    async def two_members():
        return len(active) == 6 and [list(active.values()).count(worker) for worker in "bc"] == [3, 3]

    try:
        tasks.append(
            asyncio.create_task(
                bd.run_roles(factories("a"), prefix=prefix, redis=redis, worker_id="a", poll_seconds=0.01)
            )
        )
        await eventually(one_member)
        for worker in "bc":
            tasks.append(
                asyncio.create_task(
                    bd.run_roles(factories(worker), prefix=prefix, redis=redis, worker_id=worker, poll_seconds=0.01)
                )
            )
        await eventually(three_members)
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
        await eventually(two_members)
        assert not duplicate
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert active == {}
    assert not await redis.exists(f"{prefix}:dispatch:members") or await redis.zcard(f"{prefix}:dispatch:members") == 0


@pytest.mark.asyncio
async def test_role_reassignment_waits_for_blocked_sdk_drain_without_duplicate_child(coordination, monkeypatch):
    redis, prefix = coordination
    monkeypatch.setattr(bd, "HEARTBEAT_SECONDS", 0.01)
    entered = asyncio.Event()
    successor = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    sequence = []

    def blocked_sdk():
        loop.call_soon_threadsafe(entered.set)
        release.wait(5)
        sequence.append("sdk-returned")

    async def idle():
        await asyncio.Event().wait()

    async def old_role():
        await bd.run_sync(blocked_sdk)
        sequence.append("forbidden-continuation")

    async def new_role():
        sequence.append("successor-started")
        successor.set()
        await asyncio.Event().wait()

    first = asyncio.create_task(
        bd.run_roles({"a": idle, "b": old_role}, prefix=prefix, redis=redis, worker_id="a", poll_seconds=0.01)
    )
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        second = asyncio.create_task(
            bd.run_roles({"a": idle, "b": new_role}, prefix=prefix, redis=redis, worker_id="b", poll_seconds=0.01)
        )

        async def reassigned():
            return await redis.hget(f"{prefix}:dispatch:assignments", "b") == "b"

        await eventually(reassigned)
        # Both controllers have observed the handoff, but the old SDK owns its
        # renewable lease until the real thread returns.
        await asyncio.sleep(0.05)
        assert not successor.is_set()
        assert await redis.get(f"{prefix}:lease:b")
        first.cancel()  # Cancellation during revocation drain must be retained.
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(first, 2)
        await asyncio.wait_for(successor.wait(), 2)
        assert sequence == ["sdk-returned", "successor-started"]
    finally:
        release.set()
        for task in (first, second):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (first, second) if task is not None), return_exceptions=True)


@pytest.mark.asyncio
async def test_delayed_lease_check_reply_cannot_revive_revoked_task(coordination):
    redis, prefix = coordination
    checked = asyncio.Event()
    reply = asyncio.Event()
    delay = False

    class DelayedCheck(RedisFault):
        async def eval(self, *args):
            result = await super().eval(*args)
            if args[0] == bd._LEASE_CHECK and delay:
                checked.set()
                await reply.wait()
            return result

    async with bd.WorkDispatcher(DelayedCheck(redis), prefix) as worker:
        assert await worker.publish(["target"])
        member, token = await worker.claim(90)
        async with bd.work_lease(worker, member, token) as lease:
            delay = True
            checking = asyncio.create_task(lease.check())
            try:
                await asyncio.wait_for(checked.wait(), 2)
                await redis.hset(worker._assignments_key, member, "successor")
                await lease._renew_once()
                assert lease.revoked.is_set()
                reply.set()
                with pytest.raises(bd.DispatcherUnavailable):
                    await checking
            finally:
                reply.set()
                checking.cancel()
                with suppress(asyncio.CancelledError, bd.DispatcherUnavailable):
                    await checking


@pytest.mark.asyncio
async def test_delayed_renewal_reply_past_local_deadline_fails_closed(coordination, monkeypatch):
    redis, prefix = coordination
    renewing = asyncio.Event()
    reply = asyncio.Event()
    delay = False
    clock = {"now": bd.time.monotonic()}

    class DelayedRenewal(RedisFault):
        async def eval(self, *args):
            result = await super().eval(*args)
            if args[0] == bd._LEASE_RENEW and delay:
                renewing.set()
                await reply.wait()
            return result

    async with bd.WorkDispatcher(DelayedRenewal(redis), prefix) as worker:
        assert await worker.publish(["target"])
        member, token = await worker.claim(90)
        async with bd.work_lease(worker, member, token) as lease:
            # Patch only this module's clock, not global time.monotonic used by
            # event-loop timeouts and Redis fixture liveness.
            class Clock:
                @staticmethod
                def monotonic():
                    return clock["now"]

            monkeypatch.setattr(bd, "time", Clock)
            delay = True
            renewal = asyncio.create_task(lease._renew_once())
            try:
                await asyncio.wait_for(renewing.wait(), 2)
                clock["now"] += 100
                with pytest.raises(bd.DispatcherUnavailable):
                    bd.checkpoint_sync()
                reply.set()
                await renewal
                with pytest.raises(bd.DispatcherUnavailable):
                    await lease.check()
            finally:
                reply.set()
                await renewal


@pytest.mark.asyncio
async def test_role_runner_redis_loss_drains_before_rejoin_and_starts_no_work_while_unavailable(
    coordination, monkeypatch
):
    redis, prefix = coordination
    monkeypatch.setattr(bd, "HEARTBEAT_SECONDS", 0.01)
    boundary = RedisFault(redis)
    started = asyncio.Event()
    draining = asyncio.Event()
    release = asyncio.Event()
    generations = []

    async def role():
        generations.append("started")
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            draining.set()
            await release.wait()
            generations.append("drained")

    runner = asyncio.create_task(
        bd.run_roles({"role": role}, prefix=prefix, redis=boundary, worker_id="owner", poll_seconds=0.01)
    )
    try:
        await asyncio.wait_for(started.wait(), 2)
        old_incarnation = await redis.hget(f"{prefix}:dispatch:incarnations", "owner")
        boundary.unavailable = True
        await asyncio.wait_for(draining.wait(), 2)
        await asyncio.sleep(0.05)
        assert generations == ["started"]
        assert await redis.hget(f"{prefix}:dispatch:incarnations", "owner") == old_incarnation
        boundary.unavailable = False
        started.clear()
        release.set()
        await asyncio.wait_for(started.wait(), 2)
        assert generations == ["started", "drained", "started"]
        assert await redis.hget(f"{prefix}:dispatch:incarnations", "owner") != old_incarnation
    finally:
        release.set()
        runner.cancel()
        with suppress(asyncio.CancelledError):
            await runner


@pytest.mark.asyncio
async def test_cancelled_compound_sdk_checkpoint_stops_later_mutation_and_unfenced_close_still_runs(coordination):
    redis, prefix = coordination
    entered = asyncio.Event()
    release = threading.Event()
    closed = threading.Event()
    calls = []
    loop = asyncio.get_running_loop()

    class Connection:
        def close(self):
            closed.set()

    def sdk():
        loop.call_soon_threadsafe(entered.set)
        release.wait(5)
        bd.checkpoint_sync()
        calls.append("forbidden-later-mutation")

    async with bd.WorkDispatcher(redis, prefix) as worker:
        assert await worker.publish(["target"])
        member, token = await worker.claim(90)

        async def consumer():
            async with bd.work_lease(worker, member, token):
                conn = await bd.open_connection(Connection)
                try:
                    await bd.run_sync(sdk)
                finally:
                    await bd.close_connection(conn)

        task = asyncio.create_task(consumer())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            await asyncio.sleep(0)
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
            assert calls == []
            assert closed.is_set()
            assert not await redis.exists(f"{prefix}:lease:{member}")
        finally:
            release.set()
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
async def test_leader_crash_does_not_revoke_healthy_executor_before_successor_scan(coordination, monkeypatch):
    redis, prefix = coordination
    monkeypatch.setattr(bd, "MEMBER_SECONDS", 2)
    monkeypatch.setattr(bd, "LEADER_SECONDS", 2)
    monkeypatch.setattr(bd, "HEARTBEAT_SECONDS", 0.2)
    leader = bd.WorkDispatcher(redis, prefix, worker_id="worker-a")
    executor = bd.WorkDispatcher(redis, prefix, worker_id="worker-b")
    await leader.__aenter__()
    await executor.__aenter__()
    try:
        assert await leader.publish(["project:volume-1", "project:volume-2"])
        member, owner = await executor.claim(90)
        async with bd.work_lease(executor, member, owner) as lease:
            # The leader process dies without leaving: no more heartbeats or scans.
            leader._heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await leader._heartbeat_task
            await asyncio.sleep(3)
            # Its membership has expired, but no successor has scanned yet.
            assert await redis.zscore(executor._members_key, "worker-a") is None
            await lease.check()
            assert await executor.is_leader()
            assert await executor.publish([member])
            await lease.check()
            assert not lease.revoked.is_set()
    finally:
        await executor.__aexit__(None, None, None)
        await leader.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_experience_lease_cleanup_waits_for_cancelled_native_drain(coordination, monkeypatch):
    from app.services import experience_context

    redis, prefix = coordination
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    sequence = []

    async def emit(context, event_type, **fields):
        assert context == {"source": "worker", "actor": {"user_id": "owner", "project_id": "project"}}
        assert fields["stage"] == "cleanup"
        assert fields["status"] == "observed"
        assert fields["operation_id"] == "actual-build-id"
        sequence.append("lease-cleanup")

    monkeypatch.setattr(experience_context, "emit_experience", emit)

    def native():
        loop.call_soon_threadsafe(entered.set)
        release.wait(5)
        sequence.append("native-settled")

    async with bd.WorkDispatcher(redis, prefix, worker_id="experience-owner") as worker:
        await worker.publish(["actual-build"])
        member, token = await worker.claim(90)

        async def consume():
            async with bd.work_lease(worker, member, token):
                bd.bind_worker_experience(
                    {"source": "worker", "actor": {"user_id": "owner", "project_id": "project"}}, "actual-build-id"
                )
                await bd.run_sync(native)

        task = asyncio.create_task(consume())
        try:
            await entered.wait()
            task.cancel()
            await asyncio.sleep(0)
            assert "lease-cleanup" not in sequence
            assert await redis.get(f"{prefix}:lease:{member}") == token
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert sequence == ["native-settled", "lease-cleanup"]
        finally:
            release.set()
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task
