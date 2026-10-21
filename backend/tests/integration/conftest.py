"""
통합 테스트 공통 픽스처.
afterglow.conf 또는 credentials.toml 의 실제 OpenStack 인증 정보를 사용하여 로그인 후
토큰을 획득하고, httpx AsyncClient로 FastAPI 앱에 실제 요청을 보낸다.

사전 조건:
  - Redis 실행 중 (afterglow.conf의 redis_url)
  - OpenStack 접근 가능 (afterglow.conf의 openstack 섹션 또는 credentials.toml)
  - 환경변수 AFTERGLOW_ALLOW_INSECURE=1 (개발 시크릿 키 허용)

실행:
  cd backend
  AFTERGLOW_ALLOW_INSECURE=1 uv run pytest tests/integration/ -v

admin/user 권한 분리 테스트를 위한 일반 유저 계정 설정:
  cp tests/integration/credentials.toml.example tests/integration/credentials.toml
  # 파일을 열어 [user] 섹션 비밀번호 기입
  또는 환경변수: AFTERGLOW_TEST_USER_USERNAME, AFTERGLOW_TEST_USER_PASSWORD, AFTERGLOW_TEST_USER_PROJECT
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings

# 환경변수는 루트 tests/conftest.py에서 설정됨
from app.main import app


@dataclass
class IntegrationResources:
    """통합 테스트용 OpenStack 리소스 식별자 + SSH 자격증명.

    환경변수 부재 시 픽스처 단계에서 pytest.skip으로 처리.
    """

    image_id: str
    flavor_small: str
    flavor_medium: str
    library_ids: list[str]
    ssh_key_path: str
    ssh_user: str
    ssh_key_name: str


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------


def assert_forbidden(resp) -> None:
    """403 응답 + 관리자 관련 메시지 검증."""
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
    body = resp.json()
    assert "detail" in body


def require_service(flag: str) -> None:
    """선택적 서비스 비활성화 시 테스트 skip.

    사용 예:
        require_service("service_manila_enabled")
    """
    settings = get_settings()
    if not getattr(settings, flag, False):
        pytest.skip(f"{flag}=false — 서비스 미활성화")


class RedactedMapping(dict[str, Any]):
    """Mapping-compatible fixture payload that never renders values in tracebacks."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}(keys={sorted(self)!r})"


class RedactedCredentials(RedactedMapping):
    """Credential-specific redacted mapping."""


def password_login_payload(credentials: dict[str, str]) -> RedactedCredentials:
    """Project native SDK credentials onto the domain-free browser login API."""
    return RedactedCredentials({key: credentials[key] for key in ("username", "password")})


