"""Collector consumers and safety boundaries; no live network targets.

Native tests are explicit opt-in on Linux with native BCC and BPF authority.
BPF_PROG_TEST_RUN runs synthetic headers without attaching to any interface.
These authored tests are not evidence that a kernel collector has been run.
"""

from __future__ import annotations

import copy
import ctypes as ct
import importlib
import importlib.util
import ipaddress
import json
import os
import platform
import socket
import stat
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

DIRECTORY = Path(__file__).resolve().parents[2] / "scripts/flow_collector"
PACKAGE = "afterglow_test_flow_collector"
spec = importlib.util.spec_from_file_location(
    PACKAGE, DIRECTORY / "__init__.py", submodule_search_locations=[str(DIRECTORY)]
)
package = importlib.util.module_from_spec(spec)
sys.modules[PACKAGE] = package
spec.loader.exec_module(package)
collector = importlib.import_module(PACKAGE + ".collector")
security = importlib.import_module(PACKAGE + ".security")
HOST = "compute:local"
PEER = "controller:peer"
THIRD = "storage:third"


def config():
    return {
        "host_id": HOST,
        "hosts": [
            {"id": HOST, "addresses": ["192.0.2.10", "2001:db8::10"]},
            {"id": PEER, "addresses": ["192.0.2.20", "2001:db8::20"]},
            {"id": THIRD, "addresses": ["192.0.2.30", "2001:db8::30"]},
        ],
        "interfaces": [{"name": "enp2s0", "ifindex": 2, "mac": "02:00:00:00:00:10"}],
        "interval_seconds": 5,
    }


def test_config_exact_addresses_stable_indices_and_host32_addresses():
    value = config()
    value["hosts"][0]["addresses"] = [f"2001:db8:1::{index:x}" for index in range(1, 33)]
    validated = collector.validate_config(value)
    assert len(next(host for host in validated["hosts"] if host["id"] == HOST)["addresses"]) == 32
    assert [host["id"] for host in validated["hosts"]] == sorted([HOST, PEER, THIRD])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(host_id="network:bad"),
        lambda value: value.update(host_id="compute:absent"),
        lambda value: value.update(interval_seconds=True),
        lambda value: value.update(interval_seconds=float("nan")),
        lambda value: value.update(interval_seconds=11),
        lambda value: value.update(extra="not_allowed"),
        lambda value: value["hosts"].append(copy.deepcopy(value["hosts"][0])),
        lambda value: value["hosts"][1]["addresses"].append("2001:0db8:0:0:0:0:0:10"),
        lambda value: value["hosts"][0].update(addresses=["192.0.2.0/24"]),
        lambda value: value["hosts"][0].update(addresses=["::ffff:192.0.2.10"]),
        lambda value: value["hosts"][0].update(addresses=["fe80::1%enp2s0"]),
        lambda value: value["hosts"][0].update(addresses=["224.0.0.1"]),
        lambda value: value["hosts"][0].update(addresses=["127.0.0.1"]),
        lambda value: value["hosts"][0].update(addresses=["0.0.0.0"]),
        lambda value: value["hosts"][0].update(addresses=[f"2001:db8::{index:x}" for index in range(1, 34)]),
        lambda value: value["interfaces"].append(copy.deepcopy(value["interfaces"][0])),
        lambda value: value["interfaces"][0].update(name="../../eth0"),
        lambda value: value["interfaces"][0].update(ifindex=True),
        lambda value: value["interfaces"][0].update(mac="ff:ff:ff:ff:ff:ff"),
        lambda value: value.update(interfaces=value["interfaces"] * 9),
        lambda value: value.update(
            hosts=[{"id": f"compute:node-{index}", "addresses": [f"2001:db8::{index + 1:x}"]} for index in range(129)]
        ),
    ],
)
def test_config_rejects_unreviewed_or_ambiguous_scope(mutation):
    value = config()
    mutation(value)
    with pytest.raises(collector.FlowSnapshotError, match="invalid_config"):
        collector.validate_config(value)


