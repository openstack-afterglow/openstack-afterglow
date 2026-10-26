"""Consumer behavior: current policy, target partition, output fencing and drain."""

import asyncio
import secrets
import select
import signal
import subprocess
import sys
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from app import notion_worker as nw
from app.services import notion_sync as ns
from app.services import work_dispatcher as wd


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr("app.services.resource_policy_store.get_runtime_setting", AsyncMock(return_value=True))


@pytest.fixture
async def coordination(_fake_redis_global, monkeypatch):
    from app.services.cache import _get_redis

    redis = await _get_redis()
    prefix = f"afterglow:test:notion:{secrets.token_hex(12)}"
    monkeypatch.setattr(nw, "_PREFIX", prefix)
    try:
        yield redis, prefix
    finally:
        keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
        if keys:
            await redis.delete(*keys)


def target(index=1, **values):
    return {
        "id": index,
        "api_key": "key",
        "database_id": f"output-{index}",
        "enabled": True,
        "interval_minutes": 30,
        "last_sync": None,
        **values,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values,expected",
    [
        ({"enabled": False}, []),
        ({"last_sync": (datetime.now(UTC) - timedelta(minutes=5)).isoformat()}, []),
        ({"last_sync": (datetime.now(UTC) - timedelta(minutes=45)).isoformat()}, ["1"]),
        ({"last_sync": (datetime.now(UTC) - timedelta(minutes=6)).isoformat(), "interval_minutes": 5}, ["1"]),
        ({}, ["1"]),
    ],
)
async def test_consumer_interval_and_enable_guard(monkeypatch, values, expected):
    monkeypatch.setattr(ns, "list_notion_targets", AsyncMock(return_value=[target(**values)]))
    assert await nw._discover_targets() == expected


@pytest.mark.asyncio
async def test_global_gate_prevents_registry_and_claimed_target_reads(monkeypatch):
    monkeypatch.setattr("app.services.resource_policy_store.get_runtime_setting", AsyncMock(return_value=False))
    listing = AsyncMock()
    lookup = AsyncMock()
    monkeypatch.setattr(ns, "list_notion_targets", listing)
    monkeypatch.setattr(ns, "get_notion_target", lookup)
    assert await nw._discover_targets() == []
    assert await nw._current_target("1") is None
    listing.assert_not_awaited()
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_fallback_only_without_registered_targets(monkeypatch):
    legacy = target()
    legacy.pop("id")
    monkeypatch.setattr(ns, "list_notion_targets", AsyncMock(return_value=[]))
    config = AsyncMock(return_value=legacy)
    monkeypatch.setattr(ns, "get_notion_config", config)
    assert await nw._discover_targets() == ["legacy"]
    legacy["last_sync"] = datetime.now(UTC).isoformat()
    assert await nw._discover_targets() == []
    monkeypatch.setattr(ns, "list_notion_targets", AsyncMock(return_value=[target(enabled=False)]))
    config.reset_mock()
    assert await nw._discover_targets() == []
    config.assert_not_awaited()


async def join_three(stack, redis, prefix):
    return [
        await stack.enter_async_context(wd.WorkDispatcher(redis, prefix, worker_id=f"worker-{i}")) for i in range(3)
    ]


@pytest.mark.asyncio
async def test_three_workers_execute_disjoint_targets_without_worker_registry_scans(coordination, monkeypatch):
    from contextvars import ContextVar

    redis, prefix = coordination
    targets = {str(i): target(i) for i in range(1, 10)}
    scanner_calls = []
    executor = ContextVar("test_notion_executor")
    observed = {}
    complete = asyncio.Event()

    async def listing():
        scanner_calls.append(asyncio.current_task().get_name())
        return [dict(config) for config in targets.values()]

    monkeypatch.setattr(ns, "list_notion_targets", listing)
    monkeypatch.setattr(ns, "get_notion_target", AsyncMock(side_effect=lambda index, **_: dict(targets[str(index)])))
    monkeypatch.setattr(nw, "_CHECK_INTERVAL", 0.01)
    monkeypatch.setattr(nw, "_POLL_INTERVAL", 0.001)

    async def sync(config):
        await ns.worker_checkpoint()
        observed.setdefault(executor.get(), []).append(config["id"])
        targets[str(config["id"])]["last_sync"] = datetime.now(UTC).isoformat()
        if sum(len(batch) for batch in observed.values()) == 9:
            complete.set()

    async def execute(worker):
        token = executor.set(worker.worker_id)
        try:
            await nw._execute(worker)
        finally:
            executor.reset(token)

    monkeypatch.setattr(nw, "_run_notion_target_sync", sync)
    async with AsyncExitStack() as stack:
        workers = await join_three(stack, redis, prefix)
        tasks = [asyncio.create_task(nw._scan(worker), name=f"scan:{worker.worker_id}") for worker in workers]
        tasks.extend(asyncio.create_task(execute(worker)) for worker in workers)
        try:
            await asyncio.wait_for(complete.wait(), 3)
        finally:
            await nw._drain(tasks)
    assert sorted(index for batch in observed.values() for index in batch) == list(range(1, 10))
    assert sorted(len(batch) for batch in observed.values()) == [3, 3, 3]
    assert scanner_calls and set(scanner_calls) == {"scan:worker-0"}


