"""Behavioral boundaries plus a real UDP SNMPv3 authPriv agent/reader exchange."""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from pydantic import ValidationError

from app.models.infrastructure_fabric import (
    JS_SAFE_MAX,
    UINT64_MAX,
    DeviceSample,
    FabricSettings,
    FabricTarget,
    PortSample,
)
from app.services import infrastructure_fabric as fabric

CHASSIS = "00:11:22:33:44:55"
HOST = "compute:cmp-1"


def target(**overrides):
    return FabricTarget(
        **(
            dict(
                id="sw-1",
                name="Switch One",
                chassis_id=CHASSIS,
                management_ip="192.0.2.10",
                username="readonly-user",
                auth_key="only-test-auth-key",
                priv_key="only-test-priv-key",
            )
            | overrides
        )
    )


def settings(targets=None, **overrides):
    overrides.setdefault("revision", 1)
    return SimpleNamespace(
        monitoring_infrastructure_fabric=FabricSettings(
            targets=[target()] if targets is None else targets, **overrides
        ),
        monitoring_infrastructure_topology_observers=[SimpleNamespace(host_id=HOST)],
        os_auth_url="https://identity.example/v3",
        os_region_name="RegionOne",
        os_project_name="admin",
    )


def values(counter=100):
    result = {
        fabric.UPTIME: 100000,
        fabric.BOOTS: 4,
        fabric.IF + (1, 7): 7,
        fabric.IF + (3, 7): 6,
        fabric.IF + (8, 7): 1,
        fabric.IF + (6, 7): bytes.fromhex("001122334466"),
        fabric.IFX + (1, 7): b"Ethernet7",
        fabric.IFX + (17, 7): 1,
        fabric.IFX + (19, 7): 0,
        fabric.LLDP + (3, 1, 0): 4,
        fabric.LLDP + (3, 2, 0): bytes.fromhex("001122334455"),
        fabric.LLDP + (3, 7, 1, 2, 99): 5,
        fabric.LLDP + (3, 7, 1, 3, 99): b"Ethernet7",
        fabric.LLDP + (3, 7, 1, 4, 99): b"uplink seven",
    }
    for column in (6, 7, 8, 9, 10, 11, 12, 13):
        result[fabric.IFX + (column, 7)] = counter
    return result


def sample(ts=1000, counter=100):
    data = values(counter)
    data[fabric.UPTIME] += int((ts - 1000) * 100)
    return fabric.parse_sample(data, FabricSettings(), ts)


def record(current, previous=None, **overrides):
    return (
        dict(
            sample=current.model_dump(),
            previous=previous.model_dump() if previous else None,
            error=None,
            collector="owner-a",
            collector_reset=False,
        )
        | overrides
    )


def host_observation(ts=1000, chassis=CHASSIS, port="Ethernet7"):
    return dict(
        captured_at=ts,
        interfaces=[dict(name="eth0", physical=True, rx_packets=str(UINT64_MAX))],
        sources=dict(lldp="measured"),
        lldp=[
            dict(
                interface="eth0",
                chassis_id=chassis,
                port_id=port,
                system_name="actual-lldp-switch",
                management_address="198.51.100.200",
            )
        ],
    )


@pytest.mark.parametrize("address", ["switch.example", "192.0.2.0/24", "0.0.0.0", "224.0.0.1", "fe80::1%eth0"])
def test_exact_literal_management_targets_only(address):
    with pytest.raises(ValidationError):
        target(management_ip=address)


def test_config_has_no_default_credentials_protects_errors_and_bounds():
    assert FabricSettings().targets == []
    with pytest.raises(ValidationError):
        FabricTarget(id="sw", name="sw", chassis_id=CHASSIS, management_ip="192.0.2.10", username="user")
    assert "only-test-auth-key" not in repr(target())
    assert "only-test-priv-key" not in target().model_dump_json()
    private_value = "x7~q!"
    with pytest.raises(ValidationError) as exc:
        target(auth_key=private_value)
    assert private_value not in str(exc.value)
    for overrides in (
        dict(retries=3),
        dict(concurrency=9),
        dict(max_ports=1025),
        dict(freshness_seconds=5),
        dict(retention_seconds=30),
        dict(targets=[target(), target()]),
    ):
        with pytest.raises(ValidationError):
            FabricSettings(revision=1, **overrides)


