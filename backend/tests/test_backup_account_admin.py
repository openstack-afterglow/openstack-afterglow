"""Read-only system-account diagnostics obey existing human-admin authorization."""

from unittest.mock import AsyncMock

import pytest

from app.api.deps import require_admin
from app.main import app
from app.services import backup_account_reconciler


@pytest.mark.asyncio
async def test_admin_status_and_report_are_no_store_reads(admin_client, monkeypatch):
    state = {"state": "reconciled", "enabled": True, "writes": 2}
    report = {
        "mode": "report",
        "complete": True,
        "intended_writes": [{"action": "update_backup_gigabytes", "before": 1000, "after": 32604}],
    }
    monkeypatch.setattr(backup_account_reconciler, "status", AsyncMock(return_value=state))
    monkeypatch.setattr(backup_account_reconciler, "read_report", AsyncMock(return_value=report))
    response = await admin_client.get("/api/v1/admin/backup-system-account")
    assert response.status_code == 200
    assert response.json() == state
    assert response.headers["cache-control"] == "no-store"
    response = await admin_client.get("/api/v1/admin/backup-system-account/report")
    assert response.status_code == 200
    assert response.json() == report
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_report_denies_non_admin_without_native_reads(client, monkeypatch):
    from fastapi import HTTPException

    async def denied():
        raise HTTPException(403, "system_admin_required")

    read = AsyncMock()
    monkeypatch.setattr(backup_account_reconciler, "read_report", read)
    previous = app.dependency_overrides.copy()
    try:
        app.dependency_overrides[require_admin] = denied
        response = await client.get("/api/v1/admin/backup-system-account/report")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
    assert response.status_code == 403
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_report_errors_use_fixed_safe_code(admin_client, monkeypatch):
    monkeypatch.setattr(
        backup_account_reconciler, "read_report", AsyncMock(side_effect=RuntimeError("private native payload"))
    )
    response = await admin_client.get("/api/v1/admin/backup-system-account/report")
    assert response.status_code == 503
    assert "private native payload" not in response.text
    assert "backup_system_account_report_unavailable" in response.text