@pytest.mark.asyncio
async def test_expired_target_owner_cannot_execute_and_successor_waits_for_lease(coordination, monkeypatch):
    redis, prefix = coordination
    targets = {str(i): target(i) for i in range(1, 4)}
    monkeypatch.setattr(ns, "list_notion_targets", AsyncMock(side_effect=lambda: list(targets.values())))
    monkeypatch.setattr(ns, "get_notion_target", AsyncMock(side_effect=lambda index, **_: dict(targets[str(index)])))
    observed = []

    async def sync(config):
        await ns.worker_checkpoint()
        observed.append(config["id"])
        targets[str(config["id"])]["last_sync"] = datetime.now(UTC).isoformat()

    monkeypatch.setattr(nw, "_run_notion_target_sync", sync)
    async with AsyncExitStack() as stack:
        leader, absent, survivor = await join_three(stack, redis, prefix)
        await leader.publish(await nw._discover_targets())
        member, owner = await absent.claim(90)
        seconds, micros = await redis.time()
        await redis.zadd(absent._members_key, {absent.worker_id: int(seconds) + int(micros) / 1_000_000 - 1})
        await leader.publish(await nw._discover_targets())
        for worker in (leader, survivor):
            while await worker.pending():
                claim = await worker.claim(90)
                if claim:
                    await nw._execute_target(worker, *claim)
        assert int(member) not in observed
        assert await redis.get(f"{prefix}:lease:{member}") == owner
        await leader.publish(await nw._discover_targets())
        assert await leader.claim(90) is None
        assert await survivor.claim(90) is None
        # Simulate Redis TTL expiration without waiting ninety wall-clock seconds.
        await redis.expire(f"{prefix}:lease:{member}", 0)
        await leader.publish(await nw._discover_targets())
        recovered = [(worker, claim) for worker in (leader, survivor) if (claim := await worker.claim(90))]
        assert len(recovered) == 1
        worker, claim = recovered[0]
        assert claim[0] == member and claim[1] != owner
        with pytest.raises(wd.DispatcherUnavailable):
            await nw._execute_target(absent, member, owner)
        assert await redis.get(f"{prefix}:lease:{member}") == claim[1]
        await nw._execute_target(worker, *claim)
    assert sorted(observed) == [1, 2, 3]


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["enabled", "interval", "gate", "output"])
async def test_revoked_policy_after_await_prevents_native_http_mutation(coordination, monkeypatch, revocation):
    redis, prefix = coordination
    config = target()
    monkeypatch.setattr(ns, "get_notion_target", AsyncMock(return_value=config))
    sent = []

    async def transport(request):
        sent.append(request)
        return httpx.Response(200, json={})

    async def sync(_):
        if revocation == "enabled":
            config["enabled"] = False
        elif revocation == "interval":
            config["last_sync"] = datetime.now(UTC).isoformat()
        elif revocation == "gate":
            monkeypatch.setattr("app.services.resource_policy_store.get_runtime_setting", AsyncMock(return_value=False))
        else:
            config["database_id"] = "new-output"
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            await ns._notion_request(client, "POST", "https://notion.invalid/pages", "key", json={})

    monkeypatch.setattr(nw, "_run_notion_target_sync", sync)
    async with wd.WorkDispatcher(redis, prefix) as worker:
        await worker.publish(["1"])
        # Use a snapshot as the database service does; modifying current state
        # must not also rewrite the execution snapshot.
        monkeypatch.setattr(ns, "get_notion_target", AsyncMock(side_effect=lambda *_, **__: dict(config)))
        with pytest.raises(wd.DispatcherUnavailable):
            await nw._execute_target(worker, *await worker.claim(90))
    assert sent == []


