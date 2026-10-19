"""Real enrollment persistence and mutable native-directory behavioral boundaries.

SMTP and Keystone are deterministic provider adapters, not assertions about source
text or mock forwarding. MariaDB concurrency is covered in test_domain_iam_db.
"""

import asyncio
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_token_info, require_domain_manager
from app.api.identity import iam, onboarding
from app.database import get_session
from app.models.domain_iam import DomainEnrollment
from app.services import domain_auth, domain_iam, domain_projects, identity_roles, keystone, project_service
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_project_membership_roles import PROJECT, Membership, assignment, rid

pytestmark = pytest.mark.usefixtures("ownership_journal")

PASSWORD = "correct-long-password"


@pytest.fixture
def directory(monkeypatch):
    state = Membership()
    state.managers = {"domain-manager"}
    state.default_direct = []
    state.personal_domains = {}
    state.personal_projects = {}
    state.personal_direct = []
    state.system_admins = {"system-admin"}
    state.users = {}
    state.sent = []
    state.deliver = True
    state.policy = domain_auth.LoginPolicy(domain_id="domain")
    state.settings = SimpleNamespace(
        os_username="operator",
        auth=SimpleNamespace(public_signup_enabled=False, signup_email_domains=[]),
        service_manila_enabled=False,
        smtp_enabled=True,
        smtp_host="smtp.test.invalid",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        smtp_from_address="noreply@test.invalid",
        smtp_from_name="Afterglow",
        smtp_use_tls=True,
        smtp_timeout_seconds=5,
        frontend_base_url="https://ui.test.invalid",
        smtp_invitation_token_expiry_days=7,
        site_name="Afterglow",
        monitoring_auto_sg_enabled=False,
        monitoring_scrape_cidr="",
        os_auth_url="https://identity.test.invalid/v3",
        os_interface="internal",
        os_region_name="RegionOne",
        ssl_verify=True,
    )
    for uid in ["owner", "admin", "member", "domain-manager", "system-admin", "operator", "foreign"]:
        state.users[uid] = SimpleNamespace(
            id=uid,
            name=uid,
            email=f"{uid}@test.invalid",
            enabled=True,
            domain_id="other" if uid == "foreign" else "domain",
            password=PASSWORD,
        )
    state.creates = []
    state.updates = []

    def create_user(name, email, password, domain, enabled, **extra):
        if any(u.name == name and u.domain_id == domain for u in state.users.values()):
            raise HTTPException(409, "Duplicate username")
        uid = f"created-{len(state.creates)}"
        user = SimpleNamespace(
            id=uid, name=name, email=email, password=password, domain_id=domain, enabled=enabled, **extra
        )
        state.users[uid] = user
        state.creates.append(uid)
        return user

    def update_user(uid, **attrs):
        state.updates.append((uid, attrs))
        for key, value in attrs.items():
            setattr(state.users[uid], key, value)
        return state.users[uid]

    def get_user(uid):
        if uid not in state.users:
            raise HTTPException(404, "User not found")
        return state.users[uid]

    def delete_user(uid):
        state.users.pop(uid, None)
        state.direct = [row for row in state.direct if row.get("user", {}).get("id") != uid]

    def get_project(pid):
        if pid == "default-project":
            return SimpleNamespace(id=pid, name="Default", domain_id="domain", enabled=True)
        if pid == PROJECT:
            if state.project is None:
                raise HTTPException(404, "Project not found")
            return state.project
        if pid in state.personal_projects:
            return state.personal_projects[pid]
        return SimpleNamespace(id=pid, domain_id="other", enabled=True)

    state.ks.users = SimpleNamespace(
        get=get_user,
        list=lambda domain=None, group=None: [
            u
            for u in state.users.values()
            if (domain is None or u.domain_id == domain) and (group is None or u.id in state.groups.get(group, []))
        ],
        create=create_user,
        update=update_user,
        delete=delete_user,
    )
    state.project = SimpleNamespace(
        id=PROJECT, name="Intended project", domain_id="domain", enabled=True, description=""
    )

    def projects(**kwargs):
        rows = (
            [state.project, get_project("default-project")]
            if state.project is not None
            else [get_project("default-project")]
        )
        rows.extend(state.personal_projects.values())
        return [
            p
            for p in rows
            if p.domain_id == kwargs.get("domain", p.domain_id)
            and p.name == kwargs.get("name", p.name)
            and (
                "user" not in kwargs
                or project_service._access(assignments(p.id, effective=True), state.catalog, kwargs["user"])["roles"]
            )
        ]

    def create_project(name, domain, enabled, **extra):
        pid = f"personal-default-{len(state.personal_projects)}"
        project = SimpleNamespace(id=pid, name=name, domain_id=domain, parent_id=domain, enabled=enabled, **extra)
        state.personal_projects[pid] = project
        return project

    def update_project(pid, **attrs):
        project = state.personal_projects[pid]
        for key, value in attrs.items():
            setattr(project, key, value)
        return project

    def delete_project(pid):
        state.personal_projects.pop(pid, None)
        state.personal_direct[:] = [r for r in state.personal_direct if r["scope"]["project"]["id"] != pid]

    state.ks.projects = SimpleNamespace(
        get=get_project,
        list=projects,
        create=create_project,
        update=update_project,
        delete=delete_project,
    )
    state.ks.groups = SimpleNamespace(
        list=lambda domain=None, user=None: (
            [SimpleNamespace(id="team", name="Team", domain_id=domain or "domain")]
            if (domain is None or domain == "domain") and (user is None or user in state.groups.get("team", []))
            else []
        ),
        get=lambda gid: SimpleNamespace(id=gid, name="Team", domain_id="domain"),
    )

    def create_domain(name, enabled, **extra):
        did = f"personal-domain-{len(state.personal_domains)}"
        if any(d.name == name for d in state.personal_domains.values()):
            raise HTTPException(409, "Native domain names are globally unique")
        domain = SimpleNamespace(id=did, name=name, enabled=enabled, **extra)
        state.personal_domains[did] = domain
        return domain

    def update_domain(did, **attrs):
        domain = state.personal_domains[did]
        for key, value in attrs.items():
            setattr(domain, key, value)
        return domain

    state.ks.domains = SimpleNamespace(
        get=lambda did: (
            state.personal_domains.get(did)
            or SimpleNamespace(
                id=did,
                name="Intended domain" if did == "domain" else did,
                enabled=True,
            )
        ),
        list=lambda **kwargs: (
            [SimpleNamespace(id=did, name=did, enabled=True) for did in ("domain", "other")]
            + list(state.personal_domains.values())
        ),
        create=create_domain,
        update=update_domain,
        delete=lambda did: state.personal_domains.pop(did, None),
    )
    native_assignments = state.assignments

    def assignments(project=None, effective=False, user=None, domain=None, system=None, group=None):
        if domain:
            return []
        if system:
            if group is not None:
                return []
            return [
                {"user": {"id": uid}, "role": {"id": rid("admin")}, "scope": {"system": {"all": True}}}
                for uid in state.system_admins
                if user is None or user == uid
            ]
        rows = []
        if project in {None, PROJECT}:
            rows.extend(native_assignments(PROJECT, effective))
        if project in {None, "default-project"}:
            rows.extend(state.default_direct)
            rows.extend(
                {"user": {"id": uid}, "role": {"id": rid("manager")}, "scope": {"project": {"id": "default-project"}}}
                for uid in state.managers
            )
        rows.extend(r for r in state.personal_direct if project is None or r["scope"]["project"]["id"] == project)
        if user is not None:
            rows = [row for row in rows if row.get("user", {}).get("id") == user]
        return rows

    state.ks.role_assignments.list = assignments

    def grant(role_id, *, user, project):
        if project == PROJECT:
            return state.grant(role_id, user=user, project=project)
        target = state.default_direct if project == "default-project" else state.personal_direct
        assert project == "default-project" or project in state.personal_projects
        state.calls.append(("grant", user, role_id))
        scoped = [r for r in target if r["scope"]["project"]["id"] == project]
        if role_id not in project_service._direct_ids(scoped, user):
            target.append({"user": {"id": user}, "role": {"id": role_id}, "scope": {"project": {"id": project}}})

    def revoke(role_id, *, user, project):
        if project == PROJECT:
            return state.revoke(role_id, user=user, project=project)
        target = state.default_direct if project == "default-project" else state.personal_direct
        assert project == "default-project" or project in state.personal_projects
        state.calls.append(("revoke", user, role_id))
        target[:] = [
            r
            for r in target
            if not (r["user"]["id"] == user and r["role"]["id"] == role_id and r["scope"]["project"]["id"] == project)
        ]

    state.ks.roles.grant = grant
    state.ks.roles.revoke = revoke
    conn = SimpleNamespace(close=lambda: None)

    @asynccontextmanager
    async def graph_lock(connection):
        async with state.lock:
            yield SimpleNamespace(assert_owned=AsyncMock())

    async def get_policy(did, **kwargs):
        assert did in {"domain", "other"} or did in state.personal_domains
        return state.policy if did in {"domain", "other"} else domain_auth.LoginPolicy(domain_id=did)

    async def smtp_send(message, **kwargs):
        if not state.deliver:
            raise ConnectionError("SMTP unavailable")
        state.sent.append(message)
        return {}, "accepted"

    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: state.ks)
    monkeypatch.setattr(keystone, "get_admin_project_connection", lambda: conn)
    monkeypatch.setattr(keystone, "get_settings", lambda: state.settings)
    monkeypatch.setattr(domain_iam, "get_settings", lambda: state.settings)
    monkeypatch.setattr("app.services.enrollment_policy.get_settings", lambda: state.settings)
    monkeypatch.setattr("app.services.account_recovery.get_settings", lambda: state.settings)
    monkeypatch.setattr("app.config.get_settings", lambda: state.settings)
    monkeypatch.setattr(identity_roles, "_trusted_catalog", lambda: state.catalog)
    monkeypatch.setattr(identity_roles, "load_catalog", lambda connection: state.catalog)
    monkeypatch.setattr(identity_roles, "_graph_lock", graph_lock)
    monkeypatch.setattr(identity_roles, "_session_ready", AsyncMock())
    monkeypatch.setattr(identity_roles, "_applied", AsyncMock())
    monkeypatch.setattr(project_service, "_membership_write", state.write)
    monkeypatch.setattr(project_service.cache, "invalidate", AsyncMock())
    monkeypatch.setattr(project_service.activity, "record", AsyncMock())
    monkeypatch.setattr(domain_auth, "get_policy", get_policy)
    monkeypatch.setattr("aiosmtplib.send", smtp_send)
    # Role/member authority uses actual Default native grants above. Projection
    # provider operations are exercised in test_domain_projects, not SMTP tests.
    monkeypatch.setattr(domain_projects, "sync_manager_access", AsyncMock())
    monkeypatch.setattr(domain_projects, "apply_default_quotas", AsyncMock())
    monkeypatch.setattr(
        project_service, "inspect_project_empty", AsyncMock(return_value={"can_delete": True, "resources": []})
    )
    return state


