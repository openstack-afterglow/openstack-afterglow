## Implementation Tasks

- [x] Fit desktop chat settings within viewport height while preserving compact-screen scrolling.
- [x] Diagnose and repair Perplexity search execution evidence and failed tool status.
- [x] Provide root Compose deployment and smoke tests for sibling packages.
- [x] Verify actual model prefixes and capacity through the local Compose runtime.
- [x] Expose actual included/deferred context components and token proportions.
- [x] Exercise integrated runtime and responsive browser behavior with regression gates.
- [x] Keep synchronous Keystone validation outside Lumen's API event loop without changing authorization.
- [x] Update architecture/detail documentation and archive verified changes.

## Verification evidence

- Real source-built `afterglow-local-services` passed authenticated migration/API/worker readiness, BFF discovery/list and owned-conversation context-preview smoke, then passed again after `services:down` and `services:up`.
- The same nine existing `afterglow` containers remained running across the dedicated project's down/up cycle. Private local auth keys, model metadata and the owned conversation survived restart.
- Actual Sonar metadata projected public ID `perplexity/sonar` and a 128,000-token window. GLM-5.3 without exact catalog metadata remained unknown; no fallback capacity was invented.
- Settings and context inspection were visually exercised at 390×844, 820×1180 and 1440×900. The real Compose inspector showed separate input, response reserve, safety and remaining capacity without horizontal overflow; mobile used the full-screen modal contract.
- Frontend health/auth behavior: 22 hook tests passed. Removed six landing tests that asserted source text, exact wording and implementation wiring rather than observable behavior; the public-health regression does not bypass protected-route redirect coverage.
- Live provider gap: Perplexity API credentials were unavailable locally. Source preservation and failed-tool status were verified with installed-bridge regression tests and Lumen's separate process tests, not a paid Sonar completion. No live-source success is claimed.
- Final `npm run test:gate` passed: 2,725 backend unit tests, 1,285 frontend tests, 120 consumer contracts and 24 disposable-database functional tests; backend Ruff checks and formatting passed. Existing deprecation warnings remain. Gate output: `artifact://5965`.
- Root and Lumen working-source architecture stamps and staged-index freshness checks passed. No source was staged, committed, pushed or deployed to production by this change.
