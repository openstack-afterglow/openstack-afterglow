## Implementation Tasks

- [x] Observe the production symptom and verify the Cinder policy (`backup:backup_project_attribute` = `rule:admin_api`).
- [x] Mark proven exact-project connections and add the scoped owner view at every backup read site.
- [x] Add tests that fail with the production symptom without the fix and keep the strict rule otherwise.
- [x] Run the isolated detached-worktree `npm run test:gate` (exit 0; counts in `docs/testing.md`).
- [x] Update CHANGELOG and docs/testing.md; stamp architecture; archive the change; commit on `fix/auto-backup-member-ownership`.
