from __future__ import annotations

import asyncio
import ipaddress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator, model_validator

from app.api.common.activity_recorder import rec
from app.api.common.owner_check import assert_project_resource_owner
from app.api.deps import CacheMode, cache_mode, get_os_conn, get_token_info
from app.rate_limit import limiter
from app.services import neutron
from app.services.cache import cached_call, invalidate, patch_list, ttl_slow

router = APIRouter()


class CreateSecurityGroupRequest(BaseModel):
    name: str
    description: str = ""


class CreateSecurityGroupRuleRequest(BaseModel):
    direction: str  # "ingress" | "egress"
    protocol: str | None = None  # "tcp", "udp", "icmp", None (any)
    port_range_min: int | None = None
    port_range_max: int | None = None
    remote_ip_prefix: str | None = None
    remote_group_id: str | None = None
    ethertype: str = "IPv4"

    @field_validator("remote_ip_prefix")
    @classmethod
    def validate_remote_ip_prefix(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            ipaddress.ip_network(value, strict=False)
        except ValueError as exc:
            raise ValueError("원격 IP는 CIDR 형식이어야 합니다 (예: 0.0.0.0/0)") from exc
        return value

    @model_validator(mode="after")
    def resolve_defaults(self):
        if self.remote_group_id and self.remote_ip_prefix:
            raise ValueError("원격 IP와 원격 보안 그룹은 동시에 지정할 수 없습니다")
        if self.remote_ip_prefix:
            ip_version = ipaddress.ip_network(self.remote_ip_prefix, strict=False).version
            if ip_version != (6 if self.ethertype == "IPv6" else 4):
                raise ValueError("원격 IP는 선택한 IP 버전과 일치해야 합니다")
        if not self.remote_group_id and not self.remote_ip_prefix:
            self.remote_ip_prefix = "::/0" if self.ethertype == "IPv6" else "0.0.0.0/0"
        if self.port_range_min is not None and self.port_range_max is None:
            self.port_range_max = self.port_range_min
        return self


@router.get("")
async def list_security_groups(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    pid = conn._afterglow_project_id
    try:
        return await cached_call(
            f"afterglow:neutron:{pid}:security_groups",
            ttl_slow(),
            lambda: neutron.list_security_groups(conn, project_id=pid),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="보안 그룹 목록 조회 실패")


@router.get("/quota")
async def get_security_group_quota(conn: openstack.connection.Connection = Depends(get_os_conn)):
    try:
        return await asyncio.to_thread(neutron.get_security_group_quota, conn, conn._afterglow_project_id)
    except Exception:
        raise HTTPException(status_code=503, detail="보안 그룹 할당량 조회 실패")


@router.get("/{sg_id}/instances")
async def get_security_group_instances(
    sg_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _get_sg_with_owner_check(conn, sg_id, token_info)
    try:
        return await asyncio.to_thread(neutron.list_security_group_instances, conn, conn._afterglow_project_id, sg_id)
    except Exception:
        raise HTTPException(status_code=500, detail="보안 그룹 인스턴스 조회 실패")


@router.post("", status_code=201)
@limiter.limit("10/minute")
async def create_security_group(
    request: Request,
    req: CreateSecurityGroupRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        result = neutron.create_security_group(conn, req.name, req.description)
        # terminal mutation — list 캐시에 신규 SG 직접 추가 (origin 재조회 없음)
        await patch_list(f"afterglow:neutron:{pid}:security_groups", ttl_slow(), add=result)
        await rec(token_info, conn, resource_type="security_group", action="create", resource_name=req.name)
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="security_group",
            action="create",
            status="failed",
            resource_name=req.name,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="보안 그룹 생성 실패")


async def _get_sg_with_owner_check(conn, sg_id: str, token_info: dict):
    try:
        sg = await asyncio.to_thread(conn.network.get_security_group, sg_id)
    except Exception:
        raise HTTPException(status_code=404, detail="보안 그룹을 찾을 수 없습니다")
    owner_id = getattr(sg, "project_id", None) or getattr(sg, "tenant_id", None)
    if sg is None or owner_id != conn._afterglow_project_id:
        raise HTTPException(status_code=404, detail="보안 그룹을 찾을 수 없습니다")
    assert_project_resource_owner(sg, conn, token_info, not_found_detail="보안 그룹을 찾을 수 없습니다")
    return sg


@router.delete("/{sg_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_security_group(
    request: Request,
    sg_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    await _get_sg_with_owner_check(conn, sg_id, token_info)
    try:
        neutron.delete_security_group(conn, sg_id)
        # terminal mutation — list 캐시에서 해당 SG 직접 제거 (origin 재조회 없음)
        await patch_list(f"afterglow:neutron:{pid}:security_groups", ttl_slow(), match=sg_id, remove=True)
        await rec(token_info, conn, resource_type="security_group", action="delete", resource_id=sg_id)
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="security_group",
            action="delete",
            status="failed",
            resource_id=sg_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="보안 그룹 삭제 실패")


@router.post("/{sg_id}/rules", status_code=201)
@limiter.limit("10/minute")
async def create_security_group_rule(
    request: Request,
    sg_id: str,
    req: CreateSecurityGroupRuleRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    await _get_sg_with_owner_check(conn, sg_id, token_info)
    if req.remote_group_id:
        await _get_sg_with_owner_check(conn, req.remote_group_id, token_info)
    try:
        result = neutron.create_security_group_rule(
            conn,
            sg_id=sg_id,
            direction=req.direction,
            protocol=req.protocol,
            port_range_min=req.port_range_min,
            port_range_max=req.port_range_max,
            remote_ip_prefix=req.remote_ip_prefix,
            ethertype=req.ethertype,
            remote_group_id=req.remote_group_id,
        )
        await invalidate(f"afterglow:neutron:{pid}:security_groups")
        await rec(token_info, conn, resource_type="security_group", action="add_rule", resource_id=sg_id)
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="security_group",
            action="add_rule",
            status="failed",
            resource_id=sg_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="보안 그룹 규칙 추가 실패")


@router.delete("/{sg_id}/rules/{rule_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_security_group_rule(
    request: Request,
    sg_id: str,
    rule_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    await _get_sg_with_owner_check(conn, sg_id, token_info)
    try:
        rule = await asyncio.to_thread(conn.network.get_security_group_rule, rule_id)
    except Exception:
        raise HTTPException(status_code=404, detail="보안 그룹 규칙을 찾을 수 없습니다")
    if (
        rule is None
        or getattr(rule, "security_group_id", None) != sg_id
        or (getattr(rule, "project_id", None) or getattr(rule, "tenant_id", None)) != pid
    ):
        raise HTTPException(status_code=404, detail="보안 그룹 규칙을 찾을 수 없습니다")
    assert_project_resource_owner(rule, conn, token_info, not_found_detail="보안 그룹 규칙을 찾을 수 없습니다")
    try:
        neutron.delete_security_group_rule(conn, rule_id)
        await invalidate(f"afterglow:neutron:{pid}:security_groups")
        await rec(token_info, conn, resource_type="security_group", action="remove_rule", resource_id=sg_id)
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="security_group",
            action="remove_rule",
            status="failed",
            resource_id=sg_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="보안 그룹 규칙 삭제 실패")
