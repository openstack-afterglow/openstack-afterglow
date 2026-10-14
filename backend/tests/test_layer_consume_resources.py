from __future__ import annotations

import json
import socket
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from keystoneauth1.session import Session
from keystoneauth1.token_endpoint import Token
from openstack.connection import Connection
from openstack.exceptions import HttpException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import LayerConsume
from app.services import layer_consume_resources as resources
from tests.test_layer_block import block_provider as block_provider

PROJECT = "d" * 32
VM_ID = "11111111-1111-4111-8111-111111111111"
LAYER_ID = "22222222-2222-4222-8222-222222222222"
PORT_ID = "33333333-3333-4333-8333-333333333333"
OTHER_ID = "44444444-4444-4444-8444-444444444444"


class ProjectToken(Token):
    def get_project_id(self, session):
        return PROJECT


@pytest.fixture
async def ledger(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: LayerConsume.__table__.create(sync))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(resources, "get_session_factory", lambda: factory)
    async with factory() as session:
        row = LayerConsume(
            profile_name="proof",
            share_id="",
            project_id=PROJECT,
            artifact_ids=[1],
            status="creating",
            transport="block",
        )
        session.add(row)
        await session.commit()
        consume_id = row.id
    yield factory, consume_id
    await engine.dispose()


@pytest.fixture
def provider():
    state = {
        "volumes": {},
        "servers": {},
        "ports": {},
        "floatingips": {},
        "deleted": [],
        "posts": [],
        "create_status": 202,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path.rstrip("/") in {"/v2.1", "/v2.0", "/v3", "/v3/" + PROJECT}:
                version = "v3.0" if path.startswith("/v3") else "v2.1" if path.startswith("/v2.1") else "v2.0"
                self.reply(
                    200,
                    {
                        "version": {
                            "id": version,
                            "status": "CURRENT",
                            "min_version": "3.0" if version == "v3.0" else "2.0",
                            "version": "3.70" if version == "v3.0" else "2.99",
                            "links": [{"rel": "self", "href": url + path.rstrip("/") + "/"}],
                        }
                    },
                )
                return
            kind = next((kind for kind in ("volumes", "servers", "ports", "floatingips") if f"/{kind}" in path), None)
            if kind is None:
                self.reply(404, {})
                return
            resource_id = path.rsplit("/", 1)[-1]
            if resource_id in {kind, "detail"}:
                self.reply(200, {kind: list(state[kind].values())})
            elif resource_id in state[kind]:
                self.reply(200, {kind[:-1]: state[kind][resource_id]})
            else:
                self.reply(404, {"itemNotFound": {"message": "missing", "code": 404}})

        def do_POST(self):
            kind = next(kind for kind in ("volumes", "servers", "ports") if f"/{kind}" in self.path)
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["posts"].append((kind, payload))
            if state["create_status"] >= 400:
                if state.get("rejection_gate"):
                    state["rejection_started"].set()
                    if not state["rejection_gate"].wait(timeout=10):
                        raise TimeoutError("rejection barrier not released")
                self.reply(state["create_status"], {"error": {"message": "synthetic rejection"}})
                return
            resource_id = {"volumes": LAYER_ID, "servers": VM_ID, "ports": PORT_ID}[kind]
            resource = {
                **payload[kind[:-1]],
                "id": resource_id,
                "project_id": PROJECT,
                "tenant_id": PROJECT,
                "os-vol-tenant-attr:tenant_id": PROJECT,
                "status": "available",
                "attachments": [],
                "device_id": "",
            }
            state[kind][resource_id] = resource
            if state.get("response_loss"):
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                self.close_connection = True
                return
            response = dict(resource)
            if "response_id" in state:
                response["id"] = state["response_id"]
            self.reply(state["create_status"], {kind[:-1]: response})

        def do_DELETE(self):
            path = self.path.split("?", 1)[0]
            kind = next(kind for kind in ("volumes", "servers", "ports", "floatingips") if f"/{kind}/" in path)
            resource_id = path.rsplit("/", 1)[-1]
            if kind == "floatingips" and state.get("fip_delete_status"):
                self.reply(state["fip_delete_status"], {"error": {"message": "synthetic deletion rejection"}})
                return
            if kind == "volumes" and state.get("delete_gate"):
                state["delete_started"].set()
                if not state["delete_gate"].wait(timeout=10):
                    raise TimeoutError("deletion barrier not released")
            state[kind].pop(resource_id, None)
            state["deleted"].append((kind, resource_id))
            if kind == "servers":
                for volume in state["volumes"].values():
                    volume["attachments"] = []
                    volume["status"] = "available"
                for port in state["ports"].values():
                    port["device_id"] = ""
            self.reply(204, None)

        def reply(self, status, body):
            payload = json.dumps(body).encode() if body is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    conn = Connection(
        session=Session(auth=ProjectToken(endpoint=url, token="synthetic")),
        block_storage_endpoint_override=url + "/v3/" + PROJECT,
        block_storage_api_version="3",
        compute_endpoint_override=url + "/v2.1",
        compute_api_version="2",
        network_endpoint_override=url + "/v2.0",
        network_api_version="2",
        api_timeout=2,
    )
    yield conn, state
    conn.close()
    server.shutdown()
    thread.join()
    server.server_close()


def test_owner_and_run_fence_reject_foreign_metadata():
    metadata = resources.run_metadata(1, "a" * 32, PROJECT)
    resources.fence(SimpleNamespace(project_id=PROJECT, metadata=metadata), metadata)
    with pytest.raises(RuntimeError, match="foreign consumer resource project"):
        resources.fence(SimpleNamespace(project_id="foreign", metadata=metadata), metadata)
    with pytest.raises(RuntimeError, match="foreign consumer resource run"):
        resources.fence(
            SimpleNamespace(project_id=PROJECT, metadata={**metadata, "afterglow_run_id": "other"}), metadata
        )
    with pytest.raises(RuntimeError, match="ownership evidence missing"):
        resources.fence(SimpleNamespace(project_id=PROJECT, description="not-json"), metadata, port=True)


@pytest.mark.asyncio
async def test_live_sdk_cleanup_server_before_exclusive_volume_and_port(ledger, provider):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    cloud["servers"][VM_ID] = {"id": VM_ID, "name": "proof-vm", "tenant_id": PROJECT, "metadata": metadata}
    cloud["volumes"][LAYER_ID] = {
        "id": LAYER_ID,
        "name": "proof-layer",
        "os-vol-tenant-attr:tenant_id": PROJECT,
        "metadata": metadata,
        "status": "in-use",
        "attachments": [{"server_id": VM_ID}],
        "size": 1,
    }
    cloud["ports"][PORT_ID] = {
        "id": PORT_ID,
        "name": "proof-port",
        "project_id": PROJECT,
        "description": json.dumps(metadata),
        "device_id": VM_ID,
    }
    for kind, resource_id in (("server", VM_ID), ("layer", LAYER_ID), ("port", PORT_ID)):
        name = {"server": "proof-vm", "layer": "proof-layer", "port": "proof-port"}[kind]
        await resources.record(consume_id, run_id, kind=kind, name=name, metadata=metadata)
        await resources.record(consume_id, run_id, kind=kind, name=name, metadata=metadata, resource_id=resource_id)
    await resources.cleanup(conn, consume_id, project_id=PROJECT)
    assert cloud["deleted"] == [("servers", VM_ID), ("volumes", LAYER_ID), ("ports", PORT_ID)]
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.cleanup_state == "complete" and row.status == "deleted"
        assert all(item["state"] == "deleted" for item in row.resources)
    await resources.cleanup(conn, consume_id, project_id=PROJECT)
    assert len(cloud["deleted"]) == 3


@pytest.mark.asyncio
async def test_unknown_post_result_remains_pending_then_is_discovered(ledger, provider):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    await resources.record(consume_id, run_id, kind="layer", name="intent-layer", metadata=metadata)
    with pytest.raises(RuntimeError, match="outcome unknown"):
        await resources.cleanup(conn, consume_id, project_id=PROJECT)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.cleanup_state == "pending" and row.resources[0]["id"] is None
    cloud["volumes"][LAYER_ID] = {
        "id": LAYER_ID,
        "name": "intent-layer",
        "os-vol-tenant-attr:tenant_id": PROJECT,
        "metadata": metadata,
        "status": "available",
        "attachments": [],
        "size": 1,
    }
    await resources.cleanup(conn, consume_id, project_id=PROJECT)
    assert cloud["deleted"] == [("volumes", LAYER_ID)]


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign", ["owner", "run", "attached"])
async def test_foreign_or_attached_volume_stops_cleanup_without_deletion(ledger, provider, foreign):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    cloud["volumes"][LAYER_ID] = {
        "id": LAYER_ID,
        "name": "layer",
        "os-vol-tenant-attr:tenant_id": "foreign" if foreign == "owner" else PROJECT,
        "metadata": {**metadata, **({"afterglow_run_id": "foreign"} if foreign == "run" else {})},
        "status": "available",
        "attachments": [{"server_id": "foreign"}] if foreign == "attached" else [],
        "size": 1,
    }
    await resources.record(consume_id, run_id, kind="layer", name="layer", metadata=metadata)
    await resources.record(consume_id, run_id, kind="layer", name="layer", metadata=metadata, resource_id=LAYER_ID)
    with pytest.raises(RuntimeError):
        await resources.cleanup(conn, consume_id, project_id=PROJECT)
    assert cloud["deleted"] == []
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.cleanup_state == "pending"


@pytest.mark.asyncio
async def test_automatic_cleanup_preserves_live_allocations_and_rejects_late_activation(ledger, provider):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    cloud["volumes"][LAYER_ID] = {
        "id": LAYER_ID,
        "name": "live-layer",
        "os-vol-tenant-attr:tenant_id": PROJECT,
        "metadata": metadata,
        "status": "available",
        "attachments": [],
        "size": 1,
    }
    await resources.record(consume_id, run_id, kind="layer", name="live-layer", metadata=metadata)
    await resources.record(consume_id, run_id, kind="layer", name="live-layer", metadata=metadata, resource_id=LAYER_ID)
    await resources.cleanup(conn, consume_id, project_id=PROJECT, automatic=True)
    assert cloud["deleted"] == []
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.cleanup_state == "allocating"
    await resources.cleanup(conn, consume_id, project_id=PROJECT)
    with pytest.raises(RuntimeError, match="lease lost"):
        await resources.disposition(consume_id, run_id, "active")


@pytest.mark.asyncio
async def test_corrupt_ledger_cannot_supply_foreign_resource_owner(ledger, provider):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        row.resources = [
            {
                "kind": "layer",
                "name": "foreign",
                "id": "foreign",
                "state": "allocated",
                "metadata": {**metadata, "afterglow_project_id": "foreign"},
            }
        ]
        await session.commit()
    with pytest.raises(RuntimeError, match="ledger resource owner/run mismatch"):
        await resources.cleanup(conn, consume_id, project_id=PROJECT)
    assert cloud["deleted"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("admin", [False, True])
async def test_cleanup_http_route_retains_admin_gate_and_reclaims_real_ledger(ledger, provider, monkeypatch, admin):
    import httpx
    from fastapi import FastAPI

    from app.api import deps
    from app.api.union import layer_ops
    from app.services import keystone

    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    cloud["volumes"][LAYER_ID] = {
        "id": LAYER_ID,
        "name": "api-layer",
        "os-vol-tenant-attr:tenant_id": PROJECT,
        "metadata": metadata,
        "status": "available",
        "attachments": [],
        "size": 1,
    }
    await resources.record(consume_id, run_id, kind="layer", name="api-layer", metadata=metadata)
    await resources.record(consume_id, run_id, kind="layer", name="api-layer", metadata=metadata, resource_id=LAYER_ID)
    monkeypatch.setattr(layer_ops, "get_session_factory", lambda: factory)
    monkeypatch.setattr(keystone, "get_admin_connection_for_project", lambda project: conn)
    app = FastAPI()
    app.include_router(layer_ops.router, prefix="/api/v1/admin/libraries")
    app.dependency_overrides[deps.get_token_info] = lambda: {"is_system_admin": admin, "project_id": PROJECT}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        result = await client.delete(f"/api/v1/admin/libraries/consumes/{consume_id}")
    if admin:
        assert result.status_code == 200
        assert result.json()["cleanup_state"] == "complete"
        assert result.json()["ready"] is False
        assert cloud["deleted"] == [("volumes", LAYER_ID)]
    else:
        assert result.status_code == 403 and cloud["deleted"] == []


def test_immutable_source_blocks_artifact_gc_and_pending_run_still_references_layer():
    from app.api.union.layer_ops import _artifact_delete_preview
    from app.models.db import LayerArtifact

    artifact = LayerArtifact(
        id=1, name="root", kind="dockerfile-root", parent_id=None, block_source={"state": "ready", "image_id": "source"}
    )
    preview = _artifact_delete_preview(artifact, [artifact], [], [], [])
    assert preview["can_delete"] is False
    assert preview["delete_blockers"][0]["type"] == "retained_block_source"
    artifact.block_source = None
    consumer = LayerConsume(
        id=1,
        profile_name="proof",
        share_id="",
        project_id=PROJECT,
        artifact_ids=[1],
        status="error",
        transport="block",
        run_id="a" * 32,
        cleanup_state="pending",
    )
    preview = _artifact_delete_preview(artifact, [artifact], [], [consumer], [])
    assert preview["can_delete"] is False
    assert any(blocker["type"] == "active_consume_references" for blocker in preview["delete_blockers"])
    consumer.cleanup_state = "complete"
    assert _artifact_delete_preview(artifact, [artifact], [], [consumer], [])["can_delete"] is True


@pytest.mark.asyncio
async def test_actual_publication_http_allocates_source_identity_and_materializes_sealed_bytes(
    ledger, block_provider, monkeypatch
):
    import httpx
    from fastapi import FastAPI

    from app.api import deps
    from app.api.union import layer_block_sources
    from app.models.db import LayerArtifact
    from app.services import layer_block
    from tests.test_layer_block import DATA, METADATA

    factory, _ = ledger
    conn, provider_state, entry = block_provider
    async with factory.kw["bind"].begin() as connection:
        await connection.run_sync(lambda sync: LayerArtifact.__table__.create(sync))
    async with factory() as session:
        artifact = LayerArtifact(
            id=entry["id"],
            name="root",
            kind="dockerfile-root",
            sqsh_filename="root.sqsh",
            share_id="sealed-nfs",
            parent_id=None,
            chain_id=entry["chain_id"],
            blob_digest=entry["blob_digest"],
            size_bytes=entry["size_bytes"],
            is_sealed=True,
            digest_state="ready",
        )
        session.add(artifact)
        await session.commit()
    provider_state.image = None
    provider_state.project_id = "service"
    conn._afterglow_project_id = "service"
    monkeypatch.setattr(layer_block_sources, "get_session_factory", lambda: factory)
    monkeypatch.setattr(layer_block_sources, "get_service_project_connection", lambda: conn)
    app = FastAPI()
    app.include_router(layer_block_sources.router, prefix="/api/v1/admin/libraries")
    app.dependency_overrides[deps.get_token_info] = lambda: {"is_system_admin": True}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/v1/admin/libraries/artifacts/{entry['id']}/block-source?store_id=rbd&member_project_id=caller"
        rejected = await client.put(path, content=DATA + b"wrong")
        assert rejected.status_code == 422
        assert not any(call[0] == "POST" for call in provider_state.calls)
        published = await client.put(path, content=DATA)
    assert published.status_code == 200
    source = published.json()
    assert source["state"] == "ready" and source["image_id"] != entry["block_source"]["image_id"]
    assert provider_state.data == DATA and provider_state.image["stores"] == "rbd"
    async with factory() as session:
        stored = await session.get(LayerArtifact, entry["id"])
        assert stored.block_source == source
    conn._afterglow_project_id = "caller"
    provider_state.project_id = "caller"
    entry["block_source"] = source
    layer_block.validate_sources(conn, [entry])
    volume = conn.block_storage.create_volume(
        **layer_block.layer_volume_create_options(conn, entry, "published-source-consumer", METADATA)
    )
    prepared = layer_block.prepare_layer_volume(conn, volume.id, entry, METADATA)
    assert prepared["metadata"]["readonly"] == "True"
    assert prepared["volume_image_metadata"]["image_id"] == source["image_id"]


async def allocate_volume(conn, consume_id, run_id, metadata):
    return await resources.allocate(
        consume_id,
        run_id,
        conn.block_storage.create_volume,
        resource_kind="layer",
        resource_name="allocated-layer",
        owner_metadata=metadata,
        name="allocated-layer",
        metadata=metadata,
        size=1,
    )


async def allocate_server(conn, consume_id, run_id, metadata):
    return await resources.allocate(
        consume_id,
        run_id,
        conn.compute.create_server,
        resource_kind="server",
        resource_name="allocated-server",
        owner_metadata=metadata,
        name="allocated-server",
        metadata=metadata,
        image_id=OTHER_ID,
        flavor_id=OTHER_ID,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 413, 422])
async def test_definitive_sdk_rejection_reclaims_prior_allocations(ledger, provider, status):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    await allocate_volume(conn, consume_id, run_id, metadata)
    cloud["create_status"] = status
    with pytest.raises(HttpException):
        await allocate_server(conn, consume_id, run_id, metadata)
    await resources.disposition(consume_id, run_id, "pending", status="error", error_message="rejected", completed=True)
    await resources.cleanup(conn, consume_id, project_id=PROJECT)
    assert cloud["deleted"] == [("volumes", LAYER_ID)]
    assert len(cloud["posts"]) == 2
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.cleanup_state == "complete" and row.status == "error"
        assert row.resources[1]["state"] == "rejected"
        assert row.resources[1]["response_status"] == status


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [408, 409, 429, 500, 503])
async def test_uncertain_sdk_rejection_keeps_intent_and_dependencies_pending(ledger, provider, status):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    await allocate_volume(conn, consume_id, run_id, metadata)
    cloud["create_status"] = status
    conn.compute.status_code_retries = 2
    with pytest.raises(HttpException):
        await allocate_server(conn, consume_id, run_id, metadata)
    with pytest.raises(RuntimeError, match="outcome unknown"):
        await resources.cleanup(conn, consume_id, project_id=PROJECT)
    assert cloud["deleted"] == []
    assert len(cloud["posts"]) == 2
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.cleanup_state == "pending"
        assert row.resources[1]["state"] == "intent" and row.resources[1]["id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind, provider_kind, resource_id",
    [
        ("server", "servers", VM_ID),
        ("layer", "volumes", LAYER_ID),
        ("port", "ports", PORT_ID),
    ],
)
async def test_sdk_response_loss_is_not_replayed_and_late_identity_can_be_reclaimed(
    ledger,
    provider,
    kind,
    provider_kind,
    resource_id,
):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)

    async def allocate():
        if kind == "server":
            return await allocate_server(conn, consume_id, run_id, metadata)
        if kind == "layer":
            return await allocate_volume(conn, consume_id, run_id, metadata)
        return await resources.allocate(
            consume_id,
            run_id,
            conn.network.create_port,
            resource_kind="port",
            resource_name="allocated-port",
            owner_metadata=metadata,
            name="allocated-port",
            network_id=OTHER_ID,
            description=json.dumps(metadata),
        )

    cloud["response_loss"] = True
    with pytest.raises(Exception):
        await allocate()
    assert len(cloud["posts"]) == 1
    resource = cloud[provider_kind].pop(resource_id)
    # Repeating the helper itself must not retransmit a sent/unknown intent.
    with pytest.raises(RuntimeError, match="already attempted"):
        await allocate()
    with pytest.raises(RuntimeError, match="outcome unknown"):
        await resources.cleanup(conn, consume_id, project_id=PROJECT)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.cleanup_state == "pending" and row.resources[0]["id"] is None
    cloud[provider_kind][resource_id] = resource
    await resources.cleanup(conn, consume_id, project_id=PROJECT)
    assert cloud["deleted"] == [(provider_kind, resource_id)]
    assert len(cloud["posts"]) == 1


