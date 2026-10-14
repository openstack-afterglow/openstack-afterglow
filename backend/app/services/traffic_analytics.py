"""Bounded, source-separated hourly Redis aggregates; raw client IPs never persist.

The only short-lived identifiers are random event UUIDs for exact ingest retry dedupe
(minute shards expire five minutes after their last write, max 10,000/minute/source).
All metrics updates, TTL, HLL and dedupe happen in one Redis Lua invocation.
"""

import asyncio
import hashlib
import hmac
import ipaddress
import time
from collections import defaultdict
from typing import Literal

from app.config import get_settings
from app.models.traffic_analytics import TrafficEvent
from app.services.cache import _get_redis
from app.services.traffic_geo import country_lookup

Source = Literal["backend", "frontend"]
RANGES = {"24h": 24, "7d": 168, "30d": 720}
KEY_PREFIX = "afterglow:{traffic}"
ROUTE_CATEGORIES = frozenset(
    {
        "/",
        "/admin",
        "/dashboard",
        "/login",
        "/docs",
        "/auth",
        "/health",
        "/other",
        "__unmatched__",
        "/api/compute",
        "/api/network",
        "/api/storage",
        "/api/identity",
        "/api/chat",
        "/api/monitoring",
        "/api/other",
    }
)
COUNTERS = (
    "requests",
    "success",
    "errors",
    "status_1xx",
    "status_2xx",
    "status_3xx",
    "status_4xx",
    "status_5xx",
    "pageviews",
    "unlocated",
    "request_bytes",
    "response_bytes",
    "request_bytes_known",
    "response_bytes_known",
    "latency_ms_total",
    "identity_known",
    "dropped_events",
    "reporter_dropped_events",
)
_pending_drops: dict[str, int] = defaultdict(int)

# Every key uses a common Redis Cluster hash tag. Event time is limited by ingress;
# expiries are absolute so late reports cannot extend historical retention.
AGGREGATE_LUA = r"""
for index = 3, #KEYS do
    if index ~= 4 and redis.call('HEXISTS', KEYS[index], ARGV[1]) == 1 then return 0 end
end
if redis.call('HLEN', KEYS[3]) >= 10000 then return -1 end
redis.call('HSET', KEYS[3], ARGV[1], '1')
redis.call('EXPIRE', KEYS[3], 300)
local measures = cjson.decode(ARGV[5])
local dimensions = {'t', 'c:' .. ARGV[3], 'r:' .. ARGV[4]}
for _, dimension in ipairs(dimensions) do
    for field, value in pairs(measures) do
        if field == 'latency_ms_total' then
            redis.call('HINCRBYFLOAT', KEYS[1], dimension .. '|' .. field, value)
        else
            redis.call('HINCRBY', KEYS[1], dimension .. '|' .. field, string.format('%.0f', value))
        end
    end
    local maximum = dimension .. '|latency_ms_max'
    local previous = tonumber(redis.call('HGET', KEYS[1], maximum) or '0')
    if tonumber(ARGV[6]) > previous then redis.call('HSET', KEYS[1], maximum, ARGV[6]) end
end
redis.call('EXPIREAT', KEYS[1], ARGV[2])
if ARGV[7] ~= '' then
    redis.call('PFADD', KEYS[2], ARGV[7])
    redis.call('EXPIREAT', KEYS[2], ARGV[2])
end
local first = tonumber(redis.call('HGET', KEYS[4], 'first') or ARGV[8])
local last = tonumber(redis.call('HGET', KEYS[4], 'last') or ARGV[8])
redis.call('HSET', KEYS[4], 'first', math.min(first, tonumber(ARGV[8])), 'last', math.max(last, tonumber(ARGV[8])))
redis.call('EXPIREAT', KEYS[4], ARGV[2])
return 1
"""


