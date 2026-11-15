## Implementation Tasks

- [x] Scan the production overview and a local dev-HEAD build (tutorial mode) at 1440x900 and 390x844; keep the local scan as the comparable baseline.
- [x] Drive the overview with agent-desktop (range toggle, chart data/telemetry disclosures, table sort, refresh, language) before and after.
- [x] Raise unselected range-toggle contrast; remove the overshoot easing token/curve; add `ResponsiveTable embedded` and `Alert flat`; apply them to the overview cards.
- [x] Add the "no overshoot curve" design-rules guard and prove it fails on the old curve.
- [x] Re-run the CDP detector and the same agent-desktop sweep on the fixed build (0 findings at both viewports).
- [x] Run the isolated detached-worktree `npm run test:gate` (exit 0; counts in `docs/testing.md`).
- [x] Update CHANGELOG, DESIGN.md and docs/testing.md; stamp architecture; archive the change; commit on `ux/dashboard-slop-pass`.
