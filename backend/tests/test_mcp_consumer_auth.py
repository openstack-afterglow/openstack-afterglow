"""Authenticate consumer credentials through the installed SDK and real HTTP."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from app.services.mcp_control_plane import connection as consumer


@contextmanager
def application_credential_keystone(*, user_id="user-a", project_id="project-a"):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            auth = body.get("auth", {})
            identity = auth.get("identity", {})
            credential = identity.get("application_credential", {})
            if self.path != "/v3/auth/tokens":
                status, payload = 404, {"error": {"message": "Unknown endpoint"}}
            elif "scope" in auth:
                status, payload = 400, {"error": {"message": "Application credentials cannot request scope"}}
            elif identity.get("methods") != ["application_credential"] or credential != {
                "id": "credential-a",
                "secret": "synthetic-credential-secret",
            }:
                status, payload = 401, {"error": {"message": "Unauthorized"}}
            else:
                token = {
                    "methods": ["application_credential"],
                    "user": {"id": user_id, "name": "fixture", "domain": {"id": "default", "name": "Default"}},
                    "roles": [{"id": "reader", "name": "reader"}],
                    "catalog": [],
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    "issued_at": datetime.now(UTC).isoformat(),
                }
                if project_id is not None:
                    token["project"] = {
                        "id": project_id,
                        "name": "fixture-project",
                        "domain": {"id": "default", "name": "Default"},
                    }
                status, payload = 201, {"token": token}
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            if status == 201:
                self.send_header("X-Subject-Token", "synthetic-cloud-token")
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v3"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    ("returned_user", "returned_project", "allowed"),
    [
        ("user-a", "project-a", True),
        ("other-user", "project-a", False),
        ("user-a", "other-project", False),
        ("user-a", None, False),
    ],
    ids=["owned-project", "foreign-owner", "foreign-project", "unscoped"],
)
def test_consumer_credential_authenticates_only_its_original_owner_and_project(
    monkeypatch, returned_user, returned_project, allowed
):
    with application_credential_keystone(user_id=returned_user, project_id=returned_project) as auth_url:
        monkeypatch.setattr(
            consumer,
            "get_settings",
            lambda: SimpleNamespace(
                os_auth_url=auth_url, os_region_name="RegionOne", os_interface="public", ssl_verify=True
            ),
        )
        principal = SimpleNamespace(user_id="user-a", project_id="project-a")
        if not allowed:
            with pytest.raises(consumer.McpConsumerConnectionError, match="owner/project"):
                consumer._build_connection("credential-a", "synthetic-credential-secret", principal)
            return
        connection = consumer._build_connection("credential-a", "synthetic-credential-secret", principal)
        try:
            assert connection.authorize() == "synthetic-cloud-token"
            assert connection.current_project_id == "project-a"
            assert connection.session.get_user_id() == "user-a"
        finally:
            connection.close()
