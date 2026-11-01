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
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import ConnectionPool, Redis

from app.api.common import traffic_analytics as api
from app.api.deps import get_token_info, require_admin
from app.models.traffic_analytics import TrafficAnalyticsSettings, TrafficEvent
from app.services import traffic_analytics as service
from app.services.cache import _get_redis
from tests.admin_gate import synthetic_verified_admin

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
    assert data["networks"] == []
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
        await service.record_event(
            observation(at=time.time() - days * 86400, status=201, peer_ip="10.8.4.5"), "backend"
        )
    daily = await service.snapshot("backend", "24h")
    weekly = await service.snapshot("backend", "7d")
    monthly = await service.snapshot("backend", "30d")
    assert daily["totals"]["requests"] == 1
    assert weekly["totals"]["requests"] == 2
    assert monthly["totals"]["requests"] == 3
    for data, expected in ((daily, 1), (weekly, 2), (monthly, 3)):
        assert len(data["networks"]) == 1
        assert data["networks"][0]["network"] == "10.8.0.0/16"
        assert data["networks"][0]["requests"] == expected
        assert data["networks"][0]["unique_visitors"] is None
    assert daily["totals"]["errors"] == 0  # Genuine observed absence of errors.
    assert daily["totals"]["pageviews"] == 0  # Backend never counts frontend pageviews.
    assert (await service.snapshot("frontend", "24h"))["state"] == "partial"
    assert (await service.snapshot("frontend", "24h"))["totals"] is None
    settings.traffic_analytics.retention_days = 1
    assert (await service.snapshot("backend", "30d"))["networks"][0]["requests"] == 1
    assert len((await service.snapshot("backend", "30d"))["series"]) == 24


async def test_bounded_minute_capacity_rejects_without_partial_aggregation(analytics):
    redis, _ = analytics
    value = observation(peer_ip="10.8.4.5")
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
    assert data["networks"][0]["requests"] == 1
    assert data["networks"][0]["network"] == "10.8.0.0/16"
    assert data["coverage"]["dropped_events"] == 1
    external = await service.snapshot("frontend", "24h", "external")
    internal = await service.snapshot("frontend", "24h", "internal")
    assert external["coverage"]["dropped_events"] == internal["coverage"]["dropped_events"] == 1
    assert internal["totals"] is None and internal["origins"] is None


