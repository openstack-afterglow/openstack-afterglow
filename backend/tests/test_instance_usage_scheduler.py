"""Deterministic metadata-authority scheduler checks; no live cloud writes."""

import asyncio
import copy
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from openstack.exceptions import ResourceNotFound

from app.models.instance_usage import UsageScheduleRequest
from app.services import instance_usage as usage
from app.services import instance_usage_scheduler as scheduler
from app.services.work_dispatcher import DispatcherUnavailable

NOW = datetime(2026, 10, 29, tzinfo=UTC)
PROJECT, SERVER = "project-one", "server-one"


class Redis:
    def __init__(self):
        self.values = {}
        self.available = True

    async def set(self, key, value, **_):
        if not self.available:
            raise OSError("offline")
        if key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script, _, key, owner, *args):
        if not self.available:
            raise OSError("offline")
        if self.values.get(key) != owner:
            return 0
        if "redis.call('del'" in script:
            del self.values[key]
        return 1


class Native:
    def __init__(self, *, status="ACTIVE", schedule=True, action="shelve", delete_volumes=False):
        metadata = {"unrelated": "keep"}
        if schedule:
            metadata.update(
                usage.creation_metadata(
                    {"vcpus": 12},
                    UsageScheduleRequest(expiry_action=action, delete_volumes=delete_volumes),
                    now=NOW - timedelta(days=40),
                )
            )
        self.server = dict(
            id=SERVER,
            project_id=PROJECT,
            status=status,
            metadata=metadata,
            flavor={"id": "large"},
            attached_volumes=[],
            task_state=None,
        )
        self.actions, self.flag_writes, self.metadata_writes = [], [], []
        self.failure = None
        self.volumes = {}
        self.attachments = []
        self.flavor = SimpleNamespace(id="large", name="cpu.large", vcpus=12, ram=8192, extra_specs={})
        self.compute = self
        self.block_storage = self
        self.session = SimpleNamespace(
            auth=SimpleNamespace(
                get_access=lambda _: SimpleNamespace(project_id=PROJECT, project_scoped=True, system_scoped=False)
            )
        )
        self.closed = False
        self.on_read = None
        self.legacy_flavor_id = None

    def request(self, *_args, **_kwargs):
        raise AssertionError("Fake native methods must not issue HTTP")

    def endpoint_for(self, service):
        return f"http://synthetic.invalid/{service}"

    def close(self):
        self.closed = True

    def get_server(self, server_id):
        if self.on_read:
            self.on_read()
        if self.server is None:
            raise ResourceNotFound("gone")
        assert server_id == SERVER
        server = copy.deepcopy(self.server)
        if getattr(self, "default_microversion", None) == "2.46" and self.legacy_flavor_id is not None:
            server["flavor"] = {"id": self.legacy_flavor_id}
        return server

    def set_server_metadata(self, server_id, **changes):
        assert server_id == SERVER
        self.metadata_writes.append(changes)
        self.server["metadata"].update(changes)

    def servers(self, **query):
        assert query == {"details": True, "all_projects": True}
        return [self.get_server(SERVER)] if self.server else []

    def flavors(self, **query):
        assert query == {"details": True, "is_public": None}
        return [self.flavor]

    def fetch_flavor_extra_specs(self, flavor):
        return flavor

    def _action(self, name, server_id):
        assert server_id == SERVER
        self.actions.append(name)
        if self.failure:
            raise self.failure

    def shelve_server(self, server_id):
        self._action("shelve", server_id)

    def shelve_offload_server(self, server_id):
        self._action("offload", server_id)

    def stop_server(self, server_id):
        self._action("stop", server_id)

    def delete_server(self, server_id, *, ignore_missing, force):
        assert ignore_missing is False and force is False
        self._action("delete", server_id)

    def volume_attachments(self, server_id):
        assert server_id == SERVER
        return copy.deepcopy(self.attachments)

    def get_volume(self, volume_id):
        return copy.deepcopy(self.volumes[volume_id])

    def update_volume_attachment(self, server_id, volume_id, **attrs):
        assert server_id == SERVER
        self.flag_writes.append((volume_id, attrs))
        for attachment in self.attachments:
            if attachment["volume_id"] == volume_id:
                attachment.update(attrs)
        if self.failure:
            raise self.failure

    def add_volume(self, volume_id="boot", *, flag=True):
        self.attachments.append(dict(id=volume_id, volume_id=volume_id, server_id=SERVER, delete_on_termination=flag))
        self.server["attached_volumes"].append({"id": volume_id})
        self.volumes[volume_id] = dict(
            id=volume_id, project_id=PROJECT, attachments=[{"server_id": SERVER}], is_multiattach=False
        )


