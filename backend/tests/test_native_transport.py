"""Real loopback wire regressions: reuse sockets, never caller authority or TLS trust."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from keystoneauth1.exceptions.connection import ConnectFailure, SSLError
from keystoneauth1.exceptions.http import HttpError
from keystoneauth1.identity import v3

from app.services import keystone, native_transport


@contextmanager
def transport_server(*, tls_context=None):
    """Also usable by a runpy smoke without pytest's application-wide fixtures."""
    native_transport.close_pools()
    state = SimpleNamespace(
        lock=threading.Lock(), connections=[], requests=[], auth=[], tokens={}, barrier=None, domain_enabled=True
    )

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        block_on_close = False

        def get_request(self):
            connection, address = super().get_request()
            try:
                if tls_context is not None:
                    connection = tls_context.wrap_socket(connection, server_side=True)
            except BaseException:
                connection.close()
                raise
            with state.lock:
                state.connections.append(
                    SimpleNamespace(socket=connection, number=len(state.connections) + 1, closed=threading.Event())
                )
            return connection, address

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            with state.lock:
                self.observed_connection = next(item for item in state.connections if item.socket is self.connection)

        def finish(self):
            try:
                super().finish()
            finally:
                self.observed_connection.closed.set()

        def log_message(self, *_args):
            pass

        def record(self, body=None):
            observation = {
                "method": self.command,
                "path": urlsplit(self.path).path,
                "connection": self.observed_connection.number,
                "token": self.headers.get("X-Auth-Token"),
                "operation": self.headers.get("X-Operation"),
                "private": self.headers.get("X-Only-Alice"),
                "once": self.headers.get("X-Once"),
                "cookie": self.headers.get("Cookie"),
                "body": body,
            }
            with state.lock:
                observation["project"] = state.tokens.get(observation["token"])
                state.requests.append(observation)
            return observation

        def reply(self, status, data, *, token=None, cookie=None):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if token is not None:
                self.send_header("X-Subject-Token", token)
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            observation = self.record(body)
            if observation["path"] == "/accepted-disconnect":
                # The mutation was accepted; only its response is lost. Replaying is unsafe.
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            if observation["path"] != "/v3/auth/tokens":
                self.reply(404, {"error": {"message": "unknown synthetic route"}})
                return
            auth = body["auth"]
            identity = auth["identity"]
            method = identity["methods"][0]
            caller = identity["token"]["id"] if method == "token" else identity["password"]["user"]["name"]
            scope = auth["scope"]["project"]
            project = scope.get("id", scope.get("name"))
            with state.lock:
                state.auth.append(observation)
                token = f"issued-{len(state.auth)}-{caller}-{project}"
                state.tokens[token] = project
            self.reply(
                201,
                {
                    "token": {
                        "methods": [method],
                        "issued_at": "2026-01-01T00:00:00Z",
                        "expires_at": "2099-01-01T00:00:00Z",
                        "user": {"id": caller, "name": caller, "domain": {"id": "default"}},
                        "project": {"id": project, "name": project, "domain": {"id": "default"}},
                        "roles": [{"id": "member", "name": "member"}],
                        "catalog": [
                            {
                                "id": "identity",
                                "name": "keystone",
                                "type": "identity",
                                "endpoints": [
                                    {
                                        "id": "identity-internal",
                                        "interface": "internal",
                                        "region": "RegionOne",
                                        "url": state.base + "/v3",
                                    }
                                ],
                            }
                        ],
                    }
                },
                token=token,
            )

        def do_GET(self):
            observation = self.record()
            path = observation["path"]
            if path == "/v3":
                self.reply(
                    200,
                    {
                        "version": {
                            "id": "v3.14",
                            "status": "stable",
                            "links": [{"rel": "self", "href": state.base + "/v3/"}],
                        }
                    },
                )
            elif path == "/v3/domains/default":
                self.reply(200, {"domain": {"id": "default", "name": "Default", "enabled": state.domain_enabled}})
            elif path.startswith("/status/"):
                status = int(path.rsplit("/", 1)[1])
                self.reply(status, {"error": {"code": status, "message": "synthetic native refusal"}})
            elif path in {"/service/v1/clusters", "/barrier", "/echo"}:
                if path == "/barrier":
                    state.barrier.wait(timeout=10)
                caller = observation["operation"]
                cookie = f"owner={caller}; Path=/" if caller else None
                self.reply(200, {"clusters": [observation]}, cookie=cookie)
            else:
                self.reply(404, {"error": {"message": "unknown synthetic route"}})

    server = Server(("127.0.0.1", 0), Handler)
    state.base = f"{'https' if tls_context else 'http'}://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        # Pool ownership ends before the upstream disappears. Explicitly terminate
        # handlers too so a failing implementation cannot hang the pytest process.
        native_transport.close_pools()
        for connection in state.connections:
            with suppress(OSError):
                connection.socket.shutdown(socket.SHUT_RDWR)
            connection.socket.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), "synthetic transport listener did not stop"


