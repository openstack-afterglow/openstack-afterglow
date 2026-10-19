"""Read-only projections of retained ActivityLog rows and current Redis sessions.

No auth writes, credential introspection, online inference or failure-event synthesis.
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import UTC, datetime, timedelta
from itertools import islice
from typing import Literal

from fastapi import HTTPException
from keystoneauth1 import exceptions as auth_exc
from openstack.exceptions import ForbiddenException, ResourceNotFound
from sqlalchemy import select

from app.config import get_settings
from app.database import get_session_factory, is_db_available
from app.models.activity import ActivityLog
from app.services import session_store
from app.services.cache import _get_redis

Window = Literal["24h", "7d", "30d"]
WINDOW_HOURS = {"24h": 24, "7d": 168, "30d": 720}
EVENT_LIMIT = 10000
RECENT_LIMIT = 100
SESSION_SCAN_LIMIT = 50000
SESSION_SCAN_BATCH = 500


def _native_error(exc: Exception) -> HTTPException:
    status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    if isinstance(exc, (ForbiddenException, auth_exc.Forbidden)) or status in (401, 403):
        return HTTPException(403, "login_monitoring_native_denied")
    if isinstance(exc, (ResourceNotFound, auth_exc.NotFound)) or status == 404:
        return HTTPException(404, "login_monitoring_user_not_found")
    return HTTPException(503, "login_monitoring_directory_unavailable")


def _user(user) -> dict:
    return {"id": user.id, "name": user.name or ""}


async def directory(conn, limit: int, marker: str | None) -> dict:
    def fetch():
        # SDK pagination remains native; consume only the requested page.
        kwargs = {"limit": limit}
        if marker:
            kwargs["marker"] = marker
        users = [_user(user) for user in islice(conn.identity.users(**kwargs), limit)]
        return {"items": users, "next_marker": users[-1]["id"] if len(users) == limit else None}

    try:
        return await asyncio.to_thread(fetch)
    except Exception as exc:
        raise _native_error(exc) from exc


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _stamp(value: float | int) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat()


def _number(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and 0 < number < 253402300799 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _login_method(row: ActivityLog) -> str | None:
    if not (
        row.resource_type == "auth" and row.action == "login" and row.source == "afterglow" and row.status == "success"
    ):
        return None
    # Password hook has no extra; OIDC hook explicitly records method=federated.
    if row.extra is None or row.extra == {}:
        return "password"
    if isinstance(row.extra, dict) and row.extra.get("method") == "federated":
        return "federated"
    return None


async def _history(user_id: str, now: datetime, window: Window) -> dict:
    unavailable = {
        "state": "unavailable",
        "events": None,
        "timeline": None,
        "hour_distribution": None,
        "login_successes": None,
        "recorded_login_failures": None,
        "failure_history": "not_collected",
    }
    factory = get_session_factory()
    if not is_db_available() or factory is None:
        return unavailable
    start = now - timedelta(hours=WINDOW_HOURS[window])
    conditions = [
        ActivityLog.user_id == user_id,
        ActivityLog.created_at >= start.replace(tzinfo=None),
        ActivityLog.created_at <= now.replace(tzinfo=None),
    ]
    try:
        async with factory() as session:
            # Project and secret-bearing fields never enter the public projection implicitly.
            recent = (
                (
                    await session.execute(
                        select(ActivityLog)
                        .where(*conditions)
                        .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
                        .limit(RECENT_LIMIT)
                    )
                )
                .scalars()
                .all()
            )
            logins = (
                (
                    await session.execute(
                        select(ActivityLog)
                        .where(
                            *conditions,
                            ActivityLog.resource_type == "auth",
                            ActivityLog.action == "login",
                            ActivityLog.source == "afterglow",
                        )
                        .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
                        .limit(EVENT_LIMIT + 1)
                    )
                )
                .scalars()
                .all()
            )
    except Exception:
        return unavailable
    partial = len(logins) > EVENT_LIMIT
    logins = logins[:EVENT_LIMIT]
    # Fixed UTC hour boundaries: both partial edge buckets are included.
    bucket_start = start.replace(minute=0, second=0, microsecond=0)
    count = int((now - bucket_start).total_seconds() // 3600) + 1
    timeline = [
        {"at": (bucket_start + timedelta(hours=i)).isoformat(), "successes": 0, "recorded_failures": 0}
        for i in range(count)
    ]
    hours = [{"hour": hour, "successes": 0, "recorded_failures": 0} for hour in range(24)]
    successes = failures = 0
    for row in logins:
        field = "successes" if row.status == "success" else "recorded_failures" if row.status == "failed" else None
        if field is None:
            continue
        at = _utc(row.created_at)
        timeline[int((at - bucket_start).total_seconds() // 3600)][field] += 1
        hours[at.hour][field] += 1
        successes += field == "successes"
        failures += field == "recorded_failures"
    return {
        "state": "partial" if partial else "ready",
        "events": [
            {
                "at": _utc(row.created_at).isoformat(),
                "project_id": row.project_id,
                "resource_type": row.resource_type,
                "action": row.action,
                "status": row.status,
                "auth_method": _login_method(row),
            }
            for row in recent
        ],
        "timeline": timeline,
        "hour_distribution": hours,
        "login_successes": successes,
        "recorded_login_failures": failures,
        # Existing password and OIDC hooks record success only; zero is not evidence of no failures.
        "failure_history": "not_collected",
        "event_limit": EVENT_LIMIT,
        "recent_limit": RECENT_LIMIT,
    }


async def _sessions(user_id: str, now: datetime) -> dict:
    unknown = {"state": "unknown", "items": None, "valid_count": None, "observed_recent_count": None}
    try:
        redis = await _get_redis()
        # An absent secondary index cannot prove that no session records exist.
        if not await redis.exists(session_store._user_index_key(user_id)):
            return unknown
        inventory_size = await redis.scard(session_store._user_index_key(user_id))
        rows = await session_store.list_user_sessions(user_id)
    except Exception:
        return {**unknown, "state": "unavailable"}
    timestamp = now.timestamp()
    timeout = get_settings().session_timeout_seconds
    items = []
    incomplete = inventory_size != len(rows)
    for row in rows:
        if row.get("user_id") != user_id:
            incomplete = True
            continue
        if row.get("blacklisted") is True:
            continue
        exp = _number(row.get("exp"))
        start = _number(row.get("started_at"))
        if exp is not None and exp <= timestamp:
            continue
        if start is not None and start + timeout <= timestamp:
            continue
        if exp is None or start is None or start > timestamp or not isinstance(row.get("blacklisted"), bool):
            incomplete = True
            continue
        seen = _number(row.get("last_seen"))
        if seen is not None and not start <= seen <= timestamp:
            seen = None
        # Explicit allowlist. JTI, token, origin/last fingerprint, IP and arbitrary metadata are omitted.
        items.append(
            {
                "started_at": _stamp(start),
                "last_seen": _stamp(seen) if seen else None,
                "expires_at": _stamp(min(exp, start + timeout)),
                "refresh_expires_at": _stamp(exp),
                "project_id": row.get("project_id") if isinstance(row.get("project_id"), str) else None,
                "device_type": row.get("device_type")
                if isinstance(row.get("device_type"), str)
                and row["device_type"] in {"desktop", "mobile", "tablet", "unknown"}
                else None,
                "os": row.get("os")
                if isinstance(row.get("os"), str) and row["os"] in {"Windows", "macOS", "Linux", "Android", "iOS"}
                else None,
                "auth_method": row.get("auth_method")
                if isinstance(row.get("auth_method"), str) and row["auth_method"] in {"password", "federated"}
                else None,
                "observed_recently": seen is not None and timestamp - seen <= 300,
            }
        )
    items.sort(key=lambda item: item["started_at"], reverse=True)
    return {
        "state": "partial" if incomplete else "ready",
        "items": items,
        "valid_count": None if incomplete else len(items),
        "observed_recent_count": None if incomplete else sum(item["observed_recently"] for item in items),
    }


async def selected_user(conn, user_id: str, window: Window) -> dict:
    try:
        user = await asyncio.to_thread(conn.identity.get_user, user_id)
        if user is None:
            raise HTTPException(404, "login_monitoring_user_not_found")
    except HTTPException:
        raise
    except Exception as exc:
        raise _native_error(exc) from exc
    now = datetime.now(UTC)
    history, sessions = await asyncio.gather(_history(user_id, now, window), _sessions(user_id, now))
    return {
        "user": _user(user),
        "window": window,
        "as_of": now.isoformat(),
        "from_at": (now - timedelta(hours=WINDOW_HOURS[window])).isoformat(),
        "observed_interval_seconds": 300,
        "history": history,
        "sessions": sessions,
    }


async def domain_observation(domain_id: str, user_ids: set[str], project_ids: set[str], window: Window) -> dict:
    """Aggregate retained observations only; IDs are supplied by the native directory.

    Activity in a foreign project never becomes domain activity merely because its
    actor belongs to this domain. Domain-only auth events may have no project.
    No IP, token, JTI or arbitrary ActivityLog metadata reaches this projection.
    """
    from sqlalchemy import and_, or_

    now = datetime.now(UTC)
    start = now - timedelta(hours=WINDOW_HOURS[window])
    logins = {
        "state": "unavailable",
        "successes": None,
        "recorded_failures": None,
        "failure_history": "not_collected",
        "timeline": None,
    }
    activity = {
        "state": "unavailable",
        "recent_users": None,
        "events": None,
        "last_seen": None,
        "hour_distribution": None,
    }
    # Stable note codes; the UI localizes them.
    notes = [
        "login_failure_history_not_collected",
        "activity_is_afterglow_audit_only",
        "sessions_are_not_online_presence",
    ]
    factory = get_session_factory()
    if is_db_available() and factory is not None:
        try:
            async with factory() as session:
                rows = (
                    (
                        await session.execute(
                            select(ActivityLog)
                            .where(
                                or_(
                                    ActivityLog.project_id.in_(project_ids),
                                    and_(
                                        ActivityLog.user_id.in_(user_ids),
                                        ActivityLog.project_id == "",
                                        ActivityLog.resource_type == "auth",
                                    ),
                                ),
                                ActivityLog.created_at >= start.replace(tzinfo=None),
                                ActivityLog.created_at <= now.replace(tzinfo=None),
                            )
                            .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
                            .limit(EVENT_LIMIT + 1)
                        )
                    )
                    .scalars()
                    .all()
                )
            partial = len(rows) > EVENT_LIMIT
            rows = rows[:EVENT_LIMIT]
            bucket_start = start.replace(minute=0, second=0, microsecond=0)
            count = int((now - bucket_start).total_seconds() // 3600) + 1
            timeline = [
                {"at": (bucket_start + timedelta(hours=i)).isoformat(), "successes": 0, "recorded_failures": 0}
                for i in range(count)
            ]
            hours = [{"hour": hour, "events": 0} for hour in range(24)]
            successes = failures = 0
            recent_users = set()
            for row in rows:
                at = _utc(row.created_at)
                hours[at.hour]["events"] += 1
                if row.user_id in user_ids:
                    recent_users.add(row.user_id)
                if (
                    row.user_id not in user_ids
                    or row.resource_type != "auth"
                    or row.action != "login"
                    or row.source != "afterglow"
                ):
                    continue
                key = (
                    "successes" if row.status == "success" else "recorded_failures" if row.status == "failed" else None
                )
                if key:
                    timeline[int((at - bucket_start).total_seconds() // 3600)][key] += 1
                    successes += key == "successes"
                    failures += key == "recorded_failures"
            state = "partial" if partial else "ready"
            logins.update(
                state=state,
                successes=None if partial else successes,
                recorded_failures=None if partial else failures,
                timeline=timeline,
            )
            activity.update(
                state=state,
                recent_users=None if partial else len(recent_users),
                events=None if partial else len(rows),
                last_seen=_utc(rows[0].created_at).isoformat() if rows else None,
                hour_distribution=hours,
            )
            if partial:
                notes.append("activity_observation_limit_exceeded")
        except Exception:
            notes.append("activity_storage_unavailable")
    else:
        notes.append("activity_storage_unavailable")
    sessions = await _domain_sessions(domain_id, user_ids, project_ids, now)
    if sessions["state"] != "ready":
        notes.append("sessions_incomplete")
    if sessions["unattributed_count"]:
        notes.append("sessions_without_domain_attribution")
    return {"logins": logins, "activity": activity, "sessions": sessions, "notes": notes}


async def _domain_sessions(domain_id: str, user_ids: set[str], project_ids: set[str], now: datetime) -> dict:
    """Count refresh-session records, not per-user indexes (absent for idle users).

    Records written before domain attribution are reported separately, never
    assigned to this domain. A capped or unparsable scan is partial.
    """
    result = {
        "state": "unavailable",
        "valid_count": None,
        "observed_recent_count": None,
        "unattributed_count": None,
        "online_count": None,
    }
    timestamp = now.timestamp()
    timeout = get_settings().session_timeout_seconds
    valid = recent = unattributed = 0
    incomplete = False
    try:
        redis = await _get_redis()
        keys = []
        async for key in redis.scan_iter(match=session_store._key("*"), count=SESSION_SCAN_BATCH):
            if len(keys) >= SESSION_SCAN_LIMIT:
                incomplete = True
                break
            keys.append(key)
        raws = []
        for offset in range(0, len(keys), SESSION_SCAN_BATCH):
            raws.extend(await redis.mget(keys[offset : offset + SESSION_SCAN_BATCH]))
    except Exception:
        return result
    for raw in raws:
        if raw is None:
            continue  # Expired between SCAN and MGET.
        try:
            row = json.loads(raw)
            if not isinstance(row, dict):
                raise ValueError
        except ValueError:
            incomplete = True
            continue
        if row.get("user_id") not in user_ids or row.get("blacklisted") is True:
            continue
        exp, start = _number(row.get("exp")), _number(row.get("started_at"))
        if (exp is not None and exp <= timestamp) or (start is not None and start + timeout <= timestamp):
            continue
        if exp is None or start is None or start > timestamp or not isinstance(row.get("blacklisted"), bool):
            incomplete = True
            continue
        stored_domain = row.get("domain_id")
        if not isinstance(stored_domain, str) or not stored_domain:
            unattributed += 1
            continue
        project = row.get("project_id")
        if stored_domain != domain_id or (project and project not in project_ids):
            continue
        valid += 1
        seen = _number(row.get("last_seen"))
        recent += seen is not None and start <= seen <= timestamp and timestamp - seen <= 300
    return {
        "state": "partial" if incomplete else "ready",
        "valid_count": valid,
        "observed_recent_count": recent,
        "unattributed_count": unattributed,
        "online_count": None,
    }