def state(native):
    return usage.parse_schedule(native.server).state


async def cycle(native, redis=None, clock=NOW):
    await scheduler._cycle(native, PROJECT, SERVER, clock, redis or Redis())


@pytest.mark.asyncio
async def test_existing_enrollment_starts_calendar_month_grace_once_not_creation_date():
    native = Native(schedule=False)
    native.server["created_at"] = "2015-01-01T00:00:00Z"
    await cycle(native)
    info = usage.parse_schedule(native.server)
    assert info.source == "adopted"
    assert datetime.fromisoformat(info.starts_at) == NOW
    assert datetime.fromisoformat(info.expires_at) == datetime(2026, 11, 29, tzinfo=UTC)
    original = dict(native.server["metadata"])
    await cycle(native, clock=NOW + timedelta(days=1))
    assert native.server["metadata"] == original
    assert native.actions == []
    assert native.server["metadata"]["unrelated"] == "keep"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["ACTIVE", "SHUTOFF"])
async def test_shelve_then_offload_requires_observed_status_and_never_replays(status):
    native = Native(status=status)
    await cycle(native)
    assert state(native) == "shelve_requested"
    await cycle(native)
    assert native.actions == ["shelve"]
    native.server["status"] = "SHELVED"
    await cycle(native)
    assert state(native) == "offload_requested"
    await cycle(native)
    assert native.actions == ["shelve", "offload"]
    native.server["status"] = "SHELVED_OFFLOADED"
    await cycle(native)
    assert state(native) == "complete"
    assert native.server["metadata"]["unrelated"] == "keep"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["BUILD", "ERROR", "REBOOT", "RESIZE", "UNKNOWN"])
async def test_busy_and_error_block_without_force_actions(status):
    native = Native(status=status)
    await cycle(native)
    assert state(native) == "blocked"
    assert native.actions == []


@pytest.mark.asyncio
async def test_task_state_blocks_even_when_status_active():
    native = Native()
    native.server["task_state"] = "resize_migrating"
    await cycle(native)
    assert state(native) == "blocked" and native.actions == []


@pytest.mark.asyncio
async def test_unknown_shelve_result_survives_restarts_without_replay():
    native = Native()
    native.failure = OSError("connection lost after write")
    with pytest.raises(OSError):
        await cycle(native)
    assert state(native) == "shelve_requested"
    native.failure = None
    await cycle(native)
    assert native.actions == ["shelve"]
    native.server["status"] = "SHELVED_OFFLOADED"
    await cycle(native)
    assert state(native) == "complete"


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_volumes", [False, True])
async def test_delete_stops_then_verifies_all_boot_and_data_flags(delete_volumes):
    native = Native(action="delete", delete_volumes=delete_volumes)
    native.add_volume("boot", flag=not delete_volumes)
    native.add_volume("data", flag=not delete_volumes)
    await cycle(native)
    assert native.actions == ["stop"] and state(native) == "stop_requested"
    await cycle(native)
    assert native.actions == ["stop"]
    native.server["status"] = "SHUTOFF"
    await cycle(native)
    assert native.actions == ["stop", "delete"]
    assert state(native) == "delete_requested"
    assert len(native.flag_writes) == 2
    assert all(a["delete_on_termination"] is delete_volumes for a in native.attachments)
    await cycle(native)
    assert native.actions == ["stop", "delete"]
    native.server = None
    await cycle(native)  # Native exact-project 404 is terminal, not a retry.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "defect", ["foreign", "multiattach", "second_attachment", "unknown_flag", "inventory_mismatch", "wrong_server"]
)
async def test_volume_proof_failure_never_deletes_or_changes_flags(defect):
    native = Native(status="SHUTOFF", action="delete", delete_volumes=True)
    native.add_volume()
    if defect == "foreign":
        native.volumes["boot"]["project_id"] = "other"
    elif defect == "multiattach":
        native.volumes["boot"]["is_multiattach"] = True
    elif defect == "second_attachment":
        native.volumes["boot"]["attachments"].append({"server_id": "other"})
    elif defect == "unknown_flag":
        del native.attachments[0]["delete_on_termination"]
    elif defect == "inventory_mismatch":
        native.server["attached_volumes"] = []
    else:
        native.volumes["boot"]["attachments"][0]["server_id"] = "other"
    with pytest.raises(RuntimeError):
        await cycle(native)
    assert state(native) == "blocked"
    assert native.actions == native.flag_writes == []