@pytest.mark.asyncio
async def test_legacy_singleton_and_normalized_shared_outputs_are_exclusive(coordination, monkeypatch):
    redis, prefix = coordination
    uuid = "ABCDEF12-3456-7890-ABCD-EF1234567890"
    legacy = target(database_id=uuid)
    legacy.pop("id")
    modern = target(database_id=f"https://www.notion.so/{uuid.replace('-', '').lower()}?v=anything")
    monkeypatch.setattr(ns, "get_notion_config", AsyncMock(return_value=legacy))
    monkeypatch.setattr(ns, "get_notion_target", AsyncMock(return_value=modern))
    entered = asyncio.Event()
    release = asyncio.Event()
    seen = []

    async def sync(config):
        seen.append(config)
        entered.set()
        await release.wait()

    monkeypatch.setattr(nw, "_run_notion_target_sync", sync)
    async with AsyncExitStack() as stack:
        workers = await join_three(stack, redis, prefix)
        await workers[0].publish(["1", "legacy"])
        claims = [(worker, claim) for worker in workers if (claim := await worker.claim(90))]
        assert len(claims) == 2
        worker, claim = claims[0]
        first = asyncio.create_task(nw._execute_target(worker, *claim))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            other, other_claim = claims[1]
            await nw._execute_target(other, *other_claim)
            assert len(seen) == 1
            assert not any(await asyncio.gather(*(worker.claim(90) for worker in workers)))
        finally:
            release.set()
            await first


@pytest.mark.asyncio
async def test_slow_leader_execution_does_not_block_scan_or_heartbeat(coordination, monkeypatch):
    redis, prefix = coordination
    config = target()
    listing = AsyncMock(return_value=[config])
    monkeypatch.setattr(ns, "list_notion_targets", listing)
    monkeypatch.setattr(ns, "get_notion_target", AsyncMock(return_value=config))
    monkeypatch.setattr(nw, "_CHECK_INTERVAL", 0.01)
    monkeypatch.setattr(wd, "HEARTBEAT_SECONDS", 0.01)
    started = asyncio.Event()

    async def slow(_):
        started.set()
        await asyncio.Future()

    monkeypatch.setattr(nw, "_run_notion_target_sync", slow)
    async with wd.WorkDispatcher(redis, prefix) as worker:
        await worker.publish(["1"])
        before = await redis.zscore(worker._members_key, worker.worker_id)
        tasks = [asyncio.create_task(nw._execute(worker)), asyncio.create_task(nw._scan(worker))]
        try:
            await asyncio.wait_for(started.wait(), 2)
            for _ in range(100):
                if listing.await_count >= 2 and await redis.zscore(worker._members_key, worker.worker_id) > before:
                    break
                await asyncio.sleep(0.01)
            assert listing.await_count >= 2
            assert await redis.zscore(worker._members_key, worker.worker_id) > before
        finally:
            await nw._drain(tasks)
        assert not await redis.exists(f"{prefix}:lease:1")


