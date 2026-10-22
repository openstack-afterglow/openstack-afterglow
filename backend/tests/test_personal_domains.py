"""Personal identities: SQL journals, real API requests and native SDK wire data.

Synthetic native directories never grant authority by token claim. No live cloud
is contacted; the native display test uses installed clients over loopback HTTP.
"""

import asyncio
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from keystoneauth1 import noauth
from keystoneauth1 import session as native_session
from keystoneclient.v3.client import Client
from openstack.identity.v3.domain import Domain
from sqlalchemy import select

from app.api.deps import get_token_info, require_domain_manager
from app.api.identity import iam, onboarding
from app.database import get_session
from app.models.account_spaces import PersonalProjectIntent, SharedDomainIntent
from app.models.domain_iam import DomainEnrollment
from app.services import (
    account_spaces,
    domain_display,
    domain_iam,
    domain_scope,
    keystone,
    project_service,
)
from tests.test_domain_iam import PASSWORD, email_token, manager
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import enrollments as enrollments
from tests.test_project_membership_roles import rid


@pytest.fixture
def enrollment_app(directory, enrollments):
    app = FastAPI()
    app.include_router(iam.router, prefix="/api/v1/iam")
    app.include_router(onboarding.router, prefix="/api/v1/auth")
    app.dependency_overrides[require_domain_manager] = lambda: manager()
    app.dependency_overrides[get_token_info] = lambda: manager("foreign", "other")

    async def session_dep():
        async with enrollments() as session:
            yield session

    app.dependency_overrides[get_session] = session_dep
    return app


@pytest.mark.asyncio
async def test_invites_share_account_and_personal_but_never_projects(directory, enrollments, enrollment_app):
    results = []
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        for username in ("first", "second"):
            issued = await client.post("/api/v1/iam/invitations", json={"email": f"{username}@test.invalid"})
            assert issued.status_code == 201
            body = {"token": email_token(directory.sent[-1]), "name": username, "password": PASSWORD}
            if username == "second":
                collision = await client.post("/api/v1/auth/invitations/accept", json={**body, "name": "first"})
                assert collision.status_code == 409
                assert len(directory.creates) == len(directory.personal_projects) == 1
            accepted = await client.post("/api/v1/auth/invitations/accept", json=body)
            assert accepted.status_code == 200, accepted.text
            result = accepted.json()
            results.append(result)
            uid, pid = result["user_id"], result["personal_project_id"]
            assert result["identity_domain_name"] == "Accounts" and result["domain_name"] == "Personal"
            assert directory.users[uid].domain_id == result["identity_domain_id"]
            assert directory.users[uid].afterglow_local_password is True
            assert result["personal_domain_id"] == result["domain_id"] != result["identity_domain_id"]
            project = directory.personal_projects[pid]
            assert project.enabled and project.name == result["personal_project_name"]
            assert re.fullmatch(rf"{username}-[a-z]{{8}}[0-9]{{8}}", project.name)
            assert project.afterglow_personal_user_id == uid and project.afterglow_personal_primary is True
            direct = [r for r in directory.personal_direct if r["scope"]["project"]["id"] == pid]
            assert project_service._direct_ids(direct, uid) == {rid("member")}
            assert project_service._direct_ids(directory.default_direct, uid) == {rid("project_reader")}
            assert not any(p.domain_id == result["identity_domain_id"] for p in directory.ks.projects.list())
            assert {section for project_id, section, _ in directory.quota_writes if project_id == pid} == {
                "compute",
                "volume",
                "network",
            }
            assert (await client.post("/api/v1/auth/invitations/accept", json=body)).status_code == 410
        assert len(directory.creates) == 2 and len(directory.personal_domains) == 2
        assert not directory.domain_writes
        assert results[0]["identity_domain_id"] == "operator-accounts"
        assert results[0]["personal_domain_id"] == "operator-personal"
        assert results[0]["identity_domain_id"] == results[1]["identity_domain_id"]
        assert results[0]["personal_domain_id"] == results[1]["personal_domain_id"]
        assert results[0]["personal_project_id"] != results[1]["personal_project_id"]
        directory.settings.auth.public_signup_enabled = True
        await client.post("/api/v1/auth/registrations", json={"email": "private@test.invalid"})
        private = await client.post(
            "/api/v1/auth/registrations/accept",
            json={"token": email_token(directory.sent[-1]), "name": "private", "password": PASSWORD},
        )
        assert private.status_code == 200, private.text
        listed = await client.get("/api/v1/iam/users")
        listed_ids = {row["id"] for row in listed.json()["items"]}
        assert {result["user_id"] for result in results} <= listed_ids
        assert private.json()["user_id"] not in listed_ids
        assert all(u["protected"] for u in listed.json()["items"] if u["id"] in directory.creates)
    from app.models.domain_quotas import DomainQuotaPolicy

    async with enrollments() as session:
        assert not (await session.execute(select(DomainQuotaPolicy))).scalars().all()


