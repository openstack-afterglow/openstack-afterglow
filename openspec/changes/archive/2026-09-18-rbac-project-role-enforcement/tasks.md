# Tasks

- [x] Implement `require_project_write` and `get_project_permissions` in `backend/app/api/deps.py` <!-- id: 0 -->
- [x] Add `GET /api/v1/projects/{project_id}/permissions` and current permissions introspection in `backend/app/api/identity/projects.py` <!-- id: 1 -->
- [x] Apply `require_project_write` guard to mutation endpoints in `keypairs.py`, `instances.py`, and `volumes.py` <!-- id: 2 -->
- [x] Add `isReader` and `canWrite` derived stores to `frontend/src/lib/stores/auth.ts` <!-- id: 3 -->
- [x] Add comprehensive test suite in `backend/tests/test_rbac_project_roles.py` <!-- id: 4 -->
- [x] Update `ARCHITECTURE.md` and stamp architecture guard with `scripts/check_architecture.py` <!-- id: 5 -->
- [x] Verify test gate with `npm run test:gate` <!-- id: 6 -->
- [x] Archive OpenSpec change upon completion <!-- id: 7 -->
