from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from openstack.exceptions import ResourceNotFound
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import LayerConsume
from app.models.instance_usage import UsageScheduleRequest
from app.services import instance_usage as usage
from app.services import instance_usage_cleanup as cleanup
from app.services import layer_consume_resources as resources

PROJECT = "d" * 32
SERVER = "11111111-1111-4111-8111-111111111111"
LAYER = "22222222-2222-4222-8222-222222222222"
UPPER = "33333333-3333-4333-8333-333333333333"
PORT = "44444444-4444-4444-8444-444444444444"
RUN = "a" * 32


class Native:
    def __init__(self):
        self.deleted = []
        self.server = SimpleNamespace(id=SERVER, project_id=PROJECT, status="SHUTOFF", task_state=None, metadata={})
        self.volumes = {
            identity: SimpleNamespace(
                id=identity,
                project_id=PROJECT,
                status="in-use",
                attachments=[{"server_id": SERVER}],
                is_multiattach=False,
            )
            for identity in (LAYER, UPPER)
        }
        self.attachments = [
            SimpleNamespace(volume_id=identity, delete_on_termination=False) for identity in self.volumes
        ]
        self.ports = {}
        self.compute = SimpleNamespace(
            get_server=self.get_server,
            volume_attachments=lambda _: self.attachments,
            delete_server=self.delete_server,
            request=Mock(),
        )
        self.block = SimpleNamespace(get_volume=self.get_volume, delete_volume=self.delete_volume, request=Mock())
        self.network = SimpleNamespace(
            get_port=self.get_port, delete_port=self.delete_port, ips=lambda **_: [], request=Mock()
        )
        self.conn = SimpleNamespace(
            compute=self.compute,
            block_storage=self.block,
            network=self.network,
            _afterglow_project_id=PROJECT,
            _afterglow_authenticated_project_id=PROJECT,
            session=SimpleNamespace(get_project_id=lambda: PROJECT),
        )
        self.lease = SimpleNamespace(current=AsyncMock(return_value=True))

    def get_server(self, identity):
        assert identity == SERVER
        if self.server is None:
            raise ResourceNotFound("missing")
        return self.server

    def get_volume(self, identity):
        if identity not in self.volumes:
            raise ResourceNotFound("missing")
        return self.volumes[identity]

    def get_port(self, identity):
        if identity not in self.ports:
            raise ResourceNotFound("missing")
        return self.ports[identity]

    def delete_server(self, identity, **_):
        self.deleted.append(("server", identity))
        self.server = None
        for volume in self.volumes.values():
            volume.attachments = []
            volume.status = "available"

    def delete_volume(self, identity, **_):
        self.deleted.append(("volume", identity))
        self.volumes.pop(identity)

    def delete_port(self, identity, **_):
        self.deleted.append(("port", identity))
        self.ports.pop(identity)


