## Implementation Tasks

- [x] Add an Afterglow migration and model for immutable K3s provisioning intents, resource references, idempotency, and submit state.
- [x] Implement service-authenticated intent create/status/submit endpoints that keep bootstrap payloads transient and enforce caller/project/immutable-spec invariants.
- [x] Implement idempotent Afterglow Cinder/Nova submission with existing GPU quota admission, durable resource recording, retry-safe state transitions, and scoped rollback.
- [x] Add Afterglow configuration and secret-only deployment rendering for the provisioning credential, then cover endpoint, state-machine, quota, and secret-rendering contracts.
- [x] Replace Drover Stampede's direct Cinder/Nova agent provisioning with the durable intent client while preserving bootstrap ownership, job retry behavior, VM tracking, and readiness checks.
- [x] Add Drover configuration/Kolla credential wiring and focused client/Stampede/Kolla tests for success, retry, denial, unavailable, and duplicate-submission behavior.
- [x] Run focused Afterglow and Drover checks, obtain an independent security/behavior review, resolve findings, and archive the completed change.