@pytest.mark.asyncio
async def test_public_signup_rejects_removed_input_and_lands_personal(directory, enrollment_app):
    directory.settings.auth.public_signup_enabled = True
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        assert (
            await client.post("/api/v1/auth/registrations", json={"email": "signup@test.invalid"})
        ).status_code == 202
        body = {"token": email_token(directory.sent[-1]), "name": "signup", "password": PASSWORD}
        rejected = await client.post("/api/v1/auth/registrations/accept", json={**body, "personal_domain_name": "Home"})
        assert rejected.status_code == 422 and PASSWORD not in rejected.text and not directory.creates
        accepted = await client.post("/api/v1/auth/registrations/accept", json=body)
        assert accepted.status_code == 200, accepted.text
        result = accepted.json()
        assert result["identity_domain_name"] == "Accounts" and result["domain_name"] == "Personal"
        uid, pid = result["user_id"], result["personal_project_id"]
        assert directory.users[uid].domain_id == result["identity_domain_id"]
        assert directory.users[uid].password == PASSWORD
        assert re.fullmatch(r"signup-[a-z]{8}[0-9]{8}", result["personal_project_name"])
        direct = directory.ks.role_assignments.list(project=pid, user=uid)
        assert project_service._direct_ids(direct, uid) == {rid("member")}
        assert not project_service._direct_ids(directory.default_direct, uid)
        assert not any(p.domain_id == result["identity_domain_id"] for p in directory.ks.projects.list())
        assert result["identity_domain_id"] == "operator-accounts"
        assert result["personal_domain_id"] == "operator-personal"
        assert not directory.domain_writes


@pytest.mark.asyncio
async def test_manager_account_creation_endpoint_is_removed(directory, enrollment_app):
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/iam/users", json={"name": "new", "email": "new@test.invalid", "password": PASSWORD}
        )
        assert response.status_code == 405 and not directory.creates


@pytest.mark.asyncio
async def test_system_human_creation_shares_identity_domain(directory, enrollments):
    attrs = {"name": "first", "email": "first@test.invalid", "password": PASSWORD, "enabled": True}
    async with enrollments() as session:
        with pytest.raises(HTTPException) as forged:
            await domain_iam.create_managed_user(
                attrs, "domain", {**manager("member"), "is_system_admin": True}, session
            )
        assert forged.value.status_code == 403 and not directory.creates
        first = await domain_iam.create_managed_user(attrs, "domain", manager("system-admin"), session)
        second = await domain_iam.create_managed_user(
            {**attrs, "name": "second", "email": "second@test.invalid"}, "domain", manager("system-admin"), session
        )
        assert first["identity_domain_id"] == second["identity_domain_id"]
        assert first["personal_project_id"] is second["personal_project_id"] is None
        assert first["personal_project_deferred"] and second["personal_project_deferred"]
        assert not directory.personal_projects and not directory.quota_writes
        intents = (await session.execute(select(PersonalProjectIntent))).scalars().all()
        assert len(intents) == 2 and all(row.status == "deferred" for row in intents)
        assert directory.users["operator"].domain_id == "domain"
        assert first["identity_domain_id"] == "operator-accounts"
        assert first["personal_domain_id"] == second["personal_domain_id"] == "operator-personal"
        assert not directory.domain_writes


@pytest.mark.asyncio
@pytest.mark.parametrize("selected", ["organization", "accounts"])
async def test_admin_creation_observation_context_never_admits_new_account(
    directory, enrollments, monkeypatch, selected
):
    from app.api.deps import get_admin_os_conn, get_os_conn, require_admin
    from app.api.identity import admin_identity
    from app.services import domain_auth

    original_users = {uid: vars(user).copy() for uid, user in directory.users.items()}
    original_grants = list(directory.direct)
    if selected == "accounts":
        async with domain_iam._iam_write() as mutation:
            shared = await account_spaces.ensure_shared_domains(mutation=mutation)
        selected_id = shared["account"].id
    else:
        selected_id = "domain"
    # Neither an organization allowlist/password policy nor a missing organization
    # Default is an admission requirement for a global administrator's account.
    directory.policy = domain_auth.LoginPolicy(
        domain_id="domain", password_enabled=False, allowed_email_domains=["organization.invalid"]
    )
    native_projects = directory.ks.projects.list
    directory.ks.projects.list = lambda **attrs: [p for p in native_projects(**attrs) if p.id != "default-project"]
    app = FastAPI()
    app.include_router(admin_identity.router, prefix="/api/v1/admin")
    app.dependency_overrides[require_admin] = lambda: manager("system-admin")
    app.dependency_overrides[get_token_info] = lambda: manager("system-admin")
    app.dependency_overrides[get_os_conn] = lambda: SimpleNamespace(
        identity=SimpleNamespace(get_domain=directory.ks.domains.get)
    )
    app.dependency_overrides[get_admin_os_conn] = lambda: SimpleNamespace(
        identity=SimpleNamespace(get_domain=directory.ks.domains.get)
    )

    async def session_dep():
        async with enrollments() as session:
            yield session

    app.dependency_overrides[get_session] = session_dep
    monkeypatch.setattr(admin_identity, "invalidate", AsyncMock())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/users",
            json={
                "name": "created",
                "email": "created@test.invalid",
                "password": PASSWORD,
                "domain_id": selected_id,
            },
        )
    assert response.status_code == 201, response.text
    result = response.json()
    uid = result["user_id"]
    assert result["personal_project_id"] is None and result["personal_project_deferred"]
    assert result["identity_domain_name"] == result["domain_name"] == "Accounts"
    assert directory.users[uid].domain_id == result["identity_domain_id"]
    assert directory.users[uid].password == PASSWORD and directory.users[uid].enabled
    assert re.fullmatch(r"created-[a-z]{8}[0-9]{8}", result["personal_project_name"])
    assert not project_service._direct_ids(directory.ks.role_assignments.list(user=uid), uid)
    assert not project_service._direct_ids(directory.default_direct, uid)
    assert not directory.personal_projects and not directory.quota_writes
    assert all(p.domain_id != result["identity_domain_id"] for p in directory.ks.projects.list())
    assert {old: vars(directory.users[old]).copy() for old in original_users} == original_users
    assert directory.direct == original_grants
    assert result["identity_domain_id"] == "operator-accounts"
    assert result["personal_domain_id"] == "operator-personal"
    assert not directory.domain_writes
    async with enrollments() as session:
        row = (await session.execute(select(DomainEnrollment))).scalar_one()
        assert row.kind == "managed_create" and row.domain_id is None and row.status == "accepted"
        intent = (await session.execute(select(PersonalProjectIntent))).scalar_one()
        assert intent.status == "deferred" and intent.token_hash == row.token_hash
        assert intent.personal_project_name == row.personal_project_name
        assert intent.personal_quotas == row.personal_quotas
    primary = await account_spaces.ensure_personal_project(uid)
    assert primary["domain_id"] == "operator-personal"
    assert project_service._direct_ids(directory.ks.role_assignments.list(user=uid), uid) == {rid("member")}
    assert await account_spaces.ensure_personal_project(uid) == primary
    assert len(directory.personal_projects) == 1


