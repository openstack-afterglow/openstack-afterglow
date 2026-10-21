"""Canonical native identity selection and explicit, stable external association.

All writes run inside the shared identity graph lease. No service token is ever
returned as a user credential. Native federation must return the associated ID.
"""

from __future__ import annotations

import asyncio
import copy
from urllib.parse import quote

from fastapi import HTTPException
from keystoneauth1.exceptions.http import Unauthorized
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.services import domain_projects, identity_roles, keystone

_field = identity_roles._field


def _account_users(ks, domain_id, *, operation=None):
    """Complete native inventory plus exact resources, never lossy SDK extras."""
    from app.services.domain_auth import DomainAuthUnavailable
    from app.services.domain_iam import _account_rows

    try:
        return _account_rows(ks, domain_id, operation=operation)
    except Exception:
        raise DomainAuthUnavailable("Native account inventory is unavailable or incomplete") from None


def password_account(username: str, *, operation):
    """Resolve one canonical password account inside operator-native Accounts.

    Names and normalized email aliases share one domain-scoped candidate set.
    Never probe credentials or fall back to another native identity domain.
    """
    from app.services import account_spaces
    from app.services.domain_auth import DomainAuthConflict, normalize_email

    home = _field(account_spaces.shared_domain("account", operation=operation), "id")
    rows = _account_users(operation.ks, home, operation=operation)
    email = normalize_email(username).casefold() if "@" in username else ""
    matches = [row for row in rows if _field(row, "name") == username or (email and _email(row) == email)]
    if len(matches) > 1:
        raise DomainAuthConflict("Account identity is ambiguous", code="account_ambiguous")
    if not matches:
        raise Unauthorized(message="Account is unavailable")
    selected = matches[0]
    uid = _field(selected, "id")
    user = operation.get("users", uid)
    if _field(user, "id") != uid or _field(user, "enabled") is not True:
        raise Unauthorized(message="Account is unavailable")
    name = _field(user, "name")
    if not isinstance(name, str) or not name or _field(user, "domain_id") != home:
        raise Unauthorized(message="Account is unavailable")
    return {"id": uid, "name": name, "domain_id": home}


async def authenticate_password(account, password, *, operation, username=None):
    """One native attempt guarded by canonical username/home, not login aliases.

    Callers clear the same guard only after validating the exact native proof.
    Directory/policy/transport failures are not bad-password attempts.
    """
    from app.services import login_guard
    from app.utils.auth_diagnostics import authentication_step

    canonical_name, home = account["name"], account["domain_id"]
    with authentication_step("login_guard"):
        await login_guard.check_locked(canonical_name, home)
    if username is not None and username != canonical_name:
        raise Unauthorized(message="Canonical account username does not match")
    try:
        return await operation.run(
            keystone.authenticate,
            username=canonical_name,
            password=password,
            project_name="",
            domain_name=home,
            operation=operation,
            unscoped_only=True,
        )
    except keystone.PasswordRejected:
        await login_guard.record_failure(canonical_name, home)
        raise


def _email(user):
    from app.services.domain_auth import DomainAuthError, normalize_email

    raw = _field(user, "email", "") or ""
    if not raw:
        return ""
    try:
        return normalize_email(raw).casefold()
    except DomainAuthError:
        return ""


def _bindings(user):
    from app.services.domain_auth import DomainAuthUnavailable

    values = _field(user, "afterglow_external_identities", [])
    if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
        raise DomainAuthUnavailable("Native external identity metadata is invalid")
    return values


