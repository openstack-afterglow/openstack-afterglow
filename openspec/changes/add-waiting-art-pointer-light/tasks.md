# Tasks

## 1. Source

- [x] 1.1 `LoadingState` surface passes `interactive` to `AfterglowOrbit`.
- [x] 1.2 `VmResourcePreparation` passes `interactive` to `AfterglowOrbit`.
- [x] 1.3 Auth shell passes `interactive` (`AuthStudioShell.svelte`).
- [x] 1.4 Usage schedule reason field appears only for an extended expiry or an existing reason.
- [x] 1.5 GitHub recent-user load retries on focus after a failed first load.

## 2. Tests

- [x] 2.1 Wiring test: `LoadingState` surface passes `interactive`; section variant renders no orbit (`LoadingState.orbit.test.ts`). Negative check: removing `interactive` from `LoadingState` fails the surface test.
- [x] 2.2 Wiring test: `VmResourcePreparation` passes `interactive` (`VmResourcePreparation.orbit.test.ts`).
- [ ] 2.3 Wiring test: auth shell passes `interactive`. Not written in this change.
- [x] 2.4 Usage schedule tests updated for the extension step; reason visibility test added.
- [x] 2.5 GitHub recent-user retry regression test added.
- [x] 2.6 Full frontend unit suite under Node 22: 590 files, 7920 tests passed (after the wiring tests).

## 3. Docs and gate

- [x] 3.1 `CHANGELOG.md`, `ARCHITECTURE.md`, `DESIGN.md`, `docs/testing.md` updated.
- [x] 3.2 `python3 scripts/check_architecture.py --stamp --summary` run (source_sha256 `6309eb1d…`, 4321 files); working check passes.
- [ ] 3.3 `python3 scripts/check_architecture.py --staged` before commit (not run: nothing is staged).
- [ ] 3.4 `npm run test:gate` before commit (not run in this change).

## Limits

- Browser proof of the pointer response on the waiting screens is not done. Report it as a limit.
- The Nova `MessagingTimeout` root cause is not established. This change does not fix it.
- Archive (`openspec archive add-waiting-art-pointer-light --skip-specs --yes`) waits until 2.3, 3.3, 3.4 are done.