@pytest.mark.asyncio
async def test_first_login_safe_read_failure_resumes_one_project_under_concurrent_retries(
    directory, enrollments, monkeypatch
):
    async with enrollments() as session:
        created = await domain_iam.create_managed_user(
            {"name": "retry", "email": "retry@test.invalid", "password": PASSWORD},
            "domain",
            manager("system-admin"),
            session,
        )
    uid = created["user_id"]
    original_user = vars(directory.users[uid]).copy()
    assignments = project_service._assignment_rows
    fail = True

    def unavailable_before_grant(ks, project_id, **kwargs):
        nonlocal fail
        if fail and project_id in directory.personal_projects:
            fail = False
            raise HTTPException(503, "Native role inventory unavailable before dispatch")
        return assignments(ks, project_id, **kwargs)

    monkeypatch.setattr(project_service, "_assignment_rows", unavailable_before_grant)
    with pytest.raises(HTTPException):
        await account_spaces.ensure_personal_project(uid)
    recovery = await account_spaces.personal_recovery_status(uid, created["identity_domain_id"])
    assert recovery["retryable"] and recovery["code"] == "personal_project_retry_available"
    assert not directory.personal_direct and len(directory.personal_projects) == 1
    results = await asyncio.gather(*(account_spaces.ensure_personal_project(uid) for _ in range(2)))
    assert results[0] == results[1] and len(directory.personal_projects) == 1
    assert vars(directory.users[uid]) == original_user
    async with enrollments() as session:
        intent = (await session.execute(select(PersonalProjectIntent))).scalar_one()
        enrollment = (await session.execute(select(DomainEnrollment))).scalar_one()
        assert intent.status == "accepted" and intent.token_hash == enrollment.token_hash
        assert enrollment.personal_project_id == intent.personal_project_id == results[0]["id"]
        assert len(intent.added_grants) == 1 and intent.added_grants[0]["phase"] == "confirmed"


@pytest.mark.asyncio
@pytest.mark.parametrize("native_outcome", ["absent", "lost_reply", "process_interrupted"])
async def test_first_login_unknown_create_requires_operator_settlement_before_retry(
    directory, enrollments, native_outcome, monkeypatch
):
    class ProcessInterrupted(BaseException):
        pass

    async with enrollments() as session:
        created = await domain_iam.create_managed_user(
            {"name": "uncertain", "email": "uncertain@test.invalid", "password": PASSWORD},
            "domain",
            manager("system-admin"),
            session,
        )
        enrollment = (await session.execute(select(DomainEnrollment))).scalar_one()
        quotas = dict(enrollment.personal_quotas)
    uid = created["user_id"]
    original_user = vars(directory.users[uid]).copy()
    create = directory.ks.projects.create
    calls = []

    def unknown(**attrs):
        calls.append(attrs.copy())
        if native_outcome != "absent":
            create(**attrs)
        if native_outcome == "process_interrupted":
            raise ProcessInterrupted("Process interrupted after native commit")
        raise ConnectionError("Create response lost")

    directory.ks.projects.create = unknown
    error = ProcessInterrupted if native_outcome == "process_interrupted" else HTTPException
    with pytest.raises(error):
        await account_spaces.ensure_personal_project(uid)
    for _ in range(2):
        with pytest.raises(HTTPException) as fenced:
            await account_spaces.ensure_personal_project(uid)
        assert fenced.value.detail == "personal_project_recovery_required"
    assert len(calls) == 1 and vars(directory.users[uid]) == original_user
    recovery = await account_spaces.personal_recovery_status(uid, created["identity_domain_id"])
    assert recovery["native_calls_settled_required"] and not recovery["retryable"]
    assert await account_spaces.personal_recovery_status(uid, "foreign-home") is None
    with pytest.raises(HTTPException) as forged:
        await account_spaces.settle_personal_project(
            recovery["operation_id"],
            {**manager(uid), "is_system_admin": True},
            native_calls_settled=True,
        )
    assert forged.value.status_code == 403 and len(calls) == 1
    with pytest.raises(HTTPException) as unacknowledged:
        await account_spaces.settle_personal_project(
            recovery["operation_id"],
            manager("system-admin"),
            native_calls_settled=False,
        )
    assert unacknowledged.value.status_code == 422
    settled = await account_spaces.settle_personal_project(
        recovery["operation_id"],
        manager("system-admin"),
        native_calls_settled=True,
    )
    assert settled["status"] == "cancelled" and vars(directory.users[uid]) == original_user
    directory.ks.projects.create = create
    from app.services import enrollment_policy

    changed_policy = AsyncMock(return_value={"personal_quotas": {"instances": -1}})
    monkeypatch.setattr(enrollment_policy, "read_policy", changed_policy)
    primary = await account_spaces.ensure_personal_project(uid)
    assert await account_spaces.ensure_personal_project(uid) == primary
    assert len(directory.personal_projects) == 1 and vars(directory.users[uid]) == original_user
    changed_policy.assert_not_awaited()
    async with enrollments() as session:
        intents = (await session.execute(select(PersonalProjectIntent))).scalars().all()
        assert {row.status for row in intents} == {"cancelled", "accepted"}
        assert all(row.personal_quotas == quotas for row in intents)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["quota", "activation", "finalize"])
