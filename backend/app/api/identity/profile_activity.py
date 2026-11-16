"""사용자 본인 활동 로그 조회 API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_token_info
from app.services import activity as svc

router = APIRouter()


@router.get("")
async def list_my_activity(
    token_info: dict = Depends(get_token_info),
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(None),
    resource_type: str | None = Query(None),
    action: str | None = Query(None),
) -> list[dict]:
    """본인의 의도적인 리소스 변경·세션 보안 활동만 조회 (cross-project)."""
    return await svc.list_for_user(
        token_info["user_id"],
        limit=limit,
        before_id=before_id,
        resource_type=resource_type,
        action=action,
    )
