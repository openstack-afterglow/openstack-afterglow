"""Traffic privacy/security and pass-through observation. No external network needed."""

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.api.common import traffic_analytics as api
from app.api.deps import get_token_info
from app.middleware import traffic_analytics as middleware
from app.models.traffic_analytics import TrafficAnalyticsSettings, TrafficEvent
from app.services import traffic_analytics as service
from app.services.traffic_geo import CountryLookup


@pytest.fixture
def settings(monkeypatch):
    settings = SimpleNamespace(
        traffic_analytics=TrafficAnalyticsSettings(
            enabled=True,
            hmac_key="h" * 32,
            frontend_ingest_key="f" * 32,
        ),
        trusted_proxies="",
    )
    for module in (api, service, middleware):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    service._pending_drops.clear()
    yield settings
    service._pending_drops.clear()


def event(**changes):
    return TrafficEvent(id=uuid4(), at=time.time(), status=200, route="/dashboard", latency_ms=12, **changes)


def test_settings_opt_in_secrets_and_retention():
    assert TrafficAnalyticsSettings().enabled is False
    assert TrafficAnalyticsSettings().retention_days == 30
    for changes in (
        {"enabled": True},
        {"retention_days": 31},
        {"retention_days": 0},
        {"enabled": True, "hmac_key": "x" * 32, "frontend_ingest_key": "x" * 32},
    ):
        with pytest.raises(ValidationError):
            TrafficAnalyticsSettings(**changes)
    for field in ("cluster_cidrs", "backend_trusted_proxy_cidrs", "frontend_trusted_proxy_cidrs"):
        for cidrs in (["*"], ["0.0.0.0/0"], ["172.30.1.1/16"], ["::/0"], ["bad"]):
            with pytest.raises(ValidationError):
                TrafficAnalyticsSettings(**{field: cidrs})


def test_offline_mmdb_metadata_ipv6_and_unknown_reasons(tmp_path, monkeypatch):
    import sys

    path = tmp_path / "country.mmdb"
    path.write_bytes(b"synthetic unit reader seam, not a country database")
    rows = {
        "8.8.8.8": {"country": {"iso_code": "KR"}},
        "2001:4860:4860::8888": {"country": {"iso_code": "US"}},
        "1.1.1.1": {"country": {"iso_code": "ZZ"}},
    }
    reader = SimpleNamespace(
        metadata=lambda: SimpleNamespace(database_type="DBIP-Country-Lite", build_epoch=1790812800),
        get=lambda address: rows.get(address),
        close=lambda: None,
    )
    monkeypatch.setitem(
        sys.modules, "maxminddb", SimpleNamespace(MODE_MMAP=2, open_database=lambda filename, mode: reader)
    )
    geo = CountryLookup(str(path))
    assert geo.state == "offline_mmdb" and geo.provider == "DB-IP"
    assert geo.version == "2026-10-01" and "CC BY 4.0" in geo.attribution
    assert geo.lookup("8.8.8.8") == ("KR", "located")
    assert geo.lookup("2001:4860:4860::8888") == ("US", "located")
    assert geo.lookup(None) == ("XX", "address_unavailable")
    assert geo.lookup("bad") == ("XX", "invalid_address")
    assert geo.lookup("10.1.1.1") == ("XX", "non_global")
    assert geo.lookup("9.9.9.9") == ("XX", "range_missing")
    assert geo.lookup("1.1.1.1") == ("XX", "country_invalid")
    assert CountryLookup("").lookup("8.8.8.8") == ("XX", "database_unconfigured")
    assert CountryLookup(str(tmp_path / "missing.mmdb")).lookup("8.8.8.8") == ("XX", "database_unavailable")


def test_mmdb_corruption_and_wrong_provider_fail_closed(tmp_path, monkeypatch):
    import sys
    from unittest.mock import Mock

    path = tmp_path / "country.mmdb"
    path.write_bytes(b"not a database")

    def corrupt(filename, mode):
        raise ValueError("malformed metadata, never echoed")

    monkeypatch.setitem(sys.modules, "maxminddb", SimpleNamespace(MODE_MMAP=2, open_database=corrupt))
    assert CountryLookup(str(path)).state == "unavailable"
    reader = SimpleNamespace(metadata=lambda: SimpleNamespace(database_type="Other-City", build_epoch=0), close=Mock())
    monkeypatch.setitem(
        sys.modules, "maxminddb", SimpleNamespace(MODE_MMAP=2, open_database=lambda filename, mode: reader)
    )
    assert CountryLookup(str(path)).state == "unavailable"
    reader.close.assert_called_once()


