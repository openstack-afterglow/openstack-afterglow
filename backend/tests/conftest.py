"""공통 테스트 픽스처."""

import os

os.environ.setdefault("AFTERGLOW_ALLOW_INSECURE", "1")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_ACCESS_TTL", "36000")
os.environ.setdefault("JWT_REFRESH_TTL", "36000")
os.environ.setdefault("SESSION_TIMEOUT_SECONDS", "36000")
os.environ.setdefault("K3S_KUBECONFIG_ENCRYPTION_KEY", "0123456789abcdef" * 4)
os.environ.setdefault("SERVICE_BARBICAN_ENABLED", "true")
os.environ.setdefault("SERVICE_MANILA_ENABLED", "true")
os.environ.setdefault("SERVICE_MAGNUM_ENABLED", "true")
os.environ.setdefault("SERVICE_ZUN_ENABLED", "true")
os.environ.setdefault("SERVICE_K3S_ENABLED", "true")
os.environ.setdefault("SERVICE_TROVE_ENABLED", "true")
os.environ.setdefault("SERVICE_SWIFT_ENABLED", "true")
os.environ.setdefault("SERVICE_WAYGATE_ENABLED", "true")
os.environ.setdefault("SERVICE_CHAT_ENABLED", "true")

import errno
import ipaddress
import socket
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import ArgumentError

from app.api.deps import get_os_conn, get_token_info
from app.main import app
from app.rate_limit import limiter as _rate_limiter
from tests.db_target_safety import (
    UnsafeDatabaseTargetError,
    assert_isolated_test_database,
)


def pytest_collection_modifyitems(config, items):
    """Block destructive DB tests from sharing the configured app schema."""
    if not any(item.get_closest_marker("db") for item in items):
        return

    test_database_url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL", "")
    if not test_database_url:
        return

    from app.config import get_settings

    try:
        assert_isolated_test_database(
            test_database_url=test_database_url,
            application_database_url=get_settings().database_url,
            allow_shared=os.environ.get("AFTERGLOW_ALLOW_SHARED_TEST_DATABASE") == "1",
        )
    except (ArgumentError, UnsafeDatabaseTargetError) as exc:
        raise pytest.UsageError(str(exc)) from exc


# 단위 테스트는 rate limit 동작 자체를 검증하지 않는 한 limiter 를 비활성화 — 누적
# state 가 다음 테스트에 누수되거나 동일 IP 로 5/min 같은 제한에 부딪히는 것을 회피.
# 실제 limiter 의 IP 추출/거부 동작은 tests/test_rate_limit_proxies.py 에서 별도 검증.
_rate_limiter.enabled = False


# ──────────────────────────────────────────────────────────────────
# 단위/계약 계층 non-loopback 네트워크 가드
# ──────────────────────────────────────────────────────────────────
# 단위·계약 테스트는 hermetic 해야 한다. 로컬 afterglow.conf 가 있을 때 실제
# Keystone/Prometheus 로 접속하던 테스트가 있었으므로, loopback 이외 주소로의
# TCP/UDP connect 를 차단하고 해당 테스트를 실패시킨다. 실 환경 계층
# (tests/integration/) 과 실 datastore 를 쓰는 functional(`db` marker) 테스트는 제외한다.
# unix socket 과 loopback(127.0.0.0/8, ::1, localhost) 은 허용한다.
# 한계: C 레벨 DNS 조회(getaddrinfo)는 socket.connect 를 거치지 않아 차단하지 않는다.

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


def _network_guard_exempt(node: pytest.Item) -> bool:
    if node.get_closest_marker("db") is not None:
        return True
    path = Path(str(node.path)).resolve()
    return any(path.is_relative_to(exempt) for exempt in _NETWORK_GUARD_EXEMPT_DIRS)


@pytest.fixture(autouse=True)
def _block_non_loopback_network(request, monkeypatch):
    """단위/계약 테스트의 non-loopback connect 를 차단하고, 시도가 있었다면 테스트를 실패시킨다.

    yield 값은 차단된 주소 목록이다. 가드 자체를 검증하는 테스트는 목록을 비워 teardown 실패를 피한다.
    """
    if _network_guard_exempt(request.node):
        yield None
        return

    blocked: list[str] = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def _is_blocked(sock: socket.socket, address: object) -> bool:
        if sock.family not in _INET_FAMILIES or _is_loopback_target(address):
            return False
        blocked.append(repr(address))
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

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    yield blocked
    if blocked:
        pytest.fail(
            "non-hermetic test: blocked non-loopback connect to "
            + ", ".join(sorted(set(blocked)))
            + " (mock the external service instead)",
            pytrace=False,
        )


