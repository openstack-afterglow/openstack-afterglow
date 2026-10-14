"""Host health collector, direct exporter boundary, Redis fencing and admin snapshot API."""

from __future__ import annotations

import asyncio
import gzip
import json
import socket
import time
from types import SimpleNamespace

import httpx
import pytest
from openstack.compute.v2.hypervisor import Hypervisor
from openstack.compute.v2.service import Service

from app.config import HostHealthTarget
from app.services import host_health as hh
from app.services.cache import _get_redis

UPDATED = "2026-10-14T00:00:00.000000"


def settings(*targets: dict, enabled: bool = True):
    return SimpleNamespace(
        monitoring_host_healthcheck_enabled=enabled,
        monitoring_host_healthcheck_targets=[HostHealthTarget(**target) for target in targets],
        os_auth_url="https://keystone.example.test/v3",
        os_region_name="RegionOne",
        os_project_name="admin",
    )


def exposition(
    *,
    user=10,
    system=10,
    idle=80,
    guest=5,
    eth_rx=1000,
    eth_tx=500,
    eth_rx_packets=10,
    eth_tx_packets=5,
    veth_rx=0,
    available="2147483648",
    readonly=0,
    fstype="ext4",
) -> str:
    return "\n".join(
        [
            "# TYPE node_cpu_seconds_total counter",
            f'node_cpu_seconds_total{{cpu="0",mode="user"}} {user}',
            f'node_cpu_seconds_total{{cpu="0",mode="system"}} {system}',
            f'node_cpu_seconds_total{{cpu="0",mode="idle"}} {idle}',
            'node_cpu_seconds_total{cpu="0",mode="iowait"} 0',
            "# TYPE node_cpu_guest_seconds_total counter",
            f'node_cpu_guest_seconds_total{{cpu="0",mode="user"}} {guest}',
            f'node_cpu_seconds_total{{cpu="0",mode="guest"}} {guest}',
            "# TYPE node_memory_MemAvailable_bytes gauge",
            f"node_memory_MemAvailable_bytes {available}",
            "# TYPE node_memory_MemTotal_bytes gauge",
            "node_memory_MemTotal_bytes 8589934592",
            "# TYPE node_filesystem_avail_bytes gauge",
            f'node_filesystem_avail_bytes{{device="/dev/vda1",fstype="{fstype}",mountpoint="/"}} 25',
            'node_filesystem_avail_bytes{device="tmpfs",fstype="tmpfs",mountpoint="/run"} 1',
            "# TYPE node_filesystem_size_bytes gauge",
            f'node_filesystem_size_bytes{{device="/dev/vda1",fstype="{fstype}",mountpoint="/"}} 100',
            'node_filesystem_size_bytes{device="tmpfs",fstype="tmpfs",mountpoint="/run"} 100',
            "# TYPE node_filesystem_readonly gauge",
            f'node_filesystem_readonly{{device="/dev/vda1",fstype="{fstype}",mountpoint="/"}} {readonly}',
            "# TYPE node_network_info gauge",
            'node_network_info{address="52:54:00:AA:BB:CC",broadcast="ff:ff:ff:ff:ff:ff",device="eth0",'
            'duplex="full",operstate="up"} 1',
            "# TYPE node_network_receive_bytes_total counter",
            f'node_network_receive_bytes_total{{device="eth0"}} {eth_rx}',
            'node_network_receive_bytes_total{device="lo"} 999999',
            f'node_network_receive_bytes_total{{device="veth9"}} {veth_rx}',
            f'node_network_receive_bytes_total{{device="bond0"}} {eth_rx}',
            f'node_network_receive_bytes_total{{device="eth0.100"}} {eth_rx}',
            "# TYPE node_network_transmit_bytes_total counter",
            f'node_network_transmit_bytes_total{{device="eth0"}} {eth_tx}',
            'node_network_transmit_bytes_total{device="lo"} 999999',
            f'node_network_transmit_bytes_total{{device="veth9"}} {veth_rx}',
            "# TYPE node_network_receive_packets_total counter",
            f'node_network_receive_packets_total{{device="eth0"}} {eth_rx_packets}',
            "# TYPE node_network_transmit_packets_total counter",
            f'node_network_transmit_packets_total{{device="eth0"}} {eth_tx_packets}',
            "",
        ]
    )


