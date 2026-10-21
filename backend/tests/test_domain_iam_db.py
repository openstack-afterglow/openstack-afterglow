"""MariaDB transaction races: one email token causes at most one native mutation."""

import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.account_spaces import PersonalProjectIntent, SharedDomainIntent
from app.models.domain_iam import DomainEnrollment
from app.services import account_spaces, domain_iam, project_service
from tests import test_domain_iam as scenarios
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_iam import PASSWORD, email_token, manager
from tests.test_domain_iam import directory as directory
from tests.test_project_membership_roles import PROJECT, rid

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def enrollment_db(directory, monkeypatch):
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required for enrollment FOR UPDATE races")
    engine = create_async_engine(url)
    if engine.dialect.name not in {"mysql", "mariadb"}:
        await engine.dispose()
        pytest.skip("SQLite does not implement enrollment row locks")
    from app.models.domain_quotas import DomainQuotaPolicy
    from app.models.enrollment_policy import EnrollmentPolicy, SignupRequest
    from app.services import account_spaces

    async with engine.begin() as conn:
        for model in (
            DomainEnrollment,
            EnrollmentPolicy,
            SignupRequest,
            DomainQuotaPolicy,
            PersonalProjectIntent,
            SharedDomainIntent,
        ):
            await conn.run_sync(lambda sync, model=model: model.__table__.create(sync, checkfirst=True))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.services.enrollment_policy.get_session_factory", lambda: factory)
    monkeypatch.setattr(account_spaces, "get_session_factory", lambda: factory)
    ids = []
    async with factory() as session:
        existing_policies = set((await session.execute(select(DomainQuotaPolicy.domain_id))).scalars())
        existing_shared = set((await session.execute(select(SharedDomainIntent.marker))).scalars())
        existing_personal = set((await session.execute(select(PersonalProjectIntent.token_hash))).scalars())
    yield factory, ids
    async with factory() as session:
        if ids:
            homes = (
                set(
                    (
                        await session.execute(
                            select(DomainEnrollment.identity_domain_id).where(DomainEnrollment.id.in_(ids))
                        )
                    ).scalars()
                )
                - existing_policies
                - {None}
            )
            if homes:
                await session.execute(delete(DomainQuotaPolicy).where(DomainQuotaPolicy.domain_id.in_(homes)))
            await session.execute(delete(DomainEnrollment).where(DomainEnrollment.id.in_(ids)))
            await session.execute(delete(SharedDomainIntent).where(SharedDomainIntent.marker.not_in(existing_shared)))
            await session.execute(
                delete(PersonalProjectIntent).where(PersonalProjectIntent.token_hash.not_in(existing_personal))
            )
            await session.commit()
    await engine.dispose()


async def issue(directory, enrollment_db):
    factory, ids = enrollment_db
    email = f"race-{uuid4().hex}@test.invalid"
    async with factory() as session:
        row = await domain_iam.invite(
            {"email": email, "project_id": PROJECT, "role_ids": [rid("project_member")]}, manager(), session
        )
        ids.append(row["id"])
    return row["id"], email_token(directory.sent[-1])


async def test_competing_redemptions_create_exactly_one_account_and_grant(directory, enrollment_db, monkeypatch):
    factory, ids = enrollment_db
    row_id, token = await issue(directory, enrollment_db)
    entered = asyncio.Event()
    release = asyncio.Event()
    native_create = domain_iam.create_account

    async def gated_create(*args, **kwargs):
        entered.set()
        await release.wait()
        return await native_create(*args, **kwargs)

    monkeypatch.setattr(domain_iam, "create_account", gated_create)

    async def accept(name):
        async with factory() as session:
            return await domain_iam.redeem(token, "invitation", session, name=name, password=PASSWORD)

    first = asyncio.create_task(accept("first"))
    await entered.wait()
    second = asyncio.create_task(accept("second"))
    release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    rejected = next(result for result in results if isinstance(result, HTTPException))
    assert rejected.status_code == 410
    assert len(directory.creates) == 1
    async with factory() as session:
        persisted = await session.get(DomainEnrollment, row_id)
        assert persisted.status == "accepted" and persisted.user_id == directory.creates[0]
        uid, did, pid = persisted.user_id, persisted.identity_domain_id, persisted.personal_project_id
        assert set(directory.personal_domains) == {did, persisted.personal_domain_id}
        assert set(directory.personal_projects) == {pid}
        assert directory.users[uid].domain_id == did != persisted.domain_id
        assert directory.personal_projects[pid].domain_id == persisted.personal_domain_id != did
        assert directory.personal_projects[pid].enabled and directory.users[uid].enabled
        assert project_service._direct_ids(directory.ks.role_assignments.list(project=pid), uid) == {rid("member")}
        assert project_service._direct_ids(directory.ks.role_assignments.list(project="default-project"), uid) == {
            rid("project_reader")
        }
        assert project_service._direct_ids(directory.ks.role_assignments.list(project=PROJECT), uid) == {
            rid("project_member")
        }
        personal = account_spaces.personal_project(uid, ks=directory.ks)
        assert personal["id"] == pid and personal["domain_id"] == persisted.personal_domain_id
        assert all(grant["phase"] == "confirmed" for grant in persisted.added_grants)


