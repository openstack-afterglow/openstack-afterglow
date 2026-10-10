"""사용자 셀프서비스 프로젝트 관리 API."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_caller_project_permissions,
    get_token_info,
    require_admin,
    require_project_manager,
)
from app.database import get_session
from app.models.db import ProjectInvitation
from app.services.identity_roles import visible_role_names

router = APIRouter()


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""


class CreateInvitationRequest(BaseModel):
    email: str
    keystone_role: Literal["project_member", "project_reader"] = "project_member"


class ReplaceMemberRolesRequest(BaseModel):
    role_ids: list[str]


class MigrateLegacyManagersRequest(BaseModel):
    owner_user_id: str = Field(min_length=1)


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
    )


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


# ─── 초대 ─────────────────────────────────────────────────────────────────────


@router.post("/{project_id}/invitations", status_code=201)
async def create_invitation(
    req: CreateInvitationRequest,
    project_id: str = Path(...),
    token_info: dict = Depends(get_token_info),
    session: AsyncSession = Depends(get_session),
):
    """이메일 주소로 프로젝트에 초대합니다."""
    await require_project_manager(project_id, token_info)

    project_name = await _get_project_name(project_id)

    from app.services.project_service import create_invitation

    return await create_invitation(
        project_id=project_id,
        project_name=project_name,
        invited_email=req.email.lower().strip(),
        invited_by=token_info["user_id"],
        invited_by_name=token_info.get("username", ""),
        session=session,
        keystone_role=req.keystone_role,
    )


@router.get("/{project_id}/invitations")
async def list_invitations(
    project_id: str = Path(...),
    token_info: dict = Depends(get_token_info),
    session: AsyncSession = Depends(get_session),
):
    """프로젝트 초대 목록 조회."""
    await require_project_manager(project_id, token_info)

    result = await session.execute(
        select(ProjectInvitation)
        .where(ProjectInvitation.project_id == project_id)
        .order_by(ProjectInvitation.created_at.desc())
    )
    invitations = result.scalars().all()
    visible = set(
        await visible_role_names([inv.keystone_role for inv in invitations], token_info.get("is_system_admin", False))
    )
    return {
        "items": [
            {
                "id": inv.id,
                "invited_email": inv.invited_email,
                "invited_by_name": inv.invited_by_name,
                "status": inv.status,
                "keystone_role": inv.keystone_role,
                "expires_at": inv.expires_at.isoformat() + "Z",
                "accepted_at": inv.accepted_at.isoformat() + "Z" if inv.accepted_at else None,
                "created_at": inv.created_at.isoformat() + "Z",
            }
            for inv in invitations
            if inv.keystone_role in visible
        ]
    }


@router.delete("/{project_id}/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(
    project_id: str = Path(...),
    invitation_id: int = Path(...),
    token_info: dict = Depends(get_token_info),
    session: AsyncSession = Depends(get_session),
):
    """초대 취소 (pending 상태만 가능)."""
    await require_project_manager(project_id, token_info)

    result = await session.execute(
        select(ProjectInvitation).where(
            ProjectInvitation.id == invitation_id,
            ProjectInvitation.project_id == project_id,
        )
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="초대를 찾을 수 없습니다")
    if inv.status != "pending":
        raise HTTPException(status_code=409, detail="취소할 수 없는 상태의 초대입니다")

    inv.status = "revoked"
    await session.commit()


# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────


async def _get_project_name(project_id: str) -> str:
    from app.services import keystone

    def _lookup():
        ks = keystone._get_admin_ks_client()
        try:
            p = ks.projects.get(project_id)
            return p.name or project_id
        except Exception:
            return project_id

    try:
        return await asyncio.to_thread(_lookup)
    except Exception:
        return project_id
