"""Real SQL transitions and HTTP routes, deterministic native/SMTP/Redis boundaries.

These tests exercise service behavior, not source-text patterns. No live provider
or SMTP credentials are needed; MariaDB variants reuse the concurrency scenarios.
"""

import asyncio
import hashlib
import json
import re
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from keystoneauth1.exceptions.http import Unauthorized
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_token_info
from app.api.identity import account_recovery as endpoints
from app.database import get_session
from app.models.account_recovery import AccountRecovery
from app.services import account_recovery as recovery
from app.services import domain_auth, domain_iam, domain_scope, email_service, keystone, session_store

PASSWORD = "original-password-123"
REPLACEMENT = "replacement-password-123"
CLOCK = datetime(2026, 10, 18, 12, tzinfo=UTC)


class Redis:
    def __init__(self):
        self.addresses = set()
        self.sessions = {}
        self.fail_revoke = False

    async def set(self, key, value, *, nx, ex):
        assert nx and ex == 60
        if key in self.addresses:
            return False
        self.addresses.add(key)
        return True

    async def ping(self):
        return True

    async def eval(self, script, count, key, uid):
        assert script == session_store._REVOKE_USER_SCRIPT and count == 1
        if self.fail_revoke:
            raise ConnectionError("Redis unavailable")
        removed = [record for record in self.sessions.values() if record["user_id"] == uid]
        self.sessions = {key: value for key, value in self.sessions.items() if value["user_id"] != uid}
        return [json.dumps(record) for record in removed]


@pytest.fixture
def directory(monkeypatch):
    state = SimpleNamespace(
        users={},
        sent=[],
        updates=[],
        revoked=[],
        auth_calls=[],
        deliver=True,
        native_error=False,
        native_rejected=False,
        redis=Redis(),
        lock=asyncio.Lock(),
        entered=threading.Event(),
        release=threading.Event(),
        gate=False,
        lease_lost=False,
    )
    state.settings = SimpleNamespace(
        os_username="operator",
        smtp_enabled=True,
        smtp_host="smtp.test.invalid",
        smtp_from_address="sender@test.invalid",
        frontend_base_url="https://ui.test.invalid",
        smtp_from_name="Afterglow",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        smtp_use_tls=True,
        smtp_timeout_seconds=5,
    )
    for uid in ["local", "admin", "operator", "external", "linked", "legacy-linked", "service"]:
        user = SimpleNamespace(
            id=uid, name=uid, email=f"{uid}@test.invalid", domain_id="home", enabled=True, password=PASSWORD
        )
        if uid in {"external", "linked", "legacy-linked"}:
            user.federated = [{"idp_id": "provider", "protocols": [{"protocol_id": "openid", "unique_id": uid}]}]
        if uid == "external":
            user.afterglow_local_password = False
        if uid == "linked":
            user.afterglow_local_password = True
        state.users[uid] = user
    state.catalog = [
        {"id": role, "name": role, "domain_id": None, "implied_role_ids": []} for role in ["admin", "service"]
    ]

    def get_user(uid):
        matches = [user for user in state.users.values() if user.id == uid]
        if len(matches) != 1:
            raise HTTPException(404, "No such user")
        return matches[0]

    def update_user(uid, **attrs):
        state.updates.append((uid, attrs))
        state.entered.set()
        if state.gate:
            assert state.release.wait(10), "Test did not release native dispatch"
        if state.native_rejected:
            raise HTTPException(403, "Native write rejected")
        user = get_user(uid)
        for key, value in attrs.items():
            setattr(user, key, value)
        if state.native_error:
            raise TimeoutError("Native outcome unknown")
        return user

    def authenticate(username, password, project, home, *, unscoped_only):
        state.auth_calls.append((username, home, project, unscoped_only))
        user = next(user for user in state.users.values() if user.name == username and user.domain_id == home)
        if password != user.password:
            raise Unauthorized()
        return {"user_id": user.id, "identity_domain_id": home, "token": "temporary-reauth-token"}

    state.ks = SimpleNamespace(
        users=SimpleNamespace(get=get_user, update=update_user, list=lambda **kw: list(state.users.values())),
        domains=SimpleNamespace(
            get=lambda home: SimpleNamespace(
                id=home, name="Native home", afterglow_display_name="Personal home", enabled=True
            )
        ),
        role_assignments=SimpleNamespace(
            list=lambda user, effective: (
                [{"user": {"id": user}, "role": {"id": user}, "scope": {"system": {"all": True}}}]
                if user in {"admin", "service"}
                else []
            )
        ),
    )

    async def assert_owned():
        if state.lease_lost:
            raise HTTPException(409, "Lease lost")

    @asynccontextmanager
    async def mutation():
        async with state.lock:
            yield SimpleNamespace(assert_owned=assert_owned), state.ks, state.catalog

    async def send(message, **kwargs):
        state.sent.append(message)
        if not state.deliver:
            raise ConnectionError("SMTP unavailable")

    async def redis():
        return state.redis

    async def invalidate():
        pass

    async def policy(home, email, **kwargs):
        assert home == "home"
        return domain_auth.normalize_email(email)

    monkeypatch.setattr(recovery, "get_settings", lambda: state.settings)
    monkeypatch.setattr("app.config.get_settings", lambda: state.settings)
    monkeypatch.setattr(recovery, "_now", lambda: CLOCK)
    monkeypatch.setattr(domain_iam, "_iam_write", mutation)
    monkeypatch.setattr(domain_iam, "password_policy", policy)
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: state.ks)
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    monkeypatch.setattr(keystone, "revoke_token", state.revoked.append)
    monkeypatch.setattr(session_store, "_get_redis", redis)
    monkeypatch.setattr(domain_scope, "invalidate_authority", invalidate)
    monkeypatch.setattr("aiosmtplib.send", send)
    return state


