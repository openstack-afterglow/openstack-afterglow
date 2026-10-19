"""볼륨 스냅샷 API 단위 테스트."""

from unittest.mock import AsyncMock, patch

import pytest


def _make_volume_in_use():
    from unittest.mock import MagicMock

    vol = MagicMock()
    vol.project_id = "test-project-123"
    vol.tenant_id = None
    vol.status = "in-use"
    return vol


def make_snapshot(snap_id: str = "snap-1", name: str = "test-snap", project_id: str = "test-project-123") -> dict:
    return {
        "id": snap_id,
        "name": name,
        "status": "available",
        "size": 10,
        "volume_id": "vol-1",
        "created_at": "2024-01-01T00:00:00Z",
        "description": None,
        "project_id": project_id,
    }


@pytest.mark.asyncio
async def test_list_snapshots(client, mock_conn):
    """일반 사용자 — caller_project_id=pid 로 호출되어 해당 프로젝트 스냅샷만 반환."""
    with patch("app.api.storage.volume_snapshots.cinder.list_snapshots", return_value=[make_snapshot()]) as mock_ls:
        resp = await client.get("/api/v1/volume-snapshots")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert resp.json()[0]["id"] == "snap-1"
    # caller_project_id 인자로 pid("test-project-123")가 전달돼야 함
    _args, kwargs = mock_ls.call_args
    assert kwargs.get("caller_project_id") == "test-project-123" or _args[2] == "test-project-123"


@pytest.mark.asyncio
async def test_list_snapshots_admin_sees_all(admin_client, mock_conn):
    """시스템 관리자 — caller_project_id=None 으로 호출되어 전체 스냅샷 반환."""
    other_snap = make_snapshot("snap-2", project_id="other-project")
    with patch(
        "app.api.storage.volume_snapshots.cinder.list_snapshots", return_value=[make_snapshot(), other_snap]
    ) as mock_ls:
        resp = await admin_client.get("/api/v1/volume-snapshots")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    _args, kwargs = mock_ls.call_args
    assert kwargs.get("caller_project_id") is None or (len(_args) > 2 and _args[2] is None)


@pytest.mark.asyncio
async def test_list_snapshots_filters_other_project(client, mock_conn):
    """일반 사용자 — 다른 프로젝트 스냅샷은 cinder.list_snapshots 내부에서 제외됨."""
    own_snap = make_snapshot("snap-own", project_id="test-project-123")
    # 서비스가 필터링 후 own_snap만 반환한다고 모킹
    with patch("app.api.storage.volume_snapshots.cinder.list_snapshots", return_value=[own_snap]):
        resp = await client.get("/api/v1/volume-snapshots")
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()]
    assert "snap-own" in ids
    assert "snap-other" not in ids


