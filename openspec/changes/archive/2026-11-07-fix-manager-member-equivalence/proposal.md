## Why
Resource control is defined only by the reader/member boundary. `manager` is an extra domain-administration authority (users, projects, roles, groups), not a separate resource tier, and a manager must by default act as member and reader even when no direct `member` assignment exists. The seeded Keystone role graph has no `manager -> member` edge, so the web application's project-write gates (`admin`/`member` only) treated a manager-only user as read-only while MCP already treated `manager` as manageable. The two surfaces disagreed.

## What Changes
- One shared constant, `PROJECT_WRITE_ROLE_NAMES = {admin, manager, member}`, is the application-layer definition of "may mutate project resources". Web gates (`has_project_write_permission`, therefore `require_project_write`, session `can_write`), Cloud Shell write-authority revalidation, the frontend `canWrite` fallback and MCP project capability use it.
- MCP connections stay a two-way choice, read-only or edit (`access_level` `read`/`manage`). A manager does not add a third tier or a manager-specific capability; the choice is bounded by the current resource authority (manager counts as member).
- No schema, role-graph, grant, native policy, deployment or version change. This does not grant native service authority: Nova/Cinder/Neutron decide by their own policy for the user's token, so a manager-only token succeeds there only if native policy or role implication admits it.

## Impact
Manager-only users gain project-resource mutation in the web application where the project's native services permit it; MCP and web now agree. Readers and users without any of the three roles are unchanged. Domain-management endpoints (`require_domain_manager`, project manager checks) are untouched.
