"""Atomic first-password extension for exactly Keystone 28.1.0.

Native password writers remain native. Database triggers certify every writer
against the same persistent user key, including cascaded parent deletion.
"""
import base64
import binascii
import hashlib
import json
import re
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from threading import Lock

import keystone.conf
from keystone import exception
from keystone.common import password_hashing, provider_api, sql
from keystone.common.validation import validators
from keystone.identity.backends import base
from keystone.identity.backends import sql as identity_sql
from keystone.identity.backends import sql_model as model
from oslo_config import cfg
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url

from . import schema

CONF = keystone.conf.CONF
API_REVISION = "first-password-galera-v2"
GROUP = "afterglow_initial_password"
CONF.register_group(cfg.OptGroup(GROUP))
CONF.register_opts([
    cfg.BoolOpt("enabled", default=False),
    cfg.StrOpt("service_user_id", default=""),
    cfg.ListOpt("peer_connections", default=[], secret=True),
    cfg.ListOpt("cluster_members", default=[]),
], group=GROUP)
_PENDING = ContextVar("afterglow_initial_password", default=None)


def configured():
    options = CONF[GROUP]
    if not options.enabled or not options.service_user_id:
        raise schema.Unsupported("Initial password creation is disabled")
    if not options.peer_connections or not options.cluster_members:
        raise schema.Unsupported("Every Galera member must be explicitly configured")
    if len(options.peer_connections) != len(options.cluster_members) or len(set(options.cluster_members)) != len(options.cluster_members):
        raise schema.Unsupported("Galera membership configuration is not exact")
    verify_build()
    return options


@lru_cache(maxsize=1)
def verify_build():
    import keystone
    root = Path(keystone.__file__).resolve().parent
    manifest = json.loads((root / "afterglow_initial_password_build.json").read_text())
    if (manifest.get("revision") != schema.REVISION or manifest.get("api_revision") != API_REVISION or manifest.get("keystone_version") != "28.1.0" or
            manifest.get("source_commit") != "c0f8139167179f4ffe7749516105958a2ecdc2b0" or
            manifest.get("upstream_wheel_sha256") != "4477a975a341faea86c7888a3f08c16f882af7fd3323444c42c3e89e16e5a1b0" or
            set(manifest.get("files", {})) != {"keystone/api/users.py", "keystone/identity/backends/sql.py", "keystone/identity/core.py", "keystone/identity/backends/sql_model.py", "keystone/common/validation/validators.py", "keystone/common/sql/core.py", "keystone/common/password_hashing.py", "keystone/common/password_hashers/__init__.py", "keystone/common/password_hashers/bcrypt.py", "keystone/common/password_hashers/pbkdf2.py", "keystone/common/password_hashers/scrypt.py", "keystone/federation/backends/sql.py"} or
            set(manifest.get("extension_files", {})) != {"__init__.py", "api.py", "schema.py", "migrate.py", "schema.sql"}):
        raise schema.Unsupported("Keystone extension build is unqualified")
    for relative, digest in manifest["files"].items():
        if hashlib.sha256((root.parent / relative).read_bytes()).hexdigest() != digest:
            raise schema.Unsupported("Keystone hook differs from its immutable build")
    package = Path(__file__).resolve().parent
    for relative, digest in manifest["extension_files"].items():
        if hashlib.sha256((package / relative).read_bytes()).hexdigest() != digest:
            raise schema.Unsupported("Extension differs from its immutable build")


@lru_cache(maxsize=8)
def peer_engine(url):
    parsed = make_url(url)
    if parsed.drivername != "mysql+pymysql" or not parsed.host or not parsed.database:
        raise schema.Unsupported("Explicit MariaDB peer connection required")
    return create_engine(url, pool_pre_ping=True, hide_parameters=True,
                         connect_args={"connect_timeout": 5, "read_timeout": 10, "write_timeout": 10})


_POOL_PREPARE_LOCK = Lock()


def restore_session(dbapi_connection, record, reset_state):
    previous = record.info.pop("afterglow_original_sync_wait", None)
    if previous is not None and not reset_state.terminate_only:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SET SESSION wsrep_sync_wait=" + str(previous))
        except Exception:
            record.invalidate()
            raise schema.Unsupported("Could not restore native session settings") from None
        finally:
            cursor.close()


