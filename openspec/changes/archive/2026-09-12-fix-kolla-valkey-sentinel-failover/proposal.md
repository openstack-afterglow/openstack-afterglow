# Fix Kolla Valkey Sentinel failover

## Why

Production token refresh returns HTTP 503 after Kolla Valkey promotes a different controller. The Afterglow role renders `REDIS_URL` against `groups['valkey'][0]`; live evidence on 2026-09-12 showed `172.30.0.11` was a replica while Sentinel advertised `172.30.0.12` as the `kolla` master. Reads still succeed, but session timeout `SETEX` fails with `redis.exceptions.ReadOnlyError`, so refresh correctly fails closed and the browser's expired-token polls produce alternating 401/503 requests.

## What Changes

- Make the existing Redis Sentinel client preserve the username, password, and database encoded in `redis_url` when resolving a writable master.
- Render Kolla's full Valkey Sentinel controller list and monitor name into both Kolla-managed Afterglow config layers, with Sentinel enabled.
- Replace direct-primary deployment contract assertions and documentation with the failover-aware Sentinel contract.
- Keep session validation fail-closed; do not suppress `ReadOnlyError` or bypass the timeout write.

## Scope

Afterglow runtime and its repository-owned Kolla role only. Independently owned Drover, Lumen, Waygate, and Palimpsest runtimes require their own repository/package updates if they use the same direct-primary pattern.

## Completion

Focused cache and Kolla contract tests pass; a Sentinel-routed write succeeds against a fixture/current master after the first configured Valkey node is a replica; architecture/security/deployment documentation reflects the failover-aware contract.