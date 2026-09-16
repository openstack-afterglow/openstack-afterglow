"""관리자용 cross-project 인스턴스 생성 엔드포인트 단위 테스트."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_mock_conn


@pytest.fixture(autouse=True)
def _resolve_default_placement_policies(monkeypatch):
    """Keep cross-project instance tests independent of placement policy storage."""

    async def resolve_zones(_conn, _requested_zone):
        return "", ""

    monkeypatch.setattr(
        "app.services.instance_orchestration.resolve_availability_zones",
        resolve_zones,
    )

    async def resolve_network(_conn, _settings):
        return None

    monkeypatch.setattr(
        "app.services.instance_orchestration.resolve_default_network",
        resolve_network,
    )


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _make_server(server_id: str = "srv-admin-1") -> MagicMock:
    srv = MagicMock()
    srv.id = server_id
    srv.name = "admin-vm"
    srv.status = "BUILD"
    srv.fault = None
    return srv


def _make_flavor(flavor_id: str = "f1") -> SimpleNamespace:
    return SimpleNamespace(id=flavor_id, name="m1.small", extra_specs={})


def _make_boot_vol(status: str = "available", bootable: bool = True) -> MagicMock:
    vol = MagicMock()
    vol.id = "vol-boot-1"
    vol.status = status
    vol.bootable = bootable
    return vol


_BASE_PAYLOAD = {
    "name": "admin-vm",
    "image_id": "img-1",
    "flavor_id": "flavor-1",
    "network_id": "net-1",
    "project_id": "target-project-abc",
}

_COMMON_PATCHES = [
    ("app.api.identity.admin_instances.lib_svc.resolve_with_deps", []),
    ("app.api.identity.admin_instances.nova.list_flavors", []),
    ("app.api.identity.admin_instances.neutron.list_networks", []),
    ("app.api.identity.admin_instances.cloudinit.generate_userdata", ""),
    ("app.api.compute.instances._prepare_dynamic_file_storage", {}),
    ("app.api.compute.instances._prepare_prebuilt_file_storages", []),
]


# ---------------------------------------------------------------------------
# 권한 검사
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_create_instance_non_admin_returns_403(client):
    """admin 권한 없는 사용자는 403."""
    resp = await client.post("/api/v1/admin/instances/async", json=_BASE_PAYLOAD)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_list_networks_non_admin_returns_403(client):
    """admin 권한 없는 사용자는 403."""
    resp = await client.get("/api/v1/admin/instances/networks-for-project?project_id=p1")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_list_security_groups_non_admin_returns_403(client):
    resp = await client.get("/api/v1/admin/instances/security-groups-for-project?project_id=p1")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_list_volumes_non_admin_returns_403(client):
    resp = await client.get("/api/v1/admin/instances/volumes-for-project?project_id=p1")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 입력 검증
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_create_instance_missing_project_id_returns_422(admin_client):
    """project_id 누락 시 422."""
    payload = {k: v for k, v in _BASE_PAYLOAD.items() if k != "project_id"}
    resp = await admin_client.post("/api/v1/admin/instances/async", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_create_instance_missing_boot_source_returns_422(admin_client):
    """image_id와 boot_volume_id 모두 없으면 422."""
    payload = {"name": "vm", "flavor_id": "flavor-1", "project_id": "proj-1"}
    resp = await admin_client.post("/api/v1/admin/instances/async", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_list_networks_missing_project_id_returns_422(admin_client):
    """project_id 쿼리 파라미터 누락 시 422."""
    resp = await admin_client.get("/api/v1/admin/instances/networks-for-project")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 네트워크 / 보안 그룹 조회
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_list_networks_calls_admin_conn(admin_client):
    """get_admin_connection_for_project가 지정한 project_id로 호출되는지 검증."""
    mock_conn = make_mock_conn("target-project-abc")
    with (
        patch(
            "app.api.identity.admin_instances.keystone.get_admin_connection_for_project",
            return_value=mock_conn,
        ) as mock_get_conn,
        patch("app.api.identity.admin_instances.neutron.list_networks", return_value=[]),
    ):
        resp = await admin_client.get("/api/v1/admin/instances/networks-for-project?project_id=target-project-abc")
    assert resp.status_code == 200
    mock_get_conn.assert_called_once_with("target-project-abc")


@pytest.mark.asyncio
async def test_admin_list_security_groups_returns_list(admin_client):
    mock_conn = make_mock_conn("proj-1")
    with (
        patch(
            "app.api.identity.admin_instances.keystone.get_admin_connection_for_project",
            return_value=mock_conn,
        ),
        patch(
            "app.api.identity.admin_instances.neutron.list_security_groups",
            return_value=[{"id": "sg-1", "name": "default"}],
        ),
    ):
        resp = await admin_client.get("/api/v1/admin/instances/security-groups-for-project?project_id=proj-1")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# SSE 인스턴스 생성
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_create_instance_calls_admin_conn(admin_client):
    """admin 생성 시 get_admin_connection_for_project가 target project_id로 호출된다."""
    mock_conn = make_mock_conn("target-project-abc")
    mock_conn.compute.create_volume_attachment = MagicMock(return_value=None)

    with (
        patch(
            "app.api.identity.admin_instances.keystone.get_admin_connection_for_project",
            return_value=mock_conn,
        ) as mock_get_conn,
        patch("app.api.identity.admin_instances.lib_svc.resolve_with_deps", return_value=[]),
        patch("app.api.identity.admin_instances.nova.list_flavors", return_value=[_make_flavor("flavor-1")]),
        patch(
            "app.api.identity.admin_instances.cinder.get_volume",
            return_value=_make_boot_vol(),
        ),
        patch("app.api.identity.admin_instances.cinder.create_volume_from_image") as mock_create_img,
        patch("app.api.identity.admin_instances.nova.create_server", return_value=_make_server()),
        patch("app.api.identity.admin_instances.neutron.list_networks", return_value=[]),
        patch("app.api.compute.instances._prepare_dynamic_file_storage", return_value={}),
    ):
        resp = await admin_client.post("/api/v1/admin/instances/async", json=_BASE_PAYLOAD)

    assert resp.status_code == 200
    mock_get_conn.assert_called_once_with("target-project-abc")
    mock_create_img.assert_called_once()  # image_id로 부팅 볼륨 생성


@pytest.mark.asyncio
async def test_admin_create_instance_from_image_sse(admin_client):
    """image_id 사용 시 SSE 스트림이 시작되어 200 응답이 반환된다."""
    mock_conn = make_mock_conn("proj-x")
    mock_conn.compute.create_volume_attachment = MagicMock(return_value=None)

    boot_vol = MagicMock()
    boot_vol.id = "new-boot-vol"
    boot_vol.status = "available"

    with (
        patch(
            "app.api.identity.admin_instances.keystone.get_admin_connection_for_project",
            return_value=mock_conn,
        ),
        patch("app.api.identity.admin_instances.lib_svc.resolve_with_deps", return_value=[]),
        patch("app.api.identity.admin_instances.nova.list_flavors", return_value=[_make_flavor()]),
        patch("app.api.identity.admin_instances.cinder.create_volume_from_image", return_value=boot_vol),
        patch("app.api.identity.admin_instances.cinder.rename_volume", return_value=None),
        patch("app.api.identity.admin_instances.nova.create_server", return_value=_make_server()),
        patch("app.api.identity.admin_instances.neutron.list_networks", return_value=[]),
        patch("app.api.compute.instances._prepare_dynamic_file_storage", return_value={}),
    ):
        resp = await admin_client.post(
            "/api/v1/admin/instances/async",
            json={"name": "vm-img", "image_id": "img-1", "flavor_id": "f1", "project_id": "proj-x"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_create_instance_boot_from_volume(admin_client):
    """boot_volume_id 지정 시 get_volume이 검증에 호출된다."""
    mock_conn = make_mock_conn("proj-y")
    mock_conn.compute.create_volume_attachment = MagicMock(return_value=None)

    with (
        patch(
            "app.api.identity.admin_instances.keystone.get_admin_connection_for_project",
            return_value=mock_conn,
        ),
        patch("app.api.identity.admin_instances.lib_svc.resolve_with_deps", return_value=[]),
        patch("app.api.identity.admin_instances.nova.list_flavors", return_value=[_make_flavor()]),
        patch(
            "app.api.identity.admin_instances.cinder.get_volume",
            return_value=_make_boot_vol(),
        ) as mock_get_vol,
        patch("app.api.identity.admin_instances.nova.create_server", return_value=_make_server()),
        patch("app.api.identity.admin_instances.neutron.list_networks", return_value=[]),
        patch("app.api.compute.instances._prepare_dynamic_file_storage", return_value={}),
    ):
        resp = await admin_client.post(
            "/api/v1/admin/instances/async",
            json={
                "name": "vm-vol",
                "boot_volume_id": "vol-boot-1",
                "flavor_id": "f1",
                "network_id": "net-1",
                "project_id": "proj-y",
            },
        )

    assert resp.status_code == 200
    mock_get_vol.assert_called_once_with(mock_conn, "vol-boot-1")


@pytest.mark.asyncio
async def test_admin_create_instance_no_keypair_allowed(admin_client):
    """key_name 없이도 admin 생성 성공 (콘솔 비밀번호 fallback)."""
    mock_conn = make_mock_conn("proj-z")
    mock_conn.compute.create_volume_attachment = MagicMock(return_value=None)

    boot_vol = MagicMock()
    boot_vol.id = "bv-1"
    boot_vol.status = "available"

    with (
        patch(
            "app.api.identity.admin_instances.keystone.get_admin_connection_for_project",
            return_value=mock_conn,
        ),
        patch("app.api.identity.admin_instances.lib_svc.resolve_with_deps", return_value=[]),
        patch("app.api.identity.admin_instances.nova.list_flavors", return_value=[_make_flavor()]),
        patch("app.api.identity.admin_instances.cinder.create_volume_from_image", return_value=boot_vol),
        patch("app.api.identity.admin_instances.cinder.rename_volume", return_value=None),
        patch(
            "app.api.identity.admin_instances.nova.create_server",
            return_value=_make_server(),
        ) as mock_create_srv,
        patch("app.api.identity.admin_instances.neutron.list_networks", return_value=[]),
        patch("app.api.compute.instances._prepare_dynamic_file_storage", return_value={}),
    ):
        resp = await admin_client.post(
            "/api/v1/admin/instances/async",
            json={"name": "vm-nokey", "image_id": "img-1", "flavor_id": "f1", "project_id": "proj-z"},
        )

    assert resp.status_code == 200
    # key_name이 None으로 전달되어야 함
    called_kwargs = mock_create_srv.call_args.kwargs
    assert called_kwargs.get("key_name") is None
