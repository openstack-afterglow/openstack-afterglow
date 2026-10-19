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
from app.models.traffic_analytics import LegacyTrafficEvent, OriginFilter, TrafficEvent
from app.services.cache import _get_redis
from app.services.traffic_address import resolve_address
from app.services.traffic_geo import country_lookup

Source = Literal["backend", "frontend"]
RANGES = {"24h": 24, "7d": 168, "30d": 720}
KEY_PREFIX = "afterglow:{traffic}"
ORIGINS = ("internal", "external", "unknown", "legacy_unclassified")
GEO_REASONS = (
    "address_unavailable",
    "invalid_address",
    "non_global",
    "database_unconfigured",
    "database_unavailable",
    "range_missing",
    "country_invalid",
    "lookup_failed",
    "peer_unverified",
    "forwarded_missing",
    "forwarded_invalid",
    "forwarded_all_trusted",
    "legacy_unclassified",
)
ORIGIN_REASONS = (
    "peer_unverified",
    "address_unavailable",
    "invalid_address",
    "forwarded_missing",
    "forwarded_invalid",
    "forwarded_all_trusted",
    "non_global_noncluster",
    "legacy_unclassified",
)
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
for index = 3, 9 do
    if index ~= 4 and redis.call('HEXISTS', KEYS[index], ARGV[1]) == 1 then return 0 end
end
if redis.call('HLEN', KEYS[3]) >= 10000 then return -1 end
redis.call('HSET', KEYS[3], ARGV[1], '1')
redis.call('EXPIRE', KEYS[3], 300)
local measures = cjson.decode(ARGV[5])
local origin = 'o:' .. ARGV[9] .. ':'
local dimensions = {'t', 'c:' .. ARGV[3], 'r:' .. ARGV[4], origin .. 't', origin .. 'c:' .. ARGV[3], origin .. 'r:' .. ARGV[4]}
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
    redis.call('PFADD', KEYS[10], ARGV[7])
    redis.call('EXPIREAT', KEYS[10], ARGV[2])
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


def bucket_keys(source: Source, hour: int, version: int = 2) -> tuple[str, str]:
    root = f"{KEY_PREFIX}:{source}:" + ("v2:" if version == 2 else "") + str(hour)
    return root + ":counts", root + ":visitors"


async def record_event(event: TrafficEvent | LegacyTrafficEvent, source: Source) -> bool:
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
        if isinstance(event, LegacyTrafficEvent):
            address, origin, origin_reason = None, "legacy_unclassified", "legacy_unclassified"
        else:
            observation = resolve_address(
                event.peer_ip,
                event.peer_verified,
                event.forwarded_for,
                getattr(settings, source + "_trusted_proxy_cidrs"),
                settings.cluster_cidrs,
            )
            address, origin, origin_reason = observation.address, observation.origin, observation.reason
        country, geo_reason = country_lookup(settings.geoip_mmdb).lookup(address)
        if address is None:
            geo_reason = origin_reason
        digest = identity_digest(address, settings.hmac_key.get_secret_value())
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
        if geo_reason != "located":
            measures["geo_reason_" + geo_reason] = 1
        if origin_reason != "classified":
            measures["origin_reason_" + origin_reason] = 1
        counts, visitors = bucket_keys(source, hour)
        minute = int(time.time()) // 60
        keys = [counts, visitors, f"{KEY_PREFIX}:{source}:dedupe:{minute}", f"{KEY_PREFIX}:{source}:coverage"]
        keys.extend(f"{KEY_PREFIX}:{source}:dedupe:{minute - offset}" for offset in range(1, 6))
        keys.append(visitors + ":" + origin)
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
                origin,
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


def _merge(target: dict, values: dict):
    for metric, value in values.items():
        target[metric] = (
            max(target.get(metric, 0), value) if metric == "latency_ms_max" else target.get(metric, 0) + value
        )


def _selected_dimensions(dimensions: dict, origin: OriginFilter, legacy: bool = False) -> dict:
    if legacy:
        return (
            {key: value for key, value in dimensions.items() if not key.startswith("o:")}
            if origin in {"all", "legacy_unclassified"}
            else {}
        )
    if origin == "all":
        return {key: value for key, value in dimensions.items() if not key.startswith("o:")}
    prefix = f"o:{origin}:"
    return {key[len(prefix) :]: value for key, value in dimensions.items() if key.startswith(prefix)}