def test_uint64_strings_complete_packet_sums_and_missing_counter_not_zero():
    data = values(UINT64_MAX)
    parsed = fabric.parse_sample(data, FabricSettings(), 1000)
    assert parsed.ports[0].rx_bytes == str(UINT64_MAX)
    assert parsed.ports[0].rx_packets is None  # Three uint64 components overflow the aggregate.
    assert "snmp_counter_overflow" in parsed.errors
    data = values()
    del data[fabric.IFX + (8, 7)]
    parsed = fabric.parse_sample(data, FabricSettings(), 1000)
    assert parsed.ports[0].rx_packets is None
    assert parsed.ports[0].tx_packets == "300"
    assert parsed.ports[0].rx_bytes == "100"
    assert "snmp_missing_counters" in parsed.errors
    with pytest.raises(ValidationError):
        PortSample(ifindex=1, name="p", rx_bytes=str(UINT64_MAX + 1))
    with pytest.raises(ValidationError):
        DeviceSample(captured_at=1000, errors=["secret=do-not-expose"])


def test_missing_ifname_and_cardinality_are_not_invented_or_silent():
    data = values()
    del data[fabric.IFX + (1, 7)]
    parsed = fabric.parse_sample(data, FabricSettings(), 1000)
    assert parsed.ports == [] and "snmp_invalid_response" in parsed.errors
    data = values()
    data[fabric.IF + (1, 8)] = 8
    with pytest.raises(fabric.PollError, match="snmp_cardinality_exceeded"):
        fabric.parse_sample(data, FabricSettings(max_ports=1), 1000)


def test_lldp_local_port_number_is_not_ifindex_and_management_is_metadata():
    data = values()
    remote = fabric.LLDP + (4, 1, 1)
    row = (42, 99, 1)
    for column, value in ((4, 4), (5, bytes.fromhex("aabbccddeeff")), (6, 5), (7, b"Ethernet2"), (9, b"peer-switch")):
        data[remote + (column,) + row] = value
    data[fabric.LLDP + (4, 2, 1, 3) + row + (1, 4, 198, 51, 100, 99)] = 1
    parsed = fabric.parse_sample(data, FabricSettings(), 1000)
    assert parsed.local_ports[0].number == 99
    assert parsed.ports[0].ifindex == 7
    assert fabric._resolve_port("Ethernet7", parsed.local_ports, parsed.ports) == 7
    assert fabric._resolve_port("99", parsed.local_ports, parsed.ports) is None
    assert parsed.neighbors[0].management_addresses == ["198.51.100.99"]
    assert parsed.neighbors[0].chassis_id == "aa:bb:cc:dd:ee:ff"
    # The advertisement does not create a target or a link to an unconfigured switch.
    output = fabric.project(settings(), {"sw-1": record(parsed)}, 1000)
    assert output["links"] == []
    assert len(output["devices"]) == 1


def test_adjacent_rates_first_zero_reset_reboot_missing_and_safe_delta():
    config = FabricSettings()
    first = sample()
    second = sample(1010, 200)
    assert fabric.port_rates(first.ports[0], None, first, None, config) == (
        dict.fromkeys(fabric.COUNTERS),
        None,
        "first_sample",
    )
    rates, window, reason = fabric.port_rates(second.ports[0], first.ports[0], second, first, config)
    assert rates == dict(rx_bytes=10, tx_bytes=10, rx_packets=30, tx_packets=30)
    assert window == 10 and reason is None
    unchanged = sample(1010, 100)
    assert set(fabric.port_rates(unchanged.ports[0], first.ports[0], unchanged, first, config)[0].values()) == {0}
    for changed, expected in (
        (sample(1004, 200), "stale_sample"),
        (sample(1031, 200), "stale_sample"),
        (sample(1010, 1), "counter_reset"),
        (second.model_copy(update={"engine_boots": 5}), "collector_reset"),
        (second.model_copy(update={"uptime": 1}), "collector_reset"),
    ):
        result = fabric.port_rates(changed.ports[0], first.ports[0], changed, first, config)
        assert set(result[0].values()) == {None} and result[2] == expected
    changed_port = second.ports[0].model_copy(update={"discontinuity": 1})
    assert fabric.port_rates(changed_port, first.ports[0], second, first, config)[2] == "counter_reset"
    partial = second.ports[0].model_copy(update={"rx_packets": None})
    rates, _, reason = fabric.port_rates(partial, first.ports[0], second, first, config)
    assert rates["rx_packets"] is None and rates["tx_packets"] == 30 and reason == "collector_error"
    high = first.ports[0].model_copy(update={"rx_bytes": str(UINT64_MAX - 1000)})
    higher = second.ports[0].model_copy(update={"rx_bytes": str(UINT64_MAX - 900)})
    assert fabric.port_rates(higher, high, second, first, config)[0]["rx_bytes"] == 10
    overflow = second.ports[0].model_copy(update={"rx_bytes": str(JS_SAFE_MAX + 1000)})
    rates, _, reason = fabric.port_rates(overflow, first.ports[0], second, first, config)
    assert rates["rx_bytes"] is None and reason == "overflow"


