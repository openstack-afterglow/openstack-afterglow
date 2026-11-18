"""MCP catalog BFF transport preserves native caller and service authority."""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request

from app.api.deps import get_token_info
from app.api.lumen.proxy import router
from app.services import domain_scope, identity_roles, keystone, project_service, service_proxy
from app.services.service_permissions import ROLE_IMPLICATIONS, ROLE_PRESETS


@pytest.fixture
async def catalog_proxy(monkeypatch):
    names = ["admin", "manager", "member", "reader", *(row["name"] for row in ROLE_PRESETS)]
    catalog = identity_roles._catalog(
        [{"id": f"role-{name}", "name": name} for name in names],
        [
            {"prior_role": {"id": f"role-{prior}"}, "implies": [{"id": f"role-{implied}"}]}
            for prior, implied in ROLE_IMPLICATIONS
        ],
    )
    state = SimpleNamespace(
        token_info={
            "token": "caller-native-token",
            "user_id": "user-a",
            "project_id": "project-a",
            "domain_id": "domain-a",
            "identity_domain_id": "identity-domain-a",
            "roles": ["admin", "manager"],  # Deliberately stale, untrusted JWT role hints.
            "is_system_admin": False,
        },
        roles=["member"],
        membership_reads=[],
        admin_reads=[],
        live_admin=False,
        auth_error=None,
        transport_failure=False,
        endpoint="https://lumen.test/v1",
        endpoint_reads=[],
        forwarded=[],
        status=200,
        response_body=b'{"ok":true}',
    )

    def assignments(**kwargs):
        state.membership_reads.append(kwargs)
        assert kwargs == {"project": "project-a", "effective": True}
        return [
            {"user": {"id": "user-a"}, "role": {"id": f"role-{name}"}, "scope": {"project": {"id": "project-a"}}}
            for name in state.roles
        ]

    def endpoint(token, project_id, service):
        state.endpoint_reads.append((token, project_id, service))
        return state.endpoint

    def system_admin(user_id, **kwargs):
        state.admin_reads.append(user_id)
        return state.live_admin

    monkeypatch.setattr(
        project_service.keystone,
        "_get_admin_ks_client",
        lambda: SimpleNamespace(role_assignments=SimpleNamespace(list=assignments)),
    )
    monkeypatch.setattr(identity_roles, "_trusted_catalog", lambda: catalog)
    monkeypatch.setattr(service_proxy, "_get_internal_endpoint", endpoint)
    monkeypatch.setattr(service_proxy, "get_settings", lambda: SimpleNamespace(ssl_verify=True))
    monkeypatch.setattr(domain_scope, "domain_context", lambda *args, **kwargs: {})
    monkeypatch.setattr(domain_scope, "assert_token_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(keystone, "validate_token", lambda *args, **kwargs: {"roles": ["member"]})
    monkeypatch.setattr(keystone, "_is_system_admin", system_admin)

    async def upstream(request):
        body = await request.aread()
        state.forwarded.append((request.method, str(request.url), dict(request.headers), body))
        if state.transport_failure:
            raise httpx.ConnectError("Synthetic native transport failure", request=request)
        return httpx.Response(
            state.status,
            headers={"content-type": "application/json", "cache-control": "public, max-age=3600"},
            stream=httpx.ByteStream(state.response_body),
        )

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        service_proxy.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(upstream), **kwargs),
    )
    bff = FastAPI()
    bff.include_router(router, prefix="/api/v1/chat")

    async def authenticated(request: Request):
        if state.auth_error is not None:
            raise HTTPException(status_code=state.auth_error, detail="Synthetic authentication failure")
        request.state.token_info = state.token_info.copy()
        return request.state.token_info

    bff.dependency_overrides[get_token_info] = authenticated
    async with client_type(transport=httpx.ASGITransport(app=bff), base_url="https://browser.test") as client:
        yield state, client


