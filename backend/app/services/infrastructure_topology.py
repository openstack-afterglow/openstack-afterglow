"""Reporter-driven topology and single-host bounded diagnostics in shared Redis."""

import hashlib
import hmac
import json
import time
import uuid

from fastapi import HTTPException

from app.config import get_settings
from app.models.infrastructure_topology import Observation, TraceResult
from app.services import host_health
from app.services.cache import _get_redis

INTERVAL_SECONDS = 10
STALE_SECONDS = 30
RETENTION_SAMPLES = 60
COUNTERS = ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets")

# Store rates/history only if the exact previously read observation still owns the slot.
_STORE_REPORT = """
local old = redis.call('GET', KEYS[1]) or ''
if old ~= ARGV[1] then return 0 end
local previous = tonumber(redis.call('GET', KEYS[2]) or '0')
local captured = tonumber(ARGV[2])
if captured <= previous then return -1 end
if previous > 0 and captured - previous < 5 then return -2 end
redis.call('SET', KEYS[1], ARGV[3], 'EX', ARGV[4])
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[4])
return 1
"""
_ENQUEUE = """
local active = redis.call('GET', KEYS[1])
if active then
 local job = cjson.decode(active)
 if tonumber(job.expires_at) > tonumber(ARGV[1]) and
    (job.status == 'queued' or job.status == 'running') then return 0 end
end
if redis.call('EXISTS', KEYS[3]) == 1 then return -1 end
redis.call('SET', KEYS[3], '1', 'EX', 60)
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
local history = redis.call('LRANGE', KEYS[2], 0, 19)
redis.call('DEL', KEYS[2])
for _, entry in ipairs(history) do
 if tonumber(cjson.decode(entry).created_at) >= tonumber(ARGV[1]) - tonumber(ARGV[3]) then
  redis.call('RPUSH', KEYS[2], entry)
 end
end
redis.call('LPUSH', KEYS[2], ARGV[2])
redis.call('LTRIM', KEYS[2], 0, 19)
redis.call('EXPIRE', KEYS[2], ARGV[3])
return 1
"""
# Python owns JSON encoding; Lua only compares and stores exact strings so
# empty arrays and float timestamps are never rewritten by Redis cjson.
_REPLACE_JOB = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2], 'KEEPTTL')
if ARGV[3] ~= '' then
 local history = redis.call('LRANGE', KEYS[2], 0, 19)
 for i, entry in ipairs(history) do
  if cjson.decode(entry).id == ARGV[3] then redis.call('LSET', KEYS[2], i-1, ARGV[2]) end
 end