def test_retained_discontinuity_before_uptime_wrap_does_not_permanently_hide_rates():
    first = sample().model_copy(update={"uptime": 1000})
    second = sample(1010, 200).model_copy(update={"uptime": 2000})
    prior = first.ports[0].model_copy(update={"discontinuity": 2**32 - 1000})
    current = second.ports[0].model_copy(update={"discontinuity": 2**32 - 1000})
    rates, window, reason = fabric.port_rates(current, prior, second, first, FabricSettings())
    assert rates == dict(rx_bytes=10, tx_bytes=10, rx_packets=30, tx_packets=30)
    assert window == 10 and reason is None


def test_uptime_wrap_keeps_adjacent_rates_but_reboot_or_discontinuity_does_not():
    first = sample().model_copy(update={"uptime": 2**32 - 296})
    second = sample(1010, 200).model_copy(update={"uptime": 704})
    rates, window, reason = fabric.port_rates(second.ports[0], first.ports[0], second, first, FabricSettings())
    assert rates == dict(rx_bytes=10, tx_bytes=10, rx_packets=30, tx_packets=30)
    assert window == 10 and reason is None
    for changed, expected in (
        (second.model_copy(update={"engine_boots": 5}), "collector_reset"),
        (second.model_copy(update={"uptime": 100000}), "collector_reset"),
        (
            second.model_copy(update={"ports": [second.ports[0].model_copy(update={"discontinuity": 704})]}),
            "counter_reset",
        ),
    ):
        result = fabric.port_rates(changed.ports[0], first.ports[0], changed, first, FabricSettings())
        assert set(result[0].values()) == {None} and result[1] is None and result[2] == expected


def test_graph_known_chassis_only_stable_sorted_and_stale_rates_null():
    config = settings()
    observations = {HOST: host_observation()}
    first = fabric.project(config, {"sw-1": record(sample())}, 1000, observations)
    second = fabric.project(config, {"sw-1": record(sample(1010, 200), sample())}, 1010, observations)
    assert first["links"][0]["id"] == second["links"][0]["id"]
    assert second["links"][0]["source"]["id"] == HOST
    assert second["links"][0]["target_port_id"] == "switch:sw-1:if:7"
    assert second["links"][0]["source_port_id"] is None
    assert second["ports"][0]["rx_packets_per_second"] == 30
    stale = fabric.project(config, {"sw-1": record(sample(1010, 200), sample())}, 1041, observations)
    assert stale["ports"][0]["state"] == "stale"
    assert stale["ports"][0]["reason"] == "stale_sample"
    assert stale["ports"][0]["rx_packets_per_second"] is None
    assert stale["links"][0]["state"] == "stale"
    unknown = fabric.project(config, {}, 1000, {"storage:unregistered": host_observation()})
    assert unknown["links"] == []


