"""Octavia (OpenStack Load Balancer) 서비스 래퍼."""

from __future__ import annotations

import time
from functools import partial
from threading import Lock
from typing import TYPE_CHECKING

from keystoneauth1.exceptions.catalog import EndpointNotFound

from app.services.parallel import run_parallel

if TYPE_CHECKING:
    import openstack


def _lb_to_dict(lb) -> dict:
    prov = getattr(lb, "provisioning_status", "") or ""
    raw_tags = getattr(lb, "tags", None)
    if raw_tags is None:
        tags: list[str] = []
    elif isinstance(raw_tags, (list, tuple, set)):
        tags = [str(t) for t in raw_tags]
    else:
        tags = [str(raw_tags)]
    return {
        "id": lb.id,
        "name": lb.name or "",
        "description": getattr(lb, "description", "") or "",
        "status": prov,
        "provisioning_status": prov,
        "operating_status": getattr(lb, "operating_status", "") or "",
        "vip_address": getattr(lb, "vip_address", None),
        "vip_subnet_id": getattr(lb, "vip_subnet_id", None),
        "vip_network_id": getattr(lb, "vip_network_id", None),
        "vip_port_id": getattr(lb, "vip_port_id", None),
        "project_id": getattr(lb, "project_id", None),
        "tags": tags,
    }


def _listener_to_dict(listener) -> dict:
    return {
        "id": listener.id,
        "name": listener.name or "",
        "protocol": getattr(listener, "protocol", "") or "",
        "protocol_port": getattr(listener, "protocol_port", 0),
        "status": getattr(listener, "provisioning_status", "") or "",
        "default_pool_id": getattr(listener, "default_pool_id", None),
        "load_balancer_id": getattr(listener, "load_balancer_id", None),
    }


def _pool_to_dict(p) -> dict:
    # Pool's provider body uses ``loadbalancers`` in openstacksdk 3.3.0.
    # Do not use the query's loadbalancer_id as ownership evidence.
    parents = getattr(p, "loadbalancers", None)
    parent_id = (
        parents[0].get("id")
        if isinstance(parents, list) and len(parents) == 1 and isinstance(parents[0], dict)
        else None
    )
    return {
        "id": p.id,
        "name": p.name or "",
        "protocol": getattr(p, "protocol", "") or "",
        "lb_algorithm": getattr(p, "lb_algorithm", "") or "",
        "status": getattr(p, "provisioning_status", "") or "",
        "health_monitor_id": getattr(p, "health_monitor_id", None),
        "load_balancer_id": parent_id,
    }


def _member_to_dict(m) -> dict:
    return {
        "id": m.id,
        "name": m.name or "",
        "address": getattr(m, "address", "") or "",
        "protocol_port": getattr(m, "protocol_port", 0),
        "weight": getattr(m, "weight", 1),
        "status": getattr(m, "provisioning_status", "") or "",
        "subnet_id": getattr(m, "subnet_id", None),
    }


def _hm_to_dict(hm) -> dict:
    return {
        "id": hm.id,
        "name": hm.name or "",
        "type": getattr(hm, "type", "") or "",
        "delay": getattr(hm, "delay", 5),
        "timeout": getattr(hm, "timeout", 5),
        "max_retries": getattr(hm, "max_retries", 3),
        "status": getattr(hm, "provisioning_status", "") or "",
    }


# ---------------------------------------------------------------------------
# Load Balancers
# ---------------------------------------------------------------------------


def list_load_balancers(conn: openstack.connection.Connection, project_id: str | None = None) -> list[dict]:
    kwargs = {}
    if project_id:
        kwargs["project_id"] = project_id
    return [_lb_to_dict(lb) for lb in conn.load_balancer.load_balancers(**kwargs)]


def get_load_balancer(conn: openstack.connection.Connection, lb_id: str) -> dict:
    return _lb_to_dict(conn.load_balancer.get_load_balancer(lb_id))


