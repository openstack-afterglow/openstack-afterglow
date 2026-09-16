"""Phase A' Cache ABC + RedisBackend 단위 테스트.

fakeredis 로 실 Redis 없이 백엔드 ABC 계약을 검증한다. 모든 fixture/test 는
pytest-asyncio auto 모드 (backend/pyproject.toml 의 `asyncio_mode = "auto"`) 에 의존.
"""

from __future__ import annotations

import asyncio
import json

import fakeredis.aioredis as fakeredis
import pytest

from app.services.cache import (
    cached_call,
    invalidate,
    invalidate_project,
    set_backend,
)
from app.services.cache.keys import (
    admin_key,
    mutcount_key,
    project_key,
    tag_key,
    user_key,
    version_key,
)
from app.services.cache.metrics import get as metrics_get
from app.services.cache.metrics import reset as metrics_reset
from app.services.cache.redis_backend import RedisBackend


@pytest.fixture
async def backend():
    """fakeredis 기반 RedisBackend. 전역 _backend 도 함께 주입한다."""
    client = fakeredis.FakeRedis(decode_responses=True)
    b = RedisBackend(client=client)
    set_backend(b)
    metrics_reset()
    try:
        yield b
    finally:
        set_backend(None)
        await client.close()


# ── ABC 기본 동작 ────────────────────────────────────────────────────────────
async def test_get_miss(backend: RedisBackend) -> None:
    assert await backend.get("afterglow:missing") is None


async def test_set_then_get(backend: RedisBackend) -> None:
    await backend.set("afterglow:k", "hello", ttl=10)
    assert await backend.get("afterglow:k") == "hello"


async def test_delete(backend: RedisBackend) -> None:
    await backend.set("k1", "v1", ttl=10)
    await backend.set("k2", "v2", ttl=10)
    count = await backend.delete("k1", "k2", "nonexistent")
    assert count == 2
    assert await backend.get("k1") is None
    assert await backend.get("k2") is None


async def test_delete_empty(backend: RedisBackend) -> None:
    assert await backend.delete() == 0


async def test_incr(backend: RedisBackend) -> None:
    assert await backend.incr("counter") == 1
    assert await backend.incr("counter") == 2
    assert await backend.incr("counter", ttl=60) == 3


async def test_add_to_tag_and_invalidate_tag(backend: RedisBackend) -> None:
    # 두 개의 캐시 키를 같은 태그로 묶는다
    await backend.set("afterglow:nova:p1:servers", "S", ttl=10)
    await backend.set("afterglow:nova:p1:limits", "L", ttl=10)
    await backend.add_to_tag("nova:p1", "afterglow:nova:p1:servers")
    await backend.add_to_tag("nova:p1", "afterglow:nova:p1:limits")

    removed = await backend.invalidate_tag("nova:p1")
    # 캐시 키 2개가 삭제되어야 한다 (tag SET 자체는 카운트에서 제외)
    assert removed == 2
    assert await backend.get("afterglow:nova:p1:servers") is None
    assert await backend.get("afterglow:nova:p1:limits") is None


async def test_invalidate_tag_empty_set(backend: RedisBackend) -> None:
    # 빈 태그에 대해서도 silent 하게 0 을 반환
    assert await backend.invalidate_tag("nova:empty") == 0


async def test_ping(backend: RedisBackend) -> None:
    assert await backend.ping() is True


async def test_close_idempotent(backend: RedisBackend) -> None:
    await backend.close()
    # close 후 호출해도 silent 하게 동작
    await backend.close()


# ── 키 빌더 ─────────────────────────────────────────────────────────────────
def test_key_builders() -> None:
    assert project_key("nova", "p1", "servers") == "afterglow:nova:p1:servers"
    assert project_key("nova", "p1", "servers", sub="x") == "afterglow:nova:p1:servers:x"
    assert user_key("u1", "gpu_quota") == "afterglow:user:u1:gpu_quota"
    assert admin_key("projects") == "afterglow:admin:projects"
    assert tag_key("nova", "p1") == "tag:nova:p1"
    assert mutcount_key("nova", "p1") == "afterglow:mutcount:nova:p1"
    assert version_key("nova", "p1") == "afterglow:ver:nova:p1"


# ── cached_call (레거시 API) ────────────────────────────────────────────────
async def test_cached_call_miss_then_hit(backend: RedisBackend) -> None:
    calls = {"n": 0}

    def fn() -> dict:
        calls["n"] += 1
        return {"value": calls["n"]}

    # 첫 호출: miss → fn 실행 → 저장
    r1 = await cached_call("afterglow:test:k1", 60, fn)
    assert r1 == {"value": 1}
    assert calls["n"] == 1
    assert metrics_get("cache.miss") == 1

    # 두번째 호출: hit → fn 미실행
    r2 = await cached_call("afterglow:test:k1", 60, fn)
    assert r2 == {"value": 1}
    assert calls["n"] == 1
    assert metrics_get("cache.hit") == 1


