"""Native Nova resolution must not stall unrelated async work in metric reads.

Identity and downstream telemetry are fixtures. Server resolution uses the
installed OpenStack SDK and a real bounded loopback HTTP peer.
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock

import pytest
from keystoneauth1 import session
from keystoneauth1.token_endpoint import Token
from openstack.connection import Connection

from app.api.compute import instance_metrics


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["metrics?metric=cpu", "metrics-batch?metrics=cpu", "metrics-summary"])
async def test_native_server_resolution_keeps_the_event_loop_available(client, mock_conn, monkeypatch, suffix):
    loop = asyncio.get_running_loop()
    released = threading.Event()
    observations = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path.endswith("/servers/inst-1") or path.endswith("/flavors/detail"):
                # Only the live application loop can release this native read.
                # A synchronous call on that loop times out before it can do so.
                released.clear()
                loop.call_soon_threadsafe(released.set)
                observations.append(released.wait(0.5))
                value = {
                    "server": {
                        "id": "inst-1",
                        "name": "owned-fixture",
                        "status": "ACTIVE",
                        "tenant_id": "test-project-123",
                        "addresses": {},
                        "metadata": {},
                        "flavor": {},
                        "image": {},
                    }
                }
                if path.endswith("/flavors/detail"):
                    value = {"flavors": []}
            else:
                value = {
                    "version": {
                        "id": "v2.1",
                        "status": "CURRENT",
                        "links": [{"rel": "self", "href": endpoint + "/v2.1/"}],
                    }
                }
            body = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = Connection(
        session=session.Session(auth=Token(endpoint, "synthetic-metrics-native-token")),
        compute_endpoint_override=endpoint + "/v2.1/test-project-123",
        compute_api_version="2",
        connect_retries=0,
        status_code_retries=0,
    )
    mock_conn.compute = conn.compute
    monkeypatch.setattr(instance_metrics.native_telemetry, "instance_series", AsyncMock(return_value={}))
    monkeypatch.setattr(instance_metrics, "query_range", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        instance_metrics, "query_instant_multi", AsyncMock(return_value=[({"instance_id": "inst-1"}, 5.0)])
    )
    try:
        response = await client.get("/api/v1/instances/inst-1/" + suffix)
        assert response.status_code == 200
        expected_reads = 2 if suffix == "metrics-summary" else 1
        assert observations == [True] * expected_reads, "Native HTTP blocked the application event loop"
    finally:
        released.set()
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join()
