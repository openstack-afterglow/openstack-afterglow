"""기존 부팅 볼륨으로 인스턴스 생성 단위 테스트."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from openstack.block_storage.v3.volume import Volume

from app.models.compute import InstanceInfo
from app.models.storage import VolumeInfo
from app.services.cinder import _vol_to_info


def _make_flavor():
    return SimpleNamespace(id="flavor-1", name="m1.small", extra_specs={})


@pytest.fixture(autouse=True)
def _resolve_default_placement_policies(monkeypatch):
    """Keep boot-volume tests focused on volume behavior, not policy persistence."""

    async def resolve_zones(_conn, _requested_zone):
        return "", ""

    monkeypatch.setattr(
        "app.api.compute.instances.instance_orch.resolve_availability_zones",
        resolve_zones,
    )
    monkeypatch.setattr(
        "app.api.compute.instances.nova.list_flavors",
        lambda _conn: [_make_flavor()],
    )


def test_vol_to_info_reads_bootable_via_sdk_alias():
    """openstacksdk는 Python alias `is_bootable`을 씀 — to_dict(original_names=True)로 API 필드 `bootable`을 읽는지 검증."""
    vol = Volume.new(
        **{
            "id": "vol-x",
            "name": "test-boot",
            "status": "available",
            "size": 30,
            "volume_type": "ceph_hdd",
            "attachments": [],
            "bootable": "true",
            "volume_image_metadata": {"os_distro": "ubuntu", "os_version": "22.04", "image_name": "ubuntu-22.04"},
        }
    )
    info = _vol_to_info(vol)
    assert info.bootable is True
    assert info.volume_image_metadata is not None
    assert info.volume_image_metadata["os_distro"] == "ubuntu"


def test_vol_to_info_non_bootable_volume():
    vol = Volume.new(
        **{
            "id": "vol-y",
            "name": "data-vol",
            "status": "in-use",
            "size": 10,
            "volume_type": "ceph_hdd",
            "attachments": [],
        }
    )
    info = _vol_to_info(vol)
    assert info.bootable is False
    assert info.volume_image_metadata is None


def _make_boot_vol(status: str = "available", bootable: bool = True) -> VolumeInfo:
    return VolumeInfo(
        id="vol-boot-1",
        name="test-boot-vol",
        status=status,
        size=50,
        bootable=bootable,
        attachments=[],
    )


def _make_upper_vol(status: str = "available") -> VolumeInfo:
    return VolumeInfo(id="vol-upper-1", name="upper", status=status, size=10, attachments=[])


def _make_server() -> InstanceInfo:
    return InstanceInfo(
        id="srv-1",
        name="test-vm",
        status="BUILD",
        image_id=None,
        image_name=None,
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
        user_id="test-user",
    )


_BASE_PAYLOAD = {
    "name": "test-vm",
    "boot_volume_id": "vol-boot-1",
    "flavor_id": "flavor-1",
    "network_id": "net-1",
}


_COMMON_PATCHES = [
    ("app.api.compute.instances.lib_svc.resolve_with_deps", []),
    ("app.api.compute.instances._prepare_dynamic_file_storage", {}),
    ("app.api.compute.instances.cinder.create_empty_volume", None),  # 각 테스트에서 개별 override
    ("app.api.compute.instances.nova.list_flavors", [_make_flavor()]),
    ("app.api.compute.instances.neutron.list_networks", []),
    ("app.api.compute.instances.cloudinit.generate_userdata", ""),
]


@pytest.mark.asyncio
async def test_boot_from_volume_skips_create_volume_from_image(client, mock_conn):
    """boot_volume_id 지정 시 cinder.create_volume_from_image 를 호출하지 않는다."""
    mock_conn.compute.create_volume_attachment = MagicMock(return_value=None)

    with (
        patch("app.api.compute.instances.lib_svc.resolve_with_deps", return_value=[]),
        patch("app.api.compute.instances._prepare_dynamic_file_storage", return_value={}),
        patch("app.api.compute.instances.cinder.get_volume", return_value=_make_boot_vol()) as mock_get,
        patch("app.api.compute.instances.cinder.create_volume_from_image") as mock_create_img,
        patch("app.api.compute.instances.cinder.create_empty_volume", return_value=_make_upper_vol()),
        patch("app.api.compute.instances.cinder.rename_volume", return_value=None),
        patch("app.api.compute.instances.nova.list_flavors", return_value=[_make_flavor()]),
        patch("app.api.compute.instances.nova.create_server", return_value=_make_server()),
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
        patch("app.api.compute.instances.cloudinit.generate_userdata", return_value=""),
    ):
        resp = await client.post("/api/v1/instances", json=_BASE_PAYLOAD)

    assert resp.status_code == 201
    mock_create_img.assert_not_called()
    mock_get.assert_called_once_with(mock_conn, "vol-boot-1")


@pytest.mark.asyncio
async def test_boot_from_volume_forces_delete_on_termination_false(client, mock_conn):
    """boot_volume_id 지정 시 delete_on_termination 이 반드시 False 로 전달된다."""
    mock_conn.compute.create_volume_attachment = MagicMock(return_value=None)

    with (
        patch("app.api.compute.instances.lib_svc.resolve_with_deps", return_value=[]),
        patch("app.api.compute.instances._prepare_dynamic_file_storage", return_value={}),
        patch("app.api.compute.instances.cinder.get_volume", return_value=_make_boot_vol()),
        patch("app.api.compute.instances.cinder.create_volume_from_image") as mock_create_img,
        patch("app.api.compute.instances.cinder.create_empty_volume", return_value=_make_upper_vol()),
        patch("app.api.compute.instances.cinder.rename_volume", return_value=None),
        patch("app.api.compute.instances.nova.list_flavors", return_value=[_make_flavor()]),
        patch("app.api.compute.instances.nova.create_server", return_value=_make_server()) as mock_create_srv,
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
        patch("app.api.compute.instances.cloudinit.generate_userdata", return_value=""),
    ):
        payload = {**_BASE_PAYLOAD, "delete_boot_volume_on_termination": True}
        resp = await client.post("/api/v1/instances", json=payload)

    assert resp.status_code == 201
    mock_create_img.assert_not_called()
    # 사용자가 True 를 요청해도 기존 볼륨이라 False 로 강제됨
    called_kwargs = mock_create_srv.call_args.kwargs
    assert called_kwargs["delete_boot_volume_on_termination"] is False


@pytest.mark.asyncio
async def test_boot_from_volume_image_id_and_boot_volume_id_both_returns_400(client, mock_conn):
    """image_id 와 boot_volume_id 를 동시에 지정하면 422(validation) 를 반환한다."""
    payload = {**_BASE_PAYLOAD, "image_id": "img-1"}
    resp = await client.post("/api/v1/instances", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_boot_from_volume_neither_returns_422(client, mock_conn):
    """image_id 도 boot_volume_id 도 없으면 422 를 반환한다."""
    payload = {"name": "test-vm", "flavor_id": "flavor-1"}
    resp = await client.post("/api/v1/instances", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_boot_from_volume_in_use_returns_400(client, mock_conn):
    """boot_volume_id 가 in-use 상태이면 400 을 반환한다."""
    with (
        patch("app.api.compute.instances.lib_svc.resolve_with_deps", return_value=[]),
        patch("app.api.compute.instances._prepare_dynamic_file_storage", return_value={}),
        patch("app.api.compute.instances.cinder.get_volume", return_value=_make_boot_vol(status="in-use")),
    ):
        resp = await client.post("/api/v1/instances", json=_BASE_PAYLOAD)

    assert resp.status_code == 400
    assert "available" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_boot_from_volume_non_bootable_returns_400(client, mock_conn):
    """bootable=False 볼륨은 루트 디스크로 사용할 수 없어 400 을 반환한다."""
    with (
        patch("app.api.compute.instances.lib_svc.resolve_with_deps", return_value=[]),
        patch("app.api.compute.instances._prepare_dynamic_file_storage", return_value={}),
        patch("app.api.compute.instances.cinder.get_volume", return_value=_make_boot_vol(bootable=False)),
    ):
        resp = await client.post("/api/v1/instances", json=_BASE_PAYLOAD)

    assert resp.status_code == 400
    assert "bootable" in resp.json()["detail"]