@pytest.mark.asyncio
async def test_preflight_not_sent_is_distinct_from_create_value_error(ledger, provider):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    create = Mock(side_effect=ValueError("inside create; may already have sent"))
    preflight = Mock(side_effect=ValueError("preflight failed"))
    kwargs = dict(resource_kind="layer", resource_name="proof", owner_metadata=metadata)
    with pytest.raises(ValueError, match="preflight failed"):
        await resources.allocate(consume_id, run_id, create, preflight=preflight, **kwargs)
    create.assert_not_called()
    async with factory() as session:
        assert (await session.get(LayerConsume, consume_id)).resources == []
    with pytest.raises(ValueError, match="inside create"):
        await resources.allocate(consume_id, run_id, create, **kwargs)
    with pytest.raises(RuntimeError, match="outcome unknown"):
        await resources.cleanup(conn, consume_id, project_id=PROJECT)
    assert cloud["deleted"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("response_id", [None, "", "not-a-uuid", 12])
async def test_malformed_sdk_create_identity_remains_unresolved(ledger, provider, response_id):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    cloud["response_id"] = response_id
    with pytest.raises(RuntimeError, match="identity is not a UUID"):
        await allocate_volume(conn, consume_id, run_id, metadata)
    cloud["volumes"].clear()
    with pytest.raises(RuntimeError, match="outcome unknown"):
        await resources.cleanup(conn, consume_id, project_id=PROJECT)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.cleanup_state == "pending" and row.resources[0]["id"] is None
    assert cloud["deleted"] == []


@pytest.mark.asyncio
async def test_sdk_get_identity_cannot_replace_bound_uuid(ledger, provider):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    await allocate_volume(conn, consume_id, run_id, metadata)
    cloud["volumes"][LAYER_ID]["id"] = OTHER_ID
    with pytest.raises(RuntimeError, match="GET identity mismatch"):
        await resources.cleanup(conn, consume_id, project_id=PROJECT)
    async with factory() as session:
        assert (await session.get(LayerConsume, consume_id)).resources[0]["id"] == LAYER_ID
    assert cloud["deleted"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,field,bad",
    [
        ("layer", "attachments", "omitted"),
        ("layer", "attachments", None),
        ("layer", "attachments", {}),
        ("port", "device_id", "omitted"),
        ("port", "device_id", None),
        ("port", "device_id", []),
    ],
)
async def test_sdk_cleanup_requires_explicit_typed_detachment(ledger, provider, kind, field, bad):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    if kind == "layer":
        await allocate_volume(conn, consume_id, run_id, metadata)
        resource = cloud["volumes"][LAYER_ID]
    else:
        await resources.allocate(
            consume_id,
            run_id,
            conn.network.create_port,
            resource_kind="port",
            resource_name="port",
            owner_metadata=metadata,
            name="port",
            network_id=OTHER_ID,
            description=json.dumps(metadata),
        )
        resource = cloud["ports"][PORT_ID]
    if bad == "omitted":
        resource.pop(field)
    else:
        resource[field] = bad
    with pytest.raises(RuntimeError, match="detachment evidence"):
        await resources.cleanup(conn, consume_id, project_id=PROJECT)
    assert cloud["deleted"] == []
    async with factory() as session:
        assert (await session.get(LayerConsume, consume_id)).cleanup_state == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("status,ledger_value", [("creating", None), ("creating", []), ("error", [])])
async def test_stale_unclaimed_empty_admission_recovers_without_provider(ledger, monkeypatch, status, ledger_value):
    from app.services import keystone

    factory, consume_id = ledger
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        row.status = status
        row.resources = ledger_value
        row.updated_at = datetime.now(UTC) - timedelta(hours=2)
        await session.commit()
    connect = Mock(side_effect=AssertionError("recovery must not contact provider"))
    monkeypatch.setattr(keystone, "get_admin_connection_for_project", connect)
    await resources.reconcile_once()
    connect.assert_not_called()
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.status == "error" and row.cleanup_state == "complete"
        assert row.completed_at is not None and row.run_id is None and row.resources == ledger_value
    with pytest.raises(RuntimeError, match="already claimed"):
        await resources.begin(consume_id, PROJECT, [1])


@pytest.mark.asyncio
@pytest.mark.parametrize("unsafe", ["fresh", "ledger", "server", "port", "malformed-ledger"])
async def test_unclaimed_admission_without_empty_stale_proof_is_not_terminalized(ledger, monkeypatch, unsafe):
    from app.services import keystone

    factory, consume_id = ledger
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        row.updated_at = datetime.now(UTC) - timedelta(hours=2 if unsafe != "fresh" else 0)
        row.resources = [{}] if unsafe == "ledger" else {} if unsafe == "malformed-ledger" else []
        row.server_id = VM_ID if unsafe == "server" else None
        row.port_id = PORT_ID if unsafe == "port" else None
        await session.commit()
    connect = Mock(side_effect=AssertionError("unclaimed recovery must not issue cloud I/O"))
    monkeypatch.setattr(keystone, "get_admin_connection_for_project", connect)
    await resources.reconcile_once()
    connect.assert_not_called()
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.status == "creating" and row.cleanup_state is None


@pytest.mark.asyncio
async def test_claimant_status_and_bindings_are_run_and_state_fenced(ledger, provider):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    with pytest.raises(RuntimeError, match="already claimed"):
        await resources.begin(consume_id, PROJECT, [1])
    with pytest.raises(RuntimeError, match="lease lost"):
        await resources.disposition(consume_id, "not-owner", "pending", status="error", completed=True)
    with pytest.raises(RuntimeError, match="lease lost"):
        await resources.update_allocation(consume_id, "not-owner", server_id=VM_ID)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.status == "creating" and row.completed_at is None and row.server_id is None
    await resources.update_allocation(consume_id, run_id, server_name="proof", server_id=VM_ID, port_id=PORT_ID)
    await resources.cleanup(conn, consume_id, project_id=PROJECT)
    for state, status in [("active", "active"), ("pending", "error")]:
        with pytest.raises(RuntimeError, match="lease lost"):
            await resources.disposition(consume_id, run_id, state, status=status, error_message="late", completed=True)
    with pytest.raises(RuntimeError, match="lease lost"):
        await resources.update_allocation(consume_id, run_id, server_id=OTHER_ID)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.status == "deleted" and row.cleanup_state == "complete" and row.error_message is None
        assert row.server_id == VM_ID and row.port_id == PORT_ID
    assert cloud["deleted"] == []


@pytest.mark.asyncio
async def test_active_status_commits_atomically_with_disposition(ledger):
    factory, consume_id = ledger
    run_id = await resources.begin(consume_id, PROJECT, [1])
    await resources.disposition(consume_id, run_id, "active", status="active", completed=True)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.status == "active" and row.cleanup_state == "active" and row.completed_at is not None


@pytest.mark.asyncio
async def test_heartbeat_raises_on_lost_lease_and_database_failure(ledger, monkeypatch):
    _, consume_id = ledger
    run_id = await resources.begin(consume_id, PROJECT, [1])
    monkeypatch.setattr(resources.asyncio, "sleep", AsyncMock())
    with pytest.raises(RuntimeError, match="lease lost"):
        await resources.heartbeat(consume_id, "other-run")
    monkeypatch.setattr(resources, "get_session_factory", Mock(side_effect=RuntimeError("database unavailable")))
    with pytest.raises(RuntimeError, match="database unavailable"):
        await resources.heartbeat(consume_id, run_id)


@pytest.mark.asyncio
async def test_cleanup_connection_must_match_durable_project_even_with_matching_marker(ledger, provider):
    from keystoneauth1.token_endpoint import Token as UnscopedToken

    _, consume_id = ledger
    conn, cloud = provider
    await resources.begin(consume_id, PROJECT, [1])
    conn._afterglow_project_id = PROJECT
    conn.session.auth = UnscopedToken(endpoint="http://127.0.0.1", token="synthetic")
    with pytest.raises((ValueError, RuntimeError), match="project|scope"):
        await resources.cleanup(conn, consume_id, project_id=PROJECT)
    assert cloud["deleted"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("dispatch", ["single", "bulk"])
@pytest.mark.parametrize("metadata", [{}, {"layer_transport": "nfs", "union_upper_volume_id": OTHER_ID}])
async def test_compute_delete_uses_durable_binding_when_nova_metadata_changes(
    ledger, provider, monkeypatch, dispatch, metadata
):
    from starlette.requests import Request

    from app.api.compute import instances

    factory, consume_id = ledger
    conn, cloud = provider
    conn._afterglow_project_id = PROJECT
    run_id = await resources.begin(consume_id, PROJECT, [1])
    ownership = resources.run_metadata(consume_id, run_id, PROJECT)
    await allocate_volume(conn, consume_id, run_id, ownership)
    await allocate_server(conn, consume_id, run_id, ownership)
    # No row.server_id: the ledger itself is already a durable binding.
    server = SimpleNamespace(
        id=VM_ID,
        project_id=PROJECT,
        name="proof",
        metadata=metadata,
        union_upper_volume_id=OTHER_ID,
        union_share_ids=[],
        union_strategy="dynamic",
    )
    monkeypatch.setattr(instances.nova, "get_server", lambda *_: server)
    generic_delete = Mock(side_effect=AssertionError("known block must not enter generic deletion"))
    upper_delete = Mock(side_effect=AssertionError("mutable upper metadata must not choose deletion"))
    monkeypatch.setattr(instances.nova, "delete_server", generic_delete)
    monkeypatch.setattr(instances.cinder, "delete_volume", upper_delete)
    monkeypatch.setattr(instances, "invalidate", AsyncMock())
    monkeypatch.setattr(instances.cache_invalidation, "invalidate_mutation_count", AsyncMock())
    monkeypatch.setattr(instances, "rec", AsyncMock())
    monkeypatch.setattr(instances.neutron, "cleanup_instance_fips", Mock())
    if dispatch == "single":
        await instances.delete_instance(Request({"type": "http"}), VM_ID, conn, {"project_id": PROJECT})
    else:
        await instances._bulk_delete_one(conn, {"project_id": PROJECT}, server, VM_ID, PROJECT)
    generic_delete.assert_not_called()
    upper_delete.assert_not_called()
    assert cloud["deleted"] == [("servers", VM_ID), ("volumes", LAYER_ID)]
    async with factory() as session:
        assert (await session.get(LayerConsume, consume_id)).cleanup_state == "complete"


@pytest.mark.asyncio
async def test_server_dispatch_distinguishes_ordinary_missing_tracking_unknown_and_db_loss(
    ledger, provider, monkeypatch
):
    _, consume_id = ledger
    conn, cloud = provider
    assert await resources.cleanup_for_server(conn, VM_ID, PROJECT) is False
    with pytest.raises(RuntimeError, match="tracking record missing"):
        await resources.cleanup_for_server(conn, VM_ID, PROJECT, require_block=True)
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    await resources.record(consume_id, run_id, kind="server", name="unknown-server", metadata=metadata)
    with pytest.raises(RuntimeError, match="binding unknown"):
        await resources.cleanup_for_server(conn, VM_ID, PROJECT)
    monkeypatch.setattr(resources, "get_session_factory", lambda: None)
    with pytest.raises(RuntimeError, match="database unavailable"):
        await resources.cleanup_for_server(conn, VM_ID, PROJECT)
    assert cloud["deleted"] == []


@pytest.mark.asyncio
async def test_preclaim_failure_cannot_modify_competing_run(ledger):
    factory, consume_id = ledger
    run_id = await resources.begin(consume_id, PROJECT, [1])
    assert await resources.fail_unclaimed(consume_id, PROJECT, "competing failure") is False
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.run_id == run_id and row.status == "creating" and row.cleanup_state == "allocating"
        assert row.error_message is None and row.completed_at is None


@pytest.mark.asyncio
async def test_preclaim_failure_atomically_terminalizes_only_owned_empty_admission(ledger):
    factory, consume_id = ledger
    assert await resources.fail_unclaimed(consume_id, "foreign", "foreign failure") is False
    assert await resources.fail_unclaimed(consume_id, PROJECT, "validation failed before claim") is True
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.status == "error" and row.cleanup_state == "complete" and row.run_id is None
        assert row.completed_at is not None and row.error_message == "validation failed before claim"


@pytest.mark.asyncio
async def test_malformed_legacy_bound_id_cannot_be_mistaken_for_reclamation(ledger, provider):
    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        row.resources = [{"kind": "layer", "name": "malformed", "id": "", "state": "allocated", "metadata": metadata}]
        await session.commit()
    with pytest.raises(RuntimeError, match="identity is not a UUID"):
        await resources.cleanup(conn, consume_id, project_id=PROJECT)
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.cleanup_state == "pending" and row.resources[0]["state"] == "allocated"
    assert cloud["deleted"] == []


@pytest.mark.asyncio
async def test_record_canonicalizes_valid_uuid_and_rejects_malformed_binding(ledger):
    factory, consume_id = ledger
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    await resources.record(consume_id, run_id, kind="layer", name="proof", metadata=metadata)
    with pytest.raises(RuntimeError, match="identity is not a UUID"):
        await resources.record(consume_id, run_id, kind="layer", name="proof", metadata=metadata, resource_id="")
    await resources.record(
        consume_id,
        run_id,
        kind="layer",
        name="proof",
        metadata=metadata,
        resource_id="ABCDEF12-3456-4789-ABCD-0123456789AB",
    )
    async with factory() as session:
        item = (await session.get(LayerConsume, consume_id)).resources[0]
        assert item["id"] == "abcdef12-3456-4789-abcd-0123456789ab" and item["state"] == "allocated"


@pytest.mark.asyncio
@pytest.mark.parametrize("dispatch", ["single", "bulk"])
@pytest.mark.parametrize("failure", ["missing-ledger", "unknown-server", "database", "foreign", "metadata-removed"])
async def test_compute_dispatch_uncertainty_never_reaches_generic_cleanup(
    ledger, provider, monkeypatch, dispatch, failure
):
    from starlette.requests import Request

    from app.api.compute import instances

    factory, consume_id = ledger
    conn, cloud = provider
    conn._afterglow_project_id = PROJECT
    metadata = {"layer_transport": "block"} if failure == "missing-ledger" else {}
    server = SimpleNamespace(
        id=VM_ID,
        project_id=PROJECT,
        name="proof",
        metadata=metadata,
        union_upper_volume_id=OTHER_ID,
        union_share_ids=[],
        union_strategy="dynamic",
    )
    monkeypatch.setattr(instances.nova, "get_server", lambda *_: server)
    generic = Mock()
    upper = Mock()
    monkeypatch.setattr(instances.nova, "delete_server", generic)
    monkeypatch.setattr(instances.cinder, "delete_volume", upper)
    if failure in {"unknown-server", "metadata-removed"}:
        run_id = await resources.begin(consume_id, PROJECT, [1])
        ownership = resources.run_metadata(consume_id, run_id, PROJECT)
        if failure == "unknown-server":
            await resources.record(consume_id, run_id, kind="server", name="unknown", metadata=ownership)
        else:
            await allocate_server(conn, consume_id, run_id, ownership)
            # Removing ownership tags must fail closed, not force generic delete.
            cloud["servers"][VM_ID]["metadata"] = {}
    elif failure == "foreign":
        async with factory() as session:
            row = await session.get(LayerConsume, consume_id)
            row.project_id = "foreign"
            row.server_id = VM_ID
            await session.commit()
    elif failure == "database":
        monkeypatch.setattr(resources, "get_session_factory", lambda: None)
    with pytest.raises(RuntimeError):
        if dispatch == "single":
            await instances.delete_instance(Request({"type": "http"}), VM_ID, conn, {"project_id": PROJECT})
        else:
            await instances._bulk_delete_one(conn, {"project_id": PROJECT}, server, VM_ID, PROJECT)
    generic.assert_not_called()
    upper.assert_not_called()
    assert cloud["deleted"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("dispatch", ["single", "bulk", "dedicated"])
@pytest.mark.parametrize("denial", ["pending", "failed"])
async def test_tracked_block_managed_grant_denial_preserves_vm_and_ledger_for_retry(
    ledger, provider, monkeypatch, dispatch, denial
):
    from fastapi import HTTPException
    from starlette.requests import Request

    from app.api.compute import instances
    from app.api.union import layer_ops
    from app.services import keystone

    factory, consume_id = ledger
    conn, cloud = provider
    conn._afterglow_project_id = PROJECT
    monkeypatch.setattr(layer_ops, "get_session_factory", lambda: factory)
    monkeypatch.setattr(keystone, "get_admin_connection_for_project", lambda _: conn)
    monkeypatch.setattr(conn, "close", lambda: None)
    run_id = await resources.begin(consume_id, PROJECT, [1])
    ownership = resources.run_metadata(consume_id, run_id, PROJECT)
    await allocate_server(conn, consume_id, run_id, ownership)
    grant = {"s": OTHER_ID, "i": PORT_ID, "t": "ip", "a": "192.0.2.4", "l": "rw", "m": True}
    grant_key = instances._storage_grant_key(OTHER_ID)
    metadata = {**ownership, grant_key: json.dumps(grant)}
    cloud["servers"][VM_ID]["metadata"] = metadata
    server = SimpleNamespace(
        id=VM_ID,
        project_id=PROJECT,
        name="proof",
        metadata=metadata,
        union_upper_volume_id=OTHER_ID,
        union_share_ids=[],
        union_strategy="dynamic",
    )
    monkeypatch.setattr(instances.nova, "get_server", lambda *_: server)
    rule = {
        "id": PORT_ID,
        "access_type": "ip",
        "access_to": grant["a"],
        "access_level": "rw",
        "state": "active",
        "metadata": {instances._STORAGE_RULE_OWNER: VM_ID},
    }

    def get_rule(*_):
        # Both initial identity validation and denial observation happen while
        # the VM and its durable/grant tracking still exist.
        assert VM_ID in cloud["servers"] and cloud["deleted"] == []
        assert grant_key in cloud["servers"][VM_ID]["metadata"]
        return rule

    monkeypatch.setattr(instances.manila, "get_access_rule", get_rule)
    revoke = Mock(side_effect=RuntimeError("denial failed") if denial == "failed" else None)
    monkeypatch.setattr(instances.manila, "revoke_access_rule", revoke)
    monkeypatch.setattr(instances, "_storage_share", AsyncMock())
    generic = Mock()
    upper = Mock()
    monkeypatch.setattr(instances.nova, "delete_server", generic)
    monkeypatch.setattr(instances.cinder, "delete_volume", upper)
    async with factory() as session:
        before = [dict(item) for item in (await session.get(LayerConsume, consume_id)).resources]

    async def delete():
        if dispatch == "single":
            await instances.delete_instance(Request({"type": "http"}), VM_ID, conn, {"project_id": PROJECT})
        elif dispatch == "bulk":
            await instances._bulk_delete_one(conn, {"project_id": PROJECT}, server, VM_ID, PROJECT)
        else:
            await layer_ops.delete_block_consume(consume_id, {"is_system_admin": True, "project_id": PROJECT})

    with pytest.raises(HTTPException) as failure:
        await delete()
    assert failure.value.status_code == (409 if denial == "pending" else 502)
    assert cloud["deleted"] == [] and VM_ID in cloud["servers"]
    assert grant_key in cloud["servers"][VM_ID]["metadata"]
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.resources == before and row.cleanup_state == "allocating" and row.status == "creating"
    generic.assert_not_called()
    upper.assert_not_called()
    revoke.assert_called_once_with(conn, OTHER_ID, PORT_ID)

    # An exact-rule absence on retry is observed denial completion; only now
    # may resource cleanup delete Nova and terminalize the durable ledger.
    monkeypatch.setattr(instances.manila, "get_access_rule", lambda *_: None)
    monkeypatch.setattr(instances, "invalidate", AsyncMock())
    monkeypatch.setattr(instances.cache_invalidation, "invalidate_mutation_count", AsyncMock())
    monkeypatch.setattr(instances, "rec", AsyncMock())
    monkeypatch.setattr(instances.neutron, "cleanup_instance_fips", Mock())
    await delete()
    assert cloud["deleted"] == [("servers", VM_ID)]
    async with factory() as session:
        row = await session.get(LayerConsume, consume_id)
        assert row.cleanup_state == "complete" and row.status == "deleted"
    generic.assert_not_called()
    upper.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_preserves_create_rejection_committed_after_its_snapshot(ledger, provider):
    import asyncio

    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    await allocate_volume(conn, consume_id, run_id, metadata)
    cloud.update(
        create_status=403,
        rejection_gate=threading.Event(),
        rejection_started=threading.Event(),
        delete_gate=threading.Event(),
        delete_started=threading.Event(),
    )
    allocating = asyncio.create_task(
        resources.allocate(
            consume_id,
            run_id,
            conn.block_storage.create_volume,
            resource_kind="upper",
            resource_name="second-volume",
            owner_metadata=metadata,
            name="second-volume",
            metadata=metadata,
            size=1,
        )
    )
    cleaning = None
    try:
        assert await asyncio.to_thread(cloud["rejection_started"].wait, 5)
        cleaning = asyncio.create_task(resources.cleanup(conn, consume_id, project_id=PROJECT))
        assert await asyncio.to_thread(cloud["delete_started"].wait, 5)
        cloud["rejection_gate"].set()
        with pytest.raises(HttpException):
            await allocating
        cloud["delete_gate"].set()
        await asyncio.wait_for(cleaning, timeout=5)
        async with factory() as session:
            row = await session.get(LayerConsume, consume_id)
            assert row.cleanup_state == "complete"
            assert row.resources[0]["state"] == "deleted"
            assert (row.resources[1]["state"], row.resources[1]["response_status"]) == ("rejected", 403)
        assert cloud["deleted"] == [("volumes", LAYER_ID)]
        assert len(cloud["posts"]) == 2
    finally:
        cloud["rejection_gate"].set()
        cloud["delete_gate"].set()
        await asyncio.gather(allocating, *([cleaning] if cleaning is not None else []), return_exceptions=True)


@pytest.mark.asyncio
async def test_unattended_cleanup_cannot_discard_managed_storage_tracking(ledger, provider):
    from app.api.compute import instances

    factory, consume_id = ledger
    conn, cloud = provider
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    await allocate_server(conn, consume_id, run_id, metadata)
    grant = {"s": OTHER_ID, "i": PORT_ID, "t": "ip", "a": "192.0.2.4", "l": "rw", "m": True}
    cloud["servers"][VM_ID]["metadata"][instances._storage_grant_key(OTHER_ID)] = json.dumps(grant)
    with pytest.raises(RuntimeError, match="authenticated deletion"):
        await resources.cleanup(conn, consume_id, project_id=PROJECT)
    assert VM_ID in cloud["servers"] and cloud["deleted"] == []
    async with factory() as session:
        assert (await session.get(LayerConsume, consume_id)).cleanup_state == "allocating"


@pytest.mark.asyncio
@pytest.mark.parametrize("dispatch", ["single", "bulk", "dedicated"])
@pytest.mark.parametrize("rejected", [False, True])
async def test_block_delete_reclaims_floating_ips_before_destroying_port_binding(
    ledger,
    provider,
    monkeypatch,
    dispatch,
    rejected,
):
    from starlette.requests import Request

    from app.api.compute import instances
    from app.api.union import layer_ops
    from app.services import keystone

    factory, consume_id = ledger
    conn, cloud = provider
    conn._afterglow_project_id = PROJECT
    run_id = await resources.begin(consume_id, PROJECT, [1])
    metadata = resources.run_metadata(consume_id, run_id, PROJECT)
    await allocate_server(conn, consume_id, run_id, metadata)
    cloud["ports"][PORT_ID] = {
        "id": PORT_ID,
        "name": "vm-port",
        "project_id": PROJECT,
        "device_id": VM_ID,
        "description": json.dumps(metadata),
    }
    await resources.record(consume_id, run_id, kind="port", name="vm-port", metadata=metadata, resource_id=PORT_ID)
    cloud["floatingips"][OTHER_ID] = {"id": OTHER_ID, "port_id": PORT_ID, "project_id": PROJECT}
    cloud["ports"][LAYER_ID] = {"id": LAYER_ID, "device_id": "other-vm", "project_id": "other-project"}
    cloud["floatingips"][LAYER_ID] = {"id": LAYER_ID, "port_id": LAYER_ID, "project_id": "other-project"}
    server = SimpleNamespace(
        id=VM_ID,
        project_id=PROJECT,
        name="proof",
        metadata=metadata,
        union_upper_volume_id=None,
        union_share_ids=[],
        union_strategy="dynamic",
    )
    monkeypatch.setattr(instances.nova, "get_server", lambda *_: server)
    monkeypatch.setattr(instances, "invalidate", AsyncMock())
    monkeypatch.setattr(instances.cache_invalidation, "invalidate_mutation_count", AsyncMock())
    monkeypatch.setattr(instances, "rec", AsyncMock())
    monkeypatch.setattr(layer_ops, "get_session_factory", lambda: factory)
    monkeypatch.setattr(keystone, "get_admin_connection_for_project", lambda _: conn)
    monkeypatch.setattr(conn, "close", lambda: None)

    async def delete():
        if dispatch == "single":
            await instances.delete_instance(Request({"type": "http"}), VM_ID, conn, {"project_id": PROJECT})
        elif dispatch == "bulk":
            await instances._bulk_delete_one(conn, {"project_id": PROJECT}, server, VM_ID, PROJECT)
        else:
            await layer_ops.delete_block_consume(consume_id, {"is_system_admin": True})

    if rejected:
        cloud["fip_delete_status"] = 503
        with pytest.raises(HttpException):
            await delete()
        assert VM_ID in cloud["servers"] and PORT_ID in cloud["ports"]
        assert cloud["floatingips"][OTHER_ID]["port_id"] == PORT_ID
        assert cloud["deleted"] == []
        async with factory() as session:
            assert (await session.get(LayerConsume, consume_id)).cleanup_state == "pending"
        cloud["fip_delete_status"] = None
    await delete()
    assert cloud["deleted"] == [("floatingips", OTHER_ID), ("servers", VM_ID), ("ports", PORT_ID)]
    assert set(cloud["ports"]) == set(cloud["floatingips"]) == {LAYER_ID}
    async with factory() as session:
        assert (await session.get(LayerConsume, consume_id)).cleanup_state == "complete"
