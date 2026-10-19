"""Configured identity endpoints must not silently fall back to public/another region."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from keystoneauth1.exceptions.catalog import EndpointNotFound

from app.services import keystone


@pytest.fixture
def identity_endpoints(monkeypatch):
    state = SimpleNamespace(requests=[], interface="internal", region="RegionTwo", domain_enabled=True)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, status, data, *, authenticated=False):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if authenticated:
                self.send_header("X-Subject-Token", "synthetic-operator-session")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            state.requests.append(("POST", self.path))
            assert self.path == "/v3/auth/tokens"
            self.reply(
                201,
                {
                    "token": {
                        "methods": ["password"],
                        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                        "user": {"id": "operator", "name": "operator", "domain": {"id": "default"}},
                        "project": {"id": "service", "name": "service", "domain": {"id": "default"}},
                        "roles": [{"id": "admin", "name": "admin"}],
                        "catalog": [
                            {
                                "id": "identity",
                                "type": "identity",
                                "name": "keystone",
                                "endpoints": [
                                    {
                                        "id": "other",
                                        "interface": "internal",
                                        "region": "RegionOne",
                                        "url": state.base + "/other/v3",
                                    },
                                    {
                                        "id": "public",
                                        "interface": "public",
                                        "region": "RegionTwo",
                                        "url": state.base + "/public/v3",
                                    },
                                    {
                                        "id": "internal",
                                        "interface": "internal",
                                        "region": "RegionTwo",
                                        "url": state.base + "/internal/v3",
                                    },
                                ],
                            }
                        ],
                    }
                },
                authenticated=True,
            )

        def do_GET(self):
            path = urlsplit(self.path).path.rstrip("/")
            state.requests.append(("GET", path))
            if path in {"/v3", "/internal/v3", "/public/v3", "/other/v3"}:
                self.reply(
                    200,
                    {
                        "version": {
                            "id": "v3.14",
                            "status": "stable",
                            "links": [{"rel": "self", "href": state.base + path + "/"}],
                        }
                    },
                )
            elif path == f"/{state.interface}/v3/domains/default":
                self.reply(200, {"domain": {"id": "default", "name": "Default", "enabled": state.domain_enabled}})
            else:
                self.reply(503, {"error": {"message": "wrong catalog endpoint"}})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.base = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(
        keystone,
        "get_settings",
        lambda: SimpleNamespace(
            os_auth_url=state.base + "/v3",
            os_username="operator",
            os_password="synthetic",
            os_project_name="service",
            os_user_domain_name="Default",
            os_project_domain_name="Default",
            os_interface=state.interface,
            os_region_name=state.region,
            ssl_verify=True,
        ),
    )
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("interface", ["internal", "public"])
def test_native_directory_uses_configured_interface_and_region(identity_endpoints, interface):
    state = identity_endpoints
    state.interface = interface
    client = keystone._get_admin_ks_client()
    try:
        domain = client.domains.get("default")
        assert (domain.id, domain.name, domain.enabled) == ("default", "Default", True)
        directory_reads = [path for method, path in state.requests if method == "GET" and "/domains/" in path]
        assert directory_reads == [f"/{interface}/v3/domains/default"]
    finally:
        client.session.session.close()


def test_missing_configured_region_does_not_fall_back(identity_endpoints):
    state = identity_endpoints
    state.region = "MissingRegion"
    client = keystone._get_admin_ks_client()
    try:
        with pytest.raises(EndpointNotFound):
            client.domains.get("default")
        assert not any("/domains/" in path for _, path in state.requests)
    finally:
        client.session.session.close()


def test_native_operation_reuses_real_service_auth_but_invalidates_reads(identity_endpoints):
    from fastapi import HTTPException

    from app.services.domain_scope import resolve_domain
    from app.services.native_operation import NativeOperation

    state = identity_endpoints
    with NativeOperation() as operation:
        assert resolve_domain("default", operation=operation)["enabled"] is True
        assert resolve_domain("default", operation=operation)["enabled"] is True
        assert state.requests.count(("POST", "/v3/auth/tokens")) == 1
        assert state.requests.count(("GET", "/internal/v3/domains/default")) == 1
        state.domain_enabled = False
        operation.invalidate()
        with pytest.raises(HTTPException) as denied:
            resolve_domain("default", operation=operation)
        assert denied.value.status_code == 403
        # Invalidating authority reads does not reauthenticate the service client.
        assert state.requests.count(("POST", "/v3/auth/tokens")) == 1
        assert state.requests.count(("GET", "/internal/v3/domains/default")) == 2
    with NativeOperation() as next_request:
        with pytest.raises(HTTPException) as denied:
            resolve_domain("default", operation=next_request)
        assert denied.value.status_code == 403
    assert state.requests.count(("POST", "/v3/auth/tokens")) == 2


def test_concurrent_native_operations_do_not_share_real_service_sessions(identity_endpoints):
    from concurrent.futures import ThreadPoolExecutor

    from app.services.domain_scope import resolve_domain
    from app.services.native_operation import NativeOperation

    rendezvous = threading.Barrier(2)

    def request():
        with NativeOperation() as operation:
            first = resolve_domain("default", operation=operation)
            rendezvous.wait(timeout=5)
            second = resolve_domain("default", operation=operation)
            assert first == second
            return operation.ks

    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(request) for _ in range(2)]
        clients = [request.result(timeout=10) for request in requests]
    assert clients[0] is not clients[1]
    assert identity_endpoints.requests.count(("POST", "/v3/auth/tokens")) == 2
    assert identity_endpoints.requests.count(("GET", "/internal/v3/domains/default")) == 2