def make_mock_conn(project_id: str = "test-project-123") -> MagicMock:
    """모의 OpenStack Connection 객체 생성.

    `assert_resource_owner` (defense-in-depth IDOR 가드) 가 호출하는 SDK 조회
    `conn.network.get_*`, `conn.load_balancer.get_*` 등을 caller project 와 owner 가
    일치하는 자원으로 default 응답하도록 stub. cross-project 거부 테스트는 매 테스트
    별로 patch 하거나 다른 project_id 로 별도 mock 을 만들면 된다.
    """
    conn = MagicMock()
    conn._afterglow_token = "test-token"
    conn._afterglow_project_id = project_id
    conn._afterglow_user_id = "test-user-123"
    conn.close = MagicMock()

    def _owned():
        m = MagicMock()
        m.project_id = project_id
        m.tenant_id = None
        m.is_router_external = False
        m.is_shared = False
        return m

    # return_value 패턴 — 테스트가 `mock_conn.network.get_*.return_value = X` 로
    # override 할 때 정상 동작하도록 (side_effect 사용 시 override 가 무시됨)
    # Neutron
    conn.network.get_network = MagicMock(return_value=_owned())
    conn.network.get_subnet = MagicMock(return_value=_owned())
    conn.network.get_router = MagicMock(return_value=_owned())
    conn.network.get_security_group = MagicMock(return_value=_owned())
    conn.network.get_ip = MagicMock(return_value=_owned())
    # Octavia
    conn.load_balancer.get_load_balancer = MagicMock(return_value=_owned())
    conn.load_balancer.get_listener = MagicMock(return_value=_owned())
    conn.load_balancer.get_pool = MagicMock(return_value=_owned())
    conn.load_balancer.get_health_monitor = MagicMock(return_value=_owned())
    # Cinder
    conn.block_storage.get_volume = MagicMock(return_value=_owned())
    conn.block_storage.get_snapshot = MagicMock(return_value=_owned())
    conn.block_storage.get_backup = MagicMock(return_value=_owned())
    # Trove (database)
    conn.database.get_instance = MagicMock(return_value=_owned())
    return conn


def make_token_info(
    roles: list[str] | None = None,
    project_id: str = "test-project-123",
    is_system_admin: bool = False,
    auth_method: str = "password",
) -> dict:
    """모의 token_info 딕셔너리 생성."""
    return {
        "token": "test-token",
        "project_id": project_id,
        "project_name": "test-project",
        "user_id": "test-user-123",
        "username": "testuser",
        "roles": roles or ["member"],
        "expires_at": "2099-01-01T00:00:00Z",
        "is_system_admin": is_system_admin,
        "auth_method": auth_method,
    }


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """각 테스트 전에 rate limiter storage를 리셋하여 테스트 간 간섭 방지."""
    from app.rate_limit import limiter

    try:
        limiter._storage.reset()
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def _fake_redis_global(monkeypatch):
    """Use fakeredis by default; functional tests opt into the disposable real Redis."""
    from app.services import cache as cache_mod

    if os.environ.get("AFTERGLOW_TEST_REAL_REDIS") == "1":
        cache_mod.set_backend(None)
        try:
            yield None
        finally:
            cache_mod.set_backend(None)
        return

    import fakeredis.aioredis as _fakeredis

    from app.services.cache.redis_backend import RedisBackend

    fake = _fakeredis.FakeRedis(decode_responses=True)
    cache_mod.set_backend(None)
    cache_mod.set_backend(RedisBackend(client=fake))

    async def _get_fake():
        return fake

    monkeypatch.setattr(cache_mod, "_get_redis", _get_fake, raising=False)
    monkeypatch.setattr(cache_mod, "_get_client", lambda: fake, raising=False)
    monkeypatch.setattr("app.services.session_store._get_redis", _get_fake, raising=False)
    try:
        yield fake
    finally:
        cache_mod.set_backend(None)


@pytest.fixture
def mock_conn():
    return make_mock_conn()


def patch_redis_cache_miss(monkeypatch):
    """Force cache misses: cache._get_client() returns a mock whose get/setex/delete are no-ops."""
    fake = AsyncMock()
    fake.get.return_value = None
    fake.setex.return_value = None
    fake.delete.return_value = None
    monkeypatch.setattr("app.services.cache._get_client", lambda: fake)
    return fake


@pytest.fixture
async def client(mock_conn):
    """인증 의존성을 모의 객체로 오버라이드한 AsyncClient (일반 사용자)."""

    async def override_get_os_conn():
        try:
            yield mock_conn
        finally:
            pass

    async def override_get_token_info():
        return make_token_info(roles=["member"])

    app.dependency_overrides[get_os_conn] = override_get_os_conn
    app.dependency_overrides[get_token_info] = override_get_token_info
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Auth-Token": "test-token", "X-Project-Id": "test-project-123"},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_client(mock_conn):
    """admin 역할을 가진 인증 모의 객체로 오버라이드한 AsyncClient."""

    async def override_get_os_conn():
        try:
            yield mock_conn
        finally:
            pass

    async def override_get_token_info():
        return make_token_info(roles=["admin", "member"], is_system_admin=True)

    app.dependency_overrides[get_os_conn] = override_get_os_conn
    app.dependency_overrides[get_token_info] = override_get_token_info
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Auth-Token": "test-token", "X-Project-Id": "test-project-123"},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def non_admin_client(mock_conn):
    """admin 역할 없이 member 역할만 가진 AsyncClient (403 테스트용)."""

    async def override_get_os_conn():
        try:
            yield mock_conn
        finally:
            pass

    async def override_get_token_info():
        return make_token_info(roles=["member"])

    app.dependency_overrides[get_os_conn] = override_get_os_conn
    app.dependency_overrides[get_token_info] = override_get_token_info
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Auth-Token": "test-token", "X-Project-Id": "test-project-123"},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
