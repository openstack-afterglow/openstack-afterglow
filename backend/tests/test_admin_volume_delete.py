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


def _recovery_result(status: str = "deleted"):
    from app.models.storage import (
        VolumeDeleteBackendInspection,
        VolumeDeleteCheck,
        VolumeDeleteDiagnostic,
        VolumeDeleteRecoveryResult,
        VolumeDeleteRecoveryStep,
    )

    residue = status == "backend_residue"
    diagnostic = VolumeDeleteDiagnostic(
        volume_id="vol-1",
        status="error_deleting",
        project_id="proj-abc",
        checks=[VolumeDeleteCheck(name="auth_preflight", state="present")],
        backend=VolumeDeleteBackendInspection(
            mode="inspected" if residue else "unavailable",
            classification="inconsistent" if residue else "not_inspected",
            pool="volumes" if residue else None,
        ),
        root_cause_code="backend_present_consistent" if residue else "recoverable_backend_unverified",
        confidence="high",
        summary="recoverable",
        evidence=["status=error_deleting"],
        recommended_action="recover now",
        recovery_available=True,
    )
    return VolumeDeleteRecoveryResult(
        volume_id="vol-1",
        status=status,
        verified_deleted=status == "deleted",
        diagnostic=diagnostic,
        backend_verification="residue" if residue else "unavailable",
        quota_verification="verified",
        steps=[VolumeDeleteRecoveryStep(action="diagnose", status="success", detail=diagnostic.root_cause_code)],
    )


def _redis_lock(acquired: bool = True):
    redis = MagicMock()
    redis.set = AsyncMock(return_value=acquired)
    redis.delete = AsyncMock()
    return redis


@pytest.mark.asyncio
async def test_recover_delete_volume_locks_records_full_activity_and_invalidates(admin_client, mock_conn):
    redis = _redis_lock()
    result = _recovery_result()

    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch(
            "app.api.identity.admin.volume_delete_recovery.recover_delete_volume",
            return_value=result,
        ) as recover_mock,
        patch(
            "app.api.identity.admin._invalidate_volume_recovery_caches",
            new_callable=AsyncMock,
        ) as invalidate_mock,
        patch("app.api.identity.admin.rec", new_callable=AsyncMock) as rec_mock,
    ):
        resp = await admin_client.post("/api/v1/admin/volumes/vol-1/recover-delete")

    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    redis.set.assert_awaited_once_with("afterglow:volume-recovery:lock:vol-1", ANY, nx=True, ex=600)
    redis.delete.assert_awaited_once_with("afterglow:volume-recovery:lock:vol-1")
    recover_mock.assert_called_once_with(mock_conn, "vol-1", verify_timeout_seconds=30)
    invalidate_mock.assert_awaited_once_with("proj-abc")
    rec_kwargs = rec_mock.await_args.kwargs
    assert rec_kwargs["status"] == "success"
    assert rec_kwargs["extra"]["backend_verification"] == "unavailable"
    assert rec_kwargs["extra"]["quota_verification"] == "verified"
    assert rec_kwargs["extra"]["checks"] == [{"name": "auth_preflight", "state": "present", "detail": None}]
    assert rec_kwargs["extra"]["mode"] == "force_delete"
    assert rec_kwargs["extra"]["previous_status"] is None


