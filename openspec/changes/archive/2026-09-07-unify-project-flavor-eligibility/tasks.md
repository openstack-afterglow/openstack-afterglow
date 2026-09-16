## Implementation Tasks

- [x] Add shared demand parsing and project flavor eligibility models/service with Nova and GPU quota snapshots.
- [x] Add a forward-only GPU admission reservation migration/model and enforce reservation lifecycle around Afterglow VM creation.
- [x] Extend current-project and admin target-project flavor option APIs with structured eligibility while preserving inaccessible private flavor boundaries.
- [x] Recheck the shared eligibility decision before ordinary, SSE, and administrator target-project VM mutations.
- [x] Add explicit quota-managed GPU flavor access mode plus dry-run/apply reconciliation with drift-safe responses.
- [x] Replace the VM flavor picker’s duplicated quota math with selectable/blocked backend decisions and responsive reason presentation.
- [x] Extend project quota administration with staged compute/GPU policy apply and managed-flavor reconciliation preview.
- [x] Migrate resize and K3s flavor selectors/admission to intent-aware eligibility, including delta and node-count demand.
- [x] Add focused backend/frontend regression coverage for quota boundaries, target-project scope, failures, access reconciliation, and concurrent GPU reservations.
- [x] Document the direct-Nova enforcement boundary and run focused targets followed by `npm run test:gate`.