async def test_no_high_cardinality_paths_or_country_spoofing(analytics):
    redis, _ = analytics
    counts, _ = service.bucket_keys("frontend", int(time.time()) // 3600)
    initial_fields = None
    for index in range(1, 65):
        assert await service.record_event(
            observation(route=f"/secret/{index}?token=DO-NOT-STORE", peer_ip=f"192.0.2.{index}"), "frontend"
        )
        if initial_fields is None:
            initial_fields = set(await redis.hkeys(counts))
        else:
            # New paths and hosts inside the same standard range add no fields.
            assert set(await redis.hkeys(counts)) == initial_fields
    data = await service.snapshot("frontend", "24h")
    assert [row["route"] for row in data["routes"]] == ["/other"]
    assert [row["country"] for row in data["countries"]] == ["XX"]
    assert [(row["network"], row["requests"]) for row in data["networks"]] == [("192.0.2.0/24", 64)]
    raw = repr(await redis.hgetall(counts))
    assert "DO-NOT-STORE" not in raw and "secret" not in raw
    assert all(f"192.0.2.{index}" not in raw for index in range(1, 65))
    assert {key.rsplit("|", 1)[0] for key in initial_fields} == {
        "t",
        "c:XX",
        "r:/other",
        "o:unknown:t",
        "o:unknown:c:XX",
        "o:unknown:r:/other",
        "n:resolved_client:documentation:192.0.2.0/24",
        "o:unknown:n:resolved_client:documentation:192.0.2.0/24",
    }


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
        expected_network = {"internal": "172.30.0.0/16", "unknown": "192.168.0.0/16"}.get(selected)
        assert [row["network"] for row in data["networks"]] == ([expected_network] if expected_network else [])
        assert all(row["requests"] == 1 and row["unique_visitors"] is None for row in data["networks"])
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
        id=uuid4(), at=time.time(), status=200, route="/dashboard", client_ip="172.30.4.5", latency_ms=2
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
    assert all_data["networks"] == legacy["networks"] == external["networks"] == []


async def test_networks_atomic_metrics_origin_source_dedupe_and_http(analytics):
    redis, settings = analytics
    settings.traffic_analytics.frontend_trusted_proxy_cidrs = ["172.30.0.11/32"]
    values = [
        observation(peer_ip="172.30.5.7"),
        observation(peer_ip="172.31.5.7", status=503, request_bytes=7, latency_ms=35),
        observation(peer_ip="10.8.5.7", forwarded_for="172.30.5.7"),
        observation(peer_ip="::ffff:10.8.6.8"),
        observation(peer_ip="fd12:3456:789a::12"),
        observation(peer_ip="fd98:7654:3210::34"),
        observation(peer_ip="172.30.0.11", forwarded_for="bad, 10.8.9.9"),
        observation(peer_ip="172.30.0.11", forwarded_for=None),
        observation(peer_ip="172.30.0.11", forwarded_for="172.30.0.11"),
        observation(peer_ip="172.31.9.9", peer_verified=False, forwarded_for="10.8.9.9"),
        observation(peer_ip="1.1.1.1", forwarded_for="10.8.9.9"),
        observation(peer_ip="239.1.2.3"),
    ]
    for value in values:
        assert all(await asyncio.gather(*(service.record_event(value, "frontend") for _ in range(3))))
    # The same UUID is independently accepted in the other source.
    assert await service.record_event(values[0], "backend")
    all_data = await service.snapshot("frontend", "24h")
    rows = {(row["network"], row["basis"]): row for row in all_data["networks"]}
    assert [(row["network"], row["basis"]) for row in all_data["networks"]] == [
        ("172.30.0.0/16", "socket_peer"),
        ("10.8.0.0/16", "resolved_client"),
        ("fc00::/7", "resolved_client"),
        ("172.30.0.0/16", "resolved_client"),
        ("172.31.0.0/16", "resolved_client"),
        ("224.0.0.0/4", "resolved_client"),
    ]
    assert rows[("172.30.0.0/16", "socket_peer")]["requests"] == 3
    assert rows[("10.8.0.0/16", "resolved_client")]["requests"] == 2
    assert rows[("fc00::/7", "resolved_client")]["requests"] == 2
    failed = rows[("172.31.0.0/16", "resolved_client")]
    assert failed["errors"] == failed["status_5xx"] == 1 and failed["success"] == 0
    assert failed["request_bytes"] == 7 and failed["request_bytes_known"] == 1
    assert failed["response_bytes"] == 42 and failed["response_bytes_known"] == 1
    assert failed["latency_ms_max"] == failed["latency_ms_total"] == 35
    assert all(row["unique_visitors"] is None and row["unlocated"] == row["requests"] for row in rows.values())
    assert all_data["totals"]["requests"] == 12
    assert all_data["origins"] == {"internal": 1, "external": 1, "unknown": 10, "legacy_unclassified": 0}
    xx = next(row for row in all_data["countries"] if row["country"] == "XX")
    assert sum(row["requests"] for row in rows.values()) == 10 < xx["requests"] == 12
    assert (await service.snapshot("backend", "24h"))["networks"][0]["requests"] == 1
    internal = await service.snapshot("frontend", "24h", "internal")
    unknown = await service.snapshot("frontend", "24h", "unknown")
    external = await service.snapshot("frontend", "24h", "external")
    assert [(row["network"], row["basis"]) for row in internal["networks"]] == [("172.30.0.0/16", "resolved_client")]
    assert rows[("172.30.0.0/16", "socket_peer")] in unknown["networks"]
    assert external["networks"] == []
    app = FastAPI()
    app.include_router(api.admin_router, prefix="/traffic")
    app.dependency_overrides[get_token_info] = lambda: {"is_system_admin": True}
    app.dependency_overrides[require_admin] = synthetic_verified_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/traffic?source=frontend&range=24h&origin=unknown")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["networks"] == unknown["networks"]
    counts, visitors = service.bucket_keys("frontend", int(time.time()) // 3600)
    raw = repr(await redis.hgetall(counts))
    assert all(value.peer_ip not in raw for value in values)
    assert "bad, 10.8.9.9" not in raw
    keys = [key async for key in redis.scan_iter(match=service.KEY_PREFIX + ":*")]
    assert not any(":n:" in key for key in keys)  # No per-network HLL or host keys.
    assert 0 < await redis.ttl(counts) <= settings.traffic_analytics.retention_days * 86400
    assert await redis.exists(visitors)


async def test_old_v2_unlocated_history_is_not_reconstructed_from_new_ranges(analytics):
    redis, _ = analytics
    hour = int(time.time()) // 3600
    counts, _ = service.bucket_keys("frontend", hour)
    old = {key: 0 for key in service.COUNTERS}
    old.update(requests=4, success=4, status_2xx=4, unlocated=4)
    await redis.hset(
        counts,
        mapping={
            dimension + "|" + key: value
            for dimension in ("t", "c:XX", "r:/dashboard", "o:unknown:t", "o:unknown:c:XX", "o:unknown:r:/dashboard")
            for key, value in old.items()
        },
    )
    await redis.expire(counts, 3600)
    before = await service.snapshot("frontend", "24h", "unknown")
    assert before["totals"]["requests"] == 4 and before["networks"] == []
    assert await service.record_event(observation(peer_ip="10.8.4.5"), "frontend")
    after = await service.snapshot("frontend", "24h", "unknown")
    assert after["totals"]["requests"] == after["countries"][0]["requests"] == 5
    assert after["networks"][0]["requests"] == 1
    assert after["networks"][0]["network"] == "10.8.0.0/16"


def domain_request(token_info, headers=None):
    return SimpleNamespace(state=SimpleNamespace(token_info=token_info), headers=headers or {})


async def test_domain_requests_use_validated_token_domain_only(analytics):
    redis, _ = analytics
    now = time.time()
    verified = {"user_id": "u1", "domain_id": "tenant-a"}
    spoof = {"X-Domain-Id": "tenant-b", "X-Project-Id": "foreign"}
    assert await service.record_domain_request(
        domain_request(verified, spoof), status=200, route_template="/api/v1/instances/{id}", at=now
    )
    assert await service.record_domain_request(
        domain_request(verified, spoof), status=503, route_template="/api/v1/volumes", at=now
    )
    # Unauthenticated or token-less requests are never attributed from headers.
    assert not await service.record_domain_request(
        domain_request(None, {"X-Domain-Id": "tenant-a"}), status=200, route_template="/api/v1/instances", at=now
    )
    assert not await service.record_domain_request(
        domain_request({"user_id": "u2"}, {"X-Domain-Id": "tenant-a"}), status=200, route_template=None, at=now
    )
    selected = await service.domain_snapshot("tenant-a", "24h")
    assert selected["total"] == 2 and selected["errors"] == 1
    assert {row["service"]: (row["requests"], row["errors"]) for row in selected["services"]} == {
        "nova": (1, 0),
        "cinder": (1, 1),
    }
    foreign = await service.domain_snapshot("tenant-b", "24h")
    assert foreign["total"] is None and foreign["state"] != "ready"
    raw = repr([await redis.hgetall(key) async for key in redis.scan_iter(match=service.KEY_PREFIX + ":domain:*")])
    assert "tenant-a" not in raw and "u1" not in raw and "{id}" not in raw


async def test_same_private_aggregation_range_does_not_expand_cluster_authority(analytics):
    _, settings = analytics
    settings.traffic_analytics.cluster_cidrs = ["172.30.1.0/24"]
    for address in ("172.30.1.7", "172.30.2.7"):
        assert await service.record_event(observation(peer_ip=address), "frontend")
    data = await service.snapshot("frontend", "24h")
    assert data["origins"] == {"internal": 1, "external": 0, "unknown": 1, "legacy_unclassified": 0}
    assert len(data["networks"]) == 1
    assert data["networks"][0]["network"] == "172.30.0.0/16"
    assert data["networks"][0]["requests"] == 2
    for origin in ("internal", "unknown"):
        selected = await service.snapshot("frontend", "24h", origin)
        assert selected["networks"][0]["network"] == "172.30.0.0/16"
        assert selected["networks"][0]["requests"] == 1