@pytest.mark.asyncio
async def test_recover_delete_volume_rejects_concurrent_operation(admin_client):
    redis = _redis_lock(acquired=False)

    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch("app.api.identity.admin.volume_delete_recovery.recover_delete_volume") as recover_mock,
    ):
        resp = await admin_client.post("/api/v1/admin/volumes/vol-1/recover-delete")

    assert resp.status_code == 409
    recover_mock.assert_not_called()
    redis.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_recover_delete_volume_fails_closed_when_lock_backend_is_unavailable(admin_client):
    with patch(
        "app.api.identity.admin._get_redis",
        new=AsyncMock(side_effect=RuntimeError("redis down")),
    ):
        resp = await admin_client.post("/api/v1/admin/volumes/vol-1/recover-delete")

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_backend_residue_invalidates_caches_and_is_a_failed_audit_result(admin_client):
    redis = _redis_lock()
    result = _recovery_result("backend_residue")

    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch(
            "app.api.identity.admin.volume_delete_recovery.recover_delete_volume",
            return_value=result,
        ),
        patch(
            "app.api.identity.admin._invalidate_volume_recovery_caches",
            new_callable=AsyncMock,
        ) as invalidate_mock,
        patch("app.api.identity.admin.rec", new_callable=AsyncMock) as rec_mock,
    ):
        resp = await admin_client.post("/api/v1/admin/volumes/vol-1/recover-delete")

    assert resp.status_code == 200
    assert resp.json()["status"] == "backend_residue"
    invalidate_mock.assert_awaited_once_with("proj-abc")
    assert rec_mock.await_args.kwargs["status"] == "failed"
    assert rec_mock.await_args.kwargs["error_message"] == "backend_residue"


def _recovery_body(mode: str = "force_delete", status: str = "creating") -> dict:
    return {"mode": mode, "confirm_volume_id": "vol-1", "expected_status": status}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"mode": "delete"},
        {"mode": "force_delete"},
        {"mode": "force_delete", "confirm_volume_id": "vol-1"},
        {"mode": "force_delete", "expected_status": "creating"},
        {"mode": "force_delete", "confirm_volume_id": None, "expected_status": "creating"},
        {"mode": "force_delete", "confirm_volume_id": "", "expected_status": "creating"},
        {"mode": "force_delete", "confirm_volume_id": "vol-1", "expected_status": ""},
        {"mode": "force_delete", "confirm_volume_id": 1, "expected_status": "creating"},
        {"mode": "force_delete", "confirm_volume_id": "vol-1", "expected_status": 1},
        {**_recovery_body(), "force": True},
    ],
)
async def test_recovery_body_rejects_invalid_explicit_requests_before_lock(admin_client, mock_conn, body):
    with (
        patch("app.api.identity.admin._get_redis", new_callable=AsyncMock) as get_redis,
        patch("app.api.identity.admin.volume_delete_recovery.recover_delete_volume") as recover,
    ):
        response = await admin_client.post("/api/v1/admin/volumes/vol-1/recover-delete", json=body)

    assert response.status_code == 422
    get_redis.assert_not_awaited()
    recover.assert_not_called()
    mock_conn.block_storage.get_volume.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["recover", "force_delete"])
async def test_explicit_recovery_passes_confirmation_under_lock_and_audits(admin_client, mock_conn, mode):
    from app.models.storage import VolumeDeleteRecoveryStep

    redis = _redis_lock()
    result = _recovery_result("state_reset" if mode == "recover" else "deleted")
    result.previous_status = "creating"
    if mode == "recover":
        result.final_status = "error"
        result.diagnostic.status = "error"
        result.steps.append(VolumeDeleteRecoveryStep(action="reset_state", status="success", detail="error"))

    def recover(conn, volume_id, **kwargs):
        assert redis.set.await_count == 1
        assert redis.delete.await_count == 0
        assert conn is mock_conn
        assert volume_id == "vol-1"
        assert kwargs == {**_recovery_body(mode), "verify_timeout_seconds": 0}
        return result

    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch(
            "app.api.identity.admin.volume_delete_recovery.recover_delete_volume",
            side_effect=recover,
        ) as recover_mock,
        patch("app.api.identity.admin._invalidate_volume_recovery_caches", new_callable=AsyncMock) as invalidate,
        patch("app.api.identity.admin.rec", new_callable=AsyncMock) as record,
    ):
        response = await admin_client.post(
            "/api/v1/admin/volumes/vol-1/recover-delete?verify_timeout_seconds=0",
            json=_recovery_body(mode),
        )

    assert response.status_code == 200
    assert response.json()["status"] == result.status
    assert response.json()["verified_deleted"] is (mode == "force_delete")
    recover_mock.assert_called_once()
    redis.delete.assert_awaited_once_with("afterglow:volume-recovery:lock:vol-1")
    invalidate.assert_awaited_once_with("proj-abc")
    audit = record.await_args.kwargs
    assert audit["status"] == "success"
    assert audit["error_message"] is None
    assert audit["extra"]["mode"] == mode
    assert audit["extra"]["previous_status"] == "creating"
    assert audit["extra"]["steps"] == [step.model_dump() for step in result.steps]


