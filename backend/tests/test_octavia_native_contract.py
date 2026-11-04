"""Actual SDK serialization must not join every pool to every load balancer."""

import json
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from keystoneauth1.exceptions.catalog import EndpointNotFound
from keystoneauth1.noauth import NoAuth
from keystoneauth1.session import Session
from openstack.connection import Connection

from app.api.deps import get_os_conn, get_token_info
from app.api.network import loadbalancers, networks
from app.models.storage import TopologyData
from app.services import octavia


@pytest.fixture
def native_octavia():
    state = SimpleNamespace(pool_queries=[], member_reads=Counter(), fail_pools=False)
    lbs = [
        {"id": "lb-a", "name": "a", "project_id": "project-a", "provisioning_status": "ACTIVE"},
        {"id": "lb-b", "name": "b", "project_id": "project-b", "provisioning_status": "ACTIVE"},
    ]
    pools = [
        {"id": "pool-a", "name": "a", "loadbalancers": [{"id": "lb-a"}]},
        {"id": "pool-b", "name": "b", "loadbalancers": [{"id": "lb-b"}]},
    ]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            path = parsed.path
            status = 200
            if path.rstrip("/") in ("", "/v2.0"):
                data = {
                    "version": {
                        "id": "v2.0",
                        "status": "CURRENT",
                        "links": [{"rel": "self", "href": f"http://127.0.0.1:{self.server.server_port}/v2.0/"}],
                    }
                }
            elif path.endswith("/loadbalancers"):
                owner = query.get("project_id", [None])[0]
                data = {"loadbalancers": [lb for lb in lbs if owner is None or lb["project_id"] == owner]}
            elif "/loadbalancers/" in path:
                data = {"loadbalancer": next(lb for lb in lbs if lb["id"] == path.rsplit("/", 1)[1])}
            elif path.endswith("/listeners"):
                data = {"listeners": []}
            elif path.endswith("/pools"):
                state.pool_queries.append(query)
                if state.fail_pools:
                    status, data = 503, {"error": "private-upstream-body-canary"}
                else:
                    target = query.get("loadbalancer_id", [None])[0]
                    data = {
                        "pools": [pool for pool in pools if target is None or pool["loadbalancers"][0]["id"] == target]
                    }
            elif path.endswith("/members"):
                pool_id = path.split("/")[-2]
                state.member_reads[pool_id] += 1
                data = {
                    "members": [
                        {"id": "member-" + pool_id, "name": "member", "address": "10.0.0.7", "protocol_port": 8080}
                    ]
                }
            else:
                status, data = 404, {}
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    native = Connection(
        session=Session(auth=NoAuth(), timeout=2),
        load_balancer_endpoint_override=f"http://127.0.0.1:{server.server_port}/v2.0",
        load_balancer_api_version="2",
    )
    native._afterglow_project_id = "project-a"
    native._afterglow_authenticated_project_id = "project-a"
    try:
        yield native, state
    finally:
        native.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_pool_endpoint_uses_native_filter_and_excludes_foreign_lb(native_octavia):
    native, state = native_octavia
    api = FastAPI()
    api.include_router(loadbalancers.router, prefix="/api/v1/loadbalancers")
    api.dependency_overrides[get_os_conn] = lambda: native
    api.dependency_overrides[get_token_info] = lambda: {"user_id": "user-a", "project_id": "project-a"}
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await client.get("/api/v1/loadbalancers/lb-a/pools")
    assert response.status_code == 200
    assert [(pool["id"], pool["load_balancer_id"]) for pool in response.json()] == [("pool-a", "lb-a")]
    assert state.pool_queries == [{"loadbalancer_id": ["lb-a"]}]


def test_topology_native_pools_are_read_once_and_project_edges_do_not_collide(native_octavia):
    native, state = native_octavia
    rows = octavia.get_topology_lbs(
        native,
        instances=[
            {"id": "server-a", "project_id": "project-a", "ip_addresses": [{"addr": "10.0.0.7", "type": "fixed"}]},
            {"id": "server-b", "project_id": "project-b", "ip_addresses": [{"addr": "10.0.0.7", "type": "fixed"}]},
        ],
    )
    assert {row["id"]: [(member["pool_id"], member["server_id"]) for member in row["members"]] for row in rows} == {
        "lb-a": [("pool-a", "server-a")],
        "lb-b": [("pool-b", "server-b")],
    }
    assert sorted(query["loadbalancer_id"][0] for query in state.pool_queries) == ["lb-a", "lb-b"]
    assert state.member_reads == {"pool-a": 1, "pool-b": 1}


def test_ambiguous_or_floating_addresses_never_create_fixed_member_edges(native_octavia):
    native, _ = native_octavia
    rows = octavia.get_topology_lbs(
        native,
        instances=[
            {"id": "server-a", "project_id": "project-a", "ip_addresses": [{"addr": "10.0.0.7", "type": "fixed"}]},
            {
                "id": "server-a-duplicate",
                "project_id": "project-a",
                "ip_addresses": [{"addr": "10.0.0.7", "type": "fixed"}],
            },
            {"id": "server-b", "project_id": "project-b", "ip_addresses": [{"addr": "10.0.0.7", "type": "floating"}]},
        ],
    )
    assert [member["server_id"] for row in rows for member in row["members"]] == [None, None]


@pytest.mark.asyncio
async def test_partial_native_topology_failure_is_503_not_plausible_empty_graph(native_octavia, monkeypatch):
    native, state = native_octavia
    state.fail_pools = True
    monkeypatch.setattr(networks.neutron, "get_topology", lambda *_args, **_kwargs: TopologyData())
    monkeypatch.setattr(networks.neutron, "build_compute_port_index", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(networks.nova, "list_servers", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(networks.trove, "topology_database_ips", lambda *_args, **_kwargs: set())

    async def uncached(_key, _ttl, fetch, **_kwargs):
        return fetch()

    monkeypatch.setattr(networks, "cached_call", uncached)
    api = FastAPI()
    api.include_router(networks.router, prefix="/api/v1/networks")
    api.dependency_overrides[get_os_conn] = lambda: native
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await client.get("/api/v1/networks/topology")
    assert response.status_code == 503
    assert response.json() == {"detail": "topology_load_balancers_unavailable"}
    assert "private-upstream-body-canary" not in response.text


def test_absent_catalog_is_distinct_from_transport_failure(monkeypatch):
    def absent(*_args, **_kwargs):
        raise EndpointNotFound("not configured")

    monkeypatch.setattr(octavia, "list_load_balancers", absent)
    assert octavia.get_topology_lbs(object()) == []