async def directory(ks, identity, row):
    """Fresh global email and issuer/subject ownership, before OS-FEDERATION."""
    from app.services.domain_auth import DomainAuthConflict

    rows = await asyncio.to_thread(_account_users, ks, None)
    email = identity.email.casefold()
    email_matches = [user for user in rows if _email(user) == email]
    stable = [
        user
        for user in rows
        if any(
            value.get("issuer") == identity.issuer and value.get("subject") == identity.subject
            for value in _bindings(user)
        )
    ]
    # The complete hydrated inventory also proves native tuple uniqueness. SDK
    # federated filters can omit extras or truncate before Python sees the rows.
    attached = [user for user in rows if has_native_binding(user, row, identity.subject)]
    if len(email_matches) > 1 or len(stable) > 1 or len(attached) > 1:
        raise DomainAuthConflict("Account identity is ambiguous", code="account_ambiguous")
    bound = stable[0] if stable else None
    # Existing legacy native associations need explicit canonical proof.
    if (
        attached
        and (bound is None or _field(attached[0], "id") != _field(bound, "id"))
        and (not email_matches or _field(email_matches[0], "id") != _field(attached[0], "id"))
    ):
        raise DomainAuthConflict("Native external identity requires reconciliation", code="native_binding_conflict")
    if bound and email_matches and _field(bound, "id") != _field(email_matches[0], "id"):
        raise DomainAuthConflict("External email belongs to another account", code="account_email_conflict")
    return bound, email_matches[0] if email_matches else None


def has_native_binding(user, row, subject):
    federated = _field(user, "federated", []) or []
    return any(
        isinstance(item, dict)
        and item.get("idp_id") == row.keystone_idp_id
        and any(
            isinstance(protocol, dict)
            and protocol.get("protocol_id") == row.keystone_protocol_id
            and protocol.get("unique_id") == quote(subject)
            for protocol in item.get("protocols", [])
        )
        for item in federated
    )


async def require_enrollment_complete(user):
    """Native activation alone cannot settle a journaled external enrollment."""
    from app.models.domain_iam import DomainEnrollment
    from app.services.domain_auth import DomainAuthUnavailable, _factory

    marker = _field(user, "afterglow_enrollment_id")
    if not marker:
        return  # Established links without an enrollment marker never need approval.
    try:
        async with _factory()() as session:
            enrollment = (
                await session.execute(select(DomainEnrollment).where(DomainEnrollment.token_hash == marker))
            ).scalar_one_or_none()
    except SQLAlchemyError:
        raise DomainAuthUnavailable("External enrollment settlement is unavailable") from None
    if enrollment is not None and enrollment.kind != "external":
        return  # Linking an existing local account does not enroll it again.
    if (
        enrollment is None
        or enrollment.status != "accepted"
        or enrollment.user_id != _field(user, "id")
        or enrollment.identity_domain_id != _field(user, "domain_id")
    ):
        raise DomainAuthUnavailable("External enrollment is not confirmed", code="external_enrollment_unconfirmed")


async def require_admission(user_id, domain_id, row, email, *, lease, ks, catalog, new=False):
    from app.services.account_spaces import domain_kind
    from app.services.domain_auth import DomainAuthConflict, DomainAuthDenied, provider_auto_join_allowed

    native_domain = await asyncio.to_thread(domain_projects._exact, ks.domains, domain_id)
    if domain_kind(native_domain) in {"account", "personal"}:
        raise DomainAuthDenied("Organization admission requires an organization", code="organization_domain_required")

    if not new:
        await require_enrollment_complete(await asyncio.to_thread(ks.users.get, user_id))
        try:
            await asyncio.to_thread(domain_projects.assert_membership, user_id, domain_id, ks=ks)
            return
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
    if not await provider_auto_join_allowed(domain_id, row.id, email):
        raise DomainAuthDenied("An invitation or existing membership is required", code="invitation_required")
    project = await asyncio.to_thread(domain_projects.default_project, domain_id, ks=ks)
    if project is None:
        raise DomainAuthConflict(
            "Domain Default must be prepared before auto-admission", code="domain_default_required"
        )
    if new:
        return  # authorization before creation; normal login adds reader to this existing Default
    await domain_projects._ensure_reader(lease, ks, catalog, project["id"], user_id)
    await domain_projects._sync(domain_id, lease, ks, catalog)
    await asyncio.to_thread(domain_projects.assert_membership, user_id, domain_id, ks=ks)


