"""사용자 활동 로그 기록 / 조회 서비스. Best-effort: 기록 실패는 logger.warning 만."""

from __future__ import annotations

import logging
import re
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from itertools import islice
from typing import Literal

from sqlalchemy import and_, case, desc, func, or_, select

from app.database import get_session_factory, is_db_available
from app.models.activity import ActivityLog
from app.utils.log import is_sensitive, mask_str

logger = logging.getLogger(__name__)

ActionStatus = Literal["started", "success", "failed"]

_SECRET_ASSIGNMENT = re.compile(
    r"\b(password|passwd|secret|token|api[_-]?key|authorization)\s*([=:])\s*([^\s&;,]+)", re.I
)


def _mask_text(text: str) -> str:
    masked = mask_str(text[:65535])
    return _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[redacted]", masked)


def service_for_resource(resource_type: str) -> str:
    """Map API resource types to their originating cloud service."""
    if resource_type in {"instance", "keypair", "flavor"}:
        return "nova"
    if resource_type == "image":
        return "glance"
    if resource_type.startswith("volume") or resource_type in {"snapshot", "backup"}:
        return "cinder"
    if resource_type in {"network", "subnet", "router", "security_group", "floating_ip", "port"}:
        return "neutron"
    if resource_type == "file_storage" or resource_type.startswith("share"):
        return "manila"
    if resource_type == "load_balancer" or resource_type.startswith("lb_"):
        return "octavia"
    if resource_type in {"user", "project", "auth"}:
        return "keystone"
    if resource_type in {"palimpsest_package", "palimpsest_package_key"}:
        return "palimpsest"
    return "afterglow"


# 자동 로깅 미들웨어와의 중복 억제 채널.
# BaseHTTPMiddleware 는 엔드포인트를 자식 태스크(컨텍스트 복사본)에서 실행하므로
# ContextVar 바인딩 변경은 미들웨어로 전달되지 않는다. 하지만 값(dict 참조)은
# 복사 시 참조로 공유되므로, dict 내용 변경은 양쪽에서 보인다.
# 미들웨어가 dict 를 set 하고 핸들러가 record() 를 호출하면 dict["logged"]=True 가
# 미들웨어 쪽에도 반영되어 자동 로깅을 억제한다.
_audit_ctx: ContextVar[dict | None] = ContextVar("activity_audit", default=None)

_last_db_warn_ts: float = float("-inf")  # 첫 번째 경고는 항상 즉시 출력


def _warn_db_unavailable(msg: str) -> None:
    global _last_db_warn_ts
    now = time.monotonic()
    if now - _last_db_warn_ts >= 60.0:
        logger.warning(msg)
        _last_db_warn_ts = now


async def record(
    *,
    project_id: str,
    user_id: str,
    username: str,
    resource_type: str,
    action: str,
    status: ActionStatus,
    resource_id: str | None = None,
    resource_name: str | None = None,
    error_message: str | None = None,
    extra: dict | None = None,
    request_id: str | None = None,
    service: str | None = None,
    source: str | None = None,
    page: str | None = None,
    http_status: int | None = None,
) -> None:
    """활동 1건 기록. 실패 시 silently swallow + warning."""
    # 자동 로깅 미들웨어에 "명시적 로그가 발생했음"을 신호 (중복 방지).
    # rec() 경유 호출 + k3s 서비스의 직접 record() 2곳 모두 여기서 신호를 세팅한다.
    _h = _audit_ctx.get()
    if _h is not None:
        _h.setdefault("statuses", set()).add(status)
        _h["recorded_status"] = status
        _h["logged"] = True
    if not is_db_available():
        _warn_db_unavailable("ActivityLog skipped: db unavailable (engine=None or circuit breaker open)")
        return
    factory = get_session_factory()
    if factory is None:
        _warn_db_unavailable("ActivityLog skipped: session_factory is None")
        return
    try:
        context = _audit_ctx.get() or {}
        async with factory() as session:
            row = ActivityLog(
                project_id=project_id,
                user_id=user_id,
                username=username,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name[:255] if resource_name else None,
                action=action,
                status=status,
                error_message=_mask_text(error_message) if error_message else None,
                extra=_mask_extra(extra) if extra is not None else None,
                request_id=(request_id if request_id is not None else context.get("request_id")),
                service=(
                    service if service is not None else context.get("service") or service_for_resource(resource_type)
                ),
                source=(source if source is not None else context.get("source") or "afterglow"),
                page=(page if page is not None else context.get("page")),
                http_status=http_status,
            )
            session.add(row)
            await session.commit()
    except Exception:
        logger.warning(
            "activity_log 기록 실패 (action=%s resource_type=%s)",
            action,
            resource_type,
            exc_info=True,
        )


