## Implementation Tasks

- [x] Confirm the existing hidden toggle/hourly heuristic/force failure with a local execution receipt and define the shared calendar policy contract.
- [x] Implement owned, write-authorized, validated policy create/read/update/pause/delete and normalize persisted legacy policy without dropping existing backups or force consent.
- [x] Implement calendar due dispatch in actual startup worker with renewable cross-replica lease, durable slot claim, revision/pause fences and connection shutdown.
- [x] Reconcile accepted/creating/available/error/unknown and prune only completed, owned, dependency-safe managed backups; prove 0 tiers and coincident schedules do not create extra backups.
- [x] Expose create/edit/pause/remove and next/last/result on backup page and reachable list/detail entry points at every width; remove the blind activation toggle and localize all four catalogs.
- [x] Keep meaningful API/ownership/write/schedule/retention and UI consent/project-isolation regressions; remove obsolete wiring/name/default assertions rather than repinning them.
- [x] Exercise real Redis, installed SDK/loopback Cinder, actual timer and real browser save-to-scheduled-create/status/retention; verify related selectors, targets, compiler/catalog/style and scoped architecture.
- [x] Update current API/public guides/design/architecture/changelog with exercised evidence and production/auth/storage/restore limits, then archive this rapid change.

## Qualification boundary

Feature/native/browser acceptance is complete; this is local source, not deployed. Storage709backend/142frontend and nativeSDK/Redis15cases, actual minute2runs, real main startup/shutdown,56responsive locale/theme conditions, public-guide4locales and related style pass. Full gate was executed on frozen public current working source: backend6003pass/91skip/11outside-scope managed-grant/block-tracking deletion failures; separately frontend3317+9, contracts174, functional154pass/27deselected. Svelte volume diagnostics0 with unrelated database PageState error1/legacywarnings3; overall backend format7outside-scope files fail, feature7files pass. No shared index/private inputs/production state was changed. See docs/testing.md and evidence/verification.json; no commit/push/deployment acceptance.
