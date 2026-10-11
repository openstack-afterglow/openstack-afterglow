"""Real thread/adapter and real Redis Lua boundaries, without cloud mutation."""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import anyio
import fakeredis.aioredis
import pytest

from app.services.mcp_control_plane import connection, limits, registry, transport
from app.services.mcp_control_plane.authentication import McpPrincipal
from app.services.mcp_control_plane.sdk import gather_sdk, run_sdk, sdk_deadline
from tests.test_mcp_tool_call_cache import rpc
from tests.test_mcp_tool_call_cache import running_mcp as _running_mcp

running_mcp = _running_mcp

_KEY = "afterglow:mcp:limit:project-a:grant-a:concurrency"
_SERVER_ID = "12345678-1234-1234-1234-123456789abc"


@pytest.fixture(autouse=True)
def isolated_authority(monkeypatch):
    async def resolve(principal, project_id=None, *, write=False):
        return replace(
            principal, project_id=project_id or principal.project_id, owner_project_id=principal.anchor_project_id
        )

    monkeypatch.setattr(registry, "resolve_principal_target", resolve)


@pytest.fixture
def principal():
    return McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:read", "mcp:write"}),
        source="personal_token",
    )


@pytest.fixture
async def redis(monkeypatch):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def get_redis():
        return client

    monkeypatch.setattr(limits, "_get_redis", get_redis)
    monkeypatch.setattr(
        limits,
        "get_settings",
        lambda: SimpleNamespace(
            mcp_read_rate_per_minute=100,
            mcp_mutation_rate_per_minute=100,
            mcp_concurrent_calls_per_grant=1,
        ),
    )
    yield client
    await client.close()


async def _wait(event: threading.Event):
    async with asyncio.timeout(2):
        while not event.is_set():
            await asyncio.sleep(0.001)


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["afterglow_vm_action", "afterglow_vm_delete"])
async def test_timeout_during_owner_read_fences_late_mutation_and_holds_slot(monkeypatch, principal, redis, mutation):
    owner_read_started = threading.Event()
    finish_owner_read = threading.Event()
    events = []

    class Compute:
        def get_server(self, server_id):
            owner_read_started.set()
            assert finish_owner_read.wait(2)
            events.append("owner_read_finished")
            return SimpleNamespace(id=server_id, name="vm-a", status="ACTIVE", project_id="project-a")

        def stop_server(self, *_args, **_kwargs):
            events.append("mutation_sent")

        def delete_server(self, *_args, **_kwargs):
            events.append("mutation_sent")

    conn = SimpleNamespace(compute=Compute())

    @asynccontextmanager
    async def cloud_connection(_self):
        try:
            yield conn
        finally:
            events.append("connection_closed")

    monkeypatch.setattr(registry.ConsumerCloudContext, "openstack_connection", cloud_connection)
    entry = replace(registry.entry_by_name(mutation), timeout_seconds=0.02)
    arguments = {"server_id": _SERVER_ID}
    if mutation.endswith("action"):
        arguments["action"] = "stop"

    async def invoke():
        async with limits.grant_call_slot(principal, effect="external_mutation"):
            return await registry.dispatch(
                registry.ConsumerCloudContext(principal=principal),
                entry=entry,
                arguments=entry.arguments.model_validate(arguments),
            )

    task = asyncio.create_task(invoke())
    await _wait(owner_read_started)
    await asyncio.sleep(0.04)  # deadline expired; SDK owner read remains alive
    assert not task.done()
    assert events == []
    assert await redis.scard(_KEY) == 1
    with pytest.raises(limits.McpRateLimitExceeded):
        async with limits.grant_call_slot(principal, effect="external_mutation"):
            raise AssertionError("timeout must not admit a fresh-key overlapping retry")
    finish_owner_read.set()
    with pytest.raises(ValueError, match="timed out"):
        await task
    assert events == ["owner_read_finished", "connection_closed"]
    assert await redis.exists(_KEY) == 0


@pytest.mark.asyncio
async def test_inflight_provider_request_finishes_before_connection_and_slot_release(monkeypatch, principal, redis):
    mutation_started = threading.Event()
    finish_mutation = threading.Event()
    events = []

    class Compute:
        def get_server(self, server_id):
            return SimpleNamespace(id=server_id, name="vm-a", status="ACTIVE", project_id="project-a")

        def stop_server(self, *_args):
            mutation_started.set()
            assert finish_mutation.wait(2)
            events.append("provider_request_finished")

    @asynccontextmanager
    async def cloud_connection(_self):
        try:
            yield SimpleNamespace(compute=Compute())
        finally:
            events.append("connection_closed")

    monkeypatch.setattr(registry.ConsumerCloudContext, "openstack_connection", cloud_connection)
    entry = replace(registry.entry_by_name("afterglow_vm_action"), timeout_seconds=0.02)

    async def invoke():
        async with limits.grant_call_slot(principal, effect="external_mutation"):
            await registry.dispatch(
                registry.ConsumerCloudContext(principal=principal),
                entry=entry,
                arguments=entry.arguments(server_id=_SERVER_ID, action="stop"),
            )

    task = asyncio.create_task(invoke())
    await _wait(mutation_started)
    await asyncio.sleep(0.04)
    assert not task.done()
    assert events == []
    assert await redis.scard(_KEY) == 1
    finish_mutation.set()
    with pytest.raises(ValueError, match="timed out"):
        await task
    assert events == ["provider_request_finished", "connection_closed"]
    assert await redis.exists(_KEY) == 0


