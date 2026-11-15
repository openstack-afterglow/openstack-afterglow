"""Machine identity lifecycle, secret boundaries and target-token semantics."""

import json
import string
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from keystoneauth1.exceptions.http import Unauthorized

from app.services import backup_system_account as service
from app.services import work_dispatcher


class Identity:
    def __init__(self):
        self.user = None
        self.writes = []
        self.password = None
        self.sequence = 0
        self.reject_password = False

    def domains(self, **filters):
        return [SimpleNamespace(id="service-home", name=service.get_settings().os_user_domain_name)]

    def users(self, **filters):
        return [self.user] if self.user else []

    def create_user(self, **values):
        self.sequence += 1
        self.writes.append("create")
        self.password = values.pop("password")
        self.user = SimpleNamespace(id=f"machine-{self.sequence}", **values)
        return self.user

    def update_user(self, user_id, **values):
        assert self.user.id == user_id
        if "password" in values:
            self.writes.append("password")
            if self.reject_password:
                raise ValueError("provider payload must stay private")
            self.password = values.pop("password")
        else:
            self.writes.append("options")
        for key, value in values.items():
            setattr(self.user, key, value)
        return self.user

    def get_user(self, user_id):
        assert self.user.id == user_id
        return self.user


@pytest.fixture
async def account(monkeypatch, _fake_redis_global):
    from app.services import backup_account_reconciler
    from app.services.cache import _get_redis

    redis = await _get_redis()
    monkeypatch.setattr(service, "_cached_record", None)
    monkeypatch.setattr(service, "_cached_domain", None)
    monkeypatch.setattr(service, "_get_redis", _get_redis)
    identity = Identity()
    admin = SimpleNamespace(identity=identity)
    monkeypatch.setattr(service, "checkpoint", AsyncMock())

    async def direct(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(service, "run_sync", direct)
    monkeypatch.setattr(backup_account_reconciler, "run_write", direct)
    monkeypatch.setattr(backup_account_reconciler, "checkpoint_leader", AsyncMock())

    def unscoped(user_id, password):
        if not identity.user or user_id != identity.user.id or password != identity.password:
            raise Unauthorized("private native auth text")

    monkeypatch.setattr(service, "_unscoped_auth", unscoped)
    await redis.delete(service.RECORD_KEY, service.RESET_KEY)
    try:
        yield redis, admin, identity
    finally:
        await redis.delete(service.RECORD_KEY, service.RESET_KEY)


@contextmanager
def leader(value=True):
    lease = SimpleNamespace(dispatcher=SimpleNamespace(is_leader=AsyncMock(return_value=value)))
    token = work_dispatcher._current_lease.set(lease)
    try:
        yield
    finally:
        work_dispatcher._current_lease.reset(token)


@pytest.mark.asyncio
async def test_create_stores_encrypted_verified_identity_and_options(account):
    redis, admin, identity = account
    with leader():
        result = await service.ensure_account(redis, admin)
    assert identity.writes == ["create"]
    assert result["id"] == "machine-1"
    assert "password" not in result
    assert identity.user.enabled is True
    assert identity.user.options == {**service.ACCOUNT_OPTIONS, "multi_factor_auth_rules": []}
    raw = await redis.get(service.RECORD_KEY)
    raw = raw.decode() if isinstance(raw, bytes) else raw
    assert identity.password not in raw
    assert raw.startswith("backup-account-v1:")
    assert service._decrypt_record(raw)["id"] == "machine-1"
    assert service.cached_managed_user_id() == "machine-1"
    assert len(identity.password) >= 32
    assert all(
        any(c in group for c in identity.password)
        for group in (string.ascii_uppercase, string.ascii_lowercase, string.digits, "!@#$%")
    )


@pytest.mark.asyncio
async def test_deleted_account_recreated_with_new_canonical_id(account):
    redis, admin, identity = account
    with leader():
        await service.ensure_account(redis, admin)
        identity.user = None
        await redis.delete(service.RESET_KEY)
        result = await service.ensure_account(redis, admin)
    assert result["id"] == "machine-2"
    assert service.cached_managed_user_id() == "machine-2"
    assert identity.writes == ["create", "create"]


@pytest.mark.asyncio
async def test_disabled_and_option_drift_repair_without_password_reset(account):
    redis, admin, identity = account
    with leader():
        await service.ensure_account(redis, admin)
        identity.user.enabled = False
        identity.user.options = {"ignore_password_expiry": False, "multi_factor_auth_rules": [["password", "totp"]]}
        await service.ensure_account(redis, admin)
        await service.ensure_account(redis, admin)
    assert identity.user.enabled is True
    assert identity.user.options["ignore_password_expiry"] is True
    assert identity.user.options["multi_factor_auth_rules"] == []
    assert identity.writes == ["create", "options"]


@pytest.mark.asyncio
async def test_failed_unscoped_proof_resets_once_then_backs_off(account):
    redis, admin, identity = account
    with leader():
        await service.ensure_account(redis, admin)
        await redis.delete(service.RESET_KEY)
        identity.password = "changed-directly-in-native"
        await service.ensure_account(redis, admin)
        identity.password = "changed-directly-again"
        with pytest.raises(RuntimeError, match="password_backoff"):
            await service.ensure_account(redis, admin)
    assert identity.writes.count("password") == 1


@pytest.mark.asyncio
async def test_nonleader_cannot_create_or_reset(account):
    redis, admin, identity = account
    for elected in (False,):
        with leader(elected), pytest.raises(RuntimeError, match="leader_required"):
            await service.ensure_account(redis, admin)
    with pytest.raises(RuntimeError, match="leader_required"):
        await service.ensure_account(redis, admin)
    assert identity.writes == []
    assert await redis.get(service.RESET_KEY) is None
    with leader():
        await service.ensure_account(redis, admin)
    identity.password = "native-password-drift"
    await redis.delete(service.RESET_KEY)
    with leader(False), pytest.raises(RuntimeError, match="leader_required"):
        await service.ensure_account(redis, admin)
    assert identity.writes == ["create"]
    assert await redis.get(service.RESET_KEY) is None


@pytest.mark.asyncio
async def test_password_native_rejection_keeps_previous_ciphertext(account):
    redis, admin, identity = account
    with leader():
        await service.ensure_account(redis, admin)
        old = await redis.get(service.RECORD_KEY)
        await redis.delete(service.RESET_KEY)
        identity.password = "native-drift"
        identity.reject_password = True
        with pytest.raises(RuntimeError, match="^backup_system_account_password_rejected$"):
            await service.ensure_account(redis, admin)
    assert await redis.get(service.RECORD_KEY) == old


@pytest.mark.asyncio
async def test_password_not_persisted_before_fresh_unscoped_verification(account, monkeypatch):
    redis, admin, identity = account
    with leader():
        await service.ensure_account(redis, admin)
        old = await redis.get(service.RECORD_KEY)
        await redis.delete(service.RESET_KEY)
        monkeypatch.setattr(service, "_unscoped_auth", lambda *args: (_ for _ in ()).throw(Unauthorized()))
        with pytest.raises(RuntimeError, match="password_unverified"):
            await service.ensure_account(redis, admin)
    assert identity.writes.count("password") == 1
    assert await redis.get(service.RECORD_KEY) == old


@pytest.mark.asyncio
async def test_crash_window_lost_redis_secret_recovers_after_interval(account):
    redis, admin, identity = account
    with leader():
        await service.ensure_account(redis, admin)
        await redis.delete(service.RECORD_KEY)
        with pytest.raises(RuntimeError, match="password_backoff"):
            await service.ensure_account(redis, admin)
        await redis.delete(service.RESET_KEY)
        await service.ensure_account(redis, admin)
    assert (await service.load_account(redis))["id"] == "machine-1"
    assert identity.writes == ["create", "password"]


@pytest.mark.asyncio
async def test_reserved_name_collision_not_adopted(account):
    redis, admin, identity = account
    identity.user = SimpleNamespace(id="unmanaged", name=service.ACCOUNT_NAME, domain_id="service-home", enabled=True)
    with leader(), pytest.raises(RuntimeError, match="identity_conflict"):
        await service.ensure_account(redis, admin)
    assert identity.writes == []


def test_ciphertext_tampering_and_cloud_binding_fail_closed(monkeypatch):
    record = {
        "id": "managed",
        "name": service.ACCOUNT_NAME,
        "domain_id": "home",
        "domain_name": service.get_settings().os_user_domain_name,
        "password": "synthetic-test-only",
    }
    encrypted = service._encrypt_record(record)
    with pytest.raises(RuntimeError, match="identity_invalid"):
        service._decrypt_record(encrypted[:-4] + "AAAA")
    original = service._aad()
    monkeypatch.setattr(service, "_aad", lambda: original + b"other-cloud")
    with pytest.raises(RuntimeError, match="identity_invalid"):
        service._decrypt_record(encrypted)


def test_target_scoped_auth_uses_only_machine_identity_and_scoped_401_never_resets(monkeypatch):
    calls = []
    closed = []
    access = SimpleNamespace(user_id="machine", project_id="tenant", project_scoped=True, system_scoped=False)
    conn = SimpleNamespace(
        session=SimpleNamespace(auth=SimpleNamespace(get_access=lambda _: access)), close=lambda: closed.append(True)
    )
    monkeypatch.setattr(service.native_transport, "connect", lambda **kwargs: calls.append(kwargs) or conn)
    result = service.connection_for_project("tenant", "synthetic-test-only", "machine")
    assert result is conn
    assert calls[0]["user_id"] == "machine"
    assert calls[0]["project_id"] == "tenant"
    assert "username" not in calls[0] and "project_name" not in calls[0]
    monkeypatch.setattr(conn.session.auth, "get_access", lambda _: (_ for _ in ()).throw(Unauthorized()))
    with pytest.raises(Unauthorized):
        service.connection_for_project("tenant", "synthetic-test-only", "machine")
    assert closed == [True]
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_policy_readiness_requests_only_and_never_resets(account, monkeypatch):
    redis, admin, identity = account
    settings = SimpleNamespace(backup_system_account_enabled=True)
    original = service.get_settings()
    monkeypatch.setattr(service, "get_settings", lambda: original)
    with leader():
        await service.ensure_account(redis, admin)
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "load_account", AsyncMock(return_value={"id": "machine-1"}))
    with pytest.raises(Unauthorized):
        await service.ensure_project("tenant", require_ready=True)
    assert identity.writes == ["create"]
    await redis.set(f"{service.PREFIX}:ready:tenant", json.dumps({"user_id": "machine-1"}), ex=120)
    await service.ensure_project("tenant", require_ready=True)
    await redis.delete(f"{service.PREFIX}:requests:tenant", f"{service.PREFIX}:ready:tenant")


