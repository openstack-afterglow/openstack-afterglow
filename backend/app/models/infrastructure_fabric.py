"""Protected SNMPv3 configuration and the public physical-fabric wire contract."""

import ipaddress
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

UINT64_MAX = 2**64 - 1
JS_SAFE_MAX = 2**53 - 1
State = Literal["fresh", "stale", "unmeasured", "error"]
Reason = Literal["first_sample", "counter_reset", "collector_reset", "overflow", "stale_sample", "collector_error"]
Rate = Annotated[float, Field(ge=0, le=JS_SAFE_MAX, allow_inf_nan=False)]
Timestamp = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


def canonical_chassis(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", value):
        return value.lower().replace("-", ":")
    return value


class FabricTarget(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=128)
    chassis_id: str = Field(min_length=1, max_length=128)
    management_ip: str = Field(max_length=64)
    port: int = Field(default=161, strict=True, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=32)
    auth_key: SecretStr = Field(min_length=8, max_length=255, repr=False)
    priv_key: SecretStr = Field(min_length=8, max_length=255, repr=False)
    auth_protocol: Literal["sha256", "sha384", "sha512", "sha1"] = "sha256"
    priv_protocol: Literal["aes128"] = "aes128"
    context_name: str = Field(default="", max_length=32)

    @field_validator("auth_key", "priv_key", mode="before")
    @classmethod
    def protect_input(cls, value):
        return SecretStr(value) if isinstance(value, str) else value

    @field_validator("management_ip")
    @classmethod
    def exact_management_ip(cls, value):
        if "%" in value:
            raise ValueError("Scoped management addresses are unsupported")
        address = ipaddress.ip_address(value)
        if address.is_unspecified or address.is_multicast or address.is_loopback or address.is_link_local:
            raise ValueError("Management targets must be literal unicast addresses")
        return str(address)

    _chassis = field_validator("chassis_id")(canonical_chassis)

    @model_validator(mode="after")
    def safe_identity(self):
        for value in (self.chassis_id, self.username, self.name):
            if not value.strip() or any(ord(char) < 32 for char in value):
                raise ValueError("SNMP identities must be nonempty printable strings")
        return self


class FabricSettings(StrictModel):
    # Operator-owned monotonic revision, including empty/disabled configurations.
    revision: int = Field(default=0, strict=True, ge=0, le=JS_SAFE_MAX)
    targets: list[FabricTarget] = Field(default_factory=list, max_length=32)
    poll_interval_seconds: int = Field(default=10, strict=True, ge=5, le=300)
    freshness_seconds: int = Field(default=30, strict=True, ge=5, le=600)
    timeout_seconds: float = Field(default=2, ge=0.1, le=10, allow_inf_nan=False)
    retries: int = Field(default=1, strict=True, ge=0, le=2)
    concurrency: int = Field(default=4, strict=True, ge=1, le=8)
    poll_budget_seconds: int = Field(default=30, strict=True, ge=1, le=120)
    max_ports: int = Field(default=256, strict=True, ge=1, le=1024)
    max_neighbors: int = Field(default=256, strict=True, ge=1, le=1024)
    max_varbinds: int = Field(default=16384, strict=True, ge=256, le=65536)
    retention_seconds: int = Field(default=3600, strict=True, ge=10, le=86400)

    @model_validator(mode="after")
    def bounded_unique_targets(self):
        if self.targets and self.revision == 0:
            raise ValueError("Configured fabric sources require an explicit positive revision")
        for values in (
            [target.id for target in self.targets],
            [target.chassis_id for target in self.targets],
            [(target.management_ip, target.port, target.context_name) for target in self.targets],
        ):
            if len(values) != len(set(values)):
                raise ValueError("Fabric target identities, chassis and endpoints must be unique")
        if self.freshness_seconds < self.poll_interval_seconds:
            raise ValueError("Freshness must cover the polling interval")
        if self.retention_seconds < self.freshness_seconds * 2:
            raise ValueError("Retention must cover two freshness windows")
        return self


class FabricEndpoint(StrictModel):
    kind: Literal["host", "switch"]
    id: str
    port: str


class SwitchPort(StrictModel):
    id: str
    device_id: str
    ifindex: int = Field(ge=1, le=2**31 - 1)
    name: str
    physical: bool | None = Field(default=None, strict=True)
    captured_at: Timestamp | None
    state: State
    operstate: Literal["up", "down", "unknown"]
    window_seconds: float | None = Field(default=None, ge=5, le=600, allow_inf_nan=False)
    rx_packets_per_second: Rate | None = None
    tx_packets_per_second: Rate | None = None
    rx_bytes_per_second: Rate | None = None
    tx_bytes_per_second: Rate | None = None
    measurement: Literal["snmp_if_mib"] = "snmp_if_mib"
    reason: Reason | None = None


class FabricLink(StrictModel):
    id: str
    source: FabricEndpoint
    target: FabricEndpoint
    captured_at: Timestamp
    state: Literal["fresh", "stale", "unmeasured"]
    evidence: Literal["lldp"] = "lldp"
    source_port_id: str | None = None
    target_port_id: str | None = None


class FabricDevice(StrictModel):
    id: str
    name: str
    chassis_id: str
    state: State


class FabricCoverage(StrictModel):
    description: str
    last_observed_at: Timestamp | None
    error: str | None


class FabricSnapshot(StrictModel):
    state: Literal["unconfigured", "available", "partial", "unavailable"]
    generated_at: Timestamp
    devices: list[FabricDevice]
    ports: list[SwitchPort]
    links: list[FabricLink]
    coverage: FabricCoverage


CounterString = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,19})$")]


