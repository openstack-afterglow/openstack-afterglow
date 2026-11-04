"""Bounded, opt-in SQL semantic diagnostics, independent of business ledgers."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import TypeAdapter
from pymysql.err import IntegrityError as MySQLIntegrityError
from sqlalchemy import case, delete, exists, func, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import get_session_factory, is_db_available
from app.models.activity import ActivityLog
from app.models.experience import (
    Action,
    Component,
    ExperienceAggregate,
    ExperienceCatalog,
    ExperienceEvent,
    ExperienceHold,
    ExperienceMaintenance,
    ExperienceOperationLink,
    ExperienceRecord,
    Feature,
    revision_string,
    uuid_string,
)
from app.services.interaction_policy import canonical_page, public_page
from app.utils.version import read_app_version

STAGES = frozenset(
    {
        "request",
        "api",
        "auth",
        "native",
        "native.drain",
        "blocking",
        "blocking.drain",
        "readback",
        "worker",
        "cleanup",
        "build.admission",
        "mail.admission",
        "mail.dispatch",
        "mcp.admission",
        "mcp.dispatch",
        "notion.sync",
    }
)
STATUSES = frozenset(
    {"observed", "accepted", "running", "succeeded", "failed", "cancel_requested", "cancelled", "outcome_unknown"}
)
REASONS = frozenset(
    {
        "unknown",
        "aborted",
        "lease_lost",
        "unlinked",
        "transport_complete",
        "transport_incomplete",
        "smtp_accepted",
        "pending_cleanup",
    }
)
SERVER_TYPES = frozenset(
    {
        "request.started",
        "request.completed",
        "stage.started",
        "stage.completed",
        "operation.accepted",
        "operation.state_changed",
        "worker.claimed",
        "worker.state_changed",
        "telemetry.gap",
    }
)
OPERATION_KINDS = frozenset(
    {"mcp_invocation", "library_build", "layer_build", "dockerfile_import", "email_operation", "email_delivery"}
)
_UUID_FIELDS = (
    "segment_id",
    "page_view_id",
    "action_id",
    "caused_by_event_id",
    "trace_id",
    "span_id",
    "parent_span_id",
)
BACKEND_BUILD = read_app_version()


class ExperienceUnavailable(RuntimeError):
    pass


class ExperienceConflict(ValueError):
    pass


def _integrity_code(error: IntegrityError) -> int | None:
    original = error.orig
    if isinstance(original, sqlite3.IntegrityError):
        return original.sqlite_errorcode
    if isinstance(original, MySQLIntegrityError):
        args = BaseException.args.__get__(original)
        return args[0] if args and type(args[0]) is int else None
    return None


async def lock_maintenance(session) -> None:
    """Serialize hold changes and deletion in their own SQL transaction.

    Updating a shared row also creates a write conflict across Galera nodes;
    process-local or server-local advisory locks cannot provide that boundary.
    A failed/uncertain commit is never automatically replayed.
    """
    guard = await session.get(ExperienceMaintenance, 1, with_for_update=True)
    if guard is None:
        try:
            async with session.begin_nested():
                session.add(ExperienceMaintenance(id=1, revision=0))
                await session.flush()
        except IntegrityError as exc:
            if _integrity_code(exc) not in {
                1062,
                sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY,
                sqlite3.SQLITE_CONSTRAINT_UNIQUE,
            }:
                raise
        guard = await session.get(ExperienceMaintenance, 1, with_for_update=True, populate_existing=True)
    if guard is None:
        raise ExperienceUnavailable("Maintenance ownership is unavailable")
    guard.revision += 1
    await session.flush()


def enabled() -> bool:
    return get_settings().experience_enabled is True


def _factory():
    factory = get_session_factory()
    if not is_db_available() or factory is None:
        raise ExperienceUnavailable("Diagnostic SQL is unavailable")
    return factory


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _actor(actor: dict) -> dict:
    result = {}
    for key in ("user_id", "project_id"):
        value = actor.get(key, "")
        if not isinstance(value, str) or (value and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value)):
            raise ValueError("Invalid trusted actor")
        result[key] = value
    if result["project_id"] and not result["user_id"]:
        raise ValueError("Missing trusted user")
    return result


def _context(context: dict) -> dict:
    actor = _actor(context.get("actor", {}))
    route = canonical_page(context.get("route", "/"))
    safe = {key: uuid_string(context[key]) if context.get(key) is not None else None for key in _UUID_FIELDS}
    if not safe["segment_id"] or not safe["page_view_id"]:
        raise ValueError("Missing context")
    source = context.get("source", "api")
    if source not in {"api", "worker"}:
        raise ValueError("Invalid server source")
    request_id = context.get("request_id")
    if request_id is not None and not re.fullmatch(r"req-[a-f0-9]{32}", request_id):
        raise ValueError("Invalid request reference")
    labels = {}
    for key, vocabulary in (("feature", Feature), ("action", Action), ("component", Component)):
        value = context[key]
        labels[key] = "unknown" if value == "unknown" else TypeAdapter(vocabulary).validate_python(value)
    safe.update(
        actor=actor,
        source=source,
        route=route,
        request_id=request_id,
        **labels,
        frontend_build=revision_string(context.get("frontend_build", "unknown")),
        catalog_revision=revision_string(context.get("catalog_revision", "unknown")),
    )
    return safe


def _record(data: dict, actor: dict, source: str, received_at: datetime, fingerprint: str) -> ExperienceRecord:
    return ExperienceRecord(
        received_at=received_at,
        owner_key=_digest(actor),
        user_id=actor["user_id"],
        project_id=actor["project_id"],
        segment_id=data["segment_id"],
        event_id=data["event_id"],
        action_id=data.get("action_id"),
        source=source,
        fingerprint=fingerprint,
        data=data,
    )


async def _retain_catalog(session, row: ExperienceRecord) -> None:
    if row.data.get("event_type") != "message.presented":
        return
    payload = row.data["payload"]
    key = payload.get("key")
    if not key:
        return
    from app.services.experience_catalog import catalog_entry

    identifier = _digest([row.data["catalog_revision"], key, payload["locale"]])
    stored = await session.get(ExperienceCatalog, identifier, with_for_update=True)
    if stored is None:
        entry = catalog_entry(row.data["catalog_revision"], key, payload["locale"])
        if entry is None:
            return
        session.add(ExperienceCatalog(id=identifier, **entry))
        await session.flush()
    row.catalog_id = identifier


async def ingest(*, actor: dict, events: list[ExperienceEvent], request_id: str | None = None) -> dict:
    if not enabled():
        raise ExperienceUnavailable("Experience is disabled")
    principal = _actor(actor)
    if not principal["user_id"] and any(not public_page(event.route) for event in events):
        raise ValueError("Anonymous private context")
    owner = _digest(principal)
    received = datetime.now(UTC)
    # Retrying a diagnostic insert after a unique-key race does not replay business work.
    for attempt in range(2):
        try:
            async with _factory()() as session:
                async with session.begin():
                    accepted = duplicates = 0
                    for event in events:
                        wire = event.model_dump(exclude_none=True)
                        fingerprint = _digest(wire)
                        existing = await session.scalar(
                            select(ExperienceRecord).where(
                                ExperienceRecord.owner_key == owner,
                                ExperienceRecord.segment_id == event.segment_id,
                                ExperienceRecord.event_id == event.event_id,
                            )
                        )
                        if existing is not None:
                            if existing.fingerprint != fingerprint or existing.source != "browser":
                                raise ExperienceConflict("Event identity conflict")
                            duplicates += 1
                            continue
                        data = {**wire, "backend_build": BACKEND_BUILD, "request_id": request_id}
                        row = _record(data, principal, "browser", received, fingerprint)
                        await _retain_catalog(session, row)
                        session.add(row)
                        await session.flush()
                        accepted += 1
                return {"accepted": accepted, "duplicates": duplicates, "schema_version": 2}
        except IntegrityError as exc:
            if _integrity_code(exc) not in {
                1062,
                sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY,
                sqlite3.SQLITE_CONSTRAINT_UNIQUE,
            }:
                raise
            if attempt:
                raise ExperienceConflict("Event identity conflict") from None
    raise ExperienceConflict("Event identity conflict")


async def record_server_event(
    *,
    context: dict,
    event_type: str,
    stage: str,
    status: str,
    operation_id: str | None = None,
    resource_ref: str | None = None,
    reason: str | None = None,
    occurred_at: datetime | None = None,
    http_status: int | None = None,
) -> None:
    if not enabled():
        return
    safe = _context(context)
    if http_status is not None and (
        type(http_status) is not int
        or not 100 <= http_status <= 599
        or event_type != "request.completed"
        or stage != "request"
    ):
        raise ValueError("Actual request completion HTTP status required")
    if occurred_at is not None and (
        not isinstance(occurred_at, datetime) or occurred_at.tzinfo is None or occurred_at.utcoffset() is None
    ):
        raise ValueError("Aware source timestamp required")
    if (
        event_type not in SERVER_TYPES
        or stage not in STAGES
        or status not in STATUSES
        or (reason is not None and reason not in REASONS)
    ):
        raise ValueError("Unknown source-owned diagnostic vocabulary")
    if operation_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", operation_id):
        raise ValueError("Invalid operation reference")
    if resource_ref is not None and not (re.fullmatch(r"[a-f0-9]{32}", resource_ref) or _is_uuid(resource_ref)):
        raise ValueError("Invalid resource reference")
    actor = safe.pop("actor")
    source = safe.pop("source")
    data = {
        **safe,
        "schema_version": 2,
        "redaction_revision": 1,
        "event_id": str(uuid4()),
        "event_type": event_type,
        "backend_build": BACKEND_BUILD,
        "stage": stage,
        "status": status,
        "operation_id": operation_id,
        "resource_ref": resource_ref,
        "occurred_at": occurred_at.astimezone(UTC).isoformat() if occurred_at is not None else None,
        "payload": {"reason": reason} if reason else {},
    }
    data["http_status"] = http_status
    async with _factory()() as session, session.begin():
        session.add(_record(data, actor, source, datetime.now(UTC), _digest(data)))


def _is_uuid(value) -> bool:
    try:
        uuid_string(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _operation_id(kind, operation_id):
    if (
        kind not in OPERATION_KINDS
        or not isinstance(operation_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", operation_id)
    ):
        raise ValueError("Invalid operation identity")
    return _digest([kind, operation_id])


async def bind_operation(context: dict, kind: str, operation_id: str) -> None:
    if not enabled():
        return
    identifier = _operation_id(kind, operation_id)
    safe = _context(context)
    actor = safe["actor"]
    if not all(actor.values()):
        raise ValueError("Verified operation owner required")
    try:
        async with _factory()() as session, session.begin():
            existing = await session.get(ExperienceOperationLink, identifier)
            if existing is not None:
                if existing.context != safe:
                    raise ExperienceConflict("Operation context is immutable")
                return
            session.add(
                ExperienceOperationLink(
                    id=identifier,
                    kind=kind,
                    operation_id=operation_id,
                    owner_key=_digest(actor),
                    user_id=actor["user_id"],
                    project_id=actor["project_id"],
                    segment_id=safe["segment_id"],
                    context=safe,
                )
            )
    except IntegrityError:
        # Concurrent admission must prove the same complete immutable receipt.
        async with _factory()() as session:
            existing = await session.get(ExperienceOperationLink, identifier)
            if existing is None or existing.context != safe:
                raise ExperienceConflict("Operation context is immutable") from None


async def read_operation_context(kind: str, operation_id: str, actor: dict) -> dict | None:
    if not enabled():
        return None
    identifier = _operation_id(kind, operation_id)
    principal = _actor(actor)
    if not principal["user_id"]:
        return None
    origin = actor.get("ownership_mode") == "origin_receipt" and kind in {"email_operation", "email_delivery"}
    if not origin and not principal["project_id"]:
        return None
    async with _factory()() as session:
        link = await session.get(ExperienceOperationLink, identifier)
        if (
            link is None
            or link.owner_key != _digest({"user_id": link.user_id, "project_id": link.project_id})
            or link.user_id != principal["user_id"]
            or (not origin and link.project_id != principal["project_id"])
        ):
            return None
        safe = _context(link.context)
        if safe["actor"] != {"user_id": link.user_id, "project_id": link.project_id}:
            return None
        safe["source"] = "worker"
        return safe


def _scope_predicate(project_ids, include_anonymous):
    if project_ids is not None:
        return ExperienceRecord.project_id.in_(sorted(project_ids)) & (ExperienceRecord.user_id != "")
    return True if include_anonymous else ExperienceRecord.user_id != ""


def _safe_data(row: ExperienceRecord) -> dict:
    data = row.data
    principal = _actor({"user_id": row.user_id, "project_id": row.project_id})
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 2
        or data.get("redaction_revision") != 1
        or row.source not in {"browser", "api", "worker"}
    ):
        raise ValueError("Unsupported stored diagnostic schema")
    if (
        row.owner_key != _digest(principal)
        or data.get("segment_id") != row.segment_id
        or data.get("event_id") != row.event_id
        or data.get("action_id") != row.action_id
    ):
        raise ValueError("Inconsistent stored diagnostic identity")
    if row.source == "browser":
        # Revalidate stored data too: mixed/older schemas cannot smuggle fields.
        fields = ExperienceEvent.model_fields
        event = ExperienceEvent.model_validate(
            {key: value for key, value in data.items() if key in fields}, context={"retained": True}
        )
        safe = event.model_dump(exclude_none=False)
        safe["request_id"] = (
            data.get("request_id")
            if isinstance(data.get("request_id"), str) and re.fullmatch(r"req-[a-f0-9]{32}", data["request_id"])
            else None
        )
    else:
        context = _context(
            {**data, "actor": {"user_id": row.user_id, "project_id": row.project_id}, "source": row.source}
        )
        if (
            data.get("event_type") not in SERVER_TYPES
            or data.get("stage") not in STAGES
            or data.get("status") not in STATUSES
        ):
            raise ValueError("Unknown persisted server vocabulary")
        reason = data.get("payload", {}).get("reason")
        safe = {key: value for key, value in context.items() if key not in {"actor", "source"}}
        safe.update(
            event_id=uuid_string(data["event_id"]),
            event_type=data["event_type"],
            stage=data["stage"],
            status=data["status"],
            operation_id=data.get("operation_id")
            if isinstance(data.get("operation_id"), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", data["operation_id"])
            else None,
            resource_ref=data.get("resource_ref")
            if _is_uuid(data.get("resource_ref"))
            or isinstance(data.get("resource_ref"), str)
            and re.fullmatch(r"[a-f0-9]{32}", data["resource_ref"])
            else None,
            payload={"reason": reason} if reason in REASONS else {},
            schema_version=2,
            redaction_revision=1,
        )
        http_status = data.get("http_status")
        if http_status is not None and (
            type(http_status) is not int
            or not 100 <= http_status <= 599
            or data["event_type"] != "request.completed"
            or data["stage"] != "request"
        ):
            raise ValueError("Invalid persisted request completion status")
        safe["http_status"] = http_status
        occurred_at = data.get("occurred_at")
        if occurred_at is not None:
            if not isinstance(occurred_at, str):
                raise ValueError("Invalid persisted source timestamp")
            parsed_time = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
            if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
                raise ValueError("Aware persisted source timestamp required")
            safe["occurred_at"] = parsed_time.astimezone(UTC).isoformat()
    safe.update(
        id=row.id,
        source=row.source,
        actor=_actor({"user_id": row.user_id, "project_id": row.project_id}),
        received_at=row.received_at.replace(tzinfo=UTC).isoformat(),
        backend_build=revision_string(data.get("backend_build", "unknown")),
    )
    for key in (
        "occurred_at",
        "client_seq",
        "client_monotonic_ms",
        "stage",
        "status",
        "operation_id",
        "resource_ref",
        "http_status",
    ):
        safe.setdefault(key, None)
    return safe


def _disclosure_actor(
    actor: dict, project_ids: frozenset[str] | None, domain_id: str | None, include_anonymous: bool
) -> dict:
    if actor.get("_live_system_admin") is not True:
        raise PermissionError("Fresh administrator authority required")
    if include_anonymous and (
        not get_settings().experience_anonymous_read_enabled or project_ids is not None or domain_id is not None
    ):
        raise PermissionError("Anonymous diagnostics are not authorized")
    return _actor(actor)


async def _audit_disclosure(
    session,
    principal: dict,
    *,
    count: int,
    include_anonymous: bool,
    scoped: bool,
    export: bool = False,
    segment_id: str | None = None,
    days: int | None = None,
) -> None:
    extra = {"schema_version": 2, "count": count, "include_anonymous": include_anonymous, "scoped": scoped}
    if segment_id is not None:
        extra["segment_id"] = segment_id
    if days is not None:
        extra.update(lookup="recent_segments", days=days)
    # Successful commit, not merely flush, is the disclosure boundary.
    session.add(
        ActivityLog(
            project_id=principal["project_id"],
            user_id=principal["user_id"],
            username="",
            resource_type="experience",
            resource_id=None,
            action="export" if export else "view",
            status="observed",
            source="afterglow",
            service="afterglow",
            extra=extra,
        )
    )
    await session.flush()


async def query(
    *,
    segment_id: str,
    actor: dict,
    project_ids: frozenset[str] | None,
    domain_id: str | None = None,
    action_id: str | None = None,
    before_id: int | None = None,
    limit: int = 200,
    include_anonymous: bool = False,
    export: bool = False,
) -> dict:
    if not enabled():
        raise ExperienceUnavailable("Experience is disabled")
    uuid_string(segment_id)
    if action_id is not None:
        uuid_string(action_id)
    if not 1 <= limit <= (2000 if export else 200):
        raise ValueError("Invalid diagnostic window")
    principal = _disclosure_actor(actor, project_ids, domain_id, include_anonymous)
    statement = select(ExperienceRecord).where(
        ExperienceRecord.segment_id == segment_id, _scope_predicate(project_ids, include_anonymous)
    )
    if action_id:
        statement = statement.where(ExperienceRecord.action_id == action_id)
    if before_id:
        statement = statement.where(ExperienceRecord.id < before_id)
    async with _factory()() as session:
        async with session.begin():
            rows = list((await session.scalars(statement.order_by(ExperienceRecord.id.desc()).limit(limit + 1))).all())
            has_more = len(rows) > limit
            rows = rows[:limit]
            reasons = {"clock_order_unknown"}
            events = []
            catalogs = {}
            # Reference resolution is bounded to authorized records in this window;
            # missing or off-window targets are honestly redacted, never fetched globally.
            sanitized = []
            for row in rows:
                try:
                    sanitized.append((row, _safe_data(row)))
                except (ValueError, TypeError, KeyError, AttributeError):
                    reasons.add("missing_context")
            catalog_ids = {row.catalog_id for row, _ in sanitized if row.catalog_id}
            retained_catalogs = (
                {
                    catalog.id: catalog
                    for catalog in (
                        await session.scalars(select(ExperienceCatalog).where(ExperienceCatalog.id.in_(catalog_ids)))
                    ).all()
                }
                if catalog_ids
                else {}
            )
            allowed = {(r.owner_key, r.segment_id, r.event_id) for r, _ in sanitized}
            span_allowed = {(r.owner_key, r.segment_id, data.get("span_id")) for r, data in sanitized}
            request_allowed = {
                (r.owner_key, r.segment_id, data.get("request_id")) for r, data in sanitized if r.source != "browser"
            }
            link_statement = select(ExperienceOperationLink).where(ExperienceOperationLink.segment_id == segment_id)
            if project_ids is not None:
                link_statement = link_statement.where(ExperienceOperationLink.project_id.in_(sorted(project_ids)))
            links = list((await session.scalars(link_statement.limit(2001))).all())
            operation_allowed = set()
            for link in links:
                try:
                    linked = _context(link.context)
                    valid = (
                        link.id == _operation_id(link.kind, link.operation_id)
                        and link.owner_key == _digest(linked["actor"])
                        and linked["segment_id"] == segment_id
                        and linked["actor"] == {"user_id": link.user_id, "project_id": link.project_id}
                    )
                except (ValueError, TypeError, KeyError, AttributeError):
                    valid = False
                if valid and link.user_id and (project_ids is None or link.project_id in project_ids):
                    operation_allowed.add((link.user_id, link.project_id, link.operation_id))
            for row, safe in sanitized:
                cause = safe.get("caused_by_event_id")
                if cause and (row.owner_key, row.segment_id, cause) not in allowed:
                    safe["caused_by_event_id"] = None
                    reasons.add("redacted_reference")
                for field in ("parent_span_id",):
                    if safe.get(field) and (row.owner_key, row.segment_id, safe[field]) not in span_allowed:
                        safe[field] = None
                        reasons.add("redacted_reference")
                payload = safe["payload"]
                for field, registry in (("physical_span_id", span_allowed), ("request_id", request_allowed)):
                    if payload.get(field) and (row.owner_key, row.segment_id, payload[field]) not in registry:
                        payload[field] = None
                        reasons.add("redacted_reference")
                if (
                    safe.get("operation_id")
                    and (row.user_id, row.project_id, safe["operation_id"]) not in operation_allowed
                ):
                    safe["operation_id"] = None
                    safe["resource_ref"] = None
                    reasons.add("redacted_reference")
                catalog = retained_catalogs.get(row.catalog_id)
                catalog_matches = (
                    catalog is not None
                    and catalog.revision == safe["catalog_revision"]
                    and catalog.key == payload.get("key")
                    and catalog.locale == payload.get("locale")
                )
                if catalog_matches:
                    catalogs[catalog.id] = {
                        "revision": catalog.revision,
                        "key": catalog.key,
                        "locale": catalog.locale,
                        "template": catalog.template,
                    }
                if safe["event_type"] == "message.presented" and not catalog_matches:
                    payload["restoration"] = "unavailable"
                    reasons.add("catalog_unavailable")
                events.append(safe)
            if has_more:
                reasons.add("bounded_window")
            # Audit is durable in the very transaction whose successful commit
            # permits disclosure. Unlike activity.record(), failures are not swallowed.
            await _audit_disclosure(
                session,
                principal,
                count=len(events),
                include_anonymous=include_anonymous,
                scoped=project_ids is not None,
                export=export,
                segment_id=segment_id,
            )
        return {
            "schema_version": 2,
            "events": events,
            "has_more": has_more,
            "coverage": {
                "partial": True,
                "reasons": sorted(reasons),
                "remote_spans": "unavailable",
                "screen_tail": "unknown",
            },
            "catalogs": list(catalogs.values()),
        }


async def query_segments(
    *,
    actor: dict,
    project_ids: frozenset[str] | None,
    domain_id: str | None = None,
    user_id: str | None = None,
    days: int = 1,
    limit: int = 20,
    include_anonymous: bool = False,
) -> dict:
    """Discover bounded owner/segment summaries, never event bodies or joins.

    Counts describe stored rows inside this receive-time window, not actions,
    humans, complete sessions or causal order. Reusing a segment UUID under a
    different owner cannot merge their counts or confer any read authority.
    """
    if not enabled():
        raise ExperienceUnavailable("Experience is disabled")
    if type(days) is not int or days not in {1, 7, 30} or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Invalid diagnostic window")
    if user_id is not None and (not isinstance(user_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", user_id)):
        raise ValueError("Invalid diagnostic user filter")
    principal = _disclosure_actor(actor, project_ids, domain_id, include_anonymous)
    now = datetime.now(UTC)
    last_received = func.max(ExperienceRecord.received_at).label("last_received_at")
    # Select only finite metadata, not the free JSON event body. A mixed schema
    # or unknown source makes the entire candidate summary unavailable.
    metadata_valid = (
        ExperienceRecord.source.in_(("browser", "api", "worker"))
        & (ExperienceRecord.data["schema_version"].as_integer() == 2)
        & (ExperienceRecord.data["redaction_revision"].as_integer() == 1)
        & (ExperienceRecord.data["segment_id"].as_string() == ExperienceRecord.segment_id)
        & (ExperienceRecord.data["event_id"].as_string() == ExperienceRecord.event_id)
    )
    statement = select(
        ExperienceRecord.owner_key,
        ExperienceRecord.segment_id,
        ExperienceRecord.user_id,
        ExperienceRecord.project_id,
        last_received,
        func.count().label("event_count"),
        func.sum(case((metadata_valid, 0), else_=1)).label("invalid_metadata"),
    ).where(
        ExperienceRecord.received_at >= now - timedelta(days=days),
        ExperienceRecord.received_at <= now,
        _scope_predicate(project_ids, include_anonymous),
    )
    if user_id is not None:
        statement = statement.where(ExperienceRecord.user_id == user_id)
    statement = (
        statement.group_by(
            ExperienceRecord.owner_key,
            ExperienceRecord.segment_id,
            ExperienceRecord.user_id,
            ExperienceRecord.project_id,
        )
        .order_by(
            last_received.desc(),
            ExperienceRecord.owner_key,
            ExperienceRecord.segment_id,
            ExperienceRecord.user_id,
            ExperienceRecord.project_id,
        )
        .limit(limit + 1)
    )
    async with _factory()() as session:
        async with session.begin():
            revision_fields = ("schema_version", "redaction_revision")
            if session.get_bind().dialect.name == "sqlite":
                # Inspect the original document: SQLite JSON extraction turns
                # true into SQL integer 1 before JSON_QUOTE can retain its type.
                revision_types = [
                    func.json_type(ExperienceRecord.data, f"$.{field}") == "integer" for field in revision_fields
                ]
            else:
                revision_types = [
                    func.lower(func.json_type(ExperienceRecord.data[field])) == "integer" for field in revision_fields
                ]
            statement = statement.add_columns(
                func.sum(case((revision_types[0] & revision_types[1], 0), else_=1)).label("invalid_revision_types")
            )
            candidates = list((await session.execute(statement)).mappings())
            has_more = len(candidates) > limit
            reasons = {"clock_order_unknown"}
            if has_more:
                reasons.add("bounded_window")
            segments = []
            for row in candidates[:limit]:
                try:
                    owner = _actor({"user_id": row["user_id"], "project_id": row["project_id"]})
                    segment_id = uuid_string(row["segment_id"])
                    received = row["last_received_at"]
                    count = row["event_count"]
                    if (
                        row["owner_key"] != _digest(owner)
                        or row["invalid_metadata"] != 0
                        or row["invalid_revision_types"] != 0
                        or not isinstance(received, datetime)
                        or type(count) is not int
                        or count < 1
                    ):
                        raise ValueError("Inconsistent stored summary")
                    received = received.replace(tzinfo=UTC) if received.tzinfo is None else received.astimezone(UTC)
                    segments.append(
                        {
                            "segment_id": segment_id,
                            **owner,
                            "last_received_at": received.isoformat(),
                            "event_count": count,
                        }
                    )
                except (ValueError, TypeError, KeyError, AttributeError):
                    reasons.add("missing_context")
            await _audit_disclosure(
                session,
                principal,
                count=len(segments),
                include_anonymous=include_anonymous,
                scoped=project_ids is not None,
                days=days,
            )
        return {
            "schema_version": 2,
            "segments": segments,
            "has_more": has_more,
            "coverage": {"partial": True, "reasons": sorted(reasons)},
        }


async def retain(*, apply: bool = False, batch_size: int = 500, now: datetime | None = None) -> dict:
    """One bounded maintenance transaction. Never scheduled or activated implicitly."""
    if not 1 <= batch_size <= 2000:
        raise ValueError("Retention batch must be between 1 and 2000")
    now = now or datetime.now(UTC)
    settings = get_settings()
    detail_cutoff = now - timedelta(days=settings.experience_detail_retention_days)
    aggregate_cutoff = (now - timedelta(days=settings.experience_aggregate_retention_days)).date()
    unheld = ~exists(
        select(ExperienceHold.segment_id).where(
            ExperienceHold.segment_id == ExperienceRecord.segment_id,
            ExperienceHold.owner_key == ExperienceRecord.owner_key,
        )
    )
    async with _factory()() as session:
        async with session.begin():
            if apply:
                await lock_maintenance(session)
            statement = (
                select(ExperienceRecord)
                .where(ExperienceRecord.received_at < detail_cutoff, unheld)
                .order_by(ExperienceRecord.id)
                .limit(batch_size)
            )
            if apply:
                statement = statement.with_for_update()
            rows = list((await session.scalars(statement)).all())
            aggregate_ids = list(
                (
                    await session.scalars(
                        select(ExperienceAggregate.id)
                        .where(ExperienceAggregate.day < aggregate_cutoff)
                        .limit(batch_size)
                    )
                ).all()
            )
            result = {
                "apply": apply,
                "detail_candidates": len(rows),
                "aggregate_candidates": len(aggregate_ids),
                "detail_deleted": 0,
                "aggregate_deleted": 0,
                "catalog_deleted": 0,
                "catalog_gc_deferred": 0,
            }
            if not apply:
                return result
            groups = Counter()
            for row in rows:
                try:
                    safe = _safe_data(row)
                except (ValueError, TypeError, KeyError, AttributeError):
                    continue
                groups[(row.received_at.date(), row.project_id, row.source, safe["feature"], safe["event_type"])] += 1
            for (day, project_id, source, feature, event_type), count in groups.items():
                if day < aggregate_cutoff:
                    continue
                identifier = _digest([day.isoformat(), project_id, source, feature, event_type])
                aggregate = await session.get(ExperienceAggregate, identifier, with_for_update=True)
                if aggregate is None:
                    session.add(
                        ExperienceAggregate(
                            id=identifier,
                            day=day,
                            project_id=project_id,
                            source=source,
                            feature=feature,
                            event_type=event_type,
                            count=count,
                        )
                    )
                else:
                    aggregate.count += count
            if rows:
                await session.execute(delete(ExperienceRecord).where(ExperienceRecord.id.in_([r.id for r in rows])))
                result["detail_deleted"] = len(rows)
            if aggregate_ids:
                await session.execute(delete(ExperienceAggregate).where(ExperienceAggregate.id.in_(aggregate_ids)))
                result["aggregate_deleted"] = len(aggregate_ids)
            orphan_catalogs = list(
                (
                    await session.scalars(
                        select(ExperienceCatalog.id)
                        .where(
                            ~exists(
                                select(ExperienceRecord.id).where(ExperienceRecord.catalog_id == ExperienceCatalog.id)
                            )
                        )
                        .limit(batch_size)
                    )
                ).all()
            )
            if orphan_catalogs:
                try:
                    async with session.begin_nested():
                        deleted = await session.execute(
                            delete(ExperienceCatalog).where(
                                ExperienceCatalog.id.in_(orphan_catalogs),
                                ~exists(
                                    select(ExperienceRecord.id).where(
                                        ExperienceRecord.catalog_id == ExperienceCatalog.id
                                    )
                                ),
                            )
                        )
                        result["catalog_deleted"] = deleted.rowcount
                except IntegrityError as exc:
                    if _integrity_code(exc) not in {1451, sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY}:
                        raise
                    # A concurrent attachment won: retain the exact catalog,
                    # and leave its GC to a later explicit maintenance batch.
                    result["catalog_gc_deferred"] = len(orphan_catalogs)
            unheld_link = ~exists(
                select(ExperienceHold.segment_id).where(
                    ExperienceHold.segment_id == ExperienceOperationLink.segment_id,
                    ExperienceHold.owner_key == ExperienceOperationLink.owner_key,
                )
            )
            old_links = list(
                (
                    await session.scalars(
                        select(ExperienceOperationLink.id)
                        .where(ExperienceOperationLink.created_at < detail_cutoff, unheld_link)
                        .limit(batch_size)
                    )
                ).all()
            )
            if old_links:
                await session.execute(delete(ExperienceOperationLink).where(ExperienceOperationLink.id.in_(old_links)))
        return result
