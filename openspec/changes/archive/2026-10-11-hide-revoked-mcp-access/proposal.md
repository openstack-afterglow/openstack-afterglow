## Why

The account page reloads personal MCP tokens and OAuth grants after revocation, but both SQL list queries include revoked tombstones. Users therefore keep seeing revoked records and actionable revoke buttons. Explicit revocation of an expired grant also leaves its status `expired`, making it impossible to distinguish that action from automatic expiry in the list.

## What Changes

- Exclude explicitly revoked grants (and revoked personal-token rows) from user-facing access lists while preserving durable tombstones, audit history and Keystone cleanup retries.
- Make explicit revocation transition an expired grant to `revoked`; repeat revocation remains idempotent.
- Keep unrevoked expired records visible so users can review and revoke them. Preserve owner/project filtering, default-selection invalidation and authentication rejection.
- Apply the same list contract to tutorial mode.
- Exercise real mounted routes and SQL persistence for personal tokens and OAuth, including expired records, repeat DELETE, foreign owners/projects, access/refresh rejection and pending upstream cleanup. Verify the real account UI before and after using isolated local fixtures.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- MCP access management: revoked records disappear from the account page and its counts after refresh and reload; expired records can be explicitly revoked.

## Impact

Existing authority/list queries and the tutorial transport only; no new router, response field, schema, migration, dependency or configuration. Soft revocation remains authoritative. No production credentials, DB, OpenStack resources, shared containers, release or deployment changes. Existing unrelated worktree/index changes are preserved. Verification distinguishes local SQL/HTTP/browser behavior from real Keystone/production acceptance.
