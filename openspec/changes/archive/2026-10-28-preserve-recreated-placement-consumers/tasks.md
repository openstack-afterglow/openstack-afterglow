## Investigation
- [x] Reproduce initially-empty consumer delete/recreate ABA against installed Placement in both failure handlers.

## Implementation
- [x] Remove generation/shape-only destructive rollback and scheduler cleanup; retain unresolved nonempty consumers and report IDs.
- [x] Update existing consumer/concurrency behavior regressions for the truthful reconciliation boundary.

## Verification
- [x] Run installed native suites on arm64/amd64 and affected backend/full isolated gate.
- [x] Correct architecture/operator/spec/testing receipts and the prior overly broad safety learning; preserve historical evidence.
- [x] Archive after complete source acceptance; remove only owned disposable scaffolding.
