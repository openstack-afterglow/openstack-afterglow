"""Global signup API/state boundaries with real SQL and mutable native adapters."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models.domain_iam import DomainEnrollment
from app.services import domain_iam, project_service
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_iam import PASSWORD, email_token, manager
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import enrollments as enrollments
from tests.test_personal_domains import enrollment_app as enrollment_app
from tests.test_project_membership_roles import rid

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("ownership_journal")]


def enable_signup(directory, domains=()):
    directory.settings.auth.public_signup_enabled = True
    directory.settings.auth.signup_email_domains = list(domains)


def account_body(token):
    return {"token": token, "name": "signup", "password": PASSWORD, "personal_domain_name": "My home"}


def assert_no_native_writes(directory):
    assert not directory.creates and not directory.updates and not directory.calls
    assert not directory.personal_domains and not directory.personal_projects


async def test_options_are_public_truthful_and_never_provision(directory, enrollment_app):
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        response = await client.get("/api/v1/auth/signup/options")
        assert response.status_code == 200
        assert response.json()["signup_enabled"] is False
        enable_signup(directory)
        assert (await client.get("/api/v1/auth/signup/options")).json()["signup_enabled"] is True
        directory.settings.smtp_host = ""
        response = await client.get("/api/v1/auth/signup/options")
        assert response.json()["signup_enabled"] is False
        assert response.json()["smtp_configured"] is False
        assert response.json()["recovery_enabled"] is False
        assert "no-store" in response.headers["Cache-Control"]
        assert response.headers["Referrer-Policy"] == "no-referrer"
    assert_no_native_writes(directory)


async def test_delivered_token_inspection_is_nonconsuming_and_signup_is_personal_only(
    directory, enrollments, enrollment_app
):
    enable_signup(directory)
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        issued = await client.post("/api/v1/auth/registrations", json={"email": " New@BÜCHER.Example. "})
        assert issued.status_code == 202 and issued.json() == {"accepted": True}
        token = email_token(directory.sent[-1])
        assert_no_native_writes(directory)
        async with enrollments() as session:
            row = (await session.execute(select(DomainEnrollment))).scalar_one()
            assert row.domain_id is None and row.status == "pending"
            assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
            assert token not in row.token_hash and row.email == "New@xn--bcher-kva.example"
        for _ in range(2):
            inspected = await client.get(f"/api/v1/auth/registrations/{token}")
            assert inspected.status_code == 200
            assert inspected.json() == {"email": "New@xn--bcher-kva.example", "account_exists": False}
            assert "no-store" in inspected.headers["Cache-Control"]
            assert inspected.headers["Referrer-Policy"] == "no-referrer"
            assert_no_native_writes(directory)
        accepted = await client.post("/api/v1/auth/registrations/accept", json=account_body(token))
        assert accepted.status_code == 200, accepted.text
        result = accepted.json()
        uid, home = result["user_id"], result["identity_domain_id"]
        assert home == result["domain_id"] and home not in {"domain", "other"}
        assert result["domain_name"] == result["identity_domain_name"] == "My home"
        assert directory.users[uid].afterglow_local_password is True
        assert directory.users[uid].domain_id == home and directory.users[uid].password == PASSWORD
        assert project_service._direct_ids(directory.personal_direct, uid) == {
            rid("manager"),
            rid("project_owner"),
            rid("project_reader"),
        }
        assert not project_service._direct_ids(directory.default_direct, uid)
        assert not project_service._direct_ids(directory.direct, uid)
        assert (await client.get(f"/api/v1/auth/registrations/{token}")).status_code == 410
        assert (await client.post("/api/v1/auth/registrations/accept", json=account_body(token))).status_code == 410
    async with enrollments() as session:
        row = (await session.execute(select(DomainEnrollment))).scalar_one()
        assert row.status == "accepted" and row.domain_id == row.identity_domain_id == home
        assert all(grant["domain_id"] == home and grant["phase"] == "confirmed" for grant in row.added_grants)
    assert len(directory.creates) == len(directory.personal_domains) == len(directory.personal_projects) == 1


async def test_old_domain_signup_and_target_injection_are_rejected(directory, enrollment_app):
    enable_signup(directory)
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        for did in ("domain", "other", "nonexistent"):
            response = await client.post(
                f"/api/v1/auth/domains/{did}/registrations", json={"email": "new@test.invalid"}
            )
            assert response.status_code == 403 and response.json()["detail"] == "invitation_required"
        for field in ("domain_id", "targetdomain", "project_id", "role_ids"):
            response = await client.post(
                "/api/v1/auth/registrations", json={"email": "new@test.invalid", field: "domain"}
            )
            assert response.status_code == 422
    assert not directory.sent
    assert_no_native_writes(directory)


@pytest.mark.parametrize("status", ["pending", "delivery_pending", "delivery_failed", "revoked", "accepted"])
async def test_legacy_or_undelivered_tokens_never_admit_to_old_domain(directory, enrollments, status):
    enable_signup(directory)
    token = "legacy-token-" + "a" * 40
    async with enrollments() as session:
        row = DomainEnrollment(
            kind="registration",
            domain_id="domain",
            email="new@test.invalid",
            status=status,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            role_ids=[],
            added_role_ids=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            created_at=datetime.now(UTC),
        )
        session.add(row)
        await session.commit()
        for operation in (
            lambda: domain_iam.registration_info(token, session),
            lambda: domain_iam.redeem(
                token, "registration", session, name="new", password=PASSWORD, personal_domain_name="Home"
            ),
        ):
            with pytest.raises(HTTPException) as failed:
                await operation()
            assert failed.value.status_code == (403 if status == "pending" else 410)
    assert_no_native_writes(directory)


async def test_existing_owner_is_revealed_only_with_token_and_never_reset(directory, enrollment_app):
    enable_signup(directory)
    directory.users["foreign"].email = " Owner@BÜCHER.Example. "
    original = vars(directory.users["foreign"]).copy()
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        issued = await client.post("/api/v1/auth/registrations", json={"email": "owner@xn--bcher-kva.example"})
        assert issued.status_code == 202 and issued.json() == {"accepted": True}
        assert (await client.get("/api/v1/auth/registrations/" + "x" * 43)).status_code == 404
        token = email_token(directory.sent[-1])
        inspected = await client.get(f"/api/v1/auth/registrations/{token}")
        assert inspected.json() == {
            "email": "owner@xn--bcher-kva.example",
            "account_exists": True,
            "identity_domain_id": "other",
            "identity_domain_name": "other",
        }
        assert (await client.post("/api/v1/auth/registrations/accept", json=account_body(token))).status_code == 409
    assert vars(directory.users["foreign"]) == original
    assert_no_native_writes(directory)


async def test_duplicate_legacy_email_is_ambiguous_not_merged_or_linked(directory, enrollments):
    enable_signup(directory)
    directory.users["foreign"].email = "MEMBER@Test.Invalid."
    originals = {uid: vars(directory.users[uid]).copy() for uid in ("member", "foreign")}
    async with enrollments() as session:
        await domain_iam.register("member@test.invalid", session)
        token = email_token(directory.sent[-1])
        with pytest.raises(HTTPException) as ambiguous:
            await domain_iam.registration_info(token, session)
        assert ambiguous.value.status_code == 409
        await session.rollback()
        issued = await domain_iam.invite({"email": "member@test.invalid"}, manager(), session)
        token = email_token(directory.sent[-1])
        with pytest.raises(HTTPException) as ambiguous:
            await domain_iam.redeem(token, "invitation", session, token_info=manager("member"))
        assert ambiguous.value.status_code == 409
        assert (await session.get(DomainEnrollment, issued["id"])).status == "pending"
    assert {uid: vars(directory.users[uid]) for uid in originals} == originals
    assert_no_native_writes(directory)


async def test_global_signup_rechecks_current_policy_and_expiry(directory, enrollments):
    enable_signup(directory)
    async with enrollments() as session:
        await domain_iam.register("new@test.invalid", session)
        token = email_token(directory.sent[-1])
        directory.settings.auth.signup_email_domains = ["elsewhere.invalid"]
        with pytest.raises(HTTPException) as forbidden:
            await domain_iam.redeem(
                token, "registration", session, name="new", password=PASSWORD, personal_domain_name="Home"
            )
        assert forbidden.value.status_code == 403
        row = (await session.execute(select(DomainEnrollment))).scalar_one()
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        with pytest.raises(HTTPException) as expired:
            await domain_iam.registration_info(token, session)
        assert expired.value.status_code == 410
    assert_no_native_writes(directory)


async def test_failed_delivery_cannot_be_inspected_or_redeemed(directory, enrollments):
    enable_signup(directory)
    directory.deliver = False
    async with enrollments() as session:
        with pytest.raises(HTTPException) as failed:
            await domain_iam.register("new@test.invalid", session)
        assert failed.value.status_code == 503
        row = (await session.execute(select(DomainEnrollment))).scalar_one()
        assert row.status == "delivery_failed" and row.domain_id is None
    assert_no_native_writes(directory)


@pytest.mark.parametrize("writer", ["create_account", "create_user", "create_managed_user", "update_user"])
async def test_all_managed_email_writers_reject_foreign_normalized_owner_under_graph_lease(
    directory, enrollments, writer
):
    directory.users["foreign"].email = " Owner@BÜCHER.Example. "
    original = vars(directory.users["foreign"]).copy()
    native_list = directory.ks.users.list

    def list_under_lock(**kwargs):
        assert directory.lock.locked(), "Global uniqueness lookup escaped graph lease"
        return native_list(**kwargs)

    directory.ks.users.list = list_under_lock
    attrs = {
        "email": "owner@xn--bcher-kva.example",
        "name": "unique",
        "password": PASSWORD,
        "personal_domain_name": "Home",
        "enabled": True,
    }
    async with enrollments() as session:
        with pytest.raises(HTTPException) as conflict:
            if writer == "create_account":
                await domain_iam.create_account("domain", "unique", attrs["email"], PASSWORD)
            elif writer == "create_user":
                await domain_iam.create_user(attrs, manager(), session)
            elif writer == "create_managed_user":
                await domain_iam.create_managed_user(attrs, "domain", manager("system-admin"), session)
            else:
                await domain_iam.update_user("member", {"email": attrs["email"]}, manager())
        assert conflict.value.status_code == 409
    assert vars(directory.users["foreign"]) == original
    assert_no_native_writes(directory)


async def test_two_delivered_links_for_same_email_cannot_create_two_homes(directory, enrollments):
    enable_signup(directory)
    tokens = []
    async with enrollments() as session:
        for email in ("new@test.invalid", "NEW@TEST.INVALID."):
            await domain_iam.register(email, session)
            tokens.append(email_token(directory.sent[-1]))

    async def accept(token):
        async with enrollments() as session:
            return await domain_iam.redeem(
                token, "registration", session, name="new", password=PASSWORD, personal_domain_name="Home"
            )

    results = await asyncio.gather(*(accept(token) for token in tokens), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    failure = next(result for result in results if isinstance(result, HTTPException))
    assert failure.status_code == 409
    assert len(directory.creates) == len(directory.personal_domains) == 1
    uid = next(result["user_id"] for result in results if isinstance(result, dict))
    assert not project_service._direct_ids(directory.default_direct, uid)
    assert not project_service._direct_ids(directory.direct, uid)


async def test_public_signup_unknown_personal_grant_is_fenced_without_old_tenant_access(directory, enrollments):
    enable_signup(directory)
    original_grant = directory.ks.roles.grant

    def lost_reply(role_id, *, user, project):
        original_grant(role_id, user=user, project=project)
        raise ConnectionError("Native personal grant committed but reply was lost")

    directory.ks.roles.grant = lost_reply
    async with enrollments() as session:
        await domain_iam.register("new@test.invalid", session)
        token = email_token(directory.sent[-1])
        with pytest.raises(HTTPException) as failed:
            await domain_iam.redeem(
                token, "registration", session, name="new", password=PASSWORD, personal_domain_name="Home"
            )
        assert failed.value.status_code == 503
        row = (await session.execute(select(DomainEnrollment))).scalar_one()
        assert row.status == "recovery_required" and row.domain_id == row.identity_domain_id
        assert row.added_grants[-1]["phase"] == "unknown"
        assert all(grant["domain_id"] == row.identity_domain_id for grant in row.added_grants)
        assert directory.users[row.user_id].enabled is False
        assert not project_service._direct_ids(directory.default_direct, row.user_id)
        assert not project_service._direct_ids(directory.direct, row.user_id)
        with pytest.raises(HTTPException) as replay:
            await domain_iam.redeem(
                token, "registration", session, name="new", password=PASSWORD, personal_domain_name="Home"
            )
        assert replay.value.status_code == 410
    assert len(directory.creates) == 1


async def test_unassigned_signup_failure_requires_system_operator_settlement(directory, enrollments):
    enable_signup(directory)

    def unknown_domain_create(**attrs):
        raise ConnectionError("Provider create outcome is unavailable")

    directory.ks.domains.create = unknown_domain_create
    async with enrollments() as session:
        await domain_iam.register("new@test.invalid", session)
        token = email_token(directory.sent[-1])
        with pytest.raises(HTTPException) as failed:
            await domain_iam.redeem(
                token, "registration", session, name="new", password=PASSWORD, personal_domain_name="Home"
            )
        assert failed.value.status_code == 503
        row = (await session.execute(select(DomainEnrollment))).scalar_one()
        operation_id = row.id
        assert row.domain_id is None and row.status == "recovery_required"
        assert row.domain_creation_uncertain
        assert not (await domain_iam.list_invitations(manager(), session, operations=True))["items"]
        with pytest.raises(HTTPException) as denied:
            await domain_iam.revoke(operation_id, manager(), session, operation=True)
        assert denied.value.status_code == 404
        with pytest.raises(HTTPException) as denied:
            await domain_iam.list_invitations(manager(), session, operations=True, system_domain_id="domain")
        assert denied.value.status_code == 403
        operator = manager("system-admin")
        listed = await domain_iam.list_invitations(operator, session, operations=True, system_domain_id="domain")
        assert [item["id"] for item in listed["items"]] == [operation_id]
        settled = await domain_iam.settle_enrollment_native_writes(
            operation_id, operator, session, domain_id="domain", native_writes_settled=True
        )
        assert settled["status"] == "recovery_required" and settled["native_writes_settled"] is True
        await domain_iam.revoke(operation_id, operator, session, operation=True, system_domain_id="domain")
        assert (await session.get(DomainEnrollment, operation_id)).status == "revoked"
    assert_no_native_writes(directory)


@pytest.mark.parametrize("signal", ["next", "truncated", "limited", "missing_links"])
async def test_native_collection_completeness_signals_block_account_creation(directory, signal):
    body = {"users": [], "links": {"next": None}}
    if signal == "next":
        body["links"]["next"] = "https://identity.test.invalid/v3/users?marker=hidden-owner"
    elif signal == "missing_links":
        body.pop("links")
    else:
        body[signal] = True
    directory.ks.users.client = SimpleNamespace(get=lambda url: (None, body))
    with pytest.raises(HTTPException) as incomplete:
        await domain_iam.create_account("domain", "new", "new@test.invalid", PASSWORD)
    assert incomplete.value.status_code == 503
    assert_no_native_writes(directory)


async def test_native_envelope_lookup_and_matched_account_use_exact_get_metadata(directory):
    account = directory.users["foreign"]
    account.email = "Owner@BÜCHER.Example."
    account.federated = [{"idp_id": "native-idp", "protocols": [{"protocol_id": "oidc", "unique_id": "subject"}]}]
    requests = []

    def native_get(url):
        requests.append(url)
        return None, {
            "users": [{"id": account.id, "domain_id": "other", "email": account.email, "name": account.name}],
            "links": {"next": None},
        }

    directory.ks.users.client = SimpleNamespace(get=native_get)
    async with domain_iam._iam_write():
        matches = await domain_iam._find_accounts(None, email="owner@xn--bcher-kva.example")
    assert requests == ["/users"]
    assert len(matches) == 1 and matches[0].id == "foreign"
    assert matches[0].federated == account.federated
    assert_no_native_writes(directory)


async def test_protected_user_never_trusts_federation_omission_in_list_projection(directory):
    account = directory.users["member"]
    stale_list_item = SimpleNamespace(id=account.id, name=account.name, domain_id=account.domain_id)
    account.federated = [{"idp_id": "native-idp"}]
    assert await domain_iam.protected_user(stale_list_item, "domain") is True
    assert_no_native_writes(directory)


async def test_empty_collection_email_cannot_hide_an_existing_canonical_owner(directory):
    body = {
        "users": [{"id": user.id, "domain_id": user.domain_id, "email": ""} for user in directory.users.values()],
        "links": {"next": None},
    }
    directory.ks.users.client = SimpleNamespace(get=lambda url: (None, body))
    with pytest.raises(HTTPException) as duplicate:
        await domain_iam.create_account("domain", "new", "foreign@test.invalid", PASSWORD)
    assert duplicate.value.status_code == 409
    assert_no_native_writes(directory)


def include_enrollment_admin(app):
    from app.api.deps import get_os_conn, require_admin
    from app.api.identity import enrollment_policy as policy_api

    app.include_router(policy_api.router, prefix="/api/v1/admin")
    app.dependency_overrides[require_admin] = lambda: manager("system-admin")
    app.dependency_overrides[get_os_conn] = lambda: None


async def test_reviewed_email_provisions_personal_home_only_after_approval_with_frozen_quota(
    directory, enrollments, enrollment_app, monkeypatch
):
    from app.models.domain_quotas import DomainQuotaPolicy
    from app.models.enrollment_policy import SignupRequest
    from app.services import domain_projects

    include_enrollment_admin(enrollment_app)
    quotas = {"instances": 2, "cores": 4, "ram": 4096}
    quota_observations = []

    async def verify_disabled_home(domain_id, project_id, lease):
        async with enrollments() as session:
            policy = await session.get(DomainQuotaPolicy, domain_id)
            assert policy.ceilings == policy.defaults == quotas
        project = directory.personal_projects[project_id]
        users = [u for u in directory.users.values() if u.domain_id == domain_id]
        assert project.enabled is False
        assert len(users) == 1 and users[0].enabled is False
        quota_observations.append((domain_id, project_id))

    monkeypatch.setattr(domain_projects, "apply_default_quotas", verify_disabled_home)
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        saved = await client.put(
            "/api/v1/admin/enrollment-policy",
            json={
                "revision": 0,
                "public_signup_enabled": True,
                "approval_mode": "admin",
                "personal_quotas": quotas,
            },
        )
        assert saved.status_code == 200, saved.text
        assert (await client.post("/api/v1/auth/registrations", json={"email": "new@test.invalid"})).status_code == 202
        token = email_token(directory.sent[-1])
        assert (await client.get("/api/v1/admin/signup-requests")).json()["items"] == []
        for path, body in (
            (f"/api/v1/auth/registrations/{token}", None),
            ("/api/v1/auth/registrations/accept", account_body(token)),
        ):
            result = await (client.get(path) if body is None else client.post(path, json=body))
            assert result.status_code == 403 and result.json()["detail"] == "signup_approval_pending"
        assert_no_native_writes(directory)
        requests = (await client.get("/api/v1/admin/signup-requests")).json()["items"]
        assert len(requests) == 1
        async with enrollments() as session:
            row = (await session.execute(select(DomainEnrollment))).scalar_one()
            assert row.account_name is None and row.identity_domain_id is None and row.status == "pending"
        approval = await client.post(f"/api/v1/admin/signup-requests/{requests[0]['id']}/approve", json={})
        assert approval.status_code == 200 and approval.json()["status"] == "approved"
        assert_no_native_writes(directory)
        fresh = email_token(directory.sent[-1])
        assert fresh != token
        assert (await client.get(f"/api/v1/auth/registrations/{fresh}")).status_code == 200
        result = await client.post("/api/v1/auth/registrations/accept", json=account_body(fresh))
        assert result.status_code == 200, result.text
        uid, home = result.json()["user_id"], result.json()["identity_domain_id"]
        assert home == result.json()["domain_id"] and home not in {"domain", "other"}
        assert directory.users[uid].enabled is True
        assert quota_observations == [(home, next(iter(directory.personal_projects)))]
        assert project_service._direct_ids(directory.personal_direct, uid) == {
            rid("manager"),
            rid("project_owner"),
            rid("project_reader"),
        }
        assert not project_service._direct_ids(directory.default_direct, uid)
        assert (await client.post("/api/v1/auth/registrations/accept", json=account_body(token))).status_code == 409
        assert len(directory.creates) == 1
        changed = await client.put(
            "/api/v1/admin/enrollment-policy",
            json={
                "revision": saved.json()["revision"],
                "public_signup_enabled": True,
                "approval_mode": "auto",
                "personal_quotas": {"instances": 0},
            },
        )
        assert changed.status_code == 200
    async with enrollments() as session:
        reviewed = await session.get(SignupRequest, requests[0]["id"])
        assert reviewed.status == "consumed" and reviewed.consumed_by_user_id == uid
        policy = await session.get(DomainQuotaPolicy, home)
        assert policy.ceilings == policy.defaults == quotas
        record = (await session.execute(select(DomainEnrollment).where(DomainEnrollment.user_id == uid))).scalar_one()
        assert record.personal_quotas == quotas and record.status == "accepted"


async def test_manual_signup_gate_covers_new_invite_but_not_existing_account_membership(
    directory, enrollments, enrollment_app
):
    from app.models.enrollment_policy import SignupRequest

    include_enrollment_admin(enrollment_app)
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        saved = await client.put(
            "/api/v1/admin/enrollment-policy",
            json={
                "revision": 0,
                "public_signup_enabled": False,
                "approval_mode": "admin",
                "personal_quotas": {"instances": 0},
            },
        )
        assert saved.status_code == 200
        async with enrollments() as session:
            await domain_iam.invite({"email": "new@test.invalid"}, manager(), session)
        token = email_token(directory.sent[-1])
        pending = await client.post("/api/v1/auth/invitations/accept", json=account_body(token))
        assert pending.status_code == 403 and pending.json()["detail"] == "signup_approval_pending"
        assert_no_native_writes(directory)
        request = (await client.get("/api/v1/admin/signup-requests")).json()["items"][0]
        assert (await client.post(f"/api/v1/admin/signup-requests/{request['id']}/approve", json={})).status_code == 200
        accepted = await client.post("/api/v1/auth/invitations/accept", json=account_body(token))
        assert accepted.status_code == 200, accepted.text
        uid, home = accepted.json()["user_id"], accepted.json()["identity_domain_id"]
        assert home != "domain" and directory.users[uid].domain_id == home
        assert project_service._direct_ids(directory.default_direct, uid) == {rid("project_reader")}
    async with enrollments() as session:
        await domain_iam.invite({"email": "foreign@test.invalid"}, manager(), session)
        existing_token = email_token(directory.sent[-1])
        existing = await domain_iam.redeem(
            existing_token, "invitation", session, token_info=manager("foreign", "other")
        )
        assert existing["user_id"] == "foreign" and existing["identity_domain_id"] == "other"
        assert len((await session.execute(select(SignupRequest))).scalars().all()) == 1
        with pytest.raises(HTTPException) as blocked:
            await domain_iam.create_user(
                {
                    "name": "manager-created",
                    "email": "unverified@test.invalid",
                    "password": PASSWORD,
                    "enabled": True,
                    "personal_domain_name": "Unverified",
                },
                manager(),
                session,
            )
        assert blocked.value.status_code == 403 and blocked.value.detail == "signup_requires_system_approval"
        assert len(directory.creates) == 1
