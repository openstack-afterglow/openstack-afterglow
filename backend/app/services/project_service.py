"""셀프서비스 프로젝트 생성 + 이메일 초대 비즈니스 로직."""

import asyncio
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ProjectInvitation, ProjectRole
from app.services import activity, cache
from app.services.cache import keys

_logger = logging.getLogger(__name__)


# ─── 프로젝트 생성 ────────────────────────────────────────────────────────────


async def create_project_for_user(
    name: str,
    description: str,
    user_id: str,
    username: str,
    session: AsyncSession,
) -> dict:
    """Keystone 프로젝트 생성 + 생성자를 manager로 등록."""
    from app.config import get_settings
    from app.services import keystone

    settings = get_settings()

    # 1. keystoneclient admin으로 Keystone 프로젝트 생성
    def _create_keystone_project():
        ks = keystone._get_admin_ks_client()
        kwargs: dict = {"name": name}
        if description:
            kwargs["description"] = description
        p = ks.projects.create(**kwargs)
        return {"id": p.id, "name": p.name or "", "description": getattr(p, "description", "") or ""}

    project = await asyncio.to_thread(_create_keystone_project)
    project_id = project["id"]

    # 2. 생성자에게 Keystone member role 할당
    try:
        await asyncio.to_thread(_assign_keystone_role_by_name, project_id, user_id, "member")
    except Exception:
        _logger.warning("Keystone member role 할당 실패 — 프로젝트 보상 삭제 시작", exc_info=True)
        await _compensate_delete_keystone_project(project_id)
        raise HTTPException(status_code=500, detail="프로젝트 생성 중 오류가 발생했습니다")

    # 3. afterglow DB에 manager 레코드 삽입
    try:
        role_record = ProjectRole(
            project_id=project_id,
            user_id=user_id,
            role="manager",
            granted_by=user_id,
        )
        session.add(role_record)
        await session.commit()
    except Exception:
        _logger.warning("project_roles DB 삽입 실패 — 프로젝트 보상 삭제 시작", exc_info=True)
        await session.rollback()
        await _compensate_delete_keystone_project(project_id)
        raise HTTPException(status_code=500, detail="프로젝트 생성 중 오류가 발생했습니다")

    # 4. (best-effort) monitoring SG 자동 생성
    try:
        if settings.monitoring_auto_sg_enabled and settings.monitoring_scrape_cidr:
            from app.services import neutron

            def _ensure_sgs():
                conn = keystone.get_admin_connection_for_project(project_id)
                try:
                    neutron.ensure_node_exporter_sg(
                        conn,
                        project_id,
                        settings.node_exporter_sg_name,
                        settings.monitoring_scrape_cidr,
                    )
                    neutron.ensure_dcgm_exporter_sg(
                        conn,
                        project_id,
                        settings.dcgm_exporter_sg_name,
                        settings.monitoring_scrape_cidr,
                    )
                finally:
                    conn.close()

            await asyncio.to_thread(_ensure_sgs)
    except Exception:
        _logger.warning("모니터링 SG 자동 생성 실패 (계속 진행)", exc_info=True)

    await activity.record(
        project_id=project_id,
        user_id=user_id,
        username=username,
        resource_type="project",
        action="project_create",
        status="success",
        resource_id=project_id,
        resource_name=name,
    )

    await cache.invalidate(keys.user_key(user_id, "projects"))
    await cache.invalidate("afterglow:admin:projects")
    await cache.invalidate("afterglow:admin:project_names")
    return project


async def _compensate_delete_keystone_project(project_id: str) -> None:
    """Keystone 프로젝트 생성 후 DB 실패 시 보상 삭제."""
    from app.services import keystone

    try:

        def _delete():
            ks = keystone._get_admin_ks_client()
            ks.projects.delete(project_id)

        await asyncio.to_thread(_delete)
        _logger.info("보상 트랜잭션: Keystone 프로젝트 삭제 완료 (%s)", project_id)
    except Exception:
        _logger.error("보상 트랜잭션 실패: Keystone 프로젝트 삭제 불가 (%s)", project_id, exc_info=True)


# ─── 관리자 확인 ──────────────────────────────────────────────────────────────


