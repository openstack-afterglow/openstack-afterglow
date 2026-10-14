"""Host observer parser, credential, transport and complete CLI-path contracts.

No installed ip/lldp/traceroute or remote service is needed. Child process tests
use disposable local executables; transport is inspected without network access.
These tests are authored with the feature, not evidence of an executed collector.
"""

from __future__ import annotations

import ast
import errno
import importlib.util
import json
import os
import socket
import ssl
import sys
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/host_observer.py"
spec = importlib.util.spec_from_file_location("host_observer_cli", SCRIPT)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

HOST = "compute:compute-01.example"
TOKEN = "private-observer-secret-0123456789abcdef"
BOOT = "c0fcf975-76f5-4d29-9981-c9ba91ee8932"
JOB_ID = "e14057c1-e5c1-4d2b-9601-701c07444283"
PEER = {"target_host_id": "storage:storage-02", "address": "192.0.2.2", "port": 9100}
COUNTERS = (
    b"Inter-|   Receive                                                |  Transmit\n"
    b" face |bytes packets errs drop fifo frame compressed multicast|bytes packets errs drop fifo colls carrier compressed\n"
    b"  eth0: 12345 17 0 0 0 0 0 0 67890 23 0 0 0 0 0 0\n"
)
LINK = {"ifindex": 2, "ifname": "eth0", "address": "02:00:00:00:00:01", "operstate": "UP"}
ADDRESS = {**LINK, "addr_info": [{"local": "192.0.2.10", "prefixlen": 24}, {"local": "2001:db8::10", "prefixlen": 64}]}
NEIGHBOR = {"dev": "eth0", "dst": "192.0.2.1", "lladdr": "02:00:00:00:00:02", "state": ["REACHABLE"]}
ROUTE = {"dev": "eth0", "dst": "default", "gateway": "192.0.2.1", "metric": 100}
LLDP_NEIGHBOR = {
    "chassis": {"switch-a": {"id": {"type": "mac", "value": "02:00:00:00:01:00"}, "name": "switch-a"}},
    "port": {"id": {"type": "ifname", "value": "Ethernet1"}},
}
LLDP = {"lldp": {"interface": [{"eth0": LLDP_NEIGHBOR}]}}


def job(**changes):
    now = cli.time.time()
    return {
        "id": JOB_ID,
        "target": "192.0.2.99",
        "max_hops": 16,
        "timeout_seconds": 40,
        "status": "running",
        "created_at": now - 1,
        "expires_at": now + 180,
        **changes,
    }


def json_bytes(value):
    return json.dumps(value).encode()


def mock_capture(monkeypatch, *, faults=None):
    faults = faults or {}
    commands = []

    def read(path, maximum=cli.MAX_BYTES):
        return (BOOT + "\n").encode() if str(path).endswith("boot_id") else COUNTERS

    def command(argv, timeout=cli.COMMAND_TIMEOUT):
        commands.append(argv)
        key = tuple(argv)
        if key in faults:
            raise cli.ObserverError(faults[key])
        values = {
            ("ip", "-j", "link", "show"): [LINK],
            ("ip", "-j", "address", "show"): [ADDRESS],
            ("ip", "-j", "neigh", "show"): [NEIGHBOR],
            ("ip", "-j", "route", "show", "table", "all"): [ROUTE],
            ("ip", "-j", "-6", "route", "show", "table", "all"): [{"dev": "eth0", "dst": "2001:db8::/64"}],
            ("lldpcli", "-f", "json", "show", "neighbors"): LLDP,
        }
        return json_bytes(values[key])

    monkeypatch.setattr(cli, "read_bounded", read)
    monkeypatch.setattr(cli, "run_command", command)
    return commands


def test_cli_has_only_standard_library_and_no_shell():
    tree = ast.parse(SCRIPT.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= sys.stdlib_module_names
    assert "shell=True" not in SCRIPT.read_text()
    assert "os.system" not in SCRIPT.read_text()


@pytest.mark.parametrize("mode", [0o000, 0o400, 0o640, 0o644, 0o666, 0o700])
def test_token_file_requires_exact_0600(tmp_path, mode):
    path = tmp_path / "token"
    path.write_text(TOKEN)
    path.chmod(mode)
    with pytest.raises(cli.ObserverError, match="invalid_token_file"):
        cli.load_token(path)


def test_token_file_owned_regular_and_newline(monkeypatch, tmp_path):
    path = tmp_path / "token"
    path.write_text(TOKEN + "\n")
    path.chmod(0o600)
    assert cli.load_token(path) == TOKEN
    monkeypatch.setattr(cli.os, "geteuid", lambda: os.stat(path).st_uid + 1)
    with pytest.raises(cli.ObserverError, match="invalid_token_file"):
        cli.load_token(path)


def test_token_file_rejects_symlink_and_fifo(tmp_path):
    path = tmp_path / "token"
    path.write_text(TOKEN)
    path.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(cli.ObserverError, match="invalid_token_file"):
        cli.load_token(link)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo, mode=0o600)
    with pytest.raises(cli.ObserverError, match="invalid_token_file"):
        cli.load_token(fifo)


@pytest.mark.parametrize(
    "token", ["", " secret", "secret\n", "a\rb", "a b", "秘密", "x" * 31, "x" * 257, "x" * 31 + "."]
)
def test_environment_token_rejects_header_injection_and_overflow(monkeypatch, token):
    monkeypatch.setenv("HOST_OBSERVER_TOKEN", token)
    with pytest.raises(cli.ObserverError, match="invalid_token"):
        cli.load_token(None)


def test_environment_token_and_file_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("HOST_OBSERVER_TOKEN", TOKEN)
    assert cli.load_token(None) == TOKEN
    path = tmp_path / "token"
    path.write_text("different-token-0123456789abcdef-file")
    path.chmod(0o600)
    assert cli.load_token(path) == "different-token-0123456789abcdef-file"
    path.write_text("x" * 257)
    with pytest.raises(cli.ObserverError, match="invalid_token"):
        cli.load_token(path)


@pytest.mark.parametrize(
    "url",
    [
        "http://observer.example",
        "//observer.example",
        "https://user:secret@observer.example",
        "https://observer.example?secret=yes",
        "https://observer.example#fragment",
        "https://observer.example:0",
        "https://observer.example:65536",
        "https://observer.example/../private",
        "https://observer.example/%2e%2e/",
        "https://observer.example\\evil",
        "https://observer.example\n",
        "https://",
    ],
)
def test_https_base_url_validation(url):
    with pytest.raises(cli.ObserverError, match="invalid_base_url"):
        cli.validate_base_url(url)