def route_category(template: str | None, source: Source) -> str:
    """Finite categories only. Never preserve URLs, path arguments or query text."""
    if not template or template == "__unmatched__":
        return "__unmatched__"
    if "?" in template or "#" in template:
        return "/other" if source == "frontend" else "/api/other"
    if template in ROUTE_CATEGORIES:
        return template
    if source == "frontend":
        for prefix in ("/admin", "/dashboard", "/login", "/docs", "/auth", "/health"):
            if template.startswith(prefix + "/"):
                return prefix
        return "/other"
    parts = template.strip("/").split("/")
    if parts[:2] == ["api", "v1"]:
        parts = parts[2:]
    elif parts[:1] == ["api"]:
        parts = parts[1:]
    resource = parts[0] if parts else ""
    groups = {
        "compute": {
            "servers",
            "instances",
            "flavors",
            "hypervisors",
            "images",
            "keypairs",
            "compute",
            "k3s",
            "containers",
            "zun",
        },
        "network": {
            "networks",
            "subnets",
            "routers",
            "ports",
            "floating-ips",
            "security-groups",
            "loadbalancers",
            "waygate",
            "network",
        },
        "storage": {"volumes", "snapshots", "backups", "shares", "object-storage", "union", "palimpsest", "storage"},
        "identity": {"auth", "users", "projects", "roles", "identity", "admin"},
        "chat": {"chat", "lumen", "models"},
        "monitoring": {"monitoring", "health", "metrics"},
    }
    return next((f"/api/{group}" for group, names in groups.items() if resource in names), "/api/other")


def identity_digest(address: str | None, secret: str) -> str:
    if address is None:
        return ""
    try:
        normalized = str(ipaddress.ip_address(address))
    except ValueError:
        return ""
    return hmac.new(secret.encode(), normalized.encode(), hashlib.sha256).hexdigest()


def bucket_keys(source: Source, hour: int) -> tuple[str, str]:
    root = f"{KEY_PREFIX}:{source}:{hour}"
    return root + ":counts", root + ":visitors"


async def record_event(event: TrafficEvent, source: Source) -> bool:
    """Fail open for callers, with recovered/drop coverage; never log event payloads."""
    settings = get_settings().traffic_analytics
    if not settings.enabled:
        return False
    pending = _pending_drops[source]
    # Detach before awaiting so concurrent successful writers never count the same drops.
    _pending_drops[source] = 0
    try:
        import json

        hour = int(event.at) // 3600
        country = country_lookup(settings.geoip_csv).country(event.client_ip)
        digest = identity_digest(event.client_ip, settings.hmac_key.get_secret_value())
        measures = {key: 0 for key in COUNTERS}
        measures.update(
            {
                "requests": 1,
                "success": int(200 <= event.status < 400),
                "errors": int(event.status >= 400),
                f"status_{event.status // 100}xx": 1,
                "pageviews": int(source == "frontend" and event.pageview),
                "unlocated": int(country == "XX"),
                "request_bytes": event.request_bytes or 0,
                "response_bytes": event.response_bytes or 0,
                "request_bytes_known": int(event.request_bytes is not None),
                "response_bytes_known": int(event.response_bytes is not None),
                "latency_ms_total": event.latency_ms,
                "identity_known": int(bool(digest)),
                "dropped_events": pending,
                "reporter_dropped_events": event.reporter_dropped_events,
            }
        )
        counts, visitors = bucket_keys(source, hour)
        minute = int(time.time()) // 60
        keys = [counts, visitors, f"{KEY_PREFIX}:{source}:dedupe:{minute}", f"{KEY_PREFIX}:{source}:coverage"]
        keys.extend(f"{KEY_PREFIX}:{source}:dedupe:{minute - offset}" for offset in range(1, 6))
        expiry = hour * 3600 + settings.retention_days * 86400
        async with asyncio.timeout(0.25):
            redis = await _get_redis()
            result = await redis.eval(
                AGGREGATE_LUA,
                len(keys),
                *keys,
                str(event.id),
                expiry,
                country,
                route_category(event.route, source),
                json.dumps(measures),
                event.latency_ms,
                digest,
                event.at,
            )
        if int(result) == 1:
            return True
        _pending_drops[source] += pending + int(int(result) < 0)
        return int(result) == 0  # An exact duplicate was already accepted.
    except Exception:
        _pending_drops[source] += pending + 1
        return False


def _text(value):
    return value.decode() if isinstance(value, bytes) else value


def _metrics(raw: dict, unique: int | None = None) -> dict:
    metrics = {
        key: int(raw.get(key, 0))
        for key in COUNTERS
        if key not in {"identity_known", "dropped_events", "reporter_dropped_events"}
    }
    metrics["latency_ms_total"] = float(raw.get("latency_ms_total", 0))
    metrics["latency_ms_max"] = float(raw.get("latency_ms_max", 0))
    for kind in ("request", "response"):
        if not metrics[f"{kind}_bytes_known"]:
            metrics[f"{kind}_bytes"] = None
    metrics["unique_visitors"] = unique if raw.get("identity_known", 0) else None
    metrics["visitor_identity_known"] = int(raw.get("identity_known", 0))
    return metrics


