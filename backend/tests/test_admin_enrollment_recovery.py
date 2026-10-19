"""Exact system-domain recovery through real routes and disposable enrollment SQL."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info, require_admin
from app.api.identity import domains, onboarding
from app.database import get_session
from app.models.domain_iam import DomainEnrollment
from app.services import domain_iam, project_service
from tests.admin_gate import synthetic_verified_admin
from tests.test_domain_iam import PASSWORD, email_token, manager
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import enrollments as enrollments
from tests.test_project_membership_roles import rid


@pytest.mark.asyncio
@pytest.mark.parametrize("personal_owner", [False, True])
async def test_unknown_enrollment_requires_exact_system_settlement_before_compensation(
    directory, enrollments, personal_owner
):
    original = vars(directory.users["member"]).copy()
    original_target = list(directory.direct)
    async with enrollments() as session:
        operation = await domain_iam.invite(
            {"email": "new@test.invalid" if personal_owner else "member@test.invalid"}, manager(), session
        )
    token = email_token(directory.sent[-1])
    grant = directory.ks.roles.grant
    writes = []

    def lost_reply(role_id, **attrs):
        if personal_owner and role_id != rid("project_owner"):
            return grant(role_id, **attrs)
        writes.append((role_id, attrs))
        grant(role_id, **attrs)
        raise ConnectionError("Synthetic committed grant reply lost")

    directory.ks.roles.grant = lost_reply
    application = FastAPI()
    application.include_router(domains.router, prefix="/api/v1/admin")
    application.include_router(onboarding.router, prefix="/api/v1/auth")
    actor = manager("member")
    application.dependency_overrides[get_token_info] = lambda: actor
    application.dependency_overrides[require_admin] = synthetic_verified_admin

    async def session_dep():
        async with enrollments() as session:
            yield session

    application.dependency_overrides[get_session] = session_dep
    path = f"/api/v1/admin/domains/domain/enrollment-operations/{operation['id']}"
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        endpoint = "/api/v1/auth/invitations/accept" if personal_owner else "/api/v1/auth/invitations/accept-existing"
        payload = {"token": token}
        if personal_owner:
            payload.update(name="invitee", password=PASSWORD, personal_domain_name="Personal")
        accepted = await client.post(endpoint, json=payload)
        assert accepted.status_code == 503
        if personal_owner:
            async with enrollments() as session:
                row = await session.get(DomainEnrollment, operation["id"])
                assert row.status == "recovery_required" and row.accepted_at is None
                assert row.added_grants[-1]["role_id"] == rid("project_owner")
                assert row.added_grants[-1]["phase"] == "unknown"
                assert not directory.personal_projects[row.personal_project_id].enabled
                assert not directory.users[row.user_id].enabled
                assert not project_service._direct_ids(directory.default_direct, row.user_id)
        assert (await client.get("/api/v1/admin/domains/domain/enrollment-operations")).status_code == 403
        actor = {**manager("system-admin"), "is_system_admin": True}
        listed = await client.get("/api/v1/admin/domains/domain/enrollment-operations")
        assert listed.status_code == 200
        entry = next(row for row in listed.json()["items"] if row["id"] == operation["id"])
        assert entry["recovery_required"] and not entry["native_writes_settled"]
        assert not {"token_hash", "password", "token"} & set(entry)
        assert (await client.delete(path)).status_code == 503
        for invalid in (False, "true", 1):
            assert (await client.post(path + "/reconcile", json={"native_writes_settled": invalid})).status_code == 422
        foreign = path.replace("/domains/domain/", "/domains/other/")
        assert (await client.post(foreign + "/reconcile", json={"native_writes_settled": True})).status_code == 404
        settled = await client.post(path + "/reconcile", json={"native_writes_settled": True})
        assert settled.status_code == 200 and settled.json()["native_writes_settled"]
        assert len(writes) == 1
        assert (await client.delete(path)).status_code == 204
        assert (await client.delete(path)).status_code == 409
    assert not project_service._direct_ids(directory.default_direct, "member")
    assert vars(directory.users["member"]) == original
    assert directory.direct == original_target
    assert not directory.personal_direct and not directory.personal_projects and not directory.personal_domains
