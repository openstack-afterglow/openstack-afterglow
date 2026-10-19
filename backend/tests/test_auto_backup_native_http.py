"""Installed Cinder SDK requests never replay an accepted recovery-point POST."""

import asyncio
import json
import socket
import threading
from contextlib import AsyncExitStack
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest
from keystoneauth1.session import Session
from keystoneauth1.token_endpoint import Token
from openstack.connection import Connection

from app.services import auto_backup as ab
from app.services import auto_snapshot
from app.services.work_dispatcher import WorkDispatcher
from tests.test_auto_backup import PROJECT, START, VOLUME
from tests.test_auto_backup import policy_redis as policy_redis


@pytest.fixture(params=["backup", "snapshot"])
def accepted_response_loss(request):
    kind = request.param
    plural = kind + "s"
    state = {"posts": [], "records": {}, "connections": [], "kind": kind}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, body):
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path = urlsplit(self.path).path.rstrip("/")
            if path in ("/v3", "/v3/" + PROJECT):
                self.reply(
                    200,
                    {
                        "version": {
                            "id": "v3.0",
                            "status": "CURRENT",
                            "min_version": "3.0",
                            "version": "3.70",
                            "links": [{"rel": "self", "href": endpoint + "/v3/"}],
                        }
                    },
                )
            elif path == f"/v3/{PROJECT}/volumes/{VOLUME}":
                self.reply(
                    200,
                    {
                        "volume": {
                            "id": VOLUME,
                            "status": "available",
                            "size": 1,
                            "attachments": [],
                            "os-vol-tenant-attr:tenant_id": PROJECT,
                        }
                    },
                )
            elif path == f"/v3/{PROJECT}/{plural}/detail":
                with lock:
                    records = list(state["records"].values())
                self.reply(200, {plural: records})
            elif path.startswith(f"/v3/{PROJECT}/{plural}/"):
                with lock:
                    record = state["records"].get(path.rsplit("/", 1)[-1])
                self.reply(200 if record else 404, {kind: record} if record else {"itemNotFound": {}})
            else:
                self.reply(404, {"itemNotFound": {}})

        def do_POST(self):
            if urlsplit(self.path).path.rstrip("/") != f"/v3/{PROJECT}/{plural}":
                self.reply(404, {"itemNotFound": {}})
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                state["posts"].append(body)
                backup_id = f"accepted-{len(state['posts'])}"
                record = {
                    **body[kind],
                    "id": backup_id,
                    "status": "available",
                    "size": 1,
                    **(
                        {
                            "is_incremental": body[kind]["incremental"],
                            "has_dependent_backups": False,
                            "os-backup-project-attr:project_id": PROJECT,
                        }
                        if kind == "backup"
                        else {"os-extended-snapshot-attributes:project_id": PROJECT}
                    ),
                    "created_at": "2026-06-01T03:00:00+00:00",
                }
                state["records"][backup_id] = record
                first = len(state["posts"]) == 1
            if first:
                # The provider committed; only its reply is lost. A transport
                # retry would create a second resource despite Redis slot fencing.
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                self.close_connection = True
            else:
                self.reply(202, {kind: record})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def factory(project_id):
        assert project_id == PROJECT
        conn = Connection(
            session=Session(auth=Token(endpoint=endpoint, token="synthetic-local-only")),
            block_storage_endpoint_override=endpoint + "/v3/" + PROJECT,
            block_storage_api_version="3",
            api_timeout=2,
        )
        state["connections"].append(conn)
        return conn

    try:
        yield state, factory
    finally:
        for conn in state["connections"]:
            conn.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.asyncio
