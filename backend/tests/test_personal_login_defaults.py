"""Human landing and actor-bound reconnect through real login/JWT consumers."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services import account_spaces, domain_scope, login_preferences, project_service
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_projects import domain_native as domain_native
from tests.test_domain_projects import grant, row
from tests.test_login_native_operation import login, provider_login
from tests.test_login_native_operation import native_login as native_login


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_markerless_accounts_admin_gets_own_member_primary_without_identity_mutation(
    native_login, monkeypatch, method
):
    client, native = native_login
    native.raw.append(row(user={"id": "ordinary"}, role={"id": "admin"}, scope={"system": {"all": True}}))
    before_user = vars(native.user_rows["ordinary"]).copy()
    before_grants = list(native.raw)
    response = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_system_admin"] and body["identity_domain_id"] == "account"
    assert body["initial_workspace"] == {"kind": "personal", "domain_id": "personal", "project_id": body["project_id"]}
    assert vars(native.user_rows["ordinary"]) == before_user
    assert all(grant in native.raw for grant in before_grants)
    direct = native.assignments(project=body["project_id"], user="ordinary")
    assert project_service._direct_ids(direct, "ordinary") == {"member"}
    assert (
        len([p for p in native.project_rows.values() if getattr(p, "afterglow_personal_user_id", None) == "ordinary"])
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_opt_in_remembered_workspace_is_freshly_authorized(native_login, monkeypatch, method):
    client, native = native_login
    # Organization admission already exists; reconnect must not grant or repair it.
    native.raw.append(grant("reader", user="ordinary", project="default-a"))
    await login_preferences.save("ordinary", "account", True, domain_id="tenant-a", project_id="work-a")
    before = list(native.raw)
    response = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["domain_id"], body["identity_domain_id"], body["project_id"]) == ("tenant-a", "account", "work-a")
    assert body["initial_workspace"] == {"kind": "remembered", "domain_id": "tenant-a", "project_id": "work-a"}
    assert all(grant in native.raw for grant in before)
    assert not any(call[0] in {"create_domain", "create_group"} for call in native.calls)
    assert account_spaces.personal_project("ordinary", ks=native) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["revoked", "disabled", "wrong-domain"])
async def test_inaccessible_saved_target_falls_back_to_verified_personal(native_login, fault):
    client, native = native_login
    native.raw.append(grant("reader", user="ordinary", project="default-a"))
    if fault == "revoked":
        native.raw = [r for r in native.raw if r.scope.get("project", {}).get("id") != "work-a"]
    if fault == "disabled":
        native.project_rows["work-a"].enabled = False
    await login_preferences.save(
        "ordinary",
        "account",
        True,
        domain_id="tenant-b" if fault == "wrong-domain" else "tenant-a",
        project_id="work-a",
    )
    response = await login(client)
    assert response.status_code == 200, response.text
    assert response.json()["initial_workspace"]["kind"] == "personal"
    assert response.json()["domain_id"] == "personal"


@pytest.mark.asyncio
async def test_saved_target_directory_failure_is_not_silently_treated_as_revocation(native_login, monkeypatch):
    client, _ = native_login
    await login_preferences.save("ordinary", "account", True, domain_id="tenant-a", project_id="work-a")
    original = domain_scope.resolve_domain

    def unavailable(did, **kwargs):
        if did == "tenant-a":
            raise HTTPException(503, "Directory unavailable")
        return original(did, **kwargs)

    monkeypatch.setattr(domain_scope, "resolve_domain", unavailable)
    response = await login(client)
    assert response.status_code == 503 and "token" not in response.json()


@pytest.mark.asyncio
async def test_preference_exact_home_and_user_isolation_and_atomic_opt_out(native_login):
    _, _ = native_login
    await login_preferences.save("ordinary", "account", True, domain_id="tenant-a", project_id="work-a")
    assert not (await login_preferences.read("second", "account"))["remember_last_workspace"]
    assert not (await login_preferences.read("ordinary", "home"))["remember_last_workspace"]
    await login_preferences.record("ordinary", "account", "tenant-b", "work-b")
    assert (await login_preferences.read("ordinary", "account"))["project_id"] == "work-b"
    await login_preferences.save("ordinary", "account", False)
    await login_preferences.record("ordinary", "account", "tenant-a", "work-a")
    assert await login_preferences.read("ordinary", "account") == {"remember_last_workspace": False}


@pytest.mark.asyncio
async def test_preference_store_failure_is_distinct(native_login, monkeypatch):
    client, _ = native_login
    monkeypatch.setattr(login_preferences.cache, "_get_redis", AsyncMock(side_effect=RuntimeError("private")))
    response = await login(client)
    assert response.status_code == 503
    assert response.json()["detail"] == "login_preference_unavailable"
    assert "private" not in response.text and "token" not in response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["project", "system", "system_group"])
async def test_native_service_role_excludes_automation_not_operator_name(native_login, scope):
    _, native = native_login
    native.role_rows.append(row(id="service", name="service", domain_id=None))
    if scope == "project":
        native.raw.append(grant("service", user="ordinary", project="work-a"))
    elif scope == "system":
        native.raw.append(row(user={"id": "ordinary"}, role={"id": "service"}, scope={"system": {"all": True}}))
    else:
        native.group_rows["automation"] = row(id="automation", name="Automation", domain_id="account")
        native.members["automation"] = {"ordinary"}
        native.raw.append(row(group={"id": "automation"}, role={"id": "service"}, scope={"system": {"all": True}}))
    with pytest.raises(HTTPException) as denied:
        await account_spaces.ensure_personal_project("ordinary")
    assert denied.value.status_code == 403 and denied.value.detail == "service_identity_personal_forbidden"
    assert not any(getattr(p, "afterglow_personal_user_id", None) == "ordinary" for p in native.project_rows.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_remembered_admin_nonmember_target_falls_back_to_own_personal(native_login, monkeypatch, method):
    client, native = native_login
    native.raw.append(row(user={"id": "ordinary"}, role={"id": "admin"}, scope={"system": {"all": True}}))
    await login_preferences.save("ordinary", "account", True, domain_id="tenant-b", project_id="work-b")
    response = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert response.status_code == 200, response.text
    body = response.json()
    primary = account_spaces.personal_project("ordinary", ks=native)
    assert body["is_system_admin"] and body["domain_id"] == "personal" and body["project_id"] == primary["id"]
    assert body["initial_workspace"]["kind"] == "personal"
    assert not native.assignments(user="ordinary", project="work-b", effective=True)


@pytest.mark.asyncio
async def test_profile_preference_api_uses_only_current_exact_actor_and_fresh_membership(native_login):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_token_info
    from app.api.identity import profile

    client, native = native_login
    initial = await login(client)
    assert initial.status_code == 200, initial.text
    pid = initial.json()["project_id"]
    actor = {"user_id": "ordinary", "identity_domain_id": "account", "domain_id": "personal", "project_id": pid}
    app = FastAPI()
    app.include_router(profile.router, prefix="/api/v1/profile")
    app.dependency_overrides[get_token_info] = lambda: actor
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as profile_client:
        read = await profile_client.get("/api/v1/profile/login-preference")
        assert read.status_code == 200 and read.json() == {"remember_last_workspace": False}
        assert "no-store" in read.headers["cache-control"]
        foreign = await profile_client.put(
            "/api/v1/profile/login-preference", json={"remember_last_workspace": True, "project_id": "work-b"}
        )
        assert foreign.status_code == 422
        saved = await profile_client.put("/api/v1/profile/login-preference", json={"remember_last_workspace": True})
        assert saved.status_code == 200 and saved.json()["project_id"] == pid
        native.raw = [r for r in native.raw if r.scope.get("project", {}).get("id") != pid]
        revoked = await profile_client.put("/api/v1/profile/login-preference", json={"remember_last_workspace": True})
        assert revoked.status_code == 403
        # Opt-out remains possible even after losing the selected project.
        disabled = await profile_client.put("/api/v1/profile/login-preference", json={"remember_last_workspace": False})
        assert disabled.status_code == 200 and disabled.json() == {"remember_last_workspace": False}


@pytest.mark.asyncio
@pytest.mark.parametrize("substitute", ["wrong_subject", "wrong_project", "wrong_home"])
async def test_remembered_exchange_subject_scope_substitution_never_becomes_personal_fallback(native_login, substitute):
    client, native = native_login
    native.raw.append(grant("reader", user="ordinary", project="default-a"))
    await account_spaces.ensure_personal_project("ordinary")
    await login_preferences.save("ordinary", "account", True, domain_id="tenant-a", project_id="work-a")
    setattr(native, substitute, True)
    response = await login(client)
    assert response.status_code in {401, 403} and "token" not in response.json()


@pytest.mark.asyncio
async def test_system_admin_personal_member_is_not_published_as_project_manager(native_login):
    client, native = native_login
    native.raw.append(row(user={"id": "ordinary"}, role={"id": "admin"}, scope={"system": {"all": True}}))
    signed_in = await login(client)
    assert signed_in.status_code == 200, signed_in.text
    permission = await client.get(
        "/api/v1/projects/current/permissions", headers={"Authorization": f"Bearer {signed_in.json()['token']}"}
    )
    assert permission.status_code == 200, permission.text
    body = permission.json()
    assert body["is_system_admin"] is True and body["roles"] == ["member"]
    assert body["is_manager"] is False and body["is_owner"] is False
    assert body["can_write"] is True


@pytest.mark.asyncio
async def test_system_admin_reader_user_workspace_keeps_reader_capabilities(native_login):
    client, native = native_login
    native.raw.append(row(user={"id": "ordinary"}, role={"id": "admin"}, scope={"system": {"all": True}}))
    signed_in = await login(client)
    assert signed_in.status_code == 200, signed_in.text
    selected = await client.post(
        "/api/v1/auth/token/workspace",
        headers={"Authorization": f"Bearer {signed_in.json()['token']}"},
        json={"domain_id": "tenant-a", "project_id": "work-a"},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["is_system_admin"] is True and selected.json()["can_write"] is False
    current = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {selected.json()['token']}"})
    assert current.status_code == 200 and current.json()["can_write"] is False
