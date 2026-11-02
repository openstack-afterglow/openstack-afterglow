"""Privileged, single-dispatch password replacement with registered-mail delivery.

Only the native user setter sees the generated credential. Nothing persists it;
SMTP failures cannot roll back a known password change or justify replaying it.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import secrets
import string
from datetime import UTC, datetime
from email.message import EmailMessage
from urllib.parse import quote

import aiosmtplib
from fastapi import HTTPException
from sqlalchemy import update

from app.config import get_settings
from app.models.account_recovery import AccountRecovery
from app.models.activity import ActivityLog
from app.services import (
    domain_auth,
    domain_iam,
    domain_projects,
    domain_scope,
    identity_roles,
    keystone,
    project_service,
    session_store,
)
from app.services.project_service import _provider_call

_field = identity_roles._field
_COOLDOWN_SECONDS = 300
_SYMBOLS = "!@#$%^&*()-_=+"


def _error(status, code, **effects):
    return HTTPException(status, {"code": "admin_password_reset_" + code, **effects})


def _random_password():
    # Fixed work: guarantee every class, then cryptographically shuffle once.
    classes = (string.ascii_uppercase, string.ascii_lowercase, string.digits, _SYMBOLS)
    alphabet = "".join(classes)
    chars = [secrets.choice(group) for group in classes]
    chars.extend(secrets.choice(alphabet) for _ in range(28))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


async def _subject(user_id, ks, catalog):
    user = await _provider_call(ks.users.get, user_id)
    home = _field(user, "domain_id")
    if _field(user, "id") != user_id or not isinstance(home, str) or not home:
        raise _error(503, "identity_unavailable")
    if _field(user, "enabled") is not True or _field(user, "name") == get_settings().os_username:
        raise _error(403, "subject_ineligible")
    # Stock Keystone cannot add the first local password to a federated shadow
    # user: its password setter inserts local_user with a NULL name and returns
    # 500 after a rolled-back transaction. Refuse before the fence, native write
    # and session revocation; only an explicit local-password marker qualifies.
    if _field(user, "federated") and _field(user, "afterglow_local_password") is not True:
        raise _error(409, "external_account")
    domain = await _provider_call(ks.domains.get, home)
    if _field(domain, "id") != home:
        raise _error(503, "identity_unavailable")
    if _field(domain, "enabled") is not True:
        raise _error(403, "subject_ineligible")
    # Effective listings omit system grants. Include exact raw user/group system
    # assignments so operational identities cannot evade service-role protection.
    rows = await _provider_call(lambda: list(ks.role_assignments.list(user=user_id, effective=True)))
    for row in rows:
        source = domain_projects._assignment(row, catalog, effective=True)
        if source["user_id"] != user_id:
            raise _error(503, "identity_unavailable")
    expanded = project_service._expanded_role_ids(rows, catalog, user_id)
    sources = [
        (row, "user_id", user_id)
        for row in await _provider_call(lambda: list(ks.role_assignments.list(user=user_id, system="all")))
    ]
    for group in await _provider_call(lambda: list(ks.groups.list(user=user_id))):
        gid = _field(group, "id")
        if not isinstance(gid, str) or not gid:
            raise _error(503, "identity_unavailable")
        sources.extend(
            (row, "group_id", gid)
            for row in await _provider_call(lambda gid=gid: list(ks.role_assignments.list(group=gid, system="all")))
        )
    for row, principal, subject in sources:
        source = domain_projects._assignment(row, catalog)
        if source["kind"] != "system" or source[principal] != subject:
            raise _error(503, "identity_unavailable")
        expanded.update({source["role_id"], *identity_roles._descendant_ids(catalog, source["role_id"])})
    by_id = {role["id"]: role for role in catalog}
    if any(by_id[rid]["name"].casefold() == "service" for rid in expanded):
        raise _error(403, "subject_ineligible")
    try:
        email = domain_auth.normalize_email(_field(user, "email")).casefold()
    except (domain_auth.DomainAuthError, TypeError, AttributeError):
        raise _error(409, "email_unavailable") from None
    if len(email) > 255:
        raise _error(409, "email_unavailable")
    matches = await domain_iam._find_accounts(None, email=email)
    if len(matches) != 1 or _field(matches[0], "id") != user_id or _field(matches[0], "domain_id") != home:
        raise _error(409, "email_ambiguous")
    return user, email


async def _smtp_ready():
    settings = get_settings()
    if not (
        settings.smtp_enabled
        and settings.smtp_host
        and settings.smtp_from_address
        and settings.frontend_base_url
        and settings.smtp_use_tls is True
    ):
        raise _error(503, "email_unavailable")
    # Preserve the configured SMTP timeout/auth, but credential-bearing mail
    # requires verified STARTTLS even if ordinary notification mail allows less.
    client = aiosmtplib.SMTP(
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username or None,
        password=settings.smtp_password or None,
        use_tls=False,
        start_tls=settings.smtp_use_tls,
        validate_certs=True,
        timeout=settings.smtp_timeout_seconds,
    )
    try:
        await client.connect()  # Includes configured TLS negotiation and login.
    except Exception:
        client.close()
        raise _error(503, "email_unavailable") from None
    return client


def _native_update(credential, user_id, password):
    settings = get_settings()
    transport = keystone.native_transport.create_session(timeout=30, verify=settings.ssl_verify)
    try:
        # PATCH is the same native admin setter used by `openstack user set
        # --password`. A minimal patch preserves all unrelated/federation extras.
        response = transport.request(
            f"{settings.os_auth_url.rstrip('/')}/users/{quote(user_id, safe='')}",
            "PATCH",
            json={"user": {"password": password, "afterglow_local_password": True}},
            headers={"X-Auth-Token": credential},
            authenticated=False,
            allow_reauth=False,
            redirect=False,
            connect_retries=0,
            status_code_retries=0,
            log=False,
            raise_exc=False,
        )
        try:
            return response.status_code, response.json() if response.status_code == 200 else None
        finally:
            response.close()
    finally:
        transport.session.close()


async def _deliver(client, user, email, password):
    settings = get_settings()
    login_url = settings.frontend_base_url.rstrip("/") + "/login"
    username = _field(user, "name", "")
    advice = (
        "Your administrator changed your account password. Sign in and change it immediately in your profile. "
        "Afterglow does not force a first-login expiry; native password policy still applies. "
        "If this was unexpected, contact your administrator immediately."
    )
    message = EmailMessage()
    message["Subject"] = "Account password reset"
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_address}>"
    message["To"] = email
    message.set_content(f"{advice}\n\nUsername: {username}\nPassword: {password}\nConsole login: {login_url}\n")
    message.add_alternative(
        f"<p>{html.escape(advice)}</p><p>Username: {html.escape(username)}</p>"
        f"<p>Password: <code>{html.escape(password)}</code></p>"
        f'<p><a href="{html.escape(login_url, quote=True)}">Console login</a></p>',
        subtype="html",
    )
    try:
        refused, _ = await client.send_message(message, recipients=[email], sender=settings.smtp_from_address)
        return not refused
    except Exception:
        # SMTP diagnostics can echo DATA. Never log or chain the exception.
        return False


async def _revoke(user_id):
    failed = False
    try:
        await session_store.revoke_user_sessions(user_id, revoke_keystone=True, strict_keystone=True)
    except Exception:
        failed = True
    try:
        await domain_scope.invalidate_authority()
    except Exception:
        failed = True
    return not failed


async def _dispatch_fence(session, actor, user_id):
    # The graph lease serializes this with every first-party recovery writer.
    # Consume old mailbox proofs before native dispatch, never restore on error.
    await session.execute(
        update(AccountRecovery)
        .where(
            AccountRecovery.user_id == user_id,
            AccountRecovery.kind.in_(["password", "email_change", "password_create"]),
            AccountRecovery.status.in_(["pending", "delivery_pending"]),
        )
        .values(status="superseded", consumed_at=datetime.now(UTC))
    )
    audit = ActivityLog(
        project_id=actor.get("project_id", ""),
        user_id=actor["user_id"],
        username=actor.get("username", ""),
        resource_type="user",
        resource_id=user_id,
        action="password_reset_email",
        status="started",
        service="keystone",
        source="afterglow",
        extra={"outcome": "dispatching"},
    )
    session.add(audit)
    await session.commit()
    return audit


async def _audit(session, row, outcome, *, changed=None, delivered=False, sessions_revoked=None):
    try:
        row.status = "success" if outcome == "changed" else "failed"
        row.extra = {
            "outcome": outcome,
            "changed": changed,
            "delivered": delivered,
            "sessions_revoked": sessions_revoked,
        }
        await session.commit()
        return True
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        return False


@identity_roles._complete_mutation
async def reset_password_email(user_id, actor, conn, session):
    """Drain dispatch, mail and strict session cleanup even after HTTP cancellation."""
    client = None
    try:
        if (
            actor.get("_live_system_admin") is not True
            or not actor.get("user_id")
            or getattr(conn, "_afterglow_user_id", None) != actor["user_id"]
            or not actor.get("identity_domain_id")
            or getattr(conn, "_afterglow_identity_domain_id", None) != actor["identity_domain_id"]
        ):
            raise _error(403, "system_admin_required")
        await session.rollback()
        async with domain_iam._iam_write() as (lease, ks, catalog):
            if not await _provider_call(keystone._is_system_admin, actor["user_id"]):
                raise _error(403, "system_admin_required")
            user, email = await _subject(user_id, ks, catalog)
            credential = getattr(conn, "_afterglow_token", None)
            if not isinstance(credential, str) or not credential:
                raise _error(503, "authority_unavailable")
            await identity_roles._session_ready({user_id})
            client = await _smtp_ready()
            redis = await session_store._get_redis()
            subject_key = hashlib.sha256(f"{get_settings().os_auth_url.rstrip('/')}\0{user_id}".encode()).hexdigest()
            if not await redis.set("afterglow:admin-password-reset:" + subject_key, "1", nx=True, ex=_COOLDOWN_SECONDS):
                raise _error(429, "rate_limited")
            await lease.assert_owned()
            current, current_email = await _subject(user_id, ks, catalog)
            if (
                _field(current, "domain_id") != _field(user, "domain_id")
                or _field(current, "email") != _field(user, "email")
                or current_email != email
            ):
                raise _error(409, "identity_changed")
            user = current
            await lease.assert_owned()
            password = _random_password()
            try:
                audit = await _dispatch_fence(session, actor, user_id)
            except Exception:
                await session.rollback()
                raise _error(503, "audit_failed", changed=False, delivered=False) from None
            await lease.assert_owned()
            status, payload = None, None
            try:
                status, payload = await asyncio.to_thread(_native_update, credential, user_id, password)
            except Exception:
                pass
            if status in {400, 401, 403, 404, 409, 422}:
                recorded = await _audit(session, audit, "rejected", changed=False)
                if not recorded:
                    raise _error(503, "audit_failed", changed=False, delivered=False)
                raise _error(status, "native_rejected", changed=False, delivered=False)
            result = payload.get("user") if isinstance(payload, dict) else None
            known = (
                status == 200
                and isinstance(result, dict)
                and result.get("id") == user_id
                and result.get("domain_id") == _field(user, "domain_id")
                and result.get("email") == _field(user, "email")
                and result.get("afterglow_local_password") is True
            )
            delivered = False
            if known:
                try:
                    delivered = await _deliver(client, user, email, password)
                except Exception:
                    # Even MIME construction failures occur after a real reset.
                    # They must still drain session revocation and report effects.
                    pass
            # A successful reset and any ambiguous dispatch invalidate every
            # target session; mail failure must not leave the old sessions alive.
            sessions_revoked = await _revoke(user_id)
            outcome = (
                "outcome_unknown"
                if not known
                else "sessions_failed"
                if not sessions_revoked
                else ("changed" if delivered else "email_failed")
            )
            recorded = await _audit(
                session,
                audit,
                outcome,
                changed=True if known else None,
                delivered=delivered,
                sessions_revoked=sessions_revoked,
            )
            if not known:
                raise _error(
                    502, "outcome_unknown", delivered=False, sessions_revoked=sessions_revoked, audit_recorded=recorded
                )
            if not recorded:
                raise _error(503, "audit_failed", changed=True, delivered=delivered, sessions_revoked=sessions_revoked)
            if not sessions_revoked:
                raise _error(503, "sessions_failed", changed=True, delivered=delivered)
            if not delivered:
                raise _error(503, "email_failed", changed=True, delivered=False)
            return {"status": "changed", "delivered": True}
    except HTTPException as exc:
        if isinstance(exc.detail, dict) and str(exc.detail.get("code", "")).startswith("admin_password_reset_"):
            raise
        raise _error(503, "unavailable") from None
    except Exception:
        raise _error(503, "unavailable") from None
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