class PortSample(StrictModel):
    ifindex: int = Field(strict=True, ge=1, le=2**31 - 1)
    name: str = Field(min_length=1, max_length=128)
    mac: str | None = Field(default=None, max_length=128)
    physical: bool | None = Field(default=None, strict=True)
    operstate: Literal["up", "down", "unknown"] = "unknown"
    discontinuity: int | None = Field(default=None, strict=True, ge=0, le=2**32 - 1)
    rx_bytes: CounterString | None = None
    tx_bytes: CounterString | None = None
    rx_packets: CounterString | None = None
    tx_packets: CounterString | None = None

    @field_validator("rx_bytes", "tx_bytes", "rx_packets", "tx_packets")
    @classmethod
    def uint64(cls, value):
        if value is not None and int(value) > UINT64_MAX:
            raise ValueError("Counter exceeds uint64")
        return value


class LocalPort(StrictModel):
    number: int = Field(strict=True, ge=1, le=2**31 - 1)
    subtype: int = Field(strict=True, ge=1, le=7)
    port_id: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=128)


class RemotePort(StrictModel):
    local_port: int = Field(strict=True, ge=1, le=2**31 - 1)
    chassis_id: str = Field(min_length=1, max_length=128)
    port_id: str = Field(min_length=1, max_length=128)
    system_name: str | None = Field(default=None, max_length=128)
    management_addresses: list[str] = Field(default_factory=list, max_length=8)


class DeviceSample(StrictModel):
    captured_at: Timestamp
    uptime: int | None = Field(default=None, strict=True, ge=0, le=2**32 - 1)
    engine_boots: int | None = Field(default=None, strict=True, ge=0, le=2**31 - 1)
    chassis_id: str | None = Field(default=None, max_length=128)
    ports: list[PortSample] = Field(default_factory=list, max_length=1024)
    local_ports: list[LocalPort] = Field(default_factory=list, max_length=1024)
    neighbors: list[RemotePort] = Field(default_factory=list, max_length=1024)
    errors: list[
        Literal[
            "snmp_invalid_response",
            "snmp_missing_counters",
            "snmp_counter_overflow",
            "snmp_missing_lldp",
            "snmp_missing_uptime",
        ]
    ] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def unique_rows(self):
        for values in ([port.ifindex for port in self.ports], [port.number for port in self.local_ports]):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate SNMP table rows")
        return self
