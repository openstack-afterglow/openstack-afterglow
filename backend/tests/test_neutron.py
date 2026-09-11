"""neutron.ensure_union_egress_sg + ensure_monitoring_ingress_sg 단위 테스트."""

from unittest.mock import MagicMock, patch

import pytest


def _make_sg(sg_id: str = "sg-1", name: str = "union-egress-default", rules: list | None = None) -> dict:
    return {
        "id": sg_id,
        "name": name,
        "description": "",
        "rules": rules or [],
    }


def _make_rule(protocol: str, port_min: int, port_max: int, direction: str = "egress") -> dict:
    return {
        "id": f"rule-{protocol}-{port_min}",
        "direction": direction,
        "protocol": protocol,
        "port_range_min": port_min,
        "port_range_max": port_max,
        "remote_ip_prefix": "0.0.0.0/0",
        "ethertype": "IPv4",
    }


@patch("app.services.neutron.create_security_group_rule")
@patch("app.services.neutron.create_security_group")
@patch("app.services.neutron.list_security_groups")
def test_ensure_union_egress_sg_creates_when_missing(mock_list, mock_create_sg, mock_create_rule):
    """SG 미존재 시 생성 + 6개 egress rule 등록."""
    from app.services.neutron import ensure_union_egress_sg

    mock_list.return_value = []  # SG 없음
    mock_create_sg.return_value = _make_sg()

    conn = MagicMock()
    result = ensure_union_egress_sg(conn, "proj-1")

    assert result == "union-egress-default"
    mock_create_sg.assert_called_once()
    assert mock_create_rule.call_count == 6  # 6개 rule 등록


@patch("app.services.neutron.create_security_group_rule")
@patch("app.services.neutron.create_security_group")
@patch("app.services.neutron.list_security_groups")
def test_ensure_union_egress_sg_idempotent_when_all_rules_exist(mock_list, mock_create_sg, mock_create_rule):
    """SG 존재 + 모든 rule 존재 시 생성/추가 호출 0."""
    from app.services.neutron import ensure_union_egress_sg

    all_rules = [
        _make_rule("tcp", 2049, 2049),
        _make_rule("udp", 2049, 2049),
        _make_rule("tcp", 6789, 6789),
        _make_rule("tcp", 3300, 3300),
        _make_rule("tcp", 80, 80),
        _make_rule("tcp", 443, 443),
    ]
    mock_list.return_value = [_make_sg(rules=all_rules)]

    conn = MagicMock()
    result = ensure_union_egress_sg(conn, "proj-1")

    assert result == "union-egress-default"
    mock_create_sg.assert_not_called()
    mock_create_rule.assert_not_called()


@patch("app.services.neutron.create_security_group_rule")
@patch("app.services.neutron.create_security_group")
@patch("app.services.neutron.list_security_groups")
def test_ensure_union_egress_sg_adds_missing_rules(mock_list, mock_create_sg, mock_create_rule):
    """SG 존재 + 일부 rule 누락 시 누락분만 추가."""
    from app.services.neutron import ensure_union_egress_sg

    partial_rules = [
        _make_rule("tcp", 2049, 2049),
        _make_rule("udp", 2049, 2049),
        # tcp 6789, 3300, 80, 443 누락
    ]
    mock_list.return_value = [_make_sg(rules=partial_rules)]

    conn = MagicMock()
    ensure_union_egress_sg(conn, "proj-1")

    mock_create_sg.assert_not_called()
    assert mock_create_rule.call_count == 4  # 누락된 4개만 추가


# ---------------------------------------------------------------------------
# A11: _ensure_single_port_ingress_sg / ensure_node_exporter_sg / ensure_dcgm_exporter_sg 단위 테스트
# ---------------------------------------------------------------------------


def _make_ingress_rule(protocol: str, port_min: int, port_max: int, cidr: str = "10.0.0.0/8") -> dict:
    return {
        "id": f"rule-ingress-{protocol}-{port_min}",
        "direction": "ingress",
        "protocol": protocol,
        "port_range_min": port_min,
        "port_range_max": port_max,
        "remote_ip_prefix": cidr,
        "ethertype": "IPv4",
    }