def prepare(connection):
    if connection.dialect.name != "mysql":
        raise schema.Unsupported("Only pinned MariaDB Galera is supported")
    with _POOL_PREPARE_LOCK:
        if not event.contains(connection.engine.pool, "reset", restore_session):
            event.listen(connection.engine.pool, "reset", restore_session)
    if "afterglow_original_sync_wait" not in connection.info:
        connection.info["afterglow_original_sync_wait"] = int(connection.execute(text("SELECT @@session.wsrep_sync_wait")).scalar_one())
    # This runs before the first data read or write in this transaction. The
    # ensuing SELECT is a causal barrier, including already-certified remote
    # commits not yet applied locally. Never weaken this to a snapshot read.
    connection.execute(text("SET SESSION wsrep_sync_wait=15"))
    connection.execute(text("SELECT 1"))


def membership(connection):
    variables = dict(connection.execute(text("SHOW GLOBAL VARIABLES LIKE 'wsrep_node_name'")).all())
    status = dict(connection.execute(text("SHOW GLOBAL STATUS LIKE 'wsrep_%'")).all())
    return (variables.get("wsrep_node_name"), status.get("wsrep_cluster_state_uuid"),
            status.get("wsrep_cluster_conf_id"), int(status.get("wsrep_cluster_size", "0")))


@contextmanager
def guarded_cluster(session):
    options = configured()
    connection = session.connection()
    prepare(connection)
    # Retain each peer's metadata locks until the local credential transaction
    # finishes. TOI schema changes cannot interleave after integrity checks.
    with ExitStack() as stack:
        connections = []
        for url in options.peer_connections:
            peer = stack.enter_context(peer_engine(url).connect())
            stack.enter_context(peer.begin())
            prepare(peer)
            schema.validate(peer, auditor=True)
            if peer.execute(text("SELECT CURRENT_USER()")).scalar_one() == connection.execute(text("SELECT CURRENT_USER()")).scalar_one():
                raise schema.Unsupported("Schema auditor cannot be the native writer")
            if peer.execute(text("SELECT DATABASE()")).scalar_one() != connection.execute(text("SELECT DATABASE()")).scalar_one():
                raise schema.Unsupported("Schema auditor must inspect the native database")
            connections.append(peer)
        schema.validate(session)
        before = [membership(peer) for peer in connections]
        current = membership(connection)
        expected = set(options.cluster_members)
        if ({item[0] for item in before} != expected or current[0] not in expected or
                len({item[1:] for item in before + [current]}) != 1 or
                current[3] != len(expected) or not current[1]):
            raise schema.Unsupported("Galera membership or schema census is incomplete")
        def check():
            if [membership(peer) for peer in connections] != before or membership(connection) != current:
                raise schema.Unsupported("Galera membership changed during the write")
        yield check


def pending():
    return _PENDING.get() is not None


class IdentityChanged(Exception):
    pass


class InvalidPassword(Exception):
    pass


def valid_revision(value):
    return isinstance(value, str) and 1 <= len(value) <= 20 and value.isascii() and value.isdecimal() and str(int(value)) == value and 0 <= int(value) < 18446744073709551615


def create(user_id, domain_id, password, email, identity_revision, initiator):
    return conditional_password("create", user_id, domain_id, password, email, identity_revision, initiator)


def reset(user_id, domain_id, password, email, identity_revision, initiator):
    return conditional_password("reset", user_id, domain_id, password, email, identity_revision, initiator)


def conditional_password(operation, user_id, domain_id, password, email, identity_revision, initiator):
    """Use native manager validation, audit and revocation; never retry."""
    if operation not in ("create", "reset"):
        raise schema.Unsupported("Unknown conditional password operation")
    configured()
    if not isinstance(password, str) or not password:
        raise InvalidPassword()
    if not isinstance(email, str) or not email or not valid_revision(identity_revision):
        raise exception.ValidationError(message="Exact email and canonical native identity revision are required")
    try:
        size = len(password.encode("utf-8"))
    except UnicodeError:
        raise InvalidPassword() from None
    maximum = CONF.identity.max_password_length
    if CONF.identity.password_hash_algorithm == "bcrypt":
        maximum = min(maximum, 72)
    if size > maximum:
        raise InvalidPassword()
    try:
        validators.validate_password(password)
    except exception.PasswordValidationError:
        raise InvalidPassword() from None
    manager = provider_api.ProviderAPIs.identity_api
    _, driver, entity_id = manager._get_domain_driver_and_entity_id(user_id)
    if type(driver) is not identity_sql.Identity or entity_id != user_id:
        raise schema.Unsupported("Only exact native SQL identities are supported")
    token = _PENDING.set((user_id, domain_id, password, email, identity_revision, operation))
    try:
        # The installer intercepts only the SQL driver's dispatch before the
        # native retry decorator. Everything above it stays Keystone-native.
        manager.update_user(user_id, {"password": password}, initiator=initiator)
    finally:
        _PENDING.reset(token)