def test_first_counter_sample_is_null_and_next_adjacent_sample_is_a_rate():
    values, counters, interfaces, omitted = hh.parse_metrics(exposition(), {}, 1000.0)

    assert values["cpu"] is None and values["network_rx"] is None and values["network_tx"] is None
    assert values["memory"] == pytest.approx(75.0)
    assert values["disk"] == pytest.approx(75.0)
    assert interfaces[0]["rx_bytes_per_second"] is None and interfaces[0]["rx_bytes_total"] == 1000

    values, _, interfaces, omitted = hh.parse_metrics(
        exposition(user=20, system=20, idle=140, guest=15, eth_rx=2000, eth_tx=700, eth_rx_packets=30, veth_rx=10**9),
        counters,
        1010.0,
    )

    # Guest time already sits in user time; counting it again would yield 30/90.
    assert values["cpu"] == pytest.approx(25.0)
    # Loopback, veth, bond and VLAN traffic is excluded from the physical aggregate.
    assert values["network_rx"] == pytest.approx(100.0)
    assert values["network_tx"] == pytest.approx(20.0)
    assert [item["name"] for item in interfaces] == ["eth0"]
    assert interfaces[0] == {
        "name": "eth0",
        "mac": "52:54:00:aa:bb:cc",
        "operstate": "up",
        "addresses": None,
        "rx_bytes_total": 2000,
        "tx_bytes_total": 700,
        "rx_packets_total": 30,
        "tx_packets_total": 5,
        "rx_bytes_per_second": pytest.approx(100.0),
        "tx_bytes_per_second": pytest.approx(20.0),
        "rx_packets_per_second": pytest.approx(2.0),
        "tx_packets_per_second": 0,
    }
    assert omitted == 3  # veth9, bond0 and eth0.100; loopback is not a host NIC.


def test_counter_reset_and_gap_are_null_not_zero_or_negative():
    _, counters, _, _ = hh.parse_metrics(exposition(), {}, 1000.0)

    reset, after_reset, interfaces, _ = hh.parse_metrics(exposition(user=1, eth_rx=10), counters, 1010.0)
    assert reset["cpu"] is None
    assert reset["network_rx"] is None
    assert interfaces[0]["rx_bytes_per_second"] is None

    recovered, _, _, _ = hh.parse_metrics(exposition(user=11, system=20, idle=150, eth_rx=110), after_reset, 1020.0)
    assert recovered["network_rx"] == pytest.approx(10.0)
    assert recovered["cpu"] is not None

    # Older than the staleness window: no rate across an outage.
    gap, _, _, _ = hh.parse_metrics(exposition(user=50, eth_rx=5000), counters, 1000.0 + hh.STALE_SECONDS + 1)
    assert gap["cpu"] is None and gap["network_rx"] is None


def test_nonfinite_readonly_and_pseudo_filesystem_values_are_null():
    values, _, _, _ = hh.parse_metrics(exposition(available="NaN", readonly=1), {}, 1000.0)
    assert values["memory"] is None
    assert values["disk"] is None

    tmpfs, _, _, _ = hh.parse_metrics(exposition(fstype="tmpfs"), {}, 1000.0)
    assert tmpfs["disk"] is None


def test_interface_addresses_are_unmeasured_without_the_address_info_collector():
    _, _, interfaces, _ = hh.parse_metrics(exposition(), {}, 1000.0)
    assert interfaces[0]["addresses"] is None

    labelled = exposition() + "\n".join(
        [
            "# TYPE node_network_address_info gauge",
            'node_network_address_info{address="10.20.0.7",device="eth0",netmask="24",scope="global"} 1',
            'node_network_address_info{address="fe80::1",device="eth0",netmask="64",scope="link"} 1',
            'node_network_address_info{address="not-an-ip",device="eth0",netmask="24",scope="global"} 1',
            'node_network_address_info{address="10.9.9.9",device="veth9",netmask="32",scope="global"} 1',
            "",
        ]
    )
    _, _, interfaces, _ = hh.parse_metrics(labelled, {}, 1000.0)
    assert interfaces[0]["addresses"] == ["10.20.0.7/24", "fe80::1/64"]

    no_eth_address = exposition() + (
        "# TYPE node_network_address_info gauge\n"
        'node_network_address_info{address="10.9.9.9",device="veth9",netmask="32",scope="global"} 1\n'
    )
    _, _, interfaces, _ = hh.parse_metrics(no_eth_address, {}, 1000.0)
    assert interfaces[0]["addresses"] == []


