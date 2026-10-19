"""Email-owned recovery, serialized with every first-party identity graph writer.

Delivery must finish before a proof is redeemable. Native mutations have a
committed dispatch fence: rejection, timeout, cancellation and process death
never make that token replayable. No password or plaintext token is journaled.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from keystoneauth1.exceptions.http import Unauthorized
from sqlalchemy import select, update

from app.config import get_settings
from app.models.account_recovery import AccountRecovery
from app.services import (
    domain_auth,
    domain_iam,
    domain_scope,
    email_service,
    identity_roles,
    keystone,
    project_service,
    session_store,
)
from app.services.project_service import _provider_call

_field = identity_roles._field
_ACCEPTED = {"accepted": True}


def _error(status, code):
    return HTTPException(status, {"code": code})


def _now():
    return datetime.now(UTC)


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _email(value):
    try:
        result = domain_auth.normalize_email(value).casefold()
    except domain_auth.DomainAuthError:
        raise _error(422, "invalid_email") from None
    if len(result) > 255:
        raise _error(422, "invalid_email")
    return result


def recovery_enabled():
    settings = get_settings()
    return bool(
        settings.smtp_enabled and settings.smtp_host and settings.smtp_from_address and settings.frontend_base_url
    )


async def _address_allowed(email):
    # Same Redis and atomic NX/expiry convention as the graph/federation leases.
    # Address budgets are shared across source IPs and username/password kinds.
    redis = await session_store._get_redis()
    return bool(await redis.set("afterglow:recovery:address:" + _digest(email), "1", nx=True, ex=60))


async def _eligible(user, ks, catalog):
    uid, home = _field(user, "id"), _field(user, "domain_id")
    if not uid or not home or _field(user, "enabled") is not True:
        return False
    if _field(user, "name") == get_settings().os_username:
        return False
    local = _field(user, "afterglow_local_password")
    if local is not True and (local is not None or _field(user, "federated")):
        return False
    home_row = await _provider_call(ks.domains.get, home)
    if _field(home_row, "id") != home or _field(home_row, "enabled") is not True:
        return False
    assignments = await _provider_call(lambda: list(ks.role_assignments.list(user=uid, effective=True)))
    expanded = project_service._expanded_role_ids(assignments, catalog, uid)
    by_id = {row["id"]: row for row in catalog}
    # Deliberately do not protect admin/manager: the user explicitly authorized
    # email-owned system-admin recovery. Only operational/service identities are excluded.
    return not any(by_id[rid]["name"].casefold() == "service" for rid in expanded)


async def _unique(email, user_id=None):
    matches = await domain_iam._find_accounts(None, email=email)
    if user_id is None:
        return matches[0] if len(matches) == 1 else None
    if any(_field(user, "id") != user_id for user in matches):
        raise _error(409, "email_in_use")


async def _issue(kind, user, email, session):
    token = secrets.token_urlsafe(32)
    row = AccountRecovery(
        token_hash=_digest(token),
        kind=kind,
        user_id=_field(user, "id"),
        identity_domain_id=_field(user, "domain_id"),
        original_email=_field(user, "email"),
        email=email,
        status="delivery_pending",
        expires_at=_now() + timedelta(hours=1),
        created_at=_now(),
    )
    session.add(row)
    await session.commit()
    link = f"{get_settings().frontend_base_url.rstrip('/')}/recover/{token}"
    delivered = False
    try:
        if kind == "email_change":
            # No token, target address or other secret in the old-address notice.
            notice = "An email address change was requested for your account. If this was not you, contact your administrator."
            delivered = await email_service.send_email(
                row.original_email, "Account email change requested", f"<p>{notice}</p>", notice
            )
        else:
            delivered = True
        if delivered:
            delivered = await email_service.send_email(
                email,
                "Verify your account request",
                f'<p><a href="{html.escape(link, quote=True)}">Continue account recovery</a></p>',
                f"Continue account recovery: {link}\nThis link expires in one hour. Ignore it if you did not request it.",
            )
    except Exception:
        # Transport errors must not expose account eligibility or SMTP contents.
        delivered = False
    row.status = "pending" if delivered else "delivery_failed"
    await session.commit()
    return delivered


@identity_roles._complete_mutation
async def request_recovery(kind, email, session):
    if kind not in {"username", "password"}:
        raise _error(422, "invalid_recovery_kind")
    email = _email(email)
    try:
        if not recovery_enabled() or not await _address_allowed(email):
            return dict(_ACCEPTED)
        await session.rollback()
        async with domain_iam._iam_write() as (lease, ks, catalog):
            user = await _unique(email)
            if user is not None and await _eligible(user, ks, catalog):
                await lease.assert_owned()
                await _issue(kind, user, email, session)
    except Exception:
        await session.rollback()
        # Valid request shape always has the same response, including ambiguous
        # directory ownership, ineligible accounts, unavailable DB/Redis and SMTP.
    return dict(_ACCEPTED)


async def _locked(token, session, kind=None):
    if not isinstance(token, str) or not 32 <= len(token) <= 256:
        raise _error(410, "recovery_invalid")
    row = (
        await session.execute(
            select(AccountRecovery)
            .where(AccountRecovery.token_hash == _digest(token))
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.status != "pending" or (kind is not None and row.kind != kind):
        raise _error(410, "recovery_invalid")
    expiry = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expiry <= _now():
        raise _error(410, "recovery_invalid")
    return row


async def _bound(row, ks, catalog):
    try:
        user = await _provider_call(ks.users.get, row.user_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise _error(410, "recovery_invalid") from None
        raise
    if (
        _field(user, "id") != row.user_id
        or _field(user, "domain_id") != row.identity_domain_id
        or _field(user, "email") != row.original_email
        or not await _eligible(user, ks, catalog)
    ):
        raise _error(410, "recovery_invalid")
    # A duplicate introduced after issuance may never become email ownership proof.
    matches = await domain_iam._find_accounts(None, email=_email(row.original_email))
    if len(matches) != 1 or _field(matches[0], "id") != row.user_id:
        raise _error(410, "recovery_invalid")
    return user


@identity_roles._complete_mutation
async def inspect(token, session):
    await session.rollback()
    async with domain_iam._iam_write() as (lease, ks, catalog):
        row = await _locked(token, session)
        user = await _bound(row, ks, catalog)
        home = await _provider_call(ks.domains.get, row.identity_domain_id)
        result = {
            "kind": row.kind,
            "email": row.email,
            "identity_domain_id": row.identity_domain_id,
            "identity_domain_name": _field(home, "afterglow_display_name") or _field(home, "name", ""),
        }
        if row.kind == "username":
            result["username"] = _field(user, "name")
            await lease.assert_owned()
            row.status, row.consumed_at = "consumed", _now()
            await session.commit()
        return result


@identity_roles._complete_mutation
async def request_email_change(email, current_password, token_info, session):
    email = _email(email)
    if not current_password or len(current_password) > 1024:
        raise _error(422, "invalid_password")
    if not recovery_enabled():
        return dict(_ACCEPTED)
    await session.rollback()
    async with domain_iam._iam_write() as (lease, ks, catalog):
        uid, home = token_info.get("user_id"), token_info.get("identity_domain_id")
        if not uid or not home:
            raise _error(403, "recovery_ineligible")
        user = await _provider_call(ks.users.get, uid)
        if _field(user, "id") != uid or _field(user, "domain_id") != home or not await _eligible(user, ks, catalog):
            raise _error(403, "recovery_ineligible")
        # Reauthenticate the native exact home user, never a working-domain alias.
        proof = None
        try:
            proof = await asyncio.to_thread(
                keystone.authenticate, _field(user, "name"), current_password, "", home, unscoped_only=True
            )
            if proof.get("user_id") != uid or proof.get("identity_domain_id") != home:
                raise _error(403, "recovery_ineligible")
        except Unauthorized:
            raise _error(401, "password_rejected") from None
        except HTTPException:
            raise
        except Exception:
            raise _error(503, "recovery_unavailable") from None
        finally:
            if proof and proof.get("token"):
                await _provider_call(keystone.revoke_token, proof["token"])
        if not _field(user, "email"):
            raise _error(403, "recovery_ineligible")
        await _unique(_email(_field(user, "email")), uid)
        await _unique(email, uid)
        # Keep native exact old email, including case, in the binding.
        email = await domain_iam.password_policy(home, email, password=False)
        if _email(_field(user, "email")) == email:
            raise _error(409, "email_unchanged")
        if not await _address_allowed(email):
            return dict(_ACCEPTED)
        await lease.assert_owned()
        await _issue("email_change", user, email, session)
    return dict(_ACCEPTED)


@identity_roles._complete_mutation
async def complete(token, session, *, new_password=None, kind="password"):
    if kind not in {"password", "email_change"}:
        raise _error(422, "invalid_recovery_kind")
    if kind == "password" and (not isinstance(new_password, str) or not 12 <= len(new_password) <= 1024):
        raise _error(422, "invalid_password")
    await session.rollback()
    async with domain_iam._iam_write() as (lease, ks, catalog):
        row = await _locked(token, session, kind)
        await _bound(row, ks, catalog)
        if kind == "email_change":
            await _unique(row.email, row.user_id)
            await domain_iam.password_policy(row.identity_domain_id, row.email, password=False)
        await identity_roles._session_ready({row.user_id})
        await lease.assert_owned()
        # Commit consumption BEFORE dispatch; never infer failure means no native
        # effect. Invalidate every outstanding mutation proof for this account.
        await session.execute(
            update(AccountRecovery)
            .where(
                AccountRecovery.user_id == row.user_id,
                AccountRecovery.status == "pending",
                AccountRecovery.kind.in_(["password", "email_change"]),
                AccountRecovery.token_hash != row.token_hash,
            )
            .values(status="superseded", consumed_at=_now())
        )
        row.status, row.consumed_at = "dispatching", _now()
        await session.commit()
        native_failed = False
        sessions_failed = False
        try:
            attrs = (
                {"password": new_password, "afterglow_local_password": True}
                if kind == "password"
                else {"email": row.email, "afterglow_email_verified": True}
            )
            result = await identity_roles._write(lease, ks.users.update, row.user_id, **attrs)
            if _field(result, "id") != row.user_id or _field(result, "domain_id") != row.identity_domain_id:
                native_failed = True
            if kind == "email_change" and _field(result, "email") != row.email:
                native_failed = True
        except Exception:
            native_failed = True
        finally:
            # Required on known success AND unknown outcome; no native rollback.
            try:
                await session_store.revoke_user_sessions(row.user_id, revoke_keystone=True, strict_keystone=True)
                await domain_scope.invalidate_authority()
            except Exception:
                sessions_failed = True
        row.status = "outcome_unknown" if native_failed else "sessions_failed" if sessions_failed else "changed"
        await session.commit()
        if native_failed:
            raise _error(502, "recovery_outcome_unknown")
        if sessions_failed:
            raise _error(503, "recovery_sessions_failed")
    return {"status": "changed"}
