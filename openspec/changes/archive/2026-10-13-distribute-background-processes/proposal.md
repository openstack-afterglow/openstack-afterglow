## Why

Three controllers currently run Notion synchronization, maintenance and several native service worker loops against the same target registries. The already implemented distributed Cinder backup scheduler must become the ownership contract for all shared background workloads: work is divided by role or target, and surviving participants take over without replaying accepted mutations.

## What Changes

- Inventory every API/worker/controller/scheduler background entrypoint in Afterglow and its native Drover, Lumen, Waygate and Palimpsest service checkouts; distinguish shared work from explicitly node-local or request-owned tasks.
- Reuse the Redis-time membership, independent heartbeat, assignment and fenced execution-lease implementation added for Cinder backups as a reusable Afterglow workload coordinator. Partition Notion targets, database-backup targets and applicable resource reconciliation targets; divide global maintenance roles among eligible API processes.
- Preserve existing broker/SQL job claims as the authority for queue consumers instead of adding a conflicting scheduler. Add missing role/target fences to native service loops using their own Redis namespace and existing service dependencies.
- Keep one target's current operation owned until async/SDK work drains; failed coordination stops new work and rejoins with a new incarnation. Uncertain mutation outcomes are observed, not blindly resubmitted.
- Preserve per-process caches/catalog initialization, live websocket/request tasks and host-local runtime agents. Explicitly document these necessary local roles rather than incorrectly electing a single process for them.
- Update native repository change records separately before their implementation. No commit, push, production mutation, configuration-secret rewrite or deployment is authorized by this change.

## Capabilities

### New Capabilities

- `distributed-background-work`: service-scoped role/target ownership, shared scheduling, fenced execution and failure handoff for all shared background processes.

### Modified Capabilities

None. Existing API inputs, permissions and user policy schemas are preserved.

## Impact

Afterglow API lifecycle, Notion worker, database-backup execution, global maintenance/resource reconciliation and durable library-build consumers; native service worker/controller loops where the inventory identifies gaps. Redis and existing SQL/broker stores remain the coordination/authority boundaries. All participating replicas must share each service's Redis primary, logical DB and namespace and be upgraded together; allocation is per eligible process, not equal physical-controller weighting. Real multi-process local fixtures and consumer regressions qualify changed paths; production acceptance remains separate.
