"""단위/계약 계층 non-loopback 네트워크 가드.

단위·계약 테스트는 hermetic 해야 한다. 로컬 afterglow.conf 가 있을 때 실제 Keystone/Prometheus 로 접속하던
테스트가 있었으므로, 다음을 차단하고 해당 테스트를 실패시킨다.
- loopback 이외 주소로의 TCP/UDP connect 와 connect 없는 UDP sendto
- localhost 이외 호스트 이름의 `socket.getaddrinfo`(DNS 조회). 설정 파일이 없는 CI 에서는 기본값
  `http://prometheus:9090` 같은 이름이 connect 전에 DNS 에서 실패하므로, 이것도 막아야 CI 가 mock 누락을 잡는다.
  IP literal 의 getaddrinfo 는 DNS 조회가 아니므로 허용하고 이어지는 connect 에서 판정한다.
실 환경 계층(tests/integration/)과 실 datastore 를 쓰는 functional(`db` marker) 테스트는 제외한다.
unix socket 과 loopback(127.0.0.0/8, ::1, localhost)은 허용한다.

기록에는 시도한 thread 이름을 붙인다. 이전 테스트가 남긴 background thread/task 의 connect 는 그때 실행 중인
테스트에 기록되므로 thread 이름으로 출처를 구분한다.

앱 코드가 차단 예외를 삼켜도 teardown 이 기록을 보고 테스트를 실패시킨다. 이 teardown 이 유일한 강제 지점이므로
tests/test_network_guard.py 가 이 모듈을 별도 pytest 프로세스에 plugin(`-p tests._network_guard`)으로 올려
검증한다. tests/conftest.py 는 이 fixture 를 import 해 모든 backend 테스트에 autouse 로 등록한다.

한계: `socket.getaddrinfo` 를 거치지 않는 이름 해석(`gethostbyname`, 모듈 import 시점에 getaddrinfo 를 따로
바인딩한 라이브러리, C 확장 내부 조회)과 sendmsg 는 차단하지 않는다. 설정 파일(afterglow.conf) 로딩도 격리하지
않는다. 네트워크 호출 없이 설정값에만 의존하는 경로는 이 가드가 잡지 못한다.
"""

import errno
import ipaddress
import socket
import threading
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_NETWORK_GUARD_EXEMPT_DIRS = (_TESTS_DIR / "integration",)
_INET_FAMILIES = (socket.AF_INET, socket.AF_INET6)


class NonLoopbackConnectBlocked(ConnectionRefusedError):
    """단위/계약 테스트가 loopback 이외 주소로 connect 하려 할 때 발생."""


def _is_loopback_target(address: object) -> bool:
    """connect() 대상이 loopback/unspecified 주소인지 판정한다. 호스트 이름은 localhost 만 허용."""
    host = address[0] if isinstance(address, tuple) and address else address
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    if not isinstance(host, str):
        return False
    host = host.strip("[]").split("%", 1)[0]
    if host == "" or host.lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # 이름 기반 주소는 해석(DNS) 전에 차단한다.
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_unspecified


def _is_dns_lookup(host: object) -> bool:
    """getaddrinfo(host) 가 DNS 조회를 일으키는 이름인지. None/빈 값, localhost, IP literal 은 조회가 아니다."""
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    if not isinstance(host, str) or _is_loopback_target(host):
        return False
    try:
        ipaddress.ip_address(host.strip("[]").split("%", 1)[0])
    except ValueError:
        return True
    return False


def _network_guard_exempt(node: pytest.Item) -> bool:
    if node.get_closest_marker("db") is not None:
        return True
    path = Path(str(node.path)).resolve()
    return any(path.is_relative_to(exempt) for exempt in _NETWORK_GUARD_EXEMPT_DIRS)


@pytest.fixture(autouse=True)
def _block_non_loopback_network(request, monkeypatch):
    """단위/계약 테스트의 non-loopback connect·sendto·DNS 조회를 차단하고, 시도가 있었다면 테스트를 실패시킨다.

    yield 값은 차단된 주소 목록이다. 가드 자체를 검증하는 테스트는 목록을 비워 teardown 실패를 피한다.
    """
    if _network_guard_exempt(request.node):
        yield None
        return

    blocked: list[str] = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_sendto = socket.socket.sendto
    original_getaddrinfo = socket.getaddrinfo

    def _is_blocked(sock: socket.socket, address: object) -> bool:
        if sock.family not in _INET_FAMILIES or _is_loopback_target(address):
            return False
        blocked.append(f"{address!r} [thread {threading.current_thread().name}]")
        return True

    def guarded_connect(self, address, *args, **kwargs):
        if _is_blocked(self, address):
            raise NonLoopbackConnectBlocked(
                errno.ECONNREFUSED,
                f"unit/contract tests must not connect to non-loopback address {address!r}",
            )
        return original_connect(self, address, *args, **kwargs)

    def guarded_connect_ex(self, address, *args, **kwargs):
        if _is_blocked(self, address):
            return errno.ECONNREFUSED
        return original_connect_ex(self, address, *args, **kwargs)

    def guarded_sendto(self, data, *args):
        # sendto(data, address) 와 sendto(data, flags, address) 모두 주소는 마지막 위치 인자다.
        if args and _is_blocked(self, args[-1]):
            raise NonLoopbackConnectBlocked(
                errno.ECONNREFUSED,
                f"unit/contract tests must not send to non-loopback address {args[-1]!r}",
            )
        return original_sendto(self, data, *args)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if _is_dns_lookup(host):
            blocked.append(f"getaddrinfo({host!r}) [thread {threading.current_thread().name}]")
            raise socket.gaierror(
                socket.EAI_NONAME,
                f"unit/contract tests must not resolve non-loopback host name {host!r}",
            )
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", guarded_sendto)
    yield blocked
    if blocked:
        pytest.fail(
            "non-hermetic test: blocked non-loopback network access: "
            + ", ".join(sorted(set(blocked)))
            + " (mock the external service instead)",
            pytrace=False,
        )
