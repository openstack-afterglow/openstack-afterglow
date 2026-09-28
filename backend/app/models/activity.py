"""사용자 활동 로그 ORM 모델."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BIGINT, JSON, TEXT, VARCHAR, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    project_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    username: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    resource_type: Mapped[str] = mapped_column(VARCHAR(32), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(VARCHAR(128))
    resource_name: Mapped[str | None] = mapped_column(VARCHAR(255))
    action: Mapped[str] = mapped_column(VARCHAR(48), nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(TEXT)
    request_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    external_id: Mapped[str | None] = mapped_column(VARCHAR(128), unique=True)
    event_type: Mapped[str | None] = mapped_column(VARCHAR(128))
    service: Mapped[str | None] = mapped_column(VARCHAR(32))
    source: Mapped[str | None] = mapped_column(VARCHAR(16))
    page: Mapped[str | None] = mapped_column(VARCHAR(255))
    http_status: Mapped[int | None] = mapped_column()
    extra: Mapped[dict | None] = mapped_column(JSON)

    __table_args__ = (
        Index("idx_activity_project_created", "project_id", "created_at"),
        Index("idx_activity_created_id", "created_at", "id"),
        Index("idx_activity_user_created", "user_id", "created_at"),
        Index("idx_activity_resource", "resource_type", "resource_id"),
    )
