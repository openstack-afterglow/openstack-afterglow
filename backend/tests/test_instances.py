"""인스턴스 API 단위 테스트."""

from unittest.mock import patch

import pytest

from app.models.compute import InstanceInfo


@pytest.fixture(autouse=True)
def _resolve_default_placement_policies(monkeypatch):
    """Keep security-group tests independent of persistence-backed placement selection."""

    async def resolve_zones(_conn, _requested_zone):
        return "", ""

    monkeypatch.setattr(
        "app.api.compute.instances.instance_orch.resolve_availability_zones",
        resolve_zones,
    )


def make_instance(instance_id: str = "inst-1", name: str = "test-vm", status: str = "ACTIVE") -> InstanceInfo:
    return InstanceInfo(
        id=instance_id,
        name=name,
        status=status,
        image_id="img-1",
        image_name="ubuntu-22.04",
        flavor_id="flavor-1",
        flavor_name="m1.small",
        ip_addresses=[],
        created_at="2024-01-01T00:00:00Z",
        metadata={},
        union_libraries=[],
        union_strategy=None,
        union_share_ids=[],
        union_upper_volume_id=None,
        key_name=None,
        user_id="test-user-123",
    )


# ────── GET 목록 & 상세 ──────


@pytest.mark.asyncio
async def test_list_instances(client, mock_conn):
    with (
        patch("app.api.compute.instances.nova.list_servers", return_value=[make_instance()]),
        patch("app.api.compute.instances.nova.list_flavors", return_value=[]),
        patch("app.api.compute.instances.glance.list_images", return_value=[]),
        patch("app.api.compute.instances.nova.list_volume_attachments", return_value=[]),
        patch("app.api.compute.instances.cinder.get_volume_image_metadata", return_value={}),
    ):
        resp = await client.get("/api/v1/instances")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_instance(client, mock_conn):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=make_instance()),
        patch("app.api.compute.instances.nova.list_flavors", return_value=[]),
        patch("app.api.compute.instances.glance.list_images", return_value=[]),
    ):
        resp = await client.get("/api/v1/instances/inst-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "inst-1"


@pytest.mark.asyncio
async def test_get_instance_other_project_returns_404(client, mock_conn):
    """다른 프로젝트의 인스턴스를 ID 로 직접 조회 시 owner 검증으로 404."""
    from unittest.mock import MagicMock

    foreign = MagicMock()
    foreign.id = "inst-foreign"
    foreign.project_id = "other-project-999"  # mock_conn 의 test-project-123 과 다름
    with patch("app.api.compute.instances.nova.get_server", return_value=foreign):
        resp = await client.get("/api/v1/instances/inst-foreign")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_get_other_project_instance(admin_client, mock_conn):
    """admin 은 다른 프로젝트 인스턴스도 직접 조회 가능."""
    from unittest.mock import MagicMock

    foreign = MagicMock(spec=InstanceInfo)
    foreign.id = "inst-foreign"
    foreign.name = "vm-foreign"
    foreign.project_id = "other-project-999"
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=foreign),
        patch(
            "app.api.compute.instances._resolve_names",
            return_value=[make_instance(instance_id="inst-foreign", name="vm-foreign")],
        ),
    ):
        resp = await admin_client.get("/api/v1/instances/inst-foreign")
    # admin 은 owner check 통과 — 200
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_instance_other_project_returns_404(client, mock_conn):
    """다른 프로젝트의 인스턴스 ID 로 DELETE 시 owner 검증으로 404."""
    from unittest.mock import MagicMock

    foreign = MagicMock()
    foreign.id = "inst-foreign"
    foreign.project_id = "other-project-999"
    foreign.union_upper_volume_id = None
    foreign.union_share_ids = []
    foreign.union_strategy = None
    foreign.metadata = {}
    with patch("app.api.compute.instances.nova.get_server", return_value=foreign):
        resp = await client.delete("/api/v1/instances/inst-foreign")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_start_instance_other_project_returns_404(client, mock_conn):
    """action 엔드포인트도 owner 검증으로 다른 프로젝트 차단."""
    from unittest.mock import MagicMock

    foreign = MagicMock()
    foreign.id = "inst-foreign"
    foreign.project_id = "other-project-999"
    with patch("app.api.compute.instances.nova.get_server", return_value=foreign):
        resp = await client.post("/api/v1/instances/inst-foreign/start")
    assert resp.status_code == 404


# ────── DELETE ──────