def create_load_balancer(
    conn: openstack.connection.Connection,
    name: str,
    vip_subnet_id: str = "",
    description: str = "",
    *,
    vip_network_id: str | None = None,
) -> dict:
    """Octavia LB 생성.

    vip_network_id가 있으면 provider 네트워크에 직접 VIP를 생성 (FIP 불필요).
    없으면 vip_subnet_id로 tenant 서브넷에 VIP를 생성.
    """
    kwargs: dict = {"name": name, "description": description}
    if vip_network_id:
        kwargs["vip_network_id"] = vip_network_id
    else:
        kwargs["vip_subnet_id"] = vip_subnet_id
    lb = conn.load_balancer.create_load_balancer(**kwargs)
    return _lb_to_dict(lb)


def delete_load_balancer(conn: openstack.connection.Connection, lb_id: str, cascade: bool = True) -> None:
    conn.load_balancer.delete_load_balancer(lb_id, cascade=cascade, ignore_missing=True)


def wait_for_load_balancer(
    conn: openstack.connection.Connection,
    lb_id: str,
    status: str = "ACTIVE",
    wait: int = 300,
    interval: int = 5,
) -> dict:
    """LB가 target provisioning_status에 도달할 때까지 폴링. 타임아웃 시 TimeoutError."""
    import time

    deadline = time.time() + wait
    while time.time() < deadline:
        lb = conn.load_balancer.get_load_balancer(lb_id)
        prov_status = getattr(lb, "provisioning_status", "")
        if prov_status == status:
            return _lb_to_dict(lb)
        if prov_status == "ERROR":
            raise RuntimeError(f"LB {lb_id} entered ERROR state")
        time.sleep(interval)
    raise TimeoutError(f"LB {lb_id} did not reach {status} within {wait}s")


