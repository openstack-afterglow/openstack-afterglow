"""네트워크 및 Floating IP API 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.compute import InstanceInfo
from app.models.storage import FloatingIpInfo, TopologyData


def make_fip(project_id: str = "test-project-123") -> FloatingIpInfo:
    return FloatingIpInfo(
        id="fip-1",
        floating_ip_address="1.2.3.4",
        fixed_ip_address=None,
        status="DOWN",
        port_id=None,
        floating_network_id="net-ext",
        project_id=project_id,
    )


def _make_network():
    return {
        "id": "net-1",
        "name": "mynet",
        "status": "ACTIVE",
        "project_id": "test-project-123",
        "shared": False,
        "admin_state_up": True,
        "subnets": [],
    }


@pytest.mark.asyncio
async def test_list_networks_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/networks")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_networks_success(client):
    with patch("app.api.network.networks.cached_call", new=AsyncMock(return_value=[])):
        resp = await client.get("/api/v1/networks")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_network_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/networks", json={"name": "net1"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_network_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/networks/net-1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_network_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/networks/net-1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_network_success(client):
    with patch("app.api.network.networks.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = AsyncMock(return_value=None)
        resp = await client.delete("/api/v1/networks/net-1")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_create_subnet_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/networks/net-1/subnets", json={"name": "sub1", "cidr": "10.0.0.0/24", "ip_version": 4}
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_subnet_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/networks/subnets/sub-1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_topology_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/networks/topology")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_topology_includes_instance_project_id(client, mock_conn):
    """토폴로지 응답에 인스턴스 project_id가 포함되어야 함 (필터링 정상 작동 확인)."""

    def fake_get_topology(conn, **kwargs):
        return TopologyData()

    def fake_list_servers(conn):
        return [InstanceInfo(id="inst-1", name="srv", status="ACTIVE", project_id="test-project-123")]

    mock_conn.network.ports.return_value = []

    async def fake_cached_call(key, ttl, fn, refresh=False, enabled=True):
        return fn()

    with (
        patch("app.api.network.networks.neutron.get_topology", side_effect=fake_get_topology),
        patch("app.api.network.networks.nova.list_servers", side_effect=fake_list_servers),
        patch("app.api.network.networks.cached_call", side_effect=fake_cached_call),
    ):
        resp = await client.get("/api/v1/networks/topology")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["instances"]) == 1
    assert data["instances"][0]["project_id"] == "test-project-123"


@pytest.mark.asyncio
async def test_list_floating_ips_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/networks/floating-ips")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_floating_ips_filters_by_project(client, mock_conn):
    """Floating IP 목록이 현재 프로젝트로 필터링됨을 확인 (Task 2 버그 수정)."""
    captured_project_id = None

    def mock_list_fips(conn, project_id=None):
        nonlocal captured_project_id
        captured_project_id = project_id
        return [make_fip(project_id or "")]

    with patch("app.api.network.networks.neutron.list_floating_ips", side_effect=mock_list_fips):
        resp = await client.get("/api/v1/networks/floating-ips")

    assert resp.status_code == 200
    # project_id가 전달되었어야 함
    assert captured_project_id == "test-project-123"


@pytest.mark.asyncio
async def test_create_floating_ip_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/networks/floating-ips", json={"floating_network_id": "ext-net"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_associate_floating_ip_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/networks/floating-ips/fip-1/associate", json={"port_id": "port-1"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_disassociate_floating_ip_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/networks/floating-ips/fip-1/disassociate")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_floating_ip_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/networks/floating-ips/fip-1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_get_network_detail_non_admin_returns_403(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/networks/net-1")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_get_network_detail_vlan(admin_client, mock_conn):
    mock_net = MagicMock()
    mock_net.id = "net-vlan"
    mock_net.name = "vlan-net"
    mock_net.status = "ACTIVE"
    mock_net.subnet_ids = []
    mock_net.is_router_external = False
    mock_net.is_shared = False
    mock_net.provider_network_type = "vlan"
    mock_net.provider_segmentation_id = 100
    mock_net.provider_physical_network = "physnet1"

    mock_conn.network.get_network.return_value = mock_net
    mock_conn.network.ports.return_value = []

    resp = await admin_client.get("/api/v1/admin/networks/net-vlan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "net-vlan"
    assert data["provider_network_type"] == "vlan"
    assert data["provider_segmentation_id"] == 100
    assert data["provider_physical_network"] == "physnet1"


@pytest.mark.asyncio
async def test_admin_get_network_detail_vxlan(admin_client, mock_conn):
    mock_net = MagicMock()
    mock_net.id = "net-vxlan"
    mock_net.name = "vxlan-net"
    mock_net.status = "ACTIVE"
    mock_net.subnet_ids = []
    mock_net.is_router_external = False
    mock_net.is_shared = False
    mock_net.provider_network_type = "vxlan"
    mock_net.provider_segmentation_id = 2000
    mock_net.provider_physical_network = None

    mock_conn.network.get_network.return_value = mock_net
    mock_conn.network.ports.return_value = []

    resp = await admin_client.get("/api/v1/admin/networks/net-vxlan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "net-vxlan"
    assert data["provider_network_type"] == "vxlan"
    assert data["provider_segmentation_id"] == 2000
    assert data["provider_physical_network"] is None


@pytest.mark.asyncio
async def test_admin_get_network_detail_missing_provider_values(admin_client, mock_conn):
    mock_net = MagicMock()
    mock_net.id = "net-flat"
    mock_net.name = "flat-net"
    mock_net.status = "ACTIVE"
    mock_net.subnet_ids = []
    mock_net.is_router_external = False
    mock_net.is_shared = False
    mock_net.provider_network_type = None
    mock_net.provider_segmentation_id = None
    mock_net.provider_physical_network = None

    mock_conn.network.get_network.return_value = mock_net
    mock_conn.network.ports.return_value = []

    resp = await admin_client.get("/api/v1/admin/networks/net-flat")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "net-flat"
    assert data["provider_network_type"] is None
    assert data["provider_segmentation_id"] is None
    assert data["provider_physical_network"] is None


@pytest.mark.asyncio
async def test_ordinary_user_get_network_detail_does_not_contain_provider_keys(client, mock_conn):
    mock_net = MagicMock()
    mock_net.id = "net-user"
    mock_net.name = "user-net"
    mock_net.status = "ACTIVE"
    mock_net.subnet_ids = []
    mock_net.is_router_external = True
    mock_net.is_shared = True
    mock_net.provider_network_type = "vlan"
    mock_net.provider_segmentation_id = 100
    mock_net.provider_physical_network = "physnet1"

    mock_conn.network.get_network.return_value = mock_net
    mock_conn.network.ports.return_value = []

    resp = await client.get("/api/v1/networks/net-user")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "net-user"
    assert "provider_network_type" not in data
    assert "provider_segmentation_id" not in data
    assert "provider_physical_network" not in data


@pytest.mark.asyncio
async def test_admin_get_subnet_detail_non_admin_returns_403(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/subnets/sub-1")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_get_subnet_detail_success(admin_client):
    from app.models.storage import (
        AdminSubnetDetail,
        AdminSubnetPort,
        AllocationPool,
        DhcpBindingInfo,
        SubnetIpAllocation,
    )

    fake_detail = AdminSubnetDetail(
        id="sub-1",
        name="sub-test",
        network_id="net-1",
        network_name="net-test",
        project_id="proj-1",
        cidr="10.0.0.0/24",
        gateway_ip="10.0.0.1",
        ip_version=4,
        dhcp_enabled=True,
        allocation_pools=[AllocationPool(start="10.0.0.10", end="10.0.0.250")],
        ports=[
            AdminSubnetPort(
                id="port-1",
                name="p1",
                status="ACTIVE",
                mac_address="fa:16:3e:00:00:01",
                device_owner="compute:nova",
                device_id="inst-1",
                project_id="proj-1",
                ip_addresses=["10.0.0.5"],
                binding_host_id="node-1",
            )
        ],
        allocations=[
            SubnetIpAllocation(
                ip_address="10.0.0.5",
                port_id="port-1",
                port_name="p1",
                device_owner="compute:nova",
                device_id="inst-1",
                project_id="proj-1",
                binding_host_id="node-1",
            )
        ],
        dhcp_bindings=[
            DhcpBindingInfo(
                agent_id="agent-1",
                host="node-dhcp",
                binary="neutron-dhcp-agent",
                availability_zone="nova",
                alive=True,
                admin_state_up=True,
                source="agent",
                ip_addresses=["10.0.0.2"],
                port_ids=["port-dhcp"],
            )
        ],
        dhcp_agent_data_available=True,
    )

    with patch("app.api.identity.admin.neutron.get_admin_subnet_detail", return_value=fake_detail):
        resp = await admin_client.get("/api/v1/admin/subnets/sub-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "sub-1"
    assert data["network_name"] == "net-test"
    assert data["allocation_pools"] == [{"start": "10.0.0.10", "end": "10.0.0.250"}]
    assert data["ports"][0]["binding_host_id"] == "node-1"
    assert data["allocations"][0]["ip_address"] == "10.0.0.5"
    assert data["dhcp_bindings"][0]["source"] == "agent"
    assert data["dhcp_agent_data_available"] is True


@pytest.mark.asyncio
async def test_admin_get_subnet_detail_not_found(admin_client):
    from openstack.exceptions import NotFoundException

    with patch(
        "app.api.identity.admin.neutron.get_admin_subnet_detail", side_effect=NotFoundException("Subnet not found")
    ):
        resp = await admin_client.get("/api/v1/admin/subnets/sub-missing")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "서브넷을 찾을 수 없습니다"


@pytest.mark.asyncio
async def test_admin_get_subnet_detail_generic_failure(admin_client):
    with patch("app.api.identity.admin.neutron.get_admin_subnet_detail", side_effect=RuntimeError("Unexpected error")):
        resp = await admin_client.get("/api/v1/admin/subnets/sub-error")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "내부 서버 오류"
