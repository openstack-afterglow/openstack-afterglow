"""Mount this router once at /api/v1/auth; proofs never appear in responses to requests."""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import get_token_info
from app.api.identity.iam import IamRoute, StrictBody
from app.database import get_session
from app.rate_limit import limiter
from app.services import account_recovery


class RecoveryRoute(IamRoute):
    """Keep proof responses private even when SlowAPI raises Starlette's 429."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request):
            try:
                response = await handler(request)
            except StarletteHTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
            response.headers.update(
                {"Cache-Control": "no-store, private", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}
            )
            return response

        return guarded


router = APIRouter(route_class=RecoveryRoute)


class RecoveryRequest(StrictBody):
    email: str = Field(min_length=3, max_length=255)


class RecoveryToken(StrictBody):
    token: str = Field(min_length=32, max_length=256, repr=False)


class CompletePassword(RecoveryToken):
    new_password: str = Field(min_length=12, max_length=1024, repr=False)


class EmailChange(RecoveryRequest):
    current_password: str = Field(min_length=1, max_length=1024, repr=False)


@router.post("/recovery/username", status_code=202)
@limiter.limit("3/minute")
async def request_username(
    request: Request, response: Response, req: RecoveryRequest, session: AsyncSession = Depends(get_session)
):
    return await account_recovery.request_recovery("username", req.email, session)


@router.post("/recovery/password", status_code=202)
@limiter.limit("3/minute")
async def request_password(
    request: Request, response: Response, req: RecoveryRequest, session: AsyncSession = Depends(get_session)
):
    return await account_recovery.request_recovery("password", req.email, session)


@router.get("/recovery/{token}")
@limiter.shared_limit("20/minute", scope="recovery-token-inspection")
async def inspect_recovery(
    request: Request, response: Response, token: str, session: AsyncSession = Depends(get_session)
):
    return await account_recovery.inspect(token, session)


@router.post("/recovery/password/complete")
@limiter.limit("5/minute")
async def complete_password(
    request: Request, response: Response, req: CompletePassword, session: AsyncSession = Depends(get_session)
):
    return await account_recovery.complete(req.token, session, new_password=req.new_password)


@router.post("/email/changes", status_code=202)
@limiter.limit("3/minute")
async def request_email_change(
    request: Request,
    response: Response,
    req: EmailChange,
    token_info: dict = Depends(get_token_info),
    session: AsyncSession = Depends(get_session),
):
    return await account_recovery.request_email_change(req.email, req.current_password, token_info, session)


@router.post("/email/changes/accept")
@limiter.limit("5/minute")
async def accept_email_change(
    request: Request, response: Response, req: RecoveryToken, session: AsyncSession = Depends(get_session)
):
    return await account_recovery.complete(req.token, session, kind="email_change")
