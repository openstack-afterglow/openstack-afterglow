## Implementation Tasks

### Source and release qualification

- [x] Release metadata synchronized with canonical npm bump/`version:sync` (1.30.25, then 1.30.26). Frontend npm lock 1.30.19 drift outside script ownership preserved.
- [x] Shared dev/worktree/index/private state and 1.30.24 recovery points preserved; deletion plus Accounts onboarding/last-unlink safety released together.
- [x] Architecture stamp and `npm run test:gate`: 1.30.25 `f8f8f78e…` (9127/95skip, 434/5075, 181, 166, Ruff723; two earlier attempts failed only on unrelated timing tests); 1.30.26 `9749323a…` (9136/95skip, 434/5075, 181, 166, Ruff723). Reviewer P2 enrollment-marker fix and tenant-SQL email-mapping restriction each verified fail-before/pass-after.
- [x] Pushed `6d57ab65` (CI 40011414906 attempt2) and `25b9864c` (CI 40043006794) to dev.
- [x] Immutable `v1.30.25` and `v1.30.26` published (Docker/Helm success; latest equals tag revision; amd64 CI platform, arm64 local canonical build).
- [x] 1.30.25 rollout stopped at Kolla pull guard because a concurrent operator overlay (Accounts email mapping) was absent from it; pins/links reverted with zero container actions. User confirmed email mapping is intended; ported as 1.30.26.

### Schema prerequisite before writers

- [x] Writers, DB/Redis destinations and fingerprints identified; local shared stack had been running unreleased source against the production DB since 2026-10-23 12:43Z.
- [x] Encrypted SQL/Redis/config recovery point qualified by isolated restore (103 tables/4879 rows, 2197 Redis keys incl. stream support).
- [x] Restored snapshot: 1.30.26 ORM 50 tables + journal round-trip, 1.30.24 ORM 49 tables, counts unchanged.
- [x] `account_identity_transfers` already existed (ORM-created by the concurrent local writer, empty); SQL102 `IF NOT EXISTS` is a no-op, so no DDL executed.

### Canonical full-inventory Kolla rollout

- [x] Inventory parse/targets confirmed; `--skip-tags haproxy` preserves shared HAProxy.
- [x] Overlay `globals.d/94-afterglow-email-mapping.yml` backed up and retired (module directory preserved) because 1.30.26 contains the guard.
- [x] genconfig, pull, prechecks passed on all targets.
- [x] reconfigure once over full inventory without `--limit`: c1 ok124/changed5, c2/c3 ok68/changed2, failed0/unreachable0.

### Targeted local Compose and postrollout acceptance

- [x] Local canonical targeted Compose with same executor: definition hashes and 12 effective fields unchanged, backend/frontend replaced, 16 others preserved.
- [x] Fleet: 6 healthy apps + 3 workers on `25b9864c`, 710 non-target containers unchanged, fingerprints match, tracebacks 0, public health/login-options 200, deployed guard accepts the real native mapping on all controllers without writes.
- [x] No real account deletion, native grant/resource change or association transfer performed. Human GitLab login/group reflection and authenticated admin deletion UI not exercised; Identity list transport/orphan 404 not addressed.
- [x] `docs/testing.md` and receipts recorded; archive without spec deltas.