@pytest_asyncio.fixture
async def recoveries(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'recovery.sqlite'}")
    async with engine.begin() as conn:
        await conn.run_sync(AccountRecovery.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def token_from(message):
    body = next(
        part.get_payload(decode=True).decode() for part in message.walk() if part.get_content_type() == "text/plain"
    )
    return re.search(r"/recover/([A-Za-z0-9_-]+)", body).group(1)


async def issue(directory, factory, kind="password", uid="local"):
    directory.redis.addresses.clear()
    async with factory() as session:
        result = await recovery.request_recovery(kind, directory.users[uid].email, session)
    assert result == {"accepted": True}
    return token_from(directory.sent[-1])


async def persisted(factory, token):
    async with factory() as session:
        return await session.get(AccountRecovery, hashlib.sha256(token.encode()).hexdigest())


def seed_sessions(directory, uid="local"):
    uid = directory.users[uid].id
    directory.redis.sessions = {
        "first": {"user_id": uid, "keystone_token": "native-one", "domain_id": "home"},
        "second": {"user_id": uid, "keystone_token": "native-two", "domain_id": "working-other"},
        "other": {"user_id": "unrelated", "keystone_token": "native-unrelated"},
    }


def actor(uid="local"):
    return {"user_id": uid, "identity_domain_id": "home", "domain_id": "working-other"}


@pytest_asyncio.fixture
async def client(directory, recoveries):
    app = FastAPI()
    app.include_router(endpoints.router, prefix="/api/v1/auth")

    async def session():
        async with recoveries() as value:
            yield value

    async def authenticated():
        return actor()

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_token_info] = authenticated
    enabled = endpoints.limiter.enabled
    endpoints.limiter.enabled = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as value:
        yield value
    endpoints.limiter.enabled = enabled


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["username", "password"])
async def test_requests_are_non_enumerating_and_secret_free(client, directory, recoveries, path):
    for email in [
        "local@test.invalid",
        "missing@test.invalid",
        "operator@test.invalid",
        "external@test.invalid",
        "legacy-linked@test.invalid",
        "service@test.invalid",
    ]:
        response = await client.post(f"/api/v1/auth/recovery/{path}", json={"email": email})
        assert response.status_code == 202 and response.json() == {"accepted": True}
        assert "no-store" in response.headers["cache-control"]
        assert response.headers["referrer-policy"] == "no-referrer"
    assert len(directory.sent) == 1
    async with recoveries() as session:
        rows = (await session.execute(select(AccountRecovery))).scalars().all()
        assert len(rows) == 1
        record = rows[0]
        values = [getattr(record, column.name) for column in record.__table__.columns]
        assert token_from(directory.sent[0]) not in values and PASSWORD not in values


