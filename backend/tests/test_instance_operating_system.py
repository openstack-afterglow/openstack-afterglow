"""Reader-safe OS metadata for image and volume-backed instance details."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from openstack.block_storage.v3.volume import Volume
from openstack.compute.v2.server import Server
from openstack.image.v2.image import Image

from app.services import nova


def _server(*, image_backed=True, root_device=None):
    return Server(
        id="server-os",
        name="Windows-looking-name-with-no-authority",
        status="SHUTOFF",
        image={"id": "image-os"} if image_backed else {},
        flavor={"id": "flavor-os", "original_name": "small"},
        addresses={},
        metadata={},
        tenant_id="test-project-123",
        user_id="another-creator",
        root_device_name=root_device,
    )


@pytest.mark.parametrize("flat", [False, True])
@pytest.mark.parametrize("os_type, expected", [(" Windows ", "windows"), ("LINUX", "linux"), (None, None)])
def test_image_os_comes_from_metadata_not_display_name(mock_conn, flat, os_type, expected):
    mock_conn.compute.get_server.return_value = _server()
    mock_conn.image.get_image.return_value = Image(
        id="image-os", name="Windows:latest", **({"os_type": os_type} if flat else {"properties": {"os_type": os_type}})
    )
    assert nova.get_server_image_meta(mock_conn, "server-os")["os_type"] == expected


@pytest.mark.parametrize(
    "root_device, data_bootable, expected",
    [("/dev/sda", True, "windows"), (None, False, "windows"), (None, True, None)],
)
def test_volume_os_uses_root_or_unique_bootable_metadata(mock_conn, root_device, data_bootable, expected):
    mock_conn.compute.get_server.return_value = _server(image_backed=False, root_device=root_device)
    mock_conn.compute.volume_attachments.return_value = [
        SimpleNamespace(device="/dev/vda", volume_id="data-os"),
        SimpleNamespace(device="/dev/sda", volume_id="root-os"),
    ]
    volumes = {
        "data-os": Volume(
            id="data-os", bootable="true" if data_bootable else "false", volume_image_metadata={"os_type": "linux"}
        ),
        "root-os": Volume(id="root-os", bootable="true", volume_image_metadata={"os_type": " Windows "}),
    }
    mock_conn.block_storage.get_volume.side_effect = volumes.__getitem__
    assert nova.get_server_image_meta(mock_conn, "server-os")["os_type"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("image_backed", [False, True])
async def test_instance_detail_projects_os_for_other_creator_readers(non_admin_client, mock_conn, image_backed):
    from app.api.deps import get_token_info
    from app.main import app
    from tests.conftest import make_token_info

    async def reader():
        return make_token_info(roles=["reader"])

    app.dependency_overrides[get_token_info] = reader
    mock_conn.compute.get_server.return_value = _server(image_backed=image_backed, root_device="/dev/sda")
    mock_conn.image.get_image.return_value = Image(id="image-os", name="Opaque display name", os_type="windows")
    mock_conn.compute.volume_attachments.return_value = [SimpleNamespace(device="/dev/sda", volume_id="root-os")]
    mock_conn.block_storage.get_volume.return_value = Volume(
        id="root-os", bootable="true", volume_image_metadata={"os_type": "windows"}
    )
    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[]),
        patch("app.api.compute.instances.glance.list_images", return_value=[]),
    ):
        response = await non_admin_client.get("/api/v1/instances/server-os")
    assert response.status_code == 200
    assert response.json()["os_type"] == "windows"
    password_capability = await non_admin_client.get("/api/v1/instances/server-os/admin-password/precheck")
    assert password_capability.status_code == 403


@pytest.mark.asyncio
async def test_instance_detail_unknown_os_does_not_infer_windows(non_admin_client, mock_conn):
    mock_conn.compute.get_server.return_value = _server()
    mock_conn.image.get_image.return_value = Image(id="image-os", name="Windows:latest")
    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[]),
        patch("app.api.compute.instances.glance.list_images", return_value=[]),
    ):
        response = await non_admin_client.get("/api/v1/instances/server-os")
    assert response.status_code == 200
    assert response.json()["os_type"] is None


@pytest.mark.asyncio
async def test_optional_os_lookup_failure_does_not_hide_readable_instance(non_admin_client, mock_conn):
    mock_conn.compute.get_server.side_effect = [_server(), RuntimeError("Metadata lookup unavailable")]
    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[]),
        patch("app.api.compute.instances.glance.list_images", return_value=[]),
    ):
        response = await non_admin_client.get("/api/v1/instances/server-os")
    assert response.status_code == 200
    assert response.json()["id"] == "server-os"
    assert response.json()["os_type"] is None
