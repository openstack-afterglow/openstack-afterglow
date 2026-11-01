"""Durable review records, never an effective compute quota source."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field
from sqlalchemy import VARCHAR, DateTime, Index, Integer
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.compute_pools import MAX_AMOUNT, StrictBody


class CreateGpuQuotaRequest(StrictBody):
    project_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    resource_class: str = Field(pattern=r"^CUSTOM_PCI_[0-9A-F]{4}_[0-9A-F]{4}$")
    additional: int = Field(strict=True, ge=1, le=MAX_AMOUNT)
    reason: str = Field(default="", max_length=2000)


class ResolveGpuQuotaRequest(StrictBody):
    status: Literal["fulfilled", "rejected"]
    note: str = Field(default="", max_length=2000)


class GpuQuotaRequest(Base):
    __tablename__ = "gpu_quota_requests"

    id: Mapped[str] = mapped_column(VARCHAR(32), primary_key=True)
    domain_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    project_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    requester_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    gpu_profile_name: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    resource_class: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    gpu_profile_fingerprint: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    additional: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    target_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    pool_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(VARCHAR(2000), nullable=False, default="")
    status: Mapped[str] = mapped_column(VARCHAR(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql", "mariadb"),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    reviewer_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql", "mariadb"), nullable=True
    )
    note: Mapped[str] = mapped_column(VARCHAR(2000), nullable=False, default="")

    __table_args__ = (
        Index("idx_gpu_request_domain_status", "domain_id", "status", "created_at", "id"),
        Index("idx_gpu_request_domain_created", "domain_id", "created_at", "id"),
        Index("idx_gpu_request_status", "status", "created_at", "id"),
        Index("idx_gpu_request_created", "created_at", "id"),
    )
