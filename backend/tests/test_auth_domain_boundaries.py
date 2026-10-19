"""Domain isolation through real auth routes/JWT/Redis Lua, synthetic Keystone I/O.

No live directory, provider, email transport, cloud grant or production data is used.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from keystoneauth1.exceptions.http import Unauthorized
from starlette.requests import Request

from app.api import deps
from app.api.identity import auth
from app.main import app
from app.services import domain_auth, jwt_service, keystone, session_store
from app.services.domain_auth import require_password as real_require_password
from app.services.domain_auth import require_provider as real_require_provider


@pytest.fixture
async def domain_client(monkeypatch, auth_directory):
    monkeypatch.setenv("TOKEN_IP_BINDING_MODE", "off")
    state = auth_directory
    state.users.update(
        {
            uid: {
                "id": uid,
                "name": uid,
                "domain_id": "tenant-a",
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
    state.grants = {"user": ["foreign", "own", "second"], "manager": [], "signup": []}
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
            os_auth_url="https://keystone.test/v3", ssl_verify=True, os_interface="internal", os_region_name="RegionOne"
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
            user_domain_id="tenant-a",
            project_domain_id=state.projects[pid]["domain_id"] if pid else None,
        )

    class Password:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_access(self, session):
            if self.kwargs["password"] != "valid" or self.kwargs.get("user_domain_id") != "tenant-a":
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


async def login(client, username="user"):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "valid"},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def session(tokens):
    jti = jwt_service.verify_refresh(tokens["refresh_token"])["jti"]
    return jti, await session_store.get_session(jti)


@pytest.mark.asyncio
async def test_login_canonicalizes_domain_filters_foreign_default_and_reads_actual_email(domain_client):
    client, state = domain_client
    tokens = await login(client)
    assert (tokens["domain_id"], tokens["domain_name"], tokens["project_id"], tokens["default_project_id"]) == (
        "tenant-a",
        "Tenant A",
        "own",
        "",
    )
    assert state.policy_calls == [("tenant-a", "real@allowed.test")]
    assert (await session(tokens))[1]["domain_id"] == "tenant-a"
    assert tokens["is_domain_manager"] is False
    assert tokens["can_write"] is True
    rejected = await client.post(
        "/api/v1/auth/login",
        json={"username": "user", "password": "valid", "domain_name": "Tenant A", "project_name": "Foreign"},
    )
    assert rejected.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("username,manager", [("manager", False), ("signup", False)])
async def test_no_project_users_can_login_me_and_refresh_without_project_grants(domain_client, username, manager):
    client, state = domain_client
    tokens = await login(client, username)
    assert tokens["project_id"] == ""
    assert tokens["roles"] == []
    assert tokens["can_write"] is False
    assert tokens["is_domain_manager"] is manager
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['token']}"})
    assert me.status_code == 200
    assert me.json()["domain_id"] == "tenant-a"
    assert me.json()["roles"] == []
    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rotated.status_code == 200
    assert rotated.json()["project_id"] == ""
    assert rotated.json()["domain_id"] == "tenant-a"
    assert rotated.json()["can_write"] is False
    assert state.grants[username] == []
    info = {**me.json(), "token": (await session(rotated.json()))[1]["keystone_token"]}
    if manager:
        assert (await deps.require_domain_manager(info))["is_domain_manager"] is True
    else:
        with pytest.raises(HTTPException) as exc:
            await deps.require_domain_manager(info)
        assert exc.value.status_code == 403


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
        id="provider", enabled=True, revision=7, kind="oidc", client_id="client", client_secret_ciphertext="encrypted"
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
    assert original["domain_id"] == "tenant-a"
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
async def test_live_admin_gate_rejects_out_of_band_native_revocation(domain_client, change, status):
    client, state = domain_client
    state.assignments.append({"user": {"id": "user"}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}})
    tokens = await login(client)
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
            state.assignments = []
        elif change == "user":
            state.users["user"]["enabled"] = False
        else:
            state.domains["tenant-a"]["enabled"] = False
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
    failures.assert_awaited_once_with("user", "tenant-a")


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


@pytest.mark.asyncio
async def test_projectless_admin_system_connection_is_admin_path_only(domain_client, monkeypatch):
    client, state = domain_client
    state.assignments.append(
        {"user": {"id": "manager"}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
    )
    tokens = await login(client, "manager")
    created = []
    closed = []
    access = SimpleNamespace(
        system_scoped=True, user_id="manager", user_domain_id="tenant-a", auth_token="caller-native-system-token"
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
async def test_projectless_non_admin_never_receives_system_connection(domain_client, monkeypatch):
    client, _ = domain_client
    tokens = await login(client, "signup")
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
    assert tokens["identity_domain_id"] == "tenant-a"
    assert {d["id"] for d in tokens["available_domains"]} == {"tenant-a", "tenant-b"}
    old_jti, original = await session(tokens)
    switched = await client.post(
        "/api/v1/auth/token/domain",
        json={"domain_id": "tenant-b"},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert switched.status_code == 200, switched.text
    replacement = switched.json()
    assert (replacement["identity_domain_id"], replacement["domain_id"], replacement["project_id"]) == (
        "tenant-a",
        "tenant-b",
        "foreign",
    )
    _, stored = await session(replacement)
    assert stored["identity_domain_id"] == original["identity_domain_id"] == "tenant-a"
    assert stored["started_at"] == original["started_at"]
    assert await session_store.get_session(old_jti) is None
    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401
    headers = {"Authorization": f"Bearer {replacement['token']}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert (me.json()["identity_domain_id"], me.json()["domain_id"]) == ("tenant-a", "tenant-b")
    implicit = await client.post("/api/v1/auth/token/project", json={"project_id": "own"}, headers=headers)
    assert implicit.status_code == 403
    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": replacement["refresh_token"]})
    assert rotated.status_code == 200
    assert (rotated.json()["identity_domain_id"], rotated.json()["domain_id"]) == ("tenant-a", "tenant-b")
    assert all(did == "tenant-a" for did, _ in state.policy_calls)


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
async def test_closed_signup_mode_denies_ordinary_domain_creation(domain_client):
    client, state = domain_client
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
        "tenant-a",
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
    client, _ = domain_client
    tokens = await login(client, "signup")
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
            state.domains["tenant-a"] = {**state.domains["tenant-a"], "enabled": False}

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
    tokens = await login(client)
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
    tokens = await login(client)
    _, original = await session(tokens)
    info = await deps._resolve_jwt_token_info(
        boundary_request("/api/v1/palimpsest/packages"),
        tokens["token"],
        "second",
        preserve_original=True,
    )
    assert info["token"] == "native:user:own"
    assert info["session_token"] == original["keystone_token"]
    assert (info["project_id"], info["connection_project_id"]) == ("second", "own")
    assert info["_live_system_admin"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["project", "projectless"])
async def test_system_admin_workspace_preserves_native_source_through_refresh(domain_client, source):
    client, state = domain_client
    user_id = "user" if source == "project" else "manager"
    native_project_id = "own" if source == "project" else ""
    state.grants[user_id] = [native_project_id] if native_project_id else []
    grant = {"user": {"id": user_id}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
    state.assignments.append(grant)
    tokens = await login(client, user_id)
    headers = {"Authorization": f"Bearer {tokens['token']}"}
    directory = await client.get("/api/v1/auth/workspaces?domain_id=tenant-b", headers=headers)
    assert directory.status_code == 200, directory.text
    assert [row["id"] for row in directory.json()["projects"]] == ["foreign"]
    selected = await client.post(
        "/api/v1/auth/token/workspace",
        headers=headers,
        json={"domain_id": "tenant-b", "project_id": "foreign"},
    )
    assert selected.status_code == 200, selected.text
    tokens = selected.json()
    assert (tokens["domain_id"], tokens["identity_domain_id"], tokens["project_id"]) == (
        "tenant-b",
        "tenant-a",
        "foreign",
    )
    assert jwt_service.verify_access(tokens["token"])["project_id"] == native_project_id
    _, stored = await session(tokens)
    assert (stored["project_id"], stored["target_project_id"]) == (native_project_id, "foreign")
    current = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['token']}"})
    assert current.status_code == 200, current.text
    assert (current.json()["project_id"], current.json()["project_name"]) == ("foreign", "Foreign")
    info = await deps._resolve_jwt_token_info(
        boundary_request("/api/v1/waygate/servers"),
        tokens["token"],
        "foreign",
    )
    assert (info["project_id"], info["connection_project_id"]) == ("foreign", native_project_id)
    assert info["token"] == f"native:{user_id}:{native_project_id}"
    with pytest.raises(HTTPException) as core_denied:
        await deps._resolve_jwt_token_info(boundary_request("/api/v1/networks"), tokens["token"], "foreign")
    assert core_denied.value.status_code == 403
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    tokens = refreshed.json()
    assert tokens["project_id"] == "foreign"
    assert jwt_service.verify_access(tokens["token"])["project_id"] == native_project_id
    state.assignments.remove(grant)
    with pytest.raises(HTTPException) as revoked:
        await deps._resolve_jwt_token_info(boundary_request("/api/v1/waygate/servers"), tokens["token"], "foreign")
    assert revoked.value.status_code == 403
    revoked_refresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert revoked_refresh.status_code == 403, revoked_refresh.text
    assert (await session(tokens))[1]["target_project_id"] == "foreign"


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
    assert current.json()["project_id"] == "foreign" and current.json()["is_system_admin"] is True
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    tokens = refreshed.json()
    _, stored = await session(tokens)
    assert tokens["project_id"] == stored["target_project_id"] == "foreign"
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
        response = await client.post(
            "/api/v1/auth/token/workspace",
            json={"domain_id": "tenant-a", "project_id": ""},
            headers={"Authorization": f"Bearer {tokens['token']}"},
        )
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
async def test_logical_admin_refresh_rechecks_selected_domain_email_policy(domain_client, monkeypatch):
    client, state = domain_client
    state.assignments.append(
        {
            "user": {"id": "user"},
            "role": {"id": "admin-role"},
            "scope": {"system": {"all": True}},
        }
    )
    state.grants["user"] = ["own"]
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
    assert (await session(tokens))[1]["target_project_id"] == "foreign"


@pytest.mark.asyncio
async def test_logical_admin_can_revoke_only_own_individual_sessions(domain_client):
    client, state = domain_client
    state.assignments.append(
        {
            "user": {"id": "user"},
            "role": {"id": "admin-role"},
            "scope": {"system": {"all": True}},
        }
    )
    state.grants["user"] = ["own"]
    own_other = await login(client)
    foreign_user = await login(client, "manager")
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
    assert (await session(tokens))[1]["target_project_id"] == "foreign"


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", ["user", "real@allowed.test"])
async def test_domainless_password_opens_canonical_home_once_before_workspace_selection(
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
        "tenant-a",
        "tenant-a",
        "own",
    )
    authenticate.assert_called_once()
    assert authenticate.call_args.kwargs["username"] == "user"
    assert authenticate.call_args.kwargs["domain_name"] == "tenant-a"
    assert authenticate.call_args.kwargs["unscoped_only"] is True
    assert (await session(data))[1]["identity_domain_id"] == "tenant-a"
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["identity_domain_id"] == refreshed.json()["domain_id"] == "tenant-a"
    selected = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-b", "project_id": "foreign"},
        headers={"Authorization": f"Bearer {refreshed.json()['token']}"},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["domain_id"] == "tenant-b" and selected.json()["identity_domain_id"] == "tenant-a"
    assert authenticate.call_count == 1


@pytest.mark.asyncio
async def test_foreign_membership_is_checked_only_at_explicit_workspace_selection(domain_client, monkeypatch):
    from unittest.mock import Mock

    client, state = domain_client
    state.grants["user"] = ["own"]
    authenticate = Mock(wraps=keystone.authenticate)
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    tokens = await login(client)
    assert tokens["domain_id"] == tokens["identity_domain_id"] == "tenant-a"
    denied = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-b", "project_id": "foreign"},
        headers={"Authorization": f"Bearer {tokens['token']}"},
    )
    assert denied.status_code == 403
    authenticate.assert_called_once()
    assert (await session(tokens))[1]["domain_id"] == "tenant-a"


@pytest.mark.asyncio
@pytest.mark.parametrize("collision", ["username", "email", "email_shaped_name"])
@pytest.mark.parametrize("enabled", [True, False])
async def test_global_password_identity_ambiguity_never_tries_passwords(domain_client, monkeypatch, collision, enabled):
    client, state = domain_client
    state.users["manager"]["email"] = "manager@allowed.test"
    state.users["signup"]["email"] = "signup@allowed.test"
    identifier = "user" if collision == "username" else "real@allowed.test"
    state.users["another-user"] = {
        "id": "another-user",
        "name": identifier if collision != "email" else "another-user",
        "domain_id": "default",
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
@pytest.mark.parametrize(
    "boundary,status",
    [("user", 401), ("home", 403), ("home_alias", 403), ("method", 403), ("inventory", 503), ("policy", 503)],
)
async def test_domainless_password_requires_exact_enabled_home_before_native_proof(
    domain_client, monkeypatch, boundary, status
):
    client, state = domain_client
    if boundary == "user":
        state.users["user"]["enabled"] = False
    elif boundary == "home":
        state.domains["tenant-a"]["enabled"] = False
    elif boundary == "home_alias":
        state.users["user"]["domain_id"] = "Tenant A"
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
            state.domains["tenant-a"] = {**state.domains["tenant-a"], "enabled": False}
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
        id="provider", enabled=True, revision=7, kind="oidc", client_id="client", client_secret_ciphertext="encrypted"
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
    # Only the external proof is synthetic. The HTTP callback, native subject /
    # origin admission, home preparation, policy, JWT and Redis paths are real.
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
async def test_provider_callback_opens_home_and_preserves_origin_through_refresh_and_selection(provider_login_env):
    env = provider_login_env
    client = env.client
    done = await provider_callback(env)
    assert done.status_code == 200, done.text
    tokens = done.json()
    assert tokens["identity_domain_id"] == tokens["domain_id"] == "tenant-a"
    assert tokens["project_id"] == "own" and tokens["username"] == "user"
    env.verified.assert_awaited_once_with("tenant-b", "provider", 7)
    env.revoked.assert_not_awaited()
    original = (await session(tokens))[1]
    assert original["provider_domain_id"] == "tenant-b"
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["domain_id"] == refreshed.json()["identity_domain_id"] == "tenant-a"
    switched = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-b", "project_id": "foreign"},
        headers={"Authorization": f"Bearer {refreshed.json()['token']}"},
    )
    assert switched.status_code == 200, switched.text
    saved = (await session(switched.json()))[1]
    assert saved["identity_domain_id"] == "tenant-a" and saved["domain_id"] == "tenant-b"
    assert saved["provider_domain_id"] == "tenant-b" and saved["started_at"] == original["started_at"]
    assert env.policy_origins and set(env.policy_origins) == {"tenant-b"}
    env.provider.enabled = False
    denied = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {switched.json()['token']}"})
    assert denied.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["home", "origin", "admission", "provider", "revision", "home_email"])
async def test_provider_callback_refuses_invalid_home_or_origin_without_publication(
    provider_login_env, monkeypatch, boundary
):
    env = provider_login_env
    if boundary in {"home", "origin"}:
        env.state.domains["tenant-a" if boundary == "home" else "tenant-b"]["enabled"] = False
    elif boundary == "admission":
        env.state.grants["user"] = ["own"]
    elif boundary == "provider":
        env.provider.enabled = False
    elif boundary == "revision":
        env.provider.revision = 8
    else:

        async def policy(did, **kwargs):
            return domain_auth.LoginPolicy(
                domain_id=did, allowed_email_domains=("home-only.test",) if did == "tenant-a" else ("allowed.test",)
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
async def test_provider_callback_rechecks_origin_admission_after_policy_io(provider_login_env, monkeypatch):
    env = provider_login_env
    enforce = auth._enforce_session_policy

    async def revoke_during_policy(*args):
        await enforce(*args)
        env.state.grants["user"] = ["own"]

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
    assert int(await redis.get(login_guard._fail_key("user", "tenant-a"))) == 2
    assert await redis.get(login_guard._fail_key("real@allowed.test", "tenant-b")) is None


@pytest.mark.asyncio
async def test_provider_switch_back_to_identity_home_enforces_destination_email_policy(domain_client, monkeypatch):
    from unittest.mock import AsyncMock

    async def policy(did, **kwargs):
        return domain_auth.LoginPolicy(domain_id=did, allowed_email_domains=("home-only.test",))

    monkeypatch.setattr(domain_auth, "get_policy", policy)
    require_provider = AsyncMock()
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