@pytest.mark.asyncio
async def test_unconfigured_still_has_host_lldp_no_redis_or_snmp():
    redis = SimpleNamespace(mget=AsyncMock(side_effect=AssertionError("must not read Redis")))
    output = await fabric.snapshot(
        settings=settings(targets=[]), redis=redis, now=1000, host_observations={HOST: host_observation()}
    )
    assert output["state"] == "unconfigured" and output["ports"] == []
    assert output["devices"][0]["id"].startswith("switch:lldp:")
    assert len(output["links"]) == 1
    assert output["links"][0]["target_port_id"] is None
    assert (await fabric.snapshot(settings=SimpleNamespace(), now=1000))["state"] == "unconfigured"


@pytest.mark.parametrize("physical", [False, None, "true", 1])
def test_virtual_bond_and_unqualified_host_lldp_never_become_physical_cables(physical):
    observation = host_observation()
    observation["interfaces"][0]["physical"] = physical
    output = fabric.project(settings(targets=[]), {}, 1000, {HOST: observation})
    assert output["devices"] == [] and output["links"] == []
    # Raw advertised evidence remains available for the host diagnostic inspector.
    assert observation["lldp"][0]["port_id"] == "Ethernet7"


@pytest.mark.parametrize(
    "iftype,connector,physical",
    [(6, 1, True), (6, 2, False), (161, 1, False), (135, 1, False), (6, None, None), (None, 1, None)],
)
def test_switch_lag_virtual_and_unknown_counters_never_join_a_physical_cable(iftype, connector, physical):
    data = values()
    data[fabric.IF + (3, 7)] = iftype
    data[fabric.IFX + (17, 7)] = connector
    parsed = fabric.parse_sample(data, FabricSettings(), 1000)
    assert parsed.ports[0].physical is physical
    output = fabric.project(settings(), {"sw-1": record(parsed)}, 1000, {HOST: host_observation()})
    assert output["ports"][0]["physical"] is physical
    assert output["links"][0]["target_port_id"] == ("switch:sw-1:if:7" if physical is True else None)


def test_lldp_management_family_must_match_encoded_address_length():
    data = values()
    row = (42, 99, 1)
    remote = fabric.LLDP + (4, 1, 1)
    for column, value in ((4, 4), (5, bytes.fromhex("aabbccddeeff")), (6, 5), (7, b"Ethernet2")):
        data[remote + (column,) + row] = value
    data[fabric.LLDP + (4, 2, 1, 3) + row + (2, 4, 192, 0, 2, 1)] = 1
    assert fabric.parse_sample(data, FabricSettings(), 1000).neighbors[0].management_addresses == []


async def acquire(redis, config, owner="owner-a"):
    keys = fabric._keys(config)
    gen = fabric.generation(config)
    await redis.eval(fabric._REGISTER, 3, *keys, gen)
    assert await redis.eval(fabric._ACQUIRE, 2, *keys[:2], gen, owner, fabric.LEASE_SECONDS) == 1
    return keys, gen


@pytest.mark.asyncio
async def test_durable_rates_duplicates_failures_recovery_ttl_and_secret_safety():
    async with fakeredis.aioredis.FakeRedis() as redis:
        config = settings()
        keys, _ = await acquire(redis, config)
        reader = AsyncMock(return_value=sample())
        await fabric.collect_once(config, redis, "owner-a", reader=reader, now=1000)
        first = await fabric.snapshot(settings=config, redis=redis, now=1000)
        assert first["ports"][0]["reason"] == "first_sample"
        reader.return_value = sample(1010, 200)
        await fabric.collect_once(config, redis, "owner-a", reader=reader, now=1010)
        output = await fabric.snapshot(settings=config, redis=redis, now=1010)
        assert output["ports"][0]["rx_packets_per_second"] == 30
        raw = await redis.get(keys[2])
        assert b'"rx_bytes":"200"' in raw and b"only-test-auth-key" not in raw
        assert 0 < await redis.ttl(keys[2]) <= 3600
        await fabric.collect_once(config, redis, "owner-a", reader=reader, now=1010)
        output = await fabric.snapshot(settings=config, redis=redis, now=1010)
        assert output["coverage"]["error"] == "snmp_duplicate_sample"
        assert output["ports"][0]["rx_packets_per_second"] is None
        reader.side_effect = RuntimeError("secret=only-test-auth-key")
        await fabric.collect_once(config, redis, "owner-a", reader=reader, now=1020)
        output = await fabric.snapshot(settings=config, redis=redis, now=1020)
        assert "only-test-auth-key" not in json.dumps(output)
        assert output["coverage"]["error"] == "snmp_collector_error"
        reader.side_effect = None
        reader.return_value = sample(1020, 300)
        await fabric.collect_once(config, redis, "owner-a", reader=reader, now=1020)
        output = await fabric.snapshot(settings=config, redis=redis, now=1020)
        assert output["ports"][0]["rx_packets_per_second"] is None  # Failed interval is not bridged.


