"""Dedicated, noninteractive Cinder recovery-point identity.

Only the leased reconciler creates/repairs this principal. Redis stores an
AEAD-bound identity record, never a plaintext password. Scoped authentication
failures never rotate credentials: only a failed unscoped password proof does.
"""

from __future__ import annotations

import base64
import binascii
import json
import secrets
import string
from collections.abc import Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from keystoneauth1.exceptions.http import Unauthorized
from openstack import resource
from openstack.identity.v3._proxy import Proxy as IdentityProxy
from openstack.identity.v3.user import User

from app.config import get_settings
from app.services import native_transport
from app.services.cache import _get_redis
from app.services.k3s_crypto import derive_encryption_subkey
from app.services.work_dispatcher import checkpoint, checkpoint_sync, run_sync

ACCOUNT_NAME = "afterglow-auto-backup"
ACCOUNT_DESCRIPTION = "Afterglow system account for automatic volume backups and snapshots"
ACCOUNT_OPTIONS = {
    "ignore_lockout_failure_attempts": True,
    "ignore_password_expiry": True,
    "ignore_change_password_upon_first_use": True,
}
PREFIX = "afterglow:backup_account"
RECORD_KEY = f"{PREFIX}:identity"
RESET_KEY = f"{PREFIX}:password-reset"
RESET_INTERVAL = 900
_RECORD_PREFIX = "backup-account-v1:"
_RECORD_DOMAIN = b"backup_system_account"
_cached_record: dict | None = None
_cached_domain: tuple[str, str] | None = None


class AccountUnavailable(RuntimeError):
    """Only fixed, secret-free machine-account status codes belong here."""


class _ManagedUser(User):
    """The pinned SDK User drops options/custom provenance unless declared."""

    options = resource.Body("options", type=dict)
    afterglow_system_account = resource.Body("afterglow_system_account")


def _field(value, name, default=None):
    if name == "enabled" and isinstance(value, User):
        name = "is_enabled"
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def _aad() -> bytes:
    settings = get_settings()
    return json.dumps(
        ["afterglow-backup-account-v1", settings.os_auth_url, settings.os_user_domain_name, ACCOUNT_NAME],
        separators=(",", ":"),
    ).encode()


def _encrypt_record(record: dict) -> str:
    nonce = secrets.token_bytes(12)
    payload = json.dumps(record, separators=(",", ":")).encode()
    encrypted = AESGCM(derive_encryption_subkey(_RECORD_DOMAIN)).encrypt(nonce, payload, _aad())
    return _RECORD_PREFIX + base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def _decrypt_record(raw: str) -> dict:
    try:
        if not raw.startswith(_RECORD_PREFIX):
            raise ValueError
        payload = base64.b64decode(raw[len(_RECORD_PREFIX) :], altchars=b"-_", validate=True)
        record = json.loads(
            AESGCM(derive_encryption_subkey(_RECORD_DOMAIN)).decrypt(payload[:12], payload[12:], _aad())
        )
        if (
            not isinstance(record, dict)
            or record.get("name") != ACCOUNT_NAME
            or record.get("domain_name") != get_settings().os_user_domain_name
            or not all(isinstance(record.get(key), str) and record[key] for key in ("id", "domain_id", "password"))
        ):
            raise ValueError
        return record
    except (ValueError, TypeError, UnicodeError, binascii.Error, InvalidTag) as exc:
        raise AccountUnavailable("backup_system_account_identity_invalid") from exc


def _public_record(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "password"}


async def load_account(redis=None) -> dict | None:
    """Refresh this process's trusted identity cache; never expose the secret."""
    global _cached_record, _cached_domain
    redis = redis if redis is not None else await _get_redis()
    raw = await redis.get(RECORD_KEY)
    if not raw:
        _cached_record = None
        return None
    record = _decrypt_record(raw.decode() if isinstance(raw, bytes) else raw)
    _cached_record = record
    _cached_domain = (record["domain_id"], record["domain_name"])
    return _public_record(record)


async def managed_user_id() -> str | None:
    record = await load_account()
    return record["id"] if record else None


def cached_managed_user_id() -> str | None:
    return _cached_record["id"] if _cached_record else None


def is_managed_member_source(source, project_id, managed_user_id, member_role_id=None) -> bool:
    """Exempt only an exact, direct project member source from Personal checks."""
    return bool(
        managed_user_id
        and member_role_id
        and source.get("user_id") == managed_user_id
        and source.get("role_id") == member_role_id
        and source.get("kind") == "project"
        and source.get("scope_id") == project_id
        and not source.get("group_id")
        and source.get("inherited") is False
        and source.get("users", {managed_user_id}) == {managed_user_id}
    )