@pytest.mark.asyncio
async def test_delete_instance(client, mock_conn):
    inst = make_instance()
    inst.metadata = {}
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=inst),
        patch("app.api.compute.instances.nova.delete_server", return_value=None),
        patch("app.api.compute.instances.cinder.delete_volume", return_value=None),
    ):
        resp = await client.delete("/api/v1/instances/inst-1")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_instance_cleans_nfs_access_rules(client, mock_conn):
    """prebuilt strategy VM 삭제 시 해당 VM의 cephx access rule이 svc_conn으로 revoke된다.

    NFS CIDR rule은 프로젝트 수준 grant이므로 VM 삭제 시 회수하지 않는다 (lifecycle A).
    """
    from unittest.mock import MagicMock

    inst = make_instance()  # name="test-vm"
    inst.union_strategy = "prebuilt"
    inst.union_share_ids = ["share-1"]

    mock_svc_conn = MagicMock()
    access_rules = [
        {"id": "rule-ceph-1", "access_type": "cephx", "access_to": "union-ro-test-vm-python311"},
        {"id": "rule-ceph-2", "access_type": "cephx", "access_to": "union-ro-other-vm-python311"},  # 다른 VM
        {"id": "rule-ip-1", "access_type": "ip", "access_to": "10.0.0.0/24"},  # CIDR: 회수 안 함
    ]
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=inst),
        patch("app.api.compute.instances.nova.delete_server", return_value=None),
        patch("app.api.compute.instances.keystone.get_service_project_connection", return_value=mock_svc_conn),
        patch("app.api.compute.instances.manila.list_access_rules", return_value=access_rules) as mock_list,
        patch("app.api.compute.instances.manila.revoke_access_rule") as mock_revoke,
        patch("app.api.compute.instances.neutron.cleanup_instance_fips", return_value=None),
    ):
        resp = await client.delete("/api/v1/instances/inst-1")

    assert resp.status_code == 204
    mock_list.assert_called_once_with(mock_svc_conn, "share-1")
    # test-vm의 cephx rule만 revoke, 다른 VM과 CIDR rule은 회수 안 함
    mock_revoke.assert_called_once_with(mock_svc_conn, "share-1", "rule-ceph-1")


@pytest.mark.asyncio
async def test_delete_instance_nfs_cleanup_failure_continues(client, mock_conn):
    """prebuilt access rule 정리 실패해도 VM 삭제는 계속된다."""
    from unittest.mock import MagicMock

    inst = make_instance()
    inst.union_strategy = "prebuilt"
    inst.union_share_ids = ["share-1"]

    with (
        patch("app.api.compute.instances.nova.get_server", return_value=inst),
        patch("app.api.compute.instances.nova.delete_server", return_value=None),
        patch(
            "app.api.compute.instances.keystone.get_service_project_connection",
            return_value=MagicMock(),
        ),
        patch("app.api.compute.instances.manila.list_access_rules", side_effect=Exception("Manila 오류")),
        patch("app.api.compute.instances.neutron.cleanup_instance_fips", return_value=None),
    ):
        resp = await client.delete("/api/v1/instances/inst-1")

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_instance_dynamic_skips_nfs_rule_cleanup(client, mock_conn):
    """dynamic strategy 삭제 시 NFS access rule 조회를 건너뛴다."""
    inst = make_instance()
    inst.union_strategy = "dynamic"
    inst.union_share_ids = ["share-1"]

    with (
        patch("app.api.compute.instances.nova.get_server", return_value=inst),
        patch("app.api.compute.instances.nova.delete_server", return_value=None),
        patch("app.api.compute.instances.manila.delete_file_storage", return_value=None),
        patch("app.api.compute.instances.manila.list_access_rules") as mock_list,
        patch("app.api.compute.instances.neutron.cleanup_instance_fips", return_value=None),
    ):
        resp = await client.delete("/api/v1/instances/inst-1")

    assert resp.status_code == 204
    mock_list.assert_not_called()


# ────── 라이프사이클 액션 ──────


def _own_server():
    """owner check 통과용 — caller 와 동일한 project_id."""
    from unittest.mock import MagicMock

    s = MagicMock()
    s.id = "inst-1"
    s.project_id = "test-project-123"
    return s


@pytest.mark.asyncio
async def test_start_instance(client, mock_conn):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_own_server()),
        patch("app.api.compute.instances.nova.start_server", return_value=None),
    ):
        resp = await client.post("/api/v1/instances/inst-1/start")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_stop_instance(client, mock_conn):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_own_server()),
        patch("app.api.compute.instances.nova.stop_server", return_value=None),
    ):
        resp = await client.post("/api/v1/instances/inst-1/stop")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_reboot_instance(client, mock_conn):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_own_server()),
        patch("app.api.compute.instances.nova.reboot_server", return_value=None),
    ):
        resp = await client.post("/api/v1/instances/inst-1/reboot")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_shelve_instance(client, mock_conn):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_own_server()),
        patch("app.api.compute.instances.nova.shelve_server", return_value=None),
    ):
        resp = await client.post("/api/v1/instances/inst-1/shelve")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_unshelve_instance(client, mock_conn):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_own_server()),
        patch("app.api.compute.instances.nova.unshelve_server", return_value=None),
    ):
        resp = await client.post("/api/v1/instances/inst-1/unshelve")
    assert resp.status_code == 204


# ────── 콘솔/로그 ──────


@pytest.mark.asyncio
async def test_get_console(client, mock_conn):
    with patch("app.api.compute.instances.nova.get_console_url", return_value="https://console.example.com"):
        resp = await client.get("/api/v1/instances/inst-1/console")
    assert resp.status_code == 200
    assert "url" in resp.json()


@pytest.mark.asyncio
async def test_get_console_log(client, mock_conn):
    with patch("app.api.compute.instances.nova.get_console_output", return_value="log output"):
        resp = await client.get("/api/v1/instances/inst-1/log")
    assert resp.status_code == 200
    assert "output" in resp.json()


