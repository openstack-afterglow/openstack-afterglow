"""Real auth routes, JWT/Redis Lua and v3 token HTTP; synthetic native directory.

No live Keystone, provider, cloud mutation or production data is exercised.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
import requests
from keystoneauth1.identity.v3.password import Password as NativePassword
from keystoneauth1.identity.v3.token import Token as NativeToken
from keystoneauth1.session import Session as NativeSession
from requests.adapters import BaseAdapter

from app.api.deps import get_os_conn
from app.main import app
from app.services import jwt_service, keystone, session_store
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_projects import domain_native as domain_native
from tests.test_domain_projects import grant
from tests.test_login_native_operation import login as fresh_login
from tests.test_login_native_operation import native_login as native_login
from tests.test_login_native_operation import provider_login


async def organization_login(client, *, method="password", monkeypatch=None):
    """Scope-revocation proofs begin with an explicit authorized organization choice."""
    response = await fresh_login(client) if method == "password" else await provider_login(client, monkeypatch)
    if response.status_code != 200:
        return response
    return await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-a", "project_id": "work-a"},
        headers=headers(response.json()),
    )


@pytest.fixture
async def login_proof(native_login, monkeypatch, ownership_journal):
    client, state = native_login
    state.revoked = set()
    state.revoked_users = set()
    state.issued = {"native:ordinary:": ("ordinary", "")}
    state.native_requests = []
    state.passwords = {uid: "valid" for uid in state.user_rows}
    state.substitute = None
    # Keystone token exchanges retain the original root's expiry; they do not
    # turn token authentication into a renewable password/IdP credential.
    state.native_expires = datetime.now(UTC) + timedelta(hours=1)
    state.raw.append(grant("manager", user="ordinary", project="default-a"))
    state.raw.append(grant("project_admin", user="ordinary", project="work-a"))

    def reply(request, status, body, token=None):
        response = requests.Response()
        response.status_code = status
        response.request = request
        response.url = request.url
        response.headers["Content-Type"] = "application/json"
        if token:
            response.headers["X-Subject-Token"] = token
        response._content = json.dumps(body).encode()
        return response

    def roles(uid, pid):
        ids = {row.role["id"] for row in state.assignments(user=uid, project=pid, effective=True)} if pid else set()
        while True:
            expanded = ids | {
                child["id"] for edge in state.edges if edge["prior_role"]["id"] in ids for child in edge["implies"]
            }
            if expanded == ids:
                return [{"id": rid, "name": rid} for rid in sorted(ids)]
            ids = expanded

    class NativeHTTP(BaseAdapter):
        def send(self, request, **kwargs):
            path = urlsplit(request.url).path.rstrip("/")
            state.native_requests.append((request.method, path))
            assert request.method == "POST" and path == "/v3/auth/tokens", (request.method, request.url)
            data = json.loads(request.body)["auth"]
            identity = data["identity"]
            if "password" in identity:
                user = identity["password"]["user"]
                uid = user.get("name") or user.get("id")
                if user.get("domain", {}).get("id") != state.user_rows[uid].domain_id:
                    return reply(request, 401, {"error": {"message": "Invalid identity domain"}})
                if user["password"] != state.passwords[uid]:
                    return reply(request, 401, {"error": {"message": "Invalid password"}})
            else:
                proof = identity["token"]["id"]
                if proof not in state.issued:
                    return reply(request, 401, {"error": {"message": "Invalid token"}})
                uid = state.issued[proof][0]
                if proof in state.revoked or uid in state.revoked_users:
                    return reply(request, 401, {"error": {"message": "Invalid token"}})
            pid = data.get("scope", {}).get("project", {}).get("id", "") if isinstance(data.get("scope"), dict) else ""
            if not state.user_rows[uid].enabled or pid and not state.assignments(user=uid, project=pid, effective=True):
                return reply(request, 401, {"error": {"message": "Access denied"}})
            wrong_subject = (state.substitute == "subject" and pid) or (
                state.substitute == "unscoped_subject" and not pid
            )
            actual_uid = "second" if wrong_subject else uid
            actual_pid = "default-a" if state.substitute == "project" and pid else pid
            wrong_home = (state.substitute == "identity" and pid) or (
                state.substitute == "unscoped_identity" and not pid
            )
            home = "tenant-b" if wrong_home else state.user_rows[actual_uid].domain_id
            token = f"native:{actual_uid}:{actual_pid}:{len(state.issued)}"
            state.issued[token] = (actual_uid, actual_pid)
            now = datetime.now(UTC)
            body = {
                "methods": ["token"],
                "issued_at": now.isoformat(),
                "expires_at": state.native_expires.isoformat(),
                "user": {"id": actual_uid, "name": actual_uid, "domain": {"id": home, "name": home}},
                "roles": roles(actual_uid, actual_pid),
                "catalog": [],
            }
            if actual_pid:
                project = state.project_rows[actual_pid]
                body["project"] = {
                    "id": actual_pid,
                    "name": project.name,
                    "domain": {
                        "id": "tenant-a" if state.substitute == "project_domain" else project.domain_id,
                        "name": project.domain_id,
                    },
                }
            return reply(request, 201, {"token": body}, token)

        def close(self):
            pass

    def native_session(**kwargs):
        transport = requests.Session()
        transport.mount("https://native.test/", NativeHTTP())
        return NativeSession(session=transport, **kwargs)

    original_revoke = state.roles.revoke

    def revoke(role, **kwargs):
        result = original_revoke(role, **kwargs)
        if kwargs.get("project"):
            state.revoked.update(
                token
                for token, (uid, pid) in state.issued.items()
                if uid == kwargs.get("user") and pid == kwargs["project"]
            )
        return result

    monkeypatch.setattr(state.roles, "revoke", revoke)
    monkeypatch.setattr(keystone.v3, "Password", NativePassword)
    monkeypatch.setattr(keystone.v3, "Token", NativeToken)
    monkeypatch.setattr(keystone.native_transport, "create_session", native_session)
    # Logout's directory boundary is synthetic, but browser/family invalidation
    # and the native credential rejected on future exchanges are real here.
    monkeypatch.setattr(keystone, "revoke_token", lambda token: state.revoked.add(token))
    state.app = app
    yield client, state


async def stored(tokens):
    jti = jwt_service.verify_refresh(tokens["refresh_token"])["jti"]
    return jti, await session_store.get_session(jti)


def headers(tokens):
    return {"Authorization": f"Bearer {tokens['token']}"}


@pytest.fixture
async def selected_domain_login_proof(login_proof):
    client, state = login_proof
    state.raw.append(grant("project_reader", user="ordinary", project="default-b"))
    state.raw.append(grant("project_admin", user="ordinary", project="work-b"))
    response = await organization_login(client)
    assert response.status_code == 200, response.text
    selected = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-b", "project_id": "work-b"},
        headers=headers(response.json()),
    )
    assert selected.status_code == 200, selected.text
    tokens = selected.json()
    assert (tokens["identity_domain_id"], tokens["domain_id"], tokens["project_id"]) == (
        "account",
        "tenant-b",
        "work-b",
    )
    return client, state, tokens


@pytest.mark.asyncio
async def test_repeated_projectless_refresh_preserves_selected_domain_and_home(selected_domain_login_proof):
    client, state, tokens = selected_domain_login_proof
    _, original = await stored(tokens)
    state.roles.revoke("project_admin", user="ordinary", project="work-b")
    grants, mutations = list(state.raw), list(state.calls)
    for _ in range(3):
        old_jti, _ = await stored(tokens)
        refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert refreshed.status_code == 200, refreshed.text
        tokens = refreshed.json()
        assert (tokens["domain_id"], tokens["identity_domain_id"], tokens["project_id"]) == (
            "tenant-b",
            "account",
            "",
        )
        assert tokens["roles"] == [] and tokens["can_write"] is False
        assert tokens["is_domain_manager"] is False and tokens["is_system_admin"] is False
        assert jwt_service.verify_access(tokens["token"])["project_id"] == ""
        assert await session_store.get_session(old_jti) is None
        _, current = await stored(tokens)
        assert (current["domain_id"], current["identity_domain_id"], current["project_id"]) == (
            "tenant-b",
            "account",
            "",
        )
        assert state.issued[current["keystone_token"]] == ("ordinary", "")
        for key in ("family_id", "started_at", "origin_ip", "origin_fp", "auth_method"):
            assert current[key] == original[key]
    assert state.raw == grants and state.calls == mutations


@pytest.mark.asyncio
@pytest.mark.parametrize("refresh_first", [False, True])
@pytest.mark.parametrize("scope", ["project", "workspace", "domain"])
async def test_selected_domain_project_loss_allows_context_browse_and_recovery(
    selected_domain_login_proof, refresh_first, scope
):
    client, state, tokens = selected_domain_login_proof
    _, original = await stored(tokens)
    state.roles.revoke("project_admin", user="ordinary", project="work-b")
    grants, mutations = list(state.raw), list(state.calls)
    if refresh_first:
        refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert refreshed.status_code == 200, refreshed.text
        tokens = refreshed.json()
    for _ in range(2):
        me = await client.get("/api/v1/auth/me", headers=headers(tokens))
        assert me.status_code == 200, me.text
        assert (me.json()["domain_id"], me.json()["identity_domain_id"], me.json()["project_id"]) == (
            "tenant-b",
            "account",
            "",
        )
        assert me.json()["roles"] == [] and me.json()["can_write"] is False
        assert me.json()["is_domain_manager"] is False and me.json()["is_system_admin"] is False
        browse = await client.get("/api/v1/auth/workspaces", headers=headers(tokens))
        assert browse.status_code == 200, browse.text
        assert browse.json()["domain"]["id"] == "tenant-b"
        assert [project["id"] for project in browse.json()["projects"]] == ["default-b"]
        assert browse.json()["default_project_id"] == "default-b"
    denied = await client.get("/api/v1/auth/me", headers={**headers(tokens), "X-Project-Id": "work-a"})
    assert denied.status_code == 403, denied.text
    denied = await client.get("/api/v1/projects/current/permissions", headers=headers(tokens))
    assert denied.status_code == 403, denied.text
    assert state.raw == grants and state.calls == mutations
    body = {"project_id": "default-b"} if scope == "project" else {"domain_id": "tenant-b"}
    if scope == "workspace":
        body["project_id"] = "default-b"
    recovered = await client.post(f"/api/v1/auth/token/{scope}", json=body, headers=headers(tokens))
    assert recovered.status_code == 200, recovered.text
    tokens = recovered.json()
    assert (tokens["domain_id"], tokens["identity_domain_id"], tokens["project_id"]) == (
        "tenant-b",
        "account",
        "default-b",
    )
    assert "project_admin" not in tokens["roles"] and tokens["can_write"] is False
    _, current = await stored(tokens)
    assert current["family_id"] == original["family_id"] and current["started_at"] == original["started_at"]
    assert state.issued[current["keystone_token"]] == ("ordinary", "")
    assert state.raw == grants and state.calls == mutations


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid,status",
    [
        ("membership", 403),
        ("domain", 403),
        ("home_domain", 403),
        ("home_changed", 403),
        ("native_home", 403),
        ("native_subject", 403),
        ("native_revoked", 401),
        ("user", 401),
    ],
)
async def test_projectless_selected_domain_still_requires_live_identity_and_membership(
    selected_domain_login_proof, invalid, status
):
    client, state, tokens = selected_domain_login_proof
    state.roles.revoke("project_admin", user="ordinary", project="work-b")
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    tokens = refreshed.json()
    if invalid == "membership":
        state.roles.revoke("project_reader", user="ordinary", project="default-b")
    elif invalid in {"domain", "home_domain"}:
        state.domain_rows["tenant-b" if invalid == "domain" else "account"].enabled = False
    elif invalid == "home_changed":
        state.user_rows["ordinary"].domain_id = "home"
    elif invalid == "native_home":
        state.substitute = "unscoped_identity"
    elif invalid == "native_subject":
        state.substitute = "unscoped_subject"
    elif invalid == "native_revoked":
        state.revoked_users.add("ordinary")
    else:
        state.user_rows["ordinary"].enabled = False
    grants, mutations = list(state.raw), list(state.calls)
    for path in ("/api/v1/auth/me", "/api/v1/auth/workspaces"):
        rejected = await client.get(path, headers=headers(tokens))
        assert rejected.status_code == status, rejected.text
    rejected = await client.post(
        "/api/v1/auth/token/workspace",
        json={"domain_id": "tenant-b", "project_id": "default-b"},
        headers=headers(tokens),
    )
    assert rejected.status_code == status, rejected.text
    rejected = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rejected.status_code == status, rejected.text
    assert state.raw == grants and state.calls == mutations


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["subject", "project", "identity", "project_domain"])
async def test_selected_context_cannot_hide_native_project_mismatch(selected_domain_login_proof, tamper):
    client, state, tokens = selected_domain_login_proof
    state.substitute = tamper
    grants, mutations = list(state.raw), list(state.calls)
    rejected = await client.get("/api/v1/auth/me", headers=headers(tokens))
    assert rejected.status_code == 403, rejected.text
    rejected = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rejected.status_code == 403, rejected.text
    assert (await stored(tokens))[1] is not None
    assert state.raw == grants and state.calls == mutations


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_login_publishes_unscoped_proof_not_project_token(login_proof, monkeypatch, method):
    client, state = login_proof
    response = await organization_login(client, method=method, monkeypatch=monkeypatch)
    assert response.status_code == 200, response.text
    _, session = await stored(response.json())
    assert session["project_id"] == "work-a"
    assert state.issued[session["keystone_token"]] == ("ordinary", "")
    assert state.native_requests


@pytest.mark.asyncio
async def test_own_project_role_edit_renews_current_roles_without_logout(login_proof):
    client, state = login_proof
    response = await organization_login(client)
    assert response.status_code == 200, response.text
    tokens = response.json()
    jti, original = await stored(tokens)
    changed = await client.put(
        "/api/v1/projects/work-a/members/ordinary/roles",
        json={"role_ids": ["project_reader"]},
        headers=headers(tokens),
    )
    assert changed.status_code == 200, changed.text
    assert {state.issued[token] for token in state.revoked} == {("ordinary", "work-a")}
    me = await client.get("/api/v1/auth/me", headers=headers(tokens))
    assert me.status_code == 200, me.text
    assert "project_admin" not in me.json()["roles"]
    assert "project_reader" in me.json()["roles"]
    assert me.json()["can_write"] is False
    _, after = await stored(tokens)
    assert state.issued[after["keystone_token"]] == ("ordinary", "")
    assert after["started_at"] == original["started_at"]
    assert after["family_id"] == original["family_id"]
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    assert await session_store.get_session(jti) is None
    _, replacement = await stored(refreshed.json())
    assert state.issued[replacement["keystone_token"]] == ("ordinary", "")
    assert replacement["started_at"] == original["started_at"]
    assert replacement["family_id"] == original["family_id"]


@pytest.mark.asyncio
async def test_project_token_revocation_is_not_native_login_revocation(login_proof):
    client, state = login_proof
    response = await organization_login(client)
    assert response.status_code == 200, response.text
    tokens = response.json()
    state.revoked.update(token for token, (_, pid) in state.issued.items() if pid)
    me = await client.get("/api/v1/auth/me", headers=headers(tokens))
    assert me.status_code == 200, me.text
    _, session = await stored(tokens)
    state.revoked.add(session["keystone_token"])
    denied = await client.get("/api/v1/auth/me", headers=headers(tokens))
    assert denied.status_code == 401
    refresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("refresh_first", [False, True])
async def test_project_loss_is_403_refresh_projectless_and_selection_still_works(login_proof, refresh_first):
    client, state = login_proof
    response = await organization_login(client)
    assert response.status_code == 200, response.text
    tokens = response.json()
    _, original = await stored(tokens)
    state.raw = [
        row
        for row in state.raw
        if row.scope.get("project", {}).get("id") != "work-a"
        and not (
            row.scope.get("project", {}).get("id") == "default-a"
            and getattr(row, "user", {}).get("id") == "ordinary"
            and row.role["id"] == "manager"
        )
    ]
    grants_after_removal = list(state.raw)
    # Domain remains allowed, but neither its manager status nor stale JWT may
    # recreate a project grant or grant access to ordinary cloud operations.
    denied = await client.get("/api/v1/projects/current/permissions", headers=headers(tokens))
    assert denied.status_code == 403, denied.text
    context = await client.get("/api/v1/auth/workspaces", headers=headers(tokens))
    assert context.status_code == 200, context.text
    selected = tokens
    if refresh_first:
        refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["project_id"] == "" and refreshed.json()["roles"] == []
        selected = refreshed.json()
    # A stale reserved reader projection is not current membership. Read/refresh
    # must reject its authority without silently provisioning or removing grants.
    assert state.raw == grants_after_removal
    switched = await client.post(
        "/api/v1/auth/token/project", json={"project_id": "default-a"}, headers=headers(selected)
    )
    assert switched.status_code == 200, switched.text
    _, current = await stored(switched.json())
    assert state.issued[current["keystone_token"]] == ("ordinary", "")
    assert current["started_at"] == original["started_at"]
    assert current["origin_ip"] == original["origin_ip"]
    assert current["family_id"] == original["family_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["subject", "project", "identity"])
async def test_native_project_result_cannot_substitute_session_identity(login_proof, tamper):
    client, state = login_proof
    response = await organization_login(client)
    assert response.status_code == 200, response.text
    tokens = response.json()
    state.substitute = tamper
    rejected = await client.get("/api/v1/auth/me", headers=headers(tokens))
    assert rejected.status_code == 403, rejected.text
    assert (await stored(tokens))[1] is not None


@pytest.mark.asyncio
async def test_broad_native_user_revocation_and_explicit_logout_are_terminal(login_proof):
    client, state = login_proof
    response = await organization_login(client)
    assert response.status_code == 200, response.text
    tokens = response.json()
    state.revoked_users.add("ordinary")
    assert (await client.get("/api/v1/auth/me", headers=headers(tokens))).status_code == 401
    state.revoked_users.clear()
    logged_out = await client.post("/api/v1/auth/logout", headers=headers(tokens))
    assert logged_out.status_code == 200, logged_out.text
    assert (await client.get("/api/v1/auth/me", headers=headers(tokens))).status_code == 401
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 401


@pytest.mark.asyncio
async def test_legacy_scoped_record_is_persisted_unscoped_before_role_write(login_proof, monkeypatch):
    client, state = login_proof
    response = await organization_login(client)
    assert response.status_code == 200, response.text
    tokens = response.json()
    jti, original = await stored(tokens)
    scoped = next(token for token, (_, pid) in state.issued.items() if pid == "work-a")
    await session_store.update_session_token(jti, scoped)
    checked = []
    original_update = session_store.update_session_token

    async def persist(*args, **kwargs):
        result = await original_update(*args, **kwargs)
        checked.append((await session_store.get_session(jti))["keystone_token"])
        return result

    monkeypatch.setattr(session_store, "update_session_token", persist)
    changed = await client.put(
        "/api/v1/projects/work-a/members/ordinary/roles",
        json={"role_ids": ["project_reader"]},
        headers=headers(tokens),
    )
    assert changed.status_code == 200, changed.text
    assert checked and state.issued[checked[0]] == ("ordinary", "")
    _, current = await stored(tokens)
    assert current["started_at"] == original["started_at"]
    assert (await client.get("/api/v1/auth/me", headers=headers(tokens))).status_code == 200


@pytest.mark.asyncio
async def test_invalid_login_proof_wins_over_lost_project_authority(login_proof):
    client, state = login_proof
    response = await organization_login(client)
    assert response.status_code == 200, response.text
    tokens = response.json()
    _, session = await stored(tokens)
    state.revoked.add(session["keystone_token"])
    state.raw = []
    denied = await client.get("/api/v1/projects/current/permissions", headers=headers(tokens))
    assert denied.status_code == 401, denied.text


@pytest.mark.asyncio
async def test_concurrent_proof_renewal_accepts_current_same_family(login_proof, monkeypatch):
    import asyncio

    client, state = login_proof
    response = await organization_login(client)
    assert response.status_code == 200, response.text
    tokens = response.json()
    jti, original = await stored(tokens)
    update = session_store.update_session_token
    raced = False

    async def concurrent_update(session_id, token, *, expected_token=""):
        nonlocal raced
        if not raced:
            raced = True
            concurrent = await asyncio.to_thread(keystone.validate_session, expected_token)
            assert await update(session_id, concurrent["session_token"], expected_token=expected_token)
        return await update(session_id, token, expected_token=expected_token)

    monkeypatch.setattr(session_store, "update_session_token", concurrent_update)
    result = await client.get("/api/v1/auth/me", headers=headers(tokens))
    assert result.status_code == 200, result.text
    current = await session_store.get_session(jti)
    assert raced and current["family_id"] == original["family_id"]
    assert current["started_at"] == original["started_at"]
    assert state.issued[current["keystone_token"]] == ("ordinary", "")


@pytest.mark.asyncio
async def test_account_home_password_change_keeps_personal_scope_and_replaces_credential(login_proof, monkeypatch):
    client, state = login_proof
    state.user_rows["ordinary"].default_project_id = ""
    signed_in = await fresh_login(client)
    assert signed_in.status_code == 200, signed_in.text
    original = signed_in.json()
    assert original["identity_domain_id"] == "account" and original["domain_id"] == "personal"

    def update_user(user_id, *, password):
        state.passwords[user_id] = password
        return state.user_rows[user_id]

    async def password_connection():
        yield SimpleNamespace(identity=SimpleNamespace(update_user=update_user))

    monkeypatch.setitem(app.dependency_overrides, get_os_conn, password_connection)
    changed = await client.post(
        "/api/v1/profile/password",
        json={"current_password": "valid", "new_password": "ChangedProofPass2026!"},
        headers=headers(original),
    )
    assert changed.status_code == 200, changed.text
    old = await client.post("/api/v1/auth/login", json={"username": "ordinary", "password": "valid"})
    assert old.status_code == 401
    replacement = await client.post(
        "/api/v1/auth/login", json={"username": "ordinary", "password": "ChangedProofPass2026!"}
    )
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["user_id"] == original["user_id"]
    assert replacement.json()["identity_domain_id"] == "account"
    assert replacement.json()["project_id"] == original["project_id"]
    assert state.user_rows["ordinary"].domain_id == "account"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rejected_proof,status", [("password", 401), ("unscoped_subject", 403), ("unscoped_identity", 403)]
)
async def test_personal_recovery_requires_fresh_exact_native_password_before_provisioning(
    login_proof, rejected_proof, status
):
    from app.services import account_spaces

    client, state = login_proof
    original = vars(state.user_rows["ordinary"]).copy()
    state.substitute = None if rejected_proof == "password" else rejected_proof
    response = await client.post(
        "/api/v1/auth/personal-project/recovery",
        json={"username": "ordinary", "password": "incorrect" if rejected_proof == "password" else "valid"},
    )
    assert response.status_code == status, response.text
    assert state.native_requests == [("POST", "/v3/auth/tokens")]
    assert not any(p.domain_id == "personal" for p in state.project_rows.values())
    assert vars(state.user_rows["ordinary"]) == original
    state.substitute = None
    recovered = await client.post(
        "/api/v1/auth/personal-project/recovery",
        json={"username": "ordinary", "password": "valid"},
    )
    assert recovered.status_code == 200, recovered.text
    primary = account_spaces.personal_project("ordinary", ks=state)
    assert recovered.json()["project_id"] == primary["id"]
    assert recovered.json()["identity_domain_id"] == "account"
    again = await client.post(
        "/api/v1/auth/personal-project/recovery",
        json={"username": "ordinary", "password": "valid"},
    )
    assert again.status_code == 200 and again.json()["project_id"] == primary["id"]
    assert len([p for p in state.project_rows.values() if p.domain_id == "personal"]) == 1
    assert vars(state.user_rows["ordinary"]) == original


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_day_session_refresh_preserves_native_and_absolute_deadlines(login_proof, monkeypatch, method):
    import time
    from unittest.mock import patch

    client, state = login_proof
    monkeypatch.setenv("SESSION_TIMEOUT_SECONDS", "86400")
    state.native_expires = datetime.now(UTC) + timedelta(days=1)
    response = await fresh_login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert response.status_code == 200, response.text
    tokens = response.json()
    old_jti, original = await stored(tokens)
    original["started_at"] = time.time() - 23 * 3600
    redis = await session_store._get_redis()
    await redis.setex(session_store._key(old_jti), 86400, json.dumps(original))
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    tokens = refreshed.json()
    jti, current = await stored(tokens)
    deadline = int(original["started_at"] + 86400)
    assert jwt_service.verify_refresh(tokens["refresh_token"])["exp"] <= deadline
    assert jwt_service.verify_access(tokens["token"])["exp"] <= deadline
    assert 0 < await redis.ttl(session_store._key(jti)) <= 3600
    assert await session_store.get_session(old_jti) is None
    for field in ("started_at", "family_id", "identity_domain_id", "auth_method"):
        assert current[field] == original[field]
    with patch("app.api.deps.time.time", return_value=original["started_at"] + 86400):
        expired = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert expired.status_code == 401


@pytest.mark.asyncio
async def test_short_native_root_bounds_both_browser_credentials(login_proof, monkeypatch):
    client, state = login_proof
    monkeypatch.setenv("SESSION_TIMEOUT_SECONDS", "86400")
    state.native_expires = datetime.now(UTC) + timedelta(minutes=5)
    response = await fresh_login(client)
    assert response.status_code == 200, response.text
    tokens = response.json()
    native_deadline = int(state.native_expires.timestamp())
    assert jwt_service.verify_access(tokens["token"])["exp"] == native_deadline
    assert jwt_service.verify_refresh(tokens["refresh_token"])["exp"] == native_deadline
    jti, _ = await stored(tokens)
    redis = await session_store._get_redis()
    assert 0 < await redis.ttl(session_store._key(jti)) <= 300
    # A genuinely revoked root is still terminal, never renewed by operator proof.
    state.revoked_users.add("ordinary")
    rejected = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rejected.status_code == 401
    assert await session_store.get_session(jti) is None