def test_total_addresses_remain_bounded_even_with_valid_per_host_count():
    value = config()
    value["hosts"] = [
        {
            "id": HOST if node == 0 else f"compute:n-{node}",
            "addresses": [f"2001:db8:{node:x}::{address:x}" for address in range(1, 33)],
        }
        for node in range(33)
    ]
    with pytest.raises(collector.FlowSnapshotError, match="invalid_config"):
        collector.validate_config(value)


def physical_tree(root):
    interface = root / "class/net/enp2s0"
    interface.mkdir(parents=True)
    device = root / "devices/pci0000/0000:00:01.0"
    device.mkdir(parents=True)
    (interface / "device").symlink_to(device, target_is_directory=True)
    for name, value in {"ifindex": "2", "iflink": "2", "type": "1", "address": "02:00:00:00:00:10"}.items():
        (interface / name).write_text(value)
    return interface


def test_only_explicit_physical_port_is_qualified(tmp_path):
    interface = physical_tree(tmp_path)
    # Enslaved physical NIC is acceptable. The collector never attaches its
    # virtual bridge/bond master, so it cannot count both observation layers.
    (interface / "master").symlink_to(tmp_path / "class/net/bond0")
    result = collector.qualify_interfaces(collector.validate_config(config()), tmp_path)
    assert result == {2: ("enp2s0", str((interface / "device").resolve()))}


@pytest.mark.parametrize("kind", ["virtual", "bridge", "bond", "vlan", "changed_mac", "changed_index", "non_ethernet"])
def test_rejects_duplicate_or_replaced_observation_points(tmp_path, kind):
    interface = physical_tree(tmp_path)
    if kind == "virtual":
        (interface / "device").unlink()
    elif kind == "bridge":
        (interface / "bridge").mkdir()
    elif kind == "bond":
        (interface / "bonding").mkdir()
    else:
        key, value = {
            "vlan": ("iflink", "99"),
            "changed_mac": ("address", "02:00:00:00:00:99"),
            "changed_index": ("ifindex", "99"),
            "non_ethernet": ("type", "772"),
        }[kind]
        (interface / key).write_text(value)
    with pytest.raises(collector.FlowSnapshotError, match="interface_not_qualified"):
        collector.qualify_interfaces(collector.validate_config(config()), tmp_path)


class Address6(ct.Structure):
    _fields_ = [("bytes", ct.c_ubyte * 16)]


class Map:
    def __init__(self, key=ct.c_uint, leaf=ct.c_uint):
        self.Key, self.Leaf, self.values = key, leaf, {}

    def __setitem__(self, key, value):
        self.values[bytes(key)] = value.value


def test_ipv4_ipv6_map_keys_are_exact_and_same_host_index():
    bpf = {"addresses4": Map(), "addresses6": Map(Address6), "interfaces": Map()}
    value = collector.validate_config(config())
    nodes = collector.install_address_maps(bpf, value)
    local = next(index for index, host in nodes.items() if host == HOST)
    assert bpf["addresses4"].values[ipaddress.ip_address("192.0.2.10").packed] == local
    assert bpf["addresses6"].values[ipaddress.ip_address("2001:db8::10").packed] == local
    assert len(bpf["addresses4"].values) == len(bpf["addresses6"].values) == 3
    assert bpf["interfaces"].values == {bytes(ct.c_uint(2)): 1}


@pytest.fixture
def linux_socket_constants(monkeypatch):
    # Fake factories below need Linux constants even on macOS test runners.
    monkeypatch.setattr(socket, "AF_PACKET", 17, raising=False)
    monkeypatch.setattr(socket, "SOCK_CLOEXEC", 0x80000, raising=False)


