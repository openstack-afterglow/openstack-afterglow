## Implementation Tasks

- [x] Reproduce the production AttributeError read-only and identify the nonexistent SDK method.
- [x] Replace the call with the Keystone user-groups API and validate the payload.
- [x] Align the test fake and add the real-proxy surface guard.
- [x] Verify the replacement calls read-only against the production container and a real SDK resource.
- [ ] Run the isolated detached-worktree `npm run test:gate` (record counts in `docs/testing.md`).
- [ ] Update CHANGELOG and docs/testing.md; stamp architecture; archive the change; commit on `fix/backup-account-real-sdk-groups`.