async def test_revoke_cannot_race_through_locked_redemption(directory, enrollment_db, monkeypatch):
    factory, ids = enrollment_db
    row_id, token = await issue(directory, enrollment_db)
    entered = asyncio.Event()
    release = asyncio.Event()
    native_create = domain_iam.create_account

    async def gated_create(*args, **kwargs):
        entered.set()
        await release.wait()
        return await native_create(*args, **kwargs)

    monkeypatch.setattr(domain_iam, "create_account", gated_create)

    async def accept():
        async with factory() as session:
            return await domain_iam.redeem(token, "invitation", session, name="winner", password=PASSWORD)

    async def revoke():
        async with factory() as session:
            return await domain_iam.revoke(row_id, manager(), session)

    first = asyncio.create_task(accept())
    await entered.wait()
    second = asyncio.create_task(revoke())
    release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)
    assert isinstance(results[0], dict)
    assert isinstance(results[1], HTTPException) and results[1].status_code == 409
    async with factory() as session:
        row = (await session.execute(select(DomainEnrollment).where(DomainEnrollment.id == row_id))).scalar_one()
        assert row.status == "accepted"
    assert len(directory.creates) == 1


@pytest.mark.parametrize(
    "scenario",
    [
        "test_final_sql_failure_cannot_leave_active_account_with_pending_record",
        "test_interrupted_native_work_has_durable_plan_and_can_be_recovered",
        "test_revoke_never_succeeds_while_native_grants_survive_and_retry_recovers",
    ],
)
async def test_durable_native_disposition_on_mariadb(directory, enrollment_db, monkeypatch, scenario):
    """Reuse canonical recovery semantics with actual MariaDB commit/row-lock behavior."""
    factory, ids = enrollment_db
    canonical_invite = scenarios.invite

    async def tracked_invite(directory, factory, email=None):
        result, token = await canonical_invite(
            directory, factory, email=email or f"recovery-{uuid4().hex}@test.invalid"
        )
        ids.append(result["id"])
        return result, token

    monkeypatch.setattr(scenarios, "invite", tracked_invite)
    run = getattr(scenarios, scenario)
    if scenario == "test_interrupted_native_work_has_durable_plan_and_can_be_recovered":
        await run(directory, factory, monkeypatch)
    else:
        await run(directory, factory)


async def test_global_signup_links_serialize_email_ownership_without_target_grants(
    directory, enrollment_db, ownership_journal
):
    factory, ids = enrollment_db
    directory.settings.auth.public_signup_enabled = True
    email = f"signup-{uuid4().hex}@test.invalid"
    tokens = []
    async with factory() as session:
        for address in (email, email.upper()):
            await domain_iam.register(address, session)
            token = email_token(directory.sent[-1])
            tokens.append(token)
            row = await domain_iam.lookup_token(token, "registration", session)
            ids.append(row.id)
            assert row.domain_id is None

    async def accept(token):
        async with factory() as session:
            return await domain_iam.redeem(token, "registration", session, name="signup", password=PASSWORD)

    results = await asyncio.gather(*(accept(token) for token in tokens), return_exceptions=True)
    successes = [result for result in results if isinstance(result, dict)]
    assert len(successes) == 1
    assert any(isinstance(result, HTTPException) and result.status_code == 409 for result in results)
    uid, home = successes[0]["user_id"], successes[0]["identity_domain_id"]
    assert successes[0]["domain_id"] == successes[0]["personal_domain_id"] != home
    assert len(directory.creates) == 1 and len(directory.personal_domains) == 2
    assert directory.users[uid].afterglow_local_password is True
    assert not project_service._direct_ids(directory.default_direct, uid)
    assert not project_service._direct_ids(directory.direct, uid)
    async with factory() as session:
        rows = (await session.execute(select(DomainEnrollment).where(DomainEnrollment.id.in_(ids)))).scalars().all()
        accepted = next(row for row in rows if row.status == "accepted")
        pending = next(row for row in rows if row.status == "pending")
        assert accepted.domain_id is None and accepted.identity_domain_id == home
        assert all(grant["domain_id"] == accepted.personal_domain_id for grant in accepted.added_grants)
        assert pending.domain_id is None and pending.user_id is None