@patch("app.services.neutron.create_security_group_rule")
@patch("app.services.neutron.create_security_group")
@patch("app.services.neutron.list_security_groups")
def test_ensure_single_port_ingress_sg_creates_when_missing(mock_list, mock_create_sg, mock_create_rule):
    """SG 미존재 시 생성 + 1개 ingress rule 등록."""
    from app.services.neutron import _ensure_single_port_ingress_sg

    mock_list.return_value = []
    mock_create_sg.return_value = _make_sg(sg_id="ne-sg-1", name="node_exporter")
    conn = MagicMock()

    result = _ensure_single_port_ingress_sg(
        conn, "proj-1", "node_exporter", port=9100, scrape_cidr="10.0.0.0/8", description="test"
    )

    assert result == "node_exporter"
    mock_create_sg.assert_called_once()
    assert mock_create_rule.call_count == 1
    call_kwargs = mock_create_rule.call_args[1]
    assert call_kwargs["port_range_min"] == 9100
    assert call_kwargs["direction"] == "ingress"
    assert call_kwargs["remote_ip_prefix"] == "10.0.0.0/8"


@patch("app.services.neutron.create_security_group_rule")
@patch("app.services.neutron.create_security_group")
@patch("app.services.neutron.list_security_groups")
def test_ensure_single_port_ingress_sg_idempotent(mock_list, mock_create_sg, mock_create_rule):
    """SG 존재 + rule 존재 시 생성/추가 없음."""
    from app.services.neutron import _ensure_single_port_ingress_sg

    rules = [_make_ingress_rule("tcp", 9100, 9100, "10.0.0.0/8")]
    mock_list.return_value = [_make_sg(name="node_exporter", rules=rules)]
    conn = MagicMock()

    result = _ensure_single_port_ingress_sg(
        conn, "proj-1", "node_exporter", port=9100, scrape_cidr="10.0.0.0/8", description="test"
    )

    assert result == "node_exporter"
    mock_create_sg.assert_not_called()
    mock_create_rule.assert_not_called()


@patch("app.services.neutron.create_security_group_rule")
@patch("app.services.neutron.create_security_group")
@patch("app.services.neutron.list_security_groups")
def test_ensure_single_port_ingress_sg_adds_missing_rule(mock_list, mock_create_sg, mock_create_rule):
    """SG 존재하나 rule 누락 시 rule만 추가."""
    from app.services.neutron import _ensure_single_port_ingress_sg

    mock_list.return_value = [_make_sg(name="node_exporter", rules=[])]
    conn = MagicMock()

    _ensure_single_port_ingress_sg(
        conn, "proj-1", "node_exporter", port=9100, scrape_cidr="10.0.0.0/8", description="test"
    )

    mock_create_sg.assert_not_called()
    assert mock_create_rule.call_count == 1


def test_ensure_single_port_ingress_sg_raises_without_cidr():
    """scrape_cidr 미설정 시 ValueError."""
    import pytest

    from app.services.neutron import _ensure_single_port_ingress_sg

    conn = MagicMock()
    with pytest.raises(ValueError, match="monitoring_scrape_cidr must be set"):
        _ensure_single_port_ingress_sg(conn, "proj-1", "node_exporter", port=9100, scrape_cidr="", description="test")


@patch("app.services.neutron.create_security_group_rule")
@patch("app.services.neutron.create_security_group")
@patch("app.services.neutron.list_security_groups")
def test_ensure_single_port_ingress_sg_custom_name(mock_list, mock_create_sg, mock_create_rule):
    """커스텀 SG 이름 사용."""
    from app.services.neutron import _ensure_single_port_ingress_sg

    mock_list.return_value = []
    mock_create_sg.return_value = _make_sg(name="custom-sg")
    conn = MagicMock()

    result = _ensure_single_port_ingress_sg(
        conn, "proj-1", "custom-sg", port=9400, scrape_cidr="172.16.0.0/12", description="custom"
    )

    assert result == "custom-sg"


@patch("app.services.neutron._ensure_single_port_ingress_sg")
def test_ensure_node_exporter_sg_calls_generic(mock_generic):
    """ensure_node_exporter_sg 가 port=9100, default sg_name='node_exporter' 로 호출."""
    from app.services.neutron import ensure_node_exporter_sg

    mock_generic.return_value = "node_exporter"
    conn = MagicMock()

    result = ensure_node_exporter_sg(conn, "proj-1", scrape_cidr="10.0.0.0/8")

    assert result == "node_exporter"
    _, call_kwargs = mock_generic.call_args[0], mock_generic.call_args[1]
    assert call_kwargs["port"] == 9100
    assert mock_generic.call_args[0][2] == "node_exporter"


