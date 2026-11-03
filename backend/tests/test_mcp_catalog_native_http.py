"""Nova's native target visibility and filtered provider-call bounds via installed SDK."""

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from keystoneauth1.session import Session
from keystoneauth1.token_endpoint import Token
from openstack.connection import Connection

from app.services.mcp_control_plane.catalog import list_project_flavors


@contextmanager
def native_catalog(*, admin):
    project = "target-project"
    rows = [
        {"id": "foreign4", "name": "foreign4", "vcpus": 4, "ram": 8192, "disk": 0, "os-flavor-access:is_public": False},
        {"id": "wanted4", "name": "cpu.4c_8g", "vcpus": 4, "ram": 8192, "disk": 0, "os-flavor-access:is_public": False},
        {
            "id": "other8",
            "name": "cpu.8c_16g",
            "vcpus": 8,
            "ram": 16384,
            "disk": 0,
            "os-flavor-access:is_public": False,
        },
    ]
    state = {"requests": [], "acl": [], "specs": []}

    class Native(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, payload, status=200):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            parsed = urlsplit(self.path)
            path, query = parsed.path, parse_qs(parsed.query)
            state["requests"].append((path, query))
            if path.rstrip("/") == "/v2.1":
                self.reply(
                    {
                        "version": {
                            "id": "v2.1",
                            "status": "CURRENT",
                            "min_version": "2.1",
                            "version": "2.95",
                            "links": [{"rel": "self", "href": f"http://127.0.0.1:{self.server.server_port}/v2.1/"}],
                        }
                    }
                )
            elif path == "/v2.1/flavors/detail":
                # Nova2025.2 FlavorList SQL: default public=True OR exact project
                # ACL; an admin's explicit string None removes the whole filter.
                visible = rows if admin and query.get("is_public") == ["None"] else rows[1:]
                self.reply({"flavors": visible[: int(query.get("limit", [100])[0])]})
            elif path.endswith("/os-flavor-access"):
                flavor_id = path.split("/")[-2]
                state["acl"].append(flavor_id)
                if not admin:
                    self.reply({"error": "admin-only ACL inspection"}, 403)
                else:
                    owner = project if flavor_id != "foreign4" else "foreign-project"
                    self.reply({"flavor_access": [{"flavor_id": flavor_id, "tenant_id": owner}]})
            elif path.endswith("/os-extra_specs"):
                state["specs"].append(path.split("/")[-2])
                self.reply({"extra_specs": {"afterglow:cpu_control_token": "not-public"}})
            else:
                self.reply({"error": "unknown native path"}, 404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Native)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/v2.1"
    conn = Connection(
        session=Session(auth=Token(endpoint, "synthetic-native-token")),
        compute_endpoint_override=endpoint,
        compute_api_version="2",
        compute_default_microversion="2.61",
        connect_retries=0,
    )
    conn._afterglow_project_id = project
    conn._afterglow_compute_admin = admin
    try:
        yield conn, state
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
@pytest.mark.parametrize("admin", [False, True], ids=["member", "native-admin"])
async def test_native_project_catalog_excludes_foreign_and_filters_before_acl_and_specs(admin):
    with native_catalog(admin=admin) as (conn, native):
        result = await list_project_flavors(conn, project_id="target-project", limit=3, vcpus=4, ram_mb=8192)
    assert [row["id"] for row in result["flavors"]] == ["wanted4"]
    assert result["next_marker"] is None  # only two raw target-visible rows
    assert native["acl"] == (["wanted4"] if admin else [])
    assert native["specs"] == ["wanted4"]
    assert "not-public" not in json.dumps(result)
    list_requests = [query for path, query in native["requests"] if path == "/v2.1/flavors/detail"]
    assert list_requests == [{"limit": ["3"], "is_public": ["True"]}]