@pytest_asyncio.fixture
async def enrollments(tmp_path, monkeypatch):
    from app.models.domain_quotas import DomainQuotaPolicy
    from app.models.enrollment_policy import EnrollmentPolicy, SignupRequest

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'enrollments.sqlite'}")
    async with engine.begin() as conn:
        for model in (DomainEnrollment, EnrollmentPolicy, SignupRequest, DomainQuotaPolicy):
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.services.enrollment_policy.get_session_factory", lambda: factory)
    yield factory
    await engine.dispose()


def manager(uid="domain-manager", did="domain"):
    return {"user_id": uid, "username": uid, "domain_id": did, "project_id": PROJECT, "is_system_admin": False}


def email_token(message):
    parts = [
        part.get_payload(decode=True).decode() for part in message.walk() if part.get_content_type() == "text/plain"
    ]
    return re.search(r"/(?:invitations|registrations)/([A-Za-z0-9_-]+)", "\n".join(parts)).group(1)


async def invite(directory, factory, email="new@test.invalid"):
    async with factory() as session:
        result = await domain_iam.invite(
            {"email": email, "project_id": PROJECT, "role_ids": [rid("project_member")]}, manager(), session
        )
    return result, email_token(directory.sent[-1])


@pytest.mark.asyncio
@pytest.mark.parametrize("uid", ["member", "admin", "owner"])
async def test_project_roles_do_not_authorize_domain_iam(directory, uid):
    with pytest.raises(HTTPException) as denied:
        await domain_iam.list_resources("users", manager(uid))
    assert denied.value.status_code == 403
    assert not directory.creates and not directory.updates


@pytest.mark.asyncio
async def test_own_domain_lists_and_foreign_targets(directory):
    users = await domain_iam.list_resources("users", manager())
    assert "foreign" not in {u["id"] for u in users["items"]}
    assert next(u for u in users["items"] if u["id"] == "domain-manager")["protected"]
    for kind in ["projects", "groups"]:
        rows = await domain_iam.list_resources(kind, manager())
        assert all(row["domain_id"] == "domain" for row in rows["items"])
    with pytest.raises(HTTPException) as denied:
        await domain_iam.update_user("foreign", {"password": PASSWORD}, manager())
    assert denied.value.status_code == 403
    assert not directory.updates


@pytest.mark.asyncio
@pytest.mark.parametrize("uid", ["domain-manager", "system-admin", "operator"])
async def test_privileged_accounts_never_password_reset(directory, uid):
    with pytest.raises(HTTPException) as denied:
        await domain_iam.update_user(uid, {"password": "replacement-password"}, manager())
    assert denied.value.status_code == 403
    assert directory.users[uid].password == PASSWORD
    assert not directory.updates


@pytest.mark.asyncio
async def test_manager_created_personal_identity_is_not_target_credential_managed(directory, enrollments):
    async with enrollments() as session:
        user = await domain_iam.create_user(
            {
                "personal_domain_name": "Personal",
                **{
                    "name": "created",
                    "email": "Created@Test.Invalid",
                    "password": PASSWORD,
                    "enabled": True,
                    "project_id": None,
                    "role_ids": [],
                },
            },
            manager(),
            session,
        )
    assert user["domain_id"] == "domain" and user["email"] == "Created@test.invalid"
    assert user["identity_domain_id"] != "domain" and user["identity_domain_name"] == "Personal"
    assert directory.users[user["id"]].domain_id == user["identity_domain_id"]
    with pytest.raises(HTTPException) as denied:
        await domain_iam.update_user(user["id"], {"password": "different-long-password", "enabled": False}, manager())
    assert denied.value.status_code == 403 and directory.users[user["id"]].password == PASSWORD


@pytest.mark.asyncio
async def test_native_system_role_and_foreign_project_denied(directory):
    for pid, roles in [(PROJECT, [rid("admin")]), ("foreign-project", [rid("project_member")])]:
        with pytest.raises(HTTPException) as denied:
            await domain_iam.validate_invitation_roles(pid, roles, manager())
        assert denied.value.status_code == 403
    assert not directory.calls


@pytest.mark.asyncio
async def test_domain_authority_can_add_member_but_never_remove_last_owner(directory):
    # The domain manager is not a native project owner, but can manage native grades.
    directory.users["new"] = SimpleNamespace(
        id="new", name="new", email="new@test.invalid", enabled=True, domain_id="domain"
    )
    added = await project_service.replace_member_roles(
        PROJECT, "new", [rid("project_admin")], manager(), domain_management=True
    )
    assert added["is_manager"] and not added["is_owner"]
    with pytest.raises(HTTPException) as denied:
        await project_service.replace_member_roles(PROJECT, "owner", [], manager(), domain_management=True, remove=True)
    assert denied.value.status_code == 409
    assert (await project_service.get_project_access(PROJECT, "owner"))["is_owner"]
    directory.managers.clear()
    with pytest.raises(HTTPException) as revoked:
        await project_service.replace_member_roles(PROJECT, "new", [], manager(), domain_management=True, remove=True)
    assert revoked.value.status_code == 403


@pytest.mark.asyncio
async def test_invite_delivery_new_account_membership_and_single_use(directory, enrollments, monkeypatch):
    result, token = await invite(directory, enrollments)
    native_write = identity_roles._write
    owner_intents = []

    async def journaled_write(lease, fn, *args, **attrs):
        if fn == directory.ks.roles.grant and args[0] == rid("project_owner"):
            async with enrollments() as observer:
                persisted = await observer.get(DomainEnrollment, result["id"])
                intent = persisted.added_grants[-1]
                assert intent == {
                    "project_id": attrs["project"],
                    "domain_id": persisted.identity_domain_id,
                    "role_id": rid("project_owner"),
                    "phase": "applying",
                }
                assert not directory.personal_projects[attrs["project"]].enabled
                assert not directory.users[attrs["user"]].enabled
                owner_intents.append(intent)
        if fn == directory.ks.projects.update and attrs.get("enabled") is True:
            async with enrollments() as observer:
                persisted = await observer.get(DomainEnrollment, result["id"])
                assert {g["role_id"] for g in persisted.added_grants if g["phase"] == "confirmed"} == {
                    rid("project_owner"),
                    rid("manager"),
                    rid("project_reader"),
                }
                owner = await project_service._verify_unique_owner(
                    directory.ks, directory.catalog, args[0], persisted.user_id
                )
                assert owner["owner_user_id"] == persisted.user_id
        return await native_write(lease, fn, *args, **attrs)

    monkeypatch.setattr(identity_roles, "_write", journaled_write)
    assert result["status"] == "pending" and "token" not in result
    assert directory.sent[-1]["To"] == "new@test.invalid"
    async with enrollments() as session:
        row = (await session.execute(select(DomainEnrollment))).scalar_one()
        assert row.token_hash != token and row.email == "new@test.invalid"
        public = await domain_iam.invitation_info(token, session)
        assert public["domain_id"] == "domain" and public["project_name"] == "Intended project"
        account = await domain_iam.redeem(
            token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
        )
        assert directory.users[account["user_id"]].domain_id == account["identity_domain_id"] != "domain"
        assert directory.users[account["user_id"]].password == PASSWORD
        assert project_service._direct_ids(directory.personal_direct, account["user_id"]) == {
            rid("project_owner"),
            rid("manager"),
            rid("project_reader"),
        }
        assert project_service._direct_ids(directory.default_direct, account["user_id"]) == {rid("project_reader")}
        assert len(owner_intents) == 1
        assert (await project_service.get_project_access(PROJECT, account["user_id"]))["roles"] == [
            "member",
            "project_member",
            "project_reader",
            "reader",
        ]
        with pytest.raises(HTTPException) as used:
            await domain_iam.redeem(
                token, "invitation", session, name="different", password=PASSWORD, personal_domain_name="Personal"
            )
        assert used.value.status_code == 410
    assert len(directory.creates) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["rejected", "missing_readback", "lost_reply"])