@patch("app.services.neutron._ensure_single_port_ingress_sg")
def test_ensure_dcgm_exporter_sg_calls_generic(mock_generic):
    """ensure_dcgm_exporter_sg 가 port=9400, default sg_name='dcgm_exporter' 로 호출."""
    from app.services.neutron import ensure_dcgm_exporter_sg

    mock_generic.return_value = "dcgm_exporter"
    conn = MagicMock()

    result = ensure_dcgm_exporter_sg(conn, "proj-1", scrape_cidr="10.0.0.0/8")

    assert result == "dcgm_exporter"
    _, call_kwargs = mock_generic.call_args[0], mock_generic.call_args[1]
    assert call_kwargs["port"] == 9400
    assert mock_generic.call_args[0][2] == "dcgm_exporter"


def test_strict_network_quota_requires_detailed_floatingip_usage():
    from app.services.neutron import get_network_quota

    conn = MagicMock()
    quota = MagicMock()
    quota.to_dict.return_value = {"floatingip": {"limit": 3}}
    conn.network.get_quota.return_value = quota

    with pytest.raises(ValueError):
        get_network_quota(conn, "project-a", strict=True)


def test_strict_network_quota_does_not_use_limit_only_fallback():
    from app.services.neutron import get_network_quota

    conn = MagicMock()
    conn.network.get_quota.side_effect = RuntimeError("details unavailable")

    with pytest.raises(RuntimeError):
        get_network_quota(conn, "project-a", strict=True)
    conn.network.get_quota.assert_called_once_with("project-a", details=True)


def test_strict_network_quota_preserves_openstacksdk_original_floatingip_key():
    from openstack.network.v2.quota import QuotaDetails

    from app.services.neutron import get_network_quota

    conn = MagicMock()
    conn.network.get_quota.return_value = QuotaDetails.new(floatingip={"limit": 4, "used": 1})

    result = get_network_quota(conn, "project-a", strict=True)

    assert result["floatingip"] == {"limit": 4, "in_use": 1}
    conn.network.get_quota.assert_called_once_with("project-a", details=True)


def test_network_quota_preserves_openstacksdk_original_keys_outside_strict_mode():
    from openstack.network.v2.quota import QuotaDetails

    from app.services.neutron import get_network_quota

    conn = MagicMock()
    conn.network.get_quota.return_value = QuotaDetails.new(
        floatingip={"limit": 5, "used": 2},
        security_group={"limit": 3, "used": 1},
    )
    conn.network.ips.return_value = []
    conn.network.ports.return_value = []

    result = get_network_quota(conn, "project-a")

    assert result["floatingip"] == {"limit": 5, "in_use": 2}
    assert result["security_group"] == {"limit": 3, "in_use": 1}


def test_get_network_detail_shares_serialization_and_omits_provider_attrs():
    from app.services.neutron import get_network_detail

    conn = MagicMock()
    mock_net = MagicMock()
    mock_net.id = "net-1"
    mock_net.name = "user-net"
    mock_net.status = "ACTIVE"
    mock_net.subnet_ids = []
    mock_net.is_router_external = False
    mock_net.is_shared = False
    mock_net.provider_network_type = "vlan"
    mock_net.provider_segmentation_id = 100
    mock_net.provider_physical_network = "physnet1"

    conn.network.get_network.return_value = mock_net
    conn.network.ports.return_value = []

    detail = get_network_detail(conn, "net-1")

    conn.network.get_network.assert_called_once_with("net-1")
    assert detail.id == "net-1"
    assert detail.name == "user-net"
    assert not hasattr(detail, "provider_network_type")
    assert "provider_network_type" not in detail.model_dump()


def test_get_admin_network_detail_vlan():
    from app.services.neutron import get_admin_network_detail

    conn = MagicMock()
    mock_net = MagicMock()
    mock_net.id = "net-vlan"
    mock_net.name = "admin-vlan-net"
    mock_net.status = "ACTIVE"
    mock_net.subnet_ids = []
    mock_net.is_router_external = False
    mock_net.is_shared = False
    mock_net.provider_network_type = "vlan"
    mock_net.provider_segmentation_id = 100
    mock_net.provider_physical_network = "physnet1"

    conn.network.get_network.return_value = mock_net
    conn.network.ports.return_value = []

    detail = get_admin_network_detail(conn, "net-vlan")

    conn.network.get_network.assert_called_once_with("net-vlan")
    assert detail.id == "net-vlan"
    assert detail.provider_network_type == "vlan"
    assert detail.provider_segmentation_id == 100
    assert detail.provider_physical_network == "physnet1"


