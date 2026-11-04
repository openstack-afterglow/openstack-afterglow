"""Fresh administrator authorization and scoped, audited diagnostic disclosure."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError

from app.api.common.admin_resource_scope import AdminResourceScope, admin_resource_scope
from app.api.common.experience import require_experience
from app.api.deps import require_admin
from app.models.experience import uuid_string
from app.services import experience

router = APIRouter(dependencies=[Depends(require_experience)])


def filters(
    segment_id: str = Query(..., min_length=36, max_length=36),
    action_id: str | None = Query(None, min_length=36, max_length=36),
    before_id: int | None = Query(None, ge=1, le=9223372036854775807),
    include_anonymous: bool = Query(False),
) -> dict:
    try:
        uuid_string(segment_id)
        if action_id is not None:
            uuid_string(action_id)
    except ValueError:
        raise HTTPException(422, "Canonical diagnostic identifiers required") from None
    return {
        "segment_id": segment_id,
        "action_id": action_id,
        "before_id": before_id,
        "include_anonymous": include_anonymous,
    }


async def _query(*, query_filters: dict, actor: dict, scope: AdminResourceScope, limit: int, export: bool) -> dict:
    try:
        return await experience.query(
            **query_filters,
            actor=actor,
            project_ids=scope.project_ids,
            domain_id=scope.domain_id,
            limit=limit,
            export=export,
        )
    except PermissionError:
        raise HTTPException(403, "Diagnostic scope is not authorized") from None
    except (experience.ExperienceUnavailable, SQLAlchemyError):
        raise HTTPException(503, "Experience database is unavailable") from None


@router.get("/experiences/segments")
async def list_experience_segments(
    response: Response,
    actor: dict = Depends(require_admin),
    scope: AdminResourceScope = Depends(admin_resource_scope),
    user_id: str | None = Query(None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
    days: int = Query(1, json_schema_extra={"enum": [1, 7, 30]}),
    limit: int = Query(20, ge=1, le=50),
    include_anonymous: bool = Query(False),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    if days not in {1, 7, 30}:
        raise HTTPException(422, "Diagnostic days must be 1, 7 or 30")
    try:
        return await experience.query_segments(
            actor=actor,
            project_ids=scope.project_ids,
            domain_id=scope.domain_id,
            user_id=user_id,
            days=days,
            limit=limit,
            include_anonymous=include_anonymous,
        )
    except PermissionError:
        raise HTTPException(403, "Diagnostic scope is not authorized") from None
    except (experience.ExperienceUnavailable, SQLAlchemyError):
        raise HTTPException(503, "Experience database is unavailable") from None


@router.get("/experiences")
async def list_experiences(
    response: Response,
    query_filters: dict = Depends(filters),
    actor: dict = Depends(require_admin),
    scope: AdminResourceScope = Depends(admin_resource_scope),
    limit: int = Query(200, ge=1, le=200),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return await _query(query_filters=query_filters, actor=actor, scope=scope, limit=limit, export=False)


@router.get("/experiences/export")
async def export_experiences(
    query_filters: dict = Depends(filters),
    actor: dict = Depends(require_admin),
    scope: AdminResourceScope = Depends(admin_resource_scope),
    limit: int = Query(2000, ge=1, le=2000),
) -> Response:
    projection = await _query(query_filters=query_filters, actor=actor, scope=scope, limit=limit, export=True)
    return Response(
        content=json.dumps(projection, ensure_ascii=False, separators=(",", ":")),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="afterglow-experience.json"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
