## Implementation Tasks

- [x] Inspect current Compose inputs, runner precedence, migration/bootstrap consumers and compatibility documentation; preserve shared checkout changes.
- [x] Apply AFTERGLOW_DATABASE_URL to the Afterglow Compose consumers and align production selection without changing application-level DATABASE_URL semantics.
- [x] Apply DROVER_DATABASE_URL to Drover API, worker and migration with local fallback.
- [x] Apply LUMEN_DATABASE_URL to Lumen API, worker and migration with local fallback.
- [x] Apply WAYGATE_DATABASE_URL to Waygate API, worker and migration with local fallback.
- [x] Apply PALIMPSEST_DATABASE_URL to Hub API, worker and bootstrap with local fallback.
- [x] Update the runner to accept explicit databases and preserve resolved credentials privately; verify all consumers, shell/env-file precedence, empty/default boundaries and private env-file round trips using actual Compose.
- [x] Exercise canonical built containers against disposable external-selected and fallback database targets; report runtime/image/migration evidence separately from production compatibility.
- [x] Update examples, architecture, changelog and mandatory operational synchronization/forward/backward schema compatibility assessment; run required gates and archive the completed change.

## Verification and boundaries

- Actual Compose datastore matrix67 and private runner round-trip2 passed; shared checkout orchestration175 passed. Dollar credentials remain exact and private, including the original-input-removed entry path.
- Ten canonical service images built for arm64/amd64; all14 consumers used each selected/fallback schema with real service session factories and SQL write/read (56 passed). This proves image/engine selection, not execution of migration CLI, API lifespan or production schema upgrade.
- Full `npm run test:gate` passed in the isolated 1.30.12-based dev clone: orchestration175, Kolla27, CLI19/36PWSH skipped, backend4401, frontend2569/334files plus runner9, contract174, disposable functional35/9deselected, Ruff561files. Final source digest `d32e88081e4349e2bf97917d8521593e811fc78d2ed20a89d032b0c77b1e4d04`/2532files. `docs/testing.md` records initial failures and their corrections; failed executions are not passing evidence.
- Main `agent-runtime-security` requirements were updated to explicit service-prefixed selection and distinct mandatory production compatibility qualification; strict spec validation passed. This rapid change has no delta-spec artifact to auto-sync. Isolated archive completed as `2026-10-10-compose-service-database-urls`; this receipt was integrated without overwriting unrelated shared changes.
- No owned SQL/ORM/manifest change, no production DB access/write/migration/deployment. Actual production ledger/snapshot, original encryption keys, companion state and both writer/schema directions are unqualified. The shared checkout's separate migration084/WIP was preserved and is not covered by the isolated full gate.