def test_route_cardinality_and_hmac_privacy():
    secret = "h" * 32
    assert service.identity_digest("8.8.8.8", secret) == service.identity_digest("8.8.8.8", secret)
    assert "8.8.8.8" not in service.identity_digest("8.8.8.8", secret)
    assert service.identity_digest("bad", secret) == ""
    assert service.route_category("/dashboard/instances/private-id", "frontend") == "/dashboard"
    assert service.route_category("/api/v1/servers/{server_id}", "backend") == "/api/compute"
    for number in range(1000):
        assert service.route_category(f"/unknown/secret-{number}?token=private", "backend") == "/api/other"


async def test_redis_outage_is_unknown_and_recovered_drops(settings, monkeypatch):
    broken = AsyncMock(side_effect=ConnectionError("redis unavailable"))
    monkeypatch.setattr(service, "_get_redis", broken)
    assert await service.record_event(event(), "backend") is False
    snapshot = await service.snapshot("backend", "24h")
    assert snapshot["state"] == "unavailable"
    assert snapshot["totals"] is None
    assert snapshot["coverage"]["dropped_events"] is None
    redis = SimpleNamespace(eval=AsyncMock(return_value=1))
    monkeypatch.setattr(service, "_get_redis", AsyncMock(return_value=redis))
    assert await service.record_event(event(), "backend") is True
    args = redis.eval.call_args.args
    measures = json.loads(args[args[1] + 6])
    assert measures["dropped_events"] == 1
    assert service._pending_drops["backend"] == 0


async def test_unknown_sizes_are_not_false_zero(settings, monkeypatch):
    redis = SimpleNamespace(eval=AsyncMock(return_value=1))
    monkeypatch.setattr(service, "_get_redis", AsyncMock(return_value=redis))
    await service.record_event(event(peer_ip="8.8.8.8", peer_verified=True), "frontend")
    args = redis.eval.call_args.args
    measures = json.loads(args[args[1] + 6])
    assert measures["request_bytes_known"] == 0
    assert measures["response_bytes_known"] == 0
    assert measures["unlocated"] == 1
    assert "8.8.8.8" not in repr(args)
    assert service._metrics(measures)["request_bytes"] is None
    assert service._metrics(measures)["unique_visitors"] is None


def asgi_scope(path="/api/v1/servers/private-id", headers=None):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"token=NEVER-RETAIN",
        "headers": headers or [],
        "client": ("8.8.8.8", 1234),
        "server": ("test", 80),
        "scheme": "http",
        "route": SimpleNamespace(path="/api/v1/servers/{server_id}"),
    }


async def test_middleware_streams_messages_unchanged_and_only_reads_on_demand(settings, monkeypatch):
    recorded = []

    async def record(value, source):
        recorded.append((value, source))
        return True

    monkeypatch.setattr(middleware, "record_event", record)
    incoming = [
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.request", "body": b"defg", "more_body": False},
    ]
    receive = AsyncMock(side_effect=incoming)
    sent = []
    output = [
        {"type": "http.response.start", "status": 201, "headers": []},
        {"type": "http.response.body", "body": b"one", "more_body": True},
        {"type": "http.response.body", "body": b"two!", "more_body": False},
    ]

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        assert await receive() is incoming[0]
        assert await receive() is incoming[1]
        for message in output:
            await send(message)

    await middleware.TrafficAnalyticsMiddleware(app)(asgi_scope(), receive, send)
    assert all(left is right for left, right in zip(sent, output))
    assert receive.await_count == 2
    observation, source = recorded[0]
    assert (source, observation.status, observation.request_bytes, observation.response_bytes) == ("backend", 201, 7, 7)
    assert observation.route == "/api/compute"
    assert "NEVER-RETAIN" not in observation.model_dump_json()
    assert "private-id" not in observation.model_dump_json()


async def test_middleware_does_not_consume_unread_request_and_does_not_mask_error(settings, monkeypatch):
    record = AsyncMock(return_value=True)
    monkeypatch.setattr(middleware, "record_event", record)
    receive = AsyncMock()

    async def broken(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"partial", "more_body": True})
        raise RuntimeError("application failure")

    with pytest.raises(RuntimeError, match="application failure"):
        await middleware.TrafficAnalyticsMiddleware(broken)(asgi_scope(), receive, AsyncMock())
    receive.assert_not_awaited()
    observation = record.call_args.args[0]
    assert observation.request_bytes is None and observation.response_bytes is None
    assert observation.status == 200  # Actual response-start, not fabricated 5xx.


