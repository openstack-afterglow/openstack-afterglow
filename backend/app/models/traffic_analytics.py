"""Opt-in, bounded request analytics. Secrets are independent of user authentication."""

import math
import re
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class TrafficAnalyticsSettings(BaseModel):
    enabled: bool = False
    retention_days: int = Field(30, ge=1, le=30)
    hmac_key: SecretStr = SecretStr("")
    frontend_ingest_key: SecretStr = SecretStr("")
    geoip_csv: str = ""
    site_country: str = Field("", strict=True)

    @field_validator("site_country")
    @classmethod
    def validate_site_country(cls, value: str) -> str:
        if value and (re.fullmatch(r"[A-Z]{2}", value) is None or value == "XX"):
            raise ValueError("site_country must be empty or an uppercase two-letter country code other than XX")
        return value

    @model_validator(mode="after")
    def validate_secrets(self):
        if self.enabled:
            for secret in (self.hmac_key, self.frontend_ingest_key):
                if len(secret.get_secret_value()) < 32:
                    raise ValueError(
                        "enabled traffic analytics requires two independent secrets of at least 32 characters"
                    )
            if self.hmac_key.get_secret_value() == self.frontend_ingest_key.get_secret_value():
                raise ValueError("traffic identity and ingestion secrets must be different")
        return self


ByteCount = Annotated[int, Field(ge=0, le=2**40)]


class TrafficEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    at: float
    status: int = Field(ge=100, le=599)
    route: str = Field(max_length=256)
    client_ip: str | None = Field(None, max_length=64)
    pageview: bool = False
    request_bytes: ByteCount | None = None
    response_bytes: ByteCount | None = None
    latency_ms: float = Field(ge=0, le=86_400_000)
    reporter_dropped_events: int = Field(0, ge=0, le=1_000_000)

    @field_validator("at", "latency_ms")
    @classmethod
    def finite_number(cls, value):
        if not math.isfinite(value):
            raise ValueError("finite measurement required")
        return value

    @field_validator("client_ip")
    @classmethod
    def literal_address(cls, value):
        if value is not None:
            import ipaddress

            return str(ipaddress.ip_address(value))
        return None


class TrafficMetrics(BaseModel):
    requests: int
    success: int
    errors: int
    status_1xx: int
    status_2xx: int
    status_3xx: int
    status_4xx: int
    status_5xx: int
    pageviews: int
    unlocated: int
    request_bytes: int | None
    response_bytes: int | None
    request_bytes_known: int
    response_bytes_known: int
    latency_ms_total: float
    latency_ms_max: float
    unique_visitors: int | None
    visitor_identity_known: int


class TrafficCountry(TrafficMetrics):
    country: str


class TrafficRoute(TrafficMetrics):
    route: str


class TrafficPoint(BaseModel):
    at: int
    metrics: TrafficMetrics | None


class TrafficCoverage(BaseModel):
    description: str
    geo_source: str
    site_country: str | None
    unique_method: str
    dropped_events: int | None
    reporter_dropped_events: int | None
    observed_since: float | None
    last_observed_at: float | None


class TrafficSnapshot(BaseModel):
    state: str
    source: str
    range: str
    retention_days: int
    generated_at: float
    coverage: TrafficCoverage
    totals: TrafficMetrics | None
    countries: list[TrafficCountry]
    routes: list[TrafficRoute]
    series: list[TrafficPoint]