def _mask_extra(extra: dict) -> dict:
    """Bound and mask nested JSON, including deeply nested secret keys."""

    def clean(value, depth: int = 0):
        if depth >= 6:
            return "[redacted]"
        if isinstance(value, str):
            return _mask_text(value)
        if isinstance(value, dict):
            return {
                str(k)[:255]: "[redacted]" if is_sensitive(str(k)) else clean(v, depth + 1)
                for k, v in islice(value.items(), 100)
            }
        if isinstance(value, list):
            return [clean(v, depth + 1) for v in value[:100]]
        return value

    return clean(extra)


async def list_for_project(
    project_id: str,
    *,
    limit: int = 50,
    before_id: int | None = None,
    resource_type: str | None = None,
    action: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    """admin 화면용. project 안의 모든 사용자 활동을 시간 역순으로."""
    if not is_db_available():
        return []
    factory = get_session_factory()
    if factory is None:
        return []
    async with factory() as session:
        conds = [ActivityLog.project_id == project_id]
        if before_id is not None:
            conds.append(ActivityLog.id < before_id)
        if resource_type:
            conds.append(ActivityLog.resource_type == resource_type)
        if action:
            conds.append(ActivityLog.action == action)
        if user_id:
            conds.append(ActivityLog.user_id == user_id)
        stmt = select(ActivityLog).where(and_(*conds)).order_by(desc(ActivityLog.id)).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_dict(r) for r in rows]


async def list_for_user(
    user_id: str,
    *,
    limit: int = 50,
    before_id: int | None = None,
    resource_type: str | None = None,
    action: str | None = None,
) -> list[dict]:
    """account 페이지용. 본인 활동만 (cross-project)."""
    if not is_db_available():
        return []
    factory = get_session_factory()
    if factory is None:
        return []
    async with factory() as session:
        conds = [ActivityLog.user_id == user_id]
        if before_id is not None:
            conds.append(ActivityLog.id < before_id)
        if resource_type:
            conds.append(ActivityLog.resource_type == resource_type)
        if action:
            conds.append(ActivityLog.action == action)
        stmt = select(ActivityLog).where(and_(*conds)).order_by(desc(ActivityLog.id)).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_dict(r) for r in rows]


async def get_user_activity_bounds(user_ids: list[str]) -> dict[str, dict]:
    """사용자별 최초·최근 활동 시각을 1쿼리로 배치 조회.

    Returns:
        {user_id: {"first_seen": isoformat | None, "last_seen": isoformat | None}}
        활동 기록 없는 user_id는 결과에 포함되지 않는다.
    """
    if not user_ids or not is_db_available():
        return {}
    factory = get_session_factory()
    if factory is None:
        return {}
    from sqlalchemy import func

    async with factory() as session:
        stmt = (
            select(
                ActivityLog.user_id,
                func.min(ActivityLog.created_at).label("first_seen"),
                func.max(ActivityLog.created_at).label("last_seen"),
            )
            .where(ActivityLog.user_id.in_(user_ids))
            .group_by(ActivityLog.user_id)
        )
        rows = (await session.execute(stmt)).all()
        return {
            row.user_id: {
                "first_seen": row.first_seen.isoformat() if row.first_seen else None,
                "last_seen": row.last_seen.isoformat() if row.last_seen else None,
            }
            for row in rows
        }


async def get_resource_creation_times(resource_type: str, resource_ids: list[str]) -> dict[str, str]:
    """Project/group creation events only; first activity is not a creation date."""
    if not resource_ids or not is_db_available():
        return {}
    factory = get_session_factory()
    if factory is None:
        return {}
    actions = (
        f"{resource_type}.create",
        f"{resource_type}_create",
        f"identity.{resource_type}.created",
    )
    async with factory() as session:
        stmt = (
            select(ActivityLog.resource_id, func.min(ActivityLog.created_at).label("created_at"))
            .where(
                ActivityLog.resource_type == resource_type,
                ActivityLog.resource_id.in_(resource_ids),
                ActivityLog.action.in_(actions),
                ActivityLog.status == "success",
            )
            .group_by(ActivityLog.resource_id)
        )
        rows = (await session.execute(stmt)).all()
        return {
            row.resource_id: row.created_at.replace(tzinfo=UTC).isoformat()
            if row.created_at.tzinfo is None
            else row.created_at.astimezone(UTC).isoformat()
            for row in rows
        }


class ActivityDatabaseUnavailable(RuntimeError):
    """The admin event API cannot read the activity store."""


def _event_factory():
    if not is_db_available():
        raise ActivityDatabaseUnavailable("Activity database is unavailable")
    factory = get_session_factory()
    if factory is None:
        raise ActivityDatabaseUnavailable("Activity database is unavailable")
    return factory