@pytest.mark.asyncio
async def test_shutdown_cancels_scanner_during_dependency_timeout(monkeypatch):
    entered = asyncio.Event()
    resumed = asyncio.Event()

    class Dispatcher:
        async def is_leader(self):
            entered.set()
            try:
                # Redis socket readiness uses this same transient cancellation:
                # timeout owns one request and removes it when handling expiry.
                async with asyncio.timeout(0):
                    await asyncio.Future()
            except TimeoutError:
                pass
            resumed.set()
            return False

    monkeypatch.setattr(nw, "_CHECK_INTERVAL", 60)
    scanner = asyncio.create_task(nw._scan(Dispatcher()))
    await entered.wait()
    draining = asyncio.create_task(nw._drain([scanner]))
    try:
        done, _ = await asyncio.wait([draining], timeout=2)
        assert draining in done
        assert scanner.cancelled()
        assert not resumed.is_set()
    finally:
        scanner.cancel()
        await draining


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_before_cleanup", [True, False])
async def test_lease_cleanup_cancellation_exits_consumer_after_exact_release(
    coordination, monkeypatch, cancel_before_cleanup
):
    redis, prefix = coordination
    releasing = asyncio.Event()
    allow_release = asyncio.Event()
    continued = asyncio.Event()
    original_eval = redis.eval

    async def eval_with_blocked_release(script, *args):
        if script == wd._LEASE_RELEASE:
            releasing.set()
            await allow_release.wait()
        return await original_eval(script, *args)

    monkeypatch.setattr(redis, "eval", eval_with_blocked_release)
    async with wd.WorkDispatcher(redis, prefix) as worker:
        await worker.publish(["1"])
        member, owner = await worker.claim(90)

        async def consume():
            async with wd.work_lease(worker, member, owner):
                if cancel_before_cleanup:
                    # The request exists before _settle's first await, but the
                    # exception has not yet been delivered to this consumer.
                    asyncio.current_task().cancel()
            continued.set()

        execution = asyncio.create_task(consume())
        try:
            await asyncio.wait_for(releasing.wait(), 2)
            if not cancel_before_cleanup:
                execution.cancel()
            await asyncio.sleep(0)
            assert not execution.done()
            assert not continued.is_set()
            assert await redis.get(f"{prefix}:lease:1") == owner
            assert owner in worker._work_tokens
            allow_release.set()
            done, _ = await asyncio.wait([execution], timeout=2)
            assert execution in done
            with pytest.raises(asyncio.CancelledError):
                await execution
            assert not continued.is_set()
            assert not await redis.exists(f"{prefix}:lease:1")
            assert owner not in worker._work_tokens
        finally:
            allow_release.set()
            await nw._drain([execution])


@pytest.mark.asyncio
async def test_shutdown_drains_http_children_before_database_close(monkeypatch):
    import app.database as db
    import app.services.db_auto_backup as dab

    started = asyncio.Event()
    allow_drain = asyncio.Event()
    order = []

    async def child():
        started.set()
        try:
            await asyncio.Future()
        finally:
            await allow_drain.wait()
            order.append("http-drained")

    async def notion():
        await ns._drained_parallel([child()])

    async def trove(_):
        await asyncio.Future()

    async def close():
        order.append("db-closed")

    monkeypatch.setattr(db, "init_db", lambda *_, **__: None)
    monkeypatch.setattr(db, "is_db_available", lambda: True)
    monkeypatch.setattr(db, "close_db", close)
    monkeypatch.setattr(nw, "_run_target_worker", notion)
    monkeypatch.setattr(dab, "run_scheduler", trove)
    main = asyncio.create_task(nw.main())
    await asyncio.wait_for(started.wait(), 2)
    main.cancel()
    await asyncio.sleep(0)
    assert not main.done()
    assert order == []
    allow_drain.set()
    with pytest.raises(asyncio.CancelledError):
        await main
    assert order == ["http-drained", "db-closed"]


