## Why

The source-development Compose stack previously forced literal local database URLs and its runner rejected external targets. The user explicitly requires the five service-prefixed database URLs from `.env` or the shell to select databases so development can assess production synchronization and older/newer schema compatibility. This request supersedes the earlier local-only database policy; it does not authorize production data mutation, replication, schema migration, deployment, key rotation or deletion during implementation.

## What Changes

- Map `AFTERGLOW_DATABASE_URL`, `DROVER_DATABASE_URL`, `LUMEN_DATABASE_URL`, `WAYGATE_DATABASE_URL`, and `PALIMPSEST_DATABASE_URL` to each service's existing internal `DATABASE_URL`. In source-development Compose, unset/empty values retain the current local defaults; shell values outrank the selected env file.
- Keep API, workers and migration/bootstrap consumers on the same service-specific destination. The runner accepts configured external DBs, preserves resolved URLs in its private `compose.env` without displaying credentials, and continues protecting local cache, networks, volumes, keys and loopback ports.
- Align production and minimal standalone Afterglow DB operator inputs with required nonempty `AFTERGLOW_DATABASE_URL`; preserve sibling operator inputs and application-level `DATABASE_URL` contracts. There is no generic or local fallback in production/standalone Compose.
- Replace the obsolete local-only regression with real Compose tests covering selection, precedence, empty/default behavior, service separation, worker/migration consistency and private env-file round trips.
- Correct environment examples and deployment/development guidance. Document that selecting the same production DB is direct access, not replication; startup writers/migrations need independent approval and backup/restore proof. Make current/older/newer image and schema compatibility, ledger/checksum review, encryption-key continuity and rollback assessment mandatory whenever database-affecting work is evaluated.

## Capabilities

### New Capabilities

- Per-service external database selection for current-source Compose and its preparation runner.

### Modified Capabilities

- Development database isolation changes from an unconditional local-only policy to explicit operator-selected destinations with local fallback.
- Production Afterglow operator database selection uses the named Afterglow variable.

## Impact

Compose manifests, the local-services runner, environment example, behavioral regressions, deployment/testing guidance and architecture. No application schema or service ownership changes. Tests and container smoke use only disposable local databases and synthetic external destinations; no production credentials or database writes are used. A connected production snapshot requires compatible original service encryption keys and storage references, and DB URL selection alone does not prove compatibility.