def _dimensions(raw: dict) -> dict[str, dict]:
    result: dict[str, dict] = defaultdict(dict)
    for field, value in raw.items():
        dimension, metric = _text(field).split("|", 1)
        result[dimension][metric] = float(value) if metric.startswith("latency_ms_") else int(value)
    return result


async def snapshot(source: Source, period: str) -> dict:
    settings = get_settings().traffic_analytics
    now = time.time()
    description = (
        "Backend ASGI requests only; excludes analytics ingest/read endpoints, WebSockets and requests outside this app. Body bytes are ASGI payload bytes, not wire bandwidth."
        if source == "backend"
        else "SvelteKit server requests only; HTML GET successes are SSR pageviews. Client-only SPA navigation, CDN/static bypasses and edge traffic are not observed. Body bytes exclude transport headers/compression outside the observer."
    )
    result = {
        "state": "disabled" if not settings.enabled else "unavailable",
        "source": source,
        "range": period,
        "retention_days": settings.retention_days,
        "generated_at": now,
        "coverage": {
            "description": description,
            "geo_source": country_lookup(settings.geoip_csv).state,
            "site_country": settings.site_country or None,
            "unique_method": "IP-derived HMAC + Redis HyperLogLog (~0.81% standard error); not people. NAT/shared IPs undercount; changing IPs overcount. No tracking cookie, user agent, body, token, URL/query or raw IP retained. Proxy headers use backend trusted_proxies only; frontend client address requires explicit adapter trust opt-in. Drops are recovered observations plus this worker; other lost/restarted workers and disconnected reporters are not knowable.",
            "dropped_events": None,
            "reporter_dropped_events": None,
            "observed_since": None,
            "last_observed_at": None,
        },
        "totals": None,
        "countries": [],
        "routes": [],
        "series": [],
    }
    if not settings.enabled:
        return result
    current = int(now) // 3600
    hours = list(range(current - min(RANGES[period], settings.retention_days * 24) + 1, current + 1))
    try:
        async with asyncio.timeout(3):
            redis = await _get_redis()
            pipe = redis.pipeline(transaction=True)
            for hour in hours:
                counts, visitors = bucket_keys(source, hour)
                pipe.hgetall(counts)
                pipe.pfcount(visitors)
            pipe.hgetall(f"{KEY_PREFIX}:{source}:coverage")
            pipe.pfcount(*(bucket_keys(source, hour)[1] for hour in hours))
            rows = await pipe.execute()
        merged: dict[str, dict] = defaultdict(lambda: defaultdict(int))
        for index, hour in enumerate(hours):
            dimensions = _dimensions(rows[index * 2])
            raw = dimensions.get("t")
            result["series"].append(
                {"at": hour * 3600, "metrics": _metrics(raw, int(rows[index * 2 + 1])) if raw else None}
            )
            for dimension, values in dimensions.items():
                for metric, value in values.items():
                    if metric == "latency_ms_max":
                        merged[dimension][metric] = max(merged[dimension][metric], value)
                    else:
                        merged[dimension][metric] += value
        totals = merged.get("t")
        coverage = {_text(key): float(value) for key, value in rows[-2].items()}
        if totals:
            result["totals"] = _metrics(totals, int(rows[-1]))
            result["countries"] = sorted(
                [{"country": key[2:], **_metrics(values)} for key, values in merged.items() if key.startswith("c:")],
                key=lambda row: -row["requests"],
            )
            result["routes"] = sorted(
                [{"route": key[2:], **_metrics(values)} for key, values in merged.items() if key.startswith("r:")],
                key=lambda row: -row["requests"],
            )
            result["coverage"].update(
                dropped_events=int(totals["dropped_events"]) + _pending_drops[source],
                reporter_dropped_events=int(totals["reporter_dropped_events"]),
                observed_since=max(coverage.get("first", hours[0] * 3600), hours[0] * 3600),
                last_observed_at=coverage.get("last"),
            )
        # An empty store has no proven observation interval; never present healthy zero.
        result["state"] = (
            "partial"
            if not totals
            or _pending_drops[source]
            or (totals and (totals["dropped_events"] or totals["reporter_dropped_events"]))
            or result["coverage"]["geo_source"] == "unavailable"
            else "available"
        )
    except Exception:
        pass
    return result
