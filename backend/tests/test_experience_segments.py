"""Recent diagnostic discovery on owned rows in SQLite and optional MariaDB.

Native cases require AFTERGLOW_TEST_DATABASE_URL and carry the db marker.
Only the selected experience/catalog/activity tables are created if absent;
no shared table is dropped or truncated, and cleanup targets exact inserted IDs.
These are synthetic SQL/HTTP cases, not production/native-cloud acceptance.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Integer, MetaData, delete, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.common.admin_resource_scope import AdminResourceScope, admin_resource_scope
from app.api.deps import get_admin_os_conn, get_token_info, require_admin
from app.api.identity import admin_experience
from app.models.activity import ActivityLog
from app.models.experience import ExperienceCatalog, ExperienceRecord
from app.services import experience as store

pytestmark = pytest.mark.asyncio


@pytest.fixture(params=["sqlite", pytest.param("mariadb", marks=pytest.mark.db)])
async def segment_store(request, monkeypatch, tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'recent-segments.sqlite'}"
    if request.param == "mariadb":
        url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
        if not url:
            pytest.skip("Dedicated AFTERGLOW_TEST_DATABASE_URL required for MariaDB")
        if not url.startswith("mysql+"):
            pytest.skip("MariaDB fixture requires a mysql async-driver URL")
    engine = create_async_engine(url)
    metadata = MetaData()
    for model in (ExperienceCatalog, ExperienceRecord, ActivityLog):
        table = model.__table__.to_metadata(metadata)
        if request.param == "sqlite" and model is ActivityLog:
            table.c.id.type = Integer()
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    state = SimpleNamespace(
        factory=factory,
        engine=engine,
        ids=[],
        actor={"user_id": f"recent-user-{suffix}", "project_id": f"recent-project-{suffix}"},
        other={"user_id": f"recent-other-{suffix}", "project_id": f"recent-foreign-{suffix}"},
        admin={"user_id": f"recent-admin-{suffix}", "project_id": "admin-project", "_live_system_admin": True},
        settings=SimpleNamespace(experience_enabled=True, experience_anonymous_read_enabled=False),
    )
    monkeypatch.setattr(store, "get_settings", lambda: state.settings)
    monkeypatch.setattr(store, "is_db_available", lambda: True)
    monkeypatch.setattr(store, "get_session_factory", lambda: factory)
    try:
        yield state
    finally:
        async with engine.begin() as connection:
            if state.ids:
                await connection.execute(delete(ExperienceRecord).where(ExperienceRecord.id.in_(state.ids)))
            audit_ids = list(
                (
                    await connection.scalars(
                        select(ActivityLog.id).where(
                            ActivityLog.resource_type == "experience",
                            ActivityLog.user_id == state.admin["user_id"],
                        )
                    )
                ).all()
            )
            if audit_ids:
                await connection.execute(
                    delete(ActivityLog).where(
                        ActivityLog.id.in_(audit_ids), ActivityLog.user_id == state.admin["user_id"]
                    )
                )
        await engine.dispose()


async def seed(state, *, actor=None, segment=None, received=None, source="browser", data=None, **changes):
    actor = state.actor if actor is None else actor
    record = store._record(
        {
            "schema_version": 2,
            "redaction_revision": 1,
            "segment_id": segment or str(uuid4()),
            "event_id": str(uuid4()),
            **(data or {}),
        },
        actor,
        source,
        received or datetime.now(UTC) - timedelta(seconds=1),
        "a" * 64,
    )
    for key, value in changes.items():
        setattr(record, key, value)
    async with state.factory() as session, session.begin():
        session.add(record)
        await session.flush()
        state.ids.append(record.id)
    return record


async def audits(state):
    async with state.factory() as session:
        return list(
            (
                await session.scalars(
                    select(ActivityLog).where(
                        ActivityLog.resource_type == "experience",
                        ActivityLog.user_id == state.admin["user_id"],
                    )
                )
            ).all()
        )


async def discover(state, **kwargs):
    options = {"actor": state.admin, "project_ids": frozenset({state.actor["project_id"]})}
    options.update(kwargs)
    return await store.query_segments(**options)


def app_for(state):
    app = FastAPI()
    app.include_router(admin_experience.router, prefix="/api/v1/admin")
    app.dependency_overrides[require_admin] = lambda: state.admin
    app.dependency_overrides[admin_resource_scope] = lambda: AdminResourceScope(frozenset({state.actor["project_id"]}))
    return app


async def test_discovery_without_uuid_groups_exact_owner_and_sanitizes_projection(segment_store):
    state = segment_store
    segment = str(uuid4())
    await seed(state, segment=segment, data={"password": "never-return-body", "actor": {"user_id": "forged"}})
    latest = await seed(state, segment=segment, source="api", received=datetime.now(UTC) - timedelta(milliseconds=100))
    same_project_other = {"user_id": state.other["user_id"], "project_id": state.actor["project_id"]}
    await seed(state, actor=same_project_other, segment=segment)
    await seed(state, actor=state.other, segment=segment)
    result = await discover(state)
    assert result["schema_version"] == 2 and result["has_more"] is False
    assert len(result["segments"]) == 2
    own = next(row for row in result["segments"] if row["user_id"] == state.actor["user_id"])
    assert own == {
        "segment_id": segment,
        **state.actor,
        "last_received_at": latest.received_at.isoformat(),
        "event_count": 2,
    }
    assert {row["event_count"] for row in result["segments"]} == {1, 2}
    assert set(own) == {"segment_id", "user_id", "project_id", "last_received_at", "event_count"}
    assert "never-return-body" not in json.dumps(result)
    assert "forged" not in json.dumps(result)
    assert state.other["project_id"] not in json.dumps(result)
    assert result["coverage"] == {"partial": True, "reasons": ["clock_order_unknown"]}
    audit = (await audits(state))[0]
    assert audit.action == "view"
    assert audit.extra == {
        "schema_version": 2,
        "count": 2,
        "include_anonymous": False,
        "scoped": True,
        "lookup": "recent_segments",
        "days": 1,
    }
    assert state.actor["user_id"] not in json.dumps(audit.extra)


async def test_user_filter_scope_and_receive_time_not_event_time(segment_store):
    state = segment_store
    now = datetime.now(UTC)
    recent = await seed(state, received=now - timedelta(hours=12), data={"occurred_at": "2000-01-01T00:00:00+00:00"})
    week = await seed(state, received=now - timedelta(days=3))
    month = await seed(state, received=now - timedelta(days=15))
    await seed(state, received=now - timedelta(days=31))
    await seed(state, received=now + timedelta(days=1))
    await seed(state, actor=state.other)
    for days, expected in (
        (1, {recent.segment_id}),
        (7, {recent.segment_id, week.segment_id}),
        (30, {recent.segment_id, week.segment_id, month.segment_id}),
    ):
        result = await discover(state, user_id=state.actor["user_id"], days=days)
        assert {row["segment_id"] for row in result["segments"]} == expected
        assert all(
            datetime.fromisoformat(row["last_received_at"]).utcoffset() is not None for row in result["segments"]
        )
    assert (await discover(state, user_id=state.other["user_id"]))["segments"] == []
    assert (await discover(state, project_ids=frozenset(), user_id=state.actor["user_id"]))["segments"] == []
    assert len(await audits(state)) == 5
    assert all(state.actor["user_id"] not in json.dumps(row.extra) for row in await audits(state))


async def test_corrupt_summary_metadata_omitted_with_explicit_partial_reason(segment_store):
    state = segment_store
    valid = await seed(state)
    await seed(state, owner_key="f" * 64)
    await seed(state, segment_id="not-a-canonical-segment")
    await seed(state, source="unknown")
    await seed(state, data={"schema_version": 3})
    await seed(state, data={"redaction_revision": 9})
    await seed(state, data={"schema_version": None})
    await seed(state, data={"schema_version": "2"})
    await seed(state, data={"schema_version": 2.0})
    await seed(state, data={"redaction_revision": True})
    await seed(state, event_id=str(uuid4()))
    mixed = await seed(state)
    await seed(state, segment=mixed.segment_id, data={"schema_version": 1})
    await seed(state, user_id="untrusted user with spaces")
    result = await discover(state)
    assert [row["segment_id"] for row in result["segments"]] == [valid.segment_id]
    assert result["coverage"]["partial"] is True
    assert "missing_context" in result["coverage"]["reasons"]
    assert len(await audits(state)) == 1


async def test_bounded_candidate_groups_keep_conservative_has_more(segment_store):
    state = segment_store
    now = datetime.now(UTC)
    oldest = await seed(state, received=now - timedelta(minutes=3))
    newest = await seed(state, received=now - timedelta(minutes=1))
    await seed(state, segment_id="invalid-newest", received=now - timedelta(seconds=1))
    result = await discover(state, limit=1)
    assert result["segments"] == []
    assert result["has_more"] is True
    assert set(result["coverage"]["reasons"]) == {"bounded_window", "missing_context", "clock_order_unknown"}
    filtered = await discover(state, limit=3)
    assert [row["segment_id"] for row in filtered["segments"]] == [newest.segment_id, oldest.segment_id]
    assert filtered["has_more"] is False


async def test_anonymous_extra_gate_and_fresh_admin_required_before_sql(segment_store, monkeypatch):
    state = segment_store
    anonymous = await seed(state, actor={"user_id": "", "project_id": ""})
    assert anonymous.segment_id not in {
        row["segment_id"] for row in (await discover(state, project_ids=None))["segments"]
    }
    baseline = len(await audits(state))
    for options in (
        {"actor": {**state.admin, "_live_system_admin": False}},
        {"actor": {"user_id": state.admin["user_id"], "project_id": "admin-project"}},
        {"include_anonymous": True, "project_ids": None},
    ):
        with pytest.raises(PermissionError):
            await discover(state, **options)
    state.settings.experience_anonymous_read_enabled = True
    for options in (
        {"project_ids": frozenset()},
        {"project_ids": frozenset({state.actor["project_id"]})},
        {"project_ids": None, "domain_id": "domain-a"},
    ):
        with pytest.raises(PermissionError):
            await discover(state, include_anonymous=True, **options)
    assert len(await audits(state)) == baseline
    permitted = await discover(state, include_anonymous=True, project_ids=None)
    anon = next(row for row in permitted["segments"] if row["segment_id"] == anonymous.segment_id)
    assert anon["user_id"] == anon["project_id"] == ""
    assert len(await audits(state)) == baseline + 1

    def unexpected_sql():
        pytest.fail("Disabled or unauthorized disclosure must not obtain SQL")

    monkeypatch.setattr(store, "_factory", unexpected_sql)
    with pytest.raises(PermissionError):
        await discover(state, actor={**state.admin, "_live_system_admin": False})
    state.settings.experience_enabled = False
    with pytest.raises(store.ExperienceUnavailable):
        await discover(state)
    async with AsyncClient(transport=ASGITransport(app=app_for(state)), base_url="http://test") as client:
        assert (await client.get("/api/v1/admin/experiences/segments")).status_code == 404


@pytest.mark.parametrize("failure", ["select", "audit", "commit"])
async def test_sql_audit_or_commit_failure_returns_503_without_disclosure(segment_store, failure):
    state = segment_store
    record = await seed(state)
    baseline = len(await audits(state))

    def fail_sql(connection, cursor, statement, parameters, context, executemany):
        is_read = statement.lstrip().upper().startswith("SELECT") and "experience_events" in statement
        is_audit = statement.lstrip().upper().startswith("INSERT INTO activity_logs".upper())
        if (failure == "select" and is_read) or (failure == "audit" and is_audit):
            raise OperationalError("synthetic diagnostic failure", {}, RuntimeError("private-db-detail"))

    def fail_commit(connection):
        if failure == "commit":
            raise OperationalError("synthetic commit failure", {}, RuntimeError("private-db-detail"))

    event.listen(state.engine.sync_engine, "before_cursor_execute", fail_sql)
    event.listen(state.engine.sync_engine, "commit", fail_commit)
    try:
        async with AsyncClient(transport=ASGITransport(app=app_for(state)), base_url="http://test") as client:
            response = await client.get("/api/v1/admin/experiences/segments")
        assert response.status_code == 503
        assert "segments" not in response.json()
        assert record.segment_id not in response.text
        assert "private-db-detail" not in response.text
    finally:
        event.remove(state.engine.sync_engine, "before_cursor_execute", fail_sql)
        event.remove(state.engine.sync_engine, "commit", fail_commit)
    assert len(await audits(state)) == baseline


async def test_route_bounds_no_store_and_one_audit_per_disclosure(segment_store):
    state = segment_store
    row = await seed(state)
    async with AsyncClient(transport=ASGITransport(app=app_for(state)), base_url="http://test") as client:
        for params in (
            {"days": 0},
            {"days": 2},
            {"days": 31},
            {"limit": 0},
            {"limit": 51},
            {"user_id": "x" * 65},
            {"user_id": "not an id"},
        ):
            assert (await client.get("/api/v1/admin/experiences/segments", params=params)).status_code == 422
        assert await audits(state) == []
        for days in (1, 7, 30):
            response = await client.get(
                "/api/v1/admin/experiences/segments", params={"user_id": state.actor["user_id"], "days": days}
            )
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.json()["segments"][0]["segment_id"] == row.segment_id
        assert len(await audits(state)) == 3
        assert (
            await client.get("/api/v1/admin/experiences/segments", params={"include_anonymous": "true"})
        ).status_code == 403
    assert len(await audits(state)) == 3


async def test_each_request_refreshes_native_admin_and_directory_scope(segment_store, monkeypatch):
    from app.api import deps
    from app.services import domain_scope

    state = segment_store
    await seed(state)
    foreign = await seed(state, actor=state.other)
    live = SimpleNamespace(admin=True, projects={state.actor["project_id"]}, checks=0, directory_reads=0)
    token = {
        **state.admin,
        "token": "synthetic-not-real",
        "is_system_admin": True,
        "domain_id": "domain-a",
        "identity_domain_id": "domain-a",
    }

    def is_admin(*args, **kwargs):
        live.checks += 1
        return live.admin

    def projects(**kwargs):
        live.directory_reads += 1
        return [{"id": pid, "domain_id": "domain-a"} for pid in live.projects]

    monkeypatch.setattr(domain_scope, "domain_context", lambda *args, **kwargs: {})
    monkeypatch.setattr(domain_scope, "assert_token_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(deps.keystone, "validate_token", lambda *args, **kwargs: {"domain_id": "domain-a", "roles": []})
    monkeypatch.setattr(deps.keystone, "_is_system_admin", is_admin)
    directory = SimpleNamespace(identity=SimpleNamespace(get_domain=lambda value: {"id": value}, projects=projects))
    app = FastAPI()
    app.include_router(admin_experience.router, prefix="/api/v1/admin")
    app.dependency_overrides[get_token_info] = lambda: token
    app.dependency_overrides[get_admin_os_conn] = lambda: directory
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/api/v1/admin/experiences/segments", params={"domain_id": "domain-a"})
        assert first.status_code == 200
        assert {row["project_id"] for row in first.json()["segments"]} == {state.actor["project_id"]}
        live.projects = {state.other["project_id"]}
        second = await client.get("/api/v1/admin/experiences/segments", params={"domain_id": "domain-a"})
        assert second.status_code == 200
        assert [row["segment_id"] for row in second.json()["segments"]] == [foreign.segment_id]
        live.admin = False
        denied = await client.get("/api/v1/admin/experiences/segments", params={"domain_id": "domain-a"})
        assert denied.status_code == 403
        live.admin = True
        live.projects = set()
        empty = await client.get("/api/v1/admin/experiences/segments", params={"domain_id": "domain-a"})
        assert empty.status_code == 200 and empty.json()["segments"] == []

        def directory_unavailable(value):
            raise RuntimeError("private-directory-failure")

        directory.identity.get_domain = directory_unavailable
        unavailable = await client.get("/api/v1/admin/experiences/segments", params={"domain_id": "domain-a"})
        assert unavailable.status_code == 503
        assert "segments" not in unavailable.json()
        assert "private-directory-failure" not in unavailable.text
    assert live.checks == 5
    assert live.directory_reads == 3
    assert len(await audits(state)) == 3
