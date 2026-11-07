# Tasks: optimize-user-inventory-and-directory-users

- [x] Implement in-process scoped token cache in `user_inventory.py` keyed by `(sha256(token), user_id, project_id, roles)` with LRU/expiry pruning.
- [x] Keep live `get_project_access`, `assert_project_membership`, and `domain_context` running on every request.
- [x] Allow same-request sharing of `ks` and `catalog` in `project_service.py` and `user_dashboard.py`.
- [x] Make `directory_users` lookups concurrent via `asyncio.gather` in `domain_iam.py`.
- [x] Preserve handler `Server-Timing` submetrics in `main.py` middleware and emit `memberships`/`inventories` durations in `user_dashboard.py`.
- [x] Add regression test verifying scoped token reuse with spy on `assert_project_membership` and revocation denial in `test_user_dashboard.py`.
- [x] Verify all 66 backend user dashboard tests pass (`uv run pytest tests/test_user_dashboard.py`).
- [x] Verify all 57 domain IAM and membership tests pass (`uv run pytest tests/test_admin_domains.py tests/test_domain_membership.py`).
- [x] Verify backend lint/format passes (`npm run lint:backend`).
- [x] Verify latency and orchestration test suites pass (`npm run test:latency`, `npm run test:orchestration`).
- [x] Update `ARCHITECTURE.md`, `CHANGELOG.md`, `docs/testing.md`.
- [x] Archive OpenSpec change.