@pytest.mark.asyncio
async def test_create_snapshot(client, mock_conn):
    with patch("app.api.storage.volume_snapshots.cinder.create_snapshot", return_value=make_snapshot("snap-new")):
        resp = await client.post(
            "/api/v1/volume-snapshots",
            json={
                "volume_id": "vol-1",
                "name": "test-snap",
                "description": "",
                "force": False,
            },
        )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_get_snapshot(client, mock_conn):
    with patch("app.api.storage.volume_snapshots.cinder.get_snapshot", return_value=make_snapshot()):
        resp = await client.get("/api/v1/volume-snapshots/snap-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "snap-1"


@pytest.mark.asyncio
async def test_delete_snapshot(client, mock_conn):
    with patch("app.api.storage.volume_snapshots.cinder.delete_snapshot", return_value=None):
        resp = await client.delete("/api/v1/volume-snapshots/snap-1")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_get_snapshot_cached(client, mock_conn):
    """GET /{snapshot_id} 는 cached_call 을 통해 반환된다."""
    with patch("app.api.storage.volume_snapshots.cinder.get_snapshot", return_value=make_snapshot()) as mock_get:
        resp = await client.get("/api/v1/volume-snapshots/snap-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "snap-1"
    mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_create_snapshot_invalidates_cache(client, mock_conn):
    """스냅샷 생성 후 snapshots* 패턴 무효화 + mutation count 증가."""
    with (
        patch("app.api.storage.volume_snapshots.cinder.create_snapshot", return_value=make_snapshot("snap-new")),
        patch("app.api.storage.volume_snapshots.invalidate", new_callable=AsyncMock) as mock_inv,
        patch(
            "app.api.storage.volume_snapshots.invalidation.invalidate_mutation_count", new_callable=AsyncMock
        ) as mock_mut,
        patch("app.api.storage.volume_snapshots.rec", new_callable=AsyncMock),
    ):
        resp = await client.post(
            "/api/v1/volume-snapshots",
            json={"volume_id": "vol-1", "name": "snap-new", "force": False},
        )
    assert resp.status_code == 201
    mock_inv.assert_called_once_with("afterglow:cinder:test-project-123:snapshots*")
    mock_mut.assert_called_once_with("cinder", "test-project-123")


@pytest.mark.asyncio
async def test_delete_snapshot_invalidates_cache(client, mock_conn):
    """스냅샷 삭제 후 snapshots* 패턴 무효화 + mutation count 증가."""
    with (
        patch("app.api.storage.volume_snapshots.cinder.delete_snapshot", return_value=None),
        patch("app.api.storage.volume_snapshots.invalidate", new_callable=AsyncMock) as mock_inv,
        patch(
            "app.api.storage.volume_snapshots.invalidation.invalidate_mutation_count", new_callable=AsyncMock
        ) as mock_mut,
        patch("app.api.storage.volume_snapshots.rec", new_callable=AsyncMock),
    ):
        resp = await client.delete("/api/v1/volume-snapshots/snap-1")
    assert resp.status_code == 204
    mock_inv.assert_called_once_with("afterglow:cinder:test-project-123:snapshots*")
    mock_mut.assert_called_once_with("cinder", "test-project-123")


@pytest.mark.asyncio
async def test_create_snapshot_in_use_without_force_returns_400(client, mock_conn):
    """in-use 볼륨에 force=False 로 스냅샷 생성 시 Cinder 400 메시지가 그대로 전달된다."""
    from openstack.exceptions import BadRequestException

    mock_conn.block_storage.get_volume.return_value = _make_volume_in_use()
    with (
        patch(
            "app.api.storage.volume_snapshots.cinder.create_snapshot",
            side_effect=BadRequestException(
                message="Invalid volume: Volume is in use, force snapshot is required",
                http_status=400,
            ),
        ),
        patch("app.api.storage.volume_snapshots.rec", new_callable=AsyncMock),
    ):
        resp = await client.post(
            "/api/v1/volume-snapshots",
            json={"volume_id": "vol-1", "name": "snap-fail", "force": False},
        )
    assert resp.status_code == 400
    assert "force" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_auto_snapshot_policy_lifecycle_never_submits_or_deletes_snapshots(client, mock_conn):
    mock_conn.block_storage.get_volume.return_value.status = "available"
    url = "/api/v1/volume-snapshots/auto-snapshot/vol-1"
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
    with (
        patch("app.api.storage.volume_snapshots.cinder.create_snapshot") as create,
        patch("app.api.storage.volume_snapshots.cinder.delete_snapshot") as delete,
        patch("app.api.storage.volume_snapshots.rec", new_callable=AsyncMock) as record,
    ):
        assert (await client.get(url)).status_code == 404
        saved = await client.post(url, json=body)
        assert saved.status_code == 201
        config = saved.json()
        assert all(config[field] == value for field, value in body.items())
        assert config["project_id"] == mock_conn._afterglow_project_id
        assert config["volume_id"] == "vol-1"
        assert config["next_run_at"] is not None and config["last_status"] == "never"
        fetched = await client.get(url)
        assert fetched.status_code == 200 and fetched.json() == config
        listed = await client.post("/api/v1/volume-snapshots/auto-snapshot/configs")
        assert listed.status_code == 200 and listed.json() == [config]
        paused = await client.post(url, json={**body, "enabled": False})
        assert paused.status_code == 201 and paused.json()["next_run_at"] is None
        resumed = await client.post(url, json={**body, "schedule_time": "18:15"})
        assert resumed.status_code == 201 and resumed.json()["enabled"] is True
        assert resumed.json()["schedule_time"] == "18:15" and resumed.json()["next_run_at"] is not None
        assert (await client.delete(url)).status_code == 204
        assert (await client.get(url)).status_code == 404
        assert (await client.post("/api/v1/volume-snapshots/auto-snapshot/configs")).json() == []
        assert [call.kwargs["action"] for call in record.await_args_list] == [
            "volume.auto_snapshot_enable",
            "volume.auto_snapshot_enable",
            "volume.auto_snapshot_enable",
            "volume.auto_snapshot_disable",
        ]
        create.assert_not_called()
        delete.assert_not_called()
        mock_conn.block_storage.get_snapshot.assert_not_called()


@pytest.mark.asyncio
async def test_auto_snapshot_force_requires_fresh_explicit_consent_and_pause_needs_none(client, mock_conn):
    mock_conn.block_storage.get_volume.return_value.status = "in-use"
    url = "/api/v1/volume-snapshots/auto-snapshot/vol-1"
    with patch("app.api.storage.volume_snapshots.cinder.create_snapshot") as create:
        assert (await client.post(url, json={})).status_code == 400
        assert (await client.get(url)).status_code == 404
        accepted = await client.post(url, json={"force": True})
        assert accepted.status_code == 201 and accepted.json()["force"] is True
        # Previously saved consent must not authorize a later request that omits it.
        assert (await client.post(url, json={"max_daily": 4})).status_code == 400
        assert (await client.get(url)).json() == accepted.json()
        paused = await client.post(url, json={"enabled": False, "force": False})
        assert paused.status_code == 201 and paused.json()["enabled"] is False
        mock_conn.block_storage.get_volume.return_value.status = "creating"
        assert (await client.post(url, json={})).status_code == 400
        assert (await client.post(url, json={"enabled": False})).status_code == 201
        create.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"max_daily": -1},
        {"max_monthly": 31},
        {"max_daily": True},
        {"max_daily": 0, "max_weekly": 0, "max_monthly": 0},
        {"schedule_time": "24:00"},
        {"timezone": "Unknown/Zone"},
        {"weekly_day": 7},
        {"monthly_day": 29},
        {"force": "true"},
        {"enabled": "false"},
    ],
)
async def test_auto_snapshot_invalid_settings_never_persist_or_submit(client, mock_conn, body):
    mock_conn.block_storage.get_volume.return_value.status = "available"
    url = "/api/v1/volume-snapshots/auto-snapshot/vol-1"
    with patch("app.api.storage.volume_snapshots.cinder.create_snapshot") as create:
        assert (await client.post(url, json=body)).status_code == 422
        assert (await client.get(url)).status_code == 404
        create.assert_not_called()


