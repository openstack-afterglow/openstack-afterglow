"""인스턴스 resize / revert-resize 관리자 API 단위 테스트."""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.compute import FlavorInfo, InstanceInfo


@pytest.fixture(autouse=True)
def resize_catalog():
    current = FlavorInfo(id="flavor-old", name="old", vcpus=2, ram=2048, disk=0)
    target = FlavorInfo(id="flavor-new", name="new", vcpus=4, ram=4096, disk=0)
    server = InstanceInfo(id="inst-1", name="vm", status="ACTIVE", project_id="target-project", flavor_id=current.id)
    with (
        patch("app.api.identity.admin_instances._server", return_value=server),
        patch("app.api.identity.admin.nova._list_flavors", return_value=[current, target]),
        patch(
            "app.services.flavor_eligibility.nova.get_project_quota",
            return_value={
                "instances": {"limit": 10, "in_use": 1},
                "cores": {"limit": 16, "in_use": 2},
                "ram": {"limit": 16384, "in_use": 2048},
            },
        ),
        patch("app.api.compute.instances._invalidate_resized_instance", new_callable=AsyncMock),
    ):
        yield


@pytest.mark.asyncio
async def test_admin_resize_insufficient_target_quota_denies_before_native_mutation(admin_client):
    with (
        patch(
            "app.services.flavor_eligibility.nova.get_project_quota",
            return_value={
                "instances": {"limit": 10, "in_use": 1},
                "cores": {"limit": 2, "in_use": 2},
                "ram": {"limit": 16384, "in_use": 2048},
            },
        ),
        patch("app.api.identity.admin.nova.resize_server") as resize,
    ):
        response = await admin_client.post("/api/v1/admin/instances/inst-1/resize", json={"flavor_id": "flavor-new"})
    assert response.status_code == 409
    assert "cores_insufficient" in response.json()["detail"]
    resize.assert_not_called()


@pytest.mark.asyncio
async def test_admin_resize_requires_admin(non_admin_client):
    """일반 사용자는 resize 엔드포인트에 접근 불가 (403)."""
    resp = await non_admin_client.post(
        "/api/v1/admin/instances/inst-1/resize",
        json={"flavor_id": "flavor-new"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_resize_nova_failure_returns_400(admin_client, mock_conn):
    """Nova 오류 시 400을 반환한다."""
    with patch("app.api.identity.admin.nova.resize_server", side_effect=Exception("Nova error")):
        resp = await admin_client.post(
            "/api/v1/admin/instances/inst-1/resize",
            json={"flavor_id": "flavor-new"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_resize_rejects_flavor_absent_from_target_visibility(admin_client):
    with patch("app.api.identity.admin.nova.resize_server") as resize:
        response = await admin_client.post(
            "/api/v1/admin/instances/inst-1/resize", json={"flavor_id": "private-other-project"}
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid flavor ID"
    resize.assert_not_called()


@pytest.mark.asyncio
async def test_admin_resize_uses_target_project_not_actor_workspace(admin_client):
    from app.services import compute_pools

    async def snapshot(conn, project_id):
        assert project_id == "target-project"
        return {"enabled": False}

    with (
        patch.object(compute_pools, "project_pool_snapshot", side_effect=snapshot),
        patch("app.api.identity.admin.nova.resize_server"),
    ):
        response = await admin_client.post("/api/v1/admin/instances/inst-1/resize", json={"flavor_id": "flavor-new"})
    assert response.status_code == 200
    assert response.json()["status"] == "resizing"
