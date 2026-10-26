"""admin_images.py 엔드포인트 단위 테스트."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openstack.exceptions import ResourceNotFound
from openstack.image.v2.member import Member

from app.api.deps import get_os_conn
from app.main import app
from tests.test_glance_get_image import _make_img


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


@pytest.fixture
def image_transports(admin_client, mock_conn, monkeypatch):
    """Personal caller transport cannot read the foreign private image; executor can."""
    image = _make_img(props={"os_type": "windows", "support_ticket": "preserve"})
    image.owner = image.project_id = "foreign-image-project"
    image.visibility = "private"
    mock_conn.image.get_image.return_value = image
    mock_conn.session.auth.get_access.return_value.project_id = "configured-admin-project"
    caller = MagicMock()
    caller._afterglow_project_id = "test-project-123"
    caller.image.get_image.side_effect = ResourceNotFound("Private image is not visible to caller")

    async def caller_transport():
        yield caller

    monkeypatch.setitem(app.dependency_overrides, get_os_conn, caller_transport)
    monkeypatch.setattr(
        "app.api.identity.admin_images.image_verification.enrich", AsyncMock(side_effect=lambda rows: rows)
    )
    monkeypatch.setattr("app.api.identity.admin_images.invalidate", AsyncMock())
    monkeypatch.setattr("app.api.identity.admin_images.image_verification.remove_deleted_image", AsyncMock())
    return SimpleNamespace(image=image, executor=mock_conn, caller=caller)


@pytest.mark.asyncio
async def test_admin_private_image_detail_uses_executor_without_changing_consumer_scope(admin_client, image_transports):
    state = image_transports
    url = f"/api/v1/admin/images/{state.image.id}"
    response = await admin_client.get(url)
    assert response.status_code == 200
    assert response.json()["owner"] == "foreign-image-project"
    assert response.json()["visibility"] == "private"
    state.executor.image.get_image.assert_called_once_with(state.image.id)
    state.caller.image.get_image.assert_not_called()
    consumer = await admin_client.get(f"/api/v1/images/{state.image.id}")
    assert consumer.status_code == 404
    state.caller.image.get_image.assert_called_once_with(state.image.id)
    assert state.executor._afterglow_project_id == "test-project-123"


@pytest.mark.asyncio
async def test_admin_foreign_image_existing_visibility_properties_delete_actions(admin_client, image_transports):
    state = image_transports
    image = state.image

    def update(image_id, **values):
        assert image_id == image.id
        for key, value in values.items():
            setattr(image, key, value)
        return image

    def patch_properties(path, *, json, **kwargs):
        assert path == f"/images/{image.id}"
        assert kwargs["raise_exc"] is True
        for operation in json:
            image.properties[operation["path"][1:]] = operation["value"]

    state.executor.image.update_image.side_effect = update
    state.executor.image.patch.side_effect = patch_properties
    url = f"/api/v1/admin/images/{image.id}"
    visibility = await admin_client.patch(url, json={"visibility": "shared"})
    assert visibility.status_code == 200
    assert visibility.json()["visibility"] == "shared"
    state.executor.image.update_image.assert_called_once_with(image.id, visibility="shared")
    metadata = {
        "os_type": "windows",
        "os_admin_user": "PlatformAdmin",
        "windows_initial_password_method": "nova-adminpass-configdrive",
    }
    properties = await admin_client.patch(f"{url}/properties", json={"set": metadata, "remove": []})
    assert properties.status_code == 200
    assert properties.json()["os_admin_user"] == "PlatformAdmin"
    assert properties.json()["properties"]["support_ticket"] == "preserve"
    assert properties.json()["owner"] == "foreign-image-project"
    assert (await admin_client.delete(url)).status_code == 204
    state.executor.image.delete_image.assert_called_once_with(image.id, ignore_missing=False)
    state.caller.image.get_image.assert_not_called()
    state.caller.image.update_image.assert_not_called()
    state.caller.image.patch.assert_not_called()
    state.caller.image.delete_image.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,suffix,body",
    [
        ("GET", "/members", None),
        ("POST", "/members", {"member": "shared-project"}),
        ("DELETE", "/members/shared-project", None),
        ("PATCH", "/properties", {"set": {"os_type": "windows"}}),
    ],
)
async def test_admin_image_related_routes_require_admin(non_admin_client, mock_conn, method, suffix, body):
    response = await non_admin_client.request(method, f"/api/v1/admin/images/img-1{suffix}", json=body)
    assert response.status_code == 403
    mock_conn.image.get_image.assert_not_called()
    mock_conn.image.members.assert_not_called()
    mock_conn.image.add_member.assert_not_called()
    mock_conn.image.remove_member.assert_not_called()


@pytest.mark.asyncio
async def test_admin_foreign_image_members_bind_exact_parent_and_member(admin_client, image_transports):
    state = image_transports
    image_id = state.image.id
    member = Member(member="shared-project", image_id=image_id, status="pending")
    state.executor.image.members.return_value = [member]
    state.executor.image.add_member.return_value = member
    state.executor.image.get_member.return_value = member
    url = f"/api/v1/admin/images/{image_id}/members"
    listed = await admin_client.get(url)
    assert listed.status_code == 200
    assert listed.json() == [{"member_id": "shared-project", "status": "pending", "created_at": None}]
    created = await admin_client.post(url, json={"member": "shared-project"})
    assert created.status_code == 201
    assert created.json()["member_id"] == "shared-project"
    deleted = await admin_client.delete(f"{url}/shared-project")
    assert deleted.status_code == 204
    state.executor.image.members.assert_called_once_with(image_id)
    state.executor.image.add_member.assert_called_once_with(image_id, member_id="shared-project")
    state.executor.image.get_member.assert_called_once_with("shared-project", image_id)
    state.executor.image.remove_member.assert_called_once_with("shared-project", image_id, ignore_missing=False)
    state.caller.image.members.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["detail", "list", "add", "remove"])
@pytest.mark.parametrize("invalid_parent", ["different-id", "missing-owner"])
async def test_admin_image_details_and_members_reject_unbound_parent(
    admin_client, image_transports, operation, invalid_parent
):
    state = image_transports
    image_id = state.image.id
    if invalid_parent == "different-id":
        state.image.id = "another-image"
    else:
        state.image.owner = state.image.project_id = None
    url = f"/api/v1/admin/images/{image_id}"
    if operation == "detail":
        response = await admin_client.get(url)
    elif operation == "list":
        response = await admin_client.get(f"{url}/members")
    elif operation == "add":
        response = await admin_client.post(f"{url}/members", json={"member": "shared-project"})
    else:
        response = await admin_client.delete(f"{url}/members/shared-project")
    assert response.status_code == 404
    state.executor.image.members.assert_not_called()
    state.executor.image.add_member.assert_not_called()
    state.executor.image.remove_member.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["list", "add", "remove"])
@pytest.mark.parametrize("binding", ["wrong-image", "missing-image", "wrong-member"])
async def test_admin_image_members_reject_child_binding_mismatch(admin_client, image_transports, operation, binding):
    state = image_transports
    image_id = state.image.id
    member = Member(
        member="another-project" if binding == "wrong-member" else "shared-project",
        image_id=None if binding == "missing-image" else "other-image" if binding == "wrong-image" else image_id,
        status="pending",
    )
    # Listing has no requested child ID, so a different member ID is legitimate.
    if operation == "list" and binding == "wrong-member":
        member = Member(member=None, image_id=image_id, status="pending")
    state.executor.image.members.return_value = [member]
    state.executor.image.add_member.return_value = member
    state.executor.image.get_member.return_value = member
    url = f"/api/v1/admin/images/{image_id}/members"
    if operation == "list":
        response = await admin_client.get(url)
    elif operation == "add":
        response = await admin_client.post(url, json={"member": "shared-project"})
    else:
        response = await admin_client.delete(f"{url}/shared-project")
    assert response.status_code == 404
    state.executor.image.remove_member.assert_not_called()


@pytest.mark.asyncio
async def test_admin_image_member_removal_requires_present_exact_child(admin_client, image_transports):
    state = image_transports
    state.executor.image.get_member.side_effect = ResourceNotFound("Missing membership")
    response = await admin_client.delete(f"/api/v1/admin/images/{state.image.id}/members/missing-project")
    assert response.status_code == 404
    state.executor.image.remove_member.assert_not_called()


@pytest.mark.asyncio
async def test_admin_image_member_provider_failure_is_not_empty_success(admin_client, image_transports):
    state = image_transports
    state.executor.image.members.side_effect = RuntimeError("Native member directory unavailable")
    response = await admin_client.get(f"/api/v1/admin/images/{state.image.id}/members")
    assert response.status_code == 502
    assert response.json() != []


@pytest.mark.asyncio
async def test_admin_delete_evicts_cached_project_catalogs(admin_client, mock_conn, monkeypatch):
    from app.services import cache

    keys = ["afterglow:glance:personal:images", "afterglow:glance:foreign:images"]
    for key in keys:
        assert await cache.cached_call(key, 300, lambda: [{"id": "deleted-image"}]) == [{"id": "deleted-image"}]
    monkeypatch.setattr("app.api.identity.admin_images.image_verification.remove_deleted_image", AsyncMock())
    response = await admin_client.delete("/api/v1/admin/images/deleted-image")
    assert response.status_code == 204
    for key in keys:
        assert await cache.cached_call(key, 300, lambda: []) == []
