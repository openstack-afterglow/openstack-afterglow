"""Real API/service guards with synthetic native identity; no cloud writes."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.api import deps
from app.api.identity import account_recovery as recovery_api
from app.api.identity import admin_credentials as credential_api
from app.api.identity import admin_identity, auth, domains, iam, profile
from app.api.identity import admin_password_reset as reset_api
from app.database import get_session
from app.services import (
    account_identity,
    account_recovery,
    activity,
    admin_password_reset,
    backup_system_account,
    domain_auth,
    domain_iam,
    identity_roles,
    keystone,
    login_guard,
    native_oidc,
    project_service,
)

SYSTEM_ID = "backup-machine"
HOME = "machine-home"


@pytest.fixture
def protected_identity(monkeypatch):
    record = {"id": SYSTEM_ID, "domain_id": HOME, "domain_name": "Service"}
    monkeypatch.setattr(backup_system_account, "_cached_record", record)
    monkeypatch.setattr(backup_system_account, "_cached_domain", (HOME, "Service"))
    monkeypatch.setattr(backup_system_account, "get_settings", lambda: SimpleNamespace(os_user_domain_name="Service"))
    monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(backup_system_account_enabled=False))
    users = {
        SYSTEM_ID: SimpleNamespace(
            id=SYSTEM_ID,
            name=backup_system_account.ACCOUNT_NAME,
            domain_id=HOME,
            email="machine@test.invalid",
            enabled=True,
            is_enabled=True,
        ),
        "foreign": SimpleNamespace(
            id="foreign",
            name=backup_system_account.ACCOUNT_NAME,
            domain_id="foreign-home",
            email="human@test.invalid",
            enabled=True,
            is_enabled=True,
        ),
        "human": SimpleNamespace(
            id="human",
            name="Human",
            domain_id=HOME,
            email="human2@test.invalid",
            enabled=True,
            is_enabled=True,
        ),
    }
    native = MagicMock()
    native.get_user.side_effect = users.get
    native.get_domain.side_effect = lambda did: SimpleNamespace(
        id=did, name="Service" if did == HOME else did, enabled=True
    )
    native.get_project.side_effect = lambda pid: SimpleNamespace(id=pid, name=pid, domain_id=HOME, enabled=True)
    native.get_group.side_effect = lambda gid: SimpleNamespace(id=gid, name=gid, domain_id=HOME)
    native.get_role.side_effect = lambda rid: SimpleNamespace(id=rid, name=rid, domain_id=None)
    native.users.side_effect = lambda **query: [
        user for user in users.values() if user.domain_id == query.get("domain_id")
    ]
    native.group_users.side_effect = lambda gid: [users[SYSTEM_ID]] if gid == "corrupt" else []
    native.role_assignments.side_effect = lambda **query: (
        [{"role": {"id": "member"}, "user": {"id": SYSTEM_ID}, "scope": {"project": {"id": "p"}}}]
        if query.get("role_id") == "member"
        else []
    )
    conn = SimpleNamespace(
        identity=native,
        close=lambda: None,
        _afterglow_user_id="operator",
        _afterglow_identity_domain_id=HOME,
    )
    ks = SimpleNamespace(
        users=SimpleNamespace(get=users.__getitem__),
        domains=SimpleNamespace(list=lambda **query: [native.get_domain(HOME)]),
        groups=SimpleNamespace(get=native.get_group),
    )
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: ks)
    monkeypatch.setattr(keystone, "get_admin_project_connection", lambda: conn)
    native.get_credential.side_effect = lambda cid: SimpleNamespace(
        id=cid, user_id=SYSTEM_ID, project_id=None, type="cert", blob="private"
    )
    monkeypatch.setattr(keystone, "_is_system_admin", lambda *args, **kwargs: True)
    catalog = identity_roles._catalog(
        [{"id": name, "name": name, "domain_id": None, "description": ""} for name in ("member", "reader", "custom")],
        [],
    )
    monkeypatch.setattr(identity_roles, "load_catalog", lambda conn: catalog)
    monkeypatch.setattr(identity_roles, "_trusted_catalog", lambda: catalog)

    @asynccontextmanager
    async def graph_lock(conn, **kwargs):
        yield SimpleNamespace(assert_owned=AsyncMock())

    monkeypatch.setattr(identity_roles, "_graph_lock", graph_lock)
    monkeypatch.setattr(activity, "get_user_activity_bounds", AsyncMock(return_value={}))
    monkeypatch.setattr(domain_iam, "context", AsyncMock(return_value={"domain_id": HOME, "is_domain_manager": True}))
    monkeypatch.setattr(domain_iam, "resource", AsyncMock(side_effect=lambda kind, uid, did: users[uid]))
    session = SimpleNamespace(rollback=AsyncMock())
    actor = {
        "user_id": "operator",
        "username": "Operator",
        "domain_id": HOME,
        "identity_domain_id": HOME,
        "project_id": "p",
        "_live_system_admin": True,
        "is_system_admin": True,
    }
    application = FastAPI()
    for router, prefix in (
        (admin_identity.router, "/api/v1/admin"),
        (credential_api.router, "/api/v1/admin"),
        (reset_api.router, "/api/v1/admin"),
        (domains.router, "/api/v1/admin"),
        (recovery_api.router, "/api/v1/auth"),
        (auth.router, "/api/v1/auth"),
        (iam.router, "/api/v1/iam"),
        (profile.router, "/api/v1/profile"),
    ):
        application.include_router(router, prefix=prefix)
    application.dependency_overrides[deps.get_admin_os_conn] = lambda: conn
    application.dependency_overrides[deps.get_os_conn] = lambda: conn
    application.dependency_overrides[deps.get_token_info] = lambda: actor
    application.dependency_overrides[deps.require_admin] = lambda: actor
    application.dependency_overrides[deps.require_domain_manager] = lambda: actor
    application.dependency_overrides[get_session] = lambda: session
    return SimpleNamespace(app=application, conn=conn, native=native, ks=ks, users=users, actor=actor, catalog=catalog)


@pytest.mark.parametrize(
    "method,path,body,params",
    [
        ("PATCH", f"/users/{SYSTEM_ID}", {"name": "renamed"}, {"domain_id": HOME}),
        ("PATCH", f"/users/{SYSTEM_ID}", {"enabled": False}, {"domain_id": HOME}),
        ("PATCH", f"/users/{SYSTEM_ID}", {"password": "new-private-password"}, {"domain_id": HOME}),
        ("DELETE", f"/users/{SYSTEM_ID}", None, {"domain_id": HOME}),
        ("POST", "/roles/assign", {"user_id": SYSTEM_ID, "project_id": "p", "role_id": "member"}, None),
        ("DELETE", "/roles/assign", None, {"user_id": SYSTEM_ID, "project_id": "p", "role_id": "member"}),
        ("PUT", f"/groups/team/users/{SYSTEM_ID}", None, None),
        ("DELETE", f"/groups/team/users/{SYSTEM_ID}", None, None),
        ("POST", "/roles/assign-group", {"group_id": "corrupt", "project_id": "p", "role_id": "reader"}, None),
        ("DELETE", "/roles/assign-group", None, {"group_id": "corrupt", "project_id": "p", "role_id": "reader"}),
        ("PATCH", "/groups/corrupt", {"name": "renamed"}, None),
        ("DELETE", "/groups/corrupt", None, None),
        ("POST", "/identity/system-roles/grant", {"user_id": SYSTEM_ID}, None),
        ("POST", "/identity/system-roles/revoke", {"user_id": SYSTEM_ID}, None),
        ("PUT", "/roles/member/implies/custom", None, None),
        ("PATCH", "/roles/member", {"description": "changed"}, None),
        ("DELETE", "/roles/member", None, None),
        ("PATCH", "/user-credentials/existing", {"blob": "replacement"}, {"domain_id": HOME}),
        ("DELETE", "/user-credentials/existing", None, {"domain_id": HOME}),
        ("POST", "/domains/tenant/managers", {"user_id": SYSTEM_ID, "role_id": "member"}, None),
        ("POST", f"/users/{SYSTEM_ID}/password/reset-email", {}, None),
        ("POST", "/user-credentials", {"user_id": SYSTEM_ID, "type": "cert", "blob": "private"}, {"domain_id": HOME}),
    ],
)
async def test_admin_mutations_reject_fixed_code_before_native_write(protected_identity, method, path, body, params):
    state = protected_identity
    async with AsyncClient(transport=ASGITransport(app=state.app), base_url="http://test") as client:
        response = await client.request(method, "/api/v1/admin" + path, json=body, params=params)
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": "system_account_protected"}
    for name in (
        "update_user",
        "delete_user",
        "assign_project_role_to_user",
        "unassign_project_role_from_user",
        "add_user_to_group",
        "remove_user_from_group",
        "assign_project_role_to_group",
        "unassign_project_role_from_group",
        "update_group",
        "delete_group",
        "update_role",
        "delete_role",
        "create_credential",
        "put",
        "delete",
    ):
        getattr(state.native, name).assert_not_called()


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("PATCH", f"/users/{SYSTEM_ID}", {"enabled": False}),
        ("DELETE", f"/users/{SYSTEM_ID}", None),
    ],
)
async def test_domain_iam_mutations_keep_fixed_code(protected_identity, method, path, body):
    async with AsyncClient(transport=ASGITransport(app=protected_identity.app), base_url="http://test") as client:
        response = await client.request(method, "/api/v1/iam" + path, json=body)
    assert response.status_code == 403
    assert response.json() == {"detail": "system_account_protected"}


async def test_user_and_assignment_listings_expose_marker(protected_identity):
    state = protected_identity
    state.native.role_assignments.side_effect = lambda **query: [
        {"role": {"id": "member", "name": "member"}, "user": {"id": SYSTEM_ID}, "scope": {"project": {"id": "p"}}}
    ]
    async with AsyncClient(transport=ASGITransport(app=state.app), base_url="http://test") as client:
        users = await client.get("/api/v1/admin/users", params={"domain_id": HOME})
        members = await client.get("/api/v1/admin/projects/p/members", params={"domain_id": HOME})
        group = await client.get("/api/v1/admin/groups/corrupt/users")
    assert users.status_code == members.status_code == group.status_code == 200
    system = next(user for user in users.json()["items"] if user["id"] == SYSTEM_ID)
    assert system["system_account"] == {"kind": "auto_backup"}
    assert members.json()[0]["system_account"] == {"kind": "auto_backup"}
    assert group.json()[0]["system_account"] == {"kind": "auto_backup"}
    assert domain_iam.user_dto(state.users[SYSTEM_ID])["system_account"] == {"kind": "auto_backup"}
    assert "system_account" not in domain_iam.user_dto(state.users["foreign"])


async def test_login_rejects_exact_principal_before_password_attempt(protected_identity, monkeypatch):
    monkeypatch.setattr(
        account_identity,
        "password_account",
        lambda *args, **kwargs: {
            "id": SYSTEM_ID,
            "name": backup_system_account.ACCOUNT_NAME,
            "domain_id": HOME,
        },
    )
    attempt = AsyncMock()
    monkeypatch.setattr(account_identity, "authenticate_password", attempt)
    async with AsyncClient(transport=ASGITransport(app=protected_identity.app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login", json={"username": backup_system_account.ACCOUNT_NAME, "password": "secret"}
        )
    assert response.status_code == 403
    assert response.json() == {"detail": "system_account_protected"}
    attempt.assert_not_awaited()


async def test_same_name_foreign_domain_is_not_protected(protected_identity, monkeypatch):
    user = protected_identity.users["foreign"]
    await backup_system_account.assert_not_system_account(user.id, conn=protected_identity.conn)
    assert backup_system_account.system_account_marker(user) is None
    await backup_system_account.assert_login_allowed(user_id=user.id, username=user.name, domain_id=user.domain_id)
    operation = SimpleNamespace(run=AsyncMock(return_value={"user_id": user.id}))
    monkeypatch.setattr(login_guard, "check_locked", AsyncMock())
    result = await account_identity.authenticate_password(
        {"id": user.id, "name": user.name, "domain_id": user.domain_id},
        "secret",
        operation=operation,
    )
    assert result == {"user_id": "foreign"}
    operation.run.assert_awaited_once()


async def test_token_publication_and_native_rescope_are_blocked(protected_identity):
    with pytest.raises(HTTPException) as denied:
        await auth._build_token_response(
            keystone_token="native",
            project_id="p",
            project_name="p",
            user_id=SYSTEM_ID,
            username=backup_system_account.ACCOUNT_NAME,
            roles=["member"],
            is_system_admin=False,
            domain_id=HOME,
            domain_name="Service",
            is_domain_manager=False,
            identity_domain_id=HOME,
            identity_domain_name="Service",
        )
    assert (denied.value.status_code, denied.value.detail) == (403, "system_account_protected")
    operation = SimpleNamespace(run=AsyncMock())
    with pytest.raises(HTTPException) as denied:
        await auth._scope_project(
            auth.ProjectScopeRequest(project_id="p"),
            {
                "user_id": SYSTEM_ID,
                "username": backup_system_account.ACCOUNT_NAME,
                "identity_domain_id": HOME,
            },
            operation=operation,
        )
    assert denied.value.detail == "system_account_protected"
    operation.run.assert_not_awaited()


async def test_authenticated_dependency_blocks_existing_machine_session_without_human_lookup(
    protected_identity, monkeypatch
):
    actor = {"user_id": SYSTEM_ID, "username": backup_system_account.ACCOUNT_NAME, "identity_domain_id": HOME}
    monkeypatch.setattr(deps, "_resolve_jwt_token_info", AsyncMock(return_value=actor))
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/anything", "headers": []})
    with pytest.raises(HTTPException) as denied:
        await deps.resolve_token_info(request, "Bearer synthetic")
    assert (denied.value.status_code, denied.value.detail) == (403, "system_account_protected")
    assert not hasattr(request.state, "token_info")
    protected_identity.native.get_user.reset_mock()
    human = {"user_id": "human", "username": "Human", "identity_domain_id": HOME}
    monkeypatch.setattr(deps, "_resolve_jwt_token_info", AsyncMock(return_value=human))
    assert await deps.resolve_token_info(request, "Bearer synthetic") == human
    protected_identity.native.get_user.assert_not_called()


async def test_stale_recovery_proof_and_initial_password_creation_cannot_touch_machine(protected_identity):
    state = protected_identity
    row = SimpleNamespace(user_id=SYSTEM_ID)
    with pytest.raises(HTTPException) as denied:
        await account_recovery._bound(row, state.ks, state.catalog, None)
    assert (denied.value.status_code, denied.value.detail) == (403, "system_account_protected")
    with pytest.raises(HTTPException) as denied:
        await account_recovery._creation_subject(SYSTEM_ID, HOME, state.ks, state.catalog)
    assert denied.value.detail == "system_account_protected"
    assert not await account_recovery._eligible(state.users[SYSTEM_ID], state.ks, state.catalog)
    with pytest.raises(HTTPException) as denied:
        await admin_password_reset._subject(SYSTEM_ID, state.ks, state.catalog)
    assert denied.value.detail == "system_account_protected"


async def test_federation_cannot_exchange_or_attach_machine_identity(protected_identity, monkeypatch):
    exchange = AsyncMock()
    monkeypatch.setattr(domain_auth, "keystone_federate", exchange)
    with pytest.raises(HTTPException) as denied:
        await domain_auth._canonical_federation(
            None,
            None,
            protected_identity.users[SYSTEM_ID],
            {},
            ks=protected_identity.ks,
        )
    assert denied.value.detail == "system_account_protected"
    exchange.assert_not_awaited()
    with pytest.raises(HTTPException) as denied:
        await account_identity.attach(
            protected_identity.users[SYSTEM_ID],
            None,
            None,
            lease=None,
            ks=protected_identity.ks,
        )
    assert denied.value.detail == "system_account_protected"


async def test_stale_public_reset_proof_is_rejected_through_api(protected_identity, monkeypatch):
    monkeypatch.setattr(account_recovery, "_locked", AsyncMock(return_value=SimpleNamespace(user_id=SYSTEM_ID)))
    async with AsyncClient(transport=ASGITransport(app=protected_identity.app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/recovery/password/complete",
            json={
                "token": "a" * 32,
                "new_password": "long-new-private-password",
            },
        )
    assert response.status_code == 403
    assert response.json() == {"detail": "system_account_protected"}
    protected_identity.native.update_user.assert_not_called()


@pytest.mark.parametrize(
    "path,body",
    [
        ("", {"name": "renamed"}),
        ("/password", {"current_password": "old-secret", "new_password": "new-secret"}),
    ],
)
async def test_profile_mutations_reject_machine_even_with_old_session(protected_identity, path, body):
    state = protected_identity
    state.actor.update(user_id=SYSTEM_ID, username=backup_system_account.ACCOUNT_NAME)
    async with AsyncClient(transport=ASGITransport(app=state.app), base_url="http://test") as client:
        response = await client.request("PATCH" if not path else "POST", "/api/v1/profile" + path, json=body)
    assert response.status_code == 403
    assert response.json() == {"detail": "system_account_protected"}
    state.native.update_user.assert_not_called()


async def test_application_credential_issuance_rejects_machine_owner(protected_identity):
    state = protected_identity
    state.actor.update(user_id=SYSTEM_ID, username=backup_system_account.ACCOUNT_NAME)
    state.conn.session = SimpleNamespace(
        auth=SimpleNamespace(
            get_access=lambda session: SimpleNamespace(
                project_id="p",
                user_id=SYSTEM_ID,
                role_ids=["member"],
                role_names=["member"],
            )
        )
    )
    async with AsyncClient(transport=ASGITransport(app=state.app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/application-credentials",
            params={"domain_id": HOME},
            json={
                "name": "forbidden",
                "role_ids": ["member"],
            },
        )
    assert response.status_code == 403
    assert response.json() == {"detail": "system_account_protected"}
    state.native.create_application_credential.assert_not_called()


async def test_refresh_cannot_resurrect_saved_machine_session(protected_identity, monkeypatch):
    from app.services import session_store

    monkeypatch.setattr(auth.jwt_service, "verify_refresh", lambda token: {"jti": "saved", "sub": SYSTEM_ID})
    monkeypatch.setattr(
        session_store,
        "get_session",
        AsyncMock(
            return_value={
                "user_id": SYSTEM_ID,
                "username": backup_system_account.ACCOUNT_NAME,
                "identity_domain_id": HOME,
            }
        ),
    )
    exchange = AsyncMock()
    monkeypatch.setattr(auth, "_exchange_native_scope", exchange)
    async with AsyncClient(transport=ASGITransport(app=protected_identity.app), base_url="http://test") as client:
        response = await client.post("/api/v1/auth/refresh", json={"refresh_token": "saved-refresh-token"})
    assert response.status_code == 403
    assert response.json() == {"detail": "system_account_protected"}
    exchange.assert_not_awaited()


@pytest.mark.parametrize("remove", [False, True])
async def test_project_member_edits_reject_machine_target(protected_identity, monkeypatch, remove):
    boundary = AsyncMock(return_value=True)
    monkeypatch.setattr(project_service, "_domain_access", boundary)

    @asynccontextmanager
    async def write(project_id):
        yield None, protected_identity.ks, protected_identity.catalog, [], []

    monkeypatch.setattr(project_service, "_membership_write", write)
    with pytest.raises(HTTPException) as denied:
        await project_service.replace_member_roles("p", SYSTEM_ID, ["member"], protected_identity.actor, remove=remove)
    assert (denied.value.status_code, denied.value.detail) == (403, "system_account_protected")


async def test_each_enabled_request_loads_canonical_identity_before_native_authority(protected_identity, monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(backup_system_account_enabled=True))
    monkeypatch.setattr(backup_system_account, "_cached_record", None)
    events = []

    async def load():
        events.append("load")
        monkeypatch.setattr(backup_system_account, "_cached_record", {"id": SYSTEM_ID})

    async def resolve(*args, **kwargs):
        events.append("resolve")
        assert backup_system_account.cached_managed_user_id() == SYSTEM_ID
        return {"user_id": "human", "username": "Human", "identity_domain_id": HOME}

    load_account = AsyncMock(side_effect=load)
    monkeypatch.setattr(backup_system_account, "load_account", load_account)
    monkeypatch.setattr(deps, "_resolve_jwt_token_info", resolve)
    for _ in range(2):
        request = Request({"type": "http", "method": "GET", "path": "/api/v1/anything", "headers": []})
        await deps.resolve_token_info(request, "Bearer synthetic")
    assert events == ["load", "resolve", "load", "resolve"]
    assert load_account.await_count == 2


async def test_identity_cache_failure_does_not_deny_ordinary_nonpersonal_authority(protected_identity, monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(backup_system_account_enabled=True))
    monkeypatch.setattr(
        backup_system_account, "load_account", AsyncMock(side_effect=RuntimeError("private-ciphertext"))
    )
    human = {"user_id": "human", "username": "Human", "identity_domain_id": HOME}
    resolve = AsyncMock(return_value=human)
    monkeypatch.setattr(deps, "_resolve_jwt_token_info", resolve)
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/anything", "headers": []})
    assert await deps.resolve_token_info(request, "Bearer synthetic") == human
    assert backup_system_account.cached_managed_user_id() == SYSTEM_ID
    resolve.assert_awaited_once()


async def test_account_creation_cannot_claim_reserved_name_in_system_home(protected_identity, monkeypatch):
    monkeypatch.setattr(domain_iam, "domain", AsyncMock(return_value={"id": HOME}))
    policy = AsyncMock()
    monkeypatch.setattr(domain_iam, "password_policy", policy)
    with pytest.raises(HTTPException) as denied:
        await domain_iam.create_account(
            HOME, backup_system_account.ACCOUNT_NAME, "owner@test.invalid", "private-password"
        )
    assert (denied.value.status_code, denied.value.detail) == (403, "system_account_protected")
    policy.assert_not_awaited()


@pytest.mark.parametrize(
    "body",
    [
        {"name": backup_system_account.ACCOUNT_NAME},
        {"options": {"multi_factor_auth_rules": [["password"]]}},
    ],
)
async def test_reserved_rename_and_machine_options_are_rejected(protected_identity, body):
    target = "human" if "name" in body else SYSTEM_ID
    async with AsyncClient(transport=ASGITransport(app=protected_identity.app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/admin/users/{target}",
            params={"domain_id": HOME},
            json=body,
        )
    assert response.status_code == 403
    assert response.json() == {"detail": "system_account_protected"}
    protected_identity.native.update_user.assert_not_called()


async def test_graph_recipient_guard_uses_one_reserved_lookup_not_per_user_gets(protected_identity):
    state = protected_identity
    await identity_roles._assert_mutable_users({"human", "foreign"}, conn=state.conn)
    state.native.get_user.assert_not_called()
    state.native.users.assert_called_once()


async def test_native_oidc_mapping_cannot_publish_machine_and_revokes_exchange(protected_identity, monkeypatch):
    monkeypatch.setattr(domain_auth, "require_provider", AsyncMock())
    monkeypatch.setattr(
        domain_auth,
        "keystone_federate",
        AsyncMock(
            return_value=(
                "forbidden-native-token",
                {
                    "id": SYSTEM_ID,
                    "name": backup_system_account.ACCOUNT_NAME,
                    "domain": {"id": HOME},
                },
            )
        ),
    )
    revoke = AsyncMock()
    monkeypatch.setattr(domain_auth, "_revoke_quietly", revoke)
    personal = MagicMock()
    monkeypatch.setattr("app.services.account_spaces.personal_project", personal)
    with pytest.raises(HTTPException) as denied:
        await native_oidc.federate(
            SimpleNamespace(id="provider", revision=1),
            SimpleNamespace(
                username="verified-user", issuer="issuer", email="owner@test.invalid", bearer="provider-token"
            ),
            {"id": "tenant"},
            ks=protected_identity.ks,
            lease=SimpleNamespace(assert_owned=AsyncMock()),
            catalog=protected_identity.catalog,
            descriptor=SimpleNamespace(issuer="issuer"),
        )
    assert (denied.value.status_code, denied.value.detail) == (403, "system_account_protected")
    revoke.assert_awaited_once_with("forbidden-native-token")
    personal.assert_not_called()


@pytest.mark.parametrize("load_succeeds", [True, False])
async def test_public_native_oidc_hydrates_before_first_personal_proof(
    protected_identity,
    monkeypatch,
    load_succeeds,
):
    from app.services import account_spaces, organization_provisioning

    state = protected_identity
    monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(backup_system_account_enabled=True))
    monkeypatch.setattr(backup_system_account, "_cached_record", None)

    async def load():
        if not load_succeeds:
            raise RuntimeError("unreadable-envelope")
        monkeypatch.setattr(backup_system_account, "_cached_record", {"id": SYSTEM_ID})

    loaded = AsyncMock(side_effect=load)
    monkeypatch.setattr(backup_system_account, "load_account", loaded)
    monkeypatch.setattr(domain_auth, "require_provider", AsyncMock())
    descriptor = SimpleNamespace(issuer="issuer")
    monkeypatch.setattr(domain_auth, "_require_native_mapping", lambda ks, row: descriptor)
    monkeypatch.setattr(native_oidc, "_federation_identity_reason", lambda native, descriptor: None)
    monkeypatch.setattr(native_oidc, "_email_user", lambda *args: True)
    monkeypatch.setattr(
        domain_auth,
        "keystone_federate",
        AsyncMock(
            return_value=(
                "human-native-token",
                {
                    "id": "human",
                    "name": "Human",
                    "domain": {"id": HOME},
                    "OS-FEDERATION": {},
                },
            )
        ),
    )
    monkeypatch.setattr(organization_provisioning, "require_current", AsyncMock())
    revoke = AsyncMock()
    monkeypatch.setattr(domain_auth, "_revoke_quietly", revoke)
    state.ks.projects = SimpleNamespace(
        get=lambda pid: SimpleNamespace(
            id=pid,
            afterglow_personal_user_id="human",
            afterglow_personal_primary=True,
        )
    )
    rows = [
        {"role": {"id": "member"}, "user": {"id": uid}, "scope": {"project": {"id": "p"}}}
        for uid in ("human", SYSTEM_ID)
    ]
    state.ks.role_assignments = SimpleNamespace(list=lambda **query: rows)
    sources = [
        {
            "role_id": "member",
            "user_id": uid,
            "group_id": None,
            "kind": "project",
            "scope_id": "p",
            "inherited": False,
            "users": {uid},
        }
        for uid in ("human", SYSTEM_ID)
    ]

    def personal(user_id, **kwargs):
        loaded.assert_awaited_once()
        account_spaces._verify_personal_member(
            state.ks,
            state.catalog,
            {"id": "p"},
            user_id,
            sources=sources,
        )
        return {"id": "p"}

    monkeypatch.setattr(account_spaces, "personal_project", personal)
    call = native_oidc.federate(
        SimpleNamespace(id="provider", revision=1, kind="oidc"),
        SimpleNamespace(
            username="Human",
            issuer="issuer",
            email="human2@test.invalid",
            bearer="provider-token",
            subject="subject",
        ),
        {"id": HOME, "name": "Service"},
        ks=state.ks,
        lease=SimpleNamespace(assert_owned=AsyncMock()),
        catalog=state.catalog,
        descriptor=descriptor,
    )
    if load_succeeds:
        result = await call
        assert result.user_id == "human"
        revoke.assert_not_awaited()
    else:
        with pytest.raises(HTTPException) as denied:
            await call
        assert denied.value.status_code == 503
        revoke.assert_awaited_once_with("human-native-token")
