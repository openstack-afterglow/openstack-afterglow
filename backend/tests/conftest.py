"""공통 테스트 픽스처."""

import os

os.environ.setdefault("AFTERGLOW_ALLOW_INSECURE", "1")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SERVICE_BARBICAN_ENABLED", "true")
os.environ.setdefault("SERVICE_MANILA_ENABLED", "true")
os.environ.setdefault("SERVICE_MAGNUM_ENABLED", "true")
os.environ.setdefault("SERVICE_ZUN_ENABLED", "true")
os.environ.setdefault("SERVICE_K3S_ENABLED", "true")
os.environ.setdefault("SERVICE_TROVE_ENABLED", "true")
os.environ.setdefault("SERVICE_SWIFT_ENABLED", "true")

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_os_conn, get_token_info
from app.main import app
from app.rate_limit import limiter as _rate_limiter

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
async def _flush_afterglow_cache():
    """각 테스트 시작과 종료 시 afterglow:* Redis 키를 flush.

    cached_call() 캐시가 테스트 간 누수되어 다른 테스트의 cinder.list_snapshots
    같은 mock 이 호출되지 않는 sequence-dependent flaky 회피. afterglow 자체
    네임스페이스만 정리하므로 다른 시스템과 독립.
    """

    async def _flush():
        try:
            from app.services.cache import _get_client

            client = _get_client()
            keys: list = []
            async for key in client.scan_iter(match="afterglow:*", count=100):
                keys.append(key)
            if keys:
                await client.delete(*keys)
        except Exception:
            pass

    await _flush()
    yield
    await _flush()


@pytest.fixture
def mock_conn():
    return make_mock_conn()


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
