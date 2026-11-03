"""Behavioral native/SMTP/HTTP boundaries using only dummy identities and secrets."""

import asyncio
import copy
import json
import string
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import Integer, MetaData, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import deps
from app.api.identity import admin_password_reset as endpoint
from app.database import get_session
from app.models.account_recovery import AccountRecovery
from app.models.activity import ActivityLog
from app.services import account_recovery, domain_iam, domain_scope, keystone, native_operation, session_store
from app.services import admin_password_reset as reset


@pytest_asyncio.fixture
async def directory(monkeypatch, tmp_path):
    state = SimpleNamespace(
        users={
            "target": {
                "id": "target",
                "domain_id": "home",
                "name": "Alice <Admin>",
                "email": "alice@example.test",
                "enabled": True,
                # Plain local accounts keep the ordinary administrator PATCH.
                "unrelated": {"keep": True},
            }
        },
        actor={
            "user_id": "actor",
            "identity_domain_id": "actor-home",
            "domain_id": "selected-workspace",
            "domain_name": "workspace",
            "project_id": "workspace-project",
            "is_system_admin": True,
            "token": "dummy-actor-token",
            "username": "operator",
        },
        events=[],
        updates=[],
        mail=[],
        writes=[],
        reads=[],
        capability_status=200,
        capability={"supported": True, "revision": "first-password-galera-v2"},
        password_state="existing",
        identity_revision="7",
        identity_snapshots=[],
        guarded_status=204,
        before_write=None,
        after_smtp_preflight=None,
        audits=[],
        sessions=["target-session"],
        cooldown=set(),
        service_roles=[],
        groups=[],
        raw_system=[],
        group_system=[],
        admin=True,
        response_status=200,
        response_override=None,
        native_unknown=False,
        smtp_unavailable=False,
        mail_failed=False,
        mail_refused=False,
        revoke_failed=False,
        invalidation_failed=False,
        redis_failed=False,
        lease_lost=False,
        conn_mismatch=False,
        native_gate=False,
        entered=threading.Event(),
        release=threading.Event(),
        lock=asyncio.Lock(),
        fail_commits=set(),
        commits=0,
    )
    settings = SimpleNamespace(
        os_username="service-user",
        os_auth_url="https://identity.example.test/v3",
        ssl_verify=True,
        smtp_enabled=True,
        smtp_host="smtp.example.test",
        smtp_from_address="sender@example.test",
        frontend_base_url="https://console.example.test",
        smtp_from_name="Afterglow",
        smtp_port=587,
        smtp_username="dummy-smtp-user",
        smtp_password="dummy-smtp-auth",
        smtp_use_tls=True,
        smtp_timeout_seconds=3,
    )
    state.settings = settings
    state.conn = SimpleNamespace(
        _afterglow_user_id="actor", _afterglow_identity_domain_id="actor-home", _afterglow_token="dummy-service-token"
    )
    state.catalog = [
        {"id": role, "name": role, "domain_id": None, "implied_role_ids": []} for role in ("service", "admin", "reader")
    ]

    def get_user(uid):
        if uid not in state.users:
            raise HTTPException(404, "not found")
        return copy.deepcopy(state.users[uid])

    def assignments(**kwargs):
        if kwargs.get("effective"):
            return [
                {"user": {"id": kwargs["user"]}, "role": {"id": role}, "scope": {"project": {"id": "a-project"}}}
                for role in state.service_roles
            ]
        return state.group_system if "group" in kwargs else state.raw_system

    state.ks = SimpleNamespace(
        session=SimpleNamespace(get_token=lambda: "dummy-native-service-token"),
        users=SimpleNamespace(get=get_user),
        domains=SimpleNamespace(get=lambda did: {"id": did, "enabled": True}),
        role_assignments=SimpleNamespace(list=assignments),
        groups=SimpleNamespace(list=lambda **kw: state.groups),
    )

    async def assert_owned():
        state.events.append("lease")
        if state.lease_lost:
            raise HTTPException(409, "lost lease")

    @asynccontextmanager
    async def mutation():
        async with state.lock:
            yield SimpleNamespace(assert_owned=assert_owned), state.ks, state.catalog

    async def find_accounts(home, *, email):
        return [copy.deepcopy(user) for user in state.users.values() if user.get("email", "").casefold() == email]

    class Redis:
        async def ping(self):
            state.events.append("redis-ready")
            if state.redis_failed:
                raise ConnectionError("dummy unavailable")
            return True

        async def set(self, key, value, *, nx, ex):
            assert nx and ex == 300 and value == "1"
            if key in state.cooldown:
                return False
            state.cooldown.add(key)
            return True

    async def redis():
        return Redis()

    class SMTP:
        def __init__(self, **kwargs):
            state.smtp_options = kwargs

        async def connect(self):
            state.events.append("smtp-preflight")
            if state.smtp_unavailable:
                raise RuntimeError("dummy smtp auth failed")
            if state.after_smtp_preflight is not None:
                state.after_smtp_preflight()

        async def send_message(self, message, *, recipients, sender):
            state.events.append("mail")
            state.mail.append((message, recipients, sender))
            if state.mail_failed:
                raise RuntimeError("SMTP DATA echoed: " + message.as_string())
            return ({recipients[0]: "refused"} if state.mail_refused else {}), "queued"

        def close(self):
            state.events.append("smtp-close")

    class Response:
        def __init__(self, status, payload):
            self.status_code, self.payload = status, payload

        def json(self):
            return self.payload

        def close(self):
            state.events.append("response-close")

    class Transport:
        def __init__(self):
            self.session = SimpleNamespace(close=lambda: state.events.append("transport-close"))

        def request(self, url, method, **kwargs):
            guarded = "/OS-AFTERGLOW/" in url
            if method == "GET":
                state.reads.append((url, method, kwargs))
                if url.endswith("/capabilities"):
                    return Response(state.capability_status, state.capability)
                identity = {key: state.users["target"][key] for key in ("id", "domain_id", "email")}
                identity.update(identity_revision=state.identity_revision, password_state=state.password_state)
                if state.identity_snapshots:
                    identity.update(state.identity_snapshots.pop(0))
                return Response(200, {"user": identity})
            state.events.append("native")
            state.updates.append((url, method, kwargs))
            state.entered.set()
            if state.native_gate:
                assert state.release.wait(5), "test did not release dummy native request"
            uid = "target" if guarded else url.rsplit("/", 1)[-1]
            status = state.guarded_status if guarded else state.response_status
            if guarded:
                if state.before_write is not None:
                    state.before_write()
                body = kwargs["json"]["user"]
                expected_state = "absent" if url.endswith("/initial-password") else "existing"
                if (
                    body["domain_id"] != state.users[uid]["domain_id"]
                    or body["email"] != state.users[uid]["email"]
                    or body["identity_revision"] != state.identity_revision
                    or state.password_state != expected_state
                ):
                    return Response(412, None)
                if status == 204:
                    state.writes.append(copy.deepcopy(body))
                    state.users[uid].update(password=body["password"], afterglow_local_password=True)
                    state.password_state = "existing"
                    state.identity_revision = str(int(state.identity_revision) + 1)
            elif status == 200:
                state.writes.append(copy.deepcopy(kwargs["json"]["user"]))
                state.users[uid].update(kwargs["json"]["user"])
            if state.native_unknown:
                raise RuntimeError("native secret: " + kwargs["json"]["user"]["password"])
            body = state.response_override or {"user": copy.deepcopy(state.users[uid])}
            return Response(status, body)

    def transport(**kwargs):
        assert kwargs == {"timeout": 30, "verify": True}
        return Transport()

    async def revoke(uid, **kwargs):
        assert uid == "target" and kwargs == {"revoke_keystone": True, "strict_keystone": True}
        state.events.append("revoke")
        state.sessions.clear()
        if state.revoke_failed:
            raise RuntimeError("dummy revoke failed")

    async def invalidate():
        state.events.append("invalidate")
        if state.invalidation_failed:
            raise RuntimeError("dummy cache failed")

    class Operation:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def run(self, fn, *args, **kwargs):
            kwargs.pop("operation", None)
            return fn(*args, **kwargs)

    def native_proof(token, **kwargs):
        state.events.append("actor-proof")
        return {"user_id": "actor", "identity_domain_id": "actor-home", "domain_id": "selected-workspace", "roles": []}

    monkeypatch.setattr(reset, "get_settings", lambda: settings)
    monkeypatch.setattr(account_recovery, "get_settings", lambda: settings)
    monkeypatch.setattr(domain_iam, "_iam_write", mutation)
    monkeypatch.setattr(domain_iam, "_find_accounts", find_accounts)
    monkeypatch.setattr(session_store, "_get_redis", redis)
    monkeypatch.setattr(session_store, "revoke_user_sessions", revoke)
    monkeypatch.setattr(domain_scope, "invalidate_authority", invalidate)
    monkeypatch.setattr(domain_scope, "domain_context", lambda *args: {"is_system_admin": state.admin})
    monkeypatch.setattr(domain_scope, "assert_token_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(keystone, "_is_system_admin", lambda *args, **kwargs: state.admin)
    monkeypatch.setattr(keystone, "validate_token", native_proof)
    monkeypatch.setattr(native_operation, "NativeOperation", Operation)
    monkeypatch.setattr("aiosmtplib.SMTP", SMTP)
    monkeypatch.setattr(keystone.native_transport, "create_session", transport)

    class Session(AsyncSession):
        async def commit(self):
            state.commits += 1
            state.events.append("commit")
            if state.commits in state.fail_commits:
                raise RuntimeError("dummy audit DB unavailable")
            audits = [row for row in list(self.new) + list(self.identity_map.values()) if isinstance(row, ActivityLog)]
            snapshots = [
                {"user_id": row.user_id, "resource_id": row.resource_id, "extra": copy.deepcopy(row.extra)}
                for row in audits
            ]
            await super().commit()
            state.audits.extend(snapshots)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'reset.sqlite'}")
    metadata = MetaData()
    activity_table = ActivityLog.__table__.to_metadata(metadata)
    activity_table.c.id.type = Integer()
    AccountRecovery.__table__.to_metadata(metadata)
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    state.factory = async_sessionmaker(engine, class_=Session, expire_on_commit=False)
    yield state
    await engine.dispose()


