"""Manila file_storage / access-rule cross-project IDOR 거부 검증.

afterglow 가 share metadata.union_project_id 로 owner 추적 — 다른 프로젝트의
share_id 로 detail/delete + access-rule 조작 시 404.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.storage import FileStorageInfo


def _foreign_share(fs_id: str = "share-foreign", owner: str = "other-project-999"):
    return FileStorageInfo(
        id=fs_id,
        name="foreign",
        status="available",
        size=10,
        share_proto="NFS",
        export_locations=[],
        metadata={"union_project_id": owner},
        project_id=owner,
        created_at="2024-01-01T00:00:00Z",
        nfs_export_location=None,
        library_name=None,
        library_version=None,
        built_at=None,
        is_public=False,
    )


@pytest.mark.asyncio
async def test_get_share_other_project_returns_404(client, mock_conn):
    with patch("app.api.storage.file_storage.manila.get_file_storage", return_value=_foreign_share()):
        resp = await client.get("/api/v1/file-storage/share-foreign")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_share_other_project_returns_404(client, mock_conn):
    with patch("app.api.storage.file_storage.manila.get_file_storage", return_value=_foreign_share()):
        resp = await client.delete("/api/v1/file-storage/share-foreign")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_delete_other_project_share(admin_client, mock_conn):
    with (
        patch("app.api.storage.file_storage.manila.get_file_storage", return_value=_foreign_share()),
        patch("app.api.storage.file_storage.manila.delete_file_storage", return_value=None),
        patch("app.api.storage.file_storage.invalidate", new_callable=AsyncMock) as invalidate_mock,
    ):
        resp = await admin_client.delete("/api/v1/file-storage/share-foreign")
    assert resp.status_code == 204
    invalidate_mock.assert_any_await("afterglow:manila:test-project-123:file_storages")
    invalidate_mock.assert_any_await("afterglow:manila:other-project-999:file_storages")
    invalidate_mock.assert_any_await("afterglow:admin:file_storages")


@pytest.mark.asyncio
async def test_list_access_rules_other_project_returns_404(client, mock_conn):
    with patch("app.api.storage.file_storage.manila.get_file_storage", return_value=_foreign_share()):
        resp = await client.get("/api/v1/file-storage/share-foreign/access-rules")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_access_rule_other_project_returns_404(client, mock_conn):
    """가장 위험 — 다른 프로젝트 share 에 IP rule 추가하면 cross-tenant CephFS mount 가능."""
    with patch("app.api.storage.file_storage.manila.get_file_storage", return_value=_foreign_share()):
        resp = await client.post(
            "/api/v1/file-storage/share-foreign/access-rules",
            json={"access_to": "10.0.0.0/24", "access_level": "rw", "access_type": "ip"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_access_rule_other_project_returns_404(client, mock_conn):
    with patch("app.api.storage.file_storage.manila.get_file_storage", return_value=_foreign_share()):
        resp = await client.delete("/api/v1/file-storage/share-foreign/access-rules/rule-1")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_public_share_access_passes_for_get(client, mock_conn):
    """is_public 인 share 는 cross-project 노출이 정상."""
    public = _foreign_share()
    public.is_public = True
    with patch("app.api.storage.file_storage.manila.get_file_storage", return_value=public):
        resp = await client.get("/api/v1/file-storage/share-foreign")
    assert resp.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 404, 500, 503, 504])
@pytest.mark.parametrize("suffix", ["", "/access-rules"])
async def test_share_owner_read_distinguishes_unavailable_from_absent(client, mock_conn, status, suffix):
    import httpx

    request = httpx.Request("GET", "http://native.invalid/shares/private-share")
    response = httpx.Response(status, json={"error": "PRIVATE_MANILA_BODY_CANARY"}, request=request)
    with (
        patch(
            "app.services.manila.get_file_storage",
            side_effect=httpx.HTTPStatusError("PRIVATE_MANILA_BODY_CANARY", request=request, response=response),
        ),
        patch("app.services.manila.list_access_rules") as access_rules,
    ):
        result = await client.get(f"/api/v1/file-storage/private-share{suffix}")
    assert result.status_code == (404 if status in (401, 403, 404) else 503)
    assert "PRIVATE_MANILA_BODY_CANARY" not in result.text
    access_rules.assert_not_called()


@pytest.mark.asyncio
async def test_share_owner_transport_failure_is_not_reported_absent(client, mock_conn):
    import httpx

    with patch("app.services.manila.get_file_storage", side_effect=httpx.ConnectError("PRIVATE_TRANSPORT_CANARY")):
        result = await client.get("/api/v1/file-storage/private-share")
    assert result.status_code == 503
    assert "PRIVATE_TRANSPORT_CANARY" not in result.text
