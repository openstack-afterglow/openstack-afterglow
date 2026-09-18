# Tasks

- [x] Audit all caching and query scopes across backend services <!-- id: 0 -->
- [x] Migrate keypairs cache keys from `project_key` to `user_key` in `backend/app/api/compute/keypairs.py` <!-- id: 1 -->
- [x] Update existing keypair tests to verify `user_key` usage <!-- id: 2 -->
- [x] Add cross-user cache isolation regression tests in `backend/tests/test_keypairs.py` <!-- id: 3 -->
- [x] Update ARCHITECTURE.md and stamp architecture guard <!-- id: 4 -->
- [ ] Verify test gate with `npm run test:gate` <!-- id: 5 -->
