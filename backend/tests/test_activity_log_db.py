"""Account activity intent filters against the real MariaDB REGEXP dialect."""

import os

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import tests.test_activity_log as scenarios
from app.models.activity import ActivityLog
from app.services import activity

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

_USERS = ("test-user-123", "another-user", "backup-system-user")


@pytest_asyncio.fixture
async def activity_db(monkeypatch):
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required for MariaDB activity filters")
    engine = create_async_engine(url)
    if engine.dialect.name not in {"mysql", "mariadb"}:
        await engine.dispose()
        pytest.skip("MariaDB is required for the production REGEXP dialect")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: ActivityLog.__table__.create(sync, checkfirst=True))
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def purge():
        async with factory() as session:
            await session.execute(delete(ActivityLog).where(ActivityLog.user_id.in_(_USERS)))
            await session.commit()

    async def seed_with_database_ids(factory, rows):
        # Shared lanes may already hold rows, so keep insertion order but let MariaDB assign ids.
        ids = []
        for values in rows:
            async with factory() as session:
                row = ActivityLog(
                    **{
                        "project_id": "test-project-123",
                        "user_id": "test-user-123",
                        "username": "testuser",
                        "resource_type": "instance",
                        "resource_id": "resource",
                        "status": "success",
                        **values,
                    }
                )
                session.add(row)
                await session.commit()
                ids.append(row.id)
        return ids

    monkeypatch.setattr(activity, "is_db_available", lambda: True)
    monkeypatch.setattr(activity, "get_session_factory", lambda: factory)
    monkeypatch.setattr(scenarios, "seed_activity", seed_with_database_ids)
    await purge()
    try:
        yield factory
    finally:
        await purge()
        await engine.dispose()


async def test_mariadb_filters_persisted_telemetry_and_reads(client, activity_db):
    await scenarios.test_profile_activity_filters_persisted_telemetry_and_reads(client, activity_db)


async def test_mariadb_keeps_user_intents_and_legacy_mutations_not_native_echoes(client, activity_db):
    await scenarios.test_profile_activity_keeps_user_intents_and_legacy_mutations_not_native_echoes(client, activity_db)


async def test_mariadb_classifies_real_middleware_route_operations(client, activity_db):
    await scenarios.test_account_intent_feed_classifies_real_middleware_route_operations(client, activity_db)


async def test_mariadb_cursor_pages_over_filtered_rows(client, activity_db):
    ids = await scenarios.seed_activity(
        activity_db,
        [
            {"action": "instance.create"},
            {"resource_type": "request", "action": "request.read"},
            {"action": "instance.delete"},
            {"action": "instance.stage"},
            {"action": "instance.stop", "status": "failed"},
            {"resource_type": "request", "action": "request.stage"},
            {"action": "instance.start", "status": "started"},
            {"resource_type": "request", "action": "request.read"},
        ],
    )
    first = await client.get("/api/v1/profile/activity?limit=3")
    assert [row["id"] for row in first.json()] == [ids[6], ids[4], ids[2]]
    second = await client.get(f"/api/v1/profile/activity?limit=3&before_id={ids[2]}")
    assert [row["id"] for row in second.json()] == [ids[0]]


@pytest.mark.parametrize(
    "query",
    ["resource_type=request", "action=request.read", "action=instance.read", "action=instance.stage"],
)
async def test_mariadb_explicit_filters_cannot_restore_telemetry(client, activity_db, query):
    await scenarios.test_profile_activity_explicit_filters_cannot_restore_telemetry(client, activity_db, query)
