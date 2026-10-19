"""Per-domain login policy and federated identity-provider persistence.

The Keystone domain ID is the tenant boundary. Provider client secrets are
stored only as domain/provider-bound AEAD ciphertext and never serialized.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import BIGINT, BOOLEAN, CHAR, JSON, TEXT, VARCHAR, CheckConstraint, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class DomainLoginPolicy(Base):
    """Explicitly saved login/signup policy for one Keystone domain.

    Absence of a row means the documented default: password enabled, signup
    disabled and an unrestricted login email allowlist.
    """

    __tablename__ = "domain_login_policies"

    domain_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    password_enabled: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=True)
    allowed_email_domains: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    signup_enabled: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    signup_email_domains: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(BIGINT, nullable=False, default=1)
    updated_by_user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class DomainIdentityProvider(Base):
    """One domain-bound login method. Only a successful native session issuance
    stamps verified_revision; any security edit clears it. Configuration alone
    must never authorize removal of the domain's last proven login method.
    """

    __tablename__ = "domain_identity_providers"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid4()))
    domain_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    name: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    kind: Mapped[str] = mapped_column(VARCHAR(16), nullable=False)
    issuer_url: Mapped[str | None] = mapped_column(VARCHAR(512))
    authorization_url: Mapped[str | None] = mapped_column(VARCHAR(512))
    token_url: Mapped[str | None] = mapped_column(VARCHAR(512))
    api_url: Mapped[str | None] = mapped_column(VARCHAR(512))
    client_id: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    client_secret_ciphertext: Mapped[str] = mapped_column(TEXT, nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    keystone_idp_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    keystone_protocol_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=True)
    revision: Mapped[int] = mapped_column(BIGINT, nullable=False, default=1)
    verified_revision: Mapped[int | None] = mapped_column(BIGINT)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    federation_token_type: Mapped[str] = mapped_column(VARCHAR(16), nullable=False, default="id_token")
    token_endpoint_auth_method: Mapped[str | None] = mapped_column(VARCHAR(32))
    created_by_user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    updated_by_user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("domain_id", "name", name="uq_domain_identity_provider_name"),
        Index("idx_domain_identity_provider_domain", "domain_id", "enabled"),
        CheckConstraint("kind IN ('oidc', 'github')", name="chk_domain_identity_provider_kind"),
    )
