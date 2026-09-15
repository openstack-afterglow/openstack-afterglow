from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_cached_public_gpu_flavor_is_rehydrated_before_visibility_policy(client, mock_conn):
    cached_flavor = {
        "id": "flavor-gpu",
        "name": "gpu.nvidia-l40s",
        "vcpus": 8,
        "ram": 32768,
        "disk": 100,
        "is_public": True,
        "extra_specs": {},
    }
    mock_conn.compute.get_flavor.return_value = SimpleNamespace(
        id="flavor-gpu",
        name="gpu.nvidia-l40s",
        vcpus=8,
        ram=32768,
        disk=100,
        is_public=True,
        extra_specs={"pci_passthrough:alias": "NVIDIA_L40S:1"},
    )
    gpu_status = [
        {
            "project_id": "proj-123",
            "gpu_type": "NVIDIAL40S",
            "limit": 1,
            "in_use": 0,
            "available": 1,
        }
    ]

    with (
        patch("app.api.compute.flavors.cache.cached_call", new=AsyncMock(return_value=[cached_flavor])),
        patch(
            "app.services.nova.get_project_quota",
            return_value={
                "instances": {"limit": 10, "in_use": 0},
                "cores": {"limit": 64, "in_use": 0},
                "ram": {"limit": 262144, "in_use": 0},
            },
        ),
        patch("app.services.gpu_quota.get_effective_gpu_quota_status", new=AsyncMock(return_value=gpu_status)),
    ):
        response = await client.get("/api/v1/flavors")

    assert response.status_code == 200
    assert [(item["id"], item["name"]) for item in response.json()] == [("flavor-gpu", "gpu.nvidia-l40s")]
    assert response.json()[0]["extra_specs"] == {"pci_passthrough:alias": "NVIDIA_L40S:1"}
    assert response.json()[0]["eligibility"]["selectable"] is True
    mock_conn.compute.get_flavor.assert_called_once_with("flavor-gpu")
