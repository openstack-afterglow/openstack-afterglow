## Implementation Tasks

- [x] Confirm and reuse existing admin domain GPU ceiling and exact-domain manager project GPU cap, preserving native quota and pool authority.
- [x] Persist exact-domain/project/approved-primary GPU increase requests with baseline and absolute target; add additive migration and protect shared databases from application.
- [x] Provide manager create/list and administrator queue/decision endpoints with fresh authorization, bounded pagination, concurrency safety and no quota writes on request or decision.
- [x] Require current enabled profile, same project/domain and sufficient actual domain/project ceiling readback before marking a request fulfilled; reject and uncertainty remain honest and do not replay mutations.
- [x] Expose localized manager request/status UI and discoverable admin review with manual navigation to existing quota controls; retain scope/session/readiness fences.
- [x] Verify API behavior, authorization boundaries, concurrent decisions, no-native-write guarantees, responsive UI, existing quota paths, and migration; update architecture, guides and changelog.
- [x] Record exact synthetic/live boundaries and archive after verification without production deployment or shared-DB mutation. Full gate remains blocked at the pre-existing shared architecture snapshot; live cloud acceptance is not claimed.
