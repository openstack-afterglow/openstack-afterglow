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


def test_offline_country_lookup_longest_prefix_private_and_invalid(tmp_path):
    path = tmp_path / "geo.csv"
    path.write_text("cidr,country\n8.0.0.0/8,US\n8.8.8.0/24,KR\n2001:4860::/32,US\n10.0.0.0/8,JP\n")
    geo = CountryLookup(str(path))
    assert geo.state == "offline_cidr"
    assert geo.country("8.8.8.8") == "KR"
    assert geo.country("8.1.1.1") == "US"
    assert geo.country("2001:4860:4860::8888") == "US"
    for address in (None, "bad", "10.1.1.1", "127.0.0.1", "192.0.2.1", "9.9.9.9"):
        assert geo.country(address) == "XX"
    path.write_text("cidr,country\n8.8.8.0/24,ZZ\n")
    assert CountryLookup(str(path)).state == "unavailable"
    assert CountryLookup("").state == "unconfigured"
    assert CountryLookup(str(tmp_path / "missing.csv")).country("8.8.8.8") == "XX"


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
    await service.record_event(event(client_ip="8.8.8.8"), "frontend")
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
    monkeypatch.setattr(middleware, "_get_real_ip", lambda request: "8.8.8.8")
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
    monkeypatch.setattr(middleware, "_get_real_ip", lambda request: "8.8.8.8")
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
    data = event(client_ip="8.8.8.8").model_dump(mode="json")
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
        assert record.call_args.args[0].client_ip == "8.8.8.8"
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


async def test_backend_proxy_trust_ignores_headers_unless_peer_trusted(settings, monkeypatch):
    from starlette.requests import Request

    from app import rate_limit

    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    scope = asgi_scope(headers=[(b"x-forwarded-for", b"9.9.9.9"), (b"cf-ipcountry", b"KR")])
    assert rate_limit._get_real_ip(Request(scope)) == "8.8.8.8"
    settings.trusted_proxies = "8.8.8.0/24"
    assert rate_limit._get_real_ip(Request(scope)) == "9.9.9.9"
