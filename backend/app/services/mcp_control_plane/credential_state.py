"""Best-effort, expiring observations of rejected MCP application credentials."""

from app.services import cache

_TTL_SECONDS = 604800


def _key(grant_id: str) -> str:
    return f"afterglow:mcp:credential-invalid:{grant_id}"


async def mark_invalid(grant_id: str) -> None:
    try:
        redis = await cache._get_redis()
        await redis.set(_key(grant_id), "invalid", ex=_TTL_SECONDS)
    except Exception:
        pass


async def is_invalid(grant_id: str) -> bool:
    try:
        redis = await cache._get_redis()
        return bool(await redis.exists(_key(grant_id)))
    except Exception:
        return False


async def clear_invalid(grant_id: str) -> None:
    try:
        redis = await cache._get_redis()
        key = _key(grant_id)
        if await redis.exists(key):
            await redis.delete(key)
    except Exception:
        pass