@pytest.fixture
def native_wire(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    with transport_server() as state:
        monkeypatch.setattr(
            keystone,
            "get_settings",
            lambda: SimpleNamespace(
                os_auth_url=state.base + "/v3",
                os_username="operator",
                os_password="synthetic-password",
                os_project_name="service",
                os_user_domain_name="Default",
                os_project_domain_name="Default",
                os_interface="internal",
                os_region_name="RegionOne",
                ssl_verify=True,
                service_drover_internal_url=state.base + "/service/v1",
            ),
        )
        yield state


@contextmanager
def caller_client(state, caller, project, *, sdk):
    """Use actual production factories, including the SDK's lazy session path."""
    connection = None
    if sdk:
        connection = keystone.get_openstack_connection(caller, project)
        session = connection.session

        def read():
            return keystone.get_drover_proxy(connection).clusters()["clusters"][0]

    else:
        session = native_transport.create_session(
            auth=v3.Token(auth_url=state.base + "/v3", token=caller, project_id=project), timeout=5
        )

        def read():
            return session.get(state.base + "/service/v1/clusters").json()["clusters"][0]

    try:
        yield session, read
    finally:
        session.session.close()
        if connection is not None:
            connection.close()


@pytest.mark.parametrize("sdk", [False, True], ids=["keystoneauth", "openstacksdk"])
def test_sequential_callers_reuse_tcp_after_session_close_without_sharing_authority(native_wire, sdk):
    state = native_wire
    sessions = []
    observed = []
    for caller, project in [("alice", "project-a"), ("bob", "project-b")]:
        with caller_client(state, caller, project, sdk=sdk) as (session, read):
            sessions.append(session)
            session.session.headers["X-Operation"] = caller
            if caller == "alice":
                session.session.headers["X-Only-Alice"] = "alice-private"
            first = read()
            once = session.get(state.base + "/echo", headers={"X-Once": "one-request"}).json()["clusters"][0]
            again = read()
            observed.append((first, once, again))
            assert first["cookie"] is None
            assert once["cookie"] == again["cookie"] == f"owner={caller}"
            assert once["once"] == "one-request"
            assert first["once"] is None and again["once"] is None
            assert {row["project"] for row in (first, once, again)} == {project}
            assert {row["operation"] for row in (first, once, again)} == {caller}
            assert {row["private"] for row in (first, once, again)} == {"alice-private" if caller == "alice" else None}

    assert sessions[0] is not sessions[1]
    assert sessions[0].session is not sessions[1].session
    assert sessions[0].auth is not sessions[1].auth
    assert len(state.connections) == 1
    assert len(state.auth) == 2
    assert [row["body"]["auth"]["identity"]["token"]["id"] for row in state.auth] == ["alice", "bob"]
    assert [row["body"]["auth"]["scope"]["project"]["id"] for row in state.auth] == ["project-a", "project-b"]
    assert all(row["cookie"] is None for row in state.auth)
    assert {row["token"] for row in observed[0]} == {"issued-1-alice-project-a"}
    assert {row["token"] for row in observed[1]} == {"issued-2-bob-project-b"}


def test_service_clients_reuse_tcp_but_perform_fresh_password_authentication(native_wire):
    state = native_wire
    for _ in range(2):
        client = keystone._get_admin_ks_client()
        try:
            domain = client.domains.get("default")
            assert (domain.id, domain.enabled) == ("default", True)
        finally:
            client.session.session.close()
    assert len(state.connections) == 1
    assert len(state.auth) == 2
    for row in state.auth:
        auth = row["body"]["auth"]
        assert auth["identity"]["methods"] == ["password"]
        assert auth["identity"]["password"]["user"]["name"] == "operator"
        assert auth["identity"]["password"]["user"]["password"] == "synthetic-password"
        assert auth["scope"]["project"]["name"] == "service"
    assert [row["token"] for row in state.requests if row["path"] == "/v3/domains/default"] == [
        "issued-1-operator-service",
        "issued-2-operator-service",
    ]


def test_new_native_operation_observes_revoked_authority_on_reused_socket(native_wire):
    from fastapi import HTTPException

    from app.services.domain_scope import resolve_domain
    from app.services.native_operation import NativeOperation

    state = native_wire
    with NativeOperation() as operation:
        assert resolve_domain("default", operation=operation)["enabled"] is True
        assert resolve_domain("default", operation=operation)["enabled"] is True
    state.domain_enabled = False
    with NativeOperation() as operation:
        with pytest.raises(HTTPException) as denied:
            resolve_domain("default", operation=operation)
    assert denied.value.status_code == 403
    assert len(state.auth) == 2
    reads = [row for row in state.requests if row["path"] == "/v3/domains/default"]
    assert [row["token"] for row in reads] == ["issued-1-operator-service", "issued-2-operator-service"]
    assert len(state.connections) == 1


@pytest.mark.parametrize("sdk", [False, True], ids=["keystoneauth", "openstacksdk"])
def test_simultaneous_callers_keep_credentials_headers_and_cookies_independent(native_wire, sdk):
    state = native_wire
    state.barrier = threading.Barrier(2)

    def call(caller, project):
        with caller_client(state, caller, project, sdk=sdk) as (session, _read):
            session.session.headers["X-Operation"] = caller
            session.session.cookies.set("seed", caller)
            row = session.get(state.base + "/barrier").json()["clusters"][0]
            return session, row

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(call, caller, project) for caller, project in [("alice", "project-a"), ("bob", "project-b")]
        ]
        results = [future.result(timeout=15) for future in futures]
    assert results[0][0] is not results[1][0]
    assert len({row["connection"] for _, row in results}) == 2
    assert len(state.auth) == 2
    for (_, row), caller, project in zip(results, ["alice", "bob"], ["project-a", "project-b"], strict=True):
        assert row["operation"] == caller
        assert row["project"] == project
        assert row["cookie"] == f"seed={caller}"
        assert row["token"] in {f"issued-1-{caller}-{project}", f"issued-2-{caller}-{project}"}
    assert {row["body"]["auth"]["identity"]["token"]["id"] for row in state.auth} == {"alice", "bob"}


