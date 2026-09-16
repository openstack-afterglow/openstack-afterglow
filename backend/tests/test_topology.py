"""Phase 53e — 토폴로지 서버측 project_id 필터링 단위 테스트."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.storage import (
    FloatingIpInfo,
    TopologyData,
    TopologyNetwork,
    TopologyRouter,
)

PROJECT_A = "project-aaa"
PROJECT_B = "project-bbb"


def _make_server(sid: str, name: str, project_id: str, status: str = "ACTIVE"):
    s = MagicMock()
    s.id = sid
    s.name = name
    s.status = status
    s.project_id = project_id
    s.ip_addresses = []
    s.flavor_name = None
    s.image_id = None
    return s


def _make_topo(networks=None, routers=None):
    return TopologyData(
        networks=networks or [],
        routers=routers or [],
    )


def _patch_topology_deps(topo: TopologyData, servers: list):
    """neutron.get_topology, nova.list_servers, ports, get_topology_lbs를 한 번에 패치."""
    patches = [
        patch("app.api.network.networks.neutron.get_topology", return_value=topo),
        patch("app.api.network.networks.nova.list_servers", return_value=servers),
        patch("app.api.network.networks.get_topology_lbs", return_value=[]),
    ]
    return patches


def _apply(patches):
    for p in patches:
        p.start()
    return patches


def _stop(patches):
    for p in patches:
        p.stop()


# ---------------------------------------------------------------------------
# GET /api/networks/topology — user scope 필터링
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_topology_filters_other_project_instances(client, mock_conn):
    """다른 프로젝트 인스턴스는 응답에 포함되지 않는다."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    servers = [
        _make_server("s1", "vm-a", PROJECT_A),
        _make_server("s2", "vm-b", PROJECT_B),  # 다른 프로젝트
    ]
    topo = _make_topo()
    patches = _apply(_patch_topology_deps(topo, servers))

    try:
        from app.services import cache as cache_mod

        fake = MagicMock()
        fake.get = MagicMock(return_value=None)
        fake.setex = MagicMock(return_value=None)
        with patch.object(cache_mod, "_get_client", return_value=fake):
            resp = await client.get("/api/v1/networks/topology")
    finally:
        _stop(patches)

    assert resp.status_code == 200
    data = resp.json()
    instance_ids = [i["id"] for i in data["instances"]]
    assert "s1" in instance_ids
    assert "s2" not in instance_ids


@pytest.mark.asyncio
async def test_topology_includes_external_networks(client, mock_conn):
    """external 네트워크는 다른 프로젝트 소유여도 포함된다."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    ext_net = TopologyNetwork(
        id="net-ext",
        name="public",
        status="ACTIVE",
        is_external=True,
        is_shared=False,
        project_id=None,
    )
    priv_net = TopologyNetwork(
        id="net-prv",
        name="private-a",
        status="ACTIVE",
        is_external=False,
        is_shared=False,
        project_id=PROJECT_A,
    )
    other_net = TopologyNetwork(
        id="net-other",
        name="private-b",
        status="ACTIVE",
        is_external=False,
        is_shared=False,
        project_id=PROJECT_B,
    )

    topo = _make_topo(networks=[ext_net, priv_net, other_net])
    patches = _apply(_patch_topology_deps(topo, []))

    try:
        from app.services import cache as cache_mod

        fake = MagicMock()
        fake.get = MagicMock(return_value=None)
        fake.setex = MagicMock(return_value=None)
        with patch.object(cache_mod, "_get_client", return_value=fake):
            resp = await client.get("/api/v1/networks/topology")
    finally:
        _stop(patches)

    assert resp.status_code == 200
    data = resp.json()
    net_ids = [n["id"] for n in data["networks"]]
    assert "net-ext" in net_ids  # external 포함
    assert "net-prv" in net_ids  # 자기 프로젝트 포함
    assert "net-other" not in net_ids  # 다른 프로젝트 private 제외


@pytest.mark.asyncio
async def test_topology_includes_shared_networks(client, mock_conn):
    """shared 네트워크는 다른 프로젝트 소유여도 포함된다."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    shared_net = TopologyNetwork(
        id="net-shared",
        name="shared-net",
        status="ACTIVE",
        is_external=False,
        is_shared=True,
        project_id=PROJECT_B,
    )
    topo = _make_topo(networks=[shared_net])
    patches = _apply(_patch_topology_deps(topo, []))

    try:
        from app.services import cache as cache_mod

        fake = MagicMock()
        fake.get = MagicMock(return_value=None)
        fake.setex = MagicMock(return_value=None)
        with patch.object(cache_mod, "_get_client", return_value=fake):
            resp = await client.get("/api/v1/networks/topology")
    finally:
        _stop(patches)

    assert resp.status_code == 200
    data = resp.json()
    net_ids = [n["id"] for n in data["networks"]]
    assert "net-shared" in net_ids


