"""사용자 셀프서비스 프로젝트 관리 API."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_caller_project_permissions,
    get_token_info,
    require_admin,
)
from app.database import get_session

router = APIRouter()


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    domain_id: str | None = Field(default=None, min_length=1)


class ReplaceMemberRolesRequest(BaseModel):
    role_ids: list[str]


class MigrateLegacyManagersRequest(BaseModel):
    owner_user_id: str = Field(min_length=1)


class TransferOwnershipRequest(BaseModel):
    user_id: str = Field(min_length=1)


class ProjectCreatorRequest(BaseModel):
    domain_id: str | None = Field(default=None, min_length=1)
    enabled: bool = Field(strict=True)


class OwnershipReconcileRequest(BaseModel):
    operation_id: str = Field(min_length=1)
    domain_id: str | None = Field(default=None, min_length=1)
    native_calls_settled: bool = Field(strict=True)


class ProjectPermissionsResponse(BaseModel):
    project_id: str
    user_id: str
    roles: list[str]
    is_system_admin: bool
    is_owner: bool
    service_permissions: dict[str, list[str]]
    is_manager: bool
    is_reader: bool
    can_read: bool
    can_write: bool


# ─── 프로젝트 생성 ────────────────────────────────────────────────────────────


@router.post("", status_code=201)
async def create_project(
    req: CreateProjectRequest,
    token_info: dict = Depends(get_token_info),
):
    """Create a project and explicitly assign its creator project_owner."""
    from app.services.project_service import create_project_for_user

    if not req.name.strip():
        raise HTTPException(status_code=422, detail="프로젝트 이름을 입력하세요")

    return await create_project_for_user(
        name=req.name.strip(),
        description=req.description,
        user_id=token_info["user_id"],
        username=token_info.get("username", ""),
        domain_id=req.domain_id or token_info["domain_id"],
    )


@router.get("/capabilities")
async def project_capabilities(
    domain_id: str | None = Query(None, min_length=1),
    token_info: dict = Depends(get_token_info),
):
    from app.services.project_service import can_create_project

    target = domain_id or token_info["domain_id"]
    return {"domain_id": target, "can_create_project": await can_create_project(token_info["user_id"], target)}


@router.get("/creators")
async def list_project_creators(
    domain_id: str | None = Query(None, min_length=1),
    token_info: dict = Depends(get_token_info),
):
    from app.services.project_service import project_creators

    return await project_creators(domain_id or token_info["domain_id"], token_info["user_id"])


@router.put("/creators/{user_id}")
async def delegate_project_creator(
    user_id: str,
    req: ProjectCreatorRequest,
    token_info: dict = Depends(get_token_info),
):
    from app.services.project_service import change_project_creator

    return await change_project_creator(
        req.domain_id or token_info["domain_id"], user_id, req.enabled, token_info["user_id"]
    )


@router.get("/{project_id}/eligible-users")
async def eligible_users(project_id: str, token_info: dict = Depends(get_token_info)):
    from app.services.project_service import eligible_project_users

    return await eligible_project_users(project_id, token_info)


@router.get("/{project_id}/ownership")
async def ownership(project_id: str, token_info: dict = Depends(get_token_info)):
    from app.services.project_service import project_ownership

    return await project_ownership(project_id, token_info)


@router.post("/{project_id}/ownership-transfer")
async def transfer_ownership(
    project_id: str, req: TransferOwnershipRequest, token_info: dict = Depends(get_token_info)
):
    from app.services.project_service import transfer_project_ownership

    return await transfer_project_ownership(project_id, req.user_id, token_info)


@router.post("/{project_id}/ownership-transfer/reconcile", dependencies=[Depends(require_admin)])
async def reconcile_ownership(
    project_id: str,
    req: OwnershipReconcileRequest,
    token_info: dict = Depends(get_token_info),
):
    from app.services.project_service import reconcile_project_ownership

    return await reconcile_project_ownership(
        project_id,
        req.operation_id,
        req.domain_id or token_info["domain_id"],
        token_info,
        native_calls_settled=req.native_calls_settled,
    )


@router.get("/{project_id}/deletion-check")
async def deletion_check(project_id: str, token_info: dict = Depends(get_token_info)):
    from app.services.project_service import project_deletion_check

    return await project_deletion_check(project_id, token_info)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, token_info: dict = Depends(get_token_info)):
    from app.services.project_service import delete_empty_project

    await delete_empty_project(project_id, token_info)


# ─── 권한 및 역할 조회 ────────────────────────────────────────────────────────


@router.get("/current/permissions", response_model=ProjectPermissionsResponse)
async def get_current_project_permissions(
    token_info: dict = Depends(get_token_info),
):
    """현재 활성 프로젝트에 대한 호출자의 역할 및 실효 권한 조회."""
    return await get_caller_project_permissions(token_info=token_info)


@router.get("/{project_id}/permissions", response_model=ProjectPermissionsResponse)
async def get_project_permissions(
    project_id: str = Path(...),
    token_info: dict = Depends(get_token_info),
):
    """지정된 프로젝트에 대한 호출자의 역할 및 실효 권한 조회.

    'current'를 넘기면 현재 프로젝트의 권한을 반환합니다.
    """
    if project_id == "current":
        return await get_caller_project_permissions(token_info=token_info)

    from app.services.domain_scope import assert_project_domain

    await asyncio.to_thread(assert_project_domain, token_info.get("domain_id", ""), project_id)

    # 다른 프로젝트 조회 시 소속 여부(Keystone rescope) 검증
    if not token_info.get("is_system_admin", False) and project_id != token_info.get("project_id"):
        from app.api.deps import _cached_validate

        try:
            await _cached_validate(token_info["token"], project_id)
            return await get_caller_project_permissions(
                project_id=project_id, token_info={**token_info, "is_system_admin": False}
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=403, detail="해당 프로젝트에 대한 접근 권한이 없습니다.")

    return await get_caller_project_permissions(project_id=project_id, token_info=token_info)


# ─── 멤버 조회 ────────────────────────────────────────────────────────────────


@router.get("/{project_id}/members")
async def list_project_members(
    project_id: str = Path(...),
    token_info: dict = Depends(get_token_info),
):
    """Current direct, group and inherited effective membership; no DB authority."""
    from app.services.project_service import list_members

    return await list_members(project_id, token_info)


@router.get("/{project_id}/assignable-roles")
async def get_assignable_roles(
    project_id: str = Path(...),
    token_info: dict = Depends(get_token_info),
):
    from app.services.project_service import assignable_roles

    return await assignable_roles(project_id, token_info)


@router.put("/{project_id}/members/{user_id}/roles")
async def replace_project_member_roles(
    req: ReplaceMemberRolesRequest,
    project_id: str = Path(...),
    user_id: str = Path(...),
    token_info: dict = Depends(get_token_info),
):
    from app.services.project_service import replace_member_roles

    return await replace_member_roles(project_id, user_id, req.role_ids, token_info)


@router.delete("/{project_id}/members/{user_id}")
async def remove_project_member(
    project_id: str = Path(...),
    user_id: str = Path(...),
    token_info: dict = Depends(get_token_info),
):
    """Remove only managed direct project grants; effective/group grants remain."""
    from app.services.project_service import replace_member_roles

    member = await replace_member_roles(project_id, user_id, [], token_info, remove=True)
    return {"status": "removed", "member": member}


@router.post("/{project_id}/members/migrate-legacy-managers", dependencies=[Depends(require_admin)])
async def migrate_project_legacy_managers(
    req: MigrateLegacyManagersRequest,
    project_id: str = Path(...),
    token_info: dict = Depends(get_token_info),
    session: AsyncSession = Depends(get_session),
):
    from app.services.project_service import migrate_legacy_managers

    return await migrate_legacy_managers(project_id, req.owner_user_id, token_info, session)
