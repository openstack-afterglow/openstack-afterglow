"""Consumer-visible HTTP regressions using actual ActivityLog SQL and Redis session logic.

Identity and Redis transport are isolated fixtures, not production qualification.
"""

import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from openstack.exceptions import ForbiddenException
from sqlalchemy import Integer, MetaData
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_os_conn, get_token_info, require_admin
from app.api.identity.login_monitoring import router
from app.models.activity import ActivityLog
from app.services import login_monitoring as service
from app.services import session_store
from tests.admin_gate import synthetic_verified_admin

BASE = "/api/v1/admin/monitoring/logins"


@pytest.fixture
async def monitoring(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    table = ActivityLog.__table__.to_metadata(MetaData())
    table.c.id.type = Integer()
    async with engine.begin() as connection:
        await connection.run_sync(table.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(service, "get_session_factory", lambda: factory)
    monkeypatch.setattr(service, "is_db_available", lambda: True)
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(session_timeout_seconds=3600))
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def get_redis():
        return redis

    monkeypatch.setattr(service, "_get_redis", get_redis)
    monkeypatch.setattr(session_store, "_get_redis", get_redis)
    conn = MagicMock()
    conn.identity.get_user.side_effect = lambda user_id: SimpleNamespace(id=user_id, name="Selected user")
    conn.identity.users.side_effect = lambda **kwargs: iter([SimpleNamespace(id="selected", name="Selected user")])
    authority = {"is_system_admin": True}
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/admin/monitoring/logins")
    app.dependency_overrides[get_token_info] = lambda: authority
    app.dependency_overrides[require_admin] = synthetic_verified_admin
    app.dependency_overrides[get_os_conn] = lambda: conn
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(client=client, redis=redis, factory=factory, conn=conn, authority=authority)
    await redis.close()
    await engine.dispose()


async def add_event(
    factory,
    *,
    at=None,
    user="selected",
    action="login",
    resource="auth",
    status="success",
    project="project-a",
    extra=None,
    source="afterglow",
):
    async with factory() as session:
        session.add(
            ActivityLog(
                created_at=at or datetime.now(UTC),
                user_id=user,
                username="User",
                project_id=project,
                resource_type=resource,
                action=action,
                status=status,
                source=source,
                service="keystone",
                extra=extra,
                error_message="password=do-not-expose",
                request_id="private-request",
            )
        )
        await session.commit()


async def put_session(redis, jti, **changes):
    now = int(time.time())
    record = {
        "user_id": "selected",
        "started_at": now - 100,
        "last_seen": now - 20,
        "exp": now + 10000,
        "project_id": "project-a",
        "auth_method": "password",
        "device_type": "desktop",
        "os": "Linux",
        "blacklisted": False,
        "keystone_token": "private-token",
        "origin_fp": "private-fingerprint",
        "last_fp": "private-fingerprint",
        "last_ip": "192.0.2.1",
        "future_secret": "private-secret",
    }
    record.update(changes)
    await redis.setex(session_store._key(jti), 600, json.dumps(record))
    await redis.sadd(session_store._user_index_key("selected"), jti)


@pytest.mark.asyncio
async def test_selected_user_actual_activity_and_session_allowlist(monitoring):
    m = monitoring
    await add_event(m.factory)
    await add_event(m.factory, extra={"method": "federated", "token": "secret-extra"}, project="project-b")
    await add_event(m.factory, user="other")
    await add_event(m.factory, action="create", resource="instance")
    await put_session(m.redis, "private-jti")
    response = await m.client.get(BASE + "/users/selected")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["history"]["login_successes"] == 2
    assert data["history"]["recorded_login_failures"] == 0
    assert data["history"]["failure_history"] == "not_collected"
    assert sum(bucket["successes"] for bucket in data["history"]["timeline"]) == 2
    assert sum(bucket["successes"] for bucket in data["history"]["hour_distribution"]) == 2
    assert {e["auth_method"] for e in data["history"]["events"] if e["action"] == "login"} == {"password", "federated"}
    assert len(data["history"]["events"]) == 3
    sessions = data["sessions"]
    assert sessions["valid_count"] == 1
    assert sessions["observed_recent_count"] == 1
    session = sessions["items"][0]
    assert set(session) == {
        "started_at",
        "last_seen",
        "expires_at",
        "refresh_expires_at",
        "project_id",
        "device_type",
        "os",
        "auth_method",
        "observed_recently",
    }
    assert datetime.fromisoformat(session["expires_at"]) == datetime.fromisoformat(session["started_at"]) + timedelta(
        seconds=3600
    )
    for secret in (
        "private-jti",
        "private-token",
        "private-fingerprint",
        "192.0.2.1",
        "future_secret",
        "secret-extra",
        "do-not-expose",
        "private-request",
    ):
        assert secret not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"exp": 1},
        {"blacklisted": True},
        {"started_at": 1},
    ],
)
async def test_expired_blacklisted_and_absolute_timeout_are_not_valid(monitoring, change):
    await put_session(monitoring.redis, "excluded", **change)
    data = (await monitoring.client.get(BASE + "/users/selected")).json()
    assert data["sessions"]["state"] == "ready"
    assert data["sessions"]["valid_count"] == 0
    assert data["sessions"]["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"started_at": None}, {"exp": None}, {"user_id": "foreign"}, {"blacklisted": None}])
async def test_unknown_inventory_is_not_verified_zero(monitoring, change):
    await put_session(monitoring.redis, "invalid", **change)
    data = (await monitoring.client.get(BASE + "/users/selected")).json()
    assert data["sessions"] == {"state": "partial", "items": [], "valid_count": None, "observed_recent_count": None}


@pytest.mark.asyncio
async def test_missing_inventory_and_stale_members_are_explicit(monitoring):
    response = await monitoring.client.get(BASE + "/users/selected")
    assert response.json()["sessions"]["state"] == "unknown"
    assert response.json()["sessions"]["valid_count"] is None
    await monitoring.redis.sadd(session_store._user_index_key("selected"), "missing-record")
    response = await monitoring.client.get(BASE + "/users/selected")
    assert response.json()["sessions"]["state"] == "partial"
    assert response.json()["sessions"]["valid_count"] is None


@pytest.mark.asyncio
async def test_invalid_last_seen_never_means_online_or_recent(monitoring):
    await put_session(monitoring.redis, "legacy", last_seen=None)
    data = (await monitoring.client.get(BASE + "/users/selected")).json()
    assert data["sessions"]["valid_count"] == 1
    assert data["sessions"]["observed_recent_count"] == 0
    assert data["sessions"]["items"][0]["last_seen"] is None
    assert "online" not in data["sessions"]["items"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("window,hours", [("24h", 24), ("7d", 168), ("30d", 720)])
async def test_window_and_hour_buckets_use_stored_timestamps(monitoring, window, hours):
    now = datetime(2026, 10, 14, 12, 30, tzinfo=UTC)
    await add_event(monitoring.factory, at=now - timedelta(hours=hours) + timedelta(seconds=1))
    await add_event(monitoring.factory, at=now - timedelta(hours=hours) - timedelta(seconds=1))
    await add_event(monitoring.factory, at=now + timedelta(seconds=1))
    await add_event(monitoring.factory, at=now - timedelta(minutes=5), status="failed")
    data = await service._history("selected", now, window)
    assert data["login_successes"] == 1
    assert data["recorded_login_failures"] == 1
    assert data["failure_history"] == "not_collected"
    assert len(data["timeline"]) == hours + 1
    assert data["timeline"][0]["successes"] == 1
    assert data["hour_distribution"][12]["recorded_failures"] == 1


@pytest.mark.asyncio
async def test_query_cap_is_visible_not_full_total(monitoring, monkeypatch):
    monkeypatch.setattr(service, "EVENT_LIMIT", 2)
    for _ in range(3):
        await add_event(monitoring.factory)
    data = (await monitoring.client.get(BASE + "/users/selected")).json()
    assert data["history"]["state"] == "partial"
    assert data["history"]["login_successes"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unconfigured", "breaker", "query", "redis"])
async def test_independent_source_outages_never_return_healthy_zero(monitoring, monkeypatch, failure):
    await put_session(monitoring.redis, "valid")
    await add_event(monitoring.factory)
    if failure == "unconfigured":
        monkeypatch.setattr(service, "get_session_factory", lambda: None)
    elif failure == "breaker":
        monkeypatch.setattr(service, "is_db_available", lambda: False)
    elif failure == "query":

        def broken():
            raise RuntimeError("sql-private-error")

        monkeypatch.setattr(service, "get_session_factory", lambda: broken)
    else:

        async def broken():
            raise ConnectionError("redis-private-error")

        monkeypatch.setattr(service, "_get_redis", broken)
    response = await monitoring.client.get(BASE + "/users/selected")
    assert response.status_code == 200
    data = response.json()
    if failure == "redis":
        assert data["sessions"]["state"] == "unavailable"
        assert data["sessions"]["valid_count"] is None
        assert data["history"]["login_successes"] == 1
    else:
        assert data["history"]["state"] == "unavailable"
        assert data["history"]["login_successes"] is None
        assert data["history"]["events"] is None
        assert data["sessions"]["valid_count"] == 1
    assert "private-error" not in response.text


@pytest.mark.asyncio
async def test_current_admin_required_on_both_endpoints(monitoring):
    monitoring.authority["is_system_admin"] = False
    for path in ("/users", "/users/selected"):
        assert (await monitoring.client.get(BASE + path)).status_code == 403
    monitoring.conn.identity.get_user.assert_not_called()
    monitoring.conn.identity.users.assert_not_called()


@pytest.mark.asyncio
async def test_nonexistent_native_denial_and_provider_failure(monitoring):
    monitoring.conn.identity.get_user.return_value = None
    monitoring.conn.identity.get_user.side_effect = None
    missing = await monitoring.client.get(BASE + "/users/missing")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "login_monitoring_user_not_found"
    monitoring.conn.identity.get_user.side_effect = ForbiddenException("private-native-detail")
    denied = await monitoring.client.get(BASE + "/users/selected")
    assert denied.status_code == 403
    assert denied.json()["detail"] == "login_monitoring_native_denied"
    monitoring.conn.identity.get_user.side_effect = RuntimeError("private-provider-detail")
    unavailable = await monitoring.client.get(BASE + "/users/selected")
    assert unavailable.status_code == 503
    assert "private" not in unavailable.text


@pytest.mark.asyncio
async def test_directory_native_pagination_and_explicit_failures(monitoring):
    monitoring.conn.identity.users.side_effect = lambda **kwargs: iter(
        [SimpleNamespace(id="a", name="A"), SimpleNamespace(id="b", name="B")]
    )
    response = await monitoring.client.get(BASE + "/users?limit=1&marker=before")
    assert response.json() == {"items": [{"id": "a", "name": "A"}], "next_marker": "a"}
    monitoring.conn.identity.users.assert_called_with(limit=1, marker="before")
    monitoring.conn.identity.users.side_effect = ForbiddenException("private")
    assert (await monitoring.client.get(BASE + "/users")).json()["detail"] == "login_monitoring_native_denied"
    monitoring.conn.identity.users.side_effect = RuntimeError("private")
    assert (await monitoring.client.get(BASE + "/users")).status_code == 503
    assert (await monitoring.client.get(BASE + "/users/selected?window=all")).status_code == 422


@pytest.mark.asyncio
async def test_real_session_creation_and_revocation_remove_monitorable_session(monitoring):
    await session_store.store_session(
        "revoked-jti", "private-native-token", "project-a", "selected", int(time.time()) + 600
    )
    before = await monitoring.client.get(BASE + "/users/selected")
    assert before.json()["sessions"]["valid_count"] == 1
    await session_store.delete_session("revoked-jti")
    after = await monitoring.client.get(BASE + "/users/selected")
    assert after.json()["sessions"]["items"] is None
    assert after.json()["sessions"]["state"] == "unknown"
    assert "revoked-jti" not in before.text + after.text


@pytest.mark.asyncio
async def test_domain_observation_counts_only_directory_scope(monitoring):
    m = monitoring
    await add_event(m.factory)
    await add_event(m.factory, status="failed")
    await add_event(m.factory, project="", action="logout")  # domain-only auth event
    await add_event(m.factory, project="project-x")  # same user, foreign project
    await add_event(m.factory, user="outsider", project="project-x")
    await add_event(m.factory, user="outsider", project="")
    await put_session(m.redis, "valid", domain_id="tenant-a")
    await put_session(m.redis, "foreign-project", domain_id="tenant-a", project_id="project-x")
    await put_session(m.redis, "foreign-domain", domain_id="tenant-b")
    await put_session(m.redis, "outsider", user_id="outsider", domain_id="tenant-a")
    # "idle" has no session index at all; that is a verified zero, not unknown.
    data = await service.domain_observation("tenant-a", {"selected", "idle"}, {"project-a"}, "24h")
    assert data["logins"]["successes"] == 1 and data["logins"]["recorded_failures"] == 1
    assert data["logins"]["failure_history"] == "not_collected"
    assert data["activity"]["events"] == 3 and data["activity"]["recent_users"] == 1
    assert data["sessions"] == {
        "state": "ready",
        "valid_count": 1,
        "observed_recent_count": 1,
        "unattributed_count": 0,
        "online_count": None,
    }
    assert "private" not in json.dumps(data) and "192.0.2.1" not in json.dumps(data)


@pytest.mark.asyncio
async def test_domain_observation_legacy_sessions_and_storage_outage_are_explicit(monitoring, monkeypatch):
    await put_session(monitoring.redis, "legacy")  # no stored domain
    await put_session(monitoring.redis, "attributed", domain_id="tenant-a")
    await put_session(monitoring.redis, "malformed", exp=None, domain_id="tenant-a")
    monkeypatch.setattr(service, "is_db_available", lambda: False)
    data = await service.domain_observation("tenant-a", {"selected"}, {"project-a"}, "24h")
    assert data["sessions"]["state"] == "partial"
    assert data["sessions"]["valid_count"] == 1 and data["sessions"]["unattributed_count"] == 1
    assert "sessions_without_domain_attribution" in data["notes"]
    assert data["logins"]["state"] == "unavailable" and data["logins"]["successes"] is None
    assert data["activity"]["events"] is None and data["activity"]["hour_distribution"] is None