async def test_personal_owner_failure_stays_disabled_until_exact_settlement(directory, enrollments, outcome):
    result, token = await invite(directory, enrollments)
    original_target = list(directory.direct)
    grant = directory.ks.roles.grant

    def owner_outcome(role_id, **attrs):
        if role_id != rid("project_owner"):
            return grant(role_id, **attrs)
        assert attrs["project"] in directory.personal_projects
        assert not directory.personal_projects[attrs["project"]].enabled
        if outcome == "rejected":
            raise HTTPException(403, "Native owner grant rejected")
        if outcome == "missing_readback":
            return
        grant(role_id, **attrs)
        raise ConnectionError("Native owner grant committed but reply lost")

    directory.ks.roles.grant = owner_outcome
    async with enrollments() as session:
        with pytest.raises(HTTPException) as failed:
            await domain_iam.redeem(
                token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
            )
        assert failed.value.status_code == 503
        row = await session.get(DomainEnrollment, result["id"])
        uid, pid, did = row.user_id, row.personal_project_id, row.identity_domain_id
        assert row.status == "recovery_required" and row.accepted_at is None
        assert row.added_grants[-1] == {
            "project_id": pid,
            "domain_id": did,
            "role_id": rid("project_owner"),
            "phase": "unknown",
        }
        assert not directory.personal_projects[pid].enabled and not directory.users[uid].enabled
        assert (rid("project_owner") in project_service._direct_ids(directory.personal_direct, uid)) is (
            outcome == "lost_reply"
        )
        assert not project_service._direct_ids(directory.default_direct, uid)
        assert directory.direct == original_target
        with pytest.raises(HTTPException) as unsettled:
            await domain_iam.revoke(row.id, manager(), session)
        assert unsettled.value.status_code == 503
        assert pid in directory.personal_projects and uid in directory.users
        await domain_iam.settle_enrollment_native_writes(
            row.id, manager("system-admin"), session, domain_id="domain", native_writes_settled=True
        )
        assert row.added_grants[-1]["native_present"] is (outcome == "lost_reply")
        await domain_iam.revoke(row.id, manager(), session)
        assert row.status == "revoked" and uid not in directory.users
        assert not directory.personal_direct and not directory.default_direct
        assert not directory.personal_projects and not directory.personal_domains
        assert directory.direct == original_target
        with pytest.raises(HTTPException) as replay:
            await domain_iam.redeem(
                token, "invitation", session, name="again", password=PASSWORD, personal_domain_name="Personal"
            )
        assert replay.value.status_code == 410


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_graph", ["missing_hierarchy", "manager_escalation"])
async def test_personal_default_requires_safe_owner_without_seeding(directory, enrollments, owner_graph):
    result, token = await invite(directory, enrollments)
    roles = [{"id": row["id"], "name": row["name"], "domain_id": row["domain_id"]} for row in directory.catalog]
    edges = [
        {"prior_role": {"id": row["id"]}, "implies": [{"id": child} for child in row["implied_role_ids"]]}
        for row in directory.catalog
        if row["id"] != rid("project_owner")
    ]
    if owner_graph == "manager_escalation":
        edges.append({"prior_role": {"id": rid("project_owner")}, "implies": [{"id": rid("manager")}]})
    directory.catalog = identity_roles._catalog(roles, edges)
    original_catalog = list(directory.catalog)
    original_target = list(directory.direct)
    async with enrollments() as session:
        with pytest.raises(HTTPException) as failed:
            await domain_iam.redeem(
                token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
            )
        assert failed.value.status_code == 503
        row = await session.get(DomainEnrollment, result["id"])
        assert row.status == "failed" and row.accepted_at is None
        assert row.user_id not in directory.users and not row.added_grants
        assert not directory.personal_direct and not directory.default_direct
        assert not directory.personal_projects and not directory.personal_domains
        assert directory.direct == original_target and directory.catalog == original_catalog


@pytest.mark.asyncio
async def test_personal_owner_conflict_never_activates_or_deletes_unowned_grant(directory, enrollments):
    result, token = await invite(directory, enrollments)
    grant = directory.ks.roles.grant
    foreign_grants = []

    def conflicting_owner(role_id, **attrs):
        grant(role_id, **attrs)
        if role_id == rid("project_owner"):
            grant(role_id, user="member", project=attrs["project"])
            foreign_grants.extend(row for row in directory.personal_direct if row["user"]["id"] == "member")

    directory.ks.roles.grant = conflicting_owner
    async with enrollments() as session:
        with pytest.raises(HTTPException) as failed:
            await domain_iam.redeem(
                token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
            )
        assert failed.value.status_code == 503
        row = await session.get(DomainEnrollment, result["id"])
        assert row.status == "recovery_required" and row.accepted_at is None
        assert not directory.personal_projects[row.personal_project_id].enabled
        assert row.user_id not in directory.users
        assert directory.personal_direct == foreign_grants
        assert foreign_grants and row.identity_domain_id in directory.personal_domains
        assert not project_service._direct_ids(directory.default_direct, row.user_id)


@pytest.mark.asyncio
async def test_invited_password_authenticates_only_intended_domain(directory, enrollments, monkeypatch):
    from keystoneauth1.exceptions.http import Unauthorized

    result, token = await invite(directory, enrollments)
    async with enrollments() as session:
        account = await domain_iam.redeem(
            token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
        )

    def access(uid, project_id=""):
        user = directory.users[uid]
        project = directory.ks.projects.get(project_id) if project_id else None
        return SimpleNamespace(
            user_id=uid,
            username=user.name,
            user_domain_id=user.domain_id,
            project_domain_id=project.domain_id if project else None,
            auth_token=f"native-{uid}",
            project_id=project_id,
            project_name=project.name if project else "",
            expires=datetime.now(UTC) + timedelta(hours=1),
            role_names=project_service._access(
                directory.ks.role_assignments.list(project=project_id, effective=True), directory.catalog, uid
            )["roles"]
            if project
            else [],
        )

    class PasswordProvider:
        def __init__(self, **attrs):
            self.attrs = attrs

        def get_access(self, session):
            for user in directory.users.values():
                if (
                    user.name == self.attrs["username"]
                    and user.domain_id == self.attrs["user_domain_id"]
                    and user.enabled
                    and user.password == self.attrs["password"]
                ):
                    return access(user.id)
            raise Unauthorized(message="Invalid native credentials")

    class TokenProvider:
        def __init__(self, **attrs):
            self.attrs = attrs

        def get_access(self, session):
            uid = self.attrs["token"].removeprefix("native-")
            project_id = self.attrs["project_id"]
            roles = project_service._access(
                directory.ks.role_assignments.list(project=project_id, effective=True), directory.catalog, uid
            )
            if not roles["roles"]:
                raise Unauthorized(message="Project inaccessible")
            return access(uid, project_id)

    monkeypatch.setattr(keystone.v3, "Password", PasswordProvider)
    monkeypatch.setattr(keystone.v3, "Token", TokenProvider)
    monkeypatch.setattr("keystoneclient.v3.client.Client", lambda **attrs: directory.ks)
    authenticated = await asyncio.to_thread(
        keystone.authenticate, "invitee", PASSWORD, "", account["identity_domain_id"]
    )
    assert authenticated["user_id"] == account["user_id"]
    assert authenticated["identity_domain_id"] == account["identity_domain_id"]
    with pytest.raises(Unauthorized):
        await asyncio.to_thread(keystone.authenticate, "invitee", PASSWORD, "", "other")
    directory.settings.auth.public_signup_enabled = True
    directory.settings.auth.signup_email_domains = ["test.invalid"]
    async with enrollments() as session:
        await domain_iam.register("signup@test.invalid", session)
        verified = await domain_iam.redeem(
            email_token(directory.sent[-1]),
            "registration",
            session,
            name="signup",
            password=PASSWORD,
            personal_domain_name="Personal",
        )
    signed_up = await asyncio.to_thread(keystone.authenticate, "signup", PASSWORD, "", verified["identity_domain_id"])
    assert (
        signed_up["user_id"] == verified["user_id"]
        and signed_up["identity_domain_id"] == verified["identity_domain_id"]
    )
    assert signed_up["project_id"] == domain_projects.default_project(verified["identity_domain_id"])["id"]
    assert "manager" in signed_up["roles"] and "project_reader" in signed_up["roles"]