@pytest.mark.asyncio
async def test_uncertain_attachment_put_is_readback_only_after_restart():
    native = Native(status="SHUTOFF", action="delete")
    native.add_volume(flag=True)
    native.failure = OSError("reply lost")
    with pytest.raises(OSError):
        await cycle(native)
    assert state(native) == "volume_flags_requested" and len(native.flag_writes) == 1
    native.failure = None
    await cycle(native)
    assert len(native.flag_writes) == 1 and native.actions == ["delete"]


@pytest.mark.asyncio
async def test_uncommitted_attachment_put_is_never_replayed():
    native = Native(status="SHUTOFF", action="delete")
    native.add_volume(flag=True)
    native.server["metadata"][usage.METADATA_PREFIX + "state"] = "volume_flags_requested"
    with pytest.raises(RuntimeError):
        await cycle(native)
    assert state(native) == "volume_flags_requested"
    assert native.flag_writes == native.actions == []


@pytest.mark.asyncio
async def test_corrupt_schedule_is_never_adopted_or_executed():
    native = Native()
    del native.server["metadata"][usage.METADATA_PREFIX + "reason"]
    with pytest.raises(HTTPException) as error:
        await cycle(native)
    assert error.value.status_code == 409
    assert native.metadata_writes == native.actions == []
    assert scheduler._census(native, NOW) == []


@pytest.mark.asyncio
async def test_unavailable_redis_never_mutates_native_metadata_or_lifecycle():
    native = Native()
    redis = Redis()
    redis.available = False
    await cycle(native, redis)
    assert native.metadata_writes == native.actions == []


@pytest.mark.asyncio
async def test_foreign_server_or_native_token_scope_never_authorizes_write():
    native = Native()
    native.server["project_id"] = "other"
    with pytest.raises(RuntimeError):
        await cycle(native)
    native.server["project_id"] = PROJECT
    native.session.auth.get_access = lambda _: SimpleNamespace(
        project_id="executor", project_scoped=True, system_scoped=False
    )
    with pytest.raises(RuntimeError):
        await cycle(native)
    assert native.metadata_writes == native.actions == []


@pytest.mark.asyncio
async def test_extension_committed_first_wins_and_downsize_does_not_remove_schedule():
    native = Native()
    native.server["metadata"][usage.METADATA_PREFIX + "expires_at"] = (NOW + timedelta(days=3)).isoformat()
    native.flavor.vcpus = 1
    await cycle(native)
    assert native.actions == []
    assert scheduler._census(native, NOW) == []
    assert scheduler._census(native, NOW + timedelta(days=4)) == [f"{PROJECT}:{SERVER}"]


@pytest.mark.asyncio
async def test_lost_lease_between_marker_and_action_never_dispatches(monkeypatch):
    native = Native()
    original = usage.write_schedule_metadata

    async def lose_after_mark(conn, server, changes, *, lease):
        refreshed = await original(conn, server, changes, lease=lease)
        lease.lost = True
        return refreshed

    monkeypatch.setattr(usage, "write_schedule_metadata", lose_after_mark)
    with pytest.raises(DispatcherUnavailable):
        await cycle(native)
    assert state(native) == "shelve_requested" and native.actions == []


@pytest.mark.asyncio
async def test_revision_changed_after_marker_never_dispatches(monkeypatch):
    native = Native()
    original = usage.write_schedule_metadata

    async def external_change(conn, server, changes, *, lease):
        refreshed = await original(conn, server, changes, lease=lease)
        native.server["metadata"][usage.METADATA_PREFIX + "revision"] = "f" * 32
        return refreshed

    monkeypatch.setattr(usage, "write_schedule_metadata", external_change)
    with pytest.raises(RuntimeError):
        await cycle(native)
    assert native.actions == []


