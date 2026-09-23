"""단위/계약 계층 non-loopback 네트워크 가드(tests/_network_guard.py) 자체 검증."""

import asyncio
import errno
import os
import re
import socket
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from tests._network_guard import NonLoopbackConnectBlocked, _is_dns_lookup, _is_loopback_target

_BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "address",
    [
        ("127.0.0.1", 80),
        ("127.10.20.30", 80),
        ("::1", 80, 0, 0),
        ("::ffff:127.0.0.1", 80, 0, 0),
        ("localhost", 80),
        ("LOCALHOST", 80),
        ("0.0.0.0", 80),
        ("", 80),
        ("::1%lo0", 80, 0, 0),
    ],
)
def test_loopback_targets_are_allowed(address):
    assert _is_loopback_target(address) is True


@pytest.mark.parametrize(
    "address",
    [
        ("192.0.2.1", 443),
        ("10.0.0.1", 5000),
        ("2001:db8::1", 443, 0, 0),
        ("::ffff:192.0.2.1", 443, 0, 0),
        ("keystone.example.invalid", 5000),
        (b"192.0.2.1", 443),
        ("fe80::1%lo0", 443, 0, 0),
    ],
)
def test_non_loopback_targets_are_rejected(address):
    assert _is_loopback_target(address) is False


def test_non_loopback_connect_is_blocked_and_recorded(_block_non_loopback_network):
    blocked = _block_non_loopback_network
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(NonLoopbackConnectBlocked) as excinfo:
            sock.connect(("192.0.2.1", 9))
    assert isinstance(excinfo.value, OSError)
    assert excinfo.value.errno == errno.ECONNREFUSED
    assert blocked == [f"{('192.0.2.1', 9)!r} [thread {threading.current_thread().name}]"]
    blocked.clear()  # 의도된 시도이므로 teardown 실패를 막는다.


def test_blocked_connect_records_the_attempting_thread(_block_non_loopback_network):
    blocked = _block_non_loopback_network
    errors: list[BaseException] = []

    def attempt():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.connect(("192.0.2.1", 9))
            except NonLoopbackConnectBlocked as exc:
                errors.append(exc)

    worker = threading.Thread(target=attempt, name="leaked-background-worker")
    worker.start()
    worker.join(timeout=5)
    assert len(errors) == 1
    assert blocked == [f"{('192.0.2.1', 9)!r} [thread leaked-background-worker]"]
    blocked.clear()


@pytest.mark.parametrize("with_flags", [False, True])
def test_non_loopback_udp_sendto_is_blocked(_block_non_loopback_network, with_flags):
    blocked = _block_non_loopback_network
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        args = (b"x", 0, ("192.0.2.1", 53)) if with_flags else (b"x", ("192.0.2.1", 53))
        with pytest.raises(NonLoopbackConnectBlocked):
            sock.sendto(*args)
    assert len(blocked) == 1
    assert blocked[0].startswith(repr(("192.0.2.1", 53)))
    blocked.clear()


def test_loopback_udp_sendto_is_allowed(_block_non_loopback_network):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("127.0.0.1", 0))
        server.settimeout(5)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            assert client.sendto(b"ok", server.getsockname()) == 2
            assert client.sendto(b"ok", 0, server.getsockname()) == 2
        assert server.recv(2) == b"ok"
    assert _block_non_loopback_network == []


def test_hostname_connect_is_blocked_before_resolution(_block_non_loopback_network):
    blocked = _block_non_loopback_network
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(NonLoopbackConnectBlocked):
            sock.connect(("keystone.example.invalid", 5000))
    assert len(blocked) == 1
    blocked.clear()


def test_non_loopback_connect_ex_returns_refused(_block_non_loopback_network):
    blocked = _block_non_loopback_network
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        assert sock.connect_ex(("192.0.2.1", 9)) == errno.ECONNREFUSED
    assert len(blocked) == 1
    blocked.clear()


def test_loopback_connect_is_allowed(_block_non_loopback_network):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.create_connection(server.getsockname(), timeout=5) as client:
            peer, _ = server.accept()
            with peer:
                client.sendall(b"ok")
                assert peer.recv(2) == b"ok"
    assert _block_non_loopback_network == []


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="unix socket 미지원 플랫폼")
def test_unix_socket_connect_is_not_guarded(_block_non_loopback_network):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        with pytest.raises(OSError) as excinfo:
            sock.connect("/nonexistent-afterglow-guard.sock")
    assert not isinstance(excinfo.value, NonLoopbackConnectBlocked)
    assert _block_non_loopback_network == []


@pytest.mark.parametrize(
    "host",
    [
        None,
        "",
        b"",
        "localhost",
        b"localhost",
        "127.0.0.1",
        "192.0.2.1",
        b"192.0.2.1",
        "::1",
        "2001:db8::1",
        "[::1]",
        "fe80::1%lo0",
    ],
)
def test_getaddrinfo_without_dns_is_not_a_lookup(host):
    # IP literal 은 DNS 를 쓰지 않는다. non-loopback IP 는 이어지는 connect 에서 차단된다.
    assert _is_dns_lookup(host) is False


