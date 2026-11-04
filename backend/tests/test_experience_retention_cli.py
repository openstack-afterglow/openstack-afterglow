"""Operator hold/release CLI against real isolated SQL, never production storage."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import MetaData, func, select
from sqlalchemy import event as sql_events
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import experience as models
from app.models.experience import ExperienceEvent, ExperienceHold, ExperienceOperationLink, ExperienceRecord
from app.services import experience as store
from scripts import retain_experiences as cli

pytestmark = pytest.mark.asyncio
ACTOR = {"user_id": "hold-owner", "project_id": "hold-project"}
OTHER = {"user_id": "other-owner", "project_id": "other-project"}


def event_wire():
    return {
        "schema_version": 2,
        "event_id": str(uuid4()),
        "event_type": "action.started",
        "segment_id": str(uuid4()),
        "page_view_id": str(uuid4()),
        "action_id": str(uuid4()),
        "client_seq": 1,
        "client_monotonic_ms": 1,
        "occurred_at": datetime.now(UTC).isoformat(),
        "route": "/instances",
        "feature": "compute",
        "action": "create",
        "component": "compute.create",
        "frontend_build": "1.2.3",
        "catalog_revision": "unknown",
        "redaction_revision": 1,
        "payload": {},
    }


def source_context(event, actor):
    return {
        **{
            key: event[key]
            for key in (
                "segment_id",
                "page_view_id",
                "action_id",
                "route",
                "feature",
                "action",
                "component",
                "frontend_build",
                "catalog_revision",
            )
        },
        "actor": actor,
        "source": "api",
        "request_id": f"req-{uuid4().hex}",
    }


@pytest.fixture(params=["sqlite", pytest.param("mariadb", marks=pytest.mark.db)])
async def hold_sql(request, tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path / 'experience-holds.sqlite'}"
    if request.param == "mariadb":
        url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
        if not url:
            pytest.skip("Dedicated AFTERGLOW_TEST_DATABASE_URL required")
    engine = create_async_engine(url)
    metadata = MetaData()
    for table in models.Base.metadata.sorted_tables:
        if table.name.startswith("experience_"):
            table.to_metadata(metadata)
    # No existing business table is created, deleted, or altered by this fixture.
    maintenance = metadata.tables["experience_maintenance"]
    async with engine.begin() as connection:
        if request.param == "mariadb":
            await connection.run_sync(metadata.drop_all)
            migration = (Path(__file__).parents[1] / "migrations/107_experience_events.sql").read_text()
            for statement in migration.split(";"):
                if statement.strip():
                    await connection.exec_driver_sql(statement)
        else:
            await connection.run_sync(metadata.create_all)
        if not await connection.scalar(select(func.count()).select_from(maintenance)):
            await connection.execute(maintenance.insert().values(id=1, revision=0))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = SimpleNamespace(
        experience_enabled=True,
        experience_anonymous_read_enabled=False,
        experience_detail_retention_days=30,
        experience_aggregate_retention_days=90,
    )
    monkeypatch.setattr(store, "get_settings", lambda: settings)
    monkeypatch.setattr(store, "get_session_factory", lambda: factory)
    monkeypatch.setattr(store, "is_db_available", lambda: True)
    try:
        yield factory, maintenance, engine
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.drop_all)
        await engine.dispose()


async def guard_revision(factory, maintenance):
    async with factory() as session:
        return await session.scalar(select(maintenance.c.revision).where(maintenance.c.id == 1))


async def persisted(factory, model):
    async with factory() as session:
        return list((await session.scalars(select(model))).all())


async def seed_old_segment(factory, *, both_owners=True):
    event = event_wire()
    now = datetime.now(UTC)
    actors = (ACTOR, OTHER) if both_owners else (ACTOR,)
    for index, actor in enumerate(actors):
        await store.ingest(actor=actor, events=[ExperienceEvent.model_validate(event)])
        await store.bind_operation(source_context(event, actor), "mcp_invocation", f"hold-cli-operation-{index}")
    async with factory() as session, session.begin():
        for row in (await session.scalars(select(ExperienceRecord))).all():
            row.received_at = now - timedelta(days=31)
        for link in (await session.scalars(select(ExperienceOperationLink))).all():
            link.created_at = now - timedelta(days=31)
    return event, now


async def test_cli_hold_dryrun_apply_release_and_retention_share_real_sql_guard(hold_sql):
    factory, maintenance, _ = hold_sql
    event, now = await seed_old_segment(factory)
    arguments = {"segment_id": event["segment_id"], **ACTOR}
    baseline = await guard_revision(factory, maintenance)
    dry = await cli.maintain_hold(**arguments)
    assert dry["hold_candidates"] == 1 and dry["holds_created"] == 0
    assert await persisted(factory, ExperienceHold) == []
    assert await guard_revision(factory, maintenance) == baseline
    applied = await cli.maintain_hold(**arguments, apply=True)
    assert applied["holds_created"] == 1
    assert await guard_revision(factory, maintenance) > baseline
    assert all(isinstance(value, (bool, int)) for value in applied.values())
    assert (await cli.maintain_hold(**arguments, apply=True))["holds_created"] == 0
    retired = await store.retain(apply=True, now=now)
    assert retired["detail_deleted"] == 1
    assert [row.user_id for row in await persisted(factory, ExperienceRecord)] == [ACTOR["user_id"]]
    assert [row.user_id for row in await persisted(factory, ExperienceOperationLink)] == [ACTOR["user_id"]]
    before_release = await guard_revision(factory, maintenance)
    release_dry = await cli.maintain_hold(**arguments, release=True)
    assert release_dry["release_candidates"] == 1 and release_dry["holds_released"] == 0
    assert await guard_revision(factory, maintenance) == before_release
    assert len(await persisted(factory, ExperienceHold)) == 1
    released = await cli.maintain_hold(**arguments, release=True, apply=True)
    assert released["holds_released"] == 1
    assert await guard_revision(factory, maintenance) > before_release
    assert (await store.retain(apply=True, now=now))["detail_deleted"] == 1
    assert await persisted(factory, ExperienceRecord) == []
    assert await persisted(factory, ExperienceOperationLink) == []


async def test_cli_hold_requires_existing_exact_owner_and_rolls_back_guard_on_failure(hold_sql):
    factory, maintenance, _ = hold_sql
    event, _ = await seed_old_segment(factory, both_owners=False)
    baseline = await guard_revision(factory, maintenance)
    for owner in (OTHER, {"user_id": ACTOR["user_id"], "project_id": OTHER["project_id"]}):
        with pytest.raises(ValueError):
            await cli.maintain_hold(segment_id=event["segment_id"], **owner, apply=True)
    with pytest.raises(ValueError):
        await cli.maintain_hold(segment_id=str(uuid4()), **ACTOR, apply=True)
    assert await guard_revision(factory, maintenance) == baseline
    assert await persisted(factory, ExperienceHold) == []
    assert len(await persisted(factory, ExperienceRecord)) == 1


@pytest.mark.db
async def test_mariadb_cli_hold_path_uses_actual_maintenance_revision(hold_sql):
    factory, maintenance, engine = hold_sql
    if engine.dialect.name not in {"mysql", "mariadb"}:
        pytest.skip("MariaDB-specific CLI guard receipt")
    event, _ = await seed_old_segment(factory, both_owners=False)
    baseline = await guard_revision(factory, maintenance)
    result = await cli.maintain_hold(segment_id=event["segment_id"], **ACTOR, apply=True)
    assert result["holds_created"] == 1
    assert await guard_revision(factory, maintenance) > baseline


@pytest.mark.db
async def test_mariadb_cli_hold_racing_retention_cannot_acknowledge_a_lost_hold(hold_sql):
    factory, _, engine = hold_sql
    if engine.dialect.name not in {"mysql", "mariadb"}:
        pytest.skip("Actual InnoDB row-lock concurrency boundary")
    event, now = await seed_old_segment(factory, both_owners=False)
    entered = {"hold-cli-race": asyncio.Event(), "retain-cli-race": asyncio.Event()}

    def observe_guard_dispatch(connection, cursor, statement, parameters, context, executemany):
        task = asyncio.current_task()
        if task is not None and "experience_maintenance" in statement and "FOR UPDATE" in statement.upper():
            marker = entered.get(task.get_name())
            if marker is not None:
                marker.set()

    tasks = []
    sql_events.listen(engine.sync_engine, "before_cursor_execute", observe_guard_dispatch)
    try:
        # Both real operations must queue behind a genuinely held SQL row lock,
        # not a mocked helper or a timing-only assertion.
        async with factory() as blocker, blocker.begin():
            await store.lock_maintenance(blocker)
            tasks.append(
                asyncio.create_task(
                    cli.maintain_hold(segment_id=event["segment_id"], **ACTOR, apply=True),
                    name="hold-cli-race",
                )
            )
            await asyncio.wait_for(entered["hold-cli-race"].wait(), timeout=10)
            tasks.append(
                asyncio.create_task(
                    store.retain(apply=True, now=now),
                    name="retain-cli-race",
                )
            )
            await asyncio.wait_for(entered["retain-cli-race"].wait(), timeout=10)
            assert not any(task.done() for task in tasks)
        hold_result, retained = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=20)
        assert isinstance(retained, dict)
        holds = await persisted(factory, ExperienceHold)
        records = await persisted(factory, ExperienceRecord)
        links = await persisted(factory, ExperienceOperationLink)
        if isinstance(hold_result, ValueError):
            # Retention won: the CLI must reject a now-nonexistent exact owner
            # segment, rather than acknowledge an orphan hold after deletion.
            assert retained["detail_deleted"] == 1
            assert holds == records == links == []
        else:
            # Hold won: successful acknowledgement protects BOTH detail and
            # durable lineage, regardless of InnoDB waiter scheduling order.
            assert isinstance(hold_result, dict) and hold_result["holds_created"] == 1
            assert retained["detail_deleted"] == 0
            assert len(holds) == len(records) == len(links) == 1
            assert records[0].user_id == links[0].user_id == ACTOR["user_id"]
    finally:
        sql_events.remove(engine.sync_engine, "before_cursor_execute", observe_guard_dispatch)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize(
    "arguments",
    [
        ["--hold", str(uuid4())],
        ["--release", str(uuid4()), "--user-id", "only-user"],
        ["--hold", str(uuid4()), "--release", str(uuid4()), "--user-id", "user", "--project-id", "project"],
        ["--user-id", "user", "--project-id", "project"],
    ],
)
async def test_cli_argument_errors_never_open_database(monkeypatch, arguments):
    monkeypatch.setattr(
        sys, "argv", ["retain_experiences.py", "--database-url", "invalid-url-no-connection", *arguments]
    )
    with pytest.raises(SystemExit) as raised:
        cli.main()
    assert raised.value.code == 2