def test_get_admin_network_detail_vxlan():
    from app.services.neutron import get_admin_network_detail

    conn = MagicMock()
    mock_net = MagicMock()
    mock_net.id = "net-vxlan"
    mock_net.name = "admin-vxlan-net"
    mock_net.status = "ACTIVE"
    mock_net.subnet_ids = []
    mock_net.is_router_external = False
    mock_net.is_shared = False
    mock_net.provider_network_type = "vxlan"
    mock_net.provider_segmentation_id = 5000
    mock_net.provider_physical_network = None

    conn.network.get_network.return_value = mock_net
    conn.network.ports.return_value = []

    detail = get_admin_network_detail(conn, "net-vxlan")

    conn.network.get_network.assert_called_once_with("net-vxlan")
    assert detail.provider_network_type == "vxlan"
    assert detail.provider_segmentation_id == 5000
    assert detail.provider_physical_network is None


def test_get_admin_network_detail_missing_provider_values():
    from app.services.neutron import get_admin_network_detail

    conn = MagicMock()
    mock_net = MagicMock()
    mock_net.id = "net-flat"
    mock_net.name = "admin-flat-net"
    mock_net.status = "ACTIVE"
    mock_net.subnet_ids = []
    mock_net.is_router_external = False
    mock_net.is_shared = False
    mock_net.provider_network_type = None
    mock_net.provider_segmentation_id = None
    mock_net.provider_physical_network = None

    conn.network.get_network.return_value = mock_net
    conn.network.ports.return_value = []

    detail = get_admin_network_detail(conn, "net-flat")

    conn.network.get_network.assert_called_once_with("net-flat")
    assert detail.provider_network_type is None
    assert detail.provider_segmentation_id is None
    assert detail.provider_physical_network is None


