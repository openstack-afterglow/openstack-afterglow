"""Revisioned future-enrollment policy and credential-free review decisions."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BOOLEAN, INT, JSON, VARCHAR, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.domain_quotas import QuotaMap


class EnrollmentPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(strict=True, ge=0)
    public_signup_enabled: bool = Field(strict=True)
    approval_mode: Literal["auto", "admin"]
    personal_quotas: QuotaMap


class EnrollmentPolicy(Base):
    __tablename__ = "enrollment_policy"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=False)
    revision: Mapped[int] = mapped_column(INT, nullable=False)
    public_signup_enabled: Mapped[bool] = mapped_column(BOOLEAN, nullable=False)
    approval_mode: Mapped[str] = mapped_column(VARCHAR(16), nullable=False)
    personal_quotas: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_by_user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SignupRequest(Base):
    __tablename__ = "signup_requests"

    id: Mapped[str] = mapped_column(VARCHAR(36), primary_key=True)
    source: Mapped[str] = mapped_column(VARCHAR(16), nullable=False)
    identity_hash: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, unique=True)
    binding_hash: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    email: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    domain_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    status: Mapped[str] = mapped_column(VARCHAR(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_by_user_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)

    __table_args__ = (Index("idx_signup_request_status_id", "status", "id"),)
