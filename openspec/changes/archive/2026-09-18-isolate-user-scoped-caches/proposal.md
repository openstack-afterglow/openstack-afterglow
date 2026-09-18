# Isolate User-Scoped Caches (SSH Keypair Cross-User Leakage Fix)

## Why

In OpenStack Compute (Nova), SSH keypairs are strictly user-scoped (`user_id`), not project-scoped (`project_id`). The Nova database schema and API associate each keypair with a specific Keystone user account, with no `project_id` column.
However, Afterglow's `/api/v1/keypairs` endpoint erroneously used `keys.project_key("nova", pid, "keypairs")` (`afterglow:nova:{project_id}:keypairs`) as the cache key with a 15-minute TTL (`ttl_slow()`). Because frontend API requests include `cache=true` by default, when multiple users within the same project (such as DMSLAB) accessed the dashboard or VM wizard, the first user's keypair list was cached and subsequently returned to other project members. This caused:
1. Cross-user data leakage: User B could view User A's SSH keypair names and fingerprints in their keypair management list and VM creation dropdowns.
2. VM / Cluster creation failure: Selecting another user's keypair caused Nova to fail with `Invalid key_name provided`, as Nova cannot find User A's keypair under User B's token context.
3. Cache corruption: `create_keypair` and `delete_keypair` patched this shared project-scoped cache key, mixing or desynchronizing keys among users.

A comprehensive audit confirmed that Nova keypairs are the only OpenStack resource with user-level scoping in Nova/Neutron/Cinder/Glance/Manila. Other user-specific features (such as `user_dashboard`, cloud-init snippets, tutorials, and profile) already correctly scope by `user_id`.

## What Changes

- Switch `backend/app/api/compute/keypairs.py` cache key from `keys.project_key("nova", pid, "keypairs")` to `keys.user_key(uid, "keypairs")` (`afterglow:user:{user_id}:keypairs`) for `list_keypairs`, `create_keypair`, and `delete_keypair`.
- Extract `user_id` from `token_info` / `conn._afterglow_user_id` at API admission.
- Update `backend/tests/test_keypairs.py` to assert the user-scoped cache key pattern (`afterglow:user:{user_id}:keypairs`).
- Add isolation regression tests proving that two users within the same project do not share or collide on keypair cache entries.
- Document the user-scoped caching contract in `ARCHITECTURE.md` and API documentation.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `compute-keypairs-cache-isolation`: Enforce user-scoped caching for Nova keypairs, preventing cross-user visibility and cache pollution within shared projects.

## Impact

- Files:
  - `backend/app/api/compute/keypairs.py`
  - `backend/tests/test_keypairs.py`
  - `ARCHITECTURE.md`
- Security: Eliminates cross-user credential metadata leakage and resolves downstream `Invalid key_name provided` failures.
