"""Global admin activity API against persisted rows, without a live database."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Integer, MetaData
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.activity import ActivityLog
from app.services import activity


@pytest.fixture
async def event_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    # MySQL BIGINT AUTO_INCREMENT is not SQLite INTEGER PRIMARY KEY.
    table = ActivityLog.__table__.to_metadata(MetaData())
    table.c.id.type = Integer()
    async with engine.begin() as connection:
        await connection.run_sync(table.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(activity, "is_db_available", lambda: True)
    monkeypatch.setattr(activity, "get_session_factory", lambda: factory)
    try:
        yield factory
    finally:
        await engine.dispose()


async def seed_events(factory):
    base = datetime(2026, 9, 28, 12, tzinfo=UTC)
    async with factory() as session:
        for id_, project, status, page in (
            (1, "project-a", "success", "/instances"),
            (2, "project-b", "failed", "/volumes"),
            (3, "project-a", "failed", "/instances"),
            (4, "project-b", "success", None),
            (5, "project-a", "success", "/instances"),
        ):
            session.add(
                ActivityLog(
                    id=id_,
                    created_at=base + timedelta(minutes=id_),
                    project_id=project,
                    user_id="operator",
                    username="operator",
                    resource_type="instance",
                    resource_id=f"vm-{id_}",
                    action="instance.create",
                    status=status,
                    service="nova",
                    source="afterglow",
                    page=page,
                    request_id=f"req-{id_}",
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_global_events_filter_projects_status_dates_and_cursor(admin_client, event_db):
    await seed_events(event_db)
    url = "/api/v1/admin/events?project_id=project-a&service=nova&limit=1"
    first = await admin_client.get(url)
    assert first.status_code == 200
    assert [row["id"] for row in first.json()] == [5]
    assert first.json()[0]["page"] == "/instances"
    second = await admin_client.get(url + "&before_id=5")
    assert [row["id"] for row in second.json()] == [3]
    last = await admin_client.get(url + "&before_id=3")
    assert [row["id"] for row in last.json()] == [1]
    assert (await admin_client.get(url + "&before_id=1")).json() == []
    failed = await admin_client.get("/api/v1/admin/events?project_id=project-b&status=failed&page=/volumes")
    assert [row["id"] for row in failed.json()] == [2]
    dated = await admin_client.get(
        "/api/v1/admin/events?from_at=2026-09-28T12:03:00%2B00:00&to_at=2026-09-28T12:04:00%2B00:00"
    )
    assert [row["id"] for row in dated.json()] == [4, 3]
    actor_resource = await admin_client.get("/api/v1/admin/events?username=operator&resource_id=vm-3&source=afterglow")
    assert [row["id"] for row in actor_resource.json()] == [3]


@pytest.mark.asyncio
async def test_global_event_stats_use_same_filters_and_all_rows(admin_client, event_db):
    await seed_events(event_db)
    response = await admin_client.get("/api/v1/admin/events/stats?project_id=project-a")
    assert response.status_code == 200
    assert response.json() == {
        "total": 3,
        "success": 2,
        "failed": 1,
        "started": 0,
        "by_service": [{"key": "nova", "total": 3, "failed": 1}],
        "by_project": [{"key": "project-a", "total": 3, "failed": 1}],
        "by_action": [{"key": "instance.create", "total": 3, "failed": 1}],
        "by_page": [{"key": "/instances", "total": 3, "failed": 1}],
    }
    failures = await admin_client.get("/api/v1/admin/events/stats?status=failed&service=nova")
    assert failures.json()["total"] == 2
    assert failures.json()["by_page"] == [
        {"key": "/instances", "total": 1, "failed": 1},
        {"key": "/volumes", "total": 1, "failed": 1},
    ]
    assert (await admin_client.get("/api/v1/admin/events/stats?project_id=missing")).json()["total"] == 0
    project_b = (await admin_client.get("/api/v1/admin/events/stats?project_id=project-b")).json()
    assert project_b["by_page"] == [
        {"key": "/volumes", "total": 1, "failed": 1},
        {"key": "unknown", "total": 1, "failed": 0},
    ]


@pytest.mark.asyncio
async def test_event_detail_not_found_and_legacy_metadata(admin_client, event_db):
    await seed_events(event_db)
    detail = await admin_client.get("/api/v1/admin/events/4")
    assert detail.status_code == 200
    assert detail.json()["project_id"] == "project-b"
    assert detail.json()["page"] is None
    assert detail.json()["created_at"].endswith("+00:00")
    assert (await admin_client.get("/api/v1/admin/events/999")).status_code == 404
    async with event_db() as session:
        session.add(
            ActivityLog(
                id=6,
                project_id="old",
                user_id="old",
                username="old",
                resource_type="user",
                action="user.create",
                status="success",
            )
        )
        await session.commit()
    legacy = (await admin_client.get("/api/v1/admin/events/6")).json()
    assert legacy["request_id"] is None and legacy["service"] is None and legacy["page"] is None
    assert legacy["source"] == "afterglow" and legacy["external_id"] is None
    source = await admin_client.get("/api/v1/admin/events?source=afterglow&project_id=old")
    assert [row["id"] for row in source.json()] == [6]


@pytest.mark.asyncio
async def test_events_reject_unprivileged(non_admin_client, event_db):
    await seed_events(event_db)
    for path in ("events", "events/stats", "events/1"):
        assert (await non_admin_client.get("/api/v1/admin/" + path)).status_code == 403


@pytest.mark.asyncio
async def test_events_reject_invalid_inputs(admin_client, event_db):
    await seed_events(event_db)
    for query in (
        "limit=201",
        "before_id=0",
        "from_at=2026-09-28T12:00:00",
        "to_at=2026-09-28T12:00:00",
        "status=unknown",
        "project_id=" + "x" * 65,
    ):
        assert (await admin_client.get("/api/v1/admin/events?" + query)).status_code == 422
    assert (
        await admin_client.get("/api/v1/admin/events?from_at=2026-09-29T00:00:00Z&to_at=2026-09-28T00:00:00Z")
    ).status_code == 422


@pytest.mark.asyncio
async def test_events_report_database_outage_as_unavailable(admin_client, monkeypatch):
    monkeypatch.setattr(activity, "is_db_available", lambda: False)
    for path in ("events", "events/stats", "events/1"):
        assert (await admin_client.get("/api/v1/admin/" + path)).status_code == 503


@pytest.mark.asyncio
async def test_record_masks_secrets_and_inherits_audit_metadata(event_db):
    token = activity._audit_ctx.set({"request_id": "req-1", "page": "/instances", "source": "afterglow"})
    try:
        await activity.record(
            project_id="project-a",
            user_id="operator",
            username="operator",
            resource_type="instance",
            action="instance.create",
            status="failed",
            http_status=500,
            error_message="Bearer secretSecret1234 password=hunter2",
            extra={"secret": "hunter2", "details": {"token": "sensitive", "reason": "Bearer abcdefghij api_key=xyz"}},
        )
    finally:
        activity._audit_ctx.reset(token)
    response = await activity.list_events()
    event = response[0]
    assert event["service"] == "nova" and event["source"] == "afterglow"
    assert event["request_id"] == "req-1" and event["page"] == "/instances"
    assert "secretSecret1234" not in event["error_message"]
    assert event["http_status"] == 500
    assert "hunter2" not in event["error_message"]
    assert event["extra"]["secret"] == "[redacted]"
    assert event["extra"]["details"]["token"] == "[redacted]"
    assert "abcdefghij" not in event["extra"]["details"]["reason"]
    assert "xyz" not in event["extra"]["details"]["reason"]
