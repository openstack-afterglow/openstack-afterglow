# Tasks

- [x] Narrow application-credential invalid classification with preserved public message and cause.
- [x] Execute-only structured warning and seven-day best-effort Redis observation; disable cleanup.
- [x] Add catalogue credential state without native calls or authority changes.
- [x] Add warning pill, recovery guidance and matching nine-locale messages.
- [x] Add focused backend and frontend regression tests.
- [x] Run exact selectors, related Lumen target, localization checks and isolated detached `npm run test:gate`; record actual outcomes.
- [x] Update architecture/testing/changelog, stamp architecture and run staged guard.
- [x] Archive change and preserve branch/worktree if shared dirty paths block integration.

## Initial implementation evidence and limits (5335a4b5)

- Source baseline: local `dev` commit `06a804a`; no fetch, push, tag, release or production call.
- Focused backend: 127 passed / 42 DB skips; frontend catalogue/lifecycle: 2 files / 17 passed.
- Related Lumen target: 58 backend passed; 11 frontend files / 254 passed.
- Final isolated detached `npm run test:gate`: exit 0; backend 14855 passed / 106 skipped, frontend 590 files / 7932 passed plus 9 Node tests, contract 262 passed, functional 292 passed / 46 skipped / 131 deselected, Ruff clean / 898 files formatted.
- First gate failed two checksum-dependent conditions from missing GNU `sha256sum` on sanitized PATH and one unrelated SIGINT supervisor timeout. Restoring the installed checksum path allowed the final gate to pass; the first supervisor timeout remains unexplained, not silently repaired or erased.
- Architecture working stamp and staged guard: `f3fe825d452e7ba3eda524f23182fab694fa8bf93e71cebe05ba4361e11ff6d8`, 4330 source files.
- Localization checks passed; compiled synthetic Chromium matrix: 108 locale/theme/viewport cases, zero document overflow, warning/help/button visible. Native identity/provider boundaries remain synthetic.
- Shared `ARCHITECTURE.md` and `docs/testing.md` are dirty and overlap this change. No merge into shared local `dev`; preserve `/Users/pieroot/code/afterglow-wt-dead-grant-ux` and `feat/dead-grant-ux`.
- Full logs and browser evidence: `~/.local/share/afterglow-proofs/dead-grant-ux-20261114/`; detail in `docs/testing.md`.

## Follow-up: Clear transient authentication failure observations

- [x] Clear an existing flag after successful native-authenticated read/mutation dispatch, with an existence check before deleting.
- [x] Preserve flags for local-only success, preview, mutation replay and failed dispatch; preserve responses on Redis failure.
- [x] Add recovery-to-catalogue, re-marking, Redis-clear failure and no-extra-write regression tests.
- [x] Update archived proposal/design/spec and bilingual changelog for self-clearing observations.
- [x] Re-run focused backend/frontend tests, isolated full gate and architecture stamp/staged guard.
- [x] Commit as a new commit on the existing feature branch and keep shared checkout untouched.

### Follow-up evidence

- Focused backend: 141 passed / 42 DB skips; frontend catalogue/lifecycle: 2 files / 17 passed.
- Final isolated `npm run test:gate`: exit 0, backend 14869 passed / 106 skipped; frontend 590 files / 7932 tests plus 9 Node tests; contract 262 passed; functional 292 passed / 46 skipped / 131 deselected; Ruff clean / 898 formatted.
- Working stamp and staged guard match source `786e0d019582d658d94b55429e8a1f7de56d719be3c8327196a904963d115246` / 4330 files.
- First follow-up gate failed only `test_redis_failover_retry.py::test_persistent_read_failure_has_only_two_retries[direct-disconnect]`: connections 5 instead of 3, commands 3, with unexpected TLS and non-Redis HTTP traffic in the fixture. Same-source full rerun passed without changing unrelated source.
- Both supervisor signal cases (`test_real_signal_stops_graceful_and_stubborn_children[15]` and `[2]`) passed in both follow-up gate runs. Earlier unexplained supervisor timeout did not reproduce.
- Full logs: `~/.local/share/afterglow-proofs/dead-grant-ux-20261114/self-clear-gate-{initial,final}.log`.
- The catalogue still projects only the first-by-grant-ID selection; a non-first invalid grant is invisible, and first-PAT disable/enable guidance does not replace the PAT. These two UI limitations remain untested and are documented, not claimed fixed.
