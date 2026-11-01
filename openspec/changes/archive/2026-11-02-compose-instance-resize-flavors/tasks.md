## Implementation Tasks

- [x] Move resize helpers to a service and add instance-scoped resize context to user/admin composer options, history, save and operation readback with incremental quota and conservative host regions.
- [x] Backend regression coverage for resize composer options/save boundaries.
- [x] Expose resize for ACTIVE and SHUTOFF in user/admin detail with downtime notice.
- [x] Replace the resize select with the FlavorComposer flow (compose/saved/catalog) in user and admin modes.
- [x] Frontend regression coverage; locale keys in all supported languages.
- [x] Targeted tests, check/build and browser smoke; update ARCHITECTURE/docs/CHANGELOG.
- [x] Auth recovery (user interjection): recovery-dialog logout without hidden confirm; automatic local sign-out after 3 failed authentication-service attempts.
- [x] Repository gate (`npm run test:gate`), architecture stamp, archive. Completed with1.32.0 qualification: backend12375/frontend6422/contracts183/functional167; compiled browser resize acceptance and local auth outage proof in `~/.local/share/afterglow-proofs/release-1.32.0-20261102/`.
- [x] Domain IAM self-edit (user request): domain managers may change their own managed project roles (protected_user applies only to other accounts); group/inherited-only members get row edit for direct roles. Regression test `test_privileged_domain_manager_may_raise_own_project_grade`; docs/api/iam.md, ARCHITECTURE.md, CHANGELOG.
- [x] Member/project IAM writes (`project_service._membership_write`, `create_project_for_user`, `change_project_creator`) join the FIFO graph queue (`wait=True`) so background reconciliation yields instead of returning 409; regression `test_member_role_write_queues_behind_background_lease` (fails before, passes after).
- [x] Sidebar/palette "프로젝트 관리" keeps the last confirmed capability during same-scope focus rechecks; failure/scope change/logout hide it (`projectManagement.test.ts`).
- [x] Instance detail: silent refresh failures keep the loaded instance (`refreshError` warning, timeout text); accepted resize closes the dialog immediately with background refresh; console log maps Nova 403/404/409. Regressions in `instanceDetailController.resize.test.ts` (fail before) and `test_instances.py`.
