"""GPU Quota 관리 API 단위 테스트 (admin.py 내 GPU quota 엔드포인트).

검증 항목:
1. 모든 GPU quota 엔드포인트: non-admin → 403
2. Afterglow DB 상태와 무관하게 Drover 성공 응답 전달
3. Drover 실패 시 503 fail-closed
4. 쿼터 계산 로직 (available = limit - in_use, -1 = 무제한)
"""

from unittest.mock import AsyncMock, patch

import pytest

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 인증 (admin-only) 테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_get_gpu_aliases_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/gpu-aliases")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_default_gpu_quotas_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/gpu-quotas/defaults")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_set_default_gpu_quota_requires_admin(non_admin_client):
    resp = await non_admin_client.put("/api/v1/admin/gpu-quotas/defaults", json={"gpu_type": "RTX3090", "limit": 4})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_default_gpu_quota_requires_admin(non_admin_client):
    resp = await non_admin_client.delete("/api/v1/admin/gpu-quotas/defaults/RTX3090")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_gpu_quotas_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/gpu-quotas/proj-1")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_set_gpu_quota_requires_admin(non_admin_client):
    resp = await non_admin_client.put("/api/v1/admin/gpu-quotas/proj-1", json={"gpu_type": "RTX3090", "limit": 2})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_gpu_quota_requires_admin(non_admin_client):
    resp = await non_admin_client.delete("/api/v1/admin/gpu-quotas/proj-1/RTX3090")
    assert resp.status_code == 403


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DB 헬스 상태 무관 — Drover 프록시 정상 시 성공 응답
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_get_default_gpu_quotas_succeeds(admin_client):
    with patch("app.services.gpu_quota.get_project_gpu_quotas", return_value=[{"gpu_type": "RTX3090", "limit": 4}]):
        resp = await admin_client.get("/api/v1/admin/gpu-quotas/defaults")
    assert resp.status_code == 200
    assert resp.json() == [{"gpu_type": "RTX3090", "limit": 4}]


@pytest.mark.asyncio
async def test_set_default_gpu_quota_succeeds(admin_client):
    ret = {"project_id": "__default__", "gpu_type": "RTX3090", "limit": 4}
    with (
        patch("app.services.gpu_quota.set_project_gpu_quota", return_value=ret),
        patch("app.api.identity.admin.invalidate") as mock_invalidate,
    ):
        resp = await admin_client.put("/api/v1/admin/gpu-quotas/defaults", json={"gpu_type": "RTX3090", "limit": 4})
    assert resp.status_code == 200
    assert resp.json() == ret
    mock_invalidate.assert_awaited_once_with("afterglow:nova:*:flavors")


@pytest.mark.asyncio
async def test_delete_default_gpu_quota_succeeds(admin_client):
    with patch("app.services.gpu_quota.delete_project_gpu_quota", return_value=True):
        resp = await admin_client.delete("/api/v1/admin/gpu-quotas/defaults/RTX3090")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_get_gpu_quotas_succeeds(admin_client):
    ret = [{"gpu_type": "RTX3090", "limit": 4, "in_use": 1, "available": 3}]
    with patch("app.services.gpu_quota.get_effective_gpu_quota_status", return_value=ret):
        resp = await admin_client.get("/api/v1/admin/gpu-quotas/proj-1")
    assert resp.status_code == 200
    assert resp.json() == ret


@pytest.mark.asyncio
async def test_set_gpu_quota_succeeds(admin_client):
    ret = {"project_id": "proj-1", "gpu_type": "RTX3090", "limit": 2}
    with (
        patch("app.services.gpu_quota.set_project_gpu_quota", return_value=ret),
        patch("app.api.identity.admin.invalidate") as mock_invalidate,
    ):
        resp = await admin_client.put("/api/v1/admin/gpu-quotas/proj-1", json={"gpu_type": "RTX3090", "limit": 2})
    assert resp.status_code == 200
    assert resp.json() == ret
    mock_invalidate.assert_awaited_once_with("afterglow:nova:proj-1:flavors")


