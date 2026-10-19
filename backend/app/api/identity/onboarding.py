"""Public enrollment requires a delivered email token, never an asserted email."""

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_token_info
from app.api.identity.iam import IamRoute, StrictBody
from app.database import get_session
from app.rate_limit import limiter
from app.services import domain_iam

router = APIRouter(route_class=IamRoute)


class TokenBody(StrictBody):
    token: str = Field(min_length=32, max_length=256)


class AcceptAccount(TokenBody):
    name: str = Field(min_length=1, max_length=255, pattern=r"^\S(?:.*\S)?$")
    personal_domain_name: str = Field(min_length=1, max_length=64, pattern=r"^\S(?:.*\S)?$")
    password: str = Field(min_length=12, max_length=1024)


class Register(StrictBody):
    email: str = Field(min_length=3, max_length=255)


def no_store(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"


@router.get("/invitations/{token}")
@limiter.limit("20/minute")
async def invitation(request: Request, response: Response, token: str, session: AsyncSession = Depends(get_session)):
    no_store(response)
    return await domain_iam.invitation_info(token, session)


@router.post("/invitations/accept")
@limiter.limit("5/minute")
async def accept_invitation(
    request: Request, response: Response, req: AcceptAccount, session: AsyncSession = Depends(get_session)
):
    no_store(response)
    return await domain_iam.redeem(
        req.token,
        "invitation",
        session,
        name=req.name,
        password=req.password,
        personal_domain_name=req.personal_domain_name,
    )


@router.post("/invitations/accept-existing")
@limiter.limit("5/minute")
async def accept_existing(
    request: Request,
    response: Response,
    req: TokenBody,
    token_info: dict = Depends(get_token_info),
    session: AsyncSession = Depends(get_session),
):
    no_store(response)
    return await domain_iam.redeem(req.token, "invitation", session, token_info=token_info)


@router.get("/signup/options")
@limiter.limit("20/minute")
async def signup_options(request: Request, response: Response):
    no_store(response)
    return await domain_iam.signup_options()


@router.post("/registrations", status_code=202)
@limiter.limit("3/minute")
async def register_global(
    request: Request, response: Response, req: Register, session: AsyncSession = Depends(get_session)
):
    no_store(response)
    return await domain_iam.register(req.email, session)


@router.get("/registrations/{token}")
@limiter.limit("20/minute")
async def registration(
    request: Request,
    response: Response,
    token: str = Path(min_length=32, max_length=256),
    session: AsyncSession = Depends(get_session),
):
    no_store(response)
    return await domain_iam.registration_info(token, session)


@router.post("/domains/{domain_id}/registrations", status_code=202)
@limiter.limit("3/minute")
async def register(
    request: Request, response: Response, domain_id: str, req: Register, session: AsyncSession = Depends(get_session)
):
    no_store(response)
    raise HTTPException(403, "invitation_required")


@router.post("/registrations/accept")
@limiter.limit("5/minute")
async def accept_registration(
    request: Request, response: Response, req: AcceptAccount, session: AsyncSession = Depends(get_session)
):
    no_store(response)
    return await domain_iam.redeem(
        req.token,
        "registration",
        session,
        name=req.name,
        password=req.password,
        personal_domain_name=req.personal_domain_name,
    )
