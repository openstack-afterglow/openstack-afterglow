from __future__ import annotations

import ipaddress
import logging as _logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import openstack

from app.models.storage import (
    AdminNetworkDetail,
    AdminSubnetDetail,
    AdminSubnetPort,
    AdminTopologyData,
    AdminTopologyNetwork,
    AllocationPool,
    DhcpBindingInfo,
    FloatingIpInfo,
    NetworkDetail,
    NetworkInfo,
    RouterDetail,
    RouterInfo,
    RouterInterface,
    SubnetDetail,
    SubnetIpAllocation,
    TopologyData,
    TopologyNetwork,
    TopologyRouter,
)
from app.services.parallel import run_parallel

_ROUTER_IFACE_OWNERS = [
    "network:router_interface",
    "network:router_interface_distributed",
    "network:ha_router_replicated_interface",
]

# build_compute_port_index 가 실제로 읽는 속성. Neutron 응답 직렬화 비용을 줄인다.
_COMPUTE_PORT_FIELDS = ["id", "device_id", "device_owner", "network_id", "mac_address", "fixed_ips"]

# afterglow가 자동 생성한 Security Group을 식별하는 description 접미어.
# orphan 검출에서 이 마커가 있는 SG만 cleanup 후보로 한정한다 (사용자 SG 보호).
AFTERGLOW_MANAGED_TAG = "[afterglow-managed]"


def _iter_router_interface_ports(conn, **kwargs):
    """DVR/HA를 포함한 모든 라우터 인터페이스 포트를 순회."""
    for owner in _ROUTER_IFACE_OWNERS:
        yield from conn.network.ports(device_owner=owner, **kwargs)


def list_networks(conn: openstack.connection.Connection, project_id: str | None = None) -> list[NetworkInfo]:
    all_networks = list(conn.network.networks())
    visible_networks = []
    for n in all_networks:
        if project_id and not (
            bool(getattr(n, "is_router_external", False))
            or bool(getattr(n, "is_shared", False))
            or getattr(n, "project_id", None) == project_id
        ):
            continue
        visible_networks.append(n)

    all_subnets = list(conn.network.subnets())

    visible_net_ids = {n.id for n in visible_networks}
    net_cidrs_map: dict[str, set[str]] = {}
    for s in all_subnets:
        net_id = getattr(s, "network_id", None)
        cidr = getattr(s, "cidr", None)
        if net_id and net_id in visible_net_ids and cidr:
            if net_id not in net_cidrs_map:
                net_cidrs_map[net_id] = set()
            net_cidrs_map[net_id].add(cidr)

    result = []
    for n in visible_networks:
        cidrs = _sort_cidrs(net_cidrs_map.get(n.id, set()))
        result.append(_net_to_info(n, cidrs))
    return result


def get_network(conn: openstack.connection.Connection, network_id: str) -> NetworkInfo:
    n = conn.network.get_network(network_id)
    return _net_to_info(n)


def _serialize_network_detail(conn: openstack.connection.Connection, n: Any) -> NetworkDetail:
    subnet_details = []
    for subnet_id in getattr(n, "subnet_ids", None) or []:
        try:
            s = conn.network.get_subnet(subnet_id)
            subnet_details.append(
                SubnetDetail(
                    id=s.id,
                    name=s.name or "",
                    cidr=s.cidr or "",
                    gateway_ip=s.gateway_ip,
                    dhcp_enabled=bool(s.is_dhcp_enabled),
                )
            )
        except Exception:
            continue

    # 이 네트워크에 연결된 라우터 찾기 (router_interface 포트 기준)
    router_map: dict[str, RouterInfo] = {}
    try:
        ports = list(_iter_router_interface_ports(conn, network_id=n.id))
        for port in ports:
            router_id = port.device_id
            if not router_id:
                continue
            if router_id not in router_map:
                try:
                    r = conn.network.get_router(router_id)
                    ext_net_id = None
                    if r.external_gateway_info:
                        ext_net_id = r.external_gateway_info.get("network_id")
                    router_map[router_id] = RouterInfo(
                        id=r.id,
                        name=r.name or "",
                        external_gateway_network_id=ext_net_id,
                        connected_subnet_ids=[],
                    )
                except Exception:
                    continue
            # 포트의 fixed_ips에서 서브넷 ID 추출
            for fixed_ip in port.fixed_ips or []:
                sid = fixed_ip.get("subnet_id")
                if sid and sid not in router_map[router_id].connected_subnet_ids:
                    router_map[router_id].connected_subnet_ids.append(sid)
    except Exception:
        pass

    return NetworkDetail(
        id=n.id,
        name=n.name or "",
        status=n.status,
        subnets=list(getattr(n, "subnet_ids", None) or []),
        is_external=bool(getattr(n, "is_router_external", False)),
        is_shared=bool(getattr(n, "is_shared", False)),
        subnet_details=subnet_details,
        routers=list(router_map.values()),
    )


def get_network_detail(conn: openstack.connection.Connection, network_id: str) -> NetworkDetail:
    n = conn.network.get_network(network_id)
    return _serialize_network_detail(conn, n)


def get_admin_network_detail(conn: openstack.connection.Connection, network_id: str) -> AdminNetworkDetail:
    n = conn.network.get_network(network_id)
    base_detail = _serialize_network_detail(conn, n)
    seg_id = getattr(n, "provider_segmentation_id", None)
    if seg_id is not None:
        try:
            seg_id = int(seg_id)
        except (ValueError, TypeError):
            seg_id = None

    return AdminNetworkDetail(
        **base_detail.model_dump(),
        provider_network_type=getattr(n, "provider_network_type", None),
        provider_segmentation_id=seg_id,
        provider_physical_network=getattr(n, "provider_physical_network", None),
    )


def _ip_address_key(ip_str: str) -> tuple[int, int, str]:
    try:
        address = ipaddress.ip_address(ip_str)
        return (address.version, int(address), "")
    except (ValueError, TypeError):
        return (99, 0, str(ip_str))


