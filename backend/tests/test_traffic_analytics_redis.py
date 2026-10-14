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
    # Unit-level geographic seam; production qualification must use the complete
    # mounted DB-IP MMDB, not this deterministic reader.
    rows = {"8.8.8.8": "KR", "9.9.9.9": "US"}
    monkeypatch.setattr(
        service,
        "country_lookup",
        lambda filename: SimpleNamespace(
            state="offline_mmdb",
            provider="DB-IP",
            version="2026-10-01",
            attribution="DB-IP CC BY 4.0",
            lookup=lambda address: (
                (rows[address], "located")
                if address in rows
                else ("XX", "address_unavailable" if address is None else "non_global")
            ),
        ),
    )
    settings = SimpleNamespace(
        traffic_analytics=TrafficAnalyticsSettings(
            enabled=True,
            hmac_key="identity-" + "h" * 32,
            frontend_ingest_key="frontend-" + "f" * 32,
            cluster_cidrs=["172.30.0.0/16"],
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
        peer_ip="8.8.8.8",
        peer_verified=True,
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
    other = observation(status=503, peer_ip="9.9.9.9", response_bytes=18, latency_ms=35)
    assert await service.record_event(other, "frontend")
    assert await service.record_event(observation(peer_ip=None, response_bytes=None), "frontend")
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
    external = await service.snapshot("frontend", "24h", "external")
    internal = await service.snapshot("frontend", "24h", "internal")
    assert external["coverage"]["dropped_events"] == internal["coverage"]["dropped_events"] == 1
    assert internal["totals"] is None and internal["origins"] is None


async def test_no_high_cardinality_paths_or_country_spoofing(analytics):
    redis, _ = analytics
    for index in range(25):
        await service.record_event(
            observation(route=f"/secret/{index}?token=DO-NOT-STORE", peer_ip="192.0.2.1"), "frontend"
        )
    data = await service.snapshot("frontend", "24h")
    assert [row["route"] for row in data["routes"]] == ["/other"]
    assert [row["country"] for row in data["countries"]] == ["XX"]
    counts, _ = service.bucket_keys("frontend", int(time.time()) // 3600)
    raw = repr(await redis.hgetall(counts))
    assert "DO-NOT-STORE" not in raw and "secret" not in raw and "192.0.2.1" not in raw
    assert await redis.hlen(counts) <= 6 * (len(service.COUNTERS) + 3)


async def test_origin_filter_is_atomic_across_totals_routes_countries_series_hll_and_dedupe(analytics):
    redis, _ = analytics
    for peer in ("172.30.1.4", "8.8.8.8", "9.9.9.9", "192.168.9.1", None):
        value = observation(peer_ip=peer)
        assert await service.record_event(value, "frontend")
        assert await service.record_event(value, "frontend")
    all_data = await service.snapshot("frontend", "24h")
    assert all_data["totals"]["requests"] == 5
    assert all_data["origins"] == {"internal": 1, "external": 2, "unknown": 2, "legacy_unclassified": 0}
    for selected, total, unique in (("internal", 1, 1), ("external", 2, 2), ("unknown", 2, 1)):
        data = await service.snapshot("frontend", "24h", selected)
        assert data["totals"]["requests"] == total and data["totals"]["unique_visitors"] == unique
        assert sum(row["requests"] for row in data["countries"]) == total
        assert sum(row["requests"] for row in data["routes"]) == total
        assert sum(point["metrics"]["requests"] for point in data["series"] if point["metrics"]) == total
        assert sum(data["origins"].values()) == total
        assert data["routes"][0]["origins"][selected] == total
    assert all_data["coverage"]["origin_unknown_reasons"] == {"address_unavailable": 1, "non_global_noncluster": 1}
    assert all_data["coverage"]["geo_unknown_reasons"] == {"address_unavailable": 1, "non_global": 2}


async def test_existing_v1_buckets_and_old_reporters_remain_legacy_without_reset(analytics):
    from app.models.traffic_analytics import LegacyTrafficEvent

    redis, _ = analytics
    hour = int(time.time()) // 3600
    old_counts, old_visitors = service.bucket_keys("frontend", hour, 1)
    old = {key: 0 for key in service.COUNTERS}
    old.update(requests=2, success=2, status_2xx=2, unlocated=1, identity_known=1)
    await redis.hset(
        old_counts,
        mapping={
            dimension + "|" + key: value for dimension in ("t", "c:XX", "r:/dashboard") for key, value in old.items()
        },
    )
    await redis.expire(old_counts, 3600)
    await redis.pfadd(old_visitors, "old-opaque-digest")
    await redis.expire(old_visitors, 3600)
    old_report = LegacyTrafficEvent(
        id=uuid4(), at=time.time(), status=200, route="/dashboard", client_ip="8.8.8.8", latency_ms=2
    )
    assert await service.record_event(old_report, "frontend")
    modern = observation()
    assert await service.record_event(modern, "frontend")
    # Shared dedupe boundary suppresses a retry first accepted by an old backend.
    shared = observation()
    dedupe = f"{service.KEY_PREFIX}:frontend:dedupe:{int(time.time()) // 60}"
    await redis.hset(dedupe, str(shared.id), "1")
    assert await service.record_event(shared, "frontend")
    all_data = await service.snapshot("frontend", "24h")
    legacy = await service.snapshot("frontend", "24h", "legacy_unclassified")
    external = await service.snapshot("frontend", "24h", "external")
    assert all_data["totals"]["requests"] == 4
    assert all_data["totals"]["unique_visitors"] == 2
    assert legacy["totals"]["requests"] == 3 and legacy["totals"]["unique_visitors"] == 1
    assert legacy["coverage"]["legacy_unclassified_requests"] == 3
    assert legacy["coverage"]["origin_unknown_reasons"] == {"legacy_unclassified": 3}
    assert external["totals"]["requests"] == 1 and external["coverage"]["legacy_unclassified_requests"] == 0
    assert int(await redis.hget(old_counts, "t|requests")) == 2
