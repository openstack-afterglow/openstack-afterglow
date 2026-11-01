"""Regression tests for the one-time runtime settings importer."""

from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

_SPEC = importlib.util.spec_from_file_location(
    "runtime_settings_importer",
    Path(__file__).resolve().parents[1] / "scripts/import_runtime_infrastructure_settings.py",
)
assert _SPEC and _SPEC.loader
importer = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(importer)


def test_parse_legacy_base_images_requires_unique_release_mapping():
    assert importer._parse_legacy_base_images(["ubuntu-24.04=img-24"]) == {"ubuntu-24.04": "img-24"}
    with pytest.raises(ValueError, match="RELEASE=IMAGE_ID"):
        importer._parse_legacy_base_images(["bad-value"])
    with pytest.raises(ValueError, match="duplicate"):
        importer._parse_legacy_base_images(["ubuntu-24.04=img-24", "ubuntu-24.04=img-other"])


def test_legacy_bool_honors_explicit_environment(monkeypatch):
    config = {"notion": {"enabled": False}}
    monkeypatch.setenv("NOTION_ENABLED", "true")
    assert importer._legacy_bool(config, "notion", "enabled", "NOTION_ENABLED") is True
    monkeypatch.setenv("NOTION_ENABLED", "not-a-bool")
    assert importer._legacy_bool(config, "notion", "enabled", "NOTION_ENABLED") is None


def test_default_availability_zone_seeds_compute_and_volume_policies():
    source = ("nova", "default_availability_zone", "DEFAULT_AVAILABILITY_ZONE")
    assert importer._POLICY_SOURCES["nova.default_compute_availability_zone"] == source
    assert importer._POLICY_SOURCES["cinder.default_volume_availability_zone"] == source


@pytest.fixture(scope="module")
def importer_database_url():
    database_url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL 미설정 — importer DB 통합 테스트 건너뜀")
    return database_url


@pytest.fixture(scope="module")
def importer_database(importer_database_url):
    async def setup():
        from sqlalchemy.ext.asyncio import create_async_engine

        import app.models.db  # noqa: F401
        from app.database import Base

        engine = create_async_engine(importer_database_url, pool_pre_ping=True)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    async def teardown():
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.database import Base

        engine = create_async_engine(importer_database_url, pool_pre_ping=True)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(setup())
    yield importer_database_url
    asyncio.run(teardown())


async def _importer_rows(database_url: str) -> tuple[dict[str, str], dict[str, object]]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.db import ResourcePolicy, RuntimeSetting

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            policies = {
                row.policy_key: row.resource_id for row in (await session.execute(select(ResourcePolicy))).scalars()
            }
            runtime = {
                row.setting_key: row.value_json for row in (await session.execute(select(RuntimeSetting))).scalars()
            }
            return policies, runtime
    finally:
        await engine.dispose()


async def _add_pending_library_build(database_url: str) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.db import LibraryBuild

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            session.add(
                LibraryBuild(
                    library_id="library-1",
                    file_storage_id="storage-1",
                    status="pending",
                )
            )
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.db
def test_apply_seeds_once_and_rolls_back_on_write_failure(importer_database):
    selected = {
        "nova.default_network": {"id": "network-1", "name": "tenant-network"},
    }
    runtime = {"notion.sync_enabled": True}

    assert asyncio.run(importer._apply(importer_database, selected, runtime, {})) == (1, 1, 0)
    assert asyncio.run(_importer_rows(importer_database)) == (
        {"nova.default_network": "network-1"},
        {"notion.sync_enabled": True},
    )
    assert asyncio.run(importer._apply(importer_database, selected, runtime, {})) == (0, 0, 0)

    from sqlalchemy.exc import StatementError

    with pytest.raises(StatementError):
        asyncio.run(
            importer._apply(
                importer_database,
                {"nova.default_network": {"id": "network-1", "name": "tenant-network"}},
                {"notion.sync_enabled_rollback": object()},
                {},
            )
        )

    assert asyncio.run(_importer_rows(importer_database)) == (
        {"nova.default_network": "network-1"},
        {"notion.sync_enabled": True},
    )

    asyncio.run(_add_pending_library_build(importer_database))
    with pytest.raises(ValueError, match="unresolved in-flight resource snapshots"):
        asyncio.run(
            importer._apply(
                importer_database,
                {"nova.default_network": {"id": "network-1", "name": "tenant-network"}},
                {},
                {},
            )
        )
    assert asyncio.run(_importer_rows(importer_database)) == (
        {"nova.default_network": "network-1"},
        {"notion.sync_enabled": True},
    )