def get_admin_subnet_detail(conn: openstack.connection.Connection, subnet_id: str) -> AdminSubnetDetail:
    subnet = conn.network.get_subnet(subnet_id)
    network = conn.network.get_network(subnet.network_id)

    raw_pools = getattr(subnet, "allocation_pools", []) or []
    allocation_pools: list[AllocationPool] = []
    for p in raw_pools:
        if isinstance(p, dict):
            s_ip = p.get("start")
            e_ip = p.get("end")
        else:
            s_ip = getattr(p, "start", None)
            e_ip = getattr(p, "end", None)
        if s_ip and e_ip:
            allocation_pools.append(AllocationPool(start=str(s_ip), end=str(e_ip)))
    allocation_pools.sort(key=lambda ap: _ip_address_key(ap.start))

    raw_ports = list(conn.network.ports(network_id=subnet.network_id))
    subnet_ports: list[AdminSubnetPort] = []
    allocations: list[SubnetIpAllocation] = []
    dhcp_ports: list[tuple[Any, list[str]]] = []

    for port in raw_ports:
        port_id = getattr(port, "id", "") or (port.get("id") if isinstance(port, dict) else "")
        port_name = getattr(port, "name", "") or (port.get("name") if isinstance(port, dict) else "") or ""
        port_status = getattr(port, "status", "") or (port.get("status") if isinstance(port, dict) else "") or ""
        mac_address = (
            getattr(port, "mac_address", "") or (port.get("mac_address") if isinstance(port, dict) else "") or ""
        )
        device_owner = (
            getattr(port, "device_owner", "") or (port.get("device_owner") if isinstance(port, dict) else "") or ""
        )
        device_id = getattr(port, "device_id", "") or (port.get("device_id") if isinstance(port, dict) else "") or ""
        project_id = (
            getattr(port, "project_id", None)
            or getattr(port, "tenant_id", None)
            or (port.get("project_id") or port.get("tenant_id") if isinstance(port, dict) else None)
        )
        binding_host_id = (
            getattr(port, "binding_host_id", None)
            or getattr(port, "binding:host_id", None)
            or (port.get("binding:host_id") or port.get("binding_host_id") if isinstance(port, dict) else None)
        )

        fixed_ips = getattr(port, "fixed_ips", []) or (port.get("fixed_ips") if isinstance(port, dict) else []) or []
        subnet_ips: list[str] = []
        for f in fixed_ips:
            if isinstance(f, dict):
                f_sub = f.get("subnet_id")
                f_ip = f.get("ip_address")
            else:
                f_sub = getattr(f, "subnet_id", None)
                f_ip = getattr(f, "ip_address", None)
            if f_sub == subnet_id and f_ip:
                subnet_ips.append(str(f_ip))

        if not subnet_ips:
            continue

        subnet_ips.sort(key=_ip_address_key)

        subnet_ports.append(
            AdminSubnetPort(
                id=port_id,
                name=port_name,
                status=port_status,
                mac_address=mac_address,
                device_owner=device_owner,
                device_id=device_id,
                project_id=project_id,
                ip_addresses=subnet_ips,
                binding_host_id=binding_host_id,
            )
        )

        for ip in subnet_ips:
            allocations.append(
                SubnetIpAllocation(
                    ip_address=ip,
                    port_id=port_id,
                    port_name=port_name,
                    device_owner=device_owner,
                    device_id=device_id,
                    project_id=project_id,
                    binding_host_id=binding_host_id,
                )
            )

        if device_owner.startswith("network:dhcp"):
            dhcp_ports.append((port, subnet_ips))

    subnet_ports.sort(key=lambda p: p.id)
    allocations.sort(key=lambda a: (_ip_address_key(a.ip_address), a.port_id))

    dhcp_agent_data_available = True
    agents = []
    try:
        agents = list(conn.network.network_hosting_dhcp_agents(network.id))
    except Exception:
        dhcp_agent_data_available = False

    dhcp_bindings: list[DhcpBindingInfo] = []
    matched_dhcp_port_ids: set[str] = set()

    if dhcp_agent_data_available and agents:
        for agent in agents:
            ag_id = getattr(agent, "id", None) or (agent.get("id") if isinstance(agent, dict) else None)
            ag_host = getattr(agent, "host", None) or (agent.get("host") if isinstance(agent, dict) else None)
            ag_binary = getattr(agent, "binary", None) or (agent.get("binary") if isinstance(agent, dict) else None)
            ag_az = getattr(agent, "availability_zone", None) or (
                agent.get("availability_zone") if isinstance(agent, dict) else None
            )
            ag_alive = getattr(agent, "is_alive", None)
            if ag_alive is None:
                ag_alive = getattr(agent, "alive", None)
            if ag_alive is None and isinstance(agent, dict):
                ag_alive = agent.get("is_alive") if "is_alive" in agent else agent.get("alive")

            ag_admin_up = getattr(agent, "is_admin_state_up", None)
            if ag_admin_up is None:
                ag_admin_up = getattr(agent, "admin_state_up", None)
            if ag_admin_up is None and isinstance(agent, dict):
                ag_admin_up = (
                    agent.get("is_admin_state_up") if "is_admin_state_up" in agent else agent.get("admin_state_up")
                )

            ag_ips: list[str] = []
            ag_port_ids: list[str] = []
            for d_port, d_ips in dhcp_ports:
                dp_id = getattr(d_port, "id", "") or (d_port.get("id") if isinstance(d_port, dict) else "")
                dp_host = (
                    getattr(d_port, "binding_host_id", None)
                    or getattr(d_port, "binding:host_id", None)
                    or (
                        d_port.get("binding:host_id") or d_port.get("binding_host_id")
                        if isinstance(d_port, dict)
                        else None
                    )
                )
                dp_dev_id = getattr(d_port, "device_id", "") or (
                    d_port.get("device_id") if isinstance(d_port, dict) else ""
                )

                is_match = bool(
                    (ag_host and dp_host and ag_host == dp_host)
                    or (ag_id and dp_dev_id and (ag_id in dp_dev_id or dp_dev_id in ag_id))
                    or (ag_host and dp_dev_id and ag_host in dp_dev_id)
                )

                if is_match:
                    matched_dhcp_port_ids.add(dp_id)
                    ag_port_ids.append(dp_id)
                    ag_ips.extend(d_ips)

            ag_ips = sorted(list(set(ag_ips)), key=_ip_address_key)
            ag_port_ids = sorted(list(set(ag_port_ids)))

            dhcp_bindings.append(
                DhcpBindingInfo(
                    agent_id=ag_id,
                    host=ag_host,
                    binary=ag_binary,
                    availability_zone=ag_az,
                    alive=ag_alive,
                    admin_state_up=ag_admin_up,
                    source="agent",
                    ip_addresses=ag_ips,
                    port_ids=ag_port_ids,
                )
            )

    for d_port, d_ips in dhcp_ports:
        dp_id = getattr(d_port, "id", "") or (d_port.get("id") if isinstance(d_port, dict) else "")
        if dp_id not in matched_dhcp_port_ids:
            dp_host = (
                getattr(d_port, "binding_host_id", None)
                or getattr(d_port, "binding:host_id", None)
                or (
                    d_port.get("binding:host_id") or d_port.get("binding_host_id") if isinstance(d_port, dict) else None
                )
            )
            dhcp_bindings.append(
                DhcpBindingInfo(
                    agent_id=None,
                    host=dp_host,
                    binary=None,
                    availability_zone=None,
                    alive=None,
                    admin_state_up=None,
                    source="port",
                    ip_addresses=sorted(d_ips, key=_ip_address_key),
                    port_ids=[dp_id],
                )
            )

    dhcp_bindings.sort(
        key=lambda b: (
            0 if b.source == "agent" else 1,
            b.host or "",
            b.agent_id or "",
            b.port_ids[0] if b.port_ids else "",
        )
    )

    proj_id = (
        getattr(subnet, "project_id", None)
        or getattr(subnet, "tenant_id", None)
        or (subnet.get("project_id") or subnet.get("tenant_id") if isinstance(subnet, dict) else None)
    )
    gw_ip = getattr(subnet, "gateway_ip", None) or (subnet.get("gateway_ip") if isinstance(subnet, dict) else None)
    ip_ver = getattr(subnet, "ip_version", 4) or (subnet.get("ip_version") if isinstance(subnet, dict) else 4) or 4
    dhcp_en = getattr(subnet, "is_dhcp_enabled", None)
    if dhcp_en is None:
        dhcp_en = getattr(subnet, "enable_dhcp", True)
    if dhcp_en is None and isinstance(subnet, dict):
        dhcp_en = subnet.get("is_dhcp_enabled") if "is_dhcp_enabled" in subnet else subnet.get("enable_dhcp", True)

    return AdminSubnetDetail(
        id=subnet.id if hasattr(subnet, "id") else subnet["id"],
        name=getattr(subnet, "name", "") or (subnet.get("name") if isinstance(subnet, dict) else "") or "",
        network_id=network.id if hasattr(network, "id") else network["id"],
        network_name=getattr(network, "name", "") or (network.get("name") if isinstance(network, dict) else "") or "",
        project_id=proj_id,
        cidr=getattr(subnet, "cidr", "") or (subnet.get("cidr") if isinstance(subnet, dict) else "") or "",
        gateway_ip=str(gw_ip) if gw_ip else None,
        ip_version=int(ip_ver),
        dhcp_enabled=bool(dhcp_en),
        allocation_pools=allocation_pools,
        ports=subnet_ports,
        allocations=allocations,
        dhcp_bindings=dhcp_bindings,
        dhcp_agent_data_available=dhcp_agent_data_available,
    )


