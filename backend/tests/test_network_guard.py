"""단위/계약 계층 non-loopback 네트워크 가드(tests/conftest.py) 자체 검증."""

import errno
import socket

import pytest

from tests.conftest import NonLoopbackConnectBlocked, _is_loopback_target


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
    assert blocked == [repr(("192.0.2.1", 9))]
    blocked.clear()  # 의도된 시도이므로 teardown 실패를 막는다.


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
