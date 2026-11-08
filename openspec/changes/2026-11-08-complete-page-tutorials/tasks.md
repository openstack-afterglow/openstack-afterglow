# Tasks: complete-page-tutorials

Status legend: `[ ]` open, `[x]` done with evidence in the line, `[!]` blocked with reason. Inventories: `inventory/*.md`. Worker fragments: `fragments/*.json` (merged).

## 0. Setup
- [x] Proposal, design, route inventories (`inventory/`).
- [x] Anchor conventions recorded in design.md (both ResponsiveTable snippets, item-scoped delete anchors, final step on a section that survives the delete, `confirm-accept`, `clickAt`, 390px walk).
- [!] Relay: Chrome relay extension not connected (`~/.omp/browser-relay/extension` must be loaded by the user). Blocks the real-session smoke only (section 8).

## 1. Pilot and verified tours (mockup mode, browser walked)
- [x] Buckets (`buckets`): create, list check, delete with confirm, trash arrival (`qa-mobile-bucket`). Walked 1440 and 390. Mock `lib/mockup/objectStorage.ts` + 5 unit tests.
- [x] Containers (`containers`): create, list check, delete with confirm, removal. Item-scoped delete anchor (pre-existing row not anchored, verified). Walked 1440. Mock `lib/mockup/containers.ts` + 4 unit tests.
- [x] Keypairs (`keypairs`): create (or import), list check, delete, confirm. Walked 1440 and 390. Mock in `computeNetwork.ts`.
- [x] Floating IPs (`floating-ips`): allocate (added header button), list check, release, confirm. Walked 1440 and 390.
- [x] Networks (`networks`): create, open row menu, delete, confirm. Walked 1440 and 390. `ActionMenu` guard keeps the menu open when the popover takes focus.
- [x] Security groups (`security-groups`): create, select, delete from rules panel, confirm. Walked 1440 and 390.
- [x] Secrets (`secrets`): create, list check, delete, confirm. Walked 1440 and 390. Key Manager beta gate overridden in tutorial mode only (`secrets/+page.svelte`).
- [x] Volume backups (`volume-backups`): create, list check, delete, confirm. Walked 390 and 1440. Note: some 390 runs failed on Vite full-reloads from peer edits; passing runs had no reload.
- [x] IAM projects (`iam-projects`): create, list check, delete through the dependency check, confirm. Walked 1440 and 390, 5/5 passing 390 runs without reload.
- [!] IAM groups (`iam-groups`): needs `isDomainManager` in tutorial auth. Decision: not changed globally. Not registered.
- [x] Admin announcements (`admin-announcements`, `?tutorial=admin`): create, list check, delete, confirm. Walked 1440 and 390.
- [x] Mockup transport: stateful secrets, compute, admin announcements, identity handlers. Dead pre-existing handlers removed (security-groups, quota, instances, networks POST, keypairs, secrets GET, MOCK_SECRET_ITEMS).

## 2. Storage area
- [ ] file-storage create wizard and share delete (`/dashboard/file-storage`)
- [ ] file-storage access-rule add/revoke (`/dashboard/file-storage/[id]`)
- [ ] file-storage share networks create/delete (`/dashboard/file-storage/networks`, beta gated)
- [ ] file-storage security services create/attach/delete (`/dashboard/file-storage/security-services`, beta gated)
- [ ] file-storage snapshots create/delete (`/dashboard/file-storage/snapshots`, beta gated)
- [ ] object-storage bucket object folder/upload/delete (`/dashboard/object-storage/buckets/[name]`)
- [ ] volumes create tour (`volume`, existing): verify anchors still match
- [ ] volume snapshots delete (`/dashboard/volumes/snapshots`)
- [ ] volume detail actions (`/dashboard/volumes/[id]`)

## 3. Network area
- [ ] load balancers create/delete (`/dashboard/network/loadbalancers`, `/new`, `[id]`)
- [ ] routers create/delete (`/dashboard/network/routers`, `[id]`)
- [ ] Waygate (`waygate`, existing): verify steps; add delete step if exposed
- [ ] topology (`/dashboard/network/topology`, `/dashboard/topology`): read-only, record "no tutorial" in design.md