@pytest.mark.asyncio
async def test_get_console_log_full(client, mock_conn):
    """length=0은 전체 로그 요청 — 422가 아닌 200 반환되어야 한다."""
    with patch("app.api.compute.instances.nova.get_console_output", return_value="full log"):
        resp = await client.get("/api/v1/instances/inst-1/log?length=0")
    assert resp.status_code == 200
    assert resp.json()["output"] == "full log"


@pytest.mark.asyncio
async def test_get_console_log_length_negative(client, mock_conn):
    """음수 length는 거부되어야 한다."""
    resp = await client.get("/api/v1/instances/inst-1/log?length=-1")
    assert resp.status_code == 422


# ────── 볼륨 Attach/Detach ──────


@pytest.mark.asyncio
async def test_list_instance_volumes_includes_delete_on_termination(client, mock_conn):
    vol_attachment = {
        "id": "attach-1",
        "volume_id": "vol-1",
        "device": "/dev/vdb",
        "server_id": "inst-1",
        "delete_on_termination": True,
    }

    class FakeVol:
        name = "test-vol"
        size = 10
        status = "in-use"

    with (
        patch("app.api.compute.instances.nova.list_volume_attachments", return_value=[vol_attachment]),
        patch("app.api.compute.instances.cinder.get_volume", return_value=FakeVol()),
    ):
        resp = await client.get("/api/v1/instances/inst-1/volumes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["delete_on_termination"] is True


@pytest.mark.asyncio
async def test_attach_volume(client, mock_conn):
    with patch("app.api.compute.instances.nova.attach_volume", return_value={"id": "attach-1", "volumeId": "vol-1"}):
        resp = await client.post("/api/v1/instances/inst-1/volumes", json={"volume_id": "vol-1"})
    assert resp.status_code in (200, 201)


@pytest.mark.asyncio
async def test_detach_volume(client, mock_conn):
    with patch("app.api.compute.instances.nova.detach_volume", return_value=None):
        resp = await client.delete("/api/v1/instances/inst-1/volumes/vol-1")
    assert resp.status_code == 204


# ────── 인터페이스 Attach/Detach ──────


@pytest.mark.asyncio
async def test_attach_interface(client, mock_conn):
    with patch(
        "app.api.compute.instances.nova.attach_interface",
        return_value={"port_id": "port-1", "net_id": "net-1", "ip_address": "10.0.0.2"},
    ):
        resp = await client.post("/api/v1/instances/inst-1/interfaces", json={"net_id": "net-1"})
    assert resp.status_code in (200, 201)


@pytest.mark.asyncio
async def test_detach_interface(client, mock_conn):
    with patch("app.api.compute.instances.nova.detach_interface", return_value=None):
        resp = await client.delete("/api/v1/instances/inst-1/interfaces/port-1")
    assert resp.status_code == 204


# ────── 볼륨 delete_on_termination 토글 ──────


@pytest.mark.asyncio
async def test_update_volume_attachment_set_true(client, mock_conn):
    with patch("app.api.compute.instances.nova.update_volume_attachment_delete_flag") as mock_update:
        resp = await client.patch(
            "/api/v1/instances/inst-1/volumes/vol-1",
            json={"delete_on_termination": True},
        )
    assert resp.status_code == 204
    mock_update.assert_called_once_with(mock_conn, "inst-1", "vol-1", True)


@pytest.mark.asyncio
async def test_update_volume_attachment_set_false(client, mock_conn):
    with patch("app.api.compute.instances.nova.update_volume_attachment_delete_flag") as mock_update:
        resp = await client.patch(
            "/api/v1/instances/inst-1/volumes/vol-1",
            json={"delete_on_termination": False},
        )
    assert resp.status_code == 204
    mock_update.assert_called_once_with(mock_conn, "inst-1", "vol-1", False)


@pytest.mark.asyncio
async def test_update_volume_attachment_missing_body(client, mock_conn):
    """body 누락 시 422."""
    resp = await client.patch("/api/v1/instances/inst-1/volumes/vol-1", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_volume_attachment_server_error(client, mock_conn):
    """Nova 호출 실패 시 500."""
    with patch(
        "app.api.compute.instances.nova.update_volume_attachment_delete_flag",
        side_effect=Exception("Nova 오류"),
    ):
        resp = await client.patch(
            "/api/v1/instances/inst-1/volumes/vol-1",
            json={"delete_on_termination": True},
        )
    assert resp.status_code == 500


# ────── 입력 검증 ──────


@pytest.mark.asyncio
async def test_create_instance_invalid_name(client, mock_conn):
    """인스턴스 이름 regex 검증 — 특수문자 포함 시 422."""
    resp = await client.post(
        "/api/v1/instances",
        json={
            "name": "invalid name!",
            "image_id": "img-1",
            "flavor_id": "flavor-1",
            "network_id": "net-1",
        },
    )
    assert resp.status_code == 422


# ────── Floating IP 해제 — cleanup_instance_fips 범위 검증 ──────


def _make_port(pid: str, subnet_id: str = "subnet-1"):
    from unittest.mock import MagicMock

    p = MagicMock()
    p.id = pid
    p.fixed_ips = [{"subnet_id": subnet_id, "ip_address": "10.0.0.5"}]
    return p


def _make_fip(fid: str, port_id: str | None):
    from unittest.mock import MagicMock

    f = MagicMock()
    f.id = fid
    f.port_id = port_id
    return f


@pytest.mark.asyncio
async def test_release_floating_ip_only_targets_instance_ports(client, mock_conn):
    """해제 시 해당 인스턴스 포트에 연결된 FIP만 update/delete 한다."""
    mock_conn.network.ports.return_value = [_make_port("p1"), _make_port("p2")]
    mock_conn.network.ips.return_value = [
        _make_fip("fip-1", "p1"),  # 대상 인스턴스 포트
        _make_fip("fip-2", "other-port"),  # 다른 인스턴스
        _make_fip("fip-3", None),  # 미연결
    ]

    resp = await client.delete("/api/v1/instances/inst-1/floating-ip")
    assert resp.status_code == 204

    called_ids = [call.args[0] for call in mock_conn.network.update_ip.call_args_list]
    assert called_ids == ["fip-1"], f"expected only fip-1 to be updated, got {called_ids}"
    called_delete_ids = [call.args[0] for call in mock_conn.network.delete_ip.call_args_list]
    assert called_delete_ids == ["fip-1"], f"expected only fip-1 to be deleted, got {called_delete_ids}"


@pytest.mark.asyncio
async def test_release_floating_ip_no_ports_does_nothing(client, mock_conn):
    """포트가 없는 인스턴스 해제 시 어떤 FIP도 건드리지 않는다."""
    mock_conn.network.ports.return_value = []

    resp = await client.delete("/api/v1/instances/inst-1/floating-ip")
    assert resp.status_code == 204

    mock_conn.network.update_ip.assert_not_called()
    mock_conn.network.delete_ip.assert_not_called()


@pytest.mark.asyncio
async def test_delete_instance_only_cleans_own_fips(client, mock_conn):
    """인스턴스 삭제 시에도 해당 인스턴스 FIP만 정리된다 (다른 FIP 무사)."""
    inst = make_instance()
    inst.metadata = {}
    mock_conn.network.ports.return_value = [_make_port("p-inst")]
    mock_conn.network.ips.return_value = [
        _make_fip("fip-own", "p-inst"),
        _make_fip("fip-other", "p-other"),
    ]

    with (
        patch("app.api.compute.instances.nova.get_server", return_value=inst),
        patch("app.api.compute.instances.nova.delete_server", return_value=None),
        patch("app.api.compute.instances.cinder.delete_volume", return_value=None),
    ):
        resp = await client.delete("/api/v1/instances/inst-1")
    assert resp.status_code == 204

    called_delete_ids = [call.args[0] for call in mock_conn.network.delete_ip.call_args_list]
    assert "fip-own" in called_delete_ids
    assert "fip-other" not in called_delete_ids


@pytest.mark.asyncio
async def test_release_floating_ip_per_fip_failure_isolated(client, mock_conn):
    """첫 FIP 정리 실패해도 두 번째 FIP는 정상 처리된다 (best-effort)."""
    mock_conn.network.ports.return_value = [_make_port("p1")]
    mock_conn.network.ips.return_value = [
        _make_fip("fip-fail", "p1"),
        _make_fip("fip-ok", "p1"),
    ]
    mock_conn.network.update_ip.side_effect = [Exception("Neutron 오류"), None]

    resp = await client.delete("/api/v1/instances/inst-1/floating-ip")
    assert resp.status_code == 204

    update_calls = [call.args[0] for call in mock_conn.network.update_ip.call_args_list]
    assert update_calls == ["fip-fail", "fip-ok"]


# ────── Floating IP 할당 (assign) ──────


def _make_net(net_id: str, is_external: bool = False):
    from unittest.mock import MagicMock

    n = MagicMock()
    n.id = net_id
    n.is_external = is_external
    return n


def _make_fip_info(fip_id: str, addr: str, port_id: str | None = None):
    from app.models.storage import FloatingIpInfo

    return FloatingIpInfo(id=fip_id, floating_ip_address=addr, port_id=port_id, floating_network_id="ext-net")


@pytest.mark.asyncio
async def test_assign_floating_ip_single_port_success(client, mock_conn):
    """단일 포트 인스턴스에 FIP 정상 할당."""
    mock_conn.network.ports.return_value = [_make_port("p1")]
    mock_conn.network.ips.return_value = []  # 기존 FIP 없음

    with (
        patch(
            "app.api.compute.instances.neutron.find_external_network_for_subnets",
            return_value="ext-net",
        ),
        patch(
            "app.api.compute.instances.neutron.create_floating_ip",
            return_value=_make_fip_info("fip-new", "172.30.100.1"),
        ),
        patch(
            "app.api.compute.instances.neutron.associate_floating_ip",
            return_value=_make_fip_info("fip-new", "172.30.100.1", port_id="p1"),
        ),
    ):
        resp = await client.post("/api/v1/instances/inst-1/floating-ip")

    assert resp.status_code == 200
    assert resp.json()["floating_ip_address"] == "172.30.100.1"


@pytest.mark.asyncio
async def test_assign_floating_ip_multi_port_selects_available(client, mock_conn):
    """다중 포트에서 첫 포트가 점유된 경우 두 번째 포트로 자동 선택."""
    mock_conn.network.ports.return_value = [_make_port("p1"), _make_port("p2")]
    # p1은 이미 FIP 점유, p2는 자유
    mock_conn.network.ips.return_value = [_make_fip("fip-existing", "p1")]

    captured_port = {}

    def fake_associate(conn, fip_id, instance_id, port_id=None):
        captured_port["id"] = port_id
        return _make_fip_info("fip-new", "172.30.100.2", port_id=port_id)

    with (
        patch(
            "app.api.compute.instances.neutron.find_external_network_for_subnets",
            return_value="ext-net",
        ),
        patch(
            "app.api.compute.instances.neutron.create_floating_ip",
            return_value=_make_fip_info("fip-new", "172.30.100.2"),
        ),
        patch("app.api.compute.instances.neutron.associate_floating_ip", side_effect=fake_associate),
    ):
        resp = await client.post("/api/v1/instances/inst-1/floating-ip")

    assert resp.status_code == 200
    # 사용 가능한 포트(p2)가 선택되어야 한다
    assert captured_port["id"] == "p2"


@pytest.mark.asyncio
async def test_assign_floating_ip_all_ports_occupied_returns_400(client, mock_conn):
    """모든 포트가 이미 FIP를 가진 경우 400 반환."""
    mock_conn.network.ports.return_value = [_make_port("p1")]
    mock_conn.network.ips.return_value = [_make_fip("fip-existing", "p1")]

    resp = await client.post("/api/v1/instances/inst-1/floating-ip")

    assert resp.status_code == 400
    assert "이미 Floating IP" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_assign_floating_ip_explicit_port_already_occupied_returns_409(client, mock_conn):
    """명시적으로 지정한 port_id가 이미 점유된 경우 409 반환."""
    mock_conn.network.ports.return_value = [_make_port("p1")]
    mock_conn.network.ips.return_value = [_make_fip("fip-existing", "p1")]

    resp = await client.post("/api/v1/instances/inst-1/floating-ip?port_id=p1")

    assert resp.status_code == 409
    assert "이미 Floating IP" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_assign_floating_ip_conflict_exception_rolls_back(client, mock_conn):
    """race로 ConflictException 발생 시 생성된 FIP를 삭제(rollback)한다."""
    from openstack.exceptions import ConflictException

    mock_conn.network.ports.return_value = [_make_port("p1")]
    mock_conn.network.ips.return_value = []

    deleted = []

    def fake_delete(conn, fip_id):
        deleted.append(fip_id)

    with (
        patch(
            "app.api.compute.instances.neutron.find_external_network_for_subnets",
            return_value="ext-net",
        ),
        patch(
            "app.api.compute.instances.neutron.create_floating_ip",
            return_value=_make_fip_info("fip-race", "172.30.100.3"),
        ),
        patch(
            "app.api.compute.instances.neutron.associate_floating_ip",
            side_effect=ConflictException("already has fip"),
        ),
        patch("app.api.compute.instances.neutron.delete_floating_ip", side_effect=fake_delete),
    ):
        resp = await client.post("/api/v1/instances/inst-1/floating-ip")

    assert resp.status_code == 409
    assert "fip-race" in deleted


@pytest.mark.asyncio
async def test_assign_floating_ip_no_router_returns_422(client, mock_conn):
    """서브넷이 라우터로 외부망에 연결되어 있지 않으면 422 + 안내 메시지."""
    mock_conn.network.ports.return_value = [_make_port("p1")]
    mock_conn.network.ips.return_value = []

    with patch(
        "app.api.compute.instances.neutron.find_external_network_for_subnets",
        return_value=None,
    ):
        resp = await client.post("/api/v1/instances/inst-1/floating-ip")

    assert resp.status_code == 422
    assert "라우터" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_assign_floating_ip_unreachable_external_network_returns_422(client, mock_conn):
    """associate에서 'is not reachable from subnet' 오류 발생 시 422 + 안내."""
    mock_conn.network.ports.return_value = [_make_port("p1")]
    mock_conn.network.ips.return_value = []

    deleted = []

    def fake_delete(conn, fip_id):
        deleted.append(fip_id)

    with (
        patch(
            "app.api.compute.instances.neutron.find_external_network_for_subnets",
            return_value="ext-mismatch",
        ),
        patch(
            "app.api.compute.instances.neutron.create_floating_ip",
            return_value=_make_fip_info("fip-orphan", "172.30.100.9"),
        ),
        patch(
            "app.api.compute.instances.neutron.associate_floating_ip",
            side_effect=Exception(
                "ResourceNotFound: External network ext-mismatch is not reachable from subnet subnet-1."
            ),
        ),
        patch("app.api.compute.instances.neutron.delete_floating_ip", side_effect=fake_delete),
    ):
        resp = await client.post("/api/v1/instances/inst-1/floating-ip")

    assert resp.status_code == 422
    assert "도달 불가능" in resp.json()["detail"]
    assert "fip-orphan" in deleted


# ────── Union SG 자동 attach 테스트 ──────


@pytest.mark.asyncio
async def test_create_instance_with_libraries_attaches_union_sg(client, mock_conn):
    """Union 라이브러리를 사용하는 VM 생성 시 union-egress SG가 자동으로 attach된다."""
    from unittest.mock import MagicMock as MM

    attached_sgs = []

    def fake_create_server(conn, name, flavor_id, network_id, boot_volume_id, **kwargs):
        attached_sgs.extend(kwargs.get("security_groups") or [])
        return make_instance("srv-new")

    fake_vol = MM()
    fake_vol.id = "vol-boot"
    fake_flavor = MM()
    fake_flavor.id = "flavor-1"
    fake_flavor.is_gpu = False
    fake_flavor.extra_specs = {}
    fake_upper = MM()
    fake_upper.id = "vol-upper"
    mock_conn.compute.create_volume_attachment.return_value = MM()

    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[fake_flavor]),
        patch("app.api.compute.instances.cinder.create_volume_from_image", return_value=fake_vol),
        patch("app.api.compute.instances.cinder.rename_volume"),
        patch("app.api.compute.instances.cinder.create_empty_volume", return_value=fake_upper),
        patch("app.api.compute.instances.lib_svc.resolve_with_deps", return_value=["python311"]),
        patch(
            "app.api.compute.instances._prepare_prebuilt_file_storages",
            return_value=[{"file_storage_id": "share-1", "name": "python311", "share_proto": "CEPHFS"}],
        ),
        patch("app.api.compute.instances.cloudinit.generate_userdata", return_value=b"userdata"),
        patch("app.api.compute.instances.neutron.ensure_union_egress_sg", return_value="union-egress-default"),
        patch("app.api.compute.instances.nova.create_server", side_effect=fake_create_server),
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
    ):
        resp = await client.post(
            "/api/v1/instances",
            json={
                "name": "test-vm",
                "image_id": "img-1",
                "flavor_id": "flavor-1",
                "network_id": "net-1",
                "libraries": ["python311"],
                "strategy": "prebuilt",
            },
        )

    assert resp.status_code in (200, 201, 202)
    assert "union-egress-default" in attached_sgs


