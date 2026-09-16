"""자원 owner 검증 헬퍼.

OpenStack RBAC(project-scoped 토큰)이 1차 방어선이지만, openstack policy 가 광범위하게 열려
있거나 admin 토큰 누설이 있을 때 코드 레벨에서 한 번 더 차단한다 (defense-in-depth).

사용 예:
    server = nova.get_server(conn, instance_id)
    assert_resource_owner(server, conn, token_info)
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def _caller_project_id(conn: Any) -> str | None:
    """deps.get_os_conn 이 conn 에 저장한 원본 project_id 를 추출."""
    return getattr(conn, "_afterglow_project_id", None)


def _resource_project_id(resource: Any) -> str | None:
    """openstacksdk 의 Server / Volume / Network / etc. 에서 project_id 추출.

    SDK 에 따라 `project_id` 또는 `tenant_id` 속성이 있을 수 있으므로 둘 다 시도.
    """
    pid = getattr(resource, "project_id", None)
    if pid:
        return pid
    return getattr(resource, "tenant_id", None)


def assert_resource_owner(
    resource: Any,
    conn: Any,
    token_info: dict,
    *,
    raise_404: bool = True,
    not_found_detail: str = "리소스를 찾을 수 없습니다",
) -> None:
    """리소스의 project_id 가 호출자의 project_id 와 일치하는지 검증.

    - admin (token_info.is_system_admin) 은 통과
    - 미일치 시 default 로 404 (정보 노출 최소화). 명시적 권한 거부가 더 적절한 경우 raise_404=False
    """
    if token_info.get("is_system_admin", False):
        return
    caller_pid = _caller_project_id(conn)
    resource_pid = _resource_project_id(resource)
    if caller_pid and resource_pid and resource_pid != caller_pid:
        raise HTTPException(
            status_code=404 if raise_404 else 403,
            detail=not_found_detail,
        )


def assert_project_resource_owner(
    resource: Any,
    conn: Any,
    token_info: dict,
    *,
    not_found_detail: str = "리소스를 찾을 수 없습니다",
) -> None:
    """프로젝트 소유 write 대상은 owner metadata 누락도 거부한다."""
    if token_info.get("is_system_admin", False):
        return
    caller_pid = _caller_project_id(conn)
    resource_pid = _resource_project_id(resource)
    if not caller_pid or not resource_pid or resource_pid != caller_pid:
        raise HTTPException(status_code=404, detail=not_found_detail)


def assert_instance_owner(
    server: Any,
    conn: Any,
    token_info: dict,
    *,
    raise_404: bool = True,
) -> None:
    """인스턴스 owner 검증 — assert_resource_owner 의 instance 전용 wrapper."""
    assert_resource_owner(
        server,
        conn,
        token_info,
        raise_404=raise_404,
        not_found_detail="인스턴스를 찾을 수 없습니다",
    )