def make_app(state):
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/api/v1/admin")
    app.state.limiter = endpoint.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.dependency_overrides[deps.get_token_info] = lambda: state.actor.copy()

    async def connection():
        # Keep the real fresh require_admin dependency on the endpoint itself.
        return state.conn

    app.dependency_overrides[deps.get_admin_os_conn] = connection

    async def session():
        async with state.factory() as value:
            yield value

    app.dependency_overrides[get_session] = session
    return app


async def post(state, body=None, *, app=None):
    async with AsyncClient(transport=ASGITransport(app=app or make_app(state)), base_url="http://test") as client:
        return await client.post("/api/v1/admin/users/target/password/reset-email", json={} if body is None else body)


@pytest.fixture(autouse=True)
def rate_limit():
    old = endpoint.limiter.enabled
    endpoint.limiter.enabled = False
    endpoint.limiter.reset()
    yield
    endpoint.limiter.reset()
    endpoint.limiter.enabled = old


def assert_private(response):
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["referrer-policy"] == "no-referrer"


@pytest.mark.asyncio
async def test_success_exact_native_update_then_automatic_email(directory, caplog):
    before = copy.deepcopy(directory.users["target"])
    response = await post(directory)
    assert response.status_code == 200 and response.json() == {"status": "changed", "delivered": True}
    assert_private(response)
    assert len(directory.updates) == len(directory.mail) == 1
    url, method, opts = directory.updates[0]
    assert url == "https://identity.example.test/v3/users/target" and method == "PATCH"
    password = opts["json"]["user"]["password"]
    assert len(password) >= 24
    assert all(
        any(char in group for char in password)
        for group in (string.ascii_uppercase, string.ascii_lowercase, string.digits, reset._SYMBOLS)
    )
    assert all(directory.users["target"][key] == value for key, value in before.items())
    message, recipients, _ = directory.mail[0]
    text = message.get_body(preferencelist=("plain",)).get_content()
    assert recipients == ["alice@example.test"]
    assert password in text and before["name"] in text
    assert "https://console.example.test/login" in text
    assert directory.events.index("smtp-preflight") < directory.events.index("native") < directory.events.index("mail")
    assert directory.events.index("mail") < directory.events.index("revoke")
    assert not directory.sessions and "invalidate" in directory.events
    assert password not in response.text + caplog.text + json.dumps(directory.audits)
    assert directory.audits[-1]["resource_id"] == "target" and directory.audits[-1]["user_id"] == "actor"
    assert directory.events.index("commit") < directory.events.index("native")


