## Implementation Tasks
- [x] Restore `PROJECT_WRITE_ROLE_NAMES = {admin, member}` and the gates, tests and docs that `ec82f9da` changed.
- [x] Exclude `Default` from MCP discovery, candidates, issuance, OAuth approval and use, by stored name and by the live token project name (pre-migration grants saved only the project ID).
- [x] Share one reserved-name helper across user create, administrator create and rename.
- [x] Confirm "manager only on Default" with the existing enforcement tests (no code change): `identity_roles`, `project_service` and `domain_projects` all call `assert_manager_assignment`, which also rejects roles that imply manager.
- [x] Update ARCHITECTURE, docs, CHANGELOG; restamp architecture.
- [x] Pass the full canonical test:gate on dedicated datastores (final tree `e0c5905b626a8a4bedd9f6b181a161708ff9ac7f`: backend unit 14,546 passed/106 skipped, frontend 550 files/7,615 tests, contracts 261, functional 284 passed/46 skipped, Ruff 879 files).
- [x] Commit on dev, push, verify exact-SHA CI, archive the change. `8b379096` run 42356786438 success; `b1fbca7e` run 42357788773 failed because its new endpoint test leaked `app.dependency_overrides` into 52 later tests on the same xdist worker; the fix `a7e69dca` run 42358898228 success.