@pytest.mark.asyncio
async def test_generation_change_and_lease_takeover_reject_late_owner():
    async with fakeredis.aioredis.FakeRedis() as redis:
        config = settings()
        keys, gen = await acquire(redis, config)
        await fabric.collect_once(config, redis, "owner-a", reader=AsyncMock(return_value=sample()), now=1000)
        await redis.eval(fabric._RELEASE, 1, keys[1], "owner-a")
        assert await redis.eval(fabric._ACQUIRE, 2, *keys[:2], gen, "owner-b", 30) == 1
        with pytest.raises(fabric.LeaseLost):
            await fabric.collect_once(config, redis, "owner-a", reader=AsyncMock(return_value=sample(1010)), now=1010)
        await fabric.collect_once(config, redis, "owner-b", reader=AsyncMock(return_value=sample(1010)), now=1010)
        output = await fabric.snapshot(settings=config, redis=redis, now=1010)
        assert output["ports"][0]["reason"] == "collector_reset"
        changed = settings(targets=[target(auth_key="different-test-auth-key")], revision=2)
        assert fabric.generation(changed) != gen
        await redis.eval(fabric._REGISTER, 3, *keys, fabric.generation(changed))
        assert await redis.get(keys[2]) is None
        assert await redis.eval(fabric._RENEW, 2, *keys[:2], gen, "owner-b", 30) == 0
        with pytest.raises(fabric.LeaseLost):
            await fabric.collect_once(config, redis, "owner-b", reader=AsyncMock(return_value=sample(1020)), now=1020)
        assert (await fabric.snapshot(settings=config, redis=redis, now=1020))["state"] == "unavailable"


@pytest.mark.asyncio
async def test_disable_generation_revokes_previous_poller_without_native_import():
    async with fakeredis.aioredis.FakeRedis() as redis:
        config = settings()
        keys, gen = await acquire(redis, config)
        reader = AsyncMock(side_effect=AssertionError("disabled must not poll"))
        await fabric.monitoring_loop(settings=settings(targets=[], revision=2), redis=redis, reader=reader)
        assert await redis.get(keys[1]) is None
        assert await redis.eval(fabric._ACQUIRE, 2, *keys[:2], gen, "owner-a", 30) == -1
        reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_collector_concurrency_cancellation_drains_readers_and_releases_lease():
    targets = [target(id=f"sw-{n}", chassis_id=f"chassis-{n}", management_ip=f"192.0.2.{n + 10}") for n in range(4)]
    config = settings(targets=targets, concurrency=2)
    active = 0
    peak = 0
    entered = asyncio.Event()
    stopped = []

    async def reader(item, _):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 2:
            entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1
            stopped.append(item.id)

    async with fakeredis.aioredis.FakeRedis() as redis:
        task = asyncio.create_task(fabric.monitoring_loop(settings=config, redis=redis, reader=reader))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert peak == 2 and active == 0 and len(stopped) == 2
        assert await redis.get(fabric._keys(config)[1]) is None