def system_account_marker(user) -> dict | None:
    uid = _field(user, "id") or _field(user, "user_id")
    if uid and uid == cached_managed_user_id():
        return {"kind": "auto_backup"}
    if _field(user, "name", _field(user, "username")) != ACCOUNT_NAME:
        return None
    domain_id = _field(user, "domain_id")
    domain_name = _field(user, "domain_name")
    domain = _field(user, "domain")
    domain_id = domain_id or _field(domain, "id")
    domain_name = domain_name or _field(domain, "name")
    if domain_name == get_settings().os_user_domain_name or (_cached_domain and domain_id == _cached_domain[0]):
        return {"kind": "auto_backup"}
    return None


def _identity_client(conn=None):
    if conn is not None:
        return conn.identity if hasattr(conn, "identity") else conn
    from app.services.keystone import _get_admin_ks_client

    return _get_admin_ks_client()


def _resolve_domain(identity) -> str:
    global _cached_domain
    name = get_settings().os_user_domain_name
    if _cached_domain and _cached_domain[1] == name:
        return _cached_domain[0]
    rows = (
        list(identity.domains(name=name))
        if callable(getattr(identity, "domains", None))
        else list(identity.domains.list(name=name))
    )
    rows = [row for row in rows if _field(row, "name") == name]
    if len(rows) != 1 or not _field(rows[0], "id"):
        raise HTTPException(503, "system_account_identity_unavailable")
    _cached_domain = (_field(rows[0], "id"), name)
    return _cached_domain[0]


def assert_not_system_account_sync(user_id, *, conn=None, user=None) -> None:
    """Reject reserved identity even before initial provisioning or after deletion."""
    if user_id and user_id == cached_managed_user_id():
        raise HTTPException(403, "system_account_protected")
    if not user_id:
        return
    if user is not None:
        if _field(user, "id") != user_id:
            raise HTTPException(503, "system_account_identity_unavailable")
        identity = None
    else:
        identity = _identity_client(conn)
        getter = getattr(identity, "get_user", None)
        try:
            user = getter(user_id) if getter else identity.users.get(user_id)
        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
            if status in (401, 403):
                raise HTTPException(403, "identity_native_denied") from None
            if status == 404:
                return
            raise HTTPException(503, "system_account_identity_unavailable") from None
    name = _field(user, "name")
    if not isinstance(name, str) or not name:
        raise HTTPException(503, "system_account_identity_unavailable")
    if name != ACCOUNT_NAME:
        return
    home = _field(user, "domain_id")
    if not isinstance(home, str) or not home:
        raise HTTPException(503, "system_account_identity_unavailable")
    if _cached_domain and _cached_domain[1] == get_settings().os_user_domain_name:
        reserved_home = _cached_domain[0]
    else:
        reserved_home = _resolve_domain(identity if identity is not None else _identity_client(conn))
    if home == reserved_home:
        raise HTTPException(403, "system_account_protected")


async def assert_not_system_account(user_id, *, conn=None, user=None) -> None:
    await run_sync(assert_not_system_account_sync, user_id, conn=conn, user=user)


def assert_no_system_accounts_sync(user_ids, *, conn=None) -> None:
    targets = set(user_ids)
    if not targets:
        return
    if cached_managed_user_id() in targets:
        raise HTTPException(403, "system_account_protected")
    identity = _identity_client(conn)
    domain_id = _resolve_domain(identity)
    try:
        manager = identity.users
        rows = (
            list(manager(domain_id=domain_id, name=ACCOUNT_NAME))
            if callable(manager)
            else list(manager.list(domain=domain_id, name=ACCOUNT_NAME))
        )
    except Exception as exc:
        status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
        if status in (401, 403):
            raise HTTPException(403, "identity_native_denied") from None
        raise HTTPException(503, "system_account_identity_unavailable") from None
    for user in rows:
        if (
            _field(user, "id") in targets
            and _field(user, "name") == ACCOUNT_NAME
            and _field(user, "domain_id") == domain_id
        ):
            raise HTTPException(403, "system_account_protected")


async def assert_no_system_accounts(user_ids, *, conn=None) -> None:
    await run_sync(assert_no_system_accounts_sync, user_ids, conn=conn)