async def test_middleware_metrics_failure_and_analytics_exclusion(settings, monkeypatch):
    record = AsyncMock(side_effect=ConnectionError("metrics down"))
    monkeypatch.setattr(middleware, "record_event", record)

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    await middleware.TrafficAnalyticsMiddleware(app)(asgi_scope(), AsyncMock(), AsyncMock())
    assert record.await_count == 1
    await middleware.TrafficAnalyticsMiddleware(app)(
        asgi_scope("/api/v1/monitoring/traffic/events"), AsyncMock(), AsyncMock()
    )
    assert record.await_count == 1


async def test_ingest_writer_scope_freshness_bounds_and_no_validation_echo(settings, monkeypatch):
    app = FastAPI()
    app.include_router(api.ingest_router, prefix="/ingest")
    record = AsyncMock(return_value=True)
    monkeypatch.setattr(api, "record_event", record)
    data = event(peer_ip="8.8.8.8", peer_verified=True).model_dump(mode="json")
    headers = {"Authorization": "Bearer " + "f" * 32}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/ingest/events", json=data)).status_code == 401
        bad = {**data, "country": "KR", "source": "backend", "secret": "NEVER-ECHO"}
        response = await client.post("/ingest/events", headers=headers, json=bad)
        assert response.status_code == 422 and "NEVER-ECHO" not in response.text
        assert (
            await client.post("/ingest/events", headers=headers, json={**data, "at": time.time() - 121})
        ).status_code == 422
        assert (await client.post("/ingest/events", headers=headers, content=b"x" * 2049)).status_code == 413
        response = await client.post("/ingest/events", headers={**headers, "CF-IPCountry": "KR"}, json=data)
        assert response.json() == {"accepted": True}
        assert record.call_args.args[1] == "frontend"
        assert record.call_args.args[0].peer_ip == "8.8.8.8"
        record.return_value = False
        assert (await client.post("/ingest/events", headers=headers, json=data)).status_code == 503


async def test_admin_aggregate_requires_verified_system_admin(settings, monkeypatch):
    app = FastAPI()
    app.include_router(api.admin_router, prefix="/traffic")
    app.dependency_overrides[get_token_info] = lambda: {"is_system_admin": False, "roles": ["admin"]}
    observed = AsyncMock(return_value={})
    monkeypatch.setattr(api, "snapshot", observed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/traffic")).status_code == 403
        observed.assert_not_awaited()
        app.dependency_overrides[get_token_info] = lambda: {"is_system_admin": True}
        assert (await client.get("/traffic?range=all&source=anything")).status_code == 422
        assert (await client.get("/traffic?origin=made-up")).status_code == 422
        observed.assert_not_awaited()
        monkeypatch.setattr(service, "_get_redis", AsyncMock(side_effect=ConnectionError("unavailable")))
        observed.return_value = await service.snapshot("backend", "24h")
        response = await client.get("/traffic?range=24h&source=backend")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["state"] == "unavailable"
        assert response.json()["totals"] is None
        assert response.json()["coverage"]["last_observed_at"] is None


@pytest.mark.parametrize("country", ["", "KR"])
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("source", ["backend", "frontend"])
async def test_snapshot_http_exposes_configured_or_null_site_country(settings, monkeypatch, country, enabled, source):
    settings.traffic_analytics.site_country = country
    settings.traffic_analytics.enabled = enabled
    monkeypatch.setattr(service, "_get_redis", AsyncMock(side_effect=ConnectionError("unavailable")))
    app = FastAPI()
    app.include_router(api.admin_router, prefix="/traffic")
    app.dependency_overrides[get_token_info] = lambda: {"is_system_admin": True}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/traffic?range=24h&source={source}")
    assert response.status_code == 200
    assert response.json()["coverage"]["site_country"] == (country or None)


@pytest.mark.parametrize(
    "peer,verified,chain,expected,reason",
    [
        ("8.8.8.8", True, "172.30.0.12", "external", "classified"),
        ("172.30.0.11", True, "8.8.8.8, 172.30.0.12", "external", "classified"),
        ("172.30.0.11", True, "8.8.8.8, 192.168.8.1", "unknown", "non_global_noncluster"),
        ("172.30.0.11", True, "172.30.9.4", "internal", "classified"),
        ("172.30.0.11", True, "bad, 8.8.8.8", "unknown", "forwarded_invalid"),
        ("172.30.0.11", True, None, "unknown", "forwarded_missing"),
        ("172.30.0.11", True, "172.30.0.12", "unknown", "forwarded_all_trusted"),
        ("8.8.8.8", False, "8.8.4.4", "unknown", "peer_unverified"),
        (None, True, None, "unknown", "address_unavailable"),
        ("garbage", True, None, "unknown", "invalid_address"),
        ("2001:4860:4860::8888", True, None, "external", "classified"),
        ("fd00:1234::5", True, None, "internal", "classified"),
        ("fd00:9999::5", True, None, "unknown", "non_global_noncluster"),
        ("::ffff:172.30.5.1", True, None, "internal", "classified"),
    ],
)
def test_analytics_proxy_chain_and_origin_policy(peer, verified, chain, expected, reason):
    from app.services.traffic_address import resolve_address

    result = resolve_address(
        peer, verified, chain, ["172.30.0.11/32", "172.30.0.12/32"], ["172.30.0.0/16", "fd00:1234::/48"]
    )
    assert result.origin == expected and result.reason == reason


async def test_original_peer_capture_preserves_auth_client_and_https_and_combines_headers(settings, monkeypatch):
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    from app.middleware.traffic_address import OriginalPeerMiddleware

    settings.traffic_analytics.backend_trusted_proxy_cidrs = ["172.30.0.11/32", "172.30.0.12/32"]
    record = AsyncMock(return_value=True)
    monkeypatch.setattr(middleware, "record_event", record)
    seen = []

    async def app(scope, receive, send):
        seen.append((scope["client"], scope["scheme"]))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    scope = asgi_scope(
        headers=[
            (b"x-forwarded-for", b"8.8.8.8"),
            (b"x-forwarded-for", b"172.30.0.12"),
            (b"x-forwarded-proto", b"https"),
        ]
    )
    scope["client"] = ("172.30.0.11", 43210)
    wrapped = OriginalPeerMiddleware(
        ProxyHeadersMiddleware(middleware.TrafficAnalyticsMiddleware(app), trusted_hosts="172.30.0.11,172.30.0.12")
    )
    await wrapped(scope, AsyncMock(), AsyncMock())
    # Uvicorn sees its exact original configuration (including duplicate-header semantics).
    assert seen == [(("172.30.0.12", 0), "https")]
    observed = record.call_args.args[0]
    assert observed.peer_ip == "172.30.0.11" and observed.peer_verified
    assert observed.forwarded_for == "8.8.8.8,172.30.0.12"
    assert scope["client"] == ("172.30.0.11", 43210)  # no caller mutation


async def test_backend_without_original_peer_does_not_trust_rewritten_client(settings, monkeypatch):
    record = AsyncMock(return_value=True)
    monkeypatch.setattr(middleware, "record_event", record)

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})

    await middleware.TrafficAnalyticsMiddleware(app)(asgi_scope(), AsyncMock(), AsyncMock())
    assert record.call_args.args[0].peer_verified is False


