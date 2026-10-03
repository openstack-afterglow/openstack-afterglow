"""Read-only same-host flavor capacity projection from Nova and Placement.

The result is an advisory snapshot: nothing is reserved and the Nova scheduler
remains the final allocator. Placement answers one allocation-candidates query per
flavor *shape* (CPU resource class, explicit resources, traits and one request group
per PCI device) asking for one CPU unit and one MiB. Each flavor's own CPU/RAM is
then fitted on the same candidate compute root with that response's provider
summaries and the supplier inventory ``max_unit``, so CPU, RAM and GPUs are never
combined across hosts and the reported pair is the most one VM can get on one host.
Single-cell NUMA requests are evaluated on host totals, a necessary condition for
any cell fit, and flagged ``numa_unverified``. Flavor semantics this projection
cannot bound, ambiguous mappings, unknown resource classes and failed, slow or
malformed authority responses produce ``unavailable``. Responses carry no host,
provider or tenant identifiers.

Cost bounds: one process-wide operator session is reused and discarded after a
snapshot-level failure; every request has a short timeout without retries; one
evaluation has an overall deadline; discovery callers share a short-lived
single-flight snapshot while create admission always reads fresh.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.models.compute import FlavorCapacityInfo, FlavorInfo
from app.services import gpu_inventory, keystone

_logger = logging.getLogger(__name__)

_COMPUTE_VERSION = "compute 2.53"
_PLACEMENT_VERSION = "placement 1.36"
_HYPERVISOR_PAGE_LIMIT = 1000
_MAX_HYPERVISOR_PAGES = 100
_MAX_PCI_DEVICES = 16
# One evaluation never outlives these bounds; discovery lists reuse a snapshot for the TTL.
_REQUEST_TIMEOUT_SECONDS = 5.0
_DEADLINE_SECONDS = 15.0
_SNAPSHOT_TTL_SECONDS = 10.0

_MEMORY = "MEMORY_MB"
_VCPU = "VCPU"
_PCPU = "PCPU"
_EXPLICIT_GPU_CLASSES = frozenset({"VGPU"})
_DISABLED_TRAIT = "COMPUTE_STATUS_DISABLED"
_HYPERTHREADING_TRAIT = "HW_CPU_HYPERTHREADING"
_TENANT_KEY_PREFIX = "filter_tenant_id"

_NAME_RE = re.compile(r"^[A-Z0-9_]{1,255}$")
_PCI_ID_RE = re.compile(r"^[0-9A-F]{4}$")
_COUNT_RE = re.compile(r"^[0-9]{1,9}$")
_GROUPED_KEY_RE = re.compile(r"^(?:resources|trait)[^:]+:")
_SPEC_OPERATORS = frozenset(
    {"=", "==", "!=", ">=", "<=", "<in>", "<all-in>", "<or>", "s==", "s!=", "s<", "s<=", "s>", "s>="}
)
# Scopes ignored by Placement and by Nova's capability/aggregate filters.
_IGNORED_SCOPES = frozenset({"", "afterglow", "quota", "os", "hw_rng", "hw_video"})
# hw: keys that change neither the Placement request nor NUMA cell fitting.
_NEUTRAL_HW_KEYS = frozenset(
    {
        "boot_menu",
        "cpu_cores",
        "cpu_max_cores",
        "cpu_max_sockets",
        "cpu_max_threads",
        "cpu_sockets",
        "cpu_threads",
        "hide_hypervisor_id",
        "pmu",
        "serial_port_count",
        "vif_multiqueue_enabled",
        "watchdog_action",
    }
)
# Page sizes whose single-cell fit stays bounded by host memory; hugepage pools are invisible to Placement.
_BOUNDED_PAGE_SIZES = frozenset({"small", "any"})
_CAPABILITY_FIELD_RE = re.compile(r"^[A-Za-z0-9_]+$")


class _Unsupported(ValueError):
    """Flavor semantics this projection cannot represent faithfully."""


class _UnknownAlias(_Unsupported):
    """A PCI alias absent from the GPU catalog (may be fixed by a catalog refresh)."""


class _AuthorityError(RuntimeError):
    """A Nova or Placement response that cannot be trusted, or an exhausted deadline."""


class _CachedShapeFailure(_AuthorityError):
    """A shape that already failed (and was logged) in this snapshot."""


@dataclass(frozen=True)
class _Shape:
    """Placement-visible part of a flavor; all flavors of one shape share one query.

    CPU and RAM are requested as one unit each. Nova reports ``min_unit`` and
    ``step_size`` 1 for VCPU, PCPU and MEMORY_MB inventories (its resource tracker
    rewrites them), so this relaxed query drops no root that a flavor's real amounts
    could use; those amounts are fitted locally per candidate.
    """

    cpu_class: str
    extra: tuple[tuple[str, int], ...]
    required: tuple[str, ...]
    forbidden: tuple[str, ...]
    pci_groups: tuple[str, ...]
    group_policy: str | None

    def expected(self) -> dict[str, int]:
        totals = {self.cpu_class: 1, _MEMORY: 1}
        for resource_class, amount in self.extra:
            totals[resource_class] = totals.get(resource_class, 0) + amount
        for resource_class in self.pci_groups:
            totals[resource_class] = totals.get(resource_class, 0) + 1
        return totals

    def custom_classes(self) -> frozenset[str]:
        return frozenset([*self.pci_groups, *(rc for rc, _ in self.extra if rc.startswith("CUSTOM_"))])

    def query(self) -> list[tuple[str, str]]:
        """Nova-equivalent allocation candidate query: one numbered group per PCI device."""
        resources = [(self.cpu_class, 1), (_MEMORY, 1), *self.extra]
        params = [("resources", ",".join(f"{rc}:{amount}" for rc, amount in resources))]
        traits = [*self.required, *(f"!{trait}" for trait in self.forbidden)]
        if traits:
            params.append(("required", ",".join(traits)))
        for index, resource_class in enumerate(self.pci_groups):
            params.append((f"resources_PCI{index}", f"{resource_class}:1"))
        if self.pci_groups:
            params.append(("group_policy", self.group_policy or "none"))
        params.append(("root_required", f"!{_DISABLED_TRAIT}"))
        return params


@dataclass(frozen=True)
class _Demand:
    """One flavor's single-VM request: a Placement shape plus local CPU/RAM amounts and host filters."""

    shape: _Shape
    cpu: int
    ram: int
    aggregate_specs: tuple[tuple[str, str], ...]
    # Exact ComputeCapabilitiesFilter matches against the hypervisor's top-level cpu_info fields.
    capability_specs: tuple[tuple[str, str], ...]
    numa_unverified: bool