@pytest.mark.asyncio
async def test_topology_filters_other_project_routers(client, mock_conn):
    """다른 프로젝트 라우터는 user 토폴로지에서 제외된다."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    router_a = TopologyRouter(
        id="r-a",
        name="router-a",
        status="ACTIVE",
        project_id=PROJECT_A,
    )
    router_b = TopologyRouter(
        id="r-b",
        name="router-b",
        status="ACTIVE",
        project_id=PROJECT_B,
    )
    topo = _make_topo(routers=[router_a, router_b])
    patches = _apply(_patch_topology_deps(topo, []))

    try:
        from app.services import cache as cache_mod

        fake = MagicMock()
        fake.get = MagicMock(return_value=None)
        fake.setex = MagicMock(return_value=None)
        with patch.object(cache_mod, "_get_client", return_value=fake):
            resp = await client.get("/api/v1/networks/topology")
    finally:
        _stop(patches)

    assert resp.status_code == 200
    data = resp.json()
    router_ids = [r["id"] for r in data["routers"]]
    assert "r-a" in router_ids
    assert "r-b" not in router_ids


@pytest.mark.asyncio
async def test_topology_empty_project_returns_empty(client, mock_conn):
    """자기 프로젝트 자원이 없으면 인스턴스·라우터는 빈 목록."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    servers = [_make_server("s1", "vm-b", PROJECT_B)]
    router_b = TopologyRouter(
        id="r-b",
        name="router-b",
        status="ACTIVE",
        project_id=PROJECT_B,
    )
    topo = _make_topo(routers=[router_b])
    patches = _apply(_patch_topology_deps(topo, servers))

    try:
        from app.services import cache as cache_mod

        fake = MagicMock()
        fake.get = MagicMock(return_value=None)
        fake.setex = MagicMock(return_value=None)
        with patch.object(cache_mod, "_get_client", return_value=fake):
            resp = await client.get("/api/v1/networks/topology")
    finally:
        _stop(patches)

    assert resp.status_code == 200
    data = resp.json()
    assert data["instances"] == []
    assert data["routers"] == []


# ---------------------------------------------------------------------------
# 토폴로지 캔버스 뷰 — per-NIC 포트 메타 · flavor/image · provider 키 비노출
# ---------------------------------------------------------------------------


def _make_port(port_id: str, device_id: str, network_id: str, ip: str, mac: str, device_owner: str = "compute:nova"):
    p = MagicMock()
    p.id = port_id
    p.mac_address = mac
    p.device_id = device_id
    p.device_owner = device_owner
    p.network_id = network_id
    p.fixed_ips = [{"ip_address": ip, "subnet_id": f"subnet-{network_id}"}]
    return p


def _make_ip(addr: str, network_name: str, ip_type: str = "fixed"):
    from app.models.compute import IpAddress

    return IpAddress(addr=addr, type=ip_type, network_name=network_name)


