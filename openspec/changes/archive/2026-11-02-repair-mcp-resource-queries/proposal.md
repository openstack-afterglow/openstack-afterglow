## Why

Authenticated MCP inventory reads fail for volume, snapshot, backup and Waygate lists across all eight approved projects, although direct volume and VM-attached volume reads succeed. The user requires investigation against actual deployed logs, root-cause fixes, and a precise assessment of query detail and create/manage coverage for instances, volumes, networks, containers and databases.

## What Changes

- Correlate the observed read failures with deployed Afterglow/native service logs and current source; distinguish code defects, native authorization, service configuration and disabled functionality.
- Correct proven inventory adapter defects without retries, privileged credential fallback, relaxed ownership, or synthetic empty results.
- Add consumer-visible protocol regressions and exercise installed SDK/real HTTP execution for changed paths.
- Document exact current query fields, limits, related-resource coverage and missing create/manage operations for the five requested resource families. Broad new mutation features require a separately specified contract; this change first repairs existing reads and measures current coverage as requested.
- Keep production log inspection read-only. Do not roll out images, change cloud resources, schema, policies or credentials without the separately required deployment approval.

## Capabilities

### New Capabilities

- An evidence-backed live/source coverage matrix for the five requested MCP resource families.

### Modified Capabilities

- Existing project-scoped storage and Waygate MCP inventory adapters, only where root cause is proven.

## Impact

The shared consumer registry and Lumen bridge must retain existing authorization, project bindings, redaction, pagination bounds and mutation ledger semantics. No new native authority, database schema, deployment topology or broad CRUD API is introduced by the repair. Existing unrelated shared-worktree edits are preserved. Source and isolated runtime proof are reported separately from live deployed acceptance.
