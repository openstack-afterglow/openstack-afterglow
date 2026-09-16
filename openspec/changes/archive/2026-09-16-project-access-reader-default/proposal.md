## Why

The administrator project-access modal currently requires a role-selection dialog for every user or group add and duplicates a principal once for every Keystone role. Administrators need a safe, one-click default assignment and a compact way to inspect and adjust the complete role set.

## What Changes

- Assign Keystone `reader` immediately when an administrator adds a user or group from the project-access modal.
- Consolidate each user or group into one members-list row with role chips.
- Add a detailed role checklist that assigns or revokes roles immediately and locks an assigned `reader` role until the principal is removed.
- Revoke every role for a principal through one reachable `제거` action.

## Capabilities

### New Capabilities

- Project access management can add users and groups with the least-privilege `reader` default and edit their remaining Keystone roles in place.

### Modified Capabilities

- Administrator project member presentation groups Keystone role assignments by principal rather than listing duplicate rows.

## Impact

- Frontend-only change in `AdminProjectAccessModal.svelte` and its component test coverage.
- Existing `/api/v1/admin/projects/{id}/members`, role catalog, and user/group role assignment endpoints remain the contract and source of truth.
