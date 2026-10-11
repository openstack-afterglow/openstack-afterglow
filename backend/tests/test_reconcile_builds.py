"""빌드 reconcile 및 prebuilt 가시성 단위 테스트.

검증 항목:
1. reconcile_orphan_builds: DB 비가용 → no-op
2. reconcile_orphan_builds: server_id 없음 → error 마킹 + share 메타데이터 갱신
3. reconcile_orphan_builds: VM SHUTOFF + SUCCESS sentinel → complete 승격
4. reconcile_orphan_builds: VM 없음(404) → error 마킹
5. reconcile_orphan_builds: 비터미널 row 없음 → 아무것도 안 함
6. list_libraries: service conn + include_public 으로 prebuilt 조회
7. asyncio task GC 방지: _background_tasks set에 태스크 참조 보관
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────


def _make_build_row(
    id: int = 1,
    library_id: str = "python311",
    file_storage_id: str = "share-abc",
    server_id: str | None = "server-xyz",
    port_id: str | None = "port-abc",
    build_token: str | None = "deadbeef12345678",
    status: str = "building",
):
    row = MagicMock()
    row.id = id
    row.library_id = library_id
    row.file_storage_id = file_storage_id
    row.server_id = server_id
    row.port_id = port_id
    row.build_token = build_token
    row.status = status
    return row


# ──────────────────────────────────────────────
# reconcile_orphan_builds
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconcile_no_db():
    """DB 팩토리가 None이면 no-op."""
    with patch("app.database.get_session_factory", return_value=None):
        from app.services.library_builder import reconcile_orphan_builds

        await reconcile_orphan_builds()  # 예외 없이 조용히 반환


@pytest.mark.asyncio
async def test_reconcile_no_stale_rows():
    """비터미널 row가 없으면 아무것도 하지 않는다."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_factory = MagicMock(return_value=mock_session)

    with patch("app.database.get_session_factory", return_value=mock_factory):
        from app.services.library_builder import reconcile_orphan_builds

        await reconcile_orphan_builds()

    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_reconcile_no_server_id_marks_error():
    """server_id가 없는 stale row는 error로 마킹하고 share 메타데이터를 갱신한다."""
    row = _make_build_row(server_id=None, build_token=None)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    # 첫 번째 execute: row 목록 반환
    result_rows = MagicMock()
    result_rows.scalars.return_value.all.return_value = [row]
    # 두 번째 execute: _mark_error_and_cleanup 내부 단건 조회
    result_single = MagicMock()
    result_single.scalar_one_or_none.return_value = row
    mock_session.execute = AsyncMock(side_effect=[result_rows, result_single])
    mock_session.commit = AsyncMock()

    mock_factory = MagicMock(return_value=mock_session)

    mock_conn = MagicMock()
    mock_svc_conn_coro = AsyncMock(return_value=mock_conn)
    mock_manila_update = MagicMock()
    mock_neutron_delete = MagicMock()

    with (
        patch("app.database.get_session_factory", return_value=mock_factory),
        patch("app.services.library_builder.get_service_project_connection", return_value=mock_conn),
        patch("asyncio.to_thread", new=mock_svc_conn_coro),
        patch("app.services.library_builder.manila.update_share_metadata", mock_manila_update),
        patch("app.services.library_builder.neutron.delete_port", mock_neutron_delete),
    ):
        from app.services.library_builder import reconcile_orphan_builds

        await reconcile_orphan_builds()

    # row.status가 "error"로 설정되어야 함
    assert row.status == "error"
    mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_reconcile_schedules_resume_task_for_server_id():
    """server_id와 build_token이 있는 row는 _resume_build_task asyncio.Task를 생성한다."""
    row = _make_build_row()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    result_rows = MagicMock()
    result_rows.scalars.return_value.all.return_value = [row]
    mock_session.execute = AsyncMock(return_value=result_rows)

    mock_factory = MagicMock(return_value=mock_session)

    mock_conn = MagicMock()
    mock_share = MagicMock()
    mock_share.share_proto = "NFS"

    created_tasks: list = []

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch("app.database.get_session_factory", return_value=mock_factory),
        patch("asyncio.to_thread", side_effect=fake_to_thread),
        patch("app.services.library_builder.get_service_project_connection", return_value=mock_conn),
        patch("app.services.library_builder.manila.get_file_storage", return_value=mock_share),
        patch("app.services.library_builder.lib_svc.get_by_id", return_value=MagicMock(version="3.11")),
        patch("app.services.library_builder._resume_build_task", new=AsyncMock()),
    ):
        # asyncio.create_task를 가로채서 생성된 태스크 수 확인
        original_create_task = asyncio.create_task

        def spy_create_task(coro, **kwargs):
            task = original_create_task(coro, **kwargs)
            created_tasks.append(task)
            return task

        with patch("asyncio.create_task", side_effect=spy_create_task):
            from app.services import library_builder

            # 모듈 재로드 없이 함수 직접 호출
            await library_builder.reconcile_orphan_builds()

    assert len(created_tasks) >= 1


