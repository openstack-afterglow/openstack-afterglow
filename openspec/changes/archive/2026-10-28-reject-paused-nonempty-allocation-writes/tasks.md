## Reproduce
- [x] Reproduce paused zero-delta ABA growth using actual installed Placement and native move_allocations.

## Correct
- [x] Reject paused nonempty admission/recheck without treating snapshot deltas as proof; preserve all-empty releases and require new hook revision.
- [x] Add regression coverage for unchanged/decreasing paused writes, old-revision rejection and empty release.

## Verify
- [x] Pass installed native arm64/amd64 suites, affected backend regressions and final isolated full gate.
- [x] Update operator/architecture/spec/testing evidence and correct prior pause safety conclusions without rewriting historical receipts.
- [x] Archive and remove owned disposable verification files; no production changes.