@pytest.mark.asyncio
@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize(
    "case,expected",
    [
        ("not_admin", 403),
        ("revoked_admin", 403),
        ("executor_mismatch", 403),
        ("executor_home", 403),
        ("disabled", 403),
        ("noemail", 409),
        ("duplicate", 409),
        ("configured_service", 403),
        ("service_role", 403),
        ("raw_service", 403),
        ("group_service", 403),
        ("missing_smtp", 503),
        ("smtp_down", 503),
        ("plaintext_smtp", 503),
        ("redis_down", 503),
        ("identity_mismatch", 503),
        ("lease_lost", 503),
    ],
)
async def test_preflight_prevents_native_writes(directory, case, expected, external):
    if external:
        directory.users["target"]["federated"] = [{"idp_id": "gitlab"}]
    if case == "not_admin":
        directory.actor["is_system_admin"] = False
    elif case == "revoked_admin":
        directory.admin = False
    elif case == "executor_mismatch":
        directory.conn._afterglow_user_id = "another-admin"
    elif case == "executor_home":
        directory.conn._afterglow_identity_domain_id = "wrong-home"
    elif case == "disabled":
        directory.users["target"]["enabled"] = False
    elif case == "noemail":
        directory.users["target"]["email"] = ""
    elif case == "duplicate":
        directory.users["other"] = {**directory.users["target"], "id": "other", "domain_id": "other-home"}
    elif case == "configured_service":
        directory.users["target"]["name"] = directory.settings.os_username
    elif case == "service_role":
        directory.service_roles = ["service"]
    elif case == "raw_service":
        directory.raw_system = [
            {"user": {"id": "target"}, "role": {"id": "service"}, "scope": {"system": {"all": True}}}
        ]
    elif case == "group_service":
        directory.groups = [{"id": "service-group"}]
        directory.group_system = [
            {"group": {"id": "service-group"}, "role": {"id": "service"}, "scope": {"system": {"all": True}}}
        ]
    elif case == "missing_smtp":
        directory.settings.smtp_enabled = False
    elif case == "smtp_down":
        directory.smtp_unavailable = True
    elif case == "plaintext_smtp":
        directory.settings.smtp_use_tls = False
    elif case == "redis_down":
        directory.redis_failed = True
    elif case == "identity_mismatch":
        directory.users["target"]["id"] = "another-user"
    elif case == "lease_lost":
        directory.lease_lost = True
    response = await post(directory)
    assert response.status_code == expected
    assert_private(response)
    assert not directory.updates and not directory.mail and directory.sessions


