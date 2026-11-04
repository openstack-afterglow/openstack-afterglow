"""Trove DB instance/backup cross-project IDOR 거부 검증."""

from unittest.mock import MagicMock, patch

import pytest


def _foreign(project_id: str = "other-project-999"):
    m = MagicMock()
    m.project_id = project_id
    m.tenant_id = None
    return m


@pytest.mark.asyncio
async def test_get_db_instance_other_project_returns_404(client, mock_conn):
    mock_conn.database.get_instance = MagicMock(return_value=_foreign())
    resp = await client.get("/api/v1/database-instances/inst-foreign")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_db_instance_other_project_returns_404(client, mock_conn):
    mock_conn.database.get_instance = MagicMock(return_value=_foreign())
    resp = await client.delete("/api/v1/database-instances/inst-foreign")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_restart_db_instance_other_project_returns_404(client, mock_conn):
    mock_conn.database.get_instance = MagicMock(return_value=_foreign())
    resp = await client.post("/api/v1/database-instances/inst-foreign/restart")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_enable_root_other_project_returns_404(client, mock_conn):
    """가장 위험한 케이스 — root 비밀번호 발급 endpoint."""
    mock_conn.database.get_instance = MagicMock(return_value=_foreign())
    resp = await client.post("/api/v1/database-instances/inst-foreign/root")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_enable_root_other_project(admin_client, mock_conn):
    mock_conn.database.get_instance = MagicMock(return_value=_foreign())
    with patch(
        "app.api.database.instances.asyncio.to_thread",
        side_effect=lambda fn, *a, **kw: _async_return({"name": "root", "password": "pw"}),
    ):
        # asyncio.to_thread 직접 patch 보다는 trove 함수 patch 가 안전 — 단순화
        pass
    with patch("app.services.trove.enable_root", return_value={"name": "root", "password": "pw"}):
        resp = await admin_client.post("/api/v1/database-instances/inst-foreign/root")
    assert resp.status_code == 200


async def _async_return(v):
    return v


@pytest.mark.asyncio
async def test_create_db_other_project_returns_404(client, mock_conn):
    mock_conn.database.get_instance = MagicMock(return_value=_foreign())
    resp = await client.post("/api/v1/database-instances/inst-foreign/databases", json={"name": "mydb"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_user_other_project_returns_404(client, mock_conn):
    mock_conn.database.get_instance = MagicMock(return_value=_foreign())
    resp = await client.post(
        "/api/v1/database-instances/inst-foreign/users",
        json={"name": "u1", "password": "pw"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_db_backup_other_project_returns_404(client, mock_conn):
    mock_conn.database.get_instance = MagicMock(return_value=_foreign())
    resp = await client.post("/api/v1/database-instances/inst-foreign/backups", json={"name": "b1"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_db_backup_other_project_returns_404(client, mock_conn):
    mock_conn.database.get_backup = MagicMock(return_value=_foreign())
    resp = await client.delete("/api/v1/database-instances/backups/bk-foreign")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_restore_from_other_project_backup_returns_404(client, mock_conn):
    mock_conn.database.get_backup = MagicMock(return_value=_foreign())
    resp = await client.post(
        "/api/v1/database-instances/restore",
        json={"backup_id": "bk-foreign", "name": "n", "flavor_id": "f", "volume_size": 1},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 404, 503, 504])
@pytest.mark.parametrize("suffix", ["", "/databases", "/users", "/backups", "/auto-backup"])
async def test_instance_owner_read_distinguishes_unavailable_from_absent(client, mock_conn, status, suffix):
    from openstack.exceptions import HttpException

    mock_conn.database.get_instance.side_effect = HttpException(
        "PRIVATE_PROVIDER_BODY_CANARY",
        http_status=status,
    )
    with patch("app.services.trove.get_instance") as readback:
        resp = await client.get(f"/api/v1/database-instances/inst-unavailable{suffix}")
    assert resp.status_code == (404 if status in (401, 403, 404) else 503)
    assert "PRIVATE_PROVIDER_BODY_CANARY" not in resp.text
    readback.assert_not_called()


@pytest.mark.asyncio
async def test_instance_owner_transport_failure_is_unavailable(client, mock_conn):
    mock_conn.database.get_instance.side_effect = ConnectionError("PRIVATE_TRANSPORT_CANARY")
    resp = await client.get("/api/v1/database-instances/inst-unavailable")
    assert resp.status_code == 503
    assert "PRIVATE_TRANSPORT_CANARY" not in resp.text


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 503])
async def test_instance_readback_distinguishes_unavailable_after_owner_check(client, mock_conn, status):
    from openstack.exceptions import HttpException

    with patch(
        "app.services.trove.get_instance",
        side_effect=HttpException("PRIVATE_READBACK_CANARY", http_status=status),
    ):
        resp = await client.get("/api/v1/database-instances/inst-owned?refresh=true")
    assert resp.status_code == status
    assert "PRIVATE_READBACK_CANARY" not in resp.text