async def _get_user_topology(client):
    from app.services import cache as cache_mod

    fake = MagicMock()
    fake.get = MagicMock(return_value=None)
    fake.setex = MagicMock(return_value=None)
    with patch.object(cache_mod, "_get_client", return_value=fake):
        return await client.get("/api/v1/networks/topology")


@pytest.mark.asyncio
async def test_topology_ip_addresses_join_compute_port_meta(client, mock_conn):
    """ip_addresses 항목은 compute 포트에서 network_id/port_id/mac_addr 를 조인한다 (멀티 NIC 포함)."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = [
        _make_port("port-1", "s1", "net-a", "10.0.0.5", "fa:16:3e:00:00:01"),
        _make_port("port-2", "s1", "net-b", "10.0.1.7", "fa:16:3e:00:00:02"),
        # 라우터 포트는 compute 인덱스에 포함되지 않는다
        _make_port("port-r", "r1", "net-a", "10.0.0.1", "fa:16:3e:00:00:ff", device_owner="network:router_interface"),
    ]

    server = _make_server("s1", "vm-a", PROJECT_A)
    server.ip_addresses = [_make_ip("10.0.0.5", "net-a"), _make_ip("10.0.1.7", "net-b")]
    patches = _apply(_patch_topology_deps(_make_topo(), [server]))
    try:
        resp = await _get_user_topology(client)
    finally:
        _stop(patches)

    assert resp.status_code == 200
    inst = resp.json()["instances"][0]
    by_addr = {ip["addr"]: ip for ip in inst["ip_addresses"]}
    assert by_addr["10.0.0.5"]["network_id"] == "net-a"
    assert by_addr["10.0.0.5"]["port_id"] == "port-1"
    assert by_addr["10.0.0.5"]["mac_addr"] == "fa:16:3e:00:00:01"
    assert by_addr["10.0.1.7"]["network_id"] == "net-b"
    assert by_addr["10.0.1.7"]["port_id"] == "port-2"
    assert by_addr["10.0.1.7"]["mac_addr"] == "fa:16:3e:00:00:02"
    assert sorted(inst["network_names"]) == ["net-a", "net-b"]


@pytest.mark.asyncio
async def test_topology_ip_addresses_without_port_have_null_meta(client, mock_conn):
    """포트 인덱스에 없는 IP(예: floating)는 network_id/port_id/mac_addr 가 null 이다."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    server = _make_server("s1", "vm-a", PROJECT_A)
    server.ip_addresses = [_make_ip("203.0.113.9", "net-a", ip_type="floating")]
    patches = _apply(_patch_topology_deps(_make_topo(), [server]))
    try:
        resp = await _get_user_topology(client)
    finally:
        _stop(patches)

    assert resp.status_code == 200
    ip = resp.json()["instances"][0]["ip_addresses"][0]
    assert ip["type"] == "floating"
    assert ip["network_id"] is None
    assert ip["port_id"] is None
    assert ip["mac_addr"] is None


@pytest.mark.asyncio
async def test_topology_instance_carries_flavor_and_image(client, mock_conn):
    """flavor_name / image_id 는 list_servers 항목에서 그대로 전달된다."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    server = _make_server("s1", "vm-a", PROJECT_A)
    server.flavor_name = "m1.large"
    server.image_id = "img-ubuntu"
    patches = _apply(_patch_topology_deps(_make_topo(), [server]))
    try:
        resp = await _get_user_topology(client)
    finally:
        _stop(patches)

    assert resp.status_code == 200
    inst = resp.json()["instances"][0]
    assert inst["flavor_name"] == "m1.large"
    assert inst["image_id"] == "img-ubuntu"


@pytest.mark.asyncio
async def test_topology_user_response_omits_provider_keys(client, mock_conn):
    """사용자 토폴로지 네트워크에는 provider 세그먼트 키가 존재하지 않는다 (mtu 는 포함)."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    net = TopologyNetwork(
        id="net-prv",
        name="private-a",
        status="ACTIVE",
        project_id=PROJECT_A,
        mtu=1450,
    )
    patches = _apply(_patch_topology_deps(_make_topo(networks=[net]), []))
    try:
        resp = await _get_user_topology(client)
    finally:
        _stop(patches)

    assert resp.status_code == 200
    network = resp.json()["networks"][0]
    assert network["mtu"] == 1450
    assert "provider_segmentation_id" not in network
    assert "provider_network_type" not in network
    assert "provider_physical_network" not in network