@pytest.mark.asyncio
async def test_username_get_consumes_but_password_get_does_not(client, directory, recoveries):
    token = await issue(directory, recoveries, "username")
    first = await client.get(f"/api/v1/auth/recovery/{token}")
    assert first.status_code == 200
    assert first.json() == {
        "kind": "username",
        "email": "local@test.invalid",
        "username": "local",
        "identity_domain_id": "home",
        "identity_domain_name": "Personal home",
    }
    assert (await client.get(f"/api/v1/auth/recovery/{token}")).status_code == 410
    token = await issue(directory, recoveries)
    for _ in range(2):
        result = await client.get(f"/api/v1/auth/recovery/{token}")
        assert result.status_code == 200 and "username" not in result.json()
    assert (await persisted(recoveries, token)).status == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("uid", ["local", "admin", "linked"])
async def test_reset_preserves_identity_and_revokes_every_working_domain_session(client, directory, recoveries, uid):
    token = await issue(directory, recoveries, uid=uid)
    seed_sessions(directory, uid)
    result = await client.post(
        "/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT}
    )
    assert result.status_code == 200 and result.json() == {"status": "changed"}
    assert directory.users[uid].password == REPLACEMENT and directory.users[uid].domain_id == "home"
    assert directory.users[uid].afterglow_local_password is True
    assert set(directory.redis.sessions) == {"other"}
    assert set(directory.revoked) == {"native-one", "native-two"}
    assert (await persisted(recoveries, token)).status == "changed"
    replay = await client.post(
        "/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT}
    )
    assert replay.status_code == 410 and len(directory.updates) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["expired", "email", "home", "disabled", "deleted", "duplicate", "external"])
async def test_bound_proof_cannot_reset_changed_or_ambiguous_subject(client, directory, recoveries, mutation):
    token = await issue(directory, recoveries)
    if mutation == "expired":
        async with recoveries() as session:
            row = await session.get(AccountRecovery, hashlib.sha256(token.encode()).hexdigest())
            row.expires_at = CLOCK
            await session.commit()
    elif mutation == "email":
        directory.users["local"].email = "LOCAL@test.invalid"  # even normalized-equal native edit breaks exact binding
    elif mutation == "home":
        directory.users["local"].domain_id = "other-home"
    elif mutation == "disabled":
        directory.users["local"].enabled = False
    elif mutation == "deleted":
        del directory.users["local"]
    elif mutation == "duplicate":
        directory.users["other"] = SimpleNamespace(
            id="other", name="other", email="LOCAL@test.invalid", domain_id="other-home", enabled=True
        )
    else:
        directory.users["local"].afterglow_local_password = False
    response = await client.post(
        "/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT}
    )
    assert response.status_code == 410 and not directory.updates