end
return 1
"""
JOB_FIELDS = ("id", "target", "max_hops", "timeout_seconds", "status", "created_at", "expires_at")


def _text(raw):
    return raw.decode() if isinstance(raw, bytes) else raw


def _keys(host_id, settings):
    # Every host has one cluster hash slot; clouds sharing Redis remain isolated.
    scope = json.dumps([settings.os_auth_url, settings.os_region_name, settings.os_project_name, host_id])
    digest = hashlib.sha256(scope.encode()).hexdigest()
    base = f"afterglow:infra:{{{digest}}}"
    return {suffix: f"{base}:{suffix}" for suffix in ("observation", "watermark", "job", "traces", "poll", "submit")}


def _enabled(settings):
    if not settings.monitoring_infrastructure_topology_enabled:
        raise HTTPException(503, "topology_disabled")


async def redis_client():
    try:
        return await _get_redis()
    except Exception:
        raise HTTPException(503, "topology_store_unavailable") from None


async def _redis_call(client, method, *args, **kwargs):
    try:
        return await getattr(client, method)(*args, **kwargs)
    except Exception:
        raise HTTPException(503, "topology_store_unavailable") from None


def authenticate_observer(host_id: str, authorization: str | None, *, settings=None):
    settings = settings or get_settings()
    _enabled(settings)
    supplied = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if len(supplied) > 256:
        supplied = ""  # Oversized credentials fail like wrong ones, never as echoed validation input.
    matched = None
    # Do not reveal configured host existence. Every credential is compared.
    for identity in settings.monitoring_infrastructure_topology_observers:
        if hmac.compare_digest(identity.token.get_secret_value().encode(), supplied.encode()):
            matched = identity.host_id
    if matched != host_id:
        raise HTTPException(401, "observer_unauthorized")
    return settings


def peer_targets(host_id, settings):
    return [
        peer.model_dump(exclude={"source_host_id"})
        for peer in settings.monitoring_infrastructure_topology_peer_targets
        if peer.source_host_id == host_id
    ]


def projected_peers(host_id, observation, settings, clock):
    measured = (
        {(peer["target_host_id"], peer["address"], peer["port"]): peer for peer in observation.get("peer_probes", [])}
        if observation
        else {}
    )
    result = []
    for target in peer_targets(host_id, settings):
        probe = measured.get((target["target_host_id"], target["address"], target["port"]))
        if probe is None:
            result.append(
                {**target, "status": "unknown", "checked_at": None, "latency_ms": None, "error": "probe_unmeasured"}
            )
        elif not 0 <= clock - probe["checked_at"] <= STALE_SECONDS:
            result.append({**probe, "status": "unknown", "latency_ms": None, "error": "probe_stale"})
        else:
            result.append(dict(probe))
    return result


def enrich_observation(report: Observation, old: dict | None):
    current = report.model_dump()
    prior_interfaces = {item["name"]: item for item in old["interfaces"]} if old else {}
    elapsed = current["captured_at"] - old["captured_at"] if old else 0
    for interface in current["interfaces"]:
        prior = prior_interfaces.get(interface["name"])
        measurable = bool(
            prior
            and old["boot_id"] == current["boot_id"]
            and 5 <= elapsed <= STALE_SECONDS
            and prior["mac"] == interface["mac"]
            and prior["ifindex"] == interface["ifindex"]
            and old["sources"]["counters"] == "measured"
            and current["sources"]["counters"] == "measured"
        )
        rates = {
            key: (interface[key] - prior[key]) / elapsed
            if measurable and interface[key] is not None and prior[key] is not None and interface[key] >= prior[key]
            else None
            for key in COUNTERS
        }
        interface["rates"] = rates
        interface["history"] = [
            *(prior.get("history", []) if prior else []),
            {"ts": current["captured_at"], "rates": rates},
        ][-RETENTION_SAMPLES:]
    return current


async def ingest(host_id, report: Observation, *, settings=None, redis=None, now=None):
    settings = settings or get_settings()
    _enabled(settings)
    clock = time.time() if now is None else now
    if not -5 <= clock - report.captured_at <= STALE_SECONDS:
        raise HTTPException(409, "observation_time_invalid")
    allowed = {(peer["target_host_id"], peer["address"], peer["port"]) for peer in peer_targets(host_id, settings)}
    for probe in report.peer_probes:
        if (probe.target_host_id, probe.address, probe.port) not in allowed:
            raise HTTPException(422, "peer_target_not_allowed")
        if not -5 <= clock - probe.checked_at <= STALE_SECONDS or probe.checked_at > report.captured_at + 5:
            raise HTTPException(409, "peer_probe_time_invalid")
    redis = redis if redis is not None else await redis_client()
    keys = _keys(host_id, settings)
    raw = _text(await _redis_call(redis, "get", keys["observation"])) or ""
    old = json.loads(raw) if raw else None
    previous_peers = (
        {
            (peer["target_host_id"], peer["address"], peer["port"]): peer["checked_at"]
            for peer in old.get("peer_probes", [])
        }
        if old
        else {}
    )
    for probe in report.peer_probes:
        previous = previous_peers.get((probe.target_host_id, probe.address, probe.port))
        if previous is not None and probe.checked_at <= previous:
            raise HTTPException(409, "peer_probe_replayed_or_out_of_order")
    enriched = enrich_observation(report, old)
    cutoff = report.captured_at - settings.monitoring_infrastructure_topology_retention_seconds
    for interface in enriched["interfaces"]:
        interface["history"] = [point for point in interface["history"] if point["ts"] >= cutoff]
    status = await _redis_call(
        redis,
        "eval",
        _STORE_REPORT,
        2,
        keys["observation"],
        keys["watermark"],
        raw,
        repr(report.captured_at),
        json.dumps(enriched, separators=(",", ":")),
        settings.monitoring_infrastructure_topology_retention_seconds,
    )
    if status != 1:
        raise HTTPException(
            429 if status == -2 else 409,
            "observation_rate_limited" if status == -2 else "observation_replayed_or_superseded",
        )
    return {"accepted": True, "captured_at": report.captured_at}


async def submit_trace(host_id, target, *, settings=None, redis=None, now=None):
    settings = settings or get_settings()
    _enabled(settings)
    if host_id not in {identity.host_id for identity in settings.monitoring_infrastructure_topology_observers}:
        raise HTTPException(404, "observer_not_configured")
    if target not in settings.monitoring_infrastructure_topology_trace_targets:
        raise HTTPException(422, "trace_target_not_allowed")
    clock = time.time() if now is None else now
    job = {
        "id": str(uuid.uuid4()),
        "target": target,
        "max_hops": 16,
        "timeout_seconds": 40,
        "status": "queued",
        "created_at": clock,
        "expires_at": clock + 90,
        "result": None,
    }
    redis = redis if redis is not None else await redis_client()
    keys = _keys(host_id, settings)
    status = await _redis_call(
        redis,
        "eval",
        _ENQUEUE,
        3,
        keys["job"],
        keys["traces"],
        keys["submit"],
        clock,
        json.dumps(job),
        settings.monitoring_infrastructure_topology_retention_seconds,
    )
    if status != 1:
        raise HTTPException(
            429 if status == -1 else 409, "trace_rate_limited" if status == -1 else "trace_already_active"
        )
    return job


async def poll_job(host_id, *, claim=True, settings=None, redis=None, now=None):
    """Refresh peer admission; busy observers opt out of claiming a trace."""
    settings = settings or get_settings()
    _enabled(settings)
    redis = redis if redis is not None else await redis_client()
    keys = _keys(host_id, settings)
    clock = time.time() if now is None else now
    if not await _redis_call(redis, "set", keys["poll"], "1", nx=True, ex=5):
        raise HTTPException(429, "observer_poll_rate_limited")
    if not claim:
        return {"job": None, "peer_targets": peer_targets(host_id, settings)}
    raw = _text(await _redis_call(redis, "get", keys["job"]))
    job = json.loads(raw) if raw else None
    if job is None or job["status"] != "queued" or job["expires_at"] <= clock:
        job = None
    else:
        job = {**job, "status": "running", "claimed_at": clock}
        if (
            await _redis_call(redis, "eval", _REPLACE_JOB, 2, keys["job"], keys["traces"], raw, json.dumps(job), "")
            != 1
        ):
            job = None  # A concurrent poll claimed or replaced it first.
    public = {key: job[key] for key in JOB_FIELDS} if job else None
    return {"job": public, "peer_targets": peer_targets(host_id, settings)}


async def finish_trace(host_id, job_id, result: TraceResult, *, settings=None, redis=None, now=None):
    settings = settings or get_settings()
    _enabled(settings)
    redis = redis if redis is not None else await redis_client()
    clock = time.time() if now is None else now
    keys = _keys(host_id, settings)
    raw = _text(await _redis_call(redis, "get", keys["job"]))
    if not raw:
        raise HTTPException(409, "trace_not_active")
    job = json.loads(raw)
    if job["id"] != job_id or job["status"] != "running" or job["expires_at"] <= clock:
        raise HTTPException(409, "trace_not_active")
    if job["target"] not in settings.monitoring_infrastructure_topology_trace_targets:
        raise HTTPException(409, "trace_target_revoked")
    if not max(job["claimed_at"] - 5, clock - 30) <= result.completed_at <= clock + 5:
        raise HTTPException(409, "trace_result_time_invalid")
    # A target may answer with !X/!H, or appear in partial failed-command output.
    # Its presence is not proof of success; only positive claims need matching
    # completed, timed terminal evidence.
    if result.reached and not (
        result.status == "complete"
        and result.hops
        and result.hops[-1].ip == job["target"]
        and result.hops[-1].rtt_ms is not None
    ):
        raise HTTPException(422, "trace_reached_mismatch")
    updated = json.dumps({**job, "status": result.status, "result": result.model_dump()})
    status = await _redis_call(redis, "eval", _REPLACE_JOB, 2, keys["job"], keys["traces"], raw, updated, job_id)
    if status != 1:
        raise HTTPException(409, "trace_result_replayed_or_expired")
    return {"accepted": True}


def _configured_host(identity):
    role, name = identity.host_id.split(":", 1)
    return {
        "id": identity.host_id,
        "name": name,
        "role": role,
        "address": None,
        "reachability": {"status": "unknown", "checked_at": None, "latency_ms": None, "error": None},
        "heartbeat": {"status": "unknown", "updated_at": None, "source": None},
    }


async def snapshot(*, settings=None, redis=None, now=None):
    settings = settings or get_settings()
    result = {
        "enabled": settings.monitoring_infrastructure_topology_enabled,
        "error": None,
        "inventory_error": None,
        "interval_seconds": INTERVAL_SECONDS,
        "trace_targets": settings.monitoring_infrastructure_topology_trace_targets,
        "hosts": [],
    }
    if not result["enabled"]:
        result["error"] = "topology_disabled"
        return result
    clock = time.time() if now is None else now
    health = await host_health.get_snapshot(settings=settings, redis=redis, now=clock)
    inventory = {
        host["id"]: {key: host[key] for key in ("id", "name", "role", "address", "reachability", "heartbeat")}
        for host in health["hosts"]
    }
    for identity in settings.monitoring_infrastructure_topology_observers:
        inventory.setdefault(identity.host_id, _configured_host(identity))
    result["inventory_error"] = health["error"]
    # Inventory is bounded independently of the upstream discovery implementation.
    if len(inventory) > 256:
        result["inventory_error"] = "inventory_truncated"
    configured = {identity.host_id for identity in settings.monitoring_infrastructure_topology_observers}
    hosts = [inventory[key] for key in sorted(inventory, key=lambda key: (key not in configured, key))[:256]]
    for host in hosts:
        host["observer_configured"] = host["id"] in configured
        host["peer_probes"] = projected_peers(host["id"], None, settings, clock)
    try:
        redis = redis if redis is not None else await redis_client()
        for host in hosts:
            host.update(observation=None, observation_state="unmeasured", traces=[])
            if host["id"] not in configured:
                continue
            keys = _keys(host["id"], settings)
            raw = await _redis_call(redis, "get", keys["observation"])
            if raw:
                observation = json.loads(raw)
                stale = not 0 <= clock - observation["captured_at"] <= STALE_SECONDS
                host["observation"] = observation
                host["observation_state"] = "stale" if stale else "fresh"
                if stale:
                    for interface in observation["interfaces"]:
                        interface["rates"] = dict.fromkeys(COUNTERS)
            host["peer_probes"] = projected_peers(host["id"], host["observation"], settings, clock)
            active_raw = await _redis_call(redis, "get", keys["job"])
            active = json.loads(active_raw) if active_raw else None
            for raw_trace in await _redis_call(redis, "lrange", keys["traces"], 0, 19):
                trace = json.loads(raw_trace)
                if clock - trace["created_at"] > settings.monitoring_infrastructure_topology_retention_seconds:
                    continue
                # History entries originally queued are overlaid by the active lease state.
                if active and active["id"] == trace["id"]:
                    trace = active
                if trace["status"] in {"queued", "running"} and trace["expires_at"] <= clock:
                    trace["status"] = "expired"
                host["traces"].append(trace)
    except HTTPException:
        result["error"] = "topology_store_unavailable"
        for host in hosts:
            host.update(observation=None, observation_state="unmeasured", traces=[])
            host["peer_probes"] = projected_peers(host["id"], None, settings, clock)
    except (ValueError, TypeError, KeyError):
        result["error"] = "topology_store_invalid"
        for host in hosts:
            host.update(observation=None, observation_state="unmeasured", traces=[])
            host["peer_probes"] = projected_peers(host["id"], None, settings, clock)
    result["hosts"] = hosts
    return result
