"""Installed Cinder SDK requests must not replay an accepted backup POST."""

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
from app.services.work_dispatcher import WorkDispatcher
from tests.test_auto_backup import PROJECT, START, VOLUME
from tests.test_auto_backup import policy_redis as policy_redis


@pytest.fixture
def accepted_response_loss():
    state = {"posts": [], "records": {}, "connections": []}
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
            elif path == f"/v3/{PROJECT}/backups/detail":
                with lock:
                    records = list(state["records"].values())
                self.reply(200, {"backups": records})
            elif path.startswith(f"/v3/{PROJECT}/backups/"):
                with lock:
                    record = state["records"].get(path.rsplit("/", 1)[-1])
                self.reply(200 if record else 404, {"backup": record} if record else {"itemNotFound": {}})
            else:
                self.reply(404, {"itemNotFound": {}})

        def do_POST(self):
            if urlsplit(self.path).path.rstrip("/") != f"/v3/{PROJECT}/backups":
                self.reply(404, {"itemNotFound": {}})
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                state["posts"].append(body)
                backup_id = f"accepted-{len(state['posts'])}"
                record = {
                    **body["backup"],
                    "id": backup_id,
                    "status": "available",
                    "size": 1,
                    "is_incremental": body["backup"]["incremental"],
                    "has_dependent_backups": False,
                    "os-backup-project-attr:project_id": PROJECT,
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
                self.reply(202, {"backup": record})

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
async def test_three_workers_never_replay_accepted_post_after_response_loss(policy_redis, accepted_response_loss):
    state, factory = accepted_response_loss
    config = await ab.enable_auto_backup(PROJECT, VOLUME, 1, 0, 0, now=START)
    clock = ab._time(config["next_run_at"])
    async with AsyncExitStack() as stack:
        workers = [
            await stack.enter_async_context(WorkDispatcher(policy_redis, ab._PREFIX, worker_id=f"replica-{number}"))
            for number in range(3)
        ]
        await asyncio.gather(
            *(ab.scheduler_tick(now=clock, dispatcher=worker, connection_factory=factory) for worker in workers)
        )
        assert len(state["posts"]) == 1
        uncertain = await ab.get_auto_backup_config(PROJECT, VOLUME)
        assert uncertain["last_status"] == "unknown"
        assert uncertain["last_backup_id"] is None

        for offset in (15, 30):
            await asyncio.gather(
                *(
                    ab.scheduler_tick(
                        now=clock + timedelta(seconds=offset), dispatcher=worker, connection_factory=factory
                    )
                    for worker in workers
                )
            )
        completed = await ab.get_auto_backup_config(PROJECT, VOLUME)
        assert completed["last_status"] == "available"
        assert completed["last_backup_id"] == "accepted-1"
        assert len(state["posts"]) == 1
        assert set(state["records"]) == {"accepted-1"}
