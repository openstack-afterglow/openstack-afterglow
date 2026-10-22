"""Domain isolation through real auth routes/JWT/Redis Lua, synthetic Keystone I/O.

No live directory, provider, email transport, cloud grant or production data is used.
"""

from __future__ import annotations

import json
import time
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import openstack.connection
import pytest
import requests
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from keystoneauth1 import access as ks_access
from keystoneauth1 import session as ks_session
from keystoneauth1.exceptions.http import Unauthorized
from keystoneauth1.identity.access import AccessInfoPlugin
from requests.adapters import BaseAdapter
from starlette.requests import Request

from app.api import deps
from app.api.identity import auth
from app.main import app
from app.services import account_spaces, domain_auth, jwt_service, keystone, nova, session_store
from app.services.domain_auth import require_password as real_require_password
from app.services.domain_auth import require_provider as real_require_provider
from app.services.native_operation import NativeOperation


@pytest.fixture
async def domain_client(monkeypatch, auth_directory):
    monkeypatch.setenv("TOKEN_IP_BINDING_MODE", "off")
    state = auth_directory
    state.users.update(
        {
            uid: {
                "id": uid,
                "name": uid,
                "domain_id": "accounts",
                "enabled": True,
                "email": "real@allowed.test",
                "default_project_id": "foreign",
            }
            for uid in ("user", "manager", "signup")
        }
    )
    state.projects.update(
        {
            "own": {"id": "own", "name": "Own", "domain_id": "tenant-a", "enabled": True, "description": ""},
            "second": {"id": "second", "name": "Second", "domain_id": "tenant-a", "enabled": True, "description": ""},
            "admission": {"id": "admission", "name": "Admission", "domain_id": "tenant-a", "enabled": True},
            "foreign": {
                "id": "foreign",
                "name": "Foreign",
                "domain_id": "tenant-b",
                "enabled": True,
                "description": "",
            },
        }
    )
    state.assignments = [
        {"user": {"id": "manager"}, "role": {"id": "manager-role"}, "scope": {"domain": {"id": "tenant-a"}}}
    ]
    state.grants = {"user": ["foreign", "own", "second"], "manager": ["admission"], "signup": []}
    state.password_enabled = True
    state.policy_calls = []

    async def load_policy(domain_id, **kwargs):
        return domain_auth.LoginPolicy(
            domain_id=domain_id, password_enabled=state.password_enabled, allowed_email_domains=("allowed.test",)
        )

    async def policy(domain_id, email):
        state.policy_calls.append((domain_id, email))
        return await real_require_password(domain_id, email)

    monkeypatch.setattr(domain_auth, "get_policy", load_policy)
    monkeypatch.setattr(domain_auth, "require_password", policy)
    monkeypatch.setattr(
        keystone,
        "get_settings",
        lambda: SimpleNamespace(
            os_auth_url="https://keystone.test/v3",
            os_username="service-admin",
            os_user_domain_name="Default",
            ssl_verify=True,
            os_interface="internal",
            os_region_name="RegionOne",
        ),
    )

    def access(uid, pid=""):
        return SimpleNamespace(
            user_id=uid,
            username=uid,
            project_id=pid,
            project_name=state.projects[pid]["name"] if pid else "",
            auth_token=f"native:{uid}:{pid}",
            expires=None,
            role_names=["member"] if pid else ["manager"],
            user_domain_id=state.users[uid]["domain_id"],
            project_domain_id=state.projects[pid]["domain_id"] if pid else None,
        )

    class Password:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_access(self, session):
            if self.kwargs["password"] != "valid" or self.kwargs.get("user_domain_id") != "accounts":
                raise Unauthorized()
            return access(self.kwargs["username"])

    class Token:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_access(self, session):
            _, uid, _ = self.kwargs["token"].split(":")
            pid = self.kwargs.get("project_id", "")
            if pid and pid not in state.grants[uid]:
                raise Unauthorized()
            return access(uid, pid)

    monkeypatch.setattr(keystone.v3, "Password", Password)
    monkeypatch.setattr(keystone.v3, "Token", Token)
    monkeypatch.setattr(
        "keystoneclient.v3.client.Client",
        lambda **kwargs: SimpleNamespace(
            projects=SimpleNamespace(
                list=lambda user: [SimpleNamespace(**state.projects[pid]) for pid in state.grants[user]]
            )
        ),
    )
    monkeypatch.setattr(auth, "_prewarm_dashboard", AsyncMock())
    monkeypatch.setattr(auth, "record_project_access", AsyncMock())
    monkeypatch.setattr(auth.activity_svc, "record", AsyncMock())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, state


