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
    mock_conn.block_storage.get_volume = MagicMock(return_value=_foreign())
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