@pytest.mark.asyncio
async def test_cancellation_keeps_target_and_output_owned_until_http_drain(coordination, monkeypatch):
    redis, prefix = coordination
    monkeypatch.setattr(ns, "get_notion_target", AsyncMock(return_value=target()))
    started = asyncio.Event()
    draining = asyncio.Event()
    release = asyncio.Event()

    async def child():
        started.set()
        try:
            await asyncio.Future()
        finally:
            draining.set()
            await release.wait()

    async def sync(_):
        await ns._drained_parallel([child()])

    monkeypatch.setattr(nw, "_run_notion_target_sync", sync)
    async with wd.WorkDispatcher(redis, prefix) as worker:
        await worker.publish(["1"])
        claim = await worker.claim(90)
        execution = asyncio.create_task(nw._execute_target(worker, *claim))
        shutdown = None
        try:
            await asyncio.wait_for(started.wait(), 2)
            output_owner = await redis.get(f"{prefix}:output:output-1")
            assert output_owner is not None
            execution.cancel()
            await asyncio.wait_for(draining.wait(), 2)
            shutdown = asyncio.create_task(nw._drain([execution]))
            await asyncio.sleep(0)
            assert await redis.get(f"{prefix}:lease:1") == claim[1]
            assert await redis.get(f"{prefix}:output:output-1") == output_owner
            assert not execution.done()
            assert not shutdown.done()
        finally:
            release.set()
            if shutdown is not None:
                await shutdown
            else:
                await nw._drain([execution])
        assert not await redis.exists(f"{prefix}:lease:1", f"{prefix}:output:output-1")


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [target(enabled=False), target(last_sync=datetime.now(UTC).isoformat())])
async def test_claimed_legacy_rereads_current_enable_and_interval(coordination, monkeypatch, config):
    redis, prefix = coordination
    legacy = {key: value for key, value in config.items() if key != "id"}
    monkeypatch.setattr(ns, "get_notion_config", AsyncMock(return_value=legacy))
    sync = AsyncMock()
    monkeypatch.setattr(nw, "_run_notion_target_sync", sync)
    async with wd.WorkDispatcher(redis, prefix) as worker:
        await worker.publish(["legacy"])
        await nw._execute_target(worker, *await worker.claim(90))
    sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_native_inventory_thread_finishes_before_connection_and_lease_close(coordination, monkeypatch):
    import threading
    from types import SimpleNamespace

    from app.services import native_transport

    redis, prefix = coordination
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    order = []

    def servers(**_):
        loop.call_soon_threadsafe(started.set)
        if not release.wait(5):
            raise RuntimeError("inventory test release timed out")
        order.append("sdk-finished")
        return []

    conn = SimpleNamespace(
        compute=SimpleNamespace(servers=servers),
        identity=SimpleNamespace(projects=lambda: [], users=lambda: []),
        close=lambda: order.append("connection-closed"),
    )
    monkeypatch.setattr(native_transport, "connect", lambda **_: conn)
    monkeypatch.setattr("app.services.nova.list_catalog_flavors", lambda _: [])
    monkeypatch.setattr("app.database.is_db_available", lambda: False)
    monkeypatch.setattr(ns, "get_notion_target", AsyncMock(return_value=target()))
    mutate = AsyncMock(return_value={})
    monkeypatch.setattr(ns, "sync_to_notion", mutate)
    async with wd.WorkDispatcher(redis, prefix) as worker:
        await worker.publish(["1"])
        execution = asyncio.create_task(nw._execute_target(worker, *await worker.claim(90)))
        try:
            await asyncio.wait_for(started.wait(), 2)
            execution.cancel()
            await asyncio.sleep(0)
            assert not execution.done()
            assert order == []
            assert await redis.exists(f"{prefix}:lease:1")
        finally:
            release.set()
            await nw._drain([execution])
        assert order == ["sdk-finished", "connection-closed"]
        assert not await redis.exists(f"{prefix}:lease:1")
    mutate.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_sync_does_not_record_success(monkeypatch):
    monkeypatch.setattr("app.database.is_db_available", lambda: False)
    monkeypatch.setattr("app.services.openstack_inventory.collect_instance_data", AsyncMock(return_value=[]))
    monkeypatch.setattr(ns, "sync_to_notion", AsyncMock(return_value={"errors": 1}))
    update = AsyncMock()
    monkeypatch.setattr(ns, "update_notion_target", update)
    with pytest.raises(RuntimeError, match="partial"):
        await nw._run_notion_target_sync(target())
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_executor_refreshes_gpu_overlay_before_mapping(monkeypatch):
    order = []
    monkeypatch.setattr("app.database.is_db_available", lambda: True)
    monkeypatch.setattr(
        "app.services.gpu_catalog.refresh_device_map_from_db", AsyncMock(side_effect=lambda: order.append("refresh"))
    )
    monkeypatch.setattr("app.services.openstack_inventory.collect_instance_data", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "app.services.gpu_inventory.build_alias_to_device_name_map", lambda: order.append("mapping") or {}
    )
    monkeypatch.setattr(ns, "sync_to_notion", AsyncMock(return_value={}))
    monkeypatch.setattr(ns, "update_notion_target", AsyncMock())
    await nw._run_notion_target_sync(target())
    assert order == ["refresh", "mapping"]


_BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_worker_imports_are_fastapi_free():
    script = """
import sys
import app.notion_worker
import app.services.gpu_inventory
import app.services.openstack_inventory
import app.services.notion_sync
assert not any(m in sys.modules for m in ('fastapi', 'starlette', 'uvicorn'))
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=_BACKEND_DIR)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX worker shutdown signals")
@pytest.mark.parametrize("shutdown_signal", [signal.SIGTERM, signal.SIGINT])
def test_worker_shutdown_signals_cancel_pending_work_cleanly(shutdown_signal):
    script = """
