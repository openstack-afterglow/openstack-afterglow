# Tasks

## Implementation & Test-Authoring

- [x] Update docker-compose.yml startup guidance comment to document `--env-file .env --env-file docker-compose.services.env`.
- [x] Add env_file mapping and update KEYSTONE_* environment variables to prioritize LUMEN_KEYSTONE_* with OS_* fallbacks across lumen-migrate, lumen-api, and lumen-worker.
- [x] Add explicit LUMEN_KEYSTONE_* and LUMEN_ENCRYPTION_KEY example credentials to .env.example without real secrets.
- [x] Extend test_lumen_proxy.py boundary contracts to assert Compose command order, env_file inclusion, explicit LUMEN_KEYSTONE_* mappings, and absence of localhost defaults.
- [x] Forward connection and logical target projects as distinct trusted proxy headers with regression coverage.

## Verification & Cutover

- [x] Run contract test suite to verify docker-compose.yml and .env.example assertions pass.
- [x] Verify local Compose startup using documented dual env-file invocation.
