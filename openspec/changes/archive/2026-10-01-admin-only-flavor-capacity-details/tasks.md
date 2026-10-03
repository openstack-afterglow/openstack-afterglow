## Implementation Tasks

- [x] Pass the existing wizard administrator mode into the shared flavor selector and default to hiding operator details.
- [x] Hide per-host CPU/RAM ceilings, candidate-host counts and NUMA/Nova diagnostics in consumer rows/cards and selected-flavor details; retain administrator information and consumer specifications, quota and availability.
- [x] Update behavior regressions for both presentation modes and run the exact selector, relevant target and frontend type checking.
- [x] Smoke the actual application in Chromium with synthetic identity/API fixtures for consumer and administrator surfaces, selection, blocked choices and responsive cutovers.
- [x] Update the existing detailed, design, architecture and changelog documentation with scope and verification evidence; preserve other sessions' review state.

## Verification Evidence

- Exact selector: `npm run test:target -- frontend:src/lib/components/wizard/__tests__/SelectFlavor.test.ts` — 1 file / 14 tests passed.
- Relevant target: `npm run test:target -- instances` — backend 377 and frontend 15 files / 100 tests passed.
- Type checking: `npm --prefix frontend run check` — 2,127 files, 0 errors, 0 warnings.
- Full frontend units: `npm run test:unit:frontend` — 275 files / 1,862 tests and 9 file-log runner tests passed.
- Actual application: rebuilt arm64 frontend deployed locally with Compose `--no-deps --no-build --wait`; healthy, unchanged configuration hash, environment key/value pairs and normalized mounts. amd64 build and Node execution also succeeded. No production deployment or real VM creation.
- Chromium synthetic identity/API: ordinary consumer and administrator identity in consumer mode do not render host ceilings, candidate-host counts or NUMA/Nova diagnostics. Administrator mode retains row/card ceilings and warnings plus selected-flavor host count and Nova caveat. Specs/quota remain visible; selecting the available flavor advances to settings and returning preserves an enabled Next. Insufficient and unavailable rows remain disabled in both modes.
- Both presentation modes at 390, 767, 768, 1023, 1024 and 1440px: actual visible cards/rows and panel have zero horizontal overflow. Card/row cutovers follow the panel container; 767px rows and 768px cards are intentional. Consumer dark/light and administrator light screenshots inspected. No page errors during administrator changed-path smoke; early unrelated dashboard fixture/bootstrap failures are not claimed as application-wide error-free QA.
- Architecture review: scoped staged guard passed in an isolated review root and temporary index. Shared working architecture and real index were byte/hash unchanged during that check. The actual committer must review and stamp the eventual complete staged set.
- Scope: frontend presentation only. Backend responses, authorization, quota/capacity admission, polling and pre-submit checks are unchanged. Rapid schema has no delta specs to sync; archive follows completed implementation tasks.
- Full `npm run test:gate` was not run; no commit or production rollout is part of this change. Synthetic browser proof does not verify real OpenStack scheduling.
- Archived with `openspec archive admin-only-flavor-capacity-details --yes --skip-specs` to `openspec/changes/archive/2026-10-01-admin-only-flavor-capacity-details`. All tasks complete. CLI emitted a non-blocking no-delta warning; this rapid schema intentionally contains proposal/tasks only and has no spec sync work.
- Owned QA browser/profile and disposable amd64 image were removed after smoke proof.