import asyncio
from app import notion_worker
async def pending_work():
    print('READY', flush=True)
    try:
        await asyncio.Future()
    finally:
        print('CLEANED', flush=True)
notion_worker.main = pending_work
asyncio.run(notion_worker._main_async())
"""
    with subprocess.Popen(
        [sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=_BACKEND_DIR
    ) as process:
        try:
            assert select.select([process.stdout], [], [], 10)[0], "worker did not become ready"
            assert process.stdout.readline().strip() == "READY"
            process.send_signal(shutdown_signal)
            stdout, stderr = process.communicate(timeout=5)
            assert process.returncode == 0, stderr
            assert stdout.strip() == "CLEANED"
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_section", ["gpu", "hypervisor"])
async def test_optional_section_failure_preserves_instance_sync_without_false_section_timestamp(
    monkeypatch, failed_section
):
    monkeypatch.setattr("app.database.is_db_available", lambda: False)
    monkeypatch.setattr("app.services.gpu_inventory.get_gpu_spec_list", lambda: [])
    monkeypatch.setattr("app.services.openstack_inventory.collect_instance_data", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.openstack_inventory.collect_hypervisor_data", AsyncMock(return_value=[]))
    monkeypatch.setattr(ns, "build_gpu_usage_by_gpu", lambda *_: {})
    monkeypatch.setattr(
        ns, "sync_gpu_specs_to_notion", AsyncMock(return_value={"errors": int(failed_section == "gpu")})
    )
    monkeypatch.setattr(
        ns, "sync_hypervisors_to_notion", AsyncMock(return_value={"errors": int(failed_section == "hypervisor")})
    )
    monkeypatch.setattr(ns, "fetch_gpu_spec_page_ids_by_name", AsyncMock(return_value={}))
    monkeypatch.setattr(ns, "fetch_hypervisor_page_ids_by_name", AsyncMock(return_value={}))
    instance_sync = AsyncMock(return_value={"errors": 0})
    monkeypatch.setattr(ns, "sync_to_notion", instance_sync)
    update = AsyncMock()
    monkeypatch.setattr(ns, "update_notion_target", update)
    await nw._run_notion_target_sync(target(gpu_spec_database_id="gpu-db", hypervisors_database_id="hypervisor-db"))
    instance_sync.assert_awaited_once()
    stamps = update.await_args.args[1]
    assert "last_sync" in stamps
    failed_key = "gpu_spec_last_sync" if failed_section == "gpu" else "hypervisors_last_sync"
    success_key = "hypervisors_last_sync" if failed_section == "gpu" else "gpu_spec_last_sync"
    assert failed_key not in stamps and success_key in stamps


@pytest.mark.asyncio
async def test_legacy_timestamp_update_preserves_concurrent_user_columns(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.db import NotionConfig

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.is_db_available", lambda: True)
    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    older = datetime(2026, 10, 13)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(NotionConfig.__table__.create)
        async with factory() as session:
            session.add(
                NotionConfig(
                    id=1,
                    api_key_encrypted="changed-key",
                    database_id="changed-db",
                    enabled=True,
                    interval_minutes=60,
                    gpu_spec_last_sync=older,
                )
            )
            await session.commit()
        stamp = datetime.now(UTC).isoformat()
        await ns.update_notion_config_timestamps({"last_sync": stamp})
        async with factory() as session:
            row = await session.get(NotionConfig, 1)
            assert row.api_key_encrypted == "changed-key"
            assert row.database_id == "changed-db" and row.interval_minutes == 60 and row.enabled
            assert row.last_sync is not None and row.gpu_spec_last_sync == older
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cancellation_first_received_during_normal_drain_is_propagated():
    started = asyncio.Event()
    cleaning = asyncio.Event()
    release = asyncio.Event()

    async def child():
        started.set()
        try:
            await asyncio.Future()
        finally:
            cleaning.set()
            await release.wait()

    task = asyncio.create_task(child())
    await started.wait()
    draining = asyncio.create_task(nw._drain([task]))
    await asyncio.wait_for(cleaning.wait(), 2)
    draining.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await draining
    assert task.done()


@pytest.mark.asyncio
async def test_transient_discovery_error_does_not_end_scanner_incarnation(coordination, monkeypatch):
    redis, prefix = coordination
    retried = asyncio.Event()
    calls = 0

    async def discovery():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("temporary registry failure")
        retried.set()
        return []

    monkeypatch.setattr(nw, "_discover_targets", discovery)
    monkeypatch.setattr(nw, "_CHECK_INTERVAL", 0.001)
    async with wd.WorkDispatcher(redis, prefix) as worker:
        scanner = asyncio.create_task(nw._scan(worker))
        try:
            await asyncio.wait_for(retried.wait(), 2)
            assert not scanner.done() and await worker.is_leader()
        finally:
            await nw._drain([scanner])


@pytest.fixture
async def legacy_store(coordination, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.db import NotionConfig

    redis, prefix = coordination
    key = f"{prefix}:legacy-config"
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(ns, "REDIS_CONFIG_KEY", key)
    monkeypatch.setattr("app.database.is_db_available", lambda: True)
    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(NotionConfig.__table__.create)
        yield redis, prefix, key, factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_redis_only_legacy_worker_persists_stamps_and_respects_next_interval(legacy_store, monkeypatch):
    import json

    from app.models.db import NotionConfig

    redis, prefix, key, factory = legacy_store
    config = target(database_id="redis-output", interval_minutes=60)
    config.pop("id")
    await redis.set(key, json.dumps(config))
    monkeypatch.setattr("app.services.gpu_catalog.refresh_device_map_from_db", AsyncMock())
    monkeypatch.setattr("app.services.openstack_inventory.collect_instance_data", AsyncMock(return_value=[]))
    monkeypatch.setattr(ns, "sync_to_notion", AsyncMock(return_value={"errors": 0}))
    monkeypatch.setattr(ns, "migrate_instance_db_to_korean", AsyncMock(return_value=False))
    monkeypatch.setattr(ns, "list_notion_targets", AsyncMock(return_value=[]))
    async with wd.WorkDispatcher(redis, prefix) as worker:
        await worker.publish(await nw._discover_targets())
        await nw._execute_target(worker, *await worker.claim(90))
        assert await nw._discover_targets() == []
    stored = json.loads(await redis.get(key))
    assert stored["last_sync"] is not None
    assert {field: stored[field] for field in config if field != "last_sync"} == {
        field: value for field, value in config.items() if field != "last_sync"
    }
    async with factory() as session:
        assert await session.get(NotionConfig, 1) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"enabled": False}, {"interval_minutes": 90}, {"database_id": "new-output"}])
async def test_redis_timestamp_compare_and_set_cannot_revert_policy_change(legacy_store, monkeypatch, change):
    import json

    redis, _, key, _ = legacy_store
    config = target()
    config.pop("id")
    await redis.set(key, json.dumps(config))
    changed = {**config, **change}

    class RedisRace:
        def __getattr__(self, name):
            return getattr(redis, name)

        async def eval(self, script, *args):
            if script == ns._UPDATE_REDIS_TIMESTAMPS:
                await redis.set(key, json.dumps(changed))
            return await redis.eval(script, *args)

    monkeypatch.setattr("app.services.cache._get_redis", AsyncMock(return_value=RedisRace()))
    with pytest.raises(wd.DispatcherUnavailable, match="policy changed"):
        await ns.update_notion_config_timestamps({"last_sync": datetime.now(UTC).isoformat()})
    assert json.loads(await redis.get(key)) == changed


@pytest.mark.asyncio
async def test_disabled_sql_legacy_config_cannot_fall_back_to_stale_redis_policy(legacy_store):
    import json

    from app.models.db import NotionConfig

    redis, _, key, factory = legacy_store
    config = target()
    config.pop("id")
    await redis.set(key, json.dumps(config))
    async with factory() as session:
        session.add(NotionConfig(id=1, api_key_encrypted="disabled-key", database_id="sql-output", enabled=False))
        await session.commit()
    with pytest.raises(wd.DispatcherUnavailable):
        await ns.update_notion_config_timestamps({"last_sync": datetime.now(UTC).isoformat()})
    assert json.loads(await redis.get(key)) == config
