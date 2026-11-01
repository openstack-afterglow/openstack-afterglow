"""Bounded native domain compute-pool policy and request schemas."""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

MAX_AMOUNT = 2_147_483_647
MAX_RESOURCES = 128
MAX_PROJECTS = 10_000
RESOURCE_PATTERN = re.compile(r"^(?:CPU|MEMORY_MB|CUSTOM_PCI_[0-9A-F]{4}_[0-9A-F]{4})$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
Limit = Annotated[int, Field(strict=True, ge=-1, le=MAX_AMOUNT)]
Revision = Annotated[int, Field(strict=True, ge=0, le=MAX_AMOUNT)]


def resource_map(values: dict[str, int]) -> dict[str, int]:
    if any(not RESOURCE_PATTERN.fullmatch(key) for key in values):
        raise ValueError("Only CPU, MEMORY_MB and physical PCI resource classes are supported")
    return values


Limits = Annotated[dict[str, Limit], Field(max_length=MAX_RESOURCES), AfterValidator(resource_map)]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PoolUpdate(StrictBody):
    revision: Revision
    enabled: bool
    limits: Limits


class ProjectLimitsUpdate(StrictBody):
    revision: Revision
    limits: Limits


class NativePoolPolicy(StrictBody):
    schema_version: Literal[1] = Field(alias="schema")
    revision: Revision
    enabled: bool
    limits: Limits
    project_limits: dict[str, Limits] = Field(max_length=MAX_PROJECTS)

    @field_validator("project_limits")
    @classmethod
    def project_identifiers(cls, values):
        if any(not IDENTIFIER_PATTERN.fullmatch(key) for key in values):
            raise ValueError("Invalid native project identifier")
        return values
