"""Future-only policy and one-use approvals, serialized by the identity graph lease.

Enrollment callers hold the outer graph lease across admission, native effects,
and consumption. This module never stores credentials or performs native writes.
"""

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.common.errors import public_service_error
from app.config import get_settings
from app.database import get_session_factory
from app.models.enrollment_policy import EnrollmentPolicy, EnrollmentPolicyUpdate, SignupRequest
from app.services import activity, identity_roles, quota_native

_CORE_FIELDS = {
    "compute": ("instances", "cores", "ram"),
    "volume": ("volumes", "snapshots", "gigabytes"),
    "network": tuple(quota_native.QUOTA_FIELDS["network"]),
    "file_storage": ("shares", "share_gigabytes", "share_snapshots", "share_snapshot_gigabytes", "share_networks"),
}

# Missing policy only: customized policy and frozen intents remain authoritative.
PERSONAL_DEFAULT_QUOTAS = {
    "instances": 2,
    "cores": 2,
    "ram": 4096,
    "volumes": 10,
    "snapshots": 10,
    "gigabytes": 1024,
    "network": 2,
    "subnet": 2,
    "port": 10,
    "router": 1,
    "floatingip": 1,
    "security_group": 5,
    "security_group_rule": 100,
}


@asynccontextmanager
async def _session(session=None):
    try:
        if session is not None:
            yield session
        else:
            factory = get_session_factory()
            if factory is None:
                raise public_service_error(503, "enrollment_policy_storage_unavailable")
            async with factory() as owned:
                yield owned
    except SQLAlchemyError as exc:
        raise public_service_error(503, "enrollment_policy_storage_unavailable") from exc


def _limits(values):
    keys = {key for fields in quota_native.QUOTA_FIELDS.values() for key in fields}
    if not isinstance(values, dict) or any(
        key not in keys or type(value) is not int or value < -1 for key, value in values.items()
    ):
        raise HTTPException(422, "quota_values_invalid")
    return dict(values)


def _fields():
    return {
        section: list(fields)
        for section, fields in quota_native.QUOTA_FIELDS.items()
        if section != "file_storage" or get_settings().service_manila_enabled
    }


def _policy_dto(row):
    settings = get_settings()
    quotas = (
        _limits(row.personal_quotas)
        if row is not None
        else {**{key: 0 for section in _fields() for key in _CORE_FIELDS[section]}, **PERSONAL_DEFAULT_QUOTAS}
    )
    if row is not None and (row.approval_mode not in {"auto", "admin"} or row.revision < 1):
        raise public_service_error(503, "enrollment_policy_invalid")
    return {
        "revision": row.revision if row is not None else 0,
        "public_signup_enabled": row.public_signup_enabled if row is not None else settings.auth.public_signup_enabled,
        "approval_mode": row.approval_mode if row is not None else "auto",
        "personal_quotas": quotas,
        "quota_fields": _fields(),
        "defaults_future_only": True,
        "personal_quota_source": "administrator" if row is not None else "source_defaults",
        "source_default_personal_quotas": dict(PERSONAL_DEFAULT_QUOTAS),
        "smtp_configured": bool(
            settings.smtp_enabled and settings.smtp_host and settings.smtp_from_address and settings.frontend_base_url
        ),
    }


async def read_policy(*, session=None):
    """Only an absent singleton falls back to config; unavailable SQL fails closed."""
    async with _session(session) as sql:
        row = (await sql.execute(select(EnrollmentPolicy).where(EnrollmentPolicy.id == 1))).scalar_one_or_none()
        return _policy_dto(row)


async def _audit(token_info, action, resource_id, *, extra=None, status="success"):
    await activity.record(
        project_id=token_info.get("project_id", ""),
        user_id=token_info["user_id"],
        username=token_info.get("username", ""),
        resource_type="enrollment_policy",
        action=action,
        status=status,
        resource_id=resource_id,
        extra=extra,
    )


