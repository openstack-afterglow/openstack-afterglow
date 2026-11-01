"""Project quota eligibility and create-only host capacity admission."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.models.compute import (
    FlavorCapacityInfo,
    FlavorDemandInfo,
    FlavorEligibility,
    FlavorGpuPrimaryAlias,
    FlavorInfo,
    FlavorQuotaBlocker,
    FlavorRemainingInfo,
)
from app.services import compute_pools, gpu_quota, nova
from app.services.gpu_inventory import is_gpu_flavor

_logger = logging.getLogger(__name__)

AFTERGLOW_FRONTEND_VISIBLE_SPEC = "afterglow:frontend_visible"
_FRONTEND_HIDDEN_VALUES = frozenset({"0", "false", "no", "off"})


def is_flavor_frontend_visible(flavor: Any) -> bool:
    """Return the Afterglow user-catalog visibility, defaulting legacy flavors to visible."""
    try:
        specs = flavor.get("extra_specs") if isinstance(flavor, dict) else getattr(flavor, "extra_specs", None)
        raw = (specs or {}).get(AFTERGLOW_FRONTEND_VISIBLE_SPEC)
    except (AttributeError, TypeError):
        return True
    return raw is None or str(raw).strip().lower() not in _FRONTEND_HIDDEN_VALUES


class FlavorEligibilityDenied(Exception):
    """Known quota or host capacity prevents the requested flavor demand."""

    def __init__(self, eligibility: FlavorEligibility):
        self.eligibility = eligibility
        super().__init__(format_blockers(eligibility.blockers))


class FlavorEligibilityUnavailable(Exception):
    """A quota or create-capacity authority is unavailable."""

    def __init__(self, eligibility: FlavorEligibility):
        self.eligibility = eligibility
        super().__init__(format_blockers(eligibility.blockers))


@dataclass(frozen=True)
class FlavorDemand:
    instances: int
    cores: int
    ram_mb: int
    gpus: dict[str, int]


@dataclass(frozen=True)
class FlavorAdmission:
    eligibility: FlavorEligibility
    gpu_requested: dict[str, int]
    reservation_id: str | None


def parse_gpu_demand(flavor: Any) -> dict[str, int]:
    """Return normalized GPU alias counts requested by a flavor."""
    if not is_gpu_flavor(flavor):
        return {}
    specs = (flavor.get("extra_specs") if isinstance(flavor, dict) else getattr(flavor, "extra_specs", None)) or {}
    resource_gpu_count = 0
    for key, value in specs.items():
        if re.fullmatch(r"resources\d*:[VP]GPU", str(key)):
            try:
                resource_gpu_count += max(int(value), 0)
            except (TypeError, ValueError):
                continue
    requested: dict[str, int] = {}
    for raw_entry in str(specs.get("pci_passthrough:alias", "")).split(","):
        entry = raw_entry.strip()
        if not entry or "audio" in entry.lower():
            continue
        if not is_gpu_flavor(extra_specs={"pci_passthrough:alias": entry}):
            continue
        alias, separator, raw_count = entry.rpartition(":")
        if not separator:
            alias, raw_count = entry, "1"
        try:
            count = int(raw_count.strip())
        except ValueError:
            count = 1
        count = max(count, 1)
        normalized = gpu_quota.normalize_gpu_alias(alias.strip())
        if normalized:
            requested[normalized] = requested.get(normalized, 0) + count
    if resource_gpu_count:
        requested["GPU"] = requested.get("GPU", 0) + resource_gpu_count
    return requested or {"GPU": 1}


def flavor_demand(
    flavor: Any,
    *,
    count: int = 1,
    current_flavor: Any | None = None,
) -> FlavorDemand:
    """Calculate create, multiplied-node, or resize-increase demand."""
    if count < 1:
        raise ValueError("count must be at least 1")
    target_gpus = {alias: amount * count for alias, amount in parse_gpu_demand(flavor).items()}
    target_cores = int(getattr(flavor, "vcpus", 0)) * count
    target_ram = int(getattr(flavor, "ram", 0)) * count
    if current_flavor is None:
        return FlavorDemand(count, target_cores, target_ram, target_gpus)

    current_gpus = parse_gpu_demand(current_flavor)
    return FlavorDemand(
        0,
        max(0, target_cores - int(getattr(current_flavor, "vcpus", 0))),
        max(0, target_ram - int(getattr(current_flavor, "ram", 0))),
        {
            alias: max(0, requested - current_gpus.get(alias, 0))
            for alias, requested in target_gpus.items()
            if requested > current_gpus.get(alias, 0)
        },
    )


def _remaining(entry: dict[str, Any] | None) -> int:
    if not isinstance(entry, dict):
        raise ValueError("missing compute quota resource")
    limit, in_use, reserved = entry.get("limit"), entry.get("in_use"), entry.get("reserved", 0)
    if (
        type(limit) is not int
        or type(in_use) is not int
        or type(reserved) is not int
        or limit < -1
        or in_use < 0
        or reserved < 0
    ):
        raise ValueError("invalid compute quota resource")
    return -1 if limit == -1 else max(limit - in_use - reserved, 0)


def _resource_blocker(code: str, resource: str, required: int, remaining: int) -> FlavorQuotaBlocker | None:
    if remaining == -1 or required <= remaining:
        return None
    return FlavorQuotaBlocker(code=code, resource=resource, required=required, remaining=remaining)


def evaluate_flavor(
    flavor: Any,
    *,
    compute_quota: dict[str, Any] | None,
    gpu_status: dict[str, dict[str, int]] | None,
    count: int = 1,
    current_flavor: Any | None = None,
    compute_error: bool = False,
    gpu_error: bool = False,
) -> FlavorEligibility:
    demand = flavor_demand(flavor, count=count, current_flavor=current_flavor)
    blockers: list[FlavorQuotaBlocker] = []
    compute_remaining = {"instances": 0, "cores": 0, "ram": 0}

    if compute_error or compute_quota is None:
        blockers.append(FlavorQuotaBlocker(code="compute_quota_unavailable"))
    else:
        try:
            compute_remaining = {key: _remaining(compute_quota.get(key)) for key in ("instances", "cores", "ram")}
        except (TypeError, ValueError):
            blockers.append(FlavorQuotaBlocker(code="compute_quota_unavailable"))
        else:
            for blocker in (
                _resource_blocker(
                    "instances_insufficient", "instances", demand.instances, compute_remaining["instances"]
                ),
                _resource_blocker("cores_insufficient", "cores", demand.cores, compute_remaining["cores"]),
                _resource_blocker("ram_insufficient", "ram_mb", demand.ram_mb, compute_remaining["ram"]),
            ):
                if blocker is not None:
                    blockers.append(blocker)

    gpu_remaining: dict[str, int] = {}
    if demand.gpus:
        if gpu_error or gpu_status is None:
            blockers.append(FlavorQuotaBlocker(code="gpu_quota_unavailable"))
        else:
            for alias, required in demand.gpus.items():
                status = gpu_status.get(alias)
                remaining = -1 if status and status.get("limit") == -1 else int((status or {}).get("available", 0))
                gpu_remaining[alias] = remaining
                blocker = _resource_blocker("gpu_insufficient", alias, required, remaining)
                if blocker is not None:
                    blockers.append(blocker)

    return FlavorEligibility(
        selectable=not blockers,
        requirements=FlavorDemandInfo(
            instances=demand.instances,
            cores=demand.cores,
            ram_mb=demand.ram_mb,
            gpus=demand.gpus,
        ),
        remaining=FlavorRemainingInfo(
            instances=compute_remaining["instances"],
            cores=compute_remaining["cores"],
            ram_mb=compute_remaining["ram"],
            gpus=gpu_remaining,
        ),
        blockers=blockers,
    )


def _with_eligibility(flavor: Any, eligibility: FlavorEligibility) -> Any:
    if hasattr(flavor, "model_copy"):
        return flavor.model_copy(update={"eligibility": eligibility})
    if hasattr(flavor, "__dict__"):
        flavor.eligibility = eligibility
        return flavor
    if isinstance(flavor, dict):
        return {**flavor, "eligibility": eligibility}
    return flavor


def _pool_remaining(snapshot: dict[str, Any], resource: str) -> int:
    domain = snapshot["available"].get(resource, 0)
    project = snapshot["project_available"].get(resource, -1)
    finite = [value for value in (domain, project) if value != -1]
    return min(finite) if finite else -1


def _intersect_remaining(native, pool):
    if native is None:
        return None
    finite = [value for value in (native, pool) if value != -1]
    return min(finite) if finite else -1


async def _with_pool_eligibility(
    conn: Any,
    project_id: str,
    flavor: Any,
    eligibility: FlavorEligibility,
    snapshot: dict[str, Any] | None,
    *,
    count: int,
    current_flavor: Any | None,
    unavailable: bool,
) -> FlavorEligibility:
    if unavailable:
        blockers = [*eligibility.blockers, FlavorQuotaBlocker(code="domain_pool_unavailable")]
        return eligibility.model_copy(update={"selectable": False, "blockers": blockers})
    if snapshot and snapshot.get("state") == "paused":
        return eligibility.model_copy(
            update={
                "selectable": False,
                "quota_scope": "domain",
                "domain_id": snapshot["domain_id"],
                "blockers": [*eligibility.blockers, FlavorQuotaBlocker(code="domain_pool_paused")],
            }
        )
    if not snapshot or not snapshot["enabled"]:
        return eligibility
    # Stock Nova project quotas remain authoritative alongside Afterglow policy.
    # Only the retired application GPU ledger is replaced by approved pool accounting.
    blockers = [
        blocker for blocker in eligibility.blockers if blocker.code not in {"gpu_insufficient", "gpu_quota_unavailable"}
    ]
    try:
        requested = await compute_pools.flavor_pool_requirements(conn, flavor, count=count, snapshot=snapshot)
        current = (
            await compute_pools.flavor_pool_requirements(conn, current_flavor, snapshot=snapshot)
            if current_flavor is not None
            else None
        )
        result = compute_pools.evaluate_pool_snapshot(snapshot, requested, current_requirements=current)
        blockers.extend(
            FlavorQuotaBlocker(
                code=item["code"],
                resource=item.get("resource"),
                required=item.get("required"),
                remaining=item.get("available"),
            )
            for item in result["blockers"]
        )
        remaining = eligibility.remaining.model_copy(
            update={
                "cores": _intersect_remaining(eligibility.remaining.cores, _pool_remaining(snapshot, "CPU")),
                "ram_mb": _intersect_remaining(eligibility.remaining.ram_mb, _pool_remaining(snapshot, "MEMORY_MB")),
                "gpus": {
                    resource: _pool_remaining(snapshot, resource)
                    for resource in requested
                    if resource.startswith("CUSTOM_PCI_")
                },
            }
        )
    except compute_pools.ComputePoolUnavailable:
        blockers.append(FlavorQuotaBlocker(code="domain_pool_unavailable"))
        remaining = eligibility.remaining
    requirements = eligibility.requirements
    if not any(blocker.code == "domain_pool_unavailable" for blocker in blockers):
        current_demand = current or {}
        requirements = requirements.model_copy(
            update={
                "cores": max(0, requested.get("CPU", 0) - current_demand.get("CPU", 0)),
                "ram_mb": max(0, requested.get("MEMORY_MB", 0) - current_demand.get("MEMORY_MB", 0)),
                "gpus": {
                    key: value - current_demand.get(key, 0)
                    for key, value in requested.items()
                    if key.startswith("CUSTOM_PCI_") and value > current_demand.get(key, 0)
                },
            }
        )
    return eligibility.model_copy(
        update={
            "selectable": not blockers,
            "blockers": blockers,
            "remaining": remaining,
            "requirements": requirements,
            "quota_scope": "domain",
            "domain_id": snapshot["domain_id"],
        }
    )


async def evaluate_project_flavors(
    conn: Any,
    project_id: str,
    flavors: Iterable[FlavorInfo],
    *,
    count: int = 1,
    current_flavor: Any | None = None,
    check_capacity: bool = False,
    availability_zone: str | None = None,
    fresh_capacity: bool = True,
    include_gpu_projection: bool = False,
    supported_hosts: list[dict] | None = None,
    capacity_regions: dict[str, list[dict]] | None = None,
) -> list[FlavorInfo]:
    """Attach eligibility to project-visible flavors using one snapshot per authority.

    Host capacity is evaluated only for a single-VM create (``check_capacity``, no current
    flavor, ``count == 1``). A confirmed shortage and an unverified capacity both block every
    flavor: an unresolved default zone, an operator or Placement failure, or an unrepresentable
    flavor constraint never admits a VM to Nova.
    Discovery lists pass ``fresh_capacity=False`` to project a bounded background observation.
    """
    flavor_list = list(flavors)
    if not flavor_list:
        return []
    compute_quota: dict[str, Any] | None = None
    gpu_status: dict[str, dict[str, int]] | None = None
    compute_error = False
    gpu_error = False
    pool_snapshot = None
    pool_unavailable = False
    try:
        pool_snapshot = await compute_pools.project_pool_snapshot(conn, project_id)
    except compute_pools.ComputePoolUnavailable:
        pool_unavailable = True
    try:
        compute_quota = await asyncio.to_thread(nova.get_project_quota, conn, project_id, strict=True)
    except Exception:
        _logger.warning("compute quota lookup failed for project %s", project_id, exc_info=True)
        compute_error = True

    if not (pool_snapshot and (pool_snapshot["enabled"] or pool_snapshot.get("state") == "paused")) and any(
        parse_gpu_demand(flavor) for flavor in flavor_list
    ):
        try:
            statuses = await gpu_quota.get_effective_gpu_quota_status(conn, project_id)
            gpu_status = {item["gpu_type"]: item for item in statuses}
        except Exception:
            _logger.warning("GPU quota status lookup failed for project %s", project_id, exc_info=True)
            gpu_error = True
    else:
        gpu_status = {}
    # Presentation metadata is derived independently of admission. Failure to
    # verify the current group leaves it unknown, never a guessed companion.
    gpu_capabilities = None
    if include_gpu_projection and any(
        flavor.extra_specs.get("afterglow:managed_by") == "domain-compute-v1" for flavor in flavor_list
    ):
        from app.services import flavor_automation_policy

        try:
            gpu_capabilities = await flavor_automation_policy.capabilities()
        except Exception:
            _logger.warning("managed flavor GPU presentation policy unavailable")

    capacities: dict[str, FlavorCapacityInfo] = {}
    needs_capacity = check_capacity and current_flavor is None and count == 1
    capacity_checked_at = datetime.now(UTC).isoformat()
    capacity_reason = None
    if needs_capacity:
        from app.services.flavor_capacity import evaluate_flavor_capacities
        from app.services.resource_policy_store import resolve_policies

        if not availability_zone:
            try:
                policies = await resolve_policies(conn=conn, keys=("nova.default_compute_availability_zone",))
                availability_zone = policies["nova.default_compute_availability_zone"]
            except Exception:
                capacity_reason = "default_compute_zone_unavailable"
                _logger.warning("default compute zone policy resolution failed", exc_info=True)
        if capacity_reason is None:
            try:
                composer = (
                    {"supported_hosts": supported_hosts, "region_results": capacity_regions}
                    if capacity_regions is not None
                    else {}
                )
                capacities = await evaluate_flavor_capacities(
                    flavor_list,
                    project_id=project_id,
                    availability_zone=availability_zone,
                    fresh=fresh_capacity,
                    **composer,
                )
            except Exception:
                _logger.warning("flavor host capacity lookup failed", exc_info=True)

    evaluated: list[FlavorInfo] = []
    for flavor in flavor_list:
        eligibility = evaluate_flavor(
            flavor,
            compute_quota=compute_quota,
            gpu_status=gpu_status,
            count=count,
            current_flavor=current_flavor,
            compute_error=compute_error,
            gpu_error=gpu_error,
        )
        eligibility = await _with_pool_eligibility(
            conn,
            project_id,
            flavor,
            eligibility,
            pool_snapshot,
            count=count,
            current_flavor=current_flavor,
            unavailable=pool_unavailable,
        )
        if needs_capacity:
            capacity = capacities.get(flavor.id) or FlavorCapacityInfo(
                status="unavailable", reason=capacity_reason, checked_at=capacity_checked_at
            )
            blockers = list(eligibility.blockers)
            if capacity.status in ("insufficient", "unavailable"):
                blockers.append(FlavorQuotaBlocker(code=f"host_capacity_{capacity.status}"))
            eligibility = eligibility.model_copy(
                update={"capacity": capacity, "blockers": blockers, "selectable": not blockers}
            )
        flavor = _with_eligibility(flavor, eligibility)
        if include_gpu_projection and flavor.extra_specs.get("afterglow:managed_by") == "domain-compute-v1":
            aliases = None
            if gpu_capabilities is not None:
                try:
                    projection = await compute_pools.approved_gpu_projection(flavor.extra_specs, gpu_capabilities)
                    aliases = [FlavorGpuPrimaryAlias.model_validate(row) for row in projection["gpu_primary_aliases"]]
                except compute_pools.ComputePoolUnavailable:
                    pass
            flavor = flavor.model_copy(update={"gpu_primary_aliases": aliases})
        evaluated.append(flavor)
    return evaluated


async def require_flavor_eligible(
    conn: Any,
    project_id: str,
    flavor: FlavorInfo,
    *,
    count: int = 1,
    current_flavor: Any | None = None,
    allow_gpu_authority_fallback: bool = False,
    check_capacity: bool = False,
    availability_zone: str | None = None,
) -> FlavorEligibility:
    evaluated = await evaluate_project_flavors(
        conn,
        project_id,
        [flavor],
        count=count,
        current_flavor=current_flavor,
        check_capacity=check_capacity,
        availability_zone=availability_zone,
    )
    eligibility = evaluated[0].eligibility
    assert eligibility is not None
    blockers = eligibility.blockers
    if allow_gpu_authority_fallback:
        blockers = [b for b in blockers if b.code != "gpu_quota_unavailable"]
    if not blockers:
        return eligibility
    unavailable = any(blocker.code.endswith("_unavailable") for blocker in blockers)
    if unavailable:
        raise FlavorEligibilityUnavailable(eligibility)
    raise FlavorEligibilityDenied(eligibility)


async def admit_flavor(
    conn: Any,
    project_id: str,
    flavor: FlavorInfo,
    *,
    count: int = 1,
    current_flavor: Any | None = None,
    availability_zone: str | None = None,
) -> FlavorAdmission:
    """Check Afterglow policy plus native quota/capacity; Nova owns actual allocation."""
    from app.services.gpu_inventory import require_gpu_quota

    eligibility = await require_flavor_eligible(
        conn,
        project_id,
        flavor,
        count=count,
        current_flavor=current_flavor,
        allow_gpu_authority_fallback=True,
        check_capacity=current_flavor is None and count == 1,
        availability_zone=availability_zone,
    )
    if eligibility.quota_scope == "domain":
        # Pool admission already checked the exact approved resource classes.
        # Preserve GPU initialization without writing a second, legacy quota reservation.
        requested = eligibility.requirements.gpus
        reservation_id = None
    else:
        gpu_available = await require_gpu_quota(conn, flavor, project_id=project_id)
        requested = eligibility.requirements.gpus if gpu_available else {}
        reservation_id = await gpu_quota.reserve_gpu_quota(conn, project_id, requested) if requested else None
    return FlavorAdmission(
        eligibility=eligibility,
        gpu_requested=requested,
        reservation_id=reservation_id,
    )


async def release_admission(admission: FlavorAdmission | None) -> None:
    if admission is not None:
        await gpu_quota.release_gpu_reservation(admission.reservation_id)


def format_blockers(blockers: Iterable[FlavorQuotaBlocker]) -> str:
    codes = ", ".join(blocker.code for blocker in blockers)
    return f"Flavor eligibility denied: {codes or 'unknown'}"
