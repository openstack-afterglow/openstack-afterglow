"""Durable domain policy and non-replayable native extension intents."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BOOLEAN, CHAR, JSON, VARCHAR, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def now():
    return datetime.now(UTC)


class InstanceUsagePolicy(Base):
    __tablename__ = "instance_usage_policies"
    cloud_id: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    domain_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    review_required: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    revision: Mapped[str] = mapped_column(CHAR(32), nullable=False)
    updated_by: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)


class InstanceUsageExtensionRequest(Base):
    __tablename__ = "instance_usage_extension_requests"
    id: Mapped[str] = mapped_column(CHAR(32), primary_key=True)
    cloud_id: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    domain_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    project_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    instance_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    instance_name: Mapped[str | None] = mapped_column(VARCHAR(255))
    requested_by: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    schedule_revision: Mapped[str] = mapped_column(CHAR(32), nullable=False)
    policy_revision: Mapped[str] = mapped_column(CHAR(32), nullable=False)
    revision: Mapped[str] = mapped_column(CHAR(32), nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(16), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(VARCHAR(64))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_schedule: Mapped[dict | None] = mapped_column(JSON)
    __mapper_args__ = {"version_id_col": revision, "version_id_generator": False}
    __table_args__ = (
        Index("idx_instance_usage_request_scope", "cloud_id", "domain_id", "project_id", "requested_at"),
        Index("idx_instance_usage_request_target", "cloud_id", "project_id", "instance_id", "status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"},
    )


class UsagePolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_required: bool = Field(strict=True)
    revision: str = Field(pattern=r"^[0-9a-f]{32}$")


class UsageExtensionReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    revision: str = Field(pattern=r"^[0-9a-f]{32}$")
