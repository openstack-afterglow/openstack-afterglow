"""Project service entitlements, independent of native OpenStack write authority.

Only exact effective global leaf roles grant an entitlement. A suffix, project
administrator role or plain member never does. Keystone's current assignment
and implication graph is authoritative; native services also enforce actions.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from fastapi import HTTPException

CORE_ROLE_NAMES = frozenset({"admin", "manager", "member", "reader"})
PROJECT_ROLE_NAMES = ("project_owner", "project_admin", "project_member", "project_reader")
SERVICE_GRADE_ORDER = ("reader", "user", "editor", "admin")
SERVICE_ROLE_GRADES: dict[str, dict[str, tuple[str, ...]]] = {
    "waygate": {
        "reader": ("waygate-inventory_reader",),
        "user": ("waygate-connect_user",),
        "editor": ("waygate-clients_editor", "waygate-gateways_editor"),
        "admin": ("waygate-clients_admin", "waygate-gateways_admin", "waygate-routing_admin"),
    },
    "lumen": {
        "reader": ("lumen-inventory_reader", "lumen-history_reader"),
        "user": ("lumen-chat_user", "lumen-images_user", "lumen-audio_user", "lumen-tools_user"),
        "editor": (
            "lumen-assets_editor",
            "lumen-agents_editor",
            "lumen-mcp_editor",
            "lumen-keys_editor",
            "lumen-history_editor",
        ),
        "admin": ("lumen-resources_admin",),
    },
    "drover": {
        "reader": ("drover-inventory_reader",),
        "user": ("drover-access_user",),
        "editor": ("drover-clusters_editor", "drover-workloads_editor"),
        "admin": ("drover-clusters_admin", "drover-access_admin"),
    },
    "palimpsest": {
        "reader": ("palimpsest-inventory_reader",),
        "user": ("palimpsest-download_user",),
        "editor": ("palimpsest-publish_editor", "palimpsest-keys_editor"),
        "admin": ("palimpsest-keys_admin",),
    },
}

_LEAF_DESCRIPTIONS = {
    "waygate-inventory_reader": "프로젝트 VPN 서버·클라이언트 상태 조회(비밀 제외)",
    "waygate-connect_user": "본인에게 할당된 VPN 클라이언트 설정 다운로드",
    "waygate-clients_editor": "프로젝트 VPN 클라이언트 생성·편집·사용자 할당",
    "waygate-gateways_editor": "프로젝트 VPN 게이트웨이 생성·편집",
    "waygate-clients_admin": "프로젝트 VPN 클라이언트 삭제·접속 회수",
    "waygate-gateways_admin": "프로젝트 VPN 게이트웨이 삭제·키 회전",
    "waygate-routing_admin": "프로젝트 VPN 네트워크 연결·라우팅·자격 증명 이관",
    "lumen-inventory_reader": "허용된 Lumen 모델·기능 목록 조회",
    "lumen-history_reader": "본인 또는 공유가 허용된 대화·실행·결과 조회",
    "lumen-chat_user": "텍스트 추론·본인 대화 사용",
    "lumen-images_user": "이미지 생성·편집 사용",
    "lumen-audio_user": "음성 생성·전사·실시간 음성 사용",
    "lumen-tools_user": "허용된 도구·MCP·검색 실행",
    "lumen-assets_editor": "본인 또는 허용된 공유 파일·자산 생성·편집",
    "lumen-agents_editor": "본인 또는 허용된 공유 에이전트 생성·편집",
    "lumen-mcp_editor": "본인 또는 허용된 공유 MCP 설정 생성·편집",
    "lumen-keys_editor": "본인 권한 범위 내 Lumen API 키 발급·편집",
    "lumen-history_editor": "본인 대화 기록 편집·정리",
    "lumen-resources_admin": "허용된 프로젝트 Lumen 자산·설정 삭제 및 키 회수",
    "drover-inventory_reader": "프로젝트 클러스터 상태·이벤트 조회(비밀 제외)",
    "drover-access_user": "프로젝트 클러스터의 제한된 읽기 전용 접속 설정 다운로드",
    "drover-clusters_editor": "프로젝트 클러스터 생성·편집·확장",
    "drover-workloads_editor": "허용된 namespace의 workload 편집·셸 접속",
    "drover-clusters_admin": "프로젝트 클러스터 삭제·인증서 회전",
    "drover-access_admin": "프로젝트 클러스터 관리자 접속 설정·셸 관리",
    "palimpsest-inventory_reader": "허용된 프로젝트 패키지·버전 메타데이터 조회",
    "palimpsest-download_user": "허용된 프로젝트 패키지·레이어 다운로드",
    "palimpsest-publish_editor": "프로젝트 패키지·태그·빌드 캐시 게시",
    "palimpsest-keys_editor": "본인 권한 범위 내 프로젝트 패키지 키 발급",
    "palimpsest-keys_admin": "본인 프로젝트 패키지 키 회수",
}


def _presets() -> tuple[dict, ...]:
    rows = [
        {
            "name": "project_owner",
            "description": "프로젝트 소유권·관리자 위임",
            "area": "project",
            "grade": "owner",
            "parent": None,
        },
        {
            "name": "project_admin",
            "description": "프로젝트 구성원·서비스 권한 관리",
            "area": "project",
            "grade": "admin",
            "parent": "project_owner",
        },
        {
            "name": "project_member",
            "description": "프로젝트 일반 구성원·OpenStack member",
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
    ]
    titles = {
        "reader": "메타데이터 조회",
        "user": "허용된 기능 사용·다운로드",
        "editor": "생성·편집(관리자 작업 제외)",
        "admin": "프로젝트 내 전체 서비스 관리",
    }
    for service, grades in SERVICE_ROLE_GRADES.items():
        for index, grade in enumerate(SERVICE_GRADE_ORDER):
            parent = f"{service}_{SERVICE_GRADE_ORDER[index + 1]}" if index < 3 else None
            rows.append(
                {
                    "name": f"{service}_{grade}",
                    "description": titles[grade],
                    "area": service,
                    "grade": grade,
                    "parent": parent,
                }
            )
            for leaf in grades[grade]:
                rows.append(
                    {
                        "name": leaf,
                        "description": _LEAF_DESCRIPTIONS[leaf],
                        "area": service,
                        "grade": grade,
                        "parent": f"{service}_{grade}",
                    }
                )
    return tuple(rows)


ROLE_PRESETS = _presets()
ROLE_IMPLICATIONS = (
    tuple((row["parent"], row["name"]) for row in ROLE_PRESETS if row["parent"])
    + (("project_member", "member"), ("project_reader", "reader"))
    + tuple(
        (leaf, f"{service}_reader")
        for service, grades in SERVICE_ROLE_GRADES.items()
        for grade, leaves in grades.items()
        if grade != "reader"
        for leaf in leaves
    )
)
ROLE_LEAVES = frozenset(
    leaf for grades in SERVICE_ROLE_GRADES.values() for leaves in grades.values() for leaf in leaves
)


def preset_preview() -> dict:
    return {
        "roles": [dict(row) for row in ROLE_PRESETS if row["area"] != "project"],
        "project_roles": [dict(row) for row in ROLE_PRESETS if row["area"] == "project"],
        "implications": [{"prior": prior, "implied": implied} for prior, implied in ROLE_IMPLICATIONS],
    }


def normalize_role_name(name: str) -> str:
    """Normalize both components before validation; never silently trim spaces."""
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
    return result


def service_permissions(principal: Mapping) -> dict[str, list[str]]:
    """Project actual effective leaf grants, with native membership as a ceiling.

    Parent roles work only through Keystone's CURRENT implication graph. The
    preset definition is not a second inference engine or revocation fallback.
    """
    roles = {role for role in principal.get("roles", ()) if isinstance(role, str)}
    system_admin = principal.get("is_system_admin") is True
    privileged = bool(roles & {"admin", "manager"})
    member = "member" in roles
    reader = member or "reader" in roles
    result = {}
    for service, grades in SERVICE_ROLE_GRADES.items():
        allowed = set()
        if service != "palimpsest" and system_admin:
            allowed.update(leaf for leaves in grades.values() for leaf in leaves)
        elif reader and not privileged and not (service == "palimpsest" and system_admin):
            for grade in SERVICE_GRADE_ORDER:
                if grade != "reader" and not member:
                    continue
                leaves = grades[grade]
                allowed.update(role for role in leaves if role in roles)
        result[service] = sorted(allowed)
    return result


def require_service_permission(principal: Mapping, *leaves: str) -> None:
    """Require all action entitlements; key scopes/ownership remain native checks."""
    permissions = service_permissions(principal)
    for leaf in leaves:
        service = leaf.split("-", 1)[0].split("_", 1)[0]
        if leaf not in permissions.get(service, ()):
            raise HTTPException(status_code=403, detail=f"서비스 권한이 필요합니다: {leaf}")


def require_any_service_permission(principal: Mapping, *leaves: str) -> None:
    """Require one explicit action entitlement, without inferring a parent grade."""
    permissions = service_permissions(principal)
    allowed = {leaf for values in permissions.values() for leaf in values}
    if not allowed.intersection(leaves):
        raise HTTPException(status_code=403, detail=f"서비스 권한이 필요합니다: {' 또는 '.join(leaves)}")