@pytest.mark.asyncio
async def test_recover_mode_without_confirmation_passes_optional_fields_to_service(admin_client, mock_conn):
    redis = _redis_lock()
    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch(
            "app.api.identity.admin.volume_delete_recovery.recover_delete_volume",
            return_value=_recovery_result("blocked"),
        ) as recover,
        patch("app.api.identity.admin.rec", new_callable=AsyncMock),
    ):
        response = await admin_client.post(
            "/api/v1/admin/volumes/vol-1/recover-delete",
            json={"mode": "recover"},
        )

    assert response.status_code == 200
    recover.assert_called_once_with(
        mock_conn,
        "vol-1",
        verify_timeout_seconds=30,
        mode="recover",
        confirm_volume_id=None,
        expected_status=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,live_status",
    [
        ({**_recovery_body(), "confirm_volume_id": "vol-other"}, "creating"),
        (_recovery_body(status="downloading"), "creating"),
        (_recovery_body(status="creating"), "available"),
        ({**_recovery_body("recover"), "confirm_volume_id": "vol-other"}, "creating"),
        (_recovery_body("recover", "downloading"), "creating"),
    ],
)
async def test_recovery_confirmation_mismatch_uses_live_diagnostic_under_lock_without_writes(
    admin_client, mock_conn, body, live_status
):
    redis = _redis_lock()
    diagnostic = _recovery_result().diagnostic.model_copy(
        update={"status": live_status, "root_cause_code": "creation_stalled"}
    )

    def diagnose(conn, volume_id):
        assert conn is mock_conn
        assert volume_id == "vol-1"
        assert redis.set.await_count == 1
        assert redis.delete.await_count == 0
        return diagnostic

    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch(
            "app.services.volume_delete_recovery.diagnose_volume_delete_issue",
            side_effect=diagnose,
        ) as diagnose_mock,
        patch("app.services.cinder.reset_volume_status") as reset,
        patch("app.services.cinder.force_delete_volume") as force_delete,
        patch("app.api.identity.admin._invalidate_volume_recovery_caches", new_callable=AsyncMock) as invalidate,
        patch("app.api.identity.admin.rec", new_callable=AsyncMock) as record,
    ):
        response = await admin_client.post("/api/v1/admin/volumes/vol-1/recover-delete", json=body)

    assert response.status_code == 409
    diagnose_mock.assert_called_once()
    reset.assert_not_called()
    force_delete.assert_not_called()
    mock_conn.block_storage.delete_volume.assert_not_called()
    invalidate.assert_not_awaited()
    redis.delete.assert_awaited_once_with("afterglow:volume-recovery:lock:vol-1")
    assert record.await_args.kwargs["status"] == "failed"
    assert record.await_args.kwargs["extra"]["mode"] == body["mode"]


