## Implementation Tasks

- [x] Isolate local Drover Sentinel selection and enforce the existing runtime guard
- [x] Make private config readable through a narrowly mapped supplemental GID without changing application UID or keys
- [x] Clear service rows on user/project changes while retaining same-scope refresh state
- [x] Preserve quota pagination during token-only rotation and fence stale requests
- [x] Restore Drover unversioned Keystone URL compatibility and fix its guard lint
- [x] Include the full current week in Lumen organization reports across month boundaries
- [x] Run focused regressions, actual Docker config/cache checks and final repository gates
- [x] Update architecture and detailed docs, then archive the correction change

## Verification

- Afterglow `npm run test:gate`: 2729 backend unit, 1303 frontend, 124 contract and 24 real-datastore functional tests passed; backend lint/format passed.
- Drover: 620 service tests passed, 3 skipped; SDK 111 passed; portable guard 13 passed and standard Python 3.9 stamping passed. Root/versioned Keystone validation regression failed before the fix and passed afterward.
- Lumen: 1030 service tests passed, 1 skipped, 10 deselected; SDK 126 passed; lint passed. Both provider week-boundary regressions failed before the fix and the complete billing module passed 14 tests afterward.
- Rebuilt local runtime: six non-root config readers succeeded, actual Drover Redis client selected local Redis with Sentinel disabled and PING succeeded, key values and five mounted volume identities were preserved. Fourteen containers were running, all configured healthchecks were healthy, and four initializers exited successfully; workers without a healthcheck are not claimed healthy from Docker state alone.
- Authenticated local dashboard summary/quotas returned 200 and Drover statistics returned `available: true`.
- Actual rebuilt browser: an injected 401 on a marker request caused a real successful refresh and a retry with a new token; page two retained 20 users. Desktop 1440px and mobile 390px were visually confirmed without horizontal overflow; usernames were blurred only for screenshots.