@pytest.mark.asyncio
async def test_last_enabled_owner_cannot_be_disabled(directory):
    with pytest.raises(HTTPException) as denied:
        await domain_iam.update_user("owner", {"enabled": False}, manager())
    assert denied.value.status_code == 409
    assert directory.users["owner"].enabled


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["owner", "applying", "unknown", "settled"])
async def test_home_user_disable_preserves_joined_domain_ownership(directory, ownership_journal, state):
    from app.models.project_ownership import ProjectOwnershipTransfer

    project_id = "joined-project"
    directory.personal_projects[project_id] = SimpleNamespace(
        id=project_id,
        name="Joined project",
        domain_id="other",
        enabled=True,
    )
    if state == "owner":
        directory.personal_direct.append(
            {
                "user": {"id": "member"},
                "role": {"id": rid("project_owner")},
                "scope": {"project": {"id": project_id}},
            }
        )
    else:
        async with ownership_journal() as session:
            session.add(
                ProjectOwnershipTransfer(
                    id="joined-transfer",
                    project_id=project_id,
                    domain_id="other",
                    from_user_id="member",
                    to_user_id="foreign",
                    status=state,
                    stage="grant",
                )
            )
            await session.commit()

    app = FastAPI()
    app.include_router(iam.router, prefix="/api/v1/iam")
    app.dependency_overrides[require_domain_manager] = manager
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/v1/iam/users/member", json={"enabled": False})
    assert response.status_code == 409
    assert directory.users["member"].enabled is True
    assert not directory.updates


@pytest.mark.asyncio
async def test_existing_account_not_taken_over_and_authenticated_accept(directory, enrollments):
    result, token = await invite(directory, enrollments, "member@test.invalid")
    async with enrollments() as session:
        with pytest.raises(HTTPException) as exists:
            await domain_iam.redeem(
                token,
                "invitation",
                session,
                name="takeover",
                password="attacker-password",
                personal_domain_name="Personal",
            )
        assert exists.value.status_code == 409
        assert directory.users["member"].password == PASSWORD
        await session.rollback()
        with pytest.raises(HTTPException) as foreign:
            await domain_iam.redeem(
                token, "invitation", session, token_info=manager("foreign", "other"), personal_domain_name="Personal"
            )
        assert foreign.value.status_code == 403
        await session.rollback()
        with pytest.raises(HTTPException) as wrong:
            await domain_iam.redeem(
                token, "invitation", session, token_info=manager("owner"), personal_domain_name="Personal"
            )
        assert wrong.value.status_code == 403
        await session.rollback()
        accepted = await domain_iam.redeem(
            token, "invitation", session, token_info=manager("member"), personal_domain_name="Personal"
        )
        assert accepted["user_id"] == "member"
        assert (await project_service.get_project_access(PROJECT, "member"))["roles"] == [
            "member",
            "project_member",
            "project_reader",
            "reader",
        ]
    assert not directory.creates and not directory.updates


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["revoked", "expired", "accepted", "delivery_failed"])
async def test_invalid_enrollment_state_never_creates_account(directory, enrollments, status):
    result, token = await invite(directory, enrollments)
    async with enrollments() as session:
        row = await session.get(DomainEnrollment, result["id"])
        row.status = status
        await session.commit()
        with pytest.raises(HTTPException) as denied:
            await domain_iam.redeem(
                token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
            )
        assert denied.value.status_code == 410
    assert not directory.creates


@pytest.mark.asyncio
async def test_expiry_revocation_and_inviter_authority_change(directory, enrollments):
    result, token = await invite(directory, enrollments)
    async with enrollments() as session:
        await domain_iam.revoke(result["id"], manager(), session)
        with pytest.raises(HTTPException) as revoked:
            await domain_iam.invitation_info(token, session)
        assert revoked.value.status_code == 410
    result, token = await invite(directory, enrollments, "expiry@test.invalid")
    async with enrollments() as session:
        row = await session.get(DomainEnrollment, result["id"])
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        with pytest.raises(HTTPException) as expired:
            await domain_iam.redeem(
                token, "invitation", session, name="expired", password=PASSWORD, personal_domain_name="Personal"
            )
        assert expired.value.status_code == 410
    result, token = await invite(directory, enrollments, "revoked-manager@test.invalid")
    directory.managers.clear()
    async with enrollments() as session:
        with pytest.raises(HTTPException) as denied:
            await domain_iam.redeem(
                token, "invitation", session, name="revoked", password=PASSWORD, personal_domain_name="Personal"
            )
        assert denied.value.status_code == 403
    assert not directory.creates


@pytest.mark.asyncio
async def test_smtp_failure_never_reports_invitation_success(directory, enrollments):
    directory.deliver = False
    async with enrollments() as session:
        with pytest.raises(HTTPException) as failed:
            await domain_iam.invite(
                {"email": "new@test.invalid", "project_id": PROJECT, "role_ids": [rid("project_member")]},
                manager(),
                session,
            )
        assert failed.value.status_code == 503
        row = (await session.execute(select(DomainEnrollment))).scalar_one()
        assert row.status == "delivery_failed"
    assert not directory.sent and not directory.creates


@pytest.mark.asyncio
async def test_signup_opt_in_allowlist_verification_and_no_implicit_project(directory, enrollments):
    async with enrollments() as session:
        with pytest.raises(HTTPException) as disabled:
            await domain_iam.register("signup@test.invalid", session)
        assert disabled.value.status_code == 403
        assert not directory.sent and not directory.creates
        directory.settings.auth.public_signup_enabled = True
        directory.settings.auth.signup_email_domains = ["test.invalid"]
        with pytest.raises(HTTPException) as forbidden:
            await domain_iam.register("signup@foreign.invalid", session)
        assert forbidden.value.status_code == 403
        assert await domain_iam.register("signup@test.invalid", session) == {"accepted": True}
        assert not directory.creates  # Sending email is not account creation.
        token = email_token(directory.sent[-1])
        with pytest.raises(HTTPException) as fabricated:
            await domain_iam.redeem(
                "arbitrary-unverified-token",
                "registration",
                session,
                name="attacker",
                password=PASSWORD,
                personal_domain_name="Personal",
            )
        assert fabricated.value.status_code == 404
        account = await domain_iam.redeem(
            token, "registration", session, name="signup", password=PASSWORD, personal_domain_name="Personal"
        )
        assert account["domain_id"] == account["identity_domain_id"] != "domain"
        assert not project_service._direct_ids(directory.default_direct, account["user_id"])
        assert not (await project_service.get_project_access(PROJECT, account["user_id"]))["roles"]


@pytest.mark.asyncio
async def test_signup_and_invites_recheck_current_login_email_policy(directory, enrollments):
    result, token = await invite(directory, enrollments)
    directory.policy = domain_auth.LoginPolicy(domain_id="domain", allowed_email_domains=("different.invalid",))
    async with enrollments() as session:
        with pytest.raises(HTTPException) as changed:
            await domain_iam.redeem(
                token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
            )
        assert changed.value.status_code == 403
    assert not directory.creates


@pytest.mark.asyncio
async def test_routes_reject_secret_echo_and_client_role_injection(directory, enrollments):
    app = FastAPI()
    app.include_router(iam.router, prefix="/api/v1/iam")
    app.include_router(onboarding.router, prefix="/api/v1/auth")
    app.dependency_overrides[get_token_info] = lambda: manager()
    app.dependency_overrides[require_domain_manager] = lambda: manager()

    async def session_dep():
        async with enrollments() as session:
            yield session

    app.dependency_overrides[get_session] = session_dep
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path, body in [
            ("/api/v1/iam/users", {"name": "name", "email": "valid@test.invalid", "password": "secret"}),
            (
                "/api/v1/auth/registrations/accept",
                {"token": "secret-token", "name": "name", "password": PASSWORD, "role_ids": [rid("admin")]},
            ),
        ]:
            response = await client.post(path, json=body)
            assert response.status_code == 422
            assert "secret" not in response.text and PASSWORD not in response.text
            assert "no-store" in response.headers["Cache-Control"]
    assert not directory.creates


@pytest.mark.asyncio
async def test_domain_only_manager_can_read_and_manage_native_project(directory):
    info = {**manager(), "project_id": ""}
    choices = await project_service.assignable_roles(PROJECT, info, domain_management=True)
    assert choices["is_owner"] is False and choices["can_manage_owners"] is False
    members = await project_service.list_members(PROJECT, info, domain_management=True)
    assert {row["user_id"] for row in members["items"]} == {"owner", "admin", "member"}
    directory.default_direct.append(
        {
            "user": {"id": "foreign"},
            "role": {"id": rid("project_reader")},
            "scope": {"project": {"id": "default-project"}},
        }
    )
    added = await project_service.replace_member_roles(
        PROJECT, "foreign", [rid("project_member")], info, domain_management=True
    )
    assert added["domain_id"] == "other" and added["identity_read_only"]
    assert not added["is_manager"] and not added["is_owner"]
    assert "project_member" in added["roles"]
    assert directory.calls == [("grant", "foreign", rid("project_member"))]


