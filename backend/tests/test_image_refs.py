"""Docker-style Glance image reference behavior."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.glance import create_image, list_images, update_image_metadata
from app.services.image_refs import ImageReferenceError, image_reference_fields, normalize_image_reference


def test_missing_tag_defaults_to_latest():
    assert normalize_image_reference("ubuntu") == "ubuntu:latest"
    assert image_reference_fields("ubuntu") == ("ubuntu:latest", "ubuntu", "latest")


def test_explicit_tag_is_preserved():
    assert image_reference_fields("ubuntu:24.04") == ("ubuntu:24.04", "ubuntu", "24.04")


def test_registry_port_is_not_treated_as_tag():
    assert image_reference_fields("registry.example:5000/ubuntu") == (
        "registry.example:5000/ubuntu:latest",
        "registry.example:5000/ubuntu",
        "latest",
    )


@pytest.mark.parametrize(
    "value",
    ["", "ubuntu:", "ubuntu:bad tag", "ubuntu@sha256:abc", "ubuntu:v1:v2", "repo/path:bad:v2"],
)
def test_invalid_new_reference_is_rejected(value):
    with pytest.raises(ImageReferenceError):
        normalize_image_reference(value)


def _image(name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"id-{name}",
        name=name,
        status="active",
        properties={},
        size=1,
        min_disk=1,
        min_ram=0,
        disk_format="qcow2",
        created_at=None,
        owner="project-1",
        project_id="project-1",
        visibility="private",
        os_distro="ubuntu",
    )


def test_list_exposes_same_repository_versions_as_distinct_tagged_images():
    conn = MagicMock()
    conn._afterglow_project_id = "project-1"
    conn.image.images.side_effect = [[], [], [_image("ubuntu:22.04"), _image("ubuntu:24.04")]]

    result = list_images(conn, "project-1")

    assert [(img.repository, img.tag) for img in result] == [("ubuntu", "22.04"), ("ubuntu", "24.04")]
    assert [img.name for img in result] == ["ubuntu:22.04", "ubuntu:24.04"]


def test_create_and_rename_store_canonical_name():
    conn = MagicMock()
    created = _image("ubuntu:latest")
    conn.image.create_image.return_value = created
    create_image(conn, name="ubuntu", disk_format="qcow2", data=object())
    assert conn.image.create_image.call_args.kwargs["name"] == "ubuntu:latest"

    updated = _image("ubuntu:24.04")
    conn.image.update_image.return_value = updated
    result = update_image_metadata(conn, "image-1", name="ubuntu:24.04")
    assert conn.image.update_image.call_args.kwargs["name"] == "ubuntu:24.04"
    assert (result.repository, result.tag) == ("ubuntu", "24.04")


def test_metadata_update_keeps_protected_image_state():
    conn = MagicMock()
    updated = _image("ubuntu:24.04")
    updated.is_protected = True
    conn.image.update_image.return_value = updated

    result = update_image_metadata(conn, "image-1", name="ubuntu:24.04")

    assert result.protected is True


def test_image_list_coerces_missing_protection_state_to_false():
    conn = MagicMock()
    conn._afterglow_project_id = "project-1"
    image = _image("ubuntu:24.04")
    image.is_protected = None
    conn.image.images.side_effect = [[], [], [], [image]]

    result = list_images(conn, "project-1")

    assert [(entry.id, entry.protected) for entry in result] == [(image.id, False)]
