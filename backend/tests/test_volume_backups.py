"""볼륨 백업 API 테스트."""

from unittest.mock import AsyncMock, patch

import pytest


def make_backup(bid: str = "backup-1"):
    return {
        "id": bid,
        "name": "test-backup",
        "status": "available",
        "volume_id": "vol-1",
        "size": 10,
        "is_incremental": False,
        "description": "",
        "created_at": "2024-01-01T00:00:00",
    }


@pytest.mark.asyncio
async def test_list_backups(client, mock_conn):
    with patch("app.api.storage.volume_backups.cinder.list_backups", return_value=[make_backup()]):
        resp = await client.get("/api/v1/volumes/backups")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == "backup-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(("volume_status", "force"), [("available", False), ("in-use", True)])
async def test_create_backup(client, mock_conn, volume_status, force):
    mock_conn.block_storage.get_volume.return_value.status = volume_status
    with patch("app.api.storage.volume_backups.cinder.create_backup", return_value=make_backup("backup-new")):
        resp = await client.post(
            "/api/v1/volumes/backups", json={"volume_id": "vol-1", "name": "my-backup", "force": force}
        )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_in_use_backup_requires_explicit_force_without_provider_mutation(client, mock_conn):
    mock_conn.block_storage.get_volume.return_value.status = "in-use"
    with patch("app.api.storage.volume_backups.cinder.create_backup") as create:
        resp = await client.post("/api/v1/volumes/backups", json={"volume_id": "vol-1", "name": "my-backup"})
    assert resp.status_code == 400
    create.assert_not_called()


@pytest.mark.asyncio
async def test_delete_backup(client, mock_conn):
    with patch("app.api.storage.volume_backups.cinder.delete_backup", return_value=None):
        resp = await client.delete("/api/v1/volumes/backups/backup-1")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_backup_not_shadowed_by_volumes_route(client, mock_conn):
    """볼륨 라우터가 /backups를 가로채지 않음을 확인 (Task 1 버그 수정)."""
    with patch("app.api.storage.volume_backups.cinder.list_backups", return_value=[make_backup()]):
        resp = await client.get("/api/v1/volumes/backups")
    # 404가 아닌 200이어야 함
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_restore_backup_creates_new_volume(client, mock_conn):
    """body 미전달 시 새 볼륨으로 복원하고 volume_id를 반환한다."""
    with patch(
        "app.api.storage.volume_backups.cinder.restore_backup",
        return_value={"volume_id": "vol-restored", "volume_name": "restored-vol"},
    ) as mock_restore:
        resp = await client.post("/api/v1/volumes/backups/backup-1/restore")
    assert resp.status_code == 200
    assert resp.json()["volume_id"] == "vol-restored"
    mock_restore.assert_called_once_with(mock_conn, "backup-1", None)


@pytest.mark.asyncio
async def test_restore_backup_to_existing_volume(client, mock_conn):
    """volume_id 지정 시 해당 볼륨에 복원 요청한다."""
    with patch(
        "app.api.storage.volume_backups.cinder.restore_backup",
        return_value={"volume_id": "vol-target", "volume_name": "target-vol"},
    ) as mock_restore:
        resp = await client.post("/api/v1/volumes/backups/backup-1/restore", json={"volume_id": "vol-target"})
    assert resp.status_code == 200
    mock_restore.assert_called_once_with(mock_conn, "backup-1", "vol-target")


@pytest.mark.asyncio
async def test_create_backup_sdk_error_propagates_status(client, mock_conn):
    """Cinder HttpException 발생 시 status_code + 실제 메시지가 전달된다."""
    from openstack.exceptions import HttpException

    with (
        patch(
            "app.api.storage.volume_backups.cinder.create_backup",
            side_effect=HttpException(message="Invalid backup request", http_status=400),
        ),
        patch("app.api.storage.volume_backups.rec", new_callable=AsyncMock),
    ):
        resp = await client.post("/api/v1/volumes/backups", json={"volume_id": "vol-1", "name": "bad-backup"})
    assert resp.status_code == 400
    assert "Invalid backup request" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_backup_cached(client, mock_conn):
    """GET /{backup_id} 는 cached_call 을 통해 반환된다."""
    with patch("app.api.storage.volume_backups.cinder.get_backup", return_value=make_backup()) as mock_get:
        resp = await client.get("/api/v1/volumes/backups/backup-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "backup-1"
    mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_create_backup_invalidates_cache(client, mock_conn):
    """백업 생성 후 backups* 패턴 무효화 + mutation count 증가."""
    with (
        patch("app.api.storage.volume_backups.cinder.create_backup", return_value=make_backup("backup-new")),
        patch("app.api.storage.volume_backups.invalidate", new_callable=AsyncMock) as mock_inv,
        patch(
            "app.api.storage.volume_backups.invalidation.invalidate_mutation_count", new_callable=AsyncMock
        ) as mock_mut,
        patch("app.api.storage.volume_backups.rec", new_callable=AsyncMock),
    ):
        resp = await client.post("/api/v1/volumes/backups", json={"volume_id": "vol-1", "name": "my-backup"})
    assert resp.status_code == 201
    mock_inv.assert_called_once_with("afterglow:cinder:test-project-123:backups*")
    mock_mut.assert_called_once_with("cinder", "test-project-123")


@pytest.mark.asyncio
async def test_delete_backup_invalidates_cache(client, mock_conn):
    """백업 삭제 후 backups* 패턴 무효화 + mutation count 증가."""
    with (
        patch("app.api.storage.volume_backups.cinder.delete_backup", return_value=None),
        patch("app.api.storage.volume_backups.invalidate", new_callable=AsyncMock) as mock_inv,
        patch(
            "app.api.storage.volume_backups.invalidation.invalidate_mutation_count", new_callable=AsyncMock
        ) as mock_mut,
        patch("app.api.storage.volume_backups.rec", new_callable=AsyncMock),
    ):
        resp = await client.delete("/api/v1/volumes/backups/backup-1")
    assert resp.status_code == 204
    mock_inv.assert_called_once_with("afterglow:cinder:test-project-123:backups*")
    mock_mut.assert_called_once_with("cinder", "test-project-123")


@pytest.mark.asyncio
async def test_restore_backup_invalidates_cache(client, mock_conn):
    """백업 복원 후 backups* 패턴 무효화 + mutation count 증가."""
    with (
        patch(
            "app.api.storage.volume_backups.cinder.restore_backup",
            return_value={"volume_id": "vol-restored", "volume_name": "restored-vol"},
        ),
        patch("app.api.storage.volume_backups.invalidate", new_callable=AsyncMock) as mock_inv,
        patch(
            "app.api.storage.volume_backups.invalidation.invalidate_mutation_count", new_callable=AsyncMock
        ) as mock_mut,
        patch("app.api.storage.volume_backups.rec", new_callable=AsyncMock),
    ):
        resp = await client.post("/api/v1/volumes/backups/backup-1/restore")
    assert resp.status_code == 200
    mock_inv.assert_called_once_with("afterglow:cinder:test-project-123:backups*")
    mock_mut.assert_called_once_with("cinder", "test-project-123")
