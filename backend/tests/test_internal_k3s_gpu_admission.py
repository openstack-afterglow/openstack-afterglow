from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.gpu_inventory import GpuQuotaDenied, GpuQuotaUnavailable


@pytest.fixture
async def admission_client(monkeypatch):
    monkeypatch.setenv("K3S_GPU_ADMISSION_TOKEN", "test-admission-secret")
    from app.config import get_settings

    get_settings.cache_clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_gpu_admission_rejects_missing_or_invalid_credential(admission_client, monkeypatch):
    from app.api import internal_k3s

    open_connection = MagicMock()
    monkeypatch.setattr(internal_k3s, "get_admin_connection_for_project", open_connection)
    body = {"project_id": "project-1", "flavor_id": "flavor-1"}

    missing = await admission_client.post("/api/v1/internal/k3s/gpu-admission", json=body)
    invalid = await admission_client.post(
        "/api/v1/internal/k3s/gpu-admission",
        json=body,
        headers={"X-Afterglow-K3s-Admission-Token": "invalid"},
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    open_connection.assert_not_called()


@pytest.mark.asyncio
async def test_gpu_admission_rejects_unsafe_resource_identifiers(admission_client, monkeypatch):
    from app.api import internal_k3s

    open_connection = MagicMock()
    monkeypatch.setattr(internal_k3s, "get_admin_connection_for_project", open_connection)

    response = await admission_client.post(
        "/api/v1/internal/k3s/gpu-admission",
        json={"project_id": "../project", "flavor_id": "flavor-1"},
        headers={"X-Afterglow-K3s-Admission-Token": "test-admission-secret"},
    )

    assert response.status_code == 400
    open_connection.assert_not_called()


@pytest.mark.asyncio
async def test_gpu_admission_returns_authoritative_gpu_requirement(admission_client, monkeypatch):
    from app.api import internal_k3s

    conn = MagicMock()
    flavor = SimpleNamespace(id="gpu-flavor", extra_specs={"pci_passthrough:alias": "RTX3090:1"})
    monkeypatch.setattr(internal_k3s, "get_admin_connection_for_project", MagicMock(return_value=conn))
    monkeypatch.setattr(internal_k3s.nova, "list_flavors", MagicMock(return_value=[flavor]))
    require_quota = AsyncMock(return_value=True)
    monkeypatch.setattr(internal_k3s, "require_gpu_quota", require_quota)

    response = await admission_client.post(
        "/api/v1/internal/k3s/gpu-admission",
        json={"project_id": "project-1", "flavor_id": "gpu-flavor"},
        headers={"X-Afterglow-K3s-Admission-Token": "test-admission-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {"gpu_required": True}
    require_quota.assert_awaited_once_with(conn, flavor)
    conn.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_gpu_admission_returns_authoritative_non_gpu_requirement(admission_client, monkeypatch):
    from app.api import internal_k3s

    conn = MagicMock()
    flavor = SimpleNamespace(id="cpu-flavor", extra_specs={})
    monkeypatch.setattr(internal_k3s, "get_admin_connection_for_project", MagicMock(return_value=conn))
    monkeypatch.setattr(internal_k3s.nova, "list_flavors", MagicMock(return_value=[flavor]))
    require_quota = AsyncMock(return_value=False)
    monkeypatch.setattr(internal_k3s, "require_gpu_quota", require_quota)

    response = await admission_client.post(
        "/api/v1/internal/k3s/gpu-admission",
        json={"project_id": "project-1", "flavor_id": "cpu-flavor"},
        headers={"X-Afterglow-K3s-Admission-Token": "test-admission-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {"gpu_required": False}
    require_quota.assert_awaited_once_with(conn, flavor)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (GpuQuotaDenied("quota exceeded"), 409),
        (GpuQuotaUnavailable("authority unavailable"), 503),
    ],
)
async def test_gpu_admission_propagates_quota_decision(admission_client, monkeypatch, error, status):
    from app.api import internal_k3s

    conn = MagicMock()
    flavor = SimpleNamespace(id="gpu-flavor", extra_specs={"pci_passthrough:alias": "RTX3090:1"})
    monkeypatch.setattr(internal_k3s, "get_admin_connection_for_project", MagicMock(return_value=conn))
    monkeypatch.setattr(internal_k3s.nova, "list_flavors", MagicMock(return_value=[flavor]))
    monkeypatch.setattr(internal_k3s, "require_gpu_quota", AsyncMock(side_effect=error))

    response = await admission_client.post(
        "/api/v1/internal/k3s/gpu-admission",
        json={"project_id": "project-1", "flavor_id": "gpu-flavor"},
        headers={"X-Afterglow-K3s-Admission-Token": "test-admission-secret"},
    )

    assert response.status_code == status
    conn.close.assert_called_once_with()
