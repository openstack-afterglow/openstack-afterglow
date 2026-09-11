# ADR 0001: Cache Abstraction Layer

## Status
Accepted (Phase A', 2026-05-17)

## Context
Afterglow needs Redis cache for ~85 API call sites. v1 ships a single Redis/Valkey backend, but v2 may add Memcached or alternative caches per deployment. The existing `backend/app/services/cache.py` (140 LOC) directly couples FastAPI handlers to redis-py and the `SCAN` API, which would not survive a Memcached migration without a wholesale rewrite of every call site.

We also need to enforce the **write-through forbidden** invariant. Nova `create_server` returns a partial BUILD-state response; writing that response back into the cache after a mutation would permanently stale subsequent reads until TTL expiry. The current pattern (read-through `cached_call` + explicit `invalidate` after mutation) is correct but only enforced by convention.

## Decision
- Introduce a `Cache` ABC (`backend/app/services/cache/base.py`) with `get / set / delete / incr / add_to_tag / invalidate_tag / ping / close`.
- Implement `RedisBackend` (`redis_backend.py`) over `redis.asyncio`. SCAN is exposed via a private `_scan` method only — never on the ABC.
- Keep the `backend/app/services/cache/__init__.py` re-export surface identical to the legacy `cache.py` so all ~85 call sites continue to work unchanged.
- The ABC docstring records the **write-through forbidden** invariant for `set()`: it is for read-through cache misses only, never after a mutation response.
- All invalidation flows through `delete(*keys)` or `invalidate_tag(tag)`. Pattern-based `invalidate(pattern)` continues to work via `RedisBackend._scan()` but is not on the ABC — Memcached v2 implementers will lose only that one wrapper, not the 85 call sites.
- `cached_call()` coalesces concurrent misses for the same key within one process and event loop. `asyncio.shield()` prevents a cancelled waiter from cancelling the shared origin load. Explicit refresh calls form an ordered chain behind the current same-key load, always execute their own loader, and write last so an older load cannot overwrite refreshed data.
- Self-implemented — no `aiocache` / `cashews` dependency.

## Alternatives Considered

| Library  | Reason rejected                                                                 |
|----------|---------------------------------------------------------------------------------|
| aiocache | TTL category routing and tag-set invalidation require a wrapper anyway; adds a dependency for ~30% of the surface we need. |
| cashews  | Feature-rich (decorators, locks, rate-limit) but we use ~30%; large dep + opinionated decorator-only API doesn’t fit our explicit `cached_call(key, ttl, fn)` shape. |
| Keep `cache.py` as-is | Couples all 85 call sites to redis-py; SCAN is leaked into handlers. No path to Memcached without a rewrite. |

## Consequences

### Positive
- ~300 LOC maintained in-house (small, auditable surface).
- v2 Memcached / DragonflyDB / pluggable backend can implement the same ABC without changing any call site.
- `set()` docstring makes write-through forbidden explicit and reviewable.
- Tag-set invalidation gives O(1) project-scoped flush without SCAN.
- Concurrent TTL expiry no longer amplifies one origin lookup per waiting request within a process.

### Negative
- `invalidate(pattern)` only works on Redis-class backends. Memcached v2 must implement key-prefix invalidation a different way (tag sets) before the legacy pattern helper can be removed.
- Single-flight is process-local. Multiple backend workers can still issue one origin lookup per worker when the same key expires concurrently.
- Two infra concepts to learn (tag sets + versioned keys) when adding new endpoints. Mitigated by `keys.py` builders.

### Neutral
- `_get_redis()` / `_get_client()` remain as legacy escape hatches for the handful of call sites that need a raw Redis handle (session start tracking, object-storage upload metadata, etc.). They are typed against `redis.asyncio.Redis` and will raise `RuntimeError` under a non-Redis backend — Phase B will replace these with ABC primitives.