async def test_first_login_late_response_loss_never_replays_or_accepts_unverified_primary(
    directory, enrollments, monkeypatch, phase
):
    from app.services import enrollment_policy

    async with enrollments() as session:
        created = await domain_iam.create_managed_user(
            {"name": "late", "email": "late@test.invalid", "password": PASSWORD},
            "domain",
            manager("system-admin"),
            session,
        )
    uid = created["user_id"]
    original_user = vars(directory.users[uid]).copy()
    quota = enrollment_policy.initialize_personal_quotas
    update = directory.ks.projects.update
    save = domain_iam._save
    calls = []

    async def lost_quota(*args, **kwargs):
        calls.append("quota")
        await quota(*args, **kwargs)
        raise HTTPException(503, "Quota response lost")

    def lost_activation(*args, **kwargs):
        calls.append("activation")
        update(*args, **kwargs)
        raise ConnectionError("Activation response lost")

    async def lost_finalize(*args, **kwargs):
        if isinstance(args[0], PersonalProjectIntent) and kwargs.get("status") == "accepted":
            calls.append("finalize")
            raise HTTPException(503, "SQL finalize unavailable")
        return await save(*args, **kwargs)

    if phase == "quota":
        monkeypatch.setattr(enrollment_policy, "initialize_personal_quotas", lost_quota)
    elif phase == "activation":
        directory.ks.projects.update = lost_activation
    else:
        monkeypatch.setattr(domain_iam, "_save", lost_finalize)
    with pytest.raises(HTTPException):
        await account_spaces.ensure_personal_project(uid)
    for _ in range(2):
        with pytest.raises(HTTPException) as fenced:
            await account_spaces.ensure_personal_project(uid)
        assert fenced.value.detail == "personal_project_recovery_required"
    assert calls == [phase] and len(directory.personal_projects) == 1
    assert vars(directory.users[uid]) == original_user
    recovery = await account_spaces.personal_recovery_status(uid, created["identity_domain_id"])
    assert recovery["native_calls_settled_required"]
    settled = await account_spaces.settle_personal_project(
        recovery["operation_id"],
        manager("system-admin"),
        native_calls_settled=True,
    )
    assert settled["status"] == ("cancelled" if phase == "quota" else "accepted")
    monkeypatch.setattr(enrollment_policy, "initialize_personal_quotas", quota)
    directory.ks.projects.update = update
    monkeypatch.setattr(domain_iam, "_save", save)
    primary = await account_spaces.ensure_personal_project(uid)
    assert primary["enabled"] and len(directory.personal_projects) == 1
    assert vars(directory.users[uid]) == original_user


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_completed", [False, True])
async def test_managed_acceptance_commit_loss_never_compensates_enabled_identity(
    directory, enrollments, monkeypatch, commit_completed
):
    save = domain_iam._save

    async def lost_acceptance(row, *args, **kwargs):
        if isinstance(row, DomainEnrollment) and row.kind == "managed_create" and kwargs.get("status") == "accepted":
            if commit_completed:
                await save(row, *args, **kwargs)
            raise HTTPException(503, "Acceptance commit reply lost")
        return await save(row, *args, **kwargs)

    monkeypatch.setattr(domain_iam, "_save", lost_acceptance)
    async with enrollments() as session:
        with pytest.raises(HTTPException) as lost:
            await domain_iam.create_managed_user(
                {"name": "commit-loss", "email": "commit-loss@test.invalid", "password": PASSWORD},
                "domain",
                manager("system-admin"),
                session,
            )
        assert lost.value.status_code == 503 and "acceptance outcome is unknown" in lost.value.detail
        enrollment = (await session.execute(select(DomainEnrollment))).scalar_one()
        uid = enrollment.user_id
        assert directory.users[uid].enabled and directory.users[uid].password == PASSWORD
        assert enrollment.status == ("accepted" if commit_completed else "activating")
        assert not directory.personal_projects and not directory.personal_direct
        assert not [call for call in directory.calls if call[0] in {"delete", "revoke"}]
    if commit_completed:
        primary = await account_spaces.ensure_personal_project(uid)
        assert primary["enabled"] and len(directory.personal_projects) == 1
    else:
        with pytest.raises(HTTPException) as fenced:
            await account_spaces.ensure_personal_project(uid)
        assert fenced.value.detail == "personal_project_recovery_required"
        assert not directory.personal_projects
    assert directory.users[uid].enabled and directory.users[uid].password == PASSWORD


@pytest.mark.asyncio
async def test_historical_creating_receipt_never_infers_quota_calls_settled_from_readback(directory, enrollments):
    primary = await account_spaces.ensure_personal_project("foreign")
    directory.personal_projects[primary["id"]].enabled = False
    async with enrollments() as session:
        intent = (await session.execute(select(PersonalProjectIntent))).scalar_one()
        intent.status = "creating"
        await session.commit()
    with pytest.raises(HTTPException) as fenced:
        await account_spaces.ensure_personal_project("foreign")
    assert fenced.value.detail == "personal_project_recovery_required"
    assert not directory.personal_projects[primary["id"]].enabled
    recovery = await account_spaces.personal_recovery_status("foreign", "other")
    assert recovery["native_calls_settled_required"] and not recovery["retryable"]
    assert len(directory.personal_projects) == 1


