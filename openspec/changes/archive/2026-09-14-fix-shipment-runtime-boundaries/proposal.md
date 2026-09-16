## Why

Pre-push review found gaps not exercised by the healthy macOS runtime: inherited Sentinel routing can escape the local Drover datastore, Linux bind-mounted private config can be unreadable by appuser, and token/project transitions must not leak retained rows or reset same-scope pagination. Companion Drover token validation must retain support for unversioned Keystone URLs.

## What Changes

- Explicitly disable Sentinel for local Drover API/worker/migration and enforce this in the existing isolation check.
- Preserve non-root image users and private snapshot contents; grant only snapshot readers its numeric supplemental GID and group-read permission within the existing private directory. Keep generated keys and compose.env owner-only.
- Clear retained service rows on user/project changes, not same-scope refresh. Preserve quota markers when only the token rotates.
- Restore Drover versioned/unversioned Keystone URL compatibility without unscoped reauthentication.
- Keep focused regression coverage and verify actual Docker identities and runtime I/O before the final gate.

- Include prior-month days of the current Monday-based week in Lumen official organization reports.
## Capabilities

### New Capabilities
None.

### Modified Capabilities
Local datastore/config isolation, scoped frontend refresh state, and existing Drover token validation compatibility.

## Impact

Afterglow local Compose/runner and admin state handling; companion Drover auth. No production datastore, encryption key, authorization policy, API schema, or unrelated OpenStack lifecycle change. Main owns documentation, validation, commit, push and Kolla rollout.
