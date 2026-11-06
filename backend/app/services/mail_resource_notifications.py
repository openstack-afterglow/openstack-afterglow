"""Email the existing project error/quota/usage signals without dashboard GET effects.

Only opted-in humans are scanned. Native project membership is fresh, incomplete
observations never clear a signal, and durable episodes prevent polling spam.
The delivery service rechecks recipient/preferences/project access before SMTP.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.database import get_session_factory
from app.models.db import RuntimeSetting
from app.models.instance_usage import aware_timestamp
from app.services import cinder, domain_projects, identity_roles, instance_usage, keystone, nova
from app.services.instance_usage_scheduler import _connection
from app.services.work_dispatcher import checkpoint

_logger = logging.getLogger(__name__)
_field = identity_roles._field
_CURSOR = "mail.current-notifications.cursor"
_USERS_PER_SCAN = 2
_PROJECTS_PER_USER = 2
_INTERVAL_SECONDS = 60


@dataclass(frozen=True)
class Signal:
    subject: str
    body: str


def _now():
    return datetime.now(UTC)


def _key(kind, user_id, home, project_id=""):
    digest = hashlib.sha256(f"{user_id}\0{home}\0{project_id}".encode()).hexdigest()
    return f"mail.{kind}.{digest}"


def _urgency(schedule, clock):
    # Same thresholds/order as the existing usageScheduleBell/scheduleUrgency.
    if schedule.last_error or schedule.state not in {"active", "complete"}:
        return "attention"
    if schedule.state == "complete":
        return None
    remaining = (aware_timestamp(schedule.expires_at) - clock).total_seconds()
    if remaining <= 0:
        return "expired"
    if remaining <= 86400:
        return "oneDay"
    if remaining <= 3 * 86400:
        return "threeDays"
    return "week" if remaining <= 7 * 86400 else None


def _quota_signal(resource, entry, project_id):
    if not isinstance(entry, dict):
        raise ValueError("notification_quota_unavailable")
    used, limit = entry.get("in_use"), entry.get("limit")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in (used, limit)
    ):
        raise ValueError("notification_quota_unavailable")
    if used < 0 or limit < -1:
        raise ValueError("notification_quota_unavailable")
    if limit == -1 or (limit == 0 and used == 0) or (limit > 0 and used < limit * 0.9):
        return None
    level = "full" if used >= limit else "warning"
    return (
        f"{resource}:{level}",
        Signal(
            "Project quota alert",
            f"Native project quota for {resource} is {level}. Project: {project_id}. "
            f"Observed usage: {used}; native limit: {limit}. Other domain/policy limits may also apply. "
            "Open the console to inspect the current project.",
        ),
    )


def _observe_project(conn, project_id, clock):
    """Complete each observation group independently; no unknown-to-zero fallback."""
    instance_usage.prove_project_scope(conn, project_id)
    signals, groups = {}, set()
    try:
        servers = list(instance_usage.safe_compute_proxy(conn).servers(details=True))
        for server in servers:
            instance_usage.require_server_scope(conn, server)
        error_count = sum(_field(server, "status") == "ERROR" for server in servers)
        if error_count:
            signals["instance_error:current"] = Signal(
                "Project instance error alert",
                f"Project {project_id} currently has {error_count} instance(s) in ERROR. Open the console to inspect them.",
            )
        for server in servers:
            instance_id = _field(server, "id")
            try:
                schedule = instance_usage.parse_schedule(server)
            except HTTPException:
                signals[f"usage:{instance_id}:invalid"] = Signal(
                    "Instance usage schedule needs attention",
                    f"The usage schedule for instance {instance_id} in project {project_id} cannot be verified. "
                    "Open the console and ask an administrator to inspect its schedule.",
                )
                continue
            if schedule is None:
                continue
            urgency = _urgency(schedule, clock)
            if urgency:
                signals[f"usage:{instance_id}:{schedule.revision}:{urgency}"] = Signal(
                    "Instance usage schedule reminder",
                    f"Instance {instance_id} in project {project_id}: {urgency}. "
                    f"Scheduled expiry: {schedule.expires_at}; action: {schedule.expiry_action}. "
                    "Open the console to inspect or extend its schedule. This email does not change the instance.",
                )
        groups.update({"instance_error:", "usage:"})
    except Exception as exc:
        _logger.warning("Mail instance observation unavailable (%s)", type(exc).__name__)
        # A partially built server observation cannot authorize any email.
        signals = {key: value for key, value in signals.items() if not key.startswith(("instance_error:", "usage:"))}
    for group, read, resources in (
        (
            "quota_compute:",
            lambda: nova.get_project_quota(conn, project_id, strict=True),
            ("instances", "cores", "ram"),
        ),
        ("quota_storage:", lambda: cinder.get_volume_quota(conn, project_id, strict=True), ("volumes", "gigabytes")),
    ):
        try:
            quotas = read()
            observed = {}
            for resource in resources:
                signal = _quota_signal(resource, quotas.get(resource), project_id)
                if signal is not None:
                    key, value = signal
                    observed[group + key] = value
            signals.update(observed)
            groups.add(group)
        except Exception as exc:
            _logger.warning("Mail quota observation unavailable (%s)", type(exc).__name__)
    return signals, groups


async def _claim_episodes(factory, key, signals, groups):
    """Pending episode IDs survive queue failures; enqueue dedup makes retry safe."""
    await checkpoint()
    try:
        async with factory() as session, session.begin():
            row = await session.get(RuntimeSetting, key, with_for_update=True)
            previous = row.value_json if row is not None else {}
            if not isinstance(previous, dict):
                raise ValueError("notification_episode_state_invalid")
            active = copy.deepcopy(previous.get("active", {}))
            if not isinstance(active, dict):
                raise ValueError("notification_episode_state_invalid")
            active = {
                name: value
                for name, value in active.items()
                if name in signals or not any(name.startswith(group) for group in groups)
            }
            pending = []
            for name, signal in signals.items():
                episode = active.get(name)
                if episode is None:
                    episode = active[name] = {"id": str(uuid4()), "queued": False}
                if (
                    not isinstance(episode, dict)
                    or not isinstance(episode.get("id"), str)
                    or type(episode.get("queued")) is not bool
                ):
                    raise ValueError("notification_episode_state_invalid")
                if not episode["queued"]:
                    pending.append((name, episode["id"], signal))
            if row is None:
                row = RuntimeSetting(setting_key=key, value_json={"active": active})
                session.add(row)
            elif previous.get("active") != active:
                row.value_json = {"active": active}
            await checkpoint()
        return pending
    except IntegrityError:
        # Another claimant established the state; never emit uncommitted IDs.
        return []


async def _mark_queued(factory, key, name, episode_id):
    await checkpoint()
    async with factory() as session, session.begin():
        row = await session.get(RuntimeSetting, key, with_for_update=True)
        if row is None:
            return
        value = copy.deepcopy(row.value_json)
        episode = value.get("active", {}).get(name)
        if episode and episode.get("id") == episode_id:
            episode["queued"] = True
            row.value_json = value


async def _reserve_scan(factory, clock):
    await checkpoint()
    try:
        async with factory() as session, session.begin():
            row = await session.get(RuntimeSetting, _CURSOR, with_for_update=True)
            value = row.value_json if row is not None else {}
            if not isinstance(value, dict):
                raise ValueError("notification_scan_cursor_invalid")
            if value.get("next_at") and aware_timestamp(value["next_at"]) > clock:
                return None
            offset = value.get("offset", 0)
            if type(offset) is not int or offset < 0:
                raise ValueError("notification_scan_cursor_invalid")
            value = {"offset": offset, "next_at": (clock + timedelta(seconds=_INTERVAL_SECONDS)).isoformat()}
            if row is None:
                session.add(RuntimeSetting(setting_key=_CURSOR, value_json=value))
            else:
                row.value_json = value
            return offset
    except IntegrityError:
        return None


async def _cursor(factory, key, field, value=None):
    async with factory() as session, session.begin():
        row = await session.get(RuntimeSetting, key, with_for_update=value is not None)
        previous = row.value_json if row is not None else {}
        if not isinstance(previous, dict):
            raise ValueError("notification_cursor_invalid")
        if value is None:
            result = previous.get(field, "")
            if not isinstance(result, str):
                raise ValueError("notification_cursor_invalid")
            return result
        await checkpoint()
        updated = {**previous, field: value}
        if row is None:
            session.add(RuntimeSetting(setting_key=key, value_json=updated))
        else:
            row.value_json = updated


async def _projects(user_id, home):
    ks = await instance_usage.sdk_call(keystone._get_admin_ks_client)
    user = await instance_usage.sdk_call(ks.users.get, user_id)
    if _field(user, "id") != user_id or _field(user, "domain_id") != home or _field(user, "enabled") is not True:
        return []
    rows = await instance_usage.sdk_call(lambda: list(ks.projects.list(user=user_id)))
    projects = set()
    for project in rows:
        project_id = _field(project, "id")
        if not isinstance(project_id, str) or not project_id:
            raise ValueError("notification_project_inventory_invalid")
        if _field(project, "enabled") is True:
            projects.add(project_id)
    return sorted(projects)


async def _member(user_id, project_id):
    await instance_usage.sdk_call(domain_projects.assert_project_membership, user_id, project_id)


async def scan_notifications(*, now=None):
    from app.services import mail_delivery, mail_settings

    config = await mail_settings.effective_settings()
    if not config.smtp.enabled or not config.notifications.resource_alerts_enabled:
        return
    factory = get_session_factory()
    if factory is None:
        return
    clock = aware_timestamp(now) if now is not None else _now()
    after = await _reserve_scan(factory, clock)
    if after is None:
        return
    subscribers = await mail_delivery.list_notification_subscribers(offset=after, limit=_USERS_PER_SCAN)
    if not subscribers and after:
        after = 0
        subscribers = await mail_delivery.list_notification_subscribers(offset=0, limit=_USERS_PER_SCAN)
    for subscriber in subscribers:
        user_id, home = subscriber["user_id"], subscriber["identity_domain_id"]
        project_cursor = _key("notification-project", user_id, home)
        try:
            projects = await _projects(user_id, home)
            last = await _cursor(factory, project_cursor, "project_id")
            selected = [project for project in projects if project > last][:_PROJECTS_PER_USER]
            if not selected:
                selected = projects[:_PROJECTS_PER_USER]
            for project_id in selected:
                try:
                    await checkpoint()
                    await _member(user_id, project_id)
                    async with _connection(keystone.get_admin_connection_for_project, project_id) as conn:
                        signals, groups = await instance_usage.sdk_call(_observe_project, conn, project_id, clock)
                    await _member(user_id, project_id)
                    key = _key("notification-signals", user_id, home, project_id)
                    pending = await _claim_episodes(factory, key, signals, groups)
                    for name, episode, signal in pending:
                        await checkpoint()
                        result = await mail_delivery.enqueue_notification(
                            user_id=user_id,
                            expected_identity_domain_id=home,
                            project_id=project_id,
                            event_key=f"current-signal:{episode}",
                            subject=signal.subject,
                            body=signal.body,
                        )
                        if result is not None:
                            await _mark_queued(factory, key, name, episode)
                except Exception as exc:
                    _logger.warning("Mail current-project signal unavailable (%s)", type(exc).__name__)
                await _cursor(factory, project_cursor, "project_id", project_id)
        except Exception as exc:
            _logger.warning("Mail current-user signals unavailable (%s)", type(exc).__name__)
    await _cursor(factory, _CURSOR, "offset", after + len(subscribers))