@pytest.mark.asyncio
async def test_auto_snapshot_reader_can_read_but_cannot_save_pause_or_remove(client, mock_conn):
    from app.api.deps import get_token_info
    from app.main import app
    from tests.conftest import make_token_info

    mock_conn.block_storage.get_volume.return_value.status = "available"
    url = "/api/v1/volume-snapshots/auto-snapshot/vol-1"
    assert (await client.post(url, json={})).status_code == 201
    app.dependency_overrides[get_token_info] = lambda: make_token_info(roles=["reader"])
    assert (await client.get(url)).status_code == 200
    assert (await client.post("/api/v1/volume-snapshots/auto-snapshot/configs")).status_code == 200
    assert (await client.post(url, json={})).status_code == 403
    assert (await client.post(url, json={"enabled": False})).status_code == 403
    assert (await client.delete(url)).status_code == 403
    assert (await client.get(url)).json()["enabled"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("project_id", ["foreign-project", None])
async def test_auto_snapshot_even_admin_cannot_schedule_or_remove_unowned_source(admin_client, mock_conn, project_id):
    mock_conn.block_storage.get_volume.return_value.status = "available"
    mock_conn.block_storage.get_volume.return_value.project_id = project_id
    url = "/api/v1/volume-snapshots/auto-snapshot/vol-1"
    with (
        patch("app.api.storage.volume_snapshots.auto_snapshot.get_auto_snapshot_config", new_callable=AsyncMock) as get,
        patch("app.api.storage.volume_snapshots.auto_snapshot.enable_auto_snapshot", new_callable=AsyncMock) as enable,
        patch(
            "app.api.storage.volume_snapshots.auto_snapshot.disable_auto_snapshot", new_callable=AsyncMock
        ) as disable,
    ):
        assert (await admin_client.get(url)).status_code == 404
        assert (await admin_client.post(url, json={})).status_code == 404
        assert (await admin_client.delete(url)).status_code == 404
        get.assert_not_awaited()
        enable.assert_not_awaited()
        disable.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,body,service_method",
    [
        ("get", "vol-1", None, "get_auto_snapshot_config"),
        ("post", "configs", None, "list_auto_snapshot_configs"),
        ("post", "vol-1", {}, "enable_auto_snapshot"),
        ("delete", "vol-1", None, "disable_auto_snapshot"),
    ],
)
async def test_auto_snapshot_store_failure_is_unavailable_not_empty_or_disabled(
    client, mock_conn, method, path, body, service_method
):
    mock_conn.block_storage.get_volume.return_value.status = "available"
    with patch(
        f"app.api.storage.volume_snapshots.auto_snapshot.{service_method}",
        new_callable=AsyncMock,
        side_effect=RuntimeError("private endpoint"),
    ):
        response = await client.request(method, f"/api/v1/volume-snapshots/auto-snapshot/{path}", json=body)
    assert response.status_code == 503
    assert "private endpoint" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_kind", ["resource_not_found", "http404", "none"])