def create_network(conn: openstack.connection.Connection, name: str) -> NetworkInfo:
    n = conn.network.create_network(name=name)
    return _net_to_info(n)


def delete_network(conn: openstack.connection.Connection, network_id: str) -> None:
    conn.network.delete_network(network_id, ignore_missing=True)


def create_subnet(
    conn: openstack.connection.Connection,
    network_id: str,
    name: str,
    cidr: str,
    gateway_ip: str | None = None,
    enable_dhcp: bool = True,
) -> SubnetDetail:
    kwargs = {
        "network_id": network_id,
        "name": name,
        "cidr": cidr,
        "ip_version": 4,
        "is_dhcp_enabled": enable_dhcp,
    }
    if gateway_ip:
        kwargs["gateway_ip"] = gateway_ip
    s = conn.network.create_subnet(**kwargs)
    return SubnetDetail(
        id=s.id,
        name=s.name or "",
        cidr=s.cidr or "",
        gateway_ip=s.gateway_ip,
        dhcp_enabled=bool(s.is_dhcp_enabled),
    )


def delete_subnet(conn: openstack.connection.Connection, subnet_id: str) -> None:
    conn.network.delete_subnet(subnet_id, ignore_missing=True)


def update_subnet(
    conn: openstack.connection.Connection,
    subnet_id: str,
    name: str | None = None,
    gateway_ip: str | None = None,
    enable_dhcp: bool | None = None,
) -> SubnetDetail:
    kwargs: dict = {}
    if name is not None:
        kwargs["name"] = name
    if gateway_ip is not None:
        kwargs["gateway_ip"] = gateway_ip
    if enable_dhcp is not None:
        kwargs["is_dhcp_enabled"] = enable_dhcp
    s = conn.network.update_subnet(subnet_id, **kwargs)
    return SubnetDetail(
        id=s.id,
        name=s.name or "",
        cidr=s.cidr or "",
        gateway_ip=s.gateway_ip,
        dhcp_enabled=bool(s.is_dhcp_enabled),
    )


def create_port(
    conn: openstack.connection.Connection,
    network_id: str,
    name: str,
    security_group_ids: list[str] | None = None,
) -> dict:
    """Neutron 포트를 생성하고 { id, fixed_ip } 를 반환한다.

    IP 예약 후 server에 attach 할 수 있어 Manila access rule에 고정 IP를 사전 등록할 때 사용.
    """
    kwargs: dict = {"network_id": network_id, "name": name}
    if security_group_ids:
        # Neutron 포트 API의 security_groups는 UUID 문자열 리스트를 요구한다.
        # dict({"id": ...}) 형식은 400 "is not a valid UUID"로 거부됨.
        kwargs["security_groups"] = list(security_group_ids)
    port = conn.network.create_port(**kwargs)
    fixed_ip = ""
    if port.fixed_ips:
        fixed_ip = port.fixed_ips[0].get("ip_address", "")
    return {"id": port.id, "fixed_ip": fixed_ip}


def delete_port(conn: openstack.connection.Connection, port_id: str) -> None:
    conn.network.delete_port(port_id, ignore_missing=True)


def cleanup_instance_fips(conn: openstack.connection.Connection, instance_id: str) -> None:
    """인스턴스 포트에 연결된 Floating IP만 해제하고 삭제한다.

    Neutron /v2.0/floatingips 는 device_id 필터를 지원하지 않으므로
    포트 기반으로 대상 FIP를 식별한다 (Nova가 인스턴스 포트에 device_id를 세팅).
    """
    log = _logging.getLogger(__name__)
    try:
        ports = list(conn.network.ports(device_id=instance_id))
    except Exception:
        log.warning("cleanup_instance_fips: 포트 조회 실패 (instance=%s)", instance_id, exc_info=True)
        return
    port_ids = {p.id for p in ports}
    if not port_ids:
        return
    try:
        fips = [f for f in conn.network.ips() if f.port_id in port_ids]
    except Exception:
        log.warning("cleanup_instance_fips: FIP 조회 실패 (instance=%s)", instance_id, exc_info=True)
        return
    for fip in fips:
        try:
            conn.network.update_ip(fip.id, port_id=None)
            conn.network.delete_ip(fip.id, ignore_missing=True)
        except Exception:
            log.warning("cleanup_instance_fips: FIP %s 정리 실패", fip.id, exc_info=True)


# ---------------------------------------------------------------------------
# Floating IP
# ---------------------------------------------------------------------------