@pytest.mark.asyncio
async def test_create_instance_sg_skipped_when_disabled(client, mock_conn):
    """union_auto_egress_sg_enabled=False 시 SG 자동 attach 생략."""
    from unittest.mock import MagicMock as MM

    ensure_called = []
    fake_vol = MM()
    fake_vol.id = "vol-boot"
    fake_flavor = MM()
    fake_flavor.id = "flavor-1"
    fake_flavor.is_gpu = False
    fake_flavor.extra_specs = {}
    fake_upper = MM()
    fake_upper.id = "vol-upper"
    mock_conn.compute.create_volume_attachment.return_value = MM()

    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[fake_flavor]),
        patch("app.api.compute.instances.cinder.create_volume_from_image", return_value=fake_vol),
        patch("app.api.compute.instances.cinder.rename_volume"),
        patch("app.api.compute.instances.cinder.create_empty_volume", return_value=fake_upper),
        patch("app.api.compute.instances.lib_svc.resolve_with_deps", return_value=["python311"]),
        patch(
            "app.api.compute.instances._prepare_prebuilt_file_storages",
            return_value=[{"file_storage_id": "share-1", "name": "python311", "share_proto": "CEPHFS"}],
        ),
        patch("app.api.compute.instances.cloudinit.generate_userdata", return_value=b"userdata"),
        patch(
            "app.api.compute.instances.neutron.ensure_union_egress_sg",
            side_effect=lambda *a, **kw: ensure_called.append(True) or "union-egress-default",
        ),
        patch("app.api.compute.instances.nova.create_server", return_value=make_instance("srv-new")),
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
        patch("app.api.compute.instances.get_settings") as mock_settings,
    ):
        s = MM()
        s.union_auto_egress_sg_enabled = False
        s.union_egress_sg_name = "union-egress-default"
        s.ceph_monitors = ""
        s.upper_volume_size_gb = 10
        s.os_manila_share_network_id = ""
        s.os_manila_share_type = ""
        s.os_manila_nfs_share_type = ""
        s.default_availability_zone = ""
        s.default_network_id = ""
        s.default_network_external_id = ""
        s.default_network_cidr = ""
        s.health_report_url = ""
        s.instance_volume_type = ""
        s.boot_volume_size_gb = 50
        mock_settings.return_value = s

        await client.post(
            "/api/v1/instances",
            json={
                "name": "test-vm",
                "image_id": "img-1",
                "flavor_id": "flavor-1",
                "network_id": "net-1",
                "libraries": ["python311"],
                "strategy": "prebuilt",
            },
        )

    assert not ensure_called, "union_auto_egress_sg_enabled=False임에도 ensure_union_egress_sg가 호출됨"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Monitoring SG auto-attach (A11 — node_exporter / dcgm_exporter 분리)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _make_monitoring_settings(gpu: bool = False, enabled: bool = True, cidr: str = "10.0.0.0/8"):
    """monitoring SG 관련 settings mock 헬퍼."""
    from unittest.mock import MagicMock as MM

    s = MM()
    s.union_auto_egress_sg_enabled = True
    s.union_egress_sg_name = "union-egress-default"
    s.monitoring_auto_sg_enabled = enabled
    s.monitoring_scrape_cidr = cidr
    s.node_exporter_sg_name = "node_exporter"
    s.dcgm_exporter_sg_name = "dcgm_exporter"
    s.ceph_monitors = ""
    s.upper_volume_size_gb = 10
    s.os_manila_share_network_id = ""
    s.os_manila_share_type = ""
    s.os_manila_nfs_share_type = ""
    s.default_availability_zone = ""
    s.default_network_id = ""
    s.default_network_external_id = ""
    s.default_network_cidr = ""
    s.instance_health_callback_base_url = ""
    s.instance_volume_type = ""
    s.boot_volume_size_gb = 50
    return s


