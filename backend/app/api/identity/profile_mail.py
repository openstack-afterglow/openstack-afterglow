"""Preferences belong only to the freshly resolved immutable user/home."""

from fastapi import APIRouter, Depends
from pydantic import Field

from app.api.deps import get_token_info
from app.api.identity.account_recovery import RecoveryRoute
from app.api.identity.admin_mail_delivery import _call
from app.api.identity.iam import StrictBody
from app.services import mail_delivery

router = APIRouter(route_class=RecoveryRoute)


class EmailNotifications(StrictBody):
    announcements: bool = Field(strict=True)
    resource_alerts: bool = Field(strict=True)


@router.get("/email-notifications")
async def email_notifications(token_info: dict = Depends(get_token_info)):
    return await _call(mail_delivery.preferences(token_info))


@router.put("/email-notifications")
async def save_email_notifications(payload: EmailNotifications, token_info: dict = Depends(get_token_info)):
    return await _call(mail_delivery.preferences(token_info, values=payload.model_dump()))