def test_unexpected_exporter_identity_labels_null_only_that_field():
    odd = (
        exposition()
        .replace('address="52:54:00:AA:BB:CC"', 'address="zz"')
        .replace('operstate="up"', 'operstate="sideways"')
    )
    values, _, interfaces, _ = hh.parse_metrics(odd, {}, 1000.0)
    assert (interfaces[0]["mac"], interfaces[0]["operstate"]) == (None, None)
    assert interfaces[0]["rx_bytes_total"] == 1000 and values["memory"] is not None


async def _probe_down(target):
    stamp = time.time()
    return (
        hh.ExporterReachability(status="down", checked_at=hh._iso(stamp), error="probe_timeout").model_dump(),
        None,
        stamp,
        target.address,  # This injected probe measures the fixed IP supplied by its tests.
    )


def _nova(name="cmp-1", role="compute", address="10.0.0.11", status="up"):
    heartbeat = {"status": status, "updated_at": "2026-10-14T00:00:00+00:00", "source": "nova-compute"}
    return hh.Target(name, role, address, heartbeat=heartbeat, observed_at=time.time())


async def discovered(config, discover, probe):
    collector = hh.Collector(config, await _get_redis(), discover=discover, probe=probe)
    await collector.refresh_discovery()
    return collector


@pytest.mark.asyncio
async def test_exporter_down_is_independent_of_nova_heartbeat_and_records_null_history():
    async def discover():
        return [_nova()]

    collector = await discovered(settings(), discover, _probe_down)
    state = await collector.collect(None)
    host = state["snapshot"]["hosts"][0]

    assert host["id"] == "compute:cmp-1"
    assert host["heartbeat"]["status"] == "up"
    assert host["reachability"]["status"] == "down" and host["reachability"]["error"] == "probe_timeout"
    assert host["metrics_error"] == "probe_timeout"
    assert host["interfaces"] is None
    assert all(metric["value"] is None for metric in host["metrics"].values())
    assert host["metrics"]["cpu"]["series"][-1]["value"] is None


@pytest.mark.asyncio
async def test_history_is_bounded_and_reset_when_the_probed_destination_changes():
    clock = iter(range(0, 10000, 10))
    address = {"value": "10.0.0.11"}

    async def discover():
        return [_nova(address=address["value"])]

    async def probe(target):
        stamp = 100000.0 + next(clock)
        return (
            hh.ExporterReachability(status="up", checked_at=hh._iso(stamp)).model_dump(),
            exposition(),
            stamp,
            target.address,
        )

    collector = await discovered(settings(), discover, probe)
    state = None
    for _ in range(65):
        state = await collector.collect(state)
    series = state["snapshot"]["hosts"][0]["metrics"]["memory"]["series"]
    assert len(series) == hh.HISTORY_POINTS
    assert series[-1]["ts"] - series[0]["ts"] <= hh.HISTORY_SECONDS

    address["value"] = "10.0.0.12"
    await collector.refresh_discovery()
    moved = await collector.collect(state)
    host = moved["snapshot"]["hosts"][0]
    assert len(host["metrics"]["memory"]["series"]) == 1
    assert host["metrics"]["cpu"]["value"] is None  # No rate against another host's counters.


