"""HTTP/SQL proof and one-dispatch tests; native, email and Redis are fixtures.

The graph lease is serialized in-process. These are not native Galera or
production deployment qualification and do not replace those acceptance gates.
"""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Integer, MetaData, select

from app.api.deps import get_token_info, require_admin
from app.api.identity import account_recovery as recovery_routes
from app.api.identity import auth, profile_password
from app.database import get_session
from app.models.account_recovery import AccountRecovery
from app.models.activity import ActivityLog
from app.services import account_recovery as recovery
from app.services import domain_iam, identity_roles, keystone, session_store
from tests.test_account_recovery import CLOCK, REPLACEMENT, persisted, seed_sessions, token_from
from tests.test_account_recovery import directory as directory
from tests.test_account_recovery import recoveries as recoveries

pytestmark = pytest.mark.asyncio
BASE = "/api/v1/profile/password"
COMPLETE = "/api/v1/auth/recovery/password/create/complete"
ADMIN = "/api/v1/admin/identity/password-creations/external"


@pytest.fixture
def creation(directory, monkeypatch):
    state = directory
    state.clock = CLOCK
    state.actor = {
        "user_id": "external",
        "identity_domain_id": "home",
        "domain_id": "home",
        "auth_method": "federated",
        "session_token": "native-current-session",
        "provider_id": "provider",
        "provider_revision": 1,
        "provider_domain_id": "home",
        "login_email": "external@test.invalid",
        "refresh_jti": "current-session-jti",
    }
    state.current_session = {
        **state.actor,
        "keystone_token": state.actor["session_token"],
        "exp": CLOCK.timestamp() + 3600,
        "started_at": CLOCK.timestamp(),
    }
    state.admin = {
        "user_id": "operator",
        "identity_domain_id": "home",
        "domain_id": "home",
        "project_id": "project",
        "username": "operator",
        "_live_system_admin": True,
    }
    state.support = True
    state.post_status = 204
    state.identity_revision = "5"
    state.password_states = {uid: "existing" for uid in state.users}
    state.password_states["external"] = "absent"
    state.post_reason = "password_exists"
    state.before_post = None
    state.posts = []
    state.gets = []
    state.session_identity = {"user_id": "external", "identity_domain_id": "home"}
    state.provider_enabled = True
    state.password_enabled = True
    state.provider_checks = []
    state.ks.session = SimpleNamespace(get_token=lambda: "service-native-token")
    state.settings.os_auth_url = "https://keystone.test.invalid/v3"
    state.settings.ssl_verify = True
    state.settings.session_timeout_seconds = 3600

    def native(credential, method, path, *, body=None):
        assert credential == "service-native-token"
        if method == "GET":
            state.gets.append(path)
            if path.endswith("/capabilities"):
                return (200, {"supported": state.support, "revision": recovery._INITIAL_PASSWORD_REVISION})
            user = state.users[path.split("/")[1]]
            return 200, {
                "user": {
                    "id": user.id,
                    "domain_id": user.domain_id,
                    "email": user.email,
                    "identity_revision": state.identity_revision,
                    "password_state": state.password_states[user.id],
                }
            }
        state.posts.append((path, body))
        if state.before_post is not None:
            state.before_post()
        if (
            body["user"]["identity_revision"] != state.identity_revision
            or body["user"]["email"] != state.users["external"].email
        ):
            return 412, None
        if state.post_status is None:
            raise TimeoutError("Transport must never expose the submitted password")
        if state.post_status == 204:
            state.users["external"].afterglow_local_password = True
            state.password_states["external"] = "existing"
        return state.post_status, {"error": {"reason": state.post_reason}} if state.post_status == 409 else None

    async def provider(session, identity):
        state.provider_checks.append((dict(session), dict(identity)))
        if not state.provider_enabled:
            raise HTTPException(403, "provider disabled")

    async def policy(home, email, **kwargs):
        if not state.password_enabled:
            raise HTTPException(403, "Password authentication is disabled")
        return email

    async def current_session(jti):
        assert jti == "current-session-jti"
        return state.current_session

    monkeypatch.setattr(recovery, "_initial_request", native)
    state.ks.tokens = SimpleNamespace(
        validate=lambda token, include_catalog=False: SimpleNamespace(
            auth_token=token,
            user_id=state.session_identity["user_id"],
            user_domain_id=state.session_identity["identity_domain_id"],
        )
    )
    monkeypatch.setattr(auth, "_enforce_session_policy", provider)
    monkeypatch.setattr(domain_iam, "password_policy", policy)
    monkeypatch.setattr(session_store, "get_session", current_session)
    monkeypatch.setattr(keystone, "get_admin_project_connection", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(identity_roles, "load_catalog", lambda conn: state.catalog)
    monkeypatch.setattr(recovery, "_now", lambda: state.clock)
    return state


@pytest_asyncio.fixture
async def creation_client(creation, recoveries):
    app = FastAPI()
    app.include_router(profile_password.router, prefix="/api/v1/profile")
    app.include_router(profile_password.admin_router, prefix="/api/v1/admin/identity")
    app.include_router(recovery_routes.router, prefix="/api/v1/auth")

    async def db():
        async with recoveries() as session:
            yield session

    async def actor():
        if creation.actor is None:
            raise HTTPException(401, "login required")
        return dict(creation.actor)

    async def admin():
        if creation.admin is None:
            raise HTTPException(403, "system admin required")
        return dict(creation.admin)

    app.dependency_overrides[get_session] = db
    app.dependency_overrides[get_token_info] = actor
    app.dependency_overrides[require_admin] = admin
    enabled = recovery_routes.limiter.enabled
    recovery_routes.limiter.enabled = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    recovery_routes.limiter.enabled = enabled


async def issue(client, creation):
    creation.redis.addresses.clear()
    response = await client.post(BASE + "/create/request", json={})
    assert response.status_code == 202, response.text
    assert response.json() == {"accepted": True}
    # Simulate the required new provider-login roundtrip after mail issuance.
    creation.clock += timedelta(seconds=1)
    creation.current_session["started_at"] = creation.clock.timestamp()
    return token_from(creation.sent[-1])


async def complete(client, token, password=REPLACEMENT):
    return await client.post(COMPLETE, json={"token": token, "new_password": password})


async def test_delivered_proof_and_current_same_actor_create_exactly_once(creation, creation_client, recoveries):
    assert (await creation_client.get(BASE + "/capability")).json() == {"mode": "create"}
    token = await issue(creation_client, creation)
    row = await persisted(recoveries, token)
    assert row.kind == "password_create" and row.status == "pending"
    assert row.original_email == creation.users["external"].email
    inspected = await creation_client.get("/api/v1/auth/recovery/" + token)
    assert inspected.status_code == 200
    assert inspected.json()["kind"] == "password_create"
    assert inspected.json()["identity_domain_id"] == "home"
    seed_sessions(creation, "external")
    result = await complete(creation_client, token)
    assert result.status_code == 200 and result.json() == {"status": "created"}
    assert result.headers["cache-control"] == "no-store, private"
    assert result.headers["referrer-policy"] == "no-referrer"
    assert creation.posts == [
        (
            "users/external/OS-AFTERGLOW/initial-password",
            {
                "user": {
                    "password": REPLACEMENT,
                    "domain_id": "home",
                    "email": "external@test.invalid",
                    "identity_revision": "5",
                }
            },
        )
    ]
    assert creation.revoked == ["native-one", "native-two"]
    assert (await persisted(recoveries, token)).status == "created"
    assert (await complete(creation_client, token)).status_code == 410
    assert len(creation.posts) == 1
    assert len(creation.provider_checks) >= 3
    assert (await creation_client.get(BASE + "/capability")).json() == {"mode": "change"}


@pytest.mark.parametrize(
    "failure", ["support", "password_policy", "provider", "service", "disabled", "duplicate", "password_session"]
)
async def test_ineligible_creation_never_emails_or_dispatches(creation, creation_client, failure):
    if failure == "support":
        creation.support = False
    elif failure == "password_policy":
        creation.password_enabled = False
    elif failure == "provider":
        creation.provider_enabled = False
    elif failure == "service":
        creation.users["external"].name = "operator"
    elif failure == "disabled":
        creation.users["external"].enabled = False
    elif failure == "duplicate":
        creation.users["local"].email = creation.users["external"].email
    else:
        creation.actor["auth_method"] = "password"
    expected = "change" if failure == "password_session" else "unavailable"
    if failure == "support":
        expected = "change"
    capability = (await creation_client.get(BASE + "/capability")).json()
    assert capability["mode"] == expected
    result = await creation_client.post(BASE + "/create/request", json={})
    assert result.status_code in {403, 409, 503}
    assert not creation.sent and not creation.posts


@pytest.mark.parametrize(
    "change", ["user", "home", "native_user", "native_home", "email", "provider", "policy", "unauthenticated"]
)
async def test_completion_revalidates_session_home_email_and_policy(creation, creation_client, recoveries, change):
    token = await issue(creation_client, creation)
    if change == "user":
        creation.actor["user_id"] = "local"
    elif change == "home":
        creation.actor["identity_domain_id"] = "other"
    elif change == "native_user":
        creation.session_identity["user_id"] = "local"
    elif change == "native_home":
        creation.session_identity["identity_domain_id"] = "other"
    elif change == "email":
        creation.users["external"].email = "changed@test.invalid"
    elif change == "provider":
        creation.provider_enabled = False
    elif change == "policy":
        creation.password_enabled = False
    else:
        creation.actor = None
    result = await complete(creation_client, token)
    assert result.status_code in {401, 403, 410}
    assert not creation.posts
    assert (await persisted(recoveries, token)).status == "pending"


async def test_expired_and_superseded_proofs_cannot_dispatch(creation, creation_client, recoveries):
    old = await issue(creation_client, creation)
    token = await issue(creation_client, creation)
    assert (await complete(creation_client, old)).status_code == 410
    async with recoveries() as session:
        row = await session.get(AccountRecovery, recovery._digest(token))
        row.expires_at = CLOCK - timedelta(seconds=1)
        await session.commit()
    assert (await complete(creation_client, token)).status_code == 410
    assert not creation.posts


async def test_undelivered_email_is_not_a_usable_proof(creation, creation_client, recoveries):
    creation.deliver = False
    result = await creation_client.post(BASE + "/create/request", json={})
    assert result.status_code == 503
    token = token_from(creation.sent[-1])
    assert (await persisted(recoveries, token)).status == "delivery_failed"
    assert (await complete(creation_client, token)).status_code == 410
    assert not creation.posts


async def test_existing_password_conflict_is_never_success(creation, creation_client, recoveries):
    token = await issue(creation_client, creation)
    creation.post_status = 409
    result = await complete(creation_client, token)
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "password_already_exists"
    assert (await persisted(recoveries, token)).status == "existing"
    assert (await complete(creation_client, token)).status_code == 410
    assert len(creation.posts) == 1 and not creation.revoked


@pytest.mark.parametrize("native_status", [None, 400, 401, 403, 500, 503, 307])
async def test_uncertain_outcomes_revoke_and_block_reissue(creation, creation_client, recoveries, native_status):
    token = await issue(creation_client, creation)
    seed_sessions(creation, "external")
    creation.post_status = native_status
    result = await complete(creation_client, token)
    assert result.status_code == 502
    assert result.json()["detail"]["code"] == "password_create_outcome_unknown"
    assert (await persisted(recoveries, token)).status == "outcome_unknown"
    assert creation.revoked == ["native-one", "native-two"]
    assert (await creation_client.get(BASE + "/capability")).json() == {"mode": "unavailable"}
    creation.redis.addresses.clear()
    retry = await creation_client.post(BASE + "/create/request", json={})
    assert retry.status_code == 409
    assert retry.json()["detail"]["code"] == "password_create_reconciliation_required"
    assert len(creation.posts) == 1 and len(creation.sent) == 1


async def test_crashed_dispatch_fence_prevents_new_request(creation, creation_client, recoveries):
    token = await issue(creation_client, creation)
    async with recoveries() as session:
        row = await session.get(AccountRecovery, recovery._digest(token))
        row.status = "dispatching"
        row.consumed_at = CLOCK
        await session.commit()
    creation.redis.addresses.clear()
    assert (await creation_client.post(BASE + "/create/request", json={})).status_code == 409
    assert (await complete(creation_client, token)).status_code == 410
    assert not creation.posts


async def test_concurrent_completions_have_single_dispatch(creation, creation_client):
    token = await issue(creation_client, creation)
    results = await asyncio.gather(complete(creation_client, token), complete(creation_client, token))
    assert sorted(result.status_code for result in results) == [200, 410]
    assert len(creation.posts) == 1


async def test_native_dispatch_sees_committed_consumption(creation, creation_client, recoveries, monkeypatch):
    token = await issue(creation_client, creation)
    original = recovery._initial_request
    from sqlalchemy import create_engine

    url = str(recoveries.kw["bind"].url).replace("sqlite+aiosqlite", "sqlite")
    engine = create_engine(url)

    def observed(credential, method, path, *, body=None):
        if method == "POST":
            with engine.connect() as connection:
                status = connection.execute(
                    select(AccountRecovery.status).where(AccountRecovery.token_hash == recovery._digest(token))
                ).scalar_one()
                assert status == "dispatching"
        return original(credential, method, path, body=body)

    monkeypatch.setattr(recovery, "_initial_request", observed)
    try:
        assert (await complete(creation_client, token)).status_code == 200
    finally:
        engine.dispose()


async def test_session_failure_retains_operator_reconciliation_fence(creation, creation_client, recoveries):
    token = await issue(creation_client, creation)
    seed_sessions(creation, "external")
    creation.redis.fail_revoke = True
    result = await complete(creation_client, token)
    assert result.status_code == 503
    assert result.json()["detail"]["code"] == "password_create_sessions_failed"
    assert (await persisted(recoveries, token)).status == "sessions_failed"
    assert (await creation_client.get(BASE + "/capability")).json() == {"mode": "change"}


@pytest.mark.parametrize(
    "body",
    [
        {"token": "x" * 32, "new_password": "too-short"},
        {"token": "x" * 32, "new_password": "x" * 1025},
        {"token": "x" * 32, "new_password": REPLACEMENT, "user_id": "victim"},
    ],
)
async def test_invalid_requests_do_not_echo_secret_or_dispatch(creation, creation_client, body):
    response = await creation_client.post(COMPLETE, json=body)
    assert response.status_code == 422
    assert body["new_password"] not in response.text
    assert not creation.posts


async def test_operator_settlement_is_authorized_audited_and_never_replays_old_proof(
    creation, creation_client, recoveries
):
    token = await issue(creation_client, creation)
    creation.post_status = None
    assert (await complete(creation_client, token)).status_code == 502
    operation_id = recovery._digest(token)
    body = {
        "identity_domain_id": "home",
        "operation_id": operation_id,
        "resolution": "retry",
        "evidence": "Operator drained all native writers and reconciled request audit ref-123",
        "native_calls_settled": True,
    }
    creation.admin = None
    assert (await creation_client.post(ADMIN + "/settle", json=body)).status_code == 403
    creation.admin = {"user_id": "operator", "username": "operator", "_live_system_admin": True}
    listed = await creation_client.get(ADMIN, params={"identity_domain_id": "home"})
    assert listed.json()["operations"][0]["operation_id"] == operation_id
    for value in [False, "true", 1]:
        assert (
            await creation_client.post(ADMIN + "/settle", json={**body, "native_calls_settled": value})
        ).status_code == 422
    async with recoveries.kw["bind"].begin() as connection:
        audit = ActivityLog.__table__.to_metadata(MetaData())
        audit.c.id.type = Integer()
        await connection.run_sync(lambda sync: audit.create(sync))
    response = await creation_client.post(ADMIN + "/settle", json=body)
    assert response.status_code == 200
    assert response.json() == {"status": "settled", "resolution": "retry"}
    async with recoveries() as session:
        audit_row = (await session.execute(select(ActivityLog))).scalar_one()
        assert audit_row.user_id == "operator"
        assert audit_row.extra["native_calls_settled"] is True
        assert audit_row.extra["operation_id"] == operation_id
    assert (await persisted(recoveries, token)).status == "settled_retry"
    assert (await complete(creation_client, token)).status_code == 410
    creation.post_status = 204
    new_token = await issue(creation_client, creation)
    assert new_token != token
    assert (await complete(creation_client, new_token)).status_code == 200
    assert len(creation.posts) == 2


async def test_global_email_duplicate_after_issuance_blocks_completion(creation, creation_client):
    token = await issue(creation_client, creation)
    creation.users["local"].email = creation.users["external"].email
    response = await complete(creation_client, token)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "password_create_email_ambiguous"
    assert not creation.posts


async def test_native_marker_changes_do_not_turn_creation_into_update(creation, creation_client):
    token = await issue(creation_client, creation)
    creation.users["external"].afterglow_local_password = True
    creation.post_status = 409
    response = await complete(creation_client, token)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "password_already_exists"
    assert creation.updates == []


async def test_service_role_actor_cannot_create_password(creation, creation_client):
    creation.ks.role_assignments.list = lambda **kwargs: [
        {"user": {"id": "external"}, "role": {"id": "service"}, "scope": {"system": {"all": True}}}
    ]
    response = await creation_client.post(BASE + "/create/request", json={})
    assert response.status_code == 403
    assert not creation.sent and not creation.posts


async def test_final_sql_failure_keeps_committed_fence(creation, creation_client, recoveries, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    token = await issue(creation_client, creation)
    original = AsyncSession.commit

    async def commit(session):
        if any(isinstance(row, AccountRecovery) and row.status == "created" for row in session.dirty):
            raise ConnectionError("SQL final commit unavailable")
        await original(session)

    monkeypatch.setattr(AsyncSession, "commit", commit)
    response = await complete(creation_client, token)
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "password_create_outcome_unknown"
    assert (await persisted(recoveries, token)).status == "dispatching"
    assert (await complete(creation_client, token)).status_code == 410
    assert len(creation.posts) == 1


async def test_no_plaintext_password_or_email_proof_in_journal(creation, creation_client, recoveries):
    token = await issue(creation_client, creation)
    assert (await complete(creation_client, token)).status_code == 200
    row = await persisted(recoveries, token)
    stored = repr({column.name: getattr(row, column.name) for column in AccountRecovery.__table__.columns})
    assert token not in stored
    assert REPLACEMENT not in stored


async def test_capability_provider_and_native_failures_are_unavailable(creation, creation_client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise ConnectionError("native credential service unavailable")

    monkeypatch.setattr(creation.ks.tokens, "validate", unavailable)
    assert (await creation_client.get(BASE + "/capability")).json() == {"mode": "unavailable"}
    response = await creation_client.post(BASE + "/create/request", json={})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "password_create_session_unavailable"
    assert not creation.sent and not creation.posts


async def test_redis_failure_cannot_issue_email_or_dispatch(creation, creation_client, monkeypatch):
    async def unavailable():
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr(session_store, "_get_redis", unavailable)
    assert (await creation_client.get(BASE + "/capability")).json() == {"mode": "unavailable"}
    assert (await creation_client.post(BASE + "/create/request", json={})).status_code == 503
    assert not creation.sent and not creation.posts


async def test_cancelled_completion_finishes_dispatch_before_unlock(creation, recoveries, monkeypatch):
    async with recoveries() as session:
        await recovery.request_password_creation(creation.actor, session)
    token = token_from(creation.sent[-1])
    creation.clock += timedelta(seconds=1)
    creation.current_session["started_at"] = creation.clock.timestamp()
    original = recovery._initial_request

    def blocked(credential, method, path, *, body=None):
        if method == "POST":
            creation.entered.set()
            assert creation.release.wait(5), "test did not release native dispatch"
        return original(credential, method, path, body=body)

    monkeypatch.setattr(recovery, "_initial_request", blocked)
    seed_sessions(creation, "external")
    async with recoveries() as session:
        task = asyncio.create_task(recovery.complete_password_creation(token, REPLACEMENT, creation.actor, session))
        assert await asyncio.to_thread(creation.entered.wait, 5)
        task.cancel()
        assert creation.lock.locked()
        creation.release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not creation.lock.locked()
    assert len(creation.posts) == 1
    assert creation.revoked == ["native-one", "native-two"]
    assert (await persisted(recoveries, token)).status == "created"


@pytest.mark.parametrize(
    "payload",
    [
        {"supported": True, "revision": "old-unsafe-version"},
        {"supported": 1, "revision": recovery._INITIAL_PASSWORD_REVISION},
        {"revision": recovery._INITIAL_PASSWORD_REVISION},
        None,
    ],
)
async def test_native_capability_requires_exact_supported_revision(creation, creation_client, monkeypatch, payload):
    monkeypatch.setattr(recovery, "_initial_request", lambda *args, **kwargs: (200, payload))
    response = await creation_client.post(BASE + "/create/request", json={})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "password_create_native_unavailable"
    assert not creation.sent and not creation.posts


async def test_settlement_cannot_release_fence_without_durable_audit(creation, creation_client, recoveries):
    token = await issue(creation_client, creation)
    creation.post_status = None
    assert (await complete(creation_client, token)).status_code == 502
    # No activity_logs table: audit and settlement share one strict transaction.
    response = await creation_client.post(
        ADMIN + "/settle",
        json={
            "identity_domain_id": "home",
            "operation_id": recovery._digest(token),
            "resolution": "retry",
            "evidence": "Operator reconciled all native call termination under incident-123",
            "native_calls_settled": True,
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "password_create_settlement_unavailable"
    assert (await persisted(recoveries, token)).status == "outcome_unknown"


@pytest.mark.parametrize("state", ["deleted", "blacklisted", "other_user", "other_home", "changed_provider"])
async def test_current_session_is_rechecked_inside_graph_lease(creation, creation_client, state):
    token = await issue(creation_client, creation)
    if state == "deleted":
        creation.current_session = None
    elif state == "blacklisted":
        creation.current_session["blacklisted"] = True
    elif state == "other_user":
        creation.current_session["user_id"] = "local"
    elif state == "other_home":
        creation.current_session["identity_domain_id"] = "other"
    else:
        creation.current_session["provider_revision"] = 2
    response = await complete(creation_client, token)
    assert response.status_code in {401, 403}
    assert not creation.posts


@pytest.mark.parametrize("deadline", ["exp", "absolute", "missing_exp", "missing_started"])
async def test_current_session_deadlines_fail_closed(creation, creation_client, deadline):
    token = await issue(creation_client, creation)
    if deadline == "exp":
        creation.current_session["exp"] = CLOCK.timestamp()
    elif deadline == "absolute":
        creation.current_session["started_at"] = CLOCK.timestamp() - creation.settings.session_timeout_seconds
    elif deadline == "missing_exp":
        del creation.current_session["exp"]
    else:
        del creation.current_session["started_at"]
    expected = 401 if deadline == "exp" else 403
    assert (await complete(creation_client, token)).status_code == expected
    assert not creation.posts


async def seed_pending_proof(factory, token, kind):
    async with factory() as session:
        session.add(
            AccountRecovery(
                token_hash=recovery._digest(token),
                kind=kind,
                user_id="external",
                identity_domain_id="home",
                original_email="external@test.invalid",
                email="external@test.invalid",
                status="pending",
                native_identity_revision="5" if kind == "password" else None,
                created_at=CLOCK,
                expires_at=CLOCK + timedelta(hours=1),
            )
        )
        await session.commit()


async def test_creation_supersedes_other_pending_credential_proofs(creation, creation_client, recoveries):
    token = await issue(creation_client, creation)
    await seed_pending_proof(recoveries, "p" * 32, "password")
    await seed_pending_proof(recoveries, "e" * 32, "email_change")
    assert (await complete(creation_client, token)).status_code == 200
    assert (await persisted(recoveries, "p" * 32)).status == "superseded"
    assert (await persisted(recoveries, "e" * 32)).status == "superseded"


@pytest.mark.parametrize("kind", ["password", "email_change"])
async def test_other_credential_completion_supersedes_pending_creation(creation, creation_client, recoveries, kind):
    token = await issue(creation_client, creation)
    creation.users["external"].afterglow_local_password = True
    creation.password_states["external"] = "existing"
    other = "r" * 32
    await seed_pending_proof(recoveries, other, kind)
    async with recoveries() as session:
        result = await recovery.complete(other, session, new_password=REPLACEMENT, kind=kind)
    assert result == {"status": "changed"}
    assert (await persisted(recoveries, token)).status == "superseded"
    assert len(creation.posts) == (1 if kind == "password" else 0)


async def test_capability_never_takes_graph_or_sql_row_lock(creation, creation_client, monkeypatch):
    def prohibited():
        raise AssertionError("display-only capability must not acquire graph mutation lease")

    original = recovery._creation_unsettled

    async def unlocked(user_id, session, *, lock=True):
        assert lock is False
        return await original(user_id, session, lock=lock)

    monkeypatch.setattr(domain_iam, "_iam_write", prohibited)
    monkeypatch.setattr(recovery, "_creation_unsettled", unlocked)
    assert (await creation_client.get(BASE + "/capability")).json() == {"mode": "create"}


@pytest.mark.parametrize("session_start", ["before_issue", "at_issue", "older_than_15min", "future", "nan", "inf"])
async def test_completion_requires_recent_session_strictly_after_email_issuance(
    creation, creation_client, recoveries, session_start
):
    token = await issue(creation_client, creation)
    row = await persisted(recoveries, token)
    issued = row.created_at.replace(tzinfo=CLOCK.tzinfo).timestamp()
    if session_start == "before_issue":
        creation.current_session["started_at"] = issued - 1
    elif session_start == "at_issue":
        creation.current_session["started_at"] = issued
    elif session_start == "older_than_15min":
        creation.current_session["started_at"] = issued + 0.000001
        creation.clock = row.created_at.replace(tzinfo=CLOCK.tzinfo) + timedelta(seconds=901)
    elif session_start == "future":
        creation.current_session["started_at"] = creation.clock.timestamp() + 1
    else:
        creation.current_session["started_at"] = float(session_start)
    response = await complete(creation_client, token)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "password_create_reauthentication_required"
    assert not creation.posts
    assert (await persisted(recoveries, token)).status == "pending"
    # Failure leaves the delivered proof usable after an actual fresh roundtrip.
    creation.current_session["started_at"] = creation.clock.timestamp()
    assert (await complete(creation_client, token)).status_code == 200


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
async def test_nonfinite_session_expiry_fails_closed(creation, creation_client, recoveries, invalid):
    token = await issue(creation_client, creation)
    creation.current_session["exp"] = invalid
    response = await complete(creation_client, token)
    assert response.status_code == 401
    assert not creation.posts
    assert (await persisted(recoveries, token)).status == "pending"


@pytest.mark.parametrize("change", ["email_aba", "recreated_user", "legacy_missing_revision"])
async def test_revision_bound_proof_rejects_replaced_native_identity(creation, creation_client, recoveries, change):
    token = await issue(creation_client, creation)
    if change == "legacy_missing_revision":
        async with recoveries() as session:
            row = await session.get(AccountRecovery, recovery._digest(token))
            row.native_identity_revision = None
            await session.commit()
    else:
        # Same UUID/home/email shape after native mutation is not the same
        # permanent native identity revision, including email A -> B -> A.
        creation.identity_revision = "7"
    response = await complete(creation_client, token)
    assert response.status_code == 410
    assert not creation.posts
    assert (await persisted(recoveries, token)).status == "pending"


async def test_atomic_native_compare_rejects_identity_change_after_backend_check(creation, creation_client, recoveries):
    token = await issue(creation_client, creation)
    creation.before_post = lambda: setattr(creation, "identity_revision", "6")
    response = await complete(creation_client, token)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "password_create_identity_changed"
    assert (await persisted(recoveries, token)).status == "identity_changed"
    assert creation.users["external"].afterglow_local_password is False
    assert len(creation.posts) == 1


async def test_native_existing_password_conflict_is_independent_of_error_body(creation, creation_client):
    token = await issue(creation_client, creation)
    creation.post_status = 409
    creation.post_reason = None
    response = await complete(creation_client, token)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "password_already_exists"


@pytest.mark.parametrize("revision", [None, "", "01", "-1", "1.0", 5, "18446744073709551616"])
async def test_issuance_requires_exact_native_decimal_revision(creation, creation_client, revision):
    creation.identity_revision = revision
    response = await creation_client.post(BASE + "/create/request", json={})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "password_create_native_unavailable"
    assert not creation.sent and not creation.posts


@pytest.mark.parametrize("origin,marker", [("password", False), ("federated", True), ("password", None)])
async def test_existing_change_capability_survives_unavailable_sql(
    creation, creation_client, monkeypatch, origin, marker
):
    from sqlalchemy.ext.asyncio import AsyncSession

    creation.actor["auth_method"] = origin
    creation.password_states["external"] = "existing"
    creation.users["external"].afterglow_local_password = marker

    async def unavailable(*args, **kwargs):
        raise ConnectionError("SQL journal is unavailable")

    monkeypatch.setattr(AsyncSession, "execute", unavailable)
    assert (await creation_client.get(BASE + "/capability")).json() == {"mode": "change"}


async def test_issued_native_revision_is_durable_before_email_delivery(
    creation, creation_client, recoveries, monkeypatch
):
    from app.services import email_service

    original = email_service.send_email

    async def delivered(*args, **kwargs):
        async with recoveries() as session:
            row = (await session.execute(select(AccountRecovery))).scalar_one()
            assert row.status == "delivery_pending"
            assert row.native_identity_revision == "5"
            assert row.original_email == "external@test.invalid"
        return await original(*args, **kwargs)

    monkeypatch.setattr(email_service, "send_email", delivered)
    token = await issue(creation_client, creation)
    assert (await persisted(recoveries, token)).native_identity_revision == "5"


async def test_native_prewrite_password_rejection_consumes_only_old_proof(creation, creation_client, recoveries):
    token = await issue(creation_client, creation)
    seed_sessions(creation, "external")
    creation.post_status = 422
    response = await complete(creation_client, token)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "password_create_invalid_password"
    assert (await persisted(recoveries, token)).status == "invalid_password"
    assert creation.users["external"].afterglow_local_password is False
    assert not creation.revoked
    assert "first" in creation.redis.sessions and "second" in creation.redis.sessions
    assert (await complete(creation_client, token)).status_code == 410
    assert len(creation.posts) == 1
    assert (await creation_client.get(BASE + "/capability")).json() == {"mode": "create"}
    creation.post_status = 204
    replacement_token = await issue(creation_client, creation)
    assert replacement_token != token
    assert (await complete(creation_client, replacement_token, password=REPLACEMENT + "-valid")).status_code == 200
    assert len(creation.posts) == 2