class RedactedSecret(str):
    """String-compatible secret value with a traceback-safe representation."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}('***')"


@dataclass(repr=False)
class IntegrationAuthSession:
    """실제 로그인 세션 상태.

    장시간 integration run 도중 access JWT 가 401로 만료되면 refresh 토큰으로
    한 번 회전하고, refresh 자체도 만료/실패한 경우에는 같은 크리덴셜로 즉시
    재로그인해 후속 요청을 계속 진행한다.
    """

    credentials: dict[str, str]
    label: str
    token_data: dict[str, Any] | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(label={self.label!r}, authenticated={self.token_data is not None})"

    async def get_token_data(self) -> RedactedMapping:
        async with self._lock:
            if self.token_data is None:
                await self._login_locked()
            assert self.token_data is not None
            return RedactedMapping(self.token_data)

    async def refresh_or_relogin(self) -> RedactedMapping:
        async with self._lock:
            if not await self._refresh_locked():
                await self._login_locked()
            assert self.token_data is not None
            return RedactedMapping(self.token_data)

    async def _login_locked(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/auth/login", json=password_login_payload(self.credentials))
            assert resp.status_code == 200, f"{self.label} 로그인 실패 (HTTP {resp.status_code})"
            data = resp.json()
            assert data["identity_domain_name"] == "Accounts", "Live human credentials must belong to native Accounts"
            # Native project/domain settings remain explicit live-test workspace
            # targets, never password-login authority or a fallback on failure.
            if self.credentials.get("project_name"):
                headers = {"Authorization": f"Bearer {data['token']}"}
                domains = await ac.get("/api/v1/auth/domains", headers=headers)
                assert domains.status_code == 200, f"{self.label} domain directory failed (HTTP {domains.status_code})"
                matches = [
                    domain
                    for domain in domains.json()
                    if self.credentials["domain_name"] in (domain["id"], domain["name"])
                ]
                assert len(matches) == 1, f"{self.label} requires one accessible configured workspace domain"
                domain_id = matches[0]["id"]
                workspace = await ac.get("/api/v1/auth/workspaces", params={"domain_id": domain_id}, headers=headers)
                assert workspace.status_code == 200, (
                    f"{self.label} workspace directory failed (HTTP {workspace.status_code})"
                )
                assert workspace.json()["domain"]["id"] == domain_id
                projects = [
                    project
                    for project in workspace.json()["projects"]
                    if project["name"] == self.credentials["project_name"]
                ]
                assert len(projects) == 1, f"{self.label} requires one accessible configured workspace project"
                selected = await ac.post(
                    "/api/v1/auth/token/workspace",
                    json={"domain_id": domain_id, "project_id": projects[0]["id"]},
                    headers=headers,
                )
                assert selected.status_code == 200, (
                    f"{self.label} workspace selection failed (HTTP {selected.status_code})"
                )
                scoped = selected.json()
                assert (scoped["domain_id"], scoped["project_id"]) == (domain_id, projects[0]["id"])
                assert (scoped["user_id"], scoped["identity_domain_id"]) == (
                    data["user_id"],
                    data["identity_domain_id"],
                )
                # Workspace selection can preserve a system administrator's
                # original native connection scope. Core OpenStack live tests
                # require an actual user project token, not logical authority.
                native = await ac.post(
                    "/api/v1/auth/token/project",
                    json={"project_id": projects[0]["id"]},
                    headers={"Authorization": f"Bearer {scoped['token']}"},
                )
                assert native.status_code == 200, (
                    f"{self.label} native project rescope failed (HTTP {native.status_code})"
                )
                data = native.json()
                assert (data["domain_id"], data["project_id"]) == (domain_id, projects[0]["id"])
                assert (data["user_id"], data["identity_domain_id"]) == (
                    scoped["user_id"],
                    scoped["identity_domain_id"],
                )
            self.token_data = data

    async def _refresh_locked(self) -> bool:
        if not self.token_data or not self.token_data.get("refresh_token"):
            return False

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": self.token_data["refresh_token"]},
            )
        if resp.status_code != 200:
            return False

        self.token_data = resp.json()
        return True


class AutoRefreshingAsyncClient(AsyncClient):
    """401 발생 시 refresh → 재로그인 순으로 1회 복구를 시도하는 테스트 전용 클라이언트."""

    def __init__(self, *, auth_session: IntegrationAuthSession, **kwargs):
        self._auth_session = auth_session
        super().__init__(**kwargs)

    async def request(self, method: str, url, **kwargs):
        initial = await self._auth_session.get_token_data()
        first_kwargs = dict(kwargs)
        first_kwargs["headers"] = self._auth_headers(first_kwargs.get("headers"), initial)

        response = await super().request(method, url, **first_kwargs)
        if response.status_code != 401:
            return response

        await response.aread()
        rotated = await self._auth_session.refresh_or_relogin()
        retry_kwargs = dict(kwargs)
        retry_kwargs["headers"] = self._auth_headers(retry_kwargs.get("headers"), rotated)
        return await super().request(method, url, **retry_kwargs)

    @staticmethod
    def _auth_headers(headers: Any, token_data: dict[str, Any]) -> dict[str, str]:
        merged = dict(headers or {})
        merged["Authorization"] = f"Bearer {token_data['token']}"
        merged["X-Project-Id"] = str(token_data["project_id"])
        return merged


# ---------------------------------------------------------------------------
# 전역 Redis 테스트 패치 비활성화 — 통합 테스트는 실제 Redis를 사용
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fake_redis_global():
    """tests/conftest.py의 전역 fakeredis autouse 픽스처를 여기서 no-op으로 오버라이드.

    통합 테스트는 실제 Keystone 로그인 후 세션을 실제 Redis에 저장하므로
    fakeredis로 교체하면 이후 요청에서 세션을 찾지 못해 401이 발생한다.
    """
    yield


# ---------------------------------------------------------------------------
# 설정 / 크리덴셜
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def integration_resources():
    """실 인프라 통합 테스트용 image/flavor/SSH 자격증명.

    누락 시 자동 skip — slow 마커가 붙은 테스트에서만 사용된다.
    """
    image_id = os.environ.get("AFTERGLOW_TEST_IMAGE_ID", "").strip()
    flavor_small = os.environ.get("AFTERGLOW_TEST_FLAVOR_SMALL", "").strip()
    flavor_medium = os.environ.get("AFTERGLOW_TEST_FLAVOR_MEDIUM", "").strip()
    ssh_key_path = os.environ.get("AFTERGLOW_TEST_SSH_KEY", "").strip()

    missing = [
        name
        for name, val in [
            ("AFTERGLOW_TEST_IMAGE_ID", image_id),
            ("AFTERGLOW_TEST_FLAVOR_SMALL", flavor_small),
            ("AFTERGLOW_TEST_FLAVOR_MEDIUM", flavor_medium),
            ("AFTERGLOW_TEST_SSH_KEY", ssh_key_path),
        ]
        if not val
    ]
    if missing:
        pytest.skip(f"통합 테스트 환경변수 미설정: {', '.join(missing)}")

    if not os.path.isfile(ssh_key_path):
        pytest.skip(f"SSH 키 파일이 존재하지 않음: {ssh_key_path}")

    # OpenSSH는 키 모드가 0o600(또는 더 제한적)이 아니면 거부 — CI에서 자동 보정.
    try:
        os.chmod(ssh_key_path, 0o600)
    except OSError:
        pass

    library_ids_raw = os.environ.get("AFTERGLOW_TEST_LIBRARY_IDS", "python311").strip()
    library_ids = [s.strip() for s in library_ids_raw.split(",") if s.strip()]
    ssh_user = os.environ.get("AFTERGLOW_TEST_SSH_USER", "ubuntu").strip() or "ubuntu"
    ssh_key_name = os.environ.get("AFTERGLOW_TEST_SSH_KEY_NAME", "afterglow-e2e-test").strip()

    return IntegrationResources(
        image_id=image_id,
        flavor_small=flavor_small,
        flavor_medium=flavor_medium,
        library_ids=library_ids,
        ssh_key_path=ssh_key_path,
        ssh_user=ssh_user,
        ssh_key_name=ssh_key_name,
    )


@pytest.fixture(scope="session")
def admin_credentials_fx():
    """admin 크리덴셜 (credentials.toml > afterglow.conf 폴백)."""
    from .credentials import admin_credentials

    return RedactedCredentials(admin_credentials())


@pytest.fixture(scope="session")
def admin_user_credentials_fx():
    """admin_user 크리덴셜 (admin 프로젝트 admin role 보유, default_project ≠ admin 가능). 미설정 시 skip."""
    from .credentials import admin_user_credentials

    creds = admin_user_credentials()
    if creds is None:
        pytest.skip(
            "admin_user 크리덴셜 미설정 — "
            "tests/integration/credentials.toml 의 [admin_user] 섹션 또는 "
            "AFTERGLOW_TEST_ADMIN_USER_USERNAME / AFTERGLOW_TEST_ADMIN_USER_PASSWORD 환경변수를 설정하세요."
        )
    return RedactedCredentials(creds)


@pytest.fixture(scope="session")
def user_credentials_fx():
    """일반 유저 크리덴셜. 미설정 시 테스트 skip."""
    from .credentials import user_credentials

    creds = user_credentials()
    if creds is None:
        pytest.skip(
            "일반 유저 크리덴셜 미설정 — "
            "tests/integration/credentials.toml 의 [user] 섹션 또는 "
            "AFTERGLOW_TEST_USER_USERNAME / AFTERGLOW_TEST_USER_PASSWORD 환경변수를 설정하세요."
        )
    return RedactedCredentials(creds)


@pytest.fixture(scope="session")
def project_b_credentials_fx():
    """두 번째 프로젝트 크리덴셜 (격리 테스트용). 미설정 시 skip."""
    from .credentials import project_b_credentials

    creds = project_b_credentials()
    if creds is None:
        pytest.skip(
            "project_b 크리덴셜 미설정 — "
            "tests/integration/credentials.toml 의 [project_b] 섹션 또는 "
            "AFTERGLOW_TEST_PROJECT_B_USERNAME / AFTERGLOW_TEST_PROJECT_B_PASSWORD 환경변수를 설정하세요."
        )
    return RedactedCredentials(creds)


# 하위 호환: 기존 테스트가 사용하던 `credentials` 픽스처는 admin 계정을 반환
@pytest.fixture(scope="session")
def credentials(admin_credentials_fx):
    """기존 호환성 유지: admin 크리덴셜 반환."""
    return admin_credentials_fx


@pytest.fixture(scope="session")
async def project_b_login_session(project_b_credentials_fx):
    session = IntegrationAuthSession(project_b_credentials_fx, "project_b")
    await session.get_token_data()
    return session


@pytest.fixture(scope="session")
async def project_b_auth_data(project_b_login_session):
    """project_b 계정으로 실제 Keystone 로그인. 세션 전체에서 재사용."""
    return await project_b_login_session.get_token_data()


@pytest.fixture(scope="session")
async def project_b_client(project_b_login_session):
    """project_b 계정으로 인증된 AsyncClient (격리 테스트용)."""
    async with AutoRefreshingAsyncClient(
        auth_session=project_b_login_session,
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=30,
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# 인증 데이터 (로그인)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def admin_login_session(admin_credentials_fx):
    session = IntegrationAuthSession(admin_credentials_fx, "admin")
    await session.get_token_data()
    return session


@pytest.fixture(scope="session")
async def admin_user_login_session(admin_user_credentials_fx):
    session = IntegrationAuthSession(admin_user_credentials_fx, "admin_user")
    await session.get_token_data()
    return session


@pytest.fixture(scope="session")
async def user_login_session(user_credentials_fx):
    session = IntegrationAuthSession(user_credentials_fx, "일반 유저")
    await session.get_token_data()
    return session


@pytest.fixture(scope="session")
async def admin_auth_data(admin_login_session):
    """admin 계정으로 실제 Keystone 로그인. 세션 전체에서 재사용."""
    return await admin_login_session.get_token_data()


@pytest.fixture(scope="session")
async def admin_user_auth_data(admin_user_login_session):
    """admin_user 계정으로 실제 Keystone 로그인. 세션 전체에서 재사용."""
    return await admin_user_login_session.get_token_data()


@pytest.fixture(scope="session")
async def user_auth_data(user_login_session):
    """일반 유저 계정으로 실제 Keystone 로그인. 세션 전체에서 재사용."""
    return await user_login_session.get_token_data()


# 하위 호환: 기존 `auth_data` → admin 위임
@pytest.fixture(scope="session")
async def auth_data(admin_auth_data):
    return admin_auth_data


@pytest.fixture(scope="session")
def token(admin_auth_data):
    return RedactedSecret(str(admin_auth_data["token"]))


@pytest.fixture(scope="session")
def project_id(admin_auth_data):
    return admin_auth_data["project_id"]


@pytest.fixture(scope="session")
def auth_headers(token, project_id):
    """인증 헤더 dict (admin 계정).

    get_token_info는 Authorization: Bearer JWT 경로만 지원한다.
    """
    return {
        "Authorization": f"Bearer {token}",
        "X-Project-Id": project_id,
    }


# ---------------------------------------------------------------------------
# HTTP 클라이언트
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
async def admin_client(admin_login_session):
    """admin 계정으로 인증된 AsyncClient."""
    async with AutoRefreshingAsyncClient(
        auth_session=admin_login_session,
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=30,
    ) as ac:
        yield ac


@pytest.fixture(scope="session")
async def admin_user_client(admin_user_login_session):
    """admin_user 계정으로 인증된 AsyncClient (scoped project ≠ admin 일 수 있는 admin 권한 검증용)."""
    async with AutoRefreshingAsyncClient(
        auth_session=admin_user_login_session,
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=30,
    ) as ac:
        yield ac


@pytest.fixture(scope="session")
async def user_client(user_login_session):
    """일반 유저 계정으로 인증된 AsyncClient (권한 분리 테스트용)."""
    async with AutoRefreshingAsyncClient(
        auth_session=user_login_session,
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=30,
    ) as ac:
        yield ac


# 하위 호환: 기존 `client` → admin_client 위임
@pytest.fixture(scope="session")
async def client(admin_login_session):
    """인증 헤더가 포함된 AsyncClient (admin). 기존 테스트 하위 호환용."""
    async with AutoRefreshingAsyncClient(
        auth_session=admin_login_session,
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=30,
    ) as ac:
        yield ac


@pytest.fixture(scope="session")
async def anon_client():
    """인증 없는 AsyncClient (공개 엔드포인트 테스트용)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=30,
    ) as ac:
        yield ac


async def _caller_domain_id(client):
    """Resolve the caller's authoritative domain ID, not a display name."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200, response.text
    domain_id = response.json()["domain_id"]
    assert isinstance(domain_id, str) and domain_id
    return domain_id


@pytest.fixture(scope="session")
async def selected_domain_id(client):
    return await _caller_domain_id(client)


@pytest.fixture(scope="session")
async def regular_user_domain_id(user_client):
    return await _caller_domain_id(user_client)


@pytest.fixture(scope="session")
async def admin_user_domain_id(admin_user_client):
    return await _caller_domain_id(admin_user_client)


# ---------------------------------------------------------------------------
# 세션 teardown — Redis 캐시 정리
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
async def _flush_cache_after_session():
    """세션 종료 시 afterglow:cache:* 키 일괄 삭제.

    쓰기 테스트가 생성한 리소스의 캐시 잔여물을 제거한다.
    세션 키(afterglow:session:*)는 TTL로 자연 만료되므로 건드리지 않는다.
    Redis가 없으면 조용히 무시 (단위 테스트 환경 호환).
    """
    yield
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(get_settings().redis_url)
        async for key in r.scan_iter("afterglow:cache:*"):
            await r.delete(key)
        await r.aclose()
    except Exception:
        pass