def test_https_trust_exact_host_identity_and_prefix():
    client = cli.ApiClient("https://observer.example:8443/console/", HOST, TOKEN)
    assert (client.host, client.port) == ("observer.example", 8443)
    assert client.path == "/console/api/v1/monitoring/host-observations/" + HOST.replace(":", "%3A")
    assert client.context.check_hostname
    assert client.context.verify_mode == ssl.CERT_REQUIRED
    for host in ["", "../other", HOST + "/other", "wrong\nhost"]:
        with pytest.raises(cli.ObserverError, match="invalid_host_id"):
            cli.ApiClient("https://observer.example", host, TOKEN)


class Response:
    def __init__(self, data=b'{"job":null}', status=200):
        self.status = status
        self.data = data
        self.reads = 0

    def read1(self, maximum):
        self.reads += 1
        chunk, self.data = self.data[:maximum], self.data[maximum:]
        return chunk


def mock_https(monkeypatch, response, failure=None):
    connections = []

    class Connection:
        def __init__(self, host, port, timeout, context):
            self.host, self.port, self.timeout, self.context = host, port, timeout, context
            self.sock = SimpleNamespace(settimeout=lambda value: None)
            self.requests = []
            self.closed = False
            connections.append(self)

        def request(self, method, path, body, headers):
            self.requests.append((method, path, body, headers))
            if failure:
                raise failure

        def getresponse(self):
            return response

        def close(self):
            self.closed = True

    monkeypatch.setattr(cli.http.client, "HTTPSConnection", Connection)
    return connections


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 401, 403, 500])
def test_http_never_redirects_auth_or_reads_error_bodies(monkeypatch, status):
    response = Response(b"URL https://secret.example/ TOKEN " + TOKEN.encode(), status=status)
    connections = mock_https(monkeypatch, response)
    with pytest.raises(cli.ObserverError, match="^http_status$"):
        cli.ApiClient("https://observer.example", HOST, TOKEN).request("GET", "/jobs")
    assert len(connections) == 1
    assert len(connections[0].requests) == 1
    assert response.reads == 0
    assert connections[0].closed


def test_http_payload_and_response_are_bounded(monkeypatch):
    connections = mock_https(monkeypatch, Response(b"x" * (cli.MAX_BYTES + 1)))
    client = cli.ApiClient("https://observer.example", HOST, TOKEN)
    with pytest.raises(cli.ObserverError, match="output_limit"):
        client.request("GET", "/jobs")
    assert connections[0].closed
    with pytest.raises(cli.ObserverError, match="output_limit"):
        client.request("POST", "/reports", {"oversized": "x" * cli.MAX_BYTES})
    assert len(connections) == 1


def test_http_certificate_and_socket_errors_are_safe(monkeypatch):
    mock_https(monkeypatch, Response(), ssl.SSLError("private URL " + TOKEN))
    with pytest.raises(cli.ObserverError, match="^http_failed$"):
        cli.ApiClient("https://observer.example", HOST, TOKEN).request("GET", "/jobs")
    mock_https(monkeypatch, Response(), TimeoutError(TOKEN))
    with pytest.raises(cli.ObserverError, match="^http_timeout$"):
        cli.ApiClient("https://observer.example", HOST, TOKEN).request("GET", "/jobs")


def test_http_exact_auth_and_json(monkeypatch):
    connections = mock_https(monkeypatch, Response(b'{"accepted":true}'))
    client = cli.ApiClient("https://observer.example", HOST, TOKEN)
    assert client.request("POST", "/reports", {"value": 1}) == {"accepted": True}
    method, path, body, headers = connections[0].requests[0]
    assert method == "POST" and path == client.path + "/reports"
    assert json.loads(body) == {"value": 1}
    assert headers["Authorization"] == "Bearer " + TOKEN
    assert connections[0].timeout == 10


def test_capture_actual_dual_stack_evidence_and_counter_positions(monkeypatch):
    commands = mock_capture(monkeypatch)
    report = cli.capture_report()
    assert report["boot_id"] == BOOT
    interface = report["interfaces"][0]
    assert interface == {
        "name": "eth0",
        "mac": LINK["address"],
        "operstate": "UP",
        "ifindex": 2,
        "addresses": ["192.0.2.10/24", "2001:db8::10/64"],
        "rx_bytes": 12345,
        "rx_packets": 17,
        "tx_bytes": 67890,
        "tx_packets": 23,
    }
    assert report["neighbors"][0]["state"] == "REACHABLE"
    assert report["routes"][0]["gateway"] == "192.0.2.1"
    assert report["routes"][1]["destination"] == "2001:db8::/64"
    assert report["lldp"][0] == {
        "interface": "eth0",
        "chassis_id": "02:00:00:00:01:00",
        "port_id": "Ethernet1",
        "system_name": "switch-a",
    }
    assert set(report["sources"].values()) == {"measured"}
    assert len(cli.encode_json(report)) <= cli.MAX_BYTES
    assert all("get" not in command and "traceroute" not in command for command in commands)


def test_missing_and_failed_sources_are_not_measured_empty(monkeypatch):
    mock_capture(
        monkeypatch,
        faults={
            ("lldpcli", "-f", "json", "show", "neighbors"): "command_missing",
            ("ip", "-j", "neigh", "show"): "timeout",
            ("ip", "-j", "-6", "route", "show", "table", "all"): "command_failed",
        },
    )
    report = cli.capture_report()
    assert report["sources"]["lldp"] == "unsupported" and report["lldp"] == []
    assert report["sources"]["neighbors"] == "error" and report["neighbors"] == []
    assert report["sources"]["routes"] == "error"
    assert report["routes"] == [cli.parse_routes([ROUTE])[0]]


@pytest.mark.parametrize(
    "parser,value",
    [
        (cli.parse_interfaces, [LINK] * (cli.MAX_SOURCE_INTERFACES + 1)),
        (
            lambda value: cli.parse_interfaces(value, addresses=True),
            [{**ADDRESS, "addr_info": ADDRESS["addr_info"] * 17}],
        ),
        (cli.parse_neighbors, [NEIGHBOR] * 257),
        (cli.parse_routes, [ROUTE] * 257),
        (cli.parse_lldp, {"lldp": {"interface": [{"eth0": LLDP_NEIGHBOR}] * 129}}),
        (cli.parse_interfaces, [{**LINK, "ifname": "x" * 33}]),
        (cli.parse_interfaces, [{**LINK, "ifindex": True}]),
        (cli.parse_neighbors, [{**NEIGHBOR, "dst": "lookup.example"}]),
        (cli.parse_neighbors, [{**NEIGHBOR, "dev": "eth0\nsecret"}]),
        (cli.parse_routes, [{**ROUTE, "metric": -1}]),
        (cli.parse_lldp, {"lldp": {"interface": [{"eth0": {"chassis": {}, "port": {}}}]}}),
    ],
)
def test_parsers_reject_invalid_values_and_cardinality(parser, value):
    with pytest.raises(cli.ObserverError, match="invalid_source"):
        parser(value)