def get_network_quota(conn: openstack.connection.Connection, project_id: str, *, strict: bool = False) -> dict:
    """프로젝트의 Neutron 할당량 (limit + in_use) 조회."""

    keys = ["floatingip", "security_group", "security_group_rule", "network", "port", "router", "subnet"]

    def _q(q, key):
        if isinstance(q, dict):
            value = q.get(key)
            if isinstance(value, dict):
                return {"limit": value.get("limit", -1), "in_use": value.get("used", value.get("in_use", 0))}
            return {"limit": int(value) if value is not None else -1, "in_use": 0}
        value = getattr(q, key, None)
        if isinstance(value, dict):
            return {"limit": value.get("limit", -1), "in_use": value.get("used", value.get("in_use", 0))}
        return {"limit": int(value) if value is not None else -1, "in_use": 0}

    def _strict_floatingip(raw: object) -> dict:
        if not isinstance(raw, dict) or "limit" not in raw:
            raise ValueError("Neutron floatingip limit is missing")
        usage_key = "used" if "used" in raw else "in_use" if "in_use" in raw else None
        if usage_key is None:
            raise ValueError("Neutron floatingip usage is missing")
        limit, in_use = raw["limit"], raw[usage_key]
        if (
            not isinstance(limit, (int, float))
            or isinstance(limit, bool)
            or not isinstance(in_use, (int, float))
            or isinstance(in_use, bool)
        ):
            raise ValueError("Neutron floatingip quota data is malformed")
        return {"limit": limit, "in_use": in_use}

    try:
        # details=True is the only source accepted in strict mode because it
        # carries usage; the non-detailed legacy fallback is limit-only.
        quota = conn.network.get_quota(project_id, details=True)
        if hasattr(quota, "to_dict"):
            quota_dict = quota.to_dict(original_names=True)
        else:
            quota_dict = {}
        if strict:
            result = {key: _q(quota_dict, key) for key in keys}
            result["floatingip"] = _strict_floatingip(quota_dict.get("floatingip"))
            return result
        result = {key: _q(quota_dict, key) for key in keys}
        if result["floatingip"]["in_use"] == 0:
            try:
                result["floatingip"]["in_use"] = sum(1 for _ in conn.network.ips(project_id=project_id))
            except Exception:
                pass
        if result["port"]["in_use"] == 0:
            try:
                result["port"]["in_use"] = sum(1 for _ in conn.network.ports(project_id=project_id))
            except Exception:
                pass
        return result
    except Exception:
        if strict:
            raise
        import logging as _logging

        _logging.getLogger(__name__).warning("Neutron quota details 조회 실패 — fallback", exc_info=True)
        try:
            quota = conn.network.get_quota(project_id)
            quota_dict = quota.to_dict(original_names=True) if hasattr(quota, "to_dict") else {}
            return {
                key: {"limit": int(quota_dict.get(key, -1)) if quota_dict.get(key) is not None else -1, "in_use": 0}
                for key in keys
            }
        except Exception:
            return {key: {"limit": -1, "in_use": 0} for key in keys}


def list_floating_ips(conn: openstack.connection.Connection, project_id: str | None = None) -> list[FloatingIpInfo]:
    kwargs: dict = {}
    if project_id:
        kwargs["project_id"] = project_id
    fips = list(conn.network.ips(**kwargs))
    if not fips:
        return []

    needed_port_ids = {f.port_id for f in fips if getattr(f, "port_id", None)}
    port_to_instance: dict[str, str] = {}
    if needed_port_ids:
        # FIP 에 붙은 포트만 id 로 직접 조회한다. 전체 포트 목록을 받아 필터링하면
        # 대규모 클라우드에서 이 한 번의 호출이 초 단위로 늘어난다.
        port_kwargs: dict = {"id": sorted(needed_port_ids), "fields": ["id", "device_id", "device_owner"]}
        if project_id:
            port_kwargs["project_id"] = project_id
        for p in conn.network.ports(**port_kwargs):
            if p.id in needed_port_ids and p.device_id and (p.device_owner or "").startswith("compute:"):
                port_to_instance[p.id] = p.device_id

    instance_to_name: dict[str, str] = {}
    needed_instance_ids = set(port_to_instance.values())
    if needed_instance_ids:
        # 이름만 필요하므로 detail 없는 목록으로 충분하다.
        srv_kwargs: dict = {"details": False}
        if project_id:
            srv_kwargs["project_id"] = project_id
        for s in conn.compute.servers(**srv_kwargs):
            if s.id in needed_instance_ids:
                instance_to_name[s.id] = s.name or ""

    out: list[FloatingIpInfo] = []
    for f in fips:
        info = _fip_to_info(f)
        inst_id = port_to_instance.get(getattr(f, "port_id", None) or "") or None
        if inst_id:
            info.instance_id = inst_id
            info.instance_name = instance_to_name.get(inst_id)
        out.append(info)
    return out


def create_floating_ip(conn: openstack.connection.Connection, floating_network_id: str) -> FloatingIpInfo:
    fip = conn.network.create_ip(floating_network_id=floating_network_id)
    return _fip_to_info(fip)


def find_external_network_for_subnets(
    conn: openstack.connection.Connection,
    subnet_ids: set[str],
) -> str | None:
    """주어진 서브넷에 라우터 인터페이스로 연결된 외부 게이트웨이 네트워크 ID를 반환.

    - 라우터의 external_gateway_info.network_id를 사용해 reachable한 외부망을 결정.
    - 매칭 라우터가 없거나 라우터에 외부 게이트웨이가 설정되지 않았으면 None.
    """
    if not subnet_ids:
        return None
    candidate_router_ids: set[str] = set()
    for iface_port in _iter_router_interface_ports(conn):
        iface_subnet_ids = {fi.get("subnet_id") for fi in (iface_port.fixed_ips or [])}
        if iface_subnet_ids & subnet_ids and iface_port.device_id:
            candidate_router_ids.add(iface_port.device_id)
    if not candidate_router_ids:
        return None
    for router in conn.network.routers():
        if router.id in candidate_router_ids and router.external_gateway_info:
            ext_net_id = router.external_gateway_info.get("network_id")
            if ext_net_id:
                return ext_net_id
    return None


def associate_floating_ip(
    conn: openstack.connection.Connection,
    floating_ip_id: str,
    instance_id: str,
    port_id: str | None = None,
) -> FloatingIpInfo:
    """인스턴스 포트에 floating IP 연결. port_id 미지정 시 FIP 미점유 첫 포트를 선택한다."""
    if not port_id:
        ports = list(conn.network.ports(device_id=instance_id))
        if not ports:
            raise RuntimeError("인스턴스에 연결된 포트가 없습니다")
        used_port_ids = {f.port_id for f in conn.network.ips() if f.port_id}
        available = [p for p in ports if p.id not in used_port_ids]
        if not available:
            raise RuntimeError("모든 인터페이스에 이미 Floating IP가 할당되어 있습니다")
        port_id = available[0].id
    fip = conn.network.update_ip(floating_ip_id, port_id=port_id)
    return _fip_to_info(fip)


def disassociate_floating_ip(conn: openstack.connection.Connection, floating_ip_id: str) -> FloatingIpInfo:
    fip = conn.network.update_ip(floating_ip_id, port_id=None)
    return _fip_to_info(fip)


def delete_floating_ip(conn: openstack.connection.Connection, floating_ip_id: str) -> None:
    conn.network.delete_ip(floating_ip_id, ignore_missing=True)