async def test_cached_call_coalesces_concurrent_misses(backend: RedisBackend) -> None:
    """동일 키 동시 miss는 origin을 한 번만 조회하고 모든 호출자에게 같은 결과를 반환한다."""
    calls = 0
    release = asyncio.Event()

    async def fn() -> dict:
        nonlocal calls
        calls += 1
        await release.wait()
        return {"value": calls}

    first = asyncio.create_task(cached_call("afterglow:test:single-flight", 60, fn))
    second = asyncio.create_task(cached_call("afterglow:test:single-flight", 60, fn))
    await asyncio.sleep(0)
    release.set()

    assert await asyncio.gather(first, second) == [{"value": 1}, {"value": 1}]
    assert calls == 1


async def test_cached_call_waiter_cancellation_does_not_cancel_shared_load(backend: RedisBackend) -> None:
    """한 HTTP 요청 취소가 같은 키를 기다리는 다른 요청의 origin 조회를 중단하지 않는다."""
    release = asyncio.Event()
    calls = 0

    async def fn() -> dict:
        nonlocal calls
        calls += 1
        await release.wait()
        return {"ok": True}

    cancelled = asyncio.create_task(cached_call("afterglow:test:cancelled-waiter", 60, fn))
    surviving = asyncio.create_task(cached_call("afterglow:test:cancelled-waiter", 60, fn))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    release.set()

    assert await surviving == {"ok": True}
    assert calls == 1


async def test_cached_call_refresh_waits_for_older_load_and_keeps_fresh_cache(backend: RedisBackend) -> None:
    """명시적 refresh는 진행 중인 일반 miss를 재사용하거나 그 결과로 덮어써지면 안 된다."""
    key = "afterglow:test:refresh-race"
    old_started = asyncio.Event()
    release_old = asyncio.Event()
    refresh_started = asyncio.Event()
    calls: list[str] = []

    async def load_old() -> dict:
        calls.append("old")
        old_started.set()
        await release_old.wait()
        return {"value": "old"}

    async def load_fresh() -> dict:
        calls.append("fresh")
        refresh_started.set()
        return {"value": "fresh"}

    old_request = asyncio.create_task(cached_call(key, 60, load_old))
    await old_started.wait()
    refresh_request = asyncio.create_task(cached_call(key, 60, load_fresh, refresh=True))
    await asyncio.sleep(0)

    assert not refresh_started.is_set()
    release_old.set()

    assert await old_request == {"value": "old"}
    assert await refresh_request == {"value": "fresh"}
    assert calls == ["old", "fresh"]
    assert json.loads(await backend.get(key)) == {"value": "fresh"}


async def test_cached_call_refresh(backend: RedisBackend) -> None:
    calls = {"n": 0}

    async def fn() -> dict:
        calls["n"] += 1
        return {"value": calls["n"]}

    await cached_call("afterglow:test:k2", 60, fn)
    # refresh=True → 캐시 무시하고 재실행
    r = await cached_call("afterglow:test:k2", 60, fn, refresh=True)
    assert r == {"value": 2}
    assert calls["n"] == 2


async def test_cached_call_serializes_pydantic_like() -> None:
    """model_dump() 가 호출되어 JSON 직렬화 가능 형태로 변환되어야 한다."""
    client = fakeredis.FakeRedis(decode_responses=True)
    b = RedisBackend(client=client)
    set_backend(b)
    try:

        class Pseudo:
            def model_dump(self) -> dict:
                return {"id": 7, "name": "ok"}

        result = await cached_call("afterglow:test:pyd", 30, lambda: Pseudo())
        assert isinstance(result, Pseudo)

        # 저장된 캐시는 dump 된 형태여야 한다
        raw = await b.get("afterglow:test:pyd")
        assert json.loads(raw) == {"id": 7, "name": "ok"}
    finally:
        set_backend(None)
        await client.close()


# ── invalidate / invalidate_project (레거시 헬퍼) ────────────────────────────
async def test_invalidate_exact_key(backend: RedisBackend) -> None:
    await backend.set("afterglow:nova:p1:servers", "x", ttl=60)
    await invalidate("afterglow:nova:p1:servers")
    assert await backend.get("afterglow:nova:p1:servers") is None


async def test_invalidate_pattern_uses_scan(backend: RedisBackend) -> None:
    await backend.set("afterglow:nova:p1:servers", "1", ttl=60)
    await backend.set("afterglow:nova:p1:limits", "2", ttl=60)
    await backend.set("afterglow:nova:p2:servers", "3", ttl=60)

    await invalidate("afterglow:nova:p1:*")
    assert await backend.get("afterglow:nova:p1:servers") is None
    assert await backend.get("afterglow:nova:p1:limits") is None
    # 다른 프로젝트는 영향 없어야 한다
    assert await backend.get("afterglow:nova:p2:servers") == "3"


