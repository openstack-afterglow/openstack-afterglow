"""Durable layer targets through real SQL, Redis leases and installed SDK HTTP."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import socket
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest
from fakeredis.aioredis import FakeRedis
from keystoneauth1.session import Session
from keystoneauth1.token_endpoint import Token
from openstack.connection import Connection
from sqlalchemy import Text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import LayerArtifact, LayerBuild, LayerConsume, LayerImportJob, ResourcePolicy
from app.services import build_work, layer_builder, manila
from app.services.layer_build import run_layer_build
from app.services.work_dispatcher import DispatcherUnavailable, WorkDispatcher, work_lease

PROJECT = "layer-ownership-project"
IMAGE = str(uuid.uuid5(uuid.NAMESPACE_URL, "layer-image"))
NETWORK = str(uuid.uuid5(uuid.NAMESPACE_URL, "layer-network"))
FLAVOR = "builder-flavor"


class ProjectToken(Token):
    def get_project_id(self, session):
        return PROJECT


@pytest.fixture
async def layer_database(monkeypatch, tmp_path):
    monkeypatch.setattr(LayerImportJob.__table__.c.dockerfile_text, "type", Text())
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'layer-ownership.sqlite'}")
    async with engine.connect() as connection:
        # Readers must not block writers, matching InnoDB MVCC rather than SQLite's default journal.
        await connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    async with engine.begin() as connection:
        for model in (LayerBuild, LayerArtifact, LayerConsume, LayerImportJob, ResourcePolicy):
            await connection.run_sync(lambda sync, model=model: model.__table__.create(sync))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            ResourcePolicy(
                policy_key="openstack.service_project",
                resource_kind="project",
                resource_id=PROJECT,
                resource_name=PROJECT,
            )
        )
        await session.commit()
    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    redis = FakeRedis(decode_responses=True)
    yield factory, redis
    await redis.close()
    await engine.dispose()


@pytest.fixture
def layer_provider(monkeypatch):
    state = {
        "ports": {},
        "shares": {},
        "servers": {},
        "rules": {},
        "volumes": {},
        "floatingips": {},
        "creates": [],
        "deletes": [],
        "connections": [],
        "unexpected": [],
        "lose": None,
        "reject": None,
        "fail_port_delete": False,
        "block_port": False,
        "port_accepted": threading.Event(),
        "release_port": threading.Event(),
    }
    lock = threading.RLock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, body=None):
            payload = b"" if body is None else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if payload:
                self.wfile.write(payload)

        def unexpected(self, method, path):
            # A developer machine can run unrelated local software that probes any loopback port
            # (e.g. editor language servers). Only requests under this fixture's own service roots
            # count as an unexpected provider call; foreign probes are still answered 404.
            if path.startswith(("/nova", "/neutron", "/cinder", "/glance", "/manila", "/v2", "/v3")):
                state["unexpected"].append((method, path))
            self.reply(404, {"itemNotFound": {}})

        def lost(self, kind):
            if state["lose"] != kind:
                return False
            state["lose"] = None
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            self.close_connection = True
            return True

        def do_GET(self):
            path = urlsplit(self.path).path.rstrip("/")
            if path in {"/nova", "/nova/v2.1", f"/nova/v2.1/{PROJECT}"}:
                self.reply(
                    200,
                    {
                        "version": {
                            "id": "v2.1",
                            "status": "CURRENT",
                            "min_version": "2.1",
                            "version": "2.95",
                            "links": [{"rel": "self", "href": endpoint + "/nova/v2.1/"}],
                        }
                    },
                )
                return
            if path in {"/neutron", "/neutron/v2.0"}:
                self.reply(
                    200,
                    {
                        "version": {
                            "id": "v2.0",
                            "status": "CURRENT",
                            "links": [{"rel": "self", "href": endpoint + "/neutron/v2.0/"}],
                        }
                    },
                )
                return
            if path in {"/cinder", "/cinder/v3", f"/cinder/v3/{PROJECT}"}:
                self.reply(
                    200,
                    {
                        "version": {
                            "id": "v3.0",
                            "status": "CURRENT",
                            "min_version": "3.0",
                            "version": "3.70",
                            "links": [{"rel": "self", "href": endpoint + "/cinder/v3/"}],
                        }
                    },
                )
                return
            if path in {"/glance", "/glance/v2"}:
                self.reply(
                    200,
                    {
                        "versions": [
                            {
                                "id": "v2.16",
                                "status": "CURRENT",
                                "links": [{"rel": "self", "href": endpoint + "/glance/v2/"}],
                            }
                        ]
                    },
                )
                return
            if path == f"/glance/v2/images/{IMAGE}":
                self.reply(
                    200,
                    {
                        "id": IMAGE,
                        "name": "ubuntu-24.04-server-2026-04-15",
                        "status": "active",
                        "os_distro": "ubuntu",
                        "os_version": "24.04",
                        "min_disk": 1,
                    },
                )
                return
            if path.endswith("/types"):
                self.reply(
                    200,
                    {
                        "share_types": [
                            {"id": "nfs-type", "name": "nfs", "extra_specs": {"driver_handles_share_servers": "False"}}
                        ]
                    },
                )
                return
            if path.endswith("/share-access-rules"):
                self.reply(200, {"access_list": list(state["rules"].values())})
                return
            if "/share-access-rules/" in path:
                rule = state["rules"].get(path.rsplit("/", 1)[-1])
                self.reply(200 if rule else 404, {"access": rule} if rule else {"itemNotFound": {}})
                return
            if path.endswith("/export_locations"):
                share_id = path.split("/")[-2]
                self.reply(
                    200, {"export_locations": [{"path": f"127.0.0.1:/shares/{share_id}", "is_admin_only": False}]}
                )
                return
            for kind, root, envelope in (
                ("ports", "/neutron/v2.0/ports", "port"),
                ("servers", f"/nova/v2.1/{PROJECT}/servers", "server"),
                ("shares", f"/manila/v2/{PROJECT}/shares", "share"),
                ("volumes", f"/cinder/v3/{PROJECT}/volumes", "volume"),
                ("floatingips", "/neutron/v2.0/floatingips", "floatingip"),
            ):
                if path in {root, root + "/detail"}:
                    self.reply(200, {kind: list(state[kind].values())})
                    return
                if path.startswith(root + "/"):
                    resource = state[kind].get(path.rsplit("/", 1)[-1])
                    self.reply(200 if resource else 404, {envelope: resource} if resource else {"itemNotFound": {}})
                    return
            self.unexpected("GET", path)

        def do_POST(self):
            path = urlsplit(self.path).path.rstrip("/")
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if path.endswith("/action") and "os-getConsoleOutput" in body:
                server_id = path.split("/")[-2]
                record = state["servers"][server_id]
                token = record["metadata"].get("afterglow_build_token")
                if not token:
                    # A booted guest prints the sentinel embedded in its base64 health script.
                    text = base64.b64decode(record["user_data"]).decode(errors="ignore")
                    documents = [text]
                    for blob in re.findall(r"[A-Za-z0-9+/=]{40,}", text):
                        try:
                            documents.append(base64.b64decode(blob).decode(errors="ignore"))
                        except ValueError:
                            continue
                    token = next(
                        found[-1]
                        for document in documents
                        if (found := re.findall(r"::AFTERGLOW::SUCCESS::([0-9a-f]{32})", document))
                    )
                self.reply(200, {"output": f"::AFTERGLOW::SUCCESS::{token}"})
                return
            if path.endswith("/action") and "deny_access" in body:
                rule_id = body["deny_access"]["access_id"]
                state["rules"].pop(rule_id, None)
                self.reply(202)
                return
            if path.endswith("/action") and "allow_access" in body:
                kind, source, envelope = "rule", body["allow_access"], "access"
                collection = state["rules"]
                source = {**source, "share_id": path.split("/")[-2], "state": "active"}
            elif path == "/neutron/v2.0/ports":
                kind, source, envelope = "port", body["port"], "port"
                collection = state["ports"]
                source = {
                    **source,
                    "project_id": PROJECT,
                    "tenant_id": PROJECT,
                    "device_id": "",
                    "fixed_ips": [{"ip_address": "192.0.2.17", "subnet_id": "subnet"}],
                }
            elif path == f"/manila/v2/{PROJECT}/shares":
                kind, source, envelope = "share", body["share"], "share"
                collection = state["shares"]
                if state["reject"] == "share":
                    state["reject"] = None
                    self.reply(400, {"badRequest": {"message": "synthetic definite rejection"}})
                    return
                source = {**source, "project_id": PROJECT, "status": "available"}
            elif path == f"/nova/v2.1/{PROJECT}/servers":
                kind, source, envelope = "server", body["server"], "server"
                collection = state["servers"]
                source = {**source, "tenant_id": PROJECT, "status": "SHUTOFF"}
            elif path == f"/cinder/v3/{PROJECT}/volumes":
                kind, source, envelope = "volume", body["volume"], "volume"
                collection = state["volumes"]
                source = {
                    **source,
                    "project_id": PROJECT,
                    "os-vol-tenant-attr:tenant_id": PROJECT,
                    "status": "available",
                    "attachments": [],
                    "multiattach": False,
                }
            else:
                self.unexpected("POST", path)
                return
            with lock:
                resource_id = str(
                    uuid.uuid5(uuid.NAMESPACE_URL, f"layer-owned:{kind}:{len(collection)}:{len(state['creates'])}")
                )
                record = {**source, "id": resource_id}
                collection[resource_id] = record
                state["creates"].append((kind, body))
                if kind == "server":
                    port_id = source["networks"][0]["port"]
                    state["ports"][port_id]["device_id"] = resource_id
            if kind == "port" and state["block_port"]:
                state["port_accepted"].set()
                state["release_port"].wait(10)
            if self.lost(kind):
                return
            self.reply(202 if kind == "server" else 200, {envelope: record})

        def do_DELETE(self):
            path = urlsplit(self.path).path.rstrip("/")
            for kind, root in (
                ("server", f"/nova/v2.1/{PROJECT}/servers"),
                ("port", "/neutron/v2.0/ports"),
                ("share", f"/manila/v2/{PROJECT}/shares"),
                ("volume", f"/cinder/v3/{PROJECT}/volumes"),
                ("floatingip", "/neutron/v2.0/floatingips"),
            ):
                if path.startswith(root + "/"):
                    resource_id = path.rsplit("/", 1)[-1]
                    if kind == "port" and state["fail_port_delete"]:
                        state["fail_port_delete"] = False
                        self.reply(503, {"error": "synthetic temporary failure"})
                        return
                    state[kind + "s"].pop(resource_id, None)
                    if kind == "server":
                        for port in state["ports"].values():
                            if port["device_id"] == resource_id:
                                port["device_id"] = ""
                    state["deletes"].append((kind, resource_id))
                    self.reply(204)
                    return
            self.unexpected("DELETE", path)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def connection(project_id=PROJECT):
        assert project_id == PROJECT
        conn = Connection(
            session=Session(auth=ProjectToken(endpoint=endpoint, token="synthetic-local-only")),
            compute_endpoint_override=f"{endpoint}/nova/v2.1/{PROJECT}",
            compute_api_version="2",
            network_endpoint_override=endpoint + "/neutron/v2.0",
            network_api_version="2",
            block_storage_endpoint_override=f"{endpoint}/cinder/v3/{PROJECT}",
            block_storage_api_version="3",
            image_endpoint_override=endpoint + "/glance/v2",
            image_api_version="2",
            api_timeout=3,
        )
        state["connections"].append(conn)
        return conn

    monkeypatch.setattr("app.services.keystone.get_admin_connection_for_project", connection)
    monkeypatch.setattr(
        manila,
        "get_client",
        lambda conn: manila.ManilaClient(endpoint + "/manila/v2/" + PROJECT, "synthetic-local-only", PROJECT),
    )
    try:
        yield state, connection
    finally:
        state["release_port"].set()
        for conn in state["connections"]:
            conn.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


async def admit(monkeypatch, connection, **overrides):
    from app.services import resource_policy_store

    snapshot = {
        "builder.flavor": {"id": FLAVOR},
        "builder.network": {"id": NETWORK},
        "manila.share_network": {"id": "share-network"},
        "manila.nfs_share_type": {"id": "nfs-type", "name": "nfs"},
    }
    monkeypatch.setattr(
        resource_policy_store, "get_service_project_connection", AsyncMock(side_effect=lambda *_: connection(PROJECT))
    )
    monkeypatch.setattr(resource_policy_store, "resolve_policy_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(
        resource_policy_store,
        "get_policy_snapshot",
        AsyncMock(return_value={"openstack.service_project": {"id": PROJECT}}),
    )
    inputs = {
        "layer_name": "owned-system",
        "kind": "system",
        "python_version": None,
        "pip_packages": [],
        "apt_packages": ["libxml2-dev"],
        "base_image_snapshot": {
            "base_image_id": IMAGE,
            "base_image_name": "synthetic ubuntu",
            "ubuntu_base": "ubuntu-24.04-server-2026-04-15",
        },
    }
    inputs.update(overrides)
    return await layer_builder.start_layer_build(**inputs)


async def execute(factory, redis, build_id, worker_id):
    from app.services import layer_build

    member = f"layer:{build_id}"
    async with WorkDispatcher(redis, "afterglow:builds", worker_id=worker_id) as dispatcher:
        assert await dispatcher.publish([member])
        claimed = await dispatcher.claim(90)
        assert claimed is not None
        async with work_lease(dispatcher, *claimed) as lease, build_work.bind(redis, member, lease):
            await layer_build.run_layer_build(build_id)


@pytest.fixture(autouse=True)
def short_layer_poll(monkeypatch):
    monkeypatch.setattr("app.services.layer_build._SHUTOFF_POLL_INTERVAL", 0.01)


@pytest.mark.asyncio
async def test_durable_admission_executes_frozen_recipe_on_another_worker(layer_database, layer_provider, monkeypatch):
    factory, redis = layer_database
    state, connection = layer_provider
    packages = ["libxml2-dev"]
    admitted = await admit(monkeypatch, connection, apt_packages=packages)
    assert state["creates"] == []
    packages[:] = ["vim"]
    await execute(factory, redis, admitted["build_id"], "different-api-worker")
    server_body = next(body["server"] for kind, body in state["creates"] if kind == "server")
    user_data = base64.b64decode(server_body["user_data"]).decode()
    script_b64 = re.search(r"path: /usr/local/bin/run-build\.sh\n\s+encoding: b64\n\s+content: (\S+)", user_data).group(
        1
    )
    build_script = base64.b64decode(script_b64).decode()
    # The worker executes the admitted SQL recipe, not the caller's later mutation.
    assert "libxml2-dev" in build_script and "vim" not in build_script.split()
    assert server_body["flavorRef"] == FLAVOR
    async with factory() as session:
        build = await session.get(LayerBuild, admitted["build_id"])
        artifact = await session.scalar(select(LayerArtifact).where(LayerArtifact.build_id == build.id))
        assert build.status == "complete" and artifact.is_sealed
        assert artifact.share_id in state["shares"]
    assert state["servers"] == state["ports"] == {}
    assert state["unexpected"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["port", "share", "rule", "server"])
async def test_native_create_response_loss_is_observed_without_second_post(
    layer_database, layer_provider, monkeypatch, boundary
):
    factory, redis = layer_database
    state, connection = layer_provider
    admitted = await admit(monkeypatch, connection)
    state["lose"] = boundary
    with pytest.raises(build_work.SubmissionUnknown):
        await execute(factory, redis, admitted["build_id"], "lost-response-owner")
    async with factory() as session:
        assert (await session.get(LayerBuild, admitted["build_id"])).status not in {"complete", "error", "cancelled"}
    await execute(factory, redis, admitted["build_id"], "recovery-owner")
    assert [kind for kind, _ in state["creates"]].count(boundary) == 1
    async with factory() as session:
        assert (await session.get(LayerBuild, admitted["build_id"])).status == "complete"
    assert state["unexpected"] == []


@pytest.mark.asyncio
async def test_sealed_output_survives_failed_cleanup_and_successor_does_not_rebuild(
    layer_database, layer_provider, monkeypatch
):
    factory, redis = layer_database
    state, connection = layer_provider
    admitted = await admit(monkeypatch, connection)
    state["fail_port_delete"] = True
    with pytest.raises(Exception):
        await execute(factory, redis, admitted["build_id"], "sealing-owner")
    async with factory() as session:
        build = await session.get(LayerBuild, admitted["build_id"])
        artifact = await session.scalar(select(LayerArtifact).where(LayerArtifact.build_id == build.id))
        assert build.status == "verifying" and artifact.is_sealed
        output = artifact.share_id
    assert output in state["shares"]
    await execute(factory, redis, admitted["build_id"], "cleanup-owner")
    assert output in state["shares"]
    assert [kind for kind, _ in state["creates"]] == ["port", "share", "rule", "server"]
    assert not any(kind == "share" for kind, _ in state["deletes"])
    async with factory() as session:
        assert (await session.get(LayerBuild, admitted["build_id"])).status == "complete"
        assert len((await session.scalars(select(LayerArtifact))).all()) == 1


@pytest.mark.asyncio
async def test_sql_cancellation_blocks_mutations_after_late_native_acceptance(
    layer_database, layer_provider, monkeypatch
):
    factory, redis = layer_database
    state, connection = layer_provider
    admitted = await admit(monkeypatch, connection)
    state["block_port"] = True
    task = asyncio.create_task(execute(factory, redis, admitted["build_id"], "cancelled-owner"))
    try:
        assert await asyncio.to_thread(state["port_accepted"].wait, 5)
        async with factory() as session:
            row = await session.get(LayerBuild, admitted["build_id"])
            row.status = "cancelled"
            await session.commit()
    finally:
        state["release_port"].set()
    with pytest.raises(DispatcherUnavailable):
        await task
    assert [kind for kind, _ in state["creates"]] == ["port"]
    raw = await redis.get(f"afterglow:builds:journal:layer:{admitted['build_id']}:submit:port")
    assert json.loads(raw)["state"] == "accepted"
    async with factory() as session:
        assert (await session.get(LayerBuild, admitted["build_id"])).status == "cancelled"


@pytest.mark.asyncio
async def test_wrong_layer_target_cannot_allocate(layer_database, layer_provider, monkeypatch):
    factory, redis = layer_database
    state, connection = layer_provider
    first = await admit(monkeypatch, connection, layer_name="first-system")
    second = await admit(monkeypatch, connection, layer_name="second-system")
    member = f"layer:{first['build_id']}"
    async with WorkDispatcher(redis, "afterglow:builds") as dispatcher:
        await dispatcher.publish([member])
        claimed = await dispatcher.claim(90)
        async with work_lease(dispatcher, *claimed) as lease, build_work.bind(redis, member, lease):
            with pytest.raises(DispatcherUnavailable):
                await run_layer_build(second["build_id"])
    assert state["creates"] == []


@pytest.mark.asyncio
async def test_successor_seals_existing_vm_without_recreating_revoked_grant(
    layer_database, layer_provider, monkeypatch
):
    from app.services import layer_build

    factory, redis = layer_database
    state, connection = layer_provider
    admitted = await admit(monkeypatch, connection)
    reached_sealing, release = asyncio.Event(), asyncio.Event()
    original = layer_build.resolve_digest_fields

    async def paused_sealing(*args, **kwargs):
        reached_sealing.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(layer_build, "resolve_digest_fields", paused_sealing)
    task = asyncio.create_task(execute(factory, redis, admitted["build_id"], "interrupted-sealer"))
    try:
        async with asyncio.timeout(5):
            await reached_sealing.wait()
        assert state["rules"] == {}
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    monkeypatch.setattr(layer_build, "resolve_digest_fields", original)
    await execute(factory, redis, admitted["build_id"], "successor-sealer")
    assert [kind for kind, _ in state["creates"]] == ["port", "share", "rule", "server"]
    async with factory() as session:
        assert (await session.get(LayerBuild, admitted["build_id"])).status == "complete"
        artifact = await session.scalar(select(LayerArtifact).where(LayerArtifact.build_id == admitted["build_id"]))
        assert artifact.is_sealed and artifact.share_id in state["shares"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [
        {
            "kind": "python",
            "python_version": "3.11",
            "pip_packages": ["numpy"],
            "apt_packages": [],
            "parent_artifact_id": 7,
        },
        {
            "kind": "python",
            "python_version": "3.11",
            "pip_packages": [],
            "apt_packages": [],
            "pip_index_url": "https://example.invalid/packages",
            "parent_artifact_id": 7,
        },
        {"kind": "system", "apt_packages": []},
    ],
)
async def test_invalid_durable_recipe_is_terminal_without_provider_allocation(
    layer_database, layer_provider, monkeypatch, invalid
):
    factory, redis = layer_database
    state, connection = layer_provider
    admitted = await admit(monkeypatch, connection, **invalid)
    await execute(factory, redis, admitted["build_id"], "validation-owner")
    assert state["creates"] == []
    async with factory() as session:
        row = await session.get(LayerBuild, admitted["build_id"])
        assert row.status == "error" and row.completed_at is not None
        assert await session.scalar(select(LayerArtifact).where(LayerArtifact.build_id == row.id)) is None


@pytest.mark.asyncio
async def test_missing_durable_placement_is_terminal_without_provider_allocation(
    layer_database, layer_provider, monkeypatch
):
    factory, redis = layer_database
    state, connection = layer_provider
    admitted = await admit(monkeypatch, connection)
    async with factory() as session:
        row = await session.get(LayerBuild, admitted["build_id"])
        snapshot = dict(row.resource_snapshot)
        snapshot.pop("builder.network")
        row.resource_snapshot = snapshot
        await session.commit()
    await execute(factory, redis, admitted["build_id"], "placement-owner")
    assert state["creates"] == []
    async with factory() as session:
        assert (await session.get(LayerBuild, admitted["build_id"])).status == "error"


@pytest.mark.asyncio
async def test_layer_admission_api_fails_closed_without_database(admin_client, monkeypatch, layer_provider):
    from app.api.union import layer_ops

    state, _ = layer_provider
    monkeypatch.setattr(layer_ops, "get_session_factory", lambda: None)
    monkeypatch.setattr("app.database.get_session_factory", lambda: None)
    response = await admin_client.post(
        "/api/v1/admin/libraries/build",
        json={
            "layer_name": "unavailable-system",
            "kind": "system",
            "apt_packages": ["libxml2-dev"],
            "base_image_id": IMAGE,
        },
    )
    assert response.status_code == 503
    assert state["creates"] == []


async def admit_consumer(factory, state):
    snapshot = {"network": {"id": NETWORK}, "flavor": {"id": FLAVOR}, "openstack.service_project": {"id": PROJECT}}
    state["shares"]["sealed-consumer-root"] = {
        "id": "sealed-consumer-root",
        "name": "sealed-consumer-root",
        "project_id": PROJECT,
        "status": "available",
    }
    async with factory() as session:
        artifact = LayerArtifact(
            name="consumer-root",
            kind="dockerfile-root",
            is_sealed=True,
            share_id="sealed-consumer-root",
            sqsh_filename="consumer-root.sqsh",
            ubuntu_base="ubuntu-24.04-server-2026-04-15",
            base_image_id=IMAGE,
            blob_digest="sha256:" + "d" * 64,
            size_bytes=4096,
        )
        session.add(artifact)
        await session.flush()
        consumer = LayerConsume(
            profile_name="consumer-profile",
            server_name="owned-root-consumer",
            share_id="",
            status="creating",
            project_id=PROJECT,
            transport="nfs",
            artifact_ids=[artifact.id],
            resource_snapshot=snapshot,
        )
        session.add(consumer)
        await session.flush()
        job = LayerImportJob(
            layer_prefix="consumer",
            profile_name="consumer-profile",
            ubuntu_base=artifact.ubuntu_base,
            base_image_id=IMAGE,
            status="verifying",
            artifact_ids=[artifact.id],
            consume_id=consumer.id,
        )
        session.add(job)
        await session.commit()
        return job.id, consumer.id, artifact.id, snapshot


async def execute_consumer(redis, admitted, worker):
    from app.services.layer_build import run_layer_consume

    import_id, consume_id, artifact_id, snapshot = admitted
    member = f"import:{import_id}"
    async with WorkDispatcher(redis, "afterglow:builds", worker_id=worker) as dispatcher:
        await dispatcher.publish([member])
        async with work_lease(dispatcher, *await dispatcher.claim(90)) as lease, build_work.bind(redis, member, lease):
            return await run_layer_consume(
                consume_id,
                "consumer-profile",
                "owned-root-consumer",
                FLAVOR,
                image_id=IMAGE,
                resource_snapshot=snapshot,
                artifact_ids=[artifact_id],
                transport="nfs",
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("lost_step", ["port", "rule", "volume", "server"])
async def test_shared_root_consumer_recovers_exact_accepted_identity_without_replay(
    layer_database, layer_provider, lost_step
):
    factory, redis = layer_database
    state, _ = layer_provider
    admitted = await admit_consumer(factory, state)
    state["lose"] = lost_step
    with pytest.raises(build_work.SubmissionUnknown):
        await execute_consumer(redis, admitted, "first-consumer-owner")
    async with factory() as session:
        assert (await session.get(LayerConsume, admitted[1])).status == "creating"
    server_id = await execute_consumer(redis, admitted, "successor-consumer-owner")
    assert [kind for kind, _ in state["creates"]] == ["port", "rule", "volume", "server"]
    assert state["deletes"] == []
    async with factory() as session:
        consumer = await session.get(LayerConsume, admitted[1])
        assert consumer.status == "active" and consumer.server_id == server_id
        assert (await session.get(LayerImportJob, admitted[0])).status == "verifying"
    assert state["ports"][consumer.port_id]["device_id"] == server_id


@pytest.mark.asyncio
async def test_shared_consumer_cancellation_blocks_later_mutation_after_accepted_port(layer_database, layer_provider):
    factory, redis = layer_database
    state, _ = layer_provider
    admitted = await admit_consumer(factory, state)
    state["block_port"] = True
    task = asyncio.create_task(execute_consumer(redis, admitted, "cancelled-consumer-owner"))
    try:
        async with asyncio.timeout(5):
            while not state["port_accepted"].is_set():
                await asyncio.sleep(0.01)
        async with factory() as session:
            consumer = await session.get(LayerConsume, admitted[1])
            consumer.status = "cancelled"
            await session.commit()
        state["release_port"].set()
        with pytest.raises(DispatcherUnavailable):
            await task
    finally:
        state["release_port"].set()
        await asyncio.gather(task, return_exceptions=True)
    assert [kind for kind, _ in state["creates"]] == ["port"]
    assert state["deletes"] == []
    async with factory() as session:
        assert (await session.get(LayerConsume, admitted[1])).status == "cancelled"


@pytest.mark.asyncio
async def test_cancelled_build_cleanup_observes_late_accepted_share(layer_database, layer_provider, monkeypatch):
    factory, redis = layer_database
    state, connection = layer_provider
    admitted = await admit(monkeypatch, connection)
    state["lose"] = "share"
    with pytest.raises(build_work.SubmissionUnknown):
        await execute(factory, redis, admitted["build_id"], "interrupted-before-share-observation")
    await layer_builder.cancel_layer_build(admitted["build_id"])
    member = f"layer:{admitted['build_id']}"
    async with WorkDispatcher(redis, "afterglow:builds", worker_id="cancel-cleanup-owner") as dispatcher:
        await dispatcher.publish([member])
        async with (
            work_lease(dispatcher, *await dispatcher.claim(90)) as lease,
            build_work.bind(redis, member, lease, cancel_cleanup=True),
        ):
            await run_layer_build(admitted["build_id"])
    assert [kind for kind, _ in state["creates"]] == ["port", "share"]
    assert state["shares"] == {}
    assert state["ports"] == {}
    async with factory() as session:
        row = await session.get(LayerBuild, admitted["build_id"])
        assert row.status == "cancelled"
        assert row.resource_snapshot["cancel_cleanup"] == "done"


@pytest.mark.asyncio
async def test_definitively_rejected_share_create_fails_build_and_disposes_port(
    layer_database, layer_provider, monkeypatch
):
    factory, redis = layer_database
    state, connection = layer_provider
    admitted = await admit(monkeypatch, connection)
    state["reject"] = "share"
    await execute(factory, redis, admitted["build_id"], "rejected-share-owner")
    assert [kind for kind, _ in state["creates"]] == ["port"]
    assert state["ports"] == {}
    async with factory() as session:
        row = await session.get(LayerBuild, admitted["build_id"])
        assert row.status == "error" and "400" in row.error_message
    assert state["shares"] == {}