def test_unscoped_proof_has_no_project_and_closes_owned_session(monkeypatch):
    from keystoneauth1.identity import v3

    calls = []
    closed = []
    access = SimpleNamespace(user_id="machine", project_scoped=False, system_scoped=False)
    auth = SimpleNamespace(get_access=lambda session: access)
    monkeypatch.setattr(v3, "Password", lambda **kwargs: calls.append(kwargs) or auth)
    session = SimpleNamespace(session=SimpleNamespace(close=lambda: closed.append(True)))
    monkeypatch.setattr(service.native_transport, "create_session", lambda **kwargs: session)
    service._unscoped_auth("machine", "synthetic-test-only")
    assert calls[0]["unscoped"] is True
    assert "project_id" not in calls[0] and "project_name" not in calls[0]
    assert closed == [True]


def test_installed_sdk_serializes_machine_options_and_native_provenance():
    user = service._ManagedUser.new(
        name=service.ACCOUNT_NAME,
        domain_id="home",
        password="synthetic-test-only",
        is_enabled=True,
        options={**service.ACCOUNT_OPTIONS, "multi_factor_auth_rules": []},
        afterglow_system_account="auto_backup:v1",
    )
    request = user._prepare_request(requires_id=False, prepend_key=True)
    body = request.body["user"]
    assert body["options"]["ignore_password_expiry"] is True
    assert body["afterglow_system_account"] == "auto_backup:v1"
    assert body["enabled"] is True
    assert service._field(user, "enabled") is True


