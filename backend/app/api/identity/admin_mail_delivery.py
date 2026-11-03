"""Fresh system-administrator outgoing intent and private delivery history."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import require_admin
from app.api.identity.account_recovery import RecoveryRoute
from app.api.identity.iam import StrictBody
from app.services import mail_delivery

router = APIRouter(route_class=RecoveryRoute, dependencies=[Depends(require_admin)])


class IndividualMessage(StrictBody):
    operation_id: UUID
    user_ids: list[Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]] = Field(
        min_length=1, max_length=100
    )
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000, repr=False)


class TestMessage(StrictBody):
    operation_id: UUID
    recipient_email: str = Field(min_length=3, max_length=255)


class AnnouncementMessage(StrictBody):
    operation_id: UUID


async def _call(awaitable):
    try:
        return await awaitable
    except HTTPException:
        raise
    except (SQLAlchemyError, ValueError):
        raise HTTPException(503, {"code": "mail_storage_unavailable"}) from None
    except Exception:
        raise HTTPException(503, {"code": "mail_unavailable"}) from None


@router.post("/email/messages", status_code=202)
async def send_message(payload: IndividualMessage, actor: dict = Depends(require_admin)):
    return await _call(
        mail_delivery.send_individual(
            actor_id=actor["user_id"],
            operation_id=payload.operation_id,
            user_ids=payload.user_ids,
            subject=payload.subject,
            body=payload.body,
        )
    )


@router.post("/email/test-message", status_code=202)
async def send_test_message(payload: TestMessage, actor: dict = Depends(require_admin)):
    return await _call(
        mail_delivery.send_test(
            actor_id=actor["user_id"],
            operation_id=payload.operation_id,
            recipient_email=payload.recipient_email,
        )
    )


@router.get("/email/deliveries")
async def deliveries(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    return await _call(mail_delivery.list_deliveries(limit=limit, offset=offset))


@router.get("/email/deliveries/{delivery_id}")
async def delivery(delivery_id: UUID):
    return await _call(mail_delivery.get_delivery(str(delivery_id)))


@router.post("/announcements/{announcement_id}/email", status_code=202)
async def email_announcement(announcement_id: int, payload: AnnouncementMessage, actor: dict = Depends(require_admin)):
    return await _call(
        mail_delivery.send_announcement(
            actor_id=actor["user_id"],
            operation_id=payload.operation_id,
            announcement_id=announcement_id,
        )
    )
