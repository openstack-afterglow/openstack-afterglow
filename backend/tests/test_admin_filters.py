"""관리자 엔드포인트 필터 파라미터 단위 테스트 (volumes, instances, topology)."""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# all-volumes 필터
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _make_volume(vid="v1", name="test-vol", status="available", project_id="proj-1"):
    v = MagicMock()
    v.id = vid
    v.name = name
    v.status = status
    v.size = 10
    v.project_id = project_id
    v.created_at = "2026-01-01T00:00:00Z"
    return v


def _iter_sdk_volumes(statuses):
    """SDK volume list calls return an iterator, not a paginated response dict."""
    for index, status in enumerate(statuses, start=1):
        volume = MagicMock()
        volume.id = f"vol-{index}"
        volume.status = status
        yield volume


@pytest.mark.asyncio
async def test_volume_status_summary_counts_all_project_sdk_iterator(admin_client, mock_conn):
    """status-summary counts the full all-project SDK iterator and normalizes status casing."""
    statuses = ["AVAILABLE"] * 25 + ["available", "Error", "IN-USE", None]
    mock_conn.block_storage.volumes.return_value = _iter_sdk_volumes(statuses)
    mock_conn.session.get.side_effect = AssertionError("status summary must not call paginated /volumes/detail")

    resp = await admin_client.get("/api/v1/admin/volumes/status-summary")

    assert resp.status_code == 200
    assert resp.json() == {
        "total": 29,
        "statuses": [
            {"status": "available", "count": 26},
            {"status": "error", "count": 1},
            {"status": "in-use", "count": 1},
            {"status": "unknown", "count": 1},
        ],
    }
    mock_conn.block_storage.volumes.assert_called_once_with(details=True, all_projects=True)
    mock_conn.session.get.assert_not_called()


@pytest.mark.asyncio
async def test_all_volumes_status_filter(admin_client, mock_conn):
    """status 파라미터가 Cinder SDK kwargs로 전달된다."""
    vol = _make_volume(status="available")
    mock_conn.block_storage.volumes.return_value = [vol]

    resp = await admin_client.get("/api/v1/admin/all-volumes?limit=10&status=available")
    assert resp.status_code == 200

    call_kwargs = mock_conn.block_storage.volumes.call_args[1]
    assert call_kwargs.get("status") == "available"


@pytest.mark.asyncio
async def test_all_volumes_project_id_filter(admin_client, mock_conn):
    """project_id 파라미터가 Cinder SDK kwargs로 전달된다."""
    vol = _make_volume(project_id="proj-abc")
    mock_conn.block_storage.volumes.return_value = [vol]

    resp = await admin_client.get("/api/v1/admin/all-volumes?limit=10&project_id=proj-abc")
    assert resp.status_code == 200

    call_kwargs = mock_conn.block_storage.volumes.call_args[1]
    assert call_kwargs.get("project_id") == "proj-abc"


@pytest.mark.asyncio
async def test_all_volumes_name_filter(admin_client, mock_conn):
    """name 파라미터가 name~ (substring) 키로 SDK에 전달된다."""
    vol = _make_volume(name="my-vol")
    mock_conn.block_storage.volumes.return_value = [vol]

    resp = await admin_client.get("/api/v1/admin/all-volumes?limit=10&name=my-vol")
    assert resp.status_code == 200

    call_kwargs = mock_conn.block_storage.volumes.call_args[1]
    assert call_kwargs.get("name~") == "my-vol"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# all-instances 필터
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _make_servers_response(name="test-vm", status="ACTIVE", vid="inst-1"):
    return {
        "servers": [
            {
                "id": vid,
                "name": name,
                "status": status,
                "tenant_id": "proj-1",
                "user_id": "user-1",
                "flavor": {"original_name": "cpu.2c_4g"},
                "OS-EXT-SRV-ATTR:host": "compute1",
                "created": "2026-01-01T00:00:00Z",
            }
        ]
    }


