"""Single-dispatch, encrypted outgoing mail and future safe activity notifications.

SMTP acceptance is not inbox delivery. A committed dispatch is never retried:
transport uncertainty or a crashed worker becomes an operator-visible unknown.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formataddr
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.database import get_session_factory, is_db_available
from app.models.activity import ActivityLog
from app.models.announcement import Announcement
from app.models.email_delivery import EmailDelivery, EmailNotificationCursor, EmailOperation, EmailPreference
from app.services import domain_auth, identity_roles, mail_crypto, mail_settings
from app.services.work_dispatcher import checkpoint, drain_task, run_sync, worker_experience_scope

logger = logging.getLogger(__name__)
STATUSES = ("pending", "dispatching", "accepted", "failed", "unknown", "cancelled")
RESOURCE_TYPES = frozenset(
    {
        "instance",
        "image",
        "volume",
        "volume_snapshot",
        "volume_backup",
        "snapshot",
        "backup",
        "network",
        "subnet",
        "router",
        "floating_ip",
        "floatingip",
        "port",
        "security_group",
        "load_balancer",
        "lb_listener",
        "lb_pool",
        "lb_member",
        "lb_health_monitor",
        "share",
        "share_snapshot",
        "share_network",
        "security_service",
        "file_storage",
        "container",
        "database_instance",
        "database_backup",
        "k3s_cluster",
        "magnum_cluster",
        "waygate_server",
    }
)


def _now():
    return datetime.now(UTC)


def _utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _error(status, code):
    return HTTPException(status, {"code": "mail_" + code})


def _factory():
    factory = get_session_factory()
    if factory is None or not is_db_available():
        raise _error(503, "storage_unavailable")
    return factory


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _operation_id(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise _error(422, "invalid_operation_id") from None


def _text(subject, body):
    if not isinstance(subject, str) or not 1 <= len(subject.strip()) <= 200 or "\r" in subject or "\n" in subject:
        raise _error(422, "invalid_subject")
    if not isinstance(body, str) or not 1 <= len(body.strip()) <= 10000:
        raise _error(422, "invalid_body")
    return subject.strip(), body.strip()


def _address(value):
    try:
        email = domain_auth.normalize_email(value).casefold()
        if len(email) > 255 or "\r" in email or "\n" in email:
            raise ValueError
        return email
    except (domain_auth.DomainAuthError, ValueError, TypeError, AttributeError):
        raise _error(422, "invalid_email") from None


async def _recipient(user_id, project_id=None):
    """Reuse the exact enabled-human/unique-mail guard, without password behavior."""
    from app.services import admin_password_reset, domain_projects
    from app.services.native_operation import NativeOperation

    async def resolve():
        async with NativeOperation() as operation:
            ks = await operation.run(lambda: operation.ks)
            catalog = await operation.run(operation.catalog)
            user, email = await admin_password_reset._subject(user_id, ks, catalog)
            if project_id:
                await operation.run(domain_projects.assert_project_membership, user_id, project_id, operation=operation)
            return {
                "user_id": user_id,
                "identity_domain_id": identity_roles._field(user, "domain_id"),
                "recipient_email": email,
                "project_id": project_id,
            }

    try:
        return await identity_roles._to_completion(resolve())
    except HTTPException as exc:
        if exc.status_code in (401, 403, 404, 409, 422):
            raise _error(409, "recipient_ineligible") from None
        raise _error(503, "identity_unavailable") from None
    except Exception:
        raise _error(503, "identity_unavailable") from None


async def _actor_allowed(actor_id):
    from app.services import keystone

    return bool(await run_sync(keystone._is_system_admin, actor_id))


async def _audience(announcement):
    from app.services import domain_iam
    from app.services.native_operation import NativeOperation

    if announcement.target_type == "user":
        ids = [announcement.target_id]
    else:
        # This is a complete native directory traversal, not a UI list/limit.
        async with NativeOperation() as operation:
            ks = await operation.run(lambda: operation.ks)
            rows = await operation.run(domain_iam._account_rows, ks, None)
        ids = sorted({identity_roles._field(row, "id") for row in rows})
    result = []
    for user_id in ids:
        if not isinstance(user_id, str) or not user_id:
            raise _error(503, "identity_unavailable")
        try:
            result.append(
                await _recipient(user_id, announcement.target_id if announcement.target_type == "project" else None)
            )
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
            # Ineligible/service accounts and non-members are not recipients.
    return result


def _announcement_values(row):
    return {
        key: (_utc(value).isoformat() if isinstance(value, datetime) else value)
        for key in ("title", "body", "severity", "target_type", "target_id", "starts_at", "ends_at", "is_active")
        for value in [getattr(row, key)]
    }


def _announcement_fingerprint(row):
    return _hash(
        {
            **_announcement_values(row),
            "id": row.id,
            "created_at": _utc(row.created_at).isoformat(),
            "updated_at": _utc(row.updated_at).isoformat(),
        }
    )


def _payload(row):
    try:
        value = json.loads(mail_crypto.decrypt_secret(row.payload_encrypted, purpose="delivery:" + row.id))
        subject, body = _text(value["subject"], value["body"])
        binding = {key: getattr(row, key) for key in ("user_id", "identity_domain_id", "project_id", "recipient_email")}
        if value["recipient"] != binding:
            raise ValueError("mail_recipient_binding_mismatch")
        return {**value, "subject": subject, "body": body}
    except Exception:
        raise _error(503, "payload_unavailable") from None


def _dto(row):
    try:
        subject = _payload(row)["subject"]
    except HTTPException:
        subject = "[Content unavailable]"
    return {
        "id": row.id,
        "operation_id": row.operation_id,
        "kind": row.kind,
        "user_id": row.user_id,
        "recipient_email": row.recipient_email,
        "subject": subject,
        "status": row.status,
        "error_code": row.error_code,
        "message_id": row.message_id,
        "created_at": _utc(row.created_at).isoformat(),
        "updated_at": _utc(row.updated_at).isoformat(),
    }


async def _existing(session, actor_id, operation_id, request_hash):
    operation = (
        await session.execute(
            select(EmailOperation).where(
                EmailOperation.actor_id == actor_id, EmailOperation.operation_id == operation_id
            )
        )
    ).scalar_one_or_none()
    if operation is not None and operation.request_hash != request_hash:
        raise _error(409, "operation_conflict")
    return operation


async def _summary(session, operation):
    counts = dict.fromkeys(STATUSES, 0)
    rows = (
        await session.execute(
            select(EmailDelivery.status, func.count())
            .where(EmailDelivery.operation_key == operation.id)
            .group_by(EmailDelivery.status)
        )
    ).all()
    counts.update({status: count for status, count in rows})
    nonempty = [status for status, count in counts.items() if count]
    if "dispatching" in nonempty:
        status = "dispatching"
    elif operation.audience_pending or "pending" in nonempty:
        status = "pending"
    elif len(nonempty) == 1:
        status = nonempty[0]
    elif not nonempty:
        status = "cancelled"
    else:
        status = "partial"
    return {
        "operation_id": operation.operation_id,
        "kind": operation.kind,
        "status": status,
        "audience_pending": bool(operation.audience_pending),
        "counts": counts,
    }


async def _persist_deliveries(session, operation, recipients, subject, body, announcement=None):
    for recipient in recipients:
        delivery_id = str(uuid4())
        payload = {"subject": subject, "body": body, "recipient": recipient}
        if announcement is not None:
            payload["announcement_fingerprint"] = _announcement_fingerprint(announcement)
        session.add(
            EmailDelivery(
                id=delivery_id,
                operation_key=operation.id,
                operation_id=operation.operation_id,
                kind=operation.kind,
                **recipient,
                payload_encrypted=mail_crypto.encrypt_secret(_json(payload), purpose="delivery:" + delivery_id),
                message_id=f"<afterglow.{delivery_id}@mail.invalid>",
                status="pending",
                available_at=(announcement.starts_at or announcement.created_at)
                if announcement is not None
                else _now(),
            )
        )
    await session.flush()


async def _persist(
    session,
    *,
    actor_id,
    operation_id,
    request_hash,
    kind,
    recipients,
    subject,
    body,
    announcement=None,
    notification_activity_id=None,
):
    operation = EmailOperation(
        id=uuid4().hex,
        actor_id=actor_id,
        operation_id=operation_id,
        request_hash=request_hash,
        kind=kind,
        announcement_id=announcement.id if announcement is not None else None,
        audience_pending=announcement is not None,
        announcement_fingerprint=_announcement_fingerprint(announcement) if announcement is not None else None,
        notification_activity_id=notification_activity_id,
    )
    session.add(operation)
    await session.flush()
    if announcement is None:
        await _persist_deliveries(session, operation, recipients, subject, body)
    return operation


async def _experience_admission(operation):
    from app.services.experience_context import bind_experience_operation, capture_experience_context, emit_experience

    if operation.kind == "resource_alert" or operation.actor_id in {"notifications", "system", ""}:
        return
    context = capture_experience_context(feature="admin", action="submit", component="page")
    if context is None or context.get("actor", {}).get("user_id") != operation.actor_id:
        return
    await bind_experience_operation(context, "email_operation", operation.id)
    await emit_experience(
        context, "operation.accepted", stage="mail.admission", status="accepted", operation_id=operation.id
    )


async def _enqueue(
    *,
    actor_id,
    operation_id,
    request,
    kind,
    recipients=None,
    subject,
    body,
    announcement_id=None,
    notification_activity_id=None,
):
    operation_id, request_hash = _operation_id(operation_id), _hash(request)
    factory = _factory()
    # Replays do not depend on today's recipient inventory or configuration.
    async with factory() as session:
        existing = await _existing(session, actor_id, operation_id, request_hash)
        if existing is not None:
            return await _summary(session, existing)
    if kind == "individual":
        recipients = [await _recipient(user_id) for user_id in request["user_ids"]]
    try:
        async with factory() as session, session.begin():
            announcement = None
            if announcement_id is not None:
                announcement = await session.get(Announcement, announcement_id, with_for_update=True)
                if announcement is None:
                    raise _error(404, "announcement_not_found")
                _announcement_valid(announcement, _now(), allow_future=True)
                subject, body = announcement.title, announcement.body
            operation = await _persist(
                session,
                actor_id=actor_id,
                operation_id=operation_id,
                request_hash=request_hash,
                kind=kind,
                recipients=recipients or [],
                subject=subject,
                body=body,
                announcement=announcement,
                notification_activity_id=notification_activity_id,
            )
            summary = await _summary(session, operation)
        await _experience_admission(operation)
        return summary
    except IntegrityError:
        async with factory() as session:
            existing = await _existing(session, actor_id, operation_id, request_hash)
            if existing is None:
                raise _error(503, "storage_unavailable") from None
            return await _summary(session, existing)


async def send_individual(*, actor_id, operation_id, user_ids, subject, body):
    subject, body = _text(subject, body)
    try:
        ids = set()
        for value in user_ids:
            user_id = str(value) if isinstance(value, UUID) else value
            if not isinstance(user_id, str) or not domain_auth._KEYSTONE_ID_RE.fullmatch(user_id):
                raise ValueError
            try:
                user_id = UUID(user_id).hex
            except ValueError:
                pass
            ids.add(user_id)
        ids = sorted(ids)
    except (ValueError, TypeError, AttributeError):
        raise _error(422, "invalid_user_ids") from None
    if not 1 <= len(ids) <= 100:
        raise _error(422, "invalid_user_ids")
    return await _enqueue(
        actor_id=actor_id,
        operation_id=operation_id,
        request={"kind": "individual", "user_ids": ids, "subject": subject, "body": body},
        kind="individual",
        subject=subject,
        body=body,
    )


async def send_test(*, actor_id, operation_id, recipient_email):
    email = _address(recipient_email)
    return await _enqueue(
        actor_id=actor_id,
        operation_id=operation_id,
        request={"kind": "test", "recipient_email": email},
        kind="test",
        recipients=[{"user_id": None, "identity_domain_id": None, "project_id": None, "recipient_email": email}],
        subject="Afterglow email connection test",
        body="This is an administrator-requested Afterglow test message. SMTP acceptance does not confirm inbox receipt.",
    )


def _announcement_valid(row, now, *, allow_future=False):
    if not row.is_active or row.ends_at and _utc(row.ends_at) < now:
        raise _error(409, "announcement_inactive")
    if row.starts_at and row.ends_at and _utc(row.starts_at) > _utc(row.ends_at):
        raise _error(422, "invalid_schedule")
    if not allow_future and row.starts_at and _utc(row.starts_at) > now:
        raise _error(409, "announcement_scheduled")


async def send_announcement(*, actor_id, operation_id, announcement_id):
    return await _enqueue(
        actor_id=actor_id,
        operation_id=operation_id,
        request={"kind": "announcement", "announcement_id": announcement_id},
        kind="announcement",
        subject="",
        body="",
        announcement_id=announcement_id,
    )


async def create_announcement_with_mail(row, *, actor_id, operation_id):
    """Persist a newly created announcement and its entire mail intent atomically."""
    from app.services.announcements import _serialize_admin

    operation_id = _operation_id(operation_id)
    request_hash = _hash({"kind": "announcement_create", **_announcement_values(row)})
    factory = _factory()

    async def replay(session, existing):
        original = await session.get(Announcement, existing.announcement_id)
        if original is None:
            raise _error(409, "announcement_changed")
        return {**_serialize_admin(original), "email_operation": await _summary(session, existing)}

    async with factory() as session:
        existing = await _existing(session, actor_id, operation_id, request_hash)
        if existing is not None:
            return await replay(session, existing)
    _announcement_valid(row, _now(), allow_future=True)
    try:
        async with factory() as session, session.begin():
            session.add(row)
            await session.flush()
            await session.refresh(row)
            operation = await _persist(
                session,
                actor_id=actor_id,
                operation_id=operation_id,
                request_hash=request_hash,
                kind="announcement",
                recipients=[],
                subject=row.title,
                body=row.body,
                announcement=row,
            )
            result = {**_serialize_admin(row), "email_operation": await _summary(session, operation)}
        await _experience_admission(operation)
        return result
    except IntegrityError:
        async with factory() as session:
            existing = await _existing(session, actor_id, operation_id, request_hash)
            if existing is None:
                raise _error(503, "storage_unavailable") from None
            return await replay(session, existing)


async def _expand_announcements(now, batch_size=50):
    """Materialize the complete current audience at the active dispatch boundary."""
    factory = _factory()
    settings = await mail_settings.effective_settings()
    async with factory() as session:
        ids = list(
            (
                await session.scalars(
                    select(EmailOperation.id)
                    .outerjoin(Announcement, Announcement.id == EmailOperation.announcement_id)
                    .where(
                        EmailOperation.kind == "announcement",
                        EmailOperation.audience_pending.is_(True),
                        or_(Announcement.id.is_(None), Announcement.starts_at.is_(None), Announcement.starts_at <= now),
                    )
                    .order_by(EmailOperation.created_at, EmailOperation.id)
                    .limit(batch_size)
                )
            ).all()
        )
    for operation_key in ids:
        await checkpoint()
        try:
            async with factory() as session:
                operation = await session.get(EmailOperation, operation_key)
                announcement = await session.get(Announcement, operation.announcement_id)
            allowed = settings.notifications.announcements_enabled and announcement is not None
            if allowed:
                allowed = _announcement_fingerprint(announcement) == operation.announcement_fingerprint
            if allowed:
                try:
                    _announcement_valid(announcement, now)
                except HTTPException:
                    allowed = False
            if allowed:
                allowed = await _actor_allowed(operation.actor_id)
            recipients = await _audience(announcement) if allowed else []
            async with factory() as session, session.begin():
                current = await session.get(EmailOperation, operation_key, with_for_update=True)
                if not current.audience_pending:
                    continue
                latest = await session.get(Announcement, current.announcement_id, with_for_update=True)
                if latest is None or _announcement_fingerprint(latest) != current.announcement_fingerprint:
                    allowed = False
                elif allowed:
                    try:
                        _announcement_valid(latest, now)
                    except HTTPException:
                        allowed = False
                claimed = await session.execute(
                    update(EmailOperation)
                    .where(EmailOperation.id == operation_key, EmailOperation.audience_pending.is_(True))
                    .values(audience_pending=False)
                )
                if claimed.rowcount and allowed:
                    await _persist_deliveries(session, current, recipients, latest.title, latest.body, latest)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Announcement email audience unavailable")


async def list_deliveries(*, limit=50, offset=0):
    async with _factory()() as session:
        total = await session.scalar(select(func.count()).select_from(EmailDelivery))
        rows = (
            (
                await session.execute(
                    select(EmailDelivery)
                    .order_by(EmailDelivery.created_at.desc(), EmailDelivery.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return {"items": [_dto(row) for row in rows], "total": total}


async def get_delivery(delivery_id):
    async with _factory()() as session:
        row = await session.get(EmailDelivery, delivery_id)
        if row is None:
            raise _error(404, "delivery_not_found")
        return _dto(row)


async def get_receipt_target(delivery_id):
    async with _factory()() as session:
        row = await session.get(EmailDelivery, delivery_id)
        if row is None:
            raise _error(404, "delivery_not_found")
        return {
            "kind": row.kind,
            "message_id": row.message_id,
            "recipient_email": row.recipient_email,
            "status": row.status,
        }


async def _preferences(session, user_id, home):
    row = await session.get(EmailPreference, (user_id, home))
    return {
        "announcements": row.announcements if row else True,
        "resource_alerts": row.resource_alerts if row else False,
    }


async def cancel_announcement_mail(session, announcement_id):
    """Invalidate queued versions in the same transaction as every edit/delete."""
    operations = select(EmailOperation.id).where(EmailOperation.announcement_id == announcement_id)
    await session.execute(
        update(EmailOperation)
        .where(EmailOperation.announcement_id == announcement_id, EmailOperation.audience_pending.is_(True))
        .values(audience_pending=False)
    )
    await session.execute(
        update(EmailDelivery)
        .where(EmailDelivery.operation_key.in_(operations), EmailDelivery.status == "pending")
        .values(status="cancelled", error_code="announcement_changed", updated_at=_now())
    )


async def _cancel_optouts(session, user_id, home, values):
    disabled = []
    if not values["announcements"]:
        disabled.append("announcement")
    if not values["resource_alerts"]:
        disabled.append("resource_alert")
    if disabled:
        await session.execute(
            update(EmailDelivery)
            .where(
                EmailDelivery.user_id == user_id,
                EmailDelivery.identity_domain_id == home,
                EmailDelivery.status == "pending",
                EmailDelivery.kind.in_(disabled),
            )
            .values(status="cancelled", error_code="notifications_disabled", updated_at=_now())
        )


def _set_preference_values(row, values):
    if values["resource_alerts"]:
        if row.resource_alerts is not True or row.resource_alerts_enabled_at is None:
            # Existing activity storage can retain only whole seconds.
            row.resource_alerts_enabled_at = _now().replace(microsecond=0)
    else:
        row.resource_alerts_enabled_at = None
    row.announcements, row.resource_alerts = values["announcements"], values["resource_alerts"]
    row.updated_at = _now()


async def preferences(token_info, *, values=None):
    user_id, home = token_info.get("user_id"), token_info.get("identity_domain_id")
    if not user_id or not home:
        raise _error(401, "identity_required")
    recipient = await _recipient(user_id)
    if recipient["identity_domain_id"] != home:
        raise _error(401, "identity_changed")
    factory = _factory()
    try:
        async with factory() as session, session.begin():
            if values is not None:
                row = await session.get(EmailPreference, (user_id, home), with_for_update=True)
                if row is None:
                    row = EmailPreference(user_id=user_id, identity_domain_id=home)
                    session.add(row)
                _set_preference_values(row, values)
                await session.flush()
                await _cancel_optouts(session, user_id, home, values)
            return await _preferences(session, user_id, home)
    except IntegrityError:
        # Two first writes may race; retry only the idempotent preference write,
        # never SMTP or an already persisted outgoing intent.
        async with factory() as session, session.begin():
            row = await session.get(EmailPreference, (user_id, home), with_for_update=True)
            if row is None or values is None:
                raise _error(503, "storage_unavailable") from None
            _set_preference_values(row, values)
            await _cancel_optouts(session, user_id, home, values)
            return {"announcements": row.announcements, "resource_alerts": row.resource_alerts}


async def list_notification_subscribers(*, limit=100, offset=0):
    """Page complete opt-in identity bindings; callers must revalidate natively."""
    async with _factory()() as session:
        rows = (
            (
                await session.execute(
                    select(EmailPreference)
                    .where(EmailPreference.resource_alerts.is_(True))
                    .order_by(EmailPreference.user_id, EmailPreference.identity_domain_id)
                    .limit(max(1, min(limit, 200)))
                    .offset(max(offset, 0))
                )
            )
            .scalars()
            .all()
        )
        return [{"user_id": row.user_id, "identity_domain_id": row.identity_domain_id} for row in rows]


async def enqueue_notification(
    *,
    user_id,
    project_id,
    event_key,
    subject,
    body,
    expected_identity_domain_id=None,
    event_created_at=None,
    notification_activity_id=None,
):
    """Called only by persisted, future server-owned producers; no log prose."""
    settings = await mail_settings.effective_settings()
    if not settings.notifications.resource_alerts_enabled:
        return None
    if not isinstance(event_key, str) or not event_key or len(event_key) > 255 or not project_id:
        raise _error(422, "invalid_event")
    subject, body = _text(subject, body)
    async with _factory()() as session:
        entries = (
            (
                await session.execute(
                    select(EmailPreference).where(
                        EmailPreference.user_id == user_id, EmailPreference.resource_alerts.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )
        homes = {
            entry.identity_domain_id
            for entry in entries
            if event_created_at is None
            or (
                entry.resource_alerts_enabled_at is not None
                and _utc(event_created_at) >= _utc(entry.resource_alerts_enabled_at).replace(microsecond=0)
            )
        }
    if not homes:
        return None
    if expected_identity_domain_id is not None and expected_identity_domain_id not in homes:
        raise _error(409, "identity_changed")
    recipient = await _recipient(user_id, project_id)
    if expected_identity_domain_id is not None and recipient["identity_domain_id"] != expected_identity_domain_id:
        raise _error(409, "identity_changed")
    async with _factory()() as session:
        preference = await session.get(EmailPreference, (user_id, recipient["identity_domain_id"]))
    if (
        preference is None
        or not preference.resource_alerts
        or (
            event_created_at is not None
            and (
                preference.resource_alerts_enabled_at is None
                or _utc(event_created_at) < _utc(preference.resource_alerts_enabled_at).replace(microsecond=0)
            )
        )
    ):
        return None
    operation_id = str(uuid5(NAMESPACE_URL, "afterglow:mail:" + user_id + ":" + event_key))
    return await _enqueue(
        actor_id="notifications",
        operation_id=operation_id,
        request={
            "kind": "resource_alert",
            "event": event_key,
            "user_id": user_id,
            "project_id": project_id,
            "subject": subject,
            "body": body,
        },
        kind="resource_alert",
        recipients=[recipient],
        subject=subject,
        body=body,
        notification_activity_id=notification_activity_id,
    )


def _safe_activity_failure(row):
    if (
        row.status != "failed"
        or row.source not in {"afterglow", "openstack"}
        or row.resource_type not in RESOURCE_TYPES
        or not row.user_id
        or not row.project_id
    ):
        return False
    if row.source == "afterglow":
        method = row.extra.get("method") if isinstance(row.extra, dict) else None
        if method is not None and method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return False
        if row.action in {"read", "get", "list"} or row.action.endswith((".read", ".stage")):
            return False
    return True


async def _mark_activity_seen(row):
    """A skipped event is durable too; later opt-in must not replay history."""
    operation_id = str(uuid5(NAMESPACE_URL, "afterglow:mail:" + row.user_id + f":activity:{row.id}"))
    factory = _factory()
    try:
        async with factory() as session, session.begin():
            existing = await session.scalar(
                select(EmailOperation).where(
                    or_(
                        EmailOperation.notification_activity_id == row.id,
                        (EmailOperation.actor_id == "notifications") & (EmailOperation.operation_id == operation_id),
                    )
                )
            )
            if existing is not None:
                return
            await _persist(
                session,
                actor_id="notifications",
                operation_id=operation_id,
                request_hash=_hash({"skipped_activity": row.id, "user_id": row.user_id}),
                kind="resource_alert",
                recipients=[],
                subject="",
                body="",
                notification_activity_id=row.id,
            )
    except IntegrityError:
        async with factory() as session:
            if (
                await session.scalar(select(EmailOperation.id).where(EmailOperation.notification_activity_id == row.id))
                is None
            ):
                raise _error(503, "storage_unavailable") from None


async def _collect_notifications(settings, now, batch_size):
    factory = _factory()
    enabled = settings.notifications.resource_alerts_enabled
    async with factory() as session, session.begin():
        cursor = await session.get(EmailNotificationCursor, "resource-failures", with_for_update=True)
        maximum = await session.scalar(select(func.max(ActivityLog.id))) or 0
        if cursor is None:
            session.add(
                EmailNotificationCursor(
                    name="resource-failures",
                    enabled=enabled,
                    enabled_at=now.replace(microsecond=0),
                    updated_at=now,
                    scan_after_id=0,
                    scan_until_id=maximum,
                )
            )
            return
        if not enabled or not cursor.enabled:
            cursor.enabled, cursor.enabled_at, cursor.updated_at = enabled, now.replace(microsecond=0), now
            cursor.scan_after_id, cursor.scan_until_id = 0, maximum
            return
        enabled_at = _utc(cursor.enabled_at).replace(microsecond=0)
        unseen = ~select(EmailOperation.id).where(EmailOperation.notification_activity_id == ActivityLog.id).exists()

        async def page():
            return (
                await session.scalars(
                    select(ActivityLog)
                    .where(
                        ActivityLog.status == "failed",
                        ActivityLog.source.in_(("afterglow", "openstack")),
                        ActivityLog.resource_type.in_(RESOURCE_TYPES),
                        ActivityLog.user_id != "",
                        ActivityLog.project_id != "",
                        ActivityLog.created_at >= enabled_at,
                        ActivityLog.created_at <= now,
                        unseen,
                        ActivityLog.id > cursor.scan_after_id,
                        ActivityLog.id <= cursor.scan_until_id,
                    )
                    .order_by(ActivityLog.id)
                    .limit(batch_size)
                )
            ).all()

        rows = await page()
        if not rows:
            # A finite cohort always wraps, even with continuous new arrivals.
            # Older late commits remain unseen and eligible on the next round;
            # advancing here is fairness, never a processed-event watermark.
            cursor.scan_after_id, cursor.scan_until_id = 0, maximum
            rows = await page()
        if rows:
            cursor.scan_after_id = rows[-1].id
        cursor.updated_at = now
    for row in rows:
        try:
            if _safe_activity_failure(row):
                # Never copy error prose, names, extra JSON, URLs or tokens.
                resource_id = row.resource_id or "unavailable"
                if not all(char.isalnum() or char in "-_." for char in resource_id) or len(resource_id) > 128:
                    resource_id = "unavailable"
                result = await enqueue_notification(
                    user_id=row.user_id,
                    project_id=row.project_id,
                    event_key=f"activity:{row.id}",
                    event_created_at=row.created_at,
                    notification_activity_id=row.id,
                    subject="Afterglow resource operation failed",
                    body=f"A resource operation failed.\nResource type: {row.resource_type}\nResource ID: {resource_id}\nProject ID: {row.project_id}\nReview your activity history in Afterglow for details.",
                )
                if result is not None:
                    continue  # marker and delivery intent committed atomically
            await _mark_activity_seen(row)
        except HTTPException as exc:
            if exc.status_code == 409:
                await _mark_activity_seen(row)
            else:
                # No processed marker for transient native/storage failures.
                logger.warning("Email activity notification deferred")


async def _set_status(delivery_id, status, code=None, *, expected="dispatching", now=None):
    async with _factory()() as session, session.begin():
        result = await session.execute(
            update(EmailDelivery)
            .where(EmailDelivery.id == delivery_id, EmailDelivery.status == expected)
            .values(status=status, error_code=code, updated_at=now or _now())
        )
        return bool(result.rowcount)


async def _eligible_delivery(row, operation, payload, settings, now):
    if row.kind != "resource_alert" and not await _actor_allowed(operation.actor_id):
        return "sender_ineligible"
    if row.user_id:
        current = await _recipient(row.user_id, row.project_id)
        if any(
            current[key] != getattr(row, key)
            for key in ("user_id", "identity_domain_id", "recipient_email", "project_id")
        ):
            return "recipient_changed"
        if row.kind in {"announcement", "resource_alert"}:
            async with _factory()() as session:
                preference = await _preferences(session, row.user_id, row.identity_domain_id)
            category = "announcements" if row.kind == "announcement" else "resource_alerts"
            if not preference[category] or not getattr(settings.notifications, category + "_enabled"):
                return "notifications_disabled"
    if row.kind == "announcement":
        async with _factory()() as session:
            announcement = await session.get(Announcement, operation.announcement_id)
            if announcement is None:
                return "announcement_changed"
            if _announcement_fingerprint(announcement) != payload.get("announcement_fingerprint"):
                return "announcement_changed"
            _announcement_valid(announcement, _utc(now or _now()))
            if announcement.target_type == "user" and announcement.target_id != row.user_id:
                return "recipient_changed"
            if announcement.target_type == "project" and announcement.target_id != row.project_id:
                return "recipient_changed"
    return None


async def _dispatch_one(delivery_id, *, now=None):
    dispatch_clock = now
    now = now or _now()
    settings = await mail_settings.effective_settings()
    if not settings.smtp.enabled:
        return
    async with _factory()() as session:
        row = await session.get(EmailDelivery, delivery_id)
        if row is None or row.status != "pending":
            return
        operation = await session.get(EmailOperation, row.operation_key)
    from app.services.experience_context import (
        restore_experience_operation,
        unlinked_worker_context,
    )

    experience = (
        await restore_experience_operation(
            "email_operation", operation.id, {"user_id": operation.actor_id, "ownership_mode": "origin_receipt"}
        )
        if operation is not None
        and operation.kind != "resource_alert"
        and operation.actor_id not in {"notifications", "system", ""}
        else None
    )
    linked = experience is not None
    experience = experience or unlinked_worker_context(feature="admin", action="submit", component="page")
    with worker_experience_scope(experience, row.id):
        return await _dispatch_bound_delivery(row, operation, settings, experience, linked, now, dispatch_clock)


async def _dispatch_bound_delivery(row, operation, settings, experience, linked, now, dispatch_clock):
    from app.services import email_service
    from app.services.experience_context import (
        bind_experience_operation,
        emit_experience,
        emit_experience_cleanup,
        fork_experience_call,
    )

    try:
        payload = _payload(row)
    except HTTPException:
        await _set_status(row.id, "failed", "payload_unavailable", expected="pending", now=now)
        return
    try:
        if operation is None:
            reason = "operation_unavailable"
        else:
            reason = await _eligible_delivery(row, operation, payload, settings, dispatch_clock)
        if reason:
            await _set_status(row.id, "cancelled", reason, expected="pending", now=now)
            return
    except HTTPException as exc:
        if exc.status_code in (401, 403, 404, 409, 422):
            await _set_status(row.id, "cancelled", "authority_changed", expected="pending", now=now)
            return
        raise
    message = EmailMessage()
    message["Subject"] = payload["subject"]
    message["From"] = formataddr((settings.smtp.from_name, settings.smtp.from_address))
    message["To"] = row.recipient_email
    message["Message-ID"] = row.message_id
    message.set_content(payload["body"])
    message.add_alternative("<p>" + html.escape(payload["body"]).replace("\n", "<br>\n") + "</p>", subtype="html")
    await bind_experience_operation(experience if linked else None, "email_delivery", row.id)
    await checkpoint()
    if not await _set_status(row.id, "dispatching", expected="pending", now=now):
        return

    async def dispatch_and_settle():
        recorded = False
        try:
            await checkpoint()
            await emit_experience(
                native_experience, "stage.started", stage="native", status="running", operation_id=row.id
            )
            result = await email_service.send_message(message, smtp=settings.smtp)
            # 업무상 최종 상태를 먼저 기록한다. 이후 진단은 best-effort이며 취소돼도 결과를 강등하지 않는다.
            settled = await _set_status(row.id, result.status, result.code)
            recorded = True
            await emit_experience(
                native_experience, "stage.completed", stage="native", status="observed", operation_id=row.id
            )
            if settled:
                status = {"accepted": "accepted", "failed": "failed", "cancelled": "cancelled"}.get(
                    result.status, "outcome_unknown"
                )
                await emit_experience(
                    experience,
                    "worker.state_changed",
                    stage="mail.dispatch",
                    status=status,
                    operation_id=row.id,
                    reason="smtp_accepted" if result.status == "accepted" else None,
                )
        except BaseException:
            if not recorded:
                settled = await _set_status(row.id, "unknown", "dispatch_outcome_unknown")
                if settled:
                    await emit_experience(
                        experience,
                        "worker.state_changed",
                        stage="mail.dispatch",
                        status="outcome_unknown",
                        operation_id=row.id,
                        reason="unknown",
                    )
            raise

    # Own both the actual SMTP transport and terminal SQL write. Neither caller
    # cancellation nor diagnostic cancellation may abandon them or replay DATA.
    native_experience = fork_experience_call(experience)
    task = asyncio.create_task(dispatch_and_settle())
    try:
        await emit_experience(
            experience,
            "worker.claimed",
            stage="mail.dispatch",
            status="running",
            operation_id=row.id,
            reason=None if linked else "unlinked",
        )
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await emit_experience_cleanup(
            native_experience,
            "worker.state_changed",
            stage="mail.dispatch",
            status="cancel_requested",
            operation_id=row.id,
            reason="aborted",
        )
        await drain_task(task)
        await emit_experience_cleanup(
            native_experience,
            "worker.state_changed",
            stage="native.drain",
            status="observed",
            operation_id=row.id,
            reason="aborted",
        )
        raise


async def _dispatch_pending(now, dispatch_clock, batch_size, excluded=()):
    async with _factory()() as session:
        ids = list(
            (
                await session.scalars(
                    select(EmailDelivery.id)
                    .where(
                        EmailDelivery.status == "pending",
                        EmailDelivery.available_at <= now,
                        EmailDelivery.id.not_in(excluded),
                    )
                    .order_by(
                        case((EmailDelivery.kind.in_(("test", "individual")), 0), else_=1),
                        EmailDelivery.available_at,
                        EmailDelivery.id,
                    )
                    .limit(batch_size)
                )
            ).all()
        )
    for delivery_id in ids:
        await checkpoint()
        try:
            await _dispatch_one(delivery_id, now=dispatch_clock)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Email delivery unavailable")
    return ids


async def scheduler_tick(*, now=None, batch_size=50, recover_dispatching=False):
    """One bounded SQL pass. Recovery requires exclusive dispatcher ownership."""
    if not is_db_available() or get_session_factory() is None:
        return
    dispatch_now = now
    now = _utc(now or _now())
    batch_size = max(1, min(batch_size, 200))
    await checkpoint()
    if recover_dispatching:
        async with _factory()() as session, session.begin():
            await session.execute(
                update(EmailDelivery)
                .where(EmailDelivery.status == "dispatching")
                .values(status="unknown", error_code="worker_interrupted", updated_at=now)
            )
    settings = await mail_settings.effective_settings()
    if settings.smtp.enabled:
        # Existing explicit work is served before any potentially large native
        # audience traversal; neither expansion nor old announcements starve tests.
        processed = await _dispatch_pending(now, dispatch_now, batch_size)
        await _expand_announcements(now, batch_size)
        if len(processed) < batch_size:
            await _dispatch_pending(now, dispatch_now, batch_size - len(processed), processed)
    try:
        await _collect_notifications(settings, now, batch_size)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("Email activity notification collection unavailable")
    if settings.notifications.resource_alerts_enabled:
        from app.services import mail_resource_notifications

        try:
            await mail_resource_notifications.scan_notifications()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Email resource notification collection unavailable")


async def scheduler_loop():
    while True:
        try:
            # A previous pass has drained all SMTP tasks before returning, so
            # any remaining dispatching record has an uncertain SQL settlement.
            await scheduler_tick(recover_dispatching=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            # SQL/SMTP/provider diagnostics can contain payloads and credentials.
            logger.warning("Email delivery pass unavailable")
        await asyncio.sleep(5)
