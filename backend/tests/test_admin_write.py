"""관리자 쓰기 작업 API 단위 테스트."""

from unittest.mock import AsyncMock, patch

import pytest

# ────── 비관리자 접근 거부 (403) 테스트 ──────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/v1/admin/overview", None),
        ("get", "/api/v1/admin/all-instances", None),
        ("get", "/api/v1/admin/all-volumes", None),
        ("get", "/api/v1/admin/hypervisors", None),
        ("get", "/api/v1/admin/quotas/some-project-id?domain_id=default", None),
        ("post", "/api/v1/admin/instances/inst-1/live-migrate", {}),
    ],
)
async def test_admin_endpoint_requires_admin(non_admin_client, method, path, body):
    resp = (
        await getattr(non_admin_client, method)(path) if body is None else await non_admin_client.post(path, json=body)
    )
    assert resp.status_code == 403


# ────── 관리자 접근 허용 테스트 (403이 아닌 것 확인) ──────


@pytest.mark.asyncio
async def test_admin_access_not_forbidden(admin_client, mock_conn):
    """admin 역할 보유 시 관리자 엔드포인트 접근 가능 (403이 아님)."""
    with patch("app.api.identity.admin.cached_call") as mc:
        mc.side_effect = AsyncMock(
            return_value={
                "hypervisor_count": 0,
                "running_vms": 0,
                "gpu_instances": 0,
                "instance_stats": {},
                "vcpus": {"total": 0, "allowed": 0, "used": 0},
                "ram_gb": {"total": 0, "used": 0},
                "disk_gb": {"total": 0, "used": 0},
                "containers_count": 0,
                "file_storage_count": 0,
            }
        )
        resp = await admin_client.get("/api/v1/admin/overview")
    assert resp.status_code != 403


@pytest.mark.asyncio
async def test_admin_hypervisors_not_forbidden(admin_client, mock_conn):
    with patch("app.api.identity.admin.cached_call") as mc:
        mc.side_effect = AsyncMock(return_value=[])
        resp = await admin_client.get("/api/v1/admin/hypervisors")
    assert resp.status_code != 403
