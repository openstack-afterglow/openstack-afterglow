"""Durable runner/SDK regressions with SQLite and synthetic loopback OpenStack.

Console health is synthetic here; Linux kernel mounting is a separate proof.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
import yaml
from fastapi import FastAPI, HTTPException
from keystoneauth1.exceptions import ClientException
from openstack.exceptions import SDKException
from sqlalchemy import select

from app.api import deps
from app.api.union import layer_ops
from app.models.db import LayerArtifact, LayerConsume, LayerProfile
from app.services import layer_block, layer_build, layer_consume_resources
from tests.admin_gate import synthetic_verified_admin
from tests.test_layer_block import block_provider as block_provider
from tests.test_layer_consume_resources import ledger as ledger


def artifact_entry(state, entry):
    return {
        **entry,
        "name": "runtime",
        "kind": "uv",
        "sqsh_filename": "runtime.sqsh",
        "share_id": "retained-nfs",
        "ubuntu_base": "ubuntu-24.04",
        "base_image_id": state.base_image["id"],
    }


def resource_snapshot():
    return {
        "network": {"id": "network", "name": "network"},
        "flavor": {"id": "flavor", "name": "flavor"},
        "openstack.service_project": {"id": "caller", "name": "caller"},
    }


async def prepare_row(ledger, monkeypatch, entries):
    factory, consume_id = ledger
    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        row.project_id = "caller"
        row.artifact_ids = [entry["id"] for entry in entries]
        row.resource_snapshot = resource_snapshot()
        await session.commit()
    return factory, consume_id


async def run_consumer(conn, consume_id, entries, *, usage_schedule=None):
    return await layer_build.run_layer_consume(
        consume_id,
        "proof",
        "consumer",
        "flavor",
        resource_snapshot=resource_snapshot(),
        compute_conn=conn,
        resolved_artifacts=entries,
        transport="block",
        usage_schedule=usage_schedule,
    )


@pytest.mark.asyncio
async def test_unmarked_authenticated_connection_reaches_readonly_vm_and_durable_cleanup(
    ledger,
    block_provider,
    monkeypatch,
):
    conn, state, entry = block_provider
    del conn._afterglow_project_id
    entries = [artifact_entry(state, entry)]
    factory, consume_id = await prepare_row(ledger, monkeypatch, entries)
    server_id = await run_consumer(conn, consume_id, entries)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert (row.status, row.cleanup_state, row.server_id) == ("active", "active", server_id)
        layer = next(item for item in row.resources if item["kind"] == "layer")
        assert layer["state"] == "allocated"
        assert state.volumes[layer["id"]]["metadata"]["readonly"] == "True"
        assert state.volumes[layer["id"]]["attachments"] == [{"server_id": server_id}]
    mapping = state.servers[server_id]["block_device_mapping_v2"]
    layer_mapping = next(item for item in mapping if item["source_type"] == "volume")
    assert layer_mapping == {
        "boot_index": -1,
        "uuid": layer["id"],
        "source_type": "volume",
        "destination_type": "volume",
        "delete_on_termination": False,
        "disk_bus": "virtio",
        "device_type": "disk",
    }
    state.servers[server_id]["metadata"].pop("layer_transport")
    assert await layer_consume_resources.cleanup_for_server(conn, server_id, "caller") is True
    assert state.servers == state.volumes == state.ports == {}
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert (row.status, row.cleanup_state) == ("deleted", "complete")
    deletes = [call[1] for call in state.calls if call[0] == "DELETE"]
    assert [path.split("/")[-2] for path in deletes] == ["servers", "volumes", "ports"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["denied", "guest", "response-loss"])
async def test_runner_failure_reclaims_prior_allocations_without_reposting(
    ledger,
    block_provider,
    monkeypatch,
    failure,
):
    conn, state, entry = block_provider
    state.server_rejection = 403 if failure == "denied" else None
    state.guest_failure = failure == "guest"
    state.lose_server_response = failure == "response-loss"
    entries = [artifact_entry(state, entry)]
    factory, consume_id = await prepare_row(ledger, monkeypatch, entries)
    with pytest.raises((RuntimeError, SDKException, ClientException)):
        await run_consumer(conn, consume_id, entries)
    assert state.servers == state.volumes == state.ports == {}
    assert sum(call[0] == "POST" and call[1].endswith("/servers") for call in state.calls) == 1
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert (row.status, row.cleanup_state) == ("error", "complete")
        server = next(item for item in row.resources if item["kind"] == "server")
        assert server["state"] == ("rejected" if failure == "denied" else "deleted")


@pytest.mark.asyncio
async def test_heartbeat_failure_stops_source_stage_before_any_provider_create(
    ledger,
    block_provider,
    monkeypatch,
):
    conn, state, entry = block_provider
    entries = [artifact_entry(state, entry)]
    factory, consume_id = await prepare_row(ledger, monkeypatch, entries)
    source_started = asyncio.Event()

    async def slow_validation(*_args):
        source_started.set()
        await asyncio.Future()

    async def failed_heartbeat(*_args):
        await source_started.wait()
        raise RuntimeError("lease renewal unavailable")

    monkeypatch.setattr(layer_build, "validate_consume_image_identity", slow_validation)
    monkeypatch.setattr(layer_consume_resources, "heartbeat", failed_heartbeat)
    with pytest.raises(RuntimeError, match="lease renewal unavailable"):
        await run_consumer(conn, consume_id, entries)
    assert not any(call[0] == "POST" for call in state.calls)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert (row.status, row.cleanup_state, row.resources) == ("error", "complete", [])


@pytest.mark.asyncio
async def test_competing_runner_does_not_mark_claimed_run_error(ledger, block_provider, monkeypatch):
    conn, state, entry = block_provider
    entries = [artifact_entry(state, entry)]
    factory, consume_id = await prepare_row(ledger, monkeypatch, entries)
    first_run = await layer_consume_resources.begin(consume_id, "caller", [entry["id"]])
    with pytest.raises(RuntimeError):
        await run_consumer(conn, consume_id, entries)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert (row.status, row.cleanup_state, row.run_id) == ("creating", "allocating", first_run)
    assert not any(call[0] == "POST" for call in state.calls)


@pytest.mark.asyncio
async def test_expected_project_mismatch_is_rejected_before_admission_and_mutation(
    ledger,
    block_provider,
    monkeypatch,
):
    factory, _ = ledger
    conn, state, _ = block_provider
    monkeypatch.setattr(
        layer_build, "resolve_layer_consume_resource_snapshot", AsyncMock(return_value=resource_snapshot())
    )
    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    app = FastAPI()
    app.include_router(layer_ops.router, prefix="/api/v1/admin/libraries")
    app.dependency_overrides[deps.get_token_info] = lambda: {"is_system_admin": True}
    app.dependency_overrides[deps.require_admin] = synthetic_verified_admin
    app.dependency_overrides[deps.get_os_conn] = lambda: conn
    app.dependency_overrides[deps.get_admin_os_conn] = lambda: conn
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/libraries/consume",
            json={
                "profile_name": "proof",
                "flavor_id": "flavor",
                "transport": "block",
                "expected_project_id": "foreign",
            },
        )
    assert response.status_code == 400
    async with factory() as session:
        rows = (await session.execute(select(LayerConsume))).scalars().all()
        assert [row.id for row in rows] == [ledger[1]]
    assert state.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", [["child"], ["child", "parent"], ["independent", "child", "parent"]])
async def test_partial_usr_profile_preserves_precedence_and_expands_exact_ancestors(ledger, monkeypatch, profile):
    factory, _ = ledger
    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    async with factory.kw["bind"].begin() as connection:
        await connection.run_sync(lambda sync: LayerArtifact.__table__.create(sync))
        await connection.run_sync(lambda sync: LayerProfile.__table__.create(sync))
    async with factory() as session:
        for artifact_id, name, parent in [(1, "parent", None), (2, "child", 1), (3, "independent", None)]:
            session.add(
                LayerArtifact(
                    id=artifact_id,
                    name=name,
                    kind="uv",
                    parent_id=parent,
                    share_id=f"share-{artifact_id}",
                    sqsh_filename=f"{name}.sqsh",
                    is_sealed=True,
                    ubuntu_base="ubuntu-24.04",
                    base_image_id="image",
                )
            )
        session.add(LayerProfile(name="proof", layers=profile))
        await session.commit()
    entries = await layer_build.resolve_admin_consume_artifacts("proof")
    assert [entry["name"] for entry in reversed(entries)] == (["child", "parent"] if profile[0] == "child" else profile)


@pytest.mark.asyncio
async def test_parent_child_block_layers_reach_guest_in_profile_order(ledger, block_provider, monkeypatch):
    conn, state, parent = block_provider
    parent = artifact_entry(state, parent)
    child = copy.deepcopy(parent)
    child.update(id=13, parent_id=parent["id"], name="child", sqsh_filename="child.sqsh")
    payload = b"child sealed bytes"
    child.update(blob_digest="sha256:" + hashlib.sha256(payload).hexdigest(), size_bytes=len(payload))
    child["chain_id"] = (
        "sha256:" + hashlib.sha256((parent["chain_id"] + " " + child["blob_digest"]).encode()).hexdigest()
    )
    source = child["block_source"]
    source.update(layer_block.artifact_identity(child), image_id="66666666-6666-6666-6666-666666666666")
    state.extra_images[source["image_id"]] = {
        **state.image,
        "id": source["image_id"],
        "size": len(payload),
        **layer_block.source_properties(child, source),
    }
    state.payloads[source["image_id"]] = payload
    entries = [parent, child]
    _, consume_id = await prepare_row(ledger, monkeypatch, entries)
    server_id = await run_consumer(conn, consume_id, entries)
    config = yaml.safe_load(base64.b64decode(state.servers[server_id]["user_data"]))
    manifest = next(item for item in config["write_files"] if item["path"] == "/etc/afterglow/layers/proof.conf")
    labels = [line.split("|")[1] for line in base64.b64decode(manifest["content"]).decode().splitlines()]
    assert labels == ["child.sqsh", "runtime.sqsh"]
    await layer_consume_resources.cleanup(conn, consume_id, project_id="caller")
    assert state.servers == state.volumes == state.ports == {}


@pytest.mark.asyncio
async def test_api_reports_durable_pending_id_after_unknown_create(ledger, block_provider, monkeypatch):
    factory, _ = ledger
    conn, state, source_entry = block_provider
    entry = artifact_entry(state, source_entry)
    state.server_rejection = 503
    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.services.keystone.get_admin_connection_for_project", lambda _project: conn)
    monkeypatch.setattr(
        layer_build, "resolve_layer_consume_resource_snapshot", AsyncMock(return_value=resource_snapshot())
    )
    monkeypatch.setattr(layer_build, "resolve_admin_consume_artifacts", AsyncMock(return_value=[entry]))
    app = FastAPI()
    app.include_router(layer_ops.router, prefix="/api/v1/admin/libraries")
    app.dependency_overrides[deps.get_token_info] = lambda: {"is_system_admin": True}
    app.dependency_overrides[deps.require_admin] = synthetic_verified_admin
    app.dependency_overrides[deps.get_os_conn] = lambda: conn
    app.dependency_overrides[deps.get_admin_os_conn] = lambda: conn
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/libraries/consume",
            json={
                "profile_name": "proof",
                "flavor_id": "flavor",
                "transport": "block",
                "expected_project_id": "caller",
                "server_name": "consumer",
            },
        )
    assert response.status_code == 502
    failure = response.json()["detail"]
    async with factory() as session:
        row = await session.get(LayerConsume, failure["consume_id"])
        assert row.cleanup_state == failure["cleanup_state"] == "pending"
        assert row.status == failure["status"] == "error"
        server = next(item for item in row.resources if item["kind"] == "server")
        assert (server["state"], server["id"]) == ("intent", None)
    assert state.volumes and state.ports
    assert not any(call[0] == "DELETE" for call in state.calls)
    assert sum(call[0] == "POST" and call[1].endswith("/servers") for call in state.calls) == 1


@pytest.mark.asyncio
async def test_completed_unclaimed_admission_cleanup_needs_no_cloud_connection(ledger, monkeypatch):
    factory, consume_id = ledger
    monkeypatch.setattr(layer_ops, "get_session_factory", lambda: factory)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        row.status = "error"
        row.cleanup_state = "complete"
        await session.commit()
    app = FastAPI()
    app.include_router(layer_ops.router, prefix="/api/v1/admin/libraries")
    app.dependency_overrides[deps.get_token_info] = lambda: {"is_system_admin": True}
    app.dependency_overrides[deps.require_admin] = synthetic_verified_admin
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = await client.delete(f"/api/v1/admin/libraries/consumes/{consume_id}")
        repeated = await client.delete(f"/api/v1/admin/libraries/consumes/{consume_id}")
    assert first.status_code == repeated.status_code == 200
    assert first.json()["cleanup_state"] == repeated.json()["cleanup_state"] == "complete"
    assert first.json()["status"] == repeated.json()["status"] == "error"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "flavor_change,schedule_request",
    [
        ({"vcpus": 12}, None),
        ({"ram": 65536}, None),
        ({"extra_specs": {"resources:VGPU": "1"}}, None),
        ({"extra_specs": {"afterglow:usage_schedule_required": "true"}}, None),
        ({"vcpus": 12}, {"expires_at": "2001-01-01T00:00:00Z"}),
        ({"vcpus": 12}, {"delete_volumes": True}),
        ({"vcpus": 12}, {"expires_at": "2099-01-01T00:00:00Z"}),
    ],
)
async def test_native_consumer_invalid_schedule_rejects_before_allocations(
    ledger, block_provider, monkeypatch, flavor_change, schedule_request
):
    conn, state, entry = block_provider
    state.flavor.update(flavor_change)
    entries = [artifact_entry(state, entry)]
    _, consume_id = await prepare_row(ledger, monkeypatch, entries)
    with pytest.raises(HTTPException) as error:
        await run_consumer(conn, consume_id, entries, usage_schedule=schedule_request)
    assert error.value.status_code == 422
    assert not any(call[0] == "POST" for call in state.calls)
    assert state.servers == state.volumes == state.ports == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit,delete_volumes", [(False, False), (True, False), (True, True)])
async def test_native_consumer_first_create_contains_calendar_schedule_and_lineage(
    ledger, block_provider, monkeypatch, explicit, delete_volumes
):
    from app.services import instance_usage

    conn, state, entry = block_provider
    state.flavor["vcpus"] = 12
    entries = [artifact_entry(state, entry)]
    _, consume_id = await prepare_row(ledger, monkeypatch, entries)
    created = datetime(2032, 1, 31, 10, 15, tzinfo=UTC)
    monkeypatch.setattr(instance_usage, "_clock", lambda now=None: now or created)
    request = (
        {
            "expires_at": "2032-03-31T10:15:00Z",
            "reason": "Semester research",
            "expiry_action": "delete",
            "delete_volumes": delete_volumes,
        }
        if explicit
        else {}
    )
    server_id = await run_consumer(conn, consume_id, entries, usage_schedule=request)
    creates = [call for call in state.calls if call[0] == "POST" and call[1].endswith("/servers")]
    assert len(creates) == 1
    metadata = creates[0][2]["server"]["metadata"]
    schedule = instance_usage.parse_schedule({"id": server_id, "metadata": metadata})
    assert schedule.starts_at == created.isoformat()
    assert schedule.expires_at == ("2032-03-31T10:15:00+00:00" if explicit else "2032-02-29T10:15:00+00:00")
    assert schedule.reason == ("Semester research" if explicit else "")
    assert schedule.delete_volumes is delete_volumes
    assert schedule.expiry_action == ("delete" if explicit else "shelve")
    assert metadata["afterglow_managed"] == "true"
    assert metadata["afterglow_consume_id"] == str(consume_id)
    assert metadata["layer_profile"] == "proof" and metadata["layer_transport"] == "block"
    assert metadata["base_image_id"] == state.base_image["id"]


@pytest.mark.asyncio
async def test_native_consumer_expiry_elapsed_during_allocation_never_posts_server(ledger, block_provider, monkeypatch):
    from app.services import instance_usage

    conn, state, entry = block_provider
    state.flavor["vcpus"] = 12
    entries = [artifact_entry(state, entry)]
    _, consume_id = await prepare_row(ledger, monkeypatch, entries)
    clock = [datetime(2032, 1, 31, 10, 15, tzinfo=UTC)]
    monkeypatch.setattr(instance_usage, "_clock", lambda now=None: now or clock[0])
    render = layer_build.render_layer_consume_user_data

    def delayed_render(*args, **kwargs):
        clock[0] += timedelta(minutes=2)
        return render(*args, **kwargs)

    monkeypatch.setattr(layer_build, "render_layer_consume_user_data", delayed_render)
    with pytest.raises(HTTPException) as error:
        await run_consumer(conn, consume_id, entries, usage_schedule={"expires_at": "2032-01-31T10:16:00Z"})
    assert error.value.status_code == 422
    assert not any(call[0] == "POST" and call[1].endswith("/servers") for call in state.calls)
    assert state.servers == state.volumes == state.ports == {}


@pytest.mark.asyncio
async def test_native_consumer_expiry_during_server_intent_never_posts_server(ledger, block_provider, monkeypatch):
    from app.services import instance_usage

    conn, state, entry = block_provider
    entries = [artifact_entry(state, entry)]
    _, consume_id = await prepare_row(ledger, monkeypatch, entries)
    clock = [datetime(2032, 1, 31, 10, 15, tzinfo=UTC)]
    monkeypatch.setattr(instance_usage, "_clock", lambda now=None: now or clock[0])
    record = layer_consume_resources.record
    server_intents = []

    async def delayed_record(*args, **kwargs):
        result = await record(*args, **kwargs)
        if kwargs["kind"] == "server" and kwargs.get("resource_id") is None:
            server_intents.append(True)
            clock[0] += timedelta(minutes=2)
        return result

    monkeypatch.setattr(layer_consume_resources, "record", delayed_record)
    with pytest.raises(HTTPException) as error:
        await run_consumer(conn, consume_id, entries, usage_schedule={"expires_at": "2032-01-31T10:16:00Z"})
    assert error.value.status_code == 422
    assert server_intents == [True]
    assert not any(call[0] == "POST" and call[1].endswith("/servers") for call in state.calls)
    assert state.servers == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["catalog", "consumer"])
@pytest.mark.parametrize(
    "status,envelope,accepted",
    [
        (200, {}, False),
        (200, {"extra_specs": None}, False),
        (200, {"extra_specs": []}, False),
        (200, {"extra_specs": {"resources:VGPU": 1}}, False),
        (307, {"extra_specs": {}}, False),
        (200, {"extra_specs": {}}, True),
    ],
)
async def test_native_flavor_specs_missing_envelope_never_becomes_empty_authority(
    ledger, block_provider, monkeypatch, path, status, envelope, accepted
):
    from app.services import nova

    conn, state, entry = block_provider
    state.flavor.pop("extra_specs")
    state.flavor_specs_status = status
    state.flavor_specs_response = envelope
    entries = [artifact_entry(state, entry)]
    _, consume_id = await prepare_row(ledger, monkeypatch, entries)

    async def execute():
        if path == "catalog":
            flavors = await asyncio.to_thread(nova.list_flavors, conn)
            assert len(flavors) == 1
            assert flavors[0].extra_specs == {}
            assert flavors[0].usage_schedule_required is False
        else:
            server_id = await run_consumer(conn, consume_id, entries)
            assert server_id in state.servers

    if accepted:
        await execute()
    else:
        with pytest.raises(HTTPException) as error:
            await execute()
        assert error.value.status_code == 503
        assert not any(call[0] == "POST" for call in state.calls)
        assert state.servers == state.volumes == state.ports == {}
    reads = [call for call in state.calls if call[0] == "GET" and "/os-extra_specs" in call[1]]
    assert len(reads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["catalog", "consumer"])
async def test_native_flavor_explicit_empty_specs_need_no_fallback_get(ledger, block_provider, monkeypatch, path):
    from app.services import nova

    conn, state, entry = block_provider
    state.flavor["extra_specs"] = {}
    state.flavor_specs_response = {}
    entries = [artifact_entry(state, entry)]
    _, consume_id = await prepare_row(ledger, monkeypatch, entries)
    if path == "catalog":
        flavors = await asyncio.to_thread(nova.list_flavors, conn)
        assert len(flavors) == 1 and flavors[0].extra_specs == {}
    else:
        server_id = await run_consumer(conn, consume_id, entries)
        assert server_id in state.servers
    assert not any(call[0] == "GET" and "/os-extra_specs" in call[1] for call in state.calls)
