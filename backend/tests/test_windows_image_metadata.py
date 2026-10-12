"""Authoritative Windows password metadata survives Glance and HTTP projections."""

from unittest.mock import MagicMock

import pytest
from openstack.image.v2.image import Image

from app.services import glance, image_verification
from tests.test_glance_get_image import _make_img

_METHOD = "nova-adminpass-configdrive"
_ACCOUNT = "Custom Administrator"
_METADATA = {"windows_initial_password_method": _METHOD, "os_admin_user": _ACCOUNT}


def _connection(image):
    conn = MagicMock()
    conn._afterglow_project_id = "proj-001"
    conn.image.images.side_effect = lambda **kwargs: [image] if kwargs.get("visibility") == "public" else []
    conn.image.get_image.return_value = image
    conn.image.update_image.return_value = image
    return conn


def _flat_image(**metadata):
    # Glance returns known and custom properties in one flat JSON object. The
    # SDK splits declared fields (os_type/os_admin_user) from unknown properties.
    return Image(
        id="flat-image-1",
        name="windows11:latest",
        status="active",
        min_disk=20,
        min_ram=0,
        disk_format="qcow2",
        container_format="bare",
        owner="proj-001",
        visibility="public",
        **metadata,
    )


@pytest.mark.parametrize("projection", ["list", "detail", "update"])
@pytest.mark.parametrize("os_type", ["windows", "linux"])
def test_glance_projects_flat_sdk_password_metadata(projection, os_type):
    image = _flat_image(os_type=os_type, **_METADATA)
    conn = _connection(image)
    if projection == "list":
        result = glance.list_images(conn)[0]
    elif projection == "detail":
        result = glance.get_image(conn, image.id)
    else:
        result = glance.update_image_metadata(conn, image.id, name="renamed:latest")
    assert result.os_type == os_type
    assert result.os_admin_user == _ACCOUNT
    assert result.windows_initial_password_method == _METHOD
    if projection == "detail":
        assert result.properties["os_type"] == os_type
        assert result.properties["os_admin_user"] == _ACCOUNT
        assert result.properties["windows_initial_password_method"] == _METHOD


