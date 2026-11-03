"""관리자 공지(announcement) 발송/관리 API.

전 엔드포인트 관리자 전용(require_admin). 사용자 수신 측 API는
app/api/common/announcements.py 참조.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_token_info, require_admin
from app.api.identity.account_recovery import RecoveryRoute
from app.services.announcements import (
    SEVERITIES,
    TARGET_TYPES,
    AnnouncementNotFoundError,
    AnnouncementStorageUnavailable,
    AnnouncementValidationError,
    create_announcement,
    delete_announcement,
    list_admin_announcements,
    update_announcement,
)

router = APIRouter(route_class=RecoveryRoute, dependencies=[Depends(require_admin)])


class AnnouncementCreateRequest(BaseModel):
    title: str = Field(..., max_length=200)
    body: str = Field(..., max_length=10_000)
    severity: str = Field(default="info")
    target_type: str
    target_id: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    send_email: bool = Field(default=False, strict=True)
    email_operation_id: UUID | None = None


class AnnouncementUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=10_000)
    severity: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None


class AnnouncementAdminResponse(BaseModel):
    id: int
    created_at: str
    updated_at: str
    created_by_user_id: str
    created_by_username: str
    title: str
    body: str
    severity: str
    target_type: str
    target_id: str | None
    starts_at: str | None
    ends_at: str | None
    is_active: bool
    email_operation: dict | None = None


@router.get("", response_model=list[AnnouncementAdminResponse])
async def list_announcements(limit: int = 100, offset: int = 0):
    """관리자용 전체 공지 목록 (발송 이력·타겟·활성 상태 포함)."""
    try:
        return await list_admin_announcements(limit=min(limit, 200), offset=max(offset, 0))
    except AnnouncementStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("", response_model=AnnouncementAdminResponse, status_code=201)
async def create_announcement_endpoint(
    payload: AnnouncementCreateRequest,
    token_info: dict = Depends(get_token_info),
):
    if payload.send_email and payload.email_operation_id is None:
        raise HTTPException(status_code=422, detail={"code": "mail_operation_id_required"})
    try:
        return await create_announcement(
            title=payload.title,
            body=payload.body,
            severity=payload.severity,
            target_type=payload.target_type,
            target_id=payload.target_id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            created_by_user_id=token_info.get("user_id", ""),
            created_by_username=token_info.get("username", ""),
            **(
                {"send_email": True, "email_operation_id": str(payload.email_operation_id)}
                if payload.send_email
                else {}
            ),
        )
    except AnnouncementValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AnnouncementStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError:
        raise HTTPException(status_code=503, detail={"code": "mail_payload_unavailable"}) from None


@router.patch("/{announcement_id}", response_model=AnnouncementAdminResponse)
async def update_announcement_endpoint(announcement_id: int, payload: AnnouncementUpdateRequest):
    patch = payload.model_dump(exclude_unset=True)
    try:
        return await update_announcement(announcement_id, **patch)
    except AnnouncementNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AnnouncementValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AnnouncementStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/{announcement_id}", status_code=204)
async def delete_announcement_endpoint(announcement_id: int):
    try:
        await delete_announcement(announcement_id)
    except AnnouncementNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AnnouncementStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/meta/options")
async def get_announcement_options():
    """작성 폼용 severity/target_type 허용값 목록."""
    return {"severities": list(SEVERITIES), "target_types": list(TARGET_TYPES)}