@dataclass(frozen=True)
class _Host:
    state: str  # "eligible" | "ineligible" | "unknown"
    metadata: dict[str, frozenset[str]]
    cpu_info: dict | None = None


class _AliasCatalog:
    """Maps a Nova PCI alias to Nova's default CUSTOM_PCI_<VENDOR>_<PRODUCT> class.

    Catalogs (defaults, afterglow.conf/config.gpu.toml, DB overlay) usually list a GPU's HDMI audio
    function by name only ("GA102 Audio"), while flavors request it as "<chip>-audio"; audio functions
    therefore also match on their normalized device name. GPU names are not indexed this way.
    """

    def __init__(self) -> None:
        self._exact: dict[str, set[tuple[str, str]]] = {}
        self._normalized: dict[str, set[tuple[str, str]]] = {}
        self._devices: dict[tuple[str, str], dict] = {}
        self._name_map = gpu_inventory.build_alias_to_device_name_map()
        for vendor_id, devices in gpu_inventory.PCI_DEVICE_MAP.items():
            for device_id, info in devices.items():
                key = (str(vendor_id).upper(), str(device_id).upper())
                self._devices[key] = info
                for alias in info.get("aliases") or []:
                    if not alias:
                        continue
                    self._exact.setdefault(str(alias), set()).add(key)
                    normalized = gpu_inventory._normalize_alias_value(str(alias))
                    self._normalized.setdefault(normalized, set()).add(key)
                if info.get("is_audio") and info.get("name"):
                    normalized = gpu_inventory._normalize_alias_value(str(info["name"]))
                    self._normalized.setdefault(normalized, set()).add(key)

    def resource_class(self, alias: str) -> str:
        keys = self._exact.get(alias) or self._normalized.get(gpu_inventory._normalize_alias_value(alias), set())
        if not keys:
            raise _UnknownAlias(f"PCI alias {alias!r} is not in the GPU catalog")
        if len(keys) != 1:
            raise _Unsupported(f"PCI alias {alias!r} maps to several devices")
        ((vendor_id, device_id),) = keys
        if not (_PCI_ID_RE.match(vendor_id) and _PCI_ID_RE.match(device_id)):
            raise _Unsupported(f"PCI alias {alias!r} maps to an unrepresentable device id")
        info = self._devices[(vendor_id, device_id)]
        # The shared name resolver excludes audio functions, so audio aliases must not resolve to a GPU.
        expected = None if info.get("is_audio") else info.get("name")
        if gpu_inventory.resolve_alias_to_device_name(alias, self._name_map) != expected:
            raise _Unsupported(f"PCI alias {alias!r} resolves inconsistently")
        return f"CUSTOM_PCI_{vendor_id}_{device_id}"


def _parse_pci_aliases(value: str, catalog: _AliasCatalog) -> list[str]:
    groups: list[str] = []
    seen: set[str] = set()
    for raw_entry in value.split(","):
        alias, separator, raw_count = raw_entry.strip().partition(":")
        alias, raw_count = alias.strip(), raw_count.strip()
        if not alias or not separator or not _COUNT_RE.match(raw_count):
            raise _Unsupported(f"malformed PCI alias request {raw_entry!r}")
        count = int(raw_count)
        if count < 1:
            raise _Unsupported(f"malformed PCI alias request {raw_entry!r}")
        if count > _MAX_PCI_DEVICES - len(groups):
            raise _Unsupported("unsupported PCI device count")
        if alias in seen:
            raise _Unsupported(f"duplicate PCI alias {alias!r}")
        seen.add(alias)
        groups.extend([catalog.resource_class(alias)] * count)
    if not groups:
        raise _Unsupported("unsupported PCI device count")
    return groups


