"""Strict resource coordinates; native scheduling specs are never client inputs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.compute import FlavorInfo


class StoredFlavorComposition(BaseModel):
    """Existing native identities/history are immutable, including old odd CPU tuples."""

    model_config = ConfigDict(extra="forbid", strict=True)

    vcpus: int = Field(ge=1, le=128)
    ram_mb: int = Field(ge=1024, le=2097152)
    gpu_profile_id: str | None = Field(default=None, min_length=1, max_length=64)
    gpu_count: int = Field(default=0, ge=0, le=16)

    @field_validator("ram_mb")
    @classmethod
    def memory_step(cls, value):
        if value % 1024:
            raise ValueError("Memory must use whole GiB steps")
        return value

    @model_validator(mode="after")
    def gpu_coordinates(self):
        if (self.gpu_profile_id is None) != (self.gpu_count == 0):
            raise ValueError("GPU count and approved profile must be selected together")
        return self


class FlavorComposition(StoredFlavorComposition):
    """New compositions allow every even CPU quantity, never powers-of-two rounding."""

    vcpus: int = Field(ge=2, le=128, multiple_of=2)


class ComposerProfile(BaseModel):
    id: str
    name: str


class ComposerRange(BaseModel):
    min: int
    max: int
    step: int


class ComposerRegion(BaseModel):
    vcpus: ComposerRange
    ram_mb: ComposerRange


class ComposerVariant(BaseModel):
    gpu_profile_id: str | None
    gpu_count: int
    status: Literal["available", "insufficient", "unavailable"]
    regions: list[ComposerRegion]
    preview: FlavorInfo | None


class ComposerOptions(BaseModel):
    gpu_profiles: list[ComposerProfile]
    variants: list[ComposerVariant]
    checked_at: str
    status: Literal["available", "insufficient", "unavailable"]


class SavedCompositions(BaseModel):
    items: list[FlavorInfo]