async def login(client, username="user", *, select_organization=True):
    """Open a fresh personal session, then explicitly select legacy test scope."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "valid"},
    )
    assert response.status_code == 200, response.text
    tokens = response.json()
    if not tokens["is_system_admin"]:
        assert (tokens["identity_domain_id"], tokens["domain_id"], tokens["project_id"]) == (
            "accounts",
            "personal",
            "personal-" + username,
        )
    if select_organization and tokens["project_id"]:
        selected = await client.post(
            "/api/v1/auth/token/workspace",
            json={"domain_id": "tenant-a", "project_id": "own" if username == "user" else ""},
            headers={"Authorization": f"Bearer {tokens['token']}"},
        )
        assert selected.status_code == 200, selected.text
        return selected.json()
    return tokens


async def native_project_login(client, username="user", project_id="own"):
    """Establish an actual native-project source, not an admin logical target."""
    tokens = await login(client, username, select_organization=False)
    assert tokens["is_system_admin"] is True
    _, stored = await session(tokens)
    async with NativeOperation() as operation:
        data = await operation.run(keystone.validate_token, stored["keystone_token"], project_id, operation=operation)
        assert (data["user_id"], data["identity_domain_id"], data["project_id"]) == (
            username,
            "accounts",
            project_id,
        )
        return (
            await auth._build_token_response(
                keystone_token=data["token"],
                project_id=data["project_id"],
                project_name=data["project_name"],
                user_id=data["user_id"],
                username=data["username"],
                roles=data["roles"],
                is_system_admin=data["is_system_admin"],
                domain_id=data["domain_id"],
                domain_name=data["domain_name"],
                is_domain_manager=data["is_domain_manager"],
                identity_domain_id=data["identity_domain_id"],
                identity_domain_name=data["identity_domain_name"],
                operation=operation,
            )
        ).model_dump()


def native_service_automation(monkeypatch, state, user_id):
    """Keep a genuine service principal projectless, never exempt human admins."""
    state.roles.append({"id": "service-role", "name": "service", "domain_id": None})
    state.assignments.append(
        {"user": {"id": user_id}, "role": {"id": "service-role"}, "scope": {"system": {"all": True}}}
    )
    provision_human = account_spaces.ensure_personal_project

    async def qualified_provision(uid, *, operation=None):
        # The shared fixture substitutes provisioning SQL only. Restore its real
        # native identity/role qualification for this explicit automation case.
        async with NativeOperation() as qualification:
            catalog = await qualification.run(qualification.catalog)
            await account_spaces._human(uid, (None, qualification.ks, catalog))
        return await provision_human(uid, operation=operation)

    monkeypatch.setattr(account_spaces, "ensure_personal_project", qualified_provision)


async def legacy_projectless_login(client, state, username):
    """Existing organization-home sessions remain valid through native federation."""
    state.users[username]["domain_id"] = "tenant-a"
    tokens = (
        await auth.issue_federated_login(
            boundary_request("/api/v1/auth/providers/callback"),
            BackgroundTasks(),
            unscoped_token=f"native:{username}:",
            user_id=username,
            username=username,
            domain_id="tenant-a",
            domain_name="Tenant A",
            provider_id="provider",
            provider_revision=7,
            provider_kind="oidc",
            login_email="real@allowed.test",
        )
    ).model_dump()
    selected = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-a", "project_id": ""},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert selected.status_code == 200, selected.text
    return selected.json()


async def session(tokens):
    jti = jwt_service.verify_refresh(tokens["refresh_token"])["jti"]
    return jti, await session_store.get_session(jti)


@pytest.mark.asyncio
async def test_login_canonicalizes_domain_filters_foreign_default_and_reads_actual_email(domain_client):
    client, state = domain_client
    tokens = await login(client, select_organization=False)
    assert (tokens["domain_id"], tokens["domain_name"], tokens["project_id"], tokens["default_project_id"]) == (
        "personal",
        "Personal",
        "personal-user",
        "personal-user",
    )
    assert tokens["identity_domain_id"] == state.users["user"]["domain_id"] == "accounts"
    assert state.users["user"]["default_project_id"] == "foreign"
    assert state.grants["user"] == ["foreign", "own", "second", "personal-user"]
    assert state.policy_calls and set(state.policy_calls) == {("accounts", "real@allowed.test")}
    assert (await session(tokens))[1]["domain_id"] == "personal"
    assert tokens["is_domain_manager"] is False
    assert tokens["can_write"] is True
    rejected = await client.post(
        "/api/v1/auth/login",
        json={"username": "user", "password": "valid", "domain_name": "Tenant A", "project_name": "Foreign"},
    )
    assert rejected.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["manager", "signup"])
async def test_users_without_organization_projects_get_personal_primary(domain_client, username):
    client, state = domain_client
    state.grants[username] = []
    tokens = await login(client, username, select_organization=False)
    assert tokens["project_id"] == "personal-" + username
    assert tokens["can_write"] is True
    assert tokens["is_domain_manager"] is False
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['token']}"})
    assert me.status_code == 200
    assert me.json()["domain_id"] == "personal"
    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rotated.status_code == 200
    assert (rotated.json()["project_id"], rotated.json()["domain_id"]) == ("personal-" + username, "personal")
    selected = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-a", "project_id": ""},
        headers={"Authorization": f"Bearer {rotated.json()['token']}"},
    )
    assert selected.status_code == 403
    assert state.grants[username] == ["personal-" + username]
    assert (await session(rotated.json()))[1]["domain_id"] == "personal"


@pytest.mark.asyncio
async def test_same_domain_rotation_preserves_context_foreign_rescope_and_header_denied(domain_client):
    client, _ = domain_client
    tokens = await login(client)
    old_jti, old_session = await session(tokens)
    headers = {"Authorization": f"Bearer {tokens['token']}"}
    for route, body in [("/api/v1/auth/token/project", {"project_id": "foreign"})]:
        denied = await client.post(route, json=body, headers=headers)
        assert denied.status_code == 403
    denied = await client.get("/api/v1/auth/me", headers={**headers, "X-Project-Id": "foreign"})
    assert denied.status_code == 403
    allowed = await client.post("/api/v1/auth/token/project", json={"project_id": "second"}, headers=headers)
    assert allowed.status_code == 200
    new_jti, new_session = await session(allowed.json())
    assert new_jti != old_jti
    assert await session_store.get_session(old_jti) is None
    assert new_session["domain_id"] == old_session["domain_id"] == "tenant-a"
    assert new_session["started_at"] == old_session["started_at"]
    refresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": allowed.json()["refresh_token"]})
    assert refresh.status_code == 200
    assert refresh.json()["domain_id"] == "tenant-a"
    assert refresh.json()["project_id"] == "second"


@pytest.mark.asyncio
async def test_legacy_session_missing_domain_fails_closed_without_default(domain_client, _fake_redis_global):
    client, _ = domain_client
    tokens = await login(client)
    jti, stored = await session(tokens)
    del stored["domain_id"]
    await _fake_redis_global.setex(session_store._key(jti), 3600, json.dumps(stored))
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['token']}"})
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert [me.status_code, refreshed.status_code] == [401, 401]
    assert "domain_id" not in (await session_store.get_session(jti))


@pytest.mark.asyncio
async def test_disabled_domain_denies_cached_access_and_refresh(domain_client):
    client, state = domain_client
    tokens = await login(client)
    before = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['token']}"})
    assert before.status_code == 200
    state.domains["tenant-a"]["enabled"] = False
    from app.services.domain_scope import invalidate_authority

    await invalidate_authority()
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['token']}"})
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert [me.status_code, refreshed.status_code] == [403, 403]


@pytest.mark.asyncio
async def test_password_policy_applies_to_new_login_and_refresh(domain_client):
    client, state = domain_client
    tokens = await login(client)
    state.password_enabled = False
    denied = await client.post("/api/v1/auth/login", json={"username": "user", "password": "valid"})
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert [denied.status_code, refreshed.status_code] == [403, 403]
    assert denied.json()["code"] == refreshed.json()["code"] == "password_disabled"
    assert await session_store.get_session((await session(tokens))[0]) is not None


@pytest.mark.asyncio
async def test_atomic_rotation_refuses_domain_change_and_preserves_original(auth_directory):
    exp = int(time.time()) + 600
    await session_store.store_session("original", "native", "p", "user", exp, domain_id="tenant-a")
    rotated = await session_store.store_session(
        "replacement",
        "other-native",
        "p",
        "user",
        exp,
        domain_id="tenant-b",
        previous_jti="original",
        timeout_seconds=3600,
    )
    assert rotated is False
    assert (await session_store.get_session("original"))["domain_id"] == "tenant-a"
    assert await session_store.get_session("replacement") is None


@pytest.mark.asyncio
async def test_native_package_path_keeps_original_subject_and_rejects_project_substitution(domain_client, monkeypatch):
    client, _ = domain_client
    tokens = await login(client)
    _, stored = await session(tokens)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/packages",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "scheme": "http",
            "server": ("test", 80),
        }
    )
    info = await deps._resolve_jwt_token_info(request, tokens["token"], "own", preserve_original=True)
    assert info["token"] == "native:user:own"
    assert info["session_token"] == stored["keystone_token"]
    assert info["domain_id"] == "tenant-a"
    assert info["is_system_admin"] is False
    with pytest.raises(HTTPException) as exc:
        await deps._resolve_jwt_token_info(request, tokens["token"], "foreign", preserve_original=True)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_cache_invalidation_preserves_durable_role_visibility(auth_directory, _fake_redis_global):
    from app.services.domain_scope import invalidate_authority

    await _fake_redis_global.set("afterglow:identity:role-visibility", "durable-settings")
    for key in ("domain-context:user:default", "system-admin:user", "project-domain:default:p"):
        await _fake_redis_global.set("afterglow:identity:" + key, "stale")
    await invalidate_authority()
    assert await _fake_redis_global.get("afterglow:identity:role-visibility") == "durable-settings"
    assert await _fake_redis_global.keys("afterglow:identity:domain-context:*") == []
    assert await _fake_redis_global.keys("afterglow:identity:system-admin:*") == []
    assert await _fake_redis_global.keys("afterglow:identity:project-domain:*") == []


@pytest.mark.asyncio
async def test_actual_keystone_email_not_username_controls_password_policy(domain_client):
    client, state = domain_client
    state.users["user"]["email"] = "real@allowed.test.attacker.test"
    denied = await client.post("/api/v1/auth/login", json={"username": "user", "password": "valid"})
    assert denied.status_code == 403
    assert denied.json()["code"] == "email_domain_not_allowed"
    assert "token" not in denied.json()


@pytest.mark.asyncio
async def test_provider_bound_session_rotates_canonical_context_and_obeys_revocation(domain_client, monkeypatch):
    client, state = domain_client
    provider = SimpleNamespace(
        id="provider",
        enabled=True,
        revision=7,
        kind="oidc",
        client_id="client",
        client_secret_ciphertext="encrypted",
        _organization=None,
    )

    async def load_provider(domain_id, provider_id):
        return provider if domain_id == "tenant-a" and provider_id == provider.id else None

    monkeypatch.setattr(domain_auth, "_load_provider", load_provider)
    monkeypatch.setattr(domain_auth, "require_provider", real_require_provider)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/providers/callback",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "scheme": "http",
            "server": ("test", 80),
        }
    )
    tokens = (
        await auth.issue_federated_login(
            request,
            BackgroundTasks(),
            unscoped_token="native:user:",
            user_id="user",
            username="upstream-name",
            domain_id="tenant-a",
            domain_name="Tenant A",
            provider_id="provider",
            provider_revision=7,
            provider_kind="oidc",
            login_email="real@allowed.test",
        )
    ).model_dump()
    _, original = await session(tokens)
    assert original["domain_id"] == "personal" and original["identity_domain_id"] == "accounts"
    assert original["provider_id"] == "provider"
    assert original["provider_revision"] == 7
    assert original["provider_domain_id"] == "tenant-a"
    assert original["login_email"] == "real@allowed.test"
    assert original["auth_method"] == "federated"
    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rotated.status_code == 200
    _, replacement = await session(rotated.json())
    for key in (
        "domain_id",
        "provider_id",
        "provider_revision",
        "provider_domain_id",
        "login_email",
        "auth_method",
        "started_at",
        "origin_ip",
        "origin_fp",
    ):
        assert replacement[key] == original[key]
    provider.enabled = False
    denied = await client.post("/api/v1/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]})
    assert denied.status_code == 403
    assert denied.json()["code"] == "provider_disabled"
    provider.enabled = True
    provider.revision = 8
    changed = await client.post("/api/v1/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]})
    assert changed.status_code == 403
    assert changed.json()["code"] == "provider_changed"


@pytest.mark.asyncio
@pytest.mark.parametrize("change,status", [("grant", 403), ("user", 401), ("domain", 403)])
@pytest.mark.parametrize("select_organization", [False, True], ids=["native-project", "logical-workspace"])
async def test_live_admin_gate_rejects_out_of_band_native_revocation(
    domain_client, change, status, select_organization
):
    client, state = domain_client
    state.assignments.append({"user": {"id": "user"}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}})
    # Exercise both the native admin guard and the earlier logical-workspace
    # fence without relying on cached authority or application invalidation.
    tokens = await login(client) if select_organization else await native_project_login(client)
    assert tokens["is_system_admin"] is True
    protected = FastAPI()
    mutations = []

    @protected.post("/api/v1/admin/privileged")
    async def mutate(identity=Depends(deps.require_admin)):
        mutations.append(identity["user_id"])
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=protected), base_url="http://test") as admin:
        headers = {"Authorization": f"Bearer {tokens['token']}"}
        assert (await admin.post("/api/v1/admin/privileged", headers=headers)).status_code == 200
        # Native change deliberately bypasses Afterglow invalidation/session revoke.
        if change == "grant":
            state.assignments[:] = [row for row in state.assignments if "system" not in row["scope"]]
        elif change == "user":
            state.users["user"]["enabled"] = False
        else:
            state.domains["accounts"]["enabled"] = False
        denied = await admin.post("/api/v1/admin/privileged", headers=headers)
    assert denied.status_code == status
    if change == "grant":
        assert denied.json()["detail"]["code"] == "system_admin_required"
    assert mutations == ["user"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [ConnectionError("directory unavailable"), HTTPException(503, "role graph unavailable")]
)
async def test_login_native_outage_does_not_consume_password_failure_allowance(domain_client, monkeypatch, failure):
    client, _ = domain_client
    failures = AsyncMock()
    monkeypatch.setattr(auth.login_guard, "record_failure", failures)

    def unavailable(**kwargs):
        raise failure

    monkeypatch.setattr(keystone, "authenticate", unavailable)
    result = await client.post("/api/v1/auth/login", json={"username": "user", "password": "valid"})
    assert result.status_code == 503
    failures.assert_not_awaited()


@pytest.mark.asyncio
async def test_actual_password_rejection_consumes_failure_allowance(domain_client, monkeypatch):
    client, _ = domain_client
    failures = AsyncMock()
    monkeypatch.setattr(auth.login_guard, "record_failure", failures)
    result = await client.post("/api/v1/auth/login", json={"username": "user", "password": "incorrect"})
    assert result.status_code == 401
    failures.assert_awaited_once_with("user", "accounts")


def boundary_request(path):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "client": ("127.0.0.1", 1),
            "scheme": "http",
            "server": ("test", 80),
        }
    )


class ProjectPolicyProvider(BaseAdapter):
    """Real SDK transport with project-only Nova admin policy and private ACLs."""

    def __init__(self):
        super().__init__()
        self.claims = {}
        self.requests = []
        self.provider_operations = []
        self.authentications = []
        self.closed = []

    def connect(self, *, project="executor-project", roles=("admin",), system=False, admin_project=True, mutate=None):
        token = {
            "methods": ["password"],
            "expires_at": "2036-10-22T00:00:00Z",
            "issued_at": "2026-10-22T00:00:00Z",
            "user": {"id": "configured-executor", "name": "executor", "domain": {"id": "Default"}},
            "roles": [{"id": "role-" + role, "name": role} for role in roles],
            "is_admin_project": admin_project,
            "catalog": [
                {
                    "id": "compute",
                    "name": "nova",
                    "type": "compute",
                    "endpoints": [
                        {
                            "id": "nova",
                            "interface": "public",
                            "region": "RegionOne",
                            "url": "http://nova.scope.test/v2.1",
                        }
                    ],
                }
            ],
        }
        if project is not None:
            token["project"] = {"id": project, "name": "executor", "domain": {"id": "Default"}}
        if system:
            token["system"] = {"all": True}
        if mutate:
            mutate(token)
        native_token = f"native-executor-{len(self.claims)}"
        self.claims[native_token] = deepcopy(token)
        provider = self

        class Auth(AccessInfoPlugin):
            def get_access(self, session, **kwargs):
                provider.authentications.append(native_token)
                return super().get_access(session, **kwargs)

        http = requests.Session()
        http.mount("http://", self)
        connection = openstack.connection.Connection(
            session=ks_session.Session(
                auth=Auth(ks_access.create(body={"token": token}, auth_token=native_token)), session=http
            ),
            compute_api_version="2",
        )
        close = connection.close

        def close_once():
            self.closed.append(native_token)
            close()

        connection.close = close_once
        return connection

    def send(self, request, **kwargs):
        url = urlsplit(request.url)
        path = url.path.rstrip("/")
        query = parse_qs(url.query)
        self.requests.append((request.method, path, query))
        body, status = {}, 404
        if request.method == "GET" and path in ("", "/v2.1"):
            version = {
                "id": "v2.1",
                "status": "CURRENT",
                "version": "2.96",
                "min_version": "2.1",
                "links": [{"rel": "self", "href": "http://nova.scope.test/v2.1/"}],
            }
            body, status = ({"versions": [version]} if not path else {"version": version}), 200
        elif request.method == "GET":
            token = self.claims.get(request.headers.get("X-Auth-Token"), {})
            project = token.get("project", {}).get("id")
            admin = any(role["name"].lower() == "admin" for role in token.get("roles", []))
            valid_project = bool(project) and "system" not in token
            self.provider_operations.append((path, query, deepcopy(token)))
            if not valid_project or (
                path.endswith("/servers/detail") and (not admin or token.get("is_admin_project") is not True)
            ):
                status, body = 403, {"forbidden": {"message": "project-scoped admin policy required"}}
            elif path == "/v2.1/servers/detail":
                all_tenants = query.get("all_tenants", [""])[0].lower() in {"true", "1"}
                status, body = (
                    200,
                    {
                        "servers": [{"id": "foreign-server", "name": "Foreign", "tenant_id": "other"}]
                        if all_tenants
                        else []
                    },
                )
            elif path == "/v2.1/flavors/detail":
                flavors = [
                    {"id": "public", "name": "Public", "os-flavor-access:is_public": True},
                    {"id": "personal", "name": "Personal", "os-flavor-access:is_public": False},
                    {"id": "foreign", "name": "Foreign", "os-flavor-access:is_public": False},
                ]
                if not admin:
                    flavors = [
                        flavor
                        for flavor in flavors
                        if flavor["id"] == "public" or (flavor["id"] == "personal" and project == "personal-manager")
                    ]
                status, body = 200, {"flavors": flavors}
            elif path.endswith("/os-flavor-access"):
                if not admin:
                    status, body = 403, {"forbidden": {"message": "member cannot inspect private ACLs"}}
                else:
                    flavor_id = path.split("/")[-2]
                    owner = "personal-manager" if flavor_id == "personal" else "other"
                    status, body = 200, {"flavor_access": [{"flavor_id": flavor_id, "tenant_id": owner}]}
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(body).encode()
        response.headers["Content-Type"] = "application/json"
        response.url, response.request = request.url, request
        return response

    def close(self):
        pass


@pytest.fixture
def project_policy_provider():
    return ProjectPolicyProvider()


@pytest.mark.asyncio
async def test_projectless_admin_system_connection_is_admin_path_only(domain_client, monkeypatch):
    client, state = domain_client
    state.assignments.append(
        {"user": {"id": "manager"}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
    )
    native_service_automation(monkeypatch, state, "manager")
    tokens = await login(client, "manager")
    created = []
    closed = []
    access = SimpleNamespace(
        system_scoped=True, user_id="manager", user_domain_id="accounts", auth_token="caller-native-system-token"
    )
    connection = SimpleNamespace(
        session=SimpleNamespace(auth=SimpleNamespace(get_access=lambda session: access)),
        close=lambda: closed.append(True),
    )

    def create(token, project, **kwargs):
        created.append((token, project, kwargs))
        return connection

    monkeypatch.setattr(keystone, "get_openstack_connection", create)
    request = boundary_request("/api/v1/admin/domains")
    info = await deps._resolve_jwt_token_info(request, tokens["token"], None)
    generator = deps.get_os_conn(request, info)
    conn = await anext(generator)
    assert created == [(info["token"], "", {"system_scope": True})]
    assert conn._afterglow_token == "caller-native-system-token"
    assert conn._afterglow_domain_id == "tenant-a"
    assert conn._afterglow_authenticated_project_id == ""
    await generator.aclose()
    assert closed == [True]
    tenant = deps.get_os_conn(boundary_request("/api/v1/flavors"), info)
    with pytest.raises(HTTPException) as exc:
        await anext(tenant)
    assert exc.value.status_code == 403
    assert len(created) == 1


@pytest.mark.asyncio
async def test_personal_admin_uses_explicit_project_executor_without_changing_workspace(
    domain_client, monkeypatch, project_policy_provider
):
    client, state = domain_client
    state.assignments.append(
        {"user": {"id": "manager"}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
    )
    tokens = await login(client, "manager", select_organization=False)
    provider = project_policy_provider
    executor = provider.connect()
    created = []
    monkeypatch.setattr(keystone, "get_admin_project_connection", lambda: executor)

    def create(token, project, **kwargs):
        created.append((token, project, kwargs))
        return provider.connect(project=project, roles=("member",), admin_project=False)

    monkeypatch.setattr(keystone, "get_openstack_connection", create)
    request = boundary_request("/api/v1/admin/all-instances")
    info = await deps._resolve_jwt_token_info(request, tokens["token"], None)
    before = deepcopy(info)
    native_before = deepcopy((state.users, state.projects, state.assignments, state.grants))
    assert info["project_id"] == "personal-manager" and info["domain_id"] == "personal"
    generator = deps.get_admin_os_conn(await deps.require_admin(info))
    connection = await anext(generator)
    assert provider.authentications  # Authenticate before the first Nova operation.
    assert provider.provider_operations == []
    assert connection._afterglow_authenticated_project_id == "executor-project"
    assert connection._afterglow_project_id == info["project_id"]
    assert connection._afterglow_user_id == "manager"
    assert connection._afterglow_identity_domain_id == "accounts"
    assert connection._afterglow_domain_id == "personal"
    assert connection._afterglow_compute_admin is True
    assert connection._afterglow_token == "native-executor-0"
    assert [server.id for server in connection.compute.servers(all_projects=True)] == ["foreign-server"]
    assert nova.project_flavor_visibility(connection) == {"public": True, "personal": False}
    assert any(path.endswith("/os-flavor-access") for path, _, _ in provider.provider_operations)
    await generator.aclose()
    assert provider.closed == ["native-executor-0"]
    assert created == []

    for path in ("/api/v1/flavors", "/api/v1/admin/application-credentials/context", "/api/v1/admin/domains"):
        consumer = deps.get_os_conn(boundary_request(path), info)
        consumer_connection = await anext(consumer)
        assert created[-1] == (info["token"], info["connection_project_id"], {})
        assert consumer_connection._afterglow_compute_admin is False
        assert consumer_connection._afterglow_authenticated_project_id == info["connection_project_id"]
        acl_before = sum(path.endswith("/os-flavor-access") for path, _, _ in provider.provider_operations)
        assert nova.project_flavor_visibility(consumer_connection) == {"public": True, "personal": False}
        assert sum(path.endswith("/os-flavor-access") for path, _, _ in provider.provider_operations) == acl_before
        await consumer.aclose()
    assert len(provider.closed) == 4
    for key in ("project_id", "connection_project_id", "domain_id", "identity_domain_id", "token", "user_id"):
        assert info[key] == before[key]
    assert (state.users, state.projects, state.assignments, state.grants) == native_before


@pytest.mark.asyncio
async def test_personal_member_transport_is_not_promoted_by_admin_path(
    domain_client, monkeypatch, project_policy_provider
):
    """Also runs against the old dependency: stock project-only policy rejects its system token."""
    client, state = domain_client
    state.assignments.append(
        {"user": {"id": "manager"}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
    )
    tokens = await login(client, "manager", select_organization=False)
    provider = project_policy_provider

    def create(token, project, **kwargs):
        system = kwargs.get("system_scope", False)
        return provider.connect(
            project=None if system else project,
            roles=("admin",) if system else ("member",),
            system=system,
            admin_project=False,
            mutate=lambda data: data.update(user={"id": "manager", "domain": {"id": "accounts"}}),
        )

    monkeypatch.setattr(keystone, "get_openstack_connection", create)
    request = boundary_request("/api/v1/admin/domains")
    info = await deps._resolve_jwt_token_info(request, tokens["token"], None)
    generator = deps.get_os_conn(request, info)
    connection = await anext(generator)
    try:
        assert nova.project_flavor_visibility(connection) == {"public": True, "personal": False}
        assert connection._afterglow_authenticated_project_id == tokens["project_id"]
        assert connection._afterglow_compute_admin is False
        assert not any(path.endswith("/os-flavor-access") for path, _, _ in provider.provider_operations)
    finally:
        await generator.aclose()
    assert len(provider.closed) == 1


def provider_admin_application():
    """Do not override caller authentication or live authority in these regressions."""
    protected = FastAPI()

    @protected.get("/api/v1/admin/provider-inventory")
    async def inventory(connection=Depends(deps.get_admin_os_conn)):
        return {"ids": [server.id for server in connection.compute.servers(all_projects=True)]}

    return protected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "native",
    [
        {"project": None, "system": True},
        {"system": True},
        {"project": None},
        {"project": ""},
        {"roles": ("member",)},
        {"admin_project": False},
        {"admin_project": "true"},
        {"admin_project": 1},
        {"mutate": lambda token: token.pop("is_admin_project")},
        {"mutate": lambda token: token.update(project={"id": 42})},
    ],
    ids=[
        "system",
        "ambiguous-scopes",
        "unscoped",
        "empty-project",
        "member",
        "not-admin-project",
        "string-admin-flag",
        "numeric-admin-flag",
        "missing-admin-flag",
        "malformed-project",
    ],
)
async def test_admin_provider_rejects_invalid_native_executor_before_inventory(
    domain_client, monkeypatch, project_policy_provider, native
):
    client, state = domain_client
    state.assignments.append(
        {"user": {"id": "manager"}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
    )
    tokens = await login(client, "manager", select_organization=False)
    provider = project_policy_provider
    connection = provider.connect(**native)
    monkeypatch.setattr(keystone, "get_admin_project_connection", lambda: connection)
    async with AsyncClient(transport=ASGITransport(app=provider_admin_application()), base_url="http://test") as admin:
        result = await admin.get(
            "/api/v1/admin/provider-inventory", headers={"Authorization": f"Bearer {tokens['token']}"}
        )
    assert result.status_code == 503, result.text
    assert result.json()["detail"] == "Native administrator project scope is invalid"
    assert provider.authentications
    assert provider.provider_operations == []
    assert len(provider.closed) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["ordinary", "revoked"])
async def test_admin_provider_requires_live_caller_authority_before_executor_auth(
    domain_client, monkeypatch, project_policy_provider, kind
):
    client, state = domain_client
    if kind == "revoked":
        state.assignments.append(
            {"user": {"id": "manager"}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
        )
    tokens = await login(client, "manager", select_organization=False)
    provider = project_policy_provider
    created = []

    def executor():
        created.append(True)
        return provider.connect()

    monkeypatch.setattr(keystone, "get_admin_project_connection", executor)
    async with AsyncClient(transport=ASGITransport(app=provider_admin_application()), base_url="http://test") as admin:
        headers = {"Authorization": f"Bearer {tokens['token']}"}
        if kind == "revoked":
            allowed = await admin.get("/api/v1/admin/provider-inventory", headers=headers)
            assert allowed.status_code == 200, allowed.text
            assert allowed.json() == {"ids": ["foreign-server"]}
            state.assignments[:] = [row for row in state.assignments if "system" not in row["scope"]]
        before = (len(created), len(provider.authentications), len(provider.provider_operations), len(provider.closed))
        denied = await admin.get("/api/v1/admin/provider-inventory", headers=headers)
    assert denied.status_code == 403, denied.text
    assert (
        len(created),
        len(provider.authentications),
        len(provider.provider_operations),
        len(provider.closed),
    ) == before
    assert len(created) == (1 if kind == "revoked" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["authentication", "operation"])
async def test_admin_provider_closes_executor_once_on_native_failure(
    domain_client, monkeypatch, project_policy_provider, failure
):
    client, state = domain_client
    state.assignments.append(
        {"user": {"id": "manager"}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
    )
    tokens = await login(client, "manager", select_organization=False)
    provider = project_policy_provider
    connection = provider.connect()
    if failure == "authentication":

        def unavailable(_session):
            raise Unauthorized()

        monkeypatch.setattr(connection.session.auth, "get_access", unavailable)
    else:
        # The dependency is valid; provider policy failure must still finalize it.
        provider.claims["native-executor-0"]["roles"] = [{"id": "member", "name": "member"}]
    monkeypatch.setattr(keystone, "get_admin_project_connection", lambda: connection)
    transport = ASGITransport(app=provider_admin_application(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as admin:
        result = await admin.get(
            "/api/v1/admin/provider-inventory", headers={"Authorization": f"Bearer {tokens['token']}"}
        )
    assert result.status_code == (503 if failure == "authentication" else 500)
    if failure == "authentication":
        assert result.json()["detail"] == "Administrator provider connection is unavailable"
        assert provider.provider_operations == []
    else:
        assert len(provider.provider_operations) == 1
    assert provider.closed == ["native-executor-0"]


@pytest.mark.asyncio
async def test_projectless_non_admin_never_receives_system_connection(domain_client, monkeypatch):
    client, state = domain_client
    tokens = await legacy_projectless_login(client, state, "signup")
    created = []
    monkeypatch.setattr(keystone, "get_openstack_connection", lambda *args, **kwargs: created.append(args))
    request = boundary_request("/api/v1/admin/domains")
    info = await deps._resolve_jwt_token_info(request, tokens["token"], None)
    with pytest.raises(HTTPException) as exc:
        await anext(deps.get_os_conn(request, info))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "system_admin_required"
    assert created == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,status", [("invalid", 401), ("unavailable", 503), ("revoked", 403)])
async def test_projectless_admin_system_exchange_fails_closed(domain_client, monkeypatch, kind, status):
    client, state = domain_client
    state.assignments.append(
        {"user": {"id": "manager"}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
    )
    native_service_automation(monkeypatch, state, "manager")
    tokens = await login(client, "manager")
    closed = []

    def exchange(session):
        if kind == "revoked":
            state.assignments = []
        if kind == "unavailable":
            raise ConnectionError("native exchange unavailable")
        raise Unauthorized()

    connection = SimpleNamespace(
        session=SimpleNamespace(auth=SimpleNamespace(get_access=exchange)), close=lambda: closed.append(True)
    )
    monkeypatch.setattr(keystone, "get_openstack_connection", lambda *args, **kwargs: connection)
    request = boundary_request("/api/v1/admin/domains")
    info = await deps._resolve_jwt_token_info(request, tokens["token"], None)
    with pytest.raises(HTTPException) as exc:
        await anext(deps.get_os_conn(request, info))
    assert exc.value.status_code == status
    if kind == "revoked":
        assert exc.value.detail["code"] == "system_admin_required"
    assert closed == [True]


@pytest.mark.asyncio
async def test_explicit_domain_switch_preserves_identity_and_blocks_implicit_cross_domain(domain_client):
    client, state = domain_client
    tokens = await login(client)
    assert tokens["identity_domain_id"] == "accounts"
    assert {d["id"] for d in tokens["available_domains"]} == {"personal", "tenant-a", "tenant-b"}
    old_jti, original = await session(tokens)
    switched = await client.post(
        "/api/v1/auth/token/domain",
        json={"domain_id": "tenant-b"},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert switched.status_code == 200, switched.text
    replacement = switched.json()
    assert (replacement["identity_domain_id"], replacement["domain_id"], replacement["project_id"]) == (
        "accounts",
        "tenant-b",
        "foreign",
    )
    _, stored = await session(replacement)
    assert stored["identity_domain_id"] == original["identity_domain_id"] == "accounts"
    assert stored["started_at"] == original["started_at"]
    assert await session_store.get_session(old_jti) is None
    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401
    headers = {"Authorization": f"Bearer {replacement['token']}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert (me.json()["identity_domain_id"], me.json()["domain_id"]) == ("accounts", "tenant-b")
    implicit = await client.post("/api/v1/auth/token/project", json={"project_id": "own"}, headers=headers)
    assert implicit.status_code == 403
    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": replacement["refresh_token"]})
    assert rotated.status_code == 200
    assert (rotated.json()["identity_domain_id"], rotated.json()["domain_id"]) == ("accounts", "tenant-b")
    assert state.policy_calls and set(state.policy_calls) == {("accounts", "real@allowed.test")}


@pytest.mark.asyncio
async def test_domain_switch_requires_live_membership_without_consuming_session(domain_client):
    client, state = domain_client
    tokens = await login(client)
    state.grants["user"].remove("foreign")
    denied = await client.post(
        "/api/v1/auth/token/domain",
        json={"domain_id": "tenant-b"},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert denied.status_code == 403
    assert (await session(tokens))[1]["domain_id"] == "tenant-a"


@pytest.mark.asyncio
async def test_disabled_organization_creation_denies_ordinary_creation(domain_client, monkeypatch):
    client, state = domain_client
    settings = auth.get_settings().model_copy(deep=True)
    settings.auth.organization_creation_enabled = False
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    tokens = await login(client)
    assert tokens["can_create_domain"] is False
    before = set(state.domains)
    denied = await client.post(
        "/api/v1/auth/domains",
        json={"name": "Unapproved"},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert denied.status_code == 403
    assert set(state.domains) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["native", "redis"])
async def test_domain_switch_outage_preserves_original_session(domain_client, monkeypatch, failure):
    client, _ = domain_client
    tokens = await login(client)
    old_jti, original = await session(tokens)
    if failure == "native":
        validate = keystone.validate_token

        def unavailable(token, project_id="", *, operation=None):
            if project_id == "foreign":
                raise ConnectionError("synthetic target authority outage")
            return validate(token, project_id, operation=operation)

        monkeypatch.setattr(keystone, "validate_token", unavailable)
    else:
        monkeypatch.setattr(
            session_store, "store_session", AsyncMock(side_effect=ConnectionError("synthetic Redis outage"))
        )
    response = await client.post(
        "/api/v1/auth/token/domain",
        json={"domain_id": "tenant-b"},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert response.status_code == 503
    assert "no-store" in response.headers["cache-control"]
    stored = await session_store.get_session(old_jti)
    for key in ("user_id", "identity_domain_id", "domain_id", "project_id", "started_at", "origin_ip", "origin_fp"):
        assert stored[key] == original[key]


@pytest.mark.asyncio
async def test_workspace_browsing_never_switches_session_or_changes_membership(domain_client):
    client, state = domain_client
    tokens = await login(client)
    old_jti, original = await session(tokens)
    grants = {uid: list(ids) for uid, ids in state.grants.items()}
    response = await client.get(
        "/api/v1/auth/workspaces?domain_id=tenant-b",
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["domain"]["id"] == "tenant-b"
    assert [project["id"] for project in body["projects"]] == ["foreign"]
    assert body["can_create_project"] is False
    assert "no-store" in response.headers["cache-control"]
    stored = await session_store.get_session(old_jti)
    for key in ("identity_domain_id", "domain_id", "project_id", "started_at"):
        assert stored[key] == original[key]
    assert state.grants == grants
    state.grants["user"].remove("foreign")
    revoked = await client.get(
        "/api/v1/auth/workspaces?domain_id=tenant-b",
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert revoked.status_code == 403
    assert await session_store.get_session(old_jti) is not None


@pytest.mark.asyncio
async def test_workspace_selection_commits_exact_project_and_preserves_identity_lifetime(domain_client):
    client, state = domain_client
    state.projects["foreign-second"] = {
        "id": "foreign-second",
        "name": "Foreign second",
        "domain_id": "tenant-b",
        "enabled": True,
        "description": "",
    }
    state.grants["user"].append("foreign-second")
    tokens = await login(client)
    old_jti, original = await session(tokens)
    response = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-b", "project_id": "foreign-second"},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["identity_domain_id"], result["domain_id"], result["project_id"]) == (
        "accounts",
        "tenant-b",
        "foreign-second",
    )
    _, stored = await session(result)
    assert stored["started_at"] == original["started_at"]
    assert stored["origin_ip"] == original["origin_ip"]
    assert stored["auth_method"] == original["auth_method"]
    assert await session_store.get_session(old_jti) is None
    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("project_id", ["own", "", "foreign"])
async def test_workspace_selection_rejects_foreign_empty_or_revoked_project_without_rotation(domain_client, project_id):
    client, state = domain_client
    tokens = await login(client)
    old_jti, original = await session(tokens)
    if project_id == "foreign":
        state.grants["user"].remove("foreign")
    response = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-b", "project_id": project_id},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert response.status_code == 403, response.text
    stored = await session_store.get_session(old_jti)
    assert stored["domain_id"] == original["domain_id"] == "tenant-a"
    assert stored["project_id"] == original["project_id"]
    assert stored["started_at"] == original["started_at"]


@pytest.mark.asyncio
async def test_workspace_selection_can_remain_projectless_only_without_accessible_projects(domain_client):
    client, state = domain_client
    tokens = await legacy_projectless_login(client, state, "signup")
    response = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-a", "project_id": ""},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert response.status_code == 200, response.text
    assert (response.json()["identity_domain_id"], response.json()["domain_id"], response.json()["project_id"]) == (
        "tenant-a",
        "tenant-a",
        "",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/auth/refresh", "/api/v1/auth/token/project"])
@pytest.mark.parametrize("change,status", [("project", 403), ("identity", 401), ("home", 403)])
async def test_rotation_publication_rechecks_native_authority(domain_client, monkeypatch, path, change, status):
    client, state = domain_client
    tokens = await login(client)
    old_jti, original = await session(tokens)
    headers = {"Authorization": f"Bearer {tokens['token']}"}
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    validate = keystone.validate_token
    enforce_policy = auth._enforce_session_policy
    target = "own" if path.endswith("refresh") else "second"

    def disabled_after_exchange(token, project_id="", *, operation=None):
        result = validate(token, project_id, operation=operation)
        if project_id == target:
            state.projects[target] = {**state.projects[target], "enabled": False}
        return result

    async def disabled_during_policy(*args):
        await enforce_policy(*args)
        if change == "identity":
            state.users["user"] = {**state.users["user"], "enabled": False}
        else:
            state.domains["accounts"] = {**state.domains["accounts"], "enabled": False}

    if change == "project":
        monkeypatch.setattr(keystone, "validate_token", disabled_after_exchange)
    else:
        monkeypatch.setattr(auth, "_enforce_session_policy", disabled_during_policy)
    body = {"refresh_token": tokens["refresh_token"]} if path.endswith("refresh") else {"project_id": target}
    response = await client.post(path, json=body, headers=headers)
    assert response.status_code == status, response.text
    assert "token" not in response.json()
    stored = await session_store.get_session(old_jti)
    assert stored["started_at"] == original["started_at"]
    assert stored["project_id"] == original["project_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/chat/admin/providers",
        "/api/v1/k3s/clusters",
        "/api/v1/waygate/servers",
        "/api/v1/palimpsest/hub/layers",
        "/api/v1/projects/current/permissions",
    ],
)
async def test_service_system_admin_target_needs_no_project_membership(domain_client, path):
    client, state = domain_client
    state.assignments.append(
        {
            "user": {"id": "user"},
            "role": {"id": "admin-role"},
            "scope": {"system": {"all": True}},
        }
    )
    state.grants["user"] = ["own"]
    tokens = await native_project_login(client)
    info = await deps._resolve_jwt_token_info(boundary_request(path), tokens["token"], "second")
    assert (info["user_id"], info["project_id"], info["connection_project_id"]) == ("user", "second", "own")
    assert info["_live_system_admin"] is True
    assert info["token"] == "native:user:own"
    assert (await session(tokens))[1]["project_id"] == "own"


@pytest.mark.asyncio
async def test_service_cached_admin_cannot_outlive_current_system_assignment(domain_client):
    client, state = domain_client
    grant = {"user": {"id": "user"}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
    state.assignments.append(grant)
    state.grants["user"] = ["own"]
    tokens = await login(client)
    request = boundary_request("/api/v1/waygate/servers")
    await deps._resolve_jwt_token_info(request, tokens["token"], "second")
    state.assignments.remove(grant)
    with pytest.raises(HTTPException) as denied:
        await deps._resolve_jwt_token_info(request, tokens["token"], "second")
    assert denied.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("target,disabled,status", [("foreign", False, 403), ("second", True, 403)])
async def test_service_system_admin_target_preserves_domain_and_enablement(domain_client, target, disabled, status):
    client, state = domain_client
    state.assignments.append(
        {
            "user": {"id": "user"},
            "role": {"id": "admin-role"},
            "scope": {"system": {"all": True}},
        }
    )
    tokens = await login(client)
    if disabled:
        state.projects[target]["enabled"] = False
    with pytest.raises(HTTPException) as denied:
        await deps._resolve_jwt_token_info(boundary_request("/api/v1/k3s/clusters"), tokens["token"], target)
    assert denied.value.status_code == status


@pytest.mark.asyncio
async def test_package_system_admin_preserves_original_caller_with_independent_target(domain_client, monkeypatch):
    client, state = domain_client
    state.assignments.append(
        {
            "user": {"id": "user"},
            "role": {"id": "admin-role"},
            "scope": {"system": {"all": True}},
        }
    )
    state.grants["user"] = ["own"]
    tokens = await native_project_login(client)
    _, original = await session(tokens)
    info = await deps._resolve_jwt_token_info(
        boundary_request("/api/v1/palimpsest/packages"),
        tokens["token"],
        "second",
        preserve_original=True,
    )
    assert info["token"] == "native:user:own"
    assert info["session_token"] == (await session(tokens))[1]["keystone_token"] == "native:user:"
    assert original["keystone_token"] == "native:user:own"
    assert (info["project_id"], info["connection_project_id"]) == ("second", "own")
    assert info["_live_system_admin"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["project", "projectless"])
async def test_system_admin_user_workspace_rejects_nonmember_targets_without_rotating_source(
    domain_client, source, monkeypatch
):
    client, state = domain_client
    user_id = "user" if source == "project" else "manager"
    state.grants[user_id] = ["own"] if source == "project" else ["admission"]
    state.assignments.append(
        {"user": {"id": user_id}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
    )
    if source == "projectless":
        native_service_automation(monkeypatch, state, user_id)
    tokens = await native_project_login(client, user_id) if source == "project" else await login(client, user_id)
    headers = {"Authorization": f"Bearer {tokens['token']}"}
    _, original = await session(tokens)
    directory = await client.get("/api/v1/auth/workspaces?domain_id=tenant-b", headers=headers)
    assert directory.status_code == 403, directory.text
    selected = await client.post(
        "/api/v1/auth/token/workspace",
        headers=headers,
        json={"domain_id": "tenant-b", "project_id": "foreign"},
    )
    assert selected.status_code == 403, selected.text
    assert "token" not in selected.json()
    retained = await session_store.get_session(jwt_service.verify_refresh(tokens["refresh_token"])["jti"])
    for key in ("project_id", "target_project_id", "domain_id", "identity_domain_id", "family_id", "started_at"):
        assert retained.get(key) == original.get(key)
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["project_id"] == tokens["project_id"]


@pytest.mark.asyncio
async def test_system_admin_project_loss_keeps_context_and_refresh(domain_client):
    client, state = domain_client
    grant = {"user": {"id": "user"}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
    state.assignments.append(grant)
    tokens = await login(client)
    selected = await client.post(
        "/api/v1/auth/token/workspace",
        headers={"Authorization": f"Bearer {tokens['token']}"},
        json={"domain_id": "tenant-b", "project_id": "foreign"},
    )
    assert selected.status_code == 200, selected.text
    tokens = selected.json()
    _, original = await session(tokens)
    state.grants["user"] = []

    current = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['token']}", "X-Project-Id": "foreign"},
    )
    assert current.status_code == 200, current.text
    assert current.json()["project_id"] == "" and current.json()["is_system_admin"] is True
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    tokens = refreshed.json()
    _, stored = await session(tokens)
    assert tokens["project_id"] == "" and stored.get("target_project_id") is None
    assert jwt_service.verify_access(tokens["token"])["project_id"] == stored["project_id"] == ""
    assert stored["family_id"] == original["family_id"]
    assert stored["started_at"] == original["started_at"]
    assert state.grants["user"] == []
    info = await deps._resolve_jwt_token_info(boundary_request("/api/v1/waygate/servers"), tokens["token"], "foreign")
    assert info["connection_project_id"] == "" and info["_live_system_admin"] is True
    with pytest.raises(HTTPException) as core_denied:
        await deps._resolve_jwt_token_info(boundary_request("/api/v1/networks"), tokens["token"], "foreign")
    assert core_denied.value.status_code == 403
    state.assignments.remove(grant)
    with pytest.raises(HTTPException) as revoked:
        await deps._resolve_jwt_token_info(boundary_request("/api/v1/waygate/servers"), tokens["token"], "foreign")
    assert revoked.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("stored_empty", [False, True])
async def test_package_admin_empty_target_never_falls_back_to_native_source(domain_client, stored_empty):
    client, state = domain_client
    state.assignments.append(
        {
            "user": {"id": "user"},
            "role": {"id": "admin-role"},
            "scope": {"system": {"all": True}},
        }
    )
    tokens = await login(client)
    if stored_empty:
        state.grants["user"] = [pid for pid in state.grants["user"] if pid != tokens["project_id"]]
        response = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert response.status_code == 200, response.text
        tokens = response.json()
    with pytest.raises(HTTPException) as denied:
        await deps._resolve_jwt_token_info(
            boundary_request("/api/v1/palimpsest/packages"),
            tokens["token"],
            None if stored_empty else "",
            preserve_original=True,
        )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_member_workspace_refresh_rechecks_selected_domain_email_policy(domain_client, monkeypatch):
    client, state = domain_client
    state.assignments.append(
        {
            "user": {"id": "user"},
            "role": {"id": "admin-role"},
            "scope": {"system": {"all": True}},
        }
    )
    state.grants["user"] = ["own", "foreign"]
    tokens = await login(client)
    selected = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-b", "project_id": "foreign"},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert selected.status_code == 200, selected.text
    tokens = selected.json()

    async def tightened(domain_id, **kwargs):
        return domain_auth.LoginPolicy(
            domain_id=domain_id,
            password_enabled=True,
            allowed_email_domains=("new-policy.test",) if domain_id == "tenant-b" else ("allowed.test",),
        )

    monkeypatch.setattr(domain_auth, "get_policy", tightened)
    result = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert result.status_code == 403, result.text
    assert "token" not in result.json()
    assert (await session(tokens))[1]["project_id"] == "foreign"


@pytest.mark.asyncio
async def test_admin_member_workspace_can_revoke_only_own_individual_sessions(domain_client):
    client, state = domain_client
    state.assignments.append(
        {
            "user": {"id": "user"},
            "role": {"id": "admin-role"},
            "scope": {"system": {"all": True}},
        }
    )
    state.grants["user"] = ["own", "foreign"]
    own_other = await login(client)
    foreign_user = await login(client, "manager", select_organization=False)
    own_jti, _ = await session(own_other)
    foreign_jti, _ = await session(foreign_user)
    tokens = await login(client)
    selected = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-b", "project_id": "foreign"},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert selected.status_code == 200, selected.text
    tokens = selected.json()
    headers = {"Authorization": f"Bearer {tokens['token']}"}
    own = await client.delete(f"/api/v1/auth/sessions/{own_jti}", headers=headers)
    assert own.status_code == 200, own.text
    assert await session_store.get_session(own_jti) is None
    denied = await client.delete(f"/api/v1/auth/sessions/{foreign_jti}", headers=headers)
    assert denied.status_code == 404, denied.text
    assert await session_store.get_session(foreign_jti) is not None
    assert (await session(tokens))[1]["project_id"] == "foreign"


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", ["user", "real@allowed.test"])
async def test_domainless_password_opens_personal_once_before_workspace_selection(
    domain_client, monkeypatch, identifier
):
    from unittest.mock import Mock

    client, state = domain_client
    state.users["manager"]["email"] = "manager@allowed.test"
    state.users["signup"]["email"] = "signup@allowed.test"
    authenticate = Mock(wraps=keystone.authenticate)
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    result = await client.post("/api/v1/auth/login", json={"username": identifier, "password": "valid"})
    assert result.status_code == 200, result.text
    data = result.json()
    assert (data["user_id"], data["identity_domain_id"], data["domain_id"], data["project_id"]) == (
        "user",
        "accounts",
        "personal",
        "personal-user",
    )
    authenticate.assert_called_once()
    assert authenticate.call_args.kwargs["username"] == "user"
    assert authenticate.call_args.kwargs["domain_name"] == "accounts"
    assert authenticate.call_args.kwargs["unscoped_only"] is True
    assert (await session(data))[1]["identity_domain_id"] == "accounts"
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert refreshed.status_code == 200
    assert (refreshed.json()["identity_domain_id"], refreshed.json()["domain_id"]) == ("accounts", "personal")
    selected = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-b", "project_id": "foreign"},
        headers={"Authorization": f"Bearer {refreshed.json()['token']}"},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["domain_id"] == "tenant-b" and selected.json()["identity_domain_id"] == "accounts"
    assert authenticate.call_count == 1


@pytest.mark.asyncio
async def test_foreign_membership_is_checked_only_at_explicit_workspace_selection(domain_client, monkeypatch):
    from unittest.mock import Mock

    client, state = domain_client
    state.grants["user"] = ["own"]
    authenticate = Mock(wraps=keystone.authenticate)
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    tokens = await login(client, select_organization=False)
    assert (tokens["identity_domain_id"], tokens["domain_id"]) == ("accounts", "personal")
    denied = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-b", "project_id": "foreign"},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert denied.status_code == 403
    authenticate.assert_called_once()
    assert (await session(tokens))[1]["domain_id"] == "personal"


@pytest.mark.asyncio
@pytest.mark.parametrize("collision", ["username", "email", "email_shaped_name"])
@pytest.mark.parametrize("enabled", [True, False])
async def test_accounts_password_identity_ambiguity_never_tries_passwords(
    domain_client, monkeypatch, collision, enabled
):
    client, state = domain_client
    state.users["manager"]["email"] = "manager@allowed.test"
    state.users["signup"]["email"] = "signup@allowed.test"
    identifier = "user" if collision == "username" else "real@allowed.test"
    state.users["another-user"] = {
        "id": "another-user",
        "name": identifier if collision != "email" else "another-user",
        "domain_id": "accounts",
        "enabled": enabled,
        "email": identifier if collision == "email" else "other@allowed.test",
        "default_project_id": "",
    }
    authenticate = AsyncMock()
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    result = await client.post("/api/v1/auth/login", json={"username": identifier, "password": "valid"})
    assert result.status_code == 409 and result.json()["code"] == "account_ambiguous"
    authenticate.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("collision", ["username", "email", "email_shaped_name"])
@pytest.mark.parametrize("enabled", [True, False])
async def test_other_domain_duplicates_do_not_block_accounts_password_login(
    domain_client, monkeypatch, collision, enabled
):
    from unittest.mock import Mock

    client, state = domain_client
    state.users["manager"]["email"] = "manager@allowed.test"
    state.users["signup"]["email"] = "signup@allowed.test"
    identifier = "user" if collision == "username" else "real@allowed.test"
    state.users["legacy-duplicate"] = {
        "id": "legacy-duplicate",
        "name": identifier if collision != "email" else "legacy-duplicate",
        "domain_id": "default",
        "enabled": enabled,
        "email": identifier if collision == "email" else "other@allowed.test",
    }
    users = keystone._get_admin_ks_client().users
    inventory = Mock(wraps=users.list)
    authenticate = Mock(wraps=keystone.authenticate)
    monkeypatch.setattr(users, "list", inventory)
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    response = await client.post("/api/v1/auth/login", json={"username": identifier, "password": "valid"})
    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == "user" and response.json()["identity_domain_id"] == "accounts"
    authenticate.assert_called_once()
    assert authenticate.call_args.kwargs["domain_name"] == "accounts"
    assert authenticate.call_args.kwargs["username"] == "user"
    inventory.assert_called_once_with(domain="accounts")


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", ["user", "real@allowed.test"])
@pytest.mark.parametrize("home", ["default", "tenant-a", "tenant-b"])
async def test_outside_accounts_password_login_never_attempts_native_credentials(
    domain_client, monkeypatch, identifier, home
):
    from unittest.mock import Mock

    client, state = domain_client
    state.users["user"]["domain_id"] = home
    state.users["manager"]["email"] = "manager@allowed.test"
    state.users["signup"]["email"] = "signup@allowed.test"
    authenticate, failures, guard = Mock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    monkeypatch.setattr(auth.login_guard, "record_failure", failures)
    monkeypatch.setattr(auth.login_guard, "check_locked", guard)
    response = await client.post("/api/v1/auth/login", json={"username": identifier, "password": "valid"})
    assert response.status_code == 401, response.text
    assert "token" not in response.json() and "refresh_token" not in response.json()
    authenticate.assert_not_called()
    guard.assert_not_awaited()
    failures.assert_not_awaited()


@pytest.mark.asyncio
async def test_accounts_inventory_wrong_home_readback_never_attempts_password(domain_client, monkeypatch):
    from unittest.mock import Mock

    client, state = domain_client
    state.users["user"]["domain_id"] = "tenant-a"
    native = keystone._get_admin_ks_client()

    def collection(url):
        assert url == "/users?domain_id=accounts"
        return None, {"users": [{"id": "user", "domain_id": "accounts"}], "links": {"next": None}}

    monkeypatch.setattr(native.users, "client", SimpleNamespace(get=collection), raising=False)
    authenticate = Mock()
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    response = await client.post("/api/v1/auth/login", json={"username": "user", "password": "valid"})
    assert response.status_code == 503, response.text
    authenticate.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boundary,status",
    [
        ("user", 401),
        ("home", 503),
        ("home_missing", 503),
        ("home_name", 503),
        ("home_alias", 401),
        ("method", 403),
        ("inventory", 503),
        ("policy", 503),
    ],
)
async def test_domainless_password_requires_exact_enabled_home_before_native_proof(
    domain_client, monkeypatch, boundary, status
):
    client, state = domain_client
    if boundary == "user":
        state.users["user"]["enabled"] = False
    elif boundary == "home":
        state.domains["accounts"]["enabled"] = False
    elif boundary == "home_missing":
        del state.domains["accounts"]
    elif boundary == "home_name":
        state.domains["accounts"]["name"] = "accounts"
    elif boundary == "home_alias":
        state.users["user"]["domain_id"] = "Accounts"
    elif boundary == "method":
        state.password_enabled = False
    elif boundary == "inventory":
        monkeypatch.setattr(
            keystone._get_admin_ks_client().users,
            "client",
            SimpleNamespace(get=lambda url: (None, {"users": [], "links": {"next": "/users?marker=more"}})),
            raising=False,
        )
    else:
        monkeypatch.setattr(
            domain_auth, "get_policy", AsyncMock(side_effect=domain_auth.DomainAuthUnavailable("Unavailable"))
        )
    authenticate, failures = AsyncMock(), AsyncMock()
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    monkeypatch.setattr(auth.login_guard, "record_failure", failures)
    denied = await client.post("/api/v1/auth/login", json={"username": "user", "password": "valid"})
    assert denied.status_code == status, denied.text
    assert "token" not in denied.json()
    authenticate.assert_not_called()
    failures.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary,status", [("user", 401), ("home", 403), ("moved_home", 403)])
async def test_password_policy_io_cannot_publish_stale_home_authority(domain_client, monkeypatch, boundary, status):
    client, state = domain_client
    policy = domain_auth.require_password

    async def revoke_during_policy(*args):
        await policy(*args)
        if boundary == "home":
            state.domains["accounts"] = {**state.domains["accounts"], "enabled": False}
        else:
            change = {"enabled": False} if boundary == "user" else {"domain_id": "tenant-b"}
            state.users["user"] = {**state.users["user"], **change}

    monkeypatch.setattr(domain_auth, "require_password", revoke_during_policy)
    publish = AsyncMock(wraps=auth._build_token_response)
    monkeypatch.setattr(auth, "_build_token_response", publish)
    denied = await client.post("/api/v1/auth/login", json={"username": "user", "password": "valid"})
    assert denied.status_code == status, denied.text
    publish.assert_not_awaited()


@pytest.fixture
def provider_login_env(domain_client, monkeypatch):
    client, state = domain_client
    provider = SimpleNamespace(
        id="provider",
        enabled=True,
        revision=7,
        kind="oidc",
        client_id="client",
        client_secret_ciphertext="encrypted",
        _organization=None,
    )
    policy_origins = []

    async def load_provider(did, pid):
        policy_origins.append(did)
        return provider if did == "tenant-b" and pid == provider.id else None

    settings = domain_auth.get_settings().model_copy(
        update={"frontend_base_url": "http://test", "public_api_base": "http://test"}
    )
    monkeypatch.setattr(domain_auth, "get_settings", lambda: settings)
    monkeypatch.setattr(domain_auth, "_load_provider", load_provider)
    monkeypatch.setattr(domain_auth, "require_provider", real_require_provider)
    # External proof and provisioning are synthetic. Native subject / origin,
    # personal ownership, policy, JWT and Redis session paths remain real.
    complete = AsyncMock(
        return_value=domain_auth.FederatedLogin(
            unscoped_token="native:user:",
            user_id="user",
            username="external-name",
            domain_id="tenant-b",
            domain_name="Tenant B",
            provider_id="provider",
            provider_revision=7,
            provider_kind="oidc",
            login_email="real@allowed.test",
        )
    )
    verified, revoked = AsyncMock(), AsyncMock()
    monkeypatch.setattr(domain_auth, "complete_authorization", complete)
    monkeypatch.setattr(domain_auth, "mark_provider_verified", verified)
    monkeypatch.setattr(domain_auth, "_revoke_quietly", revoked)
    return SimpleNamespace(
        client=client,
        state=state,
        provider=provider,
        policy_origins=policy_origins,
        complete=complete,
        verified=verified,
        revoked=revoked,
    )


async def provider_callback(env):
    return await env.client.post(
        "/api/v1/auth/providers/callback",
        json={"code": "verified-code", "state": "s" * 32},
        headers={"Origin": "http://test", "Sec-Fetch-Site": "same-origin"},
    )


@pytest.mark.asyncio
async def test_provider_callback_opens_personal_and_preserves_origin_through_refresh_and_selection(provider_login_env):
    env = provider_login_env
    client = env.client
    done = await provider_callback(env)
    assert done.status_code == 200, done.text
    tokens = done.json()
    assert (tokens["identity_domain_id"], tokens["domain_id"]) == ("accounts", "personal")
    assert tokens["project_id"] == "personal-user" and tokens["username"] == "user"
    env.verified.assert_awaited_once_with("tenant-b", "provider", 7)
    env.revoked.assert_not_awaited()
    original = (await session(tokens))[1]
    assert original["provider_domain_id"] == "tenant-b"
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    assert (refreshed.json()["identity_domain_id"], refreshed.json()["domain_id"]) == ("accounts", "personal")
    switched = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-b", "project_id": "foreign"},
        headers={"Authorization": f"Bearer {refreshed.json()['token']}"},
    )
    assert switched.status_code == 200, switched.text
    saved = (await session(switched.json()))[1]
    assert saved["identity_domain_id"] == "accounts" and saved["domain_id"] == "tenant-b"
    assert saved["provider_domain_id"] == "tenant-b" and saved["started_at"] == original["started_at"]
    assert env.policy_origins and set(env.policy_origins) == {"tenant-b"}
    env.provider.enabled = False
    denied = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {switched.json()['token']}"})
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_common_provider_origin_does_not_require_or_grant_workspace_membership(provider_login_env):
    env = provider_login_env
    env.state.grants["user"] = ["own", "second"]
    done = await provider_callback(env)
    assert done.status_code == 200, done.text
    tokens = done.json()
    assert (tokens["identity_domain_id"], tokens["domain_id"], tokens["project_id"]) == (
        "accounts",
        "personal",
        "personal-user",
    )
    assert env.state.grants["user"] == ["own", "second", "personal-user"]
    assert (await session(tokens))[1]["provider_domain_id"] == "tenant-b"
    denied = await env.client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-b", "project_id": "foreign"},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert denied.status_code == 403
    assert (await session(tokens))[1]["domain_id"] == "personal"


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["home", "origin", "provider", "revision", "home_email"])
async def test_provider_callback_refuses_invalid_home_or_origin_without_publication(
    provider_login_env, monkeypatch, boundary
):
    env = provider_login_env
    if boundary in {"home", "origin"}:
        env.state.domains["accounts" if boundary == "home" else "tenant-b"]["enabled"] = False
    elif boundary == "provider":
        env.provider.enabled = False
    elif boundary == "revision":
        env.provider.revision = 8
    else:

        async def policy(did, **kwargs):
            return domain_auth.LoginPolicy(
                domain_id=did, allowed_email_domains=("home-only.test",) if did == "accounts" else ("allowed.test",)
            )

        monkeypatch.setattr(domain_auth, "get_policy", policy)
    publish = AsyncMock(wraps=auth._build_token_response)
    monkeypatch.setattr(auth, "_build_token_response", publish)
    denied = await provider_callback(env)
    assert denied.status_code == 403, denied.text
    assert "token" not in denied.json()
    publish.assert_not_awaited()
    env.verified.assert_not_awaited()
    env.revoked.assert_awaited_once_with("native:user:")


@pytest.mark.asyncio
async def test_provider_callback_rechecks_origin_availability_after_policy_io(provider_login_env, monkeypatch):
    env = provider_login_env
    enforce = auth._enforce_session_policy

    async def revoke_during_policy(*args):
        await enforce(*args)
        env.state.domains["tenant-b"]["enabled"] = False

    monkeypatch.setattr(auth, "_enforce_session_policy", revoke_during_policy)
    publish = AsyncMock(wraps=auth._build_token_response)
    monkeypatch.setattr(auth, "_build_token_response", publish)
    denied = await provider_callback(env)
    assert denied.status_code == 403, denied.text
    publish.assert_not_awaited()
    env.verified.assert_not_awaited()
    env.revoked.assert_awaited_once_with("native:user:")


@pytest.mark.asyncio
async def test_provider_session_without_origin_requires_reauthentication(domain_client):
    client, state = domain_client
    with pytest.raises(HTTPException) as caught:
        await auth._enforce_session_policy(
            {
                "auth_method": "federated",
                "provider_id": "provider",
                "provider_revision": 7,
                "login_email": "real@allowed.test",
                "identity_domain_id": "tenant-a",
            },
            {"identity_domain_id": "tenant-a", "domain_id": "tenant-a", "email": "real@allowed.test"},
        )
    assert caught.value.status_code == 401


@pytest.mark.asyncio
async def test_password_aliases_share_canonical_home_account_lock(domain_client, monkeypatch):
    from unittest.mock import Mock

    from app.config import get_settings
    from app.services import login_guard

    client, state = domain_client
    state.users["manager"]["email"] = "manager@allowed.test"
    state.users["signup"]["email"] = "signup@allowed.test"
    settings = get_settings().model_copy(update={"login_max_attempts": 2, "login_lockout_seconds": 60})
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    authenticate = Mock(wraps=keystone.authenticate)
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    for identifier in ("real@allowed.test", "user"):
        result = await client.post("/api/v1/auth/login", json={"username": identifier, "password": "incorrect"})
        assert result.status_code == 401
    locked = await client.post("/api/v1/auth/login", json={"username": "user", "password": "valid"})
    assert locked.status_code == 429 and authenticate.call_count == 2
    redis = await session_store._get_redis()
    assert int(await redis.get(login_guard._fail_key("user", "accounts"))) == 2
    assert await redis.get(login_guard._fail_key("real@allowed.test", "tenant-b")) is None


@pytest.mark.asyncio
async def test_provider_switch_back_to_identity_home_enforces_destination_email_policy(domain_client, monkeypatch):
    from unittest.mock import AsyncMock

    async def policy(did, **kwargs):
        return domain_auth.LoginPolicy(domain_id=did, allowed_email_domains=("home-only.test",))

    monkeypatch.setattr(domain_auth, "get_policy", policy)
    require_provider = AsyncMock(return_value=None)
    monkeypatch.setattr(domain_auth, "require_provider", require_provider)
    with pytest.raises(domain_auth.DomainAuthDenied) as caught:
        await auth._enforce_session_policy(
            {
                "auth_method": "federated",
                "provider_id": "provider",
                "provider_revision": 7,
                "provider_domain_id": "tenant-b",
                "identity_domain_id": "tenant-a",
                "login_email": "real@allowed.test",
            },
            {"identity_domain_id": "tenant-a", "domain_id": "tenant-a", "email": "real@allowed.test"},
        )
    assert caught.value.code == "email_domain_not_allowed"
    require_provider.assert_awaited_once_with("tenant-b", "provider", 7, "real@allowed.test")