@pytest.mark.asyncio
async def test_repeated_cancellation_does_not_abandon_worker_or_release_slot(principal, redis):
    started = threading.Event()
    finish = threading.Event()

    def worker():
        started.set()
        assert finish.wait(2)

    async def invoke():
        async with limits.grant_call_slot(principal, effect="read"):
            await run_sdk(worker)

    task = asyncio.create_task(invoke())
    await _wait(started)
    task.cancel()
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.sleep(0.01)
    assert not task.done()
    assert await redis.scard(_KEY) == 1
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await redis.exists(_KEY) == 0


@pytest.mark.asyncio
async def test_anyio_level_cancellation_settles_worker_before_leaving_scope():
    started = threading.Event()
    finish = threading.Event()
    settled = threading.Event()

    def worker():
        started.set()
        assert finish.wait(2)
        settled.set()

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(run_sdk, worker)
        await _wait(started)
        tasks.cancel_scope.cancel()
        with anyio.CancelScope(shield=True):
            await asyncio.sleep(0.01)
            assert not settled.is_set()
            finish.set()
    assert settled.is_set()


@pytest.mark.asyncio
async def test_canceled_connection_construction_closes_late_result(monkeypatch, principal):
    started = threading.Event()
    finish = threading.Event()
    closed = threading.Event()

    async def credential(_principal):
        return "synthetic-credential", "synthetic-secret"

    def build(*_args):
        started.set()
        assert finish.wait(2)
        return SimpleNamespace(close=closed.set)

    monkeypatch.setattr(connection, "_load_credential", credential)
    monkeypatch.setattr(connection, "_build_connection", build)

    async def invoke():
        async with connection.consumer_connection(principal):
            raise AssertionError("canceled constructor must never yield the connection")

    task = asyncio.create_task(invoke())
    await _wait(started)
    task.cancel()
    await asyncio.sleep(0.01)
    assert not task.done()
    assert not closed.is_set()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


@pytest.mark.asyncio
async def test_parallel_sdk_reads_all_settle_before_connection_can_close():
    started = [threading.Event(), threading.Event()]
    finish = [threading.Event(), threading.Event()]

    def worker(index):
        started[index].set()
        assert finish[index].wait(2)

    async def invoke():
        with sdk_deadline(10):
            await gather_sdk(run_sdk(worker, 0), run_sdk(worker, 1))

    task = asyncio.create_task(invoke())
    for event in started:
        await _wait(event)
    task.cancel()
    finish[0].set()
    await asyncio.sleep(0.01)
    assert not task.done()  # first completed child cannot abandon the second
    finish[1].set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_tools_metadata_marks_deletions_and_lifecycle_changes_destructive(monkeypatch, principal):
    monkeypatch.setattr(transport, "current_principal", lambda: principal)
    monkeypatch.setattr(
        registry,
        "get_settings",
        lambda: SimpleNamespace(
            service_trove_enabled=True,
            service_zun_enabled=True,
            service_manila_enabled=True,
            service_k3s_enabled=True,
            service_swift_enabled=True,
            service_barbican_enabled=True,
            service_waygate_enabled=True,
        ),
    )
    tools = (await transport._list_tools(None)).tools
    metadata = {tool.name: tool.annotations for tool in tools}
    assert sum(name.endswith("delete") for name in metadata) == 8
    assert metadata["afterglow_vm_action"].destructiveHint is True
    assert metadata["afterglow_container_action"].destructiveHint is True
    assert metadata["afterglow_database_instance_restart"].destructiveHint is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module_name", "prepare_name", "request_name", "resource_argument", "action"),
    [
        ("compute", "_prepare_server_action", "request_project_server_action", "server_id", "stop"),
        ("compute", "_prepare_server_delete", "request_project_server_delete", "server_id", None),
        ("storage", "_prepare_volume_delete", "request_project_volume_delete", "volume_id", None),
        ("storage", "_prepare_snapshot_delete", "request_project_snapshot_delete", "snapshot_id", None),
        ("storage", "_prepare_backup_delete", "request_project_backup_delete", "backup_id", None),
        ("network", "_prepare_network_delete", "request_project_network_delete", "network_id", None),
        ("network", "_prepare_subnet_delete", "request_project_subnet_delete", "subnet_id", None),
        ("container", "_prepare_container_action", "request_project_container_action", "container_id", "stop"),
        ("container", "_prepare_container_delete", "request_project_container_delete", "container_id", None),
        ("database", "_prepare_instance_restart", "request_project_database_instance_restart", "instance_id", None),
        ("database", "_prepare_instance_delete", "request_project_database_instance_delete", "instance_id", None),
    ],
)
async def test_every_mutation_adapter_fences_after_slow_final_validation(
    monkeypatch, module_name, prepare_name, request_name, resource_argument, action
):
    import importlib

    module = importlib.import_module(f"app.services.mcp_control_plane.{module_name}")
    started = threading.Event()
    finish_validation = threading.Event()
    mutations = []

    def validate_owner_and_state(*_args, **_kwargs):
        started.set()
        assert finish_validation.wait(2)
        return {"status": "ACTIVE", "requested_action": action or "delete"}

    def provider_mutation(*_args, **_kwargs):
        mutations.append("sent")
        return SimpleNamespace(status_code=202)

    monkeypatch.setattr(module, prepare_name, validate_owner_and_state)
    if module_name == "container":
        monkeypatch.setattr(module, "_endpoint", lambda _conn: "https://synthetic.invalid")
    proxy = SimpleNamespace(
        stop_server=provider_mutation,
        delete_server=provider_mutation,
        delete_volume=provider_mutation,
        delete_snapshot=provider_mutation,
        delete_backup=provider_mutation,
        delete_network=provider_mutation,
        delete_subnet=provider_mutation,
        post=provider_mutation,
        delete=provider_mutation,
    )
    conn = SimpleNamespace(compute=proxy, block_storage=proxy, network=proxy, session=proxy, database=proxy)
    arguments = {"project_id": "project-a", resource_argument: "resource-a"}
    if action is not None:
        arguments["action"] = action

    async def invoke():
        with sdk_deadline(0.02):
            async with asyncio.timeout(0.02):
                await getattr(module, request_name)(conn, **arguments)

    task = asyncio.create_task(invoke())
    await _wait(started)
    await asyncio.sleep(0.04)
    assert not task.done()
    finish_validation.set()
    with pytest.raises(TimeoutError):
        await task
    assert mutations == []