def assert_login_allowed_sync(*, user_id=None, username=None, domain_id=None) -> None:
    if user_id and user_id == cached_managed_user_id():
        raise HTTPException(403, "system_account_protected")
    if username is not None and username != ACCOUNT_NAME:
        return
    if username == ACCOUNT_NAME and domain_id is not None:
        if domain_id != _resolve_domain(_identity_client()):
            return
        raise HTTPException(403, "system_account_protected")
    if user_id:
        assert_not_system_account_sync(user_id)


async def assert_login_allowed(*, user_id=None, username=None, domain_id=None) -> None:
    await run_sync(assert_login_allowed_sync, user_id=user_id, username=username, domain_id=domain_id)


def _password() -> str:
    # Guarantee mixed classes without logging or returning this value to an API.
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*_-+="
    value = [
        secrets.choice(group) for group in (string.ascii_uppercase, string.ascii_lowercase, string.digits, "!@#$%")
    ]
    value.extend(secrets.choice(alphabet) for _ in range(60))
    secrets.SystemRandom().shuffle(value)
    return "".join(value)


def _unscoped_auth(user_id: str, password: str) -> None:
    from keystoneauth1.identity import v3

    settings = get_settings()
    auth = v3.Password(auth_url=settings.os_auth_url, user_id=user_id, password=password, unscoped=True)
    session = native_transport.create_session(auth=auth, timeout=15, verify=settings.ssl_verify)
    try:
        access = auth.get_access(session)
        if access.user_id != user_id or access.project_scoped or access.system_scoped:
            raise AccountUnavailable("backup_system_account_unscoped_identity_invalid")
    finally:
        session.session.close()


def _user_call(admin, action, *args, **kwargs):
    identity = admin.identity
    if isinstance(identity, IdentityProxy):
        method = {"create": "_create", "update": "_update", "get": "_get", "list": "_list"}[action]
        return getattr(identity, method)(_ManagedUser, *args, **kwargs)
    method = {"create": "create_user", "update": "update_user", "get": "get_user", "list": "users"}[action]
    return getattr(identity, method)(*args, **kwargs)


def get_account_user(admin, user_id):
    return _user_call(admin, "get", user_id)


def _user_rows(admin, domain_id):
    rows = list(_user_call(admin, "list", domain_id=domain_id, name=ACCOUNT_NAME))
    rows = [row for row in rows if _field(row, "domain_id") == domain_id and _field(row, "name") == ACCOUNT_NAME]
    if len(rows) > 1:
        raise AccountUnavailable("backup_system_account_identity_ambiguous")
    return rows