async def is_project_manager(project_id: str, user_id: str, session: AsyncSession) -> bool:
    """project_roles 테이블에서 manager 여부 확인."""
    result = await session.execute(
        select(ProjectRole).where(
            ProjectRole.project_id == project_id,
            ProjectRole.user_id == user_id,
            ProjectRole.role == "manager",
        )
    )
    return result.scalar_one_or_none() is not None


# ─── 초대 ─────────────────────────────────────────────────────────────────────


async def create_invitation(
    project_id: str,
    project_name: str,
    invited_email: str,
    invited_by: str,
    invited_by_name: str,
    session: AsyncSession,
) -> dict:
    """초대 생성 + 이메일 발송 (이메일 열거 방지: 항상 201 반환)."""
    from app.config import get_settings

    settings = get_settings()
    expiry_days = settings.smtp_invitation_token_expiry_days
    expires_at = datetime.now(UTC) + timedelta(days=expiry_days)

    # Keystone 사용자 이메일 조회
    keystone_user = await _find_keystone_user_by_email(invited_email)

    # 토큰 생성 + 해시
    plaintext_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()

    status = "pending" if keystone_user else "no_user"
    now = datetime.now(UTC)
    invitation = ProjectInvitation(
        project_id=project_id,
        invited_email=invited_email,
        invited_user_id=keystone_user["id"] if keystone_user else None,
        invited_by=invited_by,
        invited_by_name=invited_by_name,
        token_hash=token_hash,
        status=status,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    session.add(invitation)
    await session.commit()
    await session.refresh(invitation)

    # 이메일 발송 (사용자가 존재할 때만)
    if keystone_user and settings.smtp_enabled:
        from app.services.email_service import send_invitation_email

        frontend_base = settings.frontend_base_url.rstrip("/")
        accept_url = f"{frontend_base}/invitations/{plaintext_token}"
        asyncio.create_task(
            send_invitation_email(
                to_email=invited_email,
                project_name=project_name,
                inviter_name=invited_by_name,
                accept_url=accept_url,
                expires_at=expires_at,
            )
        )

    await activity.record(
        project_id=project_id,
        user_id=invited_by,
        username=invited_by_name,
        resource_type="invitation",
        action="invitation_create",
        status="success",
        resource_id=str(invitation.id),
        extra={"invited_email": invited_email, "has_user": keystone_user is not None},
    )

    return {
        "id": invitation.id,
        "project_id": project_id,
        "invited_email": invited_email,
        "status": status,
        "expires_at": expires_at.isoformat(),
        "created_at": invitation.created_at.isoformat(),
    }


async def accept_invitation(
    plaintext_token: str,
    accepting_user_id: str,
    accepting_email: str,
    session: AsyncSession,
) -> dict:
    """초대 수락 — 이메일 일치 검증 + Keystone role 할당."""
    token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()

    result = await session.execute(select(ProjectInvitation).where(ProjectInvitation.token_hash == token_hash))
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="유효하지 않은 초대 링크입니다")

    if inv.status == "accepted":
        return {"status": "accepted", "project_id": inv.project_id}

    if inv.status in ("declined", "revoked", "expired"):
        raise HTTPException(status_code=410, detail="이미 처리되었거나 만료된 초대입니다")

    now = datetime.now(UTC)
    if inv.expires_at.replace(tzinfo=UTC) < now:
        inv.status = "expired"
        await session.commit()
        raise HTTPException(status_code=410, detail="초대 링크가 만료되었습니다")

    # 이메일 일치 검증
    if inv.invited_email.lower() != accepting_email.lower():
        raise HTTPException(status_code=403, detail="이 초대는 다른 이메일 주소로 발송되었습니다")

    # Keystone role 할당
    try:
        await asyncio.to_thread(_assign_keystone_role_by_name, inv.project_id, accepting_user_id, inv.keystone_role)
    except Exception:
        _logger.error("초대 수락 Keystone role 할당 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="프로젝트 멤버 등록 중 오류가 발생했습니다")

    inv.status = "accepted"
    inv.accepted_at = now
    await session.commit()

    await activity.record(
        project_id=inv.project_id,
        user_id=accepting_user_id,
        username=accepting_email,
        resource_type="invitation",
        action="invitation_accept",
        status="success",
        resource_id=str(inv.id),
    )

    return {"status": "accepted", "project_id": inv.project_id}


async def decline_invitation(plaintext_token: str, session: AsyncSession) -> dict:
    """초대 거절."""
    token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()

    result = await session.execute(select(ProjectInvitation).where(ProjectInvitation.token_hash == token_hash))
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="유효하지 않은 초대 링크입니다")

    if inv.status in ("accepted", "declined", "revoked"):
        return {"status": inv.status}

    inv.status = "declined"
    await session.commit()
    return {"status": "declined"}


