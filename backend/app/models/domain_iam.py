"""One-use email enrollment: domain-bound invitations and global personal signup."""

from datetime import UTC, datetime

from sqlalchemy import BOOLEAN, INT, JSON, VARCHAR, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DomainEnrollment(Base):
    __tablename__ = "domain_enrollments"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(VARCHAR(16), nullable=False)
    domain_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    email: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, unique=True)
    project_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    role_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    invited_by: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    status: Mapped[str] = mapped_column(VARCHAR(24), nullable=False, default="pending")
    user_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    project_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False, default="")
    account_name: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    new_user: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    requested_enabled: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=True)
    creation_uncertain: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    added_role_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    personal_domain_name: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    identity_domain_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    identity_native_name: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    domain_creation_uncertain: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    personal_project_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    personal_domain_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    personal_project_name: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    project_creation_uncertain: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    added_grants: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    personal_quotas: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("idx_domain_enrollment_scope", "domain_id", "kind", "status"),)