@asynccontextmanager
async def native_agent(uptimes=None, closing=None):
    """Actual local authPriv UDP responder; no production/external network involved."""
    from pysnmp.carrier.asyncio.dgram import udp
    from pysnmp.entity import config, engine
    from pysnmp.entity.rfc3413 import cmdrsp, context
    from pysnmp.hlapi.v3arch import asyncio as snmp
    from pysnmp.proto import rfc1902, rfc1905

    native_values = {}
    for oid, value in values().items():
        if isinstance(value, bytes):
            native = rfc1902.OctetString(value)
        elif oid in (fabric.UPTIME,) or oid[: len(fabric.IFX) + 1] == fabric.IFX + (19,):
            native = rfc1902.TimeTicks(value)
        elif oid[: len(fabric.IFX)] == fabric.IFX and oid[len(fabric.IFX)] in range(6, 14):
            native = rfc1902.Counter64(value)
        else:
            native = rfc1902.Integer32(value)
        native_values[oid] = native
    native_values[fabric.IFX + (6, 7)] = rfc1902.Counter64(UINT64_MAX - 100)
    calls = []
    uptime_reads = iter(uptimes) if uptimes is not None else None

    class Instrumentation:
        def read_variables(self, *bindings, **_):
            calls.append("get")
            if uptime_reads is not None and any(tuple(name) == fabric.UPTIME for name, _ in bindings):
                native_values[fabric.UPTIME] = rfc1902.TimeTicks(next(uptime_reads))
            if closing is not None and calls.count("get") == 2:
                native_values.update(closing)
            return [(name, native_values.get(tuple(name), rfc1905.noSuchInstance)) for name, value in bindings]

        def read_next_variables(self, *bindings, **_):
            calls.append("next")
            result = []
            for name, value in bindings:
                next_oid = next((oid for oid in sorted(native_values) if oid > tuple(name)), None)
                result.append(
                    (rfc1902.ObjectName(next_oid), native_values[next_oid])
                    if next_oid
                    else (name, rfc1905.endOfMibView)
                )
            return result

    agent = engine.SnmpEngine()
    protocol = udp.UdpTransport().open_server_mode(("127.0.0.1", 0))
    config.add_transport(agent, udp.DOMAIN_NAME, protocol)
    config.add_v3_user(
        agent,
        "readonly-user",
        snmp.usmHMAC192SHA256AuthProtocol,
        "only-test-auth-key",
        snmp.usmAesCfb128Protocol,
        "only-test-priv-key",
    )
    config.add_vacm_user(agent, 3, "readonly-user", "authPriv", readSubTree=(1,))
    ctx = context.SnmpContext(agent)
    ctx.unregister_context_name(b"")
    ctx.register_context_name(b"", Instrumentation())
    responders = [cmdrsp.GetCommandResponder(agent, ctx), cmdrsp.BulkCommandResponder(agent, ctx)]
    try:
        await protocol._lport  # Native asyncio bind completion, no readiness sleep/race.
        port = protocol.transport.get_extra_info("sockname")[1]
        yield port, calls
    finally:
        for responder in responders:
            responder.close(agent)
        agent.close_dispatcher()


@pytest.mark.asyncio
async def test_native_snmpv3_authpriv_roundtrip_exact_hc_uint64_and_lldp():
    async with native_agent() as (port, calls):
        # Test-only loopback construction; production config rejects loopback management targets.
        local = target().model_copy(update={"management_ip": "127.0.0.1", "port": port})
        result = await fabric.read_snmp(local, FabricSettings(timeout_seconds=0.2, retries=0, poll_budget_seconds=5))
        assert abs(result.captured_at - time.time()) < 5
        assert result.ports[0].rx_bytes == str(UINT64_MAX - 100)
        assert result.ports[0].rx_packets == "300"
        assert result.chassis_id == CHASSIS
        assert result.local_ports[0].number == 99
        assert result.errors == []
        assert "get" in calls and "next" in calls


@pytest.mark.asyncio
async def test_native_snmp_bad_auth_fails_closed_with_safe_code():
    async with native_agent() as (port, _):
        local = target().model_copy(
            update={"management_ip": "127.0.0.1", "port": port, "username": "unregistered-user"}
        )
        with pytest.raises(fabric.PollError) as exc:
            await fabric.read_snmp(local, FabricSettings(timeout_seconds=0.1, retries=0, poll_budget_seconds=2))
        assert exc.value.code in {"snmp_authentication", "snmp_timeout"}
        assert "only-test" not in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("uptimes,accepted", [([2**32 - 50, 50], True), ([100000, 1], False)])
