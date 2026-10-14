"""Native Keystone credential inputs; sensitive values are never metadata."""

import json
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")]


class ApplicationCredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4096)
    role_ids: list[Identifier] = Field(min_length=1, max_length=128)
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def future_expiry(cls, value):
        if value is not None and (value.tzinfo is None or value <= datetime.now(UTC)):
            raise ValueError("Expiry must be a future timezone-aware timestamp")
        return value


class UserCredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: Identifier
    project_id: Identifier | None = None
    type: str = Field(min_length=1, max_length=255)
    blob: str = Field(min_length=1, max_length=65536, repr=False)

    @model_validator(mode="after")
    def ec2_fields(self):
        if self.type == "ec2":
            if not self.project_id:
                raise ValueError("EC2 credentials require a project")
            try:
                json.loads(self.blob)
            except (ValueError, RecursionError):
                raise ValueError("EC2 blob must be a JSON string") from None
        return self


class UserCredentialUpdate(BaseModel):
    """Native PATCH fields are independently optional; nulls are omitted."""

    model_config = ConfigDict(extra="forbid")
    user_id: Identifier | None = None
    project_id: Identifier | None = None
    type: str | None = Field(default=None, min_length=1, max_length=255)
    blob: str | None = Field(default=None, min_length=1, max_length=65536, repr=False)