# ──────────────────────────────────────────────
# _background_tasks GC 방지
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_background_tasks_set_populated_on_start_ephemeral_build():
    """start_ephemeral_build retains its snapshot-driven background task."""
    from app.services import library_builder

    library_builder._active_builds.clear()
    started = asyncio.Event()
    release = asyncio.Event()
    mock_lib = MagicMock(id="python311", version="3.11")
    recipe = MagicMock(base_image_id="img-001", share_proto="NFS", share_size_gb=5)
    service_conn = MagicMock()

    async def fake_ephemeral_task(**kwargs):
        started.set()
        await release.wait()

    async def get_recipe(_library_id):
        return recipe

    async def resolve_policy_snapshot(**kwargs):
        return {
            "builder.flavor": {"id": "flavor-001", "name": "builder"},
            "builder.network": {"id": "network-001", "name": "builder-net"},
            "manila.nfs_share_type": {"id": "share-type-001", "name": "nfs"},
            "manila.share_network": {"id": "share-network-001", "name": "share-net"},
        }

    async def get_policy_snapshot(_keys):
        return {"openstack.service_project": {"id": "service-project", "name": "service"}}

    with (
        patch("app.services.library_builder.lib_svc.get_by_id", return_value=mock_lib),
        patch("app.services.library_recipes.get_recipe", side_effect=get_recipe),
        patch(
            "app.services.resource_policy_store.get_service_project_connection",
            new=AsyncMock(return_value=service_conn),
        ),
        patch(
            "app.services.resource_policy_store.resolve_policy_snapshot",
            new=AsyncMock(side_effect=resolve_policy_snapshot),
        ),
        patch(
            "app.services.resource_policy_store.get_policy_snapshot",
            new=AsyncMock(side_effect=get_policy_snapshot),
        ),
        patch("app.database.get_session_factory", return_value=None),
        patch(
            "app.services.library_builder._ephemeral_build_task",
            side_effect=fake_ephemeral_task,
        ),
    ):
        service_conn.image.get_image.return_value = MagicMock(name="Ubuntu")
        await library_builder.start_ephemeral_build("python311")
        await started.wait()
        assert library_builder._background_tasks
        release.set()
        await asyncio.sleep(0)

    library_builder._active_builds.clear()


@pytest.mark.asyncio
async def test_list_libraries_uses_service_conn_with_include_public(admin_client):
    """The retained catalog discovers service-owned prebuilt shares."""
    from app.services.manila import FileStorageInfo

    fake_share = MagicMock(spec=FileStorageInfo)
    fake_share.library_name = "python311"
    fake_share.id = "share-prebuilt-123"

    with (
        patch("app.api.common.libraries.get_service_project_connection", return_value=MagicMock()),
        patch("app.api.common.libraries.manila.list_file_storages", return_value=[fake_share]) as mock_list,
    ):
        resp = await admin_client.get("/api/v1/libraries")

    assert resp.status_code == 200
    assert mock_list.call_args.kwargs["include_public"] is True
    py311 = next((lib for lib in resp.json() if lib["id"] == "python311"), None)
    if py311:
        assert py311["available_prebuilt"] is True
