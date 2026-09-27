"""glance.get_image — properties 완전 노출 단위 테스트."""

from unittest.mock import MagicMock

from openstack.image.v2.image import Image

from app.services.glance import get_image


def _make_img(
    *,
    props: dict | None = None,
    os_distro: str | None = "ubuntu",
    os_hash_algo: str | None = "sha512",
    os_hash_value: str | None = "abc123",
    direct_url: str | None = "rbd://pool/vol",
    is_hidden: bool | None = False,
) -> Image:
    img = Image()
    img.id = "img-test-001"
    img.name = "test-image"
    img.status = "active"
    img.size = 1073741824
    img.min_disk = 10
    img.min_ram = 0
    img.disk_format = "qcow2"
    img.container_format = "bare"
    img.virtual_size = None
    img.created_at = "2026-01-01T00:00:00"
    img.updated_at = None
    img.checksum = None
    img.tags = []
    img.properties = dict(props or {})
    img.os_distro = os_distro
    img.hash_algo = os_hash_algo
    img.hash_value = os_hash_value
    img.direct_url = direct_url
    img.is_hidden = is_hidden
    img.is_protected = False
    img.owner = "proj-001"
    img.project_id = "proj-001"
    img.visibility = "public"
    return img


def _make_conn(img: Image) -> MagicMock:
    conn = MagicMock()
    conn.image.get_image.return_value = img
    return conn


def test_all_sdk_fields_appear_in_properties():
    """SDK 별도 필드(os_distro, os_hash_algo, os_hash_value, direct_url, os_hidden)가 properties 에 포함되어야 한다."""
    img = _make_img(props={"hw_qemu_guest_agent": "yes", "custom_key": "v"})
    result = get_image(_make_conn(img), img.id)

    assert "hw_qemu_guest_agent" in result.properties
    assert "custom_key" in result.properties
    assert "os_distro" in result.properties, "os_distro 가 properties 에 없음"
    assert "os_hash_algo" in result.properties, "os_hash_algo 가 properties 에 없음"
    assert "os_hash_value" in result.properties, "os_hash_value 가 properties 에 없음"
    assert "direct_url" in result.properties, "direct_url 이 properties 에 없음"
    assert "os_hidden" in result.properties, "os_hidden 이 properties 에 없음"


def test_separate_fields_still_populated():
    """ImageDetail 의 별도 필드(os_distro, os_hash_algo, os_hash_value, direct_url)도 여전히 채워져야 한다 (회귀 방지)."""
    img = _make_img()
    result = get_image(_make_conn(img), img.id)

    assert result.os_distro == "ubuntu"
    assert result.os_hash_algo == "sha512"
    assert result.os_hash_value == "abc123"
    assert result.direct_url == "rbd://pool/vol"
    assert result.name == "test-image:latest"
    assert result.repository == "test-image"
    assert result.tag == "latest"


def test_os_hidden_is_string_false():
    """is_hidden=False 이면 properties['os_hidden'] == 'False' (문자열)."""
    img = _make_img(is_hidden=False)
    result = get_image(_make_conn(img), img.id)
    assert result.properties["os_hidden"] == "False"


def test_os_hidden_is_string_true():
    """is_hidden=True 이면 properties['os_hidden'] == 'True' (문자열)."""
    img = _make_img(is_hidden=True)
    result = get_image(_make_conn(img), img.id)
    assert result.properties["os_hidden"] == "True"


def test_os_hidden_none_not_added():
    """SDK 가 is_hidden=None 을 반환하면 os_hidden 키가 properties 에 추가되지 않아야 한다."""
    img = _make_img(is_hidden=None)
    result = get_image(_make_conn(img), img.id)
    assert "os_hidden" not in result.properties


def test_sdk_field_does_not_overwrite_existing_property():
    """properties 에 이미 os_distro 가 있으면 SDK 값으로 덮어쓰지 않는다."""
    img = _make_img(props={"os_distro": "centos"}, os_distro="ubuntu")
    result = get_image(_make_conn(img), img.id)
    assert result.properties["os_distro"] == "centos"


def test_none_sdk_fields_not_added():
    """SDK 필드가 None 이면 properties 에 추가되지 않아야 한다."""
    img = _make_img(os_hash_algo=None, os_hash_value=None, direct_url=None, os_distro=None, is_hidden=None)
    img.properties = {}
    result = get_image(_make_conn(img), img.id)
    assert "os_hash_algo" not in result.properties
    assert "os_hash_value" not in result.properties
    assert "direct_url" not in result.properties
    assert "os_hidden" not in result.properties
