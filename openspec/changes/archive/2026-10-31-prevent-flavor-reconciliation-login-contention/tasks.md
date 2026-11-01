## Implementation Tasks

- [x] Verify current login and background graph-lease boundaries and reproduce foreground contention with existing authentication/provisioning consumers.
- [x] Implement bounded FIFO foreground graph acquisition with expiry/cancellation/ownership/store-failure protections; retain fail-fast direct graph writers.
- [x] Make managed flavor reconciliation yield at settled unit boundaries and move read-only hardware observation outside the graph lease, preserving all native and SQL mutation fences.
- [x] Exercise password/provider HTTP consumers, queue fairness/timeouts/cancellation, background no-replay/resume, and related auth/access/instances targets plus gate.
- [x] Update architecture/testing/changelog, record exact synthetic/live limits and runtime application decision, clean owned proof scaffolding and archive the change.
