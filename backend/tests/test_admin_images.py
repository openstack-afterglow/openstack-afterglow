"""admin_images.py 엔드포인트 단위 테스트."""

from types import SimpleNamespace

import pytest

from app.models.compute import ImageInfo


def _make_image(img_id: str, name: str, **extra) -> SimpleNamespace:
    base = {
        "id": img_id,
        "name": name,
        "status": "active",
        "size": 0,
        "min_disk": 0,
        "min_ram": 0,
        "disk_format": "raw",
        "os_distro": None,
        "visibility": "public",
        "owner": "owner-1",
        "created_at": None,
        "is_protected": False,
    }
    base.update(extra)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_list_admin_images_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/images")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_admin_images_allowed(admin_client, mock_conn):
    mock_conn.image.images.return_value = iter([])
    resp = await admin_client.get("/api/v1/admin/images")
    assert resp.status_code != 403


@pytest.mark.asyncio
async def test_list_admin_images_search_substring_case_insensitive(admin_client, mock_conn):
    """search='u'는 ubuntu/Windows-Update/centos 중 'u' 포함 이미지를 모두 반환해야 함."""
    images = [
        _make_image("1", "ubuntu-24.04"),
        _make_image("2", "Windows-Update-2024"),
        _make_image("3", "centos-9"),
        _make_image("4", "fedora-39"),
    ]
    mock_conn.image.images.return_value = iter(images)
    resp = await admin_client.get("/api/v1/admin/images?search=u")
    assert resp.status_code == 200
    body = resp.json()
    names = {item["name"] for item in body["items"]}
    assert names == {"ubuntu-24.04:latest", "Windows-Update-2024:latest"}


@pytest.mark.asyncio
async def test_list_admin_images_coerces_unknown_protection_to_false(admin_client, mock_conn):
    mock_conn.image.images.return_value = iter([_make_image("img-1", "ubuntu:24.04", is_protected=None)])

    resp = await admin_client.get("/api/v1/admin/images")

    assert resp.status_code == 200
    assert resp.json()["items"][0]["protected"] is False


@pytest.mark.asyncio
async def test_list_admin_images_search_no_match(admin_client, mock_conn):
    images = [
        _make_image("1", "ubuntu-24.04"),
        _make_image("2", "centos-9"),
    ]
    mock_conn.image.images.return_value = iter(images)
    resp = await admin_client.get("/api/v1/admin/images?search=zzznoexist")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["count"] == 0
    assert body["next_marker"] is None


@pytest.mark.asyncio
async def test_list_admin_images_search_pagination_with_marker(admin_client, mock_conn):
    """검색 결과가 limit 보다 많을 때 marker 기반 페이지네이션."""
    images = [_make_image(f"id-{i}", f"ubuntu-{i}") for i in range(5)]
    mock_conn.image.images.return_value = iter(images)
    resp = await admin_client.get("/api/v1/admin/images?search=ubuntu&limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert [item["id"] for item in body["items"]] == ["id-0", "id-1"]
    assert body["next_marker"] == "id-1"

    # 두 번째 페이지
    mock_conn.image.images.return_value = iter(images)
    resp2 = await admin_client.get("/api/v1/admin/images?search=ubuntu&limit=2&marker=id-1")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert [item["id"] for item in body2["items"]] == ["id-2", "id-3"]
    assert body2["next_marker"] == "id-3"


@pytest.mark.asyncio
async def test_list_admin_images_search_does_not_pass_name_to_glance(admin_client, mock_conn):
    """search 시 Glance에 name= 정확매칭 인자를 넘기면 안 된다 (substring은 클라이언트 필터)."""
    images = [_make_image("1", "ubuntu-24.04")]
    mock_conn.image.images.return_value = iter(images)
    resp = await admin_client.get("/api/v1/admin/images?search=ub")
    assert resp.status_code == 200
    # Glance 호출 인자 검사: name 키가 없어야 함
    _, called_kwargs = mock_conn.image.images.call_args
    assert "name" not in called_kwargs


@pytest.mark.asyncio
async def test_list_admin_images_visibility_passed_to_glance(admin_client, mock_conn):
    """?visibility=public 파라미터가 Glance 호출에 전달되어야 한다."""
    images = [_make_image("1", "ubuntu", visibility="public")]
    mock_conn.image.images.return_value = iter(images)
    resp = await admin_client.get("/api/v1/admin/images?visibility=public")
    assert resp.status_code == 200
    _, called_kwargs = mock_conn.image.images.call_args
    assert called_kwargs.get("visibility") == "public"


@pytest.mark.asyncio
async def test_list_admin_images_no_visibility_no_filter(admin_client, mock_conn):
    """?visibility 없으면 Glance에 visibility 인자 미전달 (모든 이미지 반환)."""
    images = [
        _make_image("1", "ubuntu", visibility="public"),
        _make_image("2", "rocky", visibility="private"),
    ]
    mock_conn.image.images.return_value = iter(images)
    resp = await admin_client.get("/api/v1/admin/images?search=ub")
    assert resp.status_code == 200
    _, called_kwargs = mock_conn.image.images.call_args
    assert "visibility" not in called_kwargs


@pytest.mark.asyncio
async def test_list_admin_images_preserves_protected_and_duplicate_uploads(admin_client, mock_conn):
    images = [
        _make_image("older", "ubuntu:latest", is_protected=True, hash_algo="sha512", hash_value="a" * 128),
        _make_image("newer", "ubuntu:latest", is_protected=False, hash_algo="sha512", hash_value="a" * 128),
    ]
    mock_conn.image.images.return_value = iter(images)

    resp = await admin_client.get("/api/v1/admin/images")

    assert resp.status_code == 200
    assert [(item["id"], item["protected"], item["os_hash_value"]) for item in resp.json()["items"]] == [
        ("older", True, "a" * 128),
        ("newer", False, "a" * 128),
    ]


@pytest.mark.asyncio
async def test_get_admin_image_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/images/img-1")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_admin_image_requires_admin(non_admin_client):
    resp = await non_admin_client.patch("/api/v1/admin/images/img-1", json={"name": "new"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_admin_image_normalizes_latest_and_explicit_tag(admin_client):
    from unittest.mock import patch

    updated = ImageInfo.model_validate(vars(_make_image("img-1", "ubuntu:24.04")))
    with patch("app.api.identity.admin_images.glance.update_image_metadata", return_value=updated) as update:
        resp = await admin_client.patch("/api/v1/admin/images/img-1", json={"name": "ubuntu:24.04"})
    assert resp.status_code == 200
    assert update.call_args.args[2] == "ubuntu:24.04"

    with patch(
        "app.api.identity.admin_images.glance.update_image_metadata",
        return_value=ImageInfo.model_validate(vars(_make_image("img-1", "ubuntu:latest"))),
    ) as update:
        resp = await admin_client.patch("/api/v1/admin/images/img-1", json={"name": "ubuntu"})
    assert resp.status_code == 200
    assert update.call_args.args[2] == "ubuntu:latest"


@pytest.mark.asyncio
async def test_patch_admin_image_rejects_invalid_reference(admin_client):
    resp = await admin_client.patch("/api/v1/admin/images/img-1", json={"name": "Ubuntu 24.04"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_admin_image_requires_admin(non_admin_client):
    resp = await non_admin_client.delete("/api/v1/admin/images/img-1")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_deactivate_image_requires_admin(non_admin_client):
    resp = await non_admin_client.post("/api/v1/admin/images/img-1/deactivate")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reactivate_image_requires_admin(non_admin_client):
    resp = await non_admin_client.post("/api/v1/admin/images/img-1/reactivate")
    assert resp.status_code == 403