@pytest.mark.asyncio
async def test_actual_mcp_http_timeout_keeps_slot_until_sdk_worker_settles(running_mcp, monkeypatch, principal, redis):
    from app.services.mcp_control_plane.ledger import MutationClaim

    started = threading.Event()
    finish = threading.Event()
    mutations = []
    ledger_outcomes = []

    class Compute:
        def get_server(self, server_id):
            started.set()
            assert finish.wait(2)
            return SimpleNamespace(id=server_id, name="vm-a", status="ACTIVE", project_id="project-a")

        def stop_server(self, *_args):
            mutations.append("stop")

    @asynccontextmanager
    async def cloud_connection(_self):
        yield SimpleNamespace(compute=Compute())

    async def verify(_token, *, urls):
        return principal

    async def claim(*_args, **_kwargs):
        return MutationClaim(state="claimed", invocation_id="invocation-a")

    async def no_op(*_args, **_kwargs):
        return None

    async def complete(*_args, **kwargs):
        ledger_outcomes.append(kwargs)

    entry = replace(registry.entry_by_name("afterglow_vm_action"), timeout_seconds=0.02)
    monkeypatch.setattr(
        registry, "_ENTRIES", tuple(entry if item.name == entry.name else item for item in registry.registry_entries())
    )
    monkeypatch.setattr(registry.ConsumerCloudContext, "openstack_connection", cloud_connection)
    monkeypatch.setattr(transport, "verify_mcp_bearer", verify)
    monkeypatch.setattr(transport, "grant_call_slot", limits.grant_call_slot)
    monkeypatch.setattr(transport, "claim_mutation", claim)
    monkeypatch.setattr(transport, "authorize_mutation_dispatch", no_op)
    monkeypatch.setattr(transport, "build_mutation_preview", no_op)
    monkeypatch.setattr(transport, "complete_mutation", complete)
    params = {
        "name": entry.name,
        "arguments": {
            "server_id": _SERVER_ID,
            "action": "stop",
            "idempotency_key": "http-mutation-0001",
        },
    }
    async with running_mcp() as client:
        task = asyncio.create_task(rpc(client, "tools/call", params))
        await _wait(started)
        await asyncio.sleep(0.04)
        assert not task.done()
        assert await redis.scard(_KEY) == 1
        blocked = await client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer synthetic-token",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    **params,
                    "arguments": {**params["arguments"], "idempotency_key": "http-mutation-0002"},
                },
            },
        )
        assert blocked.status_code == 429
        finish.set()
        response = await task
        assert response["result"]["isError"] is True
        assert mutations == []
        assert await redis.exists(_KEY) == 0
        assert len(ledger_outcomes) == 1
        assert "unknown" in ledger_outcomes[0]["error"]