@pytest.mark.asyncio
async def test_discovery_failure_keeps_probing_known_hosts_without_a_fresh_heartbeat():
    async def discover():
        return [_nova()]

    collector = await discovered(settings(), discover, _probe_down)
    first = await collector.collect(None)

    async def broken():
        raise RuntimeError("Unauthorized token=secret")

    collector._discover_override = broken
    await collector.refresh_discovery()
    failed = await collector.collect(first)

    assert failed["snapshot"]["error"] == "discovery_failed"
    assert "secret" not in json.dumps(failed)
    host = failed["snapshot"]["hosts"][0]
    assert host["id"] == "compute:cmp-1" and host["heartbeat"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_no_hosts_is_distinct_and_configured_storage_has_no_inferred_heartbeat():
    async def discover():
        return []

    empty = await (await discovered(settings(), discover, _probe_down)).collect(None)
    assert empty["snapshot"]["error"] == "no_hosts" and empty["snapshot"]["hosts"] == []

    storage = settings({"name": "Ceph-1", "address": "10.0.0.31", "role": "storage"})
    state = await (await discovered(storage, discover, _probe_down)).collect(None)
    host = state["snapshot"]["hosts"][0]
    assert state["snapshot"]["error"] is None
    assert (host["id"], host["role"], host["heartbeat"]) == (
        "storage:ceph-1",
        "storage",
        {"status": "unknown", "updated_at": None, "source": None},
    )


@pytest.mark.asyncio
async def test_configured_target_overrides_discovered_address_and_keeps_its_nova_heartbeat():
    seen = []

    async def discover():
        return [_nova(name="CTL-1", role="controller", address="ctl-1")]

    async def probe(target):
        seen.append((target.address, target.port))
        return await _probe_down(target)

    override = settings({"name": "ctl-1", "address": "10.0.0.21", "role": "controller", "port": 9101})
    state = await (await discovered(override, discover, probe)).collect(None)

    assert seen == [("10.0.0.21", 9101)]
    assert state["snapshot"]["hosts"][0]["heartbeat"]["status"] == "up"


@pytest.mark.asyncio
async def test_read_time_staleness_clears_current_values_but_keeps_history():
    async def discover():
        return [_nova()]

    async def probe(target):
        stamp = time.time()
        return (
            hh.ExporterReachability(status="up", checked_at=hh._iso(stamp), latency_ms=2).model_dump(),
            exposition(),
            stamp,
            target.address,
        )

    redis = await _get_redis()
    config = settings()
    state = await (await discovered(config, discover, probe)).collect(None)
    await redis.set(hh._keys(config)[1], json.dumps(state))

    fresh = await hh.get_snapshot(settings=config, redis=redis)
    assert fresh["stale"] is False and fresh["hosts"][0]["reachability"]["status"] == "up"
    assert fresh["hosts"][0]["metrics"]["memory"]["value"] == pytest.approx(75.0)

    stale = await hh.get_snapshot(settings=config, redis=redis, now=time.time() + hh.STALE_SECONDS + 1)
    host = stale["hosts"][0]
    assert stale["stale"] is True and stale["error"] == "snapshot_stale"
    assert host["reachability"]["status"] == "unknown" and host["reachability"]["latency_ms"] is None
    assert host["heartbeat"]["status"] == "unknown"
    assert host["metrics"]["memory"]["value"] is None
    assert host["metrics"]["memory"]["series"][0]["value"] == pytest.approx(75.0)
    assert host["interfaces"][0]["rx_bytes_total"] is None and host["interfaces"][0]["name"] == "eth0"


class BrokenRedis:
    async def get(self, key):
        raise ConnectionError("redis://:password@redis")

    async def set(self, *args, **kwargs):
        raise ConnectionError("redis://:password@redis")


@pytest.mark.asyncio
async def test_redis_outage_never_claims_a_snapshot_or_starts_collection(monkeypatch):
    snapshot = await hh.get_snapshot(settings=settings(), redis=BrokenRedis())
    assert snapshot == {
        "enabled": True,
        "interval_seconds": 10,
        "collected_at": None,
        "stale": True,
        "error": "redis_unavailable",
        "hosts": [],
    }

    calls = []

    async def discover():
        calls.append(1)
        return []

    monkeypatch.setattr(hh, "INTERVAL_SECONDS", 0.01)
    loop = asyncio.create_task(hh.monitoring_loop(settings=settings(), redis=BrokenRedis(), discover=discover))
    await asyncio.sleep(0.1)
    loop.cancel()
    await asyncio.gather(loop, return_exceptions=True)
    assert calls == []


@pytest.mark.asyncio
async def test_disabled_snapshot_and_loop_do_not_collect():
    disabled = settings(enabled=False)
    assert (await hh.get_snapshot(settings=disabled))["enabled"] is False
    await asyncio.wait_for(hh.monitoring_loop(settings=disabled), 1)


@pytest.mark.asyncio
async def test_former_owner_cannot_publish_or_release_a_newer_lease():
    redis = await _get_redis()

    async def discover():
        return [_nova()]

    collector = hh.Collector(settings(), redis, discover=discover, probe=_probe_down)
    await redis.set(collector.lease_key, "newer-owner")

    with pytest.raises(hh.LeaseLost):
        await collector.run_owned()

    assert await redis.get(collector.snapshot_key) is None
    assert await redis.get(collector.lease_key) == "newer-owner"


@pytest.mark.asyncio
async def test_concurrent_workers_share_one_collector_and_cancellation_releases_the_lease(monkeypatch):
    monkeypatch.setattr(hh, "INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(hh, "RENEW_SECONDS", 0.02)
    redis = await _get_redis()
    config = settings()
    calls = {"a": 0, "b": 0}

    def discover_for(worker):
        async def discover():
            calls[worker] += 1
            return [_nova()]

        return discover

    loops = [
        asyncio.create_task(
            hh.monitoring_loop(settings=config, redis=redis, discover=discover_for(worker), probe=_probe_down)
        )
        for worker in calls
    ]
    await asyncio.sleep(0.4)
    snapshot = await hh.get_snapshot(settings=config, redis=redis)
    for loop in loops:
        loop.cancel()
    await asyncio.gather(*loops, return_exceptions=True)

    assert sorted(value > 0 for value in calls.values()) == [False, True]
    assert snapshot["stale"] is False and snapshot["hosts"][0]["id"] == "compute:cmp-1"
    assert await redis.get(hh._keys(config)[0]) is None


@pytest.mark.asyncio
async def test_hung_nova_discovery_does_not_delay_or_stale_exporter_probes(monkeypatch):
    monkeypatch.setattr(hh, "INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(hh, "RENEW_SECONDS", 0.02)
    monkeypatch.setattr(hh, "PROBE_SECONDS", 0.05)
    release = asyncio.Event()

    async def hung_discovery():
        await release.wait()
        return []

    async def probe(target):
        stamp = time.time()
        return (
            hh.ExporterReachability(status="up", checked_at=hh._iso(stamp), latency_ms=1).model_dump(),
            None,
            stamp,
            target.address,
        )

    redis = await _get_redis()
    config = settings({"name": "cmp-1", "address": "10.0.0.11", "role": "compute"})
    loop = asyncio.create_task(hh.monitoring_loop(settings=config, redis=redis, discover=hung_discovery, probe=probe))
    try:
        await asyncio.sleep(0.3)
        snapshot = await hh.get_snapshot(settings=config, redis=redis)
    finally:
        loop.cancel()
        release.set()
        await asyncio.gather(loop, return_exceptions=True)

    assert snapshot["stale"] is False and snapshot["error"] == "discovery_pending"
    host = snapshot["hosts"][0]
    assert host["reachability"]["status"] == "up"
    assert host["heartbeat"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_cancelled_collection_awaits_inflight_probes():
    entered, started, finished = asyncio.Event(), [], []

    async def discover():
        return [_nova(name=f"cmp-{index}", address=f"10.0.0.{index + 1}") for index in range(3)]

    async def probe(target):
        started.append(target.name)
        if len(started) == 3:
            entered.set()
        try:
            await asyncio.sleep(10)
        finally:
            finished.append(target.name)

    collector = await discovered(settings(), discover, probe)
    task = asyncio.create_task(collector.collect(None))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sorted(finished) == ["cmp-0", "cmp-1", "cmp-2"]


def test_nova_discovery_uses_exact_host_ip_and_separates_heartbeat_states():
    def service(binary, host, state="up", forced=False, updated=UPDATED):
        return Service.existing(binary=binary, host=host, state=state, forced_down=forced, updated_at=updated)

    def hypervisor(host, host_ip):
        # Raw Nova JSON key "service"; the SDK resource exposes it as service_details.
        return Hypervisor.existing(service={"host": host, "id": f"svc-{host}"}, host_ip=host_ip)

    services = [
        service("nova-compute", "cmp-1"),
        service("nova-compute", "cmp-2", updated=None),
        service("nova-compute", "cmp-3", forced=True),
        service("nova-conductor", "ctl-1"),
        service("nova-scheduler", "ctl-1", state="down"),
        service("nova-consoleauth", "ctl-9"),
    ]
    hypervisors = [
        hypervisor("cmp-1", "10.0.0.11"),
        hypervisor("cmp-2", "169.254.169.254"),
        hypervisor("cmp-3", "10.0.0.13"),
        hypervisor("cmp-3", "10.0.0.14"),
    ]
    conn = SimpleNamespace(
        compute=SimpleNamespace(services=lambda: iter(services), hypervisors=lambda details: iter(hypervisors))
    )

    targets = {target.id: target for target in hh.discover_from_nova(conn)}

    assert set(targets) == {"compute:cmp-1", "compute:cmp-2", "compute:cmp-3", "controller:ctl-1"}
    assert targets["compute:cmp-1"].address == "10.0.0.11"
    assert targets["compute:cmp-1"].heartbeat["status"] == "up"
    assert targets["compute:cmp-2"].address is None  # Metadata host_ip is never probed.
    assert targets["compute:cmp-2"].heartbeat["status"] == "unknown"  # No provider timestamp.
    assert targets["compute:cmp-3"].address is None  # Ambiguous host_ip is not guessed.
    assert targets["compute:cmp-3"].heartbeat["status"] == "down"
    controller = targets["controller:ctl-1"]
    assert controller.address == "ctl-1"
    assert controller.heartbeat["status"] == "down"
    assert controller.heartbeat["source"] == "nova-conductor,nova-scheduler"


class ExporterStream(httpx.AsyncByteStream):
    """Unconsumed wire chunks with evidence of bounded reads and response closure."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.chunks_read = 0
        self.bytes_read = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.chunks_read += 1
            self.bytes_read += len(chunk)
            yield chunk

    async def aclose(self):
        self.closed = True


@pytest.fixture
async def exporter(monkeypatch):
    requests = []
    responses = {}
    streams = []

    def handler(request):
        requests.append(request)
        if "next" in responses:
            return responses["next"]
        body = exposition().encode("utf-8")
        stream = ExporterStream([body[:100], body[100:]])
        streams.append(stream)
        return httpx.Response(200, stream=stream)

    async with hh._build_client(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(hh, "_client", client)
        yield SimpleNamespace(requests=requests, responses=responses, streams=streams)


def _dns(monkeypatch, *addresses):
    async def getaddrinfo(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port)) for address in addresses]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", getaddrinfo)


@pytest.mark.asyncio
async def test_probe_pins_the_checked_dns_answer_and_preserves_the_exporter_host(exporter, monkeypatch):
    _dns(monkeypatch, "10.20.0.7")

    reachability, body, _, destination = await hh.probe_exporter(
        hh.Target("ctl-1", "controller", "ctl-1.mgmt.example", 9100)
    )

    assert reachability["status"] == "up" and reachability["error"] is None
    assert reachability["latency_ms"] is not None
    assert "node_cpu_seconds_total" in body
    assert destination == "10.20.0.7"
    assert exporter.streams[0].chunks_read == 2 and exporter.streams[0].closed
    request = exporter.requests[0]
    assert str(request.url) == "http://10.20.0.7:9100/metrics"
    assert request.headers["host"] == "ctl-1.mgmt.example:9100"
    assert "authorization" not in request.headers
    assert request.headers["accept-encoding"] == "identity"


@pytest.mark.parametrize("answers", [("169.254.169.254",), ("10.20.0.7", "127.0.0.1"), ("::ffff:127.0.0.1",)])
@pytest.mark.asyncio
async def test_probe_rejects_any_unsafe_dns_answer_before_http(exporter, monkeypatch, answers):
    _dns(monkeypatch, *answers)

    reachability, body, _, destination = await hh.probe_exporter(hh.Target("ctl-1", "controller", "ctl-1.mgmt.example"))

    assert (reachability["status"], reachability["error"], body) == ("unknown", "invalid_target", None)
    assert destination is None
    assert exporter.requests == []


@pytest.mark.asyncio
async def test_probe_does_not_follow_redirects_or_accept_oversized_bodies(exporter):
    redirect_stream = ExporterStream([b"must not read redirect bodies"])
    exporter.responses["next"] = httpx.Response(
        302, headers={"Location": "http://169.254.169.254/latest"}, stream=redirect_stream
    )
    redirected, body, _, destination = await hh.probe_exporter(hh.Target("cmp-1", "compute", "10.0.0.11"))
    assert (redirected["status"], redirected["error"], body) == ("down", "http_status", None)
    assert len(exporter.requests) == 1
    assert destination == "10.0.0.11"
    assert redirect_stream.chunks_read == 0 and redirect_stream.closed

    chunk = b"#" * 65536
    oversized_stream = ExporterStream([chunk] * (hh.MAX_BODY_BYTES // len(chunk) + 2))
    exporter.responses["next"] = httpx.Response(200, stream=oversized_stream)
    oversized, body, _, destination = await hh.probe_exporter(hh.Target("cmp-1", "compute", "10.0.0.11"))
    assert (oversized["status"], oversized["error"], body) == ("up", "body_too_large", None)
    assert destination == "10.0.0.11"
    assert oversized_stream.bytes_read == hh.MAX_BODY_BYTES + len(chunk)
    assert oversized_stream.chunks_read < len(oversized_stream.chunks)
    assert oversized_stream.closed


@pytest.mark.asyncio
async def test_dns_rotation_resets_persisted_counters_and_history(exporter, monkeypatch):
    hostname = "ctl-1.mgmt.example"

    async def discover():
        return [_nova(name="ctl-1", role="controller", address=hostname)]

    collector = await discovered(settings(), discover, hh.probe_exporter)
    clock = {"at": 100000.0}
    monkeypatch.setattr(hh.time, "time", lambda: clock["at"])

    def serve(body):
        wire = body.encode("utf-8")
        exporter.responses["next"] = httpx.Response(200, stream=ExporterStream([wire[:100], wire[100:]]))

    _dns(monkeypatch, "10.20.0.7")
    first = await collector.collect(None)
    clock["at"] += hh.INTERVAL_SECONDS
    serve(exposition(user=20, system=20, idle=140, eth_rx=2000, eth_tx=700, eth_rx_packets=30))
    stable = await collector.collect(first)
    host = stable["snapshot"]["hosts"][0]
    assert host["metrics"]["cpu"]["value"] == pytest.approx(25.0)
    assert host["metrics"]["network_rx"]["value"] == pytest.approx(100.0)
    assert all(len(metric["series"]) == 2 for metric in host["metrics"].values())
    assert stable["destinations"] == {"controller:ctl-1": "10.20.0.7"}

    # A new owner reads the actual persisted destination, not a guessed hostname identity.
    await collector.redis.set(collector.snapshot_key, json.dumps(stable))
    collector = await discovered(settings(), discover, hh.probe_exporter)
    persisted = await collector._previous()
    assert persisted["destinations"] == stable["destinations"]

    _dns(monkeypatch, "10.20.0.8")
    clock["at"] += hh.INTERVAL_SECONDS
    # Counters increase across hosts, so the reset must be identity-based, not a counter decrease.
    serve(exposition(user=100, system=100, idle=800, eth_rx=10000, eth_tx=5000, eth_rx_packets=100))
    moved = await collector.collect(persisted)
    host = moved["snapshot"]["hosts"][0]
    assert host["address"] == hostname
    assert moved["destinations"] == {"controller:ctl-1": "10.20.0.8"}
    assert all(len(metric["series"]) == 1 for metric in host["metrics"].values())
    assert all(host["metrics"][name]["value"] is None for name in ("cpu", "network_rx", "network_tx"))
    assert host["metrics"]["memory"]["value"] == pytest.approx(75.0)
    assert host["interfaces"][0]["rx_bytes_per_second"] is None
    assert host["interfaces"][0]["rx_packets_per_second"] is None

    clock["at"] += hh.INTERVAL_SECONDS
    serve(exposition(user=110, system=110, idle=860, eth_rx=11000, eth_tx=5200, eth_rx_packets=120))
    recovered = await collector.collect(moved)
    host = recovered["snapshot"]["hosts"][0]
    assert host["metrics"]["cpu"]["value"] == pytest.approx(25.0)
    assert host["metrics"]["network_rx"]["value"] == pytest.approx(100.0)
    assert host["metrics"]["network_tx"]["value"] == pytest.approx(20.0)
    assert host["interfaces"][0]["rx_packets_per_second"] == pytest.approx(2.0)
    assert all(len(metric["series"]) == 2 for metric in host["metrics"].values())
    assert [request.url.host for request in exporter.requests] == ["10.20.0.7"] * 2 + ["10.20.0.8"] * 2
    assert all(request.headers["host"] == f"{hostname}:9100" for request in exporter.requests)


@pytest.mark.parametrize("size", [hh.MAX_BODY_BYTES - 1, hh.MAX_BODY_BYTES])
@pytest.mark.asyncio
async def test_probe_accepts_streamed_bodies_up_to_the_exact_limit(exporter, size):
    wire = exposition().encode("utf-8")
    wire += b"#" + b" " * (size - len(wire) - 1)
    stream = ExporterStream([wire[start : start + 16384] for start in range(0, len(wire), 16384)])
    exporter.responses["next"] = httpx.Response(200, stream=stream)

    reachability, body, _, destination = await hh.probe_exporter(hh.Target("cmp-1", "compute", "10.0.0.11"))

    assert (reachability["status"], reachability["error"]) == ("up", None)
    assert body.encode("utf-8") == wire
    assert destination == "10.0.0.11"
    assert stream.bytes_read == size and stream.closed


@pytest.mark.asyncio
async def test_probe_rejects_compressed_bodies_without_reading_or_decompressing_them(exporter):
    stream = ExporterStream([gzip.compress(exposition().encode("utf-8"))])
    exporter.responses["next"] = httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=stream)

    reachability, body, _, destination = await hh.probe_exporter(hh.Target("cmp-1", "compute", "10.0.0.11"))

    assert (reachability["status"], reachability["error"], body) == ("up", "unsupported_encoding", None)
    assert destination == "10.0.0.11"
    assert stream.chunks_read == 0 and stream.closed


@pytest.mark.parametrize("unidentified", ["legacy_version", "missing_destinations"])
@pytest.mark.asyncio
async def test_persisted_state_without_pinned_identity_is_not_a_baseline(unidentified):
    async def discover():
        return [_nova()]

    collector = await discovered(settings(), discover, _probe_down)
    state = await collector.collect(None)
    if unidentified == "legacy_version":
        state["version"] = 2
    else:
        del state["destinations"]
    await collector.redis.set(collector.snapshot_key, json.dumps(state))

    assert await collector._previous() is None


@pytest.mark.asyncio
async def test_probe_without_a_nova_host_ip_is_unmeasured_not_down(exporter):
    reachability, body, _, destination = await hh.probe_exporter(hh.Target("cmp-2", "compute", None))
    assert (reachability["status"], reachability["error"], body) == ("unknown", "missing_address", None)
    assert destination is None
    assert exporter.requests == []


@pytest.mark.asyncio
async def test_admin_route_reads_the_shared_snapshot_without_probing(admin_client, monkeypatch):
    async def forbidden_probe(target):
        raise AssertionError("browser request must not probe exporters")

    monkeypatch.setattr(hh, "probe_exporter", forbidden_probe)
    empty = await admin_client.get("/api/v1/admin/host-health")
    assert empty.status_code == 200
    assert empty.headers["cache-control"] == "no-store"
    assert empty.json()["error"] == "not_collected" and empty.json()["stale"] is True

    async def discover():
        return [_nova()]

    from app.config import get_settings

    config = get_settings()
    redis = await _get_redis()
    state = await (await discovered(config, discover, _probe_down)).collect(None)
    await redis.set(hh._keys(config)[1], json.dumps(state))

    response = await admin_client.get("/api/v1/admin/host-health")
    body = response.json()
    assert response.status_code == 200
    assert body["interval_seconds"] == 10 and body["stale"] is False
    assert body["hosts"][0]["id"] == "compute:cmp-1"
    assert set(body["hosts"][0]["metrics"]) == {"cpu", "memory", "disk", "network_rx", "network_tx"}


@pytest.mark.asyncio
async def test_non_admin_cannot_read_host_health(non_admin_client):
    response = await non_admin_client.get("/api/v1/admin/host-health")
    assert response.status_code == 403
