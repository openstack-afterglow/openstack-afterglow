"""Persisted API/privacy contracts; no cloud or production datastore access."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import Integer, MetaData, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.responses import JSONResponse, StreamingResponse

from app.api.common import interactions
from app.main import activity_audit_middleware
from app.models.activity import ActivityLog
from app.services import activity
from app.utils.auth_diagnostics import authentication_operation, authentication_step

ACTOR = {"user_id": "verified-user", "project_id": "verified-project", "username": "verified-name"}


@pytest.fixture
async def interaction_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
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


def observation(**changes):
    return {
        "kind": "click",
        "page": "/login",
        "control": "button",
        "ordinal": 0,
        "interaction_id": str(uuid4()),
        **changes,
    }


def interaction_application():
    application = FastAPI()
    application.state.limiter = interactions.limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    application.middleware("http")(activity_audit_middleware)
    application.include_router(interactions.router, prefix="/api/v1/activity")
    return application


@pytest.fixture
async def interaction_client(interaction_db):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=interaction_application()), base_url="http://audit.test"
    ) as client:
        yield client


async def stored(factory):
    async with factory() as session:
        return (await session.execute(select(ActivityLog).order_by(ActivityLog.id))).scalars().all()


@pytest.mark.asyncio
async def test_anonymous_browser_observation_is_not_login_success(interaction_client, interaction_db):
    event = observation()
    response = await interaction_client.post("/api/v1/activity/interactions", json={"events": [event]})
    assert response.status_code == 201 and response.json() == {"accepted": 1}
    rows = await stored(interaction_db)
    assert len(rows) == 1  # no recursive audit of ingestion
    row = rows[0]
    assert (row.user_id, row.project_id, row.username) == ("", "", "")
    assert (row.source, row.status, row.resource_type, row.action) == ("browser", "observed", "ui", "ui.click")
    assert row.request_id is None and row.http_status is None
    stats = await activity.event_stats(source="browser", status="observed")
    assert stats["observed"] == stats["total"] == 1 and stats["success"] == 0
    assert (await activity.list_events(interaction_id=event["interaction_id"]))[0]["id"] == row.id


@pytest.mark.asyncio
async def test_actor_comes_only_from_verified_auth_and_dynamic_paths_are_erased(
    interaction_client, interaction_db, monkeypatch
):
    async def verified(request, authorization, project):
        assert authorization == "Bearer supplied" and project == "requested-project"
        return ACTOR.copy()

    monkeypatch.setattr(interactions, "get_token_info", verified)
    event = observation(
        page="/dashboard/compute/instances/private-resource", destination="/admin/projects/[id]/resources"
    )
    response = await interaction_client.post(
        "/api/v1/activity/interactions",
        json={"events": [event]},
        headers={"Authorization": "Bearer supplied", "X-Project-Id": "requested-project"},
    )
    assert response.status_code == 201
    row = (await stored(interaction_db))[0]
    assert row.user_id == ACTOR["user_id"] and row.project_id == ACTOR["project_id"]
    assert row.page == "/dashboard/compute/instances/:id"
    assert row.extra["destination"] == "/admin/projects/:id/resources"
    assert "private-resource" not in json.dumps(row.extra)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("user_id", "spoof"),
        ("project_id", "spoof"),
        ("status", "success"),
        ("success", True),
        ("value", "password"),
        ("query", "secret"),
        ("label", "secret"),
        ("error_message", "secret"),
        ("ordinal", True),
        ("ordinal", 10001),
        ("interaction_id", "not-a-uuid"),
        ("kind", "login"),
        ("page", "/login?password=secret"),
        ("page", "/recover/secret#token"),
        ("destination", "https://secret.example"),
    ],
)
async def test_untrusted_fields_never_persist(interaction_client, interaction_db, field, value):
    response = await interaction_client.post(
        "/api/v1/activity/interactions", json={"events": [observation(**{field: value})]}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid interaction observations"}
    assert await stored(interaction_db) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 503])
async def test_invalid_bearer_never_downgrades_to_anonymous(interaction_client, interaction_db, monkeypatch, status):
    async def denied(*_args):
        raise HTTPException(status, "Authentication unavailable")

    monkeypatch.setattr(interactions, "get_token_info", denied)
    response = await interaction_client.post(
        "/api/v1/activity/interactions", json={"events": [observation()]}, headers={"Authorization": "Bearer invalid"}
    )
    assert response.status_code == status and await stored(interaction_db) == []


@pytest.mark.asyncio
async def test_bounds_anonymous_private_pages_and_missing_store_are_explicit(
    interaction_client, interaction_db, monkeypatch
):
    for events in ([], [observation() for _ in range(21)]):
        assert (
            await interaction_client.post("/api/v1/activity/interactions", json={"events": events})
        ).status_code == 422
    assert (
        await interaction_client.post(
            "/api/v1/activity/interactions", json={"events": [observation(page="/admin/events")]}
        )
    ).status_code == 401
    assert (
        await interaction_client.post(
            "/api/v1/activity/interactions", content=b"x" * 16385, headers={"Content-Type": "application/json"}
        )
    ).status_code == 413

    async def chunks():
        yield b"{" * 8192
        yield b"x" * 8193

    assert (
        await interaction_client.post(
            "/api/v1/activity/interactions", content=chunks(), headers={"Content-Type": "application/json"}
        )
    ).status_code == 413
    assert await stored(interaction_db) == []
    monkeypatch.setattr(activity, "is_db_available", lambda: False)
    response = await interaction_client.post("/api/v1/activity/interactions", json={"events": [observation()]})
    assert response.status_code == 503 and "accepted" not in response.json()


@pytest.mark.asyncio
async def test_browser_batch_rolls_back_if_commit_fails(interaction_client, interaction_db, monkeypatch):
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.ext.asyncio import AsyncSession

    async def failed_commit(_session):
        raise OperationalError("insert", {}, RuntimeError("secret"))

    with monkeypatch.context() as context:
        context.setattr(AsyncSession, "commit", failed_commit)
        response = await interaction_client.post(
            "/api/v1/activity/interactions", json={"events": [observation(), observation()]}
        )
    assert response.status_code == 503 and "secret" not in response.text
    assert await stored(interaction_db) == []


@pytest.mark.asyncio
async def test_ingestion_rate_limit_is_real_and_does_not_persist_rejected_batch(interaction_db, monkeypatch):
    monkeypatch.setattr(interactions.limiter, "enabled", True)
    transport = httpx.ASGITransport(app=interaction_application(), client=("192.0.2.218", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://audit.test") as client:
        for _ in range(60):
            assert (
                await client.post("/api/v1/activity/interactions", json={"events": [observation()]})
            ).status_code == 201
        assert (await client.post("/api/v1/activity/interactions", json={"events": [observation()]})).status_code == 429
    assert len(await stored(interaction_db)) == 60


@pytest.mark.asyncio
async def test_auth_failure_and_recovered_intermediate_failure_are_structural(interaction_db):
    application = interaction_application()

    @application.post("/api/v1/auth/login")
    async def login():
        with authentication_operation("login"):
            try:
                with authentication_step("authenticate"):
                    raise RuntimeError("password=never-retain-attempted-user")
            except RuntimeError:
                return JSONResponse({"detail": "secret"}, status_code=401)

    @application.get("/api/v1/handled/{resource_id}")
    async def handled(request: Request, resource_id: str):
        request.state.token_info = ACTOR.copy()
        logging.getLogger("app.services.example").warning("password=%s", "never-retain-log-value")
        return {"ok": True}

    iid = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://audit.test"
    ) as client:
        failure = await client.post(
            "/api/v1/auth/login?password=never-retain-query",
            json={"username": "attempted", "password": "never-retain-body"},
        )
        success = await client.get("/api/v1/handled/never-retain-path", headers={"X-Afterglow-Interaction-Id": iid})
    assert failure.status_code == 401 and success.status_code == 200
    rows = await activity.list_events(limit=100)
    failures = [row for row in rows if row["request_id"] == failure.headers["X-Request-Id"]]
    assert all(row["user_id"] == row["username"] == row["project_id"] == "" for row in failures)
    assert any(row["extra"]["stage"] == "authenticate" and row["status"] == "failed" for row in failures)
    correlated = await activity.list_events(interaction_id=iid)
    assert {row["status"] for row in correlated} == {"success", "failed"}
    assert all(row["extra"]["route"] == "/api/v1/handled/{resource_id}" for row in correlated)
    assert any(row["extra"]["stage"] == "application_warning" for row in correlated)
    serialized = json.dumps(rows)
    for secret in ("never-retain", "attempted", "secret", "password="):
        assert secret not in serialized


@pytest.mark.asyncio
async def test_successful_login_keeps_exact_actor_and_one_business_terminal(interaction_db):
    application = interaction_application()

    @application.post("/api/v1/auth/login")
    async def login():
        with authentication_operation("login"):
            with authentication_step("authenticate"):
                pass
            await activity.record(**ACTOR, resource_type="auth", action="login", status="success")
        return {"ok": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://audit.test"
    ) as client:
        response = await client.post("/api/v1/auth/login")
    rows = await activity.list_events(request_id=response.headers["X-Request-Id"])
    assert sum(row["action"] == "login" and row["status"] == "success" for row in rows) == 1
    assert all(row["user_id"] == ACTOR["user_id"] for row in rows)
    assert any(row["extra"]["stage"] == "authenticate" for row in rows)


@pytest.mark.asyncio
async def test_poll_noise_excluded_and_stream_handshake_not_success(interaction_db):
    application = interaction_application()

    @application.get("/api/v1/poll")
    async def poll():
        return {"ok": True}

    @application.post("/api/v1/instances/async")
    async def stream():
        async def body():
            yield "data: complete\n\n"

        return StreamingResponse(body(), media_type="text/event-stream")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://audit.test"
    ) as client:
        assert (await client.get("/api/v1/poll")).status_code == 200
        assert (await client.post("/api/v1/instances/async")).status_code == 200
    assert await stored(interaction_db) == []


@pytest.mark.asyncio
async def test_intermediate_log_capture_is_bounded_and_contains_no_values(interaction_db):
    application = interaction_application()

    @application.get("/api/v1/noisy")
    async def noisy():
        for _ in range(100):
            logging.getLogger("app.services.example").error("secret=%s", "never-retain")
        return {"ok": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://audit.test"
    ) as client:
        response = await client.get("/api/v1/noisy")
    assert response.status_code == 200
    rows = await activity.list_events(limit=100)
    assert sum(row["status"] == "failed" for row in rows) == 64
    assert len(rows) == 66  # bounded evidence + truncation marker + terminal
    assert "never-retain" not in json.dumps(rows)


@pytest.mark.asyncio
async def test_anonymous_resource_and_authenticated_ticket_paths_never_persist_raw_segments(interaction_db):
    application = interaction_application()

    @application.post("/api/v1/instances/{instance_id}")
    async def anonymous_failure(instance_id: str):
        return JSONResponse({"detail": "Rejected"}, status_code=401)

    @application.post("/api/v1/cloud-shell/{ticket}")
    async def authenticated_ticket(request: Request, ticket: str):
        request.state.token_info = ACTOR.copy()
        return JSONResponse({"detail": "Expired"}, status_code=409)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://audit.test"
    ) as client:
        await client.post("/api/v1/instances/PATH_SECRET")
        await client.post("/api/v1/cloud-shell/TICKET_SECRET")
    rows = await activity.list_events()
    assert len(rows) == 2 and all(row["resource_id"] is None for row in rows)
    assert "PATH_SECRET" not in json.dumps(rows) and "TICKET_SECRET" not in json.dumps(rows)


@pytest.mark.asyncio
async def test_request_stages_commit_once_and_close_context_without_retaining_request(interaction_db, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    commits = []
    original_commit = AsyncSession.commit

    async def counted_commit(session):
        commits.append(True)
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", counted_commit)
    application = interaction_application()
    holders = []

    @application.post("/api/v1/auth/login")
    async def login():
        holders.append(activity._audit_ctx.get())
        with authentication_step("resolve"):
            pass
        with authentication_step("authenticate"):
            pass
        return JSONResponse({"detail": "Rejected"}, status_code=401)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://audit.test"
    ) as client:
        await client.post("/api/v1/auth/login", json={"password": "BODY_SECRET"})
    assert len(commits) == 1 and len(await stored(interaction_db)) == 4
    assert holders[0]["closed"] is True and "request" not in holders[0]
    assert holders[0]["metadata"]["route"] == "/api/v1/auth/login"