def test_get_admin_subnet_detail_pools_ports_allocations_agents_ordering():
    from app.services.neutron import get_admin_subnet_detail

    conn = MagicMock()

    mock_subnet = MagicMock()
    mock_subnet.id = "sub-1"
    mock_subnet.name = "subnet-main"
    mock_subnet.network_id = "net-1"
    mock_subnet.cidr = "192.168.1.0/24"
    mock_subnet.gateway_ip = "192.168.1.1"
    mock_subnet.ip_version = 4
    mock_subnet.is_dhcp_enabled = True
    mock_subnet.project_id = "proj-1"
    mock_subnet.allocation_pools = [
        {"start": "192.168.1.100", "end": "192.168.1.200"},
        {"start": "192.168.1.10", "end": "192.168.1.20"},
    ]

    mock_network = MagicMock()
    mock_network.id = "net-1"
    mock_network.name = "network-main"

    conn.network.get_subnet.return_value = mock_subnet
    conn.network.get_network.return_value = mock_network

    port1 = {
        "id": "port-1",
        "name": "vm-port-1",
        "status": "ACTIVE",
        "mac_address": "fa:16:3e:00:00:01",
        "device_owner": "compute:nova",
        "device_id": "inst-1",
        "project_id": "proj-1",
        "binding_host_id": "node-compute-1",
        "fixed_ips": [
            {"subnet_id": "sub-1", "ip_address": "192.168.1.15"},
            {"subnet_id": "sub-other", "ip_address": "10.0.0.99"},
        ],
    }
    port2 = {
        "id": "port-2",
        "name": "vm-port-2",
        "status": "ACTIVE",
        "mac_address": "fa:16:3e:00:00:02",
        "device_owner": "compute:nova",
        "device_id": "inst-2",
        "project_id": "proj-1",
        "binding_host_id": "node-compute-2",
        "fixed_ips": [{"subnet_id": "sub-1", "ip_address": "192.168.1.5"}],
    }
    dhcp_port = {
        "id": "port-dhcp",
        "name": "dhcp-port",
        "status": "ACTIVE",
        "mac_address": "fa:16:3e:00:00:03",
        "device_owner": "network:dhcp",
        "device_id": "dhcp-agent-1-net-1",
        "project_id": "proj-1",
        "binding_host_id": "node-dhcp-1",
        "fixed_ips": [{"subnet_id": "sub-1", "ip_address": "192.168.1.2"}],
    }
    other_port = {
        "id": "port-other",
        "name": "other-subnet-port",
        "status": "ACTIVE",
        "mac_address": "fa:16:3e:00:00:04",
        "device_owner": "compute:nova",
        "device_id": "inst-3",
        "project_id": "proj-1",
        "binding_host_id": "node-compute-3",
        "fixed_ips": [{"subnet_id": "sub-other", "ip_address": "10.0.0.10"}],
    }
    conn.network.ports.return_value = [port1, port2, dhcp_port, other_port]

    agent1 = {
        "id": "agent-1",
        "host": "node-dhcp-1",
        "binary": "neutron-dhcp-agent",
        "availability_zone": "nova",
        "is_alive": True,
        "is_admin_state_up": True,
    }
    conn.network.network_hosting_dhcp_agents.return_value = [agent1]

    detail = get_admin_subnet_detail(conn, "sub-1")

    conn.network.get_subnet.assert_called_once_with("sub-1")
    conn.network.get_network.assert_called_once_with("net-1")
    conn.network.ports.assert_called_once_with(network_id="net-1")
    conn.network.network_hosting_dhcp_agents.assert_called_once_with("net-1")

    assert detail.id == "sub-1"
    assert detail.name == "subnet-main"
    assert detail.network_name == "network-main"
    assert detail.dhcp_agent_data_available is True

    # 1. Pools ordered by numeric IP
    assert [p.start for p in detail.allocation_pools] == ["192.168.1.10", "192.168.1.100"]

    # 2. Ports filtered to sub-1, excluding port-other, and stripping 10.0.0.99
    assert len(detail.ports) == 3
    port_map = {p.id: p for p in detail.ports}
    assert "port-other" not in port_map
    assert port_map["port-1"].ip_addresses == ["192.168.1.15"]
    assert port_map["port-1"].binding_host_id == "node-compute-1"

    # 3. Allocations ordered by numeric IP
    alloc_ips = [a.ip_address for a in detail.allocations]
    assert alloc_ips == ["192.168.1.2", "192.168.1.5", "192.168.1.15"]
    assert detail.allocations[0].port_id == "port-dhcp"
    assert detail.allocations[0].binding_host_id == "node-dhcp-1"

    # 4. Agent mapping
    assert len(detail.dhcp_bindings) == 1
    ag = detail.dhcp_bindings[0]
    assert ag.source == "agent"
    assert ag.agent_id == "agent-1"
    assert ag.host == "node-dhcp-1"
    assert ag.ip_addresses == ["192.168.1.2"]
    assert ag.port_ids == ["port-dhcp"]


def test_get_admin_subnet_detail_scheduler_fallback_and_unmatched_dhcp_ports():
    from app.services.neutron import get_admin_subnet_detail

    conn = MagicMock()

    mock_subnet = MagicMock()
    mock_subnet.id = "sub-ovn"
    mock_subnet.name = "subnet-ovn"
    mock_subnet.network_id = "net-ovn"
    mock_subnet.cidr = "10.10.0.0/24"
    mock_subnet.gateway_ip = "10.10.0.1"
    mock_subnet.ip_version = 4
    mock_subnet.is_dhcp_enabled = True
    mock_subnet.project_id = "proj-1"
    mock_subnet.allocation_pools = []

    mock_network = MagicMock()
    mock_network.id = "net-ovn"
    mock_network.name = "network-ovn"

    conn.network.get_subnet.return_value = mock_subnet
    conn.network.get_network.return_value = mock_network

    dhcp_port = {
        "id": "port-ovn-dhcp",
        "name": "ovn-dhcp-port",
        "status": "ACTIVE",
        "mac_address": "fa:16:3e:00:00:10",
        "device_owner": "network:dhcp",
        "device_id": "ovnmeta-net-ovn",
        "project_id": "proj-1",
        "binding_host_id": "host-ovn-1",
        "fixed_ips": [{"subnet_id": "sub-ovn", "ip_address": "10.10.0.2"}],
    }
    conn.network.ports.return_value = [dhcp_port]
    conn.network.network_hosting_dhcp_agents.side_effect = Exception("DHCP agent scheduler extension not supported")

    detail = get_admin_subnet_detail(conn, "sub-ovn")

    assert detail.id == "sub-ovn"
    assert detail.dhcp_agent_data_available is False
    assert len(detail.ports) == 1
    assert len(detail.allocations) == 1
    assert detail.allocations[0].ip_address == "10.10.0.2"
    assert detail.allocations[0].binding_host_id == "host-ovn-1"

    # Synthesized source='port' DHCP binding
    assert len(detail.dhcp_bindings) == 1
    binding = detail.dhcp_bindings[0]
    assert binding.source == "port"
    assert binding.agent_id is None
    assert binding.host == "host-ovn-1"
    assert binding.ip_addresses == ["10.10.0.2"]
    assert binding.port_ids == ["port-ovn-dhcp"]