def test_lldp_dict_and_multiple_neighbor_shapes():
    value = {"lldp": {"interface": {"eth0": [LLDP_NEIGHBOR, LLDP_NEIGHBOR]}}}
    assert len(cli.parse_lldp(value)) == 2
    assert cli.parse_lldp({"lldp": {}}) == []


@pytest.mark.parametrize(
    "data",
    [
        COUNTERS.replace(b"12345", b"-1"),
        COUNTERS.replace(b"12345", b"18446744073709551616"),
        COUNTERS + COUNTERS.splitlines()[-1] + b"\n",
        b"not proc counters",
    ],
)
def test_counter_parse_failure_is_not_zero(data):
    with pytest.raises(cli.ObserverError, match="invalid_source"):
        cli.parse_counters(data)


def test_counter_changes_and_resets_stay_cumulative():
    before = cli.parse_counters(COUNTERS)["eth0"]
    after = cli.parse_counters(COUNTERS.replace(b"12345", b"3"))["eth0"]
    assert before["rx_bytes"] == 12345 and after["rx_bytes"] == 3
    assert "rates" not in before  # Backend applies boot/reset/time guards, not this script.


def test_json_rejects_nonfinite_and_deep_or_oversized_input(monkeypatch):
    # Reject excessive nesting explicitly even if the interpreter would accept
    # it. A too-deep document must never reach the recursive JSON decoder.
    loads = cli.json.loads

    def forbidden_decoder(*args, **kwargs):
        pytest.fail("Over-deep input reached json.loads")

    with monkeypatch.context() as context:
        context.setattr(cli.json, "loads", forbidden_decoder)
        for depth in (cli.MAX_JSON_DEPTH + 1, 2000):
            with pytest.raises(cli.ObserverError, match="^invalid_source$"):
                cli.decode_json(b"[" * depth + b"]" * depth)
    assert cli.json.loads is loads
    for data in (
        b'{"number":NaN}',
        b'{"number":Infinity}',
        b'{"number":-Infinity}',
        b'{"broken":}',
        b"[}",
        b'"unterminated',
        b'"\xff"',
    ):
        with pytest.raises(cli.ObserverError, match="^invalid_source$"):
            cli.decode_json(data)
    with pytest.raises(cli.ObserverError, match="^output_limit$"):
        cli.decode_json(b"x" * (cli.MAX_BYTES + 1))
    with pytest.raises(cli.ObserverError, match="^invalid_source$"):
        cli.encode_json({"number": float("inf")})


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-32"])
def test_json_depth_boundary_counts_containers_not_escaped_strings(encoding):
    leaf = {"text": '[{]}"\\' * (cli.MAX_JSON_DEPTH + 1)}
    value = leaf
    for index in range(cli.MAX_JSON_DEPTH - 1):
        value = [value] if index % 2 else {"child": value}
    assert cli.decode_json(json.dumps(value).encode(encoding)) == value
    with pytest.raises(cli.ObserverError, match="^invalid_source$"):
        cli.decode_json(json.dumps([value]).encode(encoding))


@pytest.mark.parametrize(
    "changes",
    [
        {"target": "hostname.example"},
        {"target": "192.0.2.0/24"},
        {"target": "-I"},
        {"target": "fe80::1%eth0"},
        {"max_hops": 17},
        {"max_hops": 0},
        {"max_hops": 15},
        {"max_hops": True},
        {"timeout_seconds": 41},
        {"timeout_seconds": 0},
        {"timeout_seconds": 39},
        {"timeout_seconds": 1.5},
        {"id": "../arbitrary"},
        {"status": "queued"},
        {"expires_at": 1},
        {"created_at": float("nan")},
        {"expires_at": float("inf")},
        {"command": "curl secret"},
    ],
)
def test_job_bounds_and_literal_only_validation(changes):
    with pytest.raises(cli.ObserverError, match="^invalid_job$"):
        cli.validate_job(job(**changes))


def test_job_accepts_real_contract_and_canonicalizes_ipv6():
    validated = cli.validate_job(job(target="2001:0db8::99"))
    assert validated["target"] == "2001:db8::99"
    assert validated["max_hops"] == 16 and validated["timeout_seconds"] == 40


def test_trace_parser_keeps_unknown_gaps_and_honest_reachability():
    hops, reached = cli.parse_trace(
        b"traceroute to 192.0.2.99\n 1 192.0.2.1 0.25 ms\n 2 *\n 4 192.0.2.99 1.23 ms\n", "192.0.2.99", 16
    )
    assert hops == [
        {"hop": 1, "ip": "192.0.2.1", "rtt_ms": 0.25},
        {"hop": 2, "ip": None, "rtt_ms": None},
        {"hop": 3, "ip": None, "rtt_ms": None},
        {"hop": 4, "ip": "192.0.2.99", "rtt_ms": 1.23},
    ]
    assert reached
    assert cli.parse_trace(b"1 192.0.2.99 0.1 ms !H\n", "192.0.2.99", 16)[1] is False
    assert cli.parse_trace(b"1 *\n2 *\n", "192.0.2.99", 16)[1] is False
    with pytest.raises(cli.ObserverError):
        cli.parse_trace(b"17 *\n", "192.0.2.99", 16)


def test_local_allowlist_denies_without_any_command(monkeypatch):
    monkeypatch.setattr(cli, "run_command", lambda *args, **kwargs: pytest.fail("Denied trace ran a command"))
    result = cli.execute_trace(job(), frozenset())
    assert result["status"] == "unsupported" and result["error"] == "local_target_denied"
    assert result["hops"] == [] and not result["reached"]


def test_trace_uses_real_route_get_and_bounded_numeric_one_probe_args(monkeypatch):
    commands = []

    def command(argv, timeout=cli.COMMAND_TIMEOUT):
        commands.append((argv, timeout))
        if argv[0] == "ip":
            return b'[{"dev":"bond1","gateway":"192.0.2.254"}]'
        return b"1 192.0.2.254 0.1 ms\n2 *\n3 192.0.2.99 0.8 ms\n"

    monkeypatch.setattr(cli, "run_command", command)
    result = cli.execute_trace(job(), {"192.0.2.99"})
    assert commands[0][0] == ["ip", "-j", "route", "get", "192.0.2.99"]
    assert commands[1][0] == ["traceroute", "-n", "-q", "1", "-m", "16", "-w", "1", "-4", "192.0.2.99"]
    assert 0 < commands[0][1] <= 5 and 0 < commands[1][1] <= 40
    assert result["source_interface"] == "bond1" and result["next_hop"] == "192.0.2.254"
    assert result["status"] == "complete" and result["reached"] and result["error"] is None