async def test_auto_snapshot_missing_source_policy_visible_and_removable_without_snapshot_mutation(
    client, mock_conn, missing_kind
):
    from openstack.exceptions import HttpException, ResourceNotFound

    from app.services import auto_snapshot

    mock_conn.block_storage.get_volume.return_value.status = "available"
    url = "/api/v1/volume-snapshots/auto-snapshot/vol-1"
    saved_response = await client.post(url, json={"max_daily": 3, "force": True})
    assert saved_response.status_code == 201
    saved = saved_response.json()
    if missing_kind == "none":
        mock_conn.block_storage.get_volume.return_value = None
    else:
        mock_conn.block_storage.get_volume.side_effect = (
            ResourceNotFound("private source path")
            if missing_kind == "resource_not_found"
            else HttpException(message="private source path", http_status=404)
        )
    with patch("app.api.storage.volume_snapshots.cinder.delete_snapshot") as delete:
        assert (await client.get(url)).status_code == 404
        assert (await client.post(url, json={})).status_code == 404
        listed = await client.post("/api/v1/volume-snapshots/auto-snapshot/configs")
        assert listed.status_code == 200
        policy = listed.json()[0]
        assert policy["volume_id"] == "vol-1" and policy["max_daily"] == 3
        assert policy["enabled"] is True and policy["force"] is True
        assert policy["source_status"] == "missing" and policy["source_available"] is False
        assert policy["last_error"] and "private source path" not in listed.text
        assert await auto_snapshot.get_auto_snapshot_config(mock_conn._afterglow_project_id, "vol-1") == saved
        assert (await client.delete(url)).status_code == 204
        assert await auto_snapshot.get_auto_snapshot_config(mock_conn._afterglow_project_id, "vol-1") is None
        delete.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_kind,expected_status,source_status",
    [
        ("timeout", 503, "unavailable"),
        ("http503", 503, "unavailable"),
        ("http401", 401, "not_owned"),
        ("http403", 403, "not_owned"),
        ("foreign", 404, "not_owned"),
        ("missing_owner", 404, "not_owned"),
    ],
)
async def test_auto_snapshot_source_failure_never_changes_policy(
    client, mock_conn, failure_kind, expected_status, source_status
):
    from openstack.exceptions import HttpException

    from app.services import auto_snapshot

    mock_conn.block_storage.get_volume.return_value.status = "available"
    url = "/api/v1/volume-snapshots/auto-snapshot/vol-1"
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
    listed = await client.post("/api/v1/volume-snapshots/auto-snapshot/configs")
    assert listed.status_code == 200
    policy = listed.json()[0]
    assert policy["enabled"] is True and policy["max_weekly"] == 4
    assert policy["source_status"] == source_status
    assert "private source endpoint" not in listed.text
    for method, body in (("get", None), ("post", {}), ("delete", None)):
        response = await client.request(method, url, json=body)
        assert response.status_code == expected_status
        assert "private source endpoint" not in response.text
    assert await auto_snapshot.get_auto_snapshot_config(mock_conn._afterglow_project_id, "vol-1") == saved


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity", [{"project_id": "foreign-project"}, {"volume_id": "other-volume"}, {"identity_verified": False}]
)
async def test_auto_snapshot_orphan_removal_requires_verified_saved_identity(client, mock_conn, identity):
    mock_conn.block_storage.get_volume.return_value = None
    config = {"project_id": mock_conn._afterglow_project_id, "volume_id": "vol-1", **identity}
    with (
        patch(
            "app.api.storage.volume_snapshots.auto_snapshot.get_auto_snapshot_config",
            new_callable=AsyncMock,
            return_value=config,
        ),
        patch(
            "app.api.storage.volume_snapshots.auto_snapshot.disable_auto_snapshot", new_callable=AsyncMock
        ) as disable,
    ):
        assert (await client.delete("/api/v1/volume-snapshots/auto-snapshot/vol-1")).status_code == 404
        disable.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", [{"project_id": "foreign-project"}, {"identity_verified": False}])
