## Why

Users who sign in through SSO must be able to create a local password and recover it using their canonical registered mailbox. The current administrator guard blocks federated users by metadata, while public email recovery silently excludes users with no native password even though a guarded creation journey already exists.

## What Changes

- Reuse the authenticated profile creation journey and its mailed proof plus same-account fresh SSO login; do not infer password absence from SSO metadata.
- Route mailbox password recovery for an eligible native-absent SSO identity into the same create-only journey; keep existing-password recovery conditional on the native identity revision.
- Replace unconditional administrator SSO reset rejection with native conditional create/reset selected from an authoritative credential snapshot. Preserve explicit administrator confirmation, registered-only delivery, audit fence, cooldown and session revocation.
- Preserve unsupported-native failure before dispatch, all ownership/admission/service-identity checks and no-retry outcome handling. Explain extension/SQL prerequisites rather than falling back to stock PATCH.

## Capabilities

### New Capabilities

- `sso-password-recovery`: SSO first-password creation and registered-mailbox recovery with authoritative native state and original identity preservation.

### Modified Capabilities

None.

## Impact

Backend account recovery and administrator password reset, affected regressions, existing account/recovery UI where necessary, API/security/deployment/testing documentation and architecture. No new endpoint, schema, dependency or production mutation is planned. Existing Afterglow migration103 and native first-password-galera-v2 extension/schema qualification are required for operational activation; this implementation does not deploy them. Preserve all unrelated concurrent dev/index changes.
