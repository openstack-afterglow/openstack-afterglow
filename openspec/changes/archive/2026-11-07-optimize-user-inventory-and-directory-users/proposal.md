# OpenSpec Proposal: optimize-user-inventory-and-directory-users

## Why
Live measurements on `cloud.dmslab.re.kr` using the latency harness revealed significant backend processing delays:
1. `GET /api/v1/user-dashboard/summary`: 15,124 ms of pure backend computation time across multi-project memberships.
2. `GET /api/v1/iam/users`: 9,700 ms of pure backend computation time due to serial per-user Keystone calls.

In `user-dashboard/summary`, caching the entire assembled summary is rejected by Afterglow's core security invariant: live role assignments and active membership checks must be evaluated fresh on every request to prevent revoked identities from viewing project resources. However, exchanging a new Keystone scoped token (`POST /v3/auth/tokens`) on every request for every project was introducing redundant network authentication overhead.
Similarly, in `directory_users`, looking up users sequentially across domain projects created N serial roundtrips.

## What Changes
1. **Scoped Token Reuse with Role Invariant** (`backend/app/services/user_inventory.py`):
   - Cache valid scoped tokens in process memory keyed on `(hashlib.sha256(token).hexdigest(), user_id, project_id, tuple(sorted(roles)))`.
   - Live `get_project_access` continues to evaluate fresh role assignments on every request. Any change in roles or token immediately results in a cache miss and a fresh rescope.
   - Live `assert_project_membership` and `domain_context` continue to run on every request even on cache hits. Any `PermissionError` immediately evicts the cache entry and denies access.
   - Expired entries are pruned and cache size is bounded to 2048 entries.
   - Only cache when `access.expires` is a verified `datetime` in the future.
2. **Shared Admin Client & Catalog Across Projects** (`backend/app/services/project_service.py`, `backend/app/api/common/user_dashboard.py`):
   - `get_project_access` accepts optional pre-fetched `ks` and `catalog`, avoiding redundant catalog loading across N projects within the same summary request.
3. **Concurrent Directory User Resolution** (`backend/app/services/domain_iam.py`):
   - `directory_users` resolves `sorted(ids)` concurrently via `asyncio.gather` instead of a serial for-loop, preserving live Keystone resolution without caching while eliminating N serial roundtrip latencies.
4. **Server-Timing Sub-Metrics Preservation** (`backend/app/main.py`, `backend/app/api/common/user_dashboard.py`):
   - `request_logging_middleware` in `main.py` appends to any existing `Server-Timing` headers set by route handlers instead of overwriting them.
   - `user_dashboard.py` records `memberships;dur=..., inventories;dur=...`.