# ---------------------------------------------------------------------------
# list_networks & CIDR serialization tests
# ---------------------------------------------------------------------------


class _DummyNet:
    def __init__(
        self,
        net_id: str,
        name: str = "",
        status: str = "ACTIVE",
        subnet_ids: list[str] | None = None,
        project_id: str = "proj-1",
        is_router_external: bool = False,
        is_shared: bool = False,
    ):
        self.id = net_id
        self.name = name
        self.status = status
        self.subnet_ids = subnet_ids or []
        self.project_id = project_id
        self.is_router_external = is_router_external
        self.is_shared = is_shared


class _DummySubnet:
    def __init__(self, subnet_id: str, network_id: str, cidr: str):
        self.id = subnet_id
        self.network_id = network_id
        self.cidr = cidr


def test_list_networks_cidrs_single_multiple_missing_and_orphan():
    from app.services.neutron import list_networks

    conn = MagicMock()
    net1 = _DummyNet("net-1", name="net-single", subnet_ids=["sub-1"])
    net2 = _DummyNet("net-2", name="net-multi", subnet_ids=["sub-2a", "sub-2b"])
    net3 = _DummyNet("net-3", name="net-empty", subnet_ids=[])

    sub1 = _DummySubnet("sub-1", "net-1", "10.0.0.0/24")
    sub2a = _DummySubnet("sub-2a", "net-2", "192.168.1.0/24")
    sub2b = _DummySubnet("sub-2b", "net-2", "172.16.0.0/16")
    orphan_sub = _DummySubnet("sub-orphan", "orphan-net", "10.99.0.0/24")

    conn.network.networks.return_value = [net1, net2, net3]
    conn.network.subnets.return_value = [sub1, sub2a, sub2b, orphan_sub]

    res = list_networks(conn)

    assert conn.network.networks.call_count == 1
    assert conn.network.subnets.call_count == 1
    assert getattr(conn.network, "get_subnet", MagicMock()).call_count == 0

    assert len(res) == 3
    assert res[0].id == "net-1"
    assert res[0].cidrs == ["10.0.0.0/24"]

    assert res[1].id == "net-2"
    assert res[1].cidrs == ["172.16.0.0/16", "192.168.1.0/24"]

    assert res[2].id == "net-3"
    assert res[2].cidrs == []


def test_list_networks_numeric_cidr_ordering_and_deduplication():
    from app.services.neutron import list_networks

    conn = MagicMock()
    net = _DummyNet("net-1", name="net-ordering", subnet_ids=["s1", "s2", "s3", "s4", "s5", "s6"])
    subnets = [
        _DummySubnet("s1", "net-1", "192.168.1.0/24"),
        _DummySubnet("s2", "net-1", "10.0.1.0/24"),
        _DummySubnet("s3", "net-1", "2001:db8::/32"),
        _DummySubnet("s4", "net-1", "10.0.0.0/24"),
        _DummySubnet("s5", "net-1", "10.0.0.0/16"),
        _DummySubnet("s6", "net-1", "10.0.0.0/24"),
    ]

    conn.network.networks.return_value = [net]
    conn.network.subnets.return_value = subnets

    res = list_networks(conn)

    assert len(res) == 1
    assert res[0].cidrs == [
        "10.0.0.0/16",
        "10.0.0.0/24",
        "10.0.1.0/24",
        "192.168.1.0/24",
        "2001:db8::/32",
    ]