def test_catalog_additive_specs_require_actual_legacy_native_uuid_not_original_name():
    native = Native(schedule=False)
    native.flavor.vcpus = 1
    native.flavor.extra_specs = {"afterglow:usage_schedule_required": "true"}
    native.server["flavor"] = {"original_name": "cpu.large", "vcpus": 1, "ram": 8192, "extra_specs": {}}
    native.legacy_flavor_id = "large"
    assert scheduler._census(native, NOW) == [f"{PROJECT}:{SERVER}"]


@pytest.mark.asyncio
async def test_tick_only_leader_scans_and_fresh_owned_connection_is_closed(monkeypatch):
    census, execution = Native(), Native()
    dispatcher = SimpleNamespace(
        prefix=scheduler._PREFIX,
        redis=Redis(),
        is_leader=AsyncMock(return_value=True),
        publish=AsyncMock(),
        pending=AsyncMock(return_value=1),
        claim=AsyncMock(return_value=(f"{PROJECT}:{SERVER}", "owner")),
    )

    @asynccontextmanager
    async def work(*_args, **_kwargs):
        yield

    monkeypatch.setattr(scheduler, "work_lease", work)
    await scheduler.scheduler_tick(
        now=NOW,
        census_connection_factory=lambda: census,
        connection_factory=lambda project: execution,
        dispatcher=dispatcher,
    )
    dispatcher.publish.assert_awaited_once_with([f"{PROJECT}:{SERVER}"])
    assert census.closed and execution.closed and execution.actions == ["shelve"]
    dispatcher.is_leader.return_value = False
    dispatcher.pending.return_value = 0
    await scheduler.scheduler_tick(
        now=NOW, census_connection_factory=lambda: pytest.fail("nonleader census"), dispatcher=dispatcher
    )


@pytest.mark.asyncio
async def test_actual_dispatcher_claim_and_native_lock_prevent_duplicate_execution(_fake_redis_global, monkeypatch):
    from app.services.cache import _get_redis
    from app.services.work_dispatcher import WorkDispatcher

    redis = await _get_redis()
    prefix = "afterglow:test:usage:" + secrets.token_hex(12)
    monkeypatch.setattr(scheduler, "_PREFIX", prefix)
    native = Native()
    try:
        async with WorkDispatcher(redis, prefix, worker_id="usage-a") as first:
            async with WorkDispatcher(redis, prefix, worker_id="usage-b") as second:
                for worker in (first, second, first):
                    await scheduler.scheduler_tick(
                        now=NOW,
                        census_connection_factory=lambda: native,
                        connection_factory=lambda _: native,
                        dispatcher=worker,
                        redis=redis,
                    )
                assert native.actions == ["shelve"]
                assert state(native) == "shelve_requested"
    finally:
        keys = [key async for key in redis.scan_iter(match=prefix + ":*")]
        if keys:
            await redis.delete(*keys)


@pytest.mark.asyncio
async def test_cancelled_connection_factory_drains_and_closes_before_context_finishes():
    native = Native()
    entered, release = threading.Event(), threading.Event()

    def factory():
        entered.set()
        release.wait()
        return native

    async def own():
        async with scheduler._connection(factory):
            pytest.fail("Cancelled factory cannot enter execution")

    task = asyncio.create_task(own())
    await asyncio.to_thread(entered.wait)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert native.closed


@pytest.mark.asyncio
async def test_unknown_delete_outcome_never_reissues_delete_after_restart():
    native = Native(status="SHUTOFF", action="delete")
    native.failure = OSError("uncertain DELETE")
    with pytest.raises(OSError):
        await cycle(native)
    assert state(native) == "delete_requested"
    native.failure = None
    await cycle(native)
    assert native.actions == ["delete"]


@pytest.mark.asyncio
async def test_future_extension_committed_between_due_read_and_marker_wins(monkeypatch):
    native = Native()
    original = scheduler._mark

    async def extension_before_marker(conn, server, lease, state, error=""):
        if state == "shelve_requested":
            native.server["metadata"].update(
                {
                    usage.METADATA_PREFIX + "revision": "e" * 32,
                    usage.METADATA_PREFIX + "expires_at": (NOW + timedelta(days=10)).isoformat(),
                }
            )
        return await original(conn, server, lease, state, error)

    monkeypatch.setattr(scheduler, "_mark", extension_before_marker)
    with pytest.raises(RuntimeError):
        await cycle(native)
    assert native.actions == [] and state(native) == "active"


