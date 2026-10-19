"""Real installed SDK wire calls against a deterministic loopback Keystone.

No real cloud identity, credentials or administrator policy are bypassed: the
API dependencies and Keystone are isolated test fixtures.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi import FastAPI
from keystoneauth1 import session
from keystoneauth1.identity import v3
from openstack.connection import Connection

from app.api.deps import get_os_conn, get_token_info, require_admin
from app.api.identity.admin_credentials import router
from tests.admin_gate import synthetic_verified_admin


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
        "delete_status": 204,
        "application": application,
        "credential": credential,
        "issued_override": {},
        "token_roles": [{"id": "reader-id", "name": "reader"}],
        "lookups": [],
        "lookup_status": {},
        "directory_overrides": {},
        "committed": False,
        "lookup_status_after_write": None,
        "user_issued_override": {},
        "user_updated_override": {},
        "domains": {
            "default": {"id": "default", "name": "Default", "enabled": True},
            "tenant-2": {"id": "tenant-2", "name": "Tenant", "enabled": True},
        },
        "users": {
            "user-1": {"id": "user-1", "domain_id": "default"},
            "other-user": {"id": "other-user", "domain_id": "default"},
            "foreign-user": {"id": "foreign-user", "domain_id": "tenant-2"},
            "unknown-user": {"id": "unknown-user"},
        },
        "projects": {
            "project-1": {"id": "project-1", "domain_id": "default"},
            "other-project": {"id": "other-project", "domain_id": "default"},
            "foreign-project": {"id": "foreign-project", "domain_id": "tenant-2"},
            "unknown-project": {"id": "unknown-project"},
        },
        "extra_applications": [],
        "extra_credentials": [],
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
            route, _, query = self.path.partition("?")
            if self.command == "GET" and route in ("/v3/users", "/v3/projects"):
                collection_name = route.rsplit("/", 1)[-1]
                state["lookups"].append((self.command, self.path))
                status = state["lookup_status"].get((collection_name, "*"), 200)
                if status != 200:
                    return self.respond({"error": {"message": "lookup-secret", "code": status}}, status)
                selected_domain = parse_qs(query)["domain_id"][0]
                rows = state["directory_overrides"].get(collection_name)
                if rows is None:
                    rows = [row for row in state[collection_name].values() if row.get("domain_id") == selected_domain]
                return self.respond({collection_name: rows, "links": {}})
            for collection_name, singular_name in (("domains", "domain"), ("users", "user"), ("projects", "project")):
                prefix = "/v3/" + collection_name + "/"
                if self.path.startswith(prefix) and "/" not in self.path[len(prefix) :]:
                    resource_id = self.path[len(prefix) :]
                    state["lookups"].append((self.command, self.path))
                    status = state["lookup_status"].get((collection_name, resource_id), 200)
                    if state["committed"] and state["lookup_status_after_write"] is not None:
                        status = state["lookup_status_after_write"]
                    if status != 200:
                        return self.respond({"error": {"message": "lookup-secret", "code": status}}, status)
                    resource = state[collection_name].get(resource_id)
                    if resource is None:
                        return self.respond({"error": {"message": "Missing identity"}}, 404)
                    return self.respond({singular_name: resource})
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
                if state["delete_status"] != 204:
                    status = state["delete_status"]
                    return self.respond({"error": {"message": "rollback-secret", "code": status}}, status)
                return self.respond({}, 204)
            if self.command == "PATCH":
                resource.update(body[singular])
                resource.update(state["user_updated_override"])
                state["committed"] = True
            if self.command == "POST":
                resource.update(body[singular])
                if singular == "credential" and "project_id" not in body[singular]:
                    resource["project_id"] = None
                if singular == "application_credential":
                    resource.update(state["issued_override"])
                else:
                    resource.update(state["user_issued_override"])
                state["committed"] = True
                return self.respond({singular: resource}, 201)
            if collection:
                extras = (
                    state["extra_applications"] if singular == "application_credential" else state["extra_credentials"]
                )
                return self.respond({plural: [resource, *extras]})
            return self.respond({singular: resource})

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
        "domain_id": "default",
        "domain_name": "Default",
        "identity_domain_id": "default",
        "project_id": "project-1",
        "connection_project_id": "project-1",
        "is_system_admin": True,
    }
    # Match the production dependency's working/home domain metadata without
    # replacing the real SDK session or the caller's native auth access.
    conn._afterglow_user_id = token_info["user_id"]
    conn._afterglow_domain_id = token_info["domain_id"]
    conn._afterglow_domain_name = token_info["domain_name"]
    conn._afterglow_identity_domain_id = token_info["identity_domain_id"]
    conn._afterglow_project_id = token_info["project_id"]
    conn._afterglow_authenticated_project_id = token_info["connection_project_id"]
    conn._afterglow_is_system_admin = token_info["is_system_admin"]
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/admin")
    app.dependency_overrides[get_os_conn] = lambda: conn
    app.dependency_overrides[get_token_info] = lambda: token_info
    app.dependency_overrides[require_admin] = synthetic_verified_admin
    try:
        yield app, state, token_info
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join()


class SelectedDomainClient(httpx.AsyncClient):
    def build_request(self, method, url, **kwargs):
        selected = httpx.URL(url).copy_merge_params({"domain_id": "default"})
        return super().build_request(method, selected, **kwargs)


def scoped_client(app):
    return SelectedDomainClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["application-credentials", "application-credentials/app-1", "user-credentials", "user-credentials/cred-1"]
)
async def test_metadata_never_leaks_native_secrets(native_identity, path):
    app, state, _ = native_identity
    async with scoped_client(app) as client:
        response = await client.get("/api/v1/admin/" + path)
    assert response.status_code == 200
    assert "issued-secret" not in response.text and "sensitive-blob" not in response.text
    assert "no-store" in response.headers["cache-control"]
    assert state["calls"][-1][3] == "caller-token"


@pytest.mark.asyncio
async def test_sensitive_blob_requires_explicit_detail_request(native_identity):
    app, _, _ = native_identity
    async with scoped_client(app) as client:
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
    async with scoped_client(app) as client:
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
    async with scoped_client(app) as client:
        response = await client.post(
            "/api/v1/admin/application-credentials", json={"name": "automation", "role_ids": roles}
        )
    assert response.status_code == 403
    assert state["calls"] == []


@pytest.mark.asyncio
async def test_application_issue_is_native_owner_scoped_restricted_and_once_only(native_identity):
    app, state, _ = native_identity
    async with scoped_client(app) as client:
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
        {"unrestricted": None},
        {"roles": []},
        {"secret": ""},
        {"secret": None},
    ],
)
async def test_unexpected_issued_scope_is_revoked_without_revealing_secret(native_identity, override):
    app, state, _ = native_identity
    state["issued_override"] = override
    async with scoped_client(app) as client:
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
    async with scoped_client(app) as client:
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
    async with scoped_client(app) as client:
        created = await client.post("/api/v1/admin/user-credentials", json=body)
        body["blob"] = '{"secret":"changed-sensitive"}'
        updated = await client.patch("/api/v1/admin/user-credentials/cred-1", json=body)
        deleted = await client.delete("/api/v1/admin/user-credentials/cred-1")
    assert created.status_code == 201 and updated.status_code == 200 and deleted.status_code == 204
    assert "blob" not in created.json() and "blob" not in updated.json()
    mutations = [call for call in state["calls"] if call[0] in ("POST", "PATCH")]
    assert [call[0] for call in mutations] == ["POST", "PATCH"]
    assert isinstance(mutations[1][2]["credential"]["blob"], str)
    assert mutations[1][2]["credential"]["user_id"] == "other-user"


@pytest.mark.asyncio
async def test_sensitive_validation_does_not_echo_blob(native_identity):
    app, state, _ = native_identity
    async with scoped_client(app) as client:
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
    async with scoped_client(app) as client:
        response = await client.request(method, "/api/v1/admin/" + path, json=body)
    assert response.status_code == 403 and state["calls"] == [] and state["lookups"] == []
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
    async with scoped_client(app) as client:
        created = await client.post(
            "/api/v1/admin/user-credentials", json={"user_id": "user-1", "type": credential_type, "blob": blob}
        )
        updated = await client.patch("/api/v1/admin/user-credentials/cred-1", json={"blob": "changed-raw-blob"})
    assert created.status_code == 201 and created.json()["project_id"] is None
    assert updated.status_code == 200
    assert "blob" not in created.json() and "blob" not in updated.json()
    assert "project_id" not in state["calls"][0][2]["credential"]
    assert state["calls"][0][2]["credential"]["blob"] == blob
    patch = next(call for call in state["calls"] if call[0] == "PATCH")
    assert patch[2] == {"credential": {"blob": "changed-raw-blob"}}


@pytest.mark.asyncio
async def test_creation_context_uses_real_native_token_access_fields(native_identity):
    app, _, _ = native_identity
    async with scoped_client(app) as client:
        response = await client.get("/api/v1/admin/application-credentials/context")
    assert response.status_code == 200
    assert response.json() == {
        "domain_id": "default",
        "user_id": "user-1",
        "project_id": "project-1",
        "roles": [{"id": "reader-id", "name": "reader"}],
    }


@pytest.mark.asyncio
async def test_lists_exclude_foreign_and_unproven_owners_before_publication(native_identity):
    app, state, _ = native_identity
    base = state["application"]
    state["extra_applications"] = [
        {**base, "id": "app-foreign", "project_id": "foreign-project"},
        {**base, "id": "app-unknown", "project_id": "unknown-project"},
        {**base, "id": "app-same", "project_id": "other-project"},
        {**base, "id": "app-missing-project", "project_id": None},
        {**base, "id": "app-missing-owner", "project_id": "deleted-project"},
    ]
    credential = state["credential"]
    state["extra_credentials"] = [
        {**credential, "id": "cred-foreign-user", "user_id": "foreign-user"},
        {**credential, "id": "cred-foreign-project", "user_id": "other-user", "project_id": "foreign-project"},
        {**credential, "id": "cred-unknown", "user_id": "unknown-user"},
        {**credential, "id": "cred-unknown-project", "project_id": "unknown-project"},
        {**credential, "id": "cred-missing-owner", "user_id": None},
        {**credential, "id": "cred-deleted-owner", "user_id": "deleted-user"},
        {**credential, "id": "cred-same", "user_id": "other-user", "project_id": None},
    ]
    async with scoped_client(app) as client:
        applications = await client.get("/api/v1/admin/application-credentials")
        credentials = await client.get("/api/v1/admin/user-credentials")
    assert [item["id"] for item in applications.json()["items"]] == ["app-1", "app-same"]
    assert [item["id"] for item in credentials.json()["items"]] == ["cred-1", "cred-same"]
    assert all(item["domain_id"] == "default" for item in applications.json()["items"])
    assert all(item["domain_id"] == "default" for item in credentials.json()["items"])
    assert "sensitive-blob" not in credentials.text and "issued-secret" not in applications.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/admin/application-credentials?user_id=foreign-user"),
        ("DELETE", "/api/v1/admin/application-credentials/app-1?user_id=foreign-user"),
        ("GET", "/api/v1/admin/user-credentials?user_id=foreign-user"),
    ],
)
async def test_foreign_owner_selection_is_denied_before_native_credential_call(native_identity, method, path):
    app, state, _ = native_identity
    async with scoped_client(app) as client:
        response = await client.request(method, path)
    assert response.status_code == 403
    assert response.json() == {"detail": "credential_scope_denied"}
    assert state["calls"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
async def test_foreign_user_credential_object_cannot_be_read_or_mutated(native_identity, method):
    app, state, _ = native_identity
    state["credential"]["user_id"] = "foreign-user"
    kwargs = {"json": {"blob": "changed"}} if method == "PATCH" else {}
    async with scoped_client(app) as client:
        response = await client.request(method, "/api/v1/admin/user-credentials/cred-1", **kwargs)
    assert response.status_code == 403
    assert [call[0] for call in state["calls"]] == ["GET"]
    assert "sensitive-blob" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"user_id": "foreign-user", "project_id": "project-1", "type": "ec2", "blob": '{"secret":"x"}'},
        {"user_id": "user-1", "project_id": "foreign-project", "type": "ec2", "blob": '{"secret":"x"}'},
        {"user_id": "unknown-user", "type": "cert", "blob": "raw"},
        {"user_id": "user-1", "project_id": "unknown-project", "type": "ec2", "blob": "{}"},
    ],
)
async def test_foreign_owner_cannot_receive_created_user_credential(native_identity, body):
    app, state, _ = native_identity
    async with scoped_client(app) as client:
        response = await client.post("/api/v1/admin/user-credentials", json=body)
    assert response.status_code == 403
    assert state["calls"] == []


@pytest.mark.asyncio
async def test_caller_outside_selected_domain_cannot_issue_application_credential(native_identity):
    app, state, _ = native_identity
    async with SelectedForeignDomainClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/application-credentials", json={"name": "x", "role_ids": ["reader-id"]}
        )
    assert response.status_code == 403
    assert not any(call[0] == "POST" and "application_credentials" in call[1] for call in state["calls"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected",
    [(403, "credential_native_denied"), (404, "credential_not_found"), (503, "credential_unavailable")],
)
async def test_selected_domain_lookup_preserves_native_failure(native_identity, status, expected):
    app, state, _ = native_identity
    state["lookup_status"][("domains", "default")] = status
    async with scoped_client(app) as client:
        response = await client.get("/api/v1/admin/user-credentials")
    assert response.json() == {"detail": expected}
    assert response.status_code == status
    assert "lookup-secret" not in response.text
    assert state["calls"] == []


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
        ("POST", "user-credentials", {"user_id": "user-1", "type": "cert", "blob": "raw"}),
        ("PATCH", "user-credentials/cred-1", {"blob": "raw"}),
        ("DELETE", "user-credentials/cred-1", None),
    ],
)
@pytest.mark.parametrize("domain", [None, ""])
async def test_domain_selection_is_required(native_identity, method, path, body, domain):
    app, state, _ = native_identity
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        separator = "&" if "?" in path else "?"
        query = "" if domain is None else separator + "domain_id=" + domain
        response = await client.request(method, "/api/v1/admin/" + path + query, json=body)
    assert response.status_code == 422
    assert state["calls"] == []
    assert state["lookups"] == []
    assert response.json() == {"detail": "credential_invalid_input"}
    assert "no-store" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_empty_owner_selector_does_not_fall_back_to_caller(native_identity):
    app, state, _ = native_identity
    async with scoped_client(app) as client:
        response = await client.get("/api/v1/admin/application-credentials?user_id=")
    assert response.status_code == 422
    assert response.json() == {"detail": "credential_invalid_input"}
    assert state["calls"] == []
    assert state["lookups"] == []


class SelectedForeignDomainClient(httpx.AsyncClient):
    def build_request(self, method, url, **kwargs):
        return super().build_request(method, httpx.URL(url).copy_merge_params({"domain_id": "tenant-2"}), **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "DELETE"])
@pytest.mark.parametrize("project_id", ["foreign-project", "unknown-project", None])
async def test_application_exact_object_requires_proven_domain_project(native_identity, method, project_id):
    app, state, _ = native_identity
    state["application"]["project_id"] = project_id
    async with scoped_client(app) as client:
        response = await client.request(method, "/api/v1/admin/application-credentials/app-1")
    assert response.status_code == 403
    assert response.json() == {"detail": "credential_scope_denied"}
    assert [call[0] for call in state["calls"]] == ["GET"]
    assert "issued-secret" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "field,owner",
    [
        ("project_id", "foreign-project"),
        ("project_id", "unknown-project"),
        ("user_id", "unknown-user"),
        ("user_id", None),
    ],
)
async def test_user_exact_object_requires_proven_domain_owners(native_identity, method, field, owner):
    app, state, _ = native_identity
    state["credential"][field] = owner
    kwargs = {"json": {"user_id": "user-1", "project_id": "project-1", "blob": "changed"}} if method == "PATCH" else {}
    async with scoped_client(app) as client:
        response = await client.request(method, "/api/v1/admin/user-credentials/cred-1?sensitive=true", **kwargs)
    assert response.status_code == 403
    assert response.json() == {"detail": "credential_scope_denied"}
    assert [call[0] for call in state["calls"]] == ["GET"]
    assert "sensitive-blob" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attrs",
    [
        {"user_id": "foreign-user"},
        {"project_id": "foreign-project"},
        {"user_id": "unknown-user"},
        {"project_id": "unknown-project"},
    ],
)
async def test_user_update_cannot_reassign_into_foreign_or_unknown_domain(native_identity, attrs):
    app, state, _ = native_identity
    async with scoped_client(app) as client:
        response = await client.patch("/api/v1/admin/user-credentials/cred-1", json=attrs)
    assert response.status_code == 403
    assert response.json() == {"detail": "credential_scope_denied"}
    assert [call[0] for call in state["calls"]] == ["GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize("collection,resource_id", [("users", "user-1"), ("projects", "project-1")])
@pytest.mark.parametrize("operation", ["context", "create"])
async def test_actual_issuance_user_and_project_must_match_selected_domain(
    native_identity, collection, resource_id, operation
):
    app, state, _ = native_identity
    state[collection][resource_id]["domain_id"] = "tenant-2"
    async with scoped_client(app) as client:
        if operation == "context":
            response = await client.get("/api/v1/admin/application-credentials/context")
        else:
            response = await client.post(
                "/api/v1/admin/application-credentials", json={"name": "app", "role_ids": ["reader-id"]}
            )
    assert response.status_code == 403
    assert response.json() == {"detail": "credential_scope_denied"}
    assert state["calls"] == []


@pytest.mark.asyncio
async def test_filtered_user_list_does_not_admit_other_same_domain_owner(native_identity):
    app, state, _ = native_identity
    state["extra_credentials"] = [{**state["credential"], "id": "cred-other", "user_id": "other-user"}]
    async with scoped_client(app) as client:
        response = await client.get("/api/v1/admin/user-credentials?user_id=user-1")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["cred-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "collection,resource_id", [("domains", "default"), ("users", "user-1"), ("projects", "project-1")]
)
async def test_exact_lookup_does_not_accept_substituted_identity(native_identity, collection, resource_id):
    app, state, _ = native_identity
    state[collection][resource_id]["id"] = "substituted-id"
    async with scoped_client(app) as client:
        response = await client.post(
            "/api/v1/admin/user-credentials",
            json={"user_id": "user-1", "project_id": "project-1", "type": "ec2", "blob": "{}"},
        )
    assert response.status_code == 403
    assert state["calls"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 409, 503])
async def test_native_rollback_failure_remains_explicit_and_secret_free(native_identity, status, monkeypatch):
    from app.main import app

    isolated, state, _ = native_identity
    monkeypatch.setattr(app, "dependency_overrides", isolated.dependency_overrides)
    state["issued_override"] = {"unrestricted": True}
    state["delete_status"] = status
    async with scoped_client(app) as client:
        response = await client.post(
            "/api/v1/admin/application-credentials", json={"name": "app", "role_ids": ["reader-id"]}
        )
    assert response.status_code == 502
    assert response.json() == {"detail": "credential_rollback_failed"}
    assert "issued-secret" not in response.text and "rollback-secret" not in response.text
    assert state["calls"][-1][:2] == ("DELETE", "/v3/users/user-1/application_credentials/app-1")


@pytest.mark.asyncio
async def test_invalid_issuance_without_native_id_never_guesses_rollback_identifier(native_identity):
    app, state, _ = native_identity
    state["issued_override"] = {"id": None}
    async with scoped_client(app) as client:
        response = await client.post(
            "/api/v1/admin/application-credentials", json={"name": "app", "role_ids": ["reader-id"]}
        )
    assert response.status_code == 403
    assert "issued-secret" not in response.text
    assert [call[0] for call in state["calls"]] == ["POST"]


@pytest.mark.asyncio
@pytest.mark.parametrize("collection,resource_id", [("users", "user-1"), ("projects", "project-1")])
@pytest.mark.parametrize("status,detail", [(403, "credential_native_denied"), (404, "credential_not_found")])
async def test_owner_lookup_failure_prevents_native_mutation(native_identity, collection, resource_id, status, detail):
    app, state, _ = native_identity
    state["lookup_status"][(collection, resource_id)] = status
    async with scoped_client(app) as client:
        response = await client.post(
            "/api/v1/admin/user-credentials",
            json={"user_id": "user-1", "project_id": "project-1", "type": "ec2", "blob": "{}"},
        )
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert "lookup-secret" not in response.text
    assert state["calls"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", ["users", "projects"])
async def test_domain_inventory_native_denial_never_publishes_empty_success(native_identity, collection):
    app, state, _ = native_identity
    state["lookup_status"][(collection, "*")] = 403
    async with scoped_client(app) as client:
        response = await client.get("/api/v1/admin/user-credentials")
    assert response.status_code == 403
    assert response.json() == {"detail": "credential_native_denied"}
    assert "lookup-secret" not in response.text
    assert state["calls"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", ["users", "projects"])
@pytest.mark.parametrize(
    "bad_row",
    [{"id": "foreign", "domain_id": "tenant-2"}, {"id": "unknown"}, {"domain_id": "default"}],
)
async def test_ownership_directory_requires_proven_selected_domain_rows(native_identity, collection, bad_row):
    app, state, _ = native_identity
    local_row = state[collection]["user-1" if collection == "users" else "project-1"]
    state["directory_overrides"][collection] = [local_row, bad_row]
    async with scoped_client(app) as client:
        response = await client.get("/api/v1/admin/user-credentials")
    assert response.status_code == 403
    assert response.json() == {"detail": "credential_scope_denied"}
    assert state["calls"] == []


@pytest.mark.asyncio
async def test_user_writes_do_not_requery_ownership_after_native_commit(native_identity):
    app, state, _ = native_identity
    state["lookup_status_after_write"] = 503
    async with scoped_client(app) as client:
        created = await client.post(
            "/api/v1/admin/user-credentials",
            json={"user_id": "user-1", "project_id": "project-1", "type": "ec2", "blob": "{}"},
        )
        assert created.status_code == 201
        state["committed"] = False
        updated = await client.patch("/api/v1/admin/user-credentials/cred-1", json={"blob": "changed"})
    assert updated.status_code == 200
    assert created.json()["domain_id"] == "default" and updated.json()["domain_id"] == "default"
    assert [call[0] for call in state["calls"]] == ["POST", "GET", "PATCH"]


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [{"user_id": "foreign-user"}, {"project_id": "foreign-project"}])
async def test_substituted_user_credential_owner_is_revoked_before_publication(native_identity, override):
    app, state, _ = native_identity
    state["user_issued_override"] = override
    state["lookup_status_after_write"] = 503
    async with scoped_client(app) as client:
        response = await client.post(
            "/api/v1/admin/user-credentials",
            json={"user_id": "user-1", "project_id": "project-1", "type": "ec2", "blob": "{}"},
        )
    assert response.status_code == 403
    assert response.json() == {"detail": "credential_scope_denied"}
    assert state["calls"][-1][:2] == ("DELETE", "/v3/credentials/cred-1")
    assert "sensitive-blob" not in response.text


@pytest.mark.asyncio
async def test_substituted_user_creation_rollback_failure_is_not_normal_scope_denial(native_identity, monkeypatch):
    from app.main import app

    isolated, state, _ = native_identity
    monkeypatch.setattr(app, "dependency_overrides", isolated.dependency_overrides)
    state["user_issued_override"] = {"project_id": "foreign-project"}
    state["delete_status"] = 403
    async with scoped_client(app) as client:
        response = await client.post(
            "/api/v1/admin/user-credentials",
            json={"user_id": "user-1", "project_id": "project-1", "type": "ec2", "blob": "{}"},
        )
    assert response.status_code == 502
    assert response.json() == {"detail": "credential_rollback_failed"}
    assert "rollback-secret" not in response.text


@pytest.mark.asyncio
async def test_user_update_response_must_match_prevalidated_owner_ids(native_identity):
    app, state, _ = native_identity
    state["user_updated_override"] = {"project_id": "foreign-project"}
    state["lookup_status_after_write"] = 503
    async with scoped_client(app) as client:
        response = await client.patch("/api/v1/admin/user-credentials/cred-1", json={"blob": "changed"})
    assert response.status_code == 403
    assert response.json() == {"detail": "credential_scope_denied"}
    assert [call[0] for call in state["calls"]] == ["GET", "PATCH"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["application", "user"])
async def test_already_absent_native_credential_meets_rollback_goal(native_identity, kind):
    app, state, _ = native_identity
    state["delete_status"] = 404
    if kind == "application":
        state["issued_override"] = {"unrestricted": True}
        path = "/api/v1/admin/application-credentials"
        body = {"name": "app", "role_ids": ["reader-id"]}
        native_path = "/v3/users/user-1/application_credentials/app-1"
    else:
        state["user_issued_override"] = {"project_id": "foreign-project"}
        path = "/api/v1/admin/user-credentials"
        body = {"user_id": "user-1", "project_id": "project-1", "type": "ec2", "blob": "{}"}
        native_path = "/v3/credentials/cred-1"
    async with scoped_client(app) as client:
        response = await client.post(path, json=body)
    assert response.status_code == 403
    assert response.json() == {"detail": "credential_scope_denied"}
    assert state["calls"][-1][:2] == ("DELETE", native_path)
    assert "issued-secret" not in response.text and "rollback-secret" not in response.text
