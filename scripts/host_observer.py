#!/usr/bin/env python3
"""Report actual Linux host network evidence to Afterglow (Python 3.12+, stdlib).

Usage:
  python3 scripts/host_observer.py --base-url https://console.example.org \
      --host-id compute:compute-01 --token-file /etc/afterglow/observer.token --once
  python3 scripts/host_observer.py --base-url https://console.example.org \
      --host-id compute:compute-01 --token-file /etc/afterglow/observer.token \
      --trace-target 192.0.2.1 --trace-target 2001:db8::1

The base URL is a verified HTTPS origin, optionally with a deployment path prefix;
API paths are appended to it. System CA trust is used, or --ca-file supplies a
trusted CA bundle. No insecure TLS option, HTTP redirect or proxy-env forwarding
is supported. Token files must be regular, nonsymlink, owned by the effective
process user and exactly mode 0600. HOST_OBSERVER_TOKEN is the alternative; child
commands never inherit it. There is deliberately no token argument.

Reads only existing iproute2 address/link/route/neighbour tables, /proc/net/dev,
/proc/sys/kernel/random/boot_id and installed lldpcli neighbour data. Never scans,
installs tools, captures packets, performs DNS target lookup or uses a shell.
Missing tools are unsupported; invalid, oversized or failed sources are errors,
not invented empty measurements. Counters are cumulative; the backend calculates
rates and reset/stale handling. Lists and command/HTTP output have hard bounds;
JSON input is limited to 64 nested objects/arrays before parsing.

Before reporting, authenticated polling supplies at most 64 operator-admitted
directed peer IP/port tuples. Exactly those tuples may be TCP-connected, without
DNS, authentication or payload: up to 8 workers, <=3 seconds each, <=8 seconds
per batch plus cleanup. Pending work becomes unknown, never peer-down. Admission
failure retains tuples for <=20 seconds as unknown only, never actively reprobes
cached admission. Target order rotates for coverage; no worker spills to another
cycle. Passive commands have a 1.5-second timeout and 256-KiB output cap. Clock
synchronization with the server is required for timestamp admission and rates.

Normal mode targets a 10-second cycle; slow sources/network can extend it without
overlap or catch-up bursts. A local 5-second counter-sample fence prevents rate
admission failures when one slow peer batch is followed by a fast batch. --once
reports and completes one available trace. Traces require BOTH server admission
and the explicit local literal-IP --trace-target allowlist. Installed Linux
traceroute must support -n/-q/-m/-w/-4/-6; incompatible variants return an error,
never install/fallback. One probe per hop, maximum 16 hops and a 40-second wall
deadline. Unknown '*' hops are not a failure location; only an unannotated target
reply in a completed command marks reached. The source NIC/next hop is the actual
ip -j route get result, not an inferred route match. One bounded trace worker
keeps passive reports and peer admission running without claiming another job
while busy. Shutdown waits for that worker's bounded command/result submission.
HTTPS socket operations are
bounded; OS DNS follows the host resolver timeout. Diagnostics are fixed codes
only, never tokens, URLs, response bodies or command output.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import errno
import http.client
import ipaddress
import json
import math
import os
import re
import selectors
import shutil
import signal
import socket
import ssl
import stat
import subprocess
import sys
import time
import urllib.parse
import uuid
from pathlib import Path

MAX_BYTES = 256 * 1024
MAX_JSON_DEPTH = 64
MAX_TOKEN_BYTES = 256
SAFE_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
COMMAND_TIMEOUT = 1.5
HTTP_TIMEOUT = 10.0
MIN_INTERVAL = 10.0
MAX_COUNTER = (1 << 64) - 1
PEER_TIMEOUT = 3.0
PEER_CYCLE_SECONDS = 8.0
PEER_CACHE_SECONDS = 20.0
MAX_SOURCE_INTERFACES = 4096
MAX_REPORT_INTERFACES = 64
VM_PORT_PREFIXES = ("tap", "qbr", "qvb", "qvo", "veth", "vnet", "tun")
HOST_ID_PATTERN = r"(?:compute|controller|storage):[a-z0-9][a-z0-9_.-]{0,252}"


class ObserverError(Exception):
    """Only fixed, non-sensitive codes may cross the CLI diagnostic boundary."""

    def __init__(self, code: str, output: bytes = b""):
        super().__init__(code)
        self.code = code
        self.output = output


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal message repeats unknown argv values (including secrets).
        raise ObserverError("invalid_arguments")


def text(value, limit: int, *, optional: bool = False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ObserverError("invalid_source")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ObserverError("invalid_source")
    return value


def interface_name(value):
    value = text(value, 32)
    if not re.fullmatch(r"[a-zA-Z0-9_.:@-]+", value):
        raise ObserverError("invalid_source")
    return value


def integer(value, maximum=MAX_COUNTER, *, optional=False):
    if value is None and optional:
        return None
    if type(value) is not int or not 0 <= value <= maximum:
        raise ObserverError("invalid_source")
    return value


def literal_ip(value):
    if not isinstance(value, str) or len(value) > 45 or "%" in value:
        raise ObserverError("invalid_source")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        raise ObserverError("invalid_source") from None


def rows(value, maximum):
    if not isinstance(value, list) or len(value) > maximum or not all(isinstance(row, dict) for row in value):
        raise ObserverError("invalid_source")
    return value


def decode_json(data: bytes):
    if len(data) > MAX_BYTES:
        raise ObserverError("output_limit")
    try:
        source = data.decode(json.detect_encoding(data), errors="surrogatepass")
        # Bound nesting before json.loads: its recursion limit is interpreter-
        # dependent, and delimiters inside escaped strings are not containers.
        depth, quoted, escaped = 0, False, False
        for char in source:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > MAX_JSON_DEPTH:
                    raise ValueError()
            elif char in "]}":
                depth -= 1
                if depth < 0:
                    raise ValueError()
        return json.loads(source, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError, RecursionError):
        raise ObserverError("invalid_source") from None


def encode_json(value) -> bytes:
    try:
        data = json.dumps(value, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, RecursionError):
        raise ObserverError("invalid_source") from None
    if len(data) > MAX_BYTES:
        raise ObserverError("output_limit")
    return data


def read_bounded(path: Path, maximum=MAX_BYTES) -> bytes:
    try:
        with path.open("rb") as handle:
            data = handle.read(maximum + 1)
    except OSError:
        raise ObserverError("source_unavailable") from None
    if len(data) > maximum:
        raise ObserverError("output_limit")
    return data


def load_token(token_file: Path | None) -> str:
    if token_file is None:
        token = os.environ.get("HOST_OBSERVER_TOKEN", "")
    else:
        try:
            descriptor = os.open(token_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
            with os.fdopen(descriptor, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid():
                    raise ObserverError("invalid_token_file")
                data = handle.read(MAX_TOKEN_BYTES + 2)
            # Permit one conventional final newline, never spaces or embedded lines.
            token = data.removesuffix(b"\n").decode("ascii")
        except (OSError, UnicodeError):
            raise ObserverError("invalid_token_file") from None
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token):
        raise ObserverError("invalid_token")
    return token


def validate_base_url(value: str):
    try:
        if not isinstance(value, str) or len(value) > 2048 or not value.isascii() or any(ord(c) <= 32 for c in value):
            raise ValueError
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
        if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ValueError
        if parsed.query or parsed.fragment or "\\" in value or (port is not None and not 1 <= port <= 65535):
            raise ValueError
        if not re.fullmatch(r"[A-Za-z0-9._~/-]*", parsed.path) or any(part in (".", "..") for part in parsed.path.split("/")):
            raise ValueError
        return parsed.hostname, port or 443, parsed.path.rstrip("/")
    except ValueError:
        raise ObserverError("invalid_base_url") from None


class ApiClient:
    def __init__(self, base_url: str, host_id: str, token: str, ca_file: str | None = None):
        self.host, self.port, prefix = validate_base_url(base_url)
        if not re.fullmatch(HOST_ID_PATTERN, host_id):
            raise ObserverError("invalid_host_id")
        self.path = prefix + "/api/v1/monitoring/host-observations/" + urllib.parse.quote(host_id, safe="")
        self.token = token
        try:
            self.context = ssl.create_default_context(cafile=ca_file)
        except (OSError, ssl.SSLError):
            raise ObserverError("invalid_ca_file") from None

    def request(self, method: str, suffix: str, payload=None):
        body = encode_json(payload) if payload is not None else None
        connection = http.client.HTTPSConnection(self.host, self.port, timeout=HTTP_TIMEOUT, context=self.context)
        deadline = time.monotonic() + HTTP_TIMEOUT
        try:
            connection.request(method, self.path + suffix, body=body, headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json", "Accept": "application/json",
            })
            response = connection.getresponse()
            # Never consume or repeat an error body, and never follow any redirect.
            if not 200 <= response.status < 300:
                raise ObserverError("http_status")
            output = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ObserverError("http_timeout")
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(8192, MAX_BYTES + 1 - len(output)))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > MAX_BYTES:
                    raise ObserverError("output_limit")
            return decode_json(bytes(output)) if output else None
        except TimeoutError:
            raise ObserverError("http_timeout") from None
        except (OSError, http.client.HTTPException, ssl.SSLError):
            raise ObserverError("http_failed") from None
        finally:
            connection.close()


def run_command(argv: list[str], timeout=COMMAND_TIMEOUT) -> bytes:
    """Bound stdout+stderr memory and wall time; kill the owned command group."""
    executable = shutil.which(argv[0], path=SAFE_PATH)
    if executable is None:
        raise ObserverError("command_missing")
    process = None
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        process = subprocess.Popen(
            [executable, *argv[1:]], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False,
            env={"PATH": SAFE_PATH, "LC_ALL": "C"}, start_new_session=True,
        )
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ObserverError("timeout", bytes(output))
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fd, min(8192, MAX_BYTES + 1 - len(output)))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    output.extend(chunk)
                    if len(output) > MAX_BYTES:
                        raise ObserverError("output_limit")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ObserverError("timeout", bytes(output))
            if process.wait(timeout=remaining) != 0:
                raise ObserverError("command_failed", bytes(output))
        return bytes(output)
    except subprocess.TimeoutExpired:
        raise ObserverError("timeout", bytes(output)) from None
    except OSError:
        raise ObserverError("command_failed") from None
    finally:
        if process is not None:
            # Kill before reaping on timeout/output failure, including a child
            # retaining a pipe. Never signal a process-group ID after it was
            # reaped successfully and could be reused by another process.
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            process.stdout.close()


def parse_interfaces(value, *, addresses=False):
    result = {}
    for row in rows(value, MAX_SOURCE_INTERFACES):
        name = interface_name(row.get("ifname"))
        if name in result:
            raise ObserverError("invalid_source")
        item = {
            "name": name, "mac": text(row.get("address"), 64, optional=True),
            "operstate": text(row.get("operstate", "unknown"), 24),
            "ifindex": integer(row.get("ifindex"), (1 << 31) - 1, optional=True),
            "addresses": [], "rx_bytes": None, "tx_bytes": None, "rx_packets": None, "tx_packets": None,
        }
        if item["ifindex"] == 0:
            raise ObserverError("invalid_source")
        if addresses:
            for address in rows(row.get("addr_info", []), 32):
                ip = literal_ip(address.get("local"))
                prefix = integer(address.get("prefixlen"), 32 if ":" not in ip else 128)
                item["addresses"].append(f"{ip}/{prefix}")
        result[name] = item
    return result


def parse_neighbors(value):
    result = []
    for row in rows(value, 256):
        state = row.get("state", "unknown")
        if isinstance(state, list):
            if len(state) > 8:
                raise ObserverError("invalid_source")
            state = ",".join(text(entry, 24) for entry in state) or "unknown"
        result.append({"interface": interface_name(row.get("dev")), "ip": literal_ip(row.get("dst")),
                       "mac": text(row.get("lladdr"), 64, optional=True), "state": text(state, 32)})
    return result


def parse_routes(value):
    result = []
    for row in rows(value, 256):
        # Local/blackhole/unreachable entries have no selected NIC; do not invent one.
        if "dev" not in row:
            continue
        destination = row.get("dst", "default")
        if destination != "default":
            try:
                destination = str(ipaddress.ip_network(text(destination, 49), strict=False))
            except ValueError:
                raise ObserverError("invalid_source") from None
        gateway = row.get("gateway")
        result.append({"interface": interface_name(row["dev"]), "destination": destination,
                       "gateway": literal_ip(gateway) if gateway is not None else None,
                       "metric": integer(row.get("metric"), (1 << 32) - 1, optional=True)})
    return result


def parse_counters(data: bytes):
    try:
        lines = data.decode("ascii").splitlines()
        if len(lines) < 2 or "Receive" not in lines[0] or "Transmit" not in lines[0]:
            raise ValueError
        result = {}
        for line in lines[2:]:
            name, numbers = line.rsplit(":", 1)
            name = interface_name(name.strip())
            values = numbers.split()
            if len(values) != 16 or name in result or len(result) >= 64:
                raise ValueError
            parsed = [integer(int(number)) for number in values]
            result[name] = dict(zip(("rx_bytes", "rx_packets", "tx_bytes", "tx_packets"),
                                    (parsed[0], parsed[1], parsed[8], parsed[9]), strict=True))
        return result
    except (UnicodeError, ValueError):
        raise ObserverError("invalid_source") from None


def parse_lldp(value):
    try:
        interfaces = value["lldp"].get("interface", [])
    except (KeyError, TypeError, AttributeError):
        raise ObserverError("invalid_source") from None
    if isinstance(interfaces, dict):
        interfaces = [{key: item} for key, item in interfaces.items()]
    result = []
    for group in rows(interfaces, 128):
        if len(group) != 1:
            raise ObserverError("invalid_source")
        interface, neighbors = next(iter(group.items()))
        interface_name(interface)
        if not isinstance(neighbors, list):
            neighbors = [neighbors]
        for neighbor in rows(neighbors, 128):
            if len(result) >= 128:
                raise ObserverError("invalid_source")
            try:
                chassis = neighbor["chassis"]
                if "id" not in chassis:
                    if len(chassis) != 1:
                        raise ValueError
                    chassis = next(iter(chassis.values()))
                port = neighbor["port"]
                result.append({"interface": interface, "chassis_id": text(chassis["id"]["value"], 128),
                               "port_id": text(port["id"]["value"], 128),
                               "system_name": text(chassis.get("name"), 128, optional=True)})
            except (KeyError, TypeError, ValueError, AttributeError):
                raise ObserverError("invalid_source") from None
    return result


def source(command, parser):
    try:
        return parser(decode_json(run_command(command))), "measured"
    except ObserverError as exc:
        return None, "unsupported" if exc.code == "command_missing" else "error"


def interface_priority(name, sys_root=Path("/sys")):
    """Physical NICs first, then bonds/VLANs/bridges, then per-VM ports."""
    try:
        if (sys_root / "class/net" / name / "device").exists():
            return 0
    except OSError:
        pass
    return 2 if name.startswith(VM_PORT_PREFIXES) else 1


def capture_report(proc_root=Path("/proc"), sys_root=Path("/sys")):
    boot = read_bounded(proc_root / "sys/kernel/random/boot_id", 65).strip()
    try:
        boot_id = str(uuid.UUID(boot.decode("ascii")))
    except (ValueError, UnicodeError):
        raise ObserverError("source_unavailable") from None
    links, link_state = source(["ip", "-j", "link", "show"], parse_interfaces)
    addresses, address_state = source(["ip", "-j", "address", "show"], lambda value: parse_interfaces(value, addresses=True))
    neighbors, neighbor_state = source(["ip", "-j", "neigh", "show"], parse_neighbors)
    routes, route_state = source(["ip", "-j", "route", "show", "table", "all"], parse_routes)
    # IPv6 is a distinct iproute2 family, not present in the default IPv4 table.
    routes6, route6_state = source(["ip", "-j", "-6", "route", "show", "table", "all"], parse_routes)
    lldp, lldp_state = source(["lldpcli", "-f", "json", "show", "neighbors"], parse_lldp)
    try:
        counters = parse_counters(read_bounded(proc_root / "net/dev"))
        counter_state = "measured"
    except ObserverError:
        counters, counter_state = {}, "error"
    # Associate the report timestamp with the actual cumulative counter sample.
    captured_at = time.time()
    interfaces = links if links is not None else (addresses or {})
    if addresses is not None:
        for name, address in addresses.items():
            if name not in interfaces:
                interfaces[name] = address
            else:
                interfaces[name]["addresses"] = address["addresses"]
    omitted_names = set()
    if len(interfaces) > MAX_REPORT_INTERFACES:
        ranked = sorted(interfaces, key=lambda name: (interface_priority(name, sys_root), name))
        omitted_names = set(ranked[MAX_REPORT_INTERFACES:])
        interfaces = {name: interfaces[name] for name in ranked[:MAX_REPORT_INTERFACES]}
    evidence_omitted = 0
    for name, item in interfaces.items():
        item.update(counters.get(name, {}))
    if link_state != "measured":
        address_state = "unsupported" if link_state == address_state == "unsupported" else "error"
    all_routes = (routes or []) + (routes6 or [])
    if route_state != route6_state or len(all_routes) > 256:
        route_state = "error"
    if len(all_routes) > 256:
        all_routes = []
    # A link may disappear between bounded command snapshots. Never publish a
    # dangling row that rejects the whole otherwise-valid report.
    def owned_evidence(evidence, state):
        nonlocal evidence_omitted
        evidence = evidence or []
        owned = [item for item in evidence if item["interface"] in interfaces]
        hidden = sum(item["interface"] in omitted_names for item in evidence)
        evidence_omitted += hidden
        return owned, "error" if len(owned) + hidden != len(evidence) else state

    neighbors, neighbor_state = owned_evidence(neighbors, neighbor_state)
    all_routes, route_state = owned_evidence(all_routes, route_state)
    lldp, lldp_state = owned_evidence(lldp, lldp_state)
    report = {"captured_at": captured_at, "boot_id": boot_id, "interfaces": list(interfaces.values()),
              "interfaces_omitted": len(omitted_names), "evidence_omitted": evidence_omitted,
              "neighbors": neighbors or [], "routes": all_routes, "lldp": lldp or [],
              "sources": {"addresses": address_state, "neighbors": neighbor_state, "routes": route_state,
                          "lldp": lldp_state, "counters": counter_state}}
    encode_json(report)
    return report


def validate_job(value, now=None):
    now = time.time() if now is None else now
    expected = {"id", "target", "max_hops", "timeout_seconds", "status", "created_at", "expires_at"}
    try:
        if not isinstance(value, dict) or set(value) != expected or value["status"] != "running":
            raise ValueError
        if str(uuid.UUID(value["id"])) != value["id"]:
            raise ValueError
        target = literal_ip(value["target"])
        if type(value["max_hops"]) is not int or value["max_hops"] != 16:
            raise ValueError
        if type(value["timeout_seconds"]) is not int or value["timeout_seconds"] != 40:
            raise ValueError
        created, expires = value["created_at"], value["expires_at"]
        if any(type(t) not in (int, float) or not math.isfinite(t) or not 0 <= t <= 2**53 for t in (created, expires)):
            raise ValueError
        if created > now + 30 or expires <= now or expires <= created:
            raise ValueError
        return {**value, "target": target}
    except (ValueError, TypeError, AttributeError, ObserverError):
        raise ObserverError("invalid_job") from None


def parse_trace(data: bytes, target: str, max_hops: int):
    if len(data) > MAX_BYTES:
        raise ObserverError("output_limit")
    result = {}
    reached = False
    for line in data.decode("ascii", errors="replace").splitlines():
        match = re.match(r"^\s*(\d{1,2})\s+(.+)$", line)
        if match is None:
            continue
        hop = int(match[1])
        if not 1 <= hop <= max_hops or hop in result:
            raise ObserverError("invalid_source")
        detail = match[2].split()
        if not detail:
            raise ObserverError("invalid_source")
        ip, rtt = None, None
        if detail[0] != "*":
            ip = literal_ip(detail[0])
            timing = re.search(r"(?:^|\s)(\d+(?:\.\d+)?)\s+ms(?:\s|$)", match[2])
            if timing is not None:
                rtt = float(timing[1])
                if not math.isfinite(rtt) or not 0 <= rtt <= 40000:
                    raise ObserverError("invalid_source")
            if ip == target and rtt is not None and "!" not in match[2]:
                reached = True
        result[hop] = {"hop": hop, "ip": ip, "rtt_ms": rtt}
    # Preserve internal missing rows as explicit unknowns; never invent later hops.
    return [result.get(hop, {"hop": hop, "ip": None, "rtt_ms": None})
            for hop in range(1, max(result, default=0) + 1)], reached


def execute_trace(job, allowed_targets):
    result = {"status": "error", "hops": [], "reached": False, "error": None,
              "source_interface": None, "next_hop": None, "completed_at": time.time()}
    if job["target"] not in allowed_targets:
        return {**result, "status": "unsupported", "error": "local_target_denied"}
    # Reserve the HTTP result deadline and one second of scheduling margin before
    # the backend's absolute job expiry; never reclaim or extend a lease locally.
    budget = min(job["timeout_seconds"], job["expires_at"] - time.time() - HTTP_TIMEOUT - 1)
    if budget <= 0:
        return {**result, "error": "timeout", "completed_at": time.time()}
    deadline = time.monotonic() + budget
    try:
        route_command = ["ip", "-j"] + (["-6"] if ":" in job["target"] else []) + ["route", "get", job["target"]]
        selected = rows(decode_json(run_command(route_command,
                        timeout=min(COMMAND_TIMEOUT, max(0.01, deadline - time.monotonic())))), 1)
        if len(selected) != 1:
            raise ObserverError("invalid_source")
        result["source_interface"] = interface_name(selected[0].get("dev"))
        gateway = selected[0].get("gateway")
        result["next_hop"] = literal_ip(gateway) if gateway is not None else None
    except ObserverError as exc:
        return {**result, "status": "unsupported" if exc.code == "command_missing" else "error",
                "error": "route_unavailable", "completed_at": time.time()}
    output = b""
    error = None
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ObserverError("timeout")
        output = run_command(["traceroute", "-n", "-q", "1", "-m", str(job["max_hops"]),
                              "-w", "1", "-6" if ":" in job["target"] else "-4", job["target"]], timeout=remaining)
    except ObserverError as exc:
        output = exc.output
        error = {"command_missing": "traceroute_missing", "timeout": "timeout"}.get(exc.code, "command_failed")
    try:
        result["hops"], result["reached"] = parse_trace(output, job["target"], job["max_hops"])
        if not result["hops"] and error is None:
            error = "command_failed"
    except ObserverError:
        error = "command_failed"
    result.update(status="unsupported" if error == "traceroute_missing" else ("error" if error else "complete"),
                  error=error, completed_at=time.time())
    if error is not None:
        result["reached"] = False
    if result["status"] == "unsupported":
        result["hops"] = []
    return result


def submit_trace(client, job, allowed_targets):
    result = execute_trace(job, allowed_targets)
    client.request("POST", "/jobs/" + job["id"] + "/result", result)


class TraceWorker:
    """Exactly one claimed job; the worker submits immediately after measurement."""

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="host-observer-trace")
        self.future = None

    def collect(self):
        if self.future is not None and self.future.done():
            completed, self.future = self.future, None
            completed.result()
        return self.future is not None

    def submit(self, client, job, allowed_targets):
        if self.future is not None:
            raise ObserverError("trace_busy")
        self.future = self.executor.submit(submit_trace, client, job, allowed_targets)

    def close(self):
        self.executor.shutdown(wait=True)
        self.collect()


def validate_peer_targets(value):
    targets = []
    identities = set()
    try:
        for target in rows(value, 64):
            if set(target) != {"target_host_id", "address", "port"}:
                raise ValueError
            host_id = text(target["target_host_id"], 264)
            if not re.fullmatch(HOST_ID_PATTERN, host_id):
                raise ValueError
            address = literal_ip(target["address"])
            ip = ipaddress.ip_address(address)
            if ip.is_multicast or ip.is_unspecified or ip.is_loopback or ip.is_link_local or address == "255.255.255.255":
                raise ValueError
            port = integer(target["port"], 65535)
            if port == 0 or (host_id, address, port) in identities:
                raise ValueError
            identities.add((host_id, address, port))
            targets.append({"target_host_id": host_id, "address": address, "port": port})
        return targets
    except (ObserverError, ValueError):
        raise ObserverError("invalid_peer_targets") from None


def unknown_peer(target):
    return {**target, "status": "unknown", "checked_at": time.time(), "latency_ms": None,
            "error": "source_unavailable"}


def probe_peer(target, deadline):
    if deadline - time.monotonic() < PEER_TIMEOUT:
        # Never report a shortened, budget-limited connect as a measured timeout.
        return unknown_peer(target)
    started = time.monotonic()
    result = {**target, "status": "unknown", "checked_at": time.time(), "latency_ms": None, "error": "probe_error"}
    family = socket.AF_INET6 if ":" in target["address"] else socket.AF_INET
    # A numeric sockaddr is passed directly to connect, never create_connection's
    # getaddrinfo path. No credentials, TLS negotiation or packet payload is sent.
    address = (target["address"], target["port"], 0, 0) if family == socket.AF_INET6 else (target["address"], target["port"])
    try:
        with socket.socket(family, socket.SOCK_STREAM) as connection:
            connection.settimeout(PEER_TIMEOUT)
            connection.connect(address)
        result.update(status="up", latency_ms=max(0.0, (time.monotonic() - started) * 1000), error=None)
    except TimeoutError:
        result.update(status="down", error="timeout")
    except OSError as exc:
        error = {errno.ECONNREFUSED: "connection_refused", errno.ETIMEDOUT: "timeout",
                 errno.ENETUNREACH: "network_unreachable", errno.EHOSTUNREACH: "network_unreachable"}.get(exc.errno)
        if error is not None:
            result.update(status="down", error=error)
    result["checked_at"] = time.time()
    return result


def probe_peers(targets, rotation=0):
    if not targets:
        return []
    offset = rotation % len(targets)
    ordered = targets[offset:] + targets[:offset]
    deadline = time.monotonic() + PEER_CYCLE_SECONDS
    # Queued work checks the shared deadline before opening a socket; no cycle
    # leaves pending threads behind. At most 8 sockets, each <=3 seconds and the
    # whole batch <=8 seconds (plus scheduler/cleanup overhead).
    try:
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="host-observer-peer") as executor:
            futures = [executor.submit(probe_peer, target, deadline) for target in ordered]
            return [future.result() for future in futures]
    except (OSError, RuntimeError):
        # Thread/resource admission failure is source-unavailable, not proof
        # that any peer is down. Context shutdown finishes any already-started
        # bounded work before returning, so the next cycle cannot overlap it.
        return [unknown_peer(target) for target in ordered]


class PeerTargetCache:
    """Last authenticated tuples, briefly retained ONLY as unknown on API failure."""

    def __init__(self):
        self.targets = []
        self.updated_at = None
        self.rotation = 0
        self.last_sample_at = None

    def update(self, targets):
        self.targets = targets
        self.updated_at = time.monotonic()

    def unavailable(self):
        if self.updated_at is None or time.monotonic() - self.updated_at > PEER_CACHE_SECONDS:
            self.targets = []
        return [unknown_peer(target) for target in self.targets]

    def await_sample_slot(self):
        if self.last_sample_at is not None:
            remaining = self.last_sample_at + 5.0 - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)

    def measure(self):
        result = probe_peers(self.targets, self.rotation)
        # Move the next cycle's first worker batch so queued hosts get coverage.
        self.rotation += 8
        return result


def run_cycle(client, allowed_targets, worker=None, peer_cache=None):
    """Refresh authenticated admission, report evidence, handle one trace job."""
    peer_cache = PeerTargetCache() if peer_cache is None else peer_cache
    failed, active, job, admitted = False, False, None, False
    if worker is not None:
        try:
            active = worker.collect()
        except ObserverError as exc:
            diagnostic(exc.code)
            failed = True
    # Fetch admission before the first report, including --once. Never derive
    # peer targets from neighbours, CLI input, DNS, trace targets or old success.
    # A busy worker still refreshes peer admission, but must leave queued traces
    # untouched until it can execute and submit them.
    try:
        response = client.request("GET", "/jobs?claim=false" if active else "/jobs")
        if not isinstance(response, dict) or set(response) != {"job", "peer_targets"}:
            raise ObserverError("invalid_job")
        peer_cache.update(validate_peer_targets(response["peer_targets"]))
        admitted = True
        if response["job"] is not None and not active:
            job = validate_job(response["job"])
    except ObserverError as exc:
        diagnostic(exc.code)
        failed = True
    try:
        # Finish all peer timestamps BEFORE the passive counter sample. Backend
        # ownership requires checked_at <= captured_at+5 even for slow peers.
        probes = peer_cache.measure() if admitted else peer_cache.unavailable()
        peer_cache.await_sample_slot()
        report = capture_report()
        peer_cache.last_sample_at = time.monotonic()
        report["peer_probes"] = probes
        report["sources"]["peer_probes"] = (
            "error" if not admitted or any(probe["status"] == "unknown" for probe in probes)
            else "measured" if probes else "unsupported"
        )
        client.request("POST", "/reports", report)
    except ObserverError as exc:
        diagnostic(exc.code)
        failed = True
    if job is not None:
        try:
            if worker is None:
                submit_trace(client, job, allowed_targets)
            else:
                worker.submit(client, job, allowed_targets)
        except ObserverError as exc:
            diagnostic(exc.code)
            failed = True
    return not failed


def diagnostic(code):
    print("host_observer: " + code, file=sys.stderr)


def parse_args(argv=None):
    parser = SafeArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                allow_abbrev=False)
    parser.add_argument("--base-url", required=True, help="Verified HTTPS origin/deployment prefix (no /api/v1 suffix)")
    parser.add_argument("--host-id", required=True, help="Exact operator-configured host ID; never inferred from hostname")
    parser.add_argument("--token-file", type=Path, help="Regular process-owned mode-0600 token file; otherwise HOST_OBSERVER_TOKEN")
    parser.add_argument("--ca-file", help="Optional trusted CA bundle; hostname verification stays enabled")
    parser.add_argument("--interval", type=float, default=MIN_INTERVAL, help="Cycle interval seconds, minimum/default 10")
    parser.add_argument("--once", action="store_true", help="Report, poll once, submit any trace result and exit")
    parser.add_argument("--trace-target", action="append", default=[], help="Locally authorized literal IP, repeatable; none disables traces")
    args = parser.parse_args(argv)
    if not math.isfinite(args.interval) or not MIN_INTERVAL <= args.interval <= 3600 or len(args.trace_target) > 128:
        raise ObserverError("invalid_arguments")
    try:
        args.trace_targets = frozenset(literal_ip(target) for target in args.trace_target)
    except ObserverError:
        raise ObserverError("invalid_arguments") from None
    return args


def main(argv=None):
    worker = None
    try:
        args = parse_args(argv)
        if not sys.platform.startswith("linux"):
            raise ObserverError("linux_required")
        client = ApiClient(args.base_url, args.host_id, load_token(args.token_file), args.ca_file)
        peer_cache = PeerTargetCache()
        if args.once:
            return 0 if run_cycle(client, args.trace_targets, peer_cache=peer_cache) else 1
        worker = TraceWorker()
        while True:
            started = time.monotonic()
            run_cycle(client, args.trace_targets, worker, peer_cache)
            # Nominal 10-second start cadence; never catch up after a slow cycle.
            remaining = args.interval - (time.monotonic() - started)
            time.sleep(remaining if remaining > 0 else args.interval)
    except ObserverError as exc:
        diagnostic(exc.code)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception:
        diagnostic("observer_failed")
        return 1
    finally:
        if worker is not None:
            try:
                worker.close()
            except ObserverError as exc:
                diagnostic(exc.code)
            except Exception:
                diagnostic("observer_failed")


if __name__ == "__main__":
    raise SystemExit(main())
