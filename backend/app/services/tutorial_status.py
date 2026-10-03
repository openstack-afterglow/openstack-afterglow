"""사용자별 튜토리얼(투어) 진행 이력 서비스 레이어.

- 조회: DB 미설정/장애 시 빈 dict 로 graceful degrade(announcements.py 사용자 조회 패턴 준용).
- 기록(upsert): DB 미설정/장애 시 TutorialStorageUnavailable → 라우터에서 503.
- user_id 는 라우터가 token_info 로 계산해 넘기며, 이 파일은 클라이언트 입력을 신뢰하지 않는다.
- tour_id / status 는 화이트리스트로 검증한다(임의 값 저장 방지).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_session_factory, is_db_available, mark_db_unhealthy
from app.models.db import UserTutorialStatus

# 프론트엔드 TourId 와 동기화(frontend/src/lib/tutorial/tours.ts).
TOUR_IDS: tuple[str, ...] = (
    "vm-create",
    "volume",
    "drover",
    "waygate",
    "admin-compute",
    "admin-storage",
    "admin-library",
    "admin-waygate",
    "admin-network",
    "admin-containers",
    "admin-key-manager",
    "admin-monitoring",
    "admin-system",
    "admin-identity",
)
STATUSES: tuple[str, ...] = ("completed", "dismissed")


class TutorialValidationError(ValueError):
    pass


class TutorialStorageUnavailable(RuntimeError):
    pass


def validate_tour_id(tour_id: str) -> str:
    if tour_id not in TOUR_IDS:
        raise TutorialValidationError(f"지원하지 않는 tour_id입니다: {tour_id}")
    return tour_id


def validate_status(status: str) -> str:
    if status not in STATUSES:
        raise TutorialValidationError(f"지원하지 않는 status입니다: {status}. 허용: {', '.join(STATUSES)}")
    return status


async def get_user_statuses(user_id: str) -> dict[str, str]:
    """{tour_id: status} 맵을 반환. 기록이 없는 투어는 키에 포함되지 않는다(→ 프론트에서 강조)."""
    if not user_id or not is_db_available():
        return {}
    factory = get_session_factory()
    if factory is None:
        return {}
    try:
        async with factory() as session:
            result = await session.execute(
                select(UserTutorialStatus.tour_id, UserTutorialStatus.status).where(
                    UserTutorialStatus.user_id == user_id
                )
            )
            return {tour_id: status for tour_id, status in result.all()}
    except SQLAlchemyError:
        mark_db_unhealthy()
        return {}


async def set_status(*, user_id: str, tour_id: str, status: str) -> None:
    """사용자·투어별 상태를 upsert. 검증 실패는 TutorialValidationError, DB 문제는 TutorialStorageUnavailable."""
    if not user_id:
        raise TutorialStorageUnavailable("사용자 식별자가 없습니다")
    validate_tour_id(tour_id)
    validate_status(status)
    if not is_db_available():
        raise TutorialStorageUnavailable("DB를 사용할 수 없습니다")
    factory = get_session_factory()
    if factory is None:
        raise TutorialStorageUnavailable("DB 연결이 초기화되지 않았습니다")
    try:
        async with factory() as session:
            existing = await session.execute(
                select(UserTutorialStatus).where(
                    UserTutorialStatus.user_id == user_id,
                    UserTutorialStatus.tour_id == tour_id,
                )
            )
            row = existing.scalar_one_or_none()
            if row is None:
                session.add(UserTutorialStatus(user_id=user_id, tour_id=tour_id, status=status))
            else:
                row.status = status
            await session.commit()
    except SQLAlchemyError as exc:
        mark_db_unhealthy()
        raise TutorialStorageUnavailable("튜토리얼 상태를 저장할 수 없습니다") from exc
