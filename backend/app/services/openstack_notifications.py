"""Opt-in oslo.messaging RabbitMQ consumer; independent of HTTP request auditing.

The caller owns start/stop and must stop before disposing the database. Each
configured service/exchange/topic gets a dedicated durable queue. Never attach to
an OpenStack service's RPC queue or another notification consumer's queue.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import Settings, get_settings
from app.database import get_session_factory
from app.models.activity import ActivityLog

logger = logging.getLogger(__name__)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]*\Z")
_PRIORITIES = {"debug", "info", "audit", "warn", "warning", "error", "critical", "fatal"}
_FAILURES = {"error", "failed", "failure", "exception"}
_SUCCESSES = {"end", "success", "succeeded", "complete", "completed", "created", "updated", "deleted"}
_RESOURCE_KEYS = {
    "instance": ("instance_id", "instance_uuid"),
    "volume": ("volume_id",),
    "snapshot": ("snapshot_id",),
    "backup": ("backup_id",),
    "network": ("network_id",),
    "port": ("port_id",),
    "subnet": ("subnet_id",),
    "router": ("router_id",),
    "floatingip": ("floatingip_id",),
    "image": ("image_id",),
    "user": (),
    "project": (),
    "role": (),
    "group": (),
    "trust": (),
}


class InvalidNotification(ValueError):
    """Malformed/unsupported input, never containing payload in its message."""


def _mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _identifier(value: Any, limit: int) -> str | None:
    # No coercion of arbitrary objects, clipping, free-form names or error text.
    if isinstance(value, str) and len(value) <= limit and _IDENTIFIER.fullmatch(value):
        return value
    return None


def _first_id(sources: tuple[dict, ...], keys: tuple[str, ...], limit: int = 64) -> str | None:
    for source in sources:
        for key in keys:
            value = _identifier(source.get(key), limit)
            if value:
                return value
    return None


def _unwrap(value: Any) -> dict:
    value = _mapping(value)
    for _ in range(8):
        # Nova versioned notifications and oslo.versionedobjects use the same
        # object envelope. Some service adapters use their own object namespace.
        data_keys = ("nova_object.data", "oslo.versionedobjects.data", "cinder_object.data")
        key = next((key for key in data_keys if key in value), None)
        if key is None:
            return value
        value = _mapping(value[key])
    raise InvalidNotification("versioned envelope is too deeply nested")


def normalize_notification(body: bytes, service: str, *, max_bytes: int = 1048576) -> dict:
    """Return only bounded, allowlisted ActivityLog columns; never retain payload.

    Error prose, names, metadata, auth context and arbitrary extra fields are
    deliberately omitted rather than relying on credential-pattern redaction.
    A body digest is used only when oslo's stable message_id is absent.
    """
    if len(body) > max_bytes:
        raise InvalidNotification("notification exceeds configured size limit")
    try:
        envelope = json.loads(body)
        if not isinstance(envelope, dict):
            raise InvalidNotification("notification must be an object")
        notification = envelope
        for _ in range(4):
            if "oslo.message" not in notification:
                break
            nested = notification["oslo.message"]
            notification = json.loads(nested) if isinstance(nested, str) else nested
            if not isinstance(notification, dict):
                raise InvalidNotification("oslo message must be an object")
        else:
            raise InvalidNotification("oslo envelope is too deeply nested")
        canonical = json.dumps(notification, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise InvalidNotification("invalid notification JSON envelope") from None

    event_type = _identifier(notification.get("event_type"), 255)
    if not event_type or not _identifier(service, 32):
        raise InvalidNotification("notification requires an event type and service")
    payload = _unwrap(notification.get("payload"))
    context = _mapping(notification.get("context")) or _mapping(notification.get("_context"))
    priority_value = notification.get("priority")
    priority = priority_value.lower() if isinstance(priority_value, str) else "unknown"
    if priority not in _PRIORITIES:
        priority = "unknown"
    suffix = event_type.lower().rsplit(".", 1)[-1]
    cadf_outcome = payload.get("outcome") if service == "keystone" else None
    if priority in {"error", "critical", "fatal"} or suffix in _FAILURES or cadf_outcome == "failure":
        status = "failed"
    elif suffix in _SUCCESSES or cadf_outcome == "success":
        status = "success"
    else:
        status = "started"

    # Event families give resource identity priority over related IDs (e.g. a
    # port notification's own id, not the containing network_id).
    parts = re.split(r"[._]", event_type.lower())
    resource_type = next((part for part in parts if part in _RESOURCE_KEYS), "unknown")
    if service == "cinder" and resource_type == "volume":
        # Cinder nests snapshot/backup event names under volume; Nova's
        # instance.volume_attach still concerns the instance, not the volume.
        resource_type = next((part for part in parts if part in {"snapshot", "backup"}), "volume")
    resource = _unwrap(payload.get(resource_type)) or payload
    if resource_type == "unknown":
        for kind, keys in _RESOURCE_KEYS.items():
            if _first_id((payload,), keys, 128):
                resource_type = kind
                break
    resource_keys = _RESOURCE_KEYS.get(resource_type, ())
    resource_id = _first_id((resource, payload), (*resource_keys, "uuid", "id", "resource_id"), 128)
    # CADF payload.id identifies the audit event, NOT the affected resource.
    # Keystone Basic and CADF mutations both emit resource_info; target is the
    # fallback for authentication and other CADF events without resource_info.
    if service == "keystone":
        keystone_resource = _first_id((payload,), ("resource_info",), 128)
        keystone_resource = keystone_resource or _first_id((_mapping(payload.get("target")),), ("id",), 128)
        if keystone_resource or "eventType" in payload or "typeURI" in payload:
            resource_id = keystone_resource
    project_id = _first_id((resource, payload, context), ("project_id", "tenant_id"))
    user_id = _first_id((payload, context), ("user_id",))
    project_id = project_id or _first_id(
        (notification,), ("_context_project_id", "_context_tenant_id", "_context_tenant")
    )
    user_id = user_id or _first_id((notification,), ("_context_user_id", "_context_user"))
    if service == "keystone" and not user_id:
        initiator = _mapping(payload.get("initiator"))
        initiator_type = initiator.get("typeURI")
        if isinstance(initiator_type, str) and initiator_type in {
            "service/security/account/user",
            "data/security/account/user",
        }:
            user_id = _first_id((initiator,), ("id",))
    request_id = _first_id(
        (notification, context, payload),
        ("request_id", "_context_request_id"),
        64,
    )
    request_id = request_id or _first_id(
        (notification, context, payload),
        ("global_request_id", "_context_global_request_id"),
        64,
    )
    message_id = notification.get("message_id")
    identity = message_id if isinstance(message_id, str) and message_id else canonical
    identity_bytes = json.dumps([service, identity], ensure_ascii=True, separators=(",", ":")).encode()
    external_id = "oslo:" + hashlib.sha256(identity_bytes).hexdigest()
    extra: dict[str, Any] = {"priority": priority, "normalization_version": 1}
    exception = _unwrap(payload.get("exception")) or _unwrap(payload.get("fault"))
    code = exception.get("code", payload.get("exception_code"))
    if code is None and service == "keystone":
        code = _mapping(payload.get("reason")).get("reasonCode")
    http_status = code if type(code) is int and 100 <= code <= 599 else None
    if http_status is not None:
        extra["error_code"] = http_status
    error_type = (
        _first_id((exception,), ("exception", "exception_name", "exception_type", "type", "name"), 64)
        if status == "failed"
        else None
    )
    if status == "failed" and not error_type:
        error_type = _first_id((payload,), ("exception_name", "exception_type"), 64)
    if error_type and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", error_type):
        extra["error_type"] = error_type
    result = {
        "source": "openstack",
        "service": service,
        "event_type": event_type[:128],
        "request_id": request_id,
        "external_id": external_id,
        "http_status": http_status,
        "page": None,
        "project_id": project_id or "",
        "user_id": user_id or "",
        "username": "",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "resource_name": None,
        "action": event_type[:48],
        "status": status,
        "error_message": "OpenStack notification reported failure; raw error details omitted."
        if status == "failed"
        else None,
        "extra": extra,
    }
    timestamp = notification.get("timestamp")
    if isinstance(timestamp, str) and len(timestamp) <= 40:
        with suppress(ValueError, OverflowError):
            created_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            result["created_at"] = (
                created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at.astimezone(UTC)
            )
    return result


async def persist_notification(values: dict, session_factory=None) -> bool:
    """Commit a new row or prove an existing durable duplicate; propagate outages.

    The unique external_id database constraint, not a check-then-insert or a
    process-local cache, arbitrates concurrent workers and commit/ack crashes.
    """
    factory = session_factory if session_factory is not None else get_session_factory()
    if factory is None:
        raise RuntimeError("notification database is not initialized")
    async with factory() as session:
        session.add(ActivityLog(**values))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            # Do not treat unrelated constraint failures as successful delivery.
            existing = await session.scalar(
                select(ActivityLog.id).where(ActivityLog.external_id == values["external_id"])
            )
            if existing is None:
                raise
            return False
    return True


class NotificationCollector:
    """Single lifecycle owner with reconnect and cancellation-safe redelivery."""

    def __init__(self, settings: Settings, connect):
        self.settings = settings
        self._connect = connect
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="openstack-notifications")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def handle_message(self, message, service: str) -> None:
        try:
            values = normalize_notification(
                message.body, service, max_bytes=self.settings.openstack_notifications_max_message_bytes
            )
        except InvalidNotification:
            # Poison input is rejected without logging payload or free-form errors.
            logger.warning("Rejecting malformed OpenStack notification")
            await message.reject(requeue=False)
            return
        try:
            await persist_notification(values)
        except Exception:
            # No exception repr/trace: DB diagnostics can echo statement values.
            logger.warning("OpenStack notification persistence unavailable; requeueing")
            await message.nack(requeue=True)
            raise
        # Cancellation/connection loss after commit leaves safe duplicate delivery.
        await message.ack()

    async def _consume(self, queue, service: str) -> None:
        async with queue.iterator(no_ack=False) as messages:
            async for message in messages:
                await self.handle_message(message, service)
        raise ConnectionError("notification consumer stopped")

    async def _run(self) -> None:
        while True:
            connection = None
            consumers = []
            try:
                # A fresh connection on every retry restores all queues/bindings.
                # Use plain connect so background library reconnect logs never
                # interpolate credentials or a raw connection exception.
                connection = await self._connect(
                    self.settings.openstack_notifications_amqp_url.get_secret_value(), timeout=10
                )
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=1)
                for service, binding in self.settings.openstack_notifications_bindings.items():
                    if not binding.enabled:
                        continue
                    # Publishers own exchanges; passive lookup avoids redeclaring
                    # incompatible durability flags or fabricating notification setup.
                    exchange = await channel.get_exchange(binding.exchange, ensure=True)
                    for routing_key in binding.routing_keys:
                        identity = f"{service}\0{binding.exchange}\0{routing_key}"
                        suffix = hashlib.sha256(identity.encode()).hexdigest()[:24]
                        name = f"{self.settings.openstack_notifications_queue_prefix}.{service}.{suffix}"
                        queue = await channel.declare_queue(name, durable=True, auto_delete=False, exclusive=False)
                        await queue.bind(exchange, routing_key=routing_key)
                        consumers.append(asyncio.create_task(self._consume(queue, service)))
                await asyncio.gather(*consumers)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("OpenStack notification connection/consumer unavailable; retrying")
            finally:
                for consumer in consumers:
                    consumer.cancel()
                if consumers:
                    await asyncio.gather(*consumers, return_exceptions=True)
                if connection is not None:
                    with suppress(Exception):
                        await connection.close()
            await asyncio.sleep(self.settings.openstack_notifications_retry_seconds)


async def start_notification_collector(settings: Settings | None = None) -> NotificationCollector | None:
    """Start after DB initialization; returns immediately while broker retries run.

    Disabled startup does not import the AMQP client or contact any
    broker. Invalid enabled config fails fast without disclosing credentials.
    """
    settings = settings or get_settings()
    if not settings.openstack_notifications_enabled:
        return None
    try:
        url = urlsplit(settings.openstack_notifications_amqp_url.get_secret_value())
        valid_url = (
            url.scheme in {"amqp", "amqps"}
            and bool(url.hostname)
            and bool(url.username)
            and bool(url.password)
            and url.port != 0
        )
    except ValueError:
        valid_url = False
    if not valid_url:
        raise ValueError("enabled notifications require a configured AMQP(S) URL with explicit credentials")
    if not any(binding.enabled for binding in settings.openstack_notifications_bindings.values()):
        raise ValueError("enabled notifications require at least one enabled service binding")
    try:
        from aio_pika import connect
    except ImportError:
        raise RuntimeError("install the backend dependencies to enable OpenStack notifications") from None
    collector = NotificationCollector(settings, connect)
    collector.start()
    return collector


async def stop_notification_collector(collector: NotificationCollector | None) -> None:
    """Stop consuming and return unacknowledged messages before DB disposal."""
    if collector is not None:
        await collector.stop()