async def test_invalidate_project_all_services(backend: RedisBackend) -> None:
    await backend.set("afterglow:nova:p1:servers", "x", ttl=60)
    await backend.set("afterglow:neutron:p1:networks", "y", ttl=60)
    await invalidate_project("p1")
    assert await backend.get("afterglow:nova:p1:servers") is None
    assert await backend.get("afterglow:neutron:p1:networks") is None


async def test_invalidate_project_specific_service(backend: RedisBackend) -> None:
    await backend.set("afterglow:nova:p1:servers", "x", ttl=60)
    await backend.set("afterglow:neutron:p1:networks", "y", ttl=60)
    await invalidate_project("p1", service="nova")
    assert await backend.get("afterglow:nova:p1:servers") is None
    # neutron 은 살아 있어야 한다
    assert await backend.get("afterglow:neutron:p1:networks") == "y"


# ── Redis Sentinel HA 클라이언트 팩토리 ────────────────────────────────────────


def test_sentinel_factory_selected_when_enabled(monkeypatch) -> None:
    """sentinel_enabled=True 시 _build_sentinel_client 경로가 선택된다."""
    import app.services.cache.redis_backend as rb_module
    from app.config import Settings

    fake_client = fakeredis.FakeRedis(decode_responses=True)
    sentinel_called = []

    def mock_build(settings):
        sentinel_called.append(settings.sentinel_master_name)
        return fake_client

    fake_settings = Settings(
        sentinel_enabled=True,
        sentinel_master_name="mymaster",
        sentinel_hosts="sentinel-a:26379",
    )
    monkeypatch.setattr(rb_module, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(rb_module.RedisBackend, "_build_sentinel_client", staticmethod(mock_build))

    b = rb_module.RedisBackend()
    client = b._get_client()
    assert sentinel_called == ["mymaster"], "sentinel_enabled=True 이면 _build_sentinel_client를 호출해야 한다"
    assert client is fake_client


def test_url_factory_selected_when_sentinel_disabled(monkeypatch) -> None:
    """sentinel_enabled=False 시 from_url 경로가 선택된다."""
    import app.services.cache.redis_backend as rb_module
    from app.config import Settings

    url_called = []

    def mock_from_url(url, **kwargs):
        url_called.append(url)
        return fakeredis.FakeRedis(decode_responses=True)

    fake_settings = Settings(sentinel_enabled=False, redis_url="redis://test-host:6379/0")
    monkeypatch.setattr(rb_module, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(rb_module.aioredis, "from_url", mock_from_url)

    b = rb_module.RedisBackend()
    b._get_client()
    assert url_called == ["redis://test-host:6379/0"], "sentinel_enabled=False 이면 from_url을 호출해야 한다"


def test_build_sentinel_client_preserves_redis_auth_and_database(monkeypatch) -> None:
    """Sentinel가 찾은 master에도 redis_url의 인증 정보와 DB index를 적용한다."""
    import app.services.cache.redis_backend as rb_module
    from app.config import Settings

    fake_settings = Settings(
        redis_url="redis://cache-user:p%40ss@first-replica:6379/5",
        sentinel_enabled=True,
        sentinel_master_name="kolla",
        sentinel_hosts="sentinel-a:26379,sentinel-b:26379, sentinel-c:26380",
    )

    captured_hosts: list = []
    captured_sentinel_kwargs: dict = {}
    captured_master: dict = {}
    fake_master = fakeredis.FakeRedis(decode_responses=True)

    class FakeSentinel:
        def __init__(self, hosts, **kwargs):
            captured_hosts.extend(hosts)
            captured_sentinel_kwargs.update(kwargs)

        def master_for(self, name, **kwargs):
            captured_master.update({"name": name, **kwargs})
            return fake_master

    import redis.asyncio.sentinel as sentinel_mod

    monkeypatch.setattr(sentinel_mod, "Sentinel", FakeSentinel)

    client = rb_module.RedisBackend._build_sentinel_client(fake_settings)
    assert captured_hosts == [
        ("sentinel-a", 26379),
        ("sentinel-b", 26379),
        ("sentinel-c", 26380),
    ]
    assert captured_sentinel_kwargs == {
        "socket_timeout": 5,
        "socket_connect_timeout": 3,
    }
    assert captured_master == {
        "name": "kolla",
        "username": "cache-user",
        "password": "p@ss",
        "db": 5,
        "decode_responses": True,
        "socket_keepalive": True,
        "health_check_interval": 30,
    }
    assert client is fake_master
