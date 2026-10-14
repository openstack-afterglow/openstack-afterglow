## Context

Afterglow's new Cinder backup coordinator already supplies Redis server-time membership and leadership, a separate heartbeat, stable target assignment and atomic assignment/execution-lease claims. Notion still scans every target in every worker, Trove cron executes from every Notion process, several API maintenance loops are fire-and-forget, and library admissions/recovery use process-local queues/tasks. Native service queue/operation ownership must remain in those repositories.

## Goals / Non-Goals

**Goals:**
- Every shared background process has an explicit service-scoped role, target or authoritative queue claim.
- Global roles and resource targets are divided among eligible live processes, including late joins; survivors take over after fenced lease expiry/drain.
- Only a leader scans target registries; SDK/HTTP execution cannot stall membership or scheduling.
- Preserve current authorization, source identity, policy inputs, journals, recovery and local caches.

**Non-Goals:** production deployment, credentials or IAM changes, a new external scheduler/broker/package, physical-controller weighting, provider data-copy/restore guarantees, or automatic replay of uncertain mutations.

## Decisions

1. **Reuse the existing coordinator.** Generalize the backup-only name into `WorkDispatcher`; retain the same default backup protocol and fully migrate its imports, with no alias path. Add role eligibility and membership-change role balancing rather than duplicating the implementation.
2. **Roles for indivisible shared loops; targets for independent resources.** API maintenance roles run as separately supervised assigned children. Notion sync and Trove backup partition concrete targets. Library/import work is admitted durably and claimed by build/import identity. Existing SQL/broker consumers remain competing consumers because the queue already divides work atomically. Per-process cache/catalog setup, request streams and host agents remain local.
3. **Independent liveness and execution leases.** Register hostname/PID/random incarnations; Redis TIME evaluates liveness. Revocation prevents new work, children cancel and drain SDK threads, and only token owners release. A task-local checkpoint guards new provider mutations after awaited boundaries; cleanup still closes owned connections.
4. **Authority survives queue reconstruction.** Ready sets are hints; policy/SQL/accepted-unknown journals are authoritative. Discovery rebuilds lost hints. A surviving worker observes submitted work instead of blindly creating it again.
5. **Native service boundaries remain native.** Each service receives a repo-local change before edits and uses its current Redis/SQL/broker dependencies. Afterglow cannot elect a worker for a remote service by changing BFF configuration.
6. **No role assignment for local state.** Every process still initializes its own memory and owns its live requests/sockets. Docker runtime management is host-scoped; Kubernetes management is deployment-scoped. This avoids a leader on one controller managing only its local Docker socket while other nodes drift.

## Risks / Trade-offs

- Shared Redis primary/DB/namespace and durable authority state are prerequisites; divergent stores or data loss defeat duplicate prevention. Fail closed and document this boundary.
- A provider that lacks idempotency/fencing cannot be made universally exactly-once by a TTL lease. Accepted/unknown submissions retain durable records and are reconciled, not replayed.
- Membership-change role balancing can revoke long loops; the successor must wait for execution-lease release/expiry while the former owner drains. Tests exercise late replies and shutdown.
- Per-process balancing differs from physical-controller balancing when worker counts/capabilities differ. All replicas must upgrade and use consistent service configuration.
- Concurrent public WIP may fail broad gates. Validate changed consumers and real local processes, preserve unrelated files, and report unqualified production/container/mixed-version boundaries explicitly.
