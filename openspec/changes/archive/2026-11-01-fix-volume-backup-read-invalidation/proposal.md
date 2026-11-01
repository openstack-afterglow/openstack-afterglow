## Why

The volume-backup page can show source-volume and server errors although its native-backed reads return HTTP 200. The read-only policy-list POST is treated as a mutation by the browser API client and invalidates the concurrent backup/volume GETs.

## What Changes

- **BREAKING**: replace the policy-list POST with GET at `/api/v1/volumes/backups/auto-backup/configs`, migrate every repository caller and regression.
- Preserve existing project ownership, reader access and mutation invalidation; no native or persisted data change.
- Do not show successful-empty backup artwork when the backup list failed.
- Record local log evidence, real-client regressions and isolated browser evidence separately from production acceptance.

## Capabilities

### New Capabilities
- `volume-backup-read-isolation`: policy listing does not invalidate concurrent resource reads; failed lists do not masquerade as successful empty lists.

### Modified Capabilities
None.

## Impact

Backup API route method, frontend policy controller, focused tests, API/testing/architecture documentation. Backend and frontend must cut over together. No migration, configuration, live service change or native cloud mutation.