def _make_session_response(data: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.json.return_value = data
    return mock_resp


@pytest.mark.asyncio
async def test_all_instances_status_filter(admin_client, mock_conn):
    """status 파라미터가 Nova API params로 전달된다."""
    mock_conn.compute.get_endpoint.return_value = "http://nova"
    mock_conn.session.get.return_value = _make_session_response(_make_servers_response(status="ACTIVE"))

    resp = await admin_client.get("/api/v1/admin/all-instances?limit=10&status=ACTIVE")
    assert resp.status_code == 200

    call_kwargs = mock_conn.session.get.call_args[1]
    assert call_kwargs["params"].get("status") == "ACTIVE"


@pytest.mark.asyncio
async def test_all_instances_name_filter_wraps_in_regex(admin_client, mock_conn):
    """name 파라미터가 .*{re.escape(input)}.* 형태의 regex로 Nova에 전달된다."""
    mock_conn.compute.get_endpoint.return_value = "http://nova"
    mock_conn.session.get.return_value = _make_session_response(_make_servers_response(name="test-vm"))

    resp = await admin_client.get("/api/v1/admin/all-instances?limit=10&name=test-vm")
    assert resp.status_code == 200

    call_kwargs = mock_conn.session.get.call_args[1]
    name_param = call_kwargs["params"].get("name")
    assert name_param is not None
    expected = ".*" + re.escape("test-vm") + ".*"
    assert name_param == expected


@pytest.mark.asyncio
async def test_all_instances_name_filter_escapes_metachar(admin_client, mock_conn):
    """name 필터의 정규식 메타문자가 escape 처리된다."""
    mock_conn.compute.get_endpoint.return_value = "http://nova"
    mock_conn.session.get.return_value = _make_session_response({"servers": []})

    resp = await admin_client.get("/api/v1/admin/all-instances?limit=10&name=test.vm%5B")
    assert resp.status_code == 200

    call_kwargs = mock_conn.session.get.call_args[1]
    name_param = call_kwargs["params"].get("name")
    assert ".*" in name_param
    assert r"\." in name_param
    assert r"\[" in name_param


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# topology — instance.project_id 필드
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_topology_instance_includes_project_id(admin_client, mock_conn):
    """topology 응답의 instance 항목에 project_id 필드가 포함된다."""
    from app.models.storage import TopologyData

    mock_server = MagicMock()
    mock_server.id = "inst-1"
    mock_server.name = "my-vm"
    mock_server.status = "ACTIVE"
    mock_server.project_id = "proj-topo"
    mock_server.tenant_id = None
    mock_server.addresses = {}

    mock_conn.compute.servers.return_value = [mock_server]
    mock_conn.network.ports.return_value = []

    topo_data = TopologyData(networks=[], routers=[], instances=[], floating_ips=[])

    with (
        patch("app.api.identity.admin.neutron.get_topology", return_value=topo_data),
        patch("app.api.identity.admin.cached_call", new=AsyncMock(side_effect=lambda key, ttl, fn, **kw: fn())),
    ):
        resp = await admin_client.get("/api/v1/admin/topology")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["instances"]) == 1
    assert data["instances"][0]["project_id"] == "proj-topo"


def _make_topology_port(port_id, device_id, network_id, ip, mac, device_owner="compute:nova"):
    p = MagicMock()
    p.id = port_id
    p.mac_address = mac
    p.device_id = device_id
    p.device_owner = device_owner
    p.network_id = network_id
    p.fixed_ips = [{"ip_address": ip, "subnet_id": f"subnet-{network_id}"}]
    return p


