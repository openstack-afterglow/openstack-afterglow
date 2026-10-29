## Why

Native Keystone `admin` still appears as a disabled or removal-only choice in project permission editors. The user requires it to be absent, for ordinary users and administrators alike; system administrator assignment already has its own dedicated administrator workflow.

## What Changes

- Exclude the exact case-insensitive native role name `admin` from generic project assignable-role catalogs and from all permission editor choices, including administrator user/group editors and the shared user/domain-IAM editor.
- Keep project and service roles such as `project_admin` and `lumen_admin` available under their existing authority rules.
- Preserve existing direct/native and inherited assignments when editing unrelated permissions. Do not automatically revoke live grants or convert inherited roles into direct grants.
- Preserve the existing server-side rejection of new native admin grants and the separate `system:all` administrator grant/revoke workflow. Keep the full role inventory available for administration; it is not an assignment chooser.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

Generic project role selection omits native `admin` instead of displaying a disabled/removal-only checkbox. Existing native role removal APIs remain unchanged for explicit remediation.

## Impact

`project_service.assignable_roles`, administrator access and shared member-role components, related regression tests, architecture/design and IAM/project/admin API documentation. No schema, configuration, dependency, native role graph, deployment, identity or live grant mutation is required. Verification uses local fixtures only; it is not production acceptance.
