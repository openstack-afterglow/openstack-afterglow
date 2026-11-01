"""Email-proven initial password creation and explicit operator reconciliation."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_token_info, require_admin
from app.api.identity.account_recovery import RecoveryRoute
from app.api.identity.iam import StrictBody
from app.database import get_session
from app.rate_limit import limiter
from app.services import account_recovery

router = APIRouter(route_class=RecoveryRoute)
admin_router = APIRouter(route_class=RecoveryRoute)


class PasswordCreationRequest(StrictBody):
    pass


class PasswordCreationSettlement(StrictBody):
    identity_domain_id: str = Field(min_length=1, max_length=64)
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolution: Literal["existing", "retry"]
    evidence: str = Field(min_length=1, max_length=2000)
    native_calls_settled: bool = Field(strict=True)


@router.get("/password/capability")
async def password_capability(token_info: dict = Depends(get_token_info), session: AsyncSession = Depends(get_session)):
    return await account_recovery.password_capability(token_info, session)


@router.post("/password/create/request", status_code=202)
@limiter.limit("3/minute")
async def request_password_creation(
    request: Request,
    response: Response,
    req: PasswordCreationRequest,
    token_info: dict = Depends(get_token_info),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await account_recovery.request_password_creation(token_info, session)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, {"code": "password_create_unavailable"}) from None


@router.post("/password/recovery/request", status_code=202)
@limiter.limit("3/minute")
async def request_password_recovery(
    request: Request,
    response: Response,
    req: PasswordCreationRequest,
    token_info: dict = Depends(get_token_info),
    session: AsyncSession = Depends(get_session),
):
    return await account_recovery.request_profile_password_recovery(token_info, session)


@admin_router.get("/password-creations/{user_id}")
async def password_creation_operations(
    user_id: str,
    identity_domain_id: str = Query(min_length=1, max_length=64),
    actor: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await account_recovery.password_creation_operations(user_id, identity_domain_id, session)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, {"code": "password_create_settlement_unavailable"}) from None


@admin_router.post("/password-creations/{user_id}/settle")
@limiter.limit("5/minute")
async def settle_password_creation(
    request: Request,
    response: Response,
    user_id: str,
    req: PasswordCreationSettlement,
    actor: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await account_recovery.settle_password_creation(
            user_id,
            req.identity_domain_id,
            req.operation_id,
            req.resolution,
            req.evidence,
            req.native_calls_settled,
            actor,
            session,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, {"code": "password_create_settlement_unavailable"}) from None
