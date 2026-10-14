"""Bounded host-owned observation protocol. No physical link inference."""

import ipaddress
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

HostId = Annotated[str, Field(pattern=r"^(compute|controller|storage):[a-z0-9][a-z0-9_.-]{0,252}$")]
InterfaceName = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_.:@-]+$")]
Counter = Annotated[int, Field(strict=True, ge=0, le=2**64 - 1)]
Timestamp = Annotated[float, Field(gt=0, allow_inf_nan=False)]
SourceState = Literal["measured", "unsupported", "error"]


def literal_ip(value: str) -> str:
    if "%" in value:
        raise ValueError("Scoped addresses are not supported")
    return str(ipaddress.ip_address(value))


def validate_trace_target(value: str) -> str:
    value = literal_ip(value)
    address = ipaddress.ip_address(value)
    if address.is_unspecified or address.is_multicast or address.is_loopback or address.is_link_local:
        raise ValueError("Trace targets must be literal routable unicast addresses")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class HostObserverIdentity(StrictModel):
    host_id: HostId
    token: SecretStr = Field(min_length=32, max_length=256, repr=False)

    @field_validator("token")
    @classmethod
    def token_ascii(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", value.get_secret_value()):
            raise ValueError("Observer token must be 32–256 URL-safe random characters")
        return value


class HostPeerProbeTarget(StrictModel):
    source_host_id: HostId
    target_host_id: HostId
    address: str = Field(max_length=64)
    port: int = Field(default=9100, strict=True, ge=1, le=65535)
    _address = field_validator("address")(validate_trace_target)


class PeerProbe(StrictModel):
    target_host_id: HostId
    address: str = Field(max_length=64)
    port: int = Field(strict=True, ge=1, le=65535)
    status: Literal["up", "down", "unknown"]
    checked_at: Timestamp
    latency_ms: float | None = Field(default=None, ge=0, le=10000, allow_inf_nan=False)
    error: (
        Literal["connection_refused", "timeout", "network_unreachable", "probe_error", "source_unavailable"] | None
    ) = None
    _address = field_validator("address")(validate_trace_target)

    @model_validator(mode="after")
    def honest_status(self):
        if self.status == "up" and (self.latency_ms is None or self.error is not None):
            raise ValueError("Successful probes require latency and no error")
        if self.status != "up" and (self.latency_ms is not None or self.error is None):
            raise ValueError("Unsuccessful probes require an error and unknown latency")
        if self.status == "unknown" and self.error not in {"source_unavailable", "probe_error"}:
            raise ValueError("Unknown means the source could not perform the probe")
        if self.status == "down" and self.error in {"source_unavailable", "probe_error"}:
            raise ValueError("Source or local probe errors are not measured peer failures")
        return self


def validate_topology_settings(settings):
    observers = settings.monitoring_infrastructure_topology_observers
    ids = [item.host_id for item in observers]
    tokens = [item.token.get_secret_value() for item in observers]
    if len(ids) != len(set(ids)) or len(tokens) != len(set(tokens)):
        raise ValueError("Observer identities and tokens must be unique")
    targets = settings.monitoring_infrastructure_topology_trace_targets
    normalized = [validate_trace_target(target) for target in targets]
    if len(normalized) != len(set(normalized)):
        raise ValueError("Trace targets must be unique")
    settings.monitoring_infrastructure_topology_trace_targets = normalized
    peers = settings.monitoring_infrastructure_topology_peer_targets
    pairs = set()
    for peer in peers:
        pair = (peer.source_host_id, peer.target_host_id)
        if peer.source_host_id not in ids or peer.source_host_id == peer.target_host_id:
            raise ValueError("Peer probes require an observer source and a different target host")
        if pair in pairs:
            raise ValueError("Directed peer host pairs must be unique")
        pairs.add(pair)
    return settings


class Interface(StrictModel):
    name: InterfaceName
    mac: str | None = Field(default=None, max_length=64)
    operstate: str = Field(default="UNKNOWN", max_length=24)
    addresses: list[str] = Field(default_factory=list, max_length=32)
    rx_bytes: Counter | None = None
    tx_bytes: Counter | None = None
    rx_packets: Counter | None = None
    tx_packets: Counter | None = None
    ifindex: int | None = Field(default=None, ge=1)

    @field_validator("addresses")
    @classmethod
    def valid_addresses(cls, values):
        return [str(ipaddress.ip_interface(value)) for value in values]


class Neighbor(StrictModel):
    interface: InterfaceName
    ip: str = Field(max_length=64)
    mac: str | None = Field(default=None, max_length=64)
    state: str = Field(max_length=32)
    _ip = field_validator("ip")(literal_ip)


class Route(StrictModel):
    interface: InterfaceName
    destination: str = Field(max_length=64)
    gateway: str | None = Field(default=None, max_length=64)
    metric: int | None = Field(default=None, ge=0, le=2**32 - 1)

    @field_validator("destination")
    @classmethod
    def network(cls, value):
        return value if value == "default" else str(ipaddress.ip_network(value, strict=False))

    @field_validator("gateway")
    @classmethod
    def gateway_ip(cls, value):
        return literal_ip(value) if value is not None else None


class Lldp(StrictModel):
    interface: InterfaceName
    chassis_id: str = Field(min_length=1, max_length=128)
    port_id: str = Field(min_length=1, max_length=128)
    system_name: str | None = Field(default=None, max_length=128)


class Sources(StrictModel):
    addresses: SourceState
    neighbors: SourceState
    routes: SourceState
    lldp: SourceState
    counters: SourceState
    peer_probes: SourceState = "unsupported"


class Observation(StrictModel):
    captured_at: Timestamp
    boot_id: str = Field(min_length=1, max_length=64)
    interfaces: list[Interface] = Field(max_length=64)
    # Lower-priority (for example per-VM tap/qvo) interfaces beyond the cap are
    # counted, never silently treated as a complete inventory.
    interfaces_omitted: int = Field(default=0, strict=True, ge=0, le=65536)
    evidence_omitted: int = Field(default=0, strict=True, ge=0, le=1_000_000)
    neighbors: list[Neighbor] = Field(max_length=256)
    routes: list[Route] = Field(max_length=256)
    lldp: list[Lldp] = Field(max_length=128)
    peer_probes: list[PeerProbe] = Field(default_factory=list, max_length=64)
    sources: Sources

    @model_validator(mode="after")
    def interface_ownership(self):
        names = {item.name for item in self.interfaces}
        if len(names) != len(self.interfaces):
            raise ValueError("Interface names must be unique")
        if any(item.interface not in names for item in [*self.neighbors, *self.routes, *self.lldp]):
            raise ValueError("Evidence must reference a reported interface")
        for source, evidence in (("neighbors", self.neighbors), ("routes", self.routes), ("lldp", self.lldp)):
            if getattr(self.sources, source) == "unsupported" and evidence:
                raise ValueError("Unsupported sources cannot publish measured evidence")
        pairs = [(probe.target_host_id, probe.address, probe.port) for probe in self.peer_probes]
        if len(pairs) != len(set(pairs)):
            raise ValueError("Peer probe tuples must be unique")
        return self


class TraceRequest(StrictModel):
    target: str = Field(max_length=64)
    _target = field_validator("target")(validate_trace_target)


class Hop(StrictModel):
    hop: int = Field(strict=True, ge=1, le=16)
    ip: str | None = Field(default=None, max_length=64)
    rtt_ms: float | None = Field(default=None, ge=0, le=60000, allow_inf_nan=False)

    @field_validator("ip")
    @classmethod
    def hop_ip(cls, value):
        return literal_ip(value) if value is not None else None

    @model_validator(mode="after")
    def unknown_rtt(self):
        if self.ip is None and self.rtt_ms is not None:
            raise ValueError("Unknown hops cannot have RTT")
        return self


class TraceResult(StrictModel):
    status: Literal["complete", "unsupported", "error"]
    hops: list[Hop] = Field(max_length=16)
    reached: bool
    error: (
        Literal["traceroute_missing", "local_target_denied", "command_failed", "timeout", "route_unavailable"] | None
    ) = None
    source_interface: InterfaceName | None = None
    next_hop: str | None = Field(default=None, max_length=64)
    completed_at: Timestamp

    @field_validator("next_hop")
    @classmethod
    def next_hop_ip(cls, value):
        return literal_ip(value) if value is not None else None

    @model_validator(mode="after")
    def ordered_hops(self):
        if [hop.hop for hop in self.hops] != list(range(1, len(self.hops) + 1)):
            raise ValueError("Every hop including unknown gaps must be represented in order")
        if self.reached and (self.status != "complete" or not self.hops):
            raise ValueError("Only completed measured paths can reach a target")
        if self.status == "unsupported" and (self.hops or self.reached):
            raise ValueError("Unsupported paths have no measured hops")
        return self