def _event_conditions(
    *,
    project_id: str | None = None,
    user_id: str | None = None,
    username: str | None = None,
    resource_id: str | None = None,
    resource_type: str | None = None,
    action: str | None = None,
    status: str | None = None,
    service: str | None = None,
    source: str | None = None,
    request_id: str | None = None,
    page: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    before_id: int | None = None,
) -> list:
    conditions = []
    for column, value in (
        (ActivityLog.project_id, project_id),
        (ActivityLog.user_id, user_id),
        (ActivityLog.username, username),
        (ActivityLog.resource_id, resource_id),
        (ActivityLog.resource_type, resource_type),
        (ActivityLog.action, action),
        (ActivityLog.status, status),
        (ActivityLog.service, service),
        (ActivityLog.request_id, request_id),
        (ActivityLog.page, page),
    ):
        if value is not None:
            conditions.append(column == value)
    if source == "afterglow":
        conditions.append(or_(ActivityLog.source == "afterglow", ActivityLog.source.is_(None)))
    elif source is not None:
        conditions.append(ActivityLog.source == source)
    if from_at is not None:
        conditions.append(ActivityLog.created_at >= from_at.astimezone(UTC).replace(tzinfo=None))
    if to_at is not None:
        conditions.append(ActivityLog.created_at <= to_at.astimezone(UTC).replace(tzinfo=None))
    if before_id is not None:
        conditions.append(ActivityLog.id < before_id)
    return conditions


async def list_events(*, limit: int = 50, **filters) -> list[dict]:
    """Global audit events in descending insertion order, with an exclusive ID cursor."""
    factory = _event_factory()
    conditions = _event_conditions(**filters)
    async with factory() as session:
        stmt = select(ActivityLog).where(*conditions).order_by(desc(ActivityLog.id)).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_dict(row) for row in rows]


async def get_event(event_id: int) -> dict | None:
    """Fetch one event without project scoping (admin only at the API boundary)."""
    factory = _event_factory()
    async with factory() as session:
        row = await session.get(ActivityLog, event_id)
        return _row_to_dict(row) if row is not None else None


async def event_stats(**filters) -> dict:
    """Count all matching events using SQL aggregates, not the current page."""
    factory = _event_factory()
    conditions = _event_conditions(**filters)
    async with factory() as session:
        counts = (
            await session.execute(
                select(
                    func.count(ActivityLog.id),
                    func.count(case((ActivityLog.status == "success", 1))),
                    func.count(case((ActivityLog.status == "failed", 1))),
                    func.count(case((ActivityLog.status == "started", 1))),
                ).where(*conditions)
            )
        ).one()
        groups = {}
        for name, column in (
            ("by_service", ActivityLog.service),
            ("by_project", ActivityLog.project_id),
            ("by_action", ActivityLog.action),
            ("by_page", ActivityLog.page),
        ):
            stmt = (
                select(
                    column,
                    func.count(ActivityLog.id),
                    func.count(case((ActivityLog.status == "failed", 1))),
                )
                .where(*conditions)
                .group_by(column)
                .order_by(desc(func.count(ActivityLog.id)), column.is_(None), column)
            )
            groups[name] = [
                {"key": key if key is not None else "unknown", "total": total, "failed": failed}
                for key, total, failed in (await session.execute(stmt)).all()
            ]
    return dict(zip(("total", "success", "failed", "started"), counts, strict=True)) | groups


async def list_user_management_events(
    *,
    limit: int = 50,
    before_id: int | None = None,
) -> list[dict]:
    """관리자용. resource_type='user' 이벤트를 cross-project로 시간 역순 조회.

    사용자 생성·수정·삭제 변경 로그 카드에 사용.
    """
    if not is_db_available():
        return []
    factory = get_session_factory()
    if factory is None:
        return []
    async with factory() as session:
        conds = [ActivityLog.resource_type == "user"]
        if before_id is not None:
            conds.append(ActivityLog.id < before_id)
        stmt = select(ActivityLog).where(and_(*conds)).order_by(desc(ActivityLog.id)).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_dict(r) for r in rows]


def _row_to_dict(r: ActivityLog) -> dict:
    return {
        "id": r.id,
        "created_at": r.created_at.replace(tzinfo=UTC).isoformat()
        if r.created_at.tzinfo is None
        else r.created_at.isoformat(),
        "project_id": r.project_id,
        "user_id": r.user_id,
        "username": r.username,
        "resource_type": r.resource_type,
        "resource_id": r.resource_id,
        "resource_name": r.resource_name,
        "action": r.action,
        "status": r.status,
        "error_message": r.error_message,
        "request_id": r.request_id,
        "external_id": r.external_id,
        "event_type": r.event_type,
        "service": r.service,
        "source": r.source if r.source is not None else "afterglow",
        "page": r.page,
        "http_status": r.http_status,
        "extra": r.extra,
    }