def get_lb_status_tree(conn: openstack.connection.Connection, lb_id: str) -> dict:
    """로드밸런서 상태 트리 조회 (Octavia status tree API).
    오류 발생 위치를 계층적으로 확인하는 데 사용.
    """
    try:
        # openstacksdk가 status tree를 직접 지원하지 않으므로 raw session 사용
        lb = conn.load_balancer.get_load_balancer(lb_id)
        endpoint = conn.load_balancer.get_endpoint()
        resp = conn.load_balancer._session.get(f"{endpoint.rstrip('/')}/lbaas/loadbalancers/{lb_id}/status")
        data = resp.json() if hasattr(resp, "json") else {}
        return data.get("statuses", {}).get("loadbalancer", {})
    except Exception:
        pass
    # fallback: 기본 LB 정보만 반환
    try:
        lb = conn.load_balancer.get_load_balancer(lb_id)
        return {
            "id": lb.id,
            "name": lb.name,
            "provisioning_status": getattr(lb, "provisioning_status", ""),
            "operating_status": getattr(lb, "operating_status", ""),
            "listeners": [],
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Listeners
# ---------------------------------------------------------------------------


def list_listeners(conn: openstack.connection.Connection, lb_id: str | None = None) -> list[dict]:
    kwargs = {}
    if lb_id:
        kwargs["load_balancer_id"] = lb_id
    return [_listener_to_dict(listener) for listener in conn.load_balancer.listeners(**kwargs)]


def create_listener(
    conn: openstack.connection.Connection,
    lb_id: str,
    protocol: str,
    protocol_port: int,
    name: str = "",
    default_pool_id: str | None = None,
) -> dict:
    kwargs: dict = {
        "load_balancer_id": lb_id,
        "protocol": protocol,
        "protocol_port": protocol_port,
    }
    if name:
        kwargs["name"] = name
    if default_pool_id:
        kwargs["default_pool_id"] = default_pool_id
    return _listener_to_dict(conn.load_balancer.create_listener(**kwargs))


def delete_listener(conn: openstack.connection.Connection, listener_id: str) -> None:
    conn.load_balancer.delete_listener(listener_id, ignore_missing=True)


# ---------------------------------------------------------------------------
# Pools
# ---------------------------------------------------------------------------


def list_pools(conn: openstack.connection.Connection, lb_id: str | None = None) -> list[dict]:
    kwargs = {}
    if lb_id:
        kwargs["loadbalancer_id"] = lb_id
    return [_pool_to_dict(p) for p in conn.load_balancer.pools(**kwargs)]


def create_pool(
    conn: openstack.connection.Connection,
    lb_id: str,
    protocol: str,
    lb_algorithm: str = "ROUND_ROBIN",
    name: str = "",
    listener_id: str | None = None,
) -> dict:
    kwargs: dict = {
        "load_balancer_id": lb_id,
        "protocol": protocol,
        "lb_algorithm": lb_algorithm,
    }
    if name:
        kwargs["name"] = name
    if listener_id:
        kwargs["listener_id"] = listener_id
    return _pool_to_dict(conn.load_balancer.create_pool(**kwargs))


def delete_pool(conn: openstack.connection.Connection, pool_id: str) -> None:
    conn.load_balancer.delete_pool(pool_id, ignore_missing=True)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


def list_members(conn: openstack.connection.Connection, pool_id: str) -> list[dict]:
    return [_member_to_dict(m) for m in conn.load_balancer.members(pool_id)]


def add_member(
    conn: openstack.connection.Connection,
    pool_id: str,
    address: str,
    protocol_port: int,
    subnet_id: str | None = None,
    name: str = "",
    weight: int = 1,
) -> dict:
    kwargs: dict = {
        "address": address,
        "protocol_port": protocol_port,
        "weight": weight,
    }
    if name:
        kwargs["name"] = name
    if subnet_id:
        kwargs["subnet_id"] = subnet_id
    return _member_to_dict(conn.load_balancer.create_member(pool_id, **kwargs))


def remove_member(conn: openstack.connection.Connection, pool_id: str, member_id: str) -> None:
    conn.load_balancer.delete_member(member_id, pool_id, ignore_missing=True)


# ---------------------------------------------------------------------------
# Health Monitors
# ---------------------------------------------------------------------------


def list_health_monitors(conn: openstack.connection.Connection, pool_id: str | None = None) -> list[dict]:
    kwargs = {}
    if pool_id:
        kwargs["pool_id"] = pool_id
    return [_hm_to_dict(hm) for hm in conn.load_balancer.health_monitors(**kwargs)]


def create_health_monitor(
    conn: openstack.connection.Connection,
    pool_id: str,
    type: str = "HTTP",
    delay: int = 5,
    timeout: int = 5,
    max_retries: int = 3,
    name: str = "",
) -> dict:
    kwargs: dict = {
        "pool_id": pool_id,
        "type": type,
        "delay": delay,
        "timeout": timeout,
        "max_retries": max_retries,
    }
    if name:
        kwargs["name"] = name
    return _hm_to_dict(conn.load_balancer.create_health_monitor(**kwargs))


def delete_health_monitor(conn: openstack.connection.Connection, hm_id: str) -> None:
    conn.load_balancer.delete_health_monitor(hm_id, ignore_missing=True)


# ---------------------------------------------------------------------------
# 토폴로지 수집
# ---------------------------------------------------------------------------


class TopologyLoadBalancersUnavailable(RuntimeError):
    """The native LB graph could not be observed completely."""


def get_topology_lbs(
    conn: openstack.connection.Connection,
    project_id: str | None = None,
    instances: list[dict] | None = None,
) -> list[dict]:
    """Collect the native LB graph using bounded, drained read fan-out.

    A genuinely absent Octavia catalog entry is empty. Transport, authorization
    and partial child-read failures are unavailable, never an empty graph.
    """
    try:
        lbs = list_load_balancers(conn, project_id=project_id)
    except EndpointNotFound:
        return []
    except Exception as exc:
        raise TopologyLoadBalancersUnavailable() from exc
    if not lbs:
        return []

    try:
        # One shared bounded executor per phase, not nested per-LB thread pools.
        children = run_parallel(
            *(partial(list_listeners, conn, lb_id=lb["id"]) for lb in lbs),
            *(partial(list_pools, conn, lb_id=lb["id"]) for lb in lbs),
        )
        listeners = children[: len(lbs)]
        pools_by_lb = children[len(lbs) :]
        pool_reads = []
        for lb, pools in zip(lbs, pools_by_lb, strict=True):
            for pool in pools:
                # Independently retain only native-proven parent associations.
                if not pool.get("load_balancer_id"):
                    raise TopologyLoadBalancersUnavailable()
                if pool["load_balancer_id"] == lb["id"]:
                    pool_reads.append((lb["id"], pool["id"]))
        member_rows = run_parallel(*(partial(list_members, conn, pool_id=pid) for _, pid in pool_reads))
    except TopologyLoadBalancersUnavailable:
        raise
    except Exception as exc:
        raise TopologyLoadBalancersUnavailable() from exc

    # Private networks can repeat fixed addresses across projects (and within a
    # project). Only one positively owned fixed-IP candidate may form an edge.
    ip_to_server: dict[tuple[str, str], str | None] = {}
    for server in instances or []:
        owner, server_id = server.get("project_id"), server.get("id")
        if not isinstance(owner, str) or not owner or not isinstance(server_id, str) or not server_id:
            continue
        for ip in server.get("ip_addresses") or []:
            address = ip.get("addr")
            if ip.get("type") != "fixed" or not isinstance(address, str) or not address:
                continue
            key = (owner, address)
            if key in ip_to_server and ip_to_server[key] != server_id:
                ip_to_server[key] = None
            else:
                ip_to_server[key] = server_id

    members_by_lb: dict[str, list[dict]] = {lb["id"]: [] for lb in lbs}
    owners = {lb["id"]: lb.get("project_id") for lb in lbs}
    for (lb_id, pool_id), members in zip(pool_reads, member_rows, strict=True):
        for member in members:
            address = member.get("address", "")
            members_by_lb[lb_id].append(
                {
                    "id": member.get("id", ""),
                    "address": address,
                    "protocol_port": member.get("protocol_port", 0),
                    "status": member.get("status", ""),
                    "subnet_id": member.get("subnet_id"),
                    "pool_id": pool_id,
                    "server_id": ip_to_server.get((owners[lb_id], address)),
                }
            )
    return [
        {
            **lb,
            "listeners": [
                {
                    "id": listener.get("id", ""),
                    "name": listener.get("name", ""),
                    "protocol": listener.get("protocol", ""),
                    "protocol_port": listener.get("protocol_port", 0),
                    "default_pool_id": listener.get("default_pool_id"),
                }
                for listener in lb_listeners
            ],
            "members": members_by_lb[lb["id"]],
        }
        for lb, lb_listeners in zip(lbs, listeners, strict=True)
    ]


# ---------------------------------------------------------------------------
# LB 트래픽 stats (Octavia /stats API — 누적 카운터 차분으로 rate 계산)
# ---------------------------------------------------------------------------

_lb_snapshot: dict[str, tuple[int, int, float]] = {}  # lb_id → (bytes_in, bytes_out, ts)
_snapshot_lock = Lock()


def get_lb_stats(conn, lb_id: str) -> dict[str, int] | None:
    """Octavia 누적 stats 반환. 실패 시 None."""
    try:
        s = conn.load_balancer.get_load_balancer_statistics(lb_id)
        return {
            "bytes_in": int(getattr(s, "bytes_in", 0) or 0),
            "bytes_out": int(getattr(s, "bytes_out", 0) or 0),
            "active_connections": int(getattr(s, "active_connections", 0) or 0),
        }
    except Exception:
        return None


def lb_rate_from_snapshot(lb_id: str, current: dict[str, int]) -> dict[str, float]:
    """이전 스냅샷과 비교해 bps 계산 후 스냅샷 갱신.

    최초 호출은 rx_bps=tx_bps=0 (스냅샷이 없음). 다음 폴링(15s 후)부터 정상 값.
    """
    now = time.time()
    with _snapshot_lock:
        prev = _lb_snapshot.get(lb_id)
        _lb_snapshot[lb_id] = (current["bytes_in"], current["bytes_out"], now)
    if prev is None:
        return {"rx_bps": 0.0, "tx_bps": 0.0}
    dt = now - prev[2]
    if dt <= 0:
        return {"rx_bps": 0.0, "tx_bps": 0.0}
    # bytes_out = client 가 받는 응답 → client 입장 rx
    return {
        "rx_bps": max(0.0, (current["bytes_out"] - prev[1]) / dt) * 8,
        "tx_bps": max(0.0, (current["bytes_in"] - prev[0]) / dt) * 8,
    }
