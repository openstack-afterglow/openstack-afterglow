"""토폴로지 LoadBalancer 수집/매칭 단위 테스트."""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# get_topology_lbs 단위 테스트
# ---------------------------------------------------------------------------


def _make_lb(lb_id: str, vip: str, vip_port_id: str | None = None) -> dict:
    return {
        "id": lb_id,
        "name": f"lb-{lb_id}",
        "vip_address": vip,
        "vip_subnet_id": "subnet-1",
        "vip_network_id": "net-1",
        "vip_port_id": vip_port_id,
        "status": "ACTIVE",
        "operating_status": "ONLINE",
        "project_id": "proj-1",
    }


_LISTENERS = [
    {
        "id": "li-1",
        "name": "http",
        "protocol": "HTTP",
        "protocol_port": 80,
        "default_pool_id": "pool-1",
        "status": "ACTIVE",
        "load_balancer_id": "lb-1",
    }
]
_POOLS = [
    {
        "id": "pool-1",
        "name": "p1",
        "protocol": "HTTP",
        "lb_algorithm": "ROUND_ROBIN",
        "status": "ACTIVE",
        "load_balancer_id": "lb-1",
    },
    {
        "id": "pool-2",
        "name": "p2",
        "protocol": "TCP",
        "lb_algorithm": "ROUND_ROBIN",
        "status": "ACTIVE",
        "load_balancer_id": "lb-1",
    },
]
_MEMBERS_BY_POOL = {
    "pool-1": [
        {"id": "m-1", "address": "10.0.0.5", "protocol_port": 8080, "status": "ACTIVE", "subnet_id": "subnet-1"}
    ],
    "pool-2": [
        {"id": "m-2", "address": "10.0.0.6", "protocol_port": 8443, "status": "ACTIVE", "subnet_id": "subnet-1"}
    ],
}


def test_get_topology_lbs_member_ip_matched():
    """member.address와 일치하는 인스턴스의 server_id가 채워진다."""
    from app.services.octavia import get_topology_lbs

    conn = MagicMock()
    conn.load_balancer.load_balancers.return_value = [MagicMock(**_make_lb("lb-1", "10.0.0.100"))]

    with (
        patch("app.services.octavia.list_listeners", return_value=_LISTENERS),
        patch("app.services.octavia.list_pools", return_value=_POOLS),
        patch("app.services.octavia.list_members", side_effect=lambda conn, pool_id: _MEMBERS_BY_POOL.get(pool_id, [])),
    ):
        result = get_topology_lbs(
            conn,
            instances=[
                {"id": "srv-abc", "project_id": "proj-1", "ip_addresses": [{"addr": "10.0.0.5", "type": "fixed"}]},
                {"id": "srv-xyz", "project_id": "proj-1", "ip_addresses": [{"addr": "10.0.0.6", "type": "fixed"}]},
            ],
        )

    assert len(result) == 1
    assert len(result[0]["members"]) == 2
    matched = {m["address"]: m["server_id"] for m in result[0]["members"]}
    assert matched["10.0.0.5"] == "srv-abc"
    assert matched["10.0.0.6"] == "srv-xyz"


def test_get_topology_lbs_member_ip_unmatched():
    """매칭 안 되는 멤버 IP는 server_id=None."""
    from app.services.octavia import get_topology_lbs

    conn = MagicMock()
    conn.load_balancer.load_balancers.return_value = [MagicMock(**_make_lb("lb-1", "10.0.0.100"))]

    with (
        patch("app.services.octavia.list_listeners", return_value=_LISTENERS),
        patch("app.services.octavia.list_pools", return_value=_POOLS),
        patch("app.services.octavia.list_members", side_effect=lambda conn, pool_id: _MEMBERS_BY_POOL.get(pool_id, [])),
    ):
        result = get_topology_lbs(conn, instances=[])

    assert all(m["server_id"] is None for m in result[0]["members"])


def test_get_topology_lbs_includes_extra_pool_not_in_listener():
    """listener에 묶이지 않은 추가 pool의 멤버도 응답에 포함된다 (pool 2개 시나리오)."""
    from app.services.octavia import get_topology_lbs

    conn = MagicMock()
    conn.load_balancer.load_balancers.return_value = [MagicMock(**_make_lb("lb-1", "10.0.0.100"))]

    with (
        patch("app.services.octavia.list_listeners", return_value=_LISTENERS),
        patch("app.services.octavia.list_pools", return_value=_POOLS),
        patch("app.services.octavia.list_members", side_effect=lambda conn, pool_id: _MEMBERS_BY_POOL.get(pool_id, [])),
    ):
        result = get_topology_lbs(conn)

    pool_ids = {m["pool_id"] for m in result[0]["members"]}
    assert pool_ids == {"pool-1", "pool-2"}


# ---------------------------------------------------------------------------
# /api/networks/topology E2E: load_balancers 필드 포함 여부
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_topology_endpoint_includes_load_balancers(client):
    """인증된 요청에서 응답에 load_balancers 필드가 포함된다."""

    empty_topo = {
        "networks": [],
        "routers": [],
        "instances": [],
        "floating_ips": [],
        "load_balancers": [],
    }

    with (
        patch("app.api.network.networks._fetch_topology_sync", return_value=empty_topo),
    ):
        resp = await client.get("/api/v1/networks/topology")

    assert resp.status_code == 200
    data = resp.json()
    assert "load_balancers" in data
    assert isinstance(data["load_balancers"], list)