async def test_old_frontend_writer_is_explicit_legacy_boundary(settings, monkeypatch):
    from app.models.traffic_analytics import LegacyTrafficEvent

    app = FastAPI()
    app.include_router(api.ingest_router, prefix="/ingest")
    record = AsyncMock(return_value=True)
    monkeypatch.setattr(api, "record_event", record)
    data = event().model_dump(mode="json")
    for key in ("schema_version", "peer_ip", "peer_verified", "forwarded_for"):
        data.pop(key)
    data["client_ip"] = "8.8.8.8"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/ingest/events", headers={"Authorization": "Bearer " + "f" * 32}, json=data)
    assert response.status_code == 200
    assert isinstance(record.call_args.args[0], LegacyTrafficEvent)


@pytest.mark.parametrize(
    "chain",
    [
        "8.8.8.8:443",
        "[2001:4860::1]",
        "8.8.8.8,",
        ",8.8.8.8",
        "unknown",
        "8.8.8.8," * 16 + "8.8.8.8",
        "1" * 1025,
        "fe80::1%eth0",
    ],
)
def test_trusted_proxy_rejects_entire_malformed_or_over_limit_chain(chain):
    from app.services.traffic_address import resolve_address

    result = resolve_address("172.30.0.11", True, chain, ["172.30.0.11/32"], ["172.30.0.0/16"])
    assert result.address is None and result.origin == "unknown" and result.reason == "forwarded_invalid"


async def test_sources_use_independent_exact_proxy_policies(settings, monkeypatch):
    settings.traffic_analytics.backend_trusted_proxy_cidrs = ["172.30.0.11/32"]
    settings.traffic_analytics.cluster_cidrs = ["172.30.0.0/16"]
    redis = SimpleNamespace(eval=AsyncMock(return_value=1))
    monkeypatch.setattr(service, "_get_redis", AsyncMock(return_value=redis))
    value = event(peer_ip="172.30.0.11", peer_verified=True, forwarded_for="8.8.8.8")
    assert await service.record_event(value, "backend")
    assert redis.eval.call_args.args[-1] == "external"
    assert await service.record_event(value, "frontend")
    assert redis.eval.call_args.args[-1] == "internal"
    # The same UUID belongs to independent source dedupe namespaces.
    assert ":frontend:dedupe:" in repr(redis.eval.call_args.args)
