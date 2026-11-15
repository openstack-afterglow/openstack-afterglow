# Fix the backup account inventory against the real SDK identity proxy

## Problem (observed in production after enabling 1.32.17)

With `[backup_system_account].enabled = true` the elected reconciler created the managed user (options, enabled state and encrypted credential verified), then every cycle stopped at the next inventory step with `AttributeError: 'Proxy' object has no attribute 'user_groups'`. The read-only report returned `complete=false` with `native_inventory_unavailable`. The failure is fail-closed: no role grant or quota write followed. The source tests passed because their fake identity object offered an invented `user_groups` method that the installed openstacksdk identity proxy does not have.

## Change

- `_direct_roles` reads a user's group memberships through the Keystone API (`GET /users/{id}/groups` on the identity proxy, the same raw-request pattern `_quota` already uses for Cinder) and treats an unexpected payload shape as an unavailable inventory.
- The test fake exposes the same `get` call, and a new test asserts that every method the fake identity offers exists on the real `openstack.identity.v3._proxy.Proxy`, so a fake can no longer invent SDK surface.

## Verified (read-only, production container)

`GET /users/{id}/groups` returns `200` with `groups`/`links` for the managed user, `role_assignments(user_id=...)` returns an empty list, and a real `RoleAssignment` resource yields the expected project/role mapping through `_direct_roles`.

## Non-goals

No change to account creation, password reset rules, quota derivation, authority rules or any other caller.
