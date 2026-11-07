"""Standard project-role presets and native-service capability projections.

Capability identifiers are wire-level action labels, never assignable IAM roles.
Keystone owns current project authority; each native service owns action verdicts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from fastapi import HTTPException

CORE_ROLE_NAMES = frozenset({"admin", "manager", "member", "reader"})
# Afterglow's own gates: resource control is the reader/member boundary.
# `manager` is domain administration held on the Default project; it is not
# treated as a resource role here. Drover, Waygate, Palimpsest and Lumen already
# admit manager as member in their own policies and core OpenStack services apply
# their native policy, so neither is widened by this application-layer set.
PROJECT_WRITE_ROLE_NAMES = frozenset({"admin", "member"})
PROJECT_ROLE_NAMES = ("project_owner", "project_admin", "project_member", "project_reader")
SERVICE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "waygate": (
        "waygate-inventory_reader",
        "waygate-connect_user",
        "waygate-clients_editor",
        "waygate-gateways_editor",
        "waygate-clients_admin",
        "waygate-gateways_admin",
        "waygate-routing_admin",
    ),
    "lumen": (
        "lumen-inventory_reader",
        "lumen-history_reader",
        "lumen-chat_user",
        "lumen-images_user",
        "lumen-audio_user",
        "lumen-tools_user",
        "lumen-assets_editor",
        "lumen-agents_editor",
        "lumen-mcp_editor",
        "lumen-keys_editor",
        "lumen-history_editor",
        "lumen-resources_admin",
    ),
    "drover": (
        "drover-inventory_reader",
        "drover-access_user",
        "drover-clusters_editor",
        "drover-workloads_editor",
        "drover-clusters_admin",
        "drover-access_admin",
    ),
    "palimpsest": (
        "palimpsest-inventory_reader",
        "palimpsest-download_user",
        "palimpsest-publish_editor",
        "palimpsest-keys_editor",
        "palimpsest-keys_admin",
    ),
}

ROLE_PRESETS = (
    {
        "name": "project_owner",
        "description": "프로젝트 소유권·관리자 위임",
        "area": "project",
        "grade": "owner",
        "parent": None,
    },
    {
        "name": "project_admin",
        "description": "프로젝트 구성원·역할 관리",
        "area": "project",
        "grade": "admin",
        "parent": "project_owner",
    },
    {
        "name": "project_member",
        "description": "프로젝트 리소스 생성·관리·OpenStack member",
        "area": "project",
        "grade": "member",
        "parent": "project_admin",
    },
    {
        "name": "project_reader",
        "description": "프로젝트 읽기 전용·OpenStack reader",
        "area": "project",
        "grade": "reader",
        "parent": "project_member",
    },
)
ROLE_IMPLICATIONS = tuple(
    (row["parent"], row["name"]) for row in ROLE_PRESETS if row["area"] == "project" and row["parent"]
) + (("project_member", "member"), ("project_reader", "reader"))

# Historical migration data only. Explicit preset apply may retire exactly these
# former shipped edges; never delete native role identities or assignments.
_RETIRED_GRADES = ("reader", "user", "editor", "admin")
_RETIRED_ACTION_GROUPS = {
    "waygate": (
        ("waygate-inventory_reader",),
        ("waygate-connect_user",),
        ("waygate-clients_editor", "waygate-gateways_editor"),
        ("waygate-clients_admin", "waygate-gateways_admin", "waygate-routing_admin"),
    ),
    "lumen": (
        ("lumen-inventory_reader", "lumen-history_reader"),
        ("lumen-chat_user", "lumen-images_user", "lumen-audio_user", "lumen-tools_user"),
        ("lumen-assets_editor", "lumen-agents_editor", "lumen-mcp_editor", "lumen-keys_editor", "lumen-history_editor"),
        ("lumen-resources_admin",),
    ),
    "drover": (
        ("drover-inventory_reader",),
        ("drover-access_user",),
        ("drover-clusters_editor", "drover-workloads_editor"),
        ("drover-clusters_admin", "drover-access_admin"),
    ),
    "palimpsest": (
        ("palimpsest-inventory_reader",),
        ("palimpsest-download_user",),
        ("palimpsest-publish_editor", "palimpsest-keys_editor"),
        ("palimpsest-keys_admin",),
    ),
}
RETIRED_SERVICE_ROLE_NAMES = frozenset(
    {f"{service}_{grade}" for service in _RETIRED_ACTION_GROUPS for grade in _RETIRED_GRADES}
    | {name for groups in _RETIRED_ACTION_GROUPS.values() for group in groups for name in group}
)


def _retired_service_implications():
    edges = []
    for service, groups in _RETIRED_ACTION_GROUPS.items():
        edges.extend(
            (f"{service}_{upper}", f"{service}_{lower}")
            for lower, upper in zip(_RETIRED_GRADES, _RETIRED_GRADES[1:], strict=False)
        )
        for grade, names in zip(_RETIRED_GRADES, groups, strict=True):
            for name in names:
                edges.append((f"{service}_{grade}", name))
                if grade != "reader":
                    edges.append((name, f"{service}_reader"))
    return tuple(edges)


RETIRED_SERVICE_IMPLICATIONS = _retired_service_implications()


def preset_preview() -> dict:
    return {
        "roles": [dict(row) for row in ROLE_PRESETS if row["area"] != "project"],
        "project_roles": [dict(row) for row in ROLE_PRESETS if row["area"] == "project"],
        "implications": [{"prior": prior, "implied": implied} for prior, implied in ROLE_IMPLICATIONS],
        "retired_implications": [
            {"prior": prior, "implied": implied} for prior, implied in RETIRED_SERVICE_IMPLICATIONS
        ],
    }


def normalize_role_name(name: str) -> str:
    """Normalize custom names without reviving retired service-role identities."""
    if not isinstance(name, str):
        raise ValueError("Role name must be text")
    if name.casefold() in CORE_ROLE_NAMES:
        return name.casefold()
    if name.count("_") != 1:
        raise ValueError("역할 이름은 영역_등급 형식이어야 합니다")
    parts = [re.sub(r"\s+", "-", part).casefold() for part in name.split("_")]
    if any(not re.fullmatch(r"[a-z0-9-]+", part) or not re.search(r"[a-z0-9]", part) for part in parts):
        raise ValueError("영역과 등급에는 영문·숫자·하이픈을 사용하고 공백은 하이픈으로 바꿉니다")
    result = "_".join(parts)
    if len(result) > 255:
        raise ValueError("Role name exceeds 255 characters")
    if result in RETIRED_SERVICE_ROLE_NAMES:
        raise ValueError("Retired service roles are not assignable; use standard project roles")
    return result


def service_permissions(principal: Mapping) -> dict[str, list[str]]:
    """Project only native policy verdicts; never infer them from token/UI roles."""
    projected = principal.get("service_permissions", {})
    if not isinstance(projected, Mapping):
        projected = {}
    return {
        service: sorted({action for action in projected.get(service, ()) if action in actions})
        for service, actions in SERVICE_CAPABILITIES.items()
    }


def require_service_permission(principal: Mapping, *actions: str) -> None:
    """Require native action verdicts; key scopes and ownership stay native checks."""
    permissions = service_permissions(principal)
    for action in actions:
        service = action.split("-", 1)[0].split("_", 1)[0]
        if action not in permissions.get(service, ()):
            raise HTTPException(status_code=403, detail=f"서비스 권한이 필요합니다: {action}")