@pytest.mark.parametrize(
    "code,status,error",
    [
        ("command_missing", "unsupported", "traceroute_missing"),
        ("timeout", "error", "timeout"),
        ("command_failed", "error", "command_failed"),
        ("output_limit", "error", "command_failed"),
    ],
)
def test_trace_failure_codes_do_not_expose_command_output(monkeypatch, code, status, error):
    def command(argv, timeout=cli.COMMAND_TIMEOUT):
        if argv[0] == "ip":
            return b'[{"dev":"eth0"}]'
        raise cli.ObserverError(code, b"1 *\nprivate URL TOKEN " + TOKEN.encode())

    monkeypatch.setattr(cli, "run_command", command)
    result = cli.execute_trace(job(), {"192.0.2.99"})
    assert result["status"] == status and result["error"] == error
    assert result["next_hop"] is None and not result["reached"]
    assert TOKEN not in json.dumps(result)
    assert result["hops"] == ([] if status == "unsupported" else [{"hop": 1, "ip": None, "rtt_ms": None}])


def test_route_unavailable_stops_before_active_trace(monkeypatch):
    commands = []

    def command(argv, timeout=cli.COMMAND_TIMEOUT):
        commands.append(argv)
        return b'[{"type":"unreachable"}]'

    monkeypatch.setattr(cli, "run_command", command)
    result = cli.execute_trace(job(), {"192.0.2.99"})
    assert result["error"] == "route_unavailable" and result["status"] == "error"
    assert len(commands) == 1 and commands[0][0] == "ip"


def local_command(monkeypatch, tmp_path, code):
    path = tmp_path / "command"
    path.write_text("#!" + sys.executable + "\n" + code)
    path.chmod(0o700)
    monkeypatch.setattr(cli.shutil, "which", lambda name, path: str(tmp_path / "command"))
    return path


def test_command_bounded_output_real_local_process(monkeypatch, tmp_path):
    local_command(monkeypatch, tmp_path, "import os\nwhile True: os.write(1, b'x' * 8192)\n")
    with pytest.raises(cli.ObserverError, match="^output_limit$"):
        cli.run_command(["test-command"], timeout=2)


def test_command_timeout_real_local_process_preserves_partial_hops(monkeypatch, tmp_path):
    local_command(monkeypatch, tmp_path, "import os, time\nos.write(1, b'1 *\\n')\ntime.sleep(20)\n")
    with pytest.raises(cli.ObserverError, match="^timeout$") as error:
        cli.run_command(["test-command"], timeout=0.3)
    assert error.value.output == b"1 *\n"


def test_command_environment_never_inherits_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("HOST_OBSERVER_TOKEN", TOKEN)
    monkeypatch.setenv("OTHER_SECRET", TOKEN)
    local_command(
        monkeypatch,
        tmp_path,
        "import json, os, sys\nprint(json.dumps({'env': dict(os.environ), 'argv': sys.argv[1:]}))\n",
    )
    value = json.loads(cli.run_command(["test-command", "literal"]))
    assert "HOST_OBSERVER_TOKEN" not in value["env"] and "OTHER_SECRET" not in value["env"]
    assert value["env"]["PATH"] == cli.SAFE_PATH and value["env"]["LC_ALL"] == "C"
    assert value["argv"] == ["literal"]
    assert TOKEN not in json.dumps(value)


def test_command_missing_and_nonzero_safe(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.shutil, "which", lambda *args, **kwargs: None)
    with pytest.raises(cli.ObserverError, match="^command_missing$"):
        cli.run_command(["ip", "-j", "address"])
    local_command(monkeypatch, tmp_path, "import sys\nprint('private token " + TOKEN + "')\nsys.exit(7)\n")
    with pytest.raises(cli.ObserverError, match="^command_failed$"):
        cli.run_command(["test-command"])


class CycleClient:
    def __init__(self, trace_job=None, report_failure=False):
        self.trace_job, self.report_failure = trace_job, report_failure
        self.calls = []

    def request(self, method, suffix, payload=None):
        self.calls.append((method, suffix, payload))
        if suffix == "/reports" and self.report_failure:
            raise cli.ObserverError("http_failed")
        return {"job": self.trace_job, "peer_targets": []} if suffix == "/jobs" else {"accepted": True}


def test_real_cycle_report_poll_result_path(monkeypatch):
    mock_capture(monkeypatch)
    client = CycleClient(job())
    # No local allowlist means a real unsupported result, not omission of a job.
    assert cli.run_cycle(client, frozenset())
    assert [(method, suffix) for method, suffix, _ in client.calls] == [
        ("GET", "/jobs"),
        ("POST", "/reports"),
        ("POST", "/jobs/" + JOB_ID + "/result"),
    ]
    assert client.calls[1][2]["interfaces"][0]["rx_bytes"] == 12345
    assert client.calls[1][2]["sources"]["peer_probes"] == "unsupported"
    assert client.calls[2][2]["error"] == "local_target_denied"


def test_report_failure_still_polls_and_reports_job(monkeypatch, capsys):
    mock_capture(monkeypatch)
    client = CycleClient(job(), report_failure=True)
    assert not cli.run_cycle(client, frozenset())
    assert len(client.calls) == 3
    assert capsys.readouterr().err == "host_observer: http_failed\n"


def test_malformed_jobs_are_not_executed_or_posted(monkeypatch, capsys):
    mock_capture(monkeypatch)
    client = CycleClient(job(target="lookup.example"))
    monkeypatch.setattr(cli, "execute_trace", lambda *args: pytest.fail("Invalid job executed"))
    assert not cli.run_cycle(client, frozenset())
    assert len(client.calls) == 2
    assert capsys.readouterr().err == "host_observer: invalid_job\n"


def test_once_mode_is_complete_cycle_and_no_sleep(monkeypatch):
    mock_capture(monkeypatch)
    client = CycleClient(job())
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setenv("HOST_OBSERVER_TOKEN", TOKEN)
    monkeypatch.setattr(cli, "ApiClient", lambda *args: client)
    monkeypatch.setattr(cli.time, "sleep", lambda *args: pytest.fail("Once mode slept"))
    assert cli.main(["--base-url", "https://observer.example", "--host-id", HOST, "--once"]) == 0
    assert len(client.calls) == 3


