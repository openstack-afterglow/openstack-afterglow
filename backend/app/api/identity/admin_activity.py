"""관리자용 프로젝트별 활동 로그 조회 API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import InterfaceError, OperationalError

from app.api.deps import get_token_info, require_admin
from app.services import activity as svc

router = APIRouter()


@router.get("/projects/{project_id}/activity", dependencies=[Depends(require_admin)])
async def list_project_activity(
    project_id: str,
    _: dict = Depends(get_token_info),
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(None),
    resource_type: str | None = Query(None),
    action: str | None = Query(None),
    user_id: str | None = Query(None),
) -> list[dict]:
    """프로젝트 내 모든 사용자 활동 로그 (admin only)."""
    return await svc.list_for_project(
        project_id,
        limit=limit,
        before_id=before_id,
        resource_type=resource_type,
        action=action,
        user_id=user_id,
    )


def _event_filters(
    project_id: str | None = Query(None, max_length=64),
    user_id: str | None = Query(None, max_length=64),
    username: str | None = Query(None, max_length=255),
    resource_id: str | None = Query(None, max_length=128),
    resource_type: str | None = Query(None, max_length=32),
    action: str | None = Query(None, max_length=48),
    status: str | None = Query(None, pattern="^(started|success|failed)$"),
    service: str | None = Query(None, max_length=32),
    source: str | None = Query(None, max_length=16),
    request_id: str | None = Query(None, max_length=64),
    page: str | None = Query(None, max_length=255),
    from_at: datetime | None = Query(None),
    to_at: datetime | None = Query(None),
) -> dict:
    """Require explicit timezone offsets so date ranges have one interpretation."""
    if any(value is not None and (value.tzinfo is None or value.utcoffset() is None) for value in (from_at, to_at)):
        raise HTTPException(status_code=422, detail="Date filters require a timezone offset")
    if from_at is not None and to_at is not None and from_at > to_at:
        raise HTTPException(status_code=422, detail="from_at must not exceed to_at")
    return {
        "project_id": project_id,
        "user_id": user_id,
        "username": username,
        "resource_id": resource_id,
        "resource_type": resource_type,
        "action": action,
        "status": status,
        "service": service,
        "source": source,
        "request_id": request_id,
        "page": page,
        "from_at": from_at,
        "to_at": to_at,
    }


@router.get("/events", dependencies=[Depends(require_admin)])
async def list_global_events(
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(None, ge=1, le=9223372036854775807),
    filters: dict = Depends(_event_filters),
) -> list[dict]:
    try:
        return await svc.list_events(limit=limit, before_id=before_id, **filters)
    except (svc.ActivityDatabaseUnavailable, OperationalError, InterfaceError) as exc:
        raise HTTPException(status_code=503, detail="Activity database is unavailable") from exc


@router.get("/events/stats", dependencies=[Depends(require_admin)])
async def global_event_stats(filters: dict = Depends(_event_filters)) -> dict:
    try:
        return await svc.event_stats(**filters)
    except (svc.ActivityDatabaseUnavailable, OperationalError, InterfaceError) as exc:
        raise HTTPException(status_code=503, detail="Activity database is unavailable") from exc


@router.get("/events/{event_id}", dependencies=[Depends(require_admin)])
async def get_global_event(event_id: int) -> dict:
    if not 1 <= event_id <= 9223372036854775807:
        raise HTTPException(status_code=422, detail="event_id is outside the valid range")
    try:
        event = await svc.get_event(event_id)
    except (svc.ActivityDatabaseUnavailable, OperationalError, InterfaceError) as exc:
        raise HTTPException(status_code=503, detail="Activity database is unavailable") from exc
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
