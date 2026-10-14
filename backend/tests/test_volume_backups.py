"""볼륨 백업 API 테스트."""

from unittest.mock import AsyncMock, patch

import pytest


def make_backup(bid: str = "backup-1"):
    return {
        "id": bid,
        "name": "test-backup",
        "status": "available",
        "volume_id": "vol-1",
        "size": 10,
        "is_incremental": False,
        "description": "",
        "created_at": "2024-01-01T00:00:00",
    }


@pytest.mark.asyncio
async def test_list_backups(client, mock_conn):
    with patch("app.api.storage.volume_backups.cinder.list_backups", return_value=[make_backup()]):
        resp = await client.get("/api/v1/volumes/backups")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == "backup-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(("volume_status", "force"), [("available", False), ("in-use", True)])
async def test_create_backup(client, mock_conn, volume_status, force):
    mock_conn.block_storage.get_volume.return_value.status = volume_status
    with patch("app.api.storage.volume_backups.cinder.create_backup", return_value=make_backup("backup-new")):
        resp = await client.post(
            "/api/v1/volumes/backups", json={"volume_id": "vol-1", "name": "my-backup", "force": force}
        )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_in_use_backup_requires_explicit_force_without_provider_mutation(client, mock_conn):
    mock_conn.block_storage.get_volume.return_value.status = "in-use"
    with patch("app.api.storage.volume_backups.cinder.create_backup") as create:
        resp = await client.post("/api/v1/volumes/backups", json={"volume_id": "vol-1", "name": "my-backup"})
    assert resp.status_code == 400
    create.assert_not_called()


@pytest.mark.asyncio
async def test_delete_backup(client, mock_conn):
    with patch("app.api.storage.volume_backups.cinder.delete_backup", return_value=None):
        resp = await client.delete("/api/v1/volumes/backups/backup-1")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_backup_not_shadowed_by_volumes_route(client, mock_conn):
    """볼륨 라우터가 /backups를 가로채지 않음을 확인 (Task 1 버그 수정)."""
    with patch("app.api.storage.volume_backups.cinder.list_backups", return_value=[make_backup()]):
        resp = await client.get("/api/v1/volumes/backups")
    # 404가 아닌 200이어야 함
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_restore_backup_creates_new_volume(client, mock_conn):
    """body 미전달 시 새 볼륨으로 복원하고 volume_id를 반환한다."""
    with patch(
        "app.api.storage.volume_backups.cinder.restore_backup",
        return_value={"volume_id": "vol-restored", "volume_name": "restored-vol"},
    ) as mock_restore:
        resp = await client.post("/api/v1/volumes/backups/backup-1/restore")
    assert resp.status_code == 200
    assert resp.json()["volume_id"] == "vol-restored"
    mock_restore.assert_called_once_with(mock_conn, "backup-1", None)


@pytest.mark.asyncio
async def test_restore_backup_to_existing_volume(client, mock_conn):
    """volume_id 지정 시 해당 볼륨에 복원 요청한다."""
    with patch(
        "app.api.storage.volume_backups.cinder.restore_backup",
        return_value={"volume_id": "vol-target", "volume_name": "target-vol"},
    ) as mock_restore:
        resp = await client.post("/api/v1/volumes/backups/backup-1/restore", json={"volume_id": "vol-target"})
    assert resp.status_code == 200
    mock_restore.assert_called_once_with(mock_conn, "backup-1", "vol-target")