@pytest.mark.asyncio
async def test_delivery_failure_and_unconfirmed_delivery_never_redeem(client, directory, recoveries, monkeypatch):
    directory.deliver = False
    response = await client.post("/api/v1/auth/recovery/password", json={"email": "local@test.invalid"})
    assert response.status_code == 202
    token = token_from(directory.sent[-1])
    assert (await persisted(recoveries, token)).status == "delivery_failed"
    assert (await client.get(f"/api/v1/auth/recovery/{token}")).status_code == 410
    async with recoveries() as session:
        row = await session.get(AccountRecovery, hashlib.sha256(token.encode()).hexdigest())
        row.status = "delivery_pending"
        await session.commit()
    assert (await client.get(f"/api/v1/auth/recovery/{token}")).status_code == 410


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["timeout", "rejection"])
async def test_unknown_or_rejected_native_outcome_is_consumed_not_replayed(client, directory, recoveries, mode):
    token = await issue(directory, recoveries)
    seed_sessions(directory)
    directory.native_error = mode == "timeout"
    directory.native_rejected = mode == "rejection"
    result = await client.post(
        "/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT}
    )
    assert result.status_code == 502 and result.json()["detail"]["code"] == "recovery_outcome_unknown"
    assert (await persisted(recoveries, token)).status == "outcome_unknown"
    assert set(directory.redis.sessions) == {"other"}
    assert (
        await client.post("/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT})
    ).status_code == 410
    assert len(directory.updates) == 1


@pytest.mark.asyncio
async def test_session_failure_is_real_failure_not_success(client, directory, recoveries):
    token = await issue(directory, recoveries)
    directory.redis.fail_revoke = True
    response = await client.post(
        "/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT}
    )
    assert response.status_code == 503 and response.json()["detail"]["code"] == "recovery_sessions_failed"
    assert (await persisted(recoveries, token)).status == "sessions_failed"
    assert directory.users["local"].password == REPLACEMENT
    assert (await client.get(f"/api/v1/auth/recovery/{token}")).status_code == 410


@pytest.mark.asyncio
async def test_native_revocation_failure_attempts_all_captured_tokens_and_consumes_proof(
    client, directory, recoveries, monkeypatch
):
    token = await issue(directory, recoveries)
    seed_sessions(directory)

    def revoke(native_token):
        directory.revoked.append(native_token)
        if native_token == "native-one":
            raise ConnectionError("Native token revocation unavailable")

    monkeypatch.setattr(keystone, "revoke_token", revoke)
    response = await client.post(
        "/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "recovery_sessions_failed"
    assert (await persisted(recoveries, token)).status == "sessions_failed"
    assert directory.revoked == ["native-one", "native-two"]
    assert set(directory.redis.sessions) == {"other"}
    assert directory.users["local"].password == REPLACEMENT
    replay = await client.post(
        "/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT}
    )
    assert replay.status_code == 410 and len(directory.updates) == 1


@pytest.mark.asyncio
async def test_email_change_reauth_home_notice_confirmation_uniqueness_and_revocation(client, directory, recoveries):
    seed_sessions(directory)
    result = await client.post(
        "/api/v1/auth/email/changes", json={"email": "New@Test.Invalid", "current_password": PASSWORD}
    )
    assert result.status_code == 202
    assert directory.auth_calls == [("local", "home", "", True)]
    assert "temporary-reauth-token" in directory.revoked
    notice = directory.sent[0].as_string()
    assert (
        directory.sent[0]["To"] == "local@test.invalid"
        and "/recover/" not in notice
        and "new@test.invalid" not in notice
    )
    token = token_from(directory.sent[1])
    inspected = await client.get(f"/api/v1/auth/recovery/{token}")
    assert inspected.json()["kind"] == "email_change" and inspected.json()["email"] == "new@test.invalid"
    assert directory.users["local"].email == "local@test.invalid"
    changed = await client.post("/api/v1/auth/email/changes/accept", json={"token": token})
    assert changed.status_code == 200 and changed.json() == {"status": "changed"}
    assert (
        directory.users["local"].email == "new@test.invalid"
        and directory.users["local"].afterglow_email_verified is True
    )
    assert set(directory.redis.sessions) == {"other"}
    assert (await client.post("/api/v1/auth/email/changes/accept", json={"token": token})).status_code == 410


@pytest.mark.asyncio
async def test_email_change_fails_wrong_password_and_target_collision(client, directory):
    wrong = await client.post(
        "/api/v1/auth/email/changes", json={"email": "new@test.invalid", "current_password": "incorrect-password"}
    )
    assert wrong.status_code == 401 and not directory.sent
    duplicate = await client.post(
        "/api/v1/auth/email/changes", json={"email": "admin@test.invalid", "current_password": PASSWORD}
    )
    assert duplicate.status_code == 409 and not directory.sent


@pytest.mark.asyncio
async def test_email_change_unique_check_repeated_inside_redemption_lease(client, directory, recoveries):
    response = await client.post(
        "/api/v1/auth/email/changes", json={"email": "new@test.invalid", "current_password": PASSWORD}
    )
    assert response.status_code == 202
    token = token_from(directory.sent[-1])
    directory.users["admin"].email = "NEW@test.invalid"
    result = await client.post("/api/v1/auth/email/changes/accept", json={"token": token})
    assert result.status_code == 409 and not directory.updates


@pytest.mark.asyncio
async def test_other_kind_cannot_dispatch_and_invalid_input_never_echoes_secrets(client, directory, recoveries):
    token = await issue(directory, recoveries, "username")
    result = await client.post(
        "/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT}
    )
    assert result.status_code == 410 and not directory.updates
    for body in [
        {"token": token, "new_password": "leak-secret"},
        {"token": token, "new_password": REPLACEMENT, "extra": "secret"},
    ]:
        result = await client.post("/api/v1/auth/recovery/password/complete", json=body)
        assert result.status_code == 422 and "secret" not in result.text and token not in result.text
        assert result.headers["referrer-policy"] == "no-referrer"


@pytest.mark.asyncio
async def test_address_budget_is_shared_and_unknown_accounts_still_accepted(client, directory):
    for path in ["password", "username", "password"]:
        response = await client.post(f"/api/v1/auth/recovery/{path}", json={"email": "LOCAL@Test.Invalid"})
        assert response.status_code == 202
    assert len(directory.sent) == 1
    assert all("local" not in key for key in directory.redis.addresses)


async def competing_resets(directory, factory):
    token = await issue(directory, factory)
    directory.gate = True

    async def reset():
        async with factory() as session:
            return await recovery.complete(token, session, new_password=REPLACEMENT)

    first = asyncio.create_task(reset())
    assert await asyncio.to_thread(directory.entered.wait, 10)
    second = asyncio.create_task(reset())
    directory.release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)
    assert sum(isinstance(value, dict) for value in results) == 1
    failure = next(value for value in results if isinstance(value, HTTPException))
    assert failure.status_code == 410
    assert len(directory.updates) == 1
    assert (await persisted(factory, token)).status == "changed"


@pytest.mark.asyncio
async def test_concurrent_resets_dispatch_native_once(directory, recoveries):
    await competing_resets(directory, recoveries)


@pytest.mark.asyncio
async def test_cancelled_request_drains_native_write_and_session_revocation(directory, recoveries):
    token = await issue(directory, recoveries)
    seed_sessions(directory)
    directory.gate = True

    async def reset():
        async with recoveries() as session:
            return await recovery.complete(token, session, new_password=REPLACEMENT)

    task = asyncio.create_task(reset())
    assert await asyncio.to_thread(directory.entered.wait, 10)
    task.cancel()
    directory.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await persisted(recoveries, token)).status == "changed"
    assert set(directory.redis.sessions) == {"other"} and len(directory.updates) == 1