@pytest.mark.asyncio
async def test_existing_federated_invitee_keeps_credentials_in_password_disabled_domain(directory, enrollments):
    directory.users["member"].federated = [{"idp_id": "trusted"}]
    directory.policy = domain_auth.LoginPolicy(domain_id="domain", password_enabled=False)
    result, token = await invite(directory, enrollments, "member@test.invalid")
    async with enrollments() as session:
        accepted = await domain_iam.redeem(
            token, "invitation", session, token_info=manager("member"), personal_domain_name="Personal"
        )
    assert accepted["user_id"] == "member" and directory.users["member"].password == PASSWORD
    assert not directory.creates and not directory.updates
    with pytest.raises(HTTPException) as denied:
        await domain_iam.update_user("member", {"password": "replacement-password"}, manager())
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_existing_email_signup_response_is_generic_and_never_resets(directory, enrollments):
    directory.settings.auth.public_signup_enabled = True
    directory.settings.auth.signup_email_domains = ["test.invalid"]
    async with enrollments() as session:
        assert await domain_iam.register("member@test.invalid", session) == {"accepted": True}
        token = email_token(directory.sent[-1])
        with pytest.raises(HTTPException) as exists:
            await domain_iam.redeem(
                token,
                "registration",
                session,
                name="new-name",
                password="attacker-password",
                personal_domain_name="Personal",
            )
        assert exists.value.status_code == 409
    assert directory.users["member"].password == PASSWORD and not directory.creates


@pytest.mark.asyncio
async def test_foreign_directory_response_fails_closed_before_publication(directory):
    directory.ks.groups.list = lambda **kwargs: [SimpleNamespace(id="other-team", name="Other", domain_id="other")]
    with pytest.raises(HTTPException) as denied:
        await domain_iam.list_resources("groups", manager())
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_cached_enrollment_row_is_refreshed_after_concurrent_revoke(directory, enrollments):
    result, token = await invite(directory, enrollments)
    async with enrollments() as reader:
        pending = await reader.get(DomainEnrollment, result["id"])
        assert pending.status == "pending"
        async with enrollments() as writer:
            await domain_iam.revoke(result["id"], manager(), writer)
        with pytest.raises(HTTPException) as revoked:
            await domain_iam.invitation_info(token, reader)
        assert revoked.value.status_code == 410


@pytest.mark.asyncio
async def test_system_admin_without_default_manager_grant_has_no_user_iam_context(directory):
    assert "system-admin" not in directory.managers
    app = FastAPI()
    app.include_router(iam.router, prefix="/api/v1/iam")
    app.dependency_overrides[get_token_info] = lambda: {**manager("system-admin"), "project_id": ""}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/iam/context")
    assert response.status_code == 403
    with pytest.raises(HTTPException) as denied:
        await domain_iam.context({**manager("system-admin"), "is_system_admin": True})
    assert denied.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "service", "service-alias"])
async def test_native_privileged_project_and_service_accounts_are_protected(directory, role):
    service_roles = identity_roles._catalog(
        [{"id": rid("service"), "name": "service"}, {"id": rid("service-alias"), "name": "service-alias"}],
        [{"prior_role": {"id": rid("service-alias")}, "implies": [{"id": rid("service")}]}],
    )
    directory.catalog.extend(service_roles)
    directory.direct.append(assignment("member", role))
    with pytest.raises(HTTPException) as denied:
        await domain_iam.update_user("member", {"password": "replacement-password"}, manager())
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as roles_denied:
        await project_service.replace_member_roles(PROJECT, "member", [], manager(), domain_management=True)
    assert roles_denied.value.status_code == 403
    assert directory.users["member"].password == PASSWORD and not directory.updates


@pytest.mark.asyncio
async def test_unassigned_foreign_privileged_name_does_not_block_domain_members(directory, enrollments):
    directory.catalog.extend(
        identity_roles._catalog(
            [{"id": "foreign-service", "name": "service", "domain_id": "other"}],
            [],
        )
    )
    users = await domain_iam.list_resources("users", manager())
    assert not next(user for user in users["items"] if user["id"] == "member")["protected"]
    await domain_iam.update_user("member", {"password": "replacement-password"}, manager())
    assert directory.users["member"].password == "replacement-password"
    _, token = await invite(directory, enrollments, "member@test.invalid")
    async with enrollments() as session:
        accepted = await domain_iam.redeem(token, "invitation", session, token_info=manager("member"))
    assert accepted["user_id"] == "member"
    assert rid("project_reader") in project_service._direct_ids(directory.default_direct, "member")


@pytest.mark.asyncio
@pytest.mark.parametrize("role_domain,status", [("domain", 403), ("other", 503)])
async def test_assigned_local_privileged_name_still_protects_credentials(directory, role_domain, status):
    directory.catalog.extend(
        identity_roles._catalog(
            [{"id": "local-service", "name": "service", "domain_id": role_domain}],
            [],
        )
    )
    directory.direct.append(
        {
            "user": {"id": "member"},
            "role": {"id": "local-service"},
            "scope": {"project": {"id": PROJECT}},
        }
    )
    with pytest.raises(HTTPException) as denied:
        await domain_iam.update_user("member", {"password": "replacement-password"}, manager())
    assert denied.value.status_code == status
    assert directory.users["member"].password == PASSWORD and not directory.updates


@pytest.mark.asyncio
async def test_unattributable_protection_graph_fails_closed(directory):
    directory.direct.append(
        {"user": {"id": "member"}, "role": {"id": "unknown-native-id"}, "scope": {"project": {"id": PROJECT}}}
    )
    with pytest.raises(HTTPException) as denied:
        await domain_iam.update_user("member", {"enabled": False}, manager())
    assert denied.value.status_code == 503 and directory.users["member"].enabled


@pytest.mark.asyncio
async def test_disabled_owner_cannot_satisfy_last_owner_role_removal(directory):
    directory.users["disabled-owner"] = SimpleNamespace(
        id="disabled-owner", name="disabled-owner", email="disabled@test.invalid", domain_id="domain", enabled=False
    )
    directory.direct.append(assignment("disabled-owner", "project_owner"))
    with pytest.raises(HTTPException) as denied:
        await project_service.replace_member_roles(PROJECT, "owner", [], manager(), domain_management=True, remove=True)
    assert denied.value.status_code == 409
    assert (await project_service.get_project_access(PROJECT, "owner"))["is_owner"]


@pytest.mark.asyncio
async def test_existing_invitation_acceptance_preserves_admin_and_unrelated_managed_roles(directory, enrollments):
    directory.direct.append(assignment("admin", "lumen-chat_user"))
    result, token = await invite(directory, enrollments, "admin@test.invalid")
    before = project_service._direct_ids(directory.direct, "admin")
    async with enrollments() as session:
        accepted = await domain_iam.redeem(
            token, "invitation", session, token_info=manager("admin"), personal_domain_name="Personal"
        )
    assert accepted["user_id"] == "admin"
    assert project_service._direct_ids(directory.direct, "admin") == before | {rid("project_member")}
    assert (await project_service.get_project_access(PROJECT, "admin"))["is_manager"]
    assert not [call for call in directory.calls if call[0] == "revoke"]


@pytest.mark.asyncio
async def test_partial_grant_failure_compensates_exact_new_account_and_grants(directory, enrollments):
    result, token = await invite(directory, enrollments)
    grant = directory.ks.roles.grant

    def lost_reply(*args, **kwargs):
        grant(*args, **kwargs)
        raise ConnectionError("Grant accepted but reply lost")

    directory.ks.roles.grant = lost_reply
    async with enrollments() as session:
        with pytest.raises(HTTPException) as failed:
            await domain_iam.redeem(
                token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
            )
        assert failed.value.status_code == 503
        row = await session.get(DomainEnrollment, result["id"])
        assert row.status == "recovery_required" and row.new_user and row.added_grants[-1]["phase"] == "unknown"
        assert not directory.users[row.user_id].enabled
        await domain_iam.settle_enrollment_native_writes(
            row.id,
            manager("system-admin"),
            session,
            domain_id="domain",
            native_writes_settled=True,
        )
        await domain_iam.revoke(row.id, manager(), session)
        assert row.status == "revoked"
        assert row.user_id not in directory.users
        assert not project_service._direct_ids(directory.direct, row.user_id)
        with pytest.raises(HTTPException) as replay:
            await domain_iam.redeem(
                token, "invitation", session, name="again", password=PASSWORD, personal_domain_name="Personal"
            )
        assert replay.value.status_code == 410


@pytest.mark.asyncio
async def test_revoke_never_succeeds_while_native_grants_survive_and_retry_recovers(directory, enrollments):
    result, token = await invite(directory, enrollments)
    grant = directory.ks.roles.grant
    revoke = directory.ks.roles.revoke

    def lost_reply(*args, **kwargs):
        grant(*args, **kwargs)
        raise ConnectionError("Grant reply lost")

    def revoke_unavailable(*args, **kwargs):
        raise ConnectionError("Cannot revoke native grant")

    directory.ks.roles.grant = lost_reply
    directory.ks.roles.revoke = revoke_unavailable
    async with enrollments() as session:
        with pytest.raises(HTTPException):
            await domain_iam.redeem(
                token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
            )
        row = await session.get(DomainEnrollment, result["id"])
        uid = row.user_id
        assert row.status == "recovery_required" and not directory.users[uid].enabled
        assert rid("manager") in project_service._direct_ids(directory.personal_direct, uid)
        await domain_iam.settle_enrollment_native_writes(
            row.id,
            manager("system-admin"),
            session,
            domain_id="domain",
            native_writes_settled=True,
        )
        with pytest.raises(HTTPException) as still_live:
            await domain_iam.revoke(result["id"], manager(), session)
        assert still_live.value.status_code == 503
        assert rid("manager") in project_service._direct_ids(directory.personal_direct, uid)
        operations = await domain_iam.list_invitations(manager(), session, operations=True)
        assert next(item for item in operations["items"] if item["id"] == result["id"])["recovery_required"]
        directory.ks.roles.revoke = revoke
        await domain_iam.revoke(result["id"], manager(), session)
        row = await session.get(DomainEnrollment, result["id"])
        assert row.status == "revoked"
        assert uid not in directory.users and not project_service._direct_ids(directory.direct, uid)