async def test_native_snmp_walk_uptime_wrap_and_reboot(uptimes, accepted):
    async with native_agent(uptimes) as (port, _):
        local = target().model_copy(update={"management_ip": "127.0.0.1", "port": port})
        config = FabricSettings(timeout_seconds=0.2, retries=0, poll_budget_seconds=5)
        if accepted:
            result = await fabric.read_snmp(local, config)
            assert result.uptime == uptimes[0]
            assert result.chassis_id == CHASSIS and result.ports[0].rx_bytes == str(UINT64_MAX - 100)
        else:
            with pytest.raises(fabric.PollError, match="snmp_stale_sample"):
                await fabric.read_snmp(local, config)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing_uptime", "wrong_uptime_type", "missing_boots", "engine_restart"])
async def test_native_snmp_walk_requires_closing_boot_continuity(failure):
    from pysnmp.proto import rfc1902, rfc1905

    closing = {
        "missing_uptime": {fabric.UPTIME: rfc1905.noSuchInstance},
        "wrong_uptime_type": {fabric.UPTIME: rfc1902.Integer32(100001)},
        "missing_boots": {fabric.BOOTS: rfc1905.noSuchInstance},
        "engine_restart": {fabric.UPTIME: rfc1902.TimeTicks(100100), fabric.BOOTS: rfc1902.Integer32(5)},
    }[failure]
    async with native_agent(closing=closing) as (port, _):
        local = target().model_copy(update={"management_ip": "127.0.0.1", "port": port})
        code = "snmp_stale_sample" if failure == "engine_restart" else "snmp_invalid_response"
        with pytest.raises(fabric.PollError, match=code):
            await fabric.read_snmp(local, FabricSettings(timeout_seconds=0.2, retries=0, poll_budget_seconds=5))


@pytest.mark.asyncio
async def test_inflight_generation_change_never_publishes_old_result():
    async with fakeredis.aioredis.FakeRedis() as redis:
        config = settings()
        keys, _ = await acquire(redis, config)
        started, resume = asyncio.Event(), asyncio.Event()

        async def reader(*_):
            started.set()
            await resume.wait()
            return sample()

        task = asyncio.create_task(fabric.collect_once(config, redis, "owner-a", reader=reader, now=1000))
        await asyncio.wait_for(started.wait(), 2)
        changed = settings(targets=[target(management_ip="192.0.2.20")], revision=2)
        await redis.eval(fabric._REGISTER, 3, *keys, fabric.generation(changed))
        resume.set()
        with pytest.raises(fabric.LeaseLost):
            await task
        assert await redis.get(keys[2]) is None


@pytest.mark.asyncio
async def test_corrupt_baseline_is_unknown_then_replaced_by_real_read():
    async with fakeredis.aioredis.FakeRedis() as redis:
        config = settings()
        keys, _ = await acquire(redis, config)
        await redis.set(keys[2], b"invalid-json-secret-must-not-leak")
        output = await fabric.snapshot(settings=config, redis=redis, now=1000)
        assert output["ports"] == []
        await fabric.collect_once(config, redis, "owner-a", reader=AsyncMock(return_value=sample()), now=1000)
        output = await fabric.snapshot(settings=config, redis=redis, now=1000)
        assert output["ports"][0]["reason"] == "first_sample"


@pytest.mark.asyncio
async def test_per_device_budget_cancels_stalled_source_and_reports_timeout():
    async with fakeredis.aioredis.FakeRedis() as redis:
        config = settings(poll_budget_seconds=1)
        await acquire(redis, config)
        stopped = asyncio.Event()

        async def reader(*_):
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        await asyncio.wait_for(fabric.collect_once(config, redis, "owner-a", reader=reader, now=1000), 3)
        output = await fabric.snapshot(settings=config, redis=redis, now=1000)
        assert stopped.is_set()
        assert output["coverage"]["error"] == "snmp_timeout"
        assert output["state"] == "unavailable" and output["ports"] == []


