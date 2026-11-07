## Implementation Tasks
- [ ] Restore `PROJECT_WRITE_ROLE_NAMES = {admin, member}` and the gates, tests and docs that `ec82f9da` changed.
- [ ] Exclude `Default` from MCP discovery, candidates, issuance, OAuth approval and use.
- [ ] Share one reserved-name helper across user create, administrator create and rename.
- [ ] Confirm "manager only on Default" with the existing enforcement tests (no code change).
- [ ] Update ARCHITECTURE, docs, CHANGELOG; restamp architecture.
- [ ] Pass the full canonical test:gate on dedicated datastores.
- [ ] Commit on dev, push, verify exact-SHA CI, archive the change.
