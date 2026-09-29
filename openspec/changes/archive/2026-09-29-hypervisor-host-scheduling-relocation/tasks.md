## 1. Nova API and safety

- [x] 1.1 Add admin-only service status endpoint mapping the selected hypervisor to its exact `nova-compute` service, with disable reason and cache invalidation.
- [x] 1.2 Add host-wide paginated migration and fencing-gated evacuation endpoint with per-instance request/skip/failure results.
- [x] 1.3 Cover admin authorization, state/fence guards, service identity, pagination, mixed statuses and request failures in backend tests.

## 2. Administrator workflow

- [x] 2.1 Separate liveness and scheduling presentation, add confirmed enable/disable controls and clear errors.
- [x] 2.2 Add explicit whole-host migration or evacuation controls with fencing acknowledgement and per-instance pending/failure/skip outcomes.
- [x] 2.3 Cover action visibility, confirmation, API failures, and outcomes in frontend behavior tests.

## 3. Verification and documentation

- [x] 3.1 Exercise focused backend/frontend tests, full gate, and a local browser/API smoke without changing production hosts.
- [x] 3.2 Update admin API, architecture, changelog and UI guidance; stamp architecture after final source changes.
- [x] 3.3 Archive the completed change when all implementation and verification tasks have passed.