@pytest.mark.asyncio
async def test_managed_and_markerless_interactive_admins_both_prepare_personal(directory, enrollments, monkeypatch):
    from app.api.identity import auth
    from app.services import login_preferences

    monkeypatch.setattr(login_preferences, "read", AsyncMock(return_value={"remember_last_workspace": False}))

    async with enrollments() as session:
        created = await domain_iam.create_managed_user(
            {"name": "future-admin", "email": "future-admin@test.invalid", "password": PASSWORD},
            "domain",
            manager("system-admin"),
            session,
        )
    uid = created["user_id"]
    directory.system_admins.add(uid)
    landing = AsyncMock(return_value={"prepared": True})
    monkeypatch.setattr(auth, "_prepare_domain_session", landing)
    data = {"user_id": uid, "identity_domain_id": created["identity_domain_id"], "is_system_admin": True}
    assert (await auth._prepare_initial_session(data))["prepared"] is True
    primary = account_spaces.personal_project(uid, ks=directory.ks)
    assert primary is not None and len(directory.personal_projects) == 1
    assert landing.call_args.args[1] == primary["domain_id"]
    assert landing.call_args.kwargs["requested_project_id"] == primary["id"]
    assert (await auth._prepare_initial_session(data))["prepared"] is True
    assert len(directory.personal_projects) == 1

    operator = directory.users["operator"]
    original = vars(operator).copy()
    prepared = await auth._prepare_initial_session(
        {"user_id": "operator", "identity_domain_id": operator.domain_id, "is_system_admin": True}
    )
    assert prepared["prepared"] is True and prepared["initial_workspace"]["kind"] == "personal"
    assert vars(operator) == original and len(directory.personal_projects) == 2


@pytest.mark.asyncio
async def test_historical_unknown_shared_create_settles_without_rebinding_operator_domain(directory, enrollments):
    marker = "historical-accounts-create"
    historical = SimpleNamespace(
        id="historical-accounts",
        name="accounts",
        enabled=True,
        afterglow_domain_kind="account",
        afterglow_topology_id=marker,
    )
    directory.personal_domains[historical.id] = historical
    async with enrollments() as session:
        session.add(SharedDomainIntent(kind="accounts", marker=marker, status="creating", history=[]))
        await session.commit()
    with pytest.raises(HTTPException) as unacknowledged:
        await account_spaces.settle_shared_domain("account", manager("system-admin"), native_calls_settled=False)
    assert unacknowledged.value.status_code == 422
    settled = await account_spaces.settle_shared_domain("accounts", manager("system-admin"), native_calls_settled=True)
    assert settled == {"kind": "accounts", "domain_id": historical.id, "status": "accepted"}
    with pytest.raises(HTTPException) as ambiguous:
        account_spaces.shared_domain("account")
    assert ambiguous.value.status_code == 503
    with pytest.raises(HTTPException) as fresh:
        await account_spaces.ensure_personal_project("foreign")
    assert fresh.value.status_code == 503
    assert directory.ks.domains.get(historical.id) is historical and historical.name == "accounts"
    assert not directory.domain_writes and not directory.creates and not directory.personal_projects


@pytest.mark.asyncio
async def test_uncertain_primary_creation_never_replays(directory, enrollments):
    native, calls = directory.ks.projects.create, []

    def lost(**attrs):
        calls.append(attrs)
        native(**attrs)
        raise ConnectionError("Native personal project reply lost")

    directory.ks.projects.create = lost
    async with enrollments() as session:
        issued = await domain_iam.invite({"email": "new@test.invalid"}, manager(), session)
        token = email_token(directory.sent[-1])
        with pytest.raises(HTTPException):
            await domain_iam.redeem(token, "invitation", session, name="new", password=PASSWORD)
        row = await session.get(DomainEnrollment, issued["id"])
        assert row.status == "recovery_required" and row.project_creation_uncertain
        uid = row.user_id
        with pytest.raises(HTTPException) as replay:
            await domain_iam.redeem(token, "invitation", session, name="new", password=PASSWORD)
        assert replay.value.status_code == 410
    with pytest.raises(HTTPException):
        await account_spaces.ensure_personal_project(uid)
    assert len(calls) == 1 and len(directory.creates) == 1 and not directory.users[uid].enabled
    assert len(directory.personal_domains) == 2


@pytest.mark.asyncio
async def test_legacy_login_preserves_identity_and_reuses_primary(directory, enrollments):
    original, grants = vars(directory.users["foreign"]).copy(), list(directory.direct)
    first = await account_spaces.ensure_personal_project("foreign")
    assert await account_spaces.ensure_personal_project("foreign") == first
    assert vars(directory.users["foreign"]) == original and directory.direct == grants
    assert not directory.creates and len(directory.personal_projects) == 1
    async with enrollments() as session:
        row = (await session.execute(select(PersonalProjectIntent))).scalar_one()
        assert row.status == "accepted" and row.primary_user_id == "foreign"
        assert row.personal_project_id == first["id"] and row.personal_project_name == first["name"]
    extra = await account_spaces.create_personal_project("foreign", description="Scratch work")
    assert extra["id"] != first["id"] and extra["domain_id"] == first["domain_id"]
    assert directory.personal_projects[extra["id"]].afterglow_personal_primary is False
    assert account_spaces.personal_project("foreign")["id"] == first["id"]


@pytest.mark.asyncio
async def test_legacy_unknown_create_fences_login_and_preserves_identity(directory, enrollments):
    original, calls = vars(directory.users["foreign"]).copy(), []

    def unknown(**attrs):
        calls.append(attrs)
        raise ConnectionError("Personal create not settled")

    directory.ks.projects.create = unknown
    with pytest.raises(HTTPException) as first_failure:
        await account_spaces.ensure_personal_project("foreign")
    assert first_failure.value.status_code == 503
    with pytest.raises(HTTPException) as fenced:
        await account_spaces.ensure_personal_project("foreign")
    assert fenced.value.status_code == 503 and fenced.value.detail == "personal_project_recovery_required"
    assert len(calls) == 1 and vars(directory.users["foreign"]) == original and not directory.creates


