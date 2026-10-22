## Why

Password/native subject verification succeeds, but the running backend's first-login Personal preparation fails with SQL1054 because the shared `afterglow_kolla.domain_enrollments` has only19 legacy columns. Actual read-only evidence found the seven093 columns, the098 quota snapshot column and two099 topology columns absent; the096 nullable-domain postcondition is also absent. Later intent/policy tables exist, so ORM table creation did not constitute a complete upgrade. The user authorized repair and asked to make the target ready for deployment.

## What Changes

- Preserve actual image IDs, effective DB/config/keys and writer ownership before any mutation. Create a protected backup and prove isolated restoration and the exact manifest-owned missing changes on restored data.
- Drain the actual affected Afterglow auth/enrollment writers, apply only the missing093/096/098/099 postconditions in the observed DB, and retain all existing identity, credentials, grants, resources and unresolved journals. Do not fabricate a migration ledger or blindly replay all migrations.
- Restore the same running services/configuration, verify the failing ORM/runtime path and user-visible availability, and check the actual deployment target's schema prerequisites. No release/push or five-service rollout is implied by readiness.
- Record operational evidence, restoration/rollback limits and any unavailable real-user login prerequisite. No speculative auth fallback, role grant, account merge, password reset or image replacement is in scope.

## Capabilities

### New Capabilities

None. This repairs an existing deployment prerequisite.

### Modified Capabilities

- Existing first-login Personal preparation can read the complete durable enrollment schema.
- The inspected deployment target has the same required enrollment postconditions before a new API/worker rollout.

## Impact

The shared Afterglow MariaDB schema and explicitly identified Afterglow writer maintenance window are affected. MariaDB/Galera, Keystone and sibling service runtimes/data are preserved. Additive DDL implicitly commits; old/new auth semantics are not claimed rolling-compatible. Protected backup/restore precedes live mutation; existing rows, ciphertext, native IDs/passwords/home/federation/grants/resources are not migrated. Documentation/OpenSpec receipts distinguish actual SQL/runtime evidence from synthetic or unavailable user-password/production release acceptance.
