# Route inventory: admin-b (projects through end of list)

Source: read-only subagent MinimumVulture, 2026-11-08. Verify against source before relying on a line.

1|ROUTE: /admin
2|FILE: frontend/src/routes/admin/+page.svelte
3|CREATE: none
4|DELETE: none
5|OTHER_MUTATIONS: none. It only reads data: a refresh button (`admin-ops:monitoring.refresh`), plus links to /admin/monitoring, /admin/events, /admin/users|projects|roles|groups and other resource pages. The domain usage table auto-refreshes every 60s.
6|EXISTING_TOUR: none
7|TOUR_MOUNT: no
8|NOTES: Admin overview with notifications, instance stats, donut and KPI cards, recent events, domain usage table, service counts and identity counts. A 403 on /api/v1/admin/overview sends the user to /dashboard. The admin `+layout.svelte` shows a 404 page unless `$isAdmin` is true and auth is ready (or the mock admin is active).
9|
10|ROUTE: /admin/projects
11|FILE: frontend/src/routes/admin/projects/+page.svelte (wraps `DomainScope` → `$lib/components/admin/projects/AdminProjectsPage.svelte`)
12|CREATE: header button `admin-identity:projectPage.create` opens `AdminProjectCreateModal`, a custom dialog titled `projectCreate.title`. Fields: name (required), description, and an enabled switch (`projectCreate.enabledLabel`). Submit is `actions.create` (disabled until a name is entered) and calls POST /api/v1/admin/projects?domain_id=…. No data-tour.
13|DELETE: row button `actions.delete` (a danger button) opens `AdminProjectDeleteModal` (FormModal, `projectDelete.title`). It is async: it first runs a resource check showing a per-kind count list, with `projectDelete.recheck` and per-row `projectDelete.cleanup` links to /admin/projects/[id]/resources?kind=…. Submit `actions.delete` stays disabled unless every resource count is 0 and `can_delete` is true. Calls DELETE /api/v1/admin/projects/{id}. A 409/503 re-shows the blocking report. Irreversible (`projectDelete.irreversible`).
14|OTHER_MUTATIONS: edit (`actions.edit` → `AdminProjectEditModal`: name, description, enabled; PATCH; submit `projectEdit.submit`). Permissions (`projectTable.permissions` → `AdminProjectAccessModal`): users/groups tabs, a "+" button adds a principal as reader (POST /api/v1/admin/roles/assign or assign-group), a per-member `projectAccess.permissions` panel toggles roles (POST/DELETE), and you can remove a member. Copy-ID button.
15|EXISTING_TOUR: none
16|TOUR_MOUNT: no
17|NOTES: System-admin only. `DomainScope` requires choosing a domain in the "domain" SearchSelect (`domain-admin:scope.domain`) first; until then the page shows `scope.required` and nothing below it renders. The selection is stored in the `?domain_id=` URL param. The reader shortcut needs a reader role to exist, otherwise `projectAccess.readerMissing` is shown. Auto-refresh is 60s, and the project name filter uses native server-side search.
18|
19|ROUTE: /admin/projects/[id]
20|FILE: frontend/src/routes/admin/projects/[id]/+page.svelte (wraps `DomainScope` → `AdminProjectDetailPage.svelte`)
21|CREATE: none
22|DELETE: none
23|OTHER_MUTATIONS: none. Read-only tabs: overview (`projectDetail.overviewTab`), members (`projectDetail.membersTab`, a table) and activity (`projectDetail.activityTab`, `ActivityLogTable`). Has a back link (`projectDetail.back`).
24|EXISTING_TOUR: none
25|TOUR_MOUNT: no
26|NOTES: Needs `?domain_id=` matching the project's domain (the list page links include it). A domain mismatch gives a "foreign domain" error.
27|
28|ROUTE: /admin/projects/[id]/resources
29|FILE: frontend/src/routes/admin/projects/[id]/resources/+page.svelte → `$lib/components/admin/projects/ProjectResourceMonitor.svelte`
30|CREATE: none
31|DELETE: per-resource `admin-identity:resourceMonitor.remove` (danger-outline) opens a FormModal (`resourceMonitor.confirmTitle`). The user must type the exact resource ID into the `resourceMonitor.confirmId` field before submit `resourceMonitor.remove` enables. It is async: the inventory is re-read just before deleting, then DELETE /api/v1/admin/projects/{id}/resources/{kind}/{rid}. The result shows as a `resourceMonitor.pending` or `unknownStatus` pill.
32|OTHER_MUTATIONS: none. A kind selector (`resourceMonitor.kind`, 29 kinds such as instances, volumes, networks, secrets, child_projects…) is stored in `?kind=`, plus a refresh button.
33|EXISTING_TOUR: none
34|TOUR_MOUNT: no
35|NOTES: Not wrapped in `DomainScope`. It needs `?domain_id=` in the URL, otherwise `resourceMonitor.invalidScope` is shown. The normal way in is the project delete modal's "cleanup" link. System-admin only. Secret kinds hide their names.
36|
37|ROUTE: /admin/quotas
38|FILE: frontend/src/routes/admin/quotas/+page.svelte
39|CREATE: none
40|DELETE: none
41|OTHER_MUTATIONS: (1) `GpuQuotaRequests` (adminMode) is the GPU quota request queue: `openDomain` jumps to the domain pool editor, and pending rows have a note field plus `fulfill` and a second decline button (label truncated in grep). (2) `ComputePoolPanel` (adminMode, shown once a domain is selected): an `enablePool` checkbox with `savePool`; per-project caps via a project SearchSelect, `saveCap` and `removeCap`; plus `verifyRemoveCap` for stale caps. (3) `ProjectQuotaForm`: a per-section save button `quotaForm.saveSection` (compute/storage/network/file_storage) sends only the changed fields.
42|EXISTING_TOUR: none
43|TOUR_MOUNT: no
44|NOTES: System-admin only. Flow: choose a domain (`quota-domain-scope` SearchSelect) and/or a project (`ProjectSelector`), and the quota form loads. An info alert (`compute-pools:legacyHelp`) links to /admin/domains/{id} (`managePools`). The file-storage section depends on Manila being enabled. Strings use the `admin-identity` namespace (`quotaPage.*`).
45|
46|ROUTE: /admin/roles
47|FILE: frontend/src/routes/admin/roles/+page.svelte
48|CREATE: header `admin-identity:rolePage.create` opens `RoleMetadataModal` (FormModal titled `rolePage.create`). Fields: area (`roleMetadata.area`, required), grade (`roleMetadata.grade`, required); the role name is composed from them and previewed via `roleMetadata.namePreview`. Also description and an optional domain ID (`roleMetadata.domain`). Submit `roleMetadata.create` calls POST /api/v1/admin/roles. A second header button `rolePresets.preview` opens a preset FormModal; `rolePresets.apply` asks a confirmDialog (`rolePresets.confirm`) and then POSTs /roles/presets/apply.
49|DELETE: `RoleDetailPanel` (opened by clicking a role name) has `roleDetail.delete`, which opens a FormModal (`rolePage.delete.title`). The user must type the exact role name (`rolePage.delete.confirmLabel`), then submit `rolePage.delete.submit` (danger) calls DELETE /api/v1/admin/roles/{id}. Blocked for protected, retired, or linked roles (the role must have no parents or children) via `deleteDisabledReason`.
50|OTHER_MUTATIONS: edit (`roleDetail.edit` → same modal; PATCH description, plus name if not protected or native). Implication edges: checkboxes in the detail panel (`roleDetail.inheritLabel`) PUT/DELETE /roles/{id}/implies/{child}. A list/tree ToggleGroup switches views.
51|EXISTING_TOUR: none
52|TOUR_MOUNT: no
53|NOTES: System-admin only; otherwise shows `rolePage.unauthorized.*`. Every mutation button is disabled while data is stale or loading (`canMutate`). Auto-refresh is 60s. Applying presets switches to the tree view.
54|
55|ROUTE: /admin/routers
56|FILE: frontend/src/routes/admin/routers/+page.svelte
57|CREATE: header `admin-network:routersPage.actions.create` opens `AdminRouterCreateModal` (custom dialog, `adminRouterCreateModal.title`). Fields: name (required) and an optional external network select (`adminRouterCreateModal.externalNetworkLabel`, default `noNetwork`; the list is filled from /admin/all-networks filtered to is_external). Submit `adminRouterCreateModal.create` calls POST /api/v1/admin/routers. No data-tour.
58|DELETE: row `adminRoutersTable.delete` opens `AdminRouterDeleteModal` (`adminRouterDeleteModal.title`); submit `adminRouterDeleteModal.delete` calls DELETE /api/v1/admin/routers/{id}. Simple confirm, no typed confirmation.
59|OTHER_MUTATIONS: edit/rename (`adminRoutersTable.edit` → `AdminRouterEditModal`, name only, PUT).
60|EXISTING_TOUR: none
61|TOUR_MOUNT: no
62|NOTES: Inventory route: the layout wraps it in `AdminInventoryScope` (domain/project filter). Auto-refresh is 30s. Gateway and interface management are not on this page; they live in `RouterDetailPanel` via /admin/topology.
63|
64|ROUTE: /admin/secrets
65|FILE: frontend/src/routes/admin/secrets/+page.svelte
66|CREATE: none
67|DELETE: per-row reset (`admin-system:secrets.configure` sits next to the reset button) calls DELETE /api/v1/admin/key-manager/project-quotas/{project}. No confirm dialog; the result is a toast.
68|OTHER_MUTATIONS: "configure" (`secrets.configure`) opens a FormModal (`secrets.dialogTitle`) with secrets, orders and containers number fields (empty means unlimited). `secrets.save` sends a PUT to the same path.
69|EXISTING_TOUR: admin-key-manager-header, admin-key-manager-table, admin-key-manager-ready, admin-key-manager-actions (first row)
70|TOUR_MOUNT: yes (tour="admin-key-manager")
71|NOTES: Despite the name, this page manages Barbican per-project quotas, not secrets. It needs the `$betaFeatures.keyManager` beta flag (or the admin mockup profile), otherwise `BetaFeatureGate` (`secrets.betaTitle`) is shown. Inventory-scope route. Auto-refresh defaults off.
72|
73|ROUTE: /admin/services
74|FILE: frontend/src/routes/admin/services/+page.svelte
75|CREATE: none
76|DELETE: none
77|OTHER_MUTATIONS: none. Read-only service and agent status in `ServiceTabs`/`ServiceTabPanel` across compute, network, block_storage, shared_file_system, orchestration, container, Magnum, endpoints and storage_pools. Auto-refresh is 15s.
78|EXISTING_TOUR: admin-system-header; plus in components: admin-system-tabs, per-tab anchors via `tourAnchor()` in ServiceTabs, admin-system-panel, admin-system-panel-ready
79|TOUR_MOUNT: yes (tour="admin-system")
80|NOTES: The Manila, Zun and Magnum tabs only appear when `$siteConfig.services.{manila,zun,magnum}` is enabled. Each tab loads lazily when first selected or hovered.
81|
82|ROUTE: /admin/settings
83|FILE: frontend/src/routes/admin/settings/+page.svelte
84|CREATE: none
85|DELETE: branding: per-slot `admin-system:branding.reset` (ghost button) calls DELETE /api/v1/site-config/admin/branding/{slot}. No confirm; only enabled after a logo has been uploaded.
86|OTHER_MUTATIONS: tabs are stored in `?tab=` (branding | infrastructure | enrollment | quotas | requests | email).
87|- branding: a file input (`branding.upload`) uploads a logo (png/jpeg/webp/gif).
88|- infrastructure (`AdminResourcePoliciesPanel`): each resource policy and runtime setting has its own `policies.save` (PUT).
89|- enrollment/quotas: a policy form with submit `enrollment.save` (PUT).
90|- requests: a signup queue with `enrollment.approve` / `enrollment.reject` per request (POST).
91|- email (`AdminEmailSettingsPanel`): an SMTP/IMAP form with `save`, `reset` (confirmDialog `resetConfirm`), `check` connections, and a test-send form.
92|EXISTING_TOUR: none
93|TOUR_MOUNT: no
94|NOTES: Changes apply per panel; `settings.draftHelp` explains there is no global save. Email save is disabled when security is 'none'. Signup approval may need SMTP configured (`enrollment.smtpMissing`).
95|
96|ROUTE: /admin/subnets
97|FILE: frontend/src/routes/admin/subnets/+page.svelte
98|CREATE: none
99|DELETE: none
100|OTHER_MUTATIONS: none. Read-only list from /admin/all-subnets with regex search, column filters, client-side paging, and a refresh button (`admin-network:subnetDetailPage.refresh`).
101|EXISTING_TOUR: none
102|TOUR_MOUNT: no
103|NOTES: Inventory-scope route. Rows link to /admin/subnets/{id} and the network column links to /admin/networks/{id}. To create subnets, use the network detail pages, which are outside this assignment.
104|
105|ROUTE: /admin/subnets/[id]
106|FILE: frontend/src/routes/admin/subnets/[id]/+page.svelte → `$lib/components/admin/networks/SubnetIpInventory.svelte` (standalone) → `SubnetInventoryDetails`
107|CREATE: none
108|DELETE: none
109|OTHER_MUTATIONS: none found (grep showed only refresh, retry, and a "network detail" link button).
110|EXISTING_TOUR: none
111|TOUR_MOUNT: no
112|NOTES: Read-only subnet IP inventory. `SubnetInventoryDetails` was not grepped for mutations.
113|
114|ROUTE: /admin/system-admins
115|FILE: frontend/src/routes/admin/system-admins/+page.svelte
116|CREATE: header `admin-identity:systemPage.add` opens `SystemAdminGrantModal` (custom dialog, `systemGrant.title`). Steps: choose a domain (SearchSelect `domain-admin:scope.domain`), the user list loads with search and `systemGrant.loadMore`, then the per-user `domain-admin:systemGrant.grant` button calls POST /api/v1/admin/identity/system-roles/grant and closes the modal right away. No data-tour.
117|DELETE: row `systemTable.revoke` (danger) calls POST …/system-roles/revoke. confirmDialog (`systemTable.revokeSelfConfirm`) only when revoking yourself. Disabled when only one admin is left (`systemTable.lastAdminHelp`).
118|OTHER_MUTATIONS: none
119|EXISTING_TOUR: none
120|TOUR_MOUNT: no
121|NOTES: A `SecurityPolicyBanner` shows the security policy. Auto-refresh is 60s. Granting is immediate with no confirmation step.
122|
123|ROUTE: /admin/system-info
124|FILE: frontend/src/routes/admin/system-info/+page.svelte
125|CREATE: none
126|DELETE: none
127|OTHER_MUTATIONS: none. Read-only `VersionInfoPanel` and `ServiceVersionsPanel` with a refresh button (`common:autoRefresh.refreshNow`).
128|EXISTING_TOUR: none
129|TOUR_MOUNT: no
130|NOTES: A 404 from service-versions is shown as "unavailable". System-admin only.
131|
132|ROUTE: /admin/topology
133|FILE: frontend/src/routes/admin/topology/+page.svelte
134|CREATE: none
135|DELETE: none on the page itself. The router detail slide (`RouterDetailPanel` → `RouterInfoSection`) has `router.actions.delete` with a confirmDialog (`router.confirm.delete`).
136|OTHER_MUTATIONS: everything goes through slide panels opened by clicking canvas or lane nodes.
137|- Router panel: add/remove interface and set/remove gateway (routerDetailController POST/DELETE /api/v1/routers/{id}/interfaces|gateway).
138|- Instance panel (`InstanceDetailPanel` adminMode): the InstanceHeader actions plus Migrate, Evacuate, Resize, Rename and Password modals.
139|- LB and network panels are read-only.
140|- A lane/canvas ToggleGroup (stored in localStorage `topology.view`).
141|EXISTING_TOUR: admin-network-header, admin-network-canvas, admin-network-ready, admin-network-legend, admin-network-detail (router SlidePanel dataTour)
142|TOUR_MOUNT: yes (tour="admin-network")
143|NOTES: Inventory-scope route with a traffic overlay (`AdminInventoryScope traffic`). Topology auto-refreshes every 30s and traffic every 15s. The legend only shows in lane view. A project filter comes from the inventory scope.
144|
145|ROUTE: /admin/user-credentials
146|FILE: frontend/src/routes/admin/user-credentials/+page.svelte (wraps `DomainScope` → `$lib/components/admin/credentials/CredentialManagement.svelte` kind="user")
147|CREATE: header `admin-identity:actions.create` opens a Modal (`credentials.createTitle`). Fields: user select, project (optional), type (`credentials.typeHelp`), and blob textarea. Submit `actions.save` uses `adminCredentialsController.submit`. No data-tour.
148|DELETE: row `actions.delete` (danger) opens the same Modal in delete mode (`credentials.deleteTitle`, warning `credentials.deleteWarning`); submit `actions.delete` (danger). No typed confirmation.
149|OTHER_MUTATIONS: `credentials.details` opens a detail modal with `credentials.reveal` (shows the sensitive blob) and `credentials.editSensitive` (reveal, then edit mode, then save).
150|EXISTING_TOUR: none
151|TOUR_MOUNT: no
152|NOTES: Pick a domain first (`DomainScope`). Optional user filter select (`credentials.allUsers`). Create is disabled while the user directory is loading or failed. The detail view warns about sensitive data.
153|
154|ROUTE: /admin/users
155|FILE: frontend/src/routes/admin/users/+page.svelte (wraps `DomainScope` → `$lib/components/admin/users/AdminUsersPage.svelte`)
156|CREATE: header `admin-identity:userPage.create` opens `AdminUserCreateModal` (FormModal, `userCreate.title`). Fields: name and email (required), password (`admin-*:onboarding.password` with help text), and an enabled checkbox. Submit `userCreate.create` calls POST /api/v1/admin/users, after which the modal shows an `AccountResultDetails` success alert. No data-tour on the submit button.
157|DELETE: row `actions.delete` (danger-outline) opens `AdminUserDeleteModal` (FormModal, `userDelete.title`). The user must type the exact user ID (`userDelete.confirmId`) before submit `actions.delete` (danger) enables; calls DELETE /api/v1/admin/users/{id}?domain_id. You cannot delete yourself (`userDelete.selfProtected`). It can come back with "re-read required".
158|OTHER_MUTATIONS: clicking a user name opens `AdminUserEditModal`:
159|- name, email, password and an enabled switch; submit `userEdit.update` (PATCH);
160|- email composer (`compose`);
161|- reset password and email (`userEdit.resetEmailTitle`, two-step confirm; POST …/password/reset-email);
162|- revoke all sessions (`userEdit.revokeAll` then `userEdit.confirm`; POST …/revoke-sessions);
163|- domain managers grant/revoke (`managers.grant` / `managers.revoke`).
164|EXISTING_TOUR: admin-identity-header, admin-identity-overview, admin-identity-overview-ready, admin-identity-filters, admin-identity-list, admin-identity-list-ready, admin-identity-status-filter, admin-identity-row (first row). All of these live in the components.
165|TOUR_MOUNT: yes, but inside `AdminUsersPage.svelte` (tour="admin-identity"), not in the route file
166|NOTES: Pick a domain first. Create and delete need `creationAllowed`, meaning an authenticated system admin with auth ready and no project switch or logout in progress. Auto-refresh is 60s. Has a recent-changes activity card.
167|
168|ROUTE: /admin/volumes
169|FILE: frontend/src/routes/admin/volumes/+page.svelte
170|CREATE: none. There is no create-volume button. The header has `volume:transferModal.receiveTitle` (outline), which opens `AdminVolumeTransferModal` in receive mode: target domain, project, transfer ID and auth key, then accept.
171|DELETE: from the row ActionMenu, `admin-storage:volumeList.action.delete` opens `AdminVolumeDeleteModal` (`volumeDelete.title`, irreversible); submit `volumeDelete.delete` calls DELETE /api/v1/admin/volumes/{id}. `volumeList.action.forceDelete` only appears for error/deleting status and opens `AdminVolumeForceDeleteModal`, which POSTs …/force-delete. Bulk: select rows with checkboxes, then the `BulkSelectionOverlay` delete runs a confirmDialog (`volumeList.bulkDelete.confirm`) and POSTs /admin/volumes/bulk-delete; partial results come back as toasts.
172|OTHER_MUTATIONS: from the ActionMenu:
173|- edit/rename (PATCH);
174|- extend (POST …/extend; new size must be greater than current);
175|- reset status (POST …/reset-status);
176|- transfer (only when available or awaiting-transfer; create, recover, and cancel pending);
177|- boot from volume (available and bootable; opens the admin VM wizard prefilled);
178|- recovery (error status; opens the detail slide).
179|Clicking a row opens `AdminVolumeDetailSlide` → `AdminVolumeDetailPanel` (transfer plus delete diagnostic/recovery). Also a status summary filter, volumes/capacity tabs (`?tab=capacity`), and a domain drill-down.
180|EXISTING_TOUR: admin-storage-header, admin-storage-status, admin-storage-filters, admin-storage-list, admin-storage-ready, admin-storage-timeseries (capacity tab); in components: admin-storage-status-available, admin-storage-row, admin-storage-row-open, admin-storage-detail (slide)
181|TOUR_MOUNT: yes (tour="admin-storage")
182|NOTES: Inventory-scope route with historical mode. Auto-refresh is 30s. The timeseries only shows when not scoped. Paging uses markers, with a page-size toggle.
183|
184|ROUTE: /admin/volumes/[id]
185|FILE: frontend/src/routes/admin/volumes/[id]/+page.svelte
186|CREATE: none
187|DELETE: header `volumeDetail.delete` (in `AdminVolumeDetailHeader`) runs a confirmDialog (`volumeDetail.deleteConfirm`), then DELETE, then goes to /admin/volumes.
188|OTHER_MUTATIONS: `volumeDetail.extend` opens `id/AdminVolumeExtendModal` (new size, POST …/extend). `volumeDetail.resetStatus` only shows for error/error_deleting and opens `id/AdminVolumeResetStatusModal` (target status select, POST …/reset-status).
189|EXISTING_TOUR: none (the `admin-storage-detail` anchor is on the list page's slide, not on this route)
190|TOUR_MOUNT: no
191|NOTES: Standalone detail page: info cards, attachment table, metadata card, back link. It only loads when `$auth.projectId` is set.
192|
193|ROUTE: /admin/waygate
194|FILE: frontend/src/routes/admin/waygate/+page.svelte → `$lib/components/waygate/WaygateWorkspace.svelte` (admin) → `WaygateProjectWorkspace.svelte`
195|CREATE: header `waygate:project.actions.createServer` (accent) opens a FormModal (`project.server.createTitle`) with `ClientSettingsFields` in mode server-create; submit `project.actions.create`. In the server slide, `openClientModal` issues a client (FormModal, `ClientSettingsFields` mode issue, owner field, `project.client.assignSelf`). `project.network…` attach opens a modal: choose network and subnet, then `project.actions.attach`.
196|DELETE: per-row or slide `project.actions.delete` / `project.actions.deleteServer` runs a confirmDialog (`project.confirm.serverDelete`). Bulk delete goes through checkboxes and `BulkSelectionOverlay` (`project.confirm.bulkDelete`). Client delete uses confirmDialog `project.confirm.clientDelete`. Network detach (`project.actions.detach`) uses confirmDialog `project.confirm.networkDetach`.
197|OTHER_MUTATIONS: server defaults (`project.server.defaults` → save); client settings edit and enable/disable toggle; config download and QR (owner only); backup export/import.
198|EXISTING_TOUR: waygate-header, waygate-list, waygate-ready, waygate-detail (SlidePanel), all in WaygateProjectWorkspace
199|TOUR_MOUNT: yes, inside `WaygateProjectWorkspace` (tour="admin-waygate" when admin)
200|NOTES: Needs a selected current project, otherwise `workspace.selectProject`. The create button only shows when `$siteConfig.services.waygate` is on and the user has the `waygate-gateways_editor` capability. Other gates: delete needs `waygate-gateways_admin`, client editing needs `waygate-clients_editor`, and revoke/route/connect need their own capabilities. Backup needs both revoke and route rights.