def _make_flavor(is_gpu: bool = False):
    from unittest.mock import MagicMock as MM

    f = MM()
    f.id = "flavor-gpu" if is_gpu else "flavor-1"
    f.is_gpu = is_gpu
    f.extra_specs = {}
    return f


@pytest.mark.asyncio
async def test_create_instance_non_gpu_attaches_node_exporter_only(client, mock_conn):
    """non-GPU flavor — node_exporter SG + default 포함, dcgm_exporter 미호출."""
    from unittest.mock import MagicMock as MM

    attached_sgs = []
    dc_called = []

    def fake_create_server(conn, name, flavor_id, network_id, boot_volume_id, **kwargs):
        attached_sgs.extend(kwargs.get("security_groups") or [])
        return make_instance("srv-new")

    fake_vol = MM()
    fake_vol.id = "vol-boot"
    fake_upper = MM()
    fake_upper.id = "vol-upper"
    mock_conn.compute.create_volume_attachment.return_value = MM()

    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[_make_flavor(is_gpu=False)]),
        patch("app.api.compute.instances.cinder.create_volume_from_image", return_value=fake_vol),
        patch("app.api.compute.instances.cinder.rename_volume"),
        patch("app.api.compute.instances.cinder.create_empty_volume", return_value=fake_upper),
        patch("app.api.compute.instances.lib_svc.resolve_with_deps", return_value=["python311"]),
        patch(
            "app.api.compute.instances._prepare_prebuilt_file_storages",
            return_value=[{"file_storage_id": "share-1", "name": "python311", "share_proto": "CEPHFS"}],
        ),
        patch("app.api.compute.instances.cloudinit.generate_userdata", return_value=b"userdata"),
        patch("app.api.compute.instances.neutron.ensure_union_egress_sg", return_value="union-egress-default"),
        patch("app.api.compute.instances.neutron.ensure_node_exporter_sg", return_value="node_exporter"),
        patch(
            "app.api.compute.instances.neutron.ensure_dcgm_exporter_sg",
            side_effect=lambda *a, **kw: dc_called.append(True) or "dcgm_exporter",
        ),
        patch("app.api.compute.instances.nova.create_server", side_effect=fake_create_server),
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
        patch("app.api.compute.instances.get_settings", return_value=_make_monitoring_settings(gpu=False)),
    ):
        resp = await client.post(
            "/api/v1/instances",
            json={
                "name": "test-vm",
                "image_id": "img-1",
                "flavor_id": "flavor-1",
                "network_id": "net-1",
                "libraries": ["python311"],
                "strategy": "prebuilt",
            },
        )

    assert resp.status_code in (200, 201, 202)
    assert "node_exporter" in attached_sgs
    assert "default" in attached_sgs
    assert not dc_called, "non-GPU 인스턴스에 dcgm_exporter SG가 attach됨"


