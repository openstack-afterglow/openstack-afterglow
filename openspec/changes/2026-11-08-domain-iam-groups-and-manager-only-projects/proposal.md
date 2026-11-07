# OpenSpec Proposal: domain-iam-groups-and-manager-only-projects

## Why
Domain managers use `/dashboard/iam` for user and project administration. User feedback on the current pages:
- The user page exposes domain concepts a manager does not need (the working-domain card and the "account identity domain" column).
- Group administration has no domain-manager surface; only system administrators could manage groups.
- Project management forces picking one project from a drop-down before anything is visible; a table like the system-admin domain project list is expected, with edit/members/remove per row and detail editing in a right slide-in.
- Project creation was delegated through a native `project_creator` role; the product decision is that only managers create projects, and only the standard project roles (`project_owner > project_admin > project_member > project_reader`, plus native manager/member/reader) remain. Custom roles are no longer used.

## What Changes
1. **User page**: remove the domain identity card and the identity-domain column/detail. Foreign-home accounts remain non-editable with a short explanation that names no domain.
2. **Project page**: table (name, description, status, created) with edit/members/remove; edit and members open in a new shared `SlideOver` primitive. Edit uses a new domain-manager `PATCH /api/v1/iam/projects/{project_id}` (name/description only). The Default project is neither editable nor removable. The per-project drop-down, the domain line and the creator delegation panel are removed. The page is available to domain managers only.
3. **Group page**: new `/dashboard/iam/groups` page and domain-manager group endpoints (see tasks for the exact surface), shown in the same table + slide-in pattern. A nav item is added.
4. **Project creation**: `can_create_project` is true only for domain managers (and the personal-domain own-project rule). `GET/PUT /api/v1/projects/creators*` are removed; the `project_creator` preset is dropped from `ROLE_PRESETS`. Leftover native `project_creator` roles/grants stay as inert data.

## Impact / Risks
- A non-manager sole owner can no longer delete a non-personal project: `can_delete` used `can_create_project`.
- Existing native `project_creator` assignments silently stop granting creation. No data is deleted.
- Waygate/Drover/Lumen/Palimpsest are unaffected by the creator removal (their policies key on native member/manager/admin).
- Name/description edits reuse the system-admin guards (Default immutable, ownership journal, domain scope); Default's description remains editable at the API layer but the UI blocks it.

## Out of Scope
Group role assignments on projects (managed on the projects page), changing native role identities, deployment.
