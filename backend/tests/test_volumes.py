"""볼륨 API 테스트."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def make_mock_volume(vol_id: str = "vol-1", name: str = "test-vol", status: str = "available"):
    from app.models.storage import VolumeInfo

    return VolumeInfo(id=vol_id, name=name, status=status, size=10, volume_type=None, attachments=[])


@pytest.mark.asyncio
async def test_list_volumes(client, mock_conn):
    with patch("app.api.storage.volumes.cinder.list_volumes", return_value=[make_mock_volume()]):
        resp = await client.get("/api/v1/volumes")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["id"] == "vol-1"


@pytest.mark.asyncio
async def test_list_preserves_native_creation_time_for_resource_ordering(client, mock_conn):
    from openstack.block_storage.v3.volume import Volume

    mock_conn.block_storage.volumes.return_value = [
        Volume(id="old", name="Old", status="available", size=10, created_at="2026-10-26T01:02:03.123456"),
        Volume(id="new", name="New", status="available", size=20, created_at="2026-10-28T02:03:04Z"),
        Volume(id="unknown", name="Unknown", status="available", size=30),
    ]
    response = await client.get("/api/v1/volumes")
    assert response.status_code == 200
    assert {row["id"]: row["created_at"] for row in response.json()} == {
        "old": "2026-10-26T01:02:03.123456",
        "new": "2026-10-28T02:03:04Z",
        "unknown": None,
    }


@pytest.mark.asyncio
async def test_old_cached_volume_shape_cannot_hide_native_creation_time(client, mock_conn, _fake_redis_global):
    import json

    from openstack.block_storage.v3.volume import Volume

    old = make_mock_volume().model_dump(exclude={"created_at"})
    await _fake_redis_global.set("afterglow:cinder:test-project-123:volumes:v2", json.dumps([old]), ex=60)
    mock_conn.block_storage.volumes.return_value = [
        Volume(id="vol-1", name="test-vol", status="available", size=10, created_at="2026-10-28T02:03:04Z"),
    ]
    response = await client.get("/api/v1/volumes?cache=true")
    assert response.status_code == 200
    assert response.json()[0]["created_at"] == "2026-10-28T02:03:04Z"


@pytest.mark.asyncio
async def test_create_volume(client, mock_conn):
    with patch(
        "app.api.storage.volumes.cinder.create_empty_volume", return_value=make_mock_volume("vol-new", "new-vol")
    ):
        resp = await client.post("/api/v1/volumes", json={"name": "new-vol", "size_gb": 10})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_delete_volume(client, mock_conn):
    with patch("app.api.storage.volumes.cinder.delete_volume", return_value=None):
        resp = await client.delete("/api/v1/volumes/vol-1")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_get_volume(client, mock_conn):
    with patch("app.api.storage.volumes.cinder.get_volume", return_value=make_mock_volume()):
        resp = await client.get("/api/v1/volumes/vol-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "vol-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["available", "in-use"])
async def test_rename_volume_refreshes_list_and_detail(client, mock_conn, status):
    volume = SimpleNamespace(
        id="vol-1",
        project_id="test-project-123",
        name="old-name",
        status=status,
        size=10,
        volume_type=None,
        attachments=[{"server_id": "vm-1"}] if status == "in-use" else [],
        is_bootable=False,
        volume_image_metadata=None,
    )
    mock_conn.block_storage.get_volume.return_value = volume
    mock_conn.block_storage.volumes.return_value = [volume]

    def update_volume(volume_id, *, name):
        assert volume_id == "vol-1"
        volume.name = name

    mock_conn.block_storage.update_volume.side_effect = update_volume
    with patch("app.api.storage.volumes.rec", new_callable=AsyncMock) as record:
        before = await client.get("/api/v1/volumes?cache=true")
        renamed = await client.patch("/api/v1/volumes/vol-1", json={"name": " new-name "})
        after_list = await client.get("/api/v1/volumes?cache=true")
        after_detail = await client.get("/api/v1/volumes/vol-1")

    assert before.json()[0]["name"] == "old-name"
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "new-name"
    assert renamed.json()["status"] == status
    assert after_list.json()[0]["name"] == "new-name"
    assert after_detail.json()["name"] == "new-name"
    assert mock_conn.block_storage.volumes.call_count == 2
    mock_conn.block_storage.update_volume.assert_called_once_with("vol-1", name="new-name")
    assert any(
        call.kwargs["status"] == "success" and call.kwargs["action"] == "volume.rename"
        for call in record.await_args_list
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", "  \t  ", "x" * 256])
async def test_rename_volume_rejects_invalid_name(client, mock_conn, name):
    with patch("app.api.storage.volumes.rec", new_callable=AsyncMock) as record:
        response = await client.patch("/api/v1/volumes/vol-1", json={"name": name})

    assert response.status_code == 422
    mock_conn.block_storage.get_volume.assert_not_called()
    mock_conn.block_storage.update_volume.assert_not_called()
    record.assert_not_awaited()


@pytest.mark.asyncio
async def test_rename_volume_rejects_foreign_owner_before_update(client, mock_conn):
    mock_conn.block_storage.get_volume.return_value.project_id = "other-project"
    with patch("app.api.storage.volumes.rec", new_callable=AsyncMock) as record:
        response = await client.patch("/api/v1/volumes/vol-1", json={"name": "new-name"})

    assert response.status_code == 404
    mock_conn.block_storage.update_volume.assert_not_called()
    record.assert_not_awaited()


@pytest.mark.asyncio
async def test_rename_volume_rejects_missing_owner_metadata(client, mock_conn):
    mock_conn.block_storage.get_volume.return_value.project_id = None
    mock_conn.block_storage.get_volume.return_value.tenant_id = None
    with patch("app.api.storage.volumes.rec", new_callable=AsyncMock) as record:
        response = await client.patch("/api/v1/volumes/vol-1", json={"name": "new-name"})

    assert response.status_code == 404
    mock_conn.block_storage.update_volume.assert_not_called()
    record.assert_not_awaited()


@pytest.mark.asyncio
async def test_rename_volume_rejects_reader(client, mock_conn):
    from app.api.deps import get_token_info
    from tests.conftest import make_token_info

    app.dependency_overrides[get_token_info] = lambda: make_token_info(roles=["reader"])
    with patch("app.api.storage.volumes.rec", new_callable=AsyncMock) as record:
        response = await client.patch("/api/v1/volumes/vol-1", json={"name": "new-name"})

    assert response.status_code == 403
    mock_conn.block_storage.get_volume.assert_not_called()
    mock_conn.block_storage.update_volume.assert_not_called()
    record.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,code",
    [
        (ValueError("secret traceback"), 500),
        (None, 409),
        (None, 502),
    ],
)
async def test_rename_volume_failure_does_not_report_success(client, mock_conn, error, code):
    from openstack.exceptions import HttpException

    error = error or HttpException(message="secret traceback", http_status=409 if code == 409 else 503)
    mock_conn.block_storage.update_volume.side_effect = error
    with (
        patch("app.api.storage.volumes.cinder.get_volume") as fresh_get,
        patch("app.api.storage.volumes.rec", new_callable=AsyncMock) as record,
        patch("app.api.storage.volumes.invalidate", new_callable=AsyncMock) as invalidate,
    ):
        response = await client.patch("/api/v1/volumes/vol-1", json={"name": "new-name"})

    assert response.status_code == code
    assert "secret traceback" not in response.text
    fresh_get.assert_not_called()
    invalidate.assert_not_awaited()
    assert [call.kwargs["status"] for call in record.await_args_list] == ["failed"]


@pytest.mark.asyncio
async def test_rename_volume_refresh_failure_records_failed_audit(client, mock_conn):
    with (
        patch("app.api.storage.volumes.cinder.get_volume", side_effect=RuntimeError("secret traceback")),
        patch("app.api.storage.volumes.rec", new_callable=AsyncMock) as record,
        patch("app.api.storage.volumes.invalidate", new_callable=AsyncMock),
    ):
        response = await client.patch("/api/v1/volumes/vol-1", json={"name": "new-name"})

    assert response.status_code == 500
    assert "secret traceback" not in response.text
    assert [call.kwargs["status"] for call in record.await_args_list] == ["failed"]


@pytest.mark.asyncio
async def test_list_volumes_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/volumes")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rename_volume_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.patch("/api/v1/volumes/vol-1", json={"name": "new-name"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_transfers_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/volumes/transfers")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_lookup_transfer_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/volumes/transfer/11111111-1111-4111-8111-111111111111")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_transfer_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/volumes/vol-1/transfer", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_accept_transfer_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/volumes/transfer/tr-1/accept", json={"auth_key": "abc123"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_transfer_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/volumes/transfer/tr-1")
    assert resp.status_code == 401
