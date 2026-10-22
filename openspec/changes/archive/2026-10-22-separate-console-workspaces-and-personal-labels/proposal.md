## Why

The user's four screenshots show a system administrator's user-mode chooser disclosing immutable Accounts home information, listing domains/projects through global administrator observation rather than actual membership, and a redundant global workspace selector on the administrator surface. Automatically generated Personal project names cannot be given a readable display label.

## What Changes

- User-console resource browsing and scope selection use actual freshly authorized domain/project membership for administrators and ordinary users alike; global administration remains in verified administrator APIs and page-local observation filters. Account-home metadata stays in the security session but is not shown in the resource chooser.
- Remove the global workspace selector from administrator header/drawer at all breakpoints, retaining mode switching and existing page-local resource/target filters.
- Allow the verified owner of a Personal project to edit a persistent native display-label extra through a bounded server writer. Preserve project UUID, server-generated native name, ownership/provisioning markers, quotas, role grants and resources. Reuse the existing afterglow_display_name naming convention; no SQL migration or identity/native-project rename.
- Expose label editing in user project settings, propagate the label through current header/chooser/project lists and fresh login/reload, and retain actor/scope/readiness/logout/ABA guards and all nine locales.

## Capabilities

### New Capabilities

- personal-project-display-label: the real Personal owner edits only the human-facing label, including ordinary native member owners, without granting project_owner/admin.

### Modified Capabilities

- user-workspace-membership: user-mode domain/project directory and user-facing scope commits never use system-admin authority as membership.
- console-workspace-chrome: administrator surfaces omit the global chooser while user surfaces keep the existing authorized chooser without identity-home disclosure.

## Impact

Backend auth directory/switch paths and native project display projection, a bounded project metadata endpoint, shared console chrome/chooser and project settings. Admin inventory filters and permissions remain separate. Native UUID/home/password/project name/grants/quota/resources and provisioning journals are preserved. Tests/build/browser proof run in isolated public-source/native fixtures; operational DB/IAM/config/images and unrelated concurrent work/index are untouched. No automatic commit, push or deployment is requested.
