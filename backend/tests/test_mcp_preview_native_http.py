"""MCP project preview uses validated catalogs without re-exchanging scoped tokens."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import Request
from keystoneauth1 import access
from keystoneauth1.exceptions.http import Forbidden

from app.api.deps import get_os_conn
from app.api.identity import mcp_access
from app.config import get_settings
from app.services import keystone, service_proxy
from app.services.mcp_control_plane import authority, projects


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("waygate_status", "root_case"),
    [
        (200, "valid"),
        (403, "valid"),
        (404, "valid"),
        (503, "valid"),
        (200, "absent"),
        (200, "wrong_owner"),
        (200, "wrong_domain"),
        (200, "stale_roles"),
        (200, "denied"),
    ],
)
@pytest.mark.parametrize("member_role", ["member", "manager"])
async def test_member_preview_and_mixed_manage_reuse_native_catalog_without_token_reexchange(
    monkeypatch, waygate_status, member_role, root_case
):
    calls = []
    roles = {"member-project": member_role, "reader-project": "reader"}

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
            if "password" in body["auth"]["identity"]["methods"]:
                assert body["auth"]["identity"]["password"]["user"]["name"] == "preview-operator"
                assert body["auth"]["scope"]["project"]["name"] == "preview-operator-project"
                calls.append(("PASSWORD", self.path, "operator"))
                operator = token_body("member-project")
                operator["token"]["user"]["id"] = "preview-operator"
                operator["token"]["project"]["id"] = "preview-operator-project"
                operator["token"]["catalog"].append(
                    {
                        "type": "identity",
                        "name": "keystone",
                        "endpoints": [{"interface": "internal", "region": "RegionOne", "url": base + "/v3"}],
                    }
                )
                self.reply(201, operator, token="operator-token")
                return
            subject = body["auth"]["identity"]["token"]["id"]
            calls.append(("POST", self.path, subject))
            target = body["auth"]["scope"]["project"]["id"]
            # Model Keystone allow_rescope_scoped_token=false: no scoped
            # subject may mint ANY target token, including its own project.
            if self.path != "/v3/auth/tokens" or subject != "login-root":
                self.reply(403, {"error": {"message": "rescope a scoped token"}})
                return
            if root_case == "denied":
                self.reply(403, {"error": {"message": "target scope denied"}})
                return
            target_body = token_body(target)
            if root_case == "wrong_owner":
                target_body["token"]["user"]["id"] = "foreign-owner"
            if root_case == "wrong_domain":
                target_body["token"]["project"]["domain"]["id"] = "foreign-domain"
            self.reply(201, target_body, token="restricted-" + target)

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
            elif path == "/v3/roles" and subject == "operator-token":
                self.reply(
                    200,
                    {"roles": [{"id": "role-" + role, "name": role} for role in sorted(set(roles.values()))]},
                )
            elif path == "/v3/role_inferences" and subject == "operator-token":
                self.reply(200, {"role_inferences": []})
            elif path == "/v3/role_assignments" and subject == "operator-token":
                query = parse_qs(urlsplit(self.path).query)
                target = query.get("scope.project.id", [None])[0]
                assert query.get("user.id") == ["owner"] and query.get("effective") == ["True"]
                assert target in roles
                self.reply(
                    200,
                    {
                        "role_assignments": (
                            [
                                {
                                    "user": {"id": "owner"},
                                    "role": {"id": "role-" + roles[target]},
                                    "scope": {"project": {"id": target}},
                                }
                            ]
                            if root_case != "stale_roles" or target == "member-project"
                            else []
                        )
                    },
                )
            elif path in {"/drover/v1/policy/capabilities", "/waygate/v1/policy/capabilities"}:
                target = self.headers.get("x-project-id")
                expected_subject = "browser-token" if target == "member-project" else "restricted-" + str(target)
                if target not in roles or subject != expected_subject:
                    self.reply(403, {})
                    return
                service = path.split("/")[1]
                if service == "waygate" and waygate_status != 200:
                    self.reply(waygate_status, {})
                    return
                leaves = [service + "-inventory_reader"]
                if service == "drover" and roles[target] in {"member", "manager"}:
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
            "service_mcp_enabled": True,
            "os_username": "preview-operator",
            "os_password": "preview-operator-password",
            "os_project_name": "preview-operator-project",
            "os_user_domain_name": "tenant",
            "os_project_domain_name": "tenant",
        }
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr(keystone, "get_settings", lambda: settings)
    monkeypatch.setattr(service_proxy, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_access, "get_settings", lambda: settings)

    native = access.create(body=token_body("member-project"), auth_token="browser-token")
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/auth/mcp-projects", "headers": []})
    request.state._afterglow_native_access = native
    token_info = {
        "token": "browser-token",
        "user_id": "owner",
        "project_id": "member-project",
        "connection_project_id": "member-project",
        "domain_id": "tenant",
        "domain_name": "Tenant",
        "identity_domain_id": "tenant",
        "roles": [member_role],
        "is_system_admin": False,
    }
    if root_case != "absent":
        token_info["session_token"] = "login-root"
    connection = get_os_conn(request, token_info=token_info)
    conn = await anext(connection)
    assert conn._afterglow_session_token == token_info.get("session_token")
    try:
        response = await mcp_access.get_mcp_projects(request, preview=True, token_info=token_info, conn=conn)
        assert response.headers["cache-control"] == "no-store"
        assert b"login-root" not in response.body and b"browser-token" not in response.body
        preview = json.loads(response.body)
        by_id = {row["id"]: row for row in preview}
        assert by_id["member-project"]["can_write"] is True
        assert by_id["member-project"]["scope_error"] is None
        secondary = by_id["reader-project"]
        if root_case == "valid":
            assert secondary["can_write"] is False
            assert secondary["scope_error"] is None
            assert secondary["service_permissions"]["drover"] == ["drover-inventory_reader"]
        else:
            assert secondary["can_write"] is None
            assert secondary["scope_error"] == "scope_validation_unavailable"
            assert not any(secondary["service_permissions"].values())
        assert by_id["member-project"]["service_permissions"]["drover"] == [
            "drover-clusters_editor",
            "drover-inventory_reader",
        ]
        valid_rows = [row for row in preview if row["scope_error"] is None]
        for row in valid_rows:
            assert "lumen" not in row["service_permissions"] and "lumen" not in row["service_errors"]
            if waygate_status == 200:
                assert row["service_permissions"]["waygate"] == ["waygate-inventory_reader"]
                assert "waygate" not in row["service_errors"]
            else:
                assert row["service_permissions"]["waygate"] == []
                assert row["service_errors"]["waygate"] == "permission_check_unavailable"
        # Current scope uses its validated catalog without issuing another
        # token. Only the proven unscoped browser login derives other scopes.
        rescope_subject = "browser-token" if root_case == "absent" else "login-root"
        assert [(method, path, subject) for method, path, subject in calls if method == "POST"] == [
            ("POST", "/v3/auth/tokens", rescope_subject)
        ]
        assignment_reads = [path for method, path, subject in calls if method == "GET" and subject == "operator-token"]
        expected_assignment_reads = 2 if root_case in {"valid", "stale_roles"} else 1
        assert assignment_reads.count("/v3/role_assignments") == expected_assignment_reads
        if root_case != "valid":
            expected_error = Forbidden if root_case in {"absent", "denied"} else authority.McpAuthorityError
            with pytest.raises(expected_error):
                await projects.resolve_project_scope(
                    conn, "owner", "member-project", ["member"], project_scope="all", access_level="manage"
                )
            assert not any(method == "GET" and subject == "restricted-reader-project" for method, _, subject in calls)
            return
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
        await connection.aclose()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