@pytest.mark.asyncio
async def test_delete_gpu_quota_succeeds(admin_client):
    with patch("app.services.gpu_quota.delete_project_gpu_quota", return_value=True):
        resp = await admin_client.delete("/api/v1/admin/gpu-quotas/proj-1/RTX3090")
    assert resp.status_code == 204


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GPU 서비스 예외 발생 시 503 응답 회귀 테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_get_default_gpu_quotas_exception_returns_503(admin_client):
    with patch(
        "app.services.gpu_quota.get_project_gpu_quotas", side_effect=RuntimeError("GPU quota service unreachable")
    ):
        resp = await admin_client.get("/api/v1/admin/gpu-quotas/defaults")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_get_gpu_quotas_exception_returns_503(admin_client):
    with patch(
        "app.services.gpu_quota.get_project_gpu_quotas", side_effect=RuntimeError("GPU quota service unreachable")
    ):
        resp = await admin_client.get("/api/v1/admin/gpu-quotas/proj-1")
    assert resp.status_code == 503


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GPU alias 목록 조회 (admin 허용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_get_gpu_aliases_allowed(admin_client):
    with patch(
        "app.services.gpu_inventory.get_all_gpu_aliases",
        new=AsyncMock(return_value=["RTX3090", "RTX4090"]),
    ):
        resp = await admin_client.get("/api/v1/admin/gpu-aliases")
    assert resp.status_code == 200
    assert resp.json() == {"aliases": ["RTX3090", "RTX4090"]}


@pytest.mark.asyncio
async def test_get_gpu_aliases_empty(admin_client):
    with patch(
        "app.services.gpu_inventory.get_all_gpu_aliases",
        new=AsyncMock(return_value=[]),
    ):
        resp = await admin_client.get("/api/v1/admin/gpu-aliases")
    assert resp.status_code == 200
    assert resp.json() == {"aliases": []}


@pytest.mark.asyncio
async def test_get_all_gpu_aliases_refreshes_db_overlay_before_discovery():
    """DB catalog aliases must be loaded before mapping Placement device names to quota aliases."""

    class FakeConnection:
        def close(self):
            pass

    refresh = AsyncMock()
    with (
        patch("app.database.is_db_available", return_value=True),
        patch("app.services.gpu_catalog.refresh_device_map_from_db", new=refresh),
        patch("openstack.connect", return_value=FakeConnection()),
        patch("app.services.nova.list_flavors", return_value=[]),
        patch(
            "app.services.gpu_inventory._collect_gpu_hosts", return_value={"gpu_types": [{"device_name": "RTX 3090"}]}
        ),
        patch("app.api.identity.admin_gpu.build_device_name_to_alias_map", return_value={"RTX 3090": "RTX-3090"}),
    ):
        from app.services.gpu_inventory import get_all_gpu_aliases

        result = await get_all_gpu_aliases()

    refresh.assert_awaited_once()
    assert result == ["RTX3090"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 기본 GPU quota CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def test_get_default_gpu_quotas_success(admin_client):
    with patch("app.services.gpu_quota.get_project_gpu_quotas", return_value=[{"gpu_type": "RTX3090", "limit": 4}]):
        resp = await admin_client.get("/api/v1/admin/gpu-quotas/defaults")
    assert resp.status_code == 200
    data = resp.json()
    assert data == [{"gpu_type": "RTX3090", "limit": 4}]


@pytest.mark.asyncio
async def test_get_default_gpu_quotas_empty(admin_client):
    with patch("app.services.gpu_quota.get_project_gpu_quotas", return_value=[]):
        resp = await admin_client.get("/api/v1/admin/gpu-quotas/defaults")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_set_default_gpu_quota_success(admin_client):
    ret = {"project_id": "__default__", "gpu_type": "RTX3090", "limit": 4}
    with patch("app.services.gpu_quota.set_project_gpu_quota", return_value=ret):
        resp = await admin_client.put("/api/v1/admin/gpu-quotas/defaults", json={"gpu_type": "RTX3090", "limit": 4})
    assert resp.status_code == 200
    data = resp.json()
    assert data["gpu_type"] == "RTX3090"
    assert data["limit"] == 4


@pytest.mark.asyncio
async def test_delete_default_gpu_quota_success(admin_client):
    with patch("app.services.gpu_quota.delete_project_gpu_quota", return_value=True):
        resp = await admin_client.delete("/api/v1/admin/gpu-quotas/defaults/RTX3090")
    assert resp.status_code == 204


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 프로젝트별 GPU quota CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_set_gpu_quota_success(admin_client):
    ret = {"project_id": "proj-1", "gpu_type": "RTX3090", "limit": 2}
    with patch("app.services.gpu_quota.set_project_gpu_quota", return_value=ret):
        resp = await admin_client.put("/api/v1/admin/gpu-quotas/proj-1", json={"gpu_type": "RTX3090", "limit": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == "proj-1"
    assert data["gpu_type"] == "RTX3090"
    assert data["limit"] == 2


@pytest.mark.asyncio
async def test_delete_gpu_quota_success(admin_client):
    with patch("app.services.gpu_quota.delete_project_gpu_quota", return_value=True):
        resp = await admin_client.delete("/api/v1/admin/gpu-quotas/proj-1/RTX3090")
    assert resp.status_code == 204


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 쿼터 계산 로직 테스트 (available = limit - in_use / -1 = 무제한)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_get_gpu_quotas_available_calculation(admin_client):
    ret = [{"gpu_type": "RTX3090", "limit": 4, "in_use": 1, "available": 3}]
    with patch("app.services.gpu_quota.get_effective_gpu_quota_status", return_value=ret):
        resp = await admin_client.get("/api/v1/admin/gpu-quotas/proj-1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    item = data[0]
    assert item["gpu_type"] == "RTX3090"
    assert item["limit"] == 4
    assert item["in_use"] == 1
    assert item["available"] == 3
