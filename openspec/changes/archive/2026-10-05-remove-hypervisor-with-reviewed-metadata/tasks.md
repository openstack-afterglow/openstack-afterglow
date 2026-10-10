## Implementation Tasks

- [x] Centralize Nova hypervisor/service identity and paginated host-server reads; implement retained history, heartbeat/uptime, provider-tree inspection and fail-closed removal verification.
- [x] Add administrator inspection/review and single-use approval endpoints with shared host locking, fresh checks, fingerprint comparison, audit and cache invalidation.
- [x] Add per-host metadata review, blocking reasons, required confirmation, removal outcome and responsive administrator UI.
- [x] Run focused behavior tests and real local HTTP/browser smoke for eligible/blocked/changed/expired/failed/verified removal paths without mutating a live cloud.
