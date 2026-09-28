## Implementation Tasks

- [x] Gate `none` in `frontend/src/lib/api/chatEffort.ts` on `reasoning_none_supported`, defaulting to hidden when absent.
- [x] Add `reasoning_none_supported` to `AvailableModel` and wire `ChatPanel` → `ChatInput` (`reasoningNoneSupported`) and `normalizeEffort`.
- [x] Normalize regenerate `reasoning_effort` against the target model (`effortForModel`) with tests.
- [x] Update `chatEffort.test.ts` for supported, unsupported and missing values, including `none` → `auto` normalization.
- [x] Update `docs/api/chat.md`, `ARCHITECTURE.md` and `CHANGELOG.md`.

## Verification Evidence

- `npx vitest run`: 249 files, 1458 tests passed before the regenerate fix; `npm run test:gate` result recorded in the commit. `svelte-check --threshold error`: 0 errors, 0 warnings (2026-09-26, isolated worktree on `origin/dev`).
- Browser UI against a live Lumen with the new field was not exercised; behavior is covered by unit tests only.
