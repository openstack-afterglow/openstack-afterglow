## Why

The local backend now intentionally shares the production `afterglow_kolla` database. Standard managed flavors that an earlier Afterglow database created remain in Nova with exact ownership evidence, but the current state holds no claims, so 17 standard flavors were reported as `native ID is not owned` and the automation status was unavailable. Administrator pages also mixed caller-token and admin-project provider reads, and the Swift overview counted per-project rescoped service-account connections that fail with 401 in 27 of 32 projects.

## What Changes

- Re-adopt only current wanted managed shapes from exact native evidence (deterministic ID, private, accepted immutable name, `afterglow:domain-compute-v1:<48 hex>` description); unsupported marked flavors stay unclaimed and retained; unrecoverable manual CPU hash markers are retained as `foreign_marker` without claims or native mutation.
- Retry the graph-lease waiter observation when the lease's own renewal touches the watched key.
- All `/api/v1/admin` routes require fresh system:all administrator authority (route regression test) and execute provider reads through the verified admin-project connection; documented exceptions keep caller authority for native-owner writes.
- Swift overview HEADs each `AUTH_<project>` account through the admin-project connection and reports 401/403 accounts separately as partially unreadable.

## Capabilities

### Modified Capabilities
- `managed-compute-flavors`: orphaned wanted-flavor re-adoption.
- `admin-provider-execution`: unified admin authority/execution rule.