@pytest.mark.asyncio
async def test_committed_dispatch_fence_survives_final_sql_failure(directory, recoveries, monkeypatch):
    token = await issue(directory, recoveries)
    async with recoveries() as session:
        commit = session.commit
        calls = 0

        async def fail_final_commit():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ConnectionError("Final SQL commit lost")
            await commit()

        monkeypatch.setattr(session, "commit", fail_final_commit)
        with pytest.raises(ConnectionError):
            await recovery.complete(token, session, new_password=REPLACEMENT)
    assert (await persisted(recoveries, token)).status == "dispatching"
    async with recoveries() as session:
        with pytest.raises(HTTPException) as rejected:
            await recovery.complete(token, session, new_password=REPLACEMENT)
    assert rejected.value.status_code == 410 and len(directory.updates) == 1


@pytest.mark.asyncio
async def test_undeliverable_and_ambiguous_requests_all_return_202(client, directory):
    directory.users["admin"].email = "LOCAL@test.invalid"
    assert (
        await client.post("/api/v1/auth/recovery/password", json={"email": "local@test.invalid"})
    ).status_code == 202
    assert not directory.sent
    directory.settings.smtp_enabled = False
    assert (
        await client.post("/api/v1/auth/recovery/password", json={"email": "linked@test.invalid"})
    ).status_code == 202
    assert not directory.sent


@pytest.mark.asyncio
async def test_failed_dispatch_commit_performs_no_native_write(directory, recoveries, monkeypatch):
    token = await issue(directory, recoveries)
    async with recoveries() as session:

        async def unavailable():
            raise ConnectionError("Dispatch fence unavailable")

        monkeypatch.setattr(session, "commit", unavailable)
        with pytest.raises(ConnectionError):
            await recovery.complete(token, session, new_password=REPLACEMENT)
    assert not directory.updates
    assert (await persisted(recoveries, token)).status == "pending"