@pytest.mark.asyncio
async def test_recovery_conflict_detail_does_not_leak_and_releases_lock(admin_client):
    from app.services.volume_delete_recovery import VolumeRecoveryConflict

    redis = _redis_lock()
    secret = "https://service:private-password@storage.internal X-Auth-Token=private-token"
    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch(
            "app.api.identity.admin.volume_delete_recovery.recover_delete_volume",
            side_effect=VolumeRecoveryConflict(secret),
        ),
        patch("app.api.identity.admin._invalidate_volume_recovery_caches", new_callable=AsyncMock) as invalidate,
        patch("app.api.identity.admin.rec", new_callable=AsyncMock) as record,
    ):
        response = await admin_client.post(
            "/api/v1/admin/volumes/vol-1/recover-delete",
            json=_recovery_body(),
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "볼륨 상태 또는 확인 정보가 변경되었습니다. 다시 진단하세요."
    assert secret not in response.text
    assert secret not in str(record.await_args_list)
    invalidate.assert_not_awaited()
    redis.delete.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,step_status,invalidates",
    [
        ("reset_state", "success", True),
        ("restore_name_mapping", "success", True),
        ("cleanup_stale_name_mapping", "success", True),
        ("reset_attach_status", "success", True),
        ("force_delete", "success", True),
        ("reset_state", "failed", False),
        ("restore_name_mapping", "failed", False),
        ("recheck_state", "success", False),
    ],
)
async def test_partial_recovery_failure_invalidates_only_after_successful_mutation(
    admin_client, action, step_status, invalidates
):
    from app.models.storage import VolumeDeleteRecoveryStep

    redis = _redis_lock()
    result = _recovery_result("failed")
    result.previous_status = "downloading"
    result.steps.append(VolumeDeleteRecoveryStep(action=action, status=step_status))
    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch("app.api.identity.admin.volume_delete_recovery.recover_delete_volume", return_value=result),
        patch("app.api.identity.admin._invalidate_volume_recovery_caches", new_callable=AsyncMock) as invalidate,
        patch("app.api.identity.admin.rec", new_callable=AsyncMock) as record,
    ):
        response = await admin_client.post(
            "/api/v1/admin/volumes/vol-1/recover-delete",
            json=_recovery_body("recover", "downloading"),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    if invalidates:
        invalidate.assert_awaited_once_with("proj-abc")
    else:
        invalidate.assert_not_awaited()
    audit = record.await_args.kwargs
    assert audit["status"] == "failed"
    assert audit["error_message"] == "failed"
    assert audit["extra"]["mode"] == "recover"
    assert audit["extra"]["previous_status"] == "downloading"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["recover", "force_delete"])
@pytest.mark.parametrize("lock_state", ["busy", "unavailable"])
async def test_explicit_recovery_modes_fail_closed_before_service(admin_client, mode, lock_state):
    redis = _redis_lock(acquired=False)
    get_redis = AsyncMock(return_value=redis)
    if lock_state == "unavailable":
        get_redis.side_effect = RuntimeError("redis down")
    with (
        patch("app.api.identity.admin._get_redis", new=get_redis),
        patch("app.api.identity.admin.volume_delete_recovery.recover_delete_volume") as recover,
    ):
        response = await admin_client.post(
            "/api/v1/admin/volumes/vol-1/recover-delete",
            json=_recovery_body(mode),
        )

    assert response.status_code == (409 if lock_state == "busy" else 503)
    recover.assert_not_called()
    redis.delete.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["recover", "force_delete"])
async def test_explicit_recovery_modes_require_admin_before_lock(non_admin_client, mode):
    with (
        patch("app.api.identity.admin._get_redis", new_callable=AsyncMock) as get_redis,
        patch("app.api.identity.admin.volume_delete_recovery.recover_delete_volume") as recover,
    ):
        response = await non_admin_client.post(
            "/api/v1/admin/volumes/vol-1/recover-delete",
            json=_recovery_body(mode),
        )

    assert response.status_code == 403
    get_redis.assert_not_awaited()
    recover.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("native_failure", ["revoked", "unauthorized", "unavailable"])