def test_socket_filter_installed_and_locked_before_receive_binding(linux_socket_constants):
    events = []

    class Socket:
        def setsockopt(self, *arguments):
            events.append(("option", arguments))

        def bind(self, address):
            events.append(("bind", address))

        def close(self):
            events.append(("close",))

    def factory(*arguments):
        events.append(("socket", arguments))
        return Socket()

    collector.open_observation_socket("enp2s0", 123, factory)
    assert events == [
        ("socket", (socket.AF_PACKET, socket.SOCK_RAW | socket.SOCK_CLOEXEC, 0)),
        ("option", (socket.SOL_SOCKET, 50, struct.pack("I", 123))),
        ("option", (socket.SOL_SOCKET, 44, 1)),
        ("bind", ("enp2s0", 3)),
    ]


def test_failed_attach_closes_unbound_socket(linux_socket_constants):
    events = []

    class Socket:
        def setsockopt(self, *arguments):
            raise OSError("denied")

        def close(self):
            events.append("closed")

    with pytest.raises(OSError):
        collector.open_observation_socket("enp2s0", 3, lambda *args: Socket())
    assert events == ["closed"]


class LossMap:
    Key = ct.c_uint

    def __init__(self, *flags):
        self.flags = flags

    def __getitem__(self, key):
        assert key.value == 0
        return self.flags


class CounterMap:
    def __init__(self, entries):
        self.entries = entries

    def items(self):
        return iter(self.entries)


def map_row(source=2, target=1, ifindex=2, direction=0, packets=3, octets=300):
    return SimpleNamespace(source=source, target=target, ifindex=ifindex, direction=direction), [
        SimpleNamespace(packets=packets, bytes=octets)
    ]


def sample(entries, *flags):
    return collector.read_maps(
        {"counters": CounterMap(entries), "dropped": LossMap(*flags)},
        nodes={1: HOST, 2: PEER, 3: THIRD},
        interfaces={2: ("enp2s0", "/sys/devices/pci")},
        host_id=HOST,
        collector_id="boot:instance",
        captured_at=100,
    )


def test_cpu_aggregation_preserves_uint64_and_direction_separation():
    ingress = map_row(packets=2**53 + 1)
    ingress[1].append(SimpleNamespace(packets=2, bytes=100))
    result = sample([map_row(source=1, target=2, direction=1, packets=1), ingress], 0, 0)
    assert result["overflow"] is False
    assert {row["direction"] for row in result["rows"]} == {"ingress", "egress"}
    row = next(row for row in result["rows"] if row["direction"] == "ingress")
    assert row["packets"] == str(2**53 + 3)
    assert row["bytes"] == "400"
    assert set(result) == {"collector_id", "captured_at", "overflow", "rows"}


def test_aggregate_uint64_overflow_and_kernel_drop_are_explicit():
    entry = map_row(packets=security.MAX_COUNTER, octets=security.MAX_COUNTER)
    entry[1].append(SimpleNamespace(packets=1, bytes=1))
    result = sample([entry], 0)
    assert result["overflow"] is True
    assert result["rows"][0]["packets"] == str(security.MAX_COUNTER)
    assert result["rows"][0]["bytes"] == str(security.MAX_COUNTER)
    assert sample([], 0, 1)["overflow"] is True


@pytest.mark.parametrize(
    "entry",
    [
        map_row(source=2, target=3),
        map_row(source=99),
        map_row(ifindex=3),
        map_row(direction=2),
        map_row(packets=-1),
        map_row(source=1, target=2),
        map_row(source=2, target=1, direction=1),
        map_row(source=1, target=1),
    ],
)
def test_map_reader_never_invents_unknown_endpoints_or_zero(entry):
    with pytest.raises(collector.FlowSnapshotError, match="map_read_failed"):
        sample([entry], 0)