@pytest.mark.asyncio
async def test_admin_topology_exposes_provider_meta_and_port_meta(admin_client, mock_conn):
    """admin topology 는 provider 세그먼트·mtu·SNAT·정적 경로·per-NIC 포트 메타·flavor/image 를 노출한다."""
    from app.models.storage import AdminTopologyData, AdminTopologyNetwork, TopologyRouter

    mock_server = MagicMock()
    mock_server.id = "inst-1"
    mock_server.name = "my-vm"
    mock_server.status = "ACTIVE"
    mock_server.project_id = "proj-topo"
    mock_server.tenant_id = None
    mock_server.flavor = {"original_name": "m1.small", "vcpus": 1}
    mock_server.image = {"id": "img-1"}
    mock_server.addresses = {
        "net-a": [{"addr": "10.0.0.5", "OS-EXT-IPS:type": "fixed"}],
        "net-b": [{"addr": "10.0.1.7", "OS-EXT-IPS:type": "fixed"}],
    }

    mock_conn.compute.servers.return_value = [mock_server]
    mock_conn.network.ports.return_value = [
        _make_topology_port("port-1", "inst-1", "net-a-id", "10.0.0.5", "fa:16:3e:00:00:01"),
        _make_topology_port("port-2", "inst-1", "net-b-id", "10.0.1.7", "fa:16:3e:00:00:02"),
    ]

    topo_data = AdminTopologyData(
        networks=[
            AdminTopologyNetwork(
                id="net-a-id",
                name="net-a",
                status="ACTIVE",
                mtu=1500,
                provider_network_type="vlan",
                provider_segmentation_id=100,
                provider_physical_network="physnet1",
            )
        ],
        routers=[
            TopologyRouter(
                id="r-1",
                name="router-1",
                status="ACTIVE",
                external_gateway_network_id="ext",
                enable_snat=True,
                routes=[{"destination": "192.168.50.0/24", "nexthop": "10.0.0.250"}],
            )
        ],
        instances=[],
        floating_ips=[],
    )

    with (
        patch("app.api.identity.admin.neutron.get_topology", return_value=topo_data) as get_topology,
        patch("app.api.identity.admin.cached_call", new=AsyncMock(side_effect=lambda key, ttl, fn, **kw: fn())),
    ):
        resp = await admin_client.get("/api/v1/admin/topology")

    assert resp.status_code == 200
    get_topology.assert_called_once_with(mock_conn, include_provider=True)
    data = resp.json()

    network = data["networks"][0]
    assert network["mtu"] == 1500
    assert network["provider_network_type"] == "vlan"
    assert network["provider_segmentation_id"] == 100
    assert network["provider_physical_network"] == "physnet1"

    router = data["routers"][0]
    assert router["enable_snat"] is True
    assert router["routes"] == [{"destination": "192.168.50.0/24", "nexthop": "10.0.0.250"}]

    inst = data["instances"][0]
    assert inst["flavor_name"] == "m1.small"
    assert inst["image_id"] == "img-1"
    by_addr = {ip["addr"]: ip for ip in inst["ip_addresses"]}
    assert by_addr["10.0.0.5"]["network_id"] == "net-a-id"
    assert by_addr["10.0.0.5"]["port_id"] == "port-1"
    assert by_addr["10.0.0.5"]["mac_addr"] == "fa:16:3e:00:00:01"
    assert by_addr["10.0.1.7"]["network_id"] == "net-b-id"
    assert by_addr["10.0.1.7"]["port_id"] == "port-2"
    assert by_addr["10.0.1.7"]["mac_addr"] == "fa:16:3e:00:00:02"


@pytest.mark.asyncio
async def test_admin_topology_flavor_image_null_when_not_dict(admin_client, mock_conn):
    """flavor/image 가 dict 가 아니면(빈 문자열·None) flavor_name/image_id 는 null 이다."""
    from app.models.storage import AdminTopologyData

    mock_server = MagicMock()
    mock_server.id = "inst-2"
    mock_server.name = "vm-noimg"
    mock_server.status = "ACTIVE"
    mock_server.project_id = "proj-topo"
    mock_server.tenant_id = None
    mock_server.flavor = None
    mock_server.image = ""  # 볼륨 부팅 인스턴스는 image 가 빈 문자열
    mock_server.addresses = {}

    mock_conn.compute.servers.return_value = [mock_server]
    mock_conn.network.ports.return_value = []

    with (
        patch("app.api.identity.admin.neutron.get_topology", return_value=AdminTopologyData()),
        patch("app.api.identity.admin.cached_call", new=AsyncMock(side_effect=lambda key, ttl, fn, **kw: fn())),
    ):
        resp = await admin_client.get("/api/v1/admin/topology")

    assert resp.status_code == 200
    inst = resp.json()["instances"][0]
    assert inst["flavor_name"] is None
    assert inst["image_id"] is None


