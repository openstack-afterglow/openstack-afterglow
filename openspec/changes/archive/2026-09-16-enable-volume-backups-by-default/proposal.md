## Why

Afterglow already implements the Cinder volume-backup API and UI, but the browser-local beta store initializes every feature to disabled when no preference exists. Production users therefore do not see the volume-backup navigation or page unless they manually enable it per browser, even when the cloud has an active Cinder backup service.

## What Changes

- Enable volume backups in the default beta-feature state.
- Initialize missing browser preferences from the declared defaults instead of hard-coding `false`.
- Preserve an explicit browser-local opt-out (`afterglow.beta.volumeBackups=false`).
- Keep every other beta feature disabled by default.
- Document that UI visibility and Cinder backup-service readiness are separate requirements.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `volume-backups-default`: Volume-backup navigation and flows are visible for a browser with no saved preference, while an explicit local opt-out remains authoritative.

## Impact

Affects `frontend/src/lib/stores/betaFeatures.ts`, focused store/account/navigation tests, `docs/api/volumes.md`, `ARCHITECTURE.md`, and `CHANGELOG.md`. It does not change Cinder APIs, authorization, ownership checks, persisted server state, or other beta defaults.
