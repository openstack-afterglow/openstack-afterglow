## Implementation

- [x] Reproduce and repair Dockerfile lint/Glance image protection failures with backend regressions.
- [x] Reproduce and repair optional inventory delay, strict-quota misleading bars, sub-GB RAM percentage, and stale project replies with frontend regressions.
- [x] Update `ARCHITECTURE.md`, detailed API/domain docs, and release changelog.

## Verification

- [x] Run exact backend defect selectors and frontend usage-report tests, then exercise the usage-report route in an actual browser at mobile, tablet, and desktop widths.
- [x] Run affected named test targets and frontend type/design checks; record pre-existing failures rather than hiding them.
- [x] Pass `npm run test:gate` and architecture staged freshness guard before commit/push.

## Completion

- [x] Archive only after the local acceptance evidence is complete; keep upstream/provider or deployment gaps explicit in release reporting.
