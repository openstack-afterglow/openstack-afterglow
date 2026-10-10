from __future__ import annotations

import pytest

from app.services.mcp_control_plane import limits
from app.services.mcp_control_plane.authentication import McpPrincipal


class _Redis:
    def __init__(self):
        self.values: dict[str, int | set[str]] = {}

    async def incr(self, key):
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, _key, _seconds):
        return True

    async def eval(self, _script, _keys, key, maximum, owner_token):
        owners = self.values.setdefault(key, set())
        if len(owners) >= maximum:
            return 0
        owners.add(owner_token)
        return 1

    async def srem(self, key, owner_token):
        self.values[key].discard(owner_token)
        return 1


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


@pytest.mark.asyncio
async def test_grant_call_slot_applies_per_grant_rate_and_releases_concurrency(monkeypatch, principal):
    redis = _Redis()
    monkeypatch.setattr(limits, "_get_redis", lambda: _async_value(redis))
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
        assert len(redis.values["afterglow:mcp:limit:project-a:grant-a:concurrency"]) == 1
    assert len(redis.values["afterglow:mcp:limit:project-a:grant-a:concurrency"]) == 0
    with pytest.raises(limits.McpRateLimitExceeded):
        async with limits.grant_call_slot(principal, effect="read"):
            raise AssertionError("rate-limited request must not enter")


@pytest.mark.asyncio
async def test_grant_call_slot_fails_closed_when_redis_is_unavailable(monkeypatch, principal):
    async def unavailable():
        raise OSError("redis down")

    monkeypatch.setattr(limits, "_get_redis", unavailable)

    with pytest.raises(limits.McpRateLimitUnavailable):
        async with limits.grant_call_slot(principal, effect="external_mutation"):
            raise AssertionError("unavailable limiter must not enter")


async def _async_value(value):
    return value