@pytest.mark.asyncio
async def test_final_sql_failure_cannot_leave_active_account_with_pending_record(directory, enrollments):
    result, token = await invite(directory, enrollments)
    async with enrollments() as session:
        commit = session.commit
        fail_once = True

        async def fail_final_commit():
            nonlocal fail_once
            if fail_once and any(
                isinstance(row, DomainEnrollment) and row.status == "accepted" for row in session.identity_map.values()
            ):
                fail_once = False
                raise ConnectionError("SQL commit unavailable after activation")
            await commit()

        session.commit = fail_final_commit
        with pytest.raises(HTTPException) as failed:
            await domain_iam.redeem(
                token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
            )
        assert failed.value.status_code == 503
        row = await session.get(DomainEnrollment, result["id"])
        assert row.status == "failed" and row.user_id not in directory.users
        assert not project_service._direct_ids(directory.direct, row.user_id)
        assert not directory.personal_direct and not directory.default_direct
        assert not directory.personal_projects and not directory.personal_domains


@pytest.mark.asyncio
async def test_manager_create_with_project_failure_is_durably_disposed(directory, enrollments):
    grant = directory.ks.roles.grant

    def lost_reply(*args, **kwargs):
        grant(*args, **kwargs)
        raise ConnectionError("Grant reply lost")

    directory.ks.roles.grant = lost_reply
    async with enrollments() as session:
        with pytest.raises(HTTPException) as failed:
            await domain_iam.create_user(
                {
                    "personal_domain_name": "Personal",
                    **{
                        "name": "managed",
                        "email": "managed@test.invalid",
                        "password": PASSWORD,
                        "enabled": True,
                        "project_id": PROJECT,
                        "role_ids": [rid("project_member")],
                    },
                },
                manager(),
                session,
            )
        assert failed.value.status_code == 503
        row = (
            await session.execute(select(DomainEnrollment).where(DomainEnrollment.kind == "managed_create"))
        ).scalar_one()
        assert row.status == "recovery_required" and not directory.users[row.user_id].enabled
        await domain_iam.settle_enrollment_native_writes(
            row.id,
            manager("system-admin"),
            session,
            domain_id="domain",
            native_writes_settled=True,
        )
        await domain_iam.revoke(row.id, manager(), session, operation=True)
        assert row.status == "revoked" and row.user_id not in directory.users
        assert not project_service._direct_ids(directory.direct, row.user_id)


@pytest.mark.asyncio
async def test_interrupted_native_work_has_durable_plan_and_can_be_recovered(directory, enrollments, monkeypatch):
    class ProcessInterrupted(BaseException):
        pass

    result, token = await invite(directory, enrollments)
    save = domain_iam._save

    async def interrupt_before_activation(row, session, snapshot, **attrs):
        if attrs.get("status") == "activating":
            raise ProcessInterrupted()
        await save(row, session, snapshot, **attrs)

    monkeypatch.setattr(domain_iam, "_save", interrupt_before_activation)
    async with enrollments() as session:
        with pytest.raises(ProcessInterrupted):
            await domain_iam.redeem(
                token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
            )
    async with enrollments() as session:
        row = await session.get(DomainEnrollment, result["id"])
        uid = row.user_id
        assert row.status == "granting" and {g["role_id"] for g in row.added_grants} >= {
            rid("project_member"),
            rid("project_reader"),
            rid("manager"),
            rid("project_owner"),
        }
        assert not directory.users[uid].enabled
        await domain_iam.revoke(result["id"], manager(), session)
        assert uid not in directory.users and not project_service._direct_ids(directory.direct, uid)
        assert (await session.get(DomainEnrollment, result["id"])).status == "revoked"
        assert not directory.personal_direct and not directory.default_direct
        assert not directory.personal_projects and not directory.personal_domains


@pytest.mark.asyncio
@pytest.mark.parametrize("deleted", [False, True])
async def test_historical_invitation_list_and_revoke_survive_disabled_or_deleted_project(
    directory, enrollments, deleted
):
    result, token = await invite(directory, enrollments)
    if deleted:
        directory.project = None
    else:
        directory.project.enabled = False
    async with enrollments() as session:
        listed = await domain_iam.list_invitations(manager(), session)
        assert listed["items"][0]["id"] == result["id"] and listed["items"][0]["project_name"] == "Intended project"
        with pytest.raises(HTTPException) as inactive:
            await domain_iam.redeem(
                token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
            )
        assert inactive.value.status_code in {403, 404}
        await domain_iam.revoke(result["id"], manager(), session)
        assert (await session.get(DomainEnrollment, result["id"])).status == "revoked"
    assert not directory.creates


@pytest.mark.asyncio
async def test_history_still_rejects_foreign_native_project_metadata(directory, enrollments):
    result, token = await invite(directory, enrollments)
    directory.project.domain_id = "other"
    async with enrollments() as session:
        with pytest.raises(HTTPException) as denied:
            await domain_iam.list_invitations(manager(), session)
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as denied_revoke:
            await domain_iam.revoke(result["id"], manager(), session)
        assert denied_revoke.value.status_code == 403
        row = await session.get(DomainEnrollment, result["id"])
        assert row.status == "pending"


@pytest.mark.asyncio
async def test_native_membership_mutation_invalidates_domain_qualified_caches(directory):
    await project_service.replace_member_roles(
        PROJECT, "member", [rid("project_reader")], manager(), domain_management=True
    )
    invalidated = [call.args[0] for call in project_service.cache.invalidate.await_args_list]
    assert "afterglow:user:member:domain:domain:projects" in invalidated
    assert "afterglow:admin:projects:*" in invalidated
    assert "afterglow:admin:project_names:*" in invalidated
    assert "afterglow:user:member:projects" not in invalidated


@pytest.mark.asyncio
async def test_failed_existing_acceptance_only_compensates_new_grants(directory, enrollments):
    directory.direct.append(assignment("admin", "lumen-chat_user"))
    before = project_service._direct_ids(directory.direct, "admin")
    result, token = await invite(directory, enrollments, "admin@test.invalid")
    grant = directory.ks.roles.grant

    def lost_reply(*args, **kwargs):
        grant(*args, **kwargs)
        raise ConnectionError("Native grant reply lost")

    directory.ks.roles.grant = lost_reply
    async with enrollments() as session:
        with pytest.raises(HTTPException) as failed:
            await domain_iam.redeem(
                token, "invitation", session, token_info=manager("admin"), personal_domain_name="Personal"
            )
        assert failed.value.status_code == 503
        row = await session.get(DomainEnrollment, result["id"])
        assert row.status == "recovery_required" and row.added_grants[-1]["phase"] == "unknown"
        await domain_iam.settle_enrollment_native_writes(
            row.id,
            manager("system-admin"),
            session,
            domain_id="domain",
            native_writes_settled=True,
        )
        await domain_iam.revoke(row.id, manager(), session)
        assert row.status == "revoked"
    assert project_service._direct_ids(directory.direct, "admin") == before
    assert directory.users["admin"].enabled and directory.users["admin"].password == PASSWORD
    assert not directory.updates


@pytest.mark.asyncio
async def test_lost_create_reply_recovers_only_exact_server_marked_account(directory, enrollments):
    result, token = await invite(directory, enrollments)
    create = directory.ks.users.create

    def lost_reply(**attrs):
        create(**attrs)
        raise ConnectionError("Native create reply lost")

    directory.ks.users.create = lost_reply
    async with enrollments() as session:
        with pytest.raises(HTTPException) as failed:
            await domain_iam.redeem(
                token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
            )
        assert failed.value.status_code == 503
        row = await session.get(DomainEnrollment, result["id"])
        assert row.status == "failed" and row.user_id == directory.creates[0]
        assert not row.creation_uncertain and row.user_id not in directory.users
    assert directory.users["member"].enabled and directory.users["member"].password == PASSWORD


@pytest.mark.asyncio
async def test_unknown_create_outcome_never_deletes_unowned_existing_account(directory, enrollments):
    result, token = await invite(directory, enrollments)

    def unavailable(**attrs):
        raise ConnectionError("Native create outcome is unknown")

    directory.ks.users.create = unavailable
    async with enrollments() as session:
        with pytest.raises(HTTPException):
            await domain_iam.redeem(
                token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
            )
        row = await session.get(DomainEnrollment, result["id"])
        assert row.status == "recovery_required" and row.creation_uncertain and row.user_id is None
        directory.users["external"] = SimpleNamespace(
            id="external",
            name="invitee",
            email="new@test.invalid",
            domain_id="domain",
            enabled=True,
            password="external-password",
        )
        with pytest.raises(HTTPException) as unproven:
            await domain_iam.revoke(result["id"], manager(), session)
        assert unproven.value.status_code == 503
        assert directory.users["external"].enabled and directory.users["external"].password == "external-password"


