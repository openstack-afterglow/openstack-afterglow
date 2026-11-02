## 1. Preserve and classify

- [x] 1.1 Capture all eight historical worktree heads and tracked/untracked deltas, plus canonical dev/index/private-file preservation baseline.
- [x] 1.2 Reconcile CLI model-role worktree, including remaining documentation.
- [x] 1.3 Reconcile GPU-admission post-release evidence commits and archived change.
- [x] 1.4 Reconcile i18n worktree against current nine-language dev contracts.
- [x] 1.5 Reconcile continuous model-reordering implementation and archived change.
- [x] 1.6 Reconcile 1.29.1 CLI integration guide commit and archived change.
- [x] 1.7 Reconcile router legacy component worktree.
- [x] 1.8 Reconcile Barbican legacy security commit.
- [x] 1.9 Reconcile Drover legacy component worktree.

## 2. Integrate and verify

- [x] 2.1 Integrate every applicable result without reverting modern behavior; record concrete supersession evidence for old alternatives.
- [ ] 2.2 Commit the canonical-dev merge/verification/cleanup policy and update affected architecture and existing documentation.
- [x] 2.3 Run focused changed-path checks, actual runtime/browser smoke where behavior changes, and the full project test gate; record actual failures without weakening checks.
- [ ] 2.4 Validate and archive this integration change after all applicable source and historical records are reconciled.

## 3. Canonical dev and cleanup

- [ ] 3.1 Commit verified integration, normally merge it into the canonical shared dev directory, and verify unrelated tracked/index/private changes remain intact.
- [ ] 3.2 Back up protected local files, remove reconciled worktrees and the isolated integration clone, preserve branches/recovery evidence, and report final canonical dev commit and any concrete exceptions.