def test_duplicate_map_keys_fail_and_cardinality_loss_is_marked():
    with pytest.raises(collector.FlowSnapshotError, match="map_read_failed"):
        sample([map_row(), map_row()], 0)
    # A corrupt map/table reporting more than its native limit is explicit loss,
    # not an unbounded read. Unique extra interfaces are supplied to the reader.
    entries = [map_row(ifindex=index) for index in range(1, 1026)]
    result = collector.read_maps(
        {"counters": CounterMap(entries), "dropped": LossMap(0)},
        nodes={1: HOST, 2: PEER},
        interfaces={index: (f"eth{index}", "/sys/devices/test") for index in range(1, 1026)},
        host_id=HOST,
        collector_id="boot:instance",
        captured_at=100,
    )
    assert len(result["rows"]) == 1024
    assert result["overflow"] is True


def test_oversized_handoff_reports_loss_without_partial_valid_subset():
    snapshot = sample([map_row()], 0)
    snapshot["rows"] = [
        {**snapshot["rows"][0], "source_host_id": "compute:" + "x" * 253, "target_host_id": "controller:" + "y" * 253}
        for _ in range(1024)
    ]
    encoded = collector.encode_handoff(snapshot)
    decoded = json.loads(encoded)
    assert len(encoded) <= 256 * 1024
    assert decoded == {"collector_id": "boot:instance", "captured_at": 100, "overflow": True, "rows": []}


@pytest.mark.parametrize("data", [b'{"host_id":1,"host_id":2}', b'{"value":NaN}', b'{"value":Infinity}', b"\xff"])
def test_protected_json_rejects_ambiguous_or_nonfinite_input(data):
    with pytest.raises(security.FlowSnapshotError, match="invalid_json"):
        security.decode_json(data)


def test_secure_walk_rejects_writable_ancestor_even_when_leaf_is_protected(tmp_path):
    tmp_path.chmod(0o700)
    # /tmp is writable, and macOS /tmp is a symlink: both are rejected regardless
    # of the test runner's uid. Production inputs must use /etc, output /run.
    with pytest.raises((security.FlowSnapshotError, OSError)):
        security.secure_directory(tmp_path)


def test_protected_file_rejects_symlink_fifo_bad_owner_and_bad_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(security, "secure_directory", lambda path: os.open(path, os.O_RDONLY | os.O_DIRECTORY))
    path = tmp_path / "config.json"
    path.write_text("{}")
    path.chmod(0o600)
    actual_fstat = os.fstat

    def root_stat(fd):
        value = actual_fstat(fd)
        return SimpleNamespace(st_mode=value.st_mode, st_uid=0, st_nlink=value.st_nlink, st_size=value.st_size)

    monkeypatch.setattr(security.os, "fstat", root_stat)
    assert security.protected_read(path, mode=0o600) == b"{}"
    path.chmod(0o644)
    with pytest.raises(security.FlowSnapshotError, match="unsafe_file"):
        security.protected_read(path, mode=0o600)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(security.FlowSnapshotError, match="snapshot_unavailable"):
        security.protected_read(link, mode=0o600)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(security.FlowSnapshotError, match="unsafe_file"):
        security.protected_read(fifo, mode=0o600)
    monkeypatch.setattr(security.os, "fstat", actual_fstat)
    monkeypatch.setattr(
        security.os,
        "fstat",
        lambda fd: SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=123, st_nlink=1, st_size=2),
    )
    with pytest.raises(security.FlowSnapshotError, match="unsafe_file"):
        security.protected_read(path, mode=0o600)