@pytest.mark.parametrize("projection", ["list", "detail", "update"])
@pytest.mark.parametrize(
    "properties, expected",
    [
        ({"os_type": "windows", **_METADATA}, _METADATA),
        (
            {"windows_initial_password_method": "cloudbase-user-data", "os_admin_user": "Legacy Administrator"},
            {"windows_initial_password_method": "cloudbase-user-data", "os_admin_user": "Legacy Administrator"},
        ),
        (
            {"windows_initial_password_method": "future-method", "os_admin_user": " Account "},
            {"windows_initial_password_method": "future-method", "os_admin_user": " Account "},
        ),
        (
            {"windows_initial_password_method": "", "os_admin_user": ""},
            {"windows_initial_password_method": "", "os_admin_user": ""},
        ),
        (
            {"windows_initial_password_method": None, "os_admin_user": None},
            {"windows_initial_password_method": None, "os_admin_user": None},
        ),
        ({}, {"windows_initial_password_method": None, "os_admin_user": None}),
    ],
)
def test_glance_projects_authoritative_password_properties(projection, properties, expected):
    image = _make_img(props=properties)
    # Neither Windows-looking names nor a conflicting distro may invent metadata.
    image.name = "windows11:latest"
    conn = _connection(image)
    if projection == "list":
        result = glance.list_images(conn)[0]
    elif projection == "detail":
        result = glance.get_image(conn, image.id)
    else:
        result = glance.update_image_metadata(conn, image.id, name="renamed:latest")
    payload = result.model_dump(mode="json")
    assert {key: payload[key] for key in expected} == expected
    if projection == "detail":
        assert result.properties.get("windows_initial_password_method") == properties.get(
            "windows_initial_password_method"
        )
        assert result.properties.get("os_admin_user") == properties.get("os_admin_user")


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/api/v1/images", "/api/v1/admin/images"])
@pytest.mark.parametrize("operation", ["detail", "update", "properties"])
async def test_image_http_detail_and_updates_expose_authoritative_password_metadata(
    admin_client, mock_conn, monkeypatch, prefix, operation
):
    image = _make_img(props={"os_type": "windows", **_METADATA})
    image.owner = mock_conn._afterglow_project_id
    mock_conn.image.get_image.return_value = image
    mock_conn.image.update_image.return_value = image

    def unavailable_factory():
        raise image_verification.VerificationUnavailable("Isolated verification store")

    monkeypatch.setattr(image_verification, "_factory", unavailable_factory)
    url = f"{prefix}/{image.id}"
    if operation == "detail":
        response = await admin_client.get(url)
    elif operation == "update":
        # A changed authoritative account in the SDK response must be projected,
        # rather than reusing metadata from an earlier list/cache snapshot.
        image.properties["os_admin_user"] = "Renamed Administrator"
        response = await admin_client.patch(url, json={"name": "windows11:latest"})
    else:

        def apply_property_patch(path, *, json, headers, **_kwargs):
            for patch in json:
                key = patch["path"][1:]
                if patch["op"] == "remove":
                    image.properties.pop(key, None)
                else:
                    image.properties[key] = patch["value"]

        mock_conn.image.patch.side_effect = apply_property_patch
        response = await admin_client.patch(
            f"{url}/properties",
            json={"set": {"os_admin_user": "Patched Administrator"}, "remove": ["windows_initial_password_method"]},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["windows_initial_password_method"] == image.properties.get("windows_initial_password_method")
    assert payload["os_admin_user"] == image.properties["os_admin_user"]
    assert payload["verification_status"] == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("properties", [{"os_type": "windows", **_METADATA}, {}])
async def test_image_http_list_and_cached_list_preserve_password_metadata(client, mock_conn, monkeypatch, properties):
    image = _make_img(props=properties)
    mock_conn.image.images.side_effect = lambda **kwargs: [image] if kwargs.get("visibility") == "public" else []

    def unavailable_factory():
        raise image_verification.VerificationUnavailable("Isolated verification store")

    monkeypatch.setattr(image_verification, "_factory", unavailable_factory)
    monkeypatch.setattr("app.api.compute.images.ttl_static", lambda: 300)
    for _ in range(2):
        response = await client.get("/api/v1/images?cache=true")
        assert response.status_code == 200
        payload = response.json()[0]
        assert payload["windows_initial_password_method"] == properties.get("windows_initial_password_method")
        assert payload["os_admin_user"] == properties.get("os_admin_user")
        assert payload["verification_status"] == "unavailable"
    # One uncached pass across the four Glance visibility groups.
    assert mock_conn.image.images.call_count == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/api/v1/images", "/api/v1/admin/images"])
@pytest.mark.parametrize("operation", ["detail", "update"])
async def test_image_http_projects_flat_sdk_password_metadata(admin_client, mock_conn, monkeypatch, prefix, operation):
    image = _flat_image(os_type="windows", **_METADATA)
    mock_conn.image.get_image.return_value = image
    mock_conn.image.update_image.return_value = image

    def unavailable_factory():
        raise image_verification.VerificationUnavailable("Isolated verification store")

    monkeypatch.setattr(image_verification, "_factory", unavailable_factory)
    url = f"{prefix}/{image.id}"
    response = (
        await admin_client.get(url)
        if operation == "detail"
        else await admin_client.patch(url, json={"name": "renamed:latest"})
    )
    assert response.status_code == 200
    assert response.json()["os_type"] == "windows"
    assert response.json()["os_admin_user"] == _ACCOUNT
    assert response.json()["windows_initial_password_method"] == _METHOD


@pytest.mark.asyncio
async def test_image_http_list_projects_flat_sdk_password_metadata(client, mock_conn, monkeypatch):
    image = _flat_image(os_type="windows", **_METADATA)
    mock_conn.image.images.side_effect = lambda **kwargs: [image] if kwargs.get("visibility") == "public" else []

    def unavailable_factory():
        raise image_verification.VerificationUnavailable("Isolated verification store")

    monkeypatch.setattr(image_verification, "_factory", unavailable_factory)
    response = await client.get("/api/v1/images")
    assert response.status_code == 200
    assert response.json()[0]["os_type"] == "windows"
    assert response.json()[0]["os_admin_user"] == _ACCOUNT
    assert response.json()[0]["windows_initial_password_method"] == _METHOD


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/api/v1/images", "/api/v1/admin/images"])
async def test_saved_windows_properties_refresh_warm_owner_and_shared_catalogs(
    admin_client, mock_conn, monkeypatch, prefix
):
    owner = mock_conn._afterglow_project_id
    legacy = _flat_image(
        os_type="windows",
        windows_initial_password_method="cloudbase-user-data",
        os_admin_user="Legacy Administrator",
    )
    legacy.owner = owner
    provider = {"image": legacy}
    mock_conn.image.get_image.side_effect = lambda *_args, **_kwargs: provider["image"]
    mock_conn.image.images.side_effect = lambda **kwargs: (
        [provider["image"]] if kwargs.get("visibility") == "public" else []
    )
    monkeypatch.setattr("app.api.compute.images.ttl_static", lambda: 300)

    def unavailable_factory():
        raise image_verification.VerificationUnavailable("Isolated verification store")

    monkeypatch.setattr(image_verification, "_factory", unavailable_factory)
    projects = [owner, "shared-image-consumer"]
    for project in projects:
        mock_conn._afterglow_project_id = project
        response = await admin_client.get("/api/v1/images?cache=true")
        assert response.status_code == 200
        assert response.json()[0]["windows_initial_password_method"] == "cloudbase-user-data"
    # Both consumers now use real cached serialized projections, not fresh SDK
    # responses. Saving must make a subsequent wizard/catalog see the new method.
    mock_conn.image.images.reset_mock()
    for project in projects:
        mock_conn._afterglow_project_id = project
        response = await admin_client.get("/api/v1/images?cache=true")
        assert response.json()[0]["windows_initial_password_method"] == "cloudbase-user-data"
    mock_conn.image.images.assert_not_called()

    def updated_provider(_path, *, json, headers, **_kwargs):
        updated = _flat_image(os_type="windows", **_METADATA)
        updated.owner = owner
        provider["image"] = updated

    mock_conn.image.patch.side_effect = updated_provider
    mock_conn._afterglow_project_id = owner
    response = await admin_client.patch(
        f"{prefix}/{legacy.id}/properties",
        json={"set": {"os_type": "windows", **_METADATA}, "remove": []},
    )
    assert response.status_code == 200
    assert response.json()["windows_initial_password_method"] == _METHOD
    for project in projects:
        mock_conn._afterglow_project_id = project
        response = await admin_client.get("/api/v1/images?cache=true")
        assert response.status_code == 200
        assert response.json()[0]["windows_initial_password_method"] == _METHOD
        assert response.json()[0]["os_admin_user"] == _ACCOUNT
