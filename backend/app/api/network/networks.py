from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING, Literal, NamedTuple

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.common.activity_recorder import rec
from app.api.common.owner_check import assert_resource_owner
from app.api.deps import CacheMode, cache_mode, get_os_conn, get_token_info
from app.config import get_settings
from app.models.storage import (
    AssociateFipRequest,
    CreateFipRequest,
    CreateNetworkRequest,
    CreateSubnetRequest,
    FloatingIpInfo,
    NetworkDetail,
    NetworkInfo,
    SubnetDetail,
    TopologyData,
    TopologyInstance,
    UpdateSubnetRequest,
)
from app.rate_limit import limiter
from app.services import neutron, nova, trove
from app.services.cache import cached_call, invalidate, ttl_fast, ttl_normal, ttl_static
from app.services.octavia import get_lb_stats, get_topology_lbs, lb_rate_from_snapshot, list_load_balancers
from app.services.parallel import run_parallel
from app.services.prom_query import (
    PromBadQuery,
    PromUnavailable,
    calc_step,
    is_safe_label_value,
    query_instant_multi,
    query_range_multi,
)

_logger = logging.getLogger(__name__)

# 토폴로지 트래픽 rate 윈도우. 저장소의 다른 PromQL 과 같은 값을 쓴다
# (`app/api/compute/instance_metrics.py` 가 같은 libvirt/node 카운터에 `[2m]` 을 쓴다).
#
# **이 값을 좁히지 마라.** `rate()` 는 윈도우 안에 최소 2 샘플이 필요한데,
# **이 저장소는 운영 Prometheus 의 scrape_interval 을 제어하지 않는다** — 운영은 Kolla 배포본이고
# 그 scrape 설정은 이 저장소 밖에 있다(`deploy/kolla/` 에 prometheus 설정이 없는 이유).
# `deploy/k8s*/monitoring/prometheus/configmap.yaml` 은 **다른 배포 경로**이며 운영 job 이름
# (`libvirt_exporter`, `openstack-instances-*`)과 일치하지도 않으므로 scrape 근거가 될 수 없다.
#
# 실측(2026-09-11, 운영 Prometheus, scrape 1m): 윈도우 30s 로 좁혔더니
# libvirt NIC 쿼리가 **0 시계열**을 반환해 화면에서 트래픽이 통째로 사라졌다(2m 에서는 43 시계열).
# 좁은 윈도우는 scrape 가 그만큼 빠른 배포에서만 안전하고, 우리는 그걸 보장할 수 없다.
TOPOLOGY_RATE_WINDOW = "2m"

router = APIRouter()


