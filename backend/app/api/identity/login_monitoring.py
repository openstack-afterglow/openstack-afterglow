"""Selected-user login monitoring; mounted by the application integration owner."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Response

from app.api.deps import get_os_conn, require_admin
from app.services import login_monitoring as service

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/users")
async def users(
    response: Response,
    limit: int = Query(100, ge=1, le=100),
    marker: str | None = Query(None, max_length=128),
    conn=Depends(get_os_conn),
):
    response.headers["Cache-Control"] = "no-store"
    return await service.directory(conn, limit, marker)


@router.get("/users/{user_id}")
async def user_monitoring(
    response: Response,
    user_id: str = Path(min_length=1, max_length=64),
    window: service.Window = Query("24h"),
    conn=Depends(get_os_conn),
):
    response.headers["Cache-Control"] = "no-store"
    return await service.selected_user(conn, user_id, window)