@pytest.mark.asyncio
async def test_interactive_operator_name_is_human_but_reserved_directories_stay_protected(directory, enrollments):
    original = vars(directory.users["operator"]).copy()
    primary = await account_spaces.ensure_personal_project("operator")
    assert primary["enabled"] and vars(directory.users["operator"]) == original
    assert project_service._direct_ids(directory.ks.role_assignments.list(project=primary["id"]), "operator") == {
        rid("member")
    }
    await account_spaces.ensure_personal_project("foreign")
    for domain in directory.personal_domains.values():
        with pytest.raises(HTTPException) as rejected:
            await domain_iam.directory_users(domain.id)
        assert rejected.value.status_code == 403
    assert not directory.creates


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["delayed_commit", "readback_failure", "process_interrupted"])
async def test_unsettled_grant_never_compensates_from_absence_or_replays(directory, enrollments, outcome):
    class ProcessInterrupted(BaseException):
        pass

    native_grant = directory.ks.roles.grant
    native_assignments = directory.ks.role_assignments.list
    dispatched = []
    pending = []
    readback_failed = False

    def grant(role_id, **attrs):
        dispatched.append((role_id, attrs))
        if outcome == "process_interrupted":
            raise ProcessInterrupted()
        if outcome == "delayed_commit":
            pending.append((role_id, attrs))
            raise ConnectionError("Native request remains in progress after lost response")
        return native_grant(role_id, **attrs)

    def assignments(**attrs):
        nonlocal readback_failed
        if (
            outcome == "readback_failure"
            and dispatched
            and not readback_failed
            and attrs.get("project") == "default-project"
        ):
            readback_failed = True
            raise ConnectionError("Native grant reply succeeded but readback is unavailable")
        return native_assignments(**attrs)

    directory.ks.roles.grant = grant
    directory.ks.role_assignments.list = assignments
    original = vars(directory.users["member"]).copy()
    async with enrollments() as session:
        issued = await domain_iam.invite({"email": "member@test.invalid"}, manager(), session)
        token = email_token(directory.sent[-1])
        error = ProcessInterrupted if outcome == "process_interrupted" else HTTPException
        with pytest.raises(error):
            await domain_iam.redeem(token, "invitation", session, token_info=manager("member"))
        row = await session.get(DomainEnrollment, issued["id"])
        assert row.added_grants[-1]["phase"] == ("applying" if outcome == "process_interrupted" else "unknown")
        if outcome != "process_interrupted":
            assert row.status == "recovery_required"
        if outcome != "readback_failure":
            assert not project_service._direct_ids(directory.default_direct, "member")
        with pytest.raises(HTTPException) as no_proof:
            await domain_iam.revoke(row.id, manager(), session)
        assert no_proof.value.status_code == 503 and row.status == "recovery_required"
        assert not [call for call in directory.calls if call[0] == "revoke"]
        assert not domain_iam.enrollment_dto(row)["native_writes_settled"]
        with pytest.raises(HTTPException) as replay:
            await domain_iam.redeem(token, "invitation", session, token_info=manager("member"))
        assert replay.value.status_code == 410 and len(dispatched) == 1
        for invalid_ack in (False, "true", 1, None):
            with pytest.raises(HTTPException) as rejected:
                await domain_iam.settle_enrollment_native_writes(
                    row.id,
                    manager("system-admin"),
                    session,
                    domain_id="domain",
                    native_writes_settled=invalid_ack,
                )
            assert rejected.value.status_code == 422
        with pytest.raises(HTTPException) as forbidden:
            await domain_iam.settle_enrollment_native_writes(
                row.id,
                manager("member"),
                session,
                domain_id="domain",
                native_writes_settled=True,
            )
        assert forbidden.value.status_code == 403
        # The provider completes outside the request. A role that was absent at
        # failure time can appear later, without any Afterglow replay.
        for role_id, attrs in pending:
            native_grant(role_id, **attrs)
        settled = await domain_iam.settle_enrollment_native_writes(
            row.id,
            manager("system-admin"),
            session,
            domain_id="domain",
            native_writes_settled=True,
        )
        assert settled["native_writes_settled"] and row.added_grants[-1]["phase"] == "settled"
        assert row.added_grants[-1]["settled_by"] == "system-admin"
        await domain_iam.revoke(row.id, manager(), session)
        assert row.status == "revoked" and not project_service._direct_ids(directory.default_direct, "member")
        assert vars(directory.users["member"]) == original and len(dispatched) == 1


@pytest.mark.asyncio
async def test_joined_directory_drops_revoked_foreign_membership_and_keeps_disabled_home(directory):
    directory.users["member"].enabled = False
    directory.default_direct.append(
        {
            "user": {"id": "foreign"},
            "role": {"id": rid("project_reader")},
            "scope": {"project": {"id": "default-project"}},
        }
    )
    assert {u.id for u in await domain_iam.directory_users("domain")} >= {"foreign", "member"}
    directory.default_direct.clear()
    assert "foreign" not in {u.id for u in await domain_iam.directory_users("domain")}
    assert directory.users["foreign"].domain_id == "other"