def tls_material(tmp_path):
    """Generate disposable self-signed localhost roots; no external openssl process."""

    def certificate(name):
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        now = datetime.now(UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False
            )
            .sign(key, hashes.SHA256())
        )
        cert_path = tmp_path / f"{name}.pem"
        key_path = tmp_path / f"{name}.key"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
        return cert_path, key_path

    trusted, key = certificate("transport-loopback")
    wrong_ca, _ = certificate("unrelated-loopback")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(trusted, key)
    return context, str(trusted), str(wrong_ca)


def test_insecure_tls_socket_cannot_bypass_verification_or_wrong_ca(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    context, trusted, wrong_ca = tls_material(tmp_path)
    with transport_server(tls_context=context) as state:

        def get(verify):
            session = native_transport.create_session(verify=verify, timeout=5)
            try:
                return session.get(state.base + "/echo", authenticated=False).json()["clusters"][0]
            finally:
                session.session.close()

        insecure = get(False)
        for verify in (True, wrong_ca):
            with pytest.raises(SSLError):
                get(verify)
        assert len(state.requests) == 1, "a rejected trust policy must never reach the HTTP handler"
        secure = get(trusted)
        assert secure["connection"] != insecure["connection"]
        assert get(False)["connection"] == insecure["connection"]
        assert get(trusted)["connection"] == secure["connection"]


def test_close_pools_closes_idle_socket_and_next_session_opens_new_generation(native_wire):
    state = native_wire
    first = native_transport.create_session(timeout=5)
    try:
        first_response = first.get(state.base + "/echo", authenticated=False)
        first_row = first_response.json()["clusters"][0]
    finally:
        first.session.close()
    idle = state.connections[0]
    native_transport.close_pools()
    assert idle.closed.wait(timeout=5), "pool shutdown did not send EOF to the idle native connection"
    assert first_response.json()["clusters"][0] == first_row
    native_transport.close_pools()
    next_session = native_transport.create_session(timeout=5)
    try:
        next_row = next_session.get(state.base + "/echo", authenticated=False).json()["clusters"][0]
    finally:
        next_session.session.close()
    assert len(state.connections) == 2
    assert next_row["connection"] != first_row["connection"]


async def test_api_shutdown_drains_owners_then_closes_real_idle_pool(native_wire, monkeypatch):
    from app import database
    from app import main as api
    from app.services import host_health, openstack_notifications, prom_query

    async def external_owner_closed(*_args):
        return None

    monkeypatch.setattr(api, "_background_tasks", set())
    monkeypatch.setattr(api, "_notification_collector", None)
    monkeypatch.setattr(host_health, "aclose_client", external_owner_closed)
    monkeypatch.setattr(openstack_notifications, "stop_notification_collector", external_owner_closed)
    monkeypatch.setattr(api, "stop_mcp_transport", external_owner_closed)
    monkeypatch.setattr(database, "close_db", external_owner_closed)
    monkeypatch.setattr(prom_query, "aclose_client", external_owner_closed)

    state = native_wire
    session = native_transport.create_session(timeout=5)
    try:
        retained_response = session.get(state.base + "/echo", authenticated=False)
        first_row = retained_response.json()["clusters"][0]
    finally:
        session.session.close()
    idle = state.connections[0]
    started, cancelled, drain = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def native_owner():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            await drain.wait()

    owner = asyncio.create_task(native_owner())
    api._background_tasks.add(owner)
    await asyncio.wait_for(started.wait(), timeout=5)
    shutdown = asyncio.create_task(api.shutdown_event())
    try:
        await asyncio.wait_for(cancelled.wait(), timeout=5)
        assert not shutdown.done()
        assert not idle.closed.is_set(), "shutdown closed native transport before its owner drained"
        drain.set()
        await asyncio.wait_for(shutdown, timeout=5)
        assert await asyncio.to_thread(idle.closed.wait, 5), "API shutdown left the idle native socket open"
        assert retained_response.json()["clusters"][0] == first_row
        replacement = native_transport.create_session(timeout=5)
        try:
            next_row = replacement.get(state.base + "/echo", authenticated=False).json()["clusters"][0]
        finally:
            replacement.session.close()
        assert next_row["connection"] != first_row["connection"]
        assert len(state.connections) == 2
    finally:
        drain.set()
        await asyncio.gather(owner, shutdown, return_exceptions=True)


def test_accepted_post_with_lost_response_is_not_replayed(native_wire):
    state = native_wire
    session = native_transport.create_session(timeout=5)
    payload = {"name": "one-native-mutation"}
    try:
        with pytest.raises(ConnectFailure):
            session.post(state.base + "/accepted-disconnect", json=payload, authenticated=False)
        assert session.get(state.base + "/echo", authenticated=False).status_code == 200
    finally:
        session.session.close()
    accepted = [row for row in state.requests if row["path"] == "/accepted-disconnect"]
    assert len(accepted) == 1
    assert accepted[0]["body"] == payload


@pytest.mark.parametrize("status", [401, 403, 503])
def test_native_denial_and_unavailability_remain_exact_http_errors(native_wire, status):
    state = native_wire
    with caller_client(state, "alice", "project-a", sdk=False) as (session, _read):
        with pytest.raises(HttpError) as caught:
            session.get(state.base + f"/status/{status}", allow_reauth=False)
    assert caught.value.http_status == status
    refusals = [row for row in state.requests if row["path"].startswith("/status/")]
    assert len(refusals) == 1
    assert refusals[0]["token"] == "issued-1-alice-project-a"
    assert refusals[0]["project"] == "project-a"
