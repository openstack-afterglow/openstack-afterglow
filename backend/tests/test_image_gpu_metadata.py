"""GPU recommendations receive explicit Glance metadata through writable HTTP contracts."""

from io import BytesIO
from unittest.mock import MagicMock

import pytest
from openstack.image.v2.image import Image

from app.services import glance, image_verification
from tests.test_glance_get_image import _make_img


@pytest.fixture(autouse=True)
def unavailable_verification(monkeypatch):
    def unavailable_factory():
        raise image_verification.VerificationUnavailable("Isolated verification store")

    monkeypatch.setattr(image_verification, "_factory", unavailable_factory)


def _connection(image):
    conn = MagicMock()
    conn._afterglow_project_id = image.owner
    conn.image.images.side_effect = lambda **kwargs: [image] if kwargs.get("visibility") == "public" else []
    conn.image.get_image.return_value = image
    conn.image.update_image.return_value = image
    return conn


@pytest.mark.parametrize("projection", ["list", "detail", "update"])
@pytest.mark.parametrize("flat", [False, True])
@pytest.mark.parametrize(
    "metadata",
    [
        {"gpu_vendor": "nvidia", "gpu_driver": "nvidia"},
        {"gpu_vendor": "future-vendor", "gpu_driver": "future-driver"},
        {"gpu_vendor": "", "gpu_driver": "none"},
        {},
    ],
)
def test_glance_gpu_metadata_projection(projection, flat, metadata):
    if flat:
        image = Image(
            id="gpu-image",
            name="nvidia-driver:latest",
            status="active",
            owner="project-1",
            min_disk=0,
            min_ram=0,
            disk_format="qcow2",
            container_format="bare",
            **metadata,
        )
    else:
        image = _make_img(props=metadata)
        image.name = "nvidia-driver:latest"
    conn = _connection(image)
    if projection == "list":
        result = glance.list_images(conn)[0]
    elif projection == "detail":
        result = glance.get_image(conn, image.id)
    else:
        result = glance.update_image_metadata(conn, image.id)
    assert result.gpu_vendor == metadata.get("gpu_vendor")
    assert result.gpu_driver == metadata.get("gpu_driver")


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/api/v1/images", "/api/v1/admin/images"])
async def test_image_gpu_typed_update_and_detail(admin_client, mock_conn, prefix):
    image = _make_img()
    image.owner = mock_conn._afterglow_project_id
    mock_conn.image.get_image.return_value = image

    def apply_update(path, *, json, **_kwargs):
        assert path == f"/images/{image.id}"
        for operation in json:
            image.properties[operation["path"][1:]] = operation["value"]

    mock_conn.image.patch.side_effect = apply_update
    url = f"{prefix}/{image.id}"
    for metadata in [
        {"gpu_vendor": "nvidia", "gpu_driver": "nvidia-grid"},
        {"gpu_vendor": "", "gpu_driver": "none"},
    ]:
        response = await admin_client.patch(url, json=metadata)
        assert response.status_code == 200
        assert {key: response.json()[key] for key in metadata} == metadata
        assert {item["path"][1:]: item["value"] for item in mock_conn.image.patch.call_args.kwargs["json"]} == metadata
        mock_conn.image.update_image.assert_not_called()
        detail = await admin_client.get(url)
        assert detail.status_code == 200
        assert {key: detail.json()[key] for key in metadata} == metadata


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/api/v1/images", "/api/v1/admin/images"])
@pytest.mark.parametrize("metadata", [{"gpu_vendor": "unknown"}, {"gpu_driver": "cuda"}])
async def test_image_gpu_typed_update_rejects_unsupported_declarations(admin_client, mock_conn, prefix, metadata):
    response = await admin_client.patch(f"{prefix}/image-1", json=metadata)
    assert response.status_code == 422
    mock_conn.image.update_image.assert_not_called()
    mock_conn.image.patch.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/api/v1/images", "/api/v1/admin/images"])
async def test_gpu_metadata_updates_refresh_other_project_cached_consumer_list(
    admin_client, mock_conn, monkeypatch, prefix
):
    image = _make_img()
    image.owner = mock_conn._afterglow_project_id
    mock_conn.image.images.side_effect = lambda **kwargs: [image] if kwargs.get("visibility") == "public" else []
    mock_conn.image.get_image.return_value = image
    monkeypatch.setattr("app.api.compute.images.ttl_static", lambda: 300)
    owner_project = mock_conn._afterglow_project_id
    mock_conn._afterglow_project_id = "other-project-cache"

    before = await admin_client.get("/api/v1/images?cache=true")
    assert before.status_code == 200
    assert before.json()[0]["gpu_driver"] is None
    mock_conn._afterglow_project_id = owner_project

    def apply_update(_path, *, json, **_kwargs):
        for operation in json:
            image.properties[operation["path"][1:]] = operation["value"]

    mock_conn.image.patch.side_effect = apply_update
    updated = await admin_client.patch(
        f"{prefix}/{image.id}",
        json={"gpu_vendor": "nvidia", "gpu_driver": "nvidia"},
    )
    assert updated.status_code == 200
    mock_conn._afterglow_project_id = "other-project-cache"
    after = await admin_client.get("/api/v1/images?cache=true")
    assert after.status_code == 200
    assert after.json()[0]["gpu_vendor"] == "nvidia"
    assert after.json()[0]["gpu_driver"] == "nvidia"


@pytest.mark.asyncio
async def test_image_gpu_upload_accepts_typed_metadata_and_preserves_it(client, mock_conn):
    metadata = {"gpu_vendor": "nvidia", "gpu_driver": "nvidia"}
    image = _make_img(props=metadata)
    mock_conn.image.create_image.return_value = image
    response = await client.post(
        "/api/v1/images",
        files={
            "name": (None, "ubuntu-gpu:latest"),
            "gpu_vendor": (None, metadata["gpu_vendor"]),
            "gpu_driver": (None, metadata["gpu_driver"]),
            "file": ("gpu.raw", BytesIO(b"image"), "application/octet-stream"),
        },
    )
    assert response.status_code == 201
    assert {key: response.json()[key] for key in metadata} == metadata
    kwargs = mock_conn.image.create_image.call_args.kwargs
    assert {key: kwargs[key] for key in metadata} == metadata


@pytest.mark.asyncio
async def test_image_gpu_upload_rejects_unknown_driver_before_provider_call(client, mock_conn):
    response = await client.post(
        "/api/v1/images",
        files={
            "name": (None, "ubuntu-gpu:latest"),
            "gpu_driver": (None, "cuda"),
            "file": ("gpu.raw", BytesIO(b"image"), "application/octet-stream"),
        },
    )
    assert response.status_code == 422
    mock_conn.image.create_image.assert_not_called()


@pytest.mark.asyncio
async def test_admin_image_list_exposes_declared_gpu_metadata(admin_client, mock_conn):
    metadata = {"gpu_vendor": "amd", "gpu_driver": "amdgpu"}
    image = _make_img(props=metadata)
    mock_conn.image.images.return_value = [image]
    response = await admin_client.get("/api/v1/admin/images")
    assert response.status_code == 200
    assert response.json()["items"][0]["gpu_vendor"] == "amd"
    assert response.json()["items"][0]["gpu_driver"] == "amdgpu"