async def snapshot(source: Source, period: str, origin: OriginFilter = "all") -> dict:
    settings = get_settings().traffic_analytics
    now = time.time()
    geo = country_lookup(settings.geoip_mmdb)
    description = (
        "Backend ASGI requests only; excludes analytics endpoints, WebSockets and requests outside this app."
        if source == "backend"
        else "SvelteKit server requests only; HTML GET successes are SSR pageviews. SPA navigation, CDN/static bypasses and edge traffic are not observed."
    )
    result = {
        "state": "disabled" if not settings.enabled else "unavailable",
        "source": source,
        "origin": origin,
        "origins": None,
        "range": period,
        "retention_days": settings.retention_days,
        "generated_at": now,
        "coverage": {
            "description": description + " Body bytes are application payload bytes, not wire bandwidth.",
            "geo_source": geo.state,
            "geo_provider": geo.provider,
            "geo_version": geo.version,
            "geo_attribution": geo.attribution,
            "geo_unknown_reasons": {},
            "origin_unknown_reasons": {},
            "classified_requests": None,
            "legacy_unclassified_requests": None,
            "classification_policy": "Only configured cluster CIDRs are internal. Global noncluster addresses are external; other or unverified addresses are unknown. Original socket provenance and exact right-to-left trusted proxy CIDRs are required. Legacy writers/buckets cannot be reclassified. Current DB metadata is not historical dataset attribution; replacing DBs/CIDRs affects only new events. Coverage timestamps describe the selected source, not the origin filter.",
            "site_country": settings.site_country or None,
            "unique_method": "IP-derived HMAC + Redis HyperLogLog (~0.81% standard error); not people. NAT/shared IPs undercount; changing IPs overcount. Source estimates are independent. No tracking cookie, user agent, body, token, URL/query or raw IP retained. Legacy identities retain their original method. Drops include recovered observations and this worker only; lost/restarted workers and disconnected reporters are not knowable.",
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

    def hll_keys(hour):
        old = bucket_keys(source, hour, 1)[1]
        new = bucket_keys(source, hour)[1]
        if origin == "all":
            return [old, new]
        if origin == "legacy_unclassified":
            return [old, new + ":legacy_unclassified"]
        return [new + ":" + origin]

    try:
        async with asyncio.timeout(3):
            redis = await _get_redis()
            pipe = redis.pipeline(transaction=True)
            for hour in hours:
                pipe.hgetall(bucket_keys(source, hour, 1)[0])
                pipe.hgetall(bucket_keys(source, hour)[0])
                pipe.pfcount(*hll_keys(hour))
            pipe.hgetall(f"{KEY_PREFIX}:{source}:coverage")
            pipe.pfcount(*(key for hour in hours for key in hll_keys(hour)))
            rows = await pipe.execute()
        merged = defaultdict(dict)
        route_origins = defaultdict(lambda: dict.fromkeys(ORIGINS, 0))
        selected_origins = dict.fromkeys(ORIGINS, 0)
        source_totals = {}
        for index, hour in enumerate(hours):
            old, new, unique = rows[index * 3 : index * 3 + 3]
            hourly = defaultdict(dict)
            for raw, legacy in ((old, True), (new, False)):
                all_dimensions = _dimensions(raw)
                _merge(source_totals, all_dimensions.get("t", {}))
                for selected in ORIGINS:
                    if origin not in {"all", selected}:
                        continue
                    selected_dimensions = _selected_dimensions(all_dimensions, selected, legacy)
                    selected_origins[selected] += selected_dimensions.get("t", {}).get("requests", 0)
                    for dimension, values in selected_dimensions.items():
                        if dimension.startswith("r:"):
                            route_origins[dimension[2:]][selected] += values.get("requests", 0)
                for dimension, values in _selected_dimensions(all_dimensions, origin, legacy).items():
                    _merge(hourly[dimension], values)
                # Historical v1 stores no explicit reasons. Preserve unknown coverage
                # as legacy, never infer the country/address reason retrospectively.
                if legacy and origin in {"all", "legacy_unclassified"} and "t" in all_dimensions:
                    legacy_totals = all_dimensions["t"]
                    hourly["t"]["geo_reason_legacy_unclassified"] = hourly["t"].get(
                        "geo_reason_legacy_unclassified", 0
                    ) + legacy_totals.get("unlocated", 0)
                    hourly["t"]["origin_reason_legacy_unclassified"] = hourly["t"].get(
                        "origin_reason_legacy_unclassified", 0
                    ) + legacy_totals.get("requests", 0)
            raw = hourly.get("t")
            result["series"].append({"at": hour * 3600, "metrics": _metrics(raw, int(unique)) if raw else None})
            for dimension, values in hourly.items():
                _merge(merged[dimension], values)
        totals = merged.get("t")
        coverage = {_text(key): float(value) for key, value in rows[-2].items()}
        result["coverage"].update(
            observed_since=max(coverage.get("first", hours[0] * 3600), hours[0] * 3600) if coverage else None,
            last_observed_at=coverage.get("last"),
            classified_requests=selected_origins["internal"] + selected_origins["external"] if totals else None,
            legacy_unclassified_requests=selected_origins["legacy_unclassified"] if totals else None,
        )
        if source_totals:
            # Lost events cannot be assigned an origin. Coverage is source-wide,
            # independent of the selected origin, just like source timestamps.
            result["coverage"].update(
                dropped_events=int(source_totals.get("dropped_events", 0)) + _pending_drops[source],
                reporter_dropped_events=int(source_totals.get("reporter_dropped_events", 0)),
            )
        if totals:
            result["origins"] = selected_origins
            result["totals"] = _metrics(totals, int(rows[-1]))
            result["countries"] = sorted(
                [{"country": key[2:], **_metrics(values)} for key, values in merged.items() if key.startswith("c:")],
                key=lambda row: (-row["requests"], row["country"]),
            )
            result["routes"] = sorted(
                [
                    {"route": key[2:], "origins": route_origins[key[2:]], **_metrics(values)}
                    for key, values in merged.items()
                    if key.startswith("r:")
                ],
                key=lambda row: (-row["requests"], row["route"]),
            )
            result["coverage"].update(
                geo_unknown_reasons={
                    reason: int(totals.get("geo_reason_" + reason, 0))
                    for reason in GEO_REASONS
                    if totals.get("geo_reason_" + reason)
                },
                origin_unknown_reasons={
                    reason: int(totals.get("origin_reason_" + reason, 0))
                    for reason in ORIGIN_REASONS
                    if totals.get("origin_reason_" + reason)
                },
            )
        result["state"] = (
            "partial"
            if not totals
            or _pending_drops[source]
            or source_totals.get("dropped_events")
            or source_totals.get("reporter_dropped_events")
            or geo.state == "unavailable"
            else "available"
        )
    except Exception:
        pass
    return result


DOMAIN_AGGREGATE_LUA = r"""
redis.call('HINCRBY', KEYS[1], 't|requests', 1)
redis.call('HINCRBY', KEYS[1], 't|errors', ARGV[1])
redis.call('HINCRBY', KEYS[1], 's:' .. ARGV[2] .. '|requests', 1)
redis.call('HINCRBY', KEYS[1], 's:' .. ARGV[2] .. '|errors', ARGV[1])
redis.call('HINCRBY', KEYS[1], 't|dropped', ARGV[5])
redis.call('EXPIREAT', KEYS[1], ARGV[3])
local first = tonumber(redis.call('HGET', KEYS[2], 'first') or ARGV[4])
redis.call('HSET', KEYS[2], 'first', math.min(first, tonumber(ARGV[4])), 'last', ARGV[4])
redis.call('EXPIREAT', KEYS[2], ARGV[3])
return 1
"""


def _domain_root(domain_id: str) -> str:
    return f"{KEY_PREFIX}:domain:{hashlib.sha256(domain_id.encode()).hexdigest()}"


def domain_service(template: str | None) -> str:
    """Finite labels from main.py mount prefixes; never URL arguments or queries.

    Administrative routes stay "afterglow": they are not tenant service usage.
    """
    parts = (template or "").split("/")
    if len(parts) < 4 or parts[1:3] != ["api", "v1"]:
        return "afterglow"
    resource = parts[3]
    groups = {
        "nova": {"instances", "flavors", "keypairs"},
        "glance": {"images"},
        "cinder": {"volumes", "volume-snapshots"},
        "neutron": {"networks", "routers", "security-groups"},
        "octavia": {"loadbalancers"},
        "manila": {"file-storage", "share-snapshots", "share-networks", "security-services"},
        "magnum": {"clusters"},
        "zun": {"containers", "cloud-shell"},
        "drover": {"k3s"},
        "palimpsest": {"palimpsest"},
        "trove": {"database-instances"},
        "swift": {"object-storage"},
        "barbican": {"secrets", "secret-containers", "secret-orders"},
        "waygate": {"waygate"},
        "lumen": {"chat"},
        "keystone": {"auth", "projects", "invitations", "iam", "profile"},
    }
    return next((service for service, resources in groups.items() if resource in resources), "afterglow")


async def record_domain_request(request, *, status: int, route_template: str | None, at: float) -> bool:
    """Parent middleware hook, AFTER auth: only request.state.token_info is authority.

    Call once on completion with the native matched route template. Headers,
    frontend analytics and unvalidated login names are never attribution inputs.
    This stores only hour/service request and error counters, not identities.
    """
    settings = get_settings().traffic_analytics
    info = getattr(request.state, "token_info", None)
    domain_id = info.get("domain_id") if isinstance(info, dict) else None
    if (
        not settings.enabled
        or not isinstance(domain_id, str)
        or not domain_id
        or not info.get("user_id")
        or not isinstance(status, int)
        or not 100 <= status <= 599
    ):
        return False
    root = _domain_root(domain_id)
    pending = _pending_drops[root]
    _pending_drops[root] = 0
    hour = int(at) // 3600
    try:
        async with asyncio.timeout(0.25):
            redis = await _get_redis()
            await redis.eval(
                DOMAIN_AGGREGATE_LUA,
                2,
                f"{root}:{hour}",
                f"{root}:coverage",
                int(status >= 400),
                domain_service(route_template),
                hour * 3600 + settings.retention_days * 86400,
                at,
                pending,
            )
        return True
    except Exception:
        _pending_drops[root] += pending + 1
        return False


async def domain_snapshot(domain_id: str, window: str) -> dict:
    """Observed authenticated backend requests only; an empty store is unknown."""
    from datetime import UTC, datetime

    settings = get_settings().traffic_analytics
    result = {
        "state": "disabled" if not settings.enabled else "unavailable",
        "window": window,
        "total": None,
        "errors": None,
        "services": [],
        "timeline": None,
    }
    if not settings.enabled:
        return result
    now = time.time()
    current = int(now) // 3600
    hours = list(range(current - min(RANGES[window], settings.retention_days * 24) + 1, current + 1))
    root = _domain_root(domain_id)
    try:
        async with asyncio.timeout(3):
            redis = await _get_redis()
            pipe = redis.pipeline(transaction=True)
            for hour in hours:
                pipe.hgetall(f"{root}:{hour}")
            pipe.hgetall(f"{root}:coverage")
            rows = await pipe.execute()
        totals = defaultdict(int)
        services = defaultdict(lambda: defaultdict(int))
        timeline = []
        for hour, raw in zip(hours, rows[:-1], strict=True):
            dimensions = _dimensions(raw)
            values = dimensions.get("t")
            timeline.append(
                {
                    "at": datetime.fromtimestamp(hour * 3600, UTC).isoformat(),
                    "requests": values.get("requests", 0) if values else 0,
                    "errors": values.get("errors", 0) if values else 0,
                }
            )
            if values:
                for key, value in values.items():
                    totals[key] += value
            for dimension, values in dimensions.items():
                if dimension.startswith("s:"):
                    for key, value in values.items():
                        services[dimension[2:]][key] += value
        coverage = {_text(key): float(value) for key, value in rows[-1].items()}
        if not totals or not coverage:
            result["state"] = "partial"
            return result
        partial = (
            coverage.get("first", now) > hours[0] * 3600
            or totals["dropped"]
            or _pending_drops[root]
            or RANGES[window] > settings.retention_days * 24
        )
        result.update(
            state="partial" if partial else "ready",
            total=totals["requests"],
            errors=totals["errors"],
            services=[
                {"service": service, "requests": values["requests"], "errors": values["errors"]}
                for service, values in sorted(services.items())
            ],
            timeline=timeline,
        )
    except Exception:
        return result
    return result