@pytest.mark.asyncio
async def test_topology_user_response_strips_provider_keys_from_admin_models(client, mock_conn):
    """get_topology 가 admin 모델을 돌려주더라도 response_model(TopologyData)이 provider 키를 제거한다."""
    from app.models.storage import AdminTopologyData, AdminTopologyNetwork

    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    admin_net = AdminTopologyNetwork(
        id="net-prv",
        name="private-a",
        status="ACTIVE",
        project_id=PROJECT_A,
        provider_network_type="vlan",
        provider_segmentation_id=100,
        provider_physical_network="physnet1",
    )
    topo = AdminTopologyData(networks=[admin_net])
    patches = _apply(_patch_topology_deps(topo, []))
    try:
        resp = await _get_user_topology(client)
    finally:
        _stop(patches)

    assert resp.status_code == 200
    network = resp.json()["networks"][0]
    assert network["id"] == "net-prv"
    assert "provider_segmentation_id" not in network
    assert "provider_network_type" not in network
    assert "provider_physical_network" not in network


@pytest.mark.asyncio
async def test_topology_router_carries_snat_and_routes(client, mock_conn):
    """라우터의 enable_snat / routes 필드가 응답에 그대로 전달된다."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    router_a = TopologyRouter(
        id="r-a",
        name="router-a",
        status="ACTIVE",
        project_id=PROJECT_A,
        enable_snat=False,
        routes=[{"destination": "10.20.0.0/16", "nexthop": "10.0.0.254"}],
    )
    patches = _apply(_patch_topology_deps(_make_topo(routers=[router_a]), []))
    try:
        resp = await _get_user_topology(client)
    finally:
        _stop(patches)

    assert resp.status_code == 200
    router = resp.json()["routers"][0]
    assert router["enable_snat"] is False
    assert router["routes"] == [{"destination": "10.20.0.0/16", "nexthop": "10.0.0.254"}]


# ---------------------------------------------------------------------------
# Floating IP project scope + HTTPException 전달 (보안 리뷰 회귀)
# ---------------------------------------------------------------------------


def _make_fip(fid: str, addr: str, project_id: str | None) -> FloatingIpInfo:
    return FloatingIpInfo(
        id=fid, floating_ip_address=addr, floating_network_id="net-ext", project_id=project_id, status="ACTIVE"
    )


@pytest.mark.asyncio
async def test_topology_filters_other_project_floating_ips(client, mock_conn):
    """user scope 응답의 floating_ips 는 현재 프로젝트 소유분만 포함하고, FIP 조회에도 project_id 를 넘긴다."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    topo = TopologyData(
        networks=[],
        routers=[],
        floating_ips=[
            _make_fip("fip-a", "203.0.113.10", PROJECT_A),
            _make_fip("fip-b", "203.0.113.11", PROJECT_B),
            _make_fip("fip-none", "203.0.113.12", None),
        ],
    )
    patches = [
        patch("app.api.network.networks.neutron.get_topology", return_value=topo),
        patch("app.api.network.networks.nova.list_servers", return_value=[]),
        patch("app.api.network.networks.get_topology_lbs", return_value=[]),
    ]
    mocks = _apply(patches)
    try:
        resp = await client.get("/api/v1/networks/topology")
    finally:
        _stop(mocks)

    assert resp.status_code == 200
    fip_ids = [f["id"] for f in resp.json()["floating_ips"]]
    assert fip_ids == ["fip-a"]