def _parse_demand(flavor: FlavorInfo, catalog: _AliasCatalog) -> _Demand:
    specs = flavor.extra_specs or {}
    if not isinstance(specs, dict):
        raise _Unsupported("extra_specs is not a mapping")
    explicit: dict[str, int] = {}
    required: set[str] = set()
    forbidden: set[str] = set()
    aggregate_specs: dict[str, str] = {}
    capability_specs: dict[str, str] = {}
    pci_groups: list[str] = []
    group_policy: str | None = None
    cpu_policy = thread_policy = emulator_policy = None
    numa = False

    for raw_key, raw_value in specs.items():
        key = str(raw_key)
        value = str(raw_value).strip()
        if _GROUPED_KEY_RE.match(key):
            raise _Unsupported(f"granular request group {key!r}")
        scope, separator, name = key.partition(":")
        if not separator:
            if key != "group_policy" or value not in ("none", "isolate"):
                raise _Unsupported(f"unscoped scheduler spec {key!r}")
            group_policy = value
        elif scope == "resources":
            if not _NAME_RE.match(name) or not _COUNT_RE.match(value):
                raise _Unsupported(f"malformed resource request {key!r}")
            if name.startswith("CUSTOM_PCI_"):
                raise _Unsupported("explicit PCI resource classes bypass Nova PCI tracking")
            explicit[name] = int(value)
        elif scope == "trait":
            if not _NAME_RE.match(name) or value not in ("required", "forbidden"):
                raise _Unsupported(f"malformed trait request {key!r}")
            (required if value == "required" else forbidden).add(name)
        elif scope == "aggregate_instance_extra_specs":
            if not name or not value or value.split()[0] in _SPEC_OPERATORS:
                raise _Unsupported(f"unsupported aggregate spec {key!r}")
            aggregate_specs[name] = value
        elif scope == "capabilities":
            cpu_field = name.removeprefix("cpu_info:")
            if (
                cpu_field == name
                or not _CAPABILITY_FIELD_RE.match(cpu_field)
                or not value
                or value.split()[0] in _SPEC_OPERATORS
            ):
                raise _Unsupported(f"unsupported capability spec {key!r}")
            capability_specs[cpu_field] = str(raw_value)
        elif scope == "pci_passthrough":
            if name != "alias":
                raise _Unsupported(f"unsupported PCI spec {key!r}")
            pci_groups.extend(_parse_pci_aliases(value, catalog))
        elif scope == "hw":
            if name == "cpu_policy":
                cpu_policy = value.lower()
            elif name == "cpu_thread_policy":
                thread_policy = value.lower()
            elif name == "emulator_threads_policy":
                emulator_policy = value.lower()
            elif name == "numa_nodes":
                # One guest cell needs no host topology beyond what every host has; more cells do.
                if not _COUNT_RE.match(value) or int(value) != 1:
                    raise _Unsupported(f"multi-cell or malformed hw:numa_nodes {value!r}")
                numa = True
            elif name == "mem_page_size":
                if value not in _BOUNDED_PAGE_SIZES:
                    raise _Unsupported(f"hugepage-backed hw:mem_page_size {value!r}")
                numa = True
            elif name not in _NEUTRAL_HW_KEYS:
                raise _Unsupported(f"scheduling-relevant hw spec {key!r}")
        elif scope not in _IGNORED_SCOPES:
            raise _Unsupported(f"unsupported spec scope {key!r}")

    if gpu_inventory.is_gpu_flavor(flavor) and not pci_groups and not (_EXPLICIT_GPU_CLASSES & explicit.keys()):
        raise _Unsupported("GPU flavor without a representable GPU request")

    vcpus = flavor.vcpus
    explicit_cpu = {rc: explicit.pop(rc) for rc in (_VCPU, _PCPU) if rc in explicit}
    if cpu_policy == "dedicated":
        if explicit_cpu:
            raise _Unsupported("explicit CPU resources conflict with hw:cpu_policy")
        if thread_policy not in (None, "prefer", "isolate", "require"):
            raise _Unsupported("unsupported hw:cpu_thread_policy")
        if emulator_policy not in (None, "share", "isolate"):
            raise _Unsupported("unsupported hw:emulator_threads_policy")
        cpu = {_PCPU: vcpus + (1 if emulator_policy == "isolate" else 0)}
        numa = True  # pinned CPUs imply a single-cell NUMA topology
        if thread_policy == "isolate":
            forbidden.add(_HYPERTHREADING_TRAIT)
        elif thread_policy == "require":
            required.add(_HYPERTHREADING_TRAIT)
    elif cpu_policy in (None, "shared"):
        if thread_policy is not None or emulator_policy is not None:
            raise _Unsupported("CPU thread/emulator policy requires dedicated CPUs")
        if cpu_policy == "shared" and explicit_cpu.get(_PCPU):
            raise _Unsupported("explicit PCPU conflicts with hw:cpu_policy=shared")
        cpu = explicit_cpu or {_VCPU: vcpus}
    else:
        raise _Unsupported(f"unsupported hw:cpu_policy {cpu_policy!r}")
    cpu = {rc: amount for rc, amount in cpu.items() if amount > 0}
    if len(cpu) != 1:
        raise _Unsupported("flavor must request exactly one CPU resource class")
    ((cpu_class, cpu_amount),) = cpu.items()
    memory = explicit.pop(_MEMORY, flavor.ram)
    if memory <= 0:
        raise _Unsupported("flavor requests no memory")
    if required & forbidden:
        raise _Unsupported("trait both required and forbidden")

    # Boot-from-volume callers: flavor root disk is not local DISK_GB; explicit resources:* still apply.
    return _Demand(
        shape=_Shape(
            cpu_class=cpu_class,
            extra=tuple(sorted((rc, amount) for rc, amount in explicit.items() if amount > 0)),
            required=tuple(sorted(required)),
            forbidden=tuple(sorted(forbidden)),
            pci_groups=tuple(sorted(pci_groups)),
            group_policy=group_policy,
        ),
        cpu=cpu_amount,
        ram=memory,
        aggregate_specs=tuple(sorted(aggregate_specs.items())),
        capability_specs=tuple(sorted(capability_specs.items())),
        numa_unverified=numa,
    )