def test_publisher_atomic_replacement_permissions_and_single_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "secure_directory", lambda path: os.open(path, os.O_RDONLY | os.O_DIRECTORY))
    actual_fstat = os.fstat

    def root_group_stat(fd):
        value = actual_fstat(fd)
        return SimpleNamespace(st_mode=value.st_mode, st_uid=0, st_gid=456, st_nlink=value.st_nlink)

    tmp_path.chmod(0o750)
    monkeypatch.setattr(collector.os, "fstat", root_group_stat)
    monkeypatch.setattr(collector.os, "getegid", lambda: 456)
    output = tmp_path / "snapshot.json"
    first = collector.Publisher(output)
    try:
        with pytest.raises(BlockingIOError):
            collector.Publisher(output)
        first.publish(sample([map_row()], 0))
        with output.open("rb") as prior:
            first.publish(sample([map_row(packets=7)], 0))
            assert json.load(prior)["rows"][0]["packets"] == "3"
        assert json.loads(output.read_text())["rows"][0]["packets"] == "7"
        assert stat.S_IMODE(output.stat().st_mode) == 0o640
        assert sorted(path.name for path in tmp_path.iterdir()) == ["collector.lock", "snapshot.json"]
    finally:
        first.close()
    with pytest.raises(collector.FlowSnapshotError, match="unsafe_output_name"):
        collector.Publisher(tmp_path / "collector.lock")


NATIVE = pytest.mark.skipif(
    os.getenv("AFTERGLOW_FLOW_BPF_TEST") != "1", reason="explicit Linux native BCC/BPF test authority required"
)


class TestRun(ct.Structure):
    __test__ = False
    _fields_ = [
        ("prog_fd", ct.c_uint32),
        ("retval", ct.c_uint32),
        ("data_size_in", ct.c_uint32),
        ("data_size_out", ct.c_uint32),
        ("data_in", ct.c_uint64),
        ("data_out", ct.c_uint64),
        ("repeat", ct.c_uint32),
        ("duration", ct.c_uint32),
    ]


def native_run(fd, frame):
    syscall = {"x86_64": 321, "aarch64": 280}[platform.machine()]
    packet = ct.create_string_buffer(frame)
    attributes = TestRun(prog_fd=fd, data_size_in=len(frame), data_in=ct.addressof(packet), repeat=1)
    libc = ct.CDLL(None, use_errno=True)
    result = libc.syscall(ct.c_long(syscall), ct.c_int(10), ct.byref(attributes), ct.c_uint(ct.sizeof(attributes)))
    if result != 0:
        raise OSError(ct.get_errno(), "BPF_PROG_TEST_RUN failed")
    assert attributes.retval == 0  # no packet bytes returned by the actual filter


def ethernet(source, target, *, version=4, tags=0, broadcast=False):
    protocol = 0x0800 if version == 4 else 0x86DD
    if version == 4:
        header = struct.pack(
            "!BBHHHBBH4s4s",
            0x45,
            0,
            20,
            0,
            0,
            64,
            6,
            0,
            ipaddress.ip_address(source).packed,
            ipaddress.ip_address(target).packed,
        )
    else:
        header = struct.pack(
            "!IHBB16s16s", 6 << 28, 0, 59, 64, ipaddress.ip_address(source).packed, ipaddress.ip_address(target).packed
        )
    vlan = b""
    for _ in range(tags):
        vlan = struct.pack("!HH", 1, protocol) + vlan
        protocol = 0x8100
    destination = b"\xff" * 6 if broadcast else b"\0" * 6  # loopback device in test-run
    return (destination + b"\x02\0\0\0\0\x01" + struct.pack("!H", protocol) + vlan + header).ljust(64, b"\0")


@pytest.fixture
def native_bpf():
    assert sys.platform == "linux", "native opt-in requires Linux"
    from bcc import BPF

    value = collector.validate_config(config())
    value["interfaces"][0]["ifindex"] = 1  # test-run's loopback context; never attached
    local = next(index for index, host in enumerate(value["hosts"], 1) if host["id"] == HOST)
    bpf = BPF(text=(DIRECTORY / "flow_filter.c").read_text(), cflags=[f"-DLOCAL_NODE={local}"])
    nodes = collector.install_address_maps(bpf, value)
    function = bpf.load_func("count_headers", BPF.SOCKET_FILTER)
    try:
        yield bpf, function.fd, nodes
    finally:
        bpf.cleanup()


