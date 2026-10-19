"""Allocation policy and native operation journal; neither stores credentials."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import INT, JSON, VARCHAR, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

QuotaLimit = Annotated[int, Field(strict=True, ge=-1)]


def _known_keys(values: dict[str, int]) -> dict[str, int]:
    from app.services.quota_native import QUOTA_FIELDS

    known = {key for fields in QUOTA_FIELDS.values() for key in fields}
    if set(values) - known:
        raise ValueError("Unknown quota field")
    return values


QuotaMap = Annotated[dict[str, QuotaLimit], AfterValidator(_known_keys)]


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(strict=True, ge=0)
    ceilings: QuotaMap


class DefaultsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(strict=True, ge=0)
    defaults: QuotaMap


class OperationReconcile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    native_calls_settled: bool = Field(strict=True)


class ProjectQuotaUpdate(BaseModel):
    """Flat patch matches the first-party admin quota API, without null resets."""

    model_config = ConfigDict(extra="allow")
    __pydantic_extra__: dict[str, QuotaLimit] = Field(init=False)

    @model_validator(mode="after")
    def known_fields(self):
        if not self.__pydantic_extra__:
            raise ValueError("Supply quota limits")
        _known_keys(self.__pydantic_extra__)
        return self

    def limits(self) -> dict[str, int]:
        return dict(self.__pydantic_extra__ or {})


class DomainQuotaPolicy(Base):
    __tablename__ = "domain_quota_policies"

    domain_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    revision: Mapped[int] = mapped_column(INT, nullable=False, default=0)
    ceilings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    defaults: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class DomainQuotaOperation(Base):
    __tablename__ = "domain_quota_operations"

    id: Mapped[str] = mapped_column(VARCHAR(36), primary_key=True)
    domain_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    project_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(24), nullable=False)
    requested: Mapped[dict] = mapped_column(JSON, nullable=False)
    sections: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("idx_domain_quota_operation_scope", "domain_id", "status"),)
