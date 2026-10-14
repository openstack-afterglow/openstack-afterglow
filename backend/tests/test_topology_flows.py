"""Header-counter ownership, uint64, adjacent rates and public redaction contracts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from app.api.monitoring.host_observations import HostObservationBodyLimit, router
from app.models.infrastructure_topology import HostObserverIdentity, Observation, validate_topology_settings
from app.services import infrastructure_topology as service
from app.services.cache import _get_redis

HOST = "compute:node-a"
PEER = "storage:node-b"
TOKEN = "a" * 48


def settings():
    return SimpleNamespace(
        monitoring_infrastructure_topology_enabled=True,
        monitoring_infrastructure_topology_observers=[
            HostObserverIdentity(host_id=HOST, token=TOKEN, addresses=["192.0.2.1", "2001:db8::1"]),
            HostObserverIdentity(host_id=PEER, token="b" * 48, addresses=["192.0.2.2"]),
        ],
        monitoring_infrastructure_topology_trace_targets=[],
        monitoring_infrastructure_topology_peer_targets=[],
        monitoring_infrastructure_topology_retention_seconds=3600,
        os_auth_url="https://keystone.example/v3",
        os_region_name="RegionOne",
        os_project_name="admin",
    )


def report(ts=1000, packets=2**63, octets=2**63, collector="instance-a", boot="boot-a", overflow=False):
    return Observation(
        captured_at=ts,
        boot_id=boot,
        interfaces=[{"name": "eth0", "ifindex": 2, "mac": "02:00:00:00:00:01", "physical": True}],
        neighbors=[],
        routes=[],
        lldp=[],
        sources={
            "addresses": "measured",
            "neighbors": "measured",
            "routes": "measured",
            "lldp": "unsupported",
            "counters": "unsupported",
            "flows": "error" if overflow else "measured",
        },
        flows={
            "collector_id": collector,
            "captured_at": ts,
            "overflow": overflow,
            "rows": [
                {
                    "source_host_id": HOST,
                    "target_host_id": PEER,
                    "interface": "eth0",
                    "direction": "egress",
                    "packets": str(packets),
                    "bytes": str(octets),
                },
            ],
        },
    )


def test_flow_uint64_delta_is_exact_above_javascript_integer_precision():
    first = service.enrich_observation(report(), None)
    assert first["flow_rates"][0]["reason"] == "first_sample"
    second = service.enrich_observation(report(1010, packets=2**63 + 10, octets=2**63 + 1000), first)
    flow = service.public_flows(HOST, second, 1010)[0]
    assert flow["packets_per_second"] == 1 and flow["bytes_per_second"] == 100
    assert flow["state"] == "fresh" and flow["reason"] is None and flow["window_seconds"] == 10
    assert not {"packets", "bytes", "collector_id"} & flow.keys()
    assert flow["measurement"] == "linux_skb_header_counter"
    assert service.public_flows(HOST, second, 1041)[0]["reason"] == "stale_sample"
    assert service.public_flows(HOST, second, 1041)[0]["packets_per_second"] is None


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"packets": 1}, "counter_reset"),
        ({"collector": "instance-b"}, "collector_reset"),
        ({"boot": "boot-b"}, "collector_reset"),
        ({"ts": 1040}, "stale_sample"),
        ({"overflow": True}, "overflow"),
    ],
)
def test_resets_overflow_and_gaps_are_unknown_not_zero(changes, reason):
    first = service.enrich_observation(report(), None)
    current = service.enrich_observation(report(**{"ts": 1010, **changes}), first)
    flow = service.public_flows(HOST, current, current["captured_at"])[0]
    assert flow["reason"] == reason and flow["packets_per_second"] is None and flow["bytes_per_second"] is None


def test_explicit_unchanged_adjacent_counters_measure_zero_and_ids_ignore_rates():
    first = service.enrich_observation(report(), None)
    second = service.enrich_observation(report(1010), first)
    row = service.public_flows(HOST, second, 1010)[0]
    assert row["state"] == "fresh" and row["packets_per_second"] == row["bytes_per_second"] == 0
    assert row["id"] == service.public_flows(HOST, first, 1000)[0]["id"]


@pytest.mark.parametrize("identity", [{"ifindex": 3}, {"mac": "02:00:00:00:00:02"}])
def test_replaced_physical_interface_never_inherits_peer_counter_delta(identity):
    first = service.enrich_observation(report(), None)
    value = report(1010, packets=2**63 + 10, octets=2**63 + 1000).model_dump()
    value["interfaces"][0].update(identity)
    second = service.enrich_observation(Observation.model_validate(value), first)
    flow = service.public_flows(HOST, second, 1010)[0]
    assert flow["packets_per_second"] is None and flow["bytes_per_second"] is None
    assert flow["window_seconds"] is None and flow["reason"] == "counter_reset"


@pytest.mark.parametrize(
    "identity", [{"ifindex": None}, {"mac": None}, {"mac": "not-a-mac"}, {"mac": "01:00:00:00:00:01"}]
)
def test_flow_requires_an_affirmative_physical_interface_identity(identity):
    value = report().model_dump()
    value["interfaces"][0].update(identity)
    with pytest.raises(ValidationError):
        Observation.model_validate(value)


def test_large_rates_are_unknown_and_source_error_recovery_needs_adjacent_valid_samples():
    first = service.enrich_observation(report(packets=0, octets=0), None)
    unsafe = service.enrich_observation(report(1010, packets=2**64 - 1, octets=2**64 - 1), first)
    assert unsafe["flow_rates"][0]["reason"] == "overflow"
    assert unsafe["flow_rates"][0]["packets_per_second"] is None
    error = report(1010)
    error.sources.flows = "error"
    failed = service.enrich_observation(error, first)
    recovered = service.enrich_observation(report(1020), failed)
    assert recovered["flow_rates"][0]["reason"] == "collector_error"
    assert recovered["flow_rates"][0]["packets_per_second"] is None
    adjacent = service.enrich_observation(report(1030), recovered)
    assert adjacent["flow_rates"][0]["packets_per_second"] == 0


def test_host_totals_never_supply_missing_peer_flow_evidence():
    value = report().model_dump()
    value["flows"] = None
    value["sources"]["flows"] = "unsupported"
    value["sources"]["counters"] = "measured"
    value["interfaces"][0].update(rx_packets=10000, tx_packets=20000, rx_bytes=100000, tx_bytes=200000)
    sample = service.enrich_observation(Observation.model_validate(value), None)
    assert service.public_flows(HOST, sample, 1000) == []


@pytest.mark.parametrize("counter", [-1, 1, True, "-1", "01", str(2**64), "1e3", "9" * 21])
def test_flow_counter_requires_bounded_canonical_decimal_string(counter):
    data = report().model_dump()
    data["flows"]["rows"][0]["packets"] = counter
    with pytest.raises(ValidationError):
        Observation.model_validate(data)


def test_duplicate_rows_dangling_interface_and_source_claims_rejected():
    for mutation in ("duplicate", "dangling", "unsupported", "missing", "hidden-overflow"):
        data = report().model_dump()
        if mutation == "duplicate":
            data["flows"]["rows"] *= 2
        elif mutation == "dangling":
            data["flows"]["rows"][0]["interface"] = "eth99"
        elif mutation == "unsupported":
            data["sources"]["flows"] = "unsupported"
        elif mutation == "missing":
            data["flows"] = None
        else:
            data["flows"]["overflow"] = True
        with pytest.raises(ValidationError):
            Observation.model_validate(data)


def test_registered_address_ownership_is_unique_across_ipv6_spellings():
    config = settings()
    config.monitoring_infrastructure_topology_observers[1].addresses = ["2001:db8::1"]
    with pytest.raises(ValueError, match="one host owner"):
        validate_topology_settings(config)
    with pytest.raises(ValidationError):
        HostObserverIdentity(host_id=HOST, token=TOKEN, addresses=["2001:0db8::1", "2001:db8::1"])


@pytest.mark.asyncio
async def test_ingress_direction_host_bounds_and_duplicate_sample_suppression():
    redis, config = await _get_redis(), settings()
    await service.ingest(HOST, report(), settings=config, redis=redis, now=1000)
    for mutation in ("direction", "outside", "replay", "unregistered"):
        value = report(1010)
        if mutation == "direction":
            value.flows.rows[0].direction = "ingress"
        elif mutation == "outside":
            value.flows.rows[0].target_host_id = "storage:outside"
        elif mutation == "replay":
            value.flows.captured_at = 1000
        else:
            config.monitoring_infrastructure_topology_observers[1].addresses = []
        with pytest.raises(HTTPException) as error:
            await service.ingest(HOST, value, settings=config, redis=redis, now=1010)
        assert error.value.status_code == (409 if mutation == "replay" else 422)


@pytest.mark.asyncio
async def test_real_http_auth_binding_and_public_snapshot_hides_raw_counters(monkeypatch):
    config = settings()
    monkeypatch.setattr(service, "get_settings", lambda: config)
    monkeypatch.setattr(service.time, "time", lambda: 1000)
    monkeypatch.setattr(service.host_health, "get_snapshot", AsyncMock(return_value={"hosts": [], "error": None}))
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/monitoring")
    app.add_middleware(HostObservationBodyLimit)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        base = "/api/v1/monitoring/host-observations/"
        denied = await client.post(
            base + PEER + "/reports", json=report().model_dump(), headers={"Authorization": "Bearer " + TOKEN}
        )
        assert denied.status_code == 401
        accepted = await client.post(
            base + HOST + "/reports", json=report().model_dump(), headers={"Authorization": "Bearer " + TOKEN}
        )
        assert accepted.status_code == 202 and accepted.headers["cache-control"] == "no-store"
    snapshot = await service.snapshot(settings=config, now=1000)
    host = next(host for host in snapshot["hosts"] if host["id"] == HOST)
    assert "flows" not in host["observation"] and "flow_rates" not in host["observation"]
    assert snapshot["flows"][0]["reason"] == "first_sample"