def test_normal_mode_reports_polls_results_without_overlapping(monkeypatch):
    mock_capture(monkeypatch)
    client = CycleClient(job())
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setenv("HOST_OBSERVER_TOKEN", TOKEN)
    monkeypatch.setattr(cli, "ApiClient", lambda *args: client)

    class ImmediateWorker:
        def collect(self):
            return False

        def submit(self, api, trace_job, targets):
            cli.submit_trace(api, trace_job, targets)

        def close(self):
            pass

    monkeypatch.setattr(cli, "TraceWorker", ImmediateWorker)
    sleeps = []
    clock = [0.0]

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
        if len(sleeps) == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", sleep)
    monkeypatch.setattr(cli.time, "monotonic", lambda: clock[0])
    assert cli.main(["--base-url", "https://observer.example", "--host-id", HOST]) == 130
    assert len(client.calls) == 6
    assert sleeps == [10, 10]


@pytest.mark.parametrize(
    "extra",
    [
        ["--token", TOKEN],
        ["--interval", "9"],
        ["--interval", "nan"],
        ["--trace-target", "lookup.example"],
        ["--trace-target", "192.0.2.0/24"],
        ["--base", "https://private.example/secret"],
    ],
)
def test_cli_invalid_arguments_never_echo_secrets(capsys, extra):
    assert cli.main(["--base-url", "https://observer.example", "--host-id", HOST, *extra]) == 1
    captured = capsys.readouterr()
    assert captured.err == "host_observer: invalid_arguments\n"
    assert captured.out == ""


def test_cli_local_literal_allowlist_and_default_interval():
    args = cli.parse_args(
        [
            "--base-url",
            "https://observer.example",
            "--host-id",
            HOST,
            "--trace-target",
            "192.0.2.99",
            "--trace-target",
            "2001:0db8::99",
        ]
    )
    assert args.interval == 10
    assert args.trace_targets == frozenset({"192.0.2.99", "2001:db8::99"})


def test_active_trace_worker_keeps_reports_and_prevents_second_job(monkeypatch):
    mock_capture(monkeypatch)
    entered, release = Event(), Event()
    first, queued = job(), job(id="956e750e-0808-4019-9cdd-f54d0e72513b", status="queued")

    class QueueClient(CycleClient):
        def request(self, method, suffix, payload=None):
            value = super().request(method, suffix, payload)
            if suffix == "/jobs":
                value = {
                    "job": {**self.trace_job, "status": "running"} if self.trace_job else None,
                    "peer_targets": [PEER],
                }
                self.trace_job = None  # Model the destructive claim, not a static response.
            elif suffix == "/jobs?claim=false":
                value = {"job": None, "peer_targets": [PEER]}
            return value

    client = QueueClient(first)
    probes = []

    def probe(targets, rotation):
        probes.append(targets)
        return [cli.unknown_peer(target) for target in targets]

    monkeypatch.setattr(cli, "probe_peers", probe)
    real_execute = cli.execute_trace

    def execute(trace_job, targets):
        entered.set()
        assert release.wait(timeout=3)
        return real_execute(trace_job, targets)

    monkeypatch.setattr(cli, "execute_trace", execute)
    worker = cli.TraceWorker()
    try:
        assert cli.run_cycle(client, frozenset(), worker)
        assert entered.wait(timeout=3)
        client.trace_job = queued
        assert worker.collect()
        assert cli.run_cycle(client, frozenset(), worker)
        assert client.trace_job == queued  # Busy polling must not claim and discard it.
        assert [suffix for _, suffix, _ in client.calls] == ["/jobs", "/reports", "/jobs?claim=false", "/reports"]
        assert probes == [[PEER], [PEER]]  # Peer admission/probing is not held behind the trace.
        assert client.calls[-1][2]["peer_probes"][0]["target_host_id"] == PEER["target_host_id"]
        with pytest.raises(cli.ObserverError, match="trace_busy"):
            worker.submit(client, queued, frozenset())
        release.set()
        worker.future.result(timeout=3)
        assert not worker.collect()
        assert cli.run_cycle(client, frozenset(), worker)
        assert client.trace_job is None  # The queued trace is claimed once capacity is free.
    finally:
        release.set()
        worker.close()
    results = [
        (suffix, payload) for method, suffix, payload in client.calls if method == "POST" and suffix.endswith("/result")
    ]
    assert [suffix for suffix, _ in results] == [
        "/jobs/" + first["id"] + "/result",
        "/jobs/" + queued["id"] + "/result",
    ]
    assert all(payload["error"] == "local_target_denied" for _, payload in results)


def test_failed_trace_submission_is_safely_collected(monkeypatch, capsys):
    mock_capture(monkeypatch)
    worker = cli.TraceWorker()
    monkeypatch.setattr(cli, "submit_trace", lambda *args: (_ for _ in ()).throw(cli.ObserverError("http_failed")))
    client = CycleClient()
    try:
        worker.submit(client, job(), frozenset())
        worker.executor.shutdown(wait=True)
        assert not cli.run_cycle(client, frozenset(), worker)
        assert worker.future is None
        assert len(client.calls) == 2
        assert capsys.readouterr().err == "host_observer: http_failed\n"
    finally:
        worker.close()


def test_capture_timestamp_matches_final_counter_sample(monkeypatch):
    mock_capture(monkeypatch)
    clock = [100.0]
    command = cli.run_command

    def delayed_command(*args, **kwargs):
        clock[0] += 4
        return command(*args, **kwargs)

    monkeypatch.setattr(cli, "run_command", delayed_command)
    monkeypatch.setattr(cli.time, "time", lambda: clock[0])
    report = cli.capture_report()
    assert report["captured_at"] == 124.0


def test_ipv6_route_selection_and_trace_family(monkeypatch):
    commands = []

    def command(argv, timeout=cli.COMMAND_TIMEOUT):
        commands.append(argv)
        return b'[{"dev":"eth6","gateway":"fe80::1"}]' if argv[0] == "ip" else b"1 2001:db8::99 0.5 ms\n"

    monkeypatch.setattr(cli, "run_command", command)
    result = cli.execute_trace(job(target="2001:db8::99"), {"2001:db8::99"})
    assert commands[0] == ["ip", "-j", "-6", "route", "get", "2001:db8::99"]
    assert commands[1][-2:] == ["-6", "2001:db8::99"]
    assert result["source_interface"] == "eth6" and result["next_hop"] == "fe80::1"
    assert result["reached"]