@pytest.mark.asyncio
async def test_recovery_routes_only_return_204_after_verified_native_disposition(directory, enrollments):
    result, token = await invite(directory, enrollments)
    grant = directory.ks.roles.grant
    revoke = directory.ks.roles.revoke

    def lost_reply(*args, **kwargs):
        grant(*args, **kwargs)
        raise ConnectionError("Native grant reply lost")

    def unavailable(*args, **kwargs):
        raise ConnectionError("Native revoke unavailable")

    directory.ks.roles.grant = lost_reply
    directory.ks.roles.revoke = unavailable
    async with enrollments() as session:
        with pytest.raises(HTTPException):
            await domain_iam.redeem(
                token, "invitation", session, name="invitee", password=PASSWORD, personal_domain_name="Personal"
            )
    app = FastAPI()
    app.include_router(iam.router, prefix="/api/v1/iam")
    app.dependency_overrides[get_token_info] = lambda: manager()

    async def db():
        async with enrollments() as session:
            yield session

    app.dependency_overrides[get_session] = db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get("/api/v1/iam/operations")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["id"] == result["id"]
        assert "token_hash" not in listed.text and "afterglow_enrollment_id" not in listed.text
        refused = await client.delete(f"/api/v1/iam/operations/{result['id']}")
        assert refused.status_code == 503
        directory.ks.roles.revoke = revoke
        still_uncertain = await client.delete(f"/api/v1/iam/operations/{result['id']}")
        assert still_uncertain.status_code == 503
        async with enrollments() as session:
            await domain_iam.settle_enrollment_native_writes(
                result["id"],
                manager("system-admin"),
                session,
                domain_id="domain",
                native_writes_settled=True,
            )
        recovered = await client.delete(f"/api/v1/iam/operations/{result['id']}")
        assert recovered.status_code == 204 and recovered.content == b""
        listed = await client.get("/api/v1/iam/operations")
        assert listed.json() == {"items": []}


@pytest.mark.asyncio
async def test_external_invitee_accepts_same_account_and_home_identity_stays_read_only(directory, enrollments):
    result, token = await invite(directory, enrollments, "foreign@test.invalid")
    external = directory.users["foreign"]
    original = vars(external).copy()
    async with enrollments() as session:
        with pytest.raises(HTTPException) as duplicate:
            await domain_iam.redeem(
                token, "invitation", session, name="duplicate", password="new-password", personal_domain_name="Personal"
            )
        assert duplicate.value.status_code == 409
        await session.rollback()
        accepted = await domain_iam.redeem(
            token, "invitation", session, token_info=manager("foreign", "other"), personal_domain_name="Personal"
        )
        assert accepted["user_id"] == "foreign" and accepted["domain_id"] == "domain"
        assert (await session.get(DomainEnrollment, result["id"])).new_user is False
    assert not directory.creates and not directory.updates and vars(external) == original
    access = await project_service.get_project_access(PROJECT, "foreign")
    assert "project_member" in access["roles"] and not access["is_owner"] and not access["is_manager"]
    users = (await domain_iam.list_resources("users", manager()))["items"]
    listed = next(user for user in users if user["id"] == "foreign")
    assert listed["domain_id"] == "other" and listed["protected"]
    for attrs in ({"password": "replacement"}, {"email": "changed@test.invalid"}, {"enabled": False}):
        with pytest.raises(HTTPException) as protected:
            await domain_iam.update_user("foreign", attrs, manager())
        assert protected.value.status_code == 403
    downgraded = await project_service.replace_member_roles(
        PROJECT, "foreign", [rid("project_reader")], manager(), domain_management=True
    )
    assert downgraded["roles"] == ["project_reader", "reader"]
    assert not directory.updates and vars(external) == original


@pytest.mark.asyncio
async def test_cross_identity_default_manager_controls_working_domain_not_home_credentials(directory):
    directory.users["domain-manager"].domain_id = "other"
    directory.default_direct.append(
        {
            "user": {"id": "foreign"},
            "role": {"id": rid("project_reader")},
            "scope": {"project": {"id": "default-project"}},
        }
    )
    ctx = await domain_iam.context(manager())
    assert ctx["domain_id"] == "domain" and ctx["is_domain_manager"]
    granted = await project_service.replace_member_roles(
        PROJECT, "foreign", [rid("project_admin")], manager(), domain_management=True
    )
    assert granted["is_manager"] and not granted["is_owner"]
    with pytest.raises(HTTPException) as denied:
        await domain_iam.update_user("domain-manager", {"password": "replacement"}, manager())
    assert denied.value.status_code == 403 and not directory.updates
    assert not domain_projects.has_manager("domain-manager", "other", ks=directory.ks, catalog=directory.catalog)


@pytest.mark.asyncio
async def test_last_default_manager_disable_is_guarded_before_native_write(directory):
    with pytest.raises(HTTPException) as denied:
        await domain_iam.update_user("domain-manager", {"enabled": False}, manager())
    assert denied.value.status_code == 409
    assert directory.users["domain-manager"].enabled and not directory.updates
    directory.managers.add("admin")
    disabled = await domain_iam.update_user("domain-manager", {"enabled": False}, manager("admin"))
    assert not disabled["enabled"]
    assert not domain_projects.has_manager("domain-manager", "domain", ks=directory.ks, catalog=directory.catalog)
    assert domain_projects.has_manager("admin", "domain", ks=directory.ks, catalog=directory.catalog)
    with pytest.raises(HTTPException) as revoked:
        await domain_iam.context(manager())
    assert revoked.value.status_code == 401


@pytest.mark.asyncio
async def test_revoked_invitation_issuer_cannot_grant_external_membership(directory, enrollments):
    _, token = await invite(directory, enrollments, "foreign@test.invalid")
    directory.managers.clear()
    async with enrollments() as session:
        with pytest.raises(HTTPException) as denied:
            await domain_iam.redeem(
                token, "invitation", session, token_info=manager("foreign", "other"), personal_domain_name="Personal"
            )
        assert denied.value.status_code == 403
    assert not directory.calls and not directory.creates and not directory.updates


@pytest.mark.asyncio
@pytest.mark.parametrize("group_id", [None, "team"])
@pytest.mark.parametrize("alias", [False, True])
async def test_manager_bearing_user_and_group_grants_rejected_outside_default(directory, group_id, alias):
    role_id = rid("manager")
    if alias:
        role_id = "custom-manager-alias"
        roles = [{"id": row["id"], "name": row["name"], "domain_id": row["domain_id"]} for row in directory.catalog]
        roles.append({"id": role_id, "name": "audit-alias", "domain_id": None})
        edges = [
            {"prior_role": {"id": row["id"]}, "implies": [{"id": child} for child in row["implied_role_ids"]]}
            for row in directory.catalog
        ]
        edges.append({"prior_role": {"id": role_id}, "implies": [{"id": rid("manager")}]})
        directory.catalog = identity_roles._catalog(roles, edges)
    writes = []
    conn = SimpleNamespace(
        identity=SimpleNamespace(
            assign_project_role_to_user=lambda *args: writes.append(args),
            assign_project_role_to_group=lambda *args: writes.append(args),
        )
    )
    with pytest.raises(HTTPException) as denied:
        await identity_roles.change_project_assignment(
            conn,
            manager("system-admin"),
            PROJECT,
            role_id,
            user_id="foreign" if group_id is None else None,
            group_id=group_id,
        )
    assert denied.value.status_code in {409, 422}
    assert not writes and not directory.calls


@pytest.mark.asyncio
async def test_generic_native_default_manager_revoke_refuses_last_before_write(directory):
    writes = []
    conn = SimpleNamespace(
        identity=SimpleNamespace(
            unassign_project_role_from_user=lambda *args: writes.append(args),
        )
    )
    with pytest.raises(HTTPException) as denied:
        await identity_roles.change_project_assignment(
            conn,
            manager("system-admin"),
            "default-project",
            rid("manager"),
            user_id="domain-manager",
            remove=True,
        )
    assert denied.value.status_code == 409
    assert domain_projects.has_manager("domain-manager", "domain", ks=directory.ks, catalog=directory.catalog)
    assert not writes


@pytest.mark.asyncio
async def test_role_graph_cannot_remove_last_indirect_default_manager(directory):
    roles = [{"id": row["id"], "name": row["name"], "domain_id": row["domain_id"]} for row in directory.catalog]
    roles.append({"id": "indirect-manager", "name": "management-alias", "domain_id": None})
    edges = [
        {"prior_role": {"id": row["id"]}, "implies": [{"id": child} for child in row["implied_role_ids"]]}
        for row in directory.catalog
    ]
    edges.append({"prior_role": {"id": "indirect-manager"}, "implies": [{"id": rid("manager")}]})
    directory.catalog = identity_roles._catalog(roles, edges)
    native = directory.ks.role_assignments.list

    def assignments(**kwargs):
        return [
            {**row, "role": {"id": "indirect-manager"}} if row["role"]["id"] == rid("manager") else row
            for row in native(**kwargs)
        ]

    directory.ks.role_assignments.list = assignments
    assert domain_projects.has_manager("domain-manager", "domain", ks=directory.ks, catalog=directory.catalog)
    writes = []
    conn = SimpleNamespace(identity=SimpleNamespace(delete=lambda path: writes.append(path)))
    with pytest.raises(HTTPException) as denied:
        await identity_roles.change_edge(conn, manager("system-admin"), "indirect-manager", rid("manager"), remove=True)
    assert denied.value.status_code == 409 and not writes
    assert domain_projects.has_manager("domain-manager", "domain", ks=directory.ks, catalog=directory.catalog)


