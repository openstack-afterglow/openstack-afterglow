"""Public validation for schedules whose sole authority is Nova metadata."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

UsageAction = Literal["shelve", "delete"]
UsageState = Literal[
    "active",
    "blocked",
    "shelve_requested",
    "offload_requested",
    "stop_requested",
    "volume_flags_requested",
    "volumes_ready",
    "delete_requested",
    "complete",
    "unknown",
]
REVISION_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def metadata_text(value: str, *, trim: bool = False) -> str:
    """Nova limits individual metadata values in bytes, not Unicode characters."""
    if not isinstance(value, str):
        raise ValueError("Metadata values must be strings")
    if any(unicodedata.category(char) in {"Cc", "Cs"} for char in value):
        raise ValueError("Control characters are not permitted")
    value = value.strip() if trim else value
    if len(value.encode("utf-8")) > 255:
        raise ValueError("Value must not exceed 255 UTF-8 bytes")
    return value


def aware_timestamp(value):
    if not isinstance(value, (str, datetime)):
        raise ValueError("Timestamp must be a timezone-aware ISO datetime")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return parsed.astimezone(UTC)


class UsageScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_at: AwareDatetime | None = None
    expiry_action: UsageAction = "shelve"
    delete_volumes: bool = Field(default=False, strict=True)
    reason: str = Field(default="", strict=True)

    @field_validator("expires_at", mode="before")
    @classmethod
    def timestamp(cls, value):
        return None if value is None else aware_timestamp(value).replace(microsecond=0)

    @field_validator("reason")
    @classmethod
    def reason_bytes(cls, value: str) -> str:
        return metadata_text(value, trim=True)

    @model_validator(mode="after")
    def explicit_deletion_action(self):
        if self.delete_volumes and self.expiry_action != "delete":
            raise ValueError("Volume deletion requires the delete expiry action")
        return self


class UsageScheduleUpdate(UsageScheduleRequest):
    revision: str = Field(strict=True)

    @field_validator("revision")
    @classmethod
    def revision_token(cls, value: str) -> str:
        if not REVISION_PATTERN.fullmatch(value):
            raise ValueError("Invalid schedule revision")
        return value


class UsageScheduleExtension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_at: AwareDatetime
    reason: str = Field(strict=True)
    revision: str = Field(strict=True)

    @field_validator("expires_at", mode="before")
    @classmethod
    def timestamp(cls, value):
        return aware_timestamp(value).replace(microsecond=0)

    @field_validator("reason")
    @classmethod
    def reason_bytes(cls, value: str) -> str:
        value = metadata_text(value, trim=True)
        if not value:
            raise ValueError("An extension requires a reason")
        return value

    @field_validator("revision")
    @classmethod
    def revision_token(cls, value: str) -> str:
        if not REVISION_PATTERN.fullmatch(value):
            raise ValueError("Invalid schedule revision")
        return value


class UsageScheduleInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str = Field(strict=True, min_length=1)
    starts_at: str
    expires_at: str
    expiry_action: UsageAction
    delete_volumes: bool = Field(strict=True)
    reason: str
    revision: str
    state: UsageState
    source: Literal["created", "adopted"]
    last_error: str | None = None
    extended_at: str | None = None
    extended_by: str | None = None
    instance_name: str | None = None
    server_name: str | None = None

    @field_validator("starts_at", "expires_at", "extended_at")
    @classmethod
    def utc_timestamp(cls, value):
        return None if value is None else aware_timestamp(value).isoformat()

    @field_validator("reason", "last_error", "extended_by")
    @classmethod
    def bounded_text(cls, value):
        return None if value is None else metadata_text(value)

    @field_validator("revision")
    @classmethod
    def revision_token(cls, value):
        if not REVISION_PATTERN.fullmatch(value):
            raise ValueError("Invalid schedule revision")
        return value

    @model_validator(mode="after")
    def consistent_schedule(self):
        if aware_timestamp(self.expires_at) <= aware_timestamp(self.starts_at):
            raise ValueError("Expiry must follow schedule enrollment")
        if self.delete_volumes and self.expiry_action != "delete":
            raise ValueError("Invalid native volume deletion consent")
        if self.state in {"shelve_requested", "offload_requested"} and self.expiry_action != "shelve":
            raise ValueError("Shelve operation contradicts expiry action")
        if (
            self.state
            in {
                "stop_requested",
                "volume_flags_requested",
                "volumes_ready",
                "delete_requested",
            }
            and self.expiry_action != "delete"
        ):
            raise ValueError("Delete operation contradicts expiry action")
        if bool(self.extended_at) != bool(self.extended_by):
            raise ValueError("Incomplete native extension attribution")
        if self.extended_at and aware_timestamp(self.extended_at) < aware_timestamp(self.starts_at):
            raise ValueError("Extension precedes schedule enrollment")
        if self.extended_at and (not self.reason or self.extended_by != self.extended_by.strip()):
            raise ValueError("Native extension reason and actor must be present")
        if self.reason != self.reason.strip():
            raise ValueError("Native schedule reason must be trimmed")
        return self
