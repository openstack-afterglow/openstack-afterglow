"""Exact system-domain recovery through real routes and disposable enrollment SQL."""

import pytest
from fastapi import FastAPI, HTTPException
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
@pytest.mark.parametrize("new_personal", [False, True])
async def test_unknown_enrollment_requires_exact_system_settlement_before_compensation(
    directory, enrollments, new_personal
):
    original = vars(directory.users["member"]).copy()
    original_target = list(directory.direct)
    async with enrollments() as session:
        operation = await domain_iam.invite(
            {"email": "new@test.invalid" if new_personal else "member@test.invalid"}, manager(), session
        )
    token = email_token(directory.sent[-1])
    grant = directory.ks.roles.grant
    writes = []

    def lost_reply(role_id, **attrs):
        if new_personal and role_id != rid("member"):
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
        endpoint = "/api/v1/auth/invitations/accept" if new_personal else "/api/v1/auth/invitations/accept-existing"
        payload = {"token": token}
        if new_personal:
            payload.update(name="invitee", password=PASSWORD)
        accepted = await client.post(endpoint, json=payload)
        assert accepted.status_code == 503
        if new_personal:
            async with enrollments() as session:
                row = await session.get(DomainEnrollment, operation["id"])
                assert row.status == "recovery_required" and row.accepted_at is None
                assert row.added_grants[-1]["role_id"] == rid("member")
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
    assert not directory.personal_direct and not directory.personal_projects
    assert len(directory.personal_domains) == 2 and not directory.domain_writes


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["absent", "staged", "active"])
async def test_personal_intent_system_recovery_preserves_legacy_identity(directory, enrollments, outcome):
    from app.api.identity import admin_identity
    from app.services import account_spaces

    original = vars(directory.users["foreign"]).copy()
    create, update = directory.ks.projects.create, directory.ks.projects.update
    calls = []

    def unknown_create(**attrs):
        calls.append(attrs)
        if outcome == "staged":
            create(**attrs)
        raise ConnectionError("Native personal create reply lost")

    def lost_activation(pid, **attrs):
        result = update(pid, **attrs)
        if attrs.get("enabled") is True:
            raise ConnectionError("Native activation reply lost")
        return result

    if outcome == "active":
        directory.ks.projects.update = lost_activation
    else:
        directory.ks.projects.create = unknown_create
    with pytest.raises(HTTPException) as first_failure:
        await account_spaces.ensure_personal_project("foreign")
    assert first_failure.value.status_code == 503
    with pytest.raises(HTTPException) as fenced:
        await account_spaces.ensure_personal_project("foreign")
    assert fenced.value.status_code == 503 and fenced.value.detail == "personal_project_recovery_required"
    application = FastAPI()
    application.include_router(admin_identity.router, prefix="/api/v1/admin")
    actor = manager("member")
    application.dependency_overrides[get_token_info] = lambda: actor
    application.dependency_overrides[require_admin] = synthetic_verified_admin
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        root = "/api/v1/admin/account-topology"
        assert (await client.get(root + "/operations")).status_code == 403
        actor = {**manager("system-admin"), "is_system_admin": True}
        listing = await client.get(root + "/operations")
        assert listing.status_code == 200
        operation_id = listing.json()["personal_projects"][0]["id"]
        path = root + f"/personal-projects/{operation_id}/settle"
        for invalid in (False, "true", 1):
            assert (await client.post(path, json={"native_calls_settled": invalid})).status_code == 422
        recovered = await client.post(path, json={"native_calls_settled": True})
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["status"] == ("accepted" if outcome == "active" else "cancelled")
    assert vars(directory.users["foreign"]) == original and not directory.creates
    assert len(directory.personal_domains) == 2
    directory.ks.projects.create, directory.ks.projects.update = create, update
    project = await account_spaces.ensure_personal_project("foreign")
    assert project["enabled"] and len(directory.personal_projects) == 1
    assert len(calls) == (0 if outcome == "active" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("committed", [False, True])
async def test_shared_domain_recovery_never_deletes_or_replays_unknown_create(directory, enrollments, committed):
    from app.api.identity import admin_identity
    from app.models.account_spaces import SharedDomainIntent
    from app.services import account_spaces

    marker = "historical-unknown-create"
    historical = None
    if committed:
        historical = directory.ks.domains.create(
            name="accounts", enabled=True, afterglow_domain_kind="account", afterglow_topology_id=marker
        )
    original_writes = list(directory.domain_writes)
    async with enrollments() as session:
        session.add(SharedDomainIntent(kind="accounts", marker=marker, status="creating", history=[]))
        await session.commit()
    application = FastAPI()
    application.include_router(admin_identity.router, prefix="/api/v1/admin")
    application.dependency_overrides[get_token_info] = lambda: {**manager("system-admin"), "is_system_admin": True}
    application.dependency_overrides[require_admin] = synthetic_verified_admin
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/account-topology/shared-domains/accounts/settle", json={"native_calls_settled": True}
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == ("accepted" if committed else "settled_absent")
    assert response.json()["domain_id"] == (historical.id if committed else None)
    if committed:
        with pytest.raises(HTTPException) as ambiguous:
            account_spaces.shared_domain("account")
        assert ambiguous.value.status_code == 503
        with pytest.raises(HTTPException) as fresh:
            await account_spaces.ensure_personal_project("foreign")
        assert fresh.value.status_code == 503 and not directory.personal_projects
    else:
        await account_spaces.ensure_personal_project("foreign")
        assert account_spaces.shared_domain("account").id == "operator-accounts"
    assert len(directory.personal_domains) == (3 if committed else 2) and not directory.creates
    assert directory.domain_writes == original_writes