@router.get("", response_model=list[NetworkInfo])
async def list_networks(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    pid = conn._afterglow_project_id
    try:
        return await cached_call(
            f"afterglow:neutron:{pid}:networks",
            ttl_normal(),
            lambda: neutron.list_networks(conn, pid),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="네트워크 목록 조회 실패")


@router.post("", response_model=NetworkInfo, status_code=201)
@limiter.limit("10/minute")
async def create_network(
    request: Request,
    req: CreateNetworkRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    try:
        result = await asyncio.to_thread(neutron.create_network, conn, req.name)
        await rec(token_info, conn, resource_type="network", action="create", resource_name=req.name)
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="network",
            action="create",
            status="failed",
            resource_name=req.name,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="네트워크 생성 실패")


# ---------------------------------------------------------------------------
# Default 네트워크 (고정 경로 - /{network_id} 보다 먼저 등록)
# ---------------------------------------------------------------------------


class SetDefaultNetworkRequest(BaseModel):
    network_id: str


@router.post("/ensure-default", response_model=NetworkInfo, status_code=200)
@limiter.limit("10/minute")
async def ensure_default_network(
    request: Request,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """프로젝트의 Default 네트워크를 조회하거나 생성한다.

    프론트엔드에서 프로젝트 전환 시 호출 — DB에 이미 기록된 경우 빠르게 반환.
    """
    settings = get_settings()
    if not settings.default_network_enabled:
        raise HTTPException(status_code=404, detail="Default 네트워크 기능이 비활성화 상태입니다")
    project_id = conn._afterglow_project_id
    try:
        from app.services.default_network import ensure_default_network as _ensure
        from app.services.resource_policy_store import resolve_policies

        policies = await resolve_policies(conn=conn, keys=("nova.default_external_network",))
        net_info = await _ensure(
            conn,
            project_id,
            external_network_id=policies["nova.default_external_network"],
            cidr=settings.default_network_cidr,
        )
        # 네트워크 목록 캐시 무효화
        await invalidate(f"afterglow:neutron:{project_id}:networks")
        await rec(token_info, conn, resource_type="network", action="ensure_default", resource_id=net_info.id)
        return net_info
    except Exception:
        _logger.exception("Default 네트워크 ensure 실패")
        raise HTTPException(status_code=500, detail="Default 네트워크 처리 실패")


@router.get("/default", response_model=dict)
async def get_default_network(conn: openstack.connection.Connection = Depends(get_os_conn)):
    """현재 프로젝트의 Default 네트워크 정보를 반환한다 (DB 기록 기준)."""
    project_id = conn._afterglow_project_id
    from app.services.default_network import get_default_network_record

    record = await get_default_network_record(project_id)
    if not record:
        raise HTTPException(status_code=404, detail="Default 네트워크가 설정되지 않았습니다")
    return record


@router.put("/default", response_model=dict)
async def set_default_network(
    req: SetDefaultNetworkRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """사용자가 원하는 네트워크를 프로젝트의 Default 네트워크로 지정한다."""
    project_id = conn._afterglow_project_id
    # 네트워크 존재 여부 확인
    try:
        net = await asyncio.to_thread(neutron.get_network, conn, req.network_id)
    except Exception:
        raise HTTPException(status_code=404, detail="네트워크를 찾을 수 없습니다")

    from app.services.default_network import get_default_network_record
    from app.services.default_network import set_default_network as _set

    # 서브넷 ID: 해당 네트워크의 첫 번째 서브넷 사용
    subnet_id = net.subnets[0] if net.subnets else None
    await _set(project_id, req.network_id, subnet_id)
    # 캐시 무효화
    await invalidate(f"afterglow:neutron:{project_id}:networks")
    record = await get_default_network_record(project_id)
    return record or {"project_id": project_id, "network_id": req.network_id}


# ---------------------------------------------------------------------------
# Floating IP (고정 경로 - /{network_id} 보다 먼저 등록)
# ---------------------------------------------------------------------------


@router.get("/floating-ips", response_model=list[FloatingIpInfo])
async def list_floating_ips(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    pid = conn._afterglow_project_id
    try:
        return await cached_call(
            f"afterglow:neutron:{pid}:floating_ips",
            ttl_fast(),
            lambda: neutron.list_floating_ips(conn, pid),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Floating IP 목록 조회 실패")


@router.post("/floating-ips", response_model=FloatingIpInfo, status_code=201)
@limiter.limit("10/minute")
async def create_floating_ip(
    request: Request,
    req: CreateFipRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    try:
        result = await asyncio.to_thread(neutron.create_floating_ip, conn, req.floating_network_id)
        await rec(
            token_info,
            conn,
            resource_type="floating_ip",
            action="create",
            resource_id=result.id if hasattr(result, "id") else None,
        )
        return result
    except Exception as e:
        await rec(
            token_info, conn, resource_type="floating_ip", action="create", status="failed", error_message=str(e)[:500]
        )
        raise HTTPException(status_code=500, detail="Floating IP 생성 실패")


@router.post("/floating-ips/{fip_id}/associate", response_model=FloatingIpInfo)
@limiter.limit("10/minute")
async def associate_floating_ip(
    request: Request,
    fip_id: str,
    req: AssociateFipRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    try:
        fip = await asyncio.to_thread(conn.network.get_ip, fip_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Floating IP를 찾을 수 없습니다")
    assert_resource_owner(fip, conn, token_info, not_found_detail="Floating IP를 찾을 수 없습니다")
    try:
        result = await asyncio.to_thread(neutron.associate_floating_ip, conn, fip_id, req.instance_id)
        await rec(token_info, conn, resource_type="floating_ip", action="associate", resource_id=fip_id)
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="floating_ip",
            action="associate",
            status="failed",
            resource_id=fip_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="Floating IP 연결 실패")


@router.post("/floating-ips/{fip_id}/disassociate", response_model=FloatingIpInfo)
@limiter.limit("10/minute")
async def disassociate_floating_ip(
    request: Request,
    fip_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        fip = await asyncio.to_thread(conn.network.get_ip, fip_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Floating IP를 찾을 수 없습니다")
    assert_resource_owner(fip, conn, token_info, not_found_detail="Floating IP를 찾을 수 없습니다")
    try:
        result = await asyncio.to_thread(neutron.disassociate_floating_ip, conn, fip_id)
        await invalidate(f"afterglow:neutron:{pid}:floating_ips")
        await rec(token_info, conn, resource_type="floating_ip", action="disassociate", resource_id=fip_id)
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="floating_ip",
            action="disassociate",
            status="failed",
            resource_id=fip_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="Floating IP 해제 실패")


@router.delete("/floating-ips/{fip_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_floating_ip(
    request: Request,
    fip_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        fip = await asyncio.to_thread(conn.network.get_ip, fip_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Floating IP를 찾을 수 없습니다")
    assert_resource_owner(fip, conn, token_info, not_found_detail="Floating IP를 찾을 수 없습니다")
    try:
        await asyncio.to_thread(neutron.delete_floating_ip, conn, fip_id)
        await invalidate(f"afterglow:neutron:{pid}:floating_ips")
        await rec(token_info, conn, resource_type="floating_ip", action="delete", resource_id=fip_id)
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="floating_ip",
            action="delete",
            status="failed",
            resource_id=fip_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="Floating IP 삭제 실패")


# ---------------------------------------------------------------------------
# 서브넷 (고정 경로)
# ---------------------------------------------------------------------------


@router.put("/subnets/{subnet_id}", response_model=SubnetDetail)
async def update_subnet(
    subnet_id: str,
    req: UpdateSubnetRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    try:
        sub = await asyncio.to_thread(conn.network.get_subnet, subnet_id)
    except Exception:
        raise HTTPException(status_code=404, detail="서브넷을 찾을 수 없습니다")
    assert_resource_owner(sub, conn, token_info, not_found_detail="서브넷을 찾을 수 없습니다")
    try:
        result = await asyncio.to_thread(
            neutron.update_subnet, conn, subnet_id, req.name, req.gateway_ip, req.enable_dhcp
        )
        await rec(token_info, conn, resource_type="subnet", action="update", resource_id=subnet_id)
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="subnet",
            action="update",
            status="failed",
            resource_id=subnet_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="서브넷 업데이트 실패")


@router.delete("/subnets/{subnet_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_subnet(
    request: Request,
    subnet_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    try:
        sub = await asyncio.to_thread(conn.network.get_subnet, subnet_id)
    except Exception:
        raise HTTPException(status_code=404, detail="서브넷을 찾을 수 없습니다")
    assert_resource_owner(sub, conn, token_info, not_found_detail="서브넷을 찾을 수 없습니다")
    try:
        await asyncio.to_thread(neutron.delete_subnet, conn, subnet_id)
        await rec(token_info, conn, resource_type="subnet", action="delete", resource_id=subnet_id)
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="subnet",
            action="delete",
            status="failed",
            resource_id=subnet_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="서브넷 삭제 실패")


# ---------------------------------------------------------------------------
# 글로벌 토폴로지 (고정 경로 - 동적 경로보다 먼저 등록)
# ---------------------------------------------------------------------------


def _fetch_topology_sync(conn, project_id: str | None = None) -> dict:
    """동기 방식으로 토폴로지 데이터 수집 (cached_call 내부에서 to_thread로 실행됨).

    project_id 지정 시 해당 프로젝트의 인스턴스·네트워크·라우터·Floating IP만 반환 (user scope).
    None이면 전체 반환 (admin scope).
    """

    # 서로 의존하지 않는 OpenStack 조회는 동시에 수행한다 — 직렬 호출은 응답 시간이 그대로 합산된다.
    def _db_ips() -> set:
        try:
            return trove.topology_database_ips(conn)
        except Exception:
            _logger.debug("Trove 토폴로지 IP 조회 실패 — is_database 표시 생략", exc_info=True)
            return set()

    topo, servers, port_index, db_ips = run_parallel(
        lambda: neutron.get_topology(conn, project_id=project_id),
        lambda: nova.list_servers(conn),
        lambda: neutron.build_compute_port_index(conn),
        _db_ips,
    )

    def _ip_entry(server_id: str, ip) -> dict:
        port = port_index.get((server_id, ip.addr), {})
        return {
            **ip.model_dump(),
            "network_id": port.get("network_id"),
            "port_id": port.get("port_id"),
            "mac_addr": port.get("mac_address"),
        }

    def _is_database(ip_entries: list[dict]) -> bool:
        """fixed IP 가 Trove IP 집합에 속하면 DB 인스턴스. floating IP 우연 일치는 제외."""
        return any(e.get("type") == "fixed" and e.get("addr") in db_ips for e in ip_entries)

    instance_list = []
    for s in servers:
        ip_entries = [_ip_entry(s.id, ip) for ip in s.ip_addresses]
        instance_list.append(
            TopologyInstance(
                id=s.id,
                name=s.name,
                status=s.status,
                project_id=s.project_id,
                network_names=list(set(ip.network_name for ip in s.ip_addresses)),
                ip_addresses=ip_entries,
                flavor_name=s.flavor_name,
                image_id=s.image_id,
                is_database=_is_database(ip_entries),
            )
        )

    # user scope: 현재 프로젝트 인스턴스만 표시
    if project_id:
        instance_list = [i for i in instance_list if i.project_id == project_id]
        # 네트워크: 현재 프로젝트 소유 + external + shared 만 유지
        topo.networks = [n for n in topo.networks if n.project_id == project_id or n.is_external or n.is_shared]
        # 라우터: 현재 프로젝트 소유만 유지
        topo.routers = [r for r in topo.routers if getattr(r, "project_id", None) == project_id]
        # Floating IP: 현재 프로젝트 소유만 유지 (fail-closed; 관리자 토큰으로 project 전환 시 전체 FIP가 캐시에 남지 않도록)
        topo.floating_ips = [f for f in topo.floating_ips if getattr(f, "project_id", None) == project_id]

    topo.instances = instance_list
    topo.load_balancers = get_topology_lbs(
        conn,
        project_id=project_id or getattr(conn, "_afterglow_project_id", None),
        instances=[inst.model_dump() for inst in instance_list],
    )
    return topo.model_dump()


@router.get("/topology", response_model=TopologyData)
async def get_topology(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    pid = conn._afterglow_project_id
    try:
        return await cached_call(
            f"afterglow:neutron:{pid}:topology",
            ttl_normal(),
            lambda: _fetch_topology_sync(conn, project_id=pid),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except HTTPException:
        raise
    except Exception:
        _logger.exception("토폴로지 조회 실패")
        raise HTTPException(status_code=500, detail="토폴로지 조회 실패")


class _PortContext(NamedTuple):
    """토폴로지 트래픽 두 엔드포인트가 공유하는 포트 인덱스."""

    scope_project_id: str | None
    port_map: dict[str, dict]
    mac_idx: dict[str, dict]
    instance_ids: list[str]
    instance_ports: dict[str, list[str]]


async def _load_port_context(conn, token_info: dict, all_projects: bool) -> _PortContext:
    """compute 포트맵과 그 역인덱스를 만든다 (Redis 캐시, TTL 300s).

    instant(`/topology/traffic`)와 히스토리(`/topology/traffic/history`)가 **같은 귀속
    규칙**을 쓰도록 여기 한 곳에서만 만든다. `all_projects` 는 시스템 admin 전용.
    """
    if all_projects:
        if not token_info.get("is_system_admin", False):
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
        scope_project_id: str | None = None
        cache_key = "afterglow:neutron:_all:port_mac_map"
    else:
        scope_project_id = token_info.get("project_id", "") or conn._afterglow_project_id
        cache_key = f"afterglow:neutron:{scope_project_id}:port_mac_map"

    port_map: dict[str, dict] = await cached_call(
        cache_key,
        ttl_static(),
        lambda: neutron.list_project_port_map(conn, scope_project_id),
    )
    # mac_address → {port_id, instance_id, network_id} 역인덱스
    mac_idx: dict[str, dict] = {
        v["mac_address"]: {"port_id": pid, **v} for pid, v in port_map.items() if v.get("mac_address")
    }
    instance_ids = list(
        {instance_id for v in port_map.values() if is_safe_label_value(instance_id := v.get("instance_id"))}
    )
    # instance → [port_id] 맵 (단일NIC 판별용)
    instance_ports: dict[str, list[str]] = {}
    for pid, v in port_map.items():
        iid = v.get("instance_id")
        if iid:
            instance_ports.setdefault(iid, []).append(pid)
    return _PortContext(scope_project_id, port_map, mac_idx, instance_ids, instance_ports)


def _traffic_exprs(instance_ids: list[str]) -> tuple[str, str, str, str]:
    """(node rx, node tx, libvirt rx, libvirt tx) PromQL. instant/히스토리 공용.

    rate 윈도우는 `TOPOLOGY_RATE_WINDOW` 하나만 쓴다 — 두 엔드포인트가 같은 값을 보고해야 한다.
    """
    _exclude = r"lo|veth.*|docker.*|cni.*|tap.*|qbr.*"
    # UUID 는 [0-9a-f-] 만 포함 — re.escape 쓰면 \- 로 인해 Prometheus RE2 거부.
    regex = "|".join(instance_ids)
    # `max by` 이지 `sum by` 가 아니다. (instance_id, device) 는 NIC 하나를 유일하게 지목하므로
    # 같은 키가 여러 번 나오는 것은 **같은 카운터를 여러 job 이 중복 scrape** 했다는 뜻이다
    # (실측: 한 인스턴스가 openstack-instances-internal 과 -external 양쪽에 등록되어
    #  ens3 가 2243.7 + 2429.9 = 4673.6 으로 1.9배가 됐다). 더하면 이중 계산이고,
    # 중복 scrape 값은 타이밍 차이만 있으므로 하나만 취하는 것이 맞다.
    rx_q = (
        f"max by (instance_id, device) (rate(node_network_receive_bytes_total"
        f'{{instance_id=~"{regex}",device!~"{_exclude}"}}[{TOPOLOGY_RATE_WINDOW}]))'
    )
    # libvirt: NIC 단위 demux. group_left 2단계 중첩으로 mac_address + instance_id 동시 보존.
    lv_rx_q = (
        f"sum by (instance_id, mac_address) ("
        f"(rate(libvirt_domain_interface_stats_receive_bytes_total[{TOPOLOGY_RATE_WINDOW}])"
        f" * on (instance, domain, target_device) group_left(mac_address)"
        f"   libvirt_domain_interface_stats_info)"
        f" * on (instance, domain) group_left(instance_id)"
        f' libvirt_domain_openstack_info{{instance_id=~"{regex}"}})'
    )
    return rx_q, rx_q.replace("receive", "transmit"), lv_rx_q, lv_rx_q.replace("receive", "transmit")


@router.get("/topology/traffic")
async def get_topology_traffic(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
    all_projects: bool = Query(False, description="admin 전용: 모든 프로젝트 트래픽 조회"),
) -> dict:
    """현재 토폴로지의 모든 리소스 instant 트래픽 (rx/tx bps).

    구조 엔드포인트(/topology)와 분리 — 15s 단주기 폴링 전용.
    `all_projects=true` 는 시스템 admin 만 허용 — admin 토폴로지 페이지용.
    반환: { ts, instances, networks, interfaces, routers, load_balancers, _meta }
    """
    ctx = await _load_port_context(conn, token_info, all_projects)
    scope_project_id = ctx.scope_project_id
    port_map, mac_idx = ctx.port_map, ctx.mac_idx
    instance_ids, instance_ports = ctx.instance_ids, ctx.instance_ports

    # 2) PromQL instant queries — 5-fan-out 병렬 실행
    interfaces: dict[str, dict] = {}
    instances: dict[str, dict[str, float]] = {}

    if instance_ids:
        rx_q, tx_q, lv_rx_q, lv_tx_q = _traffic_exprs(instance_ids)
        try:
            rx_pairs, tx_pairs, lv_rx_pairs, lv_tx_pairs = await asyncio.gather(
                query_instant_multi(rx_q),
                query_instant_multi(tx_q),
                query_instant_multi(lv_rx_q),
                query_instant_multi(lv_tx_q),
            )
        except (PromUnavailable, PromBadQuery) as exc:
            _logger.warning("토폴로지 트래픽 PromQL 실패 — 폴백: %s", exc)
            rx_pairs = tx_pairs = lv_rx_pairs = lv_tx_pairs = []

        # libvirt 결과 → interfaces (NIC demux 주 경로)
        for labels, val in lv_rx_pairs:
            mac = (labels.get("mac_address") or "").lower()
            iid = labels.get("instance_id")
            info = mac_idx.get(mac)
            if not info or info["instance_id"] != iid:
                continue
            pid = info["port_id"]
            interfaces.setdefault(
                pid,
                {
                    "instance_id": iid,
                    "network_id": info["network_id"],
                    "mac_address": mac,
                    "rx_bps": 0.0,
                    "tx_bps": 0.0,
                },
            )["rx_bps"] = val * 8
        for labels, val in lv_tx_pairs:
            mac = (labels.get("mac_address") or "").lower()
            iid = labels.get("instance_id")
            info = mac_idx.get(mac)
            if not info or info["instance_id"] != iid:
                continue
            pid = info["port_id"]
            if pid in interfaces:
                interfaces[pid]["tx_bps"] = val * 8
            else:
                interfaces[pid] = {
                    "instance_id": iid,
                    "network_id": info["network_id"],
                    "mac_address": mac,
                    "rx_bps": 0.0,
                    "tx_bps": val * 8,
                }

        # interfaces → instances / networks 합산
        networks: dict[str, dict[str, float]] = {}
        for ent in interfaces.values():
            iid, nid = ent["instance_id"], ent["network_id"]
            inst = instances.setdefault(iid, {"rx_bps": 0.0, "tx_bps": 0.0})
            inst["rx_bps"] += ent["rx_bps"]
            inst["tx_bps"] += ent["tx_bps"]
            net = networks.setdefault(nid, {"rx_bps": 0.0, "tx_bps": 0.0})
            net["rx_bps"] += ent["rx_bps"]
            net["tx_bps"] += ent["tx_bps"]

        # node_exporter 결과 — libvirt 미관측 인스턴스 보강
        # 쿼리가 `sum by (instance_id, device)` 라 **device 마다 시계열이 하나씩** 온다 → 누산해야 한다.
        # 대입하면 마지막 device 만 남아 과소보고된다(제외 정규식은 k3s `flannel.1`,
        # Waygate `wg0`, `bond0` 를 못 막으므로 device 2개 이상인 VM 은 흔하다).
        # 히스토리 엔드포인트도 같은 규칙이며 두 값이 어긋나면 같은 패널에서 모순으로 보인다.
        ne_instances: dict[str, dict[str, float]] = {}
        for labels, val in rx_pairs:
            iid = labels.get("instance_id")
            if iid:
                ne_instances.setdefault(iid, {"rx_bps": 0.0, "tx_bps": 0.0})["rx_bps"] += val * 8
        for labels, val in tx_pairs:
            iid = labels.get("instance_id")
            if iid:
                ne_instances.setdefault(iid, {"rx_bps": 0.0, "tx_bps": 0.0})["tx_bps"] += val * 8
        for iid, ne_vals in ne_instances.items():
            if iid in instances:
                continue
            instances[iid] = ne_vals
            # 단일NIC 인스턴스만 networks 합산 (다중NIC는 귀속 네트워크 불명확)
            ports = instance_ports.get(iid, [])
            if len(ports) == 1:
                nid = port_map.get(ports[0], {}).get("network_id", "")
                if nid:
                    net = networks.setdefault(nid, {"rx_bps": 0.0, "tx_bps": 0.0})
                    net["rx_bps"] += ne_vals["rx_bps"]
                    net["tx_bps"] += ne_vals["tx_bps"]
    else:
        networks = {}

    # 3) LB stats — Octavia /stats 차분 (병렬)
    lbs = await asyncio.to_thread(list_load_balancers, conn, scope_project_id)

    async def _lb_one(lb_id: str) -> tuple[str, dict[str, float]] | None:
        cur = await asyncio.to_thread(get_lb_stats, conn, lb_id)
        if cur is None:
            return None
        return lb_id, lb_rate_from_snapshot(lb_id, cur)

    lb_results = await asyncio.gather(*(_lb_one(lb["id"]) for lb in lbs))
    load_balancers = {lid: rate for lid, rate in (r for r in lb_results if r)}

    return {
        "ts": int(time.time()),
        "instances": instances,
        "networks": networks,
        "interfaces": interfaces,
        "routers": {},  # Phase 2 — kolla ovs/libvirt exporter 활성화 후 채워짐
        "load_balancers": load_balancers,
        "_meta": {"router_traffic": "exporter_required"},
    }


# ---------------------------------------------------------------------------
# 네트워크 사용량 히스토리 (동적 `/{network_id}` 보다 먼저 등록)
# ---------------------------------------------------------------------------

# range → 총 구간 초. step 은 저장소 공용 `calc_step()`(최소 15s, 최대 100 포인트)을 쓴다 —
# 인스턴스 메트릭 차트와 같은 관례다. step 은 `TOPOLOGY_RATE_WINDOW` 이하라야 샘플 사이
# 트래픽이 그래프에서 빠지지 않는다(`calc_step` 은 1h 에서 36s 이므로 2m 윈도우 안에 든다).
_HISTORY_RANGES: dict[str, int] = {"15m": 900, "30m": 1800, "1h": 3600}


def _window_seconds() -> int:
    """`TOPOLOGY_RATE_WINDOW` 를 초로. 형식이 바뀌면 즉시 터지게 둔다."""
    m = re.fullmatch(r"(\d+)(s|m)", TOPOLOGY_RATE_WINDOW)
    if not m:
        raise ValueError(f"rate 윈도우 형식을 해석할 수 없다: {TOPOLOGY_RATE_WINDOW}")
    return int(m.group(1)) * (60 if m.group(2) == "m" else 1)


def _history_step(range_s: int) -> int:
    """히스토리 step. 계약은 `scrape ≤ step ≤ window` 다.

    상한(step ≤ window)을 어기면 샘플 사이 트래픽이 그래프에서 빠진다.
    하한(step ≥ scrape)을 어기면 **같은 값이 반복되는 계단**이 나온다 — 실측(scrape 60s)에서
    step 15s 는 인접 동일값 비율 72%, step 60s 는 12%(트래픽이 평평한 구간의 자연 기준선)였다.

    scrape 를 알 수 없으므로(저장소가 제어하지 않는다) 윈도우가 함의하는 최악을 하한으로 쓴다:
    윈도우는 `rate` 가 2 샘플을 담도록 `window ≥ 2 × scrape` 를 전제하므로 `scrape ≤ window/2` 다.
    """
    return max(calc_step(range_s), _window_seconds() // 2)


def _series_stats(series: list[dict[str, float]]) -> dict[str, dict[str, float] | None]:
    """series 에서 방향별 평균·최대·최근을 낸다. 표본이 없으면 각 항목 `None`(0 과 구분).

    별도 `avg_over_time` 쿼리를 쓰지 않는 이유: 윈도우 평균과 step 샘플 평균이 미묘하게 달라
    그래프 최고점과 라벨 숫자가 어긋난다. 라벨은 항상 **그려진 선과 같은 표본**에서 나와야 한다.
    """
    if not series:
        return {"avg": None, "max": None, "latest": None}
    n = len(series)
    return {
        "avg": {
            "rx_bps": sum(p["rx_bps"] for p in series) / n,
            "tx_bps": sum(p["tx_bps"] for p in series) / n,
        },
        # rx·tx 최대는 서로 다른 시점일 수 있다 — 각 방향의 독립적인 최고값이다.
        "max": {
            "rx_bps": max(p["rx_bps"] for p in series),
            "tx_bps": max(p["tx_bps"] for p in series),
        },
        "latest": {"rx_bps": series[-1]["rx_bps"], "tx_bps": series[-1]["tx_bps"]},
    }


@router.get("/topology/traffic/history")
async def get_topology_traffic_history(
    network_id: str = Query(..., description="히스토리를 조회할 네트워크 ID"),
    range: Literal["15m", "30m", "1h"] = Query("15m", description="조회 구간"),
    all_projects: bool = Query(False, description="admin 전용: 모든 프로젝트 포트 대상"),
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
) -> dict:
    """네트워크 1개의 rx/tx bps 시계열 + avg/max 통계.

    instant 엔드포인트(`/topology/traffic`)와 **같은 귀속 규칙**을 쓴다. 즉 이 값은 해당
    네트워크에 붙은 NIC 들의 합이며 라우터↔스위치 트래픽이 아니다(라우터 exporter 없음).
    같은 이유로 east-west(내부 인스턴스 간) 트래픽도 포함된다.

    설계 메모:
    - **패널을 열 때 1회** 호출용이다. 폴링 루프에 넣으면 Prometheus 부하가 네트워크 수만큼 곱해진다.
    - avg/max 는 별도 `*_over_time` 쿼리가 아니라 **반환한 series 에서 계산**한다. 두 소스를 쓰면
      그래프 최고점과 라벨 숫자가 어긋난다.
    - stats 는 **방향별**(rx/tx)이다. instant 엔드포인트가 방향별 값을 주므로 합계로 내보내면
      같은 패널에서 `▼ 5.8M ▲ 2.0M` 옆에 `7.8M` 이 붙어 사용자가 대조할 수 없다.
      `max` 의 rx·tx 는 서로 다른 시점일 수 있다(각 방향의 독립적인 최고값).
    - 현재 포트맵에 없는(삭제된) 인스턴스의 과거 트래픽은 귀속 대상이 없어 빠진다 — instant 도 동일.

    반환: { network_id, range, step_s, window, series: [{ts, rx_bps, tx_bps}],
            stats: {avg, max, latest} (각각 {rx_bps, tx_bps} 또는 null), _meta }
    """
    ctx = await _load_port_context(conn, token_info, all_projects)
    range_s = _HISTORY_RANGES[range]
    step_s = _history_step(range_s)
    end_ts = int(time.time())
    start_ts = end_ts - range_s

    rx: dict[int, float] = {}
    tx: dict[int, float] = {}

    if ctx.instance_ids:
        rx_q, tx_q, lv_rx_q, lv_tx_q = _traffic_exprs(ctx.instance_ids)

        span = {"start_ts": start_ts, "end_ts": end_ts, "step_s": step_s}
        try:
            ne_rx, ne_tx, lv_rx, lv_tx = await asyncio.gather(
                query_range_multi(rx_q, **span),
                query_range_multi(tx_q, **span),
                query_range_multi(lv_rx_q, **span),
                query_range_multi(lv_tx_q, **span),
            )
        except (PromUnavailable, PromBadQuery) as exc:
            _logger.warning("토폴로지 트래픽 히스토리 PromQL 실패 — 빈 series: %s", exc)
            ne_rx = ne_tx = lv_rx = lv_tx = []

        # libvirt (주 경로): mac → port → network_id 로 이 네트워크의 NIC 만 골라 ts 별 합산.
        # 네트워크 필터보다 먼저 observed 에 담는다 — node 폴백은 "libvirt 가 못 본 인스턴스" 기준이다.
        observed: set[str] = set()
        for pairs, sink in ((lv_rx, rx), (lv_tx, tx)):
            for labels, samples in pairs:
                mac = (labels.get("mac_address") or "").lower()
                iid = labels.get("instance_id")
                info = ctx.mac_idx.get(mac)
                if not info or info["instance_id"] != iid:
                    continue
                observed.add(iid)
                if info["network_id"] != network_id:
                    continue
                for ts, val in samples:
                    sink[ts] = sink.get(ts, 0.0) + val * 8

        # node_exporter 폴백: libvirt 미관측 + 단일 NIC 인스턴스만.
        # 다중 NIC 는 device 이름으로 네트워크를 가릴 수 없어 제외한다(instant 와 동일 규칙).
        for pairs, sink in ((ne_rx, rx), (ne_tx, tx)):
            for labels, samples in pairs:
                iid = labels.get("instance_id") or ""
                if not iid or iid in observed:
                    continue
                ports = ctx.instance_ports.get(iid, [])
                if len(ports) != 1 or ctx.port_map.get(ports[0], {}).get("network_id") != network_id:
                    continue
                for ts, val in samples:
                    sink[ts] = sink.get(ts, 0.0) + val * 8

    series = [{"ts": ts, "rx_bps": rx.get(ts, 0.0), "tx_bps": tx.get(ts, 0.0)} for ts in sorted(set(rx) | set(tx))]
    return {
        "network_id": network_id,
        "range": range,
        "step_s": step_s,
        "window": TOPOLOGY_RATE_WINDOW,
        "series": series,
        "stats": _series_stats(series),
        "_meta": {"source": "network_nic_sum", "router_traffic": "exporter_required"},
    }


# ---------------------------------------------------------------------------
# 포트 목록 (동적 경로보다 먼저 등록)
# ---------------------------------------------------------------------------


@router.get("/ports", response_model=list[dict])
async def list_ports(conn: openstack.connection.Connection = Depends(get_os_conn)):
    """현재 프로젝트의 포트 목록."""
    project_id = conn._afterglow_project_id
    try:

        def _list():
            return [
                {
                    "id": p.id,
                    "name": p.name or "",
                    "status": p.status,
                    "mac_address": p.mac_address,
                    "fixed_ips": p.fixed_ips or [],
                    "network_id": p.network_id or "",
                    "device_owner": p.device_owner or "",
                    "device_id": p.device_id or "",
                }
                for p in conn.network.ports(project_id=project_id)
            ]

        return await asyncio.to_thread(_list)
    except Exception:
        _logger.exception("포트 목록 조회 실패")
        raise HTTPException(status_code=500, detail="포트 조회 실패")


# ---------------------------------------------------------------------------
# 네트워크 상세 (동적 경로 - 마지막에 등록)
# ---------------------------------------------------------------------------


@router.get("/{network_id}", response_model=NetworkDetail)
async def get_network(
    network_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    try:
        net = await asyncio.to_thread(conn.network.get_network, network_id)
    except Exception:
        raise HTTPException(status_code=404, detail="네트워크를 찾을 수 없습니다")
    # 외부/공유 네트워크는 cross-project 정상 노출이므로 owner check 면제
    if not (getattr(net, "is_router_external", False) or getattr(net, "is_shared", False)):
        assert_resource_owner(net, conn, token_info, not_found_detail="네트워크를 찾을 수 없습니다")
    try:
        return await asyncio.to_thread(neutron.get_network_detail, conn, network_id)
    except Exception:
        raise HTTPException(status_code=404, detail="네트워크를 찾을 수 없습니다")


@router.delete("/{network_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_network(
    request: Request,
    network_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    try:
        net = await asyncio.to_thread(conn.network.get_network, network_id)
    except Exception:
        raise HTTPException(status_code=404, detail="네트워크를 찾을 수 없습니다")
    assert_resource_owner(net, conn, token_info, not_found_detail="네트워크를 찾을 수 없습니다")
    try:
        await asyncio.to_thread(neutron.delete_network, conn, network_id)
        await rec(token_info, conn, resource_type="network", action="delete", resource_id=network_id)
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="network",
            action="delete",
            status="failed",
            resource_id=network_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="네트워크 삭제 실패")


@router.post("/{network_id}/subnets", response_model=SubnetDetail, status_code=201)
@limiter.limit("10/minute")
async def create_subnet(
    request: Request,
    network_id: str,
    req: CreateSubnetRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    try:
        result = await asyncio.to_thread(
            neutron.create_subnet,
            conn,
            network_id,
            req.name,
            req.cidr,
            req.gateway_ip,
            req.enable_dhcp,
        )
        await rec(
            token_info,
            conn,
            resource_type="subnet",
            action="create",
            resource_name=req.name,
            resource_id=result.id if hasattr(result, "id") else None,
        )
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="subnet",
            action="create",
            status="failed",
            resource_name=req.name,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="서브넷 생성 실패")
