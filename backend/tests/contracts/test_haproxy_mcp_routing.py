"""Exercise canonical proxy rules with real HAProxy and local identity upstreams.

Set HAPROXY_BIN to require a specific binary; otherwise skip if not installed.
Only listener/upstream addresses and Compose TLS termination are fixture-owned.
Routing rules are read verbatim from the deployment manifests.
"""

import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[3]


@contextmanager
def _upstream(identity):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()
            payload = json.dumps(
                {
                    "service": identity,
                    "path": self.path,
                    "method": self.command,
                    "host": self.headers.get("Host"),
                    "proto": self.headers.get("X-Forwarded-Proto"),
                    "body": body,
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _unused_port(exclude=()):
    while True:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        if port not in exclude:
            return port


def _configuration(kind, port, backend_port, frontend_port):
    defaults = "defaults\n    mode http\n    timeout connect 2s\n    timeout client 5s\n    timeout server 5s\n"
    if kind == "compose":
        source = (ROOT / "haproxy/haproxy.cfg").read_text()
        # Keep the full canonical frontend, replacing only its TLS listener.
        frontend = source.split("frontend https_front\n", 1)[1].split("frontend waygate_catalog_https\n", 1)[0]
        frontend = re.sub(r"    bind .*", f"    bind 127.0.0.1:{port}", frontend, count=1)
        routing = "frontend https_front\n" + frontend
        backend_name, frontend_name = "afterglow_backend", "afterglow_frontend"
    else:
        source = (ROOT / "deploy/kolla/ansible/roles/afterglow/templates/afterglow-public.cfg.j2").read_text()
        routing = (
            Environment(undefined=StrictUndefined)
            .from_string(source)
            .render(
                afterglow_public_haproxy_fqdn="cloud.dmslab.re.kr",
                afterglow_public_haproxy_router_port=_unused_port(exclude=(port,)),
            )
        )
        # Exercise the real two-hop public backend + loopback router topology.
        routing += f"\nfrontend external\n    bind 127.0.0.1:{port}\n    default_backend afterglow-public_back\n"
        backend_name, frontend_name = "afterglow-api_back", "afterglow-frontend_back"
    return (
        defaults
        + routing
        + f"\nbackend {backend_name}\n    server backend 127.0.0.1:{backend_port}\n"
        + f"\nbackend {frontend_name}\n    server frontend 127.0.0.1:{frontend_port}\n"
    )


@pytest.fixture(scope="module", params=["compose", "kolla"])
def proxy(request, tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp(f"haproxy-{request.param}")
    requested = os.environ.get("HAPROXY_BIN")
    binary = shutil.which(requested or "haproxy")
    if binary is None:
        if requested:
            pytest.fail(f"HAPROXY_BIN is unavailable: {requested}")
        pytest.skip("Install HAProxy or set HAPROXY_BIN to exercise real routing")
    with _upstream("backend") as backend_port, _upstream("frontend") as frontend_port:
        port = _unused_port()
        config = tmp_path / "haproxy.cfg"
        config.write_text(_configuration(request.param, port, backend_port, frontend_port))
        parsed = subprocess.run([binary, "-c", "-f", str(config)], capture_output=True, text=True)
        assert parsed.returncode == 0, parsed.stdout + parsed.stderr
        with (tmp_path / "haproxy.log").open("w+") as log:
            process = subprocess.Popen([binary, "-db", "-f", str(config)], stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 5
                while True:
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                            break
                    except OSError:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            log.seek(0)
                            pytest.fail(f"HAProxy did not become ready: {log.read()}")
                        time.sleep(0.02)
                yield port
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


@pytest.mark.parametrize(
    ("path", "service"),
    [
        ("/mcp", "backend"),
        ("/mcp/", "backend"),
        ("/mcp?session=123", "backend"),
        ("/mcp/oauth/register", "backend"),
        ("/mcp/oauth/authorize", "backend"),
        ("/mcp/oauth/token", "backend"),
        ("/mcp/oauth/revoke", "backend"),
        ("/.well-known/oauth-protected-resource/mcp", "backend"),
        ("/.well-known/oauth-authorization-server/mcp/oauth", "backend"),
        ("/.well-known/oauth-protected-resource/api/v1/mcp", "backend"),
        ("/api/v1/mcp", "backend"),
        ("/mcpevil", "frontend"),
        ("/mcpevil/oauth/token", "frontend"),
        ("/mcp-other", "frontend"),
        ("/.well-known-evil/oauth-protected-resource/mcp", "frontend"),
        ("/oauth/mcp/authorize", "frontend"),
        ("/oauth/token", "frontend"),
        ("/account", "frontend"),
        ("/", "frontend"),
    ],
)
def test_mcp_requests_preserve_target_method_body_and_frontend_boundaries(proxy, path, service):
    connection = http.client.HTTPConnection("127.0.0.1", proxy, timeout=5)
    try:
        connection.request(
            "POST",
            path,
            body="routing-probe",
            headers={"Host": "cloud.dmslab.re.kr", "X-Forwarded-Proto": "https"},
        )
        response = connection.getresponse()
        assert response.status == 200  # A rewrite/redirect cannot pass as routing proof.
        assert response.getheader("Location") is None
        assert json.loads(response.read()) == {
            "service": service,
            "path": path,
            "method": "POST",
            "host": "cloud.dmslab.re.kr",
            "proto": "https",
            "body": "routing-probe",
        }
    finally:
        connection.close()
