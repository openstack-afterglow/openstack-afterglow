"""Real installed SDK wire calls against a deterministic loopback Keystone.

No real cloud identity, credentials or administrator policy are bypassed: the
API dependencies and Keystone are isolated test fixtures.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from fastapi import FastAPI
from keystoneauth1 import session
from keystoneauth1.identity import v3
from openstack.connection import Connection

from app.api.deps import get_os_conn, get_token_info
from app.api.identity.admin_credentials import router


@pytest.fixture
def native_identity():
    application = {
        "id": "app-1",
        "name": "automation",
        "description": "worker",
        "project_id": "project-1",
        "roles": [{"id": "reader-id", "name": "reader"}],
        "unrestricted": False,
        "secret": "issued-secret",
    }
    credential = {
        "id": "cred-1",
        "user_id": "user-1",
        "project_id": "project-1",
        "type": "ec2",
        "blob": '{"secret":"sensitive-blob"}',
    }
    state = {
        "calls": [],
        "status": 200,
        "application": application,
        "credential": credential,
        "issued_override": {},
        "token_roles": [{"id": "reader-id", "name": "reader"}],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, value, status=200):
            data = b"" if status == 204 else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if status == 201 and self.path == "/v3/auth/tokens":
                self.send_header("X-Subject-Token", "caller-token")
            self.end_headers()
            self.wfile.write(data)

        def handle_request(self):
            if self.path.rstrip("/") == "/v3":
                return self.respond(
                    {
                        "version": {
                            "id": "v3.14",
                            "status": "stable",
                            "links": [{"rel": "self", "href": endpoint + "/v3/"}],
                        }
                    }
                )
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = json.loads(raw_body) if raw_body else None
            if self.command == "POST" and self.path == "/v3/auth/tokens":
                return self.respond(
                    {
                        "token": {
                            "methods": ["token"],
                            "issued_at": "2026-01-01T00:00:00.000000Z",
                            "expires_at": "2099-01-01T00:00:00.000000Z",
                            "user": {"id": "user-1", "name": "caller", "domain": {"id": "default", "name": "Default"}},
                            "project": {
                                "id": "project-1",
                                "name": "home",
                                "domain": {"id": "default", "name": "Default"},
                            },
                            "roles": state["token_roles"],
                            "catalog": [],
                        }
                    },
                    201,
                )
            state["calls"].append((self.command, self.path, body, self.headers.get("X-Auth-Token")))
            if state["status"] != 200:
                return self.respond(
                    {"error": {"message": "secret-in-upstream-error", "code": state["status"]}}, state["status"]
                )
            if "application_credentials" in self.path:
                resource, singular, plural = state["application"], "application_credential", "application_credentials"
                collection = self.path.rstrip("/").endswith("application_credentials")
            elif "/credentials" in self.path:
                resource, singular, plural = state["credential"], "credential", "credentials"
                collection = self.path.split("?")[0].rstrip("/").endswith("credentials")
            else:
                return self.respond({"error": {"message": "Unexpected path"}}, 404)
            if (
                singular == "credential"
                and body
                and "project_id" in body[singular]
                and body[singular]["project_id"] is None
            ):
                return self.respond({"error": {"message": "project_id cannot be null"}}, 422)
            if self.command == "DELETE":
                return self.respond({}, 204)
            if self.command == "PATCH":
                resource.update(body[singular])
            if self.command == "POST":
                resource.update(body[singular])
                if singular == "credential" and "project_id" not in body[singular]:
                    resource["project_id"] = None
                if singular == "application_credential":
                    resource.update(state["issued_override"])
                return self.respond({singular: resource}, 201)
            return self.respond({plural: [resource]} if collection else {singular: resource})

        do_GET = handle_request
        do_POST = handle_request
        do_PATCH = handle_request
        do_DELETE = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    plugin = v3.Token(auth_url=endpoint + "/v3", token="bootstrap-token", project_id="project-1")
    native_session = session.Session(auth=plugin)
    conn = Connection(
        session=native_session, identity_endpoint_override=endpoint + "/v3", identity_api_version="3", connect_retries=0
    )
    token_info = {
        "user_id": "user-1",
        "project_id": "project-1",
        "connection_project_id": "project-1",
        "is_system_admin": True,
    }
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/admin")
    app.dependency_overrides[get_os_conn] = lambda: conn
    app.dependency_overrides[get_token_info] = lambda: token_info
    try:
        yield app, state, token_info
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["application-credentials", "application-credentials/app-1", "user-credentials", "user-credentials/cred-1"]
)
async def test_metadata_never_leaks_native_secrets(native_identity, path):
    app, state, _ = native_identity
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/" + path)
    assert response.status_code == 200
    assert "issued-secret" not in response.text and "sensitive-blob" not in response.text
    assert "no-store" in response.headers["cache-control"]
    assert state["calls"][-1][3] == "caller-token"


@pytest.mark.asyncio
async def test_sensitive_blob_requires_explicit_detail_request(native_identity):
    app, _, _ = native_identity
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/user-credentials/cred-1?sensitive=true")
    assert response.json()["blob"] == '{"secret":"sensitive-blob"}'
    assert "no-store" in response.headers["cache-control"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "native_status,expected,code",
    [
        (403, 403, "credential_native_denied"),
        (404, 404, "credential_not_found"),
        (422, 422, "credential_native_invalid"),
        (503, 503, "credential_unavailable"),
    ],
)
async def test_native_failures_are_distinct_and_safe(native_identity, native_status, expected, code):
    app, state, _ = native_identity
    state["status"] = native_status
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/application-credentials?user_id=other-user")
    assert response.status_code == expected
    assert response.json() == {"detail": code}
    assert "secret-in-upstream-error" not in response.text
    assert "no-store" in response.headers["cache-control"]
    assert "/users/other-user/application_credentials" in state["calls"][-1][1]


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign,roles", [(True, ["reader-id"]), (False, ["admin-id"])])
async def test_application_creation_cannot_escalate_or_use_logical_foreign_project(native_identity, foreign, roles):
    app, state, info = native_identity
    if foreign:
        info["project_id"] = "foreign-project"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/application-credentials", json={"name": "automation", "role_ids": roles}
        )
    assert response.status_code == 403
    assert state["calls"] == []


@pytest.mark.asyncio
async def test_application_issue_is_native_owner_scoped_restricted_and_once_only(native_identity):
    app, state, _ = native_identity
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        issued = await client.post(
            "/api/v1/admin/application-credentials", json={"name": "automation", "role_ids": ["reader-id"]}
        )
        detail = await client.get("/api/v1/admin/application-credentials/app-1")
        deletion = await client.delete("/api/v1/admin/application-credentials/app-1")
    assert issued.status_code == 201 and issued.json()["secret"] == "issued-secret"
    assert "secret" not in detail.json()
    method, path, body, token = state["calls"][0]
    assert method == "POST" and path == "/v3/users/user-1/application_credentials"
    assert body["application_credential"]["unrestricted"] is False
    assert body["application_credential"]["roles"] == [{"id": "reader-id"}]
    assert "project_id" not in body["application_credential"] and token == "caller-token"
    assert deletion.status_code == 204


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [
        {"project_id": "foreign-project"},
        {"roles": [{"id": "reader-id"}, {"id": "admin-id"}]},
        {"unrestricted": True},
    ],
)
async def test_unexpected_issued_scope_is_revoked_without_revealing_secret(native_identity, override):
    app, state, _ = native_identity
    state["issued_override"] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/application-credentials", json={"name": "automation", "role_ids": ["reader-id"]}
        )
    assert response.status_code == 403 and "issued-secret" not in response.text
    assert state["calls"][-1][:2] == ("DELETE", "/v3/users/user-1/application_credentials/app-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [
        {"roles": [{"id": "reader-id"}, {"id": "operator-id"}]},
        {"expires_at": None},
        {"expires_at": "2098-01-02T00:00:00Z"},
        {"expires_at": "invalid"},
    ],
)
async def test_issued_credential_cannot_exceed_selected_roles_or_expiry(native_identity, override):
    app, state, _ = native_identity
    state["token_roles"].append({"id": "operator-id", "name": "operator"})
    state["issued_override"] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/application-credentials",
            json={
                "name": "restricted-delegation",
                "role_ids": ["reader-id"],
                "expires_at": "2098-01-01T00:00:00Z",
            },
        )
    assert response.status_code == 403 and "issued-secret" not in response.text
    assert state["calls"][-1][:2] == ("DELETE", "/v3/users/user-1/application_credentials/app-1")


@pytest.mark.asyncio
async def test_user_create_update_delete_follow_native_blob_string_contract(native_identity):
    app, state, _ = native_identity
    body = {"user_id": "other-user", "project_id": "other-project", "type": "ec2", "blob": '{"secret":"new-sensitive"}'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/v1/admin/user-credentials", json=body)
        body["blob"] = '{"secret":"changed-sensitive"}'
        updated = await client.patch("/api/v1/admin/user-credentials/cred-1", json=body)
        deleted = await client.delete("/api/v1/admin/user-credentials/cred-1")
    assert created.status_code == 201 and updated.status_code == 200 and deleted.status_code == 204
    assert "blob" not in created.json() and "blob" not in updated.json()
    assert state["calls"][0][0] == "POST" and state["calls"][1][0] == "PATCH"
    assert isinstance(state["calls"][1][2]["credential"]["blob"], str)
    assert state["calls"][1][2]["credential"]["user_id"] == "other-user"


@pytest.mark.asyncio
async def test_sensitive_validation_does_not_echo_blob(native_identity):
    app, state, _ = native_identity
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/user-credentials",
            json={"user_id": "user-1", "type": "ec2", "blob": "invalid-sensitive-blob"},
        )
    assert response.status_code == 422
    assert response.json() == {"detail": "credential_invalid_input"}
    assert "no-store" in response.headers["cache-control"] and state["calls"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "application-credentials", None),
        ("GET", "application-credentials/context", None),
        ("GET", "application-credentials/app-1", None),
        ("POST", "application-credentials", {"name": "app", "role_ids": ["reader-id"]}),
        ("DELETE", "application-credentials/app-1", None),
        ("GET", "user-credentials", None),
        ("GET", "user-credentials/cred-1?sensitive=true", None),
        ("POST", "user-credentials", {"user_id": "u", "type": "cert", "blob": "{}"}),
        ("PATCH", "user-credentials/cred-1", {"user_id": "u", "type": "cert", "blob": "{}"}),
        ("DELETE", "user-credentials/cred-1", None),
    ],
)
async def test_every_operation_requires_admin(native_identity, method, path, body):
    app, state, info = native_identity
    info["is_system_admin"] = False
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(method, "/api/v1/admin/" + path, json=body)
    assert response.status_code == 403 and state["calls"] == []
    assert "no-store" in response.headers["cache-control"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "credential_type,blob",
    [("cert", "-----BEGIN CERTIFICATE-----\\nopaque PEM\\n-----END CERTIFICATE-----"), ("totp", "JBSWY3DPEHPK3PXP")],
)
async def test_raw_native_credentials_omit_absent_project_and_support_partial_patch(
    native_identity, credential_type, blob
):
    app, state, _ = native_identity
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/admin/user-credentials", json={"user_id": "user-1", "type": credential_type, "blob": blob}
        )
        updated = await client.patch("/api/v1/admin/user-credentials/cred-1", json={"blob": "changed-raw-blob"})
    assert created.status_code == 201 and created.json()["project_id"] is None
    assert updated.status_code == 200
    assert "blob" not in created.json() and "blob" not in updated.json()
    assert "project_id" not in state["calls"][0][2]["credential"]
    assert state["calls"][0][2]["credential"]["blob"] == blob
    assert state["calls"][1][2] == {"credential": {"blob": "changed-raw-blob"}}


@pytest.mark.asyncio
async def test_creation_context_uses_real_native_token_access_fields(native_identity):
    app, _, _ = native_identity
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/application-credentials/context")
    assert response.status_code == 200
    assert response.json() == {
        "user_id": "user-1",
        "project_id": "project-1",
        "roles": [{"id": "reader-id", "name": "reader"}],
    }