@pytest.mark.asyncio
async def test_topology_passes_project_scope_to_get_topology(client, mock_conn):
    """_fetch_topology_sync 는 neutron.get_topology 에 project_id 를 넘긴다."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []
    topo = _make_topo()
    with (
        patch("app.api.network.networks.neutron.get_topology", return_value=topo) as get_topo,
        patch("app.api.network.networks.nova.list_servers", return_value=[]),
        patch("app.api.network.networks.get_topology_lbs", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology")
    assert resp.status_code == 200
    assert get_topo.call_args.kwargs.get("project_id") == PROJECT_A


@pytest.mark.asyncio
async def test_topology_http_exception_propagates(client, mock_conn):
    """조회 도중 발생한 HTTPException(예: 503 transient auth) 은 500 으로 뭉개지지 않는다."""
    from fastapi import HTTPException

    mock_conn._afterglow_project_id = PROJECT_A
    with patch(
        "app.api.network.networks.neutron.get_topology",
        side_effect=HTTPException(status_code=503, detail="인증 서비스 지연"),
    ):
        resp = await client.get("/api/v1/networks/topology")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# is_database — Trove DB 인스턴스 표시 (fixed IP 매칭 + fail-soft)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_topology_flags_trove_backed_instances(client, mock_conn):
    """fixed IP 가 Trove IP 집합에 있는 인스턴스만 is_database=true 로 표시된다."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    db_server = _make_server("s-db", "trove-vm", PROJECT_A)
    db_server.ip_addresses = [_make_ip("10.0.0.11", "net-a")]
    plain_server = _make_server("s-plain", "web-01", PROJECT_A)
    plain_server.ip_addresses = [_make_ip("10.0.0.12", "net-a")]

    patches = _apply(_patch_topology_deps(_make_topo(), [db_server, plain_server]))
    patches.append(patch("app.api.network.networks.trove.topology_database_ips", return_value={"10.0.0.11"}))
    patches[-1].start()
    try:
        resp = await _get_user_topology(client)
    finally:
        _stop(patches)

    assert resp.status_code == 200
    by_id = {i["id"]: i for i in resp.json()["instances"]}
    assert by_id["s-db"]["is_database"] is True
    assert by_id["s-plain"]["is_database"] is False


@pytest.mark.asyncio
async def test_topology_floating_ip_match_does_not_flag_database(client, mock_conn):
    """floating IP 가 Trove IP 와 우연히 같아도 is_database 로 표시하지 않는다 (fixed 전용 매칭)."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    server = _make_server("s-fip", "vm-fip", PROJECT_A)
    server.ip_addresses = [
        _make_ip("10.0.0.99", "net-a"),
        _make_ip("203.0.113.11", "net-a", ip_type="floating"),
    ]

    patches = _apply(_patch_topology_deps(_make_topo(), [server]))
    patches.append(patch("app.api.network.networks.trove.topology_database_ips", return_value={"203.0.113.11"}))
    patches[-1].start()
    try:
        resp = await _get_user_topology(client)
    finally:
        _stop(patches)

    assert resp.status_code == 200
    assert resp.json()["instances"][0]["is_database"] is False


@pytest.mark.asyncio
async def test_topology_database_flag_fails_soft_when_trove_raises(client, mock_conn):
    """Trove 조회가 예외를 던져도 200 을 유지하고 모든 인스턴스가 is_database=false 다."""
    mock_conn._afterglow_project_id = PROJECT_A
    mock_conn.network.ports.return_value = []

    server = _make_server("s1", "vm-a", PROJECT_A)
    server.ip_addresses = [_make_ip("10.0.0.11", "net-a")]

    patches = _apply(_patch_topology_deps(_make_topo(), [server]))
    patches.append(
        patch(
            "app.api.network.networks.trove.topology_database_ips",
            side_effect=RuntimeError("Trove 카탈로그 없음"),
        )
    )
    patches[-1].start()
    try:
        resp = await _get_user_topology(client)
    finally:
        _stop(patches)

    assert resp.status_code == 200
    instances = resp.json()["instances"]
    assert len(instances) == 1
    assert instances[0]["is_database"] is False