def _parse_all(flavors: list[FlavorInfo]) -> tuple[dict[str, _Demand | None], bool]:
    catalog = _AliasCatalog()
    demands: dict[str, _Demand | None] = {}
    unknown_alias = False
    for flavor in flavors:
        try:
            demands[flavor.id] = _parse_demand(flavor, catalog)
        except _Unsupported as exc:
            unknown_alias = unknown_alias or isinstance(exc, _UnknownAlias)
            _logger.info("flavor %s capacity unrepresentable: %s", flavor.id, exc)
            demands[flavor.id] = None
    return demands, unknown_alias


class _Client:
    """Strict read-only JSON GETs: short timeout, no retries, one evaluation's deadline."""

    def __init__(self, conn: Any) -> None:
        self._session = conn.session
        self._compute = self._endpoint(conn.compute.get_endpoint(), "compute")
        self._placement = self._endpoint(conn.placement.get_endpoint(), "placement")

    @staticmethod
    def _endpoint(endpoint: Any, service: str) -> str:
        if not isinstance(endpoint, str) or not endpoint:
            raise _AuthorityError(f"{service} endpoint unavailable")
        return endpoint.rstrip("/")

    def compute(self, path: str, params: Any, deadline: float) -> dict:
        body = self._get(self._compute + path, _COMPUTE_VERSION, params, deadline, missing_ok=False)
        assert body is not None
        return body

    def placement(self, path: str, params: Any, deadline: float, *, missing_ok: bool = False) -> dict | None:
        return self._get(self._placement + path, _PLACEMENT_VERSION, params, deadline, missing_ok=missing_ok)

    def _get(self, url: str, version: str, params: Any, deadline: float, *, missing_ok: bool) -> dict | None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _AuthorityError("capacity evaluation deadline exceeded")
        response = self._session.get(
            url,
            params=params,
            headers={"OpenStack-API-Version": version, "Accept": "application/json"},
            timeout=min(_REQUEST_TIMEOUT_SECONDS, remaining),
            connect_retries=0,
            status_code_retries=0,
            raise_exc=False,
        )
        status = getattr(response, "status_code", None)
        if missing_ok and status == 404:
            return None
        if not isinstance(status, int) or not 200 <= status < 300:
            raise _AuthorityError(f"{version} returned HTTP {status}")
        try:
            body = response.json()
        except ValueError as exc:
            raise _AuthorityError(f"{version} returned a non-JSON body") from exc
        if not isinstance(body, dict):
            raise _AuthorityError(f"{version} returned a non-object body")
        return body


def _list(body: dict, key: str) -> list:
    value = body.get(key)
    if not isinstance(value, list):
        raise _AuthorityError(f"response lacks list {key!r}")
    return value


def _dict(value: Any, what: str) -> dict:
    if not isinstance(value, dict):
        raise _AuthorityError(f"malformed {what}")
    return value


def _int(record: dict, key: str, minimum: int) -> int:
    value = record.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise _AuthorityError(f"malformed inventory field {key!r}")
    return value


def _next_marker(links: Any) -> str | None:
    if links is None:
        return None
    if not isinstance(links, list):
        raise _AuthorityError("malformed hypervisor links")
    for link in links:
        if isinstance(link, dict) and link.get("rel") == "next":
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(str(link.get("href", ""))).query)
            markers = query.get("marker")
            if not markers or not markers[0]:
                raise _AuthorityError("hypervisor next link lacks a marker")
            return markers[0]
    return None


def _hypervisors(client: _Client, deadline: float) -> list:
    items: list = []
    marker: str | None = None
    seen: set[str] = set()
    for _ in range(_MAX_HYPERVISOR_PAGES):
        params: dict[str, Any] = {"limit": _HYPERVISOR_PAGE_LIMIT}
        if marker:
            params["marker"] = marker
        body = client.compute("/os-hypervisors/detail", params, deadline)
        items.extend(_list(body, "hypervisors"))
        marker = _next_marker(body.get("hypervisors_links"))
        if marker is None:
            return items
        if marker in seen:
            raise _AuthorityError("hypervisor pagination repeated a marker")
        seen.add(marker)
    raise _AuthorityError("hypervisor pagination did not terminate")