@NATIVE
def test_native_socket_filter_registered_ipv4_ipv6_vlan_and_nonlocal_exclusion(native_bpf):
    bpf, fd, nodes = native_bpf
    measured = [
        ethernet("192.0.2.20", "192.0.2.10"),
        ethernet("192.0.2.20", "192.0.2.10", tags=1),
        ethernet("192.0.2.20", "192.0.2.10", tags=2),
        ethernet("2001:db8::20", "2001:db8::10", version=6),
        ethernet("2001:db8::20", "2001:db8::10", version=6, broadcast=True),
    ]
    for frame in measured:
        native_run(fd, frame)
    for frame in [
        ethernet("192.0.2.20", "192.0.2.30"),
        ethernet("192.0.2.99", "192.0.2.10"),
        ethernet("192.0.2.10", "192.0.2.20"),
        ethernet("192.0.2.10", "192.0.2.10"),
        ethernet("2001:db8::10", "2001:db8::20", version=6),
    ]:
        native_run(fd, frame)
    result = collector.read_maps(
        bpf,
        nodes=nodes,
        interfaces={1: ("lo", "test-run-only")},
        host_id=HOST,
        collector_id="boot:native",
        captured_at=100,
    )
    assert result["overflow"] is False
    assert sum(int(row["packets"]) for row in result["rows"]) == len(measured)
    # Linux test-run strips its synthetic Ethernet header before socket-filter
    # execution; MAC-relative reads still see it. Real AF_PACKET SOCK_RAW skb
    # length usually includes L2: neither is a physical-wire byte guarantee.
    assert sum(int(row["bytes"]) for row in result["rows"]) == sum(len(frame) - 14 for frame in measured)
    assert {row["direction"] for row in result["rows"]} == {"ingress"}
    assert {(row["source_host_id"], row["target_host_id"]) for row in result["rows"]} == {(PEER, HOST)}


@NATIVE
def test_native_uint64_wrap_and_non_lru_map_capacity_signal_loss(native_bpf):
    bpf, fd, nodes = native_bpf
    table = bpf["counters"]
    local = next(index for index, host in nodes.items() if host == HOST)
    peer = next(index for index, host in nodes.items() if host == PEER)
    key = table.Key(peer, local, 1, 0)
    values = table.Leaf()
    for value in values:
        value.packets = security.MAX_COUNTER
        value.bytes = security.MAX_COUNTER
    table[key] = values
    native_run(fd, ethernet("192.0.2.20", "192.0.2.10"))
    assert all(value.packets == security.MAX_COUNTER and value.bytes == security.MAX_COUNTER for value in table[key])
    loss = bpf["dropped"]
    assert any(loss[loss.Key(0)])
    table.clear()
    loss[loss.Key(0)] = loss.Leaf()
    # Fill native fixed map with synthetic keys; next genuine pair cannot evict.
    for index in range(1024):
        table[table.Key(peer, local, index + 2, 0)] = table.Leaf()
    native_run(fd, ethernet("192.0.2.20", "192.0.2.10"))
    assert len(table) == 1024
    assert any(loss[loss.Key(0)])


@NATIVE
def test_native_invalid_l3_and_excess_vlan_mark_loss_without_counters(native_bpf):
    bpf, fd, nodes = native_bpf
    invalid4 = bytearray(ethernet("192.0.2.20", "192.0.2.10"))
    invalid4[14] = 0x44  # Declared IHL is shorter than the fixed IPv4 header.
    invalid6 = bytearray(ethernet("2001:db8::20", "2001:db8::10", version=6))
    invalid6[14] = 0x40  # EtherType IPv6 but incorrect version nibble.
    losses = bpf["dropped"]
    for packet in (bytes(invalid4), bytes(invalid6), ethernet("192.0.2.20", "192.0.2.10", tags=3)):
        losses[losses.Key(0)] = losses.Leaf()
        native_run(fd, packet)
        assert any(losses[losses.Key(0)])
        assert len(bpf["counters"]) == 0
