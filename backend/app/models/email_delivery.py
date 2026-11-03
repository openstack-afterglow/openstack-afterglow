"""Durable outgoing mail intent, immutable recipient bindings and preferences."""

from datetime import UTC, datetime

from sqlalchemy import BIGINT, BOOLEAN, TEXT, VARCHAR, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now():
    return datetime.now(UTC)


_TIMESTAMP = DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql", "mariadb")


class EmailOperation(Base):
    __tablename__ = "email_operations"

    id: Mapped[str] = mapped_column(VARCHAR(32), primary_key=True)
    actor_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    operation_id: Mapped[str] = mapped_column(VARCHAR(36), nullable=False)
    request_hash: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    kind: Mapped[str] = mapped_column(VARCHAR(24), nullable=False)
    announcement_id: Mapped[int | None] = mapped_column(BIGINT)
    audience_pending: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    announcement_fingerprint: Mapped[str | None] = mapped_column(VARCHAR(64))
    notification_activity_id: Mapped[int | None] = mapped_column(BIGINT)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("actor_id", "operation_id", name="uq_email_actor_operation"),
        UniqueConstraint("notification_activity_id", name="uq_email_notification_activity"),
        Index("idx_email_operation_audience", "kind", "audience_pending", "created_at", "id"),
    )


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"

    id: Mapped[str] = mapped_column(VARCHAR(36), primary_key=True)
    operation_key: Mapped[str] = mapped_column(VARCHAR(32), nullable=False)
    operation_id: Mapped[str] = mapped_column(VARCHAR(36), nullable=False)
    kind: Mapped[str] = mapped_column(VARCHAR(24), nullable=False)
    user_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    identity_domain_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    project_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    recipient_email: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    payload_encrypted: Mapped[str] = mapped_column(TEXT, nullable=False)
    message_id: Mapped[str] = mapped_column(VARCHAR(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(VARCHAR(16), nullable=False, default="pending")
    error_code: Mapped[str | None] = mapped_column(VARCHAR(64))
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False, default=_now)
    available_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False, default=_now)

    __table_args__ = (
        Index("idx_email_delivery_pending", "status", "available_at", "id"),
        Index("idx_email_delivery_operation", "operation_key"),
        Index("idx_email_delivery_created", "created_at", "id"),
    )


class EmailPreference(Base):
    __tablename__ = "email_preferences"

    user_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    identity_domain_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    announcements: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=True)
    resource_alerts: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    resource_alerts_enabled_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP)
    updated_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False, default=_now)


class EmailNotificationCursor(Base):
    __tablename__ = "email_notification_cursors"

    name: Mapped[str] = mapped_column(VARCHAR(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    enabled_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False, default=_now)
    scan_after_id: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    scan_until_id: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False, default=_now)