@identity_roles._complete_mutation
async def update_policy(conn, attrs, *, token_info):
    req = EnrollmentPolicyUpdate.model_validate(attrs)
    quotas = _limits(req.personal_quotas)
    async with identity_roles._graph_lock(conn) as lease:
        async with _session() as sql:
            values = {
                "revision": req.revision + 1,
                "public_signup_enabled": req.public_signup_enabled,
                "approval_mode": req.approval_mode,
                "personal_quotas": quotas,
                "updated_by_user_id": token_info["user_id"],
                "updated_at": datetime.now(UTC),
            }
            await lease.assert_owned()
            if req.revision == 0:
                sql.add(EnrollmentPolicy(id=1, **values))
                try:
                    await sql.flush()
                except IntegrityError as exc:
                    await sql.rollback()
                    raise HTTPException(409, "enrollment_policy_revision_conflict") from exc
            else:
                result = await sql.execute(
                    update(EnrollmentPolicy)
                    .where(EnrollmentPolicy.id == 1, EnrollmentPolicy.revision == req.revision)
                    .values(**values)
                )
                if result.rowcount != 1:
                    raise HTTPException(409, "enrollment_policy_revision_conflict")
            await sql.commit()
            await lease.assert_owned()
            result = await read_policy(session=sql)
        await _audit(token_info, "enrollment_policy.update", "global", extra={"revision": result["revision"]})
        return result