@pytest.mark.asyncio
async def test_create_instance_gpu_attaches_both_sgs(client, mock_conn):
    """GPU flavor — node_exporter + dcgm_exporter + default 모두 포함."""
    from unittest.mock import MagicMock as MM

    attached_sgs = []

    def fake_create_server(conn, name, flavor_id, network_id, boot_volume_id, **kwargs):
        attached_sgs.extend(kwargs.get("security_groups") or [])
        return make_instance("srv-new")

    fake_vol = MM()
    fake_vol.id = "vol-boot"
    fake_upper = MM()
    fake_upper.id = "vol-upper"
    mock_conn.compute.create_volume_attachment.return_value = MM()

    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[_make_flavor(is_gpu=True)]),
        patch("app.services.gpu_quota.check_gpu_quota") as mock_check,
        patch("app.api.compute.instances.cinder.create_volume_from_image", return_value=fake_vol),
        patch("app.api.compute.instances.cinder.rename_volume"),
        patch("app.api.compute.instances.cinder.create_empty_volume", return_value=fake_upper),
        patch("app.api.compute.instances.lib_svc.resolve_with_deps", return_value=["python311"]),
        patch(
            "app.api.compute.instances._prepare_prebuilt_file_storages",
            return_value=[{"file_storage_id": "share-1", "name": "python311", "share_proto": "CEPHFS"}],
        ),
        patch("app.api.compute.instances.cloudinit.generate_userdata", return_value=b"userdata"),
        patch("app.api.compute.instances.neutron.ensure_union_egress_sg", return_value="union-egress-default"),
        patch("app.api.compute.instances.neutron.ensure_node_exporter_sg", return_value="node_exporter"),
        patch("app.api.compute.instances.neutron.ensure_dcgm_exporter_sg", return_value="dcgm_exporter"),
        patch("app.api.compute.instances.nova.create_server", side_effect=fake_create_server),
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
        patch("app.api.compute.instances.get_settings", return_value=_make_monitoring_settings(gpu=True)),
    ):
        resp = await client.post(
            "/api/v1/instances",
            json={
                "name": "test-vm",
                "image_id": "img-1",
                "flavor_id": "flavor-gpu",
                "network_id": "net-1",
                "libraries": ["python311"],
                "strategy": "prebuilt",
            },
        )

    assert resp.status_code in (200, 201, 202)
    mock_check.assert_awaited_once()
    assert "node_exporter" in attached_sgs
    assert "dcgm_exporter" in attached_sgs
    assert "default" in attached_sgs


