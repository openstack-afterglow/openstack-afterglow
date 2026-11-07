# OpenSpec Proposal: scope-user-page-system-admin-authority

## Why
On ordinary user pages, `/api/v1/{chat,k3s,waygate,palimpsest}/*` and `/api/v1/projects/current/permissions`,
a system administrator was elevated to system scope and target-membership bypass. `deps._resolve_jwt_session`
treated any service path as an admin service path, so a cross-project request was sent with the home project as
connection and the selected project as `X-Target-Project-Id`. Waygate then ran the system-admin path, whose
Trust admission had no project role on the target. The masked result was the 403 `Waygate execution delegation is
not authorized` for NLP, while the same user succeeded in the SYSTEM project with a direct member grant.

Product rule: on non-administrative pages even a system administrator acts with ordinary project roles
(manager, member, reader), never system scope. Domain-bound manager authority is evaluated through the domain for
any project in that domain.

## What Changes
1. `deps._resolve_jwt_session`: system-admin elevation (`service_admin`, `admin_target`) is limited to
   `/api/v1/admin/*` and `/api/v1/{chat,k3s,waygate,palimpsest}/admin/*`. Other service paths use the ordinary
   `assert_project_membership` and the caller's ordinary project token.
2. Tests that pinned the old elevation are replaced: user-page requests now expect `project_membership_denied`
   without membership; admin subpaths keep elevation; membership-bearing system admins get ordinary scope; the
   production shape (system admin + Default manager + projection membership, no direct grant) passes the real
   `assert_project_membership` with connection = target and no `_live_system_admin`.
3. Documentation: ARCHITECTURE.md (system-admin service paragraph), CHANGELOG.md `[Unreleased]`, docs/testing.md.

## Out of Scope (decision required, not implemented here)
- Waygate 0.3.7 requires the caller's native project role on the target to be member, manager or admin
  (`_allows`, `_current_authority`). A domain-bound manager on NLP currently has only the projection reader row
  (`domain_projects._sync` grants `reader` with `inherited_to_projects`), so a production NLP create still fails
  after this change, now with `Waygate action is not authorized` instead of the masked execution text.
- Option 1 (proposed, not approved): project the domain manager group as native `manager` on every domain project
  instead of `reader`. Widens Nova, Neutron, Cinder and Waygate authority of every Default manager across the
  domain; reverses ARCHITECTURE's separation of domain-manager priority from the native DAG. Needs a versioned
  marker migration (`default-manager-reader:v1`), login proof and readback updates, and group-list filter updates.
