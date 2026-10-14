"""Installed Trove SDK: journaled creates make exactly one native HTTP POST."""

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

from app.services import db_auto_backup as dab
from app.services import trove
from tests.test_db_auto_backup import (  # noqa: F401 - pytest fixture import
    INSTANCE,
    PROJECT,
    SLOT,
    db_redis,
    enable,
    join,
    scan,
)


@pytest.fixture
def native_trove():
    state = {
        "posts": [],
        "records": {},
        "connections": [],
        "mode": "disconnect",
        "listing_status": 200,
        "invalidations": 0,
    }
    lock = threading.Lock()

    class Auth(Token):
        def invalidate(self):
            state["invalidations"] += 1
            return True

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
            if path.endswith("/backups"):
                with lock:
                    records = list(state["records"].values())
                self.reply(state["listing_status"], {"backups": records})
            else:
                # Native endpoint discovery, not a fake SDK adapter.
                self.reply(
                    200,
                    {
                        "version": {
                            "id": "v1.0",
                            "status": "CURRENT",
                            "links": [{"rel": "self", "href": endpoint + "/v1.0/"}],
                        }
                    },
                )

        def do_POST(self):
            if urlsplit(self.path).path.rstrip("/") != f"/v1.0/{PROJECT}/backups":
                self.reply(404, {"itemNotFound": {}})
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                state["posts"].append(body)
                backup_id = f"accepted-{len(state['posts'])}"
                record = {
                    **body["backup"],
                    "id": backup_id,
                    "instance_id": body["backup"]["instance"],
                    "status": "COMPLETED",
                    "created": SLOT.isoformat(),
                }
                state["records"][backup_id] = record
                first = len(state["posts"]) == 1
            if first and state["mode"] == "disconnect":
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                self.close_connection = True
            elif first and state["mode"] in ("503", "401"):
                self.reply(int(state["mode"]), {"error": "committed but misleading response"})
            else:
                self.reply(202, {"backup": record})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def factory(project):
        assert project == PROJECT
        conn = Connection(
            session=Session(auth=Auth(endpoint=endpoint, token="synthetic-local-only"), connect_retries=2),
            database_endpoint_override=f"{endpoint}/v1.0/{PROJECT}",
            database_api_version="1",
            database_status_code_retries=2,
            database_connect_retries=2,
            api_timeout=2,
        )
        conn.database.status_code_retries = 2
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
@pytest.mark.parametrize("mode", ["disconnect", "503", "401"])
async def test_three_native_workers_make_one_post_after_lost_or_retryable_reply(db_redis, native_trove, mode):  # noqa: F811 - pytest fixture
    state, factory = native_trove
    state["mode"] = mode
    await enable()
    async with AsyncExitStack() as stack:
        workers = await join(stack, db_redis)
        await scan(workers)
        await asyncio.gather(*(dab._execute_tick(worker, factory) for worker in workers))
        assert len(state["posts"]) == 1
        key = dab._key("journal", f"{PROJECT}:{INSTANCE}:daily:{SLOT.isoformat()}")
        assert json.loads(await db_redis.get(key))["state"] == "unknown"
        assert state["invalidations"] == 0
        for offset in (15, 30):
            await scan(workers, SLOT + timedelta(seconds=offset))
            for worker in workers:
                await dab._execute_tick(worker, factory)
        assert json.loads(await db_redis.get(key))["state"] == "accepted"
        assert len(state["posts"]) == 1
        assert set(state["records"]) == {"accepted-1"}


@pytest.mark.parametrize("mode", ["503", "401"])
def test_no_retry_is_scoped_and_request_bound_callers_keep_sdk_behavior(native_trove, mode):
    state, factory = native_trove
    state["mode"] = mode
    conn = factory(PROJECT)
    with pytest.raises(Exception):
        trove.create_backup(conn, INSTANCE, "journaled", no_retry=True)
    assert len(state["posts"]) == 1
    assert state["invalidations"] == 0
    state["posts"].clear()
    state["records"].clear()
    result = trove.create_backup(conn, INSTANCE, "request-bound")
    assert result["id"] == "accepted-2"
    assert len(state["posts"]) == 2
    if mode == "401":
        assert state["invalidations"] == 1


def test_native_listing_error_is_not_empty_evidence(native_trove):
    state, factory = native_trove
    state["listing_status"] = 500
    conn = factory(PROJECT)
    with pytest.raises(Exception):
        trove.list_backups(conn, INSTANCE, strict=True)
    assert trove.list_backups(conn, INSTANCE) == []
    assert state["posts"] == []
