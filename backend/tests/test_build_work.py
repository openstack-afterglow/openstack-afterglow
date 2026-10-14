"""Build consumers exercise real Redis claims, journals and SDK drain boundaries."""

import asyncio
import secrets
import threading
from contextlib import AsyncExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import build_work, work_dispatcher


@pytest.fixture
async def owned_store(_fake_redis_global, monkeypatch):
    from app.services.cache import _get_redis

    redis = await _get_redis()
    prefix = f"afterglow:test:builds:{secrets.token_hex(12)}"
    member = f"library:{secrets.randbelow(10**12)}"
    row = SimpleNamespace(status="queued")
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.get = AsyncMock(side_effect=lambda *_: row)
    monkeypatch.setattr("app.database.get_session_factory", lambda: MagicMock(return_value=session))
    monkeypatch.setattr(work_dispatcher, "HEARTBEAT_SECONDS", 3600)
    try:
        yield redis, prefix, member, row
    finally:
        keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
        keys += [key async for key in redis.scan_iter(match=f"afterglow:builds:journal:{member}*")]
        if keys:
            await redis.delete(*keys)


@pytest.mark.asyncio
async def test_process_loss_preserves_queued_identity_and_accepted_create_is_not_replayed(owned_store):
    redis, prefix, member, row = owned_store
    creates = []

    def create():
        creates.append("server")
        return SimpleNamespace(id="server-on-provider")

    async with work_dispatcher.WorkDispatcher(redis, prefix, worker_id="first") as first:
        await first.publish([member])
        claimed, owner = await first.claim(90)
        async with work_dispatcher.work_lease(first, claimed, owner) as lease:
            async with build_work.bind(redis, member, lease):
                await build_work.submit("server", create)
    # A fresh worker discovers the same SQL row. Neither a queued status nor
    # process-local task loss authorizes another CREATE.
    async with work_dispatcher.WorkDispatcher(redis, prefix, worker_id="replacement") as replacement:
        await replacement.publish([member])
        claimed, owner = await replacement.claim(90)
        async with work_dispatcher.work_lease(replacement, claimed, owner) as lease:
            async with build_work.bind(redis, member, lease):
                journal = await build_work.submission_get("server")
                assert journal == {"state": "accepted", "result": {"id": "server-on-provider"}}
                with pytest.raises(build_work.SubmissionUnknown):
                    await build_work.submit("server", create)
    assert creates == ["server"] and row.status == "queued"


@pytest.mark.asyncio
async def test_healthy_owner_not_reconciled_or_claimed_by_peer(owned_store):
    redis, prefix, member, row = owned_store
    async with AsyncExitStack() as stack:
        workers = [
            await stack.enter_async_context(work_dispatcher.WorkDispatcher(redis, prefix, worker_id=name))
            for name in ("a", "b")
        ]
        await workers[0].publish([member])
        claims = [await worker.claim(90) for worker in workers]
        index = next(index for index, claim in enumerate(claims) if claim)
        claimed, owner = claims[index]
        async with work_dispatcher.work_lease(workers[index], claimed, owner) as lease:
            async with build_work.bind(redis, member, lease):
                await build_work.journal_update(token="durable-token")
                await workers[0].publish([member])
                assert await workers[1 - index].claim(90) is None
                await build_work.checkpoint()
                assert (await build_work.journal_get())["token"] == "durable-token"
    assert row.status == "queued"


@pytest.mark.asyncio
async def test_unknown_create_never_reissued(owned_store):
    redis, prefix, member, _ = owned_store
    creates = []

    def create():
        creates.append("accepted-response-lost")
        raise TimeoutError("response lost after provider accepted")

    async with work_dispatcher.WorkDispatcher(redis, prefix) as worker:
        await worker.publish([member])
        claimed, owner = await worker.claim(90)
        async with work_dispatcher.work_lease(worker, claimed, owner) as lease:
            async with build_work.bind(redis, member, lease):
                with pytest.raises(build_work.SubmissionUnknown):
                    await build_work.submit("server", create)
                with pytest.raises(build_work.SubmissionUnknown):
                    await build_work.submit("server", create)
                assert (await build_work.submission_get("server"))["state"] == "unknown"
    assert creates == ["accepted-response-lost"]


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_after_cancel", [False, True])
async def test_cancelled_sdk_submission_drains_records_result_and_closes(owned_store, fail_after_cancel):
    redis, prefix, member, _ = owned_store
    started, release, closed = threading.Event(), threading.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    started_async = asyncio.Event()

    def create():
        started.set()
        loop.call_soon_threadsafe(started_async.set)
        release.wait()
        if fail_after_cancel:
            raise TimeoutError("late SDK failure after cancellation")
        return SimpleNamespace(id="late-server")

    async with work_dispatcher.WorkDispatcher(redis, prefix) as worker:
        await worker.publish([member])
        claimed, owner = await worker.claim(90)
        async with work_dispatcher.work_lease(worker, claimed, owner) as lease:
            async with build_work.bind(redis, member, lease):

                async def operation():
                    try:
                        await build_work.submit("server", create)
                    finally:
                        await build_work.cleanup_sync(closed.set)

                task = asyncio.create_task(operation())
                try:
                    await asyncio.wait_for(started_async.wait(), 2)
                    task.cancel()
                    await asyncio.sleep(0)
                    assert not task.done() and not closed.is_set()
                    assert await redis.get(f"{prefix}:lease:{member}") == owner
                    release.set()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    assert closed.is_set()
                    submission = await build_work.submission_get("server")
                    if fail_after_cancel:
                        assert submission["state"] == "unknown"
                    else:
                        assert submission["result"]["id"] == "late-server"
                finally:
                    release.set()
                    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_sql_cancel_or_lost_assignment_prevents_subsequent_mutation(owned_store):
    redis, prefix, member, row = owned_store
    mutations = []
    async with work_dispatcher.WorkDispatcher(redis, prefix) as worker:
        await worker.publish([member])
        claimed, owner = await worker.claim(90)
        async with work_dispatcher.work_lease(worker, claimed, owner) as lease:
            async with build_work.bind(redis, member, lease):
                row.status = "cancelled"
                with pytest.raises(work_dispatcher.DispatcherUnavailable):
                    await build_work.submit("server", lambda: mutations.append("create"))
                row.status = "queued"
                await redis.hdel(worker._assignments_key, member)
                with pytest.raises(work_dispatcher.DispatcherUnavailable):
                    await build_work.run_sync(lambda: mutations.append("later mutation"))
    assert mutations == []


