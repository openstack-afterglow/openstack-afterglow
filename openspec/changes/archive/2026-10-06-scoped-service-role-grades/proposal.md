## Why

Existing project_owner/project_admin/project_member/project_reader roles deliberately separate tenant management from OpenStack admin/manager. Service access still largely treats all project members alike. The user requires area_grade naming, whitespace-to-hyphen normalization, parent grade roles over granular permissions, and meaningful admin/editor/user separation (e.g. a Waygate user downloads an assigned client but cannot create/delete it).

## What Changes

- Preserve/reuse existing project/core role IDs, assignments and safe inference links; do not rename native protected roles or recreate existing underscore project roles.
- Canonicalize new/renamed custom role names to lower-case area_grade, replacing whitespace runs with hyphens in both components. Existing unrelated legacy names stay readable until explicitly renamed.
- Add explicit system-admin preview/application of idempotent project/service role hierarchies. Each service has admin -> editor -> user -> reader parents plus granular area_grade leaf roles. No automatic GET/startup cloud writes.
- Authorize service actions by explicit capabilities, independently of native OpenStack member. Keep project_owner/project_admin, service admin and verified system-admin distinct; reject transitive admin/manager delegation.
- Use effective Keystone project assignment as the single project-management authority, with safe project role editing, direct/effective role visibility, last-owner protection, original-subject bounds and explicit legacy DB-manager migration requiring a selected owner.
- Expose naming preview, preset confirmation/tree and project member role assignment in existing UI patterns; disable actions absent service capability instead of falling back to member.
- Coordinate repo-local companion changes in Waygate, Lumen, Drover and Palimpsest for direct native API enforcement, secret-bearing download/credentials, grade boundaries, and key scope/current-owner authority. No source import/private DB coupling across services.

## Capabilities

### New Capabilities

- area_grade naming and reusable granular service-grade parents.
- Explicit, idempotent role preset preview/application preserving existing roles.
- Project-scoped delegation and service capability projection without OpenStack administrative escalation.
- Equivalent native/BFF authorization; user use/download, editor create/update, admin destructive/security control, all subject to project/ownership and credential attenuation.

### Modified Capabilities

- Existing role CRUD and inference management reuse their lease, validation and session invalidation.
- Project manager authorization moves from DB manager rows to current Keystone project_owner/project_admin authority.
- Existing service UI/API action gates become service-capability-aware; OpenStack can_write remains a separate base permission.

## Impact

Afterglow backend identity/project/service-proxy authorization, role UI/account project settings/auth capability state, related behavior tests and operator/API/architecture docs. Sibling native implementations are independently tracked under repo-local changes. Existing plain member tokens will no longer imply all service permissions; operators must explicitly apply/assign service roles. Existing leaked/downloaded Drover admin certificates require separately approved rotation; this change must never hand admin credentials to reduced-grade callers. No production role assignments, credentials, rollout, commit, shared Git index or unrelated merge resolution is authorized.

Implementation contract: the session artifact local://scoped-service-role-contract.md specifies exact parent/leaf names, endpoint response shapes and ownership boundaries. Durable implementation details and verification are recorded in source/docs and this checklist after execution.
