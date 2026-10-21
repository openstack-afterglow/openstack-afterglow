"""Native package BFF consumer boundaries, isolated from Keystone/Hub resources."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request

from app.api.palimpsest import hub, package_keys, packages
from app.config import get_settings
from app.models.domain_auth import DomainLoginPolicy
from app.services import identity_roles, keystone, service_proxy
from app.services.service_permissions import ROLE_PRESETS
from tests.test_domain_auth import db as db

PROJECT = "11111111111141118111111111111111"
FOREIGN = "22222222222242228222222222222222"
USER = "33333333333343338333333333333333"
KEY_ID = "44444444444444448444444444444444"
NAMESPACE = "p-" + PROJECT
DIGEST = "sha256:" + "a" * 64
KEY = "ppk_v1_" + KEY_ID + "." + "A" * 43
BASE = "/api/v1/palimpsest"
INVENTORY = "palimpsest-inventory_reader"
DOWNLOAD = "palimpsest-download_user"
PUBLISH = "palimpsest-publish_editor"
KEYS_EDITOR = "palimpsest-keys_editor"
KEYS_ADMIN = "palimpsest-keys_admin"
PACKAGE_LEAVES = [INVENTORY, DOWNLOAD, PUBLISH, KEYS_EDITOR, KEYS_ADMIN]
LEGACY_ACTIONS = [
    ("GET", "layers", INVENTORY),
    ("GET", "layers/" + DIGEST + "/blob", DOWNLOAD),
    ("POST", "image-exports", PUBLISH),
    ("DELETE", f"image-exports/{KEY_ID}", PUBLISH),
    ("GET", "images", INVENTORY),
    ("PATCH", f"uploads/{KEY_ID}", PUBLISH),
    ("POST", "bundles", DOWNLOAD),
    ("GET", "health", INVENTORY),
    ("GET", "", INVENTORY),
]


@pytest.fixture
async def package_client(monkeypatch):
    app = FastAPI()
    app.include_router(packages.router, prefix=BASE + "/packages")
    app.include_router(package_keys.router, prefix=BASE + "/package-keys")
    app.include_router(hub.router, prefix=BASE + "/hub")
    monkeypatch.setattr(get_settings(), "service_palimpsest_enabled", True)
    monkeypatch.setattr(get_settings(), "service_palimpsest_internal_url", "https://hub.invalid/v1")
    names = ["admin", "manager", "member", "reader", "service", *(row["name"] for row in ROLE_PRESETS)]
    rows = [{"id": "id-" + name, "name": name} for name in names]

    async def identity(request: Request):
        info = {
            "project_id": PROJECT,
            "user_id": USER,
            "token": "original-subject",
            "domain_id": "default",
            "identity_domain_id": "default",
            "roles": state.grants.copy(),
            "is_system_admin": state.is_system_admin,
        }
        request.state.token_info = info
        return info

    app.dependency_overrides[packages.package_browser_identity] = identity
    state = SimpleNamespace(
        context={
            "project_id": PROJECT,
            "project_name": "Project",
            "namespace": NAMESPACE,
            "package_authority": "packages.invalid:8443",
            "capabilities": {
                "packages_read": True,
                "packages_download": True,
                "packages_write": True,
                "keys_issue": True,
                "keys_revoke": True,
            },
        },
        payload={"project_id": PROJECT, "namespace": NAMESPACE, "items": [], "next_cursor": None},
        status=200,
        policy_status=200,
        policy={"service": "palimpsest", "capabilities": [], "actions": []},
        headers={},
        downloads=0,
        paths=[],
        actors=[],
        bodies=[],
    )
    state.grants = ["palimpsest_admin"]
    state.catalog = identity_roles._catalog(rows, [])
    state.assignment_user_id = USER
    state.project_ids = {PROJECT, FOREIGN}
    state.is_system_admin = False
    state.has_system_admin_role = False
    state.native_credential_valid = True

    def assignments(**query):
        projects = state.project_ids.copy()
        if "project" in query:
            projects &= {query["project"]}
        return [
            {
                "user": {"id": state.assignment_user_id},
                "role": {"id": "id-" + name},
                "scope": {"project": {"id": project_id}},
            }
            for project_id in sorted(projects)
            for name in state.grants
        ]

    def native_user(user_id):
        from keystoneauth1.exceptions.http import NotFound

        if user_id != state.assignment_user_id:
            raise NotFound()
        # Exact native identity: home domain/email do not come from a selected project or JWT.
        return {"id": user_id, "domain_id": "default", "enabled": True, "email": "owner@packages.example"}

    def native_project(project_id):
        from keystoneauth1.exceptions.http import NotFound

        if project_id not in state.project_ids:
            raise NotFound()
        return {"id": project_id, "name": "Project", "domain_id": "default", "enabled": True}

    def native_domain(domain_id):
        from keystoneauth1.exceptions.http import NotFound

        if domain_id != "default":
            raise NotFound()
        return {"id": domain_id, "name": "Default", "enabled": True}

    # Native membership provenance remains real; service policy never uses a local role DAG.
    provider = SimpleNamespace(
        roles=SimpleNamespace(list=lambda: rows),
        inference_rules=SimpleNamespace(list_inference_roles=lambda: []),
        role_assignments=SimpleNamespace(list=assignments),
        users=SimpleNamespace(get=native_user),
        projects=SimpleNamespace(get=native_project, list=lambda **_: []),
        domains=SimpleNamespace(get=native_domain),
    )
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: provider)
    monkeypatch.setattr(identity_roles, "_trusted_catalog", lambda: state.catalog)
    monkeypatch.setattr(keystone, "_is_system_admin", lambda *args, **kwargs: state.is_system_admin)
    monkeypatch.setattr(keystone, "_has_system_admin_role", lambda *args, **kwargs: state.has_system_admin_role)

    issued = {}

    def validate_native(token, project_id="", *, operation=None):
        from keystoneauth1.exceptions.http import Unauthorized

        user_id = state.assignment_user_id if token == "original-subject" else issued.get(token)
        if user_id is None or not state.native_credential_valid:
            raise Unauthorized()
        identity = keystone.get_identity_user(user_id, operation=operation)
        if project_id:
            native_project(project_id)
        native_token = f"project-subject:{user_id}:{project_id}" if project_id else "original-subject"
        issued[native_token] = user_id
        return {
            "token": native_token,
            "user_id": user_id,
            "username": "user",
            "project_id": project_id,
            "project_name": "Project" if project_id else "",
            "domain_id": "default",
            "domain_name": "Default",
            "identity_domain_id": identity["domain_id"],
            "identity_domain_name": "Default",
            "email": identity["email"],
            "roles": getattr(state, "stale_native_roles", state.grants).copy() if project_id else [],
            "is_system_admin": state.is_system_admin,
            "is_domain_manager": False,
        }

    monkeypatch.setattr(keystone, "validate_token", validate_native)

    async def upstream(request: httpx.Request):
        state.paths.append(request.url.path)
        state.actors.append(dict(request.headers))
        state.bodies.append(await request.aread())
        if not request.headers.get("authorization", "").startswith("Bearer ppk_v1_"):
            subject = request.headers.get("x-auth-token")
            if not state.native_credential_valid or not (subject == "original-subject" or subject in issued):
                return httpx.Response(
                    401, json={"error": {"code": "AUTH_REQUIRED", "message": "Native credential required"}}
                )
            if request.headers.get("x-project-id") not in state.project_ids:
                return httpx.Response(
                    403, json={"error": {"code": "PROJECT_SCOPE_MISMATCH", "message": "Invalid project"}}
                )
        if request.url.path == "/v1/policy/capabilities":
            return httpx.Response(state.policy_status, json=state.policy)
        if request.url.path == "/v1/projects/current":
            return httpx.Response(200, json=state.context)
        if request.url.path.endswith("/download"):
            state.downloads += 1
            return httpx.Response(206, content=b"verified-archive", headers={"content-range": "bytes 0-15/16"})
        return httpx.Response(
            state.status,
            stream=httpx.ByteStream(b"" if state.status == 204 else json.dumps(state.payload).encode()),
            headers={"content-type": "application/json", **state.headers},
        )

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        service_proxy.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(upstream), **kwargs),
    )
    async with client_type(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, state, app


@pytest.mark.parametrize("role", ["palimpsest_editor", PUBLISH, "admin"])
@pytest.mark.parametrize("capabilities", [[], [PUBLISH]])
async def test_native_package_capabilities_are_not_inferred_from_caller_roles(package_client, role, capabilities):
    _, state, _ = package_client
    state.policy["capabilities"] = capabilities
    result = await service_proxy.get_policy_capabilities(
        "palimpsest",
        {"token": "original-subject", "user_id": USER, "project_id": PROJECT, "roles": [role]},
    )
    assert result == state.policy
    assert result["capabilities"] == capabilities
    assert state.paths == ["/v1/policy/capabilities"]
    assert state.actors[0]["x-auth-token"] == "original-subject"
    assert state.actors[0]["x-project-id"] == PROJECT
    assert "authorization" not in state.actors[0]


@pytest.mark.parametrize("native_status", [401, 403, 503])
async def test_native_package_policy_failure_has_no_role_or_system_fallback(package_client, native_status):
    _, state, _ = package_client
    state.policy_status = native_status
    with pytest.raises(HTTPException) as denied:
        await service_proxy.get_policy_capabilities(
            "palimpsest",
            {
                "token": "original-subject",
                "user_id": USER,
                "project_id": PROJECT,
                "roles": ["admin", *PACKAGE_LEAVES],
                "is_system_admin": True,
            },
        )
    assert denied.value.status_code == native_status
    assert state.paths == ["/v1/policy/capabilities"]
    assert state.downloads == 0


@pytest.mark.parametrize("token", ["", "unknown-native-token"])
async def test_native_package_capabilities_require_original_native_credentials(package_client, token):
    _, state, _ = package_client
    state.policy["capabilities"] = [PUBLISH]
    with pytest.raises(HTTPException) as denied:
        await service_proxy.get_policy_capabilities(
            "palimpsest", {"token": token, "project_id": PROJECT, "roles": ["admin", *PACKAGE_LEAVES]}
        )
    assert denied.value.status_code == 401
    assert state.paths == (["/v1/policy/capabilities"] if token else [])
    assert state.downloads == 0


async def test_foreign_context_is_never_exposed_or_followed(package_client):
    client, state, _ = package_client
    state.context["project_id"] = FOREIGN
    response = await client.get(BASE + "/packages")
    assert response.status_code == 503
    assert FOREIGN not in response.text
    assert state.paths == ["/v1/projects/current"]


@pytest.mark.parametrize("foreign_item", [False, True])
async def test_inventory_checks_envelope_and_each_item_ownership(package_client, foreign_item):
    client, state, _ = package_client
    if foreign_item:
        state.payload["items"] = [{"project_id": FOREIGN, "namespace": NAMESPACE, "name": "private"}]
    else:
        state.payload["project_id"] = FOREIGN
    response = await client.get(BASE + "/packages")
    assert response.status_code == 503
    assert "private" not in response.text
    assert FOREIGN not in response.text


async def test_unregistered_context_is_explicit_and_does_not_issue_or_list(package_client):
    client, state, _ = package_client
    state.context["namespace"] = None
    context = await client.get(BASE + "/packages/context")
    assert context.json()["namespace"] is None
    for method, path in [("GET", "/packages"), ("POST", "/package-keys")]:
        response = await client.request(method, BASE + path, json={} if method == "POST" else None)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "NAMESPACE_UNREGISTERED"
    assert set(state.paths) == {"/v1/projects/current"}


async def test_foreign_deeplink_namespace_never_selects_upstream(package_client):
    client, state, _ = package_client
    response = await client.get(BASE + "/packages", params={"namespace": "foreign"})
    assert response.status_code == 403
    assert state.paths == ["/v1/projects/current"]


@pytest.mark.parametrize("query", ["project_id=" + FOREIGN, "limit=101", "package_type=buildkit-cache"])
async def test_unsupported_inventory_selectors_fail_before_hub(package_client, query):
    client, state, _ = package_client
    response = await client.get(BASE + "/packages?" + query)
    assert response.status_code == 422
    assert state.paths == []


async def test_key_list_rejects_another_owners_key(package_client):
    client, state, _ = package_client
    state.payload = {
        "project_id": PROJECT,
        "namespace": NAMESPACE,
        "items": [{"project_id": PROJECT, "namespace": NAMESPACE, "owner_user_id": FOREIGN, "key_id": KEY_ID}],
    }
    response = await client.get(BASE + "/package-keys")
    assert response.status_code == 503
    assert KEY_ID not in response.text


async def test_secret_once_issue_requires_matching_project_owner(package_client):
    client, state, _ = package_client
    state.status = 201
    state.payload = {
        "key": {"project_id": FOREIGN, "namespace": NAMESPACE, "owner_user_id": USER, "key_id": KEY_ID},
        "secret": KEY,
    }
    response = await client.post(BASE + "/package-keys", json={"name": "ci"})
    assert response.status_code == 503
    assert KEY not in response.text
    state.payload["key"]["project_id"] = PROJECT
    response = await client.post(BASE + "/package-keys", json={"name": "ci"})
    assert response.status_code == 201
    assert response.json()["secret"] == KEY
    assert "no-store" in response.headers["cache-control"]


async def test_human_system_admin_key_crud_without_project_roles_and_revocation(package_client):
    client, state, _ = package_client
    state.grants = []
    state.is_system_admin = state.has_system_admin_role = True
    key = {"project_id": PROJECT, "namespace": NAMESPACE, "owner_user_id": USER, "key_id": KEY_ID}
    state.status = 201
    state.payload = {"key": key, "secret": KEY}
    requested = {"name": "ci", "scope": {"packages": ["test"]}, "actions": ["packages:read"]}
    created = await client.post(BASE + "/package-keys", json=requested)
    assert created.status_code == 201
    assert created.json()["secret"] == KEY
    assert json.loads(state.bodies[-1]) == requested
    state.status = 200
    state.payload = {"project_id": PROJECT, "namespace": NAMESPACE, "items": [key]}
    listed = await client.get(BASE + "/package-keys")
    assert listed.status_code == 200
    assert listed.json()["items"] == [key]
    before_revoke = state.paths.copy()
    state.has_system_admin_role = state.is_system_admin = False
    denied = await client.delete(BASE + f"/package-keys/{KEY_ID}")
    assert denied.status_code == 403
    assert state.paths == before_revoke
    state.is_system_admin = state.has_system_admin_role = True
    state.status = 204
    assert (await client.delete(BASE + f"/package-keys/{KEY_ID}")).status_code == 204
    assert state.paths[-1] == f"/v1/projects/{NAMESPACE}/keys/{KEY_ID}"
    assert all(actor["x-auth-token"] == "original-subject" for actor in state.actors)
    assert all(actor["x-project-id"] == PROJECT for actor in state.actors)


@pytest.mark.parametrize("operation", ["context", "namespace", "inventory", "download"])
async def test_human_system_admin_custom_operations_need_no_project_leaves(package_client, operation):
    client, state, _ = package_client
    state.grants = []
    state.is_system_admin = state.has_system_admin_role = True
    if operation == "namespace":
        state.payload = state.context.copy()
        response = await client.put(BASE + "/packages/namespace", json={})
    elif operation == "download":
        state.payload = {"project_id": PROJECT, "namespace": NAMESPACE, "package": "test", "root_digest": DIGEST}
        response = await client.get(BASE + f"/packages/versions/{DIGEST}/download", params={"package": "test"})
        assert response.content == b"verified-archive"
    else:
        response = await client.get(BASE + ("/packages/context" if operation == "context" else "/packages"))
    assert response.status_code == (206 if operation == "download" else 200)
    assert state.paths


async def test_human_system_admin_retains_namespace_response_fence(package_client):
    client, state, _ = package_client
    state.grants = []
    state.is_system_admin = state.has_system_admin_role = True
    response = await client.get(BASE + "/packages", params={"namespace": "foreign"})
    assert response.status_code == 403
    assert state.paths == ["/v1/projects/current"]


async def test_system_admin_revoked_between_custom_preflight_and_io(package_client):
    client, state, _ = package_client
    state.grants = []
    state.is_system_admin = state.has_system_admin_role = True
    original_actors = state.actors

    class RevokeAfterContext(list):
        def append(self, actor):
            super().append(actor)
            state.is_system_admin = state.has_system_admin_role = False

    state.actors = RevokeAfterContext(original_actors)
    response = await client.get(BASE + "/packages")
    assert response.status_code == 403
    assert state.paths == ["/v1/projects/current"]


async def test_custom_system_authority_outage_prevents_hub_io(package_client, monkeypatch):
    client, state, _ = package_client
    state.grants = []
    state.is_system_admin = state.has_system_admin_role = True

    def unavailable(*_):
        raise HTTPException(503, "Current system authority unavailable")

    monkeypatch.setattr(keystone, "_has_system_admin_role", unavailable)
    response = await client.post(BASE + "/package-keys", json={"name": "ci"})
    assert response.status_code == 503
    assert state.paths == []


@pytest.mark.parametrize("method,path", [("POST", "/package-keys"), ("PUT", "/packages/namespace")])
async def test_custom_unverified_system_flag_cannot_replace_current_membership(package_client, method, path):
    client, state, _ = package_client
    state.grants = []
    state.is_system_admin = True
    state.has_system_admin_role = False
    response = await client.request(method, BASE + path, json={})
    assert response.status_code == 403
    assert state.paths == []


@pytest.mark.parametrize("service_principal", [False, True])
@pytest.mark.parametrize("method,path", [("POST", "/package-keys"), ("PUT", "/packages/namespace")])
async def test_custom_admin_and_service_principals_cannot_override_native_denial(
    package_client, service_principal, method, path
):
    client, state, _ = package_client
    state.grants = ["service"] if service_principal else ["admin", *PACKAGE_LEAVES]
    state.is_system_admin = state.has_system_admin_role = service_principal
    state.status = 403
    state.payload = {"error": {"code": "ACTION_DENIED", "message": "Native package policy denied the caller"}}
    response = await client.request(method, BASE + path, json={})
    assert response.status_code == 403
    assert response.json() == state.payload
    expected_path = f"/v1/projects/{NAMESPACE}/keys" if method == "POST" else f"/v1/projects/{PROJECT}/namespace"
    assert state.paths == (["/v1/projects/current"] if method == "POST" else []) + [expected_path]
    assert all(actor["x-auth-token"] == "original-subject" for actor in state.actors)
    assert state.downloads == 0


@pytest.mark.parametrize("wrong", ["project", "package", "digest"])
async def test_download_requires_matching_verified_version_metadata(package_client, wrong):
    client, state, _ = package_client
    state.payload = {"project_id": PROJECT, "namespace": NAMESPACE, "package": "test", "root_digest": DIGEST}
    state.payload[{"project": "project_id", "package": "package", "digest": "root_digest"}[wrong]] = FOREIGN
    response = await client.get(BASE + f"/packages/versions/{DIGEST}/download", params={"package": "test"})
    assert response.status_code == 503
    assert state.downloads == 0


async def test_native_metadata_denial_prevents_protected_archive_download(package_client):
    client, state, _ = package_client
    state.grants = ["palimpsest_admin", *PACKAGE_LEAVES]
    state.status = 403
    state.payload = {"error": {"code": "ACTION_DENIED", "message": "Native version policy denied the caller"}}
    response = await client.get(BASE + f"/packages/versions/{DIGEST}/download", params={"package": "test"})
    assert response.status_code == 403
    assert response.json() == state.payload
    assert state.paths == ["/v1/projects/current", f"/v1/projects/{NAMESPACE}/versions/{DIGEST}"]
    assert state.downloads == 0


@pytest.mark.parametrize("method,path", [("GET", "not-a-digest/download"), ("DELETE", "not-a-key-id")])
async def test_browser_package_identifiers_fail_before_native_action(package_client, method, path):
    client, state, _ = package_client
    route = "/packages/versions/" + path if method == "GET" else "/package-keys/" + path
    response = await client.request(method, BASE + route, params={"package": "test"} if method == "GET" else None)
    assert response.status_code == 422
    assert state.paths == []


async def test_download_stream_and_upstream_error_are_not_export_tickets(package_client):
    client, state, _ = package_client
    state.payload = {"project_id": PROJECT, "namespace": NAMESPACE, "package": "test", "root_digest": DIGEST}
    response = await client.get(BASE + f"/packages/versions/{DIGEST}/download", params={"package": "test"})
    assert response.status_code == 206
    assert response.content == b"verified-archive"
    assert response.headers["content-range"] == "bytes 0-15/16"
    assert "no-store" in response.headers["cache-control"]
    assert state.actors[-1]["x-auth-token"] == "original-subject"
    assert "authorization" not in state.actors[-1]
    state.status = 404
    state.payload = {"error": {"code": "NOT_FOUND", "message": "missing", "request_id": "request"}}
    response = await client.get(BASE + "/packages/detail", params={"package": "test"})
    assert response.status_code == 404
    assert response.json() == state.payload


@pytest.mark.parametrize(
    "path,method",
    [
        ("admin/layers", "GET"),
        ("builds", "POST"),
        ("projects/current", "GET"),
        (f"projects/{NAMESPACE}/keys", "POST"),
        ("image-exports", "POST"),
        ("image-exports/export/download", "GET"),
        ("v1/auth/me", "GET"),
    ],
)
async def test_key_gateway_cannot_reach_control_admin_or_duplicate_version(package_client, path, method):
    client, state, _ = package_client
    response = await client.request(method, BASE + "/hub/" + path, headers={"authorization": "Bearer " + KEY})
    assert response.status_code == 403
    assert state.paths == []


async def test_key_gateway_requires_configured_route_not_admin_catalog(package_client, monkeypatch):
    client, state, _ = package_client
    monkeypatch.setattr(get_settings(), "service_palimpsest_internal_url", "")
    admin_discovery = AsyncMock(side_effect=AssertionError("must not use service identity"))
    monkeypatch.setattr(service_proxy, "resolve_service_endpoint", admin_discovery)
    response = await client.get(BASE + "/hub/auth/me", headers={"authorization": "Bearer " + KEY})
    assert response.status_code == 503
    assert state.paths == []
    admin_discovery.assert_not_awaited()


async def test_key_gateway_rejects_ambiguous_keystone_identity(package_client):
    client, state, _ = package_client
    response = await client.get(
        BASE + "/hub/auth/me",
        headers={
            "authorization": "Bearer " + KEY,
            "x-auth-token": "raw-keystone",
        },
    )
    assert response.status_code == 401
    assert state.paths == []


async def test_key_offset_conflict_retains_status_error_and_acknowledged_offset(package_client):
    client, state, _ = package_client
    state.status = 409
    state.headers = {"upload-offset": "7"}
    state.payload = {"error": {"code": "OFFSET_CONFLICT", "message": "offset", "request_id": "r"}}
    response = await client.patch(
        BASE + f"/hub/projects/{NAMESPACE}/uploads/{KEY_ID}",
        params={"package": "test"},
        content=b"next-chunk",
        headers={
            "authorization": "Bearer " + KEY,
            "upload-offset": "0",
            "content-type": "application/octet-stream",
        },
    )
    assert response.status_code == 409
    assert response.headers["upload-offset"] == "7"
    assert response.json() == state.payload
    assert state.bodies == [b"next-chunk"]
    assert state.paths == [f"/v1/projects/{NAMESPACE}/uploads/{KEY_ID}"]
    assert "x-auth-token" not in state.actors[0]


async def test_key_gateway_preserves_project_assertion_and_native_denial(package_client):
    client, state, _ = package_client
    state.status = 403
    state.payload = {
        "error": {
            "code": "PROJECT_SCOPE_MISMATCH",
            "message": "project assertion does not match package key",
            "request_id": "hub-scope-conflict",
        }
    }
    path = BASE + f"/hub/projects/{NAMESPACE}/uploads/{KEY_ID}"
    headers = {"authorization": "Bearer " + KEY, "x-project-id": FOREIGN, "upload-offset": "0"}
    response = await client.patch(path, content=b"asserted-chunk", headers=headers)
    assert response.status_code == 403
    assert response.json() == state.payload
    assert state.paths == [f"/v1/projects/{NAMESPACE}/uploads/{KEY_ID}"]
    assert state.bodies == [b"asserted-chunk"]
    assert state.actors[0]["x-project-id"] == FOREIGN
    assert state.actors[0]["authorization"] == "Bearer " + KEY
    assert "x-auth-token" not in state.actors[0]


@pytest.mark.parametrize("assertions", [(PROJECT, FOREIGN), (FOREIGN, PROJECT), (PROJECT, PROJECT)])
async def test_key_duplicate_project_assertions_deny_before_hub(package_client, assertions):
    client, state, _ = package_client
    headers = [("authorization", "Bearer " + KEY), *[("x-project-id", value) for value in assertions]]
    response = await client.post(BASE + f"/hub/projects/{NAMESPACE}/uploads", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert state.paths == []
    assert state.bodies == []


async def test_credential_redirect_is_not_exposed_or_followed(package_client):
    client, state, _ = package_client
    state.status = 307
    state.headers = {"location": "https://foreign.invalid/collect"}
    response = await client.get(BASE + "/hub/auth/me", headers={"authorization": "Bearer " + KEY})
    assert response.status_code == 503
    assert "location" not in response.headers
    assert state.paths == ["/v1/auth/me"]


async def test_service_toggle_fails_before_upstream(package_client, monkeypatch):
    client, state, app = package_client
    app.dependency_overrides.clear()
    monkeypatch.setattr(get_settings(), "service_palimpsest_enabled", False)
    for path in ["/packages/context", "/package-keys", "/hub/auth/me"]:
        response = await client.get(BASE + path, headers={"authorization": "Bearer " + KEY})
        assert response.status_code == 503
    assert state.paths == []


@pytest.fixture
async def browser_session(package_client, db, monkeypatch):
    """Password session with immutable native home `default` and a real SQL policy.

    Only the policy DB fixture is reused; the package provider still owns exact
    users, projects and live grants. The allowlist requires its native email,
    not the JWT username or a cached session login address.
    """
    from app.api import deps
    from app.services import domain_scope, jwt_service, session_store, token_binding

    _, _, app = package_client
    app.dependency_overrides.clear()
    async with db() as policy_session:
        policy_session.add(
            DomainLoginPolicy(
                domain_id="default",
                password_enabled=True,
                allowed_email_domains=["packages.example"],
                updated_by_user_id=USER,
            )
        )
        await policy_session.commit()
    session = {
        "project_id": PROJECT,
        "user_id": USER,
        "domain_id": "default",
        "identity_domain_id": "default",
        "auth_method": "password",
        "keystone_token": "original-subject",
        "blacklisted": False,
    }
    monkeypatch.setattr(session_store, "get_session", AsyncMock(return_value=session))
    monkeypatch.setattr(session_store, "update_session_token", AsyncMock(return_value=True))
    monkeypatch.setattr(session_store, "session_seen_needs_touch", lambda *_: False)
    monkeypatch.setattr(token_binding, "check_binding", lambda *_: ("allow", ""))
    monkeypatch.setattr(deps, "_check_session_timeout", AsyncMock())
    monkeypatch.setattr(
        domain_scope,
        "domain_context",
        lambda uid, did, **_: {
            "domain_id": did,
            "domain_name": "Default",
            "identity_domain_id": "default",
            "identity_domain_name": "Default",
            "is_domain_manager": False,
        },
    )
    monkeypatch.setattr(domain_scope, "assert_project_domain", lambda did, pid, **_: None)
    jwt, _, _ = jwt_service.sign_access(USER, "user", PROJECT, "Project", "session-id")
    return session, jwt


async def test_browser_header_cannot_rescope_signed_jwt(package_client, browser_session):
    client, state, _ = package_client
    _, jwt = browser_session
    response = await client.get(
        BASE + "/packages/context",
        headers={
            "authorization": "Bearer " + jwt,
            "x-project-id": FOREIGN,
        },
    )
    assert response.status_code == 403
    assert state.paths == []


@pytest.mark.parametrize("field", ["project_id", "user_id"])
async def test_session_jwt_identity_disagreement_denies_before_hub(package_client, browser_session, field):
    client, state, _ = package_client
    session, jwt = browser_session
    session[field] = FOREIGN
    response = await client.get(BASE + "/packages/context", headers={"authorization": "Bearer " + jwt})
    assert response.status_code in {401, 403}
    assert state.paths == []


async def test_blacklisted_browser_session_has_no_package_authority(package_client, browser_session):
    client, state, _ = package_client
    session, jwt = browser_session
    session["blacklisted"] = True
    response = await client.get(BASE + "/packages/context", headers={"authorization": "Bearer " + jwt})
    assert response.status_code == 401
    assert state.paths == []


@pytest.mark.parametrize("path", ["/packages/context", "/hub/images"])
async def test_revoked_native_login_proof_cannot_use_browser_roles(package_client, browser_session, path):
    client, state, _ = package_client
    _, jwt = browser_session
    state.grants = ["admin", *PACKAGE_LEAVES]
    state.is_system_admin = state.has_system_admin_role = True
    state.native_credential_valid = False
    response = await client.get(BASE + path, headers={"authorization": "Bearer " + jwt})
    assert response.status_code == 401
    assert state.paths == []


@pytest.mark.parametrize("path", ["/packages/context", "/hub/images"])
async def test_current_membership_revocation_cannot_use_stale_native_token_leaves(
    package_client, browser_session, path
):
    client, state, _ = package_client
    _, jwt = browser_session
    state.stale_native_roles = ["member", *PACKAGE_LEAVES]
    state.grants = []
    response = await client.get(BASE + path, headers={"authorization": "Bearer " + jwt})
    assert response.status_code == 403
    assert state.paths == []


@pytest.mark.parametrize("credential", [KEY, "raw-keystone", "eyJ.not-a-signed-jwt.payload"])
async def test_browser_package_controls_do_not_accept_data_or_raw_credentials(
    package_client,
    browser_session,
    credential,
):
    client, state, _ = package_client
    response = await client.get(BASE + "/package-keys", headers={"authorization": "Bearer " + credential})
    assert response.status_code == 401
    assert state.paths == []


async def test_federated_64hex_owner_can_issue_owned_key(package_client, browser_session):
    from app.services import jwt_service

    client, state, _ = package_client
    session, _ = browser_session
    federated_user = "f" * 64
    session["user_id"] = federated_user
    state.assignment_user_id = federated_user
    jwt, _, _ = jwt_service.sign_access(federated_user, "federated", PROJECT, "Project", "session-id")
    state.status = 201
    state.payload = {
        "key": {"project_id": PROJECT, "namespace": NAMESPACE, "owner_user_id": federated_user, "key_id": KEY_ID},
        "secret": KEY,
    }
    response = await client.post(
        BASE + "/package-keys", headers={"authorization": "Bearer " + jwt}, json={"name": "federated-ci"}
    )
    assert response.status_code == 201
    assert response.json()["key"]["owner_user_id"] == federated_user


async def test_opaque_project_identity_preserves_case_and_namespace_mapping(package_client, browser_session):
    from app.services import jwt_service

    client, state, _ = package_client
    session, _ = browser_session
    project = "LDAP-Project.Identifier"
    state.project_ids.add(project)
    session["project_id"] = project
    state.context["project_id"] = project
    state.context["namespace"] = "operator-alias"
    jwt, _, _ = jwt_service.sign_access(USER, "user", project, "Project", "session-id")
    response = await client.get(BASE + "/packages/context", headers={"authorization": "Bearer " + jwt})
    assert response.status_code == 200
    assert response.json()["project_id"] == project
    response = await client.get(
        BASE + "/packages/context",
        headers={
            "authorization": "Bearer " + jwt,
            "x-project-id": project.lower(),
        },
    )
    assert response.status_code == 403


async def test_registration_is_explicit_empty_body_and_returns_verified_context(package_client):
    client, state, _ = package_client
    state.status = 201
    state.payload = dict(state.context)
    response = await client.put(BASE + "/packages/namespace", json={"project_id": FOREIGN})
    assert response.status_code == 422
    assert state.paths == []
    response = await client.put(BASE + "/packages/namespace", json={})
    assert response.status_code == 201
    assert response.json() == state.context
    assert state.paths == [f"/v1/projects/{PROJECT}/namespace"]


async def test_revoke_preserves_owner_only_not_found(package_client):
    client, state, _ = package_client
    state.status = 404
    state.payload = {"error": {"code": "NOT_FOUND", "message": "missing", "request_id": "r"}}
    response = await client.delete(BASE + f"/package-keys/{KEY_ID}")
    assert response.status_code == 404
    assert response.json() == state.payload
    assert "no-store" in response.headers["cache-control"]


async def test_versions_latest_size_request_and_resolve_preserve_verified_metadata(package_client):
    client, state, _ = package_client
    row = {
        "project_id": PROJECT,
        "namespace": NAMESPACE,
        "package": "test",
        "root_digest": DIGEST,
        "total_bytes": 4096,
        "root_media_type": "application/vnd.oci.image.manifest.v1+json",
    }
    state.payload = {
        "project_id": PROJECT,
        "namespace": NAMESPACE,
        "package": "test",
        "items": [row],
        "next_cursor": None,
    }
    response = await client.get(BASE + "/packages/versions", params={"package": "test", "limit": 1})
    assert response.status_code == 200
    assert response.json()["items"][0]["total_bytes"] == 4096
    state.payload = dict(row, tag="v1", digest=DIGEST)
    state.headers = {"etag": '"' + DIGEST + '"'}
    response = await client.get(BASE + "/packages/resolve", params={"package": "test", "tag": "v1"})
    assert response.status_code == 200
    assert response.json()["digest"] == DIGEST
    assert response.headers["etag"] == '"' + DIGEST + '"'


async def test_real_application_package_surface_is_v1_only(package_client):
    from app.main import app as real_app

    client, state, isolated_app = package_client
    original = dict(real_app.dependency_overrides)
    real_app.dependency_overrides[packages.package_browser_identity] = isolated_app.dependency_overrides[
        packages.package_browser_identity
    ]
    # Reuse the caller's already-isolated HTTP client class, not the proxy factory.
    client_type = type(client)
    version = {"project_id": PROJECT, "namespace": NAMESPACE, "package": "test", "root_digest": DIGEST}
    key = {"project_id": PROJECT, "namespace": NAMESPACE, "owner_user_id": USER, "key_id": KEY_ID}
    cases = [
        ("GET", "/packages/context", {}, None, 200, state.context),
        ("PUT", "/packages/namespace", {}, {}, 201, state.context),
        (
            "GET",
            "/packages",
            {},
            None,
            200,
            {"project_id": PROJECT, "namespace": NAMESPACE, "items": [], "next_cursor": None},
        ),
        (
            "GET",
            "/packages/detail",
            {"package": "test"},
            None,
            200,
            {"project_id": PROJECT, "namespace": NAMESPACE, "name": "test"},
        ),
        (
            "GET",
            "/packages/resolve",
            {"package": "test", "tag": "v1"},
            None,
            200,
            dict(version, tag="v1", digest=DIGEST),
        ),
        (
            "GET",
            "/packages/versions",
            {"package": "test"},
            None,
            200,
            {"project_id": PROJECT, "namespace": NAMESPACE, "package": "test", "items": [version], "next_cursor": None},
        ),
        ("GET", f"/packages/versions/{DIGEST}", {"package": "test"}, None, 200, version),
        ("GET", f"/packages/versions/{DIGEST}/download", {"package": "test"}, None, 206, version),
        ("GET", "/package-keys", {}, None, 200, {"project_id": PROJECT, "namespace": NAMESPACE, "items": [key]}),
        ("POST", "/package-keys", {}, {"name": "ci"}, 201, {"key": key, "secret": KEY}),
        ("DELETE", f"/package-keys/{KEY_ID}", {}, None, 204, {}),
    ]
    try:
        async with client_type(transport=httpx.ASGITransport(app=real_app), base_url="http://test") as real_client:
            for method, path, query, body, status, payload in cases:
                state.status, state.payload = status if status != 206 else 200, payload
                response = await real_client.request(method, BASE + path, params=query, json=body)
                assert response.status_code == status, (path, response.text)
                legacy = await real_client.request(method, "/api/palimpsest" + path, params=query, json=body)
                assert legacy.status_code == 404
    finally:
        real_app.dependency_overrides.clear()
        real_app.dependency_overrides.update(original)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "auth/me"),
        ("GET", "projects/current"),
        ("PUT", f"projects/{PROJECT}/namespace"),
        ("POST", f"projects/{NAMESPACE}/keys"),
        ("GET", f"projects/{NAMESPACE}/keys"),
        ("DELETE", f"projects/{NAMESPACE}/keys/{KEY_ID}"),
        ("GET", f"projects/{NAMESPACE}/packages"),
        ("GET", f"projects/{NAMESPACE}/versions/{DIGEST}/download"),
        ("POST", f"projects/{NAMESPACE}/uploads"),
        ("PATCH", f"projects/{NAMESPACE}/uploads/{KEY_ID}"),
        ("GET", f"projects/{NAMESPACE}/cache/resolve"),
        ("POST", f"projects/{NAMESPACE}/cache/uploads"),
        ("GET", "admin/projects"),
        ("POST", "layers/%2e%2e/projects/current"),
    ],
)
@pytest.mark.parametrize("asserted_project", [None, FOREIGN])
async def test_legacy_jwt_native_routes_are_denied_before_hub(
    package_client,
    browser_session,
    method,
    path,
    asserted_project,
):
    client, state, _ = package_client
    _, jwt = browser_session
    headers = {"authorization": "Bearer " + jwt}
    if asserted_project is not None:
        headers["x-project-id"] = asserted_project
    response = await client.request(method, BASE + "/hub/" + path, headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACTION_DENIED"
    assert state.paths == []


@pytest.fixture
def legacy_browser_session(package_client, browser_session, monkeypatch):
    _, state, _ = package_client
    # A native token can retain issuance-time leaves after current policy denies an action.
    state.stale_native_roles = ["member", *PACKAGE_LEAVES]
    monkeypatch.setattr("app.services.recent_projects.record_project_access", AsyncMock())
    return browser_session


async def test_revoked_home_password_policy_blocks_package_and_legacy_hub(package_client, legacy_browser_session, db):
    client, state, _ = package_client
    _, jwt = legacy_browser_session
    headers = {"authorization": "Bearer " + jwt}
    paths = ["/packages/context", "/hub/images"]
    for path in paths:
        response = await client.get(BASE + path, headers=headers)
        assert response.status_code == 200
    assert state.paths == ["/v1/projects/current", "/v1/images"]

    async with db() as policy_session:
        policy = await policy_session.get(DomainLoginPolicy, "default")
        policy.password_enabled = False
        policy.revision += 1
        await policy_session.commit()

    for path in paths:
        response = await client.get(BASE + path, headers=headers)
        assert response.status_code == 403
    assert state.paths == ["/v1/projects/current", "/v1/images"]


@pytest.mark.parametrize("method,path,leaf", LEGACY_ACTIONS)
@pytest.mark.parametrize("asserted_project", [None, FOREIGN])
@pytest.mark.parametrize("role_kind", ["grade", "leaf"])
async def test_legacy_jwt_hub_surface_retains_caller_identity(
    package_client,
    legacy_browser_session,
    method,
    path,
    leaf,
    asserted_project,
    role_kind,
):
    client, state, _ = package_client
    _, jwt = legacy_browser_session
    grade = {INVENTORY: "palimpsest_reader", DOWNLOAD: "palimpsest_user", PUBLISH: "palimpsest_editor"}[leaf]
    state.grants = [grade if role_kind == "grade" else leaf]
    headers = {"authorization": "Bearer " + jwt}
    if asserted_project is not None:
        headers["x-project-id"] = asserted_project
    response = await client.request(method, BASE + "/hub/" + path, headers=headers)
    assert response.status_code == 200
    assert state.paths == ["/v1/" + path]
    assert state.actors[0]["x-project-id"] == (asserted_project or PROJECT)
    assert state.actors[0]["x-auth-token"] == f"project-subject:{USER}:{asserted_project or PROJECT}"
    assert "authorization" not in state.actors[0]


@pytest.mark.parametrize("method,path,leaf", LEGACY_ACTIONS)
@pytest.mark.parametrize("asserted_project", [None, FOREIGN])
async def test_legacy_jwt_native_action_denial_is_not_replaced_by_token_leaves(
    package_client, legacy_browser_session, method, path, leaf, asserted_project
):
    client, state, _ = package_client
    _, jwt = legacy_browser_session
    state.grants = ["palimpsest_admin", *PACKAGE_LEAVES]
    state.status = 403
    state.payload = {"error": {"code": "ACTION_DENIED", "message": f"Native policy denied {leaf}"}}
    headers = {"authorization": "Bearer " + jwt}
    if asserted_project is not None:
        headers["x-project-id"] = asserted_project
    response = await client.request(method, BASE + "/hub/" + path, headers=headers)
    assert response.status_code == 403
    assert response.json() == state.payload
    assert state.paths == ["/v1/" + path]
    assert state.actors[0]["x-auth-token"] == f"project-subject:{USER}:{asserted_project or PROJECT}"
    assert state.actors[0]["x-project-id"] == (asserted_project or PROJECT)
    assert "authorization" not in state.actors[0]
    assert state.downloads == 0


@pytest.mark.parametrize("system_admin,native_status", [(False, 403), (True, 403), (True, 200)])
@pytest.mark.parametrize("asserted_project", [None, FOREIGN])
async def test_legacy_builds_preserve_native_system_and_operator_policy_decisions(
    package_client, legacy_browser_session, system_admin, native_status, asserted_project
):
    client, state, _ = package_client
    _, jwt = legacy_browser_session
    # The native build API retains system-only checks as well as operator policy.
    # Project admin/leaves cannot turn a native denial into permission to build.
    state.grants = ["admin", "member", *PACKAGE_LEAVES]
    state.is_system_admin = state.has_system_admin_role = system_admin
    state.status = native_status
    state.payload = (
        {"error": {"code": "ACTION_DENIED", "message": "Native build authority is required"}}
        if native_status == 403
        else {"items": []}
    )
    headers = {"authorization": "Bearer " + jwt}
    if asserted_project is not None:
        headers["x-project-id"] = asserted_project
    response = await client.get(BASE + "/hub/builds", headers=headers)
    assert response.status_code == native_status
    assert response.json() == state.payload
    assert state.paths == ["/v1/builds"]
    connection_project = PROJECT if system_admin else (asserted_project or PROJECT)
    assert state.actors[0]["x-project-id"] == connection_project
    assert state.actors[0]["x-auth-token"] == f"project-subject:{USER}:{connection_project}"
    assert state.actors[0].get("x-target-project-id", connection_project) == (asserted_project or PROJECT)
    assert "authorization" not in state.actors[0]


@pytest.mark.parametrize("method,path", [("DELETE", "image-exports/export-1"), ("PATCH", "uploads/session-1")])
async def test_legacy_hub_preserves_native_invalid_identifier_response(
    package_client, legacy_browser_session, method, path
):
    client, state, _ = package_client
    _, jwt = legacy_browser_session
    state.status = 422
    state.payload = {"error": {"code": "INVALID_IDENTIFIER", "message": "Invalid native resource identifier"}}
    response = await client.request(method, BASE + "/hub/" + path, headers={"authorization": "Bearer " + jwt})
    assert response.status_code == 422
    assert response.json() == state.payload
    assert state.paths == ["/v1/" + path]


async def test_legacy_jwt_publish_revocation_uses_current_native_policy(package_client, legacy_browser_session):
    client, state, _ = package_client
    _, jwt = legacy_browser_session
    state.grants = ["member", "palimpsest_editor"]
    path = BASE + f"/hub/uploads/{KEY_ID}"
    headers = {"authorization": "Bearer " + jwt}
    response = await client.patch(path, headers=headers, content=b"allowed-chunk")
    assert response.status_code == 200
    # The same session, grade and issuance-time token leaves remain unchanged.
    # Only the native service's current operator-policy decision is revoked.
    state.status = 403
    state.payload = {"error": {"code": "ACTION_DENIED", "message": "Current native publish authority is required"}}
    response = await client.patch(path, headers=headers, content=b"revoked-chunk")
    assert response.status_code == 403
    assert response.json() == state.payload
    assert state.paths == [f"/v1/uploads/{KEY_ID}", f"/v1/uploads/{KEY_ID}"]
    assert state.bodies == [b"allowed-chunk", b"revoked-chunk"]
    assert state.actors[0] == state.actors[1]


async def test_browser_jwt_and_keystone_header_are_ambiguous(package_client, browser_session):
    client, state, _ = package_client
    _, jwt = browser_session
    response = await client.get(
        BASE + "/packages/context",
        headers={
            "authorization": "Bearer " + jwt,
            "x-auth-token": "other-keystone",
        },
    )
    assert response.status_code == 401
    assert state.paths == []


@pytest.mark.parametrize(
    "authority",
    [
        "",
        "https://foreign.invalid",
        "user@foreign.invalid",
        "foreign.invalid/path",
        "foreign.invalid:bad",
        "foreign.invalid?target=other",
        "foreign.invalid\\evil",
    ],
)
async def test_context_requires_bare_trusted_reference_authority(package_client, authority):
    client, state, _ = package_client
    state.context["package_authority"] = authority
    response = await client.get(BASE + "/packages/context")
    assert response.status_code == 503
    assert "foreign.invalid" not in response.text


async def test_package_transport_cannot_forward_admin_home_token_to_foreign_project(package_client):
    client, state, app = package_client

    async def inconsistent_identity(request: Request):
        info = {
            "project_id": FOREIGN,
            "connection_project_id": PROJECT,
            "user_id": USER,
            "token": "original-subject",
            "is_system_admin": True,
        }
        request.state.token_info = info
        return info

    app.dependency_overrides[packages.package_browser_identity] = inconsistent_identity
    response = await client.get(BASE + "/packages/context")
    assert response.status_code == 403
    assert state.paths == []


async def test_explicit_null_reference_authority_never_guesses_request_host(package_client):
    client, state, _ = package_client
    state.context["package_authority"] = None
    response = await client.get(BASE + "/packages/context", headers={"host": "browser.invalid"})
    assert response.status_code == 200
    assert response.json()["package_authority"] is None
    del state.context["package_authority"]
    response = await client.get(BASE + "/packages/context")
    assert response.status_code == 503


@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_empty_key_success_cannot_be_treated_as_list_or_issuance(package_client, method):
    client, state, _ = package_client
    state.status = 204
    state.payload = {}
    response = await client.request(method, BASE + "/package-keys", json={} if method == "POST" else None)
    assert response.status_code == 503


async def test_browser_route_requires_configured_hub_without_token_exchange(package_client, monkeypatch):
    from app.services import keystone

    client, state, _ = package_client
    monkeypatch.setattr(get_settings(), "service_palimpsest_internal_url", "")
    exchange = AsyncMock(side_effect=AssertionError("must not re-authenticate the original subject"))
    monkeypatch.setattr(keystone, "get_openstack_connection", exchange)
    response = await client.get(BASE + "/packages/context")
    assert response.status_code == 503
    assert state.paths == []
    exchange.assert_not_called()