@pytest.mark.asyncio
async def test_assigned_worker_consumes_sql_identity_without_api_process_state(owned_store, monkeypatch):
    from app.services import ephemeral_build, library_builder

    redis, prefix, member, row = owned_store
    row.library_id = "python311"
    row.file_storage_id = "admitted-share"
    row.resource_snapshot = {"recipe": {"commands": [{"script": "frozen"}]}}
    received = []

    async def execute(build_db_id):
        await build_work.checkpoint()
        received.append((row.library_id, build_db_id, row.file_storage_id, row.resource_snapshot))
        await build_work.submit("server", lambda: SimpleNamespace(id="consumed-server"))
        row.status = "complete"

    monkeypatch.setattr(ephemeral_build, "run_ephemeral_build", execute)
    async with work_dispatcher.WorkDispatcher(redis, prefix, worker_id="assigned-worker") as worker:
        await worker.publish([member])
        claimed, owner = await worker.claim(90)
        await library_builder._execute_work(worker, claimed, owner)
        assert await redis.get(f"{prefix}:lease:{member}") is None
    assert received == [("python311", int(member.split(":")[1]), "admitted-share", row.resource_snapshot)]
    assert row.status == "complete"


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_sql", [False, True])
async def test_caller_or_sql_cancellation_cannot_start_create_after_executor_queue_delay(
    owned_store, monkeypatch, cancel_sql
):
    redis, prefix, member, row = owned_store
    queued, release = asyncio.Event(), asyncio.Event()
    original_to_thread = asyncio.to_thread
    creates = []

    async def delayed_thread(fn, *args, **kwargs):
        queued.set()
        await release.wait()
        return await original_to_thread(fn, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", delayed_thread)
    async with work_dispatcher.WorkDispatcher(redis, prefix) as worker:
        await worker.publish([member])
        claimed, owner = await worker.claim(90)
        async with work_dispatcher.work_lease(worker, claimed, owner) as lease:
            async with build_work.bind(redis, member, lease):
                task = asyncio.create_task(build_work.submit("server", lambda: creates.append("create")))
                try:
                    await asyncio.wait_for(queued.wait(), 2)
                    if cancel_sql:
                        row.status = "cancelled"
                    else:
                        task.cancel()
                    await asyncio.sleep(0)
                    release.set()
                    error = work_dispatcher.DispatcherUnavailable if cancel_sql else asyncio.CancelledError
                    with pytest.raises(error):
                        await task
                    assert (await build_work.submission_get("server"))["state"] == "unknown"
                finally:
                    release.set()
                    await asyncio.gather(task, return_exceptions=True)
    assert creates == []


@pytest.mark.asyncio
async def test_definitive_create_rejection_is_durable_and_never_replayed(owned_store):
    import httpx

    redis, prefix, member, _ = owned_store
    request = httpx.Request("POST", "https://synthetic.invalid/create")
    rejection = httpx.HTTPStatusError("rejected", request=request, response=httpx.Response(400, request=request))
    attempts = []

    def create():
        attempts.append("create")
        raise rejection

    async with work_dispatcher.WorkDispatcher(redis, prefix) as worker:
        await worker.publish([member])
        claimed, owner = await worker.claim(90)
        async with work_dispatcher.work_lease(worker, claimed, owner) as lease:
            async with build_work.bind(redis, member, lease):
                with pytest.raises(httpx.HTTPStatusError) as captured:
                    await build_work.submit("server", create)
                assert captured.value is rejection
                assert await build_work.submission_get("server") == {"state": "rejected", "response_status": 400}
                with pytest.raises(build_work.SubmissionUnknown):
                    await build_work.submit("server", create)
    assert attempts == ["create"]
