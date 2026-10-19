"""Durable native ownership mutation fence; never stores credentials."""

from datetime import UTC, datetime

from sqlalchemy import VARCHAR, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProjectOwnershipTransfer(Base):
    __tablename__ = "project_ownership_transfers"

    project_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    id: Mapped[str] = mapped_column(VARCHAR(36), nullable=False, unique=True)
    domain_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    from_user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    to_user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(24), nullable=False)
    stage: Mapped[str] = mapped_column(VARCHAR(24), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
