"""Afterglow-owned MCP control-plane SQLAlchemy models."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    BIGINT,
    BOOLEAN,
    CHAR,
    JSON,
    TEXT,
    VARCHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class McpOwnerLock(Base):
    """Per-user/project serialization row for delegated MCP authority."""

    __tablename__ = "mcp_owner_locks"

    owner_user_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    owner_project_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    lumen_selection_generation: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class McpDelegatedGrant(Base):
    """Server-held delegated authority with an immutable approved-project snapshot."""

    __tablename__ = "mcp_delegated_grants"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid4()))
    owner_user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    owner_project_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    upstream_credential_name: Mapped[str] = mapped_column(VARCHAR(128), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    source: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    access_level: Mapped[str] = mapped_column(VARCHAR(10), nullable=False)
    project_scope: Mapped[str] = mapped_column(VARCHAR(20), nullable=False, default="current", server_default="current")
    approved_projects: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(VARCHAR(10), nullable=False, default="pending")
    application_credential_id: Mapped[str | None] = mapped_column(VARCHAR(128))
    credential_ciphertext: Mapped[str | None] = mapped_column(MEDIUMTEXT)
    credential_epoch: Mapped[int] = mapped_column(BIGINT, nullable=False, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql").with_variant(DATETIME(fsp=6), "mariadb")
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleanup_pending: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    cleanup_last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    orphan_recovery_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    orphan_recovery_nonce: Mapped[str | None] = mapped_column(CHAR(36))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        CheckConstraint("source IN ('personal_token', 'oauth', 'lumen')", name="chk_mcp_grant_source"),
        CheckConstraint("access_level IN ('read', 'manage')", name="chk_mcp_grant_access"),
        CheckConstraint("project_scope IN ('current', 'selected', 'all')", name="chk_mcp_grant_project_scope"),
        CheckConstraint("status IN ('pending', 'active', 'revoked', 'expired')", name="chk_mcp_grant_status"),
        CheckConstraint("expires_at IS NOT NULL OR source = 'personal_token'", name="chk_mcp_grant_expiry"),
        Index("idx_mcp_grants_owner_status", "owner_user_id", "owner_project_id", "status"),
        Index("idx_mcp_grants_expiry", "expires_at", "status"),
    )


class McpProjectCredential(Base):
    """Restricted project credentials beyond the grant's original home credential.

    Rows are reserved before Keystone I/O so ambiguous or partial creation remains
    recoverable by deterministic name. Secrets are bound to grant/user/project.
    """

    __tablename__ = "mcp_project_credentials"

    grant_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("mcp_delegated_grants.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    upstream_credential_name: Mapped[str] = mapped_column(VARCHAR(128), nullable=False, unique=True)
    application_credential_id: Mapped[str | None] = mapped_column(VARCHAR(128))
    credential_ciphertext: Mapped[str | None] = mapped_column(MEDIUMTEXT)
    cleanup_pending: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=True, server_default="1")


class McpPersonalToken(Base):
    """One-time-visible personal MCP token; its plaintext never reaches storage."""

    __tablename__ = "mcp_personal_tokens"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid4()))
    grant_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("mcp_delegated_grants.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    visible_prefix: Mapped[str] = mapped_column(VARCHAR(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("idx_mcp_personal_tokens_grant", "grant_id"),)


class McpLumenSelection(Base):
    """Exactly one selected active personal-token or internal Lumen grant per user/project."""

    __tablename__ = "mcp_lumen_selections"

    owner_user_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    owner_project_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    grant_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("mcp_delegated_grants.id", ondelete="RESTRICT"), nullable=False
    )
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class McpOAuthClient(Base):
    __tablename__ = "mcp_oauth_clients"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid4()))
    client_id: Mapped[str] = mapped_column(VARCHAR(512), nullable=False, unique=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False)
    redirect_uris: Mapped[list] = mapped_column(JSON, nullable=False)
    client_id_issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class McpOAuthAuthorizationRequest(Base):
    __tablename__ = "mcp_oauth_authorization_requests"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid4()))
    ticket_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    client_id: Mapped[str] = mapped_column(VARCHAR(512), nullable=False)
    client_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(VARCHAR(2048), nullable=False)
    resource: Mapped[str] = mapped_column(VARCHAR(2048), nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    code_challenge: Mapped[str] = mapped_column(VARCHAR(256), nullable=False)
    state: Mapped[str | None] = mapped_column(VARCHAR(2048))
    owner_user_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    owner_project_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    grant_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grant_id: Mapped[str | None] = mapped_column(CHAR(36), ForeignKey("mcp_delegated_grants.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(VARCHAR(12), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'denied', 'expired')", name="chk_mcp_oauth_request_status"),
        Index("idx_mcp_oauth_requests_owner", "owner_user_id", "owner_project_id", "status"),
        Index("idx_mcp_oauth_requests_expiry", "expires_at", "status"),
    )


class McpOAuthCode(Base):
    __tablename__ = "mcp_oauth_codes"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid4()))
    code_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    grant_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("mcp_delegated_grants.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(VARCHAR(512), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(VARCHAR(2048), nullable=False)
    resource: Mapped[str] = mapped_column(VARCHAR(2048), nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    code_challenge: Mapped[str] = mapped_column(VARCHAR(256), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class McpOAuthTokenFamily(Base):
    __tablename__ = "mcp_oauth_token_families"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid4()))
    grant_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("mcp_delegated_grants.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    generation: Mapped[int] = mapped_column(BIGINT, nullable=False, default=1)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class McpOAuthToken(Base):
    __tablename__ = "mcp_oauth_tokens"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid4()))
    family_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("mcp_oauth_token_families.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    token_type: Mapped[str] = mapped_column(VARCHAR(10), nullable=False)
    resource: Mapped[str] = mapped_column(VARCHAR(2048), nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    generation: Mapped[int] = mapped_column(BIGINT, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("token_type IN ('access', 'refresh')", name="chk_mcp_oauth_token_type"),
        Index("idx_mcp_oauth_tokens_family", "family_id", "token_type", "generation"),
        Index("idx_mcp_oauth_tokens_expiry", "expires_at", "token_type"),
    )


class McpToolInvocation(Base):
    __tablename__ = "mcp_tool_invocations"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=lambda: str(uuid4()))
    grant_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("mcp_delegated_grants.id", ondelete="RESTRICT"), nullable=False
    )
    source: Mapped[str] = mapped_column(VARCHAR(10), nullable=False)
    tool_name: Mapped[str] = mapped_column(VARCHAR(128), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(VARCHAR(128))
    arguments_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    registry_version: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(24), nullable=False, default="claimed")
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[str | None] = mapped_column(MEDIUMTEXT)
    error: Mapped[str | None] = mapped_column(TEXT)
    resource_ref: Mapped[str | None] = mapped_column(VARCHAR(512))
    operation_ref: Mapped[str | None] = mapped_column(VARCHAR(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        CheckConstraint("source IN ('mcp', 'lumen')", name="chk_mcp_invocation_source"),
        CheckConstraint(
            "status IN ('claimed', 'dispatch_authorized', 'succeeded', 'failed', 'unknown')",
            name="chk_mcp_invocation_status",
        ),
        UniqueConstraint("grant_id", "source", "tool_name", "idempotency_key", name="uq_mcp_invocation_claim"),
        Index("idx_mcp_invocations_grant_created", "grant_id", "created_at"),
    )