def _hash(parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def _identity(source, email, issuer, subject, domain_id, provider_id):
    if source not in {"email", "oidc", "github"} or not isinstance(email, str) or not 3 <= len(email) <= 255:
        raise HTTPException(422, "signup_identity_invalid")
    if email != email.strip() or "@" not in email or any(ord(char) < 32 for char in email):
        raise HTTPException(422, "signup_identity_invalid")
    if any(
        value is not None and (not isinstance(value, str) or not 1 <= len(value) <= 64)
        for value in (domain_id, provider_id)
    ):
        raise HTTPException(422, "signup_identity_invalid")
    if source == "email":
        if issuer or subject or provider_id is not None or domain_id is not None:
            raise HTTPException(422, "signup_identity_invalid")
        identity = [source, email]
    else:
        if not isinstance(issuer, str) or not issuer or not isinstance(subject, str) or not subject:
            raise HTTPException(422, "signup_identity_invalid")
        identity = [source, issuer, subject]
    return _hash(identity), _hash([source, email, issuer, subject, domain_id, provider_id])


@identity_roles._complete_mutation
async def require_signup_approval(session, *, source, email, issuer="", subject="", domain_id=None, provider_id=None):
    """Caller supplies a verified identity and holds the outer graph lease.

    Stable identity is unique independently of mutable email or organization.
    Changing the binding cannot create a second request inheriting a decision.
    Pending creation commits before the deliberate 403, surviving caller rollback.
    """
    from app.services.domain_auth import DomainAuthError, normalize_email

    try:
        email = normalize_email(email).casefold()
    except DomainAuthError as exc:
        raise HTTPException(422, "signup_identity_invalid") from exc
    identity_hash, binding_hash = _identity(source, email, issuer, subject, domain_id, provider_id)
    async with _session(session) as sql:
        row = (
            await sql.execute(
                select(SignupRequest)
                .where(SignupRequest.identity_hash == identity_hash)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if row is None:
            if (await read_policy(session=sql))["approval_mode"] == "auto":
                return None
            row = SignupRequest(
                id=str(uuid4()),
                source=source,
                identity_hash=identity_hash,
                binding_hash=binding_hash,
                email=email,
                domain_id=domain_id,
                provider_id=provider_id,
                status="pending",
            )
            sql.add(row)
            try:
                await sql.commit()
            except IntegrityError as exc:
                await sql.rollback()
                raise HTTPException(409, "signup_approval_conflict") from exc
        if (
            row.binding_hash != binding_hash
            or row.email != email
            or row.domain_id != domain_id
            or row.provider_id != provider_id
        ):
            raise HTTPException(409, "signup_approval_identity_mismatch")
        if row.status == "approved":
            return row.id
        if row.status == "pending":
            raise HTTPException(403, "signup_approval_pending")
        if row.status == "rejected":
            raise HTTPException(403, "signup_approval_rejected")
        raise HTTPException(409, "signup_approval_consumed")


@identity_roles._complete_mutation
async def consume_approval(session, request_id, *, user_id):
    if request_id is None:
        return
    if not isinstance(user_id, str) or not 1 <= len(user_id) <= 64:
        raise HTTPException(422, "signup_user_invalid")
    async with _session(session) as sql:
        result = await sql.execute(
            update(SignupRequest)
            .where(SignupRequest.id == request_id, SignupRequest.status == "approved")
            .values(status="consumed", consumed_by_user_id=user_id, consumed_at=datetime.now(UTC))
        )
        if result.rowcount != 1:
            raise HTTPException(409, "signup_approval_not_usable")
        await sql.commit()


def _timestamp(value):
    return value.replace(tzinfo=UTC).isoformat() if value is not None else None


def request_dto(row):
    return {
        "id": row.id,
        "source": row.source,
        "email": row.email,
        "domain_id": row.domain_id,
        "provider_id": row.provider_id,
        "status": row.status,
        "created_at": _timestamp(row.created_at),
        "reviewed_at": _timestamp(row.reviewed_at),
        "reviewed_by_user_id": row.reviewed_by_user_id,
    }


def _request_id(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(422, "signup_request_id_invalid") from exc
    return value


async def list_requests(*, status="pending", cursor=None):
    if status not in {"pending", "approved", "rejected", "all"}:
        raise HTTPException(422, "signup_request_status_invalid")
    query = select(SignupRequest).order_by(SignupRequest.id).limit(51)
    if status != "all":
        query = query.where(SignupRequest.status == status)
    if cursor is not None:
        query = query.where(SignupRequest.id > _request_id(cursor))
    async with _session() as sql:
        rows = list((await sql.execute(query)).scalars())
        return {
            "items": [request_dto(row) for row in rows[:50]],
            "next_cursor": rows[49].id if len(rows) > 50 else None,
        }


@identity_roles._complete_mutation
async def review_request(conn, request_id, decision, *, token_info):
    request_id = _request_id(request_id)
    if decision not in {"approved", "rejected"}:
        raise HTTPException(422, "signup_review_invalid")
    async with identity_roles._graph_lock(conn) as lease, _session() as sql:
        row = (
            await sql.execute(select(SignupRequest).where(SignupRequest.id == request_id).with_for_update())
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "signup_request_not_found")
        if row.status == decision:
            return request_dto(row)
        if row.status != "pending":
            raise HTTPException(409, "signup_request_already_reviewed")
        await lease.assert_owned()
        result = await sql.execute(
            update(SignupRequest)
            .where(SignupRequest.id == request_id, SignupRequest.status == "pending")
            .values(status=decision, reviewed_at=datetime.now(UTC), reviewed_by_user_id=token_info["user_id"])
        )
        if result.rowcount != 1:
            raise HTTPException(409, "signup_request_already_reviewed")
        await sql.commit()
        await sql.refresh(row)
        await lease.assert_owned()
        safe = request_dto(row)
        await _audit(token_info, f"signup_request.{decision}", request_id)
        if decision == "approved" and row.source == "email":
            try:
                if (await read_policy(session=sql))["public_signup_enabled"]:
                    from app.services.domain_iam import issue_enrollment

                    await issue_enrollment(sql, kind="registration", domain_id=None, email=row.email)
                else:
                    from app.services.email_service import send_email

                    delivered = await send_email(
                        row.email,
                        "Your signup request was approved",
                        "<p>Your signup request was approved. Reopen your original verified invitation "
                        "to complete enrollment. If the invitation has expired, contact your inviter "
                        "for a renewed link. Public email registration is currently disabled.</p>",
                        "Your signup request was approved. Reopen your original verified invitation "
                        "to complete enrollment. If the invitation has expired, contact your inviter "
                        "for a renewed link. Public email registration is currently disabled.",
                    )
                    if not delivered:
                        raise HTTPException(503, "signup_approval_notification_failed")
            except Exception as exc:
                await _audit(token_info, "signup_request.notify", request_id, status="failed")
                raise HTTPException(503, "signup_approval_notification_failed; approval remains approved") from exc
        return safe


async def apply_personal_project_quotas(conn, project_id, quotas, *, lease):
    """Apply frozen signup limits directly; personal has no shared quota pool."""
    values = _limits(quotas)
    omitted = (
        sorted(set(values) & set(quota_native.QUOTA_FIELDS["file_storage"]))
        if not get_settings().service_manila_enabled
        else []
    )
    active = {key: value for key, value in values.items() if key not in omitted}
    from app.services.project_service import _provider_call

    sections = {}
    # Preflight all selected fields before dispatching any quota mutation.
    for section, fields in quota_native.QUOTA_FIELDS.items():
        selected = {native: active[key] for key, native in fields.items() if key in active}
        if not selected:
            continue
        current = await _provider_call(quota_native.get_section, conn, project_id, section)
        if any(key not in current for key in selected):
            raise HTTPException(503, "personal_project_quota_field_unavailable")
        sections[section] = selected
    for section, selected in sections.items():
        await lease.assert_owned()
        await identity_roles._write(lease, quota_native.update_section, conn, project_id, section, selected)
        checked = await _provider_call(quota_native.get_section, conn, project_id, section)
        if any(checked.get(key, {}).get("limit") != value for key, value in selected.items()):
            raise HTTPException(503, "personal_project_quota_readback_failed")
    await lease.assert_owned()
    return {"project_id": project_id, "limits": active, "omitted_fields": omitted}


async def initialize_personal_quotas(project_id, quotas, *, lease):
    from app.services import keystone
    from app.services.project_service import _provider_call

    conn = await _provider_call(keystone.get_admin_project_connection)
    try:
        return await apply_personal_project_quotas(conn, project_id, quotas, lease=lease)
    finally:
        await _provider_call(conn.close)


async def personal_quota_projects(actor, *, cursor=None):
    from app.services import account_spaces
    from app.services.native_operation import NativeOperation

    await account_spaces._system_actor(actor)
    async with NativeOperation() as operation:
        domain = await operation.run(account_spaces.shared_domain, "personal", operation=operation)
        did = identity_roles._field(domain, "id")
        rows = await operation.run(lambda: list(operation.ks.projects.list(domain=did)))
        items = []
        for row in rows:
            if identity_roles._field(row, "domain_id") != did:
                raise HTTPException(503, "personal_project_directory_unverified")
            pid = identity_roles._field(row, "id")
            if not isinstance(pid, str) or not pid:
                raise HTTPException(503, "personal_project_directory_unverified")
            items.append(
                {
                    "id": pid,
                    "name": identity_roles._field(row, "name"),
                    "user_id": identity_roles._field(row, "afterglow_personal_user_id"),
                    "enabled": identity_roles._field(row, "enabled") is True,
                }
            )
        if len({row["id"] for row in items}) != len(items):
            raise HTTPException(503, "personal_project_directory_unverified")
        items.sort(key=lambda row: row["id"])
        items = [row for row in items if cursor is None or row["id"] > cursor]
        return {"items": items[:100], "next_cursor": items[99]["id"] if len(items) > 100 else None}


async def _personal_quota_preview(conn, project_id, actor, mutation):
    from app.models.account_spaces import PersonalProjectIntent
    from app.models.domain_iam import DomainEnrollment
    from app.services import account_spaces, domain_projects, domain_quotas, project_service

    lease, ks, catalog = mutation
    await account_spaces._system_actor(actor)
    domain = await domain_quotas._call(account_spaces.shared_domain, "personal", ks=ks)
    did = identity_roles._field(domain, "id")
    project = await domain_quotas._call(ks.projects.get, project_id)
    owner = identity_roles._field(project, "afterglow_personal_user_id")
    marker = identity_roles._field(project, "afterglow_enrollment_id")
    if (
        identity_roles._field(project, "id") != project_id
        or identity_roles._field(project, "domain_id") != did
        or identity_roles._field(project, "enabled") is not True
        or not isinstance(owner, str)
        or not owner
    ):
        raise HTTPException(409, "personal_project_provenance_required")
    user = await account_spaces._human(owner, mutation)
    sources = await domain_quotas._call(domain_projects._sources, ks, project, catalog)
    member = account_spaces._personal_member_role(catalog)
    ownership = None
    if any(source["role_id"] == member["id"] for source in sources):
        await domain_quotas._call(account_spaces._verify_personal_member, ks, catalog, project, owner)
    else:
        # Only historical owner-based projects depend on the project hierarchy.
        ownership = await domain_quotas._call(project_service._ownership_state_sync, ks, catalog, project_id)
        if ownership["status"] != "unique" or ownership["owner_user_id"] != owner:
            raise HTTPException(409, "personal_project_owner_changed")
    async with _session() as sql:
        if marker:
            if not isinstance(marker, str):
                raise HTTPException(409, "personal_project_provenance_required")
            intent = await sql.get(PersonalProjectIntent, marker)
            enrollment = (
                await sql.execute(select(DomainEnrollment).where(DomainEnrollment.token_hash == marker))
            ).scalar_one_or_none()
            receipt = intent or enrollment
            if (
                receipt is None
                or receipt.status != "accepted"
                or receipt.user_id != owner
                or receipt.identity_domain_id != identity_roles._field(user, "domain_id")
                or receipt.personal_project_id != project_id
                or receipt.personal_domain_id != did
                or receipt.project_creation_uncertain
            ):
                raise HTTPException(409, "personal_project_provenance_required")
        else:
            # Historical owner primaries have native provenance, not a synthetic
            # enrollment receipt. Never adopt an unmarked/member-only project.
            primary = await domain_quotas._call(account_spaces.personal_project, owner, ks=ks)
            if ownership is None or ownership["status"] != "unique" or primary is None or primary["id"] != project_id:
                raise HTTPException(409, "personal_project_provenance_required")
            marker = {"kind": "native_owner_primary", "project_id": project_id}
        unfinished = (
            await sql.execute(
                select(PersonalProjectIntent.token_hash)
                .where(
                    PersonalProjectIntent.user_id == owner,
                    PersonalProjectIntent.status.not_in({"accepted", "cancelled"}),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if unfinished is not None:
            raise HTTPException(409, "personal_project_recovery_required")
        policy = await read_policy(session=sql)
    async with domain_quotas._session() as sql:
        await domain_quotas._assert_settled(sql, did, project_id=project_id)
    limits = {
        key: value
        for key, value in policy["personal_quotas"].items()
        if key in {key for fields in _fields().values() for key in fields}
    }
    measured, blocked = {}, []
    for section, fields in quota_native.QUOTA_FIELDS.items():
        selected = {key: native for key, native in fields.items() if key in limits}
        if not selected:
            continue
        current = await domain_quotas._call(quota_native.get_section, conn, project_id, section)
        for key, native in selected.items():
            entry = current.get(native)
            if not isinstance(entry, dict) or any(
                type(entry.get(k)) is not int for k in ("limit", "in_use", "reserved")
            ):
                raise HTTPException(503, "personal_project_usage_unavailable")
            measured[key] = entry
            if limits[key] != -1 and limits[key] < entry["in_use"] + entry["reserved"]:
                blocked.append(key)
    result = {
        "project_id": project_id,
        "domain_id": did,
        "owner_user_id": owner,
        "identity_domain_id": identity_roles._field(user, "domain_id"),
        "policy_revision": policy["revision"],
        "limits": limits,
        "current": measured,
        "blocked_fields": sorted(blocked),
        "can_apply": not blocked and bool(limits),
        "provenance": marker,
        "actor_user_id": actor["user_id"],
    }
    result["preview_id"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    await lease.assert_owned()
    return result


async def preview_personal_quotas(conn, project_id, actor):
    from app.services import domain_iam

    async with domain_iam._iam_write() as mutation:
        return await _personal_quota_preview(conn, project_id, actor, mutation)


@identity_roles._complete_mutation
async def converge_personal_quotas(conn, project_id, actor, preview_id):
    from app.services import domain_iam, domain_quotas

    async with domain_iam._iam_write() as mutation:
        preview = await _personal_quota_preview(conn, project_id, actor, mutation)
        if preview["preview_id"] != preview_id:
            raise HTTPException(409, "personal_quota_preview_changed")
        if not preview["can_apply"]:
            raise HTTPException(409, "personal_quota_usage_exceeds_policy")
        result = await domain_quotas._apply(
            conn, preview["domain_id"], project_id, preview["limits"], lease=mutation[0]
        )
        await _audit(actor, "personal_quotas.apply", project_id, extra={"operation_id": result["operation_id"]})
        return result
