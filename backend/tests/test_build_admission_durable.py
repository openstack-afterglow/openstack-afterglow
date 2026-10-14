"""A persisted admission is discovered and consumed by a different worker."""

import secrets
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import LayerBuild, LayerImportJob, LibraryBuild, LibraryRecipe, ResourcePolicy
from app.services import build_work, ephemeral_build, library_builder, library_recipes, resource_policy_store
from app.services.work_dispatcher import DispatcherUnavailable, WorkDispatcher


@pytest.fixture
async def durable_database(monkeypatch):
    # Only the disposable DDL maps MySQL MEDIUMTEXT to SQLite TEXT; production
    # metadata is restored by monkeypatch after this consumer test.
    monkeypatch.setattr(LayerImportJob.__table__.c.dockerfile_text, "type", Text())
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for model in (LibraryRecipe, LibraryBuild, LayerImportJob, LayerBuild, ResourcePolicy):
            await connection.run_sync(lambda sync, model=model: model.__table__.create(sync))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    async with factory() as session:
        recipe = LibraryRecipe(
            library_id="python311",
            version=1,
            base_image_id="image",
            share_size_gb=5,
            share_proto="NFS",
            commands=[{"script": "frozen"}],
            apt_packages=[],
            pip_packages=[],
            cloud_init_template_version=1,
        )
        session.add_all(
            [
                recipe,
                ResourcePolicy(
                    policy_key="openstack.service_project",
                    resource_kind="project",
                    resource_id="project",
                    resource_name="project",
                ),
            ]
        )
        await session.commit()
    monkeypatch.setattr(library_recipes, "get_recipe", AsyncMock(return_value=recipe))
    connection = MagicMock()
    connection.image.get_image.return_value = SimpleNamespace(name="base")
    monkeypatch.setattr(resource_policy_store, "get_service_project_connection", AsyncMock(return_value=connection))
    monkeypatch.setattr(
        resource_policy_store,
        "resolve_policy_snapshot",
        AsyncMock(
            return_value={
                "builder.flavor": {"id": "flavor"},
                "builder.network": {"id": "network"},
                "manila.nfs_share_type": {"name": "nfs"},
                "manila.share_network": {"id": "share-network"},
            }
        ),
    )
    monkeypatch.setattr(
        resource_policy_store,
        "get_policy_snapshot",
        AsyncMock(
            return_value={
                "openstack.service_project": {"id": "project"},
            }
        ),
    )
    monkeypatch.setattr(library_builder.lib_svc, "get_by_id", lambda _: SimpleNamespace(version="3.11"))
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_queue_survives_admitting_process_and_is_consumed_under_target_lease(durable_database, monkeypatch):
    from app.services.cache import _get_redis

    factory = durable_database
    executed = []

    async def execute(build_id):
        # The assigned consumer, not the admission process, has SQL+lease authority.
        await build_work.checkpoint()
        async with factory() as session:
            row = await session.get(LibraryBuild, build_id)
            executed.append(
                (row.library_id, build_id, row.file_storage_id, row.resource_snapshot["recipe"]["commands"])
            )
            row.status = "complete"
            await session.commit()

    monkeypatch.setattr(ephemeral_build, "run_ephemeral_build", execute)
    response = await library_builder.queue_build("python311", existing_share_id="existing-share")
    assert response["status"] == "queued" and not executed
    # A new admission instance observes SQL, not a former process's local set.
    with pytest.raises(RuntimeError, match="이미"):
        await library_builder.queue_build("python311")
    async with factory() as session:
        rows = (await session.execute(select(LibraryBuild))).scalars().all()
        assert len(rows) == 1 and rows[0].status == "queued" and len(rows[0].build_token) == 32
        build_id = rows[0].id
    redis = await _get_redis()
    prefix = f"afterglow:test:durable-admission:{secrets.token_hex(12)}"
    try:
        async with WorkDispatcher(redis, prefix, worker_id="different-api-process-worker") as worker:
            await library_builder._discover_work(worker)
            member, owner = await worker.claim(90)
            assert member == f"library:{build_id}"
            await library_builder._execute_work(worker, member, owner)
            assert await redis.get(f"{prefix}:lease:{member}") is None
        async with factory() as session:
            assert (await session.get(LibraryBuild, build_id)).status == "complete"
    finally:
        keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
        if keys:
            await redis.delete(*keys)
    assert executed == [("python311", build_id, "existing-share", [{"script": "frozen"}])]


@pytest.mark.asyncio
async def test_pending_library_cancellation_is_rediscovered_with_cleanup_only_authority(durable_database, monkeypatch):
    from app.services.cache import _get_redis

    factory = durable_database
    observed = []

    async def cleanup(build_id):
        with pytest.raises(DispatcherUnavailable, match="cancellation cleanup"):
            await build_work.submit("server", lambda: observed.append("create"))
        observed.append(build_work.current_binding().cancel_cleanup)
        async with factory() as session:
            row = await session.get(LibraryBuild, build_id)
            row.resource_snapshot = {**row.resource_snapshot, "cancel_cleanup": "done"}
            row.completed_at = datetime.now(UTC)
            await session.commit()

    monkeypatch.setattr(ephemeral_build, "run_ephemeral_build", cleanup)
    await library_builder.queue_build("python311", existing_share_id="existing-share")
    async with factory() as session:
        build_id = (await session.execute(select(LibraryBuild.id))).scalar_one()
    await library_builder.cancel_build(build_id)
    redis = await _get_redis()
    prefix = f"afterglow:test:cancel-cleanup:{secrets.token_hex(12)}"
    try:
        async with WorkDispatcher(redis, prefix, worker_id="cleanup-worker") as worker:
            await library_builder._discover_work(worker)
            member, owner = await worker.claim(90)
            assert member == f"library:{build_id}"
            await library_builder._execute_work(worker, member, owner)
            await library_builder._discover_work(worker)
            assert await worker.claim(90) is None
    finally:
        keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
        if keys:
            await redis.delete(*keys)
    assert observed == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["dockerfile", "dockerfile-root"])
async def test_import_owned_child_rows_never_receive_independent_layer_assignment(durable_database, kind):
    from app.services.cache import _get_redis

    factory = durable_database
    async with factory() as session:
        child = LayerBuild(layer_name="import-child", kind=kind, share_id="", status="queued")
        session.add(child)
        await session.flush()
        job = LayerImportJob(
            layer_prefix="import",
            profile_name="import",
            ubuntu_base="ubuntu",
            base_image_id="image",
            status="queued",
            build_ids=[child.id],
            artifact_ids=[],
        )
        session.add(job)
        await session.commit()
        import_id, child_id = job.id, child.id
    redis = await _get_redis()
    prefix = f"afterglow:test:import-child-authority:{secrets.token_hex(12)}"
    try:
        async with WorkDispatcher(redis, prefix) as worker:
            await library_builder._discover_work(worker)
            assert await worker.pending() == 1
            member, _ = await worker.claim(90)
            assert member == f"import:{import_id}"
            assert await worker.claim(90) is None
        async with factory() as session:
            assert (await session.get(LayerImportJob, import_id)).status == "queued"
            assert (await session.get(LayerBuild, child_id)).status == "queued"
    finally:
        keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
        if keys:
            await redis.delete(*keys)
