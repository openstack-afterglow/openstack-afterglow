"""Creation intents, never an authorization or membership cache."""

from datetime import UTC, datetime

from sqlalchemy import BOOLEAN, JSON, VARCHAR, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SharedDomainIntent(Base):
    __tablename__ = "shared_domain_intents"

    kind: Mapped[str] = mapped_column(VARCHAR(16), primary_key=True)
    marker: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(VARCHAR(24), nullable=False)
    domain_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PersonalProjectIntent(Base):
    __tablename__ = "personal_project_intents"

    status: Mapped[str] = mapped_column(VARCHAR(24), nullable=False)
    token_hash: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, index=True)
    identity_domain_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    primary_user_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True, unique=True)
    primary: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=True)
    description: Mapped[str] = mapped_column(VARCHAR(255), nullable=False, default="")
    personal_domain_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    personal_project_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    personal_project_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    project_creation_uncertain: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    added_grants: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    personal_quotas: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AccountIdentityTransfer(Base):
    """Encrypted native association snapshots; never a membership authority."""

    __tablename__ = "account_identity_transfers"

    binding_key: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    status: Mapped[str] = mapped_column(VARCHAR(24), nullable=False)
    source_user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    target_user_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    snapshot_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
