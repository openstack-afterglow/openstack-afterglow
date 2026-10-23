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
    """Fresh canonical selection; stable/native ownership is always global.

    Operator-registry OIDC email only proposes an Accounts confirmation target.
    Tenant-managed providers require account proof, never global email trust.
    """
    from app.services import account_spaces
    from app.services.domain_auth import _CONFIG_PROVIDER_PREFIX, DomainAuthConflict, DomainAuthDenied

    await require_transfer_resolved(identity)
    rows = await asyncio.to_thread(_account_users, ks, None)
    email = identity.email.casefold()
    email_matches = [user for user in rows if _email(user) == email]
    accounts_matches = []
    if row.kind == "oidc" and row.id.startswith(_CONFIG_PROVIDER_PREFIX):
        account = await asyncio.to_thread(account_spaces.shared_domain, "account", ks=ks)
        home = _field(account, "id")
        accounts_matches = [user for user in email_matches if _field(user, "domain_id") == home]
        # Legacy-only email is never an operator account-entry target. Global
        # stable/native ownership below still fences every identity domain.
        email_matches = accounts_matches
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
    transfer = None
    if (
        bound is not None
        and row.kind == "oidc"
        and row.id.startswith(_CONFIG_PROVIDER_PREFIX)
        and _field(bound, "domain_id") != home
    ):
        source_domain = await asyncio.to_thread(ks.domains.get, _field(bound, "domain_id"))
        if (
            _field(source_domain, "id") == "default"
            and _field(source_domain, "name") == "Default"
            and _field(source_domain, "enabled") is True
            and _field(bound, "enabled") is True
            and _email(bound) == email
            and attached
            and _field(attached[0], "id") == _field(bound, "id")
        ):
            transfer, bound = bound, None
        else:
            raise DomainAuthConflict(
                "External identity belongs to a non-Accounts home",
                code="account_email_conflict" if email_matches else "native_binding_conflict",
            )
    # Existing legacy native associations need explicit canonical proof.
    if (
        attached
        and transfer is None
        and (bound is None or _field(attached[0], "id") != _field(bound, "id"))
        and (not email_matches or _field(email_matches[0], "id") != _field(attached[0], "id"))
    ):
        raise DomainAuthConflict("Native external identity requires reconciliation", code="native_binding_conflict")
    if bound and email_matches and _field(bound, "id") != _field(email_matches[0], "id"):
        raise DomainAuthConflict("External email belongs to another account", code="account_email_conflict")
    if accounts_matches:
        if _field(accounts_matches[0], "enabled") is not True:
            raise DomainAuthDenied("Account is disabled", code="account_disabled")
        if bound is None:
            protocols = _field(accounts_matches[0], "federated", []) or []
            if any(
                item.get("idp_id") == row.keystone_idp_id
                and any(
                    protocol.get("protocol_id") == row.keystone_protocol_id
                    and protocol.get("unique_id") != quote(identity.subject)
                    for protocol in item.get("protocols", [])
                )
                for item in protocols
            ):
                raise DomainAuthConflict(
                    "Provider is already associated with another subject", code="native_binding_conflict"
                )
    return bound, email_matches[0] if email_matches else None, transfer


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
    from app.services.domain_auth import (
        DomainAuthConflict,
        DomainAuthDenied,
        enforce_email,
        get_policy,
        provider_auto_join_allowed,
    )

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
    # A saved manager policy may narrow operator autojoin, never authorize it.
    policy = await get_policy(domain_id)
    if policy.configured:
        enforce_email(policy, email, signup=True)
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
    home = _field(user, "domain_id")
    full = await asyncio.to_thread(ks.users.get, uid)
    if _field(full, "id") != uid or _field(full, "enabled") is not True or _field(full, "domain_id") != home:
        raise DomainAuthConflict("Canonical account changed", code="account_changed")
    if _email(full) != identity.email.casefold():
        raise DomainAuthConflict("Canonical email ownership changed", code="account_changed")
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