@pytest.mark.asyncio
async def test_system_administrator_target_allowed(directory):
    directory.service_roles = ["admin"]
    assert (await post(directory)).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("password_state", ["absent", "existing"])
@pytest.mark.parametrize(
    "metadata", ["federated_missing", "federated_false", "federated_true", "external", "marker_false"]
)
async def test_external_native_state_selects_guarded_create_or_reset(directory, password_state, metadata, caplog):
    user = directory.users["target"]
    if metadata.startswith("federated"):
        user["federated"] = [{"idp_id": "gitlab", "protocols": [{"protocol_id": "openid"}]}]
        if metadata != "federated_missing":
            user["afterglow_local_password"] = metadata == "federated_true"
    elif metadata == "external":
        user["afterglow_external_identities"] = [{"provider": "gitlab", "subject": "stable-owner"}]
    else:
        user["afterglow_local_password"] = False
    before = copy.deepcopy(user)
    directory.password_state = password_state
    response = await post(directory)
    assert response.status_code == 200 and response.json() == {"status": "changed", "delivered": True}
    assert_private(response)
    assert len(directory.updates) == len(directory.writes) == len(directory.mail) == 1
    url, method, options = directory.updates[0]
    operation = "initial-password" if password_state == "absent" else "password-reset"
    assert url == f"https://identity.example.test/v3/users/target/OS-AFTERGLOW/{operation}"
    assert method == "POST"
    password = options["json"]["user"]["password"]
    assert options["json"] == {
        "user": {"password": password, "domain_id": "home", "email": "alice@example.test", "identity_revision": "7"}
    }
    assert options["headers"] == {"X-Auth-Token": "dummy-native-service-token"}
    assert options["authenticated"] is options["allow_reauth"] is options["redirect"] is options["log"] is False
    assert options["connect_retries"] == options["status_code_retries"] == 0
    assert len(directory.reads) == 3
    assert directory.users["target"]["password"] == password
    assert all(
        directory.users["target"][key] == value for key, value in before.items() if key != "afterglow_local_password"
    )
    message, recipients, _ = directory.mail[0]
    assert (
        recipients == ["alice@example.test"] and password in message.get_body(preferencelist=("plain",)).get_content()
    )
    assert not directory.sessions and directory.audits[-1]["extra"]["outcome"] == "changed"
    assert directory.events.index("commit") < directory.events.index("native")
    assert password not in response.text + caplog.text + json.dumps(directory.audits)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"password": "browser-secret"},
        {"email": "attacker@example.test"},
        {"domain_id": "foreign"},
        [],
        "password=browser-secret",
    ],
)
async def test_only_empty_object_accepted_without_input_echo(directory, body):
    response = await post(directory, body)
    assert response.status_code == 422 and "browser-secret" not in response.text
    assert_private(response)
    assert not directory.updates


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "external,status",
    [(False, status) for status in (400, 401, 403, 404, 409, 412, 422)]
    + [(True, status) for status in (409, 412, 422)],
)
async def test_explicit_native_rejection_is_not_changed_or_emailed(directory, status, external):
    if external:
        directory.users["target"]["afterglow_local_password"] = False
    directory.response_status = directory.guarded_status = status
    response = await post(directory)
    assert response.status_code == status
    assert response.json()["detail"] == {
        "code": "admin_password_reset_native_rejected",
        "changed": False,
        "delivered": False,
    }
    assert len(directory.updates) == 1 and not directory.writes and not directory.mail and directory.sessions
    assert directory.audits[-1]["extra"]["outcome"] == "rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["timeout", "redirect", "server_error", "wrong_id", "wrong_home", "wrong_email", "missing_marker"]
)
async def test_unknown_outcome_revokes_without_mail_or_replay(directory, case, caplog):
    if case == "timeout":
        directory.native_unknown = True
    elif case == "redirect":
        directory.response_status = 307
    elif case == "server_error":
        directory.response_status = 500
    else:
        user = {**directory.users["target"], "afterglow_local_password": True}
        if case == "missing_marker":
            user.pop("afterglow_local_password")
        else:
            user[{"wrong_id": "id", "wrong_home": "domain_id", "wrong_email": "email"}[case]] = "wrong"
        directory.response_override = {"user": user}
    response = await post(directory)
    assert response.status_code == 502 and response.json()["detail"]["code"] == "admin_password_reset_outcome_unknown"
    assert "changed" not in response.json()["detail"]
    assert len(directory.updates) == 1 and not directory.mail and not directory.sessions
    password = directory.updates[0][2]["json"]["user"]["password"]
    assert password not in response.text + caplog.text + json.dumps(directory.audits)
    assert (await post(directory)).status_code == 429
    assert len(directory.updates) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("case", ["mail_exception", "recipient_refused", "sessions", "cache", "mail_and_sessions"])