def test_deleted_or_recreated_catalog_flavor_does_not_hide_actual_cpu_or_ram():
    native = Native(schedule=False)
    native.server["flavor"] = {"original_name": "cpu.large", "vcpus": 12, "ram": 8192}
    native.flavor.vcpus = 1
    assert scheduler._census(native, NOW) == [f"{PROJECT}:{SERVER}"]
    native.server["flavor"] = {"original_name": "deleted", "vcpus": 1, "ram": 65536}
    native.compute.flavors = lambda **_: []
    assert scheduler._census(native, NOW) == [f"{PROJECT}:{SERVER}"]


@pytest.mark.asyncio
async def test_ownership_loss_after_flag_write_never_deletes_or_rolls_back_flags():
    native = Native(status="SHUTOFF", action="delete")
    native.add_volume(flag=True)
    update = native.update_volume_attachment

    def changed_owner(server_id, volume_id, **attrs):
        update(server_id, volume_id, **attrs)
        native.volumes[volume_id]["project_id"] = "foreign"

    native.update_volume_attachment = changed_owner
    with pytest.raises(RuntimeError):
        await cycle(native)
    assert state(native) == "volume_flags_requested"
    assert len(native.flag_writes) == 1
    assert native.attachments[0]["delete_on_termination"] is False
    assert native.actions == []


@pytest.mark.asyncio
async def test_future_schedule_with_requested_marker_is_not_dispatched():
    native = Native()
    native.server["metadata"].update(
        {
            usage.METADATA_PREFIX + "state": "shelve_requested",
            usage.METADATA_PREFIX + "expires_at": (NOW + timedelta(days=3)).isoformat(),
        }
    )
    await cycle(native)
    assert state(native) == "shelve_requested" and native.actions == []


@pytest.mark.asyncio
async def test_managed_source_volume_is_preserved_even_when_owned_clones_are_opted_in(monkeypatch):
    from app.services import instance_usage_cleanup

    native = Native(status="SHUTOFF", action="delete", delete_volumes=True)
    native.add_volume("source", flag=True)
    native.add_volume("clone", flag=False)
    prepare = AsyncMock(return_value={"source"})
    monkeypatch.setattr(instance_usage_cleanup, "prepare_managed_delete", prepare)
    await cycle(native)
    assert native.actions == ["delete"]
    flags = {item["volume_id"]: item["delete_on_termination"] for item in native.attachments}
    assert flags == {"source": False, "clone": True}
    assert prepare.await_count >= 3


@pytest.mark.asyncio
async def test_managed_preflight_failure_blocks_before_stop_or_flag_changes(monkeypatch):
    from app.services import instance_usage_cleanup

    native = Native(action="delete", delete_volumes=True)
    prepare = AsyncMock(side_effect=HTTPException(409, "Managed source receipts do not match"))
    monkeypatch.setattr(instance_usage_cleanup, "prepare_managed_delete", prepare)
    with pytest.raises(HTTPException):
        await cycle(native)
    assert native.actions == native.flag_writes == []
    assert state(native) == "blocked"


@pytest.mark.asyncio
async def test_only_proven_native_absence_triggers_immediate_managed_finish(monkeypatch):
    from app.services import instance_usage_cleanup

    native = Native(status="SHUTOFF", action="delete")
    finish = AsyncMock()
    monkeypatch.setattr(instance_usage_cleanup, "finish_managed_delete", finish)
    original = native.delete_server

    def deleted(server_id, **kwargs):
        original(server_id, **kwargs)
        native.server = None

    native.delete_server = deleted
    await cycle(native)
    assert native.actions == ["delete"]
    finish.assert_awaited_once()
    assert finish.await_args.args == (native, SERVER, PROJECT)


