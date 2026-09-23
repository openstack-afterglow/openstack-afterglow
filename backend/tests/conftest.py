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

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import ArgumentError

from app.api.deps import get_os_conn, get_token_info
from app.main import app
from app.rate_limit import limiter as _rate_limiter

# 단위/계약 계층 non-loopback 네트워크 가드. 구현과 한계는 tests/_network_guard.py 에 있다.
# conftest 가 fixture 를 import 하므로 tests/ 아래 모든 테스트에 autouse 로 적용된다(tests/integration/ 과
# `db` marker 는 가드 내부에서 제외). 별도 plugin 모듈인 이유는 teardown 강제를 별도 pytest 프로세스에서
# `-p tests._network_guard` 로 검증하기 위해서다(tests/test_network_guard.py).
from tests._network_guard import (  # noqa: F401 — pytest 는 conftest namespace 의 fixture 를 등록한다
    NonLoopbackConnectBlocked,
    _block_non_loopback_network,
    _is_loopback_target,
)
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