def _classify(
    hypervisor: dict,
    services: dict[str, dict | None],
    host_metadata: dict[str, dict[str, set[str]]],
    host_zones: dict[str, set[str]],
    *,
    project_id: str,
    availability_zone: str | None,
) -> _Host:
    unknown = _Host("unknown", {})
    service_ref = hypervisor.get("service")
    if not isinstance(service_ref, dict):
        return unknown
    service_id, host = service_ref.get("id"), service_ref.get("host")
    service = services.get(service_id) if isinstance(service_id, str) else None
    if service is None or not isinstance(host, str) or service.get("host") != host:
        return unknown
    status, state, forced_down = service.get("status"), service.get("state"), service.get("forced_down")
    hv_status, hv_state = hypervisor.get("status"), hypervisor.get("state")
    if (
        status not in ("enabled", "disabled")
        or state not in ("up", "down")
        or not isinstance(forced_down, bool)
        or hv_status not in ("enabled", "disabled")
        or hv_state not in ("up", "down")
    ):
        return unknown
    metadata = {key: frozenset(values) for key, values in host_metadata.get(host, {}).items()}
    if status != "enabled" or state != "up" or forced_down or hv_status != "enabled" or hv_state != "up":
        return _Host("ineligible", metadata)
    zone, zones = service.get("zone"), host_zones.get(host, set())
    if not isinstance(zone, str) or len(zones) > 1 or (zones and zone not in zones):
        return unknown
    if availability_zone and zone != availability_zone:
        return _Host("ineligible", metadata)
    tenants = {
        tenant.strip()
        for key, values in metadata.items()
        if key.startswith(_TENANT_KEY_PREFIX)
        for value in values
        for tenant in value.split(",")
        if tenant.strip()
    }
    if tenants and project_id not in tenants:
        return _Host("ineligible", metadata)
    cpu_info = hypervisor.get("cpu_info")
    return _Host("eligible", metadata, cpu_info if isinstance(cpu_info, dict) else None)


@dataclass(frozen=True)
class _HostFacts:
    """Project-independent Nova facts; eligibility is derived per project and zone."""

    services: dict[str, dict | None]
    host_metadata: dict[str, dict[str, set[str]]]
    host_zones: dict[str, set[str]]
    hypervisors: tuple[dict, ...]

    @classmethod
    def fetch(cls, client: _Client, deadline: float) -> _HostFacts:
        services: dict[str, dict | None] = {}
        for service in _list(client.compute("/os-services", {"binary": "nova-compute"}, deadline), "services"):
            service = _dict(service, "compute service")
            service_id = service.get("id")
            if not isinstance(service_id, str) or not service_id:
                raise _AuthorityError("compute service lacks a UUID")
            if service.get("binary") == "nova-compute":
                services[service_id] = None if service_id in services else service

        host_metadata: dict[str, dict[str, set[str]]] = {}
        host_zones: dict[str, set[str]] = {}
        for aggregate in _list(client.compute("/os-aggregates", None, deadline), "aggregates"):
            aggregate = _dict(aggregate, "aggregate")
            hosts = aggregate.get("hosts") or []
            metadata = aggregate.get("metadata") or {}
            zone = aggregate.get("availability_zone")
            if (
                not isinstance(hosts, list)
                or not isinstance(metadata, dict)
                or not all(isinstance(h, str) for h in hosts)
            ):
                raise _AuthorityError("malformed aggregate")
            for host in hosts:
                merged = host_metadata.setdefault(host, {})
                for key, value in metadata.items():
                    merged.setdefault(str(key), set()).update(item.strip() for item in str(value).split(","))
                if zone:
                    host_zones.setdefault(host, set()).add(str(zone))
        hypervisors = tuple(_dict(item, "hypervisor") for item in _hypervisors(client, deadline))
        return cls(services, host_metadata, host_zones, hypervisors)

    def classify(self, *, project_id: str, availability_zone: str | None) -> dict[str, _Host]:
        """Nova compute-node UUID (== Placement root provider UUID) -> eligibility facts."""
        hosts: dict[str, _Host] = {}
        duplicates: set[str] = set()
        for hypervisor in self.hypervisors:
            node_uuid = hypervisor.get("id")
            if not isinstance(node_uuid, str) or not node_uuid:
                continue  # unmappable; its provider tree then classifies as unknown
            if node_uuid in hosts:
                duplicates.add(node_uuid)
            hosts[node_uuid] = _classify(
                hypervisor,
                self.services,
                self.host_metadata,
                self.host_zones,
                project_id=project_id,
                availability_zone=availability_zone,
            )
        for node_uuid in duplicates:
            hosts[node_uuid] = _Host("unknown", {})
        return hosts


def _admits(host: _Host | None, demand: _Demand) -> str:
    if host is None or host.state != "eligible":
        return "unknown" if host is None else host.state
    for key, value in demand.aggregate_specs:
        if value not in host.metadata.get(key, frozenset()):
            return "ineligible"
    for cpu_field, value in demand.capability_specs:
        if host.cpu_info is None:
            return "unknown"
        capability = host.cpu_info.get(cpu_field)
        if capability is None or str(capability) != value:
            return "ineligible"
    return "eligible"