async def test_three_workers_never_replay_accepted_post_after_response_loss(
    policy_redis, accepted_response_loss, monkeypatch
):
    state, factory = accepted_response_loss
    prefix = ab._PREFIX + ":snapshot"
    monkeypatch.setattr(auto_snapshot, "_PREFIX", prefix)
    monkeypatch.setattr(auto_snapshot, "_ALL_KEY", prefix + ":all_configs")
    if state["kind"] == "snapshot":
        service = auto_snapshot
        config = await service.enable_auto_snapshot(PROJECT, VOLUME, 1, 0, 0, now=START)
        get_config = service.get_auto_snapshot_config
        peer = ab
        await peer.enable_auto_backup(PROJECT, VOLUME, 1, 0, 0, now=START)
    else:
        service = ab
        config = await service.enable_auto_backup(PROJECT, VOLUME, 1, 0, 0, now=START)
        get_config = service.get_auto_backup_config
        peer = auto_snapshot
        await peer.enable_auto_snapshot(PROJECT, VOLUME, 1, 0, 0, now=START)
    peer_key = peer._key("config", PROJECT, VOLUME)
    peer_raw = await policy_redis.get(peer_key)
    clock = ab._time(config["next_run_at"])
    async with AsyncExitStack() as stack:
        workers = [
            await stack.enter_async_context(
                WorkDispatcher(policy_redis, service._PREFIX, worker_id=f"replica-{number}")
            )
            for number in range(3)
        ]
        await asyncio.gather(
            *(service.scheduler_tick(now=clock, dispatcher=worker, connection_factory=factory) for worker in workers)
        )
        assert len(state["posts"]) == 1
        uncertain = await get_config(PROJECT, VOLUME)
        assert uncertain["last_status"] == "unknown"
        assert uncertain[f"last_{state['kind']}_id"] is None

        for offset in (15, 30):
            await asyncio.gather(
                *(
                    service.scheduler_tick(
                        now=clock + timedelta(seconds=offset), dispatcher=worker, connection_factory=factory
                    )
                    for worker in workers
                )
            )
        completed = await get_config(PROJECT, VOLUME)
        assert completed["last_status"] == "available"
        assert completed[f"last_{state['kind']}_id"] == "accepted-1"
        assert len(state["posts"]) == 1
        assert set(state["records"]) == {"accepted-1"}
        if state["kind"] == "snapshot":
            posted = state["posts"][0]["snapshot"]
            assert posted["force"] is False
            assert posted["metadata"]["afterglow_policy_kind"] == "auto_snapshot"
            assert posted["metadata"]["afterglow_project_id"] == PROJECT
            assert posted["metadata"]["afterglow_volume_id"] == VOLUME
        else:
            posted = state["posts"][0]["backup"]
            assert posted["force"] is False
            assert posted["incremental"] is False
        # Both policies are due for the same volume, but this dispatcher must
        # neither submit nor advance the peer's configured lane.
        assert await policy_redis.get(peer_key) == peer_raw
        assert not await policy_redis.exists(peer._key("active", PROJECT, VOLUME))
        assert not await policy_redis.exists(peer._key("lease", PROJECT, VOLUME))
        assert not [key async for key in policy_redis.scan_iter(match=f"{peer._PREFIX}:dispatch:*")]


@pytest.mark.asyncio
async def test_mismatched_dispatcher_never_scans_or_executes_another_lane(
    policy_redis, accepted_response_loss, monkeypatch
):
    state, factory = accepted_response_loss
    prefix = ab._PREFIX + ":snapshot"
    monkeypatch.setattr(auto_snapshot, "_PREFIX", prefix)
    monkeypatch.setattr(auto_snapshot, "_ALL_KEY", prefix + ":all_configs")
    backup = await ab.enable_auto_backup(PROJECT, VOLUME, 1, 0, 0, now=START)
    await auto_snapshot.enable_auto_snapshot(PROJECT, VOLUME, 1, 0, 0, now=START)
    service, peer = (auto_snapshot, ab) if state["kind"] == "snapshot" else (ab, auto_snapshot)
    keys = [lane._key("config", PROJECT, VOLUME) for lane in (service, peer)]
    before = [await policy_redis.get(key) for key in keys]
    async with WorkDispatcher(policy_redis, peer._PREFIX, worker_id="wrong-lane") as worker:
        assert await worker.is_leader()
        await worker.publish([f"{PROJECT}:{VOLUME}"])
        with pytest.raises(ValueError, match="namespace does not match"):
            await service.scheduler_tick(
                now=ab._time(backup["next_run_at"]), dispatcher=worker, connection_factory=factory
            )
        assert await worker.pending() == 1
        assert [await policy_redis.get(key) for key in keys] == before
        for lane in (service, peer):
            assert not await policy_redis.exists(lane._key("active", PROJECT, VOLUME))
            assert not await policy_redis.exists(lane._key("lease", PROJECT, VOLUME))
        assert state["connections"] == []
        assert state["posts"] == []
