## Tasks

- [x] Reproduce native cross-service reuse when the next service's first serial target is disabled.
- [x] Bind first-target readiness to its service and retain disabled/source/pinned behavior.
- [x] Keep consumer regressions for disabled and source-mode first targets; prove failing-before/passing-after and run related native checks.
- [x] Exercise the final task through the real multiarch Kolla smoke; run scoped architecture/full gate and update documentation.
- [x] Archive the verified correction without promoting code, changing operator pins or restarting production.

## Evidence

The isolated original-task probe returned native CLI status0 and dispatched Waygate on controller-b without any Waygate registry selection, distributing Afterglow references instead. Production pull and the previous implementation's verification remain historical evidence, not proof of this corrected source.

- Both permanent native regressions failed before the fix (CLI status0 dispatched an unprepared later published consumer), then passed after the service-owner assertion. Final native runtime:25/25; both version synchronizers:1.30.0 (`artifact://1617`).
- Final arm64 and emulated amd64 registry/native Kolla smoke passed descriptor-only selection, serial A retention after alias movement, next-invocation B, pull container preservation, reconfigure replacement/HTTP200 and mutable extra-var rejection. Each smoke removed only its owned resources (`artifact://1615`, `artifact://1616`).
- Final isolated owned-source `npm run test:gate` passed: backend3523, frontend1896, contracts141, DBfunctional28, Ruff/format530. Staged and working architecture checks matched `f022cc9f92ba8d11e06dff75012b9143bf4468b37315f419d988e7ed1a55a6dc` over2167 files (`artifact://1619`). Concurrent native-VM source and its shared review block were deliberately excluded/preserved.
- This is source verification, not a production promotion: installed operator plugin remains049a0c22; the only production action was the existing-pins five-service pull (17hosts changed0/failed0/unreachable0,39 container snapshots unchanged).