def _provider_roots(body: dict) -> dict[str, str]:
    """Provider -> root map from one /resource_providers read, validated for consistency."""
    roots: dict[str, str] = {}
    parents: dict[str, str | None] = {}
    for provider in _list(body, "resource_providers"):
        provider = _dict(provider, "resource provider")
        uuid, root, parent = (
            provider.get("uuid"),
            provider.get("root_provider_uuid"),
            provider.get("parent_provider_uuid"),
        )
        if not isinstance(uuid, str) or not isinstance(root, str) or not (parent is None or isinstance(parent, str)):
            raise _AuthorityError("malformed resource provider")
        if uuid in roots:
            raise _AuthorityError("duplicate resource provider")
        roots[uuid] = root
        parents[uuid] = parent
    for uuid, root in roots.items():
        parent = parents[uuid]
        if roots.get(root) != root or parents.get(root) is not None:
            raise _AuthorityError("resource provider root is not a root")
        if (parent is None) != (uuid == root) or (parent is not None and roots.get(parent) != root):
            raise _AuthorityError("inconsistent resource provider tree")
    return roots


@dataclass(frozen=True)
class _ShapeView:
    """One allocation-candidates response: candidates grouped by root plus that moment's provider summaries."""

    fetched_at: str
    roots: dict[str, tuple[dict[tuple[str, str], int], ...]]
    summaries: dict[str, dict[str, tuple[int, int]]]  # provider -> class -> (capacity, used)
    unexplained: bool  # cross-tree, sharing or totals that do not match the request
    missing_class: bool  # no candidates and a requested custom class does not exist in Placement


def _now() -> str:
    return datetime.now(UTC).isoformat()


class _Snapshot:
    """Lazily filled Nova/Placement reads; discovery callers share one for _SNAPSHOT_TTL_SECONDS."""

    def __init__(self) -> None:
        self.created = time.monotonic()
        self._facts: _HostFacts | None = None
        self._roots: dict[str, str] | None = None
        self._max_units: dict[str, dict[str, int]] = {}
        self._shapes: dict[_Shape, _ShapeView] = {}
        # A failed shape stays failed for this snapshot: polls during an outage do not hammer Placement.
        self._shape_failures: dict[_Shape, str] = {}
        self._classes: dict[str, bool] = {}

    def is_fresh(self) -> bool:
        return time.monotonic() - self.created < _SNAPSHOT_TTL_SECONDS

    def facts(self, client: _Client, deadline: float) -> _HostFacts:
        if self._facts is None:
            self._facts = _HostFacts.fetch(client, deadline)
        return self._facts

    def provider_roots(self, client: _Client, deadline: float) -> dict[str, str]:
        if self._roots is None:
            body = client.placement("/resource_providers", None, deadline)
            assert body is not None
            self._roots = _provider_roots(body)
        return self._roots

    def max_unit(self, client: _Client, deadline: float, provider: str, resource_class: str) -> int:
        if provider not in self._max_units:
            path = f"/resource_providers/{urllib.parse.quote(provider, safe='')}/inventories"
            body = client.placement(path, None, deadline)
            assert body is not None
            parsed: dict[str, int] = {}
            for name, record in _dict(body.get("inventories"), "inventories").items():
                parsed[str(name)] = _int(_dict(record, "inventory"), "max_unit", 1)
            self._max_units[provider] = parsed
        units = self._max_units[provider]
        if resource_class not in units:
            raise _AuthorityError("candidate supplier lacks the allocated inventory")
        return units[resource_class]

    def shape(self, client: _Client, deadline: float, shape: _Shape) -> _ShapeView:
        if shape in self._shapes:
            return self._shapes[shape]
        if shape in self._shape_failures:
            raise _CachedShapeFailure(f"allocation candidates failed in this snapshot: {self._shape_failures[shape]}")
        try:
            view = self._fetch_shape(client, deadline, shape)
        except Exception as exc:
            self._shape_failures[shape] = str(exc) or type(exc).__name__
            raise
        self._shapes[shape] = view
        return view

    def class_exists(self, client: _Client, deadline: float, resource_class: str) -> bool:
        if resource_class not in self._classes:
            path = f"/resource_classes/{urllib.parse.quote(resource_class, safe='')}"
            self._classes[resource_class] = client.placement(path, None, deadline, missing_ok=True) is not None
        return self._classes[resource_class]

    def _fetch_shape(self, client: _Client, deadline: float, shape: _Shape) -> _ShapeView:
        roots_of = self.provider_roots(client, deadline)
        fetched_at = _now()
        body = client.placement("/allocation_candidates", shape.query(), deadline)
        assert body is not None
        expected = shape.expected()
        roots: dict[str, list[dict[tuple[str, str], int]]] = {}
        unexplained = False
        for request in _list(body, "allocation_requests"):
            allocations = _dict(_dict(request, "allocation request").get("allocations"), "allocations")
            amounts: dict[tuple[str, str], int] = {}
            for provider, allocation in allocations.items():
                resources = _dict(_dict(allocation, "allocation").get("resources"), "allocation resources")
                for resource_class, amount in resources.items():
                    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 1:
                        raise _AuthorityError("malformed allocation amount")
                    key = (str(provider), str(resource_class))
                    amounts[key] = amounts.get(key, 0) + amount
            tree_roots = {roots_of.get(provider) for provider, _ in amounts}
            totals: dict[str, int] = {}
            for (_, resource_class), amount in amounts.items():
                totals[resource_class] = totals.get(resource_class, 0) + amount
            if len(tree_roots) != 1 or None in tree_roots or totals != expected:
                unexplained = True  # cross-tree/sharing or unexplained candidate: never summed
                continue
            (root,) = tree_roots
            roots.setdefault(root, []).append(amounts)

        raw_summaries = _dict(body.get("provider_summaries"), "provider summaries")
        summaries: dict[str, dict[str, tuple[int, int]]] = {}
        for provider in {
            provider for candidates in roots.values() for amounts in candidates for provider, _ in amounts
        }:
            summary = _dict(raw_summaries.get(provider), "provider summary")
            resources = _dict(summary.get("resources"), "provider summary resources")
            summaries[provider] = {
                str(rc): (_int(_dict(record, "provider summary resource"), "capacity", 0), _int(record, "used", 0))
                for rc, record in resources.items()
            }
        missing_class = False
        if not roots and not unexplained:
            # Live Placement already rejects unregistered classes with HTTP 400; this covers empty answers too.
            missing_class = not all(self.class_exists(client, deadline, rc) for rc in sorted(shape.custom_classes()))
        return _ShapeView(
            fetched_at=fetched_at,
            roots={root: tuple(candidates) for root, candidates in roots.items()},
            summaries=summaries,
            unexplained=unexplained,
            missing_class=missing_class,
        )