## 4. Compute, containers, DB, Drover
- [ ] instances create (`vm-create`, existing): add delete-from-list step
- [ ] instance detail delete (`/dashboard/compute/instances/[id]`) with typed confirm
- [ ] account keypairs (`/dashboard/account/keypairs`)
- [ ] images (`images`, existing): verify anchors
- [ ] containers clusters create/delete (`/dashboard/containers/clusters`, `[id]`)
- [ ] containers start/stop: extend `containers` tour or record as out of scope
- [ ] database instances create/delete (`/dashboard/database/instances`, `[id]`)
- [ ] database backups create/restore/delete (`/dashboard/database/backups`)
- [ ] Drover (`drover`, existing): verify anchors; Drover detail nodegroup create

## 5. Identity, chat, account
- [ ] IAM users invite/evict (`/dashboard/iam/users`)
- [!] IAM groups (`iam-groups`): blocked, see section 1.
- [ ] chat conversations and projects (`/dashboard/chat`, `/dashboard/chat/projects`, `[id]`)
- [ ] chat agents and tools (`/dashboard/chat/tools`, `/settings`)
- [ ] account MCP tokens (`/dashboard/account/mcp`)
- [ ] read-only pages (home, notifications, activity, usage, usage-report, observability, my-resources): record "no tutorial" in design.md

## 6. Admin area
- [x] Announcements (see section 1).
- [ ] application credentials create/delete (`/admin/application-credentials`)
- [ ] chat providers, models, quotas (`/admin/chat`, `/admin/chat/models`, `/admin/chat/quotas`)
- [ ] projects create/edit/delete (`/admin/projects`, `/admin/projects/[id]/resources`)
- [ ] user credentials, roles, system admins, groups, flavors, floating IPs, networks, subnets, routers, ports (create/delete where present)
- [ ] volumes, object storage, file storage, containers, services, settings (admin)
- [ ] read-only admin pages (overview, monitoring tree, events, topology, system-info): record "no tutorial" in design.md

## 7. Shared tests and docs
- [x] Frontend: full `vitest run` 563 files / 7694 tests passed (after all merges and dead-code removal).
- [x] i18n: `tours.*` keys present in all nine locales for every registered tour (merge script checked key counts).
- [x] Backend: `tests/test_tutorial_status*.py` and `test_experience_catalog.py` pass (8 passed, 7 skipped).
- [x] Experience catalog regenerated; `--check` passes.
- [x] Architecture: tutorial registry paragraph in ARCHITECTURE.md; `docs:check` stamped.
- [x] CHANGELOG `[Unreleased]` entry for the verified tours.
- [ ] docs/testing.md: evidence for the browser walks (not written yet).
- [ ] Engine test for step selectors covers only syntax; a static check that each element selector exists in its source route is still missing.

