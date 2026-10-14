#!/usr/bin/python3
"""Passive, explicitly scoped Linux skb header counters; no packet read loop.

Run with distro /usr/bin/python3 (python3-bpfcc), never a PyPI package named bcc.
Configuration is root-owned JSON; see config.example.json and install.sh.
"""
from __future__ import annotations

import argparse
import fcntl
import ipaddress
import json
import os
import re
import signal
import socket
import stat
import struct
import sys
import threading
import time
import uuid
from pathlib import Path

if __package__:
    from .security import (
        HOST_ID, INTERFACE, MAX_BYTES, MAX_COUNTER, MAX_ROWS, FlowSnapshotError,
        decode_json, protected_read, secure_directory,
    )
else:
    from security import (
        HOST_ID, INTERFACE, MAX_BYTES, MAX_COUNTER, MAX_ROWS, FlowSnapshotError,
        decode_json, protected_read, secure_directory,
    )

MAX_HOSTS = 128
MAX_ADDRESSES = 1024
MAX_INTERFACES = 8
MAC = re.compile(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")


def validate_config(value):
    try:
        if not isinstance(value, dict) or set(value) != {"host_id", "hosts", "interfaces", "interval_seconds"}:
            raise ValueError
        if not isinstance(value["host_id"], str) or not HOST_ID.fullmatch(value["host_id"]):
            raise ValueError
        interval = value["interval_seconds"]
        if type(interval) not in (float, int) or not 1 <= interval <= 10:
            raise ValueError
        hosts, interfaces = value["hosts"], value["interfaces"]
        if not isinstance(hosts, list) or not 1 <= len(hosts) <= MAX_HOSTS:
            raise ValueError
        if not isinstance(interfaces, list) or not 1 <= len(interfaces) <= MAX_INTERFACES:
            raise ValueError
        ids, addresses = set(), set()
        for host in hosts:
            if not isinstance(host, dict) or set(host) != {"id", "addresses"}:
                raise ValueError
            if not isinstance(host["id"], str) or not HOST_ID.fullmatch(host["id"]) or host["id"] in ids:
                raise ValueError
            ids.add(host["id"])
            if not isinstance(host["addresses"], list) or not 1 <= len(host["addresses"]) <= 32:
                raise ValueError
            canonical = []
            for raw in host["addresses"]:
                if not isinstance(raw, str) or len(raw) > 45 or "%" in raw:
                    raise ValueError
                address = ipaddress.ip_address(raw)
                if address.is_unspecified or address.is_multicast or address.is_loopback or address.is_link_local or getattr(address, "ipv4_mapped", None):
                    raise ValueError
                if address in addresses:
                    raise ValueError
                addresses.add(address)
                canonical.append(str(address))
            host["addresses"] = canonical
        if value["host_id"] not in ids or len(addresses) > MAX_ADDRESSES:
            raise ValueError
        names, indices = set(), set()
        for interface in interfaces:
            if not isinstance(interface, dict) or set(interface) != {"name", "ifindex", "mac"}:
                raise ValueError
            name, index, mac = interface["name"], interface["ifindex"], interface["mac"]
            if not isinstance(name, str) or not INTERFACE.fullmatch(name) or name in names:
                raise ValueError
            if type(index) is not int or not 1 <= index <= (1 << 31) - 1 or index in indices:
                raise ValueError
            if not isinstance(mac, str) or not MAC.fullmatch(mac) or int(mac[:2], 16) & 1 or mac == "00:00:00:00:00:00":
                raise ValueError
            names.add(name)
            indices.add(index)
        # Stable, bounded map indices; configuration edits require process restart.
        value["hosts"] = sorted(hosts, key=lambda host: host["id"])
        value["interfaces"] = sorted(interfaces, key=lambda interface: interface["name"])
        return value
    except (ValueError, TypeError, KeyError, OverflowError):
        raise FlowSnapshotError("invalid_config") from None


def qualify_interfaces(config, sys_root=Path("/sys")):
    """Validate reviewed identities, not discover or choose observation devices.

    A physical slave of a bond/bridge is allowed; its virtual master is not.
    iflink==ifindex also rejects veth/VLAN/tunnel aliases of a physical device.
    """
    result = {}
    try:
        for interface in config["interfaces"]:
            path = sys_root / "class/net" / interface["name"]
            if not (path / "device").exists() or not (path / "device").resolve().is_relative_to((sys_root / "devices").resolve()):
                raise ValueError
            if (path / "bridge").exists() or (path / "bonding").exists():
                raise ValueError
            if int((path / "type").read_text()) != 1:
                raise ValueError
            index = int((path / "ifindex").read_text())
            if index != interface["ifindex"] or int((path / "iflink").read_text()) != index:
                raise ValueError
            if (path / "address").read_text().strip().lower() != interface["mac"]:
                raise ValueError
            result[index] = (interface["name"], str((path / "device").resolve()))
        return result
    except (OSError, ValueError, TypeError, KeyError):
        raise FlowSnapshotError("interface_not_qualified") from None


def install_address_maps(bpf, config):
    nodes = {host["id"]: index for index, host in enumerate(config["hosts"], 1)}
    for host in config["hosts"]:
        for raw in host["addresses"]:
            address = ipaddress.ip_address(raw)
            if address.version == 4:
                table = bpf["addresses4"]
                key = table.Key(int.from_bytes(address.packed, sys.byteorder))
            else:
                table = bpf["addresses6"]
                key = table.Key()
                key.bytes[:] = address.packed
            table[key] = table.Leaf(nodes[host["id"]])
    table = bpf["interfaces"]
    for interface in config["interfaces"]:
        table[table.Key(interface["ifindex"])] = table.Leaf(1)
    return {index: host for host, index in nodes.items()}


def open_observation_socket(interface, program_fd, socket_factory=socket.socket):
    # Protocol zero receives NOTHING until the return-zero filter is installed.
    # Lock the filter before binding ETH_P_ALL; never recv(), send(), promiscuous
    # membership, TC, XDP, route, qdisc, offload or firewall changes.
    handle = socket_factory(socket.AF_PACKET, socket.SOCK_RAW | socket.SOCK_CLOEXEC, 0)
    try:
        handle.setsockopt(socket.SOL_SOCKET, 50, struct.pack("I", program_fd))  # SO_ATTACH_BPF
        handle.setsockopt(socket.SOL_SOCKET, 44, 1)  # SO_LOCK_FILTER
        handle.bind((interface, 3))  # ETH_P_ALL, Python sockaddr_ll host order
        return handle
    except BaseException:
        handle.close()
        raise


def read_maps(bpf, *, nodes, interfaces, host_id, collector_id, captured_at):
    """Read cumulative per-CPU maps, preserving uint64 exactly as decimal text.

    Each CPU has a monotonic counter. Summation is not a global packet-time atomic
    transaction; the short read window is part of Linux skb sampling semantics.
    """
    rows = []
    overflow = False
    seen = set()
    try:
        for key, values in bpf["counters"].items():
            if len(rows) >= MAX_ROWS:
                overflow = True
                break
            source, target = nodes[key.source], nodes[key.target]
            interface = interfaces[key.ifindex][0]
            if source == target or key.direction not in (0, 1):
                raise ValueError
            if (source if key.direction else target) != host_id:
                raise ValueError
            identity = (source, target, interface, key.direction)
            if identity in seen:
                raise ValueError
            seen.add(identity)
            packets, octets = 0, 0
            for value in values:
                if not 0 <= value.packets <= MAX_COUNTER or not 0 <= value.bytes <= MAX_COUNTER:
                    raise ValueError
                packets += value.packets
                octets += value.bytes
            if packets > MAX_COUNTER or octets > MAX_COUNTER:
                overflow = True
            rows.append({"source_host_id": source, "target_host_id": target, "interface": interface,
                         "direction": "egress" if key.direction else "ingress",
                         "packets": str(min(packets, MAX_COUNTER)), "bytes": str(min(octets, MAX_COUNTER))})
        # Read sticky kernel loss AFTER counters, so a full-map/overflow event
        # concurrent with sampling is not discarded as a successful zero sample.
        losses = bpf["dropped"]
        overflow |= any(int(flag) != 0 for flag in losses[losses.Key(0)])
    except (KeyError, TypeError, ValueError, OSError, OverflowError):
        raise FlowSnapshotError("map_read_failed") from None
    rows.sort(key=lambda row: (row["source_host_id"], row["target_host_id"], row["interface"], row["direction"]))
    return {"collector_id": collector_id, "captured_at": captured_at, "overflow": overflow, "rows": rows}


def encode_handoff(snapshot):
    data = json.dumps(snapshot, allow_nan=False, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if len(data) > MAX_BYTES:
        # Explicit loss, never truncate a set of apparently complete counters.
        data = json.dumps({**snapshot, "overflow": True, "rows": []}, allow_nan=False, separators=(",", ":")).encode("ascii")
    if len(data) > MAX_BYTES:
        raise FlowSnapshotError("snapshot_limit")
    return data


class Publisher:
    """Atomic root:reader-group 0640 JSON, one process, no pinned maps."""

    def __init__(self, output):
        self.directory = secure_directory(Path(output).parent)
        self.name = Path(output).name
        self.lock = None
        try:
            if not re.fullmatch(r"[A-Za-z0-9_-]+\.json", self.name):
                raise FlowSnapshotError("unsafe_output_name")
            info = os.fstat(self.directory)
            if info.st_gid != os.getegid() or stat.S_IMODE(info.st_mode) != 0o750 or os.getegid() == 0:
                raise FlowSnapshotError("unsafe_output_directory")
            self.lock = os.open("collector.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600, dir_fd=self.directory)
            lock_info = os.fstat(self.lock)
            if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != 0 or lock_info.st_nlink != 1 or stat.S_IMODE(lock_info.st_mode) != 0o600:
                raise FlowSnapshotError("unsafe_lock")
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.close()
            raise

    def publish(self, snapshot):
        data = encode_handoff(snapshot)
        name = ".snapshot-" + uuid.uuid4().hex
        fd = None
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self.directory)
            with os.fdopen(fd, "wb") as handle:
                fd = None
                handle.write(data)
                handle.flush()
                os.fchmod(handle.fileno(), 0o640)
                os.fsync(handle.fileno())
            os.replace(name, self.name, src_dir_fd=self.directory, dst_dir_fd=self.directory)
            os.fsync(self.directory)
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(name, dir_fd=self.directory)
            except FileNotFoundError:
                pass

    def close(self):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
        if self.directory is not None:
            os.close(self.directory)
            self.directory = None


def run(config_path, output, stop):
    if os.geteuid() != 0 or sys.platform != "linux":
        raise FlowSnapshotError("linux_root_required")
    config = validate_config(decode_json(protected_read(config_path, mode=0o600)))
    qualified = qualify_interfaces(config)
    boot_id = str(uuid.UUID(Path("/proc/sys/kernel/random/boot_id").read_text().strip()))
    collector_id = boot_id + ":" + str(uuid.uuid4())
    sockets = []
    bpf = None
    publisher = Publisher(output)
    try:
        from bcc import BPF  # Native distro BCC dependency, absent from observer.

        source = protected_read(Path(__file__).with_name("flow_filter.c"), mode=0o644).decode("ascii")
        local = next(index for index, host in enumerate(config["hosts"], 1) if host["id"] == config["host_id"])
        bpf = BPF(text=source, cflags=["-DLOCAL_NODE=" + str(local)])
        nodes = install_address_maps(bpf, config)
        function = bpf.load_func("count_headers", BPF.SOCKET_FILTER)
        for interface in config["interfaces"]:
            sockets.append(open_observation_socket(interface["name"], function.fd))
        while not stop.is_set():
            # Hotplug or a changed physical identity fails closed: old counters
            # must never acquire a replacement NIC's identity.
            if qualify_interfaces(config) != qualified:
                raise FlowSnapshotError("interface_changed")
            snapshot = read_maps(bpf, nodes=nodes, interfaces=qualified, host_id=config["host_id"],
                                 collector_id=collector_id, captured_at=time.time())
            publisher.publish(snapshot)
            stop.wait(config["interval_seconds"])
    finally:
        for handle in sockets:
            handle.close()
        if bpf is not None:
            bpf.cleanup()
        publisher.close()
        # The last handoff naturally expires after <=30s, including SIGKILL.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("/run/afterglow-flow/snapshot.json"))
    args = parser.parse_args(argv)
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda signum, frame: stop.set())
    try:
        run(args.config, args.output, stop)
    except FlowSnapshotError as exc:
        print("flow_collector: " + str(exc), file=sys.stderr)
        return 1
    except Exception:
        # BCC verifier/compiler/runtime stderr may contain host-specific details;
        # never log configuration or packet bytes in our own diagnostic output.
        print("flow_collector: native_collector_failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