@pytest.mark.asyncio
async def test_admin_topology_http_exception_propagates(admin_client, mock_conn):
    """admin topology 조회 도중 HTTPException 은 상태 코드를 유지한 채 전달된다."""
    from fastapi import HTTPException

    with (
        patch(
            "app.api.identity.admin.neutron.get_topology",
            side_effect=HTTPException(status_code=503, detail="인증 서비스 지연"),
        ),
        patch("app.api.identity.admin.cached_call", new=AsyncMock(side_effect=lambda key, ttl, fn, **kw: fn())),
    ):
        resp = await admin_client.get("/api/v1/admin/topology")
    assert resp.status_code == 503


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# topology — is_database (Trove DB 인스턴스 표시)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _make_topology_server(sid, addresses, project_id="proj-topo"):
    s = MagicMock()
    s.id = sid
    s.name = f"vm-{sid}"
    s.status = "ACTIVE"
    s.project_id = project_id
    s.tenant_id = None
    s.flavor = None
    s.image = None
    s.addresses = addresses
    return s


@pytest.mark.asyncio
async def test_admin_topology_flags_database_instances(admin_client, mock_conn):
    """admin topology 도 Trove fixed IP 매칭으로 is_database 를 표시하고, 전체 프로젝트 목록을 조회한다."""
    from app.models.storage import AdminTopologyData

    db_server = _make_topology_server("inst-db", {"net-a": [{"addr": "10.0.0.11", "OS-EXT-IPS:type": "fixed"}]})
    plain_server = _make_topology_server("inst-plain", {"net-a": [{"addr": "10.0.0.12", "OS-EXT-IPS:type": "fixed"}]})
    # floating IP 가 Trove IP 와 우연히 같은 경우는 표시하지 않는다
    fip_server = _make_topology_server("inst-fip", {"net-a": [{"addr": "203.0.113.11", "OS-EXT-IPS:type": "floating"}]})

    mock_conn.compute.servers.return_value = [db_server, plain_server, fip_server]
    mock_conn.network.ports.return_value = []

    with (
        patch("app.api.identity.admin.neutron.get_topology", return_value=AdminTopologyData()),
        patch(
            "app.api.identity.admin.trove.topology_database_ips",
            return_value={"10.0.0.11", "203.0.113.11"},
        ) as db_ips,
        patch("app.api.identity.admin.cached_call", new=AsyncMock(side_effect=lambda key, ttl, fn, **kw: fn())),
    ):
        resp = await admin_client.get("/api/v1/admin/topology")

    assert resp.status_code == 200
    by_id = {i["id"]: i for i in resp.json()["instances"]}
    assert by_id["inst-db"]["is_database"] is True
    assert by_id["inst-plain"]["is_database"] is False
    assert by_id["inst-fip"]["is_database"] is False
    assert db_ips.call_args.kwargs.get("all_projects") is True


@pytest.mark.asyncio
async def test_admin_topology_database_flag_fails_soft(admin_client, mock_conn):
    """Trove 조회 예외 시에도 admin topology 는 200 이며 is_database 는 모두 false 다."""
    from app.models.storage import AdminTopologyData

    server = _make_topology_server("inst-1", {"net-a": [{"addr": "10.0.0.11", "OS-EXT-IPS:type": "fixed"}]})
    mock_conn.compute.servers.return_value = [server]
    mock_conn.network.ports.return_value = []

    with (
        patch("app.api.identity.admin.neutron.get_topology", return_value=AdminTopologyData()),
        patch(
            "app.api.identity.admin.trove.topology_database_ips",
            side_effect=RuntimeError("Trove mgmt 미지원"),
        ),
        patch("app.api.identity.admin.cached_call", new=AsyncMock(side_effect=lambda key, ttl, fn, **kw: fn())),
    ):
        resp = await admin_client.get("/api/v1/admin/topology")

    assert resp.status_code == 200
    assert resp.json()["instances"][0]["is_database"] is False