@pytest.mark.asyncio
async def test_missing_encryption_key_prevents_native_creation(account, monkeypatch):
    redis, admin, identity = account

    def unavailable_key(domain):
        raise RuntimeError("encryption key is not configured")

    monkeypatch.setattr(service, "derive_encryption_subkey", unavailable_key)
    with leader(), pytest.raises(RuntimeError, match="encryption key"):
        await service.ensure_account(redis, admin)
    assert identity.writes == []
    assert await redis.get(service.RESET_KEY) is None


def test_fresh_native_user_guard_reuses_verified_metadata_without_operator_lookup(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(service, "_cached_record", None)
    monkeypatch.setattr(service, "_cached_domain", ("service-home", service.get_settings().os_user_domain_name))

    def unexpected_lookup(*args, **kwargs):
        raise AssertionError("Fresh native user metadata must not open another operator client")

    monkeypatch.setattr(service, "_identity_client", unexpected_lookup)
    service.assert_not_system_account_sync("human", user={"id": "human", "name": "ordinary", "domain_id": "other"})
    with pytest.raises(HTTPException) as denied:
        service.assert_not_system_account_sync(
            "machine", user={"id": "machine", "name": service.ACCOUNT_NAME, "domain_id": "service-home"}
        )
    assert denied.value.status_code == 403
    assert denied.value.detail == "system_account_protected"
    service.assert_not_system_account_sync(
        "foreign", user={"id": "foreign", "name": service.ACCOUNT_NAME, "domain_id": "foreign-home"}
    )


@pytest.mark.parametrize(
    "user",
    [{"id": "other", "name": "ordinary"}, {"id": "human"}, {"id": "human", "name": None}],
)
def test_fresh_user_metadata_must_prove_exact_identity_and_name(monkeypatch, user):
    from fastapi import HTTPException

    monkeypatch.setattr(service, "_cached_record", None)
    with pytest.raises(HTTPException) as denied:
        service.assert_not_system_account_sync("human", user=user)
    assert denied.value.status_code == 503