def update_user(driver, user_id, user):
    expected = _PENDING.get()
    if not expected or user_id != expected[0] or user != {"password": expected[2]}:
        raise schema.Unsupported("Conditional native dispatch binding differs")
    domain_id = expected[1]
    with ExitStack() as cluster_stack:
        with sql.session_for_write() as session:
            check_cluster = cluster_stack.enter_context(guarded_cluster(session))
            guard = session.execute(text(
                "UPDATE afterglow_password_guard SET revision=revision+1 WHERE user_id=:id AND revision=:revision"
            ), {"id": user_id, "revision": int(expected[4])})
            if guard.rowcount != 1:
                raise IdentityChanged()
            # Locking/current SQL reads, NOT the cached manager/ORM snapshot.
            subject = session.execute(text(
                "SELECT id, domain_id, enabled FROM `user` WHERE id=:id FOR UPDATE"
            ), {"id": user_id}).one_or_none()
            if subject is None:
                raise exception.UserNotFound(user_id=user_id)
            if subject.id != user_id or subject.domain_id != domain_id or subject.enabled != 1:
                raise exception.Forbidden(message="Exact enabled native subject/home required")
            original_email = session.query(model.User.extra).filter_by(id=user_id).with_for_update().scalar()
            if not isinstance(original_email, dict) or original_email.get("email") != expected[3]:
                raise IdentityChanged()
            locals_, history = password_history(session, user_id, domain_id)
            operation = expected[5]
            if operation == "create":
                # ANY history, including NULL or malformed hashes, prohibits
                # initial creation. Never treat a broken history as absence.
                if history:
                    raise exception.Conflict(type="initial password", details="Native password history already exists")
            elif operation == "reset":
                if credential_state(locals_, history) != "existing":
                    raise exception.Conflict(type="password reset", details="Native existing password history required")
            else:
                raise schema.Unsupported("Unknown conditional password operation")
            session.expire_all()
            subject_ref = session.query(model.User).filter_by(id=user_id).populate_existing().with_for_update().one_or_none()
            if not subject_ref or subject_ref.domain_id != domain_id or subject_ref.enabled is not True:
                raise exception.Forbidden(message="Native subject is unavailable or disabled")
            if operation == "create" and subject_ref.password_ref is not None:
                raise exception.Conflict(type="initial password", details="Native password history already exists")
            if operation == "reset" and (subject_ref.local_user is None or subject_ref.password_ref is None):
                raise schema.Unsupported("Native existing password mapping differs")
            validate_federation(session, user_id)
            if subject_ref.local_user is None:
                name = subject_ref.name
                if not isinstance(name, str) or not name:
                    raise schema.Unsupported("Federated subject has no native local name")
                subject_ref.local_user = model.LocalUser(name=name)
            # Use Keystone's native setter: configured hash, expiry, history.
            # Do not reconstruct User.from_dict (it can lose federation extras).
            subject_ref.password = expected[2]
            if driver._change_password_required(subject_ref):
                from oslo_utils import timeutils
                subject_ref.password_ref.expires_at = timeutils.utcnow()
            extras = dict(subject_ref.extra or {})
            extras["afterglow_local_password"] = True
            subject_ref.extra = extras
            session.flush()
            result = base.filter_user(subject_ref.to_dict(include_extra_dict=True))
            check_cluster()
        return result


def validate_federation(session, user_id):
    rows = session.execute(text(
        "SELECT f.id,i.id AS provider_id,i.enabled,p.id AS protocol_id,m.id AS mapping_id "
        "FROM federated_user f LEFT JOIN identity_provider i ON i.id=f.idp_id "
        "LEFT JOIN federation_protocol p ON p.idp_id=f.idp_id AND p.id=f.protocol_id "
        "LEFT JOIN mapping m ON m.id=p.mapping_id WHERE f.user_id=:id FOR UPDATE"
    ), {"id": user_id}).all()
    if any(row.provider_id is None or row.enabled != 1 or row.protocol_id is None or row.mapping_id is None for row in rows):
        raise schema.Unsupported("Native federation binding is unavailable or disabled")


