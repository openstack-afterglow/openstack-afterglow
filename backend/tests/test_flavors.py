"""compute/flavors.py 엔드포인트 단위 테스트."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.compute import FlavorInfo
from app.services.cache import ttl_static


@pytest.mark.asyncio
async def test_list_flavors_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/flavors")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_flavors_success(client, mock_conn):
    """nova.list_flavors 결과를 정상 반환한다."""

    async def mock_cached_call(key, ttl, fn, *, refresh=False, **kw):
        return await fn()

    with (
        patch("app.api.compute.flavors.nova.list_flavors", return_value=[]),
        patch("app.services.cache.cached_call", new=mock_cached_call),
    ):
        resp = await client.get("/api/v1/flavors")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_flavors_excludes_afterglow_hidden_flavors_before_eligibility(client, mock_conn):
    async def mock_cached_call(key, ttl, fn, *, refresh=False, **kw):
        return await fn()

    visible = FlavorInfo(id="visible", name="user.small", vcpus=1, ram=1024, disk=10)
    hidden = FlavorInfo(
        id="hidden",
        name="amphora",
        vcpus=1,
        ram=1024,
        disk=5,
        extra_specs={"afterglow:frontend_visible": "false"},
    )
    evaluator = AsyncMock(side_effect=lambda _conn, _pid, flavors: list(flavors))
    with (
        patch("app.api.compute.flavors.nova.list_flavors", return_value=[visible, hidden]),
        patch("app.services.cache.cached_call", new=mock_cached_call),
        patch("app.services.flavor_eligibility.evaluate_project_flavors", evaluator),
    ):
        resp = await client.get("/api/v1/flavors")

    assert resp.status_code == 200
    assert [item["id"] for item in resp.json()] == ["visible"]
    assert [flavor.id for flavor in evaluator.await_args.args[2]] == ["visible"]


@pytest.mark.asyncio
async def test_list_flavors_uses_static_ttl(client, mock_conn):
    """캐시 TTL이 ttl_static() (300s)으로 호출되어야 한다."""
    captured = {}

    async def mock_cached_call(key, ttl, fn, *, refresh=False, **kw):
        captured["key"] = key
        captured["ttl"] = ttl
        return await fn()

    with (
        patch("app.api.compute.flavors.nova.list_flavors", return_value=[]),
        patch("app.services.cache.cached_call", new=mock_cached_call),
    ):
        resp = await client.get("/api/v1/flavors")

    assert resp.status_code == 200
    assert "flavors" in captured.get("key", "")
    assert "nova" in captured.get("key", "")
    assert captured.get("ttl") == ttl_static()


@pytest.mark.asyncio
async def test_list_flavors_cache_bypass(client, mock_conn):
    """?refresh=true 쿼리스트링이 cached_call에 refresh=True로 전달되어야 한다."""
    captured = {}

    async def mock_cached_call(key, ttl, fn, *, refresh=False, **kw):
        captured["refresh"] = refresh
        return await fn()

    with (
        patch("app.api.compute.flavors.nova.list_flavors", return_value=[]),
        patch("app.services.cache.cached_call", new=mock_cached_call),
    ):
        resp = await client.get("/api/v1/flavors?refresh=true")

    assert resp.status_code == 200
    assert captured.get("refresh") is True