def _assign_keystone_role_by_name(project_id: str, user_id: str, role_name: str) -> None:
    """role 이름으로 Keystone role 할당 (keystoneclient admin 크리덴셜 사용)."""
    from app.services import keystone

    ks = keystone._get_admin_ks_client()
    roles = ks.roles.list(name=role_name)
    if not roles:
        raise RuntimeError(f"Keystone role '{role_name}'을 찾을 수 없습니다")
    role_id = roles[0].id
    ks.roles.grant(role_id, user=user_id, project=project_id)


async def _find_keystone_user_by_email(email: str) -> dict | None:
    """이메일로 Keystone 사용자 조회. 미발견 시 None."""
    from app.services import keystone

    def _lookup():
        ks = keystone._get_admin_ks_client()
        users = ks.users.list(email=email)
        if users:
            u = users[0]
            return {"id": u.id, "name": u.name, "email": getattr(u, "email", email)}
        return None

    try:
        return await asyncio.to_thread(_lookup)
    except Exception:
        _logger.warning("Keystone 사용자 이메일 조회 실패 (email=%s)", email, exc_info=True)
        return None


# ─── 초대 정보 공개 조회 ──────────────────────────────────────────────────────


async def get_invitation_info(plaintext_token: str, session: AsyncSession) -> dict:
    """토큰으로 초대 정보 조회 (공개 엔드포인트용)."""
    token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()

    result = await session.execute(select(ProjectInvitation).where(ProjectInvitation.token_hash == token_hash))
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="유효하지 않은 초대 링크입니다")

    # 만료 여부 업데이트
    now = datetime.now(UTC)
    if inv.status == "pending" and inv.expires_at.replace(tzinfo=UTC) < now:
        inv.status = "expired"
        await session.commit()

    # 프로젝트 이름 조회
    project_name = await _get_project_name(inv.project_id)

    return {
        "project_id": inv.project_id,
        "project_name": project_name,
        "inviter_name": inv.invited_by_name,
        "invited_email": inv.invited_email,
        "status": inv.status,
        "expires_at": inv.expires_at.isoformat(),
    }


async def _get_project_name(project_id: str) -> str:
    """Keystone에서 프로젝트 이름 조회."""
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


# ─── 매니저 관리 ──────────────────────────────────────────────────────────────


async def promote_to_manager(
    project_id: str,
    target_user_id: str,
    granted_by: str,
    session: AsyncSession,
) -> None:
    """프로젝트 멤버를 manager로 승격."""
    existing = await session.execute(
        select(ProjectRole).where(
            ProjectRole.project_id == project_id,
            ProjectRole.user_id == target_user_id,
            ProjectRole.role == "manager",
        )
    )
    if existing.scalar_one_or_none():
        return  # 이미 manager

    role = ProjectRole(
        project_id=project_id,
        user_id=target_user_id,
        role="manager",
        granted_by=granted_by,
    )
    session.add(role)
    await session.commit()


async def demote_manager(
    project_id: str,
    target_user_id: str,
    session: AsyncSession,
) -> None:
    """manager 해제 — 마지막 1인 보호."""
    result = await session.execute(
        select(ProjectRole).where(
            ProjectRole.project_id == project_id,
            ProjectRole.role == "manager",
        )
    )
    managers = result.scalars().all()

    if len(managers) <= 1:
        raise HTTPException(status_code=409, detail="프로젝트에는 최소 1명의 관리자가 필요합니다")

    for m in managers:
        if m.user_id == target_user_id:
            await session.delete(m)
            await session.commit()
            return

    raise HTTPException(status_code=404, detail="해당 사용자는 이 프로젝트의 관리자가 아닙니다")
