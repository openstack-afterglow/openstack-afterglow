"""One email, exact per-project grants and the existing durable recovery journal."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info, require_domain_manager
from app.api.identity import iam, onboarding
from app.database import get_session
from app.models.domain_iam import DomainEnrollment
from app.services import domain_iam, project_service
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_iam import (
    PASSWORD,
    email_token,
    manager,
)
from tests.test_domain_iam import (
    directory as directory,
)
from tests.test_domain_iam import (
    enrollments as enrollments,
)
from tests.test_project_membership_roles import PROJECT, rid

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("ownership_journal")]
SECOND = "22222222-2222-4222-8222-222222222222"


def plan():
    return [
        {"project_id": PROJECT, "role_ids": [rid("project_member")]},
        {"project_id": SECOND, "role_ids": [rid("project_reader")]},
    ]


def second_project(directory):
    directory.extra_projects[SECOND] = SimpleNamespace(
        id=SECOND, name="Second project", domain_id="domain", enabled=True, description=""
    )


async def issue(directory, enrollments, *, email="member@test.invalid"):
    second_project(directory)
    async with enrollments() as session:
        result = await domain_iam.invite({"email": email, "projects": plan()}, manager(), session)
    assert len(directory.sent) == 1
    body = "\n".join(
        part.get_payload(decode=True).decode()
        for part in directory.sent[-1].walk()
        if part.get_content_type() == "text/plain"
    )
    assert all(value in body for value in (PROJECT, SECOND, rid("project_member"), rid("project_reader")))
    return result, email_token(directory.sent[-1])


@pytest.mark.parametrize("new_account", [False, True])
async def test_one_email_accepts_both_exact_projects_plus_Default(directory, enrollments, new_account):
    issued, token = await issue(
        directory, enrollments, email="new@test.invalid" if new_account else "member@test.invalid"
    )
    assert [p["project_id"] for p in issued["projects"]] == [PROJECT, SECOND]
    async with enrollments() as session:
        public = await domain_iam.invitation_info(token, session)
        assert [p["project_id"] for p in public["projects"]] == [PROJECT, SECOND]
        account = await domain_iam.redeem(
            token,
            "invitation",
            session,
            **({"name": "new-invitee", "password": PASSWORD} if new_account else {"token_info": manager("member")}),
        )
        uid = account["user_id"]
        assert rid("project_member") in project_service._direct_ids(directory.direct, uid)
        assert project_service._direct_ids(directory.extra_direct, uid) == {rid("project_reader")}
        assert project_service._direct_ids(directory.default_direct, uid) == {rid("project_reader")}
        row = await session.get(DomainEnrollment, issued["id"])
        assert row.status == "accepted" and all(g["phase"] == "confirmed" for g in row.added_grants)
        with pytest.raises(HTTPException) as replay:
            await domain_iam.redeem(token, "invitation", session, token_info=manager("member"))
        assert replay.value.status_code == 410


@pytest.mark.parametrize("change", ["foreign", "disabled", "role_revoked", "manager_revoked"])
async def test_every_selected_project_and_role_revalidated_before_any_accept_write(directory, enrollments, change):
    _, token = await issue(directory, enrollments)
    before = list(directory.calls)
    if change == "foreign":
        directory.extra_projects[SECOND].domain_id = "other"
    elif change == "disabled":
        directory.extra_projects[SECOND].enabled = False
    elif change == "role_revoked":
        directory.catalog = [r for r in directory.catalog if r["id"] != rid("project_reader")]
    else:
        directory.managers.clear()
    async with enrollments() as session:
        with pytest.raises(HTTPException):
            await domain_iam.redeem(token, "invitation", session, token_info=manager("member"))
    assert directory.calls == before and not directory.creates
    assert not directory.default_direct and not directory.extra_direct


@pytest.mark.parametrize(
    "roles", [[rid("admin")], [rid("project_owner")], ["missing-role"], [rid("project_reader"), rid("project_reader")]]
)
async def test_invitation_project_roles_reject_escalation_invalid_and_duplicate(directory, enrollments, roles):
    second_project(directory)
    async with enrollments() as session:
        with pytest.raises(HTTPException):
            await domain_iam.invite(
                {"email": "new@test.invalid", "projects": [*plan()[:1], {"project_id": SECOND, "role_ids": roles}]},
                manager(),
                session,
            )
    assert not directory.sent and not directory.calls and not directory.creates


async def test_partial_second_project_grant_is_not_replayed_or_compensated_until_settled(directory, enrollments):
    issued, token = await issue(directory, enrollments)
    original = list(directory.direct)
    grant = directory.ks.roles.grant
    attempts = []

    def lost_reply(role_id, **attrs):
        attempts.append((attrs["project"], role_id))
        grant(role_id, **attrs)
        if attrs["project"] == SECOND:
            raise ConnectionError("Second grant response lost after native commit")

    directory.ks.roles.grant = lost_reply
    async with enrollments() as session:
        with pytest.raises(HTTPException):
            await domain_iam.redeem(token, "invitation", session, token_info=manager("member"))
        row = await session.get(DomainEnrollment, issued["id"])
        assert row.status == "recovery_required"
        assert row.added_grants[-1] == {
            "project_id": SECOND,
            "domain_id": "domain",
            "role_id": rid("project_reader"),
            "phase": "unknown",
        }
        before = list(attempts)
        with pytest.raises(HTTPException):
            await domain_iam.revoke(row.id, manager(), session)
        with pytest.raises(HTTPException) as replay:
            await domain_iam.redeem(token, "invitation", session, token_info=manager("member"))
        assert replay.value.status_code == 410 and attempts == before
        await domain_iam.settle_enrollment_native_writes(
            row.id, manager("system-admin"), session, domain_id="domain", native_writes_settled=True
        )
        await domain_iam.revoke(row.id, manager(), session)
        assert row.status == "revoked"
    assert directory.direct == original and not directory.default_direct and not directory.extra_direct
    assert "member" in directory.users and attempts == before


async def test_legacy_persisted_single_project_invitation_still_redeems(directory, enrollments):
    async with enrollments() as session:
        await domain_iam.issue_enrollment(
            session,
            kind="invitation",
            domain_id="domain",
            email="member@test.invalid",
            project_id=PROJECT,
            role_ids=[rid("project_member")],
            invited_by="domain-manager",
        )
        token = email_token(directory.sent[-1])
        await domain_iam.redeem(token, "invitation", session, token_info=manager("member"))
    assert rid("project_member") in project_service._direct_ids(directory.direct, "member")
    assert project_service._direct_ids(directory.default_direct, "member") == {rid("project_reader")}


async def test_http_invitation_projects_contract_and_accept_existing(directory, enrollments):
    second_project(directory)
    first = "11111111-1111-4111-8111-111111111111"
    directory.extra_projects[first] = SimpleNamespace(
        id=first, name="First UUID project", domain_id="domain", enabled=True, description=""
    )
    selected = [{"project_id": first, "role_ids": [rid("project_member")]}, plan()[1]]
    app = FastAPI()
    app.include_router(iam.router, prefix="/api/v1/iam")
    app.include_router(onboarding.router, prefix="/api/v1/auth")
    app.dependency_overrides[require_domain_manager] = manager
    app.dependency_overrides[get_token_info] = lambda: manager("member")

    async def db():
        async with enrollments() as session:
            yield session

    app.dependency_overrides[get_session] = db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        legacy = await client.post(
            "/api/v1/iam/invitations",
            json={"email": "member@test.invalid", "project_id": PROJECT, "role_ids": [rid("project_member")]},
        )
        assert legacy.status_code == 422 and not directory.sent
        result = await client.post(
            "/api/v1/iam/invitations", json={"email": "member@test.invalid", "projects": selected}
        )
        assert result.status_code == 201, result.text
        assert len(result.json()["projects"]) == 2 and len(directory.sent) == 1
        accepted = await client.post(
            "/api/v1/auth/invitations/accept-existing", json={"token": email_token(directory.sent[-1])}
        )
        assert accepted.status_code == 200, accepted.text
    for project in selected:
        grants = [g for g in directory.extra_direct if g["scope"]["project"]["id"] == project["project_id"]]
        assert project_service._direct_ids(grants, "member") == set(project["role_ids"])


async def test_duplicate_or_foreign_project_plan_never_delivers(directory, enrollments):
    second_project(directory)
    for requested in (
        [plan()[0], plan()[0]],
        [*plan()[:1], {"project_id": "foreign", "role_ids": [rid("project_reader")]}],
    ):
        async with enrollments() as session:
            with pytest.raises(HTTPException) as denied:
                await domain_iam.invite({"email": "member@test.invalid", "projects": requested}, manager(), session)
            assert denied.value.status_code in {403, 422}
    assert not directory.sent and not directory.calls


async def test_zero_project_plan_admits_only_Default_without_changing_existing_account(directory, enrollments):
    before = vars(directory.users["member"]).copy()
    direct = list(directory.direct)
    async with enrollments() as session:
        result = await domain_iam.invite({"email": "member@test.invalid", "projects": []}, manager(), session)
        assert result["projects"] == []
        await domain_iam.redeem(email_token(directory.sent[-1]), "invitation", session, token_info=manager("member"))
    assert directory.direct == direct and not directory.extra_direct
    assert project_service._direct_ids(directory.default_direct, "member") == {rid("project_reader")}
    assert vars(directory.users["member"]) == before


async def test_project_filtered_invitation_list_and_revoke_find_second_project(directory, enrollments):
    issued, _ = await issue(directory, enrollments)
    async with enrollments() as session:
        listed = await domain_iam.list_invitations(manager(), session, project_id=SECOND)
        assert [row["id"] for row in listed["items"]] == [issued["id"]]
        await domain_iam.revoke(issued["id"], manager(), session, project_id=SECOND)
        row = await session.get(DomainEnrollment, issued["id"])
        assert row.status == "revoked" and not row.added_grants
    assert not directory.calls


async def test_malformed_multi_project_plan_fails_closed_without_native_writes(directory, enrollments):
    issued, token = await issue(directory, enrollments)
    async with enrollments() as session:
        row = await session.get(DomainEnrollment, issued["id"])
        row.role_ids = [*row.role_ids, row.role_ids[0]]
        await session.commit()
        with pytest.raises(HTTPException) as denied:
            await domain_iam.redeem(token, "invitation", session, token_info=manager("member"))
        assert denied.value.status_code == 503
    assert not directory.calls and not directory.creates and not directory.default_direct


@pytest.mark.parametrize("target", [PROJECT, SECOND])
async def test_history_validates_each_selected_project_domain_before_list_or_revoke(directory, enrollments, target):
    issued, _ = await issue(directory, enrollments)
    project = directory.project if target == PROJECT else directory.extra_projects[target]
    project.domain_id = "other"
    async with enrollments() as session:
        with pytest.raises(HTTPException) as denied_list:
            await domain_iam.list_invitations(manager(), session)
        assert denied_list.value.status_code == 403
        with pytest.raises(HTTPException) as denied_revoke:
            await domain_iam.revoke(issued["id"], manager(), session)
        assert denied_revoke.value.status_code == 403
        row = await session.get(DomainEnrollment, issued["id"])
        assert row.status == "pending"
    assert not directory.calls