def _coerce_int(value: Any) -> int | None:
    """OpenStack 속성값을 int 로 안전하게 변환 (실패 시 None)."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _normalize_router_routes(raw_routes: Any) -> list[dict]:
    """라우터 정적 경로를 [{destination, nexthop}] 로 정규화. 형식이 어긋난 항목은 건너뛴다."""
    routes: list[dict] = []
    for entry in raw_routes or []:
        if not isinstance(entry, dict):
            continue
        destination = entry.get("destination")
        nexthop = entry.get("nexthop")
        if not destination or not nexthop:
            continue
        routes.append({"destination": str(destination), "nexthop": str(nexthop)})
    return routes


def build_compute_port_index(conn: openstack.connection.Connection) -> dict[tuple[str, str], dict]:
    """compute 포트를 한 번 순회해 (device_id, ip_address) → 포트 메타 인덱스를 만든다.

    토폴로지 핸들러(user/admin)가 인스턴스 ip_addresses 에 network_id/port_id/mac_address 를
    조인할 때 공유한다. device_owner 가 ``compute:`` 로 시작하고 device_id 가 있는 포트만 포함한다.
    Neutron 이 포트당 직렬화하는 속성 수가 응답 시간을 지배하므로 필요한 필드만 요청한다
    (``device_owner`` prefix 매칭이 필요해 서버측 device_owner 필터는 쓰지 않는다).
    """
    index: dict[tuple[str, str], dict] = {}
    for p in conn.network.ports(fields=_COMPUTE_PORT_FIELDS):
        dev_owner = p.device_owner or ""
        if not p.device_id or not dev_owner.startswith("compute:"):
            continue
        for fip in p.fixed_ips or []:
            ip = fip.get("ip_address")
            if ip:
                index[(p.device_id, ip)] = {
                    "network_id": p.network_id,
                    "port_id": p.id,
                    "mac_address": getattr(p, "mac_address", None),
                }
    return index


def get_topology(
    conn: openstack.connection.Connection, *, include_provider: bool = False, project_id: str | None = None
) -> TopologyData:
    """배치 조회로 전체 토폴로지 데이터를 수집. 독립 조회는 스레드로 동시에 수행한다.

    ``project_id`` 가 주어지면 Floating IP는 해당 프로젝트 소유분만 조회한다(사용자 scope).

    mtu / enable_snat / routes 는 이미 조회한 객체의 속성에서 채우므로 추가 호출이 없다.
    ``include_provider=True`` 이면 네트워크를 ``AdminTopologyNetwork`` (provider 세그먼트 메타 포함)로
    직렬화해 ``AdminTopologyData`` 를 반환한다. 기본값은 provider 키가 없는 ``TopologyData`` 이다.
    """
    # 1. 서로 의존하지 않는 조회(네트워크/서브넷/라우터/FIP/라우터 인터페이스 포트)를 동시에 수행.
    #    직렬 호출은 각 응답 시간이 그대로 합산돼 대규모 클라우드에서 토폴로지 응답이 수 초로 늘어난다.
    iface_port_calls = [
        (lambda owner=owner: list(conn.network.ports(device_owner=owner))) for owner in _ROUTER_IFACE_OWNERS
    ]
    all_networks, all_subnets, all_routers, floating_ips, *iface_port_groups = run_parallel(
        lambda: list(conn.network.networks()),
        lambda: list(conn.network.subnets()),
        lambda: list(conn.network.routers()),
        lambda: list_floating_ips(conn, project_id),
        *iface_port_calls,
    )

    # 2. 서브넷 → 맵 구축
    subnet_map: dict[str, SubnetDetail] = {}  # subnet_id → SubnetDetail
    subnet_network_map: dict[str, str] = {}  # subnet_id → network_id
    for s in all_subnets:
        subnet_map[s.id] = SubnetDetail(
            id=s.id,
            name=s.name or "",
            cidr=s.cidr or "",
            gateway_ip=s.gateway_ip,
            dhcp_enabled=bool(s.is_dhcp_enabled),
        )
        subnet_network_map[s.id] = s.network_id

    # 3. 라우터 인터페이스 포트 → router_id→[subnet_ids] 맵 (DVR/HA 포함)
    router_subnets: dict[str, list[str]] = {}
    router_subnet_port_count: dict[str, dict[str, int]] = {}  # rid → {sid → port 수}
    router_interface_ips: dict[str, list[dict]] = {}  # rid → [{ip_address, subnet_id}]
    for port in (port for group in iface_port_groups for port in group):
        rid = port.device_id
        if not rid:
            continue
        if rid not in router_subnets:
            router_subnets[rid] = []
        if rid not in router_subnet_port_count:
            router_subnet_port_count[rid] = {}
        if rid not in router_interface_ips:
            router_interface_ips[rid] = []
        for fip in port.fixed_ips or []:
            sid = fip.get("subnet_id")
            ip_addr = fip.get("ip_address")
            if sid:
                router_subnet_port_count[rid][sid] = router_subnet_port_count[rid].get(sid, 0) + 1
                if sid not in router_subnets[rid]:
                    router_subnets[rid].append(sid)
            # 중복 IP 제거 (DVR replicated 포트는 같은 IP 여러 번 나올 수 있음)
            if (
                ip_addr
                and sid
                and not any(e["ip_address"] == ip_addr and e["subnet_id"] == sid for e in router_interface_ips[rid])
            ):
                router_interface_ips[rid].append({"ip_address": ip_addr, "subnet_id": sid})

    # 4. 전체 라우터
    topo_routers = []
    for r in all_routers:
        ext_net_id = None
        ext_gw_ips: list[str] = []
        enable_snat: bool | None = None
        if r.external_gateway_info:
            ext_net_id = r.external_gateway_info.get("network_id")
            for efip in r.external_gateway_info.get("external_fixed_ips", []):
                ip = efip.get("ip_address")
                if ip:
                    ext_gw_ips.append(ip)
            raw_snat = r.external_gateway_info.get("enable_snat")
            enable_snat = bool(raw_snat) if raw_snat is not None else None
        dvr_sids = [sid for sid, cnt in router_subnet_port_count.get(r.id, {}).items() if cnt > 1]
        topo_routers.append(
            TopologyRouter(
                id=r.id,
                name=r.name or "",
                status=r.status or "",
                external_gateway_network_id=ext_net_id,
                external_gateway_ips=ext_gw_ips,
                interface_ips=router_interface_ips.get(r.id, []),
                is_distributed=bool(getattr(r, "is_distributed", False)),
                is_ha=bool(getattr(r, "is_ha", False)),
                connected_subnet_ids=router_subnets.get(r.id, []),
                dvr_subnet_ids=dvr_sids,
                project_id=getattr(r, "project_id", None),
                enable_snat=enable_snat,
                routes=_normalize_router_routes(getattr(r, "routes", None)),
            )
        )

    # 5. 네트워크별 서브넷 grouping
    network_subnets: dict[str, list[SubnetDetail]] = {}
    for subnet_id, net_id in subnet_network_map.items():
        if net_id not in network_subnets:
            network_subnets[net_id] = []
        if subnet_id in subnet_map:
            network_subnets[net_id].append(subnet_map[subnet_id])

    topo_networks: list[TopologyNetwork] = []
    for n in all_networks:
        base_fields = {
            "id": n.id,
            "name": n.name or "",
            "status": n.status or "",
            "is_external": bool(n.is_router_external),
            "is_shared": bool(n.is_shared),
            "project_id": getattr(n, "project_id", None),
            "subnet_details": network_subnets.get(n.id, []),
            "mtu": _coerce_int(getattr(n, "mtu", None)),
        }
        if include_provider:
            # provider 세그먼트 메타는 관리자 응답에서만 노출한다.
            topo_networks.append(
                AdminTopologyNetwork(
                    **base_fields,
                    provider_network_type=getattr(n, "provider_network_type", None),
                    provider_segmentation_id=_coerce_int(getattr(n, "provider_segmentation_id", None)),
                    provider_physical_network=getattr(n, "provider_physical_network", None),
                )
            )
        else:
            topo_networks.append(TopologyNetwork(**base_fields))

    if include_provider:
        return AdminTopologyData(
            networks=topo_networks,
            routers=topo_routers,
            instances=[],  # API 핸들러에서 nova 데이터 주입
            floating_ips=floating_ips,
        )
    return TopologyData(
        networks=topo_networks,
        routers=topo_routers,
        instances=[],  # API 핸들러에서 nova 데이터 주입
        floating_ips=floating_ips,
    )


# ---------------------------------------------------------------------------
# 라우터 CRUD
# ---------------------------------------------------------------------------


def list_routers(conn: openstack.connection.Connection, project_id: str | None = None) -> list[RouterInfo]:
    kwargs: dict = {}
    if project_id:
        kwargs["project_id"] = project_id
    result = []
    for r in conn.network.routers(**kwargs):
        ext_net_id = None
        if r.external_gateway_info:
            ext_net_id = r.external_gateway_info.get("network_id")
        # connected subnets via router_interface ports
        subnet_ids: list[str] = []
        try:
            for port in _iter_router_interface_ports(conn, device_id=r.id):
                for fip in port.fixed_ips or []:
                    sid = fip.get("subnet_id")
                    if sid and sid not in subnet_ids:
                        subnet_ids.append(sid)
        except Exception:
            pass
        result.append(
            RouterInfo(
                id=r.id,
                name=r.name or "",
                status=r.status or "",
                project_id=getattr(r, "project_id", None),
                external_gateway_network_id=ext_net_id,
                connected_subnet_ids=subnet_ids,
            )
        )
    return result


def get_router_detail(conn: openstack.connection.Connection, router_id: str) -> RouterDetail:
    r = conn.network.get_router(router_id)
    ext_net_id = None
    ext_net_name = None
    if r.external_gateway_info:
        ext_net_id = r.external_gateway_info.get("network_id")
        if ext_net_id:
            try:
                ext_net = conn.network.get_network(ext_net_id)
                ext_net_name = ext_net.name or ext_net_id
            except Exception:
                pass

    interfaces: list[RouterInterface] = []
    for port in _iter_router_interface_ports(conn, device_id=r.id):
        for fip in port.fixed_ips or []:
            sid = fip.get("subnet_id", "")
            ip = fip.get("ip_address", "")
            subnet_name = ""
            net_id = port.network_id or ""
            try:
                s = conn.network.get_subnet(sid)
                subnet_name = s.name or sid
            except Exception:
                pass
            interfaces.append(
                RouterInterface(
                    id=port.id,
                    subnet_id=sid,
                    subnet_name=subnet_name,
                    network_id=net_id,
                    ip_address=ip,
                )
            )

    return RouterDetail(
        id=r.id,
        name=r.name or "",
        status=r.status or "",
        project_id=getattr(r, "project_id", None),
        external_gateway_network_id=ext_net_id,
        external_gateway_network_name=ext_net_name,
        interfaces=interfaces,
    )


def create_router(
    conn: openstack.connection.Connection, name: str, external_network_id: str | None = None
) -> RouterInfo:
    kwargs: dict = {"name": name}
    if external_network_id:
        kwargs["external_gateway_info"] = {"network_id": external_network_id}
    r = conn.network.create_router(**kwargs)
    ext_net_id = None
    if r.external_gateway_info:
        ext_net_id = r.external_gateway_info.get("network_id")
    return RouterInfo(
        id=r.id,
        name=r.name or "",
        status=r.status or "",
        project_id=getattr(r, "project_id", None),
        external_gateway_network_id=ext_net_id,
    )


def delete_router(conn: openstack.connection.Connection, router_id: str) -> None:
    conn.network.delete_router(router_id, ignore_missing=True)


def add_router_interface(
    conn: openstack.connection.Connection, router_id: str, subnet_id: str, auto_gateway: bool = False
) -> dict:
    if auto_gateway:
        subnet = conn.network.get_subnet(subnet_id)
        if not subnet.gateway_ip:
            import ipaddress

            gw = str(next(ipaddress.ip_network(subnet.cidr, strict=False).hosts()))
            conn.network.update_subnet(subnet_id, gateway_ip=gw)
    result = conn.network.add_interface_to_router(router_id, subnet_id=subnet_id)
    return {"subnet_id": result.get("subnet_id", subnet_id), "port_id": result.get("port_id", "")}


def remove_router_interface(conn: openstack.connection.Connection, router_id: str, subnet_id: str) -> None:
    conn.network.remove_interface_from_router(router_id, subnet_id=subnet_id)


def set_router_gateway(conn: openstack.connection.Connection, router_id: str, external_network_id: str) -> None:
    conn.network.update_router(router_id, external_gateway_info={"network_id": external_network_id})


def remove_router_gateway(conn: openstack.connection.Connection, router_id: str) -> None:
    conn.network.update_router(router_id, external_gateway_info=None)


def list_instance_ports(conn: openstack.connection.Connection, instance_id: str) -> list[dict]:
    """인스턴스에 연결된 포트 목록 반환."""
    ports = list(conn.network.ports(device_id=instance_id))
    return [
        {
            "id": p.id,
            "network_id": p.network_id,
            "mac_address": p.mac_address,
            "fixed_ips": p.fixed_ips or [],
            "security_group_ids": p.security_group_ids or [],
            "status": p.status,
        }
        for p in ports
    ]


def _sg_to_dict(sg) -> dict:
    return {
        "id": sg.id,
        "name": sg.name,
        "description": sg.description,
        "rules": [
            {
                "id": r["id"],
                "direction": r["direction"],
                "protocol": r.get("protocol"),
                "port_range_min": r.get("port_range_min"),
                "port_range_max": r.get("port_range_max"),
                "remote_ip_prefix": r.get("remote_ip_prefix"),
                "ethertype": r.get("ethertype"),
            }
            for r in (sg.security_group_rules or [])
        ],
    }


def list_security_groups(conn: openstack.connection.Connection, project_id: str | None = None) -> list[dict]:
    kwargs: dict = {}
    if project_id:
        kwargs["project_id"] = project_id
    return [_sg_to_dict(sg) for sg in conn.network.security_groups(**kwargs)]


def create_security_group(conn: openstack.connection.Connection, name: str, description: str = "") -> dict:
    sg = conn.network.create_security_group(name=name, description=description)
    return _sg_to_dict(sg)


def delete_security_group(conn: openstack.connection.Connection, sg_id: str) -> None:
    conn.network.delete_security_group(sg_id, ignore_missing=True)


def create_security_group_rule(
    conn: openstack.connection.Connection,
    sg_id: str,
    direction: str,
    protocol: str | None = None,
    port_range_min: int | None = None,
    port_range_max: int | None = None,
    remote_ip_prefix: str | None = None,
    ethertype: str = "IPv4",
    remote_group_id: str | None = None,
) -> dict:
    kwargs: dict = {
        "security_group_id": sg_id,
        "direction": direction,
        "ether_type": ethertype,
    }
    if protocol:
        kwargs["protocol"] = protocol
    if port_range_min is not None:
        kwargs["port_range_min"] = port_range_min
    if port_range_max is not None:
        kwargs["port_range_max"] = port_range_max
    if remote_ip_prefix:
        kwargs["remote_ip_prefix"] = remote_ip_prefix
    if remote_group_id:
        kwargs["remote_group_id"] = remote_group_id
    rule = conn.network.create_security_group_rule(**kwargs)
    return {
        "id": rule.id,
        "direction": rule.direction,
        "protocol": rule.protocol,
        "port_range_min": rule.port_range_min,
        "port_range_max": rule.port_range_max,
        "remote_ip_prefix": rule.remote_ip_prefix,
        "ethertype": rule.ether_type,
    }


def delete_security_group_rule(conn: openstack.connection.Connection, rule_id: str) -> None:
    conn.network.delete_security_group_rule(rule_id, ignore_missing=True)


_UNION_EGRESS_RULES: list[dict] = [
    {"protocol": "tcp", "port_range_min": 2049, "port_range_max": 2049},  # NFS
    {"protocol": "udp", "port_range_min": 2049, "port_range_max": 2049},  # NFS UDP
    {"protocol": "tcp", "port_range_min": 6789, "port_range_max": 6789},  # CephFS mon v1
    {"protocol": "tcp", "port_range_min": 3300, "port_range_max": 3300},  # Ceph msgr v2
    {"protocol": "tcp", "port_range_min": 80, "port_range_max": 80},  # envmgr-init HTTP
    {"protocol": "tcp", "port_range_min": 443, "port_range_max": 443},  # envmgr-init HTTPS
]


def ensure_union_egress_sg(
    conn: openstack.connection.Connection, project_id: str, sg_name: str = "union-egress-default"
) -> str:
    """Union VM용 egress SG를 idempotent하게 확보하고 SG 이름을 반환한다.

    SG가 없으면 생성 후 NFS/CephFS/HTTP(S) egress rule을 추가한다.
    이미 있으면 누락된 rule만 보충한다.
    """
    sgs = list_security_groups(conn, project_id=project_id)
    existing = next((sg for sg in sgs if sg["name"] == sg_name), None)

    if existing is None:
        sg = create_security_group(conn, sg_name, f"Union VM egress — NFS/CephFS/HTTP(S) {AFTERGLOW_MANAGED_TAG}")
        sg_id = sg["id"]
        existing_rules: list[dict] = []
    else:
        sg_id = existing["id"]
        existing_rules = existing.get("rules", [])

    # (protocol, min, max)로 기존 egress rule 목록 색인
    existing_keys = {
        (r.get("protocol"), r.get("port_range_min"), r.get("port_range_max"))
        for r in existing_rules
        if r.get("direction") == "egress"
    }

    for rule in _UNION_EGRESS_RULES:
        key = (rule["protocol"], rule["port_range_min"], rule["port_range_max"])
        if key not in existing_keys:
            create_security_group_rule(
                conn,
                sg_id,
                direction="egress",
                protocol=rule["protocol"],
                port_range_min=rule["port_range_min"],
                port_range_max=rule["port_range_max"],
                remote_ip_prefix="0.0.0.0/0",
            )

    return sg_name


def _ensure_single_port_ingress_sg(
    conn: openstack.connection.Connection,
    project_id: str,
    sg_name: str,
    *,
    port: int,
    scrape_cidr: str,
    description: str,
) -> str:
    """단일 TCP 포트 ingress SG를 idempotent하게 확보하고 SG 이름을 반환한다.

    scrape_cidr이 비어있으면 ValueError(환경별 명시 주입 필수).
    SG가 없으면 생성 후 ingress rule을 추가한다.
    이미 있으면 누락된 rule만 보충한다.
    """
    if not scrape_cidr:
        raise ValueError("monitoring_scrape_cidr must be set — env 주입 필수")

    sgs = list_security_groups(conn, project_id=project_id)
    existing = next((sg for sg in sgs if sg["name"] == sg_name), None)

    if existing is None:
        sg = create_security_group(conn, sg_name, description)
        sg_id = sg["id"]
        existing_rules: list[dict] = []
    else:
        sg_id = existing["id"]
        existing_rules = existing.get("rules", [])

    existing_keys = {
        (r.get("protocol"), r.get("port_range_min"), r.get("port_range_max"), r.get("remote_ip_prefix"))
        for r in existing_rules
        if r.get("direction") == "ingress"
    }

    if ("tcp", port, port, scrape_cidr) not in existing_keys:
        create_security_group_rule(
            conn,
            sg_id,
            direction="ingress",
            protocol="tcp",
            port_range_min=port,
            port_range_max=port,
            remote_ip_prefix=scrape_cidr,
        )

    return sg_name


def ensure_node_exporter_sg(
    conn: openstack.connection.Connection,
    project_id: str,
    sg_name: str = "node_exporter",
    scrape_cidr: str = "",
) -> str:
    """node_exporter (tcp/9100) ingress SG를 idempotent하게 확보한다. 반환: sg_name."""
    return _ensure_single_port_ingress_sg(
        conn,
        project_id,
        sg_name,
        port=9100,
        scrape_cidr=scrape_cidr,
        description=f"Prometheus scrape — node_exporter ingress (tcp/9100) {AFTERGLOW_MANAGED_TAG}",
    )


def ensure_dcgm_exporter_sg(
    conn: openstack.connection.Connection,
    project_id: str,
    sg_name: str = "dcgm_exporter",
    scrape_cidr: str = "",
) -> str:
    """dcgm_exporter (tcp/9400) ingress SG를 idempotent하게 확보한다. 반환: sg_name."""
    return _ensure_single_port_ingress_sg(
        conn,
        project_id,
        sg_name,
        port=9400,
        scrape_cidr=scrape_cidr,
        description=f"Prometheus scrape — dcgm_exporter ingress (tcp/9400) {AFTERGLOW_MANAGED_TAG}",
    )


def update_port_security_groups(
    conn: openstack.connection.Connection, port_id: str, security_group_ids: list[str]
) -> dict:
    port = conn.network.update_port(port_id, security_groups=security_group_ids)
    return {
        "id": port.id,
        "security_group_ids": port.security_group_ids or [],
    }


# ---------------------------------------------------------------------------
# 프로젝트 기본 네트워크 (Default Network) — 동기 Neutron 연산
# ---------------------------------------------------------------------------

_default_net_logger = _logging.getLogger(__name__)


def _find_external_network(conn: openstack.connection.Connection) -> str | None:
    """첫 번째 외부(provider) 네트워크 ID를 반환. 없으면 None."""
    try:
        for n in conn.network.networks():
            if n.is_router_external:
                return n.id
    except Exception:
        pass
    return None


def _find_existing_router_for_subnet(
    conn: openstack.connection.Connection,
    subnet_id: str,
) -> str | None:
    """서브넷에 이미 연결된 라우터가 있으면 그 ID를 반환."""
    try:
        for port in _iter_router_interface_ports(conn, network_id=None):
            for fip in port.fixed_ips or []:
                if fip.get("subnet_id") == subnet_id:
                    return port.device_id
    except Exception:
        pass
    return None


def provision_default_network(
    conn: openstack.connection.Connection,
    project_id: str,
    external_network_id: str,
    cidr: str = "192.168.0.0/24",
) -> tuple[str, str | None, str | None, bool]:
    """Find or create a project's Default network using an explicit external network.

    The selected external network is required. Provisioning must never guess the
    first external network because that can connect a tenant to the wrong edge.
    """
    if not external_network_id:
        raise ValueError("an external network selection is required for default network provisioning")

    # ── Neutron 검색 ─────────────────────────────────────────────────────────
    try:
        existing = [
            n for n in conn.network.networks(project_id=project_id) if n.name == "Default" and not n.is_router_external
        ]
        if existing:
            net = existing[0]
            subnet_id = net.subnet_ids[0] if net.subnet_ids else None
            router_id: str | None = None

            # 기존 네트워크에 라우터가 연결되어 있는지 확인 → 없으면 자동 생성
            if subnet_id and external_network_id:
                router_id = _find_existing_router_for_subnet(conn, subnet_id)
                if not router_id:
                    try:
                        router = conn.network.create_router(
                            name="Default",
                            external_gateway_info={"network_id": external_network_id},
                        )
                        conn.network.add_interface_to_router(router.id, subnet_id=subnet_id)
                        router_id = router.id
                        _default_net_logger.info("기존 Default 네트워크(%s)에 라우터(%s) 자동 연결", net.id, router_id)
                    except Exception:
                        _default_net_logger.warning("기존 네트워크에 라우터 자동 연결 실패", exc_info=True)

            return net.id, subnet_id, router_id, False
    except Exception:
        _default_net_logger.warning("Neutron 네트워크 검색 실패", exc_info=True)

    # ── 새로 생성 ────────────────────────────────────────────────────────────
    net = None
    subnet = None
    router = None
    subnet_id = None
    router_id = None
    try:
        net = conn.network.create_network(name="Default")
        # CIDR의 첫 번째 호스트를 게이트웨이로 사용 (예: 192.168.0.0/24 → 192.168.0.1)
        try:
            import ipaddress

            network_addr = ipaddress.IPv4Network(cidr, strict=False)
            gateway: str | None = str(list(network_addr.hosts())[0])
        except Exception:
            gateway = None
        subnet = conn.network.create_subnet(
            network_id=net.id,
            name="Default",
            cidr=cidr,
            ip_version=4,
            is_dhcp_enabled=True,
            **({} if gateway is None else {"gateway_ip": gateway}),
        )
        subnet_id = subnet.id

        # 라우터 생성 및 외부 네트워크 게이트웨이 연결
        if external_network_id:
            router = conn.network.create_router(
                name="Default",
                external_gateway_info={"network_id": external_network_id},
            )
            conn.network.add_interface_to_router(router.id, subnet_id=subnet.id)
            router_id = router.id
        else:
            _default_net_logger.warning("외부 네트워크를 찾을 수 없어 라우터 생성을 건너뜁니다")
    except Exception as exc:
        _default_net_logger.error("Default 네트워크 생성 실패, 롤백", exc_info=True)
        # 생성된 리소스 정리
        if router:
            try:
                if subnet:
                    conn.network.remove_interface_from_router(router.id, subnet_id=subnet.id)
                conn.network.delete_router(router.id, ignore_missing=True)
            except Exception:
                pass
        if subnet:
            try:
                conn.network.delete_subnet(subnet.id, ignore_missing=True)
            except Exception:
                pass
        if net:
            try:
                conn.network.delete_network(net.id, ignore_missing=True)
            except Exception:
                pass
        raise RuntimeError("Default 네트워크 생성 실패") from exc

    return net.id, subnet_id, router_id, True


def _fip_to_info(f) -> FloatingIpInfo:
    return FloatingIpInfo(
        id=f.id,
        floating_ip_address=f.floating_ip_address,
        fixed_ip_address=f.fixed_ip_address,
        status=f.status or "",
        port_id=f.port_id,
        floating_network_id=f.floating_network_id,
        project_id=getattr(f, "project_id", None),
    )


def _sort_cidrs(cidrs: Any) -> list[str]:
    def cidr_key(cidr: str):
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            return (net.version, net.network_address, net.prefixlen, cidr)
        except (ValueError, TypeError):
            return (99, cidr, 0, cidr)

    unique_cidrs = set(c for c in cidrs if c)
    return sorted(unique_cidrs, key=cidr_key)


def _net_to_info(n, cidrs: list[str] | None = None) -> NetworkInfo:
    return NetworkInfo(
        id=n.id,
        name=n.name or "",
        status=n.status,
        subnets=list(getattr(n, "subnet_ids", None) or []),
        cidrs=list(cidrs or []),
        is_external=bool(getattr(n, "is_router_external", False)),
        is_shared=bool(getattr(n, "is_shared", False)),
    )


def list_project_compute_ports(conn, project_id: str) -> tuple[list[str], dict[str, list[str]]]:
    """compute 포트를 순회해 (instance_ids, network_id→[instance_id]) 맵 반환.

    get_topology_traffic 에서 PromQL regex 빌드 및 네트워크별 트래픽 합산에 사용.
    """
    instance_ids: list[str] = []
    net_to_instances: dict[str, list[str]] = {}
    for p in conn.network.ports(project_id=project_id):
        dev_owner = p.device_owner or ""
        if not p.device_id or not dev_owner.startswith("compute:"):
            continue
        server_id = p.device_id
        net_id = p.network_id or ""
        if server_id not in instance_ids:
            instance_ids.append(server_id)
        if net_id:
            lst = net_to_instances.setdefault(net_id, [])
            if server_id not in lst:
                lst.append(server_id)
    return instance_ids, net_to_instances


def list_project_port_map(conn, project_id: str | None) -> dict[str, dict]:
    """compute 포트 상세 매핑 반환.

    project_id=None 이면 모든 프로젝트의 compute 포트 조회 (admin 전용).

    Returns:
        {port_id: {"instance_id", "network_id", "mac_address"}}
    멀티-NIC 트래픽 demux 와 포트맵 캐싱에 사용.
    """
    out: dict[str, dict] = {}
    kwargs = {"project_id": project_id} if project_id else {}
    for p in conn.network.ports(**kwargs):
        if not p.device_id or not (p.device_owner or "").startswith("compute:"):
            continue
        out[p.id] = {
            "instance_id": p.device_id,
            "network_id": p.network_id or "",
            "mac_address": (p.mac_address or "").lower(),
        }
    return out