async def test_partial_effects_are_truthful_and_secret_free(directory, case, caplog, external):
    if external:
        directory.users["target"]["federated"] = [{"idp_id": "gitlab"}]
    directory.mail_failed = case in {"mail_exception", "mail_and_sessions"}
    directory.mail_refused = case == "recipient_refused"
    directory.revoke_failed = case in {"sessions", "mail_and_sessions"}
    directory.invalidation_failed = case == "cache"
    response = await post(directory)
    detail = response.json()["detail"]
    cleanup_failure = case in {"sessions", "cache", "mail_and_sessions"}
    assert response.status_code == 503 and detail["changed"] is True
    assert detail["code"] == "admin_password_reset_" + ("sessions_failed" if cleanup_failure else "email_failed")
    assert detail["delivered"] is (case in {"sessions", "cache"})
    assert len(directory.updates) == len(directory.mail) == 1 and not directory.sessions
    assert len(directory.writes) == 1
    assert "invalidate" in directory.events
    password = directory.updates[0][2]["json"]["user"]["password"]
    assert password not in response.text + caplog.text + json.dumps(directory.audits)


@pytest.mark.asyncio
async def test_same_subject_cooldown_shared_between_administrators(directory):
    assert (await post(directory)).status_code == 200
    directory.actor["user_id"] = directory.conn._afterglow_user_id = "second-admin"
    # Invoke the service with another already freshly proven administrator.
    actor = {**directory.actor, "_live_system_admin": True}
    async with directory.factory() as session:
        with pytest.raises(HTTPException) as result:
            await reset.reset_password_email("target", actor, directory.conn, session)
    assert result.value.status_code == 429 and len(directory.updates) == 1


