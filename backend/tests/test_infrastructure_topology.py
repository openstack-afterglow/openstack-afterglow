"""Behavioral protocol/ownership/rate/history/lease regressions; no network scanning."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from app.api.monitoring.host_observations import MAX_BODY_BYTES, HostObservationBodyLimit, router
from app.models.infrastructure_topology import (
    HostObserverIdentity,
    HostPeerProbeTarget,
    Observation,
    PeerProbe,
    TraceRequest,
    TraceResult,
    validate_topology_settings,
)
from app.services import infrastructure_topology as topology
from app.services.cache import _get_redis

HOST = "compute:cmp-1"
TOKEN = "a" * 48


def settings():
    return SimpleNamespace(
        monitoring_infrastructure_topology_enabled=True,
        monitoring_infrastructure_topology_observers=[HostObserverIdentity(host_id=HOST, token=TOKEN)],
        monitoring_infrastructure_topology_trace_targets=["1.1.1.1", "10.0.0.2"],
        monitoring_infrastructure_topology_retention_seconds=3600,
        monitoring_infrastructure_topology_peer_targets=[],
        monitoring_host_healthcheck_enabled=False,
        monitoring_host_healthcheck_targets=[],
        os_auth_url="https://keystone.example/v3",
        os_region_name="RegionOne",
        os_project_name="admin",
    )


def observation(ts=1000, counter=100, boot="boot-a"):
    return Observation(
        captured_at=ts,
        boot_id=boot,
        interfaces=[
            dict(
                name="eth0",
                mac="00:11:22:33:44:55",
                ifindex=2,
                operstate="UP",
                addresses=["10.0.0.11/24"],
                **dict.fromkeys(topology.COUNTERS, counter),
            )
        ],
        neighbors=[dict(interface="eth0", ip="10.0.0.2", mac="00:11:22:33:44:66", state="REACHABLE")],
        routes=[dict(interface="eth0", destination="default", gateway="10.0.0.2")],
        lldp=[],
        sources=dict.fromkeys(("addresses", "neighbors", "routes", "lldp", "counters"), "measured"),
    )


def test_counter_rates_first_reset_gap_boot_and_partial_counters_are_honest():
    first = topology.enrich_observation(observation(), None)
    assert set(first["interfaces"][0]["rates"].values()) == {None}
    second = topology.enrich_observation(observation(1010, 200), first)
    assert second["interfaces"][0]["rates"] == dict.fromkeys(topology.COUNTERS, 10)
    assert len(second["interfaces"][0]["history"]) == 2
    for report in (observation(1020, 1), observation(1050, 300), observation(1020, 300, "boot-b")):
        assert set(topology.enrich_observation(report, second)["interfaces"][0]["rates"].values()) == {None}
    partial = observation(1020, 300)
    partial.interfaces[0].rx_packets = None
    result = topology.enrich_observation(partial, second)["interfaces"][0]["rates"]
    assert result["rx_packets"] is None and result["rx_bytes"] == 10


def test_config_token_uniqueness_exact_host_binding_and_no_secret_repr():
    config = settings()
    assert TOKEN not in repr(config.monitoring_infrastructure_topology_observers[0])
    assert topology.authenticate_observer(HOST, "Bearer " + TOKEN, settings=config) is config
    for host, auth in (("storage:cmp-1", "Bearer " + TOKEN), (HOST, None), (HOST, "Bearer wrong")):
        with pytest.raises(HTTPException) as exc:
            topology.authenticate_observer(host, auth, settings=config)
        assert exc.value.status_code == 401
    config.monitoring_infrastructure_topology_observers.append(
        HostObserverIdentity(host_id="storage:st-1", token=TOKEN)
    )
    with pytest.raises(ValueError, match="unique"):
        validate_topology_settings(config)


@pytest.mark.parametrize(
    "target", ["example.com", "1.1.1.0/24", "--help", "127.0.0.1", "169.254.169.254", "::1", "ff02::1", "fe80::1%eth0"]
)
def test_traceroute_rejects_dns_cidr_scoped_and_non_unicast_targets(target):
    with pytest.raises(ValidationError):
        TraceRequest(target=target)


def test_report_cardinality_and_interface_ownership():
    payload = observation().model_dump()
    payload["neighbors"][0]["interface"] = "eth-other"
    with pytest.raises(ValidationError, match="reported interface"):
        Observation.model_validate(payload)
    payload = observation().model_dump()
    payload["interfaces"] *= 65
    with pytest.raises(ValidationError):
        Observation.model_validate(payload)


@pytest.mark.asyncio
async def test_atomic_report_replay_out_of_order_rate_and_ttl():
    redis = await _get_redis()
    config = settings()
    await topology.ingest(HOST, observation(), settings=config, redis=redis, now=1000)
    for report, clock, status in (
        (observation(), 1000, 409),
        (observation(999), 1000, 409),
        (observation(1001), 1001, 429),
        (observation(900), 1000, 409),
    ):
        with pytest.raises(HTTPException) as exc:
            await topology.ingest(HOST, report, settings=config, redis=redis, now=clock)
        assert exc.value.status_code == status
    competing = await asyncio.gather(
        topology.ingest(HOST, observation(1010, 200), settings=config, redis=redis, now=1010),
        topology.ingest(HOST, observation(1010, 300), settings=config, redis=redis, now=1010),
        return_exceptions=True,
    )
    assert sum(isinstance(value, dict) for value in competing) == 1
    stored = json.loads(await redis.get(topology._keys(HOST, config)["observation"]))
    assert stored["captured_at"] == 1010
    assert len(stored["interfaces"][0]["history"]) == 2
    assert 0 < await redis.ttl(topology._keys(HOST, config)["watermark"]) <= 3600


@pytest.mark.asyncio
async def test_single_target_single_claim_result_replay_and_expiry():
    redis = await _get_redis()
    config = settings()
    with pytest.raises(HTTPException) as exc:
        await topology.submit_trace(HOST, "8.8.8.8", settings=config, redis=redis, now=1000)
    assert exc.value.status_code == 422
    job = await topology.submit_trace(HOST, "1.1.1.1", settings=config, redis=redis, now=1000)
    assert job["max_hops"] == 16 and job["timeout_seconds"] == 40
    with pytest.raises(HTTPException) as exc:
        await topology.submit_trace(HOST, "10.0.0.2", settings=config, redis=redis, now=1001)
    assert exc.value.status_code == 409
    claimed = (await topology.poll_job(HOST, settings=config, redis=redis, now=1005))["job"]
    assert claimed["id"] == job["id"] and claimed["status"] == "running"
    with pytest.raises(HTTPException) as exc:
        await topology.poll_job(HOST, settings=config, redis=redis, now=1006)
    assert exc.value.status_code == 429
    result = TraceResult(
        status="complete",
        completed_at=1010,
        reached=True,
        source_interface="eth0",
        next_hop="10.0.0.2",
        hops=[
            dict(hop=1, ip="10.0.0.2", rtt_ms=0.5),
            dict(hop=2, ip=None, rtt_ms=None),
            dict(hop=3, ip="1.1.1.1", rtt_ms=3.7),
        ],
    )
    assert await topology.finish_trace(HOST, job["id"], result, settings=config, redis=redis, now=1010) == {
        "accepted": True
    }
    with pytest.raises(HTTPException) as exc:
        await topology.finish_trace(HOST, job["id"], result, settings=config, redis=redis, now=1011)
    assert exc.value.status_code == 409
    # Test clock and Redis expiry clock are independent; release the cooldown explicitly.
    await redis.delete(topology._keys(HOST, config)["submit"])
    other = await topology.submit_trace(HOST, "10.0.0.2", settings=config, redis=redis, now=1100)
    await redis.delete(topology._keys(HOST, config)["poll"])
    await topology.poll_job(HOST, settings=config, redis=redis, now=1101)
    with pytest.raises(HTTPException) as exc:
        await topology.finish_trace(HOST, other["id"], result, settings=config, redis=redis, now=1200)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_stale_snapshot_preserves_evidence_but_hides_current_rate(monkeypatch):
    redis = await _get_redis()
    config = settings()
    await topology.ingest(HOST, observation(), settings=config, redis=redis, now=1000)
    await topology.ingest(HOST, observation(1010, 200), settings=config, redis=redis, now=1010)
    monkeypatch.setattr(topology.host_health, "get_snapshot", AsyncMock(return_value={"hosts": [], "error": None}))
    fresh = await topology.snapshot(settings=config, redis=redis, now=1011)
    host = fresh["hosts"][0]
    assert host["observation_state"] == "fresh" and host["observation"]["interfaces"][0]["rates"]["tx_packets"] == 10
    assert host["observation"]["lldp"] == []  # Neighbor/route evidence never generates physical links.
    stale = (await topology.snapshot(settings=config, redis=redis, now=1041))["hosts"][0]
    assert stale["observation_state"] == "stale"
    assert set(stale["observation"]["interfaces"][0]["rates"].values()) == {None}
    assert stale["observation"]["neighbors"][0]["ip"] == "10.0.0.2"
    assert stale["observation"]["interfaces"][0]["history"][-1]["rates"]["rx_bytes"] == 10


@pytest.mark.asyncio
async def test_observer_http_auth_cross_host_and_chunked_limit(monkeypatch):
    config = settings()
    monkeypatch.setattr(topology, "get_settings", lambda: config)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/monitoring")
    app.add_middleware(HostObservationBodyLimit)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        path = "/api/v1/monitoring/host-observations/"
        response = await client.post(path + HOST + "/reports", json=observation().model_dump())
        assert response.status_code == 401
        response = await client.post(
            path + "storage:st-1/reports", json=observation().model_dump(), headers={"Authorization": "Bearer " + TOKEN}
        )
        assert response.status_code == 401

        async def chunks():
            yield b" " * (MAX_BODY_BYTES // 2)
            yield b" " * (MAX_BODY_BYTES // 2 + 1)

        response = await client.post(
            path + HOST + "/reports", content=chunks(), headers={"Authorization": "Bearer " + TOKEN}
        )
        assert response.status_code == 413


@pytest.mark.asyncio
async def test_admin_routes_deny_non_admin(non_admin_client):
    base = "/api/v1/admin/infrastructure-topology"
    assert (await non_admin_client.get(base)).status_code == 403
    assert (
        await non_admin_client.post(base + "/hosts/" + HOST + "/traces", json={"target": "1.1.1.1"})
    ).status_code == 403


@pytest.mark.asyncio
async def test_redis_failure_is_explicit_not_an_empty_healthy_graph(monkeypatch):
    monkeypatch.setattr(topology.host_health, "get_snapshot", AsyncMock(return_value={"hosts": [], "error": None}))
    redis = AsyncMock()
    redis.get.side_effect = ConnectionError("private redis token")
    result = await topology.snapshot(settings=settings(), redis=redis, now=1000)
    assert result["error"] == "topology_store_unavailable"
    assert result["hosts"][0]["observation_state"] == "unmeasured"
    assert "private" not in json.dumps(result)


@pytest.mark.asyncio
async def test_http_observer_report_admin_map_job_poll_and_result_roundtrip(monkeypatch):
    from app.api.deps import require_admin
    from app.api.identity.admin_infrastructure_topology import router as admin_router

    config = settings()
    clock = {"now": 1000.0}
    monkeypatch.setattr(topology, "get_settings", lambda: config)
    monkeypatch.setattr(topology.time, "time", lambda: clock["now"])
    monkeypatch.setattr(topology.host_health, "get_snapshot", AsyncMock(return_value={"hosts": [], "error": None}))
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/monitoring")
    app.include_router(admin_router, prefix="/api/v1/admin")
    app.dependency_overrides[require_admin] = lambda: {"user_id": "fixture-admin"}
    app.add_middleware(HostObservationBodyLimit)
    headers = {"Authorization": "Bearer " + TOKEN}
    observer_base = "/api/v1/monitoring/host-observations/" + HOST
    admin_base = "/api/v1/admin/infrastructure-topology"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(observer_base + "/reports", json=observation().model_dump(), headers=headers)
        assert response.status_code == 202 and response.headers["cache-control"] == "no-store"
        snapshot = (await client.get(admin_base)).json()
        assert snapshot["hosts"][0]["observation_state"] == "fresh"
        assert snapshot["hosts"][0]["observation"]["routes"][0]["gateway"] == "10.0.0.2"
        response = await client.post(admin_base + "/hosts/" + HOST + "/traces", json={"target": "1.1.1.1"})
        assert response.status_code == 202
        job_id = response.json()["id"]
        clock["now"] = 1005.0
        job = (await client.get(observer_base + "/jobs", headers=headers)).json()["job"]
        assert job["id"] == job_id and job["status"] == "running"
        clock["now"] = 1006.0
        result = {
            "status": "complete",
            "completed_at": 1006,
            "reached": False,
            "hops": [{"hop": 1, "ip": "10.0.0.2", "rtt_ms": 0.3}, {"hop": 2, "ip": None, "rtt_ms": None}],
        }
        response = await client.post(observer_base + "/jobs/" + job_id + "/result", json=result, headers=headers)
        assert response.status_code == 202
        trace = (await client.get(admin_base)).json()["hosts"][0]["traces"][0]
        assert trace["status"] == "complete" and trace["result"]["reached"] is False
        assert trace["result"]["hops"][1] == {"hop": 2, "ip": None, "rtt_ms": None}


def test_unknown_gaps_cannot_be_omitted_or_given_fake_rtt():
    for hops in ([{"hop": 2, "ip": "10.0.0.2", "rtt_ms": 1}], [{"hop": 1, "ip": None, "rtt_ms": 1}]):
        with pytest.raises(ValidationError):
            TraceResult(status="complete", completed_at=1000, reached=False, hops=hops)


@pytest.mark.asyncio
async def test_history_bound_and_ttl_retention(monkeypatch):
    redis = await _get_redis()
    config = settings()
    config.monitoring_infrastructure_topology_retention_seconds = 300
    for index in range(65):
        await topology.ingest(
            HOST, observation(1000 + index * 10, 100 + index * 100), settings=config, redis=redis, now=1000 + index * 10
        )
    stored = json.loads(await redis.get(topology._keys(HOST, config)["observation"]))
    history = stored["interfaces"][0]["history"]
    assert len(history) <= topology.RETENTION_SAMPLES
    assert history[0]["ts"] >= stored["captured_at"] - 300
    assert history[-1]["rates"]["rx_bytes"] == 10
    assert 0 < await redis.ttl(topology._keys(HOST, config)["observation"]) <= 300


@pytest.mark.asyncio
async def test_peer_targets_are_source_owned_exact_literal_tuples_and_unknown_when_stale(monkeypatch):
    redis = await _get_redis()
    config = settings()
    config.monitoring_infrastructure_topology_peer_targets = [
        HostPeerProbeTarget(source_host_id=HOST, target_host_id="storage:st-1", address="10.0.0.21", port=9100)
    ]
    assert validate_topology_settings(config) is config
    allowed = (await topology.poll_job(HOST, settings=config, redis=redis, now=1000))["peer_targets"]
    assert allowed == [{"target_host_id": "storage:st-1", "address": "10.0.0.21", "port": 9100}]
    assert topology.peer_targets("storage:st-1", config) == []  # Directed only; no reversed probe.
    report = observation()
    report.sources.peer_probes = "measured"
    report.peer_probes = [
        PeerProbe(
            target_host_id="storage:st-1", address="10.0.0.22", port=9100, status="up", checked_at=1000, latency_ms=1
        )
    ]
    with pytest.raises(HTTPException) as exc:
        await topology.ingest(HOST, report, settings=config, redis=redis, now=1000)
    assert exc.value.detail == "peer_target_not_allowed"
    report.peer_probes[0].address = "10.0.0.21"
    report.peer_probes[0].port = 22
    with pytest.raises(HTTPException) as exc:
        await topology.ingest(HOST, report, settings=config, redis=redis, now=1000)
    assert exc.value.detail == "peer_target_not_allowed"
    report.peer_probes[0].port = 9100
    report.peer_probes[0].checked_at = 900
    with pytest.raises(HTTPException) as exc:
        await topology.ingest(HOST, report, settings=config, redis=redis, now=1000)
    assert exc.value.detail == "peer_probe_time_invalid"
    report.peer_probes[0].checked_at = 1000
    await topology.ingest(HOST, report, settings=config, redis=redis, now=1000)
    monkeypatch.setattr(topology.host_health, "get_snapshot", AsyncMock(return_value={"hosts": [], "error": None}))
    snapshot = await topology.snapshot(settings=config, redis=redis, now=1001)
    probe = snapshot["hosts"][0]["peer_probes"][0]
    assert probe["status"] == "up" and probe["latency_ms"] == 1
    stale = (await topology.snapshot(settings=config, redis=redis, now=1031))["hosts"][0]["peer_probes"][0]
    assert stale["status"] == "unknown" and stale["latency_ms"] is None and stale["error"] == "probe_stale"
    assert stale["checked_at"] == 1000


def test_peer_probe_source_and_status_do_not_fabricate_reachability():
    config = settings()
    target = dict(source_host_id="storage:other", target_host_id=HOST, address="10.0.0.21", port=9100)
    config.monitoring_infrastructure_topology_peer_targets = [HostPeerProbeTarget(**target)]
    with pytest.raises(ValueError, match="observer source"):
        validate_topology_settings(config)
    for status, latency, error in (
        ("up", None, None),
        ("unknown", None, "timeout"),
        ("down", None, "source_unavailable"),
    ):
        with pytest.raises(ValidationError):
            PeerProbe(
                target_host_id="storage:st-1",
                address="10.0.0.21",
                port=9100,
                status=status,
                checked_at=1000,
                latency_ms=latency,
                error=error,
            )
    unknown = topology.projected_peers(HOST, None, settings(), 1000)
    assert unknown == []


def test_invalid_operator_token_is_not_in_validation_exception():
    secret = "sensitive operator token with spaces"
    with pytest.raises(ValidationError) as exc:
        HostObserverIdentity(host_id=HOST, token=secret)
    assert secret not in str(exc.value)


@pytest.mark.asyncio
async def test_peer_measurement_replay_cannot_refresh_a_new_report():
    redis = await _get_redis()
    config = settings()
    config.monitoring_infrastructure_topology_peer_targets = [
        HostPeerProbeTarget(source_host_id=HOST, target_host_id="storage:st-1", address="10.0.0.21", port=9100)
    ]
    report = observation()
    report.sources.peer_probes = "measured"
    report.peer_probes = [
        PeerProbe(
            target_host_id="storage:st-1", address="10.0.0.21", port=9100, status="up", checked_at=1000, latency_ms=1
        )
    ]
    await topology.ingest(HOST, report, settings=config, redis=redis, now=1000)
    report.captured_at = 1010
    with pytest.raises(HTTPException) as exc:
        await topology.ingest(HOST, report, settings=config, redis=redis, now=1010)
    assert exc.value.detail == "peer_probe_replayed_or_out_of_order"


@pytest.mark.asyncio
async def test_observer_evidence_survives_partial_health_inventory(monkeypatch):
    redis = await _get_redis()
    config = settings()
    monkeypatch.setattr(
        topology.host_health, "get_snapshot", AsyncMock(return_value={"hosts": [], "error": "snapshot_stale"})
    )
    await topology.ingest(HOST, observation(), settings=config, redis=redis, now=1000)
    await topology.ingest(HOST, observation(1010, 200), settings=config, redis=redis, now=1010)
    snapshot = await topology.snapshot(settings=config, redis=redis, now=1011)
    assert snapshot["error"] is None and snapshot["inventory_error"] == "snapshot_stale"
    host = snapshot["hosts"][0]
    assert host["reachability"]["status"] == "unknown"
    assert host["observation_state"] == "fresh" and host["observation"]["interfaces"][0]["rates"]["rx_bytes"] == 10


def test_topology_keys_isolate_clouds_and_share_one_slot_per_host():
    cloud_a, cloud_b = settings(), settings()
    cloud_b.os_region_name = "RegionTwo"
    keys = topology._keys(HOST, cloud_a)
    assert keys != topology._keys(HOST, cloud_b)
    assert len({key.split("{", 1)[1].split("}", 1)[0] for key in keys.values()}) == 1


def test_long_inventory_names_and_local_probe_errors_are_honest():
    name = "h" * 253
    identity = HostObserverIdentity(host_id="storage:" + name, token=TOKEN)
    assert identity.host_id == "storage:" + name
    with pytest.raises(ValidationError):
        HostObserverIdentity(host_id="storage:" + name + "h", token=TOKEN)
    probe = PeerProbe(
        target_host_id="storage:st-1",
        address="10.0.0.21",
        port=9100,
        status="unknown",
        checked_at=1000,
        error="probe_error",
    )
    assert probe.status == "unknown" and probe.latency_ms is None
    with pytest.raises(ValidationError):
        PeerProbe(
            target_host_id="storage:st-1",
            address="10.0.0.21",
            port=9100,
            status="down",
            checked_at=1000,
            error="probe_error",
        )


@pytest.mark.asyncio
async def test_busy_http_poll_refreshes_peers_without_claiming_and_keeps_rate_limit(monkeypatch):
    config = settings()
    config.monitoring_infrastructure_topology_peer_targets = [
        HostPeerProbeTarget(source_host_id=HOST, target_host_id="storage:st-1", address="10.0.0.21", port=9100),
        HostPeerProbeTarget(source_host_id="storage:st-1", target_host_id=HOST, address="10.0.0.11", port=9100),
    ]
    redis = await _get_redis()
    submitted = await topology.submit_trace(HOST, "1.1.1.1", settings=config, redis=redis, now=1000)
    keys = topology._keys(HOST, config)
    queued = await redis.get(keys["job"])
    history = await redis.lrange(keys["traces"], 0, -1)
    clock = {"now": 1001.0}
    monkeypatch.setattr(topology, "get_settings", lambda: config)
    monkeypatch.setattr(topology.time, "time", lambda: clock["now"])
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/monitoring")
    path = "/api/v1/monitoring/host-observations/" + HOST + "/jobs"
    headers = {"Authorization": "Bearer " + TOKEN}
    expected_peers = [{"target_host_id": "storage:st-1", "address": "10.0.0.21", "port": 9100}]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(path + "?claim=false")).status_code == 401
        response = await client.get(path + "?claim=false", headers=headers)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert response.json() == {"job": None, "peer_targets": expected_peers}
        assert await redis.get(keys["job"]) == queued
        assert await redis.lrange(keys["traces"], 0, -1) == history
        assert json.loads(queued)["status"] == "queued" and "claimed_at" not in json.loads(queued)
        for suffix in ("?claim=false", ""):
            limited = await client.get(path + suffix, headers=headers)
            assert limited.status_code == 429 and limited.json()["detail"] == "observer_poll_rate_limited"
        assert await redis.get(keys["job"]) == queued
        # Redis TTL time is independent of the service clock; release cooldown.
        await redis.delete(keys["poll"])
        clock["now"] = 1006.0
        response = await client.get(path, headers=headers)  # Default still claims.
        assert response.status_code == 200 and response.json()["peer_targets"] == expected_peers
        assert response.json()["job"]["id"] == submitted["id"]
        assert response.json()["job"]["status"] == "running"
        claimed = json.loads(await redis.get(keys["job"]))
        assert claimed["claimed_at"] == 1006 and claimed["result"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hops",
    [
        [{"hop": 1, "ip": "10.0.0.2", "rtt_ms": 0.5}],
        [{"hop": 1, "ip": "1.1.1.1", "rtt_ms": None}],
        [{"hop": 1, "ip": "1.1.1.1", "rtt_ms": 0.5}, {"hop": 2, "ip": None, "rtt_ms": None}],
    ],
)
async def test_positive_reachability_requires_timed_terminal_target_and_does_not_poison_job(hops):
    config = settings()
    redis = await _get_redis()
    submitted = await topology.submit_trace(HOST, "1.1.1.1", settings=config, redis=redis, now=1000)
    await topology.poll_job(HOST, settings=config, redis=redis, now=1001)
    keys = topology._keys(HOST, config)
    running = await redis.get(keys["job"])
    history = await redis.lrange(keys["traces"], 0, -1)
    invalid = TraceResult(status="complete", completed_at=1002, reached=True, hops=hops)
    with pytest.raises(HTTPException) as exc:
        await topology.finish_trace(HOST, submitted["id"], invalid, settings=config, redis=redis, now=1002)
    assert exc.value.status_code == 422 and exc.value.detail == "trace_reached_mismatch"
    assert await redis.get(keys["job"]) == running
    assert await redis.lrange(keys["traces"], 0, -1) == history
    valid = TraceResult(
        status="complete", completed_at=1003, reached=True, hops=[{"hop": 1, "ip": "1.1.1.1", "rtt_ms": 0.5}]
    )
    assert await topology.finish_trace(HOST, submitted["id"], valid, settings=config, redis=redis, now=1003) == {
        "accepted": True
    }
    assert json.loads(await redis.get(keys["job"]))["result"] == valid.model_dump()


@pytest.mark.asyncio
async def test_polled_job_has_only_the_public_collector_contract():
    config = settings()
    redis = await _get_redis()
    await topology.submit_trace(HOST, "1.1.1.1", settings=config, redis=redis, now=1000)
    job = (await topology.poll_job(HOST, settings=config, redis=redis, now=1001))["job"]
    assert set(job) == {"id", "target", "max_hops", "timeout_seconds", "status", "created_at", "expires_at"}
    private = json.loads(await redis.get(topology._keys(HOST, config)["job"]))
    assert private["claimed_at"] == 1001 and private["result"] is None


@pytest.mark.asyncio
async def test_unsupported_trace_keeps_empty_hops_array_and_exact_timestamps(monkeypatch):
    config = settings()
    redis = await _get_redis()
    await topology.submit_trace(HOST, "1.1.1.1", settings=config, redis=redis, now=1000.123456)
    job = (await topology.poll_job(HOST, settings=config, redis=redis, now=1001.654321))["job"]
    result = TraceResult(
        status="unsupported", hops=[], reached=False, error="traceroute_missing", completed_at=1002.987654
    )
    await topology.finish_trace(HOST, job["id"], result, settings=config, redis=redis, now=1003)
    monkeypatch.setattr(topology.host_health, "get_snapshot", AsyncMock(return_value={"hosts": [], "error": None}))
    trace = (await topology.snapshot(settings=config, redis=redis, now=1004))["hosts"][0]["traces"][0]
    assert trace["status"] == "unsupported" and trace["result"]["hops"] == []
    assert trace["created_at"] == 1000.123456 and trace["result"]["completed_at"] == 1002.987654


@pytest.mark.asyncio
async def test_oversized_observer_credential_is_unauthorized_without_echo(monkeypatch):
    config = settings()
    monkeypatch.setattr(topology, "get_settings", lambda: config)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/monitoring")
    secret = "s" * 400
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/monitoring/host-observations/" + HOST + "/jobs", headers={"Authorization": "Bearer " + secret}
        )
    assert response.status_code == 401 and secret not in response.text
    assert response.json()["detail"] == "observer_unauthorized"