def test_real_native_sdk_duplicate_display_names_and_lossy_sdk_resolution(monkeypatch):
    domains, requests = {}, []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.command, self.path, body))
            attrs = body["domain"]
            if any(d["name"] == attrs["name"] for d in domains.values()):
                return self.respond(409, {"error": {"message": "Native domain name must be unique"}})
            did = f"domain-{len(domains)}"
            domains[did] = {"id": did, **attrs}
            self.respond(201, {"domain": domains[did]})

        def do_GET(self):
            path = urlsplit(self.path).path
            requests.append((self.command, path, None))
            if path == "/v3/domains":
                return self.respond(200, {"domains": list(domains.values())})
            did = path.removeprefix("/v3/domains/")
            if did not in domains:
                return self.respond(404, {"error": {"message": "Domain not found"}})
            self.respond(200, {"domain": domains[did]})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    transport = native_session.Session(auth=noauth.NoAuth())
    native = Client(session=transport, endpoint_override=f"http://127.0.0.1:{server.server_port}/v3")
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: native)
    try:
        first = native.domains.create(name=domain_display.native_name(), enabled=True, afterglow_display_name="Shared")
        second = native.domains.create(name=domain_display.native_name(), enabled=True, afterglow_display_name="Shared")
        assert first.id != second.id and first.name != second.name
        assert domain_scope.resolve_domain(first.id)["name"] == "Shared"
        assert domain_scope.resolve_domain(second.id)["name"] == "Shared"
        with pytest.raises(HTTPException) as ambiguous:
            domain_scope.resolve_domain("Shared")
        assert ambiguous.value.status_code == 409 and "domain ID" in ambiguous.value.detail
        lossy = Domain(**domains[first.id])
        assert domain_display.display_name(lossy) == "Shared"
        domains[second.id].pop("afterglow_display_name")
        assert domain_scope.resolve_domain(second.name)["id"] == second.id
        assert len([r for r in requests if r[0] == "POST"]) == 2
    finally:
        transport.session.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_native_member_revocation_never_creates_a_replacement_primary(directory, enrollments):
    primary = await account_spaces.ensure_personal_project("foreign")
    directory.ks.roles.revoke(rid("member"), user="foreign", project=primary["id"])
    with pytest.raises(HTTPException):
        await account_spaces.ensure_personal_project("foreign")
    assert len(directory.personal_projects) == 1 and not directory.creates


@pytest.mark.asyncio
async def test_active_primary_cannot_bypass_unfinished_enrollment_or_disabled_home(directory, enrollments):
    await account_spaces.ensure_personal_project("foreign")
    async with enrollments() as session:
        row = DomainEnrollment(
            kind="external",
            domain_id=None,
            email="foreign@test.invalid",
            token_hash="active-incomplete",
            user_id="foreign",
            new_user=True,
            status="activating",
            expires_at=domain_iam.datetime.now(domain_iam.UTC),
        )
        session.add(row)
        await session.commit()
    with pytest.raises(HTTPException) as incomplete:
        await account_spaces.ensure_personal_project("foreign")
    assert incomplete.value.detail == "personal_project_recovery_required"
    assert len(directory.personal_projects) == 1 and not directory.creates
    async with enrollments() as session:
        row = (await session.execute(select(DomainEnrollment))).scalar_one()
        row.status = "accepted"
        await session.commit()
    native_get = directory.ks.domains.get

    def disabled_home(did):
        domain = native_get(did)
        if did == "other":
            domain.enabled = False
        return domain

    directory.ks.domains.get = disabled_home
    with pytest.raises(HTTPException) as disabled:
        await account_spaces.ensure_personal_project("foreign")
    assert disabled.value.status_code == 403 and len(directory.personal_projects) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["legacy_personal", "managed_create", "registration", "invitation"])
@pytest.mark.parametrize("kind", ["account", "personal"])
@pytest.mark.parametrize("fault", ["missing", "disabled", "wrong_kind", "ambiguous", "wrong_case", "display_only"])
async def test_invalid_operator_domain_fails_before_human_or_project_creation(
    directory, enrollments, entry, kind, fault
):
    did = "operator-accounts" if kind == "account" else "operator-personal"
    domain = directory.personal_domains[did]
    if fault == "missing":
        del directory.personal_domains[did]
    elif fault == "disabled":
        domain.enabled = False
    elif fault == "wrong_kind":
        domain.afterglow_domain_kind = "organization"
    elif fault == "ambiguous":
        directory.personal_domains["duplicate"] = SimpleNamespace(id="duplicate", name=domain.name, enabled=True)
    elif fault == "wrong_case":
        domain.name = domain.name.lower()
    else:
        domain.afterglow_display_name, domain.name = domain.name, "opaque-organization-name"
    original_domains = {key: vars(value).copy() for key, value in directory.personal_domains.items()}
    original_users = {key: vars(value).copy() for key, value in directory.users.items()}
    with pytest.raises(HTTPException) as denied:
        if entry == "legacy_personal":
            await account_spaces.ensure_personal_project("foreign")
        else:
            async with enrollments() as session:
                if entry == "managed_create":
                    await domain_iam.create_managed_user(
                        {"name": "new", "email": "new@test.invalid", "password": PASSWORD},
                        "domain",
                        manager("system-admin"),
                        session,
                    )
                else:
                    if entry == "registration":
                        directory.settings.auth.public_signup_enabled = True
                        await domain_iam.register("new@test.invalid", session)
                    else:
                        await domain_iam.invite({"email": "new@test.invalid"}, manager(), session)
                    await domain_iam.redeem(
                        email_token(directory.sent[-1]), entry, session, name="new", password=PASSWORD
                    )
    assert denied.value.status_code == 503
    assert not directory.domain_writes and not directory.creates and not directory.personal_projects
    assert not directory.default_direct and not directory.personal_direct
    assert {key: vars(value) for key, value in directory.personal_domains.items()} == original_domains
    assert {key: vars(value) for key, value in directory.users.items()} == original_users