async def test_auto_snapshot_list_rejects_unverified_saved_identity(client, mock_conn, identity):
    config = {"project_id": mock_conn._afterglow_project_id, "volume_id": "vol-1", **identity}
    with patch(
        "app.api.storage.volume_snapshots.auto_snapshot.list_auto_snapshot_configs",
        new_callable=AsyncMock,
        return_value=[config],
    ):
        response = await client.post("/api/v1/volume-snapshots/auto-snapshot/configs")
    assert response.status_code == 503
    mock_conn.block_storage.get_volume.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["post", "delete"])
async def test_auto_snapshot_preserves_service_admission_fence(client, mock_conn, method):
    from fastapi import HTTPException

    mock_conn.block_storage.get_volume.return_value.status = "available"
    service_method = "enable_auto_snapshot" if method == "post" else "disable_auto_snapshot"
    with patch(
        f"app.api.storage.volume_snapshots.auto_snapshot.{service_method}",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=409, detail="Policy admission fenced"),
    ):
        response = await client.request(
            method, "/api/v1/volume-snapshots/auto-snapshot/vol-1", json={} if method == "post" else None
        )
    assert response.status_code == 409
    assert response.json()["detail"] == "Policy admission fenced"


@pytest.mark.asyncio
async def test_manual_snapshot_force_still_passes_through_without_touching_policy(client, mock_conn):
    mock_conn.block_storage.get_volume.return_value = _make_volume_in_use()
    with (
        patch("app.api.storage.volume_snapshots.cinder.create_snapshot", return_value=make_snapshot()) as create,
        patch("app.api.storage.volume_snapshots.auto_snapshot.enable_auto_snapshot", new_callable=AsyncMock) as enable,
    ):
        response = await client.post(
            "/api/v1/volume-snapshots", json={"volume_id": "vol-1", "name": "manual", "force": True}
        )
    assert response.status_code == 201
    create.assert_called_once_with(mock_conn, "vol-1", "manual", None, True)
    enable.assert_not_awaited()