async def attach(user, row, identity, *, lease, ks, password_proven=False, explicit_proof=False):
    from app.services.domain_auth import DomainAuthConflict, DomainAuthUnavailable

    uid = _field(user, "id")
    full = await asyncio.to_thread(ks.users.get, uid)
    if _field(full, "id") != uid or _field(full, "enabled") is not True:
        raise DomainAuthConflict("Canonical account changed", code="account_changed")
    federated = copy.deepcopy(_field(full, "federated", []) or [])
    if not isinstance(federated, list):
        raise DomainAuthUnavailable("Native federation metadata is invalid")
    if not has_native_binding(full, row, identity.subject):
        item = next((item for item in federated if item.get("idp_id") == row.keystone_idp_id), None)
        if item is None:
            item = {"idp_id": row.keystone_idp_id, "protocols": []}
            federated.append(item)
        previous = [
            protocol for protocol in item["protocols"] if protocol.get("protocol_id") == row.keystone_protocol_id
        ]
        if previous:
            if not explicit_proof or any(value.get("issuer") == identity.issuer for value in _bindings(full)):
                raise DomainAuthConflict(
                    "Provider is already associated with another subject", code="native_binding_conflict"
                )
            # An exact canonical+external proof may migrate an untracked legacy
            # preferred-username association. Never replace a known stable link.
            item["protocols"] = [
                protocol for protocol in item["protocols"] if protocol.get("protocol_id") != row.keystone_protocol_id
            ]
        item["protocols"].append({"protocol_id": row.keystone_protocol_id, "unique_id": quote(identity.subject)})
    bindings = copy.deepcopy(_bindings(full))
    value = {"issuer": identity.issuer, "subject": identity.subject}
    if value not in bindings:
        bindings.append(value)
    fields = {"federated": federated, "afterglow_external_identities": bindings}
    if password_proven:
        fields["afterglow_local_password"] = True
    if (
        federated == (_field(full, "federated", []) or [])
        and bindings == _bindings(full)
        and (not password_proven or _field(full, "afterglow_local_password") is True)
    ):
        return full
    immutable = {key: _field(full, key) for key in ("domain_id", "name", "email", "default_project_id")}
    # Preserve password, home, email, username and saved project preference.
    await identity_roles._write(lease, ks.users.update, uid, **fields)
    checked = await asyncio.to_thread(ks.users.get, uid)
    if (
        _field(checked, "id") != uid
        or _field(checked, "enabled") is not True
        or any(_field(checked, key) != previous for key, previous in immutable.items())
        or not has_native_binding(checked, row, identity.subject)
        or value not in _bindings(checked)
        or (password_proven and _field(checked, "afterglow_local_password") is not True)
    ):
        raise DomainAuthUnavailable(
            "Native federation attachment was not confirmed", code="native_attachment_unconfirmed"
        )
    return checked


async def create_external(row, identity, *, lease, ks, catalog, admission_domain_id=None):
    from app.services import domain_iam
    from app.services.domain_auth import DomainAuthDenied, DomainAuthUnavailable

    try:
        user = await domain_iam.enroll_external(
            row, identity, lease=lease, ks=ks, catalog=catalog, admission_domain_id=admission_domain_id
        )
    except HTTPException as exc:
        if exc.status_code == 403 and exc.detail in ("signup_approval_pending", "signup_approval_rejected"):
            raise DomainAuthDenied("New account approval is required", code=exc.detail) from None
        raise
    home = _field(user, "domain_id")
    uid = _field(user, "id")
    from app.services import account_spaces

    account = await asyncio.to_thread(account_spaces.shared_domain, "account", ks=ks)
    if not uid or not isinstance(home, str) or home != _field(account, "id"):
        raise DomainAuthUnavailable("Native external account creation was not confirmed")
    checked = await asyncio.to_thread(ks.users.get, uid)
    if (
        _field(checked, "id") != uid
        or _field(checked, "domain_id") != home
        or _field(checked, "enabled") is not True
        or _email(checked) != identity.email.casefold()
        or {"issuer": identity.issuer, "subject": identity.subject} not in _bindings(checked)
        or not has_native_binding(checked, row, identity.subject)
        or _field(checked, "afterglow_local_password") is not False
    ):
        raise DomainAuthUnavailable("Native external account creation was not confirmed")
    await require_enrollment_complete(checked)
    return checked
