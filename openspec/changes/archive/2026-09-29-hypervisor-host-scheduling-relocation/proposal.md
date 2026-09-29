## Why

An admin can inspect a live-but-disabled compute host, but cannot change its scheduling state from the hypervisor page or move all workloads away from it. A down host additionally needs an explicit, safety-gated evacuation path distinct from live migration.

## What Changes

- Give system administrators explicit Nova `nova-compute` enable/disable controls; require a reason for disabling and keep service scheduling distinct from host liveness.
- On an up/disabled host, provide a separate confirmed whole-host migration action. On a down host, provide evacuation only after the administrator acknowledges that the source is fenced.
- Enumerate every current source instance, submit an appropriate per-instance operation, and report each request, skip, or failure without claiming that asynchronous relocation has completed.
- Preserve existing per-instance migration actions and make no automatic workload movement when changing scheduling state.

## Capabilities

### New Capabilities

- `hypervisor-host-operations`: Admin-only compute service scheduling and safety-gated host workload migration/evacuation with per-instance outcomes.

### Modified Capabilities

None.

## Impact

Admin hypervisor FastAPI routes, Nova service/instance calls and cache invalidation; Svelte hypervisor table/detail controls and outcomes; backend and frontend behavior tests; admin API, architecture, and changelog documentation. No database migration or new image architecture.