@pytest.mark.asyncio
async def test_create_instance_monitoring_sg_skipped_when_disabled(client, mock_conn):
    """monitoring_auto_sg_enabled=False 시 두 SG 모두 미호출."""
    from unittest.mock import MagicMock as MM

    ne_called = []
    dc_called = []

    fake_vol = MM()
    fake_vol.id = "vol-boot"
    fake_upper = MM()
    fake_upper.id = "vol-upper"
    mock_conn.compute.create_volume_attachment.return_value = MM()

    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[_make_flavor(is_gpu=False)]),
        patch("app.api.compute.instances.cinder.create_volume_from_image", return_value=fake_vol),
        patch("app.api.compute.instances.cinder.rename_volume"),
        patch("app.api.compute.instances.cinder.create_empty_volume", return_value=fake_upper),
        patch("app.api.compute.instances.lib_svc.resolve_with_deps", return_value=["python311"]),
        patch(
            "app.api.compute.instances._prepare_prebuilt_file_storages",
            return_value=[{"file_storage_id": "share-1", "name": "python311", "share_proto": "CEPHFS"}],
        ),
        patch("app.api.compute.instances.cloudinit.generate_userdata", return_value=b"userdata"),
        patch("app.api.compute.instances.neutron.ensure_union_egress_sg", return_value="union-egress-default"),
        patch(
            "app.api.compute.instances.neutron.ensure_node_exporter_sg",
            side_effect=lambda *a, **kw: ne_called.append(True) or "node_exporter",
        ),
        patch(
            "app.api.compute.instances.neutron.ensure_dcgm_exporter_sg",
            side_effect=lambda *a, **kw: dc_called.append(True) or "dcgm_exporter",
        ),
        patch("app.api.compute.instances.nova.create_server", return_value=make_instance("srv-new")),
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
        patch(
            "app.api.compute.instances.get_settings",
            return_value=_make_monitoring_settings(enabled=False),
        ),
    ):
        await client.post(
            "/api/v1/instances",
            json={
                "name": "test-vm",
                "image_id": "img-1",
                "flavor_id": "flavor-1",
                "network_id": "net-1",
                "libraries": ["python311"],
                "strategy": "prebuilt",
            },
        )

    assert not ne_called, "monitoring_auto_sg_enabled=False인데 ensure_node_exporter_sg 호출됨"
    assert not dc_called, "monitoring_auto_sg_enabled=False인데 ensure_dcgm_exporter_sg 호출됨"