@pytest.mark.asyncio
async def test_resource_receipt_reconciler_is_leader_only_and_uses_fresh_factory(monkeypatch):
    from app.services import instance_usage_cleanup

    reconcile = AsyncMock()
    monkeypatch.setattr(instance_usage_cleanup, "reconcile_managed_deletes", reconcile)
    redis = Redis()

    def factory(_):
        return Native()

    dispatcher = SimpleNamespace(redis=redis, is_leader=AsyncMock(return_value=True))
    await scheduler._cleanup_tick(dispatcher, factory)
    reconcile.assert_awaited_once_with(connection_factory=factory, redis=redis)
    dispatcher.is_leader.return_value = False
    await scheduler._cleanup_tick(dispatcher, factory)
    assert reconcile.await_count == 1


@pytest.mark.asyncio
async def test_complete_offloaded_schedule_is_idle_but_native_resume_is_new_intent():
    native = Native(status="SHELVED_OFFLOADED")
    await cycle(native)
    assert state(native) == "complete"
    assert scheduler._census(native, NOW) == []
    native.server["status"] = "ACTIVE"
    assert scheduler._census(native, NOW) == [f"{PROJECT}:{SERVER}"]
    await cycle(native)
    assert native.actions == ["shelve"] and state(native) == "shelve_requested"


@pytest.mark.asyncio
async def test_pending_and_identical_blocked_states_do_not_rotate_revisions():
    native = Native(status="ERROR")
    await cycle(native)
    metadata = dict(native.server["metadata"])
    await cycle(native)
    assert native.server["metadata"] == metadata
    native.server["status"] = "ACTIVE"
    await cycle(native)
    metadata = dict(native.server["metadata"])
    metadata[usage.METADATA_PREFIX + "last_error"] = "Managed grant revocation requested; observation required"
    native.server["metadata"] = metadata
    await cycle(native)
    assert native.server["metadata"] == metadata


@pytest.mark.asyncio
async def test_uncertain_managed_grant_finalization_never_deletes_or_replays(monkeypatch):
    from app.services import instance_usage_cleanup

    native = Native(status="SHUTOFF", action="delete")
    native.add_volume(flag=True)

    async def finalize(conn, server, lease):
        assert state(native) == "delete_requested"
        assert native.attachments[0]["delete_on_termination"] is False
        native.server["metadata"][usage.METADATA_PREFIX + "last_error"] = (
            "Managed grant revocation requested; observation required"
        )
        raise HTTPException(502, "Grant revocation outcome unknown")

    finalizer = AsyncMock(side_effect=finalize)
    monkeypatch.setattr(instance_usage_cleanup, "finalize_managed_delete_preflight", finalizer)
    with pytest.raises(HTTPException):
        await cycle(native)
    metadata = dict(native.server["metadata"])
    await cycle(native)
    assert finalizer.await_count == 1
    assert native.actions == [] and state(native) == "delete_requested"
    assert native.server["metadata"] == metadata


@pytest.mark.asyncio
async def test_native_volume_flags_are_reproved_after_managed_grant_finalization(monkeypatch):
    from app.services import instance_usage_cleanup

    native = Native(status="SHUTOFF", action="delete")
    native.add_volume(flag=True)

    async def finalize(conn, server, lease):
        assert state(native) == "delete_requested"
        native.attachments[0]["delete_on_termination"] = True
        return native.get_server(SERVER)

    monkeypatch.setattr(instance_usage_cleanup, "finalize_managed_delete_preflight", finalize)
    with pytest.raises(RuntimeError):
        await cycle(native)
    assert native.actions == [] and state(native) == "delete_requested"


@pytest.mark.asyncio
async def test_deleted_reused_flavor_name_does_not_adopt_old_small_instance():
    native = Native(schedule=False)
    native.server["flavor"] = {"original_name": "cpu.large", "vcpus": 2, "ram": 8192, "extra_specs": {}}
    assert scheduler._census(native, NOW) == []
    await cycle(native)
    assert native.metadata_writes == []
    native.flavor.extra_specs = {"afterglow:usage_schedule_required": "true"}
    native.legacy_flavor_id = "deleted-flavor-uuid"
    assert scheduler._census(native, NOW) == []
    await cycle(native)
    assert native.metadata_writes == []


