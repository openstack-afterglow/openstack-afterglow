"""Current native signals + durable SQL episodes; no live cloud or mail calls."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import RuntimeSetting
from app.services import mail_resource_notifications as signals

CLOCK = datetime(2026, 11, 3, 12, tzinfo=UTC)


@pytest_asyncio.fixture
async def episodes(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mail-signals.sqlite'}")
    async with engine.begin() as connection:
        await connection.run_sync(RuntimeSetting.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.parametrize(
    "remaining,expected",
    [
        (7 * 86400 + 1, None),
        (7 * 86400, "week"),
        (3 * 86400, "threeDays"),
        (86400, "oneDay"),
        (0, "expired"),
        (-1, "expired"),
    ],
)
def test_deadline_bell_boundaries_select_the_corresponding_email_window(remaining, expected):
    schedule = SimpleNamespace(
        last_error=None, state="active", expires_at=(CLOCK + timedelta(seconds=remaining)).isoformat()
    )
    assert signals._urgency(schedule, CLOCK) == expected


def test_completed_schedule_is_quiet_but_uncertain_native_work_remains_attention():
    schedule = SimpleNamespace(last_error=None, state="complete", expires_at=CLOCK.isoformat())
    assert signals._urgency(schedule, CLOCK) is None
    schedule.state = "delete_requested"
    assert signals._urgency(schedule, CLOCK) == "attention"


@pytest.mark.parametrize(
    "limit,used,expected",
    [(-1, 100000, None), (0, 0, None), (0, 1, "full"), (100, 89, None), (100, 90, "warning"), (100, 100, "full")],
)
def test_native_quota_alerts_do_not_invent_usage_or_treat_unlimited_as_full(limit, used, expected):
    result = signals._quota_signal("cores", {"limit": limit, "in_use": used}, "project")
    assert (result[0] if result else None) == (f"cores:{expected}" if expected else None)


@pytest.mark.parametrize(
    "entry",
    [
        {"limit": 10},
        {"in_use": 10},
        {"limit": True, "in_use": 0},
        {"limit": 10, "in_use": -1},
        {"limit": 10, "in_use": float("nan")},
    ],
)
def test_unknown_quota_fields_cannot_authorize_alert_mail(entry):
    with pytest.raises(ValueError):
        signals._quota_signal("cores", entry, "project")


@pytest.mark.asyncio
async def test_polling_and_restarts_do_not_repeat_an_active_episode_but_recurrence_is_new(episodes):
    signal = {"instance_error:current": signals.Signal("Instance alert", "Safe current project alert")}
    first = await signals._claim_episodes(episodes, "mail.episode", signal, {"instance_error:"})
    name, episode, _ = first[0]
    await signals._mark_queued(episodes, "mail.episode", name, episode)
    assert await signals._claim_episodes(episodes, "mail.episode", signal, {"instance_error:"}) == []
    # Missing observation is not a health transition and must retain dedup.
    assert await signals._claim_episodes(episodes, "mail.episode", {}, set()) == []
    assert await signals._claim_episodes(episodes, "mail.episode", signal, {"instance_error:"}) == []
    await signals._claim_episodes(episodes, "mail.episode", {}, {"instance_error:"})
    recurrence = await signals._claim_episodes(episodes, "mail.episode", signal, {"instance_error:"})
    assert recurrence[0][1] != episode


@pytest.mark.asyncio
async def test_queue_failure_keeps_the_same_pending_episode_for_idempotent_enqueue(episodes):
    signal = {"usage:vm:revision:oneDay": signals.Signal("Usage reminder", "Safe deadline")}
    first = await signals._claim_episodes(episodes, "mail.episode", signal, {"usage:"})
    retried = await signals._claim_episodes(episodes, "mail.episode", signal, {"usage:"})
    assert first[0][1] == retried[0][1]
    await signals._mark_queued(episodes, "mail.episode", first[0][0], first[0][1])
    assert await signals._claim_episodes(episodes, "mail.episode", signal, {"usage:"}) == []


def connection(project="project", native_project=None, servers=None):
    proof = SimpleNamespace(project_id=native_project or project, project_scoped=True, system_scoped=False)
    proxy = SimpleNamespace(request=lambda *args, **kwargs: None, servers=lambda **kwargs: servers or [])
    return SimpleNamespace(
        session=SimpleNamespace(auth=SimpleNamespace(get_access=lambda session: proof)),
        compute=proxy,
        close=lambda: None,
    )


def quotas(monkeypatch):
    monkeypatch.setattr(
        signals.nova,
        "get_project_quota",
        lambda *args, **kwargs: {name: {"in_use": 0, "limit": 100} for name in ("instances", "cores", "ram")},
    )
    monkeypatch.setattr(
        signals.cinder,
        "get_volume_quota",
        lambda *args, **kwargs: {name: {"in_use": 0, "limit": 100} for name in ("volumes", "gigabytes")},
    )


def test_foreign_native_rows_are_not_mailed_or_misread_as_healthy(monkeypatch):
    quotas(monkeypatch)
    server = {"id": "foreign", "project_id": "other", "status": "ERROR"}
    observed, known = signals._observe_project(connection(servers=[server]), "project", CLOCK)
    assert not any(key.startswith(("instance_error:", "usage:")) for key in observed)
    assert "instance_error:" not in known and "usage:" not in known
    assert known == {"quota_compute:", "quota_storage:"}


def test_native_project_proof_mismatch_precedes_any_resource_read(monkeypatch):
    quotas(monkeypatch)
    with pytest.raises(RuntimeError):
        signals._observe_project(connection(native_project="other"), "project", CLOCK)


def test_native_error_and_malformed_schedule_generate_only_safe_current_signals(monkeypatch):
    quotas(monkeypatch)
    server = {"id": "vm", "project_id": "project", "status": "ERROR", "metadata": {"secret": "never-mail-me"}}
    monkeypatch.setattr(
        signals.instance_usage,
        "parse_schedule",
        lambda server: (_ for _ in ()).throw(HTTPException(502, "secret native body")),
    )
    observed, known = signals._observe_project(connection(servers=[server]), "project", CLOCK)
    assert {"instance_error:current", "usage:vm:invalid"} <= observed.keys()
    assert {"instance_error:", "usage:"} <= known
    assert "never-mail-me" not in repr(observed) and "secret native body" not in repr(observed)


@pytest.mark.asyncio
async def test_current_scan_rotates_projects_and_rechecks_membership_before_enqueue(episodes, monkeypatch):
    from app.services import mail_delivery, mail_settings

    monkeypatch.setattr(signals, "get_session_factory", lambda: episodes)
    config = SimpleNamespace(
        smtp=SimpleNamespace(enabled=True), notifications=SimpleNamespace(resource_alerts_enabled=True)
    )

    async def settings():
        return config

    async def subscribers(*, offset, limit):
        return [{"user_id": "human", "identity_domain_id": "home"}] if offset == 0 else []

    async def projects(user_id, home):
        return ["project1", "project2", "project3"]

    checks = []
    revoked = False

    async def member(user_id, project_id):
        checks.append(project_id)
        # Membership changes while resource reads are in progress.
        if revoked and checks.count(project_id) % 2 == 0:
            raise HTTPException(403, "revoked")

    @asynccontextmanager
    async def scoped(factory, project_id):
        yield object()

    def observe(conn, project_id, clock):
        return {"instance_error:current": signals.Signal("Error", "Safe error")}, {"instance_error:"}

    queued = {}

    async def enqueue(**kwargs):
        assert kwargs["expected_identity_domain_id"] == "home"
        queued[kwargs["event_key"]] = kwargs["project_id"]
        return {"status": "queued"}

    monkeypatch.setattr(mail_settings, "effective_settings", settings)
    monkeypatch.setattr(mail_delivery, "list_notification_subscribers", subscribers)
    monkeypatch.setattr(mail_delivery, "enqueue_notification", enqueue)
    monkeypatch.setattr(signals, "_projects", projects)
    monkeypatch.setattr(signals, "_member", member)
    monkeypatch.setattr(signals, "_connection", scoped)
    monkeypatch.setattr(signals, "_observe_project", observe)
    await signals.scan_notifications(now=CLOCK)
    assert set(queued.values()) == {"project1", "project2"}
    await signals.scan_notifications(now=CLOCK + timedelta(seconds=61))
    assert set(queued.values()) == {"project1", "project2", "project3"}
    assert len(queued) == 3
    # Healthy clearing then a new recurrence is still fenced by current rights.
    revoked = True
    checks.clear()
    monkeypatch.setattr(
        signals,
        "_observe_project",
        lambda *args: ({"usage:vm:new:oneDay": signals.Signal("Due", "Safe due")}, {"usage:"}),
    )
    await signals.scan_notifications(now=CLOCK + timedelta(seconds=122))
    assert len(queued) == 3
    config.notifications.resource_alerts_enabled = False
    checks.clear()
    await signals.scan_notifications(now=CLOCK + timedelta(seconds=183))
    assert checks == []
