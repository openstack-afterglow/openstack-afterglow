## Why

The reported administrator role-detail screen rejects `project_reader -> audit` with `Unsafe role implication requires review: project_owner -> audit`. `_validate_preset_catalog` treats every name outside the shipped preset closure as unsafe, even when an authenticated system administrator intentionally edits the current Keystone DAG. The project membership `_managed_roles` validator repeats that restriction; allowing only the write would make all ancestor project management roles unusable afterward.

## What Changes

- Permit administrator-selected global custom descendants without treating an unknown name as a native administrator or managed-grade escalation by itself. Keep the full transitive graph authoritative; do not special-case `audit` or add virtual grants.
- Continue bounding all recognized core/project/service preset identities against the existing allowed descendant closure. Preserve canonical identity validation, direct/indirect cycle and cross-domain guards, admin/manager prohibition, read-to-member/write escalation checks and dedicated ownership workflow.
- Align project membership validation so a graph with an approved custom descendant remains usable for existing project grades. Custom roles remain unavailable for independent project-level delegation; the system administrator controls their implication edges.
- Add endpoint regressions for the reported link, additive preset application afterward, unchanged system-admin requirements, transitive forbidden descendants and project reader assignment using the extended graph.

## Capabilities

### Modified Capabilities

- System-admin role implication management and current-DAG project membership validation distinguish custom identities from recognized privilege boundaries.

## Impact

`identity_roles.py`, `project_service.py`, their existing backend endpoint tests and role API/security/architecture documentation. No frontend wire contract, schema, database URL, native policy or production Keystone assignment/edge changes. Verification uses synthetic identity/session boundaries; production native policy meaning of the existing `audit` role is not inferred from its label.