@pytest.mark.asyncio
async def test_modern_additive_enrollment_uses_fresh_exact_native_flavor_uuid():
    native = Native(schedule=False)
    native.flavor.vcpus = 2
    native.flavor.extra_specs = {"afterglow:usage_schedule_required": "true"}
    native.server["flavor"] = {"original_name": "old-renamed-name", "vcpus": 2, "ram": 8192, "extra_specs": {}}
    native.legacy_flavor_id = "large"
    assert scheduler._census(native, NOW) == [f"{PROJECT}:{SERVER}"]
    await cycle(native)
    assert usage.parse_schedule(native.server).source == "adopted"


@pytest.mark.asyncio
async def test_unavailable_legacy_flavor_identity_cannot_fabricate_designated_match():
    native = Native(schedule=False)
    native.flavor.vcpus = 2
    native.flavor.extra_specs = {"afterglow:usage_schedule_required": "true"}
    native.server["flavor"] = {"original_name": "cpu.large", "vcpus": 2, "ram": 8192, "extra_specs": {}}
    assert scheduler._census(native, NOW) == []
    with pytest.raises(RuntimeError, match="UUID"):
        await cycle(native)
    assert native.metadata_writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_startup_opt_in_controls_real_native_census_and_expiry(monkeypatch, _fake_redis_global, enabled):
    """Run actual startup registration, usage loop, dispatcher and native cycle."""
    from app import main
    from app.config import Settings
    from app.services import (
        auto_backup,
        auto_snapshot,
        infrastructure_fabric,
        instance_usage_cleanup,
        keystone,
        work_dispatcher,
    )

    loop = asyncio.get_running_loop()
    action_seen = asyncio.Event()
    unrelated_started = asyncio.Event()
    stop_unrelated = asyncio.Event()
    census_calls = []
    project_connections = []

    class ObservedNative(Native):
        def servers(self, **query):
            census_calls.append(query)
            return super().servers(**query)

        def _action(self, name, server_id):
            super()._action(name, server_id)
            loop.call_soon_threadsafe(action_seen.set)

    native = ObservedNative()

    def project_connection(project_id):
        project_connections.append(project_id)
        return native

    async def unrelated(*_args, **_kwargs):
        unrelated_started.set()
        await stop_unrelated.wait()

    settings = Settings().model_copy(
        update={
            "database_url": "",
            "instance_usage_scheduler_enabled": enabled,
            "monitoring_host_healthcheck_enabled": False,
            "openstack_notifications_enabled": False,
            "worker_runtime_mode": "static",
        }
    )
    monkeypatch.setattr(main, "_get_cfg", lambda: settings)
    monkeypatch.setattr(
        main,
        "_svc_cfg",
        SimpleNamespace(
            service_swift_enabled=False,
            service_mcp_enabled=False,
            service_cloud_shell_enabled=False,
        ),
    )
    monkeypatch.setattr(main, "_background_tasks", set())
    monkeypatch.setattr(auto_backup, "scheduler_loop", unrelated)
    monkeypatch.setattr(auto_snapshot, "scheduler_loop", unrelated)
    monkeypatch.setattr(infrastructure_fabric, "monitoring_loop", unrelated)
    monkeypatch.setattr(work_dispatcher, "run_roles", unrelated)
    monkeypatch.setattr(keystone, "get_admin_project_connection", lambda: native)
    monkeypatch.setattr(keystone, "get_admin_connection_for_project", project_connection)
    monkeypatch.setattr(scheduler, "_clock", lambda now=None: NOW)
    cleanup = AsyncMock()
    monkeypatch.setattr(instance_usage_cleanup, "reconcile_managed_deletes", cleanup)

    try:
        await main.start_background_workers()
        await asyncio.wait_for(unrelated_started.wait(), 2)
        names = {task.get_name() for task in main._background_tasks}
        assert ("instance-usage-dispatch" in names) is enabled
        if enabled:
            await asyncio.wait_for(action_seen.wait(), 3)
            assert census_calls == [{"details": True, "all_projects": True}]
            assert project_connections == [PROJECT]
            assert native.actions == ["shelve"]
            assert native.metadata_writes
        else:
            # Other startup tasks actually run; an accidentally registered usage
            # loop would reach the same working dispatcher/native boundary.
            await asyncio.sleep(0.03)
            assert census_calls == []
            assert project_connections == []
            assert native.metadata_writes == []
            assert native.actions == []
            cleanup.assert_not_awaited()
    finally:
        tasks = tuple(main._background_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        main._background_tasks.clear()