@pytest.mark.asyncio
@pytest.mark.parametrize("marked", [False, True])
async def test_operator_domains_resolve_without_metadata_or_native_writes(directory, enrollments, marked):
    for kind, did in (("account", "operator-accounts"), ("personal", "operator-personal")):
        if marked:
            directory.personal_domains[did].afterglow_domain_kind = kind
    original = {did: vars(domain).copy() for did, domain in directory.personal_domains.items()}
    async with domain_iam._iam_write() as mutation:
        first = await account_spaces.ensure_shared_domains(mutation=mutation)
        second = await account_spaces.ensure_shared_domains(mutation=mutation)
    assert first == second
    assert first["account"].id == "operator-accounts" and first["personal"].id == "operator-personal"
    assert {did: vars(domain) for did, domain in directory.personal_domains.items()} == original
    assert not directory.domain_writes and not directory.creates and not directory.personal_projects
    async with enrollments() as session:
        assert not (await session.execute(select(SharedDomainIntent))).scalars().all()


@pytest.mark.asyncio
async def test_existing_owner_personal_home_password_and_external_tuple_are_never_migrated(directory, enrollments):
    user = directory.users["foreign"]
    user.afterglow_external_identities = [{"issuer": "https://idp.test.invalid", "subject": "original-sub"}]
    async with domain_iam._iam_write() as mutation:
        shared = await account_spaces.ensure_shared_domains(mutation=mutation)
    legacy = directory.ks.projects.create(
        name="preserved-personal",
        domain=shared["personal"].id,
        enabled=True,
        afterglow_personal_user_id="foreign",
        afterglow_personal_primary=True,
    )
    for role in ("project_owner", "project_reader"):
        directory.ks.roles.grant(rid(role), user="foreign", project=legacy.id)
    original_user, original_project = vars(user).copy(), vars(legacy).copy()
    original_grants = list(directory.personal_direct)
    original_calls = list(directory.calls)
    result = await account_spaces.ensure_personal_project("foreign")
    assert result["id"] == legacy.id and result["name"] == "preserved-personal"
    assert vars(user) == original_user and vars(legacy) == original_project
    assert directory.personal_direct == original_grants and directory.calls == original_calls
    assert not directory.creates and not directory.default_direct


def test_generated_personal_name_is_normalized_unique_and_bounded():
    first = account_spaces.project_name("  A name / " + "x" * 500)
    second = account_spaces.project_name("  A name / " + "x" * 500)
    assert len(first) == len(second) == 64
    assert first.startswith("A-name-") and first != second
    assert len(account_spaces.project_name("external-" + "f" * 64)) == 64


@pytest.mark.asyncio
async def test_personal_activation_rejects_native_domain_inherited_authority(directory, enrollments):
    native = directory.ks.role_assignments.list

    def assignments(**attrs):
        rows = list(native(**attrs))
        for domain in directory.personal_domains.values():
            if domain.name == "Personal" and not attrs.get("effective") and attrs.get("user") in {None, "foreign"}:
                rows.append(
                    {
                        "user": {"id": "foreign"},
                        "role": {"id": rid("project_reader")},
                        "scope": {"domain": {"id": domain.id}, "OS-INHERIT:inherited_to": "projects"},
                    }
                )
        return rows

    directory.ks.role_assignments.list = assignments
    async with enrollments() as session:
        await domain_iam.invite({"email": "new@test.invalid"}, manager(), session)
        with pytest.raises(HTTPException):
            await domain_iam.redeem(
                email_token(directory.sent[-1]), "invitation", session, name="new", password=PASSWORD
            )
    assert directory.personal_projects and all(not project.enabled for project in directory.personal_projects.values())
    assert not project_service._direct_ids(directory.default_direct, directory.creates[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["member", "FOREIGN@TEST.INVALID"])
async def test_registration_cannot_lock_out_a_legacy_global_login_alias(directory, enrollments, username):
    directory.settings.auth.public_signup_enabled = True
    original = {uid: vars(user).copy() for uid, user in directory.users.items()}
    async with enrollments() as session:
        await domain_iam.register("fresh@test.invalid", session)
        token = email_token(directory.sent[-1])
        with pytest.raises(HTTPException) as collision:
            await domain_iam.redeem(token, "registration", session, name=username, password=PASSWORD)
        assert collision.value.status_code == 409
        row = (await session.execute(select(DomainEnrollment))).scalar_one()
        assert row.status == "pending" and row.user_id is None
    assert not directory.creates and not directory.personal_projects and not directory.domain_writes
    assert {uid: vars(user) for uid, user in directory.users.items()} == original


@pytest.mark.asyncio
async def test_registration_email_cannot_shadow_an_existing_email_shaped_username(directory, enrollments):
    directory.settings.auth.public_signup_enabled = True
    directory.users["member"].name = "reserved@test.invalid"
    async with enrollments() as session:
        await domain_iam.register("reserved@test.invalid", session)
        with pytest.raises(HTTPException) as collision:
            await domain_iam.redeem(
                email_token(directory.sent[-1]), "registration", session, name="fresh", password=PASSWORD
            )
        assert collision.value.status_code == 409
    assert not directory.creates and not directory.personal_projects and not directory.domain_writes


@pytest.mark.asyncio
async def test_reserved_domains_cannot_issue_invitations(directory, enrollments, enrollment_app):
    await account_spaces.ensure_personal_project("foreign")
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        for native_domain in directory.personal_domains.values():
            enrollment_app.dependency_overrides[require_domain_manager] = lambda did=native_domain.id: manager(
                "domain-manager", did
            )
            response = await client.post("/api/v1/iam/invitations", json={"email": "new@test.invalid"})
            assert response.status_code == 403
    assert not directory.sent and not directory.creates
    async with enrollments() as session:
        assert not (await session.execute(select(DomainEnrollment))).scalars().all()