async def test_recovery_keeps_fresh_native_admin_guard_before_lock(admin_client, native_failure):
    from keystoneauth1.exceptions.http import Unauthorized

    from app.api.deps import require_admin
    from app.main import app

    previous = app.dependency_overrides.copy()
    app.dependency_overrides.pop(require_admin)
    native = MagicMock(return_value={"domain_id": "default", "roles": ["admin"]})
    if native_failure == "unauthorized":
        native.side_effect = Unauthorized()
    elif native_failure == "unavailable":
        native.side_effect = RuntimeError("native unavailable")
    try:
        with (
            patch("app.services.domain_scope.domain_context", return_value={}),
            patch("app.services.domain_scope.assert_token_context"),
            patch("app.services.keystone.validate_token", new=native),
            patch("app.services.keystone._is_system_admin", return_value=False) as live_grant,
            patch("app.api.identity.admin._get_redis", new_callable=AsyncMock) as get_redis,
            patch("app.api.identity.admin.volume_delete_recovery.recover_delete_volume") as recover,
        ):
            response = await admin_client.post(
                "/api/v1/admin/volumes/vol-1/recover-delete",
                json=_recovery_body("recover"),
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    expected_status = {"revoked": 403, "unauthorized": 401, "unavailable": 503}[native_failure]
    assert response.status_code == expected_status
    native.assert_called_once()
    if native_failure == "revoked":
        live_grant.assert_called_once()
        assert response.json()["detail"]["code"] == "system_admin_required"
    else:
        live_grant.assert_not_called()
    get_redis.assert_not_awaited()
    recover.assert_not_called()


@pytest.mark.asyncio
async def test_recovery_generic_failure_records_mode_without_leaking_and_releases_lock(admin_client):
    redis = _redis_lock()
    secret = "https://service:private-password@storage.internal X-Auth-Token=private-token"
    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch(
            "app.api.identity.admin.volume_delete_recovery.recover_delete_volume",
            side_effect=RuntimeError(secret),
        ),
        patch("app.api.identity.admin.rec", new_callable=AsyncMock) as record,
    ):
        response = await admin_client.post(
            "/api/v1/admin/volumes/vol-1/recover-delete",
            json=_recovery_body("recover"),
        )

    assert response.status_code == 500
    assert secret not in response.text
    assert secret not in str(record.await_args_list)
    assert record.await_args.kwargs["extra"] == {"mode": "recover", "previous_status": None}
    redis.delete.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["creating", "downloading"])
@pytest.mark.parametrize("mode", ["legacy", "recover"])
async def test_creation_recovery_requires_confirmation_without_native_writes(admin_client, mock_conn, status, mode):
    redis = _redis_lock()
    diagnostic = _recovery_result().diagnostic.model_copy(
        update={"status": status, "root_cause_code": "creation_stalled"}
    )
    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch("app.services.volume_delete_recovery.diagnose_volume_delete_issue", return_value=diagnostic),
        patch("app.services.cinder.reset_volume_status") as reset,
        patch("app.services.cinder.force_delete_volume") as force_delete,
        patch("app.api.identity.admin.rec", new_callable=AsyncMock),
    ):
        kwargs = {} if mode == "legacy" else {"json": {"mode": "recover"}}
        response = await admin_client.post("/api/v1/admin/volumes/vol-1/recover-delete", **kwargs)

    assert response.status_code == 409
    reset.assert_not_called()
    force_delete.assert_not_called()
    mock_conn.block_storage.delete_volume.assert_not_called()
    redis.delete.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["recover", "force_delete"])
