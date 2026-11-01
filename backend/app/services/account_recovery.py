"""Email-owned recovery, serialized with every first-party identity graph writer.

Delivery must finish before a proof is redeemable. Native mutations have a
committed dispatch fence: rejection, timeout, cancellation and process death
never make that token replayable. No password or plaintext token is journaled.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import math
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from keystoneauth1.exceptions.http import NotFound, Unauthorized
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
    if _external_credential(user):
        credential = await _initial_support(ks)
        if (await _initial_identity(credential, user))["password_state"] != "existing":
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


def _external_credential(user):
    return (
        bool(_field(user, "federated"))
        or bool(_field(user, "afterglow_external_identities"))
        or _field(user, "afterglow_local_password") is False
    )


async def _unique(email, user_id=None):
    matches = await domain_iam._find_accounts(None, email=email)
    if user_id is None:
        return matches[0] if len(matches) == 1 else None
    if any(_field(user, "id") != user_id for user in matches):
        raise _error(409, "email_in_use")


async def _issue(kind, user, email, session, *, native_identity_revision=None):
    token = secrets.token_urlsafe(32)
    row = AccountRecovery(
        token_hash=_digest(token),
        kind=kind,
        user_id=_field(user, "id"),
        identity_domain_id=_field(user, "domain_id"),
        original_email=_field(user, "email"),
        email=email,
        native_identity_revision=native_identity_revision,
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
            warning = (
                " A local password can bypass your identity provider's MFA and deactivation controls. "
                "Continue only if you accept this and sign in as the same external account."
                if kind == "password_create"
                else ""
            )
            delivered = await email_service.send_email(
                email,
                "Verify your account request",
                f'<p><a href="{html.escape(link, quote=True)}">Continue account recovery</a></p>'
                + (f"<p>{warning}</p>" if warning else ""),
                f"Continue account recovery: {link}\nThis link expires in one hour. Ignore it if you did not request it.{warning}",
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
                revision = None
                if kind == "password":
                    credential = await _initial_support(ks)
                    identity = await _initial_identity(credential, user)
                    if identity["password_state"] != "existing":
                        return dict(_ACCEPTED)
                    revision = identity["identity_revision"]
                await lease.assert_owned()
                await _issue(kind, user, email, session, native_identity_revision=revision)
    except Exception:
        await session.rollback()
        # Valid request shape always has the same response, including ambiguous
        # directory ownership, ineligible accounts, unavailable DB/Redis and SMTP.
    return dict(_ACCEPTED)


async def request_profile_password_recovery(token_info, session):
    # Target comes from the authenticated immutable subject, never form input.
    # Keep the public non-enumerating response even if mail/directory is down.
    try:
        uid, home = token_info.get("user_id"), token_info.get("identity_domain_id")
        ks = await _provider_call(keystone._get_admin_ks_client)
        user = await _provider_call(ks.users.get, uid)
        if _field(user, "id") != uid or _field(user, "domain_id") != home or _field(user, "enabled") is not True:
            return dict(_ACCEPTED)
        return await request_recovery("password", _field(user, "email"), session)
    except Exception:
        await session.rollback()
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
    if row.kind == "password":
        if not _valid_identity_revision(row.native_identity_revision):
            raise _error(410, "recovery_invalid")
        credential = await _initial_support(ks)
        identity = await _initial_identity(credential, user)
        if identity["password_state"] != "existing" or identity["identity_revision"] != row.native_identity_revision:
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
        user = (
            await _creation_bound(row, ks, catalog) if row.kind == "password_create" else await _bound(row, ks, catalog)
        )
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
        user = await _bound(row, ks, catalog)
        credential = None
        if kind == "password":
            credential = await _initial_support(ks)
            identity = await _initial_identity(credential, user)
            if (
                identity["password_state"] != "existing"
                or identity["identity_revision"] != row.native_identity_revision
            ):
                raise _error(410, "recovery_invalid")
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
                AccountRecovery.kind.in_(["password", "email_change", "password_create"]),
                AccountRecovery.token_hash != row.token_hash,
            )
            .values(status="superseded", consumed_at=_now())
        )
        row.status, row.consumed_at = "dispatching", _now()
        await session.commit()
        native_failed = False
        sessions_failed = False
        native_status = None
        try:
            await lease.assert_owned()
            if kind == "password":
                from urllib.parse import quote

                path = f"users/{quote(row.user_id, safe='')}/OS-AFTERGLOW/password-reset"
                body = {
                    "password": new_password,
                    "domain_id": row.identity_domain_id,
                    "email": row.original_email,
                    "identity_revision": row.native_identity_revision,
                }
                status, _ = await asyncio.to_thread(_initial_request, credential, "POST", path, body={"user": body})
                native_status = status
                native_failed = status != 204
            else:
                attrs = {"email": row.email, "afterglow_email_verified": True}
                result = await identity_roles._write(lease, ks.users.update, row.user_id, **attrs)
                if _field(result, "id") != row.user_id or _field(result, "domain_id") != row.identity_domain_id:
                    native_failed = True
                if kind == "email_change" and _field(result, "email") != row.email:
                    native_failed = True
        except Exception:
            native_failed = True
        finally:
            # Native conditional refusal happened before a credential write.
            # All other responses may be outcome-unknown and require revocation.
            if native_status not in {409, 412, 422}:
                try:
                    await session_store.revoke_user_sessions(row.user_id, revoke_keystone=True, strict_keystone=True)
                    await domain_scope.invalidate_authority()
                except Exception:
                    sessions_failed = True
        row.status = (
            "rejected"
            if native_status in {409, 412, 422}
            else "outcome_unknown"
            if native_failed
            else "sessions_failed"
            if sessions_failed
            else "changed"
        )
        await session.commit()
        if native_status in {409, 412}:
            raise _error(410, "recovery_invalid")
        if native_status == 422:
            raise _error(422, "invalid_password")
        if native_failed:
            raise _error(502, "recovery_outcome_unknown")
        if sessions_failed:
            raise _error(503, "recovery_sessions_failed")
    return {"status": "changed"}


_INITIAL_PASSWORD_REVISION = "first-password-galera-v2"
_CREATION_UNSETTLED = {"dispatching", "outcome_unknown", "sessions_failed"}


async def _creation_subject(user_id, home, ks, catalog, *, proof_eligible=True):
    if not isinstance(user_id, str) or not user_id or not isinstance(home, str) or not home:
        raise _error(403, "password_create_ineligible")
    user = await _provider_call(ks.users.get, user_id)
    domain = await _provider_call(ks.domains.get, home)
    if (
        _field(user, "id") != user_id
        or _field(user, "domain_id") != home
        or _field(user, "enabled") is not True
        or _field(domain, "id") != home
        or _field(domain, "enabled") is not True
        or _field(user, "name") == get_settings().os_username
    ):
        raise _error(403, "password_create_ineligible")
    assignments = await _provider_call(lambda: list(ks.role_assignments.list(user=user_id, effective=True)))
    expanded = project_service._expanded_role_ids(assignments, catalog, user_id)
    by_id = {item["id"]: item for item in catalog}
    if any(by_id[rid]["name"].casefold() == "service" for rid in expanded):
        raise _error(403, "password_create_ineligible")
    if proof_eligible:
        email = _email(_field(user, "email"))
        await domain_iam.password_policy(home, email)
        matches = await domain_iam._find_accounts(None, email=email)
        if len(matches) != 1 or _field(matches[0], "id") != user_id or _field(matches[0], "domain_id") != home:
            raise _error(409, "password_create_email_ambiguous")
    return user


async def _creation_actor(token_info, ks, catalog, *, proof_created_at=None):
    if token_info.get("auth_method") != "federated":
        raise _error(403, "password_create_external_session_required")
    uid, home = token_info.get("user_id"), token_info.get("identity_domain_id")
    user = await _creation_subject(uid, home, ks, catalog)
    proof = token_info.get("session_token")
    if not isinstance(proof, str) or not proof:
        raise _error(401, "password_create_session_invalid")
    refresh_jti = token_info.get("refresh_jti")
    if not isinstance(refresh_jti, str) or not refresh_jti:
        raise _error(401, "password_create_session_invalid")
    try:
        current = await session_store.get_session(refresh_jti)
    except Exception:
        raise _error(503, "password_create_session_unavailable") from None
    if not current or current.get("blacklisted"):
        raise _error(401, "password_create_session_invalid")
    if (
        current.get("user_id") != uid
        or current.get("identity_domain_id") != home
        or current.get("keystone_token") != proof
        or any(
            current.get(key) != token_info.get(key)
            for key in ("auth_method", "provider_id", "provider_revision", "provider_domain_id", "login_email")
        )
    ):
        raise _error(403, "password_create_session_mismatch")
    try:
        now = _now().timestamp()
        started = float(current["started_at"])
        expiry = float(current["exp"])
    except (KeyError, TypeError, ValueError, OverflowError):
        if proof_created_at is not None:
            raise _error(403, "password_create_reauthentication_required") from None
        raise _error(401, "password_create_session_invalid") from None
    if proof_created_at is not None:
        issued = proof_created_at if proof_created_at.tzinfo else proof_created_at.replace(tzinfo=UTC)
        # This proves a recent Afterglow/provider roundtrip, not IdP password
        # entry or MFA freshness. Equality fails: login must follow issuance.
        if (
            not math.isfinite(started)
            or not math.isfinite(now)
            or started <= issued.timestamp()
            or started > now
            or now - started > 15 * 60
        ):
            raise _error(403, "password_create_reauthentication_required")
    expired = (
        not all(math.isfinite(value) for value in (now, started, expiry))
        or now >= expiry
        or now >= started + get_settings().session_timeout_seconds
    )
    if expired:
        raise _error(401, "password_create_session_invalid")
    try:
        native = await asyncio.to_thread(ks.tokens.validate, proof, include_catalog=False)
        native_uid, native_home = native.user_id, native.user_domain_id
    except NotFound as exc:
        # Subject-token expiry/revocation is native404, not service-auth401.
        # A generic endpoint/proxy404 proves neither a valid nor invalid user.
        if exc.message.partition(" (HTTP ")[0] in keystone._NATIVE_INVALID_TOKEN_MESSAGES:
            raise _error(401, "password_create_session_invalid") from None
        raise _error(503, "password_create_session_unavailable") from None
    except Exception:
        raise _error(503, "password_create_session_unavailable") from None
    if native_uid != uid or native_home != home:
        raise _error(403, "password_create_session_mismatch")
    if _email(token_info.get("login_email")) != _email(_field(user, "email")):
        raise _error(403, "password_create_session_mismatch")
    # Reuse the actual provider revision/admission checks, not an external-login
    # flag as proof that the provider or native subject is still authorized.
    from app.api.identity.auth import _enforce_session_policy

    try:
        await _enforce_session_policy(
            token_info,
            {"user_id": uid, "identity_domain_id": home, "domain_id": home, "email": _field(user, "email")},
        )
    except domain_auth.DomainAuthError as exc:
        raise _error(exc.status_code, "password_create_ineligible") from None
    return user


def _initial_request(credential, method, path, *, body=None):
    settings = get_settings()
    transport = keystone.native_transport.create_session(timeout=30, verify=settings.ssl_verify)
    try:
        response = transport.request(
            f"{settings.os_auth_url.rstrip('/')}/{path}",
            method,
            json=body,
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
            payload = response.json() if response.status_code == 200 else None
            return response.status_code, payload
        finally:
            response.close()
    finally:
        transport.session.close()


async def _initial_support(ks):
    try:
        credential = await asyncio.to_thread(ks.session.get_token)
        if not isinstance(credential, str) or not credential:
            raise ValueError("missing native service credential")
        status, payload = await asyncio.to_thread(
            _initial_request, credential, "GET", "OS-AFTERGLOW/initial-password/capabilities"
        )
        if (
            status != 200
            or not isinstance(payload, dict)
            or payload.get("supported") is not True
            or payload.get("revision") != _INITIAL_PASSWORD_REVISION
        ):
            raise ValueError("unsupported native guard")
        return credential
    except Exception:
        raise _error(503, "password_create_native_unavailable") from None


def _valid_identity_revision(value):
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 20
        and value.isascii()
        and value.isdecimal()
        and (value == "0" or not value.startswith("0"))
        and int(value) <= 18446744073709551615
    )


async def _initial_identity(credential, user):
    from urllib.parse import quote

    try:
        status, payload = await asyncio.to_thread(
            _initial_request,
            credential,
            "GET",
            f"users/{quote(_field(user, 'id'), safe='')}/OS-AFTERGLOW/initial-password/identity",
        )
        identity = payload.get("user") if isinstance(payload, dict) else None
        if (
            status != 200
            or not isinstance(identity, dict)
            or identity.get("id") != _field(user, "id")
            or identity.get("domain_id") != _field(user, "domain_id")
            or identity.get("email") != _field(user, "email")
            or not _valid_identity_revision(identity.get("identity_revision"))
            or identity.get("password_state") not in {"existing", "absent"}
        ):
            raise ValueError("unavailable native identity revision")
        return identity
    except Exception:
        raise _error(503, "password_create_native_unavailable") from None


async def _creation_unsettled(user_id, session, *, lock=True):
    query = (
        select(AccountRecovery)
        .where(
            AccountRecovery.user_id == user_id,
            AccountRecovery.kind == "password_create",
            AccountRecovery.status.in_(_CREATION_UNSETTLED),
        )
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update()
    rows = (await session.execute(query)).scalars().all()
    return list(rows)


async def password_capability(token_info, session):
    conn = None
    try:
        uid, home = token_info.get("user_id"), token_info.get("identity_domain_id")
        if not uid or not home:
            return {"mode": "unavailable"}
        if token_info.get("auth_method") == "password":
            # This is only a form capability, never native write authority.
            # Current-password proof on POST is independent of admin/SMTP.
            return {"mode": "change"}
        # Display-only fresh snapshot: no graph lease and no SQL row locks.
        # POST revalidates every prerequisite under the identity mutation lease.
        ks = await _provider_call(keystone._get_admin_ks_client)
        user = await _provider_call(ks.users.get, uid)
        domain = await _provider_call(ks.domains.get, home)
        if (
            _field(user, "id") != uid
            or _field(user, "domain_id") != home
            or _field(user, "enabled") is not True
            or _field(domain, "id") != home
            or _field(domain, "enabled") is not True
        ):
            return {"mode": "unavailable"}
        if token_info.get("auth_method") != "federated" and not _external_credential(user):
            return {"mode": "change"}
        try:
            credential = await _initial_support(ks)
            identity = await _initial_identity(credential, user)
        except HTTPException:
            # A current-password form is safe even if absence cannot be proven.
            # Never offer first creation on an unavailable native observation.
            return {"mode": "change", "reason": "password_state_unknown"}
        if identity["password_state"] == "existing":
            return {"mode": "change"}
        if not recovery_enabled() or await _creation_unsettled(uid, session, lock=False):
            return {"mode": "unavailable"}
        conn = await _provider_call(keystone.get_admin_project_connection)
        catalog = await _provider_call(identity_roles.load_catalog, conn)
        await _creation_actor(token_info, ks, catalog)
        await identity_roles._session_ready({uid})
        return {"mode": "create"}
    except Exception:
        return {"mode": "unavailable"}
    finally:
        if conn is not None:
            await asyncio.to_thread(conn.close)


@identity_roles._complete_mutation
async def request_password_creation(token_info, session):
    if not recovery_enabled():
        raise _error(503, "password_create_email_unavailable")
    await session.rollback()
    async with domain_iam._iam_write() as (lease, ks, catalog):
        user = await _creation_actor(token_info, ks, catalog)
        uid = _field(user, "id")
        if await _creation_unsettled(uid, session):
            raise _error(409, "password_create_reconciliation_required")
        credential = await _initial_support(ks)
        identity = await _initial_identity(credential, user)
        if identity["password_state"] != "absent":
            raise _error(409, "password_already_exists")
        revision = identity["identity_revision"]
        await identity_roles._session_ready({uid})
        email = _email(_field(user, "email"))
        if not await _address_allowed(email):
            raise _error(429, "password_create_rate_limited")
        await lease.assert_owned()
        await session.execute(
            update(AccountRecovery)
            .where(
                AccountRecovery.user_id == uid,
                AccountRecovery.kind == "password_create",
                AccountRecovery.status == "pending",
            )
            .values(status="superseded", consumed_at=_now())
        )
        if not await _issue("password_create", user, email, session, native_identity_revision=revision):
            raise _error(503, "password_create_email_unavailable")
    return dict(_ACCEPTED)


async def _creation_bound(row, ks, catalog, token_info=None):
    if token_info is not None and (
        token_info.get("user_id") != row.user_id or token_info.get("identity_domain_id") != row.identity_domain_id
    ):
        raise _error(403, "password_create_session_mismatch")
    user = (
        await _creation_actor(token_info, ks, catalog, proof_created_at=row.created_at)
        if token_info is not None
        else await _creation_subject(row.user_id, row.identity_domain_id, ks, catalog)
    )
    if _field(user, "email") != row.original_email or _email(row.email) != _email(row.original_email):
        raise _error(410, "recovery_invalid")
    return user


async def _creation_revoke(user_id):
    await session_store.revoke_user_sessions(user_id, revoke_keystone=True, strict_keystone=True)
    await domain_scope.invalidate_authority()


@identity_roles._complete_mutation
async def complete_password_creation(token, new_password, token_info, session):
    from urllib.parse import quote

    if not isinstance(new_password, str) or not 12 <= len(new_password) <= 1024:
        raise _error(422, "invalid_password")
    await session.rollback()
    async with domain_iam._iam_write() as (lease, ks, catalog):
        row = await _locked(token, session, "password_create")
        if not _valid_identity_revision(row.native_identity_revision):
            raise _error(410, "recovery_invalid")
        user = await _creation_bound(row, ks, catalog, token_info)
        if await _creation_unsettled(row.user_id, session):
            raise _error(409, "password_create_reconciliation_required")
        credential = await _initial_support(ks)
        identity = await _initial_identity(credential, user)
        if identity["identity_revision"] != row.native_identity_revision:
            raise _error(410, "recovery_invalid")
        if identity["password_state"] != "absent":
            raise _error(409, "password_already_exists")
        await identity_roles._session_ready({row.user_id})
        await lease.assert_owned()
        await session.execute(
            update(AccountRecovery)
            .where(
                AccountRecovery.user_id == row.user_id,
                AccountRecovery.kind.in_(["password_create", "password", "email_change"]),
                AccountRecovery.status == "pending",
                AccountRecovery.token_hash != row.token_hash,
            )
            .values(status="superseded", consumed_at=_now())
        )
        row.status, row.consumed_at = "dispatching", _now()
        await session.commit()
        status = None
        try:
            await lease.assert_owned()
            status, _ = await asyncio.to_thread(
                _initial_request,
                credential,
                "POST",
                f"users/{quote(row.user_id, safe='')}/OS-AFTERGLOW/initial-password",
                body={
                    "user": {
                        "password": new_password,
                        "domain_id": row.identity_domain_id,
                        "email": row.original_email,
                        "identity_revision": row.native_identity_revision,
                    }
                },
            )
        except Exception:
            # Never attach a transport exception: it can contain the password.
            pass
        sessions_failed = False
        # Native contract reserves 422 solely for explicit password validation
        # before manager.update_user; all manager/DB-stage failures stay unknown.
        if status not in {409, 412, 422}:
            try:
                await _creation_revoke(row.user_id)
            except Exception:
                sessions_failed = True
        if status == 409:
            row.status = "existing"
        elif status == 412:
            row.status = "identity_changed"
        elif status == 422:
            row.status = "invalid_password"
        elif status != 204:
            row.status = "outcome_unknown"
        else:
            row.status = "sessions_failed" if sessions_failed else "created"
        try:
            await session.commit()
        except Exception:
            # The committed dispatch fence survives even if final journaling
            # fails. A known native response must never make the proof reusable.
            await session.rollback()
            raise _error(502, "password_create_outcome_unknown") from None
        if status == 409:
            raise _error(409, "password_already_exists")
        if status == 412:
            raise _error(409, "password_create_identity_changed")
        if status == 422:
            raise _error(422, "password_create_invalid_password")
        if status != 204:
            raise _error(502, "password_create_outcome_unknown")
        if sessions_failed:
            raise _error(503, "password_create_sessions_failed")
    return {"status": "created"}


@identity_roles._complete_mutation
async def password_creation_operations(user_id, home, session):
    await session.rollback()
    async with domain_iam._iam_write() as (_, ks, catalog):
        await _creation_subject(user_id, home, ks, catalog, proof_eligible=False)
        rows = await _creation_unsettled(user_id, session)
        return {
            "operations": [
                {"operation_id": row.token_hash, "status": row.status, "created_at": row.created_at}
                for row in rows
                if row.identity_domain_id == home
            ]
        }


@identity_roles._complete_mutation
async def settle_password_creation(
    user_id, home, operation_id, resolution, evidence, native_calls_settled, actor, session
):
    from app.models.activity import ActivityLog

    if actor.get("_live_system_admin") is not True:
        raise _error(403, "system_admin_required")
    if native_calls_settled is not True or resolution not in {"existing", "retry"} or not evidence.strip():
        raise _error(422, "password_create_settlement_invalid")
    await session.rollback()
    async with domain_iam._iam_write() as (lease, ks, catalog):
        user = await _creation_subject(user_id, home, ks, catalog, proof_eligible=False)
        await _initial_support(ks)
        rows = await _creation_unsettled(user_id, session)
        row = next((item for item in rows if item.token_hash == operation_id and item.identity_domain_id == home), None)
        if row is None:
            raise _error(409, "password_create_settlement_invalid")
        marker = _field(user, "afterglow_local_password")
        if (resolution == "existing" and marker is not True) or (resolution == "retry" and marker is not False):
            raise _error(409, "password_create_settlement_marker_mismatch")
        # This only settles an operator-reconciled journal. Marker true is not
        # proof that the lost request's submitted password is effective; marker
        # false is not absence proof. Retry still requires a new email proof and
        # the native atomic guard, never replay of the consumed operation.
        await identity_roles._session_ready({user_id})
        await _creation_revoke(user_id)
        await lease.assert_owned()
        # Same transaction as release: unlike activity.record this audit is not
        # best effort. No password, bearer proof or native response is retained.
        session.add(
            ActivityLog(
                project_id=actor.get("project_id", ""),
                user_id=actor["user_id"],
                username=actor.get("username", ""),
                resource_type="user",
                resource_id=user_id,
                action="password_creation_settle",
                status="success",
                service="keystone",
                source="afterglow",
                extra={
                    "operation_id": operation_id,
                    "identity_domain_id": home,
                    "resolution": resolution,
                    "evidence": evidence,
                    "native_calls_settled": True,
                },
            )
        )
        row.status = "settled_existing" if resolution == "existing" else "settled_retry"
        await session.commit()
    return {"status": "settled", "resolution": resolution}
