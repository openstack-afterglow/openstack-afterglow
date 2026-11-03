"""Private revision-fenced transport settings; no cached authority or outage fallback."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import asdict, dataclass, field
from email.utils import parseaddr

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import get_settings
from app.database import get_session_factory, is_db_available, is_db_configured
from app.models.db import RuntimeSetting
from app.services import mail_crypto

KEY = "mail.transport"
_MAX_REVISION = 2**53 - 1
_ABSENT = object()


@dataclass(frozen=True)
class SMTPSettings:
    enabled: bool = False
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = field(default="", repr=False)
    from_address: str = "noreply@afterglow.example.com"
    from_name: str = "Afterglow"
    security: str = "starttls"
    timeout_seconds: int = 10


@dataclass(frozen=True)
class IMAPSettings:
    enabled: bool = False
    host: str = ""
    port: int = 993
    username: str = ""
    password: str = field(default="", repr=False)
    security: str = "tls"
    mailbox: str = "INBOX"
    timeout_seconds: int = 10


@dataclass(frozen=True)
class Notifications:
    announcements_enabled: bool = True
    resource_alerts_enabled: bool = False


@dataclass(frozen=True)
class MailSettings:
    revision: int
    source: str
    smtp: SMTPSettings
    imap: IMAPSettings
    notifications: Notifications


def _error(code="mail_settings_invalid", status=422):
    return HTTPException(status, code)


def _host(value):
    if not isinstance(value, str) or len(value) > 253 or value != value.strip():
        raise _error()
    if not value:
        return value
    try:
        ipaddress.ip_address(value)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value):
            raise _error()
        if any(
            not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in value.split(".")
        ):
            raise _error()
    return value


def _text(value, maximum, *, empty=True):
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or (not empty and not value)
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise _error()
    return value


def _transport(value, kind, *, web=False):
    cls = SMTPSettings if kind == "smtp" else IMAPSettings
    fields = cls.__dataclass_fields__
    if not isinstance(value, dict) or set(value) != set(fields):
        raise _error()
    data = dict(value)
    if type(data["enabled"]) is not bool or type(data["port"]) is not int or not 1 <= data["port"] <= 65535:
        raise _error()
    if type(data["timeout_seconds"]) is not int:
        raise _error()
    if web:
        if not 1 <= data["timeout_seconds"] <= 30:
            raise _error()
        data["host"] = _host(data["host"])
    else:
        # Keep legacy source values usable, including FQDNs and underscore DNS
        # labels, while bounding operations and rejecting unsafe endpoint prose.
        data["timeout_seconds"] = max(1, min(30, data["timeout_seconds"]))
        _text(data["host"], 1024)
        if any(character.isspace() or character in "/@\\" for character in data["host"]):
            raise _error()
    _text(data["username"], 320)
    password = data["password"]
    if (
        not isinstance(password, str)
        or len(password) > 4096
        or "\0" in password
        or "\r" in password
        or "\n" in password
    ):
        raise _error()
    allowed = {"starttls", "tls"} if web or kind == "imap" else {"starttls", "tls", "none"}
    if (
        not isinstance(data["security"], str)
        or data["security"] not in allowed
        or (data["security"] == "none" and (password or data["username"]))
    ):
        raise _error()
    if web and data["enabled"] and not data["host"]:
        raise _error()
    if kind == "smtp":
        address = _text(data["from_address"], 254, empty=False)
        display, parsed = parseaddr(address, strict=True)
        if display or parsed != address or not re.fullmatch(r"[^\s<>@]+@[^\s<>@]+", address):
            raise _error()
        _text(data["from_name"], 200)
    else:
        _text(data["mailbox"], 200, empty=False)
    return cls(**data)


def _file_settings(base):
    smtp = {
        name: getattr(base, "smtp_" + name, field.default) for name, field in SMTPSettings.__dataclass_fields__.items()
    }
    explicit = getattr(base, "smtp_security", "")
    ssl = getattr(base, "smtp_use_ssl", False)
    if explicit:
        if explicit not in {"none", "starttls", "tls"} or (ssl and explicit != "tls"):
            raise _error("mail_config_unavailable", 503)
        smtp["security"] = explicit
    else:
        smtp["security"] = "tls" if ssl else "starttls" if getattr(base, "smtp_use_tls", True) else "none"
    imap = {
        name: getattr(base, "imap_" + name, field.default) for name, field in IMAPSettings.__dataclass_fields__.items()
    }
    try:
        return MailSettings(0, "config", _transport(smtp, "smtp"), _transport(imap, "imap"), Notifications())
    except HTTPException:
        raise _error("mail_config_unavailable", 503) from None


def _factory(base, *, required=False):
    factory = get_session_factory()
    configured = is_db_configured() or bool(getattr(base, "database_url", "")) or factory is not None
    if not configured and not required:
        return None
    if factory is None or not is_db_available():
        raise _error("mail_settings_storage_unavailable", 503)
    return factory


def _stored(value):
    if value is _ABSENT:
        return {"revision": 0, "override": None}
    if (
        not isinstance(value, dict)
        or set(value) != {"revision", "override"}
        or type(value["revision"]) is not int
        or not 1 <= value["revision"] <= _MAX_REVISION
    ):
        raise _error("mail_settings_unavailable", 503)
    return value


def _resolve(value, defaults):
    record = _stored(value)
    override = record["override"]
    if override is None:
        return MailSettings(record["revision"], "config", defaults.smtp, defaults.imap, defaults.notifications)
    try:
        if not isinstance(override, dict) or set(override) != {"smtp", "imap", "notifications"}:
            raise ValueError
        transports = {}
        for kind in ("smtp", "imap"):
            data = dict(override[kind])
            encrypted = data.pop("password_ciphertext")
            if not isinstance(encrypted, str):
                raise ValueError
            data["password"] = mail_crypto.decrypt_secret(encrypted, purpose=kind) if encrypted else ""
            transports[kind] = _transport(data, kind, web=True)
        notes = override["notifications"]
        if set(notes) != {"announcements_enabled", "resource_alerts_enabled"} or any(
            type(v) is not bool for v in notes.values()
        ):
            raise ValueError
        return MailSettings(record["revision"], "runtime", **transports, notifications=Notifications(**notes))
    except Exception:
        raise _error("mail_settings_unavailable", 503) from None


async def effective_settings(*, base_settings=None):
    base = base_settings if base_settings is not None else get_settings()
    defaults = _file_settings(base)
    factory = _factory(base)
    if factory is None:
        return defaults
    try:
        async with factory() as session:
            row = await session.get(RuntimeSetting, KEY)
            return _resolve(row.value_json if row else _ABSENT, defaults)
    except SQLAlchemyError:
        raise _error("mail_settings_storage_unavailable", 503) from None


def public_settings(settings):
    result = {"revision": settings.revision, "source": settings.source, "notifications": asdict(settings.notifications)}
    for kind in ("smtp", "imap"):
        data = asdict(getattr(settings, kind))
        data["password_configured"] = bool(data.pop("password"))
        result[kind] = data
    return result


async def smtp_ready(*, base_settings=None, require_frontend=False):
    base = base_settings if base_settings is not None else get_settings()
    smtp = (await effective_settings(base_settings=base)).smtp
    return bool(
        smtp.enabled
        and smtp.host
        and smtp.from_address
        and (not require_frontend or getattr(base, "frontend_base_url", ""))
    )


def _new_override(body, current):
    if not isinstance(body, dict) or set(body) != {"revision", "smtp", "imap", "notifications"}:
        raise _error()
    result = {}
    for kind in ("smtp", "imap"):
        draft = body[kind]
        if not isinstance(draft, dict):
            raise _error()
        draft = dict(draft)
        draft.pop("password_configured", None)
        password = draft.pop("password", None)
        clear = draft.pop("clear_password", False)
        reconfirm = draft.pop("reconfirm_password", False)
        if type(clear) is not bool or type(reconfirm) is not bool or (clear and password is not None):
            raise _error()
        previous = getattr(current, kind)
        if password is not None and (
            not isinstance(password, str) or not password or password in {"********", "••••••••"}
        ):
            raise _error()
        if (
            password is None
            and not clear
            and previous.password
            and not reconfirm
            and any(draft.get(name) != getattr(previous, name) for name in ("host", "port", "username", "security"))
        ):
            raise _error("mail_secret_reconfirmation_required")
        secret = "" if clear else previous.password if password is None else password
        resolved = _transport({**draft, "password": secret}, kind, web=True)
        data = asdict(resolved)
        data.pop("password")
        try:
            data["password_ciphertext"] = mail_crypto.encrypt_secret(secret, purpose=kind) if secret else ""
        except ValueError:
            raise _error("mail_secret_unavailable", 503) from None
        result[kind] = data
    notes = body["notifications"]
    if (
        not isinstance(notes, dict)
        or set(notes) != {"announcements_enabled", "resource_alerts_enabled"}
        or any(type(v) is not bool for v in notes.values())
    ):
        raise _error()
    result["notifications"] = dict(notes)
    return result


async def save_settings(body=None, *, revision=None, reset=False, user_id=None, base_settings=None):
    base = base_settings if base_settings is not None else get_settings()
    expected = revision if reset else body.get("revision") if isinstance(body, dict) else None
    if type(expected) is not int or not 0 <= expected < _MAX_REVISION:
        raise _error()
    defaults = _file_settings(base)
    factory = _factory(base, required=True)
    try:
        async with factory() as session, session.begin():
            row = await session.get(RuntimeSetting, KEY, with_for_update=True)
            old = row.value_json if row else _ABSENT
            if _stored(old)["revision"] != expected:
                raise _error("mail_settings_revision_conflict", 409)
            current = defaults if reset else _resolve(old, defaults)
            value = {"revision": expected + 1, "override": None if reset else _new_override(body, current)}
            if row is None:
                session.add(RuntimeSetting(setting_key=KEY, value_json=value, updated_by_user_id=user_id))
                await session.flush()
            else:
                row.value_json = value
                row.updated_by_user_id = user_id
        return public_settings(_resolve(value, defaults))
    except IntegrityError:
        raise _error("mail_settings_revision_conflict", 409) from None
    except SQLAlchemyError:
        raise _error("mail_settings_storage_unavailable", 503) from None