@pytest.fixture
async def managed(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(LayerConsume.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(cleanup, "get_session_factory", lambda: factory)
    monkeypatch.setattr(resources, "get_session_factory", lambda: factory)
    monkeypatch.setattr(usage, "safe_compute_proxy", lambda conn: conn.compute)
    monkeypatch.setattr(cleanup, "_revoke_health", AsyncMock())
    native = Native()
    metadata = usage.creation_metadata(
        {}, UsageScheduleRequest(expiry_action="delete"), now=datetime(2026, 1, 1, tzinfo=UTC)
    )
    metadata[usage.METADATA_PREFIX + "state"] = "delete_requested"
    async with factory() as session:
        row = LayerConsume(
            profile_name="proof",
            share_id="",
            project_id=PROJECT,
            server_id=SERVER,
            transport="block",
            run_id=RUN,
            artifact_ids=[1],
            cleanup_state="active",
            status="active",
        )
        session.add(row)
        await session.flush()
        marker = resources.run_metadata(row.id, RUN, PROJECT)
        for volume in native.volumes.values():
            volume.metadata = dict(marker)
        row.resources = [
            dict(kind=kind, id=identity, name=kind, metadata=marker, state="allocated")
            for kind, identity in (("server", SERVER), ("layer", LAYER), ("upper", UPPER))
        ]
        native.server.metadata = {**metadata, **marker, "layer_transport": "block"}
        native.server.metadata["afterglow_managed"] = "true"
        await session.commit()
        consume_id = row.id

    async def write_metadata(conn, server, changes, *, lease):
        assert await lease.current()
        native.server.metadata.update(changes)
        return native.server

    monkeypatch.setattr(usage, "write_schedule_metadata", write_metadata)
    yield native, factory, consume_id
    await engine.dispose()


async def arm(native, *, delete=False):
    native.server.metadata[usage.METADATA_PREFIX + "delete_volumes"] = str(delete).lower()
    await cleanup.prepare_managed_delete(native.conn, native.server, delete, native.lease)
    await cleanup.finalize_managed_delete_preflight(native.conn, native.server, native.lease)


async def test_retention_armed_before_absence_blocks_intervening_reclaimer(managed):
    native, factory, consume_id = managed
    await arm(native)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        receipt = row.resource_snapshot[cleanup.RECEIPT]
        assert receipt["retained_volume_ids"] == sorted([LAYER, UPPER])
        assert receipt["baseline_delete_on_termination"] == {LAYER: False, UPPER: False}
        assert not receipt["complete"]
    native.delete_server(SERVER)
    # The background block reclaimer may win the race before the usage finisher.
    with pytest.raises(RuntimeError, match="exact native absence"):
        await resources.cleanup(native.conn, consume_id, project_id=PROJECT, automatic=True)
    assert set(native.volumes) == {LAYER, UPPER}
    await cleanup.finish_managed_delete(native.conn, SERVER, PROJECT, native.lease)
    await resources.cleanup(native.conn, consume_id, project_id=PROJECT, automatic=True)
    assert native.deleted == [("server", SERVER)]
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.cleanup_state == "complete"
        assert {item["id"] for item in row.resources if item["state"] == "retained"} == {LAYER, UPPER}
        assert row.resource_snapshot[cleanup.RECEIPT]["retained_source_volume_ids"] == sorted([LAYER, UPPER])
        from app.api.union.layer_ops import _is_blocking_consume

        assert _is_blocking_consume(row)
    # An outside owner may delete a kept clone, but an overlay upper still
    # depends on the immutable lower stack. Release only when both are gone.
    native.volumes.pop(LAYER)
    await cleanup.finish_managed_delete(native.conn, SERVER, PROJECT, native.lease)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.resource_snapshot[cleanup.RECEIPT]["retained_source_volume_ids"] == [UPPER]
        assert _is_blocking_consume(row)
    assert UPPER in native.volumes
    native.volumes.pop(UPPER)
    await cleanup.finish_managed_delete(native.conn, SERVER, PROJECT, native.lease)
    async with factory() as session:
        assert not _is_blocking_consume(await session.get(LayerConsume, consume_id))


async def test_explicit_consent_observes_nova_deleted_disks_never_cinder_replays(managed):
    native, factory, consume_id = managed
    await arm(native, delete=True)
    native.delete_server(SERVER)
    with pytest.raises(RuntimeError, match="Nova volume deletion is not confirmed"):
        await cleanup.finish_managed_delete(native.conn, SERVER, PROJECT, native.lease)
    assert native.deleted == [("server", SERVER)]
    native.volumes.clear()  # Native Nova BDM completion, not helper compensation.
    await cleanup.finish_managed_delete(native.conn, SERVER, PROJECT, native.lease)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.resource_snapshot[cleanup.RECEIPT]["complete"]
        assert all(item["state"] == "deleted" for item in row.resources)
    assert native.deleted == [("server", SERVER)]


@pytest.mark.parametrize("failure", ["foreign", "multiattach", "attachments", "unknown_flag"])
async def test_prepare_rejects_ambiguous_or_foreign_volume_before_arming(managed, failure):
    native, factory, consume_id = managed
    if failure == "foreign":
        native.volumes[LAYER].project_id = "foreign"
    elif failure == "multiattach":
        native.volumes[LAYER].is_multiattach = True
    elif failure == "attachments":
        native.volumes[LAYER].attachments.append({"server_id": "another"})
    else:
        native.attachments[0].delete_on_termination = None
    with pytest.raises(RuntimeError):
        await cleanup.prepare_managed_delete(native.conn, native.server, False, native.lease)
    async with factory() as session:
        assert cleanup.RECEIPT not in ((await session.get(LayerConsume, consume_id)).resource_snapshot or {})
    assert native.deleted == []


async def test_prepare_then_extension_leaves_original_explicit_delete_usable(managed, monkeypatch):
    native, factory, consume_id = managed
    await cleanup.prepare_managed_delete(native.conn, native.server, False, native.lease)
    async with factory() as session:
        assert cleanup.RECEIPT not in ((await session.get(LayerConsume, consume_id)).resource_snapshot or {})
    native.server.metadata[usage.METADATA_PREFIX + "state"] = "active"
    native.server.metadata[usage.METADATA_PREFIX + "expires_at"] = "2030-01-01T00:00:00+00:00"
    monkeypatch.setattr(resources.neutron, "cleanup_instance_fips", Mock())
    await resources.cleanup(native.conn, consume_id, project_id=PROJECT)
    assert native.deleted == [("server", SERVER), ("volume", LAYER), ("volume", UPPER)]


async def test_cloud_read_unknown_never_becomes_absence_or_replays_delete(managed):
    native, factory, consume_id = managed
    await arm(native)
    native.compute.get_server = Mock(side_effect=TimeoutError("read lost"))
    with pytest.raises(TimeoutError):
        await cleanup.finish_managed_delete(native.conn, SERVER, PROJECT, native.lease)
    async with factory() as session:
        assert not (await session.get(LayerConsume, consume_id)).resource_snapshot[cleanup.RECEIPT]["complete"]
    assert native.deleted == []


async def test_null_get_is_not_native_absence(managed):
    native, _, _ = managed
    await arm(native)
    native.compute.get_server = lambda _: None
    with pytest.raises(RuntimeError, match="absence is not proven"):
        await cleanup.finish_managed_delete(native.conn, SERVER, PROJECT, native.lease)
    assert native.deleted == []


async def test_plain_vm_needs_no_database(monkeypatch):
    native = Native()
    monkeypatch.setattr(cleanup, "get_session_factory", lambda: None)
    assert await cleanup.prepare_managed_delete(native.conn, native.server, False, native.lease) == set()


async def test_metadata_grant_uncertain_deny_is_never_replayed(managed, monkeypatch):
    import json

    from app.services import manila

    native, _, _ = managed
    grant = dict(s="share", i="rule", t="ip", a="10.0.0.2", l="rw", m=True)
    native.server.metadata[manila.INSTANCE_STORAGE_GRANT_PREFIX + "proof"] = json.dumps(grant)
    monkeypatch.setattr(manila, "get_file_storage", lambda *_: SimpleNamespace(id="share", project_id=PROJECT))
    rule = dict(
        id="rule", access_type="ip", access_to="10.0.0.2", access_level="rw", metadata={"afterglow_instance_id": SERVER}
    )
    getter = Mock(return_value=rule)
    monkeypatch.setattr(manila, "get_access_rule", getter)
    deny = Mock(side_effect=TimeoutError("reply lost"))
    monkeypatch.setattr(manila, "revoke_access_rule", deny)
    with pytest.raises(TimeoutError):
        await cleanup.finalize_managed_delete_preflight(native.conn, native.server, native.lease)
    with pytest.raises(RuntimeError, match="no automatic replay"):
        await cleanup.finalize_managed_delete_preflight(native.conn, native.server, native.lease)
    assert deny.call_count == 1
    getter.return_value = None
    await cleanup.finalize_managed_delete_preflight(native.conn, native.server, native.lease)
    assert deny.call_count == 1
    assert native.deleted == []


async def test_port_unknown_delete_observed_after_restart_without_replay(managed):
    native, factory, consume_id = managed
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        row.resources = [
            *row.resources,
            dict(
                kind="port",
                id=PORT,
                name="port",
                state="allocated",
                metadata=resources.run_metadata(consume_id, RUN, PROJECT),
            ),
        ]
        await session.commit()
    native.ports[PORT] = SimpleNamespace(id=PORT, project_id=PROJECT, device_id="")
    await arm(native)
    native.delete_server(SERVER)
    actual = native.network.delete_port

    def lost(identity, **kwargs):
        actual(identity, **kwargs)
        raise TimeoutError("reply lost")

    native.network.delete_port = lost
    with pytest.raises(TimeoutError):
        await cleanup.finish_managed_delete(native.conn, SERVER, PROJECT, native.lease)
    await cleanup.finish_managed_delete(native.conn, SERVER, PROJECT, native.lease)
    assert native.deleted.count(("port", PORT)) == 1
    assert set(native.volumes) == {LAYER, UPPER}


@pytest.mark.parametrize(
    "payload",
    [
        {"instance_id": SERVER, "project_id": "foreign"},
        {"instance_id": "legacy-health-id", "project_id": PROJECT},
        {"instance_id": "another-vm", "project_id": PROJECT},
    ],
)
async def test_foreign_or_unbound_health_receipt_never_revokes(monkeypatch, payload):
    import json

    from app.services import instance_health

    health_id = payload["instance_id"]
    redis = SimpleNamespace(
        get=AsyncMock(side_effect=["secret-token", json.dumps(payload)]), eval=AsyncMock(), delete=AsyncMock()
    )
    monkeypatch.setattr(instance_health, "_redis", AsyncMock(return_value=redis))
    with pytest.raises(RuntimeError, match="owner differs|exact native server binding"):
        await cleanup._revoke_health(health_id, PROJECT, SERVER)
    redis.delete.assert_not_awaited()
    redis.eval.assert_not_awaited()


async def test_exact_health_receipt_revokes_and_confirms(monkeypatch):
    import json

    from app.services import instance_health

    redis = SimpleNamespace(
        get=AsyncMock(
            side_effect=["secret-token", json.dumps({"instance_id": SERVER, "project_id": PROJECT}), None, None]
        ),
        eval=AsyncMock(return_value=1),
    )
    monkeypatch.setattr(instance_health, "_redis", AsyncMock(return_value=redis))
    await cleanup._revoke_health(SERVER, PROJECT, SERVER)
    redis.eval.assert_awaited_once()


@pytest.mark.parametrize("catalog", [False, True])
async def test_nfs_catalog_keep_upper_revokes_exact_rule_preserves_source_refs(managed, monkeypatch, catalog):
    from fastapi import HTTPException

    from app.services import manila, palimpsest_catalog_cleanup

    native, factory, consume_id = managed
    grant = dict(s="source-share", i="source-rule", t="ip", a="10.0.0.9", l="ro", m=True)
    details = dict(port_ids=[], managed_volume_ids=[UPPER], rules=[grant], share_project_id=PROJECT)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        row.transport = "nfs"
        row.resources = {}
        row.resource_snapshot = {"catalog_revision": "immutable"} if catalog else {}
        await session.commit()
    native.server.metadata["layer_transport"] = "nfs"
    if catalog:
        monkeypatch.setattr(cleanup, "_catalog_preflight", AsyncMock(return_value=details))
        monkeypatch.setattr("app.services.palimpsest_catalog.get_session_factory", lambda: factory)
        monkeypatch.setattr(palimpsest_catalog_cleanup, "_authority", AsyncMock())
    else:
        monkeypatch.setattr(cleanup, "_nfs_receipt", AsyncMock(return_value=details))
    present = {"rule": True}
    rule = dict(id=grant["i"], access_type="ip", access_to=grant["a"], access_level="ro")
    monkeypatch.setattr(manila, "get_file_storage", lambda *_: SimpleNamespace(id=grant["s"], project_id=PROJECT))
    monkeypatch.setattr(manila, "get_access_rule", lambda *_: rule if present["rule"] else None)
    deny = Mock(side_effect=lambda *_: present.update(rule=False))
    monkeypatch.setattr(manila, "revoke_access_rule", deny)
    await arm(native)
    assert deny.call_count == 0  # Never revoke before native server absence.
    native.delete_server(SERVER)
    if catalog:
        with pytest.raises(HTTPException) as blocked:
            await palimpsest_catalog_cleanup.cleanup_consume(
                native.conn, consume_id, {"project_id": PROJECT}, delete_server=False
            )
        assert blocked.value.status_code == 409
    await cleanup.finish_managed_delete(native.conn, SERVER, PROJECT, native.lease)
    assert deny.call_count == 1
    assert set(native.volumes) == {LAYER, UPPER}
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.status == "deleted"
        assert row.resource_snapshot[cleanup.RECEIPT]["retained_source_volume_ids"] == [UPPER]
        if catalog:
            assert row.resources["catalog_retained_volume_ids"] == [UPPER]
    await cleanup.finish_managed_delete(native.conn, SERVER, PROJECT, native.lease)
    assert deny.call_count == 1


async def test_rotated_health_receipt_fails_closed_without_deleting_new_credential(monkeypatch):
    import json

    from app.services import instance_health

    redis = SimpleNamespace(
        get=AsyncMock(side_effect=["old-token", json.dumps({"instance_id": SERVER, "project_id": PROJECT})]),
        eval=AsyncMock(return_value=0),
        delete=AsyncMock(),
    )
    monkeypatch.setattr(instance_health, "_redis", AsyncMock(return_value=redis))
    with pytest.raises(RuntimeError, match="changed or is not confirmed"):
        await cleanup._revoke_health(SERVER, PROJECT, SERVER)
    redis.delete.assert_not_awaited()


@pytest.mark.parametrize("reuse", ["reattached", "deleted", "transferred"])
async def test_retained_disk_reuse_does_not_strand_other_cleanup(managed, reuse):
    native, factory, consume_id = managed
    await arm(native)
    native.delete_server(SERVER)
    if reuse == "reattached":
        native.volumes[UPPER].attachments = [{"server_id": "new-owner-vm"}]
    elif reuse == "deleted":
        native.volumes.pop(UPPER)
    else:
        native.volumes[UPPER].project_id = "transferred-project"
    await cleanup.finish_managed_delete(native.conn, SERVER, PROJECT, native.lease)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.cleanup_state == "complete"
        assert row.resource_snapshot[cleanup.RECEIPT]["complete"]
    assert native.deleted == [("server", SERVER)]


async def test_union_metadata_without_consume_needs_no_database(monkeypatch):
    native = Native()
    native.server.metadata = {
        "union_strategy": "dynamic",
        "union_share_ids": "shared-data",
        "union_upper_volume_id": UPPER,
    }
    monkeypatch.setattr(cleanup, "get_session_factory", lambda: None)
    assert await cleanup.prepare_managed_delete(native.conn, native.server, False, native.lease) == set()


async def test_legacy_name_only_union_rule_blocks_without_revoking(monkeypatch):
    from app.services import keystone, manila

    native = Native()
    native.server.name = "legacy-name"
    native.server.metadata = {"union_strategy": "prebuilt", "union_share_ids": "shared-source"}
    native.conn.session.auth = SimpleNamespace(
        get_access=lambda _: SimpleNamespace(project_id=PROJECT, project_scoped=True, system_scoped=False)
    )
    native.conn.close = Mock()
    monkeypatch.setattr(keystone, "get_service_project_connection", lambda: native.conn)
    monkeypatch.setattr(manila, "get_file_storage", lambda *_: SimpleNamespace(id="shared-source", project_id=PROJECT))
    monkeypatch.setattr(
        manila,
        "list_access_rules",
        lambda *_, **__: [{"id": "legacy-rule", "access_type": "cephx", "access_to": "union-ro-legacy-name-random"}],
    )
    deny = Mock()
    monkeypatch.setattr(manila, "revoke_access_rule", deny)
    with pytest.raises(RuntimeError, match="lacks an exact instance ownership receipt"):
        await cleanup.prepare_managed_delete(native.conn, native.server, False, native.lease)
    deny.assert_not_called()
    assert native.deleted == []