@pytest.mark.asyncio
async def test_http_rate_limit_is_private_and_three_per_minute(directory):
    endpoint.limiter.enabled = True
    app = make_app(directory)
    results = []
    for _ in range(4):
        directory.cooldown.clear()
        results.append(await post(directory, app=app))
    assert [item.status_code for item in results] == [200, 200, 200, 429]
    assert_private(results[-1])
    assert len(directory.updates) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("external", [False, True])
async def test_cancelled_http_owner_drains_native_email_and_session_cleanup(directory, external):
    if external:
        directory.users["target"]["afterglow_local_password"] = False
    directory.native_gate = True
    actor = {**directory.actor, "_live_system_admin": True}
    session = directory.factory()
    task = asyncio.create_task(reset.reset_password_email("target", actor, directory.conn, session))
    try:
        assert await asyncio.to_thread(directory.entered.wait, 3)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and directory.lock.locked()
    finally:
        directory.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(directory.updates) == len(directory.mail) == 1
    assert not directory.sessions and not directory.lock.locked()
    assert directory.audits[-1]["extra"]["outcome"] == "changed"
    await session.close()


async def seed_proofs(directory):
    async with directory.factory() as session:
        for index, (uid, kind, status) in enumerate(
            [
                ("target", "password", "pending"),
                ("target", "email_change", "pending"),
                ("target", "password_create", "delivery_pending"),
                ("target", "username", "pending"),
                ("other", "password", "pending"),
            ]
        ):
            session.add(
                AccountRecovery(
                    token_hash=f"{index:064x}",
                    user_id=uid,
                    kind=kind,
                    status=status,
                    identity_domain_id="home",
                    original_email="alice@example.test",
                    email="alice@example.test",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
        await session.commit()
    directory.commits = 0


@pytest.mark.asyncio
@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("unknown", [False, True])
async def test_old_password_and_email_proofs_consumed_before_reset_even_if_unknown(directory, unknown, external):
    if external:
        directory.users["target"]["afterglow_local_password"] = False
    await seed_proofs(directory)
    directory.native_unknown = unknown
    response = await post(directory)
    assert response.status_code == (502 if unknown else 200)
    async with directory.factory() as session:
        proofs = (await session.execute(select(AccountRecovery).order_by(AccountRecovery.token_hash))).scalars().all()
        assert [row.status for row in proofs] == ["superseded", "superseded", "superseded", "pending", "pending"]
        assert all(row.consumed_at is not None for row in proofs[:3])
        audit = (await session.execute(select(ActivityLog))).scalar_one()
        assert audit.extra["outcome"] == ("outcome_unknown" if unknown else "changed")
        assert audit.resource_id == "target" and audit.user_id == "actor"
    assert directory.events.index("commit") < directory.events.index("native")


@pytest.mark.asyncio
@pytest.mark.parametrize("external", [False, True])
async def test_durable_dispatch_fence_failure_prevents_mutation(directory, external):
    if external:
        directory.users["target"]["afterglow_local_password"] = False
    await seed_proofs(directory)
    directory.fail_commits = {1}
    response = await post(directory)
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "admin_password_reset_audit_failed",
        "changed": False,
        "delivered": False,
    }
    assert not directory.updates and not directory.mail and directory.sessions
    async with directory.factory() as session:
        proof = await session.get(AccountRecovery, f"{0:064x}")
        assert proof.status == "pending" and proof.consumed_at is None
        assert not (await session.execute(select(ActivityLog))).scalars().all()


@pytest.mark.asyncio
@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("outcome", ["changed", "unknown", "rejected"])
async def test_final_audit_failure_preserves_truthful_effects_and_dispatch_fence(directory, outcome, external):
    if external:
        directory.users["target"]["afterglow_local_password"] = False
    await seed_proofs(directory)
    directory.fail_commits = {2}
    directory.native_unknown = outcome == "unknown"
    directory.response_status = 403 if outcome == "rejected" else 200
    directory.guarded_status = 409 if outcome == "rejected" else 204
    response = await post(directory)
    detail = response.json()["detail"]
    assert response.status_code == (502 if outcome == "unknown" else 503)
    if outcome == "unknown":
        assert detail["code"] == "admin_password_reset_outcome_unknown" and detail["audit_recorded"] is False
        assert "changed" not in detail
    else:
        assert detail["code"] == "admin_password_reset_audit_failed"
        assert detail["changed"] is (outcome == "changed")
        assert detail["delivered"] is (outcome == "changed")
    assert len(directory.updates) == 1
    assert bool(directory.sessions) is (outcome == "rejected")
    async with directory.factory() as session:
        proof = await session.get(AccountRecovery, f"{0:064x}")
        assert proof.status == "superseded"
        audit = (await session.execute(select(ActivityLog))).scalar_one()
        assert audit.status == "started" and audit.extra == {"outcome": "dispatching"}


async def assert_external_predispatch_refusal(directory, response, code="external_account"):
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "admin_password_reset_" + code}
    assert_private(response)
    assert not directory.updates and not directory.writes and not directory.mail
    assert directory.sessions == ["target-session"] and not directory.cooldown
    assert "revoke" not in directory.events and "invalidate" not in directory.events
    async with directory.factory() as session:
        proofs = (await session.execute(select(AccountRecovery))).scalars().all()
        assert all(row.status in {"pending", "delivery_pending"} and row.consumed_at is None for row in proofs)
        assert not (await session.execute(select(ActivityLog))).scalars().all()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    ["unsupported", "old_revision", "capability_missing", "capability_error", "missing_service_credential"],
)
async def test_external_unavailable_native_refuses_before_cooldown_and_fence(directory, case):
    directory.users["target"]["federated"] = [{"idp_id": "gitlab"}]
    await seed_proofs(directory)
    if case == "unsupported":
        directory.capability["supported"] = False
    elif case == "old_revision":
        directory.capability["revision"] = "first-password-galera-v1"
    elif case == "capability_missing":
        directory.capability_status = 404
    elif case == "capability_error":
        directory.capability_status = 503
    else:
        directory.ks.session.get_token = lambda: ""
    response = await post(directory)
    await assert_external_predispatch_refusal(directory, response)
    assert "smtp-preflight" not in directory.events


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["initial", "revalidation"])
@pytest.mark.parametrize(
    "snapshot",
    [
        {"id": "foreign-user"},
        {"domain_id": "foreign-home"},
        {"email": "foreign@example.test"},
        {"password_state": "unknown"},
        {"password_state": None},
        {"identity_revision": None},
        {"identity_revision": "07"},
        {"identity_revision": "18446744073709551616"},
    ],
)
async def test_external_invalid_or_foreign_snapshot_has_no_effects(directory, snapshot, stage):
    directory.users["target"]["afterglow_external_identities"] = [{"provider": "gitlab", "subject": "target"}]
    directory.identity_snapshots = ([{}] if stage == "revalidation" else []) + [snapshot]
    await seed_proofs(directory)
    response = await post(directory)
    await assert_external_predispatch_refusal(directory, response)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["home", "email", "email_aba", "state", "classification"])