async def test_explicit_creation_recovery_rechecks_status_before_first_write(admin_client, mock_conn, mode):
    redis = _redis_lock()
    diagnostic = _recovery_result().diagnostic.model_copy(
        update={"status": "creating", "root_cause_code": "creation_stalled"}
    )
    changed = diagnostic.model_copy(update={"status": "available", "recovery_available": False})
    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch(
            "app.services.volume_delete_recovery.diagnose_volume_delete_issue",
            side_effect=[diagnostic, changed],
        ) as diagnose,
        patch("app.services.cinder.reset_volume_status") as reset,
        patch("app.services.cinder.force_delete_volume") as force_delete,
        patch("app.api.identity.admin._invalidate_volume_recovery_caches", new_callable=AsyncMock) as invalidate,
        patch("app.api.identity.admin.rec", new_callable=AsyncMock),
    ):
        response = await admin_client.post(
            "/api/v1/admin/volumes/vol-1/recover-delete",
            json=_recovery_body(mode),
        )

    assert response.status_code == 409
    assert diagnose.call_count == 2
    reset.assert_not_called()
    force_delete.assert_not_called()
    mock_conn.block_storage.delete_volume.assert_not_called()
    invalidate.assert_not_awaited()
    redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_recovery_audit_failure_does_not_hide_state_reset_or_hold_lock(admin_client):
    redis = _redis_lock()
    result = _recovery_result("state_reset")
    result.previous_status = "creating"
    result.final_status = "error"
    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch("app.api.identity.admin.volume_delete_recovery.recover_delete_volume", return_value=result),
        patch("app.api.identity.admin._invalidate_volume_recovery_caches", new_callable=AsyncMock) as invalidate,
        patch("app.api.identity.admin.rec", new=AsyncMock(side_effect=RuntimeError("audit unavailable"))),
    ):
        response = await admin_client.post(
            "/api/v1/admin/volumes/vol-1/recover-delete",
            json=_recovery_body("recover"),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "state_reset"
    assert response.json()["verified_deleted"] is False
    invalidate.assert_awaited_once_with("proj-abc")
    redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_recover_already_error_is_idempotent_without_confirmation_or_native_writes(admin_client, mock_conn):
    redis = _redis_lock()
    diagnostic = _recovery_result().diagnostic.model_copy(update={"status": "error"})
    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch(
            "app.services.volume_delete_recovery.diagnose_volume_delete_issue",
            return_value=diagnostic,
        ) as diagnose,
        patch("app.services.cinder.reset_volume_status") as reset,
        patch("app.services.cinder.force_delete_volume") as force_delete,
        patch("app.api.identity.admin._invalidate_volume_recovery_caches", new_callable=AsyncMock) as invalidate,
        patch("app.api.identity.admin.rec", new_callable=AsyncMock) as record,
    ):
        response = await admin_client.post(
            "/api/v1/admin/volumes/vol-1/recover-delete",
            json={"mode": "recover"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "state_reset"
    assert body["previous_status"] == "error"
    assert body["final_status"] == "error"
    assert body["verified_deleted"] is False
    assert diagnose.call_count == 2
    reset.assert_not_called()
    force_delete.assert_not_called()
    mock_conn.block_storage.delete_volume.assert_not_called()
    invalidate.assert_awaited_once_with("proj-abc")
    redis.delete.assert_awaited_once()
    assert record.await_args.kwargs["status"] == "success"
    assert record.await_args.kwargs["extra"]["mode"] == "recover"
    assert record.await_args.kwargs["extra"]["previous_status"] == "error"


@pytest.mark.asyncio
async def test_creation_state_change_failure_audits_previous_final_status_and_mode(admin_client):
    from app.models.storage import VolumeDeleteRecoveryStep

    redis = _redis_lock()
    result = _recovery_result("failed")
    result.previous_status = "creating"
    result.final_status = "available"
    result.diagnostic.status = "available"
    result.steps = [
        VolumeDeleteRecoveryStep(action="reset_state", status="success", detail="error"),
        VolumeDeleteRecoveryStep(
            action="verify_after_force_delete", status="failed", detail="creation_delete_state_changed:available"
        ),
    ]
    with (
        patch("app.api.identity.admin._get_redis", new=AsyncMock(return_value=redis)),
        patch("app.api.identity.admin.volume_delete_recovery.recover_delete_volume", return_value=result),
        patch("app.api.identity.admin._invalidate_volume_recovery_caches", new_callable=AsyncMock),
        patch("app.api.identity.admin.rec", new_callable=AsyncMock) as record,
    ):
        response = await admin_client.post("/api/v1/admin/volumes/vol-1/recover-delete", json=_recovery_body())
    assert response.json()["status"] == "failed"
    assert record.await_args.kwargs["extra"]["mode"] == "force_delete"
    assert record.await_args.kwargs["extra"]["previous_status"] == "creating"
    assert record.await_args.kwargs["extra"]["final_status"] == "available"
