"""Login behavior through real authority logic with synthetic native transport."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient
from keystoneauth1.exceptions.http import Unauthorized

from app.api.identity import auth
from app.main import app
from app.services import domain_auth, domain_projects, jwt_service, keystone, session_store
from app.services.native_operation import NativeOperation
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_projects import domain_native as domain_native
from tests.test_domain_projects import grant, row

pytestmark = pytest.mark.usefixtures("ownership_journal")


@pytest.fixture
async def native_login(monkeypatch, domain_native):
    n = domain_native
    n.exchanges = []
    n.sessions = []
    n.wrong_subject = False
    n.wrong_project = False
    n.wrong_home = False
    n.policy_enabled = True
    n.password_error = None
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
            if n.password_error:
                raise n.password_error
            if self.kwargs["password"] != "valid":
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
    monkeypatch.setattr(keystone.ks_session, "Session", session)
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
async def test_saved_default_login_exchanges_only_preferred_project(native_login, monkeypatch, method):
    client, n = native_login
    await domain_projects.ensure_login_access("ordinary", "tenant-a")
    n.calls.clear()
    response = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project_id"] == body["default_project_id"] == "work-a"
    assert body["project_name"] == "Work"
    assert body["can_write"] is False and body["is_domain_manager"] is False
    assert jwt_service.verify_access(body["token"])["project_id"] == "work-a"
    claims = jwt_service.verify_refresh(body["refresh_token"])
    assert (await session_store.get_session(claims["jti"]))["project_id"] == "work-a"
    assert [pid for kind, pid in n.exchanges if kind == "token" and pid] == ["work-a"]
    assert n.calls == []
    assert all(sess.session.close.call_count == 1 for sess in n.sessions)


@pytest.mark.asyncio
async def test_repair_login_preserves_saved_project_preference(native_login):
    client, n = native_login
    response = await login(client)
    assert response.status_code == 200, response.text
    assert response.json()["project_id"] == "work-a"
    assert [(kind, pid) for kind, pid in n.exchanges if kind == "token" and pid] == [("token", "work-a")]
    assert domain_projects.default_project("tenant-a")["id"] == "default-a"
    assert "project_reader" in {r.role["id"] for r in n.assignments(project="default-a", user="ordinary")}
    assert all(sess.session.close.call_count == 1 for sess in n.sessions)


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
            n.domain_rows["tenant-a"].enabled = False

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
    monkeypatch.setattr(domain_auth, "require_provider", AsyncMock())
    monkeypatch.setattr(domain_auth, "mark_provider_verified", AsyncMock())
    monkeypatch.setattr(domain_auth, "_revoke_quietly", AsyncMock())
    return await client.post(
        "/api/v1/auth/providers/callback", json={"code": "verified-synthetic-code", "state": "verified-state-" * 4}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
@pytest.mark.parametrize("preference", ["unset", "foreign", "disabled", "revoked", "deleted", "missing"])
async def test_unavailable_saved_project_falls_back_without_changing_preference(
    native_login, monkeypatch, method, preference
):
    client, n = native_login
    saved = "work-a"
    if preference == "unset":
        saved = ""
    elif preference == "foreign":
        saved = "work-b"
        n.raw.append(grant("reader", user="ordinary", project=saved))
    elif preference == "disabled":
        n.project_rows[saved].enabled = False
    elif preference in {"revoked", "deleted"}:
        n.raw = [r for r in n.raw if r.scope.get("project", {}).get("id") != saved]
        if preference == "deleted":
            del n.project_rows[saved]
    else:
        saved = "missing-project"
    n.user_rows["ordinary"].default_project_id = saved
    response = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert response.status_code == 200, response.text
    assert response.json()["project_id"] == response.json()["default_project_id"] == "default-a"
    assert [pid for kind, pid in n.exchanges if kind == "token" and pid] == ["default-a"]
    assert n.user_rows["ordinary"].default_project_id == saved


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_initial_home_ignores_foreign_saved_project_and_provider_origin(native_login, monkeypatch, method):
    client, n = native_login
    n.user_rows["ordinary"].domain_id = "tenant-b"
    response = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["domain_id"], body["identity_domain_id"], body["project_id"], body["default_project_id"]) == (
        "tenant-b",
        "tenant-b",
        "default-b",
        "default-b",
    )
    assert n.user_rows["ordinary"].default_project_id == "work-a"
    assert jwt_service.verify_access(body["token"])["project_id"] == "default-b"
    claims = jwt_service.verify_refresh(body["refresh_token"])
    session = await session_store.get_session(claims["jti"])
    assert (session["domain_id"], session["identity_domain_id"], session["project_id"]) == (
        "tenant-b",
        "tenant-b",
        "default-b",
    )
    if method == "provider":
        assert session["provider_domain_id"] == "tenant-a"
    assert [pid for kind, pid in n.exchanges if kind == "token" and pid] == ["default-b"]
    assert all(sess.session.close.call_count == 1 for sess in n.sessions)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_first_login_prepares_default_before_automatic_home_scope(native_login, monkeypatch, method):
    client, n = native_login
    del n.project_rows["default-a"]
    n.raw = [r for r in n.raw if r.scope.get("project", {}).get("id") != "default-a"]
    response = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert response.status_code == 200, response.text
    assert response.json()["project_id"] == "work-a"
    assert response.json()["default_project_id"] == "work-a"
    assert [pid for kind, pid in n.exchanges if kind == "token" and pid] == ["work-a"]
    assert any(r.role["id"] == "project_owner" for r in n.assignments(project="created-default", user="ordinary"))
    assert not domain_projects.has_manager("ordinary", "tenant-a")


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_projectless_first_login_then_participant_receive_real_default_scope(native_login, monkeypatch, method):
    client, n = native_login
    del n.project_rows["default-a"]
    n.raw = []
    n.user_rows["participant"] = row(
        id="participant", name="participant", enabled=True, domain_id="tenant-a", email="actual@example.test"
    )
    first = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert first.status_code == 200, first.text
    creator = first.json()
    assert creator["project_id"] == creator["default_project_id"] == "created-default"
    assert creator["project_name"] == "Default"
    assert "project_owner" in creator["roles"] and creator["can_write"] is True
    assert creator["is_domain_manager"] is False
    assert "token" in creator and "refresh_token" in creator
    n.calls.clear()
    joined = (
        await login(client, username="participant")
        if method == "password"
        else await provider_login(client, monkeypatch, "participant")
    )
    assert joined.status_code == 200, joined.text
    participant = joined.json()
    assert participant["project_id"] == participant["default_project_id"] == "created-default"
    assert participant["roles"] == ["project_reader", "reader"]
    assert participant["can_write"] is False and participant["is_domain_manager"] is False
    assert {p.id for p in n.project_rows.values() if p.domain_id == "tenant-a" and p.name == "Default"} == {
        "created-default"
    }
    n.calls.clear()
    again = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert again.status_code == 200, again.text
    assert again.json()["project_id"] == "created-default"
    assert n.calls == []
    assert all(sess.session.close.call_count == 1 for sess in n.sessions)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_rejected_initial_owner_never_issues_a_projectless_fallback_session(native_login, monkeypatch, method):
    from fastapi import HTTPException

    client, n = native_login
    del n.project_rows["default-a"]
    n.raw = []
    original = n.roles.grant

    def reject_owner(role, **kwargs):
        if role == "project_owner":
            raise HTTPException(403, "Owner assignment rejected")
        return original(role, **kwargs)

    monkeypatch.setattr(n.roles, "grant", reject_owner)
    response = await login(client) if method == "password" else await provider_login(client, monkeypatch)
    assert response.status_code == 403, response.text
    assert "token" not in response.json() and "refresh_token" not in response.json()
    assert not any(pid for kind, pid in n.exchanges if kind == "token")
    assert not any(p.name == "Default" and p.enabled for p in n.project_rows.values() if p.domain_id == "tenant-a")


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
