"""admin 볼륨 삭제 엔드포인트 — force-delete 폴백 분기 단위 테스트."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from openstack.exceptions import ResourceNotFound


def _make_volume(status: str, attachments: list | None = None) -> MagicMock:
    v = MagicMock()
    v.status = status
    v.attachments = attachments or []
    return v


@pytest.mark.asyncio
async def test_delete_volume_available_uses_normal_delete(admin_client, mock_conn):
    """available 상태 볼륨은 정상 delete 경로를 탄다."""
    mock_conn.block_storage.get_volume.return_value = _make_volume("available")

    with patch("app.services.cinder.force_delete_volume") as mock_force:
        resp = await admin_client.delete("/api/v1/admin/volumes/vol-1")

    assert resp.status_code == 204
    mock_conn.block_storage.delete_volume.assert_called_once_with("vol-1", ignore_missing=True)
    mock_force.assert_not_called()


@pytest.mark.asyncio
async def test_delete_volume_error_deleting_uses_reset_then_delete(admin_client, mock_conn):
    """error_deleting 상태 볼륨은 reset_status → 일반 delete 경로로 정리된다."""
    mock_conn.block_storage.get_volume.return_value = _make_volume("error_deleting")

    with (
        patch("app.services.cinder.reset_volume_status") as mock_reset,
        patch("app.services.cinder.force_delete_volume") as mock_force,
    ):
        resp = await admin_client.delete("/api/v1/admin/volumes/vol-2")

    assert resp.status_code == 204
    mock_reset.assert_called_once()
    mock_conn.block_storage.delete_volume.assert_called_once_with("vol-2", ignore_missing=True)
    mock_force.assert_not_called()


@pytest.mark.asyncio
async def test_delete_volume_error_uses_reset_then_delete(admin_client, mock_conn):
    """error 상태 볼륨도 reset_status → 일반 delete 경로로 정리된다."""
    mock_conn.block_storage.get_volume.return_value = _make_volume("error")

    with (
        patch("app.services.cinder.reset_volume_status"),
        patch("app.services.cinder.force_delete_volume") as mock_force,
    ):
        resp = await admin_client.delete("/api/v1/admin/volumes/vol-3")

    assert resp.status_code == 204
    mock_conn.block_storage.delete_volume.assert_called_once()
    mock_force.assert_not_called()


@pytest.mark.asyncio
async def test_delete_volume_delete_fails_falls_back_to_force(admin_client, mock_conn):
    """reset 후 일반 delete가 실패하면 force_delete로 최종 폴백한다."""
    from openstack.exceptions import HttpException

    mock_conn.block_storage.get_volume.return_value = _make_volume("error_deleting")
    mock_conn.block_storage.delete_volume.side_effect = HttpException(http_status=400, message="still bad")

    with (
        patch("app.services.cinder.reset_volume_status"),
        patch("app.services.cinder.force_delete_volume") as mock_force,
    ):
        resp = await admin_client.delete("/api/v1/admin/volumes/vol-fb")

    assert resp.status_code == 204
    mock_force.assert_called_once()


@pytest.mark.asyncio
async def test_delete_volume_already_gone_returns_204(admin_client, mock_conn):
    """Cinder에 볼륨이 이미 없으면 204로 idempotent 처리된다."""
    mock_conn.block_storage.get_volume.side_effect = ResourceNotFound()

    with patch("app.services.cinder.force_delete_volume") as mock_force:
        resp = await admin_client.delete("/api/v1/admin/volumes/vol-gone")

    assert resp.status_code == 204
    mock_conn.block_storage.delete_volume.assert_not_called()
    mock_force.assert_not_called()


@pytest.mark.asyncio
async def test_delete_volume_deleting_uses_reset_then_delete(admin_client, mock_conn):
    """deleting 상태(stuck)도 reset_status → 일반 delete 경로로 진입한다."""
    mock_conn.block_storage.get_volume.return_value = _make_volume("deleting")

    with (
        patch("app.services.cinder.reset_volume_status") as mock_reset,
        patch("app.services.cinder.force_delete_volume") as mock_force,
    ):
        resp = await admin_client.delete("/api/v1/admin/volumes/vol-stuck")

    assert resp.status_code == 204
    mock_reset.assert_called_once()
    mock_conn.block_storage.delete_volume.assert_called_once()
    mock_force.assert_not_called()


@pytest.mark.asyncio
async def test_delete_volume_in_use_returns_400(admin_client, mock_conn):
    """in-use 상태 볼륨은 force-delete 폴백 없이 400을 반환한다."""
    from openstack.exceptions import HttpException

    mock_conn.block_storage.get_volume.return_value = _make_volume("in-use", attachments=[{"id": "att-1"}])
    mock_conn.block_storage.delete_volume.side_effect = HttpException(http_status=400, message="Invalid volume")

    with patch("app.services.cinder.force_delete_volume") as mock_force:
        resp = await admin_client.delete("/api/v1/admin/volumes/vol-attached")

    assert resp.status_code == 400
    mock_force.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_delete_volumes_continues_after_secret_bearing_failure(admin_client, mock_conn):
    from openstack.exceptions import HttpException

    attached = _make_volume("in-use", attachments=[{"id": "att-1"}])
    attached.project_id = "project-2"
    available = _make_volume("available")
    available.project_id = "project-1"
    sensitive_detail = "https://service:private-password@storage.internal denied X-Auth-Token=private-token"
    mock_conn.block_storage.get_volume.side_effect = [attached, available]
    mock_conn.block_storage.delete_volume.side_effect = [HttpException(http_status=400, message=sensitive_detail), None]

    with (
        patch("app.api.identity.admin.rec", new_callable=AsyncMock) as record,
        patch("app.api.identity.admin._invalidate_volume_recovery_caches", new_callable=AsyncMock),
    ):
        response = await admin_client.post(
            "/api/v1/admin/volumes/bulk-delete",
            json={"volume_ids": ["vol-attached", "vol-ok"]},
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [(item["id"], item["ok"]) for item in results] == [("vol-attached", False), ("vol-ok", True)]
    assert results[0]["error"]
    assert results[1]["error"] is None
    for secret in ("private-password", "private-token", "storage.internal"):
        assert secret not in response.text
        assert secret not in str(record.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "volume_ids",
    [[], ["duplicate", "duplicate"], [f"vol-{index}" for index in range(51)]],
)
async def test_bulk_delete_volumes_rejects_invalid_id_sets(admin_client, mock_conn, volume_ids):
    resp = await admin_client.post("/api/v1/admin/volumes/bulk-delete", json={"volume_ids": volume_ids})

    assert resp.status_code == 422
    mock_conn.block_storage.get_volume.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_delete_volumes_requires_admin(non_admin_client, mock_conn):
    resp = await non_admin_client.post(
        "/api/v1/admin/volumes/bulk-delete",
        json={"volume_ids": ["vol-1"]},
    )

    assert resp.status_code == 403
    mock_conn.block_storage.get_volume.assert_not_called()


# ── force-delete 엔드포인트 테스트 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_force_delete_normal_status_succeeds(admin_client, mock_conn):
    """available 상태 볼륨도 force-delete 엔드포인트로 삭제 가능하다."""
    mock_conn.block_storage.get_volume.return_value = _make_volume("available")

    with (
        patch("app.services.cinder.reset_volume_status"),
        patch("app.services.cinder.force_delete_volume") as mock_force,
    ):
        resp = await admin_client.post("/api/v1/admin/volumes/vol-x/force-delete")

    assert resp.status_code == 204
    mock_conn.block_storage.delete_volume.assert_called_once()
    mock_force.assert_not_called()


@pytest.mark.asyncio
async def test_force_delete_attached_returns_409(admin_client, mock_conn):
    """attached 볼륨은 강제 삭제 시 409를 반환한다."""
    mock_conn.block_storage.get_volume.return_value = _make_volume("in-use", attachments=[{"id": "a"}])

    resp = await admin_client.post("/api/v1/admin/volumes/vol-att/force-delete")

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_force_delete_already_gone_returns_204(admin_client, mock_conn):
    """이미 없는 볼륨에 force-delete 요청 시 204로 idempotent 처리된다."""
    mock_conn.block_storage.get_volume.side_effect = ResourceNotFound()

    resp = await admin_client.post("/api/v1/admin/volumes/vol-gone/force-delete")

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_force_delete_volume_requires_admin(non_admin_client):
    """비admin 사용자는 force-delete 엔드포인트에 접근할 수 없다."""
    resp = await non_admin_client.post("/api/v1/admin/volumes/vol-1/force-delete")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_get_delete_diagnostics(non_admin_client):
    """비admin 사용자는 delete-diagnostics 엔드포인트에 접근할 수 없다."""
    resp = await non_admin_client.get("/api/v1/admin/volumes/vol-1/delete-diagnostics")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_recover_delete(non_admin_client):
    """비admin 사용자는 recover-delete 엔드포인트에 접근할 수 없다."""
    resp = await non_admin_client.post("/api/v1/admin/volumes/vol-1/recover-delete")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_recover_delete_volume_records_activity_and_invalidates(admin_client, mock_conn):
    """복구 성공 시 activity, 캐시 무효화, mutation count bump 를 함께 수행한다."""
    from app.models.storage import (
        VolumeDeleteDiagnostic,
        VolumeDeleteRecoveryResult,
        VolumeDeleteRecoveryStep,
    )

    diagnostic = VolumeDeleteDiagnostic(
        volume_id="vol-1",
        status="error_deleting",
        project_id="proj-abc",
        attachments=[],
        dependencies=[],
        messages=[],
        root_cause_code="recoverable_error_deleting",
        confidence="high",
        summary="recoverable",
        evidence=["status=error_deleting"],
        recommended_action="recover now",
        recovery_available=True,
        force_delete_available=True,
    )
    result = VolumeDeleteRecoveryResult(
        volume_id="vol-1",
        status="deleted",
        verified_deleted=True,
        final_status=None,
        diagnostic=diagnostic,
        steps=[
            VolumeDeleteRecoveryStep(action="diagnose", status="success", detail="recoverable_error_deleting"),
            VolumeDeleteRecoveryStep(action="reset_status", status="success", detail="error/detached"),
        ],
    )

    with (
        patch(
            "app.api.identity.admin.volume_delete_recovery.recover_delete_volume", return_value=result
        ) as recover_mock,
        patch("app.api.identity.admin.invalidate", new_callable=AsyncMock) as invalidate_mock,
        patch(
            "app.api.identity.admin.cache_invalidation.invalidate_mutation_count",
            new_callable=AsyncMock,
        ) as mutation_mock,
        patch("app.api.identity.admin.rec", new_callable=AsyncMock) as rec_mock,
    ):
        resp = await admin_client.post("/api/v1/admin/volumes/vol-1/recover-delete")

    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    recover_mock.assert_called_once_with(mock_conn, "vol-1", ANY, verify_timeout_seconds=30)
    assert invalidate_mock.await_count == 4
    invalidate_mock.assert_any_await("afterglow:cinder:proj-abc:volumes*")
    invalidate_mock.assert_any_await("afterglow:cinder:proj-abc:vol_attach:*")
    invalidate_mock.assert_any_await("afterglow:admin:overview*")
    invalidate_mock.assert_any_await("afterglow:admin:monitoring*")
    mutation_mock.assert_awaited_once_with("cinder", "proj-abc")
    rec_mock.assert_awaited_once()
    rec_kwargs = rec_mock.await_args.kwargs
    assert rec_kwargs["resource_type"] == "volume"
    assert rec_kwargs["action"] == "volume.recover_delete"
    assert rec_kwargs["status"] == "success"
    assert rec_kwargs["resource_id"] == "vol-1"
    assert rec_kwargs["error_message"] is None
    assert rec_kwargs["extra"]["result"] == "deleted"
    assert rec_kwargs["extra"]["verified_deleted"] is True
    assert rec_kwargs["extra"]["root_cause"] == "recoverable_error_deleting"
    assert rec_kwargs["extra"]["steps"][0]["action"] == "diagnose"