async def ensure_account(redis, admin) -> dict:
    """Called only by the elected reconciler under its renewable work lease.

    A Redis reset window is reserved before a native write. If the process dies
    after Keystone accepted a password and before Redis saved it, the next leader
    detects failed unscoped proof and resets again after that bounded window.
    """
    from app.services.backup_account_reconciler import checkpoint_leader, run_write
    from app.services.work_dispatcher import _current_lease

    lease = _current_lease.get()
    if lease is None or not await lease.dispatcher.is_leader():
        raise AccountUnavailable("backup_system_account_leader_required")
    await checkpoint()
    # Prove storage can encrypt before creating or changing a native password.
    derive_encryption_subkey(_RECORD_DOMAIN)
    existing = await load_account(redis)
    domain_id = await run_sync(_resolve_domain, admin.identity)
    rows = await run_sync(_user_rows, admin, domain_id)
    user = rows[0] if rows else None
    created = False
    if user is None:
        if not await redis.set(RESET_KEY, "pending", nx=True, ex=RESET_INTERVAL):
            raise AccountUnavailable("backup_system_account_password_backoff")
        password = _password()
        try:
            user = await run_write(
                _user_call,
                admin,
                "create",
                name=ACCOUNT_NAME,
                domain_id=domain_id,
                password=password,
                enabled=True,
                description=ACCOUNT_DESCRIPTION,
                options={**ACCOUNT_OPTIONS, "multi_factor_auth_rules": []},
                afterglow_system_account="auto_backup:v1",
            )
        except Exception:
            raise AccountUnavailable("backup_system_account_create_rejected") from None
        created = True
        if not _field(user, "id"):
            raise AccountUnavailable("backup_system_account_identity_unverified")
        user = await run_sync(get_account_user, admin, _field(user, "id"))
    user_id = _field(user, "id")
    if not user_id or _field(user, "domain_id") != domain_id or _field(user, "name") != ACCOUNT_NAME:
        raise AccountUnavailable("backup_system_account_identity_unverified")
    if not created and not (
        existing and existing["id"] == user_id or _field(user, "afterglow_system_account") == "auto_backup:v1"
    ):
        raise AccountUnavailable("backup_system_account_identity_conflict")
    options = dict(_field(user, "options", {}) or {})
    if (
        not _field(user, "enabled", False)
        or any(options.get(key) is not value for key, value in ACCOUNT_OPTIONS.items())
        or options.get("multi_factor_auth_rules")
    ):
        try:
            await run_write(
                _user_call,
                admin,
                "update",
                user_id,
                enabled=True,
                options={**options, **ACCOUNT_OPTIONS, "multi_factor_auth_rules": []},
            )
        except Exception:
            raise AccountUnavailable("backup_system_account_repair_rejected") from None
        user = await run_sync(get_account_user, admin, user_id)
        observed = _field(user, "options", {}) or {}
        if (
            _field(user, "enabled") is not True
            or any(observed.get(key) is not value for key, value in ACCOUNT_OPTIONS.items())
            or observed.get("multi_factor_auth_rules")
        ):
            raise AccountUnavailable("backup_system_account_repair_unverified")
    if not created:
        password = _cached_record["password"] if existing and existing["id"] == user_id else _password()
        valid = False
        try:
            await run_sync(_unscoped_auth, user_id, password)
            valid = True
        except Unauthorized:
            pass
        if valid and existing:
            return existing
        if not valid:
            if not await redis.set(RESET_KEY, "pending", nx=True, ex=RESET_INTERVAL):
                raise AccountUnavailable("backup_system_account_password_backoff")
            password = _password()
            try:
                await run_write(_user_call, admin, "update", user_id, password=password)
            except Exception:
                raise AccountUnavailable("backup_system_account_password_rejected") from None
    # Persist only a successfully written AND freshly proved unscoped credential.
    try:
        await run_sync(_unscoped_auth, user_id, password)
    except Exception:
        raise AccountUnavailable("backup_system_account_password_unverified") from None
    record = {
        "id": user_id,
        "name": ACCOUNT_NAME,
        "domain_id": domain_id,
        "domain_name": get_settings().os_user_domain_name,
        "password": password,
    }
    encrypted = _encrypt_record(record)
    await checkpoint_leader()
    await redis.set(RECORD_KEY, encrypted)
    await load_account(redis)
    return _public_record(record)


async def ensure_project(project_id: str, *, require_ready: bool = False) -> None:
    """Queue a hint after policy persistence; only the reconciler grants roles."""
    if not get_settings().backup_system_account_enabled:
        if require_ready:
            raise Unauthorized("Scheduled protection system account is not activated")
        return
    redis = await _get_redis()
    await redis.set(f"{PREFIX}:requests:{project_id}", "1", ex=300)
    if not require_ready:
        return
    record = await load_account(redis)
    raw = await redis.get(f"{PREFIX}:ready:{project_id}")
    try:
        ready = json.loads(raw) if raw else None
    except (ValueError, TypeError):
        ready = None
    if not record or not ready or ready.get("user_id") != record["id"]:
        raise Unauthorized("Scheduled protection system account authorization is pending")


def connection_for_project(project_id: str, password: str, user_id: str):
    """Authenticate as the machine user, never fixed admin, in the exact tenant."""
    from app.services.instance_usage import prove_project_scope

    checkpoint_sync()
    settings = get_settings()
    conn = native_transport.connect(
        load_envvars=False,
        load_yaml_config=False,
        auth_url=settings.os_auth_url,
        auth_type="password",
        user_id=user_id,
        password=password,
        project_id=project_id,
        region_name=settings.os_region_name,
        interface=settings.os_interface,
        api_timeout=30,
        verify=settings.ssl_verify,
    )
    try:
        access = conn.session.auth.get_access(conn.session)
        if access.user_id != user_id:
            raise AccountUnavailable("backup_system_account_target_identity_invalid")
        prove_project_scope(conn, project_id)
        if vars(conn).get("_afterglow_usage_operator_scope") is not None:
            raise RuntimeError("Scheduled recovery points require exact-project credentials")
        return conn
    except BaseException:
        conn.close()
        raise


def get_connection_for_project(project_id: str):
    if not get_settings().backup_system_account_enabled or not _cached_record:
        raise Unauthorized("Scheduled protection system account is not ready")
    return connection_for_project(project_id, _cached_record["password"], _cached_record["id"])