## 8. Verification
- [x] Acceptance policy (user decision 2026-11-08): tablet-and-up only; walks at 768x1024 and 1440x1000 (390px results are history). Final walk on the last engine build (settle wait: target highlighted at once with Close+Previous only, clicks inside the target and advance clicks swallowed until the `readyElement` anchor appears, `waitAllowsInput` steps stay typeable, target loss leaves the wait at once; information steps swallow clicks on the next step's click target): all 29 create/delete tours I own passed at both widths with real clicks and typing, no Escape, `tut-` items only (`vm-create`, `instance-detail-delete`, `volume`, `buckets`, `containers`, `secrets`, `volume-backups`, `iam-projects`, `keypairs`, `floating-ips`, `security-groups`, `networks`, `volume-snapshots`, `file-storage`, `load-balancers`, `routers`, `containers-clusters`, `database-instances`, `database-backups`, `account-mcp`, `admin-projects`, `admin-flavors`, `admin-networks`, `admin-routers`, `admin-floating-ips`, `admin-ports`, `admin-announcements`, `admin-application-credentials`, `admin-object-storage`). Exception: `buckets` 768 with Enter in the name field (see testing.md). The waiting state was observed only in `database-backups` step 4 and `admin-ports` step 2; other mocks settle before their step shows. `drover`/`waygate`/`images`/`admin-*` system tours predate this change and were not walked. Mobile gate verified at 390px.
- [ ] 768px popover overlap on the VM wizard footer (`vm-create`, `instance-detail-delete` steps 2-5) hides part of the Cancel button only; required controls stay reachable. Recorded, not fixed.
- [x] `file-storage` and `account-mcp` re-evaluated under the new policy and registered (walked at 768 and 1440).
- [ ] Mockup walks for the remaining tours (sections 2–6).
- [!] Real-session smoke (one create and one delete per tour with cleanup): blocked until the Chrome relay is connected.
- [!] `npm run test:gate` on the change tree: not green as one run (see docs/testing.md 2026-11-09). Stage by stage with Python 3.12 first on PATH: Node orchestration/Kolla/CLI 266+29+56 pass, backend unit 14745 passed (one earlier run had a non-reproduced `test_concurrency_is_bounded_and_parallel` failure), contract 261 passed, functional 284 passed, lint:backend clean, docs:check and catalog check pass. Frontend unit passes except `NetworkSection.refresh.test.ts` (3, another session's `NetworkSection.svelte`), which keeps the gate red. The old line follows for history: `svelte-check` shows 2 errors in `WaygateLock.test.ts` from another session's Waygate work (not this change).
- [ ] Known issue: the tour highlight and popover do not follow when the user scrolls `#main-content` during a step (all tours). The `volume-snapshots` form does not re-fit its highlight when an error grows it. The confirm-dialog step highlights only `확인`, so `취소` is covered by the overlay (Escape is the way out and now rewinds immediately).
- [ ] Archive the change only after sections 2–8 are complete.

## 9. Wave 2 (2026-11-08)
- [x] Registered: load-balancers, routers, database-instances, containers-clusters, volume-snapshots, admin-application-credentials. 1440px walk passed for the first five and admin credentials; volume-snapshots passed at 390px.
- [!] Unregistered: `file-storage` (390px: step 2 overlay covers form fields when the submit is highlighted; the popover covers the create button when the form is highlighted). `account-mcp` (1440px: step 4 revoke button stays off-screen after the post-issue list reload; the global scroll fix did not solve it and was reverted).
- [x] Copy fixes in nine locales: container and bucket confirm steps say '확인'; volume-backup step 2 says "사용 가능한 볼륨"; floating-IP allocation help names the page allocate button.
- [x] Tutorial mode fails closed in central `fetchWithAuth` (`client.ts`): synthetic JSON when a fixture matches, `409 mockup.unsupported` otherwise. Per-module credential bypass removed.
- [!] Known open: `database-instances` step 3 says BUILD while the mock is ACTIVE; `security-groups` step 3 can show stale default-group data for a moment.
- [ ] Real-session walk: blocked. Local Keystone points to 172.30.0.253 (DMS Lab, treated as production). Needs explicit approval of a throwaway project.
- [ ] Unrelated failing test from another session: `NetworkSection.refresh.test.ts` (3 cases, button label 인바운드 허용 규칙 펼치기). `NetworkSection.svelte` is modified in the working tree by another session.
- [x] Unregistered after the 390px walk failed: `database-instances`, `networks`, `admin-announcements`, `admin-application-credentials`. Causes: tall form or list against the popover and the 48px header. Step retargeting to submit buttons was tried and reverted because the overlay blocked input. Re-registration needs an engine popover placement change and both-width walks.
- [x] Shared fixes kept: mock banner hidden during tours, instant center-before-highlight scroll, per-step `popoverSide`, `preventScroll` on dialog focus restore (verified: `admin-application-credentials` step 4), central tutorial fail-closed in `fetchWithAuth`, composer mock routes for the VM wizard.

## 10. Wave 3 (2026-11-08)
- [x] Registered and walked at 390px and 1440px (real clicks and typing, `tut-` items only): `database-backups` (starts on the backups page, creates and deletes the backup inside the instance detail panel), `admin-projects`, `admin-flavors`, `admin-networks`, `admin-routers`.
- [x] `admin-projects` start button moved into the route's `DomainScope` header so it exists before a domain is chosen.
- [x] `TutorialStartButton` hides its invite bubble while a tour runs (it covered the highlighted Stop and Delete buttons).
- [!] `instance-detail-delete` (11 steps, runs the VM wizard): passes 1440px; fails 390px at wizard steps 4 and 5 (popover covers the wizard footer). Same cause as `vm-create` at 390px. Registration decision pending the user.
- [!] `vm-create` at 390px (existing tour): steps 4 and 5 fail (popover covers `다음` and `VM 생성`), step 6 header covers the list toolbar. Pending the user.
- [x] Read-only pages recorded as "no tutorial" in design.md.
- [x] Wave 4-5: registered and walked at 768 and 1440: `file-storage` (768px popover covers Cancel only), `account-mcp` (7 steps, settled marker), `admin-floating-ips`, `admin-ports`, `admin-object-storage`. Engine: Escape on a highlighted dialog rewinds immediately to the previous valid step.
- [x] Skipped (no create action in UI): admin subnets, volumes, containers, file storage.
- [x] Wave 6: registered and walked at 768 and 1440 on the last build: `admin-groups` (6 steps), `admin-users` (8 steps, two start buttons: the invite bubble belongs to the create/delete tour, the page-tour button has a distinct label and `invite={false}`), `admin-roles` (8 steps), `admin-domains` (7 steps, create then disable: Afterglow has no domain delete). Mocks `adminGroups.ts`, `adminUsers.ts`, `adminRolesDomains.ts` with tests; `TutorialStartButton` gained `label` and `invite` props.
- [x] Engine hardening during the re-walks (see docs/testing.md): settle wait with Close/Previous only, swallowed clicks and Next, `waitAllowsInput`, `rewindOnNew` (new error alert only), Previous availability re-evaluated after DOM changes, `input`/`change` recheck, focus kept on the typing field and never left on the popover x for interactive steps, Space swallowed on a bare page, overlay re-synced on inner scroll, next step's click target guarded on information steps.
- [ ] Re-walk on the very last build: secrets, iam-projects, keypairs, buckets, containers, volume, volume-backups, security-groups, networks, floating-ips, file-storage, load-balancers, routers, containers-clusters, database-instances, admin-networks, admin-routers, admin-floating-ips, admin-application-credentials, admin-object-storage (last walked one build earlier, before the information-step form focus rule, scroll sync and `rewindOnNew`).
- [x] Real-administrator tours (owner decision 2026-11-08: real administrators only, no mock): `admin-user-credentials` (5 steps, create then delete the credential the tour created, never Reveal or Edit sensitive), `admin-settings` (8 steps, read-only tab guide) and `admin-system-admins` (3 steps, read-only: no step advances on a click, and because the highlighted Add button and the admin list contain live buttons (Revoke POSTs at once, without confirmation for other admins) every step is `readOnly`, so the engine swallows any click or keyboard activation inside the highlight; a mutation check confirmed the behavioral test fails without that guard). A guided revoke was removed: the grant API is idempotent and does not report whether it created the assignment, and a snapshot comparison outside the role-graph lock cannot tell a concurrent real grant from this tour's, so the tour could revoke another administrator's work. Central gate `tutorial/access.ts` (`canStartTour`, used by `startTour`, so the button, `?tour=` and saved-tour resume share it) refuses the tutorial profile (its synthetic admin has `isSystemAdmin: true`) and requires a live token, `isSystemAdmin`, `authReady`, no project switch or logout. No fixtures. Unit tests cover the gate and the read-only guard; none of these has been walked in a real session. Compiled-build check (local compose `frontend`, headless Chromium 1440x1000, tutorial admin profile): `?tour=admin-system-admins|admin-user-credentials|admin-settings` on an allowed mock route opens no popover, persists no tour and does not navigate, while the ordinary `admin-projects` deep link starts and persists; the three pages redirect to `/admin` in tutorial mode and render no start button.
- [!] Real-session walk on `dmslab/afterglow-test` (project `a13d5434f0fa42418fc98af16b5235ae`, created 2026-11-08 through the admin Projects page; the first POST got 409 from the role-graph lock, one retry after 20s got 201): blocked until the owner signs in on `localhost:3080` (CORS allows only `localhost:3080` and `localhost`, so the local compose `frontend` image was rebuilt from this tree and only that service was swapped). Walk `admin-user-credentials` only; do not change global administrator grants.
- [ ] Not implemented: chat (disabled in mock), `iam-groups` (tutorial auth has no `isDomainManager`), admin services (read-only), admin subnets/volumes/containers/file storage (no create action). Known: information steps leave focus on the popover x (Space or Enter there closes the tour); `admin-application-credentials` dialog first focuses its own close button while loading; `admin-object-storage` 768 step 5 popover hides the badge; `canDelete` leaves Delete enabled on soft-deleted buckets.
