"""Durable ephemeral execution against SQL, Redis journals and an observable provider.

No provider orchestration or build_work boundary is mocked: first execution,
late responses, revocation and the next owner all use the same durable records.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import threading
from datetime import UTC, datetime
from types import SimpleNamespace

import fakeredis.aioredis
import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import database
from app.models.db import LibraryBuild
from app.services import build_work
from app.services import ephemeral_build as service
from app.services.work_dispatcher import DispatcherUnavailable

_TOKEN = "aaaa1111bbbb2222cccc3333dddd4444"
_SUCCESS = f"::AFTERGLOW::SUCCESS::{_TOKEN}"
_FAILURE = f"::AFTERGLOW::FAILURE::{_TOKEN}::rc=1"


def _snapshot():
    return {
        "openstack.service_project": {"id": "service-project"},
        "base_image": {"id": "img-001"},
        "builder.flavor": {"id": "flv-001"},
        "builder.network": {"id": "net-001"},
        "manila": {
            "share_proto": "NFS",
            "share_type": "nfs-type",
            "share_network_id": "sn-001",
            "share_size_gb": 5,
        },
        "recipe": {
            "library_id": "python311",
            "version": 7,
            "share_proto": "NFS",
            "apt_packages": [],
            "commands": [{"step": "snapshot", "progress_pct": 50, "script": "echo admitted-recipe"}],
        },
        "library_version": "3.11-admitted",
    }


class Lease:
    def __init__(self, redis, build_id, owner):
        self.redis = redis
        self.key = f"test:lease:library:{build_id}"
        self.owner = owner
        self.lost = False

    async def check(self):
        if self.lost or await self.redis.get(self.key) != self.owner:
            raise DispatcherUnavailable("test owner lost")


class Provider:
    def __init__(self):
        self.calls = []
        self.shares = {}
        self.ports = {}
        self.servers = {}
        self.rules = {}
        self.console = _SUCCESS
        self.server_status = "SHUTOFF"
        self.connections = []
        self.server_get_seen = threading.Event()
        self.create_started = threading.Event()
        self.create_release = threading.Event()
        self.block_create = False
        self.create_error = None
        self.close_started = threading.Event()
        self.close_release = threading.Event()
        self.block_close = False

    def connect(self, project):
        assert project == "service-project"
        conn = SimpleNamespace(
            compute=SimpleNamespace(
                create_server=self.create_server,
                get_server=self.get_server,
                servers=self.list_servers,
                delete_server=self.delete_server,
                get_server_console_output=lambda *args, **kwargs: {"output": self.console},
            ),
            network=SimpleNamespace(
                create_port=self.create_port,
                get_port=lambda identity: self.ports.get(identity),
                ports=self.list_ports,
                delete_port=self.delete_port,
            ),
            closed=False,
        )

        def close():
            self.close_started.set()
            if self.block_close:
                if not self.close_release.wait(5):
                    raise TimeoutError("test close was never released")
            conn.closed = True
            self.calls.append(("close",))

        conn.close = close
        self.connections.append(conn)
        return conn

    def create_share(self, conn, **fields):
        self.calls.append(("create_share", fields))
        share = SimpleNamespace(id="share-001", status="available", **fields)
        self.shares[share.id] = share
        return {"id": share.id, "status": share.status}

    def get_share(self, conn, identity):
        return self.shares[identity]

    def metadata(self, conn, identity, fields):
        self.calls.append(("metadata", identity, fields))
        self.shares[identity].metadata.update(fields)

    def public(self, conn, identity, value):
        self.shares[identity].public = value

    def create_port(self, **fields):
        self.calls.append(("create_port", fields))
        port = SimpleNamespace(id="port-001", fixed_ips=[{"ip_address": "10.0.0.5"}], **fields)
        self.ports[port.id] = port
        return port

    def list_ports(self, name, network_id):
        return [port for port in self.ports.values() if port.name == name and port.network_id == network_id]

    def delete_port(self, identity, ignore_missing=True):
        self.calls.append(("delete_port", identity))
        self.ports.pop(identity, None)

    def create_access(self, conn, share_id, access_to, level, access_type, *, metadata=None, wait_for_key=True):
        assert wait_for_key is False  # CREATE returns before key readiness or cleanup.
        self.calls.append(("create_access", share_id, access_to, metadata))
        identity = f"rule-{self.count('create_access'):03d}"  # Provider IDs are never reused.
        rule = {
            "id": identity,
            "share_id": share_id,
            "access_to": access_to,
            "access_level": level,
            "access_type": access_type,
            "state": "active",
            "access_key": "ceph-secret" if access_type == "cephx" else None,
        }
        self.rules[identity] = rule
        return rule

    def revoke(self, conn, share_id, identity):
        self.calls.append(("revoke", identity))
        self.rules.pop(identity, None)

    def create_server(self, **fields):
        self.calls.append(("create_server", fields))
        self.create_started.set()
        if self.block_create:
            if not self.create_release.wait(5):
                raise TimeoutError("test CREATE was never released")
        server = SimpleNamespace(
            id="server-001", status=self.server_status, created_at=datetime.now(UTC).isoformat(), **fields
        )
        self.servers[server.id] = server
        if self.create_error is not None:
            raise self.create_error
        return server

    def get_server(self, identity):
        self.server_get_seen.set()
        server = self.servers[identity]
        server.status = self.server_status
        return server

    def list_servers(self, name):
        return [server for server in self.servers.values() if re.fullmatch(name, server.name)]

    def delete_server(self, identity):
        self.calls.append(("delete_server", identity))
        self.servers.pop(identity, None)

    def count(self, operation):
        return sum(call[0] == operation for call in self.calls)


@pytest.fixture
async def execution(monkeypatch, tmp_path):
    # A cancelled operation can discard a connection; file SQLite keeps rows.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ephemeral.sqlite'}")
    async with engine.connect() as connection:
        # Readers must not block writers, matching InnoDB MVCC rather than SQLite's default journal.
        await connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: LibraryBuild.__table__.create(sync))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    provider = Provider()
    monkeypatch.setattr(service.keystone, "get_admin_connection_for_project", provider.connect)
    monkeypatch.setattr(service.manila, "submit_file_storage", provider.create_share)
    monkeypatch.setattr(service.manila, "get_file_storage", provider.get_share)
    monkeypatch.setattr(service.manila, "list_file_storages", lambda conn: list(provider.shares.values()))
    monkeypatch.setattr(service.manila, "update_share_metadata", provider.metadata)
    monkeypatch.setattr(service.manila, "set_share_public", provider.public)
    monkeypatch.setattr(service.manila, "create_access_rule", provider.create_access)
    monkeypatch.setattr(service.manila, "list_access_rules", lambda *args, **kwargs: list(provider.rules.values()))
    monkeypatch.setattr(service.manila, "get_access_rule", lambda conn, share, identity: provider.rules.get(identity))
    monkeypatch.setattr(service.manila, "revoke_access_rule", provider.revoke)
    monkeypatch.setattr(service.manila, "get_export_locations", lambda *args: ["10.0.0.1:/output"])
    monkeypatch.setattr(service, "_SHUTOFF_POLL_INTERVAL", 0)
    async with factory() as session:
        row = LibraryBuild(
            library_id="python311",
            file_storage_id="",
            status="queued",
            build_token=_TOKEN,
            resource_snapshot=_snapshot(),
        )
        session.add(row)
        await session.commit()
        build_id = row.id
    yield SimpleNamespace(factory=factory, redis=redis, provider=provider, build_id=build_id)
    provider.create_release.set()
    provider.close_release.set()
    await redis.close()
    await engine.dispose()


async def _row(execution):
    async with execution.factory() as session:
        return await session.get(LibraryBuild, execution.build_id)


async def _change(execution, **fields):
    async with execution.factory() as session:
        row = await session.get(LibraryBuild, execution.build_id)
        for key, value in fields.items():
            setattr(row, key, value)
        await session.commit()


async def _lease(execution, owner="first"):
    lease = Lease(execution.redis, execution.build_id, owner)
    await execution.redis.set(lease.key, lease.owner)
    return lease


async def _run(execution, lease=None):
    lease = lease or await _lease(execution)
    async with build_work.bind(execution.redis, f"library:{execution.build_id}", lease):
        await service.run_ephemeral_build(execution.build_id)


async def _seen(event):
    async def wait():
        while not event.is_set():
            await asyncio.sleep(0.001)

    await asyncio.wait_for(wait(), 3)


@pytest.mark.asyncio
async def test_success_uses_admitted_recipe_version_and_token_then_cleans_and_closes(execution):
    await _run(execution)
    row = await _row(execution)
    provider = execution.provider
    assert row.status == "complete"
    assert row.build_token == _TOKEN
    assert row.completed_at is not None
    assert provider.count("create_share") == provider.count("create_port") == provider.count("create_server") == 1
    assert not provider.servers and not provider.ports and not provider.rules
    share = provider.shares[row.file_storage_id]
    assert share.metadata["union_type"] == "prebuilt"
    assert share.metadata["union_version"] == "3.11-admitted"
    assert share.public
    vm_fields = next(call[1] for call in provider.calls if call[0] == "create_server")
    user_data = base64.b64decode(vm_fields["user_data"]).decode()
    encoded_script = re.search(r"    content: ([A-Za-z0-9+/=]+)", user_data).group(1)
    assert "echo admitted-recipe" in base64.b64decode(encoded_script).decode()
    assert _TOKEN in user_data
    assert all(conn.closed for conn in provider.connections)
    calls = [call[0] for call in provider.calls]
    assert calls.index("create_port") < calls.index("create_access") < calls.index("create_server")


@pytest.mark.asyncio
@pytest.mark.parametrize("console,cloud_status", [(_FAILURE, "failure"), ("no sentinel", "indeterminate")])
async def test_failure_and_indeterminate_keep_output_and_finish_without_transient_resources(
    execution, console, cloud_status
):
    execution.provider.console = console
    await _run(execution)
    row = await _row(execution)
    assert row.status == "error" and row.cloud_init_status == cloud_status
    assert row.console_log_excerpt == console
    assert not execution.provider.servers and not execution.provider.ports
    assert execution.provider.connections[0].closed


@pytest.mark.asyncio
async def test_existing_share_is_verified_and_reused(execution):
    existing = SimpleNamespace(id="existing", metadata={}, status="available")
    execution.provider.shares[existing.id] = existing
    await _change(execution, file_storage_id=existing.id)
    await _run(execution)
    assert (await _row(execution)).status == "complete"
    assert execution.provider.count("create_share") == 0
    assert existing.metadata["union_status"] == "ready"


@pytest.mark.asyncio
async def test_missing_existing_share_does_not_allocate_a_replacement(execution):
    await _change(execution, file_storage_id="missing")
    await _run(execution)
    row = await _row(execution)
    assert row.status == "error" and "사전 생성 share missing" in row.error_message
    assert execution.provider.count("create_share") == 0
    assert execution.provider.count("create_port") == 0
    assert execution.provider.connections[0].closed


@pytest.mark.asyncio
async def test_lost_owner_preserves_vm_and_next_owner_observes_output_without_create(execution):
    provider = execution.provider
    provider.server_status = "ACTIVE"
    lease = await _lease(execution)
    task = asyncio.create_task(_run(execution, lease))
    await _seen(provider.server_get_seen)
    lease.lost = True
    with pytest.raises(DispatcherUnavailable):
        await asyncio.wait_for(task, 3)
    assert (await _row(execution)).status not in build_work.TERMINAL
    assert provider.servers and provider.ports
    assert provider.count("delete_server") == provider.count("delete_port") == 0
    assert provider.connections[0].closed

    provider.server_status = "SHUTOFF"
    await _run(execution, await _lease(execution, "successor"))
    row = await _row(execution)
    assert row.status == "complete" and row.console_log_excerpt == _SUCCESS
    assert provider.count("create_share") == provider.count("create_port") == provider.count("create_server") == 1
    assert all(conn.closed for conn in provider.connections)


@pytest.mark.asyncio
async def test_process_cancellation_preserves_vm_and_is_recoverable(execution):
    provider = execution.provider
    provider.server_status = "ACTIVE"
    task = asyncio.create_task(_run(execution))
    await _seen(provider.server_get_seen)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.servers and provider.ports
    assert provider.count("delete_server") == provider.count("delete_port") == 0
    assert provider.connections[0].closed
    provider.server_status = "SHUTOFF"
    await _run(execution, await _lease(execution, "successor"))
    assert (await _row(execution)).status == "complete"
    assert provider.count("create_server") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("observable", [True, False])
async def test_unknown_server_submission_is_observed_or_fails_closed_never_reissued(execution, observable):
    provider = execution.provider
    await execution.redis.set(
        f"afterglow:builds:journal:library:{execution.build_id}:submit:server",
        json.dumps({"state": "submitting"}),
    )
    if observable:
        provider.shares["share-001"] = SimpleNamespace(id="share-001", status="available", metadata={})
        await _change(execution, file_storage_id="share-001")
        provider.servers["server-001"] = SimpleNamespace(
            id="server-001",
            name=f"afterglow-build-python311-{_TOKEN[:8]}",
            metadata={"afterglow_library_build": f"afterglow-library-build-{execution.build_id}"},
            status="SHUTOFF",
            created_at=datetime.now(UTC).isoformat(),
        )
        await _run(execution)
    else:
        with pytest.raises(build_work.SubmissionUnknown, match="will not be reissued"):
            await _run(execution)
    row = await _row(execution)
    assert provider.count("create_server") == 0
    if observable:
        assert row.status == "complete" and row.console_log_excerpt == _SUCCESS
    else:
        assert row.status not in build_work.TERMINAL
        assert provider.count("delete_server") == provider.count("delete_port") == 0
    assert provider.connections[0].closed


@pytest.mark.asyncio
async def test_cancelled_sql_row_wins_over_late_accepted_create_and_owned_cleanup(execution):
    provider = execution.provider
    provider.block_create = True
    task = asyncio.create_task(_run(execution))
    try:
        await _seen(provider.create_started)
        await _change(execution, status="cancelled", progress_step="사용자 취소", error_message="admin cancelled")
    finally:
        provider.create_release.set()
    with pytest.raises(DispatcherUnavailable):
        await asyncio.wait_for(task, 3)
    row = await _row(execution)
    assert row.status == "cancelled" and row.error_message == "admin cancelled"
    assert row.progress_step == "사용자 취소"
    assert provider.count("create_server") == 1
    assert provider.count("delete_server") == provider.count("delete_port") == 1
    assert not provider.servers and not provider.ports and not provider.rules
    assert provider.connections[0].closed


@pytest.mark.asyncio
async def test_cancel_during_create_drains_late_acceptance_before_close_and_handoff(execution):
    provider = execution.provider
    provider.block_create = True
    task = asyncio.create_task(_run(execution))
    try:
        await _seen(provider.create_started)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        assert not provider.connections[0].closed
    finally:
        provider.create_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.servers and provider.connections[0].closed
    recorded = json.loads(
        await execution.redis.get(f"afterglow:builds:journal:library:{execution.build_id}:submit:server")
    )
    assert recorded == {"state": "accepted", "result": {"id": "server-001"}}
    await _run(execution, await _lease(execution, "successor"))
    assert (await _row(execution)).status == "complete"
    assert provider.count("create_server") == 1


@pytest.mark.asyncio
async def test_repeated_cancel_still_drains_connection_close(execution):
    provider = execution.provider
    provider.block_close = True
    task = asyncio.create_task(_run(execution))
    try:
        await _seen(provider.close_started)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done() and not provider.connections[0].closed
    finally:
        provider.close_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.connections[0].closed


@pytest.mark.asyncio
async def test_missing_sql_authority_never_starts_provider_work(execution, monkeypatch):
    lease = await _lease(execution)
    monkeypatch.setattr(database, "get_session_factory", lambda: None)
    with pytest.raises(DispatcherUnavailable):
        await _run(execution, lease)
    assert not execution.provider.connections
    assert not execution.provider.calls


@pytest.mark.asyncio
async def test_incomplete_admitted_snapshot_fails_without_live_recipe_fallback(execution):
    snapshot = _snapshot()
    snapshot.pop("recipe")
    await _change(execution, resource_snapshot=snapshot)
    await _run(execution)
    row = await _row(execution)
    assert row.status == "error" and "snapshot is incomplete" in row.error_message
    assert not execution.provider.connections


@pytest.mark.asyncio
async def test_manila_enriched_http_error_reaches_terminal_sql_message(execution, monkeypatch):
    request = httpx.Request("POST", "https://manila.example.com/v2/proj/shares")
    response = httpx.Response(404, json={"itemNotFound": {"message": "Share type not found."}}, request=request)
    error = httpx.HTTPStatusError(
        "Manila API 404: Share type not found. 가용 share type: ['nfstype']",
        request=request,
        response=response,
    )

    def reject(*args, **kwargs):
        raise error

    monkeypatch.setattr(service.manila, "submit_file_storage", reject)
    await _run(execution)
    row = await _row(execution)
    assert row.status == "error"
    assert "Share type not found" in row.error_message and "nfstype" in row.error_message
    assert execution.provider.connections[0].closed


@pytest.mark.asyncio
async def test_lease_lost_during_create_records_late_id_without_deleting_active_output(execution):
    provider = execution.provider
    provider.block_create = True
    lease = await _lease(execution)
    task = asyncio.create_task(_run(execution, lease))
    try:
        await _seen(provider.create_started)
        lease.lost = True
    finally:
        provider.create_release.set()
    with pytest.raises(DispatcherUnavailable):
        await asyncio.wait_for(task, 3)
    assert provider.servers and provider.ports
    assert provider.count("delete_server") == provider.count("delete_port") == 0
    assert provider.connections[0].closed
    # A late owner cannot use its old lease to submit anything else.
    with pytest.raises(DispatcherUnavailable):
        await _run(execution, lease)
    await _run(execution, await _lease(execution, "successor"))
    row = await _row(execution)
    assert row.status == "complete" and row.console_log_excerpt == _SUCCESS
    assert provider.count("create_server") == 1


@pytest.mark.asyncio
async def test_share_identity_is_durable_before_readiness_poll_and_recovers_without_post(execution, monkeypatch):
    provider = execution.provider
    lease = await _lease(execution)

    def lose_after_read(conn, identity):
        lease.lost = True
        return provider.get_share(conn, identity)

    monkeypatch.setattr(service.manila, "get_file_storage", lose_after_read)
    with pytest.raises(DispatcherUnavailable):
        await _run(execution, lease)
    recorded = json.loads(
        await execution.redis.get(f"afterglow:builds:journal:library:{execution.build_id}:submit:share")
    )
    assert recorded["state"] == "accepted" and recorded["result"]["id"] == "share-001"
    assert provider.count("create_share") == 1 and provider.shares
    assert provider.connections[0].closed
    monkeypatch.setattr(service.manila, "get_file_storage", provider.get_share)
    await _run(execution, await _lease(execution, "successor"))
    assert (await _row(execution)).status == "complete"
    assert provider.count("create_share") == 1


@pytest.mark.asyncio
async def test_cephfs_raw_rules_keep_keys_out_of_journal_and_promote_share(execution):
    snapshot = _snapshot()
    snapshot["recipe"]["share_proto"] = "CEPHFS"
    snapshot["manila"].update(share_proto="CEPHFS", share_network_id="")
    await _change(execution, resource_snapshot=snapshot)
    await _run(execution)
    row = await _row(execution)
    assert row.status == "complete"
    assert execution.provider.shares[row.file_storage_id].metadata["union_cephx_user"] == "union-ro-python311"
    for step in ("rw_access", "ro_access"):
        raw = await execution.redis.get(f"afterglow:builds:journal:library:{execution.build_id}:submit:{step}")
        assert json.loads(raw)["state"] == "accepted"
        assert "ceph-secret" not in raw


@pytest.mark.asyncio
async def test_bound_target_cannot_execute_a_different_sql_build(execution):
    lease = await _lease(execution)
    async with build_work.bind(execution.redis, f"library:{execution.build_id}", lease):
        with pytest.raises(DispatcherUnavailable, match="does not match"):
            await service.run_ephemeral_build(execution.build_id + 1)
    assert not execution.provider.connections


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "step,operation", [("share", "create_share"), ("port", "create_port"), ("rw_access", "create_access")]
)
async def test_unknown_provisioning_submission_is_never_replayed(execution, step, operation):
    await execution.redis.set(
        f"afterglow:builds:journal:library:{execution.build_id}:submit:{step}",
        json.dumps({"state": "unknown"}),
    )
    with pytest.raises(build_work.SubmissionUnknown, match=f"{step} submission outcome is unknown"):
        await _run(execution)
    row = await _row(execution)
    assert row.status not in build_work.TERMINAL
    assert execution.provider.count("delete_server") == execution.provider.count("delete_port") == 0
    assert execution.provider.count(operation) == 0
    assert execution.provider.count("create_server") == 0
    assert execution.provider.connections[0].closed


@pytest.mark.asyncio
async def test_cancelled_create_response_loss_preserves_output_and_unknown_journal(execution):
    provider = execution.provider
    provider.block_create = True
    provider.create_error = ConnectionError("accepted CREATE response lost")
    task = asyncio.create_task(_run(execution))
    try:
        await _seen(provider.create_started)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
    finally:
        provider.create_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await _row(execution)).status not in build_work.TERMINAL
    assert provider.servers and provider.ports
    assert provider.count("delete_server") == provider.count("delete_port") == 0
    assert provider.connections[0].closed
    recorded = json.loads(
        await execution.redis.get(f"afterglow:builds:journal:library:{execution.build_id}:submit:server")
    )
    assert recorded["state"] == "unknown"
    provider.create_error = None
    await _run(execution, await _lease(execution, "successor"))
    assert (await _row(execution)).status == "complete"
    assert provider.count("create_server") == 1


@pytest.mark.asyncio
async def test_successor_waits_for_old_inflight_create_then_observes_late_output(execution):
    provider = execution.provider
    provider.block_create = True
    old_lease = await _lease(execution)
    old_task = asyncio.create_task(_run(execution, old_lease))
    try:
        await _seen(provider.create_started)
        old_lease.lost = True
        successor = await _lease(execution, "successor")
        with pytest.raises(build_work.SubmissionUnknown):
            await _run(execution, successor)
        assert (await _row(execution)).status not in build_work.TERMINAL
        assert provider.ports and provider.count("delete_port") == 0
    finally:
        provider.create_release.set()
    with pytest.raises(DispatcherUnavailable):
        await old_task
    await _run(execution, successor)
    row = await _row(execution)
    assert row.status == "complete" and row.console_log_excerpt == _SUCCESS
    assert provider.count("create_server") == 1
    assert provider.count("create_access") == 1
    assert all(conn.closed for conn in provider.connections)


@pytest.mark.asyncio
async def test_sdk_response_loss_is_not_terminal_failure_or_destructive_cleanup(execution):
    provider = execution.provider
    provider.create_error = ConnectionError("accepted CREATE response lost")
    with pytest.raises(build_work.SubmissionUnknown) as failure:
        await _run(execution)
    assert isinstance(failure.value.__cause__, ConnectionError)
    assert (await _row(execution)).status not in build_work.TERMINAL
    assert provider.servers and provider.ports
    assert provider.count("delete_server") == provider.count("delete_port") == 0
    assert provider.connections[0].closed
    provider.create_error = None
    await _run(execution, await _lease(execution, "successor"))
    row = await _row(execution)
    assert row.status == "complete" and row.console_log_excerpt == _SUCCESS
    assert provider.count("create_server") == 1
    assert provider.count("create_access") == 1


@pytest.mark.asyncio
async def test_cancel_in_owner_gap_stays_runnable_until_cleanup_owner_removes_unknown_vm(execution):
    from app.services import library_builder

    provider = execution.provider
    # The owner vanishes after Nova accepted the VM but before its response: SQL
    # never records the VM; only the unknown journal submission and the VM exist.
    provider.create_error = ConnectionError("accepted CREATE response lost")
    with pytest.raises(build_work.SubmissionUnknown):
        await _run(execution)
    assert (await _row(execution)).server_id is None and provider.servers
    calls_before = len(provider.calls)

    assert await library_builder.cancel_build(execution.build_id) == {"cancelled": True, "library_id": "python311"}
    row = await _row(execution)
    assert row.status == "cancelled" and row.completed_at is None
    assert row.resource_snapshot["cancel_cleanup"] == "pending"
    assert len(provider.calls) == calls_before

    lease = await _lease(execution, "cleanup-owner")
    async with build_work.bind(execution.redis, f"library:{execution.build_id}", lease, cancel_cleanup=True):
        await service.run_ephemeral_build(execution.build_id)

    row = await _row(execution)
    assert row.status == "cancelled" and row.completed_at is not None
    assert row.resource_snapshot["cancel_cleanup"] == "done"
    assert not provider.servers and not provider.ports and not provider.rules
    assert provider.shares  # The output share is retained, as on every cancellation.
    created = [call[0] for call in provider.calls if call[0].startswith("create_")]
    assert created == ["create_share", "create_port", "create_access", "create_server"]
    assert all(conn.closed for conn in provider.connections)


@pytest.mark.asyncio
async def test_unknown_ro_rule_preserves_success_outcome_without_false_ready_and_recovers(execution, monkeypatch):
    provider = execution.provider
    snapshot = _snapshot()
    snapshot["recipe"]["share_proto"] = "CEPHFS"
    snapshot["manila"].update(share_proto="CEPHFS", share_network_id="")
    await _change(execution, resource_snapshot=snapshot)

    def lose_ro_response(conn, share_id, access_to, level, access_type, **kwargs):
        rule = provider.create_access(conn, share_id, access_to, level, access_type, **kwargs)
        if level == "ro":
            raise ConnectionError("RO CREATE accepted but response lost")
        return rule

    monkeypatch.setattr(service.manila, "create_access_rule", lose_ro_response)
    with pytest.raises(build_work.SubmissionUnknown):
        await _run(execution)
    row = await _row(execution)
    assert row.status not in build_work.TERMINAL
    share = provider.shares[row.file_storage_id]
    assert share.metadata["union_status"] != "ready" and not getattr(share, "public", False)
    assert provider.servers and provider.ports
    assert provider.count("delete_server") == provider.count("delete_port") == 0
    journal = json.loads(await execution.redis.get(f"afterglow:builds:journal:library:{execution.build_id}"))
    assert journal["outcome"] == {"result": "success"}
    monkeypatch.setattr(service.manila, "create_access_rule", provider.create_access)
    await _run(execution, await _lease(execution, "successor"))
    assert (await _row(execution)).status == "complete"
    assert share.metadata["union_status"] == "ready" and share.public
    assert provider.count("create_access") == 2  # Exactly one RW and one RO, including response loss.
    assert all(conn.closed for conn in provider.connections)


@pytest.mark.asyncio
@pytest.mark.parametrize("console,terminal", [(_SUCCESS, "complete"), (_FAILURE, "error")])
async def test_leader_discovery_retains_execution_assignment_while_terminal_disposal_drains(
    execution,
    monkeypatch,
    console,
    terminal,
):
    from sqlalchemy import Text

    from app.models.db import LayerBuild, LayerImportJob
    from app.services import library_builder
    from app.services.work_dispatcher import WorkDispatcher

    # Discovery reads all durable work kinds. Adapt only disposable SQLite DDL,
    # as in the durable-admission tests, without changing production metadata.
    monkeypatch.setattr(LayerImportJob.__table__.c.dockerfile_text, "type", Text())
    async with execution.factory.kw["bind"].begin() as connection:
        for model in (LayerImportJob, LayerBuild):
            await connection.run_sync(lambda sync, model=model: model.__table__.create(sync))
    provider = execution.provider
    provider.console = console
    disposal_started = threading.Event()
    disposal_release = threading.Event()
    delete_server = provider.delete_server

    def blocked_disposal(identity):
        disposal_started.set()
        if not disposal_release.wait(5):
            raise TimeoutError("test disposal was never released")
        delete_server(identity)

    monkeypatch.setattr(provider, "delete_server", blocked_disposal)
    prefix = f"test:ephemeral-discovery:{execution.build_id}"
    async with WorkDispatcher(execution.redis, prefix, worker_id="ephemeral-owner") as worker:
        await library_builder._discover_work(worker)
        member, owner = await worker.claim(90)
        assert member == f"library:{execution.build_id}"
        task = asyncio.create_task(library_builder._execute_work(worker, member, owner))
        try:
            await _seen(disposal_started)
            row = await _row(execution)
            assert row.status not in build_work.TERMINAL and row.completed_at is None
            # Repeated real leader scans must not revoke a healthy cleanup owner.
            for _ in range(2):
                await library_builder._discover_work(worker)
                assert await worker.is_assigned(member)
                assert await worker.claim(90) is None
            assert not provider.connections[0].closed
        finally:
            disposal_release.set()
            await asyncio.wait_for(task, 3)
        assert (await _row(execution)).status == terminal
        assert not provider.servers and not provider.ports
        assert provider.connections[0].closed
        await library_builder._discover_work(worker)
        assert not await worker.is_assigned(member)