def test_two_configured_switches_join_only_actual_lldp_port_evidence():
    second_target = target(id="sw-2", name="Switch Two", chassis_id="aa:bb:cc:dd:ee:ff", management_ip="192.0.2.11")
    config = settings(targets=[second_target, target()])
    data = values()
    row = (100, 99, 1)
    remote = fabric.LLDP + (4, 1, 1)
    for column, value in ((4, 4), (5, bytes.fromhex("aabbccddeeff")), (6, 5), (7, b"Ethernet7")):
        data[remote + (column,) + row] = value
    first = fabric.parse_sample(data, config.monitoring_infrastructure_fabric, 1000)
    second = sample().model_copy(update={"chassis_id": second_target.chassis_id})
    output = fabric.project(config, {"sw-1": record(first), "sw-2": record(second)}, 1000)
    assert [device["id"] for device in output["devices"]] == ["switch:sw-1", "switch:sw-2"]
    assert len(output["links"]) == 1
    link = output["links"][0]
    assert link["source_port_id"] == "switch:sw-1:if:7"
    assert link["target_port_id"] == "switch:sw-2:if:7"
    assert (
        fabric._resolve_port("Ethernet7", [], [first.ports[0], first.ports[0].model_copy(update={"ifindex": 8})])
        is None
    )


def test_lldp_network_address_identifiers_are_decoded_not_probed():
    assert fabric._identifier(bytes([1, 192, 0, 2, 3]), 5) == "192.0.2.3"
    assert fabric._port_identifier(bytes([1, 192, 0, 2, 4]), 4) == "192.0.2.4"
    assert fabric._identifier(bytes([2, 192, 0, 2, 3]), 5) is None


@pytest.mark.asyncio
async def test_new_revision_then_late_old_runner_cannot_restore_retired_config():
    async with fakeredis.aioredis.FakeRedis() as redis:
        old = settings(revision=1)
        keys, old_gen = await acquire(redis, old)
        new = settings(targets=[target(auth_key="new-authoritative-auth-key")], revision=2)
        new_gen = fabric.generation(new)
        assert await redis.eval(fabric._REGISTER, 3, *keys, new_gen) == 1
        assert await redis.eval(fabric._ACQUIRE, 2, *keys[:2], new_gen, "owner-new", 30) == 1
        await fabric.collect_once(new, redis, "owner-new", reader=AsyncMock(return_value=sample()), now=1000)
        state = await redis.get(keys[2])
        assert await redis.eval(fabric._REGISTER, 3, *keys, old_gen) == -1
        assert await redis.eval(fabric._ACQUIRE, 2, *keys[:2], old_gen, "owner-old", 30) == -1
        reader = AsyncMock(side_effect=AssertionError("retired configuration must not poll"))
        await fabric.monitoring_loop(settings=old, redis=redis, reader=reader)
        reader.assert_not_awaited()
        assert (await redis.get(keys[0])).decode() == new_gen
        assert (await redis.get(keys[1])).decode() == "owner-new"
        assert await redis.get(keys[2]) == state
        conflicting = settings(targets=[target(management_ip="192.0.2.22")], revision=2)
        assert await redis.eval(fabric._REGISTER, 3, *keys, fabric.generation(conflicting)) == -1
        assert await redis.get(keys[2]) == state
        assert await redis.eval(fabric._REGISTER, 3, *keys, new_gen) == 1
        assert await redis.get(keys[2]) == state


def test_configured_sources_require_explicit_positive_authoritative_revision():
    with pytest.raises(ValidationError, match="revision"):
        FabricSettings(targets=[target()])
    with pytest.raises(ValidationError):
        FabricSettings(revision=JS_SAFE_MAX + 1)


@pytest.mark.asyncio
async def test_revision_change_prevents_queued_targets_from_starting_native_requests():
    async with fakeredis.aioredis.FakeRedis() as redis:
        targets = [target(), target(id="sw-2", chassis_id="second-chassis", management_ip="192.0.2.11")]
        old = settings(targets=targets, concurrency=1, revision=1)
        keys, _ = await acquire(redis, old)
        new = settings(targets=[], revision=2)
        calls = []

        async def reader(item, _):
            calls.append(item.id)
            assert await redis.eval(fabric._REGISTER, 3, *keys, fabric.generation(new)) == 1
            return sample()

        with pytest.raises(ExceptionGroup) as exc:
            await fabric.collect_once(old, redis, "owner-a", reader=reader, now=1000)
        assert exc.value.subgroup(fabric.LeaseLost) is not None
        assert calls == ["sw-1"]
        assert await redis.get(keys[2]) is None