async def test_external_identity_changes_between_snapshots_refuse_before_fence(directory, case):
    user = directory.users["target"]
    user["federated"] = [{"idp_id": "gitlab"}]
    await seed_proofs(directory)

    def change_identity():
        if case == "home":
            user["domain_id"] = "foreign-home"
        elif case == "email":
            user["email"] = "new@example.test"
        elif case == "email_aba":
            original = user["email"]
            user["email"] = "temporary@example.test"
            directory.identity_revision = "8"
            user["email"] = original
            directory.identity_revision = "9"
        elif case == "state":
            directory.password_state = "absent"
        else:
            user.pop("federated")

    directory.after_smtp_preflight = change_identity
    response = await post(directory)
    await assert_external_predispatch_refusal(directory, response, "identity_changed")


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["home", "email", "revision_aba", "password_created"])
async def test_external_native_cas_refuses_post_snapshot_races_without_revocation(directory, case):
    user = directory.users["target"]
    user["federated"] = [{"idp_id": "gitlab"}]
    directory.password_state = "absent"
    await seed_proofs(directory)

    def race():
        if case == "home":
            user["domain_id"] = "foreign-home"
        elif case == "email":
            user["email"] = "new@example.test"
        elif case == "revision_aba":
            original = user["email"]
            user["email"] = "temporary@example.test"
            directory.identity_revision = "8"
            user["email"] = original
            directory.identity_revision = "9"
        else:
            directory.password_state = "existing"

    directory.before_write = race
    response = await post(directory)
    assert response.status_code == 412 and response.json()["detail"] == {
        "code": "admin_password_reset_native_rejected",
        "changed": False,
        "delivered": False,
    }
    assert len(directory.updates) == 1 and not directory.writes and not directory.mail
    assert directory.sessions == ["target-session"]
    assert "revoke" not in directory.events and "invalidate" not in directory.events
    assert user["federated"] == [{"idp_id": "gitlab"}] and "password" not in user
    async with directory.factory() as session:
        proof = await session.get(AccountRecovery, f"{0:064x}")
        assert proof.status == "superseded"
        audit = (await session.execute(select(ActivityLog))).scalar_one()
        assert audit.extra["outcome"] == "rejected" and audit.extra["changed"] is False
    assert (await post(directory)).status_code == 429
    assert len(directory.updates) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("password_state", ["absent", "existing"])