@pytest.mark.asyncio
async def test_create_backup_sdk_error_propagates_status(client, mock_conn):
    """Cinder HttpException 발생 시 status_code + 실제 메시지가 전달된다."""
    from openstack.exceptions import HttpException

    with (
        patch(
            "app.api.storage.volume_backups.cinder.create_backup",
            side_effect=HttpException(message="Invalid backup request", http_status=400),
        ),
        patch("app.api.storage.volume_backups.rec", new_callable=AsyncMock),
    ):
        resp = await client.post("/api/v1/volumes/backups", json={"volume_id": "vol-1", "name": "bad-backup"})
    assert resp.status_code == 400
    assert "Invalid backup request" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_backup_cached(client, mock_conn):
    """GET /{backup_id} 는 cached_call 을 통해 반환된다."""
    with patch("app.api.storage.volume_backups.cinder.get_backup", return_value=make_backup()) as mock_get:
        resp = await client.get("/api/v1/volumes/backups/backup-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "backup-1"
    mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_create_backup_invalidates_cache(client, mock_conn):
    """백업 생성 후 backups* 패턴 무효화 + mutation count 증가."""
    with (
        patch("app.api.storage.volume_backups.cinder.create_backup", return_value=make_backup("backup-new")),
        patch("app.api.storage.volume_backups.invalidate", new_callable=AsyncMock) as mock_inv,
        patch(
            "app.api.storage.volume_backups.invalidation.invalidate_mutation_count", new_callable=AsyncMock
        ) as mock_mut,
        patch("app.api.storage.volume_backups.rec", new_callable=AsyncMock),
    ):
        resp = await client.post("/api/v1/volumes/backups", json={"volume_id": "vol-1", "name": "my-backup"})
    assert resp.status_code == 201
    mock_inv.assert_called_once_with("afterglow:cinder:test-project-123:backups*")
    mock_mut.assert_called_once_with("cinder", "test-project-123")


@pytest.mark.asyncio
async def test_delete_backup_invalidates_cache(client, mock_conn):
    """백업 삭제 후 backups* 패턴 무효화 + mutation count 증가."""
    with (
        patch("app.api.storage.volume_backups.cinder.delete_backup", return_value=None),
        patch("app.api.storage.volume_backups.invalidate", new_callable=AsyncMock) as mock_inv,
        patch(
            "app.api.storage.volume_backups.invalidation.invalidate_mutation_count", new_callable=AsyncMock
        ) as mock_mut,
        patch("app.api.storage.volume_backups.rec", new_callable=AsyncMock),
    ):
        resp = await client.delete("/api/v1/volumes/backups/backup-1")
    assert resp.status_code == 204
    mock_inv.assert_called_once_with("afterglow:cinder:test-project-123:backups*")
    mock_mut.assert_called_once_with("cinder", "test-project-123")


@pytest.mark.asyncio
async def test_restore_backup_invalidates_cache(client, mock_conn):
    """백업 복원 후 backups* 패턴 무효화 + mutation count 증가."""
    with (
        patch(
            "app.api.storage.volume_backups.cinder.restore_backup",
            return_value={"volume_id": "vol-restored", "volume_name": "restored-vol"},
        ),
        patch("app.api.storage.volume_backups.invalidate", new_callable=AsyncMock) as mock_inv,
        patch(
            "app.api.storage.volume_backups.invalidation.invalidate_mutation_count", new_callable=AsyncMock
        ) as mock_mut,
        patch("app.api.storage.volume_backups.rec", new_callable=AsyncMock),
    ):
        resp = await client.post("/api/v1/volumes/backups/backup-1/restore")
    assert resp.status_code == 200
    mock_inv.assert_called_once_with("afterglow:cinder:test-project-123:backups*")
    mock_mut.assert_called_once_with("cinder", "test-project-123")


@pytest.mark.asyncio
async def test_schedule_save_get_list_pause_resume_remove_are_persisted_without_immediate_backup(client, mock_conn):
    mock_conn.block_storage.get_volume.return_value.status = "available"
    url = "/api/v1/volumes/backups/auto-backup/vol-1"
    body = {
        "max_daily": 3,
        "max_weekly": 0,
        "max_monthly": 1,
        "schedule_time": "17:45",
        "timezone": "Asia/Seoul",
        "weekly_day": 3,
        "monthly_day": 15,
        "force": False,
    }
    with patch("app.api.storage.volume_backups.cinder.create_backup") as create:
        saved = await client.post(url, json=body)
        assert saved.status_code == 201
        config = saved.json()
        assert all(config[field] == value for field, value in body.items())
        assert config["next_run_at"] is not None and config["last_status"] == "never"
        fetched = await client.get(url)
        assert fetched.status_code == 200 and fetched.json() == config
        listed = await client.post("/api/v1/volumes/backups/auto-backup/configs")
        assert listed.status_code == 200 and listed.json() == [config]
        paused = await client.post(url, json={**body, "enabled": False})
        assert paused.status_code == 201 and paused.json()["next_run_at"] is None
        resumed = await client.post(url, json=body)
        assert resumed.status_code == 201 and resumed.json()["enabled"] is True
        assert resumed.json()["next_run_at"] is not None
        removed = await client.delete(url)
        assert removed.status_code == 204
        assert (await client.get(url)).status_code == 404
        assert (await client.post("/api/v1/volumes/backups/auto-backup/configs")).json() == []
        create.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_force_is_explicit_and_pause_needs_no_force(client, mock_conn):
    mock_conn.block_storage.get_volume.return_value.status = "in-use"
    url = "/api/v1/volumes/backups/auto-backup/vol-1"
    refused = await client.post(url, json={})
    assert refused.status_code == 400
    assert (await client.get(url)).status_code == 404
    accepted = await client.post(url, json={"force": True})
    assert accepted.status_code == 201 and accepted.json()["force"] is True
    paused = await client.post(url, json={"enabled": False, "force": False})
    assert paused.status_code == 201 and paused.json()["enabled"] is False
    mock_conn.block_storage.get_volume.return_value.status = "backing-up"
    assert (await client.post(url, json={})).status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"max_daily": -1},
        {"max_monthly": 31},
        {"max_daily": 0, "max_weekly": 0, "max_monthly": 0},
        {"schedule_time": "24:00"},
        {"timezone": "Unknown/Zone"},
        {"weekly_day": 7},
        {"monthly_day": 29},
        {"force": "true"},
    ],
)
async def test_invalid_schedule_does_not_persist_or_submit(client, mock_conn, body):
    mock_conn.block_storage.get_volume.return_value.status = "available"
    url = "/api/v1/volumes/backups/auto-backup/vol-1"
    assert (await client.post(url, json=body)).status_code == 422
    assert (await client.get(url)).status_code == 404