def test_list_networks_visibility_filtering():
    from app.services.neutron import list_networks

    conn = MagicMock()
    owned_net = _DummyNet("net-owned", project_id="proj-a")
    ext_net = _DummyNet("net-ext", project_id="proj-b", is_router_external=True)
    shared_net = _DummyNet("net-shared", project_id="proj-c", is_shared=True)
    private_other_net = _DummyNet("net-private-other", project_id="proj-b")

    sub_owned = _DummySubnet("s-owned", "net-owned", "10.1.0.0/24")
    sub_ext = _DummySubnet("s-ext", "net-ext", "203.0.113.0/24")
    sub_shared = _DummySubnet("s-shared", "net-shared", "10.2.0.0/24")
    sub_private_other = _DummySubnet("s-priv", "net-private-other", "10.3.0.0/24")

    conn.network.networks.return_value = [owned_net, ext_net, shared_net, private_other_net]
    conn.network.subnets.return_value = [sub_owned, sub_ext, sub_shared, sub_private_other]

    res = list_networks(conn, project_id="proj-a")

    assert conn.network.networks.call_count == 1
    assert conn.network.subnets.call_count == 1

    net_ids = [n.id for n in res]
    assert net_ids == ["net-owned", "net-ext", "net-shared"]
    assert res[0].cidrs == ["10.1.0.0/24"]
    assert res[1].cidrs == ["203.0.113.0/24"]
    assert res[2].cidrs == ["10.2.0.0/24"]


