"""Durable issuer/organization identity and one-dispatch native operation fence."""

from datetime import UTC, datetime

from sqlalchemy import VARCHAR, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OrganizationBinding(Base):
    __tablename__ = "organization_bindings"

    binding_key: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    issuer_url: Mapped[str] = mapped_column(VARCHAR(2048), nullable=False)
    external_org_id: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    client_id: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    domain_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True, unique=True)
    creator_user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    intent_id: Mapped[str] = mapped_column(VARCHAR(36), nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
