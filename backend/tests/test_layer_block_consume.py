"""Durable runner/SDK regressions with SQLite and synthetic loopback OpenStack.

Console health is synthetic here; Linux kernel mounting is a separate proof.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
from unittest.mock import AsyncMock

import httpx
import pytest
import yaml
from fastapi import FastAPI
from keystoneauth1.exceptions import ClientException
from openstack.exceptions import SDKException
from sqlalchemy import select

from app.api import deps
from app.api.union import layer_ops
from app.models.db import LayerArtifact, LayerConsume, LayerProfile
from app.services import layer_block, layer_build, layer_consume_resources
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


async def run_consumer(conn, consume_id, entries):
    return await layer_build.run_layer_consume(
        consume_id,
        "proof",
        "consumer",
        "flavor",
        resource_snapshot=resource_snapshot(),
        compute_conn=conn,
        resolved_artifacts=entries,
        transport="block",
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
    app.dependency_overrides[deps.get_os_conn] = lambda: conn
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
    app.dependency_overrides[deps.get_os_conn] = lambda: conn
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
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = await client.delete(f"/api/v1/admin/libraries/consumes/{consume_id}")
        repeated = await client.delete(f"/api/v1/admin/libraries/consumes/{consume_id}")
    assert first.status_code == repeated.status_code == 200
    assert first.json()["cleanup_state"] == repeated.json()["cleanup_state"] == "complete"
    assert first.json()["status"] == repeated.json()["status"] == "error"
