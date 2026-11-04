"""Explicit, bounded diagnostic context; never an authority or business retry path."""

from __future__ import annotations

import asyncio
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from app.config import get_settings
from app.services.interaction_policy import canonical_page, interaction_id

_TIMEOUT = 0.250
_REQUEST_ID = re.compile(r"req-[a-f0-9]{32}\Z")
_OWNER_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_STAGES = frozenset(
    {
        "request",
        "native",
        "blocking",
        "blocking.drain",
        "native.drain",
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
_STATUSES = frozenset(
    {"observed", "accepted", "running", "succeeded", "failed", "cancel_requested", "cancelled", "outcome_unknown"}
)
_REASONS = frozenset(
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


@dataclass(frozen=True)
class SafeExperienceContext:
    segment_id: str
    page_view_id: str
    route: str
    actor: dict = field(default_factory=dict)
    source: str = "api"
    action_id: str | None = None
    caused_by_event_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    feature: str = "unknown"
    action: str = "unknown"
    component: str = "unknown"
    frontend_build: str = "unknown"
    catalog_revision: str = "unknown"
    request_id: str | None = None


_context: ContextVar[dict | None] = ContextVar("experience_context", default=None)
_request: ContextVar[Any | None] = ContextVar("experience_request", default=None)


def experience_enabled() -> bool:
    return getattr(get_settings(), "experience_enabled", False) is True


def trusted_actor(value: dict | None) -> dict:
    if not isinstance(value, dict):
        return {}
    return {
        key: value[key]
        for key in ("user_id", "project_id", "domain_id")
        if isinstance(value.get(key), str) and _OWNER_ID.fullmatch(value[key])
    }


def capture_request_context(request, request_id: str, verified_actor: dict | None) -> dict | None:
    """Accept only canonical correlation headers, never client identity or URLs."""
    if not experience_enabled():
        return None
    headers = request.headers
    seen = set()
    for key, _ in request.scope.get("headers", []):
        name = key.lower()
        if name.startswith(b"x-afterglow-experience-") or name == b"x-afterglow-page":
            if name in seen:
                return None
            seen.add(name)
    ids = {}
    for field_name, suffix in (
        ("segment_id", "Segment"),
        ("page_view_id", "Page-View"),
        ("action_id", "Action"),
        ("caused_by_event_id", "Event"),
        ("trace_id", "Trace"),
        ("span_id", "Span"),
    ):
        raw = headers.get("X-Afterglow-Experience-" + suffix)
        if raw is not None:
            value = interaction_id(raw)
            if value is None or value != raw:
                return None
            ids[field_name] = value
    if not ids.get("segment_id") or not ids.get("page_view_id"):
        return None
    raw_page = headers.get("X-Afterglow-Page", "")
    try:
        page = canonical_page(raw_page)
    except ValueError:
        return None
    if page != raw_page:
        return None
    attempt = headers.get("X-Afterglow-Experience-Attempt")
    if attempt is not None and (not re.fullmatch(r"[1-9][0-9]{0,2}", attempt) or int(attempt) > 100):
        return None
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        return None
    return asdict(SafeExperienceContext(**ids, route=page, actor=trusted_actor(verified_actor), request_id=request_id))


def capture_experience_context(*, feature=None, action=None, component=None) -> dict | None:
    value = _context.get()
    if value is None or not experience_enabled():
        return None
    captured = {**value, "actor": dict(value.get("actor", {}))}
    request = _request.get()
    if request is not None:
        from app.services.activity import _audit_ctx

        # Both references are populated by existing verified audit/dependency code.
        audit = _audit_ctx.get() or getattr(request.state, "experience_audit_context", None) or {}
        actor = (
            getattr(request.state, "token_info", None)
            or getattr(request.state, "experience_actor", None)
            or audit.get("actor")
        )
        captured["actor"] = trusted_actor(actor)
        actual_id = audit.get("request_id")
        if isinstance(actual_id, str) and _REQUEST_ID.fullmatch(actual_id):
            captured["request_id"] = actual_id
    for key, supplied in (("feature", feature), ("action", action), ("component", component)):
        if supplied is not None:
            captured[key] = supplied
    return captured


def fork_experience_call(context: dict | None) -> dict | None:
    """Give one owned call a stable child span without copying business values."""
    if context is None:
        return None
    return {**context, "parent_span_id": context.get("span_id"), "span_id": str(uuid4())}


@contextmanager
def experience_scope(context: dict | None, *, request=None):
    token = _context.set({**context, "actor": dict(context.get("actor", {}))} if context else None)
    request_token = _request.set(request)
    try:
        yield
    finally:
        _request.reset(request_token)
        _context.reset(token)


def unlinked_worker_context(*, feature="unknown", action="unknown", component="unknown") -> dict | None:
    if not experience_enabled():
        return None
    return asdict(
        SafeExperienceContext(
            segment_id=str(uuid4()),
            page_view_id=str(uuid4()),
            route="/",
            source="worker",
            feature=feature,
            action=action,
            component=component,
        )
    )


async def _best_effort(call):
    """Bound SQL diagnostics; cancellation of the business caller still propagates."""
    try:
        async with asyncio.timeout(_TIMEOUT):
            return await call()
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            raise
        return None
    except Exception:
        return None


async def emit_experience(
    context,
    event_type,
    *,
    stage,
    status,
    operation_id=None,
    resource_ref=None,
    reason=None,
    occurred_at=None,
    http_status=None,
) -> None:
    if (
        not experience_enabled()
        or context is None
        or stage not in _STAGES
        or status not in _STATUSES
        or reason is not None
        and reason not in _REASONS
    ):
        return
    from app.services.experience import record_server_event

    await _best_effort(
        lambda: record_server_event(
            context=context,
            event_type=event_type,
            stage=stage,
            status=status,
            operation_id=operation_id,
            resource_ref=resource_ref,
            reason=reason,
            occurred_at=occurred_at,
            http_status=http_status,
        )
    )


async def emit_experience_cleanup(*args, **kwargs) -> bool:
    """Drain bounded diagnostics without letting cancellation interrupt cleanup.

    Return newly observed caller cancellation so a normal cleanup can propagate
    it after releasing its resources. Diagnostic child cancellation is not a
    business cancellation.
    """
    from anyio import CancelScope

    task = asyncio.create_task(_best_effort(lambda: emit_experience(*args, **kwargs)))
    interrupted = False
    with CancelScope(shield=True):
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                current = asyncio.current_task()
                interrupted = interrupted or (current is not None and current.cancelling() > 0)
            except Exception:
                break
    if not task.cancelled():
        task.exception()
    return interrupted


async def bind_experience_operation(context, kind, operation_id) -> None:
    if not experience_enabled() or context is None:
        return
    from app.services.experience import bind_operation

    await _best_effort(lambda: bind_operation(context, kind, str(operation_id)))


async def restore_experience_operation(kind, operation_id, actor) -> dict | None:
    if not experience_enabled() or not isinstance(actor, dict):
        return None
    owner = trusted_actor(actor)
    origin_receipt = kind in {"email_operation", "email_delivery"} and actor.get("ownership_mode") == "origin_receipt"
    if not owner.get("user_id") or (not owner.get("project_id") and not origin_receipt):
        return None
    from app.services.experience import read_operation_context

    lookup_actor = {**owner, "ownership_mode": "origin_receipt"} if origin_receipt else owner
    restored = await _best_effort(lambda: read_operation_context(kind, str(operation_id), lookup_actor))
    if restored is None:
        return None
    return {**restored, "source": "worker"}


def experience_owner_receipt() -> dict | None:
    context = capture_experience_context()
    owner = trusted_actor(context.get("actor")) if context else {}
    return owner if owner.get("user_id") and owner.get("project_id") else None


async def build_experience_context(kind: str, identity: str) -> dict | None:
    if not experience_enabled():
        return None

    async def read():
        from app.database import get_session_factory
        from app.models.db import LayerBuild, LayerImportJob, LibraryBuild

        model, operation_kind = {
            "library": (LibraryBuild, "library_build"),
            "layer": (LayerBuild, "layer_build"),
            "import": (LayerImportJob, "dockerfile_import"),
        }[kind]
        async with get_session_factory()() as session:
            row = await session.get(model, int(identity))
            owner = (row.resource_snapshot or {}).get("experience_owner") if row else None
        return await restore_experience_operation(operation_kind, identity, owner or {})

    return await _best_effort(read)


async def build_experience_terminal(kind: str, identity: str) -> str:
    if not experience_enabled():
        return "outcome_unknown"

    async def read():
        from app.database import get_session_factory
        from app.models.db import LayerBuild, LayerImportJob, LibraryBuild

        model = {"library": LibraryBuild, "layer": LayerBuild, "import": LayerImportJob}[kind]
        async with get_session_factory()() as session:
            row = await session.get(model, int(identity))
            if row is not None and row.status == "cancelled" and row.completed_at is not None:
                return "cancelled"
            return (
                {"complete": "succeeded", "error": "failed", "timeout": "outcome_unknown"}.get(
                    row.status, "outcome_unknown"
                )
                if row
                else "outcome_unknown"
            )

    return await _best_effort(read) or "outcome_unknown"