@pytest.mark.asyncio
async def test_reset_supersedes_other_outstanding_mutation_proofs(directory, recoveries):
    first = await issue(directory, recoveries)
    second = await issue(directory, recoveries)
    async with recoveries() as session:
        await recovery.complete(first, session, new_password=REPLACEMENT)
    assert (await persisted(recoveries, second)).status == "superseded"
    async with recoveries() as session:
        with pytest.raises(HTTPException) as rejected:
            await recovery.complete(second, session, new_password=REPLACEMENT)
    assert rejected.value.status_code == 410 and len(directory.updates) == 1


@pytest.mark.asyncio
async def test_email_change_delivery_failure_returns_202_without_redeemable_proof(
    client, directory, recoveries, monkeypatch
):
    calls = 0
    send = email_service.send_email

    async def fail_target(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            directory.deliver = False
        return await send(*args, **kwargs)

    monkeypatch.setattr(email_service, "send_email", fail_target)
    response = await client.post(
        "/api/v1/auth/email/changes", json={"email": "new@test.invalid", "current_password": PASSWORD}
    )
    assert response.status_code == 202 and response.json() == {"accepted": True}
    token = token_from(directory.sent[-1])
    assert (await persisted(recoveries, token)).status == "delivery_failed"
    assert (await client.post("/api/v1/auth/email/changes/accept", json={"token": token})).status_code == 410
    assert not directory.updates


@pytest.mark.asyncio
async def test_email_change_external_only_and_operational_accounts_fail_closed(directory, recoveries):
    for uid in ["operator", "external", "legacy-linked", "service"]:
        async with recoveries() as session:
            with pytest.raises(HTTPException) as rejected:
                await recovery.request_email_change("new@test.invalid", PASSWORD, actor(uid), session)
        assert rejected.value.status_code == 403
    assert not directory.sent and not directory.updates


@pytest.mark.asyncio
async def test_concurrent_username_owner_reads_reveal_name_once(directory, recoveries):
    token = await issue(directory, recoveries, "username")

    async def read_owner():
        async with recoveries() as session:
            return await recovery.inspect(token, session)

    results = await asyncio.gather(read_owner(), read_owner(), return_exceptions=True)
    assert sum(isinstance(result, dict) and result.get("username") == "local" for result in results) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code == 410 for result in results) == 1


@pytest.mark.asyncio
async def test_recovery_service_never_logs_bearer_or_password(directory, recoveries, caplog):
    token = await issue(directory, recoveries)
    directory.native_error = True
    async with recoveries() as session:
        with pytest.raises(HTTPException):
            await recovery.complete(token, session, new_password=REPLACEMENT)
    assert token not in caplog.text and REPLACEMENT not in caplog.text and PASSWORD not in caplog.text


@pytest.mark.asyncio
async def test_token_inspection_budget_is_shared_across_distinct_bearer_paths(directory, recoveries):
    app = FastAPI()
    app.state.limiter = endpoints.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(endpoints.router, prefix="/api/v1/auth")

    async def session():
        async with recoveries() as value:
            yield value

    app.dependency_overrides[get_session] = session
    enabled = endpoints.limiter.enabled
    endpoints.limiter.enabled = True
    try:
        transport = ASGITransport(app=app, client=("192.0.2.143", 50000))
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            for index in range(20):
                token = f"proof-{index:038d}"
                result = await client.get(f"/api/v1/auth/recovery/{token}")
                assert result.status_code == 410
            result = await client.get("/api/v1/auth/recovery/proof-00000000000000000000000000000000000020")
            assert result.status_code == 429
            assert "no-store" in result.headers["cache-control"]
            assert result.headers["referrer-policy"] == "no-referrer"
        other_source = ASGITransport(app=app, client=("192.0.2.144", 50000))
        async with AsyncClient(transport=other_source, base_url="http://localhost") as client:
            result = await client.get("/api/v1/auth/recovery/proof-00000000000000000000000000000000000020")
            assert result.status_code == 410
    finally:
        endpoints.limiter.enabled = enabled
