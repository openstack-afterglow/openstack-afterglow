"""Bounded read-only SNMPv3 authPriv polling and evidence-only LLDP joins.

Supported native API: pysnmp==7.1.22 (v3arch asyncio get_cmd/bulk_cmd), with
cryptography>=43 for AES privacy. Numeric OIDs avoid external MIB downloads.
Only configured literal management addresses ever become transport targets.
Redis stores uint64 counters as decimal strings, never Lua/JSON floating values.
"""

import asyncio
import hashlib
import ipaddress
import json
import logging
import math
import secrets
import time
from contextlib import suppress

from app.models.infrastructure_fabric import (
    JS_SAFE_MAX,
    UINT64_MAX,
    DeviceSample,
    FabricSettings,
    FabricSnapshot,
    LocalPort,
    PortSample,
    RemotePort,
    canonical_chassis,
)

logger = logging.getLogger(__name__)
COUNTERS = ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets")
MAX_STATE_BYTES = 24 * 1024 * 1024
LEASE_SECONDS = 30
IF = (1, 3, 6, 1, 2, 1, 2, 2, 1)
IFX = (1, 3, 6, 1, 2, 1, 31, 1, 1, 1)
LLDP = (1, 0, 8802, 1, 1, 2, 1)
UPTIME = (1, 3, 6, 1, 2, 1, 1, 3, 0)
BOOTS = (1, 3, 6, 1, 6, 3, 10, 2, 1, 2, 0)
ERRORS = frozenset(
    {
        "snmp_timeout",
        "snmp_authentication",
        "snmp_network_unreachable",
        "snmp_unsupported",
        "snmp_dependency_unavailable",
        "snmp_collector_error",
        "snmp_cardinality_exceeded",
        "snmp_invalid_response",
        "snmp_missing_counters",
        "snmp_missing_lldp",
        "snmp_missing_uptime",
        "snmp_identity_mismatch",
        "snmp_counter_overflow",
        "snmp_stale_sample",
        "snmp_duplicate_sample",
    }
)
_REGISTER = """
local incoming = tonumber(string.match(ARGV[1], '^(%d+):'))
if not incoming then return -1 end
local old = redis.call('GET', KEYS[1])
if old then
 local current = tonumber(string.match(old, '^(%d+):'))
 if not current or incoming < current then return -1 end
 if incoming == current then
  if old == ARGV[1] then return 1 end
  return -1
 end
end
redis.call('SET', KEYS[1], ARGV[1])
redis.call('DEL', KEYS[2], KEYS[3])
return 1
"""
_ACQUIRE = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return -1 end
if redis.call('SET', KEYS[2], ARGV[2], 'NX', 'EX', ARGV[3]) then return 1 end
return 0
"""
_RENEW = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] or redis.call('GET', KEYS[2]) ~= ARGV[2] then return 0 end
return redis.call('EXPIRE', KEYS[2], ARGV[3])
"""
_PUBLISH = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] or redis.call('GET', KEYS[2]) ~= ARGV[2] then return 0 end
redis.call('SET', KEYS[3], ARGV[3], 'EX', ARGV[4])
return 1
"""
_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""


class PollError(Exception):
    def __init__(self, code):
        self.code = code if code in ERRORS else "snmp_collector_error"
        super().__init__(self.code)


class LeaseLost(Exception):
    pass


def _config(settings):
    if isinstance(settings, FabricSettings):
        return settings
    return getattr(settings, "monitoring_infrastructure_fabric", None) or FabricSettings()


def _keys(settings):
    scope = [getattr(settings, name, "") for name in ("os_auth_url", "os_region_name", "os_project_name")]
    digest = hashlib.sha256(json.dumps(scope).encode()).hexdigest()[:24]
    base = f"afterglow:fabric:{{{digest}}}"
    return tuple(f"{base}:{suffix}" for suffix in ("generation", "lease", "state"))


def generation(settings):
    config = _config(settings)
    payload = config.model_dump(mode="json")
    # Include secret changes in the generation, but never persist the plaintext.
    for row, target in zip(payload["targets"], config.targets, strict=True):
        for key in ("auth_key", "priv_key"):
            row[key] = hashlib.sha256(getattr(target, key).get_secret_value().encode()).hexdigest()
    payload["targets"].sort(key=lambda row: row["id"])
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return f"{config.revision}:{digest}"


def device_id(target):
    return f"switch:{target.id}"


def _uint(value, maximum=UINT64_MAX):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= maximum else None


def _text(value):
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return None
    if not isinstance(value, str) or not value or len(value) > 128 or any(ord(c) < 32 for c in value):
        return None
    return value


def _network_identifier(value):
    if not isinstance(value, bytes) or not value or value[0] not in (1, 2):
        return None
    expected = 4 if value[0] == 1 else 16
    if len(value) != expected + 1:
        return None
    return str(ipaddress.ip_address(value[1:]))


def _identifier(value, subtype):
    if subtype == 4 and isinstance(value, bytes) and len(value) == 6:
        return value.hex(":")  # chassis subtype 4 is MAC; port MAC uses subtype 3.
    if subtype == 5:
        return _network_identifier(value)
    return canonical_chassis(_text(value) or "") or None


def _port_identifier(value, subtype):
    if subtype == 3 and isinstance(value, bytes) and len(value) == 6:
        return value.hex(":")
    if subtype == 4:
        return _network_identifier(value)
    return _text(value)


def _sum_counters(values):
    if any(_uint(value) is None for value in values):
        return None
    total = sum(values)
    return str(total) if total <= UINT64_MAX else None


def parse_sample(values, config, captured_at):
    """Decode bounded numeric-OID values. Missing/partial HC components stay null."""
    errors = set()
    indices = sorted({oid[-1] for oid in values if oid[: len(IF)] == IF and len(oid) == len(IF) + 2})
    if len(indices) > config.max_ports:
        raise PollError("snmp_cardinality_exceeded")
    ports = []
    for index in indices:
        if not 1 <= index <= 2**31 - 1 or _uint(values.get(IF + (1, index)), 2**31 - 1) != index:
            continue
        name = _text(values.get(IFX + (1, index)))
        if name is None:
            errors.add("snmp_invalid_response")
            continue  # Never invent an ifName from ifIndex/description.
        counts = {}
        for field, columns in (
            ("rx_bytes", (6,)),
            ("tx_bytes", (10,)),
            ("rx_packets", (7, 8, 9)),
            ("tx_packets", (11, 12, 13)),
        ):
            components = [values.get(IFX + (column, index)) for column in columns]
            counts[field] = _sum_counters(components)
            if counts[field] is None:
                errors.add("snmp_missing_counters")
                if all(_uint(value) is not None for value in components):
                    errors.add("snmp_counter_overflow")
        mac = values.get(IF + (6, index))
        iftype = _uint(values.get(IF + (3, index)), 2**31 - 1)
        connector = _uint(values.get(IFX + (17, index)), 2)
        physical = (
            True
            if iftype == 6 and connector == 1
            else False
            if (iftype is not None and iftype != 6) or connector == 2
            else None
        )
        ports.append(
            PortSample(
                ifindex=index,
                name=name,
                mac=mac.hex(":") if isinstance(mac, bytes) and len(mac) == 6 else None,
                physical=physical,
                operstate={1: "up", 2: "down"}.get(values.get(IF + (8, index)), "unknown"),
                discontinuity=_uint(values.get(IFX + (19, index)), 2**32 - 1),
                **counts,
            )
        )
        if ports[-1].discontinuity is None:
            errors.add("snmp_missing_counters")
    if not ports:
        errors.add("snmp_missing_counters")
    local_root = LLDP + (3, 7, 1)
    local_numbers = sorted(
        {oid[-1] for oid in values if oid[: len(local_root)] == local_root and len(oid) == len(local_root) + 2}
    )
    if len(local_numbers) > config.max_ports:
        raise PollError("snmp_cardinality_exceeded")
    local = []
    for number in local_numbers:
        subtype = values.get(local_root + (2, number))
        identifier = _port_identifier(values.get(local_root + (3, number)), subtype)
        if subtype in range(1, 8) and identifier and 1 <= number <= 2**31 - 1:
            local.append(
                LocalPort(
                    number=number,
                    subtype=subtype,
                    port_id=identifier,
                    description=_text(values.get(local_root + (4, number))),
                )
            )
    remote_root = LLDP + (4, 1, 1)
    rows = sorted(
        {oid[-3:] for oid in values if oid[: len(remote_root)] == remote_root and len(oid) == len(remote_root) + 4}
    )
    if len(rows) > config.max_neighbors:
        raise PollError("snmp_cardinality_exceeded")
    mgmt_root = LLDP + (4, 2, 1)
    management = {}
    for oid in values:
        if oid[: len(mgmt_root)] != mgmt_root:
            continue
        suffix = oid[len(mgmt_root) :]
        # column, timeMark, localPortNum, remIndex, addressSubtype, length, address octets
        if (
            len(suffix) < 7
            or suffix[4] not in (1, 2)
            or suffix[5] != len(suffix[6:])
            or suffix[5] != (4 if suffix[4] == 1 else 16)
        ):
            continue
        try:
            address = str(ipaddress.ip_address(bytes(suffix[6:])))
        except ValueError:
            continue
        addresses = management.setdefault(suffix[1:4], set())
        addresses.add(address)
        if len(addresses) > 8:
            raise PollError("snmp_cardinality_exceeded")
    neighbors = []
    for row in rows:
        chassis = _identifier(values.get(remote_root + (5,) + row), values.get(remote_root + (4,) + row))
        port = _port_identifier(values.get(remote_root + (7,) + row), values.get(remote_root + (6,) + row))
        if chassis and port and 1 <= row[1] <= 2**31 - 1:
            neighbors.append(
                RemotePort(
                    local_port=row[1],
                    chassis_id=chassis,
                    port_id=port,
                    system_name=_text(values.get(remote_root + (9,) + row)),
                    management_addresses=sorted(management.get(row, [])),
                )
            )
    chassis = _identifier(values.get(LLDP + (3, 2, 0)), values.get(LLDP + (3, 1, 0)))
    if chassis is None or not local:
        errors.add("snmp_missing_lldp")
    uptime = _uint(values.get(UPTIME), 2**32 - 1)
    if uptime is None:
        errors.add("snmp_missing_uptime")
    return DeviceSample(
        captured_at=captured_at,
        uptime=uptime,
        engine_boots=_uint(values.get(BOOTS), 2**31 - 1),
        chassis_id=chassis,
        ports=ports,
        local_ports=local,
        neighbors=neighbors,
        errors=sorted(errors),
    )


def _snmp_error(indication, status):
    # Inspect locally only; exceptions/agent strings must not reach logs or API.
    text = str(indication).lower()
    if any(word in text for word in ("auth", "user", "digest", "decrypt", "security", "unknownengine")):
        return "snmp_authentication"
    if "timeout" in text or "timed out" in text or "before timeout" in text:
        return "snmp_timeout"
    if any(word in text for word in ("unreachable", "route", "network")):
        return "snmp_network_unreachable"
    if status:
        return "snmp_unsupported"
    return "snmp_collector_error"


async def read_snmp(target, config):
    """Execute real SNMPv3 GET/GETBULK, never SET, with a total per-device deadline."""
    try:
        from pysnmp.hlapi.v3arch import asyncio as snmp
        from pysnmp.proto import rfc1902, rfc1905
    except ImportError:
        raise PollError("snmp_dependency_unavailable") from None
    engine = snmp.SnmpEngine(maxMessageSize=16384)
    values = {}
    records = 0
    try:
        async with asyncio.timeout(config.poll_budget_seconds):
            auth = snmp.UsmUserData(
                target.username,
                authKey=target.auth_key.get_secret_value(),
                privKey=target.priv_key.get_secret_value(),
                authProtocol={
                    "sha1": snmp.usmHMACSHAAuthProtocol,
                    "sha256": snmp.usmHMAC192SHA256AuthProtocol,
                    "sha384": snmp.usmHMAC256SHA384AuthProtocol,
                    "sha512": snmp.usmHMAC384SHA512AuthProtocol,
                }[target.auth_protocol],
                privProtocol=snmp.usmAesCfb128Protocol,
            )
            transport_type = (
                snmp.Udp6TransportTarget
                if ipaddress.ip_address(target.management_ip).version == 6
                else snmp.UdpTransportTarget
            )
            transport = await transport_type.create(
                (target.management_ip, target.port), timeout=config.timeout_seconds, retries=config.retries
            )
            context = snmp.ContextData(contextName=target.context_name)

            async def request(command, *args):
                result = await command(engine, auth, transport, context, *args, lookupMib=False)
                indication, status, _, bindings = result
                if indication or status:
                    raise PollError(_snmp_error(indication, status))
                if len(bindings) > 50:
                    raise PollError("snmp_cardinality_exceeded")
                return bindings

            def store(oid, value):
                nonlocal records
                records += 1
                if records > config.max_varbinds:
                    raise PollError("snmp_cardinality_exceeded")
                if isinstance(value, (rfc1905.NoSuchObject, rfc1905.NoSuchInstance, rfc1905.EndOfMibView)):
                    return False
                if oid in values:
                    raise PollError("snmp_invalid_response")
                if (
                    oid[: len(IFX)] == IFX
                    and len(oid) == len(IFX) + 2
                    and oid[len(IFX)] in range(6, 14)
                    and not isinstance(value, rfc1902.Counter64)
                ):
                    return True  # A 32-bit/vendor substitute is not a high-capacity counter.
                if isinstance(value, rfc1902.OctetString):
                    native = value.asOctets()
                    if len(native) > 256:
                        raise PollError("snmp_invalid_response")
                elif isinstance(
                    value,
                    (
                        rfc1902.Integer,
                        rfc1902.Integer32,
                        rfc1902.Counter32,
                        rfc1902.Counter64,
                        rfc1902.Gauge32,
                        rfc1902.TimeTicks,
                    ),
                ):
                    native = int(value)
                else:
                    return True  # Unneeded OID values are not retained.
                values[oid] = native
                return True

            opening = await request(
                snmp.get_cmd, *(snmp.ObjectType(snmp.ObjectIdentity(oid)) for oid in (UPTIME, BOOTS))
            )
            if (
                len(opening) != 2
                or tuple(opening[0][0]) != UPTIME
                or tuple(opening[1][0]) != BOOTS
                or not isinstance(opening[0][1], rfc1902.TimeTicks)
                or not isinstance(opening[1][1], rfc1902.Integer32)
                or int(opening[1][1]) < 0
            ):
                raise PollError("snmp_invalid_response")
            for oid, value in opening:
                store(tuple(oid), value)
            walk_started = time.monotonic()
            for root in (IF, IFX, LLDP):
                cursor = root
                finished = False
                while not finished:
                    bindings = await request(snmp.bulk_cmd, 0, 50, snmp.ObjectType(snmp.ObjectIdentity(cursor)))
                    if not bindings:
                        break
                    for oid, value in bindings:
                        numeric = tuple(oid)
                        if numeric[: len(root)] != root:
                            finished = True
                            break
                        if numeric <= cursor:
                            if isinstance(value, rfc1905.EndOfMibView):
                                finished = True
                                break
                            raise PollError("snmp_invalid_response")
                        cursor = numeric
                        if not store(numeric, value):
                            finished = True
                            break
            # A reboot during the multi-request walk invalidates its entire counter baseline.
            ending = await request(
                snmp.get_cmd, *(snmp.ObjectType(snmp.ObjectIdentity(oid)) for oid in (UPTIME, BOOTS))
            )
            if (
                len(ending) != 2
                or tuple(ending[0][0]) != UPTIME
                or tuple(ending[1][0]) != BOOTS
                or not isinstance(ending[0][1], rfc1902.TimeTicks)
                or not isinstance(ending[1][1], rfc1902.Integer32)
                or int(ending[1][1]) < 0
            ):
                raise PollError("snmp_invalid_response")
            end_uptime, end_boots = int(ending[0][1]), int(ending[1][1])
            if (
                end_boots != values[BOOTS]
                or (end_uptime - values[UPTIME]) % 2**32 / 100 > time.monotonic() - walk_started + 5
            ):
                raise PollError("snmp_stale_sample")
            sample = parse_sample(values, config, time.time())
            if sample.chassis_id is not None and sample.chassis_id != target.chassis_id:
                raise PollError("snmp_identity_mismatch")
            return sample
    except TimeoutError:
        raise PollError("snmp_timeout") from None
    except OSError:
        raise PollError("snmp_network_unreachable") from None
    finally:
        engine.close_dispatcher()  # Also closes cancelled requests' UDP transports/timers.


def port_rates(current, prior, sample, old, config):
    rates = dict.fromkeys(COUNTERS)
    elapsed = sample.captured_at - old.captured_at if old else 0
    uptime_delta = (
        (sample.uptime - old.uptime) % 2**32
        if old is not None and sample.uptime is not None and old.uptime is not None
        else None
    )
    reason = None
    if old is None or prior is None:
        reason = "first_sample"
    elif not 5 <= elapsed <= config.freshness_seconds:
        reason = "stale_sample"
    elif (
        uptime_delta is None
        or sample.engine_boots is None
        or old.engine_boots is None
        or current.discontinuity is None
        or prior.discontinuity is None
    ):
        reason = "collector_error"
    elif (
        uptime_delta == 0
        or sample.engine_boots != old.engine_boots
        or abs(uptime_delta / 100 - elapsed) > config.poll_budget_seconds + 5
        or current.name != prior.name
        or current.mac != prior.mac
        or current.physical != prior.physical
        or sample.chassis_id != old.chassis_id
    ):
        reason = "collector_reset"
    elif current.discontinuity != prior.discontinuity:
        reason = "counter_reset"
    if reason is not None:
        return rates, None, reason
    for field in COUNTERS:
        a, b = getattr(current, field), getattr(prior, field)
        if a is None or b is None:
            reason = reason or "collector_error"
            continue
        delta = int(a) - int(b)
        if delta < 0:
            return dict.fromkeys(COUNTERS), None, "counter_reset"
        # Compare exact integers before the division/float conversion.
        if delta > JS_SAFE_MAX or delta / elapsed > JS_SAFE_MAX:
            reason = "overflow"
            continue
        rates[field] = delta / elapsed
    return rates, elapsed if any(value is not None for value in rates.values()) else None, reason


def _decode_state(raw, config, expected_generation):
    if not raw:
        return {}
    if len(raw) > MAX_STATE_BYTES:
        raise ValueError("Oversized fabric state")
    decoded = json.loads(raw)
    if decoded.get("generation") != expected_generation:
        return {}
    devices = decoded.get("devices", {})
    if not isinstance(devices, dict) or len(devices) > len(config.targets):
        raise ValueError("Invalid fabric state")
    allowed = {target.id for target in config.targets}
    for key, record in devices.items():
        if key not in allowed or record.get("error") not in ERRORS | {None}:
            raise ValueError("Invalid fabric source")
        for field in ("sample", "previous"):
            if record.get(field) is not None:
                parsed = DeviceSample.model_validate(record[field])
                if (
                    len(parsed.ports) > config.max_ports
                    or len(parsed.local_ports) > config.max_ports
                    or len(parsed.neighbors) > config.max_neighbors
                ):
                    raise ValueError("Invalid fabric cardinality")
    return devices


async def collect_once(settings, redis, owner, *, reader=read_snmp, now=None):
    """One fenced collection cycle; injectable reader is only for behavioral tests."""
    config = _config(settings)
    keys = _keys(settings)
    gen = generation(settings)
    if not await redis.eval(_RENEW, 2, *keys[:2], gen, owner, LEASE_SECONDS):
        raise LeaseLost()
    raw = await redis.get(keys[2])  # Redis availability errors must still end ownership.
    try:
        previous = _decode_state(raw, config, gen)
    except (ValueError, TypeError, KeyError, AttributeError):
        previous = {}  # Replace a corrupt baseline only with real newly polled observations.
    semaphore = asyncio.Semaphore(config.concurrency)

    async def poll(target):
        record = previous.get(target.id, {})
        async with semaphore:
            if not await redis.eval(_RENEW, 2, *keys[:2], gen, owner, LEASE_SECONDS):
                raise LeaseLost()
            try:
                async with asyncio.timeout(config.poll_budget_seconds):
                    sample = DeviceSample.model_validate(await reader(target, config))
                if (
                    len(sample.ports) > config.max_ports
                    or len(sample.local_ports) > config.max_ports
                    or len(sample.neighbors) > config.max_neighbors
                ):
                    raise PollError("snmp_cardinality_exceeded")
                clock = time.time() if now is None else now
                if not 0 <= clock - sample.captured_at <= config.freshness_seconds:
                    raise PollError("snmp_stale_sample")
                if sample.chassis_id is not None and sample.chassis_id != target.chassis_id:
                    raise PollError("snmp_identity_mismatch")
                old = record.get("sample")
                if old and sample.captured_at <= old["captured_at"]:
                    raise PollError("snmp_duplicate_sample")
                # Error/lease gaps break adjacency rather than averaging a failed interval.
                same_collector = record.get("collector") == owner
                prior = old if record.get("error") is None and same_collector else None
                return target.id, {
                    "sample": sample.model_dump(),
                    "previous": prior,
                    "error": None,
                    "collector": owner,
                    "collector_reset": bool(old and not same_collector),
                }
            except (PollError, TimeoutError) as exc:
                error = exc.code if isinstance(exc, PollError) else "snmp_timeout"
            except Exception:
                error = "snmp_collector_error"
            return target.id, {
                "sample": record.get("sample"),
                "previous": None,
                "error": error,
                "collector": owner,
                "collector_reset": False,
            }

    async with asyncio.TaskGroup() as group:
        polls = [group.create_task(poll(target)) for target in config.targets]
    records = dict(task.result() for task in polls)
    encoded = json.dumps({"generation": gen, "devices": records}, allow_nan=False, separators=(",", ":"))
    if len(encoded.encode()) > MAX_STATE_BYTES:
        raise PollError("snmp_cardinality_exceeded")
    if not await redis.eval(_PUBLISH, 3, *keys, gen, owner, encoded, config.retention_seconds):
        raise LeaseLost()
    return records


async def monitoring_loop(*, settings=None, redis=None, reader=read_snmp):
    """App owns cancellation/await. A changed generation permanently retires old runners."""
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    config = _config(settings)
    keys, gen = _keys(settings), generation(settings)
    registered = False
    while True:
        tasks = []
        owner = secrets.token_hex(24)
        try:
            client = redis
            if client is None:
                from app.services.cache import _get_redis

                client = await _get_redis()
            if not registered:
                if await client.eval(_REGISTER, 3, *keys, gen) != 1:
                    return  # Older/restarted configurations cannot reactivate retired sources.
                registered = True
            if not config.targets:
                return  # Registering an empty generation revokes the previous configured runner.
            acquired = await client.eval(_ACQUIRE, 2, *keys[:2], gen, owner, LEASE_SECONDS)
            if acquired < 0:
                return  # Never reactivate obsolete credentials/configuration.
            if acquired:

                async def renew(client=client, owner=owner):
                    while True:
                        await asyncio.sleep(5)
                        if not await client.eval(_RENEW, 2, *keys[:2], gen, owner, LEASE_SECONDS):
                            raise LeaseLost()

                async def cycles(client=client, owner=owner):
                    while True:
                        started = time.monotonic()
                        await collect_once(settings, client, owner, reader=reader)
                        await asyncio.sleep(max(0, config.poll_interval_seconds - (time.monotonic() - started)))

                tasks = [asyncio.create_task(renew()), asyncio.create_task(cycles())]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
        except Exception:
            logger.warning("fabric: collection or shared coordination unavailable")
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if registered:
                with suppress(Exception):
                    await client.eval(_RELEASE, 1, keys[1], owner)
        await asyncio.sleep(config.poll_interval_seconds)


def _resolve_port(identifier, local_ports, ports):
    aliases = {identifier}
    for local in local_ports:
        if identifier in (local.port_id, local.description):
            aliases.update(value for value in (local.port_id, local.description) if value)
    matches = {port.ifindex: port for port in ports if port.name in aliases or port.mac in aliases}
    # LLDP localPortNum is NOT ifIndex. Logical/LAG counters are not a physical cable.
    if len(matches) == 1:
        port = next(iter(matches.values()))
        if port.physical is True:
            return port.ifindex
    return None


def _link(links, a, b, captured, fresh, port_a=None, port_b=None):
    ordered = sorted(((a, port_a), (b, port_b)), key=lambda pair: (pair[0]["id"], pair[0]["port"]))
    (source, source_port), (target, target_port) = ordered
    identity = json.dumps([source, target], sort_keys=True, separators=(",", ":"))
    key = "fabric-link:" + hashlib.sha256(identity.encode()).hexdigest()[:24]
    old = links.get(key)
    if old is None or captured > old["captured_at"]:
        links[key] = dict(
            id=key,
            source=source,
            target=target,
            captured_at=captured,
            state="fresh" if fresh else "stale",
            evidence="lldp",
            source_port_id=source_port,
            target_port_id=target_port,
        )


def project(settings, records, clock, host_observations=None, error=None):
    config = _config(settings)
    devices, ports, links, samples = {}, [], {}, {}
    by_chassis = {target.chassis_id: target for target in config.targets}
    failures = {error} if error else set()
    observed = []
    healthy = 0
    for target in sorted(config.targets, key=lambda item: item.id):
        record = records.get(target.id, {})
        sample = DeviceSample.model_validate(record["sample"]) if record.get("sample") else None
        old = DeviceSample.model_validate(record["previous"]) if record.get("previous") else None
        current_error = record.get("error")
        fresh = sample is not None and 0 <= clock - sample.captured_at <= config.freshness_seconds
        state = "error" if current_error else "fresh" if fresh else "stale" if sample else "unmeasured"
        devices[device_id(target)] = dict(
            id=device_id(target), name=target.name, chassis_id=target.chassis_id, state=state
        )
        if sample:
            observed.append(sample.captured_at)
            samples[target.id] = sample
            failures.update(sample.errors)
            prior_ports = {port.ifindex: port for port in old.ports} if old else {}
            for port in sample.ports:
                rates, window, reason = port_rates(port, prior_ports.get(port.ifindex), sample, old, config)
                if record.get("collector_reset") and reason == "first_sample":
                    reason = "collector_reset"
                if not fresh or current_error:
                    rates, window = dict.fromkeys(COUNTERS), None
                    reason = "collector_error" if current_error else "stale_sample"
                ports.append(
                    dict(
                        id=f"{device_id(target)}:if:{port.ifindex}",
                        device_id=device_id(target),
                        ifindex=port.ifindex,
                        name=port.name,
                        physical=port.physical,
                        captured_at=sample.captured_at,
                        state=state,
                        operstate=port.operstate,
                        window_seconds=window,
                        measurement="snmp_if_mib",
                        reason=reason,
                        **{field + "_per_second": rate for field, rate in rates.items()},
                    )
                )
        if current_error:
            failures.add(current_error)
        elif not fresh:
            failures.add("snmp_stale_sample" if sample else "snmp_unmeasured")
        elif not sample.errors:
            healthy += 1
    for target in config.targets:
        sample = samples.get(target.id)
        if sample is None or sample.chassis_id != target.chassis_id:
            continue
        locals_by_number = {port.number: port for port in sample.local_ports}
        for remote in sample.neighbors:
            other = by_chassis.get(remote.chassis_id)
            local = locals_by_number.get(remote.local_port)
            if other is None or other.id == target.id or local is None:
                continue  # No auto-targeting or graph inference from sysName/management IP.
            other_sample = samples.get(other.id)
            source_index = _resolve_port(local.port_id, sample.local_ports, sample.ports)
            target_index = (
                _resolve_port(remote.port_id, other_sample.local_ports, other_sample.ports) if other_sample else None
            )
            _link(
                links,
                dict(kind="switch", id=device_id(target), port=local.port_id),
                dict(kind="switch", id=device_id(other), port=remote.port_id),
                sample.captured_at,
                0 <= clock - sample.captured_at <= config.freshness_seconds,
                f"{device_id(target)}:if:{source_index}" if source_index else None,
                f"{device_id(other)}:if:{target_index}" if target_index else None,
            )
    registered_hosts = {
        identity.host_id for identity in getattr(settings, "monitoring_infrastructure_topology_observers", [])
    }
    for host_id, raw in sorted((host_observations or {}).items()):
        if host_id not in registered_hosts:
            continue
        report = raw.model_dump() if hasattr(raw, "model_dump") else raw
        if not isinstance(report, dict) or report.get("sources", {}).get("lldp") != "measured":
            continue
        captured = report.get("captured_at")
        if (
            not isinstance(captured, (int, float))
            or isinstance(captured, bool)
            or not math.isfinite(captured)
            or captured <= 0
            or captured > clock
        ):
            continue
        interfaces = {row["name"] for row in report.get("interfaces", []) if row.get("physical") is True}
        for neighbor in report.get("lldp", [])[:128]:
            chassis = canonical_chassis(neighbor.get("chassis_id", ""))
            remote_port = neighbor.get("port_id")
            if not chassis or not remote_port or neighbor.get("interface") not in interfaces:
                continue
            target = by_chassis.get(chassis)
            did = device_id(target) if target else "switch:lldp:" + hashlib.sha256(chassis.encode()).hexdigest()[:24]
            fresh = 0 <= clock - captured <= config.freshness_seconds
            if did not in devices:
                devices[did] = dict(
                    id=did,
                    name=neighbor.get("system_name") or chassis,
                    chassis_id=chassis,
                    state="fresh" if fresh else "stale",
                )
            elif target is None and fresh:
                devices[did]["state"] = "fresh"
            peer = samples.get(target.id) if target else None
            index = _resolve_port(remote_port, peer.local_ports, peer.ports) if peer else None
            _link(
                links,
                dict(kind="host", id=host_id, port=neighbor["interface"]),
                dict(kind="switch", id=did, port=remote_port),
                captured,
                fresh,
                None,
                f"{did}:if:{index}" if index else None,
            )
            observed.append(captured)
    state = (
        "unconfigured"
        if not config.targets
        else "available"
        if healthy == len(config.targets)
        else "partial"
        if any(device["state"] == "fresh" for device in devices.values())
        else "unavailable"
    )
    return FabricSnapshot.model_validate(
        dict(
            state=state,
            generated_at=clock,
            devices=sorted(devices.values(), key=lambda row: row["id"]),
            ports=sorted(ports, key=lambda row: row["id"]),
            links=sorted(links.values(), key=lambda row: row["id"]),
            coverage=dict(
                description="SNMPv3 IF-MIB HC counters and LLDP evidence; host NIC totals never substitute switch rates.",
                last_observed_at=max(observed) if observed else None,
                error=",".join(sorted(failures)) or None,
            ),
        )
    ).model_dump()


async def snapshot(*, settings=None, redis=None, now=None, host_observations=None):
    """Read shared durable observations only; API calls never start native polls."""
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    clock = time.time() if now is None else now
    config = _config(settings)
    if not config.targets:
        return project(settings, {}, clock, host_observations)
    try:
        if redis is None:
            from app.services.cache import _get_redis

            redis = await _get_redis()
        keys, gen = _keys(settings), generation(settings)
        active, raw = await redis.mget(keys[0], keys[2])
        active = active.decode() if isinstance(active, bytes) else active
        if active != gen:
            return project(settings, {}, clock, host_observations, "snmp_configuration_pending")
        records = _decode_state(raw, config, gen)
    except Exception:
        return project(settings, {}, clock, host_observations, "snmp_store_unavailable")
    return project(settings, records, clock, host_observations)