@pytest.mark.asyncio
async def test_schedule_reader_can_read_but_cannot_save_pause_or_remove(client, mock_conn):
    from app.api.deps import get_token_info
    from app.main import app
    from tests.conftest import make_token_info

    mock_conn.block_storage.get_volume.return_value.status = "available"
    url = "/api/v1/volumes/backups/auto-backup/vol-1"
    assert (await client.post(url, json={})).status_code == 201
    app.dependency_overrides[get_token_info] = lambda: make_token_info(roles=["reader"])
    assert (await client.get(url)).status_code == 200
    assert (await client.post("/api/v1/volumes/backups/auto-backup/configs")).status_code == 200
    assert (await client.post(url, json={})).status_code == 403
    assert (await client.post(url, json={"enabled": False})).status_code == 403
    assert (await client.delete(url)).status_code == 403
    assert (await client.get(url)).json()["enabled"] is True


@pytest.mark.asyncio
async def test_schedule_store_failure_is_unavailable_not_empty_or_disabled(client, mock_conn):
    mock_conn.block_storage.get_volume.return_value.status = "available"
    with patch("app.services.auto_backup._get_redis", side_effect=RuntimeError("private endpoint")):
        for method, url, body in (
            ("get", "/api/v1/volumes/backups/auto-backup/vol-1", None),
            ("post", "/api/v1/volumes/backups/auto-backup/configs", None),
            ("post", "/api/v1/volumes/backups/auto-backup/vol-1", {}),
            ("delete", "/api/v1/volumes/backups/auto-backup/vol-1", None),
        ):
            response = await client.request(method, url, json=body)
            assert response.status_code == 503
            assert "private endpoint" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_kind", ["resource_not_found", "http404", "none"])