@pytest.mark.asyncio
@pytest.mark.parametrize("delete", [False, True])
async def test_last_group_default_manager_membership_and_group_delete_are_guarded(directory, delete):
    directory.managers.clear()
    directory.groups["team"] = ["domain-manager"]
    native = directory.ks.role_assignments.list

    def assignments(project=None, effective=False, user=None, **kwargs):
        rows = list(native(project=project, effective=effective, user=user, **kwargs))
        if project in {None, "default-project"} and not kwargs.get("domain") and not kwargs.get("system"):
            if effective:
                rows.extend(
                    {
                        "user": {"id": uid},
                        "role": {"id": rid("manager")},
                        "scope": {"project": {"id": "default-project"}},
                        "links": {"membership": f"https://identity/v3/groups/team/users/{uid}"},
                    }
                    for uid in directory.groups["team"]
                    if user is None or user == uid
                )
            elif user is None:
                rows.append(
                    {
                        "group": {"id": "team"},
                        "role": {"id": rid("manager")},
                        "scope": {"project": {"id": "default-project"}},
                    }
                )
        return rows

    directory.ks.role_assignments.list = assignments
    assert domain_projects.has_manager("domain-manager", "domain", ks=directory.ks, catalog=directory.catalog)
    writes = []
    conn = SimpleNamespace(
        identity=SimpleNamespace(
            remove_user_from_group=lambda *args: writes.append(args),
            delete_group=lambda *args, **kwargs: writes.append(args),
        )
    )
    with pytest.raises(HTTPException) as denied:
        await identity_roles.change_group_membership(
            conn,
            manager("system-admin"),
            "team",
            user_id="domain-manager",
            remove=not delete,
            delete=delete,
        )
    assert denied.value.status_code == 409 and not writes
    assert directory.groups["team"] == ["domain-manager"]
    assert domain_projects.has_manager("domain-manager", "domain", ks=directory.ks, catalog=directory.catalog)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["add", "remove", "delete", "grant", "revoke"])
async def test_managed_projection_group_cannot_be_tampered_with(directory, action):
    directory.ks.groups.get = lambda gid: SimpleNamespace(
        id=gid,
        name="afterglow-default-managers-domain",
        description="afterglow:default-manager-reader:v1:domain",
        domain_id="domain",
    )
    writes = []
    conn = SimpleNamespace(
        identity=SimpleNamespace(
            add_user_to_group=lambda *args: writes.append(args),
            remove_user_from_group=lambda *args: writes.append(args),
            delete_group=lambda *args, **kwargs: writes.append(args),
            assign_project_role_to_group=lambda *args: writes.append(args),
            unassign_project_role_from_group=lambda *args: writes.append(args),
        )
    )
    with pytest.raises(HTTPException) as denied:
        if action in {"grant", "revoke"}:
            await identity_roles.change_project_assignment(
                conn,
                manager("system-admin"),
                PROJECT,
                rid("project_reader"),
                group_id="projection",
                remove=action == "revoke",
            )
        else:
            await identity_roles.change_group_membership(
                conn,
                manager("system-admin"),
                "projection",
                user_id="foreign",
                remove=action == "remove",
                delete=action == "delete",
            )
    assert denied.value.status_code == 403 and not writes


@pytest.mark.asyncio
async def test_manager_revoke_with_another_enabled_manager_removes_actual_authority(directory, monkeypatch):
    directory.managers.add("admin")
    monkeypatch.setattr(identity_roles, "_assignment_invalidation", AsyncMock())

    def revoke(project_id, user_id, role_id):
        assert (project_id, role_id) == ("default-project", rid("manager"))
        directory.managers.remove(user_id)

    conn = SimpleNamespace(identity=SimpleNamespace(unassign_project_role_from_user=revoke))
    result = await identity_roles.change_project_assignment(
        conn,
        manager("system-admin"),
        "default-project",
        rid("manager"),
        user_id="domain-manager",
        remove=True,
    )
    assert result == {"status": "revoked"}
    assert domain_projects.has_manager("admin", "domain", ks=directory.ks, catalog=directory.catalog)
    assert not domain_projects.has_manager("domain-manager", "domain", ks=directory.ks, catalog=directory.catalog)
    with pytest.raises(HTTPException) as denied:
        await domain_iam.context(manager())
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_role_graph_cannot_remove_required_default_native_reader_entitlement(directory):
    writes = []
    conn = SimpleNamespace(identity=SimpleNamespace(delete=lambda path: writes.append(path)))
    with pytest.raises(HTTPException) as denied:
        await identity_roles.change_edge(
            conn, manager("system-admin"), rid("project_reader"), rid("reader"), remove=True
        )
    assert denied.value.status_code in {409, 422}
    assert not writes
    assert (
        rid("reader")
        in next(row for row in directory.catalog if row["id"] == rid("project_reader"))["inherited_role_ids"]
    )


@pytest.mark.asyncio
async def test_cross_identity_invitation_rejects_provider_subject_substitution(directory, enrollments):
    result, token = await invite(directory, enrollments, "foreign@test.invalid")
    get_user = directory.ks.users.get
    directory.ks.users.get = lambda uid: (
        SimpleNamespace(
            id="different-account", name="other", email="foreign@test.invalid", enabled=True, domain_id="other"
        )
        if uid == "foreign"
        else get_user(uid)
    )
    async with enrollments() as session:
        with pytest.raises(HTTPException) as denied:
            await domain_iam.redeem(
                token, "invitation", session, token_info=manager("foreign", "other"), personal_domain_name="Personal"
            )
        assert denied.value.status_code == 503
        assert (await session.get(DomainEnrollment, result["id"])).status == "pending"
    assert not directory.calls and not directory.creates and not directory.updates


@pytest.mark.asyncio
@pytest.mark.parametrize("group", [False, True])
async def test_admin_project_assignment_accepts_external_principal_without_identity_write(
    directory, monkeypatch, group
):
    from app.api.deps import get_os_conn, require_admin
    from app.api.identity import admin_identity
    from tests.admin_gate import synthetic_verified_admin

    directory.groups["external-team"] = ["foreign"]
    get_group = directory.ks.groups.get
    directory.ks.groups.get = lambda gid: (
        SimpleNamespace(id=gid, name="External team", description="", domain_id="other")
        if gid == "external-team"
        else get_group(gid)
    )

    def assign_group(project_id, group_id, role_id):
        assert project_id == PROJECT and role_id == rid("project_reader")
        directory.direct.append(assignment(None, "project_reader", group=group_id))

    identity = SimpleNamespace(
        get_domain=directory.ks.domains.get,
        get_project=directory.ks.projects.get,
        get_user=directory.ks.users.get,
        get_group=directory.ks.groups.get,
        get_role=lambda role_id: SimpleNamespace(**next(row for row in directory.catalog if row["id"] == role_id)),
        assign_project_role_to_user=lambda pid, uid, role_id: directory.ks.roles.grant(role_id, user=uid, project=pid),
        assign_project_role_to_group=assign_group,
        group_users=lambda gid: [directory.ks.users.get(uid) for uid in directory.groups[gid]],
        role_assignments=lambda scope_project_id, include_names: directory.ks.role_assignments.list(
            project=scope_project_id
        ),
    )
    app = FastAPI()
    app.include_router(admin_identity.router, prefix="/api/v1/admin")
    app.dependency_overrides[get_os_conn] = lambda: SimpleNamespace(identity=identity)
    app.dependency_overrides[get_token_info] = lambda: {**manager("system-admin"), "is_system_admin": True}
    app.dependency_overrides[require_admin] = synthetic_verified_admin
    monkeypatch.setattr(identity_roles, "_assignment_invalidation", AsyncMock())
    body = {"project_id": PROJECT, "role_id": rid("project_reader")}
    body["group_id" if group else "user_id"] = "external-team" if group else "foreign"
    path = "/api/v1/admin/roles/assign-group" if group else "/api/v1/admin/roles/assign"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        granted = await client.post(path, params={"domain_id": "domain"}, json=body)
        assert granted.status_code == 200
        listed = await client.get(f"/api/v1/admin/projects/{PROJECT}/members", params={"domain_id": "domain"})
        assert listed.status_code == 200
        assert any(row["user_id"] == ("group:external-team" if group else "foreign") for row in listed.json())
        protected = await client.patch(
            "/api/v1/admin/users/foreign", params={"domain_id": "domain"}, json={"password": "replacement"}
        )
        assert protected.status_code == 403
    access = await project_service.get_project_access(PROJECT, "foreign")
    assert access == {"is_owner": False, "is_manager": False, "roles": ["project_reader", "reader"]}
    with pytest.raises(HTTPException) as denied:
        await domain_iam.context(manager("foreign"))
    assert denied.value.status_code == 403
    assert not directory.updates and not directory.creates and directory.users["foreign"].password == PASSWORD