def assert_private(response):
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload", "status"),
    [
        ("GET", "mcp-settings?q=GitHub&featured=true&access=oauth&state=needs_auth&offset=20&limit=10", None, 200),
        ("POST", "mcp-connections", {"template_id": 7, "label": "Work", "variables": {"region": "eu"}}, 201),
        ("PATCH", "mcp-connections/12", {"headers": {"Authorization": "synthetic-secret"}, "is_active": True}, 200),
        ("DELETE", "mcp-connections/12", None, 204),
        ("GET", "domains/domain-a/mcp-connections?offset=0&limit=50", None, 200),
        ("POST", "domains/domain-a/mcp-connections", {"template_id": 7, "auth_mode": "oauth"}, 201),
        ("PATCH", "domains/domain-a/mcp-connections/12", {"name": "Team", "oauth_scopes": ["read"]}, 200),
        ("DELETE", "domains/domain-a/mcp-connections/12", None, 204),
        ("PATCH", "domains/domain-a/mcp-connections/12/activation", {"is_active": True, "config_version": 3}, 200),
        ("PATCH", "mcp-servers/12/activation", {"is_active": True, "config_version": 3}, 200),
        ("POST", "mcp-servers/12/oauth/start", None, 200),
        ("GET", "mcp-servers/12/oauth", None, 200),
        ("DELETE", "mcp-servers/12/oauth", None, 204),
        ("GET", "archived-connections", None, 200),
        ("GET", "domains/domain-a/archived-connections", None, 200),
        ("POST", "archived-connections/17/restore", None, 200),
        ("POST", "domains/domain-a/archived-connections/17/restore", None, 200),
    ],
)
async def test_catalog_routes_preserve_method_query_body_and_native_member(
    catalog_proxy, method, path, payload, status
):
    state, client = catalog_proxy
    state.status = status
    state.response_body = b"" if status == 204 else b'{"native":"unchanged"}'
    body = json.dumps(payload).encode() if payload is not None else b""
    response = await client.request(
        method, f"/api/v1/chat/{path}", content=body, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == status
    assert response.content == state.response_body
    assert_private(response)
    forwarded_method, url, headers, forwarded_body = state.forwarded[0]
    assert forwarded_method == method
    assert url == f"https://lumen.test/v1/{path}"
    assert forwarded_body == body
    assert headers["content-type"] == "application/json"
    assert headers["x-auth-token"] == "caller-native-token"
    assert headers["x-project-id"] == "project-a"
    assert "x-target-project-id" not in headers
    assert state.membership_reads == [{"project": "project-a", "effective": True}]
    assert state.admin_reads == []
    assert state.endpoint_reads == [("caller-native-token", "project-a", "lumen")]


@pytest.mark.asyncio
async def test_foreign_domain_and_identity_claims_never_change_forwarded_authority(catalog_proxy):
    state, client = catalog_proxy
    state.status = 403  # Lumen, not the BFF, owns exact-domain management policy.
    state.response_body = b'{"detail":"Forbidden"}'
    payload = {
        "template_id": 7,
        "user_id": "other-user",
        "project_id": "other-project",
        "domain_id": "domain-b",
        "is_system_admin": True,
        "can_manage_domain": True,
        "roles": ["admin"],
    }
    response = await client.post(
        "/api/v1/chat/domains/domain-b/mcp-connections?domain_id=domain-b&user_id=other-user",
        json=payload,
        headers={
            "Authorization": "Bearer browser-jwt",
            "X-Auth-Token": "forged-admin-token",
            "X-Project-Id": "other-project",
            "X-Target-Project-Id": "other-project",
            "X-User-Id": "other-user",
            "X-Domain-Id": "domain-b",
            "X-Roles": "admin",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}
    assert_private(response)
    method, url, headers, body = state.forwarded[0]
    assert method == "POST"
    assert url == "https://lumen.test/v1/domains/domain-b/mcp-connections?domain_id=domain-b&user_id=other-user"
    assert json.loads(body) == payload
    assert headers["x-auth-token"] == "caller-native-token"
    assert headers["x-project-id"] == "project-a"
    assert not {"authorization", "x-target-project-id", "x-user-id", "x-domain-id", "x-roles"} & headers.keys()
    assert state.admin_reads == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["authentication", "membership", "directory", "endpoint", "transport", "native"])
async def test_mcp_failures_are_private_without_fallback(catalog_proxy, monkeypatch, failure):
    state, client = catalog_proxy
    if failure == "authentication":
        state.auth_error = 401
    elif failure == "membership":
        state.roles = []
    elif failure == "directory":

        async def unavailable(*args, **kwargs):
            raise HTTPException(status_code=503, detail="Native directory unavailable")

        monkeypatch.setattr(project_service, "get_project_access", unavailable)
    elif failure == "endpoint":
        state.endpoint = None
    elif failure == "transport":
        state.transport_failure = True
    else:
        state.status = 503
    response = await client.get("/api/v1/chat/mcp-settings")

    expected = 401 if failure == "authentication" else 403 if failure == "membership" else 503
    assert response.status_code == expected
    assert_private(response)
    assert state.admin_reads == []
    if failure in {"authentication", "membership", "directory"}:
        assert state.endpoint_reads == []
        assert state.forwarded == []


@pytest.mark.asyncio
@pytest.mark.parametrize("claimed_admin", [False, True])
async def test_featured_install_rejects_ordinary_or_revoked_system_admin(catalog_proxy, claimed_admin):
    state, client = catalog_proxy
    state.token_info["is_system_admin"] = claimed_admin
    response = await client.post("/api/v1/chat/admin/mcp-registry/install-featured")

    assert response.status_code == 403
    assert_private(response)
    assert state.admin_reads == (["user-a"] if claimed_admin else [])
    assert state.endpoint_reads == []
    assert state.forwarded == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "admin/mcp-registry?offset=0&limit=50", None),
        ("POST", "admin/mcp-registry/install-featured", None),
        ("POST", "admin/mcp-registry/install-all", None),
        ("POST", "admin/mcp-registry/7/install", {"label": "Shared"}),
    ],
)
async def test_registry_routes_keep_fresh_admin_and_exact_transport(catalog_proxy, method, path, payload):
    state, client = catalog_proxy
    state.token_info["is_system_admin"] = True
    state.live_admin = True
    body = json.dumps(payload).encode() if payload is not None else b""
    response = await client.request(method, f"/api/v1/chat/{path}", content=body)

    assert response.status_code == 200
    assert_private(response)
    assert state.admin_reads == ["user-a"]
    assert state.membership_reads == []
    forwarded_method, url, headers, forwarded_body = state.forwarded[0]
    assert (forwarded_method, url, forwarded_body) == (method, f"https://lumen.test/v1/{path}", body)
    assert headers["x-auth-token"] == "caller-native-token"
    assert headers["x-project-id"] == "project-a"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/admin/mcp-registry/install-featured",
        "x/%2E%2E/admin/mcp-registry/install-featured",
        "%2E/admin/mcp-registry/install-featured",
        "mcp-connections//12",
        "mcp-connections/12/",
        "mcp-settings%3Fuser_id=other-user",
        "mcp-settings%23fragment",
        "x%5Cadmin/mcp-registry/install-featured",
    ],
)
async def test_noncanonical_paths_never_reach_native_authorization_or_transport(catalog_proxy, path):
    state, client = catalog_proxy
    response = await client.post(f"/api/v1/chat/{path}")

    assert response.status_code == 400
    assert response.json() == {"detail": "Non-canonical Lumen API path"}
    assert_private(response)
    assert state.membership_reads == []
    assert state.admin_reads == []
    assert state.endpoint_reads == []
    assert state.forwarded == []