def test_net_to_info_optional_cidrs_parameter():
    from app.services.neutron import _net_to_info

    net = _DummyNet("net-1", name="demo", status="ACTIVE", subnet_ids=["sub-1"])

    info1 = _net_to_info(net)
    assert info1.cidrs == []

    info2 = _net_to_info(net, ["10.0.0.0/24", "10.0.1.0/24"])
    assert info2.cidrs == ["10.0.0.0/24", "10.0.1.0/24"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# get_topology — mtu / enable_snat / routes / provider (include_provider) / compute 포트 인덱스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _topology_conn():
    """networks/subnets/routers/ports/ips 를 stub 한 MagicMock conn."""
    conn = MagicMock()

    net = MagicMock()
    net.id = "net-1"
    net.name = "vlan-net"
    net.status = "ACTIVE"
    net.is_router_external = False
    net.is_shared = False
    net.project_id = "proj-1"
    net.mtu = "1450"  # 문자열도 int 로 변환된다
    net.provider_network_type = "vlan"
    net.provider_segmentation_id = "100"
    net.provider_physical_network = "physnet1"
    conn.network.networks.return_value = [net]

    subnet = MagicMock()
    subnet.id = "subnet-1"
    subnet.name = "subnet-1"
    subnet.cidr = "10.0.0.0/24"
    subnet.gateway_ip = "10.0.0.1"
    subnet.is_dhcp_enabled = True
    subnet.network_id = "net-1"
    conn.network.subnets.return_value = [subnet]

    router_with_gw = MagicMock()
    router_with_gw.id = "r-gw"
    router_with_gw.name = "router-gw"
    router_with_gw.status = "ACTIVE"
    router_with_gw.project_id = "proj-1"
    router_with_gw.is_distributed = False
    router_with_gw.is_ha = False
    router_with_gw.external_gateway_info = {
        "network_id": "net-ext",
        "enable_snat": False,
        "external_fixed_ips": [{"ip_address": "203.0.113.5", "subnet_id": "subnet-ext"}],
    }
    router_with_gw.routes = [
        {"destination": "10.20.0.0/16", "nexthop": "10.0.0.254"},
        {"destination": "10.30.0.0/16"},  # nexthop 누락 → 제외
        "garbage",  # dict 아님 → 제외
    ]

    router_no_gw = MagicMock()
    router_no_gw.id = "r-nogw"
    router_no_gw.name = "router-nogw"
    router_no_gw.status = "ACTIVE"
    router_no_gw.project_id = "proj-1"
    router_no_gw.is_distributed = False
    router_no_gw.is_ha = False
    router_no_gw.external_gateway_info = None
    router_no_gw.routes = None
    conn.network.routers.return_value = [router_with_gw, router_no_gw]

    conn.network.ports.return_value = []
    conn.network.ips.return_value = []
    return conn


def test_get_topology_default_omits_provider_keys_and_fills_mtu_snat_routes():
    from app.models.storage import AdminTopologyData, TopologyData
    from app.services.neutron import get_topology

    conn = _topology_conn()
    topo = get_topology(conn)

    assert isinstance(topo, TopologyData)
    assert not isinstance(topo, AdminTopologyData)
    net = topo.networks[0].model_dump()
    assert net["mtu"] == 1450
    assert "provider_network_type" not in net
    assert "provider_segmentation_id" not in net
    assert "provider_physical_network" not in net
    assert "provider_segmentation_id" not in topo.model_dump()["networks"][0]

    routers = {r.id: r for r in topo.routers}
    assert routers["r-gw"].enable_snat is False
    assert routers["r-gw"].routes == [{"destination": "10.20.0.0/16", "nexthop": "10.0.0.254"}]
    assert routers["r-gw"].external_gateway_ips == ["203.0.113.5"]
    assert routers["r-nogw"].enable_snat is None
    assert routers["r-nogw"].routes == []


def test_get_topology_include_provider_returns_admin_models():
    from app.models.storage import AdminTopologyData, AdminTopologyNetwork
    from app.services.neutron import get_topology

    conn = _topology_conn()
    topo = get_topology(conn, include_provider=True)

    assert isinstance(topo, AdminTopologyData)
    assert isinstance(topo.networks[0], AdminTopologyNetwork)
    net = topo.model_dump()["networks"][0]
    assert net["mtu"] == 1450
    assert net["provider_network_type"] == "vlan"
    assert net["provider_segmentation_id"] == 100
    assert net["provider_physical_network"] == "physnet1"
    # 라우터 필드는 provider 여부와 무관하게 동일하다
    assert {r.id: r.enable_snat for r in topo.routers} == {"r-gw": False, "r-nogw": None}


def test_get_topology_call_count_unchanged_with_include_provider():
    """include_provider 는 추가 OpenStack 호출을 만들지 않는다."""
    from app.services.neutron import get_topology

    def _call_counts(include_provider: bool) -> dict[str, int]:
        conn = _topology_conn()
        get_topology(conn, include_provider=include_provider)
        conn.network.get_network.assert_not_called()
        conn.network.get_router.assert_not_called()
        return {
            name: getattr(conn.network, name).call_count for name in ("networks", "subnets", "routers", "ports", "ips")
        }

    baseline = _call_counts(False)
    assert baseline["networks"] == 1
    assert baseline["subnets"] == 1
    assert baseline["routers"] == 1
    assert baseline["ips"] == 1
    assert _call_counts(True) == baseline


def test_get_topology_invalid_mtu_and_segmentation_become_none():
    from app.services.neutron import get_topology

    conn = _topology_conn()
    net = conn.network.networks.return_value[0]
    net.mtu = "not-a-number"
    net.provider_segmentation_id = "n/a"

    topo = get_topology(conn, include_provider=True)
    dumped = topo.model_dump()["networks"][0]
    assert dumped["mtu"] is None
    assert dumped["provider_segmentation_id"] is None


def test_build_compute_port_index_filters_and_maps_meta():
    from app.services.neutron import build_compute_port_index

    def _port(port_id, device_id, owner, network_id, ips, mac="fa:16:3e:aa:bb:cc"):
        p = MagicMock()
        p.id = port_id
        p.device_id = device_id
        p.device_owner = owner
        p.network_id = network_id
        p.mac_address = mac
        p.fixed_ips = [{"ip_address": ip, "subnet_id": "s"} for ip in ips]
        return p

    conn = MagicMock()
    conn.network.ports.return_value = [
        _port("p-1", "vm-1", "compute:nova", "net-a", ["10.0.0.5", "fd00::5"], mac="fa:16:3e:00:00:01"),
        _port("p-2", "vm-1", "compute:az2", "net-b", ["10.0.1.7"], mac="fa:16:3e:00:00:02"),
        _port("p-r", "r-1", "network:router_interface", "net-a", ["10.0.0.1"]),
        _port("p-dhcp", "", "compute:nova", "net-a", ["10.0.0.2"]),
        _port("p-noip", "vm-2", "compute:nova", "net-a", []),
    ]

    index = build_compute_port_index(conn)

    conn.network.ports.assert_called_once_with()
    assert index[("vm-1", "10.0.0.5")] == {"network_id": "net-a", "port_id": "p-1", "mac_address": "fa:16:3e:00:00:01"}
    assert index[("vm-1", "fd00::5")]["port_id"] == "p-1"
    assert index[("vm-1", "10.0.1.7")] == {"network_id": "net-b", "port_id": "p-2", "mac_address": "fa:16:3e:00:00:02"}
    assert ("r-1", "10.0.0.1") not in index
    assert ("", "10.0.0.2") not in index
    assert all(key[0] != "vm-2" for key in index)
