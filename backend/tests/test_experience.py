"""Semantic diagnostics on actual SQLite and optional dedicated MariaDB storage.

MariaDB cases use AFTERGLOW_TEST_DATABASE_URL, the existing isolated test DB
contract. No business service/native transport is contacted.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import Integer, MetaData, delete, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.common import experience as ingest_api
from app.api.common.admin_resource_scope import AdminResourceScope, admin_resource_scope
from app.api.deps import require_admin
from app.api.identity import admin_experience
from app.models.activity import ActivityLog
from app.models.experience import (
    ExperienceAggregate,
    ExperienceCatalog,
    ExperienceEvent,
    ExperienceHold,
    ExperienceMaintenance,
    ExperienceOperationLink,
    ExperienceRecord,
)
from app.services import experience as store

pytestmark = pytest.mark.asyncio
MODELS = (
    ExperienceRecord,
    ExperienceCatalog,
    ExperienceOperationLink,
    ExperienceHold,
    ExperienceMaintenance,
    ExperienceAggregate,
    ActivityLog,
)
ACTOR = {"user_id": "user-a", "project_id": "project-a"}
ADMIN = {"user_id": "admin", "project_id": "admin-project", "_live_system_admin": True}


def wire(**changes):
    result = {
        "schema_version": 2,
        "event_id": str(uuid4()),
        "event_type": "action.started",
        "segment_id": str(uuid4()),
        "page_view_id": str(uuid4()),
        "action_id": str(uuid4()),
        "client_seq": 1,
        "client_monotonic_ms": 1.25,
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
    result.update(changes)
    return result


def context(event, actor=ACTOR):
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
        "request_id": "req-" + "a" * 32,
        "span_id": str(uuid4()),
    }


@pytest.fixture(params=["sqlite", pytest.param("mariadb", marks=pytest.mark.db)])
async def sql_store(request, monkeypatch, tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'experience.sqlite'}"
    if request.param == "mariadb":
        url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
        if not url:
            pytest.skip("Dedicated AFTERGLOW_TEST_DATABASE_URL required")
    engine = create_async_engine(url)
    monkeypatch.setitem(ADMIN, "user_id", f"experience-admin-{uuid4().hex}")
    metadata = MetaData()
    for model in MODELS:
        table = model.__table__.to_metadata(metadata)
        if request.param == "sqlite" and model is ActivityLog:
            table.c.id.type = Integer()
    async with engine.begin() as connection:
        if request.param == "mariadb":
            # These five tables belong solely to this fixture. Recreate them
            # from raw SQL107 every run; never reuse stale CREATE IF NOT EXISTS
            # results or drop the shared business activity table.
            for table in reversed(metadata.sorted_tables):
                if table.name != ActivityLog.__tablename__:
                    await connection.run_sync(lambda sync, table=table: table.drop(sync, checkfirst=True))
            migration = (Path(__file__).parents[1] / "migrations/107_experience_events.sql").read_text()
            for statement in migration.split(";"):
                if statement.strip():
                    await connection.exec_driver_sql(statement)
        await connection.run_sync(metadata.create_all)
        for table in reversed(metadata.sorted_tables):
            if table.name != ActivityLog.__tablename__:
                await connection.execute(delete(table))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = SimpleNamespace(
        experience_enabled=True,
        experience_anonymous_read_enabled=False,
        experience_detail_retention_days=30,
        experience_aggregate_retention_days=90,
    )
    monkeypatch.setattr(store, "get_settings", lambda: settings)
    monkeypatch.setattr(store, "is_db_available", lambda: True)
    monkeypatch.setattr(store, "get_session_factory", lambda: factory)
    try:
        yield factory, settings, engine
    finally:
        async with engine.begin() as connection:
            for table in reversed(metadata.sorted_tables):
                if table.name == ActivityLog.__tablename__:
                    await connection.execute(
                        delete(table).where(table.c.resource_type == "experience", table.c.user_id == ADMIN["user_id"])
                    )
                else:
                    await connection.run_sync(lambda sync, table=table: table.drop(sync, checkfirst=True))
        await engine.dispose()


async def rows(factory, model):
    async with factory() as session:
        statement = select(model)
        if model is ActivityLog:
            statement = statement.where(
                ActivityLog.resource_type == "experience", ActivityLog.user_id == ADMIN["user_id"]
            )
        return list((await session.scalars(statement)).all())


async def test_actual_storage_exact_dedup_and_atomic_conflict(sql_store):
    factory, _, _ = sql_store
    event = wire()
    parsed = ExperienceEvent.model_validate(event)
    assert await store.ingest(actor=ACTOR, events=[parsed]) == {"accepted": 1, "duplicates": 0, "schema_version": 2}
    assert (await store.ingest(actor=ACTOR, events=[parsed]))["duplicates"] == 1
    conflicting = ExperienceEvent.model_validate({**event, "client_seq": 2})
    fresh = ExperienceEvent.model_validate(wire(segment_id=event["segment_id"]))
    with pytest.raises(store.ExperienceConflict):
        await store.ingest(actor=ACTOR, events=[fresh, conflicting])
    persisted = await rows(factory, ExperienceRecord)
    assert len(persisted) == 1
    assert persisted[0].data["client_seq"] == 1
    assert persisted[0].source == "browser"
    assert persisted[0].user_id == ACTOR["user_id"]
    assert persisted[0].received_at is not None
    # Owner namespaces never let one actor poison another actor's idempotency key.
    assert (await store.ingest(actor={"user_id": "other", "project_id": "project-b"}, events=[parsed]))["accepted"] == 1


@pytest.mark.parametrize(
    "mutation",
    [
        {"actor": ACTOR},
        {"source": "worker"},
        {"backend_build": "1.2.3"},
        {"payload": {"password": "must-not-persist"}},
        {"occurred_at": "2026-01-01T00:00:00"},
        {"frontend_build": "customer free text"},
        {"route": "/instances?password=secret"},
        {"event_type": "operation.accepted"},
    ],
)
async def test_wire_cannot_forge_server_or_collect_text(mutation):
    with pytest.raises(ValidationError):
        ExperienceEvent.model_validate(wire(**mutation))


async def test_consent_finite_summary_is_component_fenced():
    consent = wire(
        event_type="view.state_changed",
        feature="mcp",
        component="mcp.consent",
        payload={"state": "ready", "step": 1, "access": "mixed", "selection": "some"},
    )
    assert ExperienceEvent.model_validate(consent).payload["access"] == "mixed"
    for change in ({"feature": "compute"}, {"component": "page"}, {"event_type": "action.started"}):
        with pytest.raises(ValidationError):
            ExperienceEvent.model_validate({**consent, **change})


async def test_actual_scope_anonymous_and_cross_scope_reference(sql_store):
    factory, settings, _ = sql_store
    segment = str(uuid4())
    foreign = wire(segment_id=segment)
    own = wire(segment_id=segment, caused_by_event_id=foreign["event_id"])
    await store.ingest(
        actor={"user_id": "user-b", "project_id": "project-b"}, events=[ExperienceEvent.model_validate(foreign)]
    )
    await store.ingest(actor=ACTOR, events=[ExperienceEvent.model_validate(own)])
    anon = wire(segment_id=segment, route="/login")
    await store.ingest(actor={}, events=[ExperienceEvent.model_validate(anon)])
    result = await store.query(segment_id=segment, actor=ADMIN, project_ids=frozenset({"project-a"}))
    assert [event["event_id"] for event in result["events"]] == [own["event_id"]]
    assert result["events"][0]["caused_by_event_id"] is None
    assert "redacted_reference" in result["coverage"]["reasons"]
    assert len(await rows(factory, ActivityLog)) == 1
    with pytest.raises(PermissionError):
        await store.query(segment_id=segment, actor=ADMIN, project_ids=None, include_anonymous=True)
    settings.experience_anonymous_read_enabled = True
    for scope in (frozenset(), frozenset({"project-a"})):
        with pytest.raises(PermissionError):
            await store.query(segment_id=segment, actor=ADMIN, project_ids=scope, include_anonymous=True)
    with pytest.raises(PermissionError):
        await store.query(
            segment_id=segment, actor={**ADMIN, "_live_system_admin": False}, project_ids=None, include_anonymous=True
        )
    result = await store.query(segment_id=segment, actor=ADMIN, project_ids=None, include_anonymous=True, export=True)
    assert len(result["events"]) == 3
    assert result["coverage"]["screen_tail"] == "unknown"
    assert len(await rows(factory, ActivityLog)) == 2


async def test_async_arrival_does_not_claim_client_or_business_order(sql_store):
    _, _, _ = sql_store
    first = wire(client_seq=1)
    later = wire(segment_id=first["segment_id"], client_seq=2, caused_by_event_id=first["event_id"])
    await store.ingest(actor=ACTOR, events=[ExperienceEvent.model_validate(later)])
    await asyncio.sleep(0)
    await store.ingest(actor=ACTOR, events=[ExperienceEvent.model_validate(first)])
    ctx = context(first)
    await store.record_server_event(context=ctx, event_type="operation.accepted", stage="native", status="accepted")
    result = await store.query(segment_id=first["segment_id"], actor=ADMIN, project_ids=frozenset({"project-a"}))
    assert result["events"][0]["status"] == "accepted"
    browser = [row for row in result["events"] if row["source"] == "browser"]
    assert [row["client_seq"] for row in browser] == [1, 2]
    assert "clock_order_unknown" in result["coverage"]["reasons"]
    assert result["coverage"]["partial"] is True


async def test_immutable_operation_origin_receipt(sql_store):
    factory, _, _ = sql_store
    event = wire()
    ctx = context(event)
    await store.bind_operation(ctx, "email_operation", "operation-1")
    await store.bind_operation(ctx, "email_operation", "operation-1")
    assert len(await rows(factory, ExperienceOperationLink)) == 1
    with pytest.raises(store.ExperienceConflict):
        await store.bind_operation(
            context(event, {"user_id": "other", "project_id": "other"}), "email_operation", "operation-1"
        )
    assert (
        await store.read_operation_context(
            "email_operation", "operation-1", {"user_id": "other", "ownership_mode": "origin_receipt"}
        )
        is None
    )
    restored = await store.read_operation_context(
        "email_operation", "operation-1", {"user_id": ACTOR["user_id"], "ownership_mode": "origin_receipt"}
    )
    assert restored["actor"] == ACTOR
    assert restored["source"] == "worker"
    assert await store.read_operation_context("email_operation", "operation-1", {"user_id": ACTOR["user_id"]}) is None
    assert (
        await store.read_operation_context(
            "email_operation", "operation-1", {"user_id": ACTOR["user_id"], "project_id": "other"}
        )
        is None
    )


async def test_retention_dry_run_holds_rollup_and_mixed_schema(sql_store):
    factory, _, _ = sql_store
    now = datetime.now(UTC)
    held, old, expired, mixed = [wire() for _ in range(4)]
    await store.ingest(
        actor=ACTOR, events=[ExperienceEvent.model_validate(value) for value in (held, old, expired, mixed)]
    )
    async with factory() as session, session.begin():
        persisted = list((await session.scalars(select(ExperienceRecord).order_by(ExperienceRecord.id))).all())
        for index, record in enumerate(persisted):
            record.received_at = now - timedelta(days=100 if index == 2 else 31)
        persisted[3].data = ["must-not-export"]
        session.add(ExperienceHold(owner_key=store._digest(ACTOR), segment_id=held["segment_id"]))
        session.add(
            ExperienceAggregate(
                id="f" * 64,
                day=(now - timedelta(days=91)).date(),
                project_id="project-a",
                source="browser",
                feature="compute",
                event_type="action.started",
                count=9,
            )
        )
    dry = await store.retain(now=now)
    assert dry["detail_candidates"] == 3 and dry["detail_deleted"] == 0
    assert len(await rows(factory, ExperienceRecord)) == 4
    applied = await store.retain(apply=True, now=now)
    assert applied["detail_deleted"] == 3 and applied["aggregate_deleted"] == 1
    assert [row.segment_id for row in await rows(factory, ExperienceRecord)] == [held["segment_id"]]
    aggregates = await rows(factory, ExperienceAggregate)
    assert len(aggregates) == 1 and aggregates[0].count == 1
    assert (await store.retain(apply=True, now=now))["detail_deleted"] == 0
    projected = await store.query(segment_id=held["segment_id"], actor=ADMIN, project_ids=None)
    assert "must-not-export" not in json.dumps(projected)


async def test_api_boundaries_disabled_invalid_credential_and_limits(sql_store, monkeypatch):
    factory, settings, _ = sql_store
    app = FastAPI()
    app.include_router(ingest_api.router, prefix="/api/v1/activity")
    app.include_router(admin_experience.router, prefix="/api/v1/admin")
    app.dependency_overrides[require_admin] = lambda: ADMIN
    app.dependency_overrides[admin_resource_scope] = lambda: AdminResourceScope()

    async def reject(*args, **kwargs):
        raise HTTPException(401, "Invalid credential")

    monkeypatch.setattr(ingest_api, "get_token_info", reject)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        settings.experience_enabled = False
        assert (await client.get("/api/v1/activity/experience-contract")).status_code == 404
        assert (await client.post("/api/v1/activity/experience-events", json={})).status_code == 404
        assert (await client.get("/api/v1/admin/experiences", params={"segment_id": str(uuid4())})).status_code == 404
        settings.experience_enabled = True
        assert (await client.get("/api/v1/activity/experience-contract")).json()["max_body_bytes"] == 32768
        body = {"schema_version": 2, "events": [wire(route="/login")]}
        response = await client.post(
            "/api/v1/activity/experience-events", json=body, headers={"Authorization": "Bearer invalid"}
        )
        assert response.status_code == 401
        assert await rows(factory, ExperienceRecord) == []
        assert (
            await client.post(
                "/api/v1/activity/experience-events", content="x" * 32769, headers={"content-type": "application/json"}
            )
        ).status_code == 413
        assert (
            await client.post(
                "/api/v1/activity/experience-events",
                json={"schema_version": 2, "events": [wire(route="/login") for _ in range(21)]},
            )
        ).status_code == 422
        malformed = await client.post(
            "/api/v1/activity/experience-events",
            json={"schema_version": 2, "events": [wire(payload={"password": "must-not-echo"})]},
        )
        assert malformed.status_code == 422 and "must-not-echo" not in malformed.text
        response = await client.post("/api/v1/activity/experience-events", json=body)
        assert response.status_code == 201 and response.json()["accepted"] == 1
        receipt = (await rows(factory, ExperienceRecord))[0]
        assert receipt.data["request_id"] == response.headers["x-request-id"]
        assert receipt.data["request_id"].startswith("req-")


async def test_sql_failure_never_discloses_without_persisted_audit(sql_store):
    factory, _, engine = sql_store
    if engine.dialect.name != "sqlite":
        pytest.skip("Audit-table DDL failure injection is confined to the owned SQLite fixture")
    event = wire()
    await store.ingest(actor=ACTOR, events=[ExperienceEvent.model_validate(event)])
    async with engine.begin() as connection:
        await connection.run_sync(ActivityLog.__table__.drop)
    from sqlalchemy.exc import SQLAlchemyError

    with pytest.raises(SQLAlchemyError):
        await store.query(segment_id=event["segment_id"], actor=ADMIN, project_ids=None)
    # Restore only this owned fixture table so teardown remains bounded.
    metadata = MetaData()
    audit = ActivityLog.__table__.to_metadata(metadata)
    if engine.dialect.name == "sqlite":
        audit.c.id.type = Integer()
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    assert await rows(factory, ActivityLog) == []


async def test_catalog_is_exact_retained_revision_not_latest_fallback(sql_store, monkeypatch):
    factory, _, _ = sql_store
    from app.services import experience_catalog

    revision, messages = experience_catalog._catalog()
    key = next(key for key, translations in messages.items() if "ko" in translations)
    event = wire(
        event_type="message.presented",
        catalog_revision=revision,
        payload={"key": key, "locale": "ko", "tone": "warning", "restoration": "restored"},
    )
    await store.ingest(actor=ACTOR, events=[ExperienceEvent.model_validate(event)])
    retained = await rows(factory, ExperienceCatalog)
    assert len(retained) == 1
    expected = retained[0].template
    # A later deployment can stop recognizing the key. History still uses the
    # originally retained exact static entry, not the current resolver.
    monkeypatch.setattr(experience_catalog, "is_known_message_key", lambda key: False)
    monkeypatch.setattr(experience_catalog, "catalog_entry", lambda *args: None)
    projection = await store.query(segment_id=event["segment_id"], actor=ADMIN, project_ids=None)
    assert projection["catalogs"] == [{"revision": revision, "key": key, "locale": "ko", "template": expected}]
    assert "template" not in projection["events"][0]["payload"]
    old = wire(
        event_type="message.presented",
        catalog_revision="f" * 64,
        payload={"key": key, "locale": "ko", "tone": "info", "restoration": "restored"},
    )
    monkeypatch.setattr(experience_catalog, "is_known_message_key", lambda key: True)
    await store.ingest(actor=ACTOR, events=[ExperienceEvent.model_validate(old)])
    unavailable = await store.query(segment_id=old["segment_id"], actor=ADMIN, project_ids=None)
    assert unavailable["catalogs"] == []
    assert unavailable["events"][0]["payload"]["restoration"] == "unavailable"


@pytest.mark.parametrize("mismatch", ["revision", "key", "locale", "missing"])
async def test_catalog_restoration_is_validated_per_authorized_message(sql_store, mismatch):
    factory, _, _ = sql_store
    from app.services.experience_catalog import _catalog

    revision, messages = _catalog()
    keys = [key for key, translations in messages.items() if "ko" in translations]
    segment = str(uuid4())
    invalid = wire(
        segment_id=segment,
        event_type="message.presented",
        catalog_revision=revision,
        payload={"key": keys[0], "locale": "ko", "tone": "warning", "restoration": "restored"},
    )
    valid = {**invalid, "event_id": str(uuid4()), "client_seq": 2}
    await store.ingest(
        actor=ACTOR, events=[ExperienceEvent.model_validate(invalid), ExperienceEvent.model_validate(valid)]
    )
    foreign = {
        **invalid,
        "event_id": str(uuid4()),
        "payload": {**invalid["payload"], "key": keys[1]},
    }
    await store.ingest(
        actor={"user_id": "foreign-user", "project_id": "foreign-project"},
        events=[ExperienceEvent.model_validate(foreign)],
    )
    async with factory() as session, session.begin():
        record = await session.scalar(select(ExperienceRecord).where(ExperienceRecord.event_id == invalid["event_id"]))
        if mismatch == "revision":
            record.data = {**record.data, "catalog_revision": "f" * 64}
        elif mismatch in {"key", "locale"}:
            record.data = {
                **record.data,
                "payload": {**record.data["payload"], mismatch: keys[1] if mismatch == "key" else "en"},
            }
        else:
            record.catalog_id = None
    projected = await store.query(segment_id=segment, actor=ADMIN, project_ids=frozenset({ACTOR["project_id"]}))
    by_id = {event["event_id"]: event for event in projected["events"]}
    assert set(by_id) == {invalid["event_id"], valid["event_id"]}
    assert by_id[valid["event_id"]]["payload"]["restoration"] == "restored"
    assert by_id[invalid["event_id"]]["payload"]["restoration"] == "unavailable"
    assert [(catalog["revision"], catalog["key"], catalog["locale"]) for catalog in projected["catalogs"]] == [
        (revision, keys[0], "ko")
    ]
    assert "catalog_unavailable" in projected["coverage"]["reasons"]


async def test_mixed_schema_metadata_and_child_refs_are_sanitized_again(sql_store):
    factory, _, _ = sql_store
    event = wire()
    await store.ingest(actor=ACTOR, events=[ExperienceEvent.model_validate(event)])
    async with factory() as session, session.begin():
        record = await session.scalar(select(ExperienceRecord))
        record.data = {**record.data, "arbitrary": {"token": "must-not-export"}}
        malformed = store._record(
            {
                "schema_version": 1,
                "segment_id": event["segment_id"],
                "event_id": str(uuid4()),
                "span_id": ["invalid"],
                "password": "must-not-export",
            },
            ACTOR,
            "api",
            datetime.now(UTC),
            "a" * 64,
        )
        session.add(malformed)
        null_payload = {
            **context(event),
            "schema_version": 2,
            "redaction_revision": 1,
            "event_id": str(uuid4()),
            "event_type": "stage.completed",
            "stage": "native",
            "status": "observed",
            "payload": None,
        }
        session.add(store._record(null_payload, ACTOR, "api", datetime.now(UTC), "b" * 64))
    projection = await store.query(segment_id=event["segment_id"], actor=ADMIN, project_ids=None)
    assert len(projection["events"]) == 1
    assert "missing_context" in projection["coverage"]["reasons"]
    assert "must-not-export" not in json.dumps(projection)


async def test_default_off_server_sink_and_link_do_not_touch_sql(sql_store):
    factory, settings, _ = sql_store
    settings.experience_enabled = False
    event = wire()
    await store.record_server_event(
        context=context(event), event_type="request.started", stage="request", status="observed"
    )
    await store.bind_operation(context(event), "mcp_invocation", "invocation-1")
    assert await store.read_operation_context("mcp_invocation", "invocation-1", ACTOR) is None
    assert await rows(factory, ExperienceRecord) == []
    assert await rows(factory, ExperienceOperationLink) == []
    assert await rows(factory, ActivityLog) == []


async def test_workspace_selection_summary_is_component_action_fenced():
    selected = wire(
        event_type="view.state_changed",
        feature="iam",
        component="page",
        action="select",
        payload={"state": "ready", "selection_kind": "home"},
    )
    assert ExperienceEvent.model_validate(selected).payload["selection_kind"] == "home"
    for change in ({"feature": "auth"}, {"component": "shared.form"}, {"action": "view"}):
        with pytest.raises(ValidationError):
            ExperienceEvent.model_validate({**selected, **change})


async def test_hold_scope_cannot_be_borrowed_by_another_owner(sql_store):
    factory, _, _ = sql_store
    now = datetime.now(UTC)
    event = wire()
    other = {"user_id": "other", "project_id": "project-b"}
    await store.ingest(actor=ACTOR, events=[ExperienceEvent.model_validate(event)])
    await store.ingest(actor=other, events=[ExperienceEvent.model_validate(event)])
    await store.bind_operation(context(event), "mcp_invocation", "held-operation")
    await store.bind_operation(context(event, other), "mcp_invocation", "other-operation")
    async with factory() as session, session.begin():
        for record in (await session.scalars(select(ExperienceRecord))).all():
            record.received_at = now - timedelta(days=31)
        for link in (await session.scalars(select(ExperienceOperationLink))).all():
            link.created_at = now - timedelta(days=31)
        session.add(ExperienceHold(owner_key=store._digest(ACTOR), segment_id=event["segment_id"]))
    result = await store.retain(apply=True, now=now)
    assert result["detail_deleted"] == 1
    assert [row.user_id for row in await rows(factory, ExperienceRecord)] == [ACTOR["user_id"]]
    assert [row.operation_id for row in await rows(factory, ExperienceOperationLink)] == ["held-operation"]


async def test_browser_parent_span_is_preserved_only_in_same_owner_scope(sql_store):
    _, _, _ = sql_store
    parent = wire(span_id=str(uuid4()))
    child = wire(segment_id=parent["segment_id"], parent_span_id=parent["span_id"])
    await store.ingest(
        actor=ACTOR, events=[ExperienceEvent.model_validate(parent), ExperienceEvent.model_validate(child)]
    )
    result = await store.query(segment_id=parent["segment_id"], actor=ADMIN, project_ids=frozenset({"project-a"}))
    projected = next(row for row in result["events"] if row["event_id"] == child["event_id"])
    assert projected["parent_span_id"] == parent["span_id"]


async def test_server_unknown_labels_and_unverified_private_request_are_honest(sql_store):
    _, settings, _ = sql_store
    event = wire()
    ctx = {**context(event, {}), "feature": "unknown", "action": "unknown", "component": "unknown"}
    await store.record_server_event(context=ctx, event_type="request.completed", stage="request", status="observed")
    assert (await store.query(segment_id=event["segment_id"], actor=ADMIN, project_ids=None))["events"] == []
    settings.experience_anonymous_read_enabled = True
    result = await store.query(segment_id=event["segment_id"], actor=ADMIN, project_ids=None, include_anonymous=True)
    assert result["events"][0]["feature"] == "unknown"
    assert result["events"][0]["route"] == "/instances"


async def test_server_capture_time_is_distinct_from_actual_receipt(sql_store):
    factory, _, _ = sql_store
    event = wire()
    captured = datetime.now(UTC) - timedelta(seconds=5)
    await store.record_server_event(
        context=context(event), event_type="request.started", stage="request", status="observed", occurred_at=captured
    )
    stored = (await rows(factory, ExperienceRecord))[0]
    assert datetime.fromisoformat(stored.data["occurred_at"]) == captured
    assert stored.received_at.replace(tzinfo=UTC) > captured
    projected = await store.query(segment_id=event["segment_id"], actor=ADMIN, project_ids=None)
    assert datetime.fromisoformat(projected["events"][0]["occurred_at"]) == captured
    with pytest.raises(ValueError):
        await store.record_server_event(
            context=context(event),
            event_type="request.started",
            stage="request",
            status="observed",
            occurred_at=datetime.now(),
        )
    assert len(await rows(factory, ExperienceRecord)) == 1


async def test_verified_http_status_is_server_only_and_not_business_readiness(sql_store):
    factory, _, _ = sql_store
    event = wire(event_type="result.received", payload={"stage": "response", "http_status": 201})
    await store.ingest(actor=ACTOR, events=[ExperienceEvent.model_validate(event)])
    for code in (200, 201, 202, 403, 503):
        await store.record_server_event(
            context=context(event), event_type="request.completed", stage="request", status="observed", http_status=code
        )
    projected = await store.query(segment_id=event["segment_id"], actor=ADMIN, project_ids=None)
    browser = next(row for row in projected["events"] if row["source"] == "browser")
    assert browser["http_status"] is None and browser["payload"]["http_status"] == 201
    server = [row for row in projected["events"] if row["source"] != "browser"]
    assert {row["http_status"] for row in server} == {200, 201, 202, 403, 503}
    assert {row["status"] for row in server} == {"observed"}
    for invalid in (True, 99, 600, "200"):
        with pytest.raises(ValueError):
            await store.record_server_event(
                context=context(event),
                event_type="request.completed",
                stage="request",
                status="observed",
                http_status=invalid,
            )
    with pytest.raises(ValueError):
        await store.record_server_event(
            context=context(event), event_type="operation.accepted", stage="native", status="accepted", http_status=202
        )
    assert len(await rows(factory, ExperienceRecord)) == 6


@pytest.mark.db
async def test_mariadb_migration_107_has_exact_owner_scoped_hold_schema(sql_store):
    # This explicit marker also makes the canonical DB target discover this
    # module; parameter-level MariaDB marks alone are not a source selector.
    _, _, engine = sql_store
    if engine.dialect.name not in {"mysql", "mariadb"}:
        pytest.skip("Raw MariaDB migration metadata assertion")
    async with engine.connect() as connection:
        primary_key = await connection.run_sync(lambda sync: inspect(sync).get_pk_constraint("experience_holds"))
        link_columns = await connection.run_sync(lambda sync: inspect(sync).get_columns("experience_operation_links"))
    assert primary_key["constrained_columns"] == ["owner_key", "segment_id"]
    owner = next(column for column in link_columns if column["name"] == "owner_key")
    assert owner["nullable"] is False


@pytest.mark.db
async def test_catalog_selected_for_gc_survives_a_newly_committed_message(sql_store, monkeypatch):
    """An accepted message must not lose its exact template to stale GC candidates."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.experience_catalog import _catalog

    factory, _, engine = sql_store
    if engine.dialect.name not in {"mysql", "mariadb"}:
        pytest.skip("Concurrent native MariaDB DML snapshot behavior")
    # Exercise the supported native isolation mode without gap locks masking
    # the stale-candidate race. The fixture owns this engine and its pool.
    engine.update_execution_options(isolation_level="READ COMMITTED")
    revision, messages = _catalog()
    key = next(key for key, translations in messages.items() if "ko" in translations)
    original_event = wire(
        event_type="message.presented",
        catalog_revision=revision,
        payload={"key": key, "locale": "ko", "tone": "info", "restoration": "restored"},
    )
    await store.ingest(actor=ACTOR, events=[ExperienceEvent.model_validate(original_event)])
    async with factory() as session, session.begin():
        await session.execute(delete(ExperienceRecord))
    fresh = ExperienceEvent.model_validate({**original_event, "event_id": str(uuid4()), "client_seq": 2})
    original_scalars = AsyncSession.scalars
    interleaved = False

    async def commit_after_gc_selection(session, statement, *args, **kwargs):
        nonlocal interleaved
        result = await original_scalars(session, statement, *args, **kwargs)
        selected = getattr(statement, "column_descriptions", ())
        if not interleaved and any(
            column.get("entity") is ExperienceCatalog and column.get("name") == "id" for column in selected
        ):
            interleaved = True
            await store.ingest(actor=ACTOR, events=[fresh])
        return result

    monkeypatch.setattr(AsyncSession, "scalars", commit_after_gc_selection)
    await store.retain(apply=True)
    assert interleaved
    projected = await store.query(segment_id=original_event["segment_id"], actor=ADMIN, project_ids=None)
    assert len(projected["events"]) == 1
    assert projected["events"][0]["payload"]["restoration"] == "restored"
    assert [(entry["revision"], entry["key"], entry["locale"]) for entry in projected["catalogs"]] == [
        (revision, key, "ko")
    ]