@pytest.mark.parametrize(
    "target",
    [
        {**PEER, "address": "lookup.example"},
        {**PEER, "address": "192.0.2.0/24"},
        {**PEER, "address": "0.0.0.0"},
        {**PEER, "address": "224.0.0.1"},
        {**PEER, "address": "fe80::1"},
        {**PEER, "address": "fe80::1%eth0"},
        {**PEER, "address": "127.0.0.1"},
        {**PEER, "address": "::1"},
        {**PEER, "address": "255.255.255.255"},
        {**PEER, "port": 0},
        {**PEER, "port": 65536},
        {**PEER, "port": True},
        {**PEER, "port": "9100"},
        {**PEER, "target_host_id": "host/other"},
        {**PEER, "target_host_id": "compute:" + "a" * 254},
        {**PEER, "credentials": "secret"},
    ],
)
def test_peer_admission_rejects_dns_scans_injection_and_bounds(target):
    with pytest.raises(cli.ObserverError, match="^invalid_peer_targets$"):
        cli.validate_peer_targets([target])


def test_peer_admission_cardinality_identity_and_ipv6():
    with pytest.raises(cli.ObserverError, match="invalid_peer_targets"):
        cli.validate_peer_targets([PEER] * 65)
    with pytest.raises(cli.ObserverError, match="invalid_peer_targets"):
        cli.validate_peer_targets([PEER, PEER])
    longest = {**PEER, "target_host_id": "controller:" + "a" * 253, "address": "2001:0db8::99"}
    result = cli.validate_peer_targets([longest])
    assert result == [{**longest, "address": "2001:db8::99"}]
    client = cli.ApiClient("https://observer.example", "controller:" + "a" * 253, TOKEN)
    assert client.path.endswith("controller%3A" + "a" * 253)


def test_peer_success_and_refusal_real_numeric_loopback_without_dns(monkeypatch):
    monkeypatch.setattr(cli.socket, "getaddrinfo", lambda *args, **kwargs: pytest.fail("Peer performed DNS"))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        # Tests call the low-level probe with loopback; operator admission itself
        # rejects loopback. No remote sockets or payload are exercised here.
        target = {**PEER, "address": "127.0.0.1", "port": port}
        result = cli.probe_peer(target, cli.time.monotonic() + 8)
        assert result["status"] == "up" and result["error"] is None
        assert result["latency_ms"] >= 0
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(1)
            assert connection.recv(1) == b""  # Collector closed without payload.
    refused = cli.probe_peer(target, cli.time.monotonic() + 8)
    assert refused["status"] == "down" and refused["error"] == "connection_refused"
    assert refused["latency_ms"] is None


@pytest.mark.parametrize(
    "failure,status,error",
    [
        (TimeoutError("private"), "down", "timeout"),
        (OSError(errno.ENETUNREACH, "private"), "down", "network_unreachable"),
        (OSError(errno.EHOSTUNREACH, "private"), "down", "network_unreachable"),
        (OSError(errno.EMFILE, "private"), "unknown", "probe_error"),
    ],
)
def test_peer_socket_failures_are_truthful_bounded_and_safe(monkeypatch, failure, status, error):
    sockets = []

    class Connection:
        def __init__(self, family, kind):
            self.family, self.kind = family, kind
            sockets.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def settimeout(self, seconds):
            self.timeout = seconds

        def connect(self, address):
            self.address = address
            raise failure

    monkeypatch.setattr(cli.socket, "socket", Connection)
    monkeypatch.setattr(cli.socket, "getaddrinfo", lambda *args: pytest.fail("DNS requested"))
    result = cli.probe_peer(PEER, cli.time.monotonic() + 8)
    assert result["status"] == status and result["error"] == error
    assert result["latency_ms"] is None and "private" not in json.dumps(result)
    assert sockets[0].family == socket.AF_INET and sockets[0].kind == socket.SOCK_STREAM
    assert sockets[0].address == ("192.0.2.2", 9100)
    assert 0 < sockets[0].timeout <= 3 and sockets[0].closed


def test_peer_deadline_unattempted_is_unknown_and_opens_no_socket(monkeypatch):
    monkeypatch.setattr(cli.socket, "socket", lambda *args: pytest.fail("Expired work opened a socket"))
    result = cli.probe_peer(PEER, cli.time.monotonic() - 1)
    assert result["status"] == "unknown" and result["error"] == "source_unavailable"
    assert result["latency_ms"] is None


def test_peer_batch_has_eight_workers_one_deadline_and_rotates(monkeypatch):
    clock = [100.0]
    attempted = []
    pools = []
    monkeypatch.setattr(cli.time, "monotonic", lambda: clock[0])

    class InlineExecutor:
        def __init__(self, max_workers, thread_name_prefix):
            pools.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def submit(self, function, target, deadline):
            value = function(target, deadline)
            return SimpleNamespace(result=lambda: value)

    def fake_probe(target, deadline):
        if clock[0] >= deadline:
            return cli.unknown_peer(target)
        attempted.append(target["target_host_id"])
        clock[0] += min(3.0, deadline - clock[0])
        return {**target, "status": "down", "error": "timeout", "checked_at": cli.time.time(), "latency_ms": None}

    monkeypatch.setattr(cli, "ThreadPoolExecutor", InlineExecutor)
    monkeypatch.setattr(cli, "probe_peer", fake_probe)
    targets = [{**PEER, "target_host_id": f"compute:node-{index}"} for index in range(64)]
    result = cli.probe_peers(targets, rotation=8)
    assert pools == [8] and clock[0] == 108
    assert attempted == ["compute:node-8", "compute:node-9", "compute:node-10"]
    assert len(result) == 64 and all(row["status"] == "unknown" for row in result[3:])


