"""Login behavior through real authority logic with synthetic native transport."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient
from keystoneauth1.exceptions.http import Unauthorized

from app.api.identity import auth
from app.main import app
from app.services import (
    account_spaces,
    domain_auth,
    domain_projects,
    enrollment_policy,
    jwt_service,
    keystone,
    session_store,
)
from app.services.native_operation import NativeOperation
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_projects import domain_native as domain_native
from tests.test_domain_projects import grant, row

pytestmark = pytest.mark.usefixtures("ownership_journal")


@pytest.fixture
async def native_login(monkeypatch, domain_native, ownership_journal):
    n = domain_native
    from app.models.account_spaces import PersonalProjectIntent, SharedDomainIntent
    from app.models.domain_iam import DomainEnrollment
    from app.models.enrollment_policy import EnrollmentPolicy, SignupRequest

    async with ownership_journal() as sql:
        connection = await sql.connection()
        for model in (PersonalProjectIntent, SharedDomainIntent, DomainEnrollment, EnrollmentPolicy, SignupRequest):
            await connection.run_sync(model.__table__.create)
        sql.add(
            EnrollmentPolicy(
                id=1,
                revision=1,
                public_signup_enabled=True,
                approval_mode="auto",
                personal_quotas={},
                updated_by_user_id="operator",
                updated_at=datetime.now(UTC),
            )
        )
        await sql.commit()
    monkeypatch.setattr("app.database.get_session_factory", lambda: ownership_journal)
    monkeypatch.setattr(account_spaces, "get_session_factory", lambda: ownership_journal)
    monkeypatch.setattr(enrollment_policy, "get_session_factory", lambda: ownership_journal)
    for kind in ("account", "personal"):
        n.domain_rows[kind] = row(id=kind, name="Accounts" if kind == "account" else "Personal", enabled=True)
    n.exchanges = []
    n.password_domains = []
    n.sessions = []
    n.wrong_subject = False
    n.wrong_project = False
    n.wrong_home = False
    n.policy_enabled = True
    n.password_error = None
    n.user_rows["ordinary"].domain_id = "account"
    n.user_rows["ordinary"].email = "actual@example.test"
    n.user_rows["ordinary"].default_project_id = "work-a"
    n.raw.append(grant("reader", user="ordinary", project="work-a"))
    settings = SimpleNamespace(
        os_auth_url="https://native.test/v3", ssl_verify=True, os_interface="internal", os_region_name="RegionOne"
    )
    monkeypatch.setattr(keystone, "get_settings", lambda: settings)

    def effective_roles(uid, pid):
        ids = {r.role["id"] for r in n.assignments(user=uid, project=pid, effective=True)} if pid else set()
        while True:
            expanded = ids | {
                child["id"] for edge in n.edges if edge["prior_role"]["id"] in ids for child in edge["implies"]
            }
            if expanded == ids:
                return sorted(ids)
            ids = expanded

    def access(uid, pid=""):
        return SimpleNamespace(
            user_id=uid,
            username=uid,
            user_domain_id="tenant-b" if n.wrong_home else n.user_rows[uid].domain_id,
            project_id=pid,
            project_name=n.project_rows[pid].name if pid else "",
            project_domain_id=n.project_rows[pid].domain_id if pid else "",
            auth_token=f"native:{uid}:{pid}",
            role_names=effective_roles(uid, pid),
            expires=None,
        )

    class Password:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_access(self, session):
            n.exchanges.append(("password", ""))
            n.password_domains.append(self.kwargs.get("user_domain_id"))
            if n.password_error:
                raise n.password_error
            if (
                self.kwargs["password"] != "valid"
                or self.kwargs.get("user_domain_id") != n.user_rows[self.kwargs["username"]].domain_id
            ):
                raise Unauthorized()
            return access(self.kwargs["username"])

    class Token:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_access(self, session):
            uid = self.kwargs["token"].split(":")[1]
            pid = self.kwargs.get("project_id", "")
            n.exchanges.append(("token", pid))
            if pid and not n.assignments(user=uid, project=pid, effective=True):
                raise Unauthorized()
            return access("second" if n.wrong_subject and pid else uid, "default-a" if n.wrong_project and pid else pid)

    def session(**kwargs):
        sess = SimpleNamespace(session=SimpleNamespace(close=Mock()))
        n.sessions.append(sess)
        return sess

    def projects(user):
        ids = {r.scope["project"]["id"] for r in n.assignments(user=user, effective=True)}
        return [n.project_rows[pid] for pid in n.project_rows if pid in ids]

    monkeypatch.setattr(keystone.v3, "Password", Password)
    monkeypatch.setattr(keystone.v3, "Token", Token)
    monkeypatch.setattr(keystone.native_transport, "create_session", session)
    monkeypatch.setattr("keystoneclient.v3.client.Client", lambda **_: row(projects=row(list=projects)))

    async def policy(did, **kwargs):
        return domain_auth.LoginPolicy(domain_id=did, password_enabled=n.policy_enabled)

    monkeypatch.setattr(domain_auth, "get_policy", policy)
    monkeypatch.setattr(auth, "_prewarm_dashboard", AsyncMock())
    monkeypatch.setattr(auth, "record_project_access", AsyncMock())
    monkeypatch.setattr(auth.activity_svc, "record", AsyncMock())
    monkeypatch.setattr(auth.login_guard, "record_success", AsyncMock())
    n.failures = AsyncMock()
    monkeypatch.setattr(auth.login_guard, "record_failure", n.failures)
    monkeypatch.setattr(auth.login_guard, "check_locked", AsyncMock())
    monkeypatch.setenv("TOKEN_IP_BINDING_MODE", "off")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, n


async def login(client, **overrides):
    return await client.post(
        "/api/v1/auth/login",
        json={"username": "ordinary", "password": "valid", **overrides},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_fresh_login_uses_personal_project_not_organization_preference(native_login, monkeypatch, method):
    client, native = native_login
    response = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert response.status_code == 200, response.text
    assert native.password_domains == (["account"] if method == "password" else [])
    body = response.json()
    primary = account_spaces.personal_project("ordinary", ks=native)
    assert (body["domain_id"], body["identity_domain_id"]) == ("personal", "account")
    assert body["project_id"] == body["default_project_id"] == primary["id"]
    assert body["project_name"].startswith("ordinary-")
    assert body["can_write"] is True and body["is_domain_manager"] is False
    assert native.user_rows["ordinary"].default_project_id == "work-a"
    assert jwt_service.verify_access(body["token"])["project_id"] == primary["id"]
    claims = jwt_service.verify_refresh(body["refresh_token"])
    stored = await session_store.get_session(claims["jti"])
    assert (stored["domain_id"], stored["identity_domain_id"], stored["project_id"]) == (
        "personal",
        "account",
        primary["id"],
    )
    assert all(session.session.close.call_count == 1 for session in native.sessions)


@pytest.mark.asyncio
async def test_repeated_accounts_login_preserves_personal_identity_and_existing_grants(native_login):
    client, native = native_login
    before = [vars(assignment).copy() for assignment in native.raw]
    first = await login(client)
    assert first.status_code == 200, first.text
    primary = first.json()["project_id"]
    native.calls.clear()
    again = await login(client)
    assert again.status_code == 200, again.text
    assert again.json()["project_id"] == primary
    assert native.user_rows["ordinary"].domain_id == "account"
    assert native.user_rows["ordinary"].default_project_id == "work-a"
    assert all(assignment in [vars(row) for row in native.raw] for assignment in before)
    assert native.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("revoked", ["user", "domain"])
async def test_provider_policy_wait_cannot_publish_a_disabled_identity_or_domain(native_login, monkeypatch, revoked):
    client, n = native_login
    await domain_projects.ensure_login_access("ordinary", "tenant-a")
    enforce_policy = auth._enforce_session_policy

    async def disable_after_policy(*args):
        await enforce_policy(*args)
        if revoked == "user":
            n.user_rows["ordinary"].enabled = False
        else:
            n.domain_rows["account"].enabled = False

    monkeypatch.setattr(auth, "_enforce_session_policy", disable_after_policy)
    response = await provider_login(client, monkeypatch)
    assert response.status_code == (401 if revoked == "user" else 403)
    assert "token" not in response.json() and "refresh_token" not in response.json()
    assert not any(pid for kind, pid in n.exchanges if kind == "token")
    assert all(sess.session.close.call_count == 1 for sess in n.sessions)


async def provider_login(client, monkeypatch, username="ordinary"):
    # Upstream identity is the synthetic boundary; scope preparation, JWT and
    # browser-session issuance below it execute the real public callback path.
    monkeypatch.setattr(
        domain_auth,
        "get_settings",
        lambda: SimpleNamespace(frontend_base_url="http://test", public_api_base="http://test"),
    )
    monkeypatch.setattr(
        domain_auth,
        "complete_authorization",
        AsyncMock(
            return_value=domain_auth.FederatedLogin(
                unscoped_token=f"native:{username}:",
                user_id=username,
                username=username,
                domain_id="tenant-a",
                domain_name="tenant-a",
                provider_id="cfg:organization_sso",
                provider_revision=1,
                provider_kind="oidc",
                login_email="actual@example.test",
            )
        ),
    )
    monkeypatch.setattr(domain_auth, "require_provider", AsyncMock(return_value=row(_organization=None)))
    monkeypatch.setattr(domain_auth, "mark_provider_verified", AsyncMock())
    monkeypatch.setattr(domain_auth, "_revoke_quietly", AsyncMock())
    return await client.post(
        "/api/v1/auth/providers/callback", json={"code": "verified-synthetic-code", "state": "verified-state-" * 4}
    )


@pytest.mark.asyncio
async def test_personal_landing_keeps_legacy_home_and_provider_origin_distinct(native_login, monkeypatch):
    client, native = native_login
    native.user_rows["ordinary"].domain_id = "tenant-b"
    response = await provider_login(client, monkeypatch)
    assert response.status_code == 200, response.text
    body = response.json()
    primary = account_spaces.personal_project("ordinary", ks=native)
    assert (body["domain_id"], body["identity_domain_id"], body["project_id"]) == (
        "personal",
        "tenant-b",
        primary["id"],
    )
    assert native.user_rows["ordinary"].default_project_id == "work-a"
    claims = jwt_service.verify_refresh(body["refresh_token"])
    stored = await session_store.get_session(claims["jti"])
    assert (stored["domain_id"], stored["identity_domain_id"]) == ("personal", "tenant-b")
    assert stored["provider_domain_id"] == "tenant-a"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_personal_login_does_not_bootstrap_missing_organization_default(native_login, monkeypatch, method):
    client, native = native_login
    del native.project_rows["default-a"]
    native.raw = [
        assignment for assignment in native.raw if assignment.scope.get("project", {}).get("id") != "default-a"
    ]
    response = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert response.status_code == 200, response.text
    assert response.json()["domain_id"] == "personal"
    assert not any(
        project.name == "Default" for project in native.project_rows.values() if project.domain_id == "tenant-a"
    )
    assert not domain_projects.has_manager("ordinary", "tenant-a")


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_users_in_accounts_get_distinct_private_personal_projects(native_login, monkeypatch, method):
    client, native = native_login
    native.user_rows["participant"] = row(
        id="participant", name="participant", enabled=True, domain_id="account", email="participant@example.test"
    )
    first = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert first.status_code == 200, first.text
    second = (
        await login(client, username="participant")
        if method == "password"
        else await provider_login(client, monkeypatch, "participant")
    )
    assert second.status_code == 200, second.text
    assert first.json()["project_id"] != second.json()["project_id"]
    for response, uid in ((first, "ordinary"), (second, "participant")):
        body = response.json()
        assert body["domain_id"] == "personal" and body["identity_domain_id"] == "account"
        assert set(body["roles"]) == {"member"} and body["can_write"] is True
        assert body["is_domain_manager"] is False
        project = native.project_rows[body["project_id"]]
        assert project.afterglow_personal_user_id == uid
        assert native.user_rows[uid].domain_id == "account"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_rejected_initial_member_never_issues_a_projectless_fallback_session(native_login, monkeypatch, method):
    from fastapi import HTTPException

    client, n = native_login
    del n.project_rows["default-a"]
    n.raw = []
    original = n.roles.grant

    def reject_member(role, **kwargs):
        if role == "member":
            raise HTTPException(403, "Member assignment rejected")
        return original(role, **kwargs)

    monkeypatch.setattr(n.roles, "grant", reject_member)
    response = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert response.status_code == 403, response.text
    assert "token" not in response.json() and "refresh_token" not in response.json()
    assert not any(pid for kind, pid in n.exchanges if kind == "token")
    personal = [project for project in n.project_rows.values() if project.domain_id == "personal"]
    assert len(personal) == 1 and personal[0].enabled is False


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["wrong_subject", "wrong_project", "wrong_home"])
async def test_login_rejects_substituted_native_subject_project_or_home(native_login, tamper):
    client, n = native_login
    await domain_projects.ensure_login_access("ordinary", "tenant-a")
    setattr(n, tamper, True)
    response = await login(client)
    assert response.status_code == 403
    assert "token" not in response.json()
    n.failures.assert_not_awaited()
    assert all(sess.session.close.call_count == 1 for sess in n.sessions)


@pytest.mark.asyncio
async def test_disabled_password_policy_does_not_exchange_or_increment_bad_password(native_login):
    client, n = native_login
    n.policy_enabled = False
    response = await login(client, password="bad")
    assert response.status_code == 403
    assert response.json()["code"] == "password_disabled"
    assert n.exchanges == []
    assert n.calls == []
    n.failures.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("outage,status,failures", [(False, 401, 1), (True, 503, 0)])
async def test_only_password_rejection_counts_toward_lockout(native_login, outage, status, failures):
    client, n = native_login
    if outage:
        n.password_error = RuntimeError("directory unavailable")
    response = await login(client, password="bad")
    assert response.status_code == status
    assert n.failures.await_count == failures
    assert n.calls == []
    assert all(sess.session.close.call_count == 1 for sess in n.sessions)


@pytest.mark.asyncio
async def test_authenticate_existing_caller_still_selects_requested_project(native_login):
    _, n = native_login
    n.user_rows["ordinary"].domain_id = "tenant-a"
    data = keystone.authenticate("ordinary", "valid", "Work", "tenant-a")
    assert data["user_id"] == "ordinary"
    assert data["project_id"] == "work-a"
    assert n.exchanges == [("password", ""), ("token", "work-a")]
    assert all(sess.session.close.call_count == 1 for sess in n.sessions)


def test_owned_operation_closes_every_session_and_clears_authority():
    operation = NativeOperation()
    first = SimpleNamespace(session=SimpleNamespace(close=Mock()))
    second = SimpleNamespace(session=SimpleNamespace(close=Mock()))
    with operation:
        operation.own_session(first)
        operation.own_session(first)
        operation.own_session(second)
        operation.read(("example",), lambda: "observed")
    first.session.close.assert_called_once()
    second.session.close.assert_called_once()
    assert operation.reads == {}


@pytest.mark.parametrize("original_error", [False, True])
def test_cleanup_attempts_every_session_and_preserves_original_error(original_error):
    first = SimpleNamespace(session=SimpleNamespace(close=Mock()))
    second = SimpleNamespace(session=SimpleNamespace(close=Mock(side_effect=RuntimeError("close failed"))))
    operation = NativeOperation()
    expected = ValueError if original_error else RuntimeError
    with pytest.raises(expected, match="operation failed" if original_error else "close failed"):
        with operation:
            operation.own_session(first)
            operation.own_session(second)
            if original_error:
                raise ValueError("operation failed")
    first.session.close.assert_called_once()
    second.session.close.assert_called_once()
    assert operation.reads == {}


@pytest.mark.asyncio
async def test_cancelled_operation_drains_native_work_before_closing_sessions():
    import asyncio
    import threading

    entered = threading.Event()
    release = threading.Event()
    observed = []
    session = SimpleNamespace(session=SimpleNamespace(close=Mock(side_effect=lambda: observed.append("closed"))))
    operation = NativeOperation()

    def native_read():
        entered.set()
        assert release.wait(timeout=5)
        assert session.session.close.call_count == 0
        operation.read(("read",), lambda: "finished")
        observed.append("read finished")

    async def request():
        async with operation:
            operation.own_session(session)
            await operation.run(native_read)

    task = asyncio.create_task(request())
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        session.session.close.assert_not_called()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert observed == ["read finished", "closed"]
    assert operation.reads == {}


@pytest.mark.asyncio
async def test_async_cleanup_preserves_operation_error_and_closes_all_sessions():
    first = SimpleNamespace(session=SimpleNamespace(close=Mock()))
    second = SimpleNamespace(session=SimpleNamespace(close=Mock(side_effect=RuntimeError("close failed"))))
    with pytest.raises(ValueError, match="operation failed"):
        async with NativeOperation() as operation:
            operation.own_session(first)
            operation.own_session(second)
            raise ValueError("operation failed")
    first.session.close.assert_called_once()
    second.session.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_exact_personal_landing_does_not_enumerate_native_memberships(native_login, monkeypatch, method):
    client, native = native_login
    # Identity, Personal provenance, role graph and exact native scope exchange
    # remain real. The unrelated user-membership listing is no longer on the
    # password or completed-provider login critical path.
    listing = Mock(side_effect=AssertionError("Unnecessary membership enumeration"))
    monkeypatch.setattr(keystone, "list_projects", listing)
    response = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert response.status_code == 200, response.text
    listing.assert_not_called()
    primary = response.json()["project_id"]
    assert any(kind == "token" and project == primary for kind, project in native.exchanges)
    native.roles.revoke("member", user="ordinary", project=primary)
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": response.json()["refresh_token"]})
    # Revoking the only Personal membership removes working-domain authority
    # before project scope fallback is considered (unlike an organization that
    # still has its independent Default membership).
    assert refreshed.status_code == 403
    assert "token" not in refreshed.json()
