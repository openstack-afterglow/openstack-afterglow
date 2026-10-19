"""Durable one-use account proofs; only SHA-256 token digests are persisted."""

from datetime import UTC, datetime

from sqlalchemy import VARCHAR, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AccountRecovery(Base):
    __tablename__ = "account_recoveries"

    token_hash: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    kind: Mapped[str] = mapped_column(VARCHAR(16), nullable=False)
    user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    identity_domain_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    original_email: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    email: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(24), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("idx_account_recovery_user", "user_id", "status"),)