@pytest.mark.parametrize(
    "case",
    [
        "timeout_after_commit",
        "redirect",
        "server_error",
        "unexpected_success",
        "bad_request",
        "unauthorized",
        "forbidden",
        "not_found",
    ],
)
async def test_external_unknown_outcome_never_mails_or_replays(directory, password_state, case, caplog):
    directory.users["target"]["federated"] = [{"idp_id": "gitlab"}]
    directory.password_state = password_state
    await seed_proofs(directory)
    if case == "timeout_after_commit":
        directory.native_unknown = True
    else:
        directory.guarded_status = {
            "redirect": 307,
            "server_error": 500,
            "unexpected_success": 200,
            "bad_request": 400,
            "unauthorized": 401,
            "forbidden": 403,
            "not_found": 404,
        }[case]
    response = await post(directory)
    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "admin_password_reset_outcome_unknown",
        "delivered": False,
        "sessions_revoked": True,
        "audit_recorded": True,
    }
    assert len(directory.updates) == 1 and not directory.mail and not directory.sessions
    assert len(directory.writes) == (1 if case == "timeout_after_commit" else 0)
    if case == "timeout_after_commit":
        assert directory.users["target"]["password"] == directory.writes[0]["password"]
    async with directory.factory() as session:
        proof = await session.get(AccountRecovery, f"{0:064x}")
        assert proof.status == "superseded"
        audit = (await session.execute(select(ActivityLog))).scalar_one()
        assert audit.extra["outcome"] == "outcome_unknown" and audit.extra["changed"] is None
    password = directory.updates[0][2]["json"]["user"]["password"]
    assert password not in response.text + caplog.text + json.dumps(directory.audits)
    assert (await post(directory)).status_code == 429
    assert len(directory.updates) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("password_state", ["absent", "existing"])
@pytest.mark.parametrize("status", ["dispatching", "outcome_unknown", "sessions_failed"])
async def test_external_unsettled_creation_requires_reconciliation_before_any_effect(directory, password_state, status):
    directory.users["target"]["federated"] = [{"idp_id": "gitlab"}]
    directory.password_state = password_state
    await seed_proofs(directory)
    async with directory.factory() as session:
        proof = await session.get(AccountRecovery, f"{2:064x}")
        proof.status = status
        proof.consumed_at = datetime.now(UTC)
        await session.commit()
    response = await post(directory)
    assert response.status_code == 409 and response.json()["detail"] == {
        "code": "admin_password_reset_external_account"
    }
    assert_private(response)
    assert not directory.updates and not directory.writes and not directory.mail and not directory.cooldown
    assert directory.sessions == ["target-session"]
    assert "smtp-preflight" not in directory.events and "revoke" not in directory.events
    assert "invalidate" not in directory.events
    async with directory.factory() as session:
        proofs = (await session.execute(select(AccountRecovery).order_by(AccountRecovery.token_hash))).scalars().all()
        assert [row.status for row in proofs] == ["pending", "pending", status, "pending", "pending"]
        assert proofs[2].consumed_at is not None
        assert proofs[0].consumed_at is proofs[1].consumed_at is None
        assert not (await session.execute(select(ActivityLog))).scalars().all()
