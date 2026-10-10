"""Redis-backed per-grant rate and concurrency controls for inbound MCP."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

import anyio

from app.config import get_settings
from app.services.cache import _get_redis
from app.services.mcp_control_plane.authentication import McpPrincipal


class McpRateLimitExceeded(RuntimeError):
    """A verified grant exceeded a bounded request or call budget."""


class McpRateLimitUnavailable(RuntimeError):
    """Redis is required; MCP never downgrades to process-local limiting."""


# An active SDK thread cannot be stopped by deleting a Redis TTL. Keep each
# unique owner's slot until actual completion; a crashed worker fails closed
# until an operator confirms it has stopped and reconciles provider outcomes.
_SLOT_ACQUIRE = """
local kind = redis.call('TYPE', KEYS[1]).ok
if kind ~= 'none' and kind ~= 'set' then return -1 end
if redis.call('SCARD', KEYS[1]) >= tonumber(ARGV[1]) then return 0 end
redis.call('SADD', KEYS[1], ARGV[2])
return 1
"""


def _base(principal: McpPrincipal) -> str:
    return f"afterglow:mcp:limit:{principal.project_id}:{principal.grant_id}"


async def _check_rate(principal: McpPrincipal, *, effect: Literal["read", "external_mutation"]) -> None:
    settings = get_settings()
    maximum = (
        settings.mcp_mutation_rate_per_minute if effect == "external_mutation" else settings.mcp_read_rate_per_minute
    )
    bucket = int(time.time() // 60)
    try:
        redis = await _get_redis()
        key = f"{_base(principal)}:rate:{effect}:{bucket}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 61)
    except Exception as exc:
        raise McpRateLimitUnavailable("MCP rate limiting is unavailable") from exc
    if count > maximum:
        raise McpRateLimitExceeded("MCP rate limit exceeded")


@asynccontextmanager
async def grant_call_slot(
    principal: McpPrincipal, *, effect: Literal["read", "external_mutation"]
) -> AsyncIterator[None]:
    """Hold one cross-replica concurrency slot through the complete SDK request."""
    await _check_rate(principal, effect=effect)
    settings = get_settings()
    key = f"{_base(principal)}:concurrency"
    owner_token = uuid4().hex
    try:
        redis = await _get_redis()
        acquired = await redis.eval(_SLOT_ACQUIRE, 1, key, settings.mcp_concurrent_calls_per_grant, owner_token)
    except Exception as exc:
        raise McpRateLimitUnavailable("MCP concurrency limiting is unavailable") from exc
    if int(acquired) == -1:
        raise McpRateLimitUnavailable("MCP concurrency state requires a drained legacy limiter")
    if int(acquired) != 1:
        raise McpRateLimitExceeded("MCP concurrent call limit exceeded")
    try:
        yield
    finally:
        try:
            with anyio.CancelScope(shield=True):
                await redis.srem(key, owner_token)
        except Exception:
            # Retaining this owner token fails closed; never free another active
            # worker or mask a completed provider response when Redis is down.
            pass
