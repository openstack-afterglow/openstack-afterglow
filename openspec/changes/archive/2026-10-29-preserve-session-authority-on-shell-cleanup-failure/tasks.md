## Implementation Tasks

- [x] Preserve completed rotation/revocation/blacklist outcomes on best-effort shell-token cleanup failure, while honoring strict native cleanup and logout pending signaling.
- [x] Restore exact legacy blacklist fallback when the family pointer is absent.
- [x] Preserve revoked authority errors and retire credentials after failed consume promotion.
- [x] Isolate malformed receipts from other credential/orphan cleanup without discarding uncertain resources.
- [x] Atomically gate admission on unresolved persistent resource ownership after active/reservation TTL expiry.
- [x] Prove failing-before/passing-after regressions, affected auth/security targets and actual isolated runtime; update current-source image proof, docs/architecture/changelog and archive.

## Acceptance Boundary

- Current source/local: parent7failing-before, session6failed/4passed-before; corrected core239passed, real Redis78passed, six owned Python lint/format passed. Actual Uvicorn/SDK/native503 fixture proves new-ticket409 after liveness deletion and committed scope/new-login authority with pending exact cleanup.
- Canonical backend/worker strict-receipt images rebuilt and actual commands/full API startup/HTTP200/shutdown exercised on arm64/amd64 with matching frozen dependency-only cache; no cold-build or complete cloud/dependency readiness claim. Frontend/native source unchanged; their earlier receipts are not relabeled current reruns.
- No whole-gate rerun, commit/push, production/IAM/native resource/user-home mutation. Prior unrelated/unproven whole backend failures and external qualification gaps remain documented. Matching API cohort must drain prior receipt schema; unknown/lost resource evidence stays owned pending manual reconciliation.
