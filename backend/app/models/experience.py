"""Separate diagnostic records: observations are never operation authority."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import BIGINT, JSON, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.services.interaction_policy import canonical_page

Feature = Literal[
    "auth",
    "account",
    "mcp",
    "compute",
    "block_storage",
    "file_storage",
    "object_storage",
    "network",
    "container",
    "database",
    "k3s",
    "waygate",
    "lumen",
    "palimpsest",
    "iam",
    "admin",
    "monitoring",
    "settings",
    "activity",
    "docs",
]
Action = Literal[
    "view",
    "load",
    "submit",
    "create",
    "update",
    "delete",
    "start",
    "stop",
    "restart",
    "attach",
    "detach",
    "select",
    "approve",
    "deny",
    "cancel",
    "sign_in",
    "sign_out",
    "refresh",
    "verify",
    "recover",
    "change_password",
    "export",
    "inspect",
    "navigate",
    "open",
    "close",
    "retry",
]
Component = Literal[
    "app.shell",
    "app.navigation",
    "page",
    "resource.list",
    "resource.detail",
    "auth.login",
    "auth.callback",
    "auth.recover",
    "auth.signup",
    "auth.invitation",
    "auth.password",
    "auth.verification",
    "auth.provider",
    "mcp.consent",
    "compute.create",
    "block_storage.create",
    "shared.button",
    "shared.form",
    "shared.field",
    "shared.modal",
    "shared.alert",
    "shared.toast",
    "shared.wizard",
    "shared.table",
    "shared.stream",
    "admin.events",
]
BrowserType = Literal[
    "view.entered",
    "view.state_changed",
    "action.started",
    "validation.rejected",
    "message.presented",
    "result.received",
    "result.applied",
    "result.committed",
    "result.discarded",
    "view.exposure_changed",
    "telemetry.gap",
]
Locale = Literal["ko", "en", "ja", "zh-CN", "sw", "nb", "ms", "vi", "bn", "unknown"]


def uuid_string(value: str) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Canonical UUID required")
    return value


def revision_string(value: str) -> str:
    if value != "unknown" and not re.fullmatch(
        r"(?:[0-9]+\.[0-9]+\.[0-9]+(?:[-+][a-zA-Z0-9.-]+)?|[a-f0-9]{7,64})", value
    ):
        raise ValueError("Source revision required")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    @field_validator("schema_version", "redaction_revision", mode="before", check_fields=False)
    @classmethod
    def strict_revision_number(cls, value):
        if type(value) is not int:
            raise ValueError("Integer schema revision required")
        return value


class EmptyPayload(StrictModel):
    pass


class StatePayload(StrictModel):
    state: Literal["loading", "ready", "empty", "error", "disabled"]
    step: int | None = Field(None, ge=0, le=32)
    access: Literal["none", "read", "manage", "mixed"] | None = None
    selection: Literal["none", "some", "all"] | None = None
    selection_kind: Literal["domain", "project", "home"] | None = None


class ValidationPayload(StrictModel):
    reason: Literal["required", "policy", "format", "quota", "capacity", "authority", "unknown"]


class MessagePayload(StrictModel):
    key: str | None = Field(None, max_length=180)
    locale: Locale
    tone: Literal["neutral", "info", "success", "warning", "danger"]
    restoration: Literal["restored", "redacted", "unavailable"]

    @field_validator("key")
    @classmethod
    def known_key(cls, value, info):
        if value is not None:
            if not re.fullmatch(r"[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+", value):
                raise ValueError("Invalid catalog key")
            from app.services.experience_catalog import is_known_message_key

            if not (info.context or {}).get("retained") and not is_known_message_key(value):
                raise ValueError("Unknown catalog key")
        return value


class ResultPayload(StrictModel):
    request_id: str | None = Field(None, pattern=r"^req-[a-f0-9]{32}$")
    http_status: int | None = Field(None, ge=100, le=599)
    stage: Literal["response", "state", "dom"]
    transport: Literal["network", "cache", "shared"] | None = None
    physical_span_id: str | None = None

    @field_validator("physical_span_id")
    @classmethod
    def physical_uuid(cls, value):
        return uuid_string(value) if value is not None else None


class DiscardPayload(ResultPayload):
    reason: Literal["stale", "aborted", "scope_changed", "unmounted", "unknown"]


class ExposurePayload(StrictModel):
    visibility: Literal["visible", "hidden"]
    focused: bool | None = None


class GapPayload(StrictModel):
    reason: Literal["queue_overflow", "transport_failed", "deadline", "unsupported", "scope_changed"]
    count: int = Field(ge=1, le=2147483647)


PAYLOADS = {
    "view.entered": EmptyPayload,
    "action.started": EmptyPayload,
    "view.state_changed": StatePayload,
    "validation.rejected": ValidationPayload,
    "message.presented": MessagePayload,
    "result.received": ResultPayload,
    "result.applied": ResultPayload,
    "result.committed": ResultPayload,
    "result.discarded": DiscardPayload,
    "view.exposure_changed": ExposurePayload,
    "telemetry.gap": GapPayload,
}


class ExperienceEvent(StrictModel):
    schema_version: Literal[2]
    event_id: str
    event_type: BrowserType
    segment_id: str
    page_view_id: str
    action_id: str | None = None
    caused_by_event_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    client_seq: int = Field(ge=1, le=2147483647)
    client_monotonic_ms: int | float = Field(ge=0, le=604800000, allow_inf_nan=False)
    occurred_at: str = Field(max_length=40)
    route: str = Field(max_length=255)
    feature: Feature
    action: Action
    component: Component
    frontend_build: str = Field(max_length=80)
    catalog_revision: str = Field(max_length=80)
    redaction_revision: Literal[1]
    payload: dict

    @field_validator(
        "event_id",
        "segment_id",
        "page_view_id",
        "action_id",
        "caused_by_event_id",
        "trace_id",
        "span_id",
        "parent_span_id",
    )
    @classmethod
    def canonical_uuid(cls, value):
        return uuid_string(value) if value is not None else None

    @field_validator("route")
    @classmethod
    def safe_route(cls, value):
        if canonical_page(value) != value:
            raise ValueError("Canonical route required")
        return value

    @field_validator("frontend_build", "catalog_revision")
    @classmethod
    def source_revision(cls, value):
        return revision_string(value)

    @field_validator("occurred_at")
    @classmethod
    def aware_time(cls, value):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Timezone required")
        return value

    @model_validator(mode="after")
    def typed_payload(self, info):
        if (
            self.event_type == "view.state_changed"
            and any(key in self.payload for key in ("access", "selection"))
            and (self.feature != "mcp" or self.component != "mcp.consent")
        ):
            raise ValueError("Consent summary is restricted to MCP consent")
        if (
            self.event_type == "view.state_changed"
            and "selection_kind" in self.payload
            and (self.feature != "iam" or self.component != "page" or self.action != "select")
        ):
            raise ValueError("Workspace selection kind is restricted to IAM selection")
        self.payload = (
            PAYLOADS[self.event_type].model_validate(self.payload, context=info.context).model_dump(exclude_none=True)
        )
        return self


class ExperienceBatch(StrictModel):
    schema_version: Literal[2]
    events: list[ExperienceEvent] = Field(min_length=1, max_length=20)


_ID = BIGINT().with_variant(Integer, "sqlite")
_TIME = DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql")


class ExperienceRecord(Base):
    __tablename__ = "experience_events"
    id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    received_at: Mapped[datetime] = mapped_column(_TIME, default=lambda: datetime.now(UTC))
    owner_key: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(String(64))
    project_id: Mapped[str] = mapped_column(String(64))
    segment_id: Mapped[str] = mapped_column(String(36))
    event_id: Mapped[str] = mapped_column(String(36))
    action_id: Mapped[str | None] = mapped_column(String(36))
    source: Mapped[str] = mapped_column(String(16))
    fingerprint: Mapped[str] = mapped_column(String(64))
    catalog_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("experience_catalogs.id", name="fk_experience_event_catalog", ondelete="RESTRICT"),
    )
    data: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("owner_key", "segment_id", "event_id", name="uq_experience_owner_event"),
        Index("ix_experience_scope_segment", "project_id", "segment_id", "id"),
        Index("ix_experience_segment_action", "segment_id", "action_id", "id"),
        Index("ix_experience_retention", "received_at", "id"),
        Index("ix_experience_catalog", "catalog_id"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"},
    )


class ExperienceCatalog(Base):
    __tablename__ = "experience_catalogs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(180))
    locale: Mapped[str] = mapped_column(String(16))
    template: Mapped[str] = mapped_column(Text)
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}


class ExperienceOperationLink(Base):
    __tablename__ = "experience_operation_links"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    operation_id: Mapped[str] = mapped_column(String(128))
    owner_key: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(String(64))
    project_id: Mapped[str] = mapped_column(String(64))
    segment_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(_TIME, default=lambda: datetime.now(UTC))
    context: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        Index("ix_experience_link_retention", "created_at"),
        Index("ix_experience_link_segment", "segment_id"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"},
    )


class ExperienceHold(Base):
    __tablename__ = "experience_holds"
    owner_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    segment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(_TIME, default=lambda: datetime.now(UTC))
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}


class ExperienceMaintenance(Base):
    __tablename__ = "experience_maintenance"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    revision: Mapped[int] = mapped_column(BIGINT)
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}


class ExperienceAggregate(Base):
    __tablename__ = "experience_aggregates"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[datetime] = mapped_column(Date)
    project_id: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16))
    feature: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(48))
    count: Mapped[int] = mapped_column(BIGINT)
    __table_args__ = (
        Index("ix_experience_aggregate_retention", "day"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"},
    )