def test_new_mcp_mutations_have_structural_audit_prefixes():
    from app.main import _resource_for_path

    for path, resource_id in (
        ("admin/mcp-registry/install-featured", "install-featured"),
        ("mcp-connections/12", "12"),
        ("domains/domain-a/mcp-connections/12", "domain-a"),
    ):
        assert _resource_for_path(f"/api/v1/chat/{path}") == ("chat_mcp_connection", resource_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "mcp-settings",
        "mcp-connections/12",
        "domains/domain-a/mcp-connections/12/activation",
        "mcp-servers/12/oauth",
        "admin/mcp-registry/install-featured",
        "admin/mcp-servers/12",
        "admin/mcp-connections/12",
    ],
)
async def test_every_mcp_namespace_is_private_before_authentication(catalog_proxy, path):
    state, client = catalog_proxy
    state.auth_error = 401
    response = await client.get(f"/api/v1/chat/{path}")

    assert response.status_code == 401
    assert_private(response)
    assert state.forwarded == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 403, 404, 405, 503])
async def test_native_catalog_errors_keep_status_body_and_private_policy(catalog_proxy, status):
    state, client = catalog_proxy
    state.status = status
    state.response_body = b'{"detail":"Native MCP request rejected"}'
    response = await client.put("/api/v1/chat/mcp-connections/12", json={"is_active": True})

    assert response.status_code == status
    assert response.content == state.response_body
    assert_private(response)
    assert state.forwarded[0][0] == "PUT"