@pytest_asyncio.fixture
async def isolated_policy_importer(tmp_path, monkeypatch):
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.db import ResourcePolicy, RuntimeSetting

    database_url = f"sqlite+aiosqlite:///{tmp_path / 'policy-import.sqlite'}"
    engine = create_async_engine(database_url)

    @event.listens_for(engine.sync_engine, "connect")
    def sqlite_transaction_control(dbapi_connection, _record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine.sync_engine, "begin")
    def physical_outer_transaction(connection):
        # sqlite's legacy driver otherwise releases an initial SAVEPOINT as a
        # top-level commit, which cannot exercise importer atomic rollback.
        connection.exec_driver_sql("BEGIN")

    async with engine.begin() as connection:
        await connection.run_sync(ResourcePolicy.__table__.create)
        await connection.run_sync(RuntimeSetting.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(importer, "create_async_engine", lambda *_args, **_kwargs: engine)
    monkeypatch.setattr(importer, "_inflight_snapshot_blockers", AsyncMock(return_value=[]))
    yield database_url, engine, factory
    await engine.dispose()


@pytest.mark.parametrize("winner_id", [None, "native-reconciler-zone"])
@pytest.mark.asyncio
async def test_policy_insert_race_keeps_current_winner_and_continues_import(
    isolated_policy_importer, monkeypatch, winner_id
):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.db import ResourcePolicy, RuntimeSetting

    database_url, engine, factory = isolated_policy_importer
    compute = "nova.default_compute_availability_zone"
    volume = "cinder.default_volume_availability_zone"
    async with factory() as session, session.begin():
        session.add(
            ResourcePolicy(
                policy_key=compute,
                resource_kind="compute_availability_zone",
                resource_id=winner_id,
                resource_name="current administrator decision",
                constraints={"manual": True},
                updated_by_user_id="administrator",
            )
        )
    async with factory() as session:
        winner = await session.get(ResourcePolicy, compute)
        before = {column.name: getattr(winner, column.name) for column in ResourcePolicy.__table__.columns}
    current_reads = []

    class StaleSnapshotSession(AsyncSession):
        async def execute(self, statement, *args, **kwargs):
            if str(statement) == str(select(ResourcePolicy.policy_key)):
                # Synthetic old RR observation; the competing committed row and
                # duplicate-key exception below come from actual SQL storage.
                return SimpleNamespace(scalars=lambda: iter(()))
            return await super().execute(statement, *args, **kwargs)

        async def scalar(self, statement, *args, **kwargs):
            if statement._for_update_arg is not None:
                current_reads.append(statement)
            return await super().scalar(statement, *args, **kwargs)

    stale_factory = async_sessionmaker(engine, class_=StaleSnapshotSession, expire_on_commit=False)
    monkeypatch.setattr(importer, "async_sessionmaker", lambda *_args, **_kwargs: stale_factory)
    assert await importer._apply(
        database_url,
        {compute: {"id": "legacy-zone", "name": "Legacy"}, volume: {"id": "storage", "name": "Storage"}},
        {"notion.sync_enabled": True},
        {},
    ) == (1, 1, 0)
    assert len(current_reads) == 1, "duplicate winner requires a current locking read, not the stale snapshot"
    async with factory() as session:
        winner = await session.get(ResourcePolicy, compute)
        assert {column.name: getattr(winner, column.name) for column in ResourcePolicy.__table__.columns} == before
        assert (await session.get(ResourcePolicy, volume)).resource_id == "storage"
        assert (await session.get(RuntimeSetting, "notion.sync_enabled")).value_json is True


@pytest.mark.asyncio
async def test_non_duplicate_policy_integrity_error_rolls_back_all_new_seeds(isolated_policy_importer):
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app.models.db import ResourcePolicy, RuntimeSetting

    database_url, engine, factory = isolated_policy_importer
    async with engine.begin() as connection:
        await connection.exec_driver_sql(
            """CREATE TRIGGER reject_policy_integrity BEFORE INSERT ON resource_policies
            WHEN NEW.policy_key = 'nova.default_compute_availability_zone'
            BEGIN SELECT RAISE(ABORT, 'unrelated policy integrity failure'); END"""
        )
    with pytest.raises(IntegrityError, match="unrelated policy integrity failure"):
        await importer._apply(
            database_url,
            {
                "cinder.default_volume_availability_zone": {"id": "storage", "name": "Storage"},
                "nova.default_compute_availability_zone": {"id": "compute", "name": "Compute"},
            },
            {"notion.sync_enabled": True},
            {},
        )
    async with factory() as session:
        assert (await session.execute(select(ResourcePolicy))).scalars().all() == []
        assert (await session.execute(select(RuntimeSetting))).scalars().all() == []


@pytest.mark.asyncio
async def test_duplicate_without_current_key_winner_is_not_swallowed():
    from contextlib import asynccontextmanager

    from sqlalchemy.exc import IntegrityError

    class DuplicateKey(Exception):
        pass

    failure = IntegrityError("INSERT", {}, DuplicateKey(1062, "duplicate key"))

    @asynccontextmanager
    async def savepoint():
        yield

    session = SimpleNamespace(
        begin_nested=savepoint,
        add=lambda _row: None,
        flush=AsyncMock(side_effect=failure),
        scalar=AsyncMock(return_value=None),
    )
    with pytest.raises(IntegrityError) as caught:
        await importer._insert_policy_if_absent(
            session, "nova.default_compute_availability_zone", {"id": "compute", "name": "Compute"}
        )
    assert caught.value is failure
    session.scalar.assert_awaited_once()
    assert session.scalar.call_args.args[0]._for_update_arg is not None