@pytest.mark.parametrize("host", ["prometheus", "keystone.example.invalid", b"prometheus", "foo.localhost"])
def test_host_names_are_dns_lookups(host):
    assert _is_dns_lookup(host) is True


def test_host_name_getaddrinfo_is_blocked_and_recorded(_block_non_loopback_network):
    blocked = _block_non_loopback_network
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("prometheus.example.invalid", 9090)
    assert blocked == [f"getaddrinfo('prometheus.example.invalid') [thread {threading.current_thread().name}]"]
    blocked.clear()


def test_ip_literal_and_localhost_getaddrinfo_are_allowed(_block_non_loopback_network):
    for host in ("127.0.0.1", "192.0.2.1", "::1", "localhost", None):
        assert socket.getaddrinfo(host, 80, type=socket.SOCK_STREAM)
    assert _block_non_loopback_network == []


async def test_event_loop_getaddrinfo_is_blocked_in_its_executor_thread(_block_non_loopback_network):
    # asyncio(httpx/anyio 포함)는 executor thread 에서 socket.getaddrinfo 를 부른다.
    blocked = _block_non_loopback_network
    with pytest.raises(socket.gaierror):
        await asyncio.get_running_loop().getaddrinfo("prometheus", 9090)
    assert len(blocked) == 1
    assert blocked[0].startswith("getaddrinfo('prometheus') [thread ")
    assert not blocked[0].endswith("[thread MainThread]")
    blocked.clear()


def test_guard_is_autouse_for_tests_that_do_not_request_it(request):
    # 아래 subprocess 검증은 plugin 을 `-p` 로 올리므로, conftest 의 import 가 fixture 를 autouse 로 등록하는지는
    # 이 테스트가 확인한다. fixture 를 인자로 요청하지 않는다.
    assert "_block_non_loopback_network" in request.fixturenames
    assert socket.socket.connect.__name__ == "guarded_connect"
    assert socket.socket.connect_ex.__name__ == "guarded_connect_ex"
    assert socket.socket.sendto.__name__ == "guarded_sendto"
    assert socket.getaddrinfo.__name__ == "guarded_getaddrinfo"


_INNER_TESTS = """
    import socket


    def test_swallows_blocked_connect():
        # 앱 코드가 연결 오류를 삼키는 경우. 차단이 꺼지면 실제 connect 가 1초 뒤 timeout 으로 끝난다.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            try:
                sock.connect(("192.0.2.1", 9))
            except OSError:
                pass


    def test_swallows_blocked_dns_lookup():
        try:
            socket.getaddrinfo("prometheus.example.invalid", 9090)
        except OSError:
            pass


    def test_loopback_only():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            with socket.create_connection(server.getsockname(), timeout=5):
                pass
"""


def test_teardown_fails_a_test_that_swallows_the_blocked_connect(tmp_path):
    """차단 예외를 삼킨 테스트도 teardown 이 error 로 실패시킨다. 이 teardown 이 유일한 강제 지점이다.

    plugin 모듈만 올린 별도 pytest 프로세스에서 inner 테스트를 돌려 teardown 결과(error)를 관찰한다.
    """
    (tmp_path / "test_inner_guard.py").write_text(textwrap.dedent(_INNER_TESTS))
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(_BACKEND_DIR), env.get("PYTHONPATH")]))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "tests._network_guard",
            "-p",
            "no:cacheprovider",
            "-rA",
            "--rootdir",
            str(tmp_path),
            "test_inner_guard.py",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert re.search(r"^=+ 3 passed, 2 errors in ", output, re.M), output
    # call 단계는 통과하고(예외를 삼켰으므로) teardown 만 error 다. loopback 대조군은 error 가 없다.
    assert "PASSED test_inner_guard.py::test_swallows_blocked_connect" in output, output
    assert "ERROR test_inner_guard.py::test_swallows_blocked_connect" in output, output
    assert re.search(
        r"^_+ ERROR at teardown of test_swallows_blocked_connect _+\n"
        r"non-hermetic test: blocked non-loopback network access: \('192\.0\.2\.1', 9\) \[thread MainThread\]",
        output,
        re.M,
    ), output
    assert "PASSED test_inner_guard.py::test_swallows_blocked_dns_lookup" in output, output
    assert re.search(
        r"^_+ ERROR at teardown of test_swallows_blocked_dns_lookup _+\n"
        r"non-hermetic test: blocked non-loopback network access: "
        r"getaddrinfo\('prometheus\.example\.invalid'\) \[thread MainThread\]",
        output,
        re.M,
    ), output
    assert "PASSED test_inner_guard.py::test_loopback_only" in output, output
    assert "ERROR test_inner_guard.py::test_loopback_only" not in output, output