def password_history(session, user_id, domain_id):
    locals_ = session.execute(text(
        "SELECT id, domain_id FROM local_user WHERE user_id=:id FOR UPDATE"
    ), {"id": user_id}).all()
    if len(locals_) > 1 or (locals_ and locals_[0].domain_id != domain_id):
        raise schema.Unsupported("Native local identity mapping differs")
    history = []
    if locals_:
        history = session.execute(text(
            "SELECT id,password_hash FROM password WHERE local_user_id=:id FOR UPDATE"
        ), {"id": locals_[0].id}).all()
    return locals_, history


def encoded_hash_bytes(value):
    if not re.fullmatch(r"[A-Za-z0-9./+]+", value):
        raise ValueError()
    normalized = value.replace(".", "+")
    decoded = base64.b64decode(normalized + "=" * (-len(normalized) % 4), validate=True)
    if base64.b64encode(decoded).decode("ascii").rstrip("=") != normalized:
        raise ValueError()
    return decoded


def valid_password_hash(value):
    """Parse the pinned native formats without computing a password KDF.

    Native hasher identification alone accepts truncated/NULL payloads. Check
    complete parameters and encoded salt/digest; never expose or log a hash.
    These representations cannot prove knowledge of the existing password.
    """
    if not isinstance(value, str) or not 1 <= len(value) <= 255:
        return False
    try:
        hasher = password_hashing._get_hasher_from_ident(value)
        if hasher.name == "bcrypt":
            return re.fullmatch(r"\$2[abxy]\$(?:0[4-9]|[12][0-9]|3[01])\$[./A-Za-z0-9]{21}[.Oeu][./A-Za-z0-9]{30}[.CGKOSWaeimquy26]", value) is not None
        if hasher.name == "bcrypt_sha256":
            return re.fullmatch(r"\$bcrypt-sha256\$v=2,t=2[ab],r=(?:[4-9]|[12][0-9]|3[01])\$[./A-Za-z0-9]{21}[.Oeu]\$[./A-Za-z0-9]{30}[.CGKOSWaeimquy26]", value) is not None
        parts = value.split("$")
        if len(parts) != 5 or parts[0] or not encoded_hash_bytes(parts[3]):
            return False
        digest = encoded_hash_bytes(parts[4])
        if hasher.name == "pbkdf2_sha512":
            return (parts[2].isascii() and parts[2].isdecimal() and
                    1 <= int(parts[2]) <= 2147483647 and len(digest) == 64)
        if hasher.name == "scrypt":
            parameters = parts[2].split(",")
            if len(parameters) != 3 or any(item.count("=") != 1 for item in parameters):
                return False
            parameters = dict(item.split("=") for item in parameters)
            if set(parameters) != {"ln", "r", "p"} or any(
                    not item.isascii() or not item.isdecimal() for item in parameters.values()):
                return False
            ln, r, p = (int(parameters[key]) for key in ("ln", "r", "p"))
            return 1 <= ln <= 31 and r >= 1 and p >= 1 and r * p < 1073741824 and len(digest) == 32
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        return False
    return False


def credential_state(locals_, history):
    if not history:
        return "absent"
    if not locals_ or any(not valid_password_hash(row.password_hash) for row in history):
        raise schema.Unsupported("Native password history is unavailable or malformed")
    return "existing"


def identity(user_id):
    with sql.session_for_write() as session, guarded_cluster(session) as check:
        subject = session.query(model.User).filter_by(id=user_id).populate_existing().with_for_update().one_or_none()
        if subject is None:
            raise exception.UserNotFound(user_id=user_id)
        if subject.id != user_id or subject.enabled is not True:
            raise exception.Forbidden(message="Exact enabled native subject required")
        validate_federation(session, user_id)
        email = (subject.extra or {}).get("email")
        if not isinstance(email, str) or not email:
            raise schema.Unsupported("Exact native email is unavailable")
        revision = session.execute(text("SELECT revision FROM afterglow_password_guard WHERE user_id=:id FOR UPDATE"), {"id": user_id}).scalar_one()
        locals_, history = password_history(session, user_id, subject.domain_id)
        state = credential_state(locals_, history)
        value = {"id": subject.id, "domain_id": subject.domain_id, "email": email, "identity_revision": str(revision), "password_state": state}
        check()
        return {"user": value}
