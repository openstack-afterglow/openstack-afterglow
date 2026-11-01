"""Shared native resize facts for project and administrator surfaces."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from app.models.compute import FlavorInfo, FlavorQuotaBlocker

RESIZABLE_STATUSES = frozenset({"ACTIVE", "SHUTOFF"})


@dataclass(frozen=True)
class ResizeTarget:
    """The instance allocation a resize replaces; never a create admission."""

    current: FlavorInfo
    image_backed: bool


def require_resizable(server) -> None:
    if (server.status or "").upper() not in RESIZABLE_STATUSES:
        raise HTTPException(status_code=409, detail="현재 상태에서는 리사이즈할 수 없습니다")


def current_flavor(server, flavors: list[FlavorInfo]) -> FlavorInfo:
    snapshot = server._flavor_snapshot
    if snapshot is not None:
        # Nova's embedded flavor is the instance's allocation, not the mutable catalog.
        # In particular a deleted/private/renamed flavor need not be in list_flavors.
        resources = (snapshot.get("vcpus"), snapshot.get("ram"), snapshot.get("disk"))
        if (
            not server.flavor_name
            or any(type(value) is not int for value in resources)
            or resources[0] <= 0
            or resources[1] <= 0
            or resources[2] < 0
            or not isinstance(snapshot.get("extra_specs"), dict)
        ):
            raise HTTPException(status_code=409, detail="현재 플레이버를 확인할 수 없습니다")
        return FlavorInfo(
            id=server.flavor_id or "",
            name=server.flavor_name,
            vcpus=resources[0],
            ram=resources[1],
            disk=resources[2],
            extra_specs=snapshot["extra_specs"],
        )
    current = next((flavor for flavor in flavors if flavor.id == server.flavor_id), None)
    if current is None and not server.flavor_id and server.flavor_name:
        matches = [flavor for flavor in flavors if flavor.name == server.flavor_name]
        current = matches[0] if len(matches) == 1 else None
    if current is None:
        raise HTTPException(status_code=409, detail="현재 플레이버를 확인할 수 없습니다")
    return current


def target_for(server, flavors: list[FlavorInfo]) -> ResizeTarget:
    require_resizable(server)
    return ResizeTarget(current=current_flavor(server, flavors), image_backed=bool(server.image_id))


def target_blockers(target: FlavorInfo, resize: ResizeTarget, *, same_flavor: bool = True) -> list[FlavorQuotaBlocker]:
    current = resize.current
    blockers = []
    if same_flavor and (target.id == current.id or (not current.id and target.name == current.name)):
        blockers.append(FlavorQuotaBlocker(code="same_flavor"))
    if resize.image_backed and target.disk < current.disk:
        blockers.append(FlavorQuotaBlocker(code="disk_shrink"))
    return blockers


def apply_target_blockers(
    flavors: list[FlavorInfo], resize: ResizeTarget, *, same_flavor: bool = True
) -> list[FlavorInfo]:
    for flavor in flavors:
        blockers = target_blockers(flavor, resize, same_flavor=same_flavor)
        if blockers and flavor.eligibility is not None:
            flavor.eligibility = flavor.eligibility.model_copy(
                update={"selectable": False, "blockers": [*flavor.eligibility.blockers, *blockers]}
            )
    return flavors