@pytest.mark.asyncio
async def test_create_instance_monitoring_sg_skipped_when_no_cidr(client, mock_conn):
    """monitoring_scrape_cidr 빈 값이면 두 SG 모두 미호출."""
    from unittest.mock import MagicMock as MM

    ne_called = []

    fake_vol = MM()
    fake_vol.id = "vol-boot"
    fake_upper = MM()
    fake_upper.id = "vol-upper"
    mock_conn.compute.create_volume_attachment.return_value = MM()

    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[_make_flavor(is_gpu=False)]),
        patch("app.api.compute.instances.cinder.create_volume_from_image", return_value=fake_vol),
        patch("app.api.compute.instances.cinder.rename_volume"),
        patch("app.api.compute.instances.cinder.create_empty_volume", return_value=fake_upper),
        patch("app.api.compute.instances.lib_svc.resolve_with_deps", return_value=["python311"]),
        patch(
            "app.api.compute.instances._prepare_prebuilt_file_storages",
            return_value=[{"file_storage_id": "share-1", "name": "python311", "share_proto": "CEPHFS"}],
        ),
        patch("app.api.compute.instances.cloudinit.generate_userdata", return_value=b"userdata"),
        patch("app.api.compute.instances.neutron.ensure_union_egress_sg", return_value="union-egress-default"),
        patch(
            "app.api.compute.instances.neutron.ensure_node_exporter_sg",
            side_effect=lambda *a, **kw: ne_called.append(True) or "node_exporter",
        ),
        patch("app.api.compute.instances.nova.create_server", return_value=make_instance("srv-new")),
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
        patch(
            "app.api.compute.instances.get_settings",
            return_value=_make_monitoring_settings(cidr=""),
        ),
    ):
        await client.post(
            "/api/v1/instances",
            json={
                "name": "test-vm",
                "image_id": "img-1",
                "flavor_id": "flavor-1",
                "network_id": "net-1",
                "libraries": ["python311"],
                "strategy": "prebuilt",
            },
        )

    assert not ne_called, "scrape_cidr 미설정인데 ensure_node_exporter_sg 호출됨"