async def create_external(row, identity, *, lease, ks, catalog, admission_domain_id=None, confirmed_entry=False):
    from app.services import domain_iam
    from app.services.domain_auth import DomainAuthDenied, DomainAuthUnavailable

    try:
        user = await domain_iam.enroll_external(
            row,
            identity,
            lease=lease,
            ks=ks,
            catalog=catalog,
            admission_domain_id=admission_domain_id,
            confirmed_entry=confirmed_entry,
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


def _transfer_key(identity):
    import hashlib

    return hashlib.sha256((identity.issuer + "\x00" + identity.subject).encode()).hexdigest()


def _identity_snapshot(user):
    return {
        "id": _field(user, "id"),
        "domain_id": _field(user, "domain_id"),
        "email": _email(user),
        "name": _field(user, "name"),
        "federated": copy.deepcopy(_field(user, "federated", []) or []),
        "afterglow_external_identities": copy.deepcopy(_bindings(user)),
    }


def _without_binding(snapshot, row, identity):
    result = copy.deepcopy(snapshot)
    result["afterglow_external_identities"] = [
        value
        for value in result["afterglow_external_identities"]
        if not (value.get("issuer") == identity.issuer and value.get("subject") == identity.subject)
    ]
    federated = []
    for item in result["federated"]:
        if item.get("idp_id") == row.keystone_idp_id:
            item["protocols"] = [
                protocol
                for protocol in item.get("protocols", [])
                if not (
                    protocol.get("protocol_id") == row.keystone_protocol_id
                    and protocol.get("unique_id") == quote(identity.subject)
                )
            ]
            if not item["protocols"]:
                continue
        federated.append(item)
    result["federated"] = federated
    return result


def _seal_transfer(key, snapshot):
    import base64
    import json
    import os

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from app.services.k3s_crypto import derive_encryption_subkey

    nonce = os.urandom(12)
    ciphertext = AESGCM(derive_encryption_subkey(b"account_identity_transfer")).encrypt(
        nonce, json.dumps(snapshot).encode(), key.encode()
    )
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def _open_transfer(key, ciphertext):
    import base64
    import json

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from app.services.domain_auth import DomainAuthUnavailable
    from app.services.k3s_crypto import derive_encryption_subkey

    try:
        raw = base64.urlsafe_b64decode(ciphertext)
        return json.loads(
            AESGCM(derive_encryption_subkey(b"account_identity_transfer")).decrypt(raw[:12], raw[12:], key.encode())
        )
    except Exception:
        raise DomainAuthUnavailable(
            "Identity transfer journal is unavailable", code="identity_transfer_recovery_required"
        ) from None


async def _transfer_record(identity):
    from app.models.account_spaces import AccountIdentityTransfer
    from app.services.domain_auth import DomainAuthUnavailable, _factory

    try:
        async with _factory()() as session:
            return await session.get(AccountIdentityTransfer, _transfer_key(identity))
    except SQLAlchemyError:
        raise DomainAuthUnavailable("Identity transfer journal is unavailable") from None


async def require_transfer_resolved(identity):
    from app.services.domain_auth import DomainAuthUnavailable

    journal = await _transfer_record(identity)
    if journal is not None and journal.status not in {"committed", "rolled_back"}:
        raise DomainAuthUnavailable("Identity transfer requires recovery", code="identity_transfer_recovery_required")


async def assert_user_transfer_resolved(user_id):
    """Identity deletion cannot strand a pending native association transfer.

    Callers hold the shared graph lease, as do transfer begin/recovery writes.
    Keep completed encrypted receipts; they are not native user ownership.
    """
    from app.models.account_spaces import AccountIdentityTransfer
    from app.services.domain_auth import DomainAuthUnavailable, _factory

    try:
        async with _factory()() as session:
            query = (
                select(AccountIdentityTransfer.binding_key)
                .where(
                    AccountIdentityTransfer.status.notin_(("committed", "rolled_back")),
                    (AccountIdentityTransfer.source_user_id == user_id)
                    | (AccountIdentityTransfer.target_user_id == user_id),
                )
                .limit(1)
            )
            if (await session.execute(query)).first() is not None:
                raise HTTPException(409, "identity_transfer_recovery_required")
    except SQLAlchemyError:
        raise DomainAuthUnavailable("Identity transfer journal is unavailable") from None


async def _save_transfer(journal, *, lease):
    from datetime import UTC, datetime

    from app.services.domain_auth import DomainAuthUnavailable, _factory

    try:
        async with _factory()() as session:
            journal.updated_at = datetime.now(UTC)
            await session.merge(journal)
            await lease.assert_owned()
            await session.commit()
    except SQLAlchemyError:
        raise DomainAuthUnavailable("Identity transfer journal is unavailable") from None


async def _write_identity_snapshot(snapshot, *, lease, ks):
    from app.services.domain_auth import DomainAuthUnavailable

    if not snapshot["federated"]:
        current = await asyncio.to_thread(ks.users.get, snapshot["id"])
        if _field(current, "federated", []):
            # Keystone treats [] as "leave existing associations unchanged".
            # Refuse before stripping stable metadata while native links survive.
            raise DomainAuthUnavailable(
                "Last native association requires operator unlink", code="identity_transfer_recovery_required"
            )

    await identity_roles._write(
        lease,
        ks.users.update,
        snapshot["id"],
        federated=snapshot["federated"],
        afterglow_external_identities=snapshot["afterglow_external_identities"],
    )
    checked = await asyncio.to_thread(ks.users.get, snapshot["id"])
    if _identity_snapshot(checked) != snapshot or _field(checked, "enabled") is not True:
        raise DomainAuthUnavailable(
            "Identity transfer write was not confirmed", code="identity_transfer_recovery_required"
        )


def require_supported_identity_transfer(source, row, identity):
    from app.services.domain_auth import DomainAuthConflict

    detached = _without_binding(_identity_snapshot(source), row, identity)
    if not detached["federated"]:
        raise DomainAuthConflict(
            "Keystone cannot remove the last federation association through user PATCH; operator unlink is required",
            code="native_binding_conflict",
        )
    return detached


async def begin_identity_transfer(source, target, row, identity, *, lease, ks):
    from app.models.account_spaces import AccountIdentityTransfer

    detached = require_supported_identity_transfer(source, row, identity)

    snapshot = {
        "source": _identity_snapshot(source),
        "target": _identity_snapshot(target) if target is not None else None,
        "idp_id": row.keystone_idp_id,
        "protocol_id": row.keystone_protocol_id,
    }
    key = _transfer_key(identity)
    journal = AccountIdentityTransfer(
        binding_key=key,
        status="applying",
        source_user_id=_field(source, "id"),
        target_user_id=_field(target, "id") if target is not None else None,
        snapshot_ciphertext=_seal_transfer(key, snapshot),
    )
    await _save_transfer(journal, lease=lease)
    await _write_identity_snapshot(detached, lease=lease, ks=ks)
    journal.status = "detached"
    await _save_transfer(journal, lease=lease)
    return journal


async def confirm_identity_transfer(journal, user, row, identity, *, lease, ks):
    snapshot = _open_transfer(journal.binding_key, journal.snapshot_ciphertext)
    from app.services.domain_auth import DomainAuthUnavailable

    source = await asyncio.to_thread(ks.users.get, journal.source_user_id)
    target = await asyncio.to_thread(ks.users.get, _field(user, "id"))
    if (
        _identity_snapshot(source) != _without_binding(snapshot["source"], row, identity)
        or _field(source, "enabled") is not True
        or _identity_snapshot(target) != _identity_snapshot(user)
        or _field(target, "enabled") is not True
        or not has_native_binding(target, row, identity.subject)
        or {"issuer": identity.issuer, "subject": identity.subject} not in _bindings(target)
    ):
        raise DomainAuthUnavailable("Identity transfer ownership changed", code="identity_transfer_recovery_required")
    snapshot["target_after"] = _identity_snapshot(user)
    journal.target_user_id = _field(user, "id")
    journal.snapshot_ciphertext = _seal_transfer(journal.binding_key, snapshot)
    journal.status = "attached"
    await _save_transfer(journal, lease=lease)


async def commit_identity_transfer(journal, user_id, *, lease):
    journal.target_user_id, journal.status = user_id, "committed"
    await _save_transfer(journal, lease=lease)


async def recover_identity_transfer(row, identity, *, lease, ks, native_writes_settled=False):
    """Roll back only exact journal-owned identity fields; preserve all other native state.

    Unconfirmed calls/process death require explicit operator settlement, not a
    fresh OAuth proof or an instantaneous GET. Known-confirmed native writes
    may compensate after a later canonical-token failure.
    """
    from types import SimpleNamespace

    from app.services.domain_auth import DomainAuthUnavailable

    journal = await _transfer_record(identity)
    if journal is None or journal.status in {"committed", "rolled_back"}:
        return
    from app.services.domain_auth import _CONFIG_PROVIDER_PREFIX

    if row.kind != "oidc" or not row.id.startswith(_CONFIG_PROVIDER_PREFIX):
        raise DomainAuthUnavailable("Identity transfer requires recovery", code="identity_transfer_recovery_required")
    if journal.status != "attached" and native_writes_settled is not True:
        journal.status = "recovery_required"
        await _save_transfer(journal, lease=lease)
        raise DomainAuthUnavailable(
            "Native identity writes need explicit settlement", code="identity_transfer_recovery_required"
        )
    snapshot = _open_transfer(journal.binding_key, journal.snapshot_ciphertext)
    native_row = SimpleNamespace(keystone_idp_id=snapshot["idp_id"], keystone_protocol_id=snapshot["protocol_id"])
    journal.status = "restoring"
    await _save_transfer(journal, lease=lease)
    try:
        source = await asyncio.to_thread(ks.users.get, journal.source_user_id)
        original = snapshot["source"]
        current = _identity_snapshot(source)
        if _field(source, "enabled") is not True or current not in (
            original,
            _without_binding(original, native_row, identity),
        ):
            raise ValueError("Source identity changed")
        rows = await asyncio.to_thread(_account_users, ks, None)
        owners = [
            user
            for user in rows
            if _field(user, "id") != journal.source_user_id
            and (
                any(
                    value.get("issuer") == identity.issuer and value.get("subject") == identity.subject
                    for value in _bindings(user)
                )
                or has_native_binding(user, native_row, identity.subject)
            )
        ]
        if len(owners) > 1:
            raise ValueError("Target ownership ambiguous")
        target_before = snapshot["target"]
        if owners:
            target = owners[0]
            current_target = _identity_snapshot(target)
            if snapshot.get("target_after") is not None and current_target not in (
                snapshot["target_after"],
                target_before,
            ):
                raise ValueError("Confirmed target identity changed")
            if target_before is not None:
                if _without_binding(current_target, native_row, identity) != target_before:
                    raise ValueError("Target identity changed")
                restore_target = target_before
            else:
                from app.services import account_spaces

                account = await asyncio.to_thread(account_spaces.shared_domain, "account", ks=ks)
                if (
                    current_target["domain_id"] != _field(account, "id")
                    or current_target["email"] != identity.email.casefold()
                ):
                    raise ValueError("Target identity changed")
                if (
                    not _field(target, "afterglow_enrollment_id")
                    or _field(target, "afterglow_local_password") is not False
                ):
                    raise ValueError("Target creation provenance unavailable")
                await require_enrollment_complete(target)
                restore_target = _without_binding(current_target, native_row, identity)
            await _write_identity_snapshot(restore_target, lease=lease, ks=ks)
        elif target_before is not None:
            target = await asyncio.to_thread(ks.users.get, target_before["id"])
            if _identity_snapshot(target) != target_before:
                raise ValueError("Target identity changed")
        if current != original:
            await _write_identity_snapshot(original, lease=lease, ks=ks)
        journal.status = "rolled_back"
        await _save_transfer(journal, lease=lease)
    except BaseException as exc:
        journal.status = "recovery_required"
        await _save_transfer(journal, lease=lease)
        raise DomainAuthUnavailable(
            "Identity transfer requires recovery", code="identity_transfer_recovery_required"
        ) from exc
