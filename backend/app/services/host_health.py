"""Read-only, direct node-exporter observations, independently collected every 10s.

The configured service account reads Nova inventory; browser callers only read a
shared Redis snapshot. Neither exporter HTTP nor Nova heartbeat proves host-to-host
RPC/data-plane connectivity. No installation, security-group or remote mutation.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import math
import re
import secrets
import socket
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import islice
from typing import Literal

import httpx
from prometheus_client.parser import text_string_to_metric_families
from pydantic import BaseModel, Field

from app.config import get_settings, validate_host_health_address
from app.services.cache import _get_redis

_logger = logging.getLogger(__name__)
INTERVAL_SECONDS = 10
STALE_SECONDS = 30
PROBE_SECONDS = 3
MAX_TARGETS = 64
MAX_PARALLEL = 8
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_STATE_BYTES = 8 * 1024 * 1024
MAX_SAMPLES = 40000
MAX_INTERFACES = 32
HISTORY_SECONDS = 600
MAX_INTERFACE_ADDRESSES = 16
HISTORY_POINTS = 60
LEASE_SECONDS = 30
RENEW_SECONDS = 5
METRICS = ("cpu", "memory", "disk", "network_rx", "network_tx")
Role = Literal["compute", "controller", "storage"]
# Exclude loopback, virtual and stacked interfaces to avoid counting traffic twice
# (bridge + veth/tap, bond/team + physical slaves, VLAN + parent).
_VIRTUAL_INTERFACE = re.compile(
    r"^(?:lo$|docker|veth|virbr|br[-\d]|cni|flannel|cali|tap|tun|qbr|qvb|qvo|qr-|qg-|"
    r"ovs|vxlan|geneve|wg\d|wireguard|bond|team|vlan|dummy|ifb|gre|gretap|ip6|sit|vnet)"
)
_INTERFACE_NAME = re.compile(r"[A-Za-z0-9_.:@-]{1,64}")
_MAC = re.compile(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5,19}")
_OPERSTATES = {"up", "down", "unknown", "dormant", "notpresent", "lowerlayerdown", "testing"}
_CPU_MODES = {"user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"}
_ROOT_FILESYSTEMS = {"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "f2fs", "bcachefs"}
_INTERFACE_COUNTERS = {
    "rx_bytes": "node_network_receive_bytes_total",
    "tx_bytes": "node_network_transmit_bytes_total",
    "rx_packets": "node_network_receive_packets_total",
    "tx_packets": "node_network_transmit_packets_total",
}
_WANTED = {
    "node_cpu_seconds_total",
    "node_memory_MemAvailable_bytes",
    "node_memory_MemTotal_bytes",
    "node_filesystem_avail_bytes",
    "node_filesystem_size_bytes",
    "node_filesystem_readonly",
    "node_filesystem_device_error",
    "node_network_info",
    "node_network_address_info",
    *_INTERFACE_COUNTERS.values(),
}
_RENEW = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""
# Ownership check and publication (snapshot + history + counter baselines) are atomic.
_PUBLISH = """
if redis.call('get', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('set', KEYS[2], ARGV[2], 'EX', ARGV[3])
return 1
"""
_client: httpx.AsyncClient | None = None


class WireModel(BaseModel):
    model_config = {"extra": "forbid", "allow_inf_nan": False}


class MetricPoint(WireModel):
    ts: float
    value: float | None


class HostMetric(WireModel):
    value: float | None = None
    unit: Literal["%", "B/s"]
    series: list[MetricPoint] = Field(default_factory=list, max_length=HISTORY_POINTS)


class ExporterReachability(WireModel):
    status: Literal["up", "down", "unknown"] = "unknown"
    checked_at: str | None = None
    latency_ms: float | None = None
    error: str | None = None


class NovaHeartbeat(WireModel):
    status: Literal["up", "down", "unknown"] = "unknown"
    updated_at: str | None = None
    source: str | None = None


class HostMetrics(WireModel):
    cpu: HostMetric
    memory: HostMetric
    disk: HostMetric
    network_rx: HostMetric
    network_tx: HostMetric


class HostInterface(WireModel):
    """One physical NIC; identity fields are only node_exporter labels."""

    name: str
    mac: str | None = None
    operstate: str | None = None
    # Only from node_exporter --collector.netdev.address-info; null when not exported.
    addresses: list[str] | None = Field(default=None, max_length=MAX_INTERFACE_ADDRESSES)
    rx_bytes_total: float | None = None
    tx_bytes_total: float | None = None
    rx_packets_total: float | None = None
    tx_packets_total: float | None = None
    rx_bytes_per_second: float | None = None
    tx_bytes_per_second: float | None = None
    rx_packets_per_second: float | None = None
    tx_packets_per_second: float | None = None


class HostHealth(WireModel):
    id: str
    name: str
    role: Role
    address: str | None
    reachability: ExporterReachability
    heartbeat: NovaHeartbeat
    metrics: HostMetrics
    metrics_error: str | None = None
    interfaces: list[HostInterface] | None = Field(default=None, max_length=MAX_INTERFACES)
    interfaces_omitted: int | None = None


class HostHealthSnapshot(WireModel):
    enabled: bool
    interval_seconds: Literal[10] = INTERVAL_SECONDS
    collected_at: str | None = None
    stale: bool = True
    error: str | None = None
    hosts: list[HostHealth] = Field(default_factory=list, max_length=MAX_TARGETS)


@dataclass
class Target:
    name: str
    role: str
    address: str | None
    port: int = 9100
    heartbeat: dict = field(default_factory=lambda: NovaHeartbeat().model_dump())
    observed_at: float | None = None

    @property
    def id(self) -> str:
        return f"{self.role}:{self.name.lower()}"


class DiscoveryError(Exception):
    def __init__(self, code: str = "discovery_failed"):
        self.code = code
        super().__init__(code)


class LeaseLost(Exception):
    pass


# The last item is the checked IP actually used as the HTTP destination, not DNS input.
Probe = Callable[[Target], Awaitable[tuple[dict, str | None, float, str | None]]]
Discover = Callable[[], Awaitable[list[Target]]]


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat()


def _timestamp(value) -> float | None:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.replace(tzinfo=result.tzinfo or UTC).timestamp()
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def _keys(settings) -> tuple[str, str]:
    # Separate clouds sharing Redis while every worker of one cloud shares a lease.
    scope = json.dumps([settings.os_auth_url, settings.os_region_name, settings.os_project_name])
    digest = hashlib.sha256(scope.encode()).hexdigest()[:24]
    prefix = f"afterglow:host-health:{{{digest}}}"
    return f"{prefix}:lease", f"{prefix}:snapshot"


def _empty(settings, error: str | None = None) -> dict:
    enabled = settings.monitoring_host_healthcheck_enabled
    return HostHealthSnapshot(enabled=enabled, stale=enabled, error=error).model_dump()


def _field(record, name, default=None):
    return record.get(name, default) if isinstance(record, Mapping) else getattr(record, name, default)


def _heartbeat(services: list) -> dict:
    states, times, sources = [], [], set()
    for service in services:
        sources.add(_field(service, "binary"))
        forced = _field(service, "is_forced_down", _field(service, "forced_down", False))
        states.append("down" if forced is True else _field(service, "state"))
        stamp = _timestamp(_field(service, "updated_at"))
        if stamp is not None:
            times.append(stamp)
    status = "down" if "down" in states else "up" if states and all(s == "up" for s in states) else "unknown"
    # A missing provider timestamp is never replaced by collection time.
    if status == "up" and len(times) != len(services):
        status = "unknown"
    return NovaHeartbeat(
        status=status,
        updated_at=_iso(min(times)) if times else None,
        source=",".join(sorted(sources)) if sources else None,
    ).model_dump()


def discover_from_nova(conn) -> list[Target]:
    """Compute address = exact Nova host_ip; controllers = scheduler/conductor host DNS."""
    services = list(islice(conn.compute.services(), MAX_TARGETS * 4 + 1))
    hypervisors = list(islice(conn.compute.hypervisors(details=True), MAX_TARGETS + 1))
    if len(services) > MAX_TARGETS * 4 or len(hypervisors) > MAX_TARGETS:
        raise DiscoveryError("target_limit")
    groups: dict[tuple[str, str], list] = {}
    for service in services:
        binary = _field(service, "binary")
        if binary not in {"nova-compute", "nova-scheduler", "nova-conductor"}:
            continue
        name = _field(service, "host")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,252}", name):
            raise DiscoveryError()
        role = "compute" if binary == "nova-compute" else "controller"
        groups.setdefault((role, name.lower()), []).append(service)
    addresses: dict[str, set[str]] = {}
    for hypervisor in hypervisors:
        details = _field(hypervisor, "service_details", None) or _field(hypervisor, "service", None) or {}
        name, address = _field(details, "host"), _field(hypervisor, "host_ip")
        if not isinstance(name, str) or not isinstance(address, str):
            continue
        try:
            # Never substitute a display hostname for a missing/unsafe Nova host_ip.
            ipaddress.ip_address(address)
            address = validate_host_health_address(address)
        except ValueError:
            continue
        addresses.setdefault(name.lower(), set()).add(address)
    observed_at = time.time()
    targets = []
    for (role, name), records in sorted(groups.items()):
        host = _field(records[0], "host")
        if role == "compute":
            candidates = addresses.get(name, set())
            address = next(iter(candidates)) if len(candidates) == 1 else None
        else:
            address = host
        targets.append(Target(host, role, address, heartbeat=_heartbeat(records), observed_at=observed_at))
    return targets


def _build_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    """Shipped exporter client policy; tests inject only the transport."""
    return httpx.AsyncClient(
        transport=transport,
        timeout=PROBE_SECONDS,
        trust_env=False,
        follow_redirects=False,
        limits=httpx.Limits(max_connections=MAX_PARALLEL, max_keepalive_connections=MAX_PARALLEL),
        headers={"Accept": "text/plain", "Accept-Encoding": "identity"},
    )


def _http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = _build_client()
    return _client


async def aclose_client() -> None:
    """Close this service's HTTP pool; call after cancelling/awaiting monitoring_loop."""
    global _client
    client, _client = _client, None
    if client is not None:
        await client.aclose()


async def _resolve(address: str, port: int) -> str:
    address = validate_host_health_address(address)
    with suppress(ValueError):
        return str(ipaddress.ip_address(address))
    answers = await asyncio.get_running_loop().getaddrinfo(address, port, type=socket.SOCK_STREAM)
    if not answers or len(answers) > 16:
        raise ValueError("unsafe DNS result")
    # Reject any unsafe answer, not only the one selected for this connection.
    return sorted({validate_host_health_address(answer[4][0]) for answer in answers})[0]


async def probe_exporter(target: Target) -> tuple[dict, str | None, float, str | None]:
    """GET the checked pinned IP once; return reachability, body, time and that IP.

    The configured hostname remains the Host header, never the connection authority.
    No redirect, proxy, authentication, query or response decompression is allowed.
    """
    started = time.monotonic()
    status, error, body, latency = "unknown", None, None, None
    ip = None
    try:
        if target.address is None:
            error = "missing_address"
        else:
            async with asyncio.timeout(PROBE_SECONDS):
                try:
                    ip = await _resolve(target.address, target.port)
                except ValueError:
                    error = "invalid_target"
                except OSError:
                    error = "dns_failed"
                if error is None:
                    authority = f"[{ip}]" if ":" in ip else ip
                    host = f"[{target.address}]" if ":" in target.address else target.address
                    # The checked IP is the URL authority, so HTTPX never re-resolves DNS.
                    url = f"http://{authority}:{target.port}/metrics"
                    headers = {"Host": f"{host}:{target.port}"}
                    async with _http_client().stream("GET", url, headers=headers) as response:
                        status = "up" if response.status_code == 200 else "down"
                        encoding = response.headers.get("content-encoding", "identity").lower()
                        if status == "down":
                            error = "http_status"
                        elif encoding not in {"", "identity"}:
                            error = "unsupported_encoding"
                        else:
                            chunks, size = [], 0
                            async for chunk in response.aiter_raw(chunk_size=65536):
                                size += len(chunk)
                                if size > MAX_BODY_BYTES:
                                    error = "body_too_large"
                                    break
                                chunks.append(chunk)
                            if error is None:
                                try:
                                    body = b"".join(chunks).decode("utf-8")
                                except UnicodeDecodeError:
                                    error = "metrics_invalid"
                    latency = round((time.monotonic() - started) * 1000, 2)
    except (TimeoutError, httpx.TimeoutException):
        status, error, body = "down", "probe_timeout", None
    except httpx.HTTPError:
        status, error, body = "down", "probe_failed", None
    except Exception:
        # Unknown local failure is not evidence that the exporter is down.
        status, error, body, latency = "unknown", "probe_failed", None, None
    checked = time.time()
    reachability = ExporterReachability(status=status, checked_at=_iso(checked), latency_ms=latency, error=error)
    return reachability.model_dump(), body, checked, ip


def _finite(value) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def _ratio(available, total) -> float | None:
    if not _finite(available) or not _finite(total) or total <= 0 or not 0 <= available <= total:
        return None
    return 100 * (1 - available / total)


def _counter_delta(current: dict, previous: dict) -> dict | None:
    if not current or current.keys() != previous.keys():
        return None
    result = {}
    for key, value in current.items():
        old = previous[key]
        if not _finite(value) or not _finite(old) or old < 0 or value < old:
            return None
        result[key] = value - old
    return result


def _rate(current, old, elapsed: float) -> float | None:
    if not _finite(current) or not _finite(old) or old < 0 or current < old or elapsed <= 0:
        return None
    rate = (current - old) / elapsed
    return rate if math.isfinite(rate) else None


def parse_metrics(text: str, previous: dict, stamp: float) -> tuple[dict, dict, list[dict], int]:
    """Return current values, next counter baselines, physical NICs and omitted NIC count.

    CPU excludes guest double-counting; disk is the single writable root
    filesystem. Rates require the same complete series on adjacent scrapes; a
    reset/missing/nonfinite member yields null rather than a masked aggregate.
    """
    samples: dict[str, list] = {name: [] for name in _WANTED}
    count = 0
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            count += 1
            if count > MAX_SAMPLES:
                raise ValueError("too many metrics")
            if sample.name in samples:
                samples[sample.name].append(sample)

    values = dict.fromkeys(METRICS)
    counters: dict = {"at": stamp, "cpu": {}, "network_rx": {}, "network_tx": {}, "interfaces": {}}
    elapsed = stamp - previous.get("at", stamp)
    adjacent = 0 < elapsed <= STALE_SECONDS

    cpu, modes, invalid = {}, {}, False
    for sample in samples["node_cpu_seconds_total"]:
        core, mode = sample.labels.get("cpu"), sample.labels.get("mode")
        if mode in {"guest", "guest_nice"}:
            continue  # Already included in user/nice by the Linux kernel.
        key = f"{core}:{mode}"
        if not core or mode not in _CPU_MODES or key in cpu or not _finite(sample.value) or sample.value < 0:
            invalid = True
            continue
        cpu[key] = sample.value
        modes.setdefault(core, set()).add(mode)
    if not invalid and modes and all({"idle", "user", "system"} <= present for present in modes.values()):
        counters["cpu"] = cpu
    delta = _counter_delta(counters["cpu"], previous.get("cpu", {})) if adjacent else None
    if delta:
        total = sum(delta.values())
        idle = sum(value for key, value in delta.items() if key.rsplit(":", 1)[-1] in {"idle", "iowait"})
        if _finite(total) and total > 0:
            values["cpu"] = _ratio(idle, total)

    def singleton(name):
        group = samples[name]
        return group[0].value if len(group) == 1 and not group[0].labels else None

    values["memory"] = _ratio(singleton("node_memory_MemAvailable_bytes"), singleton("node_memory_MemTotal_bytes"))

    root: dict[str, dict] = {}
    ambiguous = set()
    for name in (
        "node_filesystem_avail_bytes",
        "node_filesystem_size_bytes",
        "node_filesystem_readonly",
        "node_filesystem_device_error",
    ):
        for sample in samples[name]:
            labels = sample.labels
            device = labels.get("device")
            if labels.get("mountpoint") != "/" or labels.get("fstype") not in _ROOT_FILESYSTEMS or not device:
                continue
            group = root.setdefault(device, {})
            if name in group:
                ambiguous.add(device)
            group[name] = sample.value
    if len(root) == 1:
        device, group = next(iter(root.items()))
        writable = group.get("node_filesystem_readonly") == 0 and group.get("node_filesystem_device_error", 0) == 0
        if device not in ambiguous and writable:
            values["disk"] = _ratio(group.get("node_filesystem_avail_bytes"), group.get("node_filesystem_size_bytes"))

    devices: dict[str, dict] = {}
    invalid_devices: set[str] = set()
    omitted: set[str] = set()
    for field_name, metric in _INTERFACE_COUNTERS.items():
        for sample in samples[metric]:
            device = sample.labels.get("device", "")
            if device == "lo":
                continue
            if _VIRTUAL_INTERFACE.match(device) or "." in device:
                omitted.add(device)
                continue
            if not _INTERFACE_NAME.fullmatch(device):
                invalid_devices.add(device)
                continue
            fields = devices.setdefault(device, {})
            if field_name in fields or not _finite(sample.value) or sample.value < 0:
                invalid_devices.add(device)
            fields[field_name] = sample.value
    for metric, field_name in (("network_rx", "rx_bytes"), ("network_tx", "tx_bytes")):
        if invalid_devices or any(field_name not in fields for fields in devices.values()):
            continue  # Unknown aggregate membership: clear baseline, report null.
        counters[metric] = {device: fields[field_name] for device, fields in devices.items()}
        delta = _counter_delta(counters[metric], previous.get(metric, {})) if adjacent else None
        if delta is not None:
            rate = sum(delta.values()) / elapsed
            values[metric] = rate if math.isfinite(rate) else None

    info: dict[str, dict] = {}
    for sample in samples["node_network_info"]:
        device = sample.labels.get("device")
        if device in info:
            info[device] = {}  # Conflicting identity labels are not authoritative.
            continue
        mac = (sample.labels.get("address") or "").lower()
        operstate = (sample.labels.get("operstate") or "").lower()
        info[device] = {
            "mac": mac if _MAC.fullmatch(mac) and mac.strip("0:") else None,
            "operstate": operstate if operstate in _OPERSTATES else None,
        }
    # Present only with node_exporter --collector.netdev.address-info. When absent,
    # addresses are unmeasured (null); when present, a device without one is [].
    address_info = samples["node_network_address_info"]
    addresses: dict[str, set[str]] | None = {} if address_info else None
    for sample in address_info:
        try:
            prefix = f"/{int(sample.labels['netmask'])}" if sample.labels.get("netmask") else ""
            value = str(ipaddress.ip_interface(f"{sample.labels.get('address', '')}{prefix}"))
        except (ValueError, TypeError):
            continue
        addresses.setdefault(sample.labels.get("device"), set()).add(value)
    previous_interfaces = previous.get("interfaces", {}) if adjacent else {}
    names = sorted(set(devices) - invalid_devices)
    interfaces = []
    for device in names[:MAX_INTERFACES]:
        fields = devices[device]
        counters["interfaces"][device] = fields
        old = previous_interfaces.get(device, {})
        identity = info.get(device, {})
        interface = {"name": device, "mac": identity.get("mac"), "operstate": identity.get("operstate")}
        if addresses is not None:
            interface["addresses"] = sorted(addresses.get(device, set()))[:MAX_INTERFACE_ADDRESSES]
        for name in _INTERFACE_COUNTERS:
            interface[f"{name}_total"] = fields.get(name)
            interface[f"{name}_per_second"] = _rate(fields.get(name), old.get(name), elapsed)
        interfaces.append(HostInterface.model_validate(interface).model_dump())
    hidden = len(omitted) + len(invalid_devices) + max(0, len(names) - MAX_INTERFACES)
    return values, counters, interfaces, hidden


def _decode(raw) -> dict | None:
    if raw is None:
        return None
    if len(raw) > MAX_STATE_BYTES:
        raise ValueError("snapshot too large")
    state = json.loads(raw)
    # v2 did not persist pinned destinations; its baselines cannot prove continuity.
    if not isinstance(state, dict) or state.get("version") != 3:
        raise ValueError("unknown snapshot version")
    state["snapshot"] = HostHealthSnapshot.model_validate(state["snapshot"]).model_dump()
    for name in ("counters", "ports", "destinations", "observed"):
        if not isinstance(state.get(name), dict):
            raise ValueError("invalid snapshot state")
    return state


def _clear_current(host: dict, error: str) -> None:
    host["metrics_error"] = error
    for metric in host["metrics"].values():
        metric["value"] = None
    for interface in host["interfaces"] or []:
        for key in list(interface):
            if key not in {"name", "mac"}:
                interface[key] = None


async def get_snapshot(*, settings=None, redis=None, now: float | None = None) -> dict:
    """Read the shared Redis snapshot only; never probes on behalf of a browser."""
    settings = settings or get_settings()
    if not settings.monitoring_host_healthcheck_enabled:
        return _empty(settings)
    try:
        redis = redis if redis is not None else await _get_redis()
        raw = await redis.get(_keys(settings)[1])
    except Exception:
        return _empty(settings, "redis_unavailable")
    try:
        state = _decode(raw)
        if state is None:
            return _empty(settings, "not_collected")
        result = state["snapshot"]
        clock = time.time() if now is None else now
        collected = _timestamp(result["collected_at"])
        stale = collected is None or not 0 <= clock - collected <= STALE_SECONDS
        result["stale"] = stale
        if stale:
            result["error"] = result["error"] or "snapshot_stale"
        for host in result["hosts"]:
            checked = _timestamp(host["reachability"]["checked_at"])
            if stale or checked is None or not 0 <= clock - checked <= STALE_SECONDS:
                host["reachability"].update(status="unknown", latency_ms=None, error="snapshot_stale")
                _clear_current(host, "snapshot_stale")
            observed = state["observed"].get(host["id"])
            if stale or not _finite(observed) or not 0 <= clock - observed <= STALE_SECONDS:
                host["heartbeat"]["status"] = "unknown"
        return HostHealthSnapshot.model_validate(result).model_dump()
    except (ValueError, TypeError, KeyError, AttributeError):
        return _empty(settings, "snapshot_invalid")


class Collector:
    """One owner session. Injectable discover/probe; no production SSRF exemptions."""

    def __init__(
        self,
        settings,
        redis,
        *,
        discover: Discover | None = None,
        probe: Probe | None = None,
        connection_factory=None,
    ):
        self.settings, self.redis = settings, redis
        self.probe = probe or probe_exporter
        self._discover_override = discover
        self._connection_factory = connection_factory
        self._conn = None
        self.lease_key, self.snapshot_key = _keys(settings)
        self.owner = secrets.token_hex(24)
        # Discovery runs beside exporter cycles so a slow Nova/Keystone never delays probes.
        self._targets: list[Target] | None = None
        self._discovered_at: float | None = None
        self._discovery_error: str | None = "discovery_pending"
        self._discovery_attempted = asyncio.Event()

    def _discover_owned(self) -> list[Target]:
        if self._conn is None:
            factory = self._connection_factory
            if factory is None:
                from app.services.keystone import get_admin_project_connection

                factory = get_admin_project_connection
            self._conn = factory()
        try:
            return discover_from_nova(self._conn)
        except Exception:
            self._close_connection()
            raise

    def _close_connection(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            with suppress(Exception):
                conn.close()

    async def _run_sync(self, function):
        # Cancelling to_thread alone would leave the SDK session/job running. Drain
        # the owned API-timeout-bounded job before releasing this worker's lease.
        task = asyncio.create_task(asyncio.to_thread(function))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            with suppress(Exception):
                await task
            raise

    async def discover(self) -> list[Target]:
        if self._discover_override is not None:
            return await self._discover_override()
        return await self._run_sync(self._discover_owned)

    async def refresh_discovery(self) -> None:
        """One Nova read. A failure keeps known identities but never their old heartbeat."""
        try:
            targets = await self.discover()
        except Exception as exc:
            self._discovery_error = exc.code if isinstance(exc, DiscoveryError) else "discovery_failed"
            if self._targets is not None:
                self._targets = [Target(item.name, item.role, item.address, item.port) for item in self._targets]
        else:
            self._targets, self._discovered_at, self._discovery_error = targets, time.time(), None
        finally:
            self._discovery_attempted.set()

    async def _discovery_loop(self) -> None:
        while True:
            await self.refresh_discovery()
            await asyncio.sleep(INTERVAL_SECONDS)

    async def collect(self, previous: dict | None) -> dict:
        """Probe the cached inventory; this never awaits Nova."""
        previous = previous or {
            "snapshot": {"hosts": []},
            "counters": {},
            "ports": {},
            "destinations": {},
            "observed": {},
        }
        prior_hosts = {host["id"]: host for host in previous["snapshot"]["hosts"]}
        error = self._discovery_error
        if self._targets is None:
            # Before a successful discovery, keep probing known exporters without a heartbeat.
            targets = [
                Target(host["name"], host["role"], host["address"], previous["ports"].get(host["id"], 9100))
                for host in prior_hosts.values()
                if host["role"] != "storage"
            ]
        else:
            targets = list(self._targets)
            if error is None and (self._discovered_at is None or time.time() - self._discovered_at > STALE_SECONDS):
                error = "discovery_stale"  # A hung Nova read is reported, not shown as current.
        by_id = {target.id: target for target in targets}
        configured = []
        for override in self.settings.monitoring_host_healthcheck_targets:
            target = Target(override.name, override.role, override.address, override.port)
            discovered = by_id.get(target.id)
            if discovered:
                target.heartbeat, target.observed_at = discovered.heartbeat, discovered.observed_at
            by_id[target.id] = target
            configured.append(target.id)
        # Configured targets have priority; overflow is reported, never hidden as healthy.
        ordered = configured + sorted(set(by_id) - set(configured))
        if len(ordered) > MAX_TARGETS:
            error = "target_limit"
        targets = [by_id[identity] for identity in ordered[:MAX_TARGETS]]
        if not targets and error is None:
            error = "no_hosts"
        semaphore = asyncio.Semaphore(MAX_PARALLEL)

        async def observe(target: Target):
            async with semaphore:
                reachability, body, stamp, destination = await self.probe(target)
            old = prior_hosts.get(target.id, {})
            # DNS names can move between exporters without changing inventory.
            # Unknown destinations never establish continuity with prior evidence.
            same = (
                destination is not None
                and previous["destinations"].get(target.id) == destination
                and old.get("address") == target.address
                and previous["ports"].get(target.id) == target.port
            )
            baseline = previous["counters"].get(target.id, {}) if same else {}
            values, counters, interfaces, omitted = dict.fromkeys(METRICS), {}, None, None
            metrics_error = reachability["error"]
            if body is not None and reachability["status"] == "up":
                try:
                    values, counters, interfaces, omitted = await asyncio.to_thread(
                        parse_metrics, body, baseline, stamp
                    )
                    metrics_error = (
                        None if all(value is not None for value in values.values()) else "metrics_incomplete"
                    )
                except Exception:
                    # One malformed exporter body must not suppress every other host.
                    values, counters, interfaces, omitted = dict.fromkeys(METRICS), {}, None, None
                    metrics_error = "metrics_invalid"
            metrics = {}
            for metric in METRICS:
                history = old.get("metrics", {}).get(metric, {}).get("series", []) if same else []
                history = [point for point in history if stamp - HISTORY_SECONDS <= point["ts"] < stamp]
                metrics[metric] = {
                    "value": values[metric],
                    "unit": "B/s" if metric.startswith("network_") else "%",
                    "series": (history + [{"ts": stamp, "value": values[metric]}])[-HISTORY_POINTS:],
                }
            host = HostHealth(
                id=target.id,
                name=target.name,
                role=target.role,
                address=target.address,
                reachability=reachability,
                heartbeat=target.heartbeat,
                metrics=metrics,
                metrics_error=metrics_error,
                interfaces=interfaces,
                interfaces_omitted=omitted,
            ).model_dump()
            return host, counters, destination

        tasks = [asyncio.create_task(observe(target)) for target in targets]
        try:
            results = await asyncio.gather(*tasks)
        finally:
            # Cancellation or one unexpected failure leaves no orphan probe.
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return {
            "version": 3,
            "snapshot": HostHealthSnapshot(
                enabled=True,
                collected_at=_iso(time.time()),
                stale=False,
                error=error,
                hosts=[host for host, _, _ in results],
            ).model_dump(),
            "counters": {host["id"]: counters for host, counters, _ in results},
            "ports": {target.id: target.port for target in targets},
            "destinations": {host["id"]: destination for host, _, destination in results},
            "observed": {target.id: target.observed_at for target in targets},
        }

    async def _previous(self) -> dict | None:
        raw = await self.redis.get(self.snapshot_key)  # Redis errors end ownership.
        try:
            return _decode(raw)
        except (ValueError, TypeError, KeyError, AttributeError):
            return None  # Corrupt/old state is replaced, not trusted as a baseline.

    async def _renew(self) -> None:
        while True:
            await asyncio.sleep(RENEW_SECONDS)
            if not await self.redis.eval(_RENEW, 1, self.lease_key, self.owner, LEASE_SECONDS):
                raise LeaseLost()

    async def _cycles(self) -> None:
        # Give the first Nova read a short head start, never an unbounded one.
        with suppress(TimeoutError):
            await asyncio.wait_for(self._discovery_attempted.wait(), PROBE_SECONDS)
        while True:
            started = time.monotonic()
            state = await self.collect(await self._previous())
            encoded = json.dumps(state, allow_nan=False, separators=(",", ":"))
            if len(encoded) > MAX_STATE_BYTES:
                raise ValueError("snapshot too large")
            ttl = HISTORY_SECONDS * 2
            if not await self.redis.eval(_PUBLISH, 2, self.lease_key, self.snapshot_key, self.owner, encoded, ttl):
                raise LeaseLost()
            # Sequential: a slow cycle skips elapsed slots instead of overlapping.
            await asyncio.sleep(INTERVAL_SECONDS - ((time.monotonic() - started) % INTERVAL_SECONDS))

    async def run_owned(self) -> None:
        tasks = (
            asyncio.create_task(self._renew()),
            asyncio.create_task(self._discovery_loop()),
            asyncio.create_task(self._cycles()),
        )
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            with suppress(Exception):
                await self._run_sync(self._close_connection)
            with suppress(Exception):
                await self.redis.eval(_RELEASE, 1, self.lease_key, self.owner)


async def monitoring_loop(*, settings=None, redis=None, discover=None, probe=None, connection_factory=None) -> None:
    """Independent, non-overlapping 10s collector; the app cancels and awaits it.

    Only the Redis lease owner collects. Lease/Redis loss cancels its children and
    the atomic owner fence forbids a late former owner publishing or releasing.
    """
    settings = settings or get_settings()
    if not settings.monitoring_host_healthcheck_enabled:
        return
    while True:
        try:
            client = redis if redis is not None else await _get_redis()
            collector = Collector(
                settings, client, discover=discover, probe=probe, connection_factory=connection_factory
            )
            if await client.set(collector.lease_key, collector.owner, nx=True, ex=LEASE_SECONDS):
                await collector.run_owned()
        except Exception:
            # Fixed message only: SDK/HTTP/Redis exceptions can contain credentials.
            _logger.warning("host_health: collection or shared coordination unavailable")
        await asyncio.sleep(INTERVAL_SECONDS)
