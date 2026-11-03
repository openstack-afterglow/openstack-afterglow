"""관리자 공지(announcement) 서비스 레이어.

- 관리자 CRUD: DB 미설정/장애 시 AnnouncementStorageUnavailable → 라우터에서 503.
- 사용자 조회: DB 미설정/장애 시 빈 목록/0건으로 graceful degrade (site_branding.py 패턴 준용).
- 타겟팅 판별은 이 파일에서만 수행하며, 호출자가 넘긴 target 필터는 절대 신뢰하지 않는다
  (IDOR 방지 — 항상 서버가 가진 user_id/project_id 기준으로 재계산).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_session_factory, is_db_available, mark_db_unhealthy
from app.models.announcement import Announcement, AnnouncementRead

SEVERITIES: tuple[str, ...] = ("info", "warning", "danger")
TARGET_TYPES: tuple[str, ...] = ("all", "project", "user")

_MAX_TITLE_LEN = 200
_MAX_BODY_LEN = 10_000
# OpenStack/Keystone project_id·user_id는 32자 hex UUID가 일반적이나, 여유를 두고
# 영숫자/하이픈/언더스코어만 허용하는 화이트리스트로 검증한다 (DB 컬럼 폭 VARCHAR(64)와 일치).
_TARGET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class AnnouncementValidationError(ValueError):
    pass


class AnnouncementNotFoundError(LookupError):
    pass


class AnnouncementStorageUnavailable(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def validate_severity(severity: str) -> str:
    if severity not in SEVERITIES:
        raise AnnouncementValidationError(f"지원하지 않는 severity입니다: {severity}. 허용: {', '.join(SEVERITIES)}")
    return severity


def validate_target(target_type: str, target_id: str | None) -> tuple[str, str | None]:
    if target_type not in TARGET_TYPES:
        raise AnnouncementValidationError(
            f"지원하지 않는 target_type입니다: {target_type}. 허용: {', '.join(TARGET_TYPES)}"
        )
    if target_type == "all":
        return target_type, None
    if not target_id or not _TARGET_ID_RE.match(target_id):
        raise AnnouncementValidationError(f"target_type='{target_type}'에는 유효한 target_id가 필요합니다")
    return target_type, target_id


def validate_title(title: str) -> str:
    stripped = title.strip()
    if not stripped:
        raise AnnouncementValidationError("제목은 비어 있을 수 없습니다")
    if len(stripped) > _MAX_TITLE_LEN:
        raise AnnouncementValidationError(f"제목은 {_MAX_TITLE_LEN}자를 초과할 수 없습니다")
    return stripped


def validate_body(body: str) -> str:
    stripped = body.strip()
    if not stripped:
        raise AnnouncementValidationError("본문은 비어 있을 수 없습니다")
    if len(stripped) > _MAX_BODY_LEN:
        raise AnnouncementValidationError(f"본문은 {_MAX_BODY_LEN}자를 초과할 수 없습니다")
    return stripped


def _require_session_factory():
    if not is_db_available():
        raise AnnouncementStorageUnavailable("DB를 사용할 수 없습니다")
    factory = get_session_factory()
    if factory is None:
        raise AnnouncementStorageUnavailable("DB 연결이 초기화되지 않았습니다")
    return factory


def _serialize_admin(a: Announcement) -> dict[str, Any]:
    return {
        "id": a.id,
        "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
        "created_by_user_id": a.created_by_user_id,
        "created_by_username": a.created_by_username,
        "title": a.title,
        "body": a.body,
        "severity": a.severity,
        "target_type": a.target_type,
        "target_id": a.target_id,
        "starts_at": a.starts_at.isoformat() if a.starts_at else None,
        "ends_at": a.ends_at.isoformat() if a.ends_at else None,
        "is_active": a.is_active,
    }


def _serialize_user(a: Announcement, *, is_read: bool) -> dict[str, Any]:
    # 알림함 상세 보기에서 발송자·게시/만료 시각을 표시하기 위해 노출한다.
    # 타겟 정보(target_type/target_id)는 다른 수신자 추론에 쓰일 수 있고,
    # created_by_user_id(Keystone 내부 UUID)는 일반 사용자에게 불필요한
    # 내부 식별자라 노출하지 않는다 — 발송자는 username으로 충분.
    return {
        "id": a.id,
        "created_at": a.created_at.isoformat(),
        "created_by_username": a.created_by_username,
        "title": a.title,
        "body": a.body,
        "severity": a.severity,
        "starts_at": a.starts_at.isoformat() if a.starts_at else None,
        "ends_at": a.ends_at.isoformat() if a.ends_at else None,
        "is_read": is_read,
    }


# ---------------------------------------------------------------------------
# 관리자 CRUD
# ---------------------------------------------------------------------------


async def create_announcement(
    *,
    title: str,
    body: str,
    severity: str,
    target_type: str,
    target_id: str | None,
    starts_at: datetime | None,
    ends_at: datetime | None,
    created_by_user_id: str,
    created_by_username: str,
    send_email: bool = False,
    email_operation_id: str | None = None,
) -> dict[str, Any]:
    title = validate_title(title)
    body = validate_body(body)
    severity = validate_severity(severity)
    target_type, target_id = validate_target(target_type, target_id)
    factory = _require_session_factory()

    row = Announcement(
        created_by_user_id=created_by_user_id,
        created_by_username=created_by_username,
        title=title,
        body=body,
        severity=severity,
        target_type=target_type,
        target_id=target_id,
        starts_at=starts_at,
        ends_at=ends_at,
        is_active=True,
    )
    try:
        if send_email:
            from app.services import mail_delivery

            return await mail_delivery.create_announcement_with_mail(
                row, actor_id=created_by_user_id, operation_id=email_operation_id
            )
        async with factory() as session, session.begin():
            session.add(row)
            await session.flush()
            await session.refresh(row)
            result = _serialize_admin(row)
    except SQLAlchemyError as exc:
        mark_db_unhealthy()
        raise AnnouncementStorageUnavailable("공지를 저장할 수 없습니다") from exc
    return result


async def list_admin_announcements(*, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    factory = _require_session_factory()
    try:
        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(Announcement).order_by(Announcement.created_at.desc()).limit(limit).offset(offset)
                    )
                )
                .scalars()
                .all()
            )
    except SQLAlchemyError as exc:
        mark_db_unhealthy()
        raise AnnouncementStorageUnavailable("공지 목록을 조회할 수 없습니다") from exc
    return [_serialize_admin(row) for row in rows]


async def update_announcement(announcement_id: int, **patch: Any) -> dict[str, Any]:
    factory = _require_session_factory()
    try:
        async with factory() as session, session.begin():
            row = (
                await session.execute(select(Announcement).where(Announcement.id == announcement_id).with_for_update())
            ).scalar_one_or_none()
            if row is None:
                raise AnnouncementNotFoundError(f"공지를 찾을 수 없습니다: {announcement_id}")
            if "title" in patch and patch["title"] is not None:
                row.title = validate_title(patch["title"])
            if "body" in patch and patch["body"] is not None:
                row.body = validate_body(patch["body"])
            if "severity" in patch and patch["severity"] is not None:
                row.severity = validate_severity(patch["severity"])
            if "target_type" in patch and patch["target_type"] is not None:
                target_type, target_id = validate_target(patch["target_type"], patch.get("target_id", row.target_id))
                row.target_type = target_type
                row.target_id = target_id
            if "starts_at" in patch:
                row.starts_at = patch["starts_at"]
            if "ends_at" in patch:
                row.ends_at = patch["ends_at"]
            if "is_active" in patch and patch["is_active"] is not None:
                row.is_active = bool(patch["is_active"])
            from app.services.mail_delivery import cancel_announcement_mail

            await cancel_announcement_mail(session, announcement_id)
            await session.flush()
            await session.refresh(row)
            result = _serialize_admin(row)
    except SQLAlchemyError as exc:
        mark_db_unhealthy()
        raise AnnouncementStorageUnavailable("공지를 수정할 수 없습니다") from exc
    return result


async def delete_announcement(announcement_id: int) -> None:
    factory = _require_session_factory()
    try:
        async with factory() as session, session.begin():
            row = (
                await session.execute(select(Announcement).where(Announcement.id == announcement_id).with_for_update())
            ).scalar_one_or_none()
            if row is None:
                raise AnnouncementNotFoundError(f"공지를 찾을 수 없습니다: {announcement_id}")
            from app.services.mail_delivery import cancel_announcement_mail

            await cancel_announcement_mail(session, announcement_id)
            await session.delete(row)
    except SQLAlchemyError as exc:
        mark_db_unhealthy()
        raise AnnouncementStorageUnavailable("공지를 삭제할 수 없습니다") from exc


# ---------------------------------------------------------------------------
# 사용자 조회/읽음 처리 — 타겟팅은 항상 서버가 계산 (IDOR 방지)
# ---------------------------------------------------------------------------


def _visibility_predicate(*, user_id: str, project_id: str):
    now = _now()
    return and_(
        Announcement.is_active.is_(True),
        or_(Announcement.starts_at.is_(None), Announcement.starts_at <= now),
        or_(Announcement.ends_at.is_(None), Announcement.ends_at >= now),
        or_(
            Announcement.target_type == "all",
            and_(Announcement.target_type == "project", Announcement.target_id == project_id),
            and_(Announcement.target_type == "user", Announcement.target_id == user_id),
        ),
    )


async def list_user_announcements(*, user_id: str, project_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """호출자에게 타겟된 공지만 반환. target 필터는 서버가 user_id/project_id로 직접 계산한다."""
    if not is_db_available():
        return []
    factory = get_session_factory()
    if factory is None:
        return []
    try:
        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(Announcement)
                        .where(_visibility_predicate(user_id=user_id, project_id=project_id))
                        .order_by(Announcement.created_at.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                return []
            read_ids = set(
                (
                    await session.execute(
                        select(AnnouncementRead.announcement_id).where(
                            AnnouncementRead.user_id == user_id,
                            AnnouncementRead.announcement_id.in_([r.id for r in rows]),
                        )
                    )
                )
                .scalars()
                .all()
            )
    except SQLAlchemyError:
        mark_db_unhealthy()
        return []
    return [_serialize_user(row, is_read=row.id in read_ids) for row in rows]


async def count_unread(*, user_id: str, project_id: str) -> int:
    if not is_db_available():
        return 0
    factory = get_session_factory()
    if factory is None:
        return 0
    try:
        async with factory() as session:
            visible_ids = (
                (
                    await session.execute(
                        select(Announcement.id).where(_visibility_predicate(user_id=user_id, project_id=project_id))
                    )
                )
                .scalars()
                .all()
            )
            if not visible_ids:
                return 0
            read_ids = set(
                (
                    await session.execute(
                        select(AnnouncementRead.announcement_id).where(
                            AnnouncementRead.user_id == user_id,
                            AnnouncementRead.announcement_id.in_(visible_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
    except SQLAlchemyError:
        mark_db_unhealthy()
        return 0
    return len({*visible_ids} - read_ids)


async def mark_read(*, announcement_id: int, user_id: str, project_id: str) -> bool:
    """호출자에게 타겟되지 않은 공지면 False (라우터에서 404 처리) — visibility 재검증이 핵심 방어선."""
    if not is_db_available():
        return False
    factory = get_session_factory()
    if factory is None:
        return False
    try:
        async with factory() as session, session.begin():
            visible = (
                await session.execute(
                    select(Announcement.id).where(
                        Announcement.id == announcement_id,
                        _visibility_predicate(user_id=user_id, project_id=project_id),
                    )
                )
            ).scalar_one_or_none()
            if visible is None:
                return False
            existing = (
                await session.execute(
                    select(AnnouncementRead).where(
                        AnnouncementRead.announcement_id == announcement_id,
                        AnnouncementRead.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(AnnouncementRead(announcement_id=announcement_id, user_id=user_id))
    except SQLAlchemyError as exc:
        mark_db_unhealthy()
        raise AnnouncementStorageUnavailable("읽음 처리를 저장할 수 없습니다") from exc
    return True
