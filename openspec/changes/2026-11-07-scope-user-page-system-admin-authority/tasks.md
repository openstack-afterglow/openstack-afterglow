# Tasks: scope-user-page-system-admin-authority

- [x] Reproduce the production failure: NLP request logged 403 at 13:47:44 and 13:48:24 UTC for user pieroot; same user 201 in SYSTEM at 12:27:47 UTC.
- [x] Identify the masked path: system-admin elevation on `/api/v1/waygate/` (0.3.7 `_current_authority` has no executor branch; probe returned the exact text).
- [x] Limit system-admin service elevation to `/api/v1/{chat,k3s,waygate,palimpsest}/admin/*` in `deps._resolve_jwt_session`.
- [x] Replace tests that pinned elevation on user pages (8 cases) with user-page denial, admin-subpath elevation, and membership-bearing ordinary scope.
- [x] Add production-shape regression: system admin + Default manager + projection membership, no direct grant, on a user page passes `assert_project_membership` with connection = target and no `_live_system_admin`.
- [x] Prove the regression fails on the pre-change routing (connection `own`) and passes after the change.
- [x] Run related backend suites: 653 passed (`test_waygate_authorization`, `test_auth_domain_boundaries`, service/lumen/palimpsest proxy contracts, `test_palimpsest_packages`, `test_flavors`, `test_dashboard_optional_usage_native_http`).
- [x] Update ARCHITECTURE.md, CHANGELOG.md `[Unreleased]`, docs/testing.md.
- [x] Run the architecture check (`npm run docs:check`).
- [x] `npm run test:gate` run on the pre-commit tree: docs:check OK, backend unit 14,619 passed/94 skipped (re-run after a format-only change), contract 261 passed, functional 284 passed/46 skipped, backend lint OK after formatting `project_service.py`. Frontend unit FAILS locally: 82 files/1,123 tests, identical to the unmodified 1.32.10 baseline (pre-existing jsdom `localStorage` issue, cause unknown); exact-SHA CI is the frontend evidence.
- [x] Projection reader→manager (approved option 1): `domain_projects` projects domain-inherited `manager`; v1 exact reader grant migrates under the lease; projection-derived effective rows excluded from manager/creator/last-manager computations (`_derived_rows`, guard `exclude_projection=True`); login proof, bootstrap check and sync use manager. The earlier cycle (projection as a legitimate source) was reverted.
- [x] Test pins updated for the reader→manager projection only (projection grant, projected roles, direct-Default-reader check); fake directory now models group provenance (`links.membership`) and group/domain revoke. Foreign-directory expectation moved from 403 to 503 (fail-closed in projection proof).
- [x] Sibling services: Lumen, Drover, Palimpsest and Waygate policies admit native `manager` (code evidence); `PROJECT_WRITE_ROLE_NAMES` (Afterglow-owned mutation routes) is not on the Waygate path; Waygate create UI is gated by the `waygate-gateways_editor` capability projection (not verified for manager-only).
- [ ] NOT DONE: commit, deployment, live re-verification.
- [ ] NOT DONE: archive this change after the gate and live verification.
