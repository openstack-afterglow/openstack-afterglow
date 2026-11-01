"""Mount once under /api/v1/admin; generated passwords never enter responses."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_admin_os_conn, require_admin
from app.api.identity.account_recovery import RecoveryRoute
from app.api.identity.iam import StrictBody
from app.database import get_session
from app.rate_limit import limiter
from app.services import admin_password_reset

router = APIRouter(route_class=RecoveryRoute)


class ResetEmail(StrictBody):
    """The browser selects only the exact native target ID, never credentials/mail."""


@router.post("/users/{user_id}/password/reset-email")
@limiter.limit("3/minute")
async def reset_password_email(
    request: Request,
    response: Response,
    user_id: str,
    req: ResetEmail,
    actor: dict = Depends(require_admin),
    conn=Depends(get_admin_os_conn),
    session: AsyncSession = Depends(get_session),
):
    return await admin_password_reset.reset_password_email(user_id, actor, conn, session)
