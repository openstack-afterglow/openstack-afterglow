## Implementation Tasks

- [x] Reproduce retained revoked personal tokens and OAuth grants through real SQL-backed management HTTP routes; inspect authentication and cleanup behavior.
- [x] Exclude revoked records from management lists, make expired-grant revocation explicit, and align tutorial list behavior without deleting tombstones.
- [x] Add regression coverage for owner/project isolation, expired and repeated revocation, Lumen-default clearing, credential rejection and cleanup retention.
- [x] Verify affected tests, multi-architecture local runtimes and the actual account UI; record exact evidence and limits in existing docs/changelog and architecture review.
- [x] Archive the completed change.

## Verification receipt

- Canonical local arm64/amd64 SQL/HTTP and compiled account UI: active/expired personal and OAuth revocation, 2→1→0 counts, reload persistence, cancel, and cleanup-failure retention passed with synthetic identity/Keystone.
- Exact DB regressions10; OAuth/project files59; named MCP216; frontend tutorial/account92 passed. Compiled tutorial refresh excludes revoked records; its full reload intentionally resets in-memory fixtures.
- Scoped full `npm run test:gate` exited0: backend4595, frontend2709+runner9, consumer contract154, functional83, Ruff573files. PowerShell36 skipped because no runtime.
- Working/staged architecture digest `c439ce29330b22a793ed8f0e36d42f4c61022665f651066d5ac09fc282a21b73`/2546files; staged check used a temporary index. Shared index/review marker and unrelated WIP preserved.
- Image build context was the current shared worktree; isolated gate source was frozen HEAD plus four MCP source/test overlays, with its baseline runner. No production qualification, commit/push or deployment.
- Evidence: `/Users/pieroot/.local/share/afterglow-proofs/hide-revoked-mcp-access-20261011/`; detailed boundaries and resolved environment failures: `docs/testing.md`.
- Archived via `openspec archive hide-revoked-mcp-access --skip-specs --yes`; generic delta-spec and self-referential archive-checkbox warnings were non-blocking. All implementation/checklist items are now complete.