def test_peer_cache_failure_is_bounded_unknown_never_reprobed(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(cli.time, "monotonic", lambda: clock[0])
    cache = cli.PeerTargetCache()
    assert cache.unavailable() == []
    cache.update([PEER])
    clock[0] = 119
    result = cache.unavailable()
    assert result[0]["status"] == "unknown" and result[0]["error"] == "source_unavailable"
    assert result[0]["latency_ms"] is None
    clock[0] = 121
    assert cache.unavailable() == [] and cache.targets == []


def test_cycle_probes_finish_before_passive_counter_capture(monkeypatch):
    mock_capture(monkeypatch)
    clock = [100.0]
    order = []
    monkeypatch.setattr(cli.time, "time", lambda: clock[0])
    capture = cli.capture_report

    def delayed_probe(targets, rotation):
        order.append("probe")
        # Second worker batch and deadline-queued unknowns finish at +8, the
        # previously broken case when checked_at exceeded captured_at+5.
        clock[0] += 8
        return [cli.unknown_peer(target) for target in targets]

    def captured():
        order.append("capture")
        return capture()

    class Client(CycleClient):
        def request(self, method, suffix, payload=None):
            value = super().request(method, suffix, payload)
            return {"job": None, "peer_targets": [PEER]} if suffix == "/jobs" else value

    monkeypatch.setattr(cli, "probe_peers", delayed_probe)
    monkeypatch.setattr(cli, "capture_report", captured)
    client = Client()
    assert cli.run_cycle(client, frozenset())
    report = client.calls[1][2]
    assert order == ["probe", "capture"]
    assert report["captured_at"] == 108
    assert report["peer_probes"][0]["checked_at"] <= report["captured_at"]
    assert report["sources"]["peer_probes"] == "error"


def test_peer_api_failure_reports_cached_unknown_then_empty_error(monkeypatch, capsys):
    mock_capture(monkeypatch)
    clock = [100.0]
    monkeypatch.setattr(cli.time, "monotonic", lambda: clock[0])
    cache = cli.PeerTargetCache()
    cache.update([PEER])
    monkeypatch.setattr(cli, "probe_peers", lambda *args: pytest.fail("API failure actively probed cached admission"))

    class Client(CycleClient):
        def request(self, method, suffix, payload=None):
            self.calls.append((method, suffix, payload))
            if suffix == "/jobs":
                raise cli.ObserverError("http_failed")
            return {"accepted": True}

    client = Client()
    assert not cli.run_cycle(client, frozenset(), peer_cache=cache)
    report = client.calls[-1][2]
    assert report["peer_probes"][0]["error"] == "source_unavailable"
    assert report["sources"]["peer_probes"] == "error"
    clock[0] = 121
    assert not cli.run_cycle(client, frozenset(), peer_cache=cache)
    assert client.calls[-1][2]["peer_probes"] == []
    assert client.calls[-1][2]["sources"]["peer_probes"] == "error"
    assert capsys.readouterr().err == "host_observer: http_failed\nhost_observer: http_failed\n"


def test_missing_interfaces_remove_dangling_evidence_and_mark_sources(monkeypatch):
    mock_capture(
        monkeypatch,
        faults={
            ("ip", "-j", "link", "show"): "command_failed",
            ("ip", "-j", "address", "show"): "command_failed",
        },
    )
    report = cli.capture_report()
    assert report["interfaces"] == []
    for source in ("neighbors", "routes", "lldp"):
        assert report[source] == [] and report["sources"][source] == "error"


def test_busy_compute_keeps_physical_nics_and_counts_omitted_vm_ports(monkeypatch, tmp_path):
    from app.models.infrastructure_topology import Observation

    mock_capture(monkeypatch)
    command = cli.run_command
    (tmp_path / "class/net/eth0/device").mkdir(parents=True)
    links = [{**LINK, "ifname": f"tap{index}"} for index in range(70)] + [{**LINK, "ifname": "eth0"}]

    def busy(argv, timeout=cli.COMMAND_TIMEOUT):
        if argv[:3] in (["ip", "-j", "link"], ["ip", "-j", "address"]):
            return json_bytes(links)
        if argv[:3] == ["ip", "-j", "neigh"]:
            return json_bytes([NEIGHBOR, {**NEIGHBOR, "dev": "tap69"}])
        return command(argv, timeout)

    monkeypatch.setattr(cli, "run_command", busy)
    report = cli.capture_report(sys_root=tmp_path)
    names = [item["name"] for item in report["interfaces"]]
    assert len(names) == 64 and names[0] == "eth0" and "tap69" not in names
    assert report["interfaces_omitted"] == 7 and report["evidence_omitted"] == 1
    # An omitted interface is counted coverage, not a corrupted neighbour source.
    assert report["sources"]["addresses"] == "measured" and report["sources"]["neighbors"] == "measured"
    assert [item["interface"] for item in report["neighbors"]] == ["eth0"]
    Observation.model_validate({**report, "peer_probes": []})


def test_budget_limited_peer_is_unknown_not_a_measured_timeout(monkeypatch):
    monkeypatch.setattr(cli.socket, "socket", lambda *args: pytest.fail("Short-budget work opened a socket"))
    result = cli.probe_peer(PEER, cli.time.monotonic() + cli.PEER_TIMEOUT - 0.5)
    assert result["status"] == "unknown" and result["error"] == "source_unavailable"
    assert result["latency_ms"] is None


def test_trace_error_cannot_claim_reached_target(monkeypatch):
    def command(argv, timeout=cli.COMMAND_TIMEOUT):
        if argv[0] == "ip":
            return b'[{"dev":"eth0"}]'
        raise cli.ObserverError("command_failed", b"1 192.0.2.99 0.1 ms\n")

    monkeypatch.setattr(cli, "run_command", command)
    result = cli.execute_trace(job(), {"192.0.2.99"})
    assert result["status"] == "error" and not result["reached"]


def test_job_rejects_private_redis_claim_fields():
    with pytest.raises(cli.ObserverError, match="invalid_job"):
        cli.validate_job({**job(), "result": None, "claimed_at": cli.time.time()})


def test_report_sample_fence_handles_slow_then_fast_peer_cycle(monkeypatch):
    clock = [110.0]
    sleeps = []
    cache = cli.PeerTargetCache()
    cache.last_sample_at = 108.0
    monkeypatch.setattr(cli.time, "monotonic", lambda: clock[0])

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(cli.time, "sleep", sleep)
    cache.await_sample_slot()
    assert sleeps == [3.0] and clock[0] == 113.0
    cache.await_sample_slot()
    assert sleeps == [3.0]  # No sleep once minimum sample separation is satisfied.


def test_expiring_trace_reserves_submission_and_runs_no_command(monkeypatch):
    now = cli.time.time()
    monkeypatch.setattr(cli, "run_command", lambda *args, **kwargs: pytest.fail("Insufficient lease ran a command"))
    result = cli.execute_trace(job(expires_at=now + 5), {"192.0.2.99"})
    assert result["status"] == "error" and result["error"] == "timeout"
    assert not result["reached"] and result["hops"] == []
    assert result["completed_at"] >= now


def test_trace_short_lease_reduces_whole_command_deadline(monkeypatch):
    now = cli.time.time()
    commands = []

    def command(argv, timeout=cli.COMMAND_TIMEOUT):
        commands.append((argv, timeout))
        return b'[{"dev":"eth0"}]' if argv[0] == "ip" else b"1 *\n"

    monkeypatch.setattr(cli, "run_command", command)
    result = cli.execute_trace(job(expires_at=now + 20), {"192.0.2.99"})
    assert result["status"] == "complete" and not result["reached"]
    assert 0 < commands[1][1] <= 9


def test_collector_payloads_match_actual_backend_models(monkeypatch):
    from app.models.infrastructure_topology import Observation, TraceResult

    mock_capture(monkeypatch)
    client = CycleClient(job())
    assert cli.run_cycle(client, frozenset())
    report = Observation.model_validate(client.calls[1][2])
    result = TraceResult.model_validate(client.calls[2][2])
    assert report.interfaces[0].rx_bytes == 12345
    assert report.sources.peer_probes == "unsupported"
    assert result.status == "unsupported" and result.error == "local_target_denied"


@pytest.fixture
def observer_settings():
    from app.models.infrastructure_topology import HostObserverIdentity

    return SimpleNamespace(
        monitoring_infrastructure_topology_enabled=True,
        monitoring_infrastructure_topology_observers=[HostObserverIdentity(host_id=HOST, token=TOKEN)],
        monitoring_infrastructure_topology_trace_targets=["192.0.2.99"],
        monitoring_infrastructure_topology_retention_seconds=3600,
        monitoring_infrastructure_topology_peer_targets=[],
        os_auth_url="https://keystone.example/v3",
        os_region_name="RegionOne",
        os_project_name="admin",
    )


@pytest.mark.asyncio
async def test_real_claimed_redis_shape_is_filtered_by_backend_before_collector(observer_settings):
    from app.services import infrastructure_topology as topology
    from app.services.cache import _get_redis

    redis = await _get_redis()
    submitted = await topology.submit_trace(HOST, "192.0.2.99", settings=observer_settings, redis=redis)
    response = await topology.poll_job(HOST, settings=observer_settings, redis=redis)
    claimed = json.loads(await redis.get(topology._keys(HOST, observer_settings)["job"]))
    assert claimed["status"] == "running" and claimed["result"] is None and "claimed_at" in claimed
    assert set(response) == {"job", "peer_targets"}
    assert set(response["job"]) == {"id", "target", "max_hops", "timeout_seconds", "status", "created_at", "expires_at"}
    assert cli.validate_job(response["job"])["id"] == submitted["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("annotation,failure", [(" !X", None), (" !H", None), ("", "command_failed"), ("", "timeout")])
async def test_actual_unsuccessful_terminal_target_evidence_is_persisted(
    monkeypatch, observer_settings, annotation, failure
):
    from app.models.infrastructure_topology import TraceResult
    from app.services import infrastructure_topology as topology
    from app.services.cache import _get_redis

    redis = await _get_redis()
    submitted = await topology.submit_trace(HOST, "192.0.2.99", settings=observer_settings, redis=redis)
    claimed = (await topology.poll_job(HOST, settings=observer_settings, redis=redis))["job"]
    output = ("1 192.0.2.1 0.25 ms\n2 192.0.2.99 1.23 ms" + annotation + "\n").encode()

    def command(argv, timeout=cli.COMMAND_TIMEOUT):
        if argv[0] == "ip":
            return b'[{"dev":"eth0","gateway":"192.0.2.1"}]'
        if failure is not None:
            raise cli.ObserverError(failure, output)
        return output

    monkeypatch.setattr(cli, "run_command", command)
    result = TraceResult.model_validate(cli.execute_trace(cli.validate_job(claimed), {"192.0.2.99"}))
    assert result.status == ("error" if failure else "complete") and result.reached is False
    assert result.hops[-1].ip == "192.0.2.99" and result.hops[-1].rtt_ms == 1.23
    assert result.error == failure
    assert await topology.finish_trace(HOST, submitted["id"], result, settings=observer_settings, redis=redis) == {
        "accepted": True
    }
    stored = json.loads(await redis.get(topology._keys(HOST, observer_settings)["job"]))
    history = json.loads((await redis.lrange(topology._keys(HOST, observer_settings)["traces"], 0, 0))[0])
    assert stored["result"] == result.model_dump() and stored["status"] == result.status
    assert history == stored


def test_ipv6_peer_numeric_sockaddr_and_no_dns_or_payload(monkeypatch):
    sockets = []

    class Connection:
        def __init__(self, family, kind):
            self.family = family
            sockets.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, seconds):
            self.timeout = seconds

        def connect(self, address):
            self.address = address

    monkeypatch.setattr(cli.socket, "socket", Connection)
    monkeypatch.setattr(cli.socket, "getaddrinfo", lambda *args: pytest.fail("DNS requested"))
    target = {**PEER, "address": "2001:db8::2"}
    result = cli.probe_peer(target, cli.time.monotonic() + 8)
    assert result["status"] == "up" and result["error"] is None
    assert sockets[0].family == socket.AF_INET6
    assert sockets[0].address == ("2001:db8::2", 9100, 0, 0)
    assert 0 < sockets[0].timeout <= 3


def test_actual_peer_report_matches_backend_honest_status_model(monkeypatch):
    from app.models.infrastructure_topology import Observation

    mock_capture(monkeypatch)

    class Client(CycleClient):
        def request(self, method, suffix, payload=None):
            value = super().request(method, suffix, payload)
            return {"job": None, "peer_targets": [PEER]} if suffix == "/jobs" else value

    def measure(targets, rotation):
        return [{**targets[0], "status": "up", "checked_at": cli.time.time(), "latency_ms": 1.25, "error": None}]

    monkeypatch.setattr(cli, "probe_peers", measure)
    client = Client()
    assert cli.run_cycle(client, frozenset())
    report = Observation.model_validate(client.calls[1][2])
    assert report.sources.peer_probes == "measured"
    assert report.peer_probes[0].status == "up" and report.peer_probes[0].latency_ms == 1.25


def test_peer_worker_resource_failure_is_unknown_not_peer_down(monkeypatch):
    def unavailable_executor(*args, **kwargs):
        raise RuntimeError("private resource details " + TOKEN)

    monkeypatch.setattr(cli, "ThreadPoolExecutor", unavailable_executor)
    result = cli.probe_peers([PEER])
    assert result[0]["status"] == "unknown" and result[0]["error"] == "source_unavailable"
    assert result[0]["latency_ms"] is None and TOKEN not in json.dumps(result)


def test_unexpected_cli_failure_has_fixed_non_sensitive_diagnostic(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setenv("HOST_OBSERVER_TOKEN", TOKEN)

    def failed_client(*args):
        raise RuntimeError("https://private.example/ " + TOKEN)

    monkeypatch.setattr(cli, "ApiClient", failed_client)
    assert cli.main(["--base-url", "https://observer.example", "--host-id", HOST, "--once"]) == 1
    captured = capsys.readouterr()
    assert captured.err == "host_observer: observer_failed\n" and captured.out == ""
