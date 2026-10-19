"""Manager-only IAM within the authenticated user's canonical identity domain."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_domain_manager
from app.database import get_session
from app.rate_limit import limiter
from app.services import domain_iam, project_service


class IamRoute(APIRoute):
    """Never echo password/token input through Pydantic's validation errors."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request):
            try:
                response = await handler(request)
            except RequestValidationError:
                response = JSONResponse({"detail": "Invalid IAM request"}, status_code=422)
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
            response.headers.update(
                {"Cache-Control": "no-store, private", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}
            )
            return response

        return guarded


router = APIRouter(route_class=IamRoute)


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateUser(StrictBody):
    name: str = Field(min_length=1, max_length=255, pattern=r"^\S(?:.*\S)?$")
    personal_domain_name: str = Field(min_length=1, max_length=64, pattern=r"^\S(?:.*\S)?$")
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=1024)
    enabled: bool = True
    project_id: str | None = None
    role_ids: list[str] = Field(default_factory=list, max_length=256)


class UpdateUser(StrictBody):
    name: str | None = Field(default=None, min_length=1, max_length=255, pattern=r"^\S(?:.*\S)?$")
    email: str | None = Field(default=None, min_length=3, max_length=255)
    password: str | None = Field(default=None, min_length=12, max_length=1024)
    enabled: bool | None = None


class MemberRoles(StrictBody):
    role_ids: list[str] = Field(max_length=256)


class Invite(StrictBody):
    email: str = Field(min_length=3, max_length=255)
    project_id: str | None = Field(default=None, min_length=1, max_length=64)
    role_ids: list[str] = Field(default_factory=list, max_length=256)


@router.get("/context")
async def get_context(token_info: dict = Depends(require_domain_manager)):
    return await domain_iam.context(token_info)


@router.get("/users")
async def users(token_info: dict = Depends(require_domain_manager)):
    return await domain_iam.list_resources("users", token_info)


@router.post("/users", status_code=201)
@limiter.limit("20/minute")
async def create_user(
    request: Request,
    req: CreateUser,
    token_info: dict = Depends(require_domain_manager),
    session: AsyncSession = Depends(get_session),
):
    return await domain_iam.create_user(req.model_dump(), token_info, session)


@router.patch("/users/{user_id}")
@limiter.limit("20/minute")
async def update_user(
    request: Request, user_id: str, req: UpdateUser, token_info: dict = Depends(require_domain_manager)
):
    attrs = req.model_dump(exclude_unset=True)
    if not attrs or any(value is None for value in attrs.values()):
        raise HTTPException(422, "Supply non-null user fields")
    return await domain_iam.update_user(user_id, attrs, token_info)


@router.get("/projects")
async def projects(token_info: dict = Depends(require_domain_manager)):
    return await domain_iam.list_resources("projects", token_info)


@router.get("/groups")
async def groups(token_info: dict = Depends(require_domain_manager)):
    return await domain_iam.list_resources("groups", token_info)


@router.get("/projects/{project_id}/members")
async def members(project_id: str, token_info: dict = Depends(require_domain_manager)):
    await domain_iam.context(token_info)
    return await project_service.list_members(project_id, token_info, domain_management=True)


@router.get("/projects/{project_id}/assignable-roles")
async def assignable_roles(project_id: str, token_info: dict = Depends(require_domain_manager)):
    await domain_iam.context(token_info)
    return await project_service.assignable_roles(project_id, token_info, domain_management=True)


@router.put("/projects/{project_id}/members/{user_id}/roles")
async def replace_roles(
    project_id: str, user_id: str, req: MemberRoles, token_info: dict = Depends(require_domain_manager)
):
    await domain_iam.context(token_info)
    return await project_service.replace_member_roles(
        project_id, user_id, req.role_ids, token_info, domain_management=True
    )


@router.delete("/projects/{project_id}/members/{user_id}")
async def remove_member(project_id: str, user_id: str, token_info: dict = Depends(require_domain_manager)):
    await domain_iam.context(token_info)
    result = await project_service.replace_member_roles(
        project_id, user_id, [], token_info, remove=True, domain_management=True
    )
    return {"status": "removed", "member": result}


@router.get("/invitations")
async def invitations(token_info: dict = Depends(require_domain_manager), session: AsyncSession = Depends(get_session)):
    return await domain_iam.list_invitations(token_info, session)


@router.post("/invitations", status_code=201)
@limiter.limit("10/minute")
async def invite(
    request: Request,
    req: Invite,
    token_info: dict = Depends(require_domain_manager),
    session: AsyncSession = Depends(get_session),
):
    return await domain_iam.invite(req.model_dump(), token_info, session)


@router.delete("/invitations/{invitation_id}", status_code=204)
async def revoke(
    invitation_id: int, token_info: dict = Depends(require_domain_manager), session: AsyncSession = Depends(get_session)
):
    await domain_iam.revoke(invitation_id, token_info, session)


@router.get("/operations")
async def operations(token_info: dict = Depends(require_domain_manager), session: AsyncSession = Depends(get_session)):
    return await domain_iam.list_invitations(token_info, session, operations=True)


@router.delete("/operations/{operation_id}", status_code=204)
async def recover(
    operation_id: int, token_info: dict = Depends(require_domain_manager), session: AsyncSession = Depends(get_session)
):
    await domain_iam.revoke(operation_id, token_info, session, operation=True)
