# Tasks

## Afterglow authority

- [x] Add the forward-only Afterglow `gpu_quotas` schema migration and ORM model.
- [x] Restore a fail-closed Afterglow GPU quota service with canonical alias, default, project override, usage, and admission semantics.
- [x] Replace Drover quota calls in VM creation, flavor visibility, dashboard quota availability, and admin quota CRUD while preserving public API contracts.
- [x] Add audited Drover-to-Afterglow quota import tooling that rejects invalid/colliding/divergent data and verifies copied rows.
- [x] Replace Drover-proxy tests with Afterglow authority, import, flavor, dashboard, and VM-admission regression coverage.

## Drover removal

- [x] Remove Drover GPU quota API/service/model/SDK methods and quota-only Stampede admission behavior in the sibling `../drover` checkout; retain K3s GPU capacity/scheduling behavior.
- [ ] Add a forward-only Drover retirement migration only after the audited transfer and complete Afterglow rollout; update Drover tests and API documentation. (Blocked: production data and deployment authority unavailable.)

## Cutover verification

- [x] Run focused Afterglow GPU quota, flavor, dashboard, and VM creation tests.
- [x] Run focused Drover K3s GPU scheduling and SDK tests.
- [x] Review both repository changes and record ordered production rollout/rollback evidence. Production execution remains blocked pending credentials and audited source data.
