"""Native Redis/Lua acceptance; selected by the parent's disposable functional runner.

These tests deliberately do not emulate Lua or HLL in Python. Set
AFTERGLOW_TEST_REAL_REDIS=1 only against the isolated test Redis profile.
"""

import asyncio
import os
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from redis.asyncio import ConnectionPool, Redis

from app.models.traffic_analytics import TrafficAnalyticsSettings, TrafficEvent
from app.services import traffic_analytics as service
from app.services.cache import _get_redis

pytestmark = [
    pytest.mark.db,
    pytest.mark.redis,
    pytest.mark.skipif(
        os.environ.get("AFTERGLOW_TEST_REAL_REDIS") != "1",
        reason="requires disposable real Redis functional profile",
    ),
]


@pytest.fixture
async def analytics(monkeypatch, tmp_path):
    geo = tmp_path / "geo.csv"
    geo.write_text("cidr,country\n8.8.8.0/24,KR\n9.9.9.0/24,US\n")
    settings = SimpleNamespace(
        traffic_analytics=TrafficAnalyticsSettings(
            enabled=True,
            hmac_key="identity-" + "h" * 32,
            frontend_ingest_key="frontend-" + "f" * 32,
            geoip_csv=str(geo),
        )
    )
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    prefix = f"afterglow:{{traffic-test-{uuid4()}}}"
    monkeypatch.setattr(service, "KEY_PREFIX", prefix)
    redis = await _get_redis()
    monkeypatch.setattr(service, "_get_redis", lambda: _get_redis())
    service._pending_drops.clear()
    yield redis, settings
    keys = [key async for key in redis.scan_iter(match=prefix + ":*")]
    if keys:
        await redis.delete(*keys)
    service._pending_drops.clear()


def observation(**changes):
    values = dict(
        id=uuid4(),
        at=time.time(),
        status=200,
        route="/dashboard/instances/{id}",
        client_ip="8.8.8.8",
        pageview=True,
        request_bytes=None,
        response_bytes=42,
        latency_ms=12,
    )
    values.update(changes)
    return TrafficEvent(**values)


async def test_atomic_concurrent_count_dedupe_country_hll_and_privacy(analytics):
    redis, settings = analytics
    same = observation()
    assert all(await asyncio.gather(*(service.record_event(same, "frontend") for _ in range(32))))
    assert await service.record_event(same.model_copy(update={"at": same.at - 60}), "frontend")
    other = observation(status=503, client_ip="9.9.9.9", response_bytes=18, latency_ms=35)
    assert await service.record_event(other, "frontend")
    assert await service.record_event(observation(client_ip=None, response_bytes=None), "frontend")
    data = await service.snapshot("frontend", "24h")
    assert data["state"] == "available"
    totals = data["totals"]
    assert totals["requests"] == 3 and totals["success"] == 2 and totals["errors"] == 1
    assert totals["status_2xx"] == 2 and totals["status_5xx"] == 1
    assert totals["pageviews"] == 3 and totals["unique_visitors"] == 2
    assert totals["request_bytes"] is None and totals["request_bytes_known"] == 0
    assert totals["response_bytes"] == 60 and totals["response_bytes_known"] == 2
    assert totals["latency_ms_total"] == 59 and totals["latency_ms_max"] == 35
    assert totals["unlocated"] == 1
    assert {row["country"] for row in data["countries"]} == {"KR", "US", "XX"}
    assert data["routes"][0]["route"] == "/dashboard"
    assert sum(point["metrics"]["requests"] for point in data["series"] if point["metrics"]) == 3
    assert len(data["series"]) == 24 and sum(point["metrics"] is None for point in data["series"]) == 23
    assert data["coverage"]["last_observed_at"] >= same.at
    assert (await service.snapshot("backend", "24h"))["totals"] is None
    keys = [key async for key in redis.scan_iter(match=service.KEY_PREFIX + ":*")]
    # DUMP is binary. The installed hiredis reader decodes before Redis's
    # per-command NEVER_DECODE flag, so use a separate binary pool; otherwise a
    # decode error also poisons the shared connection's next pipeline response.
    pool = ConnectionPool(**{**redis.connection_pool.connection_kwargs, "decode_responses": False})
    try:
        async with Redis(connection_pool=pool) as binary:
            for key in keys:
                ttl = await redis.ttl(key)
                assert 0 < ttl <= settings.traffic_analytics.retention_days * 86400
                stored = await binary.dump(key)
                assert b"8.8.8.8" not in stored and b"9.9.9.9" not in stored
                assert b"instances" not in stored and b"identity-" not in stored
    finally:
        await pool.disconnect()


async def test_hourly_ranges_distinguish_empty_from_measured_zero(analytics):
    redis, settings = analytics
    # Service can backfill trusted local measurements; network ingest separately
    # enforces +/-120 seconds. No untrusted API accepts historical timestamps.
    for days in (0, 2, 10, 31):
        await service.record_event(observation(at=time.time() - days * 86400, status=201), "backend")
    daily = await service.snapshot("backend", "24h")
    weekly = await service.snapshot("backend", "7d")
    monthly = await service.snapshot("backend", "30d")
    assert daily["totals"]["requests"] == 1
    assert weekly["totals"]["requests"] == 2
    assert monthly["totals"]["requests"] == 3
    assert daily["totals"]["errors"] == 0  # Genuine observed absence of errors.
    assert daily["totals"]["pageviews"] == 0  # Backend never counts frontend pageviews.
    assert (await service.snapshot("frontend", "24h"))["state"] == "partial"
    assert (await service.snapshot("frontend", "24h"))["totals"] is None
    settings.traffic_analytics.retention_days = 1
    assert len((await service.snapshot("backend", "30d"))["series"]) == 24


async def test_bounded_minute_capacity_rejects_without_partial_aggregation(analytics):
    redis, _ = analytics
    value = observation()
    dedupe = f"{service.KEY_PREFIX}:frontend:dedupe:{int(value.at) // 60}"
    await redis.hset(dedupe, mapping={str(uuid4()): "1" for _ in range(10000)})
    await redis.expire(dedupe, 300)
    assert await service.record_event(value, "frontend") is False
    counts, visitors = service.bucket_keys("frontend", int(value.at) // 3600)
    assert not await redis.exists(counts)
    assert not await redis.exists(visitors)
    assert service._pending_drops["frontend"] == 1
    await redis.delete(dedupe)
    assert await service.record_event(value, "frontend")
    data = await service.snapshot("frontend", "24h")
    assert data["state"] == "partial"
    assert data["totals"]["requests"] == 1
    assert data["coverage"]["dropped_events"] == 1


async def test_no_high_cardinality_paths_or_country_spoofing(analytics):
    redis, _ = analytics
    for index in range(25):
        await service.record_event(
            observation(route=f"/secret/{index}?token=DO-NOT-STORE", client_ip="192.0.2.1"), "frontend"
        )
    data = await service.snapshot("frontend", "24h")
    assert [row["route"] for row in data["routes"]] == ["/other"]
    assert [row["country"] for row in data["countries"]] == ["XX"]
    counts, _ = service.bucket_keys("frontend", int(time.time()) // 3600)
    raw = repr(await redis.hgetall(counts))
    assert "DO-NOT-STORE" not in raw and "secret" not in raw and "192.0.2.1" not in raw
    assert await redis.hlen(counts) <= 3 * (len(service.COUNTERS) + 1)