def _unavailable(demand: _Demand | None, checked_at: str) -> FlavorCapacityInfo:
    return FlavorCapacityInfo(
        status="unavailable",
        checked_at=checked_at,
        cpu_resource_class=demand.shape.cpu_class if demand else None,
        numa_unverified=bool(demand and demand.numa_unverified),
    )


def _verdict(
    demand: _Demand,
    hosts: dict[str, _Host],
    view: _ShapeView,
    snapshot: _Snapshot,
    client: _Client,
    deadline: float,
) -> FlavorCapacityInfo:
    cpu_class = demand.shape.cpu_class

    def summary(provider: str, resource_class: str) -> tuple[int, int]:
        record = view.summaries.get(provider, {}).get(resource_class)
        if record is None:
            raise _AuthorityError("provider summary lacks an allocated class")
        return record

    def per_vm(provider: str, resource_class: str) -> int:
        capacity, used = summary(provider, resource_class)
        return min(max(capacity - used, 0), snapshot.max_unit(client, deadline, provider, resource_class))

    def fits(amounts: dict[tuple[str, str], int]) -> bool:
        for (provider, resource_class), amount in amounts.items():
            if resource_class == cpu_class:
                amount = demand.cpu
            elif resource_class == _MEMORY:
                amount = demand.ram
            capacity, used = summary(provider, resource_class)
            if used + amount > capacity:
                return False
            if resource_class in (cpu_class, _MEMORY) and amount > snapshot.max_unit(
                client, deadline, provider, resource_class
            ):
                return False
        return True

    fitting: list[tuple[int, int]] = []
    compatible: list[tuple[int, int]] = []
    unknown = view.unexplained
    for root, candidates in view.roots.items():
        verdict = _admits(hosts.get(root), demand)
        if verdict != "eligible":
            unknown = unknown or verdict == "unknown"
            continue
        best_fit: tuple[int, int] | None = None
        best_any: tuple[int, int] | None = None
        for amounts in candidates:
            cpu_supplier = next(provider for provider, rc in amounts if rc == cpu_class)
            ram_supplier = next(provider for provider, rc in amounts if rc == _MEMORY)
            bound = (per_vm(cpu_supplier, cpu_class), per_vm(ram_supplier, _MEMORY))
            best_any = bound if best_any is None else max(best_any, bound)
            if fits(amounts):
                best_fit = bound if best_fit is None else max(best_fit, bound)
        if best_fit is not None:
            fitting.append(best_fit)
        if best_any is not None:
            compatible.append(best_any)

    def info(status: str, hosts_count: int = 0, pair: tuple[int, int] | None = None) -> FlavorCapacityInfo:
        return FlavorCapacityInfo(
            status=status,
            checked_at=view.fetched_at,
            candidate_hosts=hosts_count,
            cpu_resource_class=cpu_class,
            remaining_vcpus=pair[0] if pair else None,
            remaining_ram_mb=pair[1] if pair else None,
            numa_unverified=demand.numa_unverified,
        )

    if fitting:
        return info("available", len(fitting), max(fitting))
    if unknown or view.missing_class:
        return info("unavailable")
    return info("insufficient", 0, max(compatible) if compatible else None)


@dataclass(frozen=True)
class _Operator:
    conn: Any
    client: _Client


_operator_lock = threading.Lock()
_operator: _Operator | None = None
_shared_snapshot_lock = threading.Lock()
_shared_snapshot: _Snapshot | None = None
_discovery_locks: dict[int, tuple[asyncio.AbstractEventLoop, asyncio.Lock]] = {}


def _close(conn: Any) -> None:
    try:
        conn.close()
    except Exception:
        _logger.debug("closing capacity operator connection failed", exc_info=True)


