"""토폴로지 트래픽 엔드포인트 테스트."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PROJECT_ID = "test-project-123"


# ── 픽스처 ───────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _bypass_port_cache():
    """테스트 간 Redis 캐시 오염 방지: cached_call 을 항상 함수를 직접 호출하도록 패치."""

    async def _passthrough(_key, _ttl, fn):
        return fn()

    with patch("app.api.network.networks.cached_call", side_effect=_passthrough):
        yield


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _mock_port(
    device_id: str,
    network_id: str,
    device_owner: str = "compute:nova",
    port_id: str | None = None,
    mac_address: str | None = None,
):
    p = MagicMock()
    p.id = port_id or f"port-{device_id}"
    p.device_id = device_id
    p.device_owner = device_owner
    p.network_id = network_id
    p.mac_address = mac_address or "fa:16:3e:00:00:01"
    p.fixed_ips = [{"ip_address": "10.0.0.1", "subnet_id": "sub-1"}]
    return p


def _prom_instant_response(label_val_pairs: list[tuple[dict, float]]):
    """query_instant_multi 가 반환할 (labels, value) 리스트 생성."""
    return [(labels, val) for labels, val in label_val_pairs]


# ── 테스트: VM 트래픽 PromQL 매핑 ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_traffic_returns_instances_from_promql(client, mock_conn):
    """node_exporter 결과에서 VM rx/tx bps 가 응답에 포함되고 byte→bit 변환(×8)이 적용돼야 한다."""
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    rx_pairs = _prom_instant_response(
        [
            ({"instance_id": "uuid-1", "device": "ens3"}, 125_000.0),  # 125kB/s → 1Mbps
        ]
    )
    tx_pairs = _prom_instant_response(
        [
            ({"instance_id": "uuid-1", "device": "ens3"}, 62_500.0),  # 62.5kB/s → 500kbps
        ]
    )

    with (
        patch("app.api.network.networks.query_instant_multi", new=AsyncMock(side_effect=[rx_pairs, tx_pairs, [], []])),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic")

    assert resp.status_code == 200
    body = resp.json()
    assert "uuid-1" in body["instances"]
    inst = body["instances"]["uuid-1"]
    assert abs(inst["rx_bps"] - 1_000_000.0) < 1
    assert abs(inst["tx_bps"] - 500_000.0) < 1


@pytest.mark.anyio
async def test_traffic_aggregates_by_network(client, mock_conn):
    """같은 네트워크에 속한 VM 들의 bps 가 network 합산에 반영돼야 한다."""
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01"),
        _mock_port("uuid-2", "net-a", port_id="port-2", mac_address="fa:16:3e:00:00:02"),
    ]

    rx_pairs = _prom_instant_response(
        [
            ({"instance_id": "uuid-1", "device": "ens3"}, 100.0),
            ({"instance_id": "uuid-2", "device": "ens3"}, 200.0),
        ]
    )
    tx_pairs: list = []

    with (
        patch("app.api.network.networks.query_instant_multi", new=AsyncMock(side_effect=[rx_pairs, tx_pairs, [], []])),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic")

    assert resp.status_code == 200
    body = resp.json()
    net = body["networks"]["net-a"]
    assert abs(net["rx_bps"] - (100.0 + 200.0) * 8) < 1


@pytest.mark.anyio
async def test_traffic_routers_empty_with_meta(client, mock_conn):
    """routers 는 빈 dict, _meta.router_traffic 이 'exporter_required' 여야 한다."""
    mock_conn.network.ports.return_value = []

    with (
        patch("app.api.network.networks.query_instant_multi", new=AsyncMock(return_value=[])),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic")

    assert resp.status_code == 200
    body = resp.json()
    assert body["routers"] == {}
    assert body["_meta"]["router_traffic"] == "exporter_required"


@pytest.mark.anyio
async def test_traffic_handles_no_instances(client, mock_conn):
    """인스턴스 0개여도 200 OK 반환해야 한다."""
    mock_conn.network.ports.return_value = []

    with patch("app.api.network.networks.list_load_balancers", return_value=[]):
        resp = await client.get("/api/v1/networks/topology/traffic")

    assert resp.status_code == 200
    body = resp.json()
    assert body["instances"] == {}
    assert body["networks"] == {}


@pytest.mark.anyio
async def test_traffic_prom_unavailable_falls_back(client, mock_conn):
    """PromUnavailable 발생 시 instances={} 로 fallback — 전체 500 금지."""
    from app.services.prom_query import PromUnavailable

    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    with (
        patch(
            "app.api.network.networks.query_instant_multi",
            new=AsyncMock(side_effect=PromUnavailable("timeout")),
        ),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic")

    assert resp.status_code == 200
    assert resp.json()["instances"] == {}


# ── 테스트: LB 차분 계산 ──────────────────────────────────────────────────────


def test_traffic_lb_first_call_zero():
    """최초 스냅샷 없을 때 lb_rate_from_snapshot 은 rx_bps=tx_bps=0 을 반환해야 한다."""
    from app.services import octavia

    octavia._lb_snapshot.clear()

    result = octavia.lb_rate_from_snapshot("lb-new", {"bytes_in": 1000, "bytes_out": 2000, "active_connections": 1})
    assert result["rx_bps"] == 0.0
    assert result["tx_bps"] == 0.0


def test_traffic_lb_rate_from_snapshot():
    """두 번째 호출에서 누적 차분으로 rate 를 계산해야 한다."""
    from app.services import octavia

    lb_id = "lb-rate-test"
    octavia._lb_snapshot.pop(lb_id, None)

    t0 = time.time() - 10  # 10초 전에 스냅샷이 있었다고 가정
    with octavia._snapshot_lock:
        octavia._lb_snapshot[lb_id] = (0, 0, t0)

    result = octavia.lb_rate_from_snapshot(
        lb_id, {"bytes_in": 1_250_000, "bytes_out": 2_500_000, "active_connections": 5}
    )
    # bytes_out 증분 2_500_000 bytes / 10s * 8 = 2_000_000 bps = 2 Mbps (rx)
    assert result["rx_bps"] > 0
    assert result["tx_bps"] > 0
    # bytes_in 증분 / 10s * 8: 1_250_000 / 10 * 8 = 1_000_000 bps
    assert abs(result["tx_bps"] - 1_000_000) < 50_000  # ±5% 허용 (타이밍)


# ── 테스트: query_instant_multi ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_query_instant_multi_parses_results():
    """query_instant_multi 가 Prometheus JSON 에서 (labels, value) 리스트를 파싱해야 한다."""
    from unittest.mock import patch

    from app.services.prom_query import query_instant_multi

    fake_body = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": {"instance_id": "uuid-1"}, "value": [1700000000, "42.5"]},
                {"metric": {"instance_id": "uuid-2"}, "value": [1700000000, "10.0"]},
            ],
        },
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_body
    mock_resp.raise_for_status = MagicMock()

    async def _mock_get(*args, **kwargs):
        return mock_resp

    with patch("app.services.prom_query._get_client") as mock_client:
        mock_client.return_value.get = _mock_get
        result = await query_instant_multi('node_cpu_seconds_total{instance_id="uuid-1"}')

    assert len(result) == 2
    labels0, val0 = result[0]
    assert labels0["instance_id"] == "uuid-1"
    assert val0 == 42.5
    labels1, val1 = result[1]
    assert labels1["instance_id"] == "uuid-2"
    assert val1 == 10.0


# ── 테스트: libvirt-exporter MAC 기반 demux ───────────────────────────────────


@pytest.mark.anyio
async def test_traffic_libvirt_fills_missing_instances(client, mock_conn):
    """node_exporter 에 없는 인스턴스를 libvirt MAC 기반 경로로 채워야 한다."""
    MAC1 = "fa:16:3e:00:00:01"
    MAC2 = "fa:16:3e:00:00:02"
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address=MAC1),
        _mock_port("uuid-2", "net-a", port_id="port-2", mac_address=MAC2),
    ]

    # uuid-1 은 node_exporter 에만, uuid-2 는 libvirt 에만 있음
    ne_rx = _prom_instant_response([({"instance_id": "uuid-1", "device": "ens3"}, 100.0)])
    ne_tx: list = []
    lv_rx = _prom_instant_response([({"instance_id": "uuid-2", "mac_address": MAC2}, 200.0)])
    lv_tx = _prom_instant_response([({"instance_id": "uuid-2", "mac_address": MAC2}, 50.0)])

    with (
        patch("app.api.network.networks.query_instant_multi", new=AsyncMock(side_effect=[ne_rx, ne_tx, lv_rx, lv_tx])),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic")

    assert resp.status_code == 200
    body = resp.json()
    assert "uuid-1" in body["instances"]
    assert abs(body["instances"]["uuid-1"]["rx_bps"] - 100.0 * 8) < 1
    assert "uuid-2" in body["instances"]
    assert abs(body["instances"]["uuid-2"]["rx_bps"] - 200.0 * 8) < 1
    assert abs(body["instances"]["uuid-2"]["tx_bps"] - 50.0 * 8) < 1


@pytest.mark.anyio
async def test_traffic_libvirt_primary_node_exporter_supplements(client, mock_conn):
    """libvirt 가 주 경로(NIC demux). libvirt 미관측 인스턴스는 node_exporter 로 보강."""
    MAC1 = "fa:16:3e:00:00:01"
    MAC2 = "fa:16:3e:00:00:02"
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address=MAC1),
        _mock_port("uuid-2", "net-a", port_id="port-2", mac_address=MAC2),
    ]

    # uuid-1 은 libvirt + node_exporter 양쪽, uuid-2 는 node_exporter 만
    ne_rx = _prom_instant_response(
        [
            ({"instance_id": "uuid-1", "device": "ens3"}, 100.0),  # libvirt 값(200)에 밀려야 함
            ({"instance_id": "uuid-2", "device": "ens3"}, 50.0),  # libvirt 없으므로 보강
        ]
    )
    ne_tx = _prom_instant_response(
        [
            ({"instance_id": "uuid-2", "device": "ens3"}, 10.0),
        ]
    )
    lv_rx = _prom_instant_response([({"instance_id": "uuid-1", "mac_address": MAC1}, 200.0)])
    lv_tx = _prom_instant_response([({"instance_id": "uuid-1", "mac_address": MAC1}, 80.0)])

    with (
        patch("app.api.network.networks.query_instant_multi", new=AsyncMock(side_effect=[ne_rx, ne_tx, lv_rx, lv_tx])),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic")

    assert resp.status_code == 200
    body = resp.json()
    # uuid-1 은 libvirt 값 사용 (200 * 8)
    assert abs(body["instances"]["uuid-1"]["rx_bps"] - 200.0 * 8) < 1
    assert abs(body["instances"]["uuid-1"]["tx_bps"] - 80.0 * 8) < 1
    # uuid-2 는 node_exporter 보강 (50 * 8)
    assert abs(body["instances"]["uuid-2"]["rx_bps"] - 50.0 * 8) < 1
    assert abs(body["instances"]["uuid-2"]["tx_bps"] - 10.0 * 8) < 1


@pytest.mark.anyio
async def test_traffic_libvirt_query_uses_openstack_info_join(client, mock_conn):
    """libvirt PromQL 2개가 openstack_info 조인과 double group_left 패턴을 사용하는지 검증."""
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    calls: list[str] = []

    async def _capture_query(promql: str):
        calls.append(promql)
        return []

    with (
        patch("app.api.network.networks.query_instant_multi", side_effect=_capture_query),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic")

    assert resp.status_code == 200
    assert len(calls) == 4
    lv_calls = [q for q in calls if "libvirt_domain_interface_stats_" in q]
    assert len(lv_calls) == 2
    for q in lv_calls:
        # 1단계 join: target_device 기준 mac_address 붙이기
        assert "* on (instance, domain, target_device) group_left(mac_address)" in q
        assert "libvirt_domain_interface_stats_info" in q
        # 2단계 join: domain 기준 instance_id 붙이기
        assert "* on (instance, domain) group_left(instance_id)" in q
        assert "libvirt_domain_openstack_info" in q


# ── 테스트: 멀티-NIC demux ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_traffic_multi_nic_demux(client, mock_conn):
    """멀티-NIC 인스턴스의 NIC 가 다른 네트워크에 각각 demux 돼야 한다."""
    MAC_A = "fa:16:3e:00:01:01"
    MAC_B = "fa:16:3e:00:01:02"
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-a1", mac_address=MAC_A),
        _mock_port("uuid-1", "net-b", port_id="port-b1", mac_address=MAC_B),
    ]

    lv_rx = _prom_instant_response(
        [
            ({"instance_id": "uuid-1", "mac_address": MAC_A}, 100.0),
            ({"instance_id": "uuid-1", "mac_address": MAC_B}, 200.0),
        ]
    )
    lv_tx = _prom_instant_response(
        [
            ({"instance_id": "uuid-1", "mac_address": MAC_A}, 10.0),
            ({"instance_id": "uuid-1", "mac_address": MAC_B}, 20.0),
        ]
    )

    with (
        patch("app.api.network.networks.query_instant_multi", new=AsyncMock(side_effect=[[], [], lv_rx, lv_tx])),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic")

    assert resp.status_code == 200
    body = resp.json()

    # interfaces 에 NIC 별로 2개 entry
    assert "port-a1" in body["interfaces"]
    assert "port-b1" in body["interfaces"]
    assert body["interfaces"]["port-a1"]["network_id"] == "net-a"
    assert body["interfaces"]["port-b1"]["network_id"] == "net-b"
    assert abs(body["interfaces"]["port-a1"]["rx_bps"] - 100.0 * 8) < 1
    assert abs(body["interfaces"]["port-b1"]["rx_bps"] - 200.0 * 8) < 1

    # instances 합산 = 두 NIC 합
    assert abs(body["instances"]["uuid-1"]["rx_bps"] - (100.0 + 200.0) * 8) < 1

    # networks 가 NIC 단위로 분리
    assert abs(body["networks"]["net-a"]["rx_bps"] - 100.0 * 8) < 1
    assert abs(body["networks"]["net-b"]["rx_bps"] - 200.0 * 8) < 1


@pytest.mark.anyio
async def test_traffic_node_exporter_supplements_single_nic_to_networks(client, mock_conn):
    """single-NIC 인스턴스가 libvirt 에 없고 node_exporter 에만 있으면 networks 에도 합산돼야 한다."""
    MAC1 = "fa:16:3e:00:00:01"
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address=MAC1),
    ]

    ne_rx = _prom_instant_response([({"instance_id": "uuid-1", "device": "ens3"}, 100.0)])
    ne_tx: list = []

    with (
        patch("app.api.network.networks.query_instant_multi", new=AsyncMock(side_effect=[ne_rx, ne_tx, [], []])),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic")

    assert resp.status_code == 200
    body = resp.json()
    assert "uuid-1" in body["instances"]
    assert abs(body["instances"]["uuid-1"]["rx_bps"] - 100.0 * 8) < 1
    # single-NIC 이므로 networks 에도 합산
    assert "net-a" in body["networks"]
    assert abs(body["networks"]["net-a"]["rx_bps"] - 100.0 * 8) < 1


@pytest.mark.anyio
async def test_traffic_node_exporter_multi_nic_skips_networks_aggregation(client, mock_conn):
    """multi-NIC 인스턴스가 libvirt 에 미관측이면 instances 는 채우되 networks 합산은 스킵해야 한다."""
    MAC_A = "fa:16:3e:00:01:01"
    MAC_B = "fa:16:3e:00:01:02"
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-a1", mac_address=MAC_A),
        _mock_port("uuid-1", "net-b", port_id="port-b1", mac_address=MAC_B),
    ]

    ne_rx = _prom_instant_response([({"instance_id": "uuid-1", "device": "ens3"}, 300.0)])
    ne_tx: list = []

    with (
        patch("app.api.network.networks.query_instant_multi", new=AsyncMock(side_effect=[ne_rx, ne_tx, [], []])),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic")

    assert resp.status_code == 200
    body = resp.json()
    # instances 는 채워져야 함
    assert "uuid-1" in body["instances"]
    assert abs(body["instances"]["uuid-1"]["rx_bps"] - 300.0 * 8) < 1
    # multi-NIC 이므로 귀속 불명 → networks 에 합산 없음
    assert "net-a" not in body["networks"]
    assert "net-b" not in body["networks"]


@pytest.mark.anyio
async def test_traffic_new_attach_within_libvirt_scrape_window(client, mock_conn):
    """attach 직후 libvirt 미스크레이프 윈도: port_map 에는 등장하되 libvirt 결과 비었을 때 200 OK."""
    MAC1 = "fa:16:3e:00:00:01"
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address=MAC1),
    ]

    # libvirt 가 아직 스크레이프 못 한 상태 (lv_rx, lv_tx 모두 빈 리스트)
    with (
        patch("app.api.network.networks.query_instant_multi", new=AsyncMock(side_effect=[[], [], [], []])),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic")

    assert resp.status_code == 200
    body = resp.json()
    # 에러가 아닌 빈 dict 또는 rx/tx=0 으로 처리됨
    assert isinstance(body["instances"], dict)
    if "uuid-1" in body["instances"]:
        assert body["instances"]["uuid-1"]["rx_bps"] == 0.0
    assert "port-1" not in body["interfaces"]


@pytest.mark.anyio
async def test_traffic_libvirt_promql_uses_double_group_left(client, mock_conn):
    """libvirt PromQL 에 mac_address 조인과 instance_id 조인이 모두 포함돼야 한다."""
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    calls: list[str] = []

    async def _capture_query(promql: str):
        calls.append(promql)
        return []

    with (
        patch("app.api.network.networks.query_instant_multi", side_effect=_capture_query),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        await client.get("/api/v1/networks/topology/traffic")

    lv_calls = [
        q
        for q in calls
        if "libvirt_domain_interface_stats_receive_bytes_total" in q
        or "libvirt_domain_interface_stats_transmit_bytes_total" in q
    ]
    assert len(lv_calls) == 2
    for q in lv_calls:
        assert "* on (instance, domain, target_device) group_left(mac_address)" in q
        assert "* on (instance, domain) group_left(instance_id)" in q


# ── 테스트: all_projects 파라미터 ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_traffic_all_projects_requires_admin(non_admin_client, mock_conn):
    """all_projects=true + is_system_admin=False → 403."""
    resp = await non_admin_client.get("/api/v1/networks/topology/traffic?all_projects=true")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_traffic_all_projects_admin_unscoped_ports(admin_client, mock_conn):
    """admin + all_projects=true → conn.network.ports 가 project_id 인자 없이 호출."""
    mock_conn.network.ports.return_value = []

    with (
        patch("app.api.network.networks.query_instant_multi", new=AsyncMock(return_value=[])),
        patch("app.api.network.networks.list_load_balancers", return_value=[]) as mock_lbs,
    ):
        resp = await admin_client.get("/api/v1/networks/topology/traffic?all_projects=true")
    assert resp.status_code == 200
    assert mock_conn.network.ports.called
    _, kwargs = mock_conn.network.ports.call_args
    assert "project_id" not in kwargs
    mock_lbs.assert_called_once()
    lb_positional = mock_lbs.call_args.args
    assert lb_positional[1] is None  # scope_project_id=None


@pytest.mark.anyio
async def test_traffic_default_scoped_to_project(client, mock_conn):
    """all_projects 미지정(False) → ports(project_id=...) 로 스코프."""
    mock_conn.network.ports.return_value = []

    with (
        patch("app.api.network.networks.query_instant_multi", new=AsyncMock(return_value=[])),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic")
    assert resp.status_code == 200
    assert mock_conn.network.ports.called
    _, kwargs = mock_conn.network.ports.call_args
    assert kwargs.get("project_id") == _PROJECT_ID


# ── 테스트: rate 윈도우와 scrape interval 결합 ────────────────────────────────


@pytest.mark.anyio
async def test_traffic_rate_window_is_30s(client, mock_conn):
    """토폴로지 트래픽 PromQL 4개 모두 30초 rate 윈도우를 써야 한다.

    캔버스가 사용량을 30초 단위로 읽는 근거다. 2m 로 되돌리면 화면 값이 2분 평균이 되어
    순간 사용량이 뭉개진다.
    """
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    calls: list[str] = []

    async def _capture_query(promql: str):
        calls.append(promql)
        return []

    with (
        patch("app.api.network.networks.query_instant_multi", side_effect=_capture_query),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic")

    assert resp.status_code == 200
    assert len(calls) == 4
    for q in calls:
        assert "[30s]" in q, f"30초 윈도우가 아니다: {q}"
        assert "[2m]" not in q


def test_topology_scrape_interval_supports_rate_window():
    """토폴로지가 쓰는 두 job 의 scrape_interval 이 rate 윈도우를 지탱해야 한다.

    Prometheus rate 는 윈도우 안에 최소 2 샘플이 필요하고 jitter 를 감당하려면 3 샘플이 안전하다.
    scrape 를 다시 올리면(예: 30s) `rate(...[30s])` 는 빈 결과를 돌려주고 화면 트래픽이 사라진다 —
    코드만 보면 알 수 없는 결합이므로 배포 설정을 함께 고정한다.
    """
    import re
    from pathlib import Path

    from app.api.network.networks import TOPOLOGY_RATE_WINDOW

    m = re.fullmatch(r"(\d+)s", TOPOLOGY_RATE_WINDOW)
    assert m, f"윈도우 형식이 초 단위가 아니다: {TOPOLOGY_RATE_WINDOW}"
    window_s = int(m.group(1))

    root = Path(__file__).resolve().parents[2]
    # **배포본과 template 을 모두 본다.** 한쪽만 검사하면 template 으로 세운 새 클러스터에
    # libvirt exporter 가 없어도(= 주 경로 상실) 테스트가 초록으로 남는다 — 실제로 그랬다.
    configs = [
        root / "deploy" / "k8s" / "monitoring" / "prometheus" / "configmap.yaml",
        root / "deploy" / "k8s-template" / "monitoring" / "prometheus" / "configmap.yaml",
    ]
    for cfg in configs:
        text = cfg.read_text(encoding="utf-8")

        global_m = re.search(r"^\s*global:\s*\n\s*scrape_interval:\s*(\d+)s", text, re.MULTILINE)
        assert global_m, f"{cfg.name}: global scrape_interval 을 찾지 못했다"
        global_s = int(global_m.group(1))

        # 토폴로지 트래픽이 읽는 두 exporter job
        for job in ("instances-node", "instances-libvirt"):
            job_m = re.search(rf"- job_name: '{job}'\n(?:\s+scrape_interval:\s*(\d+)s\n)?", text)
            assert job_m, f"{cfg.parent.parents[1].name}: {job} job 을 찾지 못했다"
            scrape_s = int(job_m.group(1)) if job_m.group(1) else global_s
            assert scrape_s * 3 <= window_s, (
                f"{cfg.parent.parents[1].name}: {job} scrape_interval={scrape_s}s 는 "
                f"rate 윈도우 {window_s}s 에 3 샘플을 채우지 못한다"
            )


# ── 테스트: 사용량 히스토리 (`/topology/traffic/history`) ─────────────────────


def _prom_range_response(label_series_pairs: list[tuple[dict, list[tuple[int, float]]]]):
    """query_range_multi 가 반환할 (labels, [(ts, value)]) 리스트 생성."""
    return [(labels, samples) for labels, samples in label_series_pairs]


@pytest.mark.anyio
async def test_history_folds_libvirt_series_for_requested_network(client, mock_conn):
    """libvirt 시계열이 mac→네트워크 귀속을 거쳐 ts 별로 합산되고 ×8 이 적용돼야 한다."""
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01"),
        _mock_port("uuid-2", "net-a", port_id="port-2", mac_address="fa:16:3e:00:00:02"),
    ]

    lv_rx = _prom_range_response(
        [
            ({"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:01"}, [(100, 100.0), (115, 200.0)]),
            ({"instance_id": "uuid-2", "mac_address": "fa:16:3e:00:00:02"}, [(100, 50.0), (115, 50.0)]),
        ]
    )

    with patch(
        "app.api.network.networks.query_range_multi",
        new=AsyncMock(side_effect=[[], [], lv_rx, []]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic/history?network_id=net-a")

    assert resp.status_code == 200
    body = resp.json()
    assert [p["ts"] for p in body["series"]] == [100, 115]
    assert abs(body["series"][0]["rx_bps"] - (100.0 + 50.0) * 8) < 1
    assert abs(body["series"][1]["rx_bps"] - (200.0 + 50.0) * 8) < 1
    assert body["series"][0]["tx_bps"] == 0.0


@pytest.mark.anyio
async def test_history_excludes_other_networks(client, mock_conn):
    """다른 네트워크에 붙은 NIC 의 트래픽은 이 네트워크 히스토리에 들어가면 안 된다."""
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01"),
        _mock_port("uuid-1", "net-b", port_id="port-2", mac_address="fa:16:3e:00:00:02"),
    ]

    lv_rx = _prom_range_response(
        [
            ({"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:01"}, [(100, 10.0)]),
            ({"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:02"}, [(100, 999.0)]),
        ]
    )

    with patch(
        "app.api.network.networks.query_range_multi",
        new=AsyncMock(side_effect=[[], [], lv_rx, []]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic/history?network_id=net-a")

    assert resp.status_code == 200
    series = resp.json()["series"]
    assert len(series) == 1
    assert abs(series[0]["rx_bps"] - 10.0 * 8) < 1, "net-b NIC 트래픽이 섞였다"


@pytest.mark.anyio
async def test_history_stats_come_from_returned_series(client, mock_conn):
    """avg/max/latest 는 반환한 series 로 계산돼야 한다.

    `avg_over_time` 같은 별도 쿼리로 채우면 그래프 최고점과 라벨 숫자가 어긋난다.
    """
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    lv_rx = _prom_range_response(
        [({"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:01"}, [(100, 100.0), (115, 300.0)])]
    )
    lv_tx = _prom_range_response(
        [({"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:01"}, [(100, 0.0), (115, 100.0)])]
    )

    with patch(
        "app.api.network.networks.query_range_multi",
        new=AsyncMock(side_effect=[[], [], lv_rx, lv_tx]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic/history?network_id=net-a")

    assert resp.status_code == 200
    body = resp.json()
    rxs = [p["rx_bps"] for p in body["series"]]
    txs = [p["tx_bps"] for p in body["series"]]
    assert rxs == [800.0, 2400.0]
    assert txs == [0.0, 800.0]
    stats = body["stats"]
    assert abs(stats["avg"]["rx_bps"] - sum(rxs) / len(rxs)) < 1e-6
    assert abs(stats["avg"]["tx_bps"] - sum(txs) / len(txs)) < 1e-6
    assert abs(stats["max"]["rx_bps"] - max(rxs)) < 1e-6
    assert abs(stats["max"]["tx_bps"] - max(txs)) < 1e-6
    assert stats["latest"] == {"rx_bps": rxs[-1], "tx_bps": txs[-1]}


@pytest.mark.anyio
async def test_history_stats_are_direction_split_not_summed(client, mock_conn):
    """stats 는 rx+tx 합계가 아니라 방향별이어야 한다.

    instant 엔드포인트가 방향별(`▼ rx ▲ tx`)을 주므로 합계로 내보내면 같은 패널에서
    `▼ 5.8M ▲ 2.0M` 옆에 `7.8M` 이 붙어 사용자가 두 행을 대조할 수 없다.
    """
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    lv_rx = _prom_range_response([({"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:01"}, [(100, 1000.0)])])
    lv_tx = _prom_range_response([({"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:01"}, [(100, 250.0)])])

    with patch(
        "app.api.network.networks.query_range_multi",
        new=AsyncMock(side_effect=[[], [], lv_rx, lv_tx]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic/history?network_id=net-a")

    stats = resp.json()["stats"]
    for key in ("avg", "max", "latest"):
        assert set(stats[key]) == {"rx_bps", "tx_bps"}, f"{key} 가 방향별이 아니다: {stats[key]}"
        assert abs(stats[key]["rx_bps"] - 8000.0) < 1e-6
        assert abs(stats[key]["tx_bps"] - 2000.0) < 1e-6
        # 합계(10000)를 어느 필드에도 담지 않는다
        assert 10000.0 not in stats[key].values()


@pytest.mark.anyio
async def test_history_max_per_direction_can_be_at_different_timestamps(client, mock_conn):
    """rx 최대와 tx 최대가 서로 다른 시점이어도 각각 그 방향의 최고값이어야 한다."""
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    lv_rx = _prom_range_response(
        [({"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:01"}, [(100, 500.0), (115, 100.0)])]
    )
    lv_tx = _prom_range_response(
        [({"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:01"}, [(100, 10.0), (115, 300.0)])]
    )

    with patch(
        "app.api.network.networks.query_range_multi",
        new=AsyncMock(side_effect=[[], [], lv_rx, lv_tx]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic/history?network_id=net-a")

    stats = resp.json()["stats"]
    assert abs(stats["max"]["rx_bps"] - 4000.0) < 1e-6  # ts=100
    assert abs(stats["max"]["tx_bps"] - 2400.0) < 1e-6  # ts=115


@pytest.mark.anyio
async def test_history_fills_zero_for_direction_missing_at_a_timestamp(client, mock_conn):
    """rx 에만 있는 ts 는 tx=0 으로 채워 표본 수가 방향별로 달라지지 않게 한다."""
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    lv_rx = _prom_range_response(
        [({"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:01"}, [(100, 10.0), (115, 20.0)])]
    )
    # tx 는 두 번째 표본만 존재
    lv_tx = _prom_range_response([({"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:01"}, [(115, 5.0)])])

    with patch(
        "app.api.network.networks.query_range_multi",
        new=AsyncMock(side_effect=[[], [], lv_rx, lv_tx]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic/history?network_id=net-a")

    series = resp.json()["series"]
    assert [p["ts"] for p in series] == [100, 115]
    assert series[0]["tx_bps"] == 0.0
    assert abs(series[1]["tx_bps"] - 40.0) < 1e-6


@pytest.mark.anyio
async def test_history_node_fallback_only_for_single_nic(client, mock_conn):
    """node_exporter 폴백은 libvirt 미관측 + 단일 NIC 인스턴스만 귀속한다."""
    mock_conn.network.ports.return_value = [
        # 단일 NIC — 폴백 대상
        _mock_port("uuid-solo", "net-a", port_id="port-solo", mac_address="fa:16:3e:00:00:aa"),
        # 다중 NIC — device 이름으로 네트워크를 가릴 수 없어 제외돼야 한다
        _mock_port("uuid-multi", "net-a", port_id="port-m1", mac_address="fa:16:3e:00:00:bb"),
        _mock_port("uuid-multi", "net-b", port_id="port-m2", mac_address="fa:16:3e:00:00:cc"),
    ]

    ne_rx = _prom_range_response(
        [
            ({"instance_id": "uuid-solo", "device": "ens3"}, [(100, 10.0)]),
            ({"instance_id": "uuid-multi", "device": "ens3"}, [(100, 999.0)]),
        ]
    )

    with patch(
        "app.api.network.networks.query_range_multi",
        new=AsyncMock(side_effect=[ne_rx, [], [], []]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic/history?network_id=net-a")

    assert resp.status_code == 200
    series = resp.json()["series"]
    assert len(series) == 1
    assert abs(series[0]["rx_bps"] - 10.0 * 8) < 1, "다중 NIC 인스턴스가 귀속됐다"


@pytest.mark.anyio
async def test_history_node_fallback_skips_libvirt_observed(client, mock_conn):
    """libvirt 가 이미 본 인스턴스는 node 폴백에서 제외돼야 한다(이중 계산 금지)."""
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    ne_rx = _prom_range_response([({"instance_id": "uuid-1", "device": "ens3"}, [(100, 500.0)])])
    lv_rx = _prom_range_response([({"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:01"}, [(100, 10.0)])])

    with patch(
        "app.api.network.networks.query_range_multi",
        new=AsyncMock(side_effect=[ne_rx, [], lv_rx, []]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic/history?network_id=net-a")

    assert resp.status_code == 200
    series = resp.json()["series"]
    assert abs(series[0]["rx_bps"] - 10.0 * 8) < 1, "libvirt 값에 node 값이 더해졌다"


@pytest.mark.anyio
async def test_history_prom_failure_returns_empty_series(client, mock_conn):
    """Prometheus 장애 시 500 이 아니라 빈 series + stats None 을 돌려준다."""
    from app.services.prom_query import PromUnavailable

    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    with patch(
        "app.api.network.networks.query_range_multi",
        new=AsyncMock(side_effect=PromUnavailable("연결 실패")),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic/history?network_id=net-a")

    assert resp.status_code == 200
    body = resp.json()
    assert body["series"] == []
    assert body["stats"] == {"avg": None, "max": None, "latest": None}


@pytest.mark.anyio
async def test_history_all_projects_requires_system_admin(client, mock_conn):
    """all_projects=true 는 시스템 admin 이 아니면 403 이어야 한다."""
    mock_conn.network.ports.return_value = []

    with patch("app.api.network.networks.query_range_multi", new=AsyncMock(return_value=[])):
        resp = await client.get("/api/v1/networks/topology/traffic/history?network_id=net-a&all_projects=true")

    assert resp.status_code == 403


@pytest.mark.anyio
async def test_history_uses_rate_window_and_range_step(client, mock_conn):
    """히스토리 쿼리도 30초 rate 윈도우를 쓰고, step 은 range 별 고정값이어야 한다."""
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    calls: list[dict] = []

    async def _capture(promql: str, *, start_ts: int, end_ts: int, step_s: int):
        calls.append({"q": promql, "start_ts": start_ts, "end_ts": end_ts, "step_s": step_s})
        return []

    with patch("app.api.network.networks.query_range_multi", side_effect=_capture):
        resp = await client.get("/api/v1/networks/topology/traffic/history?network_id=net-a&range=30m")

    assert resp.status_code == 200
    assert len(calls) == 4
    for c in calls:
        assert "[30s]" in c["q"], f"30초 윈도우가 아니다: {c['q']}"
        assert c["step_s"] == 30
        assert c["end_ts"] - c["start_ts"] == 1800
    assert resp.json()["step_s"] == 30


def test_history_step_never_exceeds_rate_window():
    """모든 range 의 step 이 rate 윈도우 이하여야 한다.

    step > 윈도우면 샘플 사이 트래픽이 그래프에서 통째로 사라진다. `calc_step()`(range//100)
    을 쓰면 1h 에서 36s 가 나와 이 계약이 깨지므로 고정 표를 쓴다.
    """
    import re

    from app.api.network.networks import _HISTORY_RANGES, TOPOLOGY_RATE_WINDOW

    m = re.fullmatch(r"(\d+)s", TOPOLOGY_RATE_WINDOW)
    assert m
    window_s = int(m.group(1))

    assert _HISTORY_RANGES, "range 표가 비어 있다"
    for label, (range_s, step_s) in _HISTORY_RANGES.items():
        assert step_s <= window_s, f"{label}: step {step_s}s 가 rate 윈도우 {window_s}s 보다 크다"
        assert range_s % step_s == 0, f"{label}: range 가 step 의 배수가 아니다"


@pytest.mark.anyio
async def test_history_foreign_network_id_leaks_nothing(client, mock_conn):
    """다른 프로젝트의 network_id 를 넣어도 빈 series 여야 한다.

    포트맵이 호출자 프로젝트로 스코프되므로 mac_idx 에 남의 포트가 없다 —
    network_id 자체는 검증하지 않지만 귀속 대상이 없어 아무것도 새지 않는다.
    """
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    lv_rx = _prom_range_response([({"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:01"}, [(100, 999.0)])])

    with patch(
        "app.api.network.networks.query_range_multi",
        new=AsyncMock(side_effect=[[], [], lv_rx, []]),
    ):
        resp = await client.get("/api/v1/networks/topology/traffic/history?network_id=net-other-project")

    assert resp.status_code == 200
    body = resp.json()
    assert body["series"] == []
    assert body["stats"]["max"] is None


@pytest.mark.anyio
async def test_instant_and_history_agree_on_multi_device_node_fallback(client, mock_conn):
    """같은 입력에서 instant 와 history 의 네트워크 합산값이 같아야 한다.

    node 쿼리는 `sum by (instance_id, device)` 라 **device 마다 시계열이 하나씩** 온다.
    한쪽이 대입(마지막 device 만), 한쪽이 누산(전체 합)이면 같은 패널에서 몇 배 차이 나는
    두 숫자를 나란히 보여준다. 게스트 안 device 가 2개 이상인 VM 은 흔하다 —
    제외 정규식(`lo|veth|docker|cni|tap|qbr`)은 k3s `flannel.1`, Waygate `wg0`, `bond0` 를 못 막는다.
    """
    mock_conn.network.ports.return_value = [
        _mock_port("uuid-1", "net-a", port_id="port-1", mac_address="fa:16:3e:00:00:01")
    ]

    # libvirt 미관측 → node 폴백 경로. 한 인스턴스에 device 2개.
    devices = [
        ({"instance_id": "uuid-1", "device": "eth0"}, 1_000_000.0),
        ({"instance_id": "uuid-1", "device": "flannel.1"}, 400_000.0),
    ]
    expected_rx = (1_000_000.0 + 400_000.0) * 8

    with (
        patch(
            "app.api.network.networks.query_instant_multi",
            new=AsyncMock(side_effect=[_prom_instant_response(devices), [], [], []]),
        ),
        patch("app.api.network.networks.list_load_balancers", return_value=[]),
    ):
        instant = await client.get("/api/v1/networks/topology/traffic")

    with patch(
        "app.api.network.networks.query_range_multi",
        new=AsyncMock(
            side_effect=[
                _prom_range_response([(labels, [(100, val)]) for labels, val in devices]),
                [],
                [],
                [],
            ]
        ),
    ):
        history = await client.get("/api/v1/networks/topology/traffic/history?network_id=net-a")

    assert instant.status_code == 200 and history.status_code == 200
    instant_rx = instant.json()["networks"]["net-a"]["rx_bps"]
    history_rx = history.json()["series"][-1]["rx_bps"]

    assert abs(instant_rx - expected_rx) < 1, f"instant 가 device 를 다 세지 않았다: {instant_rx}"
    assert abs(history_rx - expected_rx) < 1, f"history 가 device 를 다 세지 않았다: {history_rx}"
    assert abs(instant_rx - history_rx) < 1, (
        f"같은 입력인데 instant={instant_rx} history={history_rx} — 패널에서 두 숫자가 어긋난다"
    )


@pytest.mark.anyio
async def test_history_drops_non_finite_samples(client, mock_conn):
    """Prometheus 가 "NaN"/"+Inf" 를 보내도 응답 JSON 이 무효해지지 않아야 한다.

    `float("NaN")` 은 예외를 던지지 않으므로 그대로 담으면 합계·최대가 NaN 이 되고
    응답에 `NaN` 리터럴이 들어가 클라이언트 파싱이 깨진다.
    """
    from app.services.prom_query import query_range_multi

    payload = {
        "status": "success",
        "data": {
            "result": [
                {
                    "metric": {"instance_id": "uuid-1", "mac_address": "fa:16:3e:00:00:01"},
                    "values": [[100, "10"], [115, "NaN"], [130, "+Inf"], [145, "20"]],
                }
            ]
        },
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload

    with patch("app.services.prom_query._get_client") as mock_client:
        mock_client.return_value.get = AsyncMock(return_value=mock_resp)
        result = await query_range_multi("expr", start_ts=0, end_ts=200, step_s=15)

    assert len(result) == 1
    samples = result[0][1]
    assert [ts for ts, _ in samples] == [100, 145], "NaN/Inf 표본이 남았다"
    assert all(v == v and abs(v) != float("inf") for _, v in samples)
