"""Cinder volume/snapshot/backup cross-project IDOR 거부 검증."""

from unittest.mock import MagicMock, patch

import pytest


def _foreign(project_id: str = "other-project-999"):
    m = MagicMock()
    m.project_id = project_id
    m.tenant_id = None
    return m


# ────── Volume ──────


@pytest.mark.asyncio
async def test_get_volume_other_project_returns_404(client, mock_conn):
    mock_conn.block_storage.get_volume = MagicMock(return_value=_foreign())
    resp = await client.get("/api/v1/volumes/vol-foreign")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_volume_other_project_returns_404(client, mock_conn):
    mock_conn.block_storage.get_volume = MagicMock(return_value=_foreign())
    resp = await client.delete("/api/v1/volumes/vol-foreign")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_volume_transfer_other_project_returns_404(client, mock_conn):
    mock_conn.block_storage.get_volume = MagicMock(
        return_value={"id": "vol-foreign", "project_id": "other-project-999"}
    )
    with patch("app.services.volume_transfers.scoped_connection", return_value=(mock_conn, "scoped-token")):
        resp = await client.post("/api/v1/volumes/vol-foreign/transfer", json={"name": "tx"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_delete_other_project_volume(admin_client, mock_conn):
    mock_conn.block_storage.get_volume = MagicMock(return_value=_foreign())
    with patch("app.api.storage.volumes.cinder.delete_volume", return_value=None):
        resp = await admin_client.delete("/api/v1/volumes/vol-foreign")
    assert resp.status_code == 204


# ────── Snapshot ──────


@pytest.mark.asyncio
async def test_get_snapshot_other_project_returns_404(client, mock_conn):
    mock_conn.block_storage.get_snapshot = MagicMock(return_value=_foreign())
    resp = await client.get("/api/v1/volume-snapshots/snap-foreign")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_snapshot_other_project_returns_404(client, mock_conn):
    mock_conn.block_storage.get_snapshot = MagicMock(return_value=_foreign())
    resp = await client.delete("/api/v1/volume-snapshots/snap-foreign")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_snapshot_for_other_project_volume_returns_404(client, mock_conn):
    mock_conn.block_storage.get_volume = MagicMock(return_value=_foreign())
    resp = await client.post("/api/v1/volume-snapshots", json={"volume_id": "vol-foreign", "name": "s1"})
    assert resp.status_code == 404


# ────── Backup ──────


@pytest.mark.asyncio
async def test_get_backup_other_project_returns_404(client, mock_conn):
    mock_conn.block_storage.get_backup = MagicMock(return_value=_foreign())
    resp = await client.get("/api/v1/volumes/backups/bk-foreign")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_backup_other_project_returns_404(client, mock_conn):
    mock_conn.block_storage.get_backup = MagicMock(return_value=_foreign())
    resp = await client.delete("/api/v1/volumes/backups/bk-foreign")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_backup_for_other_project_volume_returns_404(client, mock_conn):
    mock_conn.block_storage.get_volume = MagicMock(return_value=_foreign())
    resp = await client.post("/api/v1/volumes/backups", json={"volume_id": "vol-foreign", "name": "b1", "force": True})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_restore_other_project_backup_returns_404(client, mock_conn):
    mock_conn.block_storage.get_backup = MagicMock(return_value=_foreign())
    resp = await client.post("/api/v1/volumes/backups/bk-foreign/restore", json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("method,body", [("get", None), ("post", {"force": True}), ("delete", None)])
@pytest.mark.parametrize("owner", [None, "other-project-999"])
async def test_schedule_foreign_or_unproven_source_is_denied_even_to_admin(
    admin_client, mock_conn, method, body, owner
):
    mock_conn.block_storage.get_volume.return_value.project_id = owner
    mock_conn.block_storage.get_volume.return_value.status = "available"
    with (
        patch("app.services.auto_backup.enable_auto_backup") as save,
        patch("app.services.auto_backup.disable_auto_backup") as remove,
    ):
        response = await admin_client.request(method, "/api/v1/volumes/backups/auto-backup/vol-foreign", json=body)
    assert response.status_code == 404
    save.assert_not_called()
    remove.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_list_retains_stored_policy_without_foreign_source_details(client, mock_conn):
    from app.services.auto_backup import enable_auto_backup

    await enable_auto_backup(mock_conn._afterglow_project_id, "vol-foreign")
    mock_conn.block_storage.get_volume.return_value.project_id = "other-project-999"
    response = await client.post("/api/v1/volumes/backups/auto-backup/configs")
    assert response.status_code == 200
    policy = response.json()[0]
    assert policy["volume_id"] == "vol-foreign" and policy["enabled"] is True
    assert policy["source_status"] == "not_owned" and policy["source_available"] is False
    assert "other-project-999" not in response.text
    assert (await client.delete("/api/v1/volumes/backups/auto-backup/vol-foreign")).status_code == 404
