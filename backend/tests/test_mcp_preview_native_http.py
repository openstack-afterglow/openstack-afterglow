"""MCP project preview uses validated catalogs without re-exchanging scoped tokens."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from keystoneauth1 import access

from app.config import get_settings
from app.services import keystone, project_service, service_proxy
from app.services.mcp_control_plane import authority, projects


@pytest.mark.asyncio
@pytest.mark.parametrize("waygate_status", [200, 403, 404, 503])
async def test_member_preview_and_mixed_manage_reuse_native_catalog_without_token_reexchange(
    monkeypatch, waygate_status
):
    calls = []
    roles = {"member-project": "member", "reader-project": "reader"}

    def token_body(project_id):
        return {
            "token": {
                "methods": ["token"],
                "issued_at": datetime.now(UTC).isoformat(),
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "user": {"id": "owner", "domain": {"id": "tenant"}},
                "project": {"id": project_id, "name": project_id, "domain": {"id": "tenant"}},
                "roles": [{"id": "role-" + roles[project_id], "name": roles[project_id]}],
                "catalog": [
                    {
                        "type": service,
                        "name": service,
                        "endpoints": [
                            {"interface": "internal", "region": "RegionOne", "url": base + "/" + service + "/v1"}
                        ],
                    }
                    for service in ("drover", "waygate")
                ],
            }
        }

    class Native(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, status, body, *, token=None):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if token:
                self.send_header("X-Subject-Token", token)
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            subject = body["auth"]["identity"]["token"]["id"]
            calls.append(("POST", self.path, subject))
            if self.path != "/v3/auth/tokens" or subject != "browser-token":
                self.reply(403, {"error": {"message": "restricted token cannot be re-exchanged"}})
                return
            target = body["auth"]["scope"]["project"]["id"]
            self.reply(201, token_body(target), token="restricted-" + target)

        def do_GET(self):
            path = urlsplit(self.path).path.rstrip("/")
            subject = self.headers.get("X-Auth-Token")
            calls.append(("GET", path, subject))
            if path == "/v3":
                self.reply(
                    200,
                    {
                        "version": {
                            "id": "v3.14",
                            "status": "stable",
                            "links": [{"rel": "self", "href": base + "/v3/"}],
                        }
                    },
                )
            elif path == "/v3/auth/projects" and subject == "browser-token":
                self.reply(
                    200,
                    {
                        "projects": [
                            {"id": project_id, "name": project_id, "domain_id": "tenant", "enabled": True}
                            for project_id in roles
                        ]
                    },
                )
            elif path in {"/drover/v1/policy/capabilities", "/waygate/v1/policy/capabilities"}:
                target = self.headers.get("x-project-id")
                if target not in roles or subject != "restricted-" + target:
                    self.reply(403, {})
                    return
                service = path.split("/")[1]
                if service == "waygate" and waygate_status != 200:
                    self.reply(waygate_status, {})
                    return
                leaves = [service + "-inventory_reader"]
                if service == "drover" and roles[target] == "member":
                    leaves.append("drover-clusters_editor")
                self.reply(200, {"service": service, "capabilities": leaves, "actions": []})
            else:
                self.reply(404, {})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Native)
    base = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = get_settings().model_copy(
        update={
            "os_auth_url": base + "/v3",
            "os_region_name": "RegionOne",
            "os_interface": "internal",
            "service_drover_internal_url": "",
            "service_waygate_internal_url": "",
            "service_k3s_enabled": True,
            "service_waygate_enabled": True,
            "service_palimpsest_enabled": False,
            "service_chat_enabled": True,
        }
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr(keystone, "get_settings", lambda: settings)
    monkeypatch.setattr(service_proxy, "get_settings", lambda: settings)

    async def current_roles(project_id, user_id):
        assert user_id == "owner"
        return [{"id": "role-" + roles[project_id], "name": roles[project_id], "inherited_role_ids": []}]

    monkeypatch.setattr(project_service, "get_project_delegation_roles", current_roles)
    native = access.create(body=token_body("member-project"), auth_token="browser-token")
    conn = keystone.get_openstack_connection("browser-token", "member-project", native_access=native)
    conn._afterglow_user_id = "owner"
    conn._afterglow_token = "browser-token"
    conn._afterglow_domain_id = "tenant"
    conn._afterglow_identity_domain_id = "tenant"
    try:
        preview = await projects.project_permission_preview(conn, "owner")
        by_id = {row["id"]: row for row in preview}
        assert by_id["member-project"]["can_write"] is True
        assert by_id["reader-project"]["can_write"] is False
        assert by_id["member-project"]["service_permissions"]["drover"] == [
            "drover-clusters_editor",
            "drover-inventory_reader",
        ]
        assert by_id["reader-project"]["service_permissions"]["drover"] == ["drover-inventory_reader"]
        for row in preview:
            assert "lumen" not in row["service_permissions"] and "lumen" not in row["service_errors"]
            if waygate_status == 200:
                assert row["service_permissions"]["waygate"] == ["waygate-inventory_reader"]
                assert "waygate" not in row["service_errors"]
            else:
                assert row["service_permissions"]["waygate"] == []
                assert row["service_errors"]["waygate"] == "permission_check_unavailable"
        # Only initial target rescopes may exchange the browser token. Native
        # capability calls must reuse each validated restricted-token catalog.
        assert all(subject == "browser-token" for method, _, subject in calls if method == "POST")
        metadata = await projects.resolve_project_scope(
            conn, "owner", "member-project", ["reader"], project_scope="all", access_level="manage"
        )
        grant = SimpleNamespace(approved_projects=metadata, owner_project_id="member-project", access_level="manage")
        authority.validate_grant_project(grant, "member-project", write=True)
        with pytest.raises(authority.McpGrantStateError, match="management"):
            authority.validate_grant_project(grant, "reader-project", write=True)
        grant.access_level = "read"
        with pytest.raises(authority.McpGrantStateError, match="management"):
            authority.validate_grant_project(grant, "member-project", write=True)
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
