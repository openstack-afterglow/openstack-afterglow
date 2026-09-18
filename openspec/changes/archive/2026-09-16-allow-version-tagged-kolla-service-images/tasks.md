## Implementation Tasks

- [x] Update `validate_image_ref.py` in Waygate to permit non-latest version tags alongside digests.
- [x] Update `validate_image_ref.py` in Palimpsest to permit non-latest version tags alongside digests.
- [x] Update `backend/tests/test_kolla_waygate_image_ref.py` with tests for version tags, latest rejection, and bare reference rejection.
- [x] Add Palimpsest validator unit test coverage in `backend/tests/test_kolla_palimpsest_image_ref.py`.
- [x] Verify `scripts/kolla-contract.test.js` and all targeted Kolla tests pass.
- [x] Run complete gate tests (`npm run test:gate`).
- [x] Stamp architecture check and archive the change.
