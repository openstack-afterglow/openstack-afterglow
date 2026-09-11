"""Project-scoped flavor quota eligibility shared by discovery and admission."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.models.compute import (
    FlavorDemandInfo,
    FlavorEligibility,
    FlavorInfo,
    FlavorQuotaBlocker,
    FlavorRemainingInfo,
)
from app.services import gpu_quota, nova
from app.services.gpu_inventory import is_gpu_flavor

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
    """A known project quota prevents the requested flavor demand."""

    def __init__(self, eligibility: FlavorEligibility):
        self.eligibility = eligibility
        super().__init__(format_blockers(eligibility.blockers))


class FlavorEligibilityUnavailable(Exception):
    """A quota authority needed for the requested flavor is unavailable."""

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
        return -1
    limit = entry.get("limit")
    in_use = entry.get("in_use")
    int_limit = int(limit) if isinstance(limit, (int, float)) and not isinstance(limit, bool) else -1
    int_in_use = int(in_use) if isinstance(in_use, (int, float)) and not isinstance(in_use, bool) else 0
    return -1 if int_limit == -1 else max(int_limit - int_in_use, 0)


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


async def evaluate_project_flavors(
    conn: Any,
    project_id: str,
    flavors: Iterable[FlavorInfo],
    *,
    count: int = 1,
    current_flavor: Any | None = None,
) -> list[FlavorInfo]:
    """Attach eligibility to project-visible flavors using one snapshot per authority."""
    flavor_list = list(flavors)
    compute_quota: dict[str, Any] | None = None
    gpu_status: dict[str, dict[str, int]] | None = None
    compute_error = False
    gpu_error = False
    try:
        compute_quota = await asyncio.to_thread(nova.get_project_quota, conn, project_id)
    except Exception:
        compute_error = True

    if any(parse_gpu_demand(flavor) for flavor in flavor_list):
        try:
            statuses = await gpu_quota.get_effective_gpu_quota_status(conn, project_id)
            gpu_status = {item["gpu_type"]: item for item in statuses}
        except Exception:
            gpu_error = True
    else:
        gpu_status = {}

    return [
        _with_eligibility(
            flavor,
            evaluate_flavor(
                flavor,
                compute_quota=compute_quota,
                gpu_status=gpu_status,
                count=count,
                current_flavor=current_flavor,
                compute_error=compute_error,
                gpu_error=gpu_error,
            ),
        )
        for flavor in flavor_list
    ]


async def require_flavor_eligible(
    conn: Any,
    project_id: str,
    flavor: FlavorInfo,
    *,
    count: int = 1,
    current_flavor: Any | None = None,
    allow_gpu_authority_fallback: bool = False,
) -> FlavorEligibility:
    evaluated = await evaluate_project_flavors(
        conn,
        project_id,
        [flavor],
        count=count,
        current_flavor=current_flavor,
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
) -> FlavorAdmission:
    """Require eligibility and reserve custom GPU headroom before mutation."""
    from app.services.gpu_inventory import require_gpu_quota

    gpu_available = await require_gpu_quota(conn, flavor)
    eligibility = await require_flavor_eligible(
        conn,
        project_id,
        flavor,
        count=count,
        current_flavor=current_flavor,
        allow_gpu_authority_fallback=True,
    )
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
    return f"Flavor quota eligibility denied: {codes or 'unknown'}"
