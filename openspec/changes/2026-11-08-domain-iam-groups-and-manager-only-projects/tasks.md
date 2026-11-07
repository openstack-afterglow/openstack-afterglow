# Tasks: domain-iam-groups-and-manager-only-projects

- [x] User page: remove the working-domain card and the identity-domain column/detail (foreign-home accounts stay non-editable, note names no domain). Test: `ProjectIamConsole.test.ts` (no domain id/identity column), `DomainIam.test.ts`.
- [x] Shared right slide-in primitive `ui/SlideOver.svelte` (+ `motion-slide-left` keyframe), exported from `ui/index.ts`.
- [x] Project page: table (name, description, status, created) with edit / members / remove; edit and members in `SlideOver`; removal through `AdminProjectDeleteModal`; Default project edit/remove disabled; manager-only entry; per-project drop-down, domain line and creator panel removed. `ProjectLifecycleSection` gained `showDelete`.
- [x] Backend `PATCH /api/v1/iam/projects/{project_id}` (name/description only) in `domain_iam_projects.py`; 40 tests in `test_domain_iam_project_edit.py`.
- [x] Group management: backend `domain_iam_groups.py` + `/api/v1/iam/groups*` (create/edit/delete/members, protected read-only groups, projection group hidden), `identity_roles.change_group_membership` gained an `authorize` hook; frontend `GroupIamConsole`/`IamGroups`/`IamGroupMembers`, route `/dashboard/iam/groups`, nav item, namespace `domain-iam-groups` in 9 locales. Tests: `test_domain_iam_groups.py` (10), `IamGroups.test.ts` (6), nav/Sidebar.
- [x] Project creation by domain managers only: `can_create_project` manager-only (personal own-project rule kept); creator endpoints and `project_creator` preset removed; leftover native role/grants inert. Tests updated/added in `test_domain_projects.py`, `test_project_authority_lifecycle.py`, `test_project_self_service.py`, `test_identity_roles.py`, `test_service_authorization.py`.
- [x] Roles: assignable-role catalog (`project_service._managed_roles`) already offers only project_owner (not assignable)/project_admin/project_member/project_reader plus native member/reader; custom roles are never offered. Verified, no change.
- [x] i18n: `domain-iam` keys added/removed in 9 locales, IAM guide (ko + 8 locales) updated, hardcoded-text allowlist refreshed, experience catalog regenerated (`npm run experience:catalog`).
- [x] API docs (`docs/api/{projects,admin,auth,iam}.md`), ARCHITECTURE.md, CHANGELOG.md, docs/testing.md updated.
- [ ] NOT DONE: browser verification of the new pages against a running stack (no live IAM fixture available); only component tests with mocked clients were run.
- [ ] NOT DONE: commit, deployment, live verification (domain manager creates a Waygate server in the NLP project after the manager-projection change is deployed).
- [ ] NOT DONE: archive this change after the gate and live verification.