async def test_missing_source_policy_remains_visible_and_can_be_removed_without_backup_mutation(
    client, mock_conn, missing_kind
):
    from openstack.exceptions import HttpException, ResourceNotFound

    from app.services import auto_backup

    mock_conn.block_storage.get_volume.return_value.status = "available"
    url = "/api/v1/volumes/backups/auto-backup/vol-1"
    saved = (await client.post(url, json={"max_daily": 3, "force": True})).json()
    if missing_kind == "none":
        mock_conn.block_storage.get_volume.return_value = None
    else:
        mock_conn.block_storage.get_volume.side_effect = (
            ResourceNotFound("private source path")
            if missing_kind == "resource_not_found"
            else HttpException(message="private source path", http_status=404)
        )
    with patch("app.api.storage.volume_backups.cinder.delete_backup") as delete_backup:
        listed = await client.post("/api/v1/volumes/backups/auto-backup/configs")
        assert listed.status_code == 200
        policy = listed.json()[0]
        assert policy["volume_id"] == "vol-1" and policy["max_daily"] == 3
        assert policy["enabled"] is True and policy["force"] is True
        assert policy["source_status"] == "missing" and policy["source_available"] is False
        assert policy["last_error"] and "private source path" not in listed.text
        persisted = await auto_backup.get_auto_backup_config(mock_conn._afterglow_project_id, "vol-1")
        assert persisted == saved  # source observation did not fake a disabled/error policy.
        assert (await client.delete(url)).status_code == 204
        assert await auto_backup.get_auto_backup_config(mock_conn._afterglow_project_id, "vol-1") is None
        delete_backup.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_kind,delete_status,source_status",
    [
        ("timeout", 503, "unavailable"),
        ("http503", 503, "unavailable"),
        ("http403", 403, "not_owned"),
        ("foreign", 404, "not_owned"),
        ("missing_owner", 404, "not_owned"),
    ],
)
async def test_source_outage_or_unproven_ownership_is_not_permission_to_remove_policy(
    client, mock_conn, failure_kind, delete_status, source_status
):
    from openstack.exceptions import HttpException

    from app.services import auto_backup

    mock_conn.block_storage.get_volume.return_value.status = "available"
    url = "/api/v1/volumes/backups/auto-backup/vol-1"
    saved_response = await client.post(url, json={"max_weekly": 4})
    assert saved_response.status_code == 201
    saved = saved_response.json()
    if failure_kind == "timeout":
        mock_conn.block_storage.get_volume.side_effect = TimeoutError("private source endpoint")
    elif failure_kind.startswith("http"):
        mock_conn.block_storage.get_volume.side_effect = HttpException(
            message="private source endpoint", http_status=int(failure_kind[4:])
        )
    else:
        mock_conn.block_storage.get_volume.return_value.project_id = (
            "foreign-project" if failure_kind == "foreign" else None
        )
    listed = await client.post("/api/v1/volumes/backups/auto-backup/configs")
    assert listed.status_code == 200
    policy = listed.json()[0]
    assert policy["enabled"] is True and policy["max_weekly"] == 4
    assert policy["source_status"] == source_status
    assert "private source endpoint" not in listed.text
    assert (await client.delete(url)).status_code == delete_status
    assert await auto_backup.get_auto_backup_config(mock_conn._afterglow_project_id, "vol-1") == saved


@pytest.mark.asyncio
async def test_orphan_removal_rejects_policy_with_unproven_persisted_owner(client, mock_conn):
    from app.services import auto_backup
    from app.services.cache import _get_redis

    mock_conn.block_storage.get_volume.return_value.status = "available"
    url = "/api/v1/volumes/backups/auto-backup/vol-1"
    saved_response = await client.post(url, json={})
    assert saved_response.status_code == 201
    config = saved_response.json()
    config["project_id"] = "foreign-project"
    raw = auto_backup._dump(config)
    redis = await _get_redis()
    key = auto_backup._key("config", mock_conn._afterglow_project_id, "vol-1")
    await redis.set(key, raw)
    mock_conn.block_storage.get_volume.return_value = None
    assert (await client.delete(url)).status_code == 404
    assert await redis.get(key) == raw


@pytest.mark.asyncio
async def test_scheduled_backup_and_completion_refresh_warm_inventory(client, mock_conn):
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    from app.services import auto_backup

    project_id = mock_conn._afterglow_project_id
    mock_conn.block_storage.get_volume.return_value.status = "available"
    records = {}
    mock_conn.block_storage.backups.side_effect = lambda **kwargs: list(records.values())
    mock_conn.block_storage.get_backup.side_effect = lambda backup_id: records[backup_id]

    def create(**fields):
        backup = SimpleNamespace(
            id="scheduled-new",
            name=fields["name"],
            status="creating",
            volume_id="vol-1",
            project_id=project_id,
            size=10,
            is_incremental=False,
            has_dependent_backups=False,
            description="",
            created_at="2026-06-01T03:00:00+00:00",
        )
        records[backup.id] = backup
        return backup

    mock_conn.block_storage.create_backup.side_effect = create
    policy = await auto_backup.enable_auto_backup(
        project_id, "vol-1", 2, 0, 0, now=datetime(2026, 5, 31, 12, tzinfo=UTC)
    )
    url = "/api/v1/volumes/backups?cache=true"
    assert (await client.get(url)).json() == []
    due = datetime.fromisoformat(policy["next_run_at"])
    await auto_backup.run_backup_cycle(mock_conn, project_id, "vol-1", now=due)
    creating = (await client.get(url)).json()
    assert [(row["id"], row["status"]) for row in creating] == [("scheduled-new", "creating")]
    records["scheduled-new"].status = "available"
    await auto_backup.run_backup_cycle(mock_conn, project_id, "vol-1", now=due + timedelta(seconds=15))
    completed = (await client.get(url)).json()
    assert [(row["id"], row["status"]) for row in completed] == [("scheduled-new", "available")]
