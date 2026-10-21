"""Real isolated SQL for policy CAS, immutable admission and one-use review.

Synthetic lease/native/SMTP boundaries do not prove production Redis locking,
MariaDB row-lock behavior, native quota support or real mailbox delivery.
"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_os_conn, get_token_info, require_admin
from app.api.identity import enrollment_policy as api
from app.models.domain_iam import DomainEnrollment
from app.models.domain_quotas import DomainQuotaPolicy
from app.models.enrollment_policy import EnrollmentPolicy, EnrollmentPolicyUpdate, SignupRequest
from app.services import domain_iam, email_service
from app.services import enrollment_policy as service

ACTOR = {"user_id": "reviewer", "username": "Admin", "project_id": "project"}
IDENTITY = {
    "source": "oidc",
    "email": "owner@example.test",
    "issuer": "https://issuer.example.test",
    "subject": "immutable-subject",
    "domain_id": "organization",
    "provider_id": "provider",
}
SAFE_FIELDS = {
    "id",
    "source",
    "email",
    "domain_id",
    "provider_id",
    "status",
    "created_at",
    "reviewed_at",
    "reviewed_by_user_id",
}


@pytest_asyncio.fixture
async def policy_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'enrollment.sqlite'}")
    async with engine.begin() as connection:
        for model in (EnrollmentPolicy, SignupRequest, DomainQuotaPolicy, DomainEnrollment):
            await connection.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = SimpleNamespace(
        auth=SimpleNamespace(public_signup_enabled=True),
        service_manila_enabled=False,
        smtp_enabled=True,
        smtp_host="smtp.example.test",
        smtp_from_address="cloud@example.test",
        frontend_base_url="https://cloud.example.test",
        smtp_invitation_token_expiry_days=7,
    )
    monkeypatch.setattr(service, "get_session_factory", lambda: factory)
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(domain_iam, "get_settings", lambda: settings)
    monkeypatch.setattr(service.activity, "record", AsyncMock())
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(email_service, "send_email", send)
    lease = SimpleNamespace(assert_owned=AsyncMock())
    held = False

    @asynccontextmanager
    async def graph(_):
        nonlocal held
        assert not held, "nested identity graph lease"
        held = True
        try:
            yield lease
        finally:
            held = False

    monkeypatch.setattr(service.identity_roles, "_graph_lock", graph)
    state = SimpleNamespace(engine=engine, factory=factory, settings=settings, lease=lease, send=send)
    yield state
    await engine.dispose()


async def set_policy(revision=0, mode="admin", quotas=None, enabled=True):
    return await service.update_policy(
        None,
        {
            "revision": revision,
            "public_signup_enabled": enabled,
            "approval_mode": mode,
            "personal_quotas": {"instances": 0} if quotas is None else quotas,
        },
        token_info=ACTOR,
    )


async def pending(db, **identity):
    async with db.factory() as session:
        with pytest.raises(HTTPException) as error:
            await service.require_signup_approval(session, **(identity or IDENTITY))
        assert error.value.status_code == 403
        assert error.value.detail == "signup_approval_pending"
        await session.rollback()
    async with db.factory() as session:
        return (await session.execute(select(SignupRequest))).scalar_one().id


@pytest.mark.asyncio
async def test_absent_policy_preserves_config_auto_and_zero_core_defaults(policy_db):
    result = await service.read_policy()
    assert result["revision"] == 0
    assert result["public_signup_enabled"] is True
    assert result["approval_mode"] == "auto"
    assert result["defaults_future_only"] is True
    assert result["smtp_configured"] is True
    assert result["personal_quotas"] == {
        key: 0 for section in ("compute", "volume", "network") for key in service._CORE_FIELDS[section]
    }
    assert "key_pairs" not in result["personal_quotas"]
    assert "file_storage" not in result["quota_fields"]
    policy_db.settings.auth.public_signup_enabled = False
    policy_db.settings.service_manila_enabled = True
    result = await service.read_policy()
    assert result["public_signup_enabled"] is False
    assert result["personal_quotas"]["share_snapshots"] == 0
    assert "share_groups" not in result["personal_quotas"]


@pytest.mark.asyncio
async def test_storage_unavailable_never_falls_back_to_auto(policy_db, monkeypatch):
    monkeypatch.setattr(service, "get_session_factory", lambda: None)
    with pytest.raises(HTTPException) as error:
        await service.read_policy()
    assert error.value.status_code == 503
    async with policy_db.engine.begin() as connection:
        await connection.run_sync(EnrollmentPolicy.__table__.drop)
    async with policy_db.factory() as session:
        with pytest.raises(HTTPException) as error:
            await service.require_signup_approval(session, **IDENTITY)
    assert error.value.status_code == 503
    assert "sqlite" not in str(error.value.detail)


@pytest.mark.asyncio
async def test_persisted_policy_survives_config_change_and_cas_conflicts(policy_db):
    result = await set_policy(quotas={"instances": 0, "key_pairs": -1}, enabled=False)
    assert result["revision"] == 1
    policy_db.settings.auth.public_signup_enabled = True
    assert (await service.read_policy())["public_signup_enabled"] is False
    for stale in (0, 2):
        with pytest.raises(HTTPException) as error:
            await set_policy(stale, mode="auto", quotas={"instances": -1})
        assert error.value.status_code == 409
    result = await set_policy(1, mode="auto", quotas={})
    assert result["revision"] == 2 and result["personal_quotas"] == {}
    assert service.activity.record.await_count == 2


@pytest.mark.parametrize("quotas", [{"instances": True}, {"cores": 1.0}, {"ram": -2}, {"secret": 0}])
def test_policy_rejects_coercion_and_unknown_quota_fields(quotas):
    with pytest.raises(ValidationError):
        EnrollmentPolicyUpdate(
            revision=0,
            public_signup_enabled=True,
            approval_mode="admin",
            personal_quotas=quotas,
        )


@pytest.mark.asyncio
async def test_auto_creates_no_queue_and_none_consumption_is_noop(policy_db):
    async with policy_db.factory() as session:
        assert await service.require_signup_approval(session, **IDENTITY) is None
        await service.consume_approval(session, None, user_id="user")
        assert (await session.execute(select(SignupRequest))).scalars().all() == []


@pytest.mark.asyncio
async def test_pending_commit_survives_caller_rollback_and_deduplicates(policy_db):
    await set_policy()
    first = await pending(policy_db)
    assert await pending(policy_db) == first
    await set_policy(1, mode="auto")
    assert await pending(policy_db) == first
    assert policy_db.send.await_count == 0


@pytest.mark.asyncio
async def test_rejection_survives_auto_toggle_and_cannot_be_reapproved(policy_db):
    await set_policy()
    request_id = await pending(policy_db)
    rejected = await service.review_request(None, request_id, "rejected", token_info=ACTOR)
    assert set(rejected) == SAFE_FIELDS
    assert rejected["reviewed_by_user_id"] == "reviewer"
    assert await service.review_request(None, request_id, "rejected", token_info=ACTOR) == rejected
    await set_policy(1, mode="auto")
    async with policy_db.factory() as session:
        with pytest.raises(HTTPException) as error:
            await service.require_signup_approval(session, **IDENTITY)
        assert error.value.detail == "signup_approval_rejected"
    with pytest.raises(HTTPException) as error:
        await service.review_request(None, request_id, "approved", token_info=ACTOR)
    assert error.value.status_code == 409
    policy_db.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_native_gate_requires_review_and_consumption_blocks_every_replay(policy_db):
    await set_policy()
    native_create = AsyncMock(return_value="native-user")

    async def enroll():
        async with policy_db.factory() as session:
            request_id = await service.require_signup_approval(session, **IDENTITY)
            user_id = await native_create()
            await service.consume_approval(session, request_id, user_id=user_id)

    with pytest.raises(HTTPException):
        await enroll()
    native_create.assert_not_awaited()
    request_id = (await service.list_requests())["items"][0]["id"]
    approved = await service.review_request(None, request_id, "approved", token_info=ACTOR)
    assert approved["status"] == "approved"
    native_create.assert_not_awaited()  # review itself is SQL-only
    await enroll()
    native_create.assert_awaited_once()
    with pytest.raises(HTTPException) as error:
        await enroll()
    assert error.value.detail == "signup_approval_consumed"
    for user_id in ("native-user", "different-user"):
        async with policy_db.factory() as session:
            with pytest.raises(HTTPException):
                await service.consume_approval(session, request_id, user_id=user_id)
    for decision in ("approved", "rejected"):
        with pytest.raises(HTTPException):
            await service.review_request(None, request_id, decision, token_info=ACTOR)
    async with policy_db.factory() as session:
        row = await session.get(SignupRequest, request_id)
        assert row.status == "consumed" and row.consumed_by_user_id == "native-user"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"email": "other@example.test"},
        {"domain_id": "other-org"},
        {"provider_id": "other-provider"},
    ],
)
async def test_approval_cannot_be_retargeted(policy_db, change):
    await set_policy()
    request_id = await pending(policy_db)
    await service.review_request(None, request_id, "approved", token_info=ACTOR)
    async with policy_db.factory() as session:
        with pytest.raises(HTTPException) as error:
            await service.require_signup_approval(session, **(IDENTITY | change))
        assert error.value.detail == "signup_approval_identity_mismatch"
        assert (await session.get(SignupRequest, request_id)).status == "approved"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", [{"issuer": "https://other.test"}, {"subject": "other-subject"}, {"source": "github"}]
)
async def test_approval_not_inherited_by_another_stable_identity(policy_db, change):
    await set_policy()
    request_id = await pending(policy_db)
    await service.review_request(None, request_id, "approved", token_info=ACTOR)
    async with policy_db.factory() as session:
        with pytest.raises(HTTPException) as error:
            await service.require_signup_approval(session, **(IDENTITY | change))
        assert error.value.detail == "signup_approval_pending"
        rows = list((await session.execute(select(SignupRequest))).scalars())
        assert len(rows) == 2


@pytest.mark.asyncio
async def test_email_review_issues_real_registration_mail_without_stored_credentials(policy_db):
    await set_policy()
    request_id = await pending(policy_db, source="email", email="owner@example.test")
    approved = await service.review_request(None, request_id, "approved", token_info=ACTOR)
    assert approved["status"] == "approved"
    policy_db.send.assert_awaited_once()
    args = policy_db.send.await_args.args
    assert args[0] == "owner@example.test"
    assert "https://cloud.example.test/registrations/" in args[3]
    raw_token = args[3].rsplit("/", 1)[1]
    async with policy_db.factory() as session:
        enrollment = (await session.execute(select(DomainEnrollment))).scalar_one()
        assert enrollment.kind == "registration" and enrollment.domain_id is None
        assert enrollment.status == "pending" and raw_token != enrollment.token_hash
        assert raw_token not in repr(enrollment.__dict__)
        row = await session.get(SignupRequest, request_id)
        assert raw_token not in repr(row.__dict__)
        assert not {"issuer", "subject", "password", "token"} & set(SignupRequest.__table__.columns.keys())
    assert await service.review_request(None, request_id, "approved", token_info=ACTOR) == approved
    policy_db.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_email_notification_is_explicit_but_review_committed_and_not_replayed(policy_db):
    await set_policy()
    request_id = await pending(policy_db, source="email", email="owner@example.test")
    policy_db.send.return_value = False
    with pytest.raises(HTTPException) as error:
        await service.review_request(None, request_id, "approved", token_info=ACTOR)
    assert error.value.status_code == 503
    assert "approval remains approved" in error.value.detail
    result = await service.review_request(None, request_id, "approved", token_info=ACTOR)
    assert result["status"] == "approved"
    policy_db.send.assert_awaited_once()
    async with policy_db.factory() as session:
        assert (await session.execute(select(DomainEnrollment))).scalar_one().status == "delivery_failed"


@pytest.mark.asyncio
async def test_cancelled_review_settles_mail_before_unlock_and_never_replays(policy_db):
    await set_policy()
    request_id = await pending(policy_db, source="email", email="owner@example.test")
    entered, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def deliver(*args):
        entered.set()
        await release.wait()
        finished.set()
        return True

    policy_db.send.side_effect = deliver
    task = asyncio.create_task(service.review_request(None, request_id, "approved", token_info=ACTOR))
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()
    assert (await service.review_request(None, request_id, "approved", token_info=ACTOR))["status"] == "approved"
    policy_db.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_personal_quota_updates_native_projects_without_shared_budget(policy_db, monkeypatch):
    native, writes = {}, []

    def read(conn, pid, section):
        values = native.setdefault(pid, {"instances": 20, "cores": 40, "key_pairs": 10})
        return {key: {"limit": value, "in_use": 0} for key, value in values.items()}

    def update(conn, pid, section, values):
        writes.append((pid, section, dict(values)))
        native[pid].update(values)

    monkeypatch.setattr(service.quota_native, "get_section", read)
    monkeypatch.setattr(service.quota_native, "update_section", update)
    values = {"instances": 0, "cores": -1, "key_pairs": 3, "shares": 0}
    first = await service.apply_personal_project_quotas(None, "first", values, lease=policy_db.lease)
    second = await service.apply_personal_project_quotas(None, "second", {"instances": 5}, lease=policy_db.lease)
    assert first["omitted_fields"] == ["shares"] and second["limits"] == {"instances": 5}
    assert native["first"] == {"instances": 0, "cores": -1, "key_pairs": 3}
    assert native["second"]["instances"] == 5 and len(writes) == 2
    async with policy_db.factory() as session:
        assert not (await session.execute(select(DomainQuotaPolicy))).scalars().all()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing_field", "wrong_readback", "lost_lease"])
async def test_personal_quota_cannot_activate_unverified_limits(policy_db, monkeypatch, failure):
    writes = []

    def read(conn, pid, section):
        return {} if failure == "missing_field" else {"instances": {"limit": 99, "in_use": 0}}

    def update(conn, pid, section, values):
        writes.append(values)

    monkeypatch.setattr(service.quota_native, "get_section", read)
    monkeypatch.setattr(service.quota_native, "update_section", update)
    if failure == "lost_lease":
        policy_db.lease.assert_owned.side_effect = HTTPException(409, "lease lost")
    with pytest.raises(HTTPException):
        await service.apply_personal_project_quotas(None, "first", {"instances": 0}, lease=policy_db.lease)
    assert len(writes) == (1 if failure == "wrong_readback" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/enrollment-policy", None),
        (
            "PUT",
            "/enrollment-policy",
            {
                "revision": 0,
                "public_signup_enabled": True,
                "approval_mode": "auto",
                "personal_quotas": {},
            },
        ),
        ("GET", "/signup-requests", None),
        ("POST", "/signup-requests/00000000-0000-0000-0000-000000000000/approve", None),
        ("POST", "/signup-requests/00000000-0000-0000-0000-000000000000/reject", None),
    ],
)
async def test_admin_enrollment_routes_reject_nonadmin_and_revoked_authority(
    policy_db, monkeypatch, method, path, payload
):
    from app.services import domain_scope, keystone

    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/admin")
    app.dependency_overrides[get_os_conn] = lambda: None
    monkeypatch.setattr(domain_scope, "domain_context", lambda *args: {})
    monkeypatch.setattr(domain_scope, "assert_token_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(keystone, "validate_token", lambda *args, **kwargs: {"domain_id": "personal"})
    monkeypatch.setattr(keystone, "_is_system_admin", lambda *args: False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for cached_admin in (False, True):
            app.dependency_overrides[get_token_info] = lambda: {
                "user_id": "revoked",
                "domain_id": "personal",
                "identity_domain_id": "personal",
                "is_system_admin": cached_admin,
                "token": "synthetic-native-proof",
            }
            response = await client.request(method, "/api/v1/admin" + path, json=payload)
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == "system_admin_required"
    async with policy_db.factory() as session:
        assert await session.get(EnrollmentPolicy, 1) is None
        assert (await session.execute(select(SignupRequest))).scalars().all() == []


@pytest.mark.asyncio
async def test_api_requires_fresh_admin_and_secret_free_bounded_pagination(policy_db, monkeypatch):
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/admin")
    app.dependency_overrides[get_os_conn] = lambda: None
    app.dependency_overrides[get_token_info] = lambda: {"user_id": "ordinary", "is_system_admin": False}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/api/v1/admin/enrollment-policy")
        assert denied.status_code == 403
        assert denied.headers["cache-control"] == "no-store, private"
        app.dependency_overrides[get_token_info] = lambda: {
            "user_id": "stale-admin",
            "domain_id": "personal",
            "identity_domain_id": "personal",
            "is_system_admin": True,
            "token": "private-native-token",
        }
        from app.services import domain_scope, keystone

        monkeypatch.setattr(domain_scope, "domain_context", lambda *args: {})
        monkeypatch.setattr(domain_scope, "assert_token_context", lambda *args, **kwargs: None)
        monkeypatch.setattr(keystone, "validate_token", lambda *args, **kwargs: {"domain_id": "personal"})
        fresh = MagicMock(return_value=False)
        monkeypatch.setattr(keystone, "_is_system_admin", fresh)
        denied = await client.get("/api/v1/admin/signup-requests")
        assert denied.status_code == 403
        assert fresh.call_count == 1
        app.dependency_overrides[require_admin] = lambda: ACTOR
        async with policy_db.factory() as session:
            for index in range(55):
                session.add(
                    SignupRequest(
                        id=str(uuid4()),
                        source="oidc",
                        email=f"owner{index}@example.test",
                        identity_hash=f"identity-{index}",
                        binding_hash=f"private-binding-{index}",
                        status="pending",
                    )
                )
            await session.commit()
        first = await client.get("/api/v1/admin/signup-requests")
        assert first.status_code == 200
        body = first.json()
        assert len(body["items"]) == 50 and body["next_cursor"]
        assert all(set(row) == SAFE_FIELDS for row in body["items"])
        assert "private-binding" not in first.text and "identity_hash" not in first.text
        second = (await client.get("/api/v1/admin/signup-requests", params={"cursor": body["next_cursor"]})).json()
        assert len(second["items"]) == 5 and second["next_cursor"] is None
        assert not {row["id"] for row in body["items"]} & {row["id"] for row in second["items"]}
        request_id = body["items"][0]["id"]
        decision = await client.post(f"/api/v1/admin/signup-requests/{request_id}/approve")
        assert decision.status_code == 200 and decision.json()["status"] == "approved"
        conflict = await client.post(f"/api/v1/admin/signup-requests/{request_id}/reject")
        assert conflict.status_code == 409
        assert (await client.get("/api/v1/admin/signup-requests?status=consumed")).status_code == 422
        invalid = await client.get("/api/v1/admin/signup-requests?cursor=private-secret")
        assert invalid.status_code == 422 and "private-secret" not in invalid.text
        invalid = await client.put("/api/v1/admin/enrollment-policy", json={"password": "private-secret"})
        assert invalid.status_code == 422 and "private-secret" not in invalid.text
        saved = await client.put(
            "/api/v1/admin/enrollment-policy",
            json={
                "revision": 0,
                "public_signup_enabled": False,
                "approval_mode": "admin",
                "personal_quotas": {},
            },
        )
        assert saved.status_code == 200 and saved.json()["revision"] == 1


@pytest.mark.asyncio
async def test_pending_or_rejected_request_cannot_be_consumed(policy_db):
    await set_policy()
    request_id = await pending(policy_db)
    async with policy_db.factory() as session:
        with pytest.raises(HTTPException) as error:
            await service.consume_approval(session, request_id, user_id="native-user")
        assert error.value.detail == "signup_approval_not_usable"
    await service.review_request(None, request_id, "rejected", token_info=ACTOR)
    async with policy_db.factory() as session:
        with pytest.raises(HTTPException):
            await service.consume_approval(session, request_id, user_id="native-user")
    assert (await service.list_requests(status="rejected"))["items"][0]["status"] == "rejected"


@pytest.mark.asyncio
async def test_enrollment_quota_snapshot_is_durable_and_not_rewritten_by_policy(policy_db, monkeypatch):
    await set_policy(quotas={"instances": 0, "cores": 0})
    async with policy_db.factory() as session:
        snapshot = (await service.read_policy(session=session))["personal_quotas"]
        row = DomainEnrollment(
            kind="external",
            domain_id="organization",
            email="owner@example.test",
            token_hash="digest",
            expires_at=service.datetime.now(service.UTC),
            personal_quotas=snapshot,
        )
        session.add(row)
        await session.commit()
        enrollment_id = row.id
    await set_policy(1, quotas={"instances": 7})
    async with policy_db.factory() as session:
        row = await session.get(DomainEnrollment, enrollment_id)
        assert row.personal_quotas == {"instances": 0, "cores": 0}
        native = {"instances": 99, "cores": 99}

        def read(conn, pid, section):
            return {key: {"limit": value, "in_use": 0} for key, value in native.items()}

        def update(conn, pid, section, values):
            native.update(values)

        monkeypatch.setattr(service.quota_native, "get_section", read)
        monkeypatch.setattr(service.quota_native, "update_section", update)
        seeded = await service.apply_personal_project_quotas(
            None, "project", row.personal_quotas, lease=policy_db.lease
        )
        assert seeded["limits"] == native == row.personal_quotas


@pytest.mark.asyncio
async def test_email_case_and_idna_variants_share_rejection_even_in_auto_mode(policy_db):
    await set_policy()
    request_id = await pending(policy_db, source="email", email="Owner@BÜCHER.example")
    assert await pending(policy_db, source="email", email="OWNER@xn--bcher-kva.example") == request_id
    rejected = await service.review_request(None, request_id, "rejected", token_info=ACTOR)
    assert rejected["email"] == "owner@xn--bcher-kva.example"
    await set_policy(1, mode="auto")
    async with policy_db.factory() as session:
        with pytest.raises(HTTPException) as error:
            await service.require_signup_approval(session, source="email", email="oWnEr@bücher.EXAMPLE")
        assert error.value.detail == "signup_approval_rejected"
        assert len((await session.execute(select(SignupRequest))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_external_email_case_and_idna_variants_preserve_exact_approval_binding(policy_db):
    await set_policy()
    request_id = await pending(policy_db, **(IDENTITY | {"email": "Owner@BÜCHER.example"}))
    await service.review_request(None, request_id, "approved", token_info=ACTOR)
    async with policy_db.factory() as session:
        approved = await service.require_signup_approval(
            session, **(IDENTITY | {"email": "OWNER@xn--bcher-kva.example"})
        )
        assert approved == request_id


@pytest.mark.asyncio
async def test_email_approval_with_public_signup_disabled_notifies_invitation_completion(policy_db):
    await set_policy(enabled=False)
    request_id = await pending(policy_db, source="email", email="owner@example.test")
    result = await service.review_request(None, request_id, "approved", token_info=ACTOR)
    assert result["status"] == "approved"
    policy_db.send.assert_awaited_once()
    args = policy_db.send.await_args.args
    assert args[0] == "owner@example.test"
    assert "original verified invitation" in args[2] and "contact your inviter" in args[3]
    assert "/registrations/" not in args[2] + args[3]
    async with policy_db.factory() as session:
        assert (await session.execute(select(DomainEnrollment))).scalars().all() == []
        approved = await service.require_signup_approval(session, source="email", email="owner@example.test")
        assert approved == request_id
        await service.consume_approval(session, request_id, user_id="invited-user")
    policy_db.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_invitation_approval_notification_failure_stays_approved_without_resend(policy_db):
    await set_policy(enabled=False)
    request_id = await pending(policy_db, source="email", email="owner@example.test")
    policy_db.send.return_value = False
    with pytest.raises(HTTPException) as error:
        await service.review_request(None, request_id, "approved", token_info=ACTOR)
    assert error.value.status_code == 503
    assert "approval remains approved" in error.value.detail
    result = await service.review_request(None, request_id, "approved", token_info=ACTOR)
    assert result["status"] == "approved"
    policy_db.send.assert_awaited_once()
    async with policy_db.factory() as session:
        assert (await session.execute(select(DomainEnrollment))).scalars().all() == []
