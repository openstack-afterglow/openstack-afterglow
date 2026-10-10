from __future__ import annotations

import fakeredis.aioredis
import pytest

from app.services.mcp_control_plane import limits
from app.services.mcp_control_plane.authentication import McpPrincipal

_KEY = "afterglow:mcp:limit:project-a:grant-a:concurrency"


@pytest.fixture
def principal():
    return McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:read", "mcp:write"}),
        source="personal_token",
    )


@pytest.fixture
async def redis(monkeypatch):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def get_redis():
        return client

    monkeypatch.setattr(limits, "_get_redis", get_redis)
    monkeypatch.setattr(
        limits,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {"mcp_read_rate_per_minute": 100, "mcp_mutation_rate_per_minute": 100, "mcp_concurrent_calls_per_grant": 1},
        )(),
    )
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_grant_call_slot_applies_per_grant_rate_and_releases_concurrency(monkeypatch, principal, redis):
    monkeypatch.setattr(
        limits,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {"mcp_read_rate_per_minute": 1, "mcp_mutation_rate_per_minute": 1, "mcp_concurrent_calls_per_grant": 1},
        )(),
    )
    async with limits.grant_call_slot(principal, effect="read"):
        assert await redis.scard(_KEY) == 1
        assert await redis.ttl(_KEY) == -1  # a TTL cannot prove a worker stopped
    assert await redis.exists(_KEY) == 0
    with pytest.raises(limits.McpRateLimitExceeded):
        async with limits.grant_call_slot(principal, effect="read"):
            raise AssertionError("rate-limited request must not enter")


@pytest.mark.asyncio
async def test_old_owner_release_cannot_remove_new_generation_slot(principal, redis):
    first = limits.grant_call_slot(principal, effect="read")
    await first.__aenter__()
    first_owner = await redis.smembers(_KEY)
    # Simulate external deletion/old TTL expiry, then a later request. The old
    # release must never decrement/release the new owner's budget.
    await redis.delete(_KEY)
    second = limits.grant_call_slot(principal, effect="read")
    await second.__aenter__()
    second_owner = await redis.smembers(_KEY)
    assert second_owner != first_owner
    await first.__aexit__(None, None, None)
    assert await redis.smembers(_KEY) == second_owner
    try:
        with pytest.raises(limits.McpRateLimitExceeded):
            async with limits.grant_call_slot(principal, effect="read"):
                raise AssertionError("new generation still holds its slot")
    finally:
        await second.__aexit__(None, None, None)
    assert await redis.exists(_KEY) == 0


@pytest.mark.asyncio
async def test_lost_release_fails_closed_instead_of_ttl_reclaim(principal, redis, monkeypatch):
    async def unavailable_release(*_args):
        raise OSError("redis outage")

    async with limits.grant_call_slot(principal, effect="external_mutation"):
        monkeypatch.setattr(redis, "srem", unavailable_release)
    assert await redis.scard(_KEY) == 1
    assert await redis.ttl(_KEY) == -1
    with pytest.raises(limits.McpRateLimitExceeded):
        async with limits.grant_call_slot(principal, effect="read"):
            raise AssertionError("unreconciled owner must retain its budget")


@pytest.mark.asyncio
async def test_legacy_counter_requires_drain_before_new_slot(principal, redis):
    await redis.set(_KEY, 1, ex=120)
    with pytest.raises(limits.McpRateLimitUnavailable, match="legacy"):
        async with limits.grant_call_slot(principal, effect="read"):
            raise AssertionError("counter state must not be interpreted as an empty owner set")
    assert await redis.get(_KEY) == "1"


@pytest.mark.asyncio
async def test_atomic_slot_admission_enforces_concurrent_budget(principal, redis):
    import asyncio

    contexts = [limits.grant_call_slot(principal, effect="read") for _ in range(8)]
    results = await asyncio.gather(*(context.__aenter__() for context in contexts), return_exceptions=True)
    acquired = [
        context for context, result in zip(contexts, results, strict=True) if not isinstance(result, BaseException)
    ]
    assert len(acquired) == 1
    assert sum(isinstance(result, limits.McpRateLimitExceeded) for result in results) == 7
    await acquired[0].__aexit__(None, None, None)
    assert await redis.exists(_KEY) == 0


@pytest.mark.asyncio
async def test_grant_call_slot_fails_closed_when_redis_is_unavailable(monkeypatch, principal):
    async def unavailable():
        raise OSError("redis down")

    monkeypatch.setattr(limits, "_get_redis", unavailable)
    with pytest.raises(limits.McpRateLimitUnavailable):
        async with limits.grant_call_slot(principal, effect="external_mutation"):
            raise AssertionError("unavailable limiter must not enter")