def _operator_session() -> _Operator:
    """Process-wide operator connection; its token is reused until a snapshot-level failure."""
    global _operator
    with _operator_lock:
        if _operator is None:
            conn = keystone.get_admin_project_connection()
            try:
                _operator = _Operator(conn, _Client(conn))
            except Exception:
                _close(conn)
                raise
        return _operator


def _discard_operator(operator: _Operator) -> None:
    global _operator
    with _operator_lock:
        if _operator is operator:
            _operator = None
    _close(operator.conn)


def _discovery_snapshot() -> _Snapshot:
    global _shared_snapshot
    with _shared_snapshot_lock:
        if _shared_snapshot is None or not _shared_snapshot.is_fresh():
            _shared_snapshot = _Snapshot()
        return _shared_snapshot


def _discovery_lock() -> asyncio.Lock:
    """Single-flight lock for the running loop (uvloop loops are not weak-referenceable)."""
    loop = asyncio.get_running_loop()
    for key, (other, _) in list(_discovery_locks.items()):
        if other.is_closed():
            del _discovery_locks[key]
    entry = _discovery_locks.get(id(loop))
    if entry is None or entry[0] is not loop:
        entry = _discovery_locks[id(loop)] = (loop, asyncio.Lock())
    return entry[1]


def _project(
    demands: dict[str, _Demand | None],
    *,
    project_id: str,
    availability_zone: str | None,
    snapshot: _Snapshot,
) -> dict[str, FlavorCapacityInfo]:
    deadline = time.monotonic() + _DEADLINE_SECONDS
    checked_at = _now()
    results = {flavor_id: _unavailable(None, checked_at) for flavor_id, demand in demands.items() if demand is None}
    pending = {flavor_id: demand for flavor_id, demand in demands.items() if demand is not None}
    if not pending:
        return results
    operator: _Operator | None = None
    try:
        operator = _operator_session()
        client = operator.client
        hosts = snapshot.facts(client, deadline).classify(project_id=project_id, availability_zone=availability_zone)
        snapshot.provider_roots(client, deadline)
        verdicts: dict[_Demand, FlavorCapacityInfo] = {}
        for flavor_id, demand in pending.items():
            if demand not in verdicts:
                try:
                    view = snapshot.shape(client, deadline, demand.shape)
                    verdicts[demand] = _verdict(demand, hosts, view, snapshot, client, deadline)
                except _CachedShapeFailure:
                    # Logged when the shape first failed; polls sharing the snapshot must not repeat it per flavor.
                    verdicts[demand] = _unavailable(demand, checked_at)
                except _AuthorityError as exc:
                    _logger.warning("flavor %s host capacity unavailable: %s", flavor_id, exc)
                    verdicts[demand] = _unavailable(demand, checked_at)
                except Exception:
                    _logger.warning("flavor %s host capacity unavailable", flavor_id, exc_info=True)
                    verdicts[demand] = _unavailable(demand, checked_at)
            results[flavor_id] = verdicts[demand]
    except Exception:
        _logger.warning("flavor host capacity snapshot unavailable", exc_info=True)
        if operator is not None:
            _discard_operator(operator)
        for flavor_id, demand in pending.items():
            results.setdefault(flavor_id, _unavailable(demand, checked_at))
    return results


async def _refresh_gpu_catalog() -> bool:
    from app.database import is_db_available

    if not is_db_available():
        return False
    try:
        from app.services import gpu_catalog

        await gpu_catalog.refresh_device_map_from_db()
    except Exception:
        _logger.warning("GPU catalog refresh for capacity aliases failed", exc_info=True)
        return False
    return True


async def evaluate_flavor_capacities(
    flavors: Iterable[FlavorInfo],
    *,
    project_id: str,
    availability_zone: str | None,
    fresh: bool = True,
) -> dict[str, FlavorCapacityInfo]:
    """Project one VM of each flavor onto read-only Nova/Placement state.

    ``fresh`` (create admission) reads now. Discovery lists pass ``fresh=False`` and may
    reuse a snapshot up to ``_SNAPSHOT_TTL_SECONDS`` old, built single-flight per process.
    """
    flavor_list = list(flavors)
    if not flavor_list:
        return {}
    demands, unknown_alias = _parse_all(flavor_list)
    if unknown_alias and await _refresh_gpu_catalog():
        demands, _ = _parse_all(flavor_list)
    zone = availability_zone or None

    async def run() -> dict[str, FlavorCapacityInfo]:
        if fresh:
            return await asyncio.to_thread(
                _project, demands, project_id=project_id, availability_zone=zone, snapshot=_Snapshot()
            )
        async with _discovery_lock():
            return await asyncio.to_thread(
                _project, demands, project_id=project_id, availability_zone=zone, snapshot=_discovery_snapshot()
            )

    try:
        return await asyncio.wait_for(run(), timeout=_DEADLINE_SECONDS + _REQUEST_TIMEOUT_SECONDS)
    except TimeoutError:
        _logger.warning("flavor host capacity evaluation exceeded its deadline")
        checked_at = _now()
        return {flavor_id: _unavailable(demand, checked_at) for flavor_id, demand in demands.items()}
