## Why

System-scope administrators lose the admin-mode entry despite native authority. Both domain and password login require mouse submission. Existing authentication binds every account to its immutable Keystone identity domain, preventing the user's requested cross-domain account and Default-project manager model.

## What Changes

- Repair native exact system:all admin detection for direct, group and actual inferred roles; project/domain admin must not escalate.
- Restore native Enter submission for domain resolution and password login without duplicate requests or IME submission.
- New domains receive an enabled `Default` project and canonical manager grant to the exact authenticated creator, including creators whose identity domain differs.
- Domain users receive Default `project_reader` after verified login. Default's effective managers are common domain administrators and receive native read access to all that domain's projects; ordinary project_owner/admin/member/reader delegation remains separate.
- Only Default-effective managers enter user IAM; keep its entry in user-mode left navigation independently of selected project. No systemadmin-only user-IAM bypass; system administration remains separate.
- Protect at least one enabled effective Default manager and prevent manager assignment on other projects, including equivalent indirect/inferred authority. Protect the Default anchor and managed native access projection from ordinary edits.
- Separate immutable identity domain/login-policy origin from session working domain. List only authorized enabled domains, allow explicit domain selection/switch with atomic session rotation and exact project-domain validation. Preserve origin/lifetime/provider binding and late-response fences.
- Permit authenticated ordinary users, including newly verified-email-registered users, to create domains when their identity domain's existing signup policy permits it. Otherwise require live systemadmin. Reuse existing signup configuration and email-verification flow, not a second global signup mode.
- Existing domains do not acquire an arbitrary first-login manager; use explicit administrator bootstrap where creator provenance is unavailable. No production native grants/projects are changed during development verification.

## Capabilities

### New Capabilities

- Default-anchored common domain management, read-only automatic membership, last-manager safety and native read-access projection.
- One account across authorized domains, post-login domain selection and safe domain switching/creation.

### Modified Capabilities

- Native effective administrator authority, keyboard login, domain creation, IAM grants/invitations, session lifecycle and user navigation.

## Impact

Backend identity/auth/dependency/session, native project membership and admin role mutation boundaries; frontend auth mapping, domain selection/creation/navigation and four-language copy. Existing Keystone account identity domains and project-specific grants are not rewritten. Native group projection uses only project_reader inherited over the target domain, never service-account impersonation or manager grants on other projects. Existing graph lease serializes Afterglow mutations; external native changes and already-issued Keystone token lifetime remain independent limits. Validate installed SDK/HTTP behavior, real Redis/SQL where affected, compiled browser flows, canonical affected images on all declared architectures, safe local deployment and health. Preserve concurrent work, private config, volumes and production data; no commit/push/production rollout in scope.
