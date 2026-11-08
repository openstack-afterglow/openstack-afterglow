# Route inventory: admin-a (announcements through ports)

Source: read-only subagent SecretSalamander, 2026-11-08. Verify against source before relying on a line.

1|ROUTE: /admin/announcements
2|FILE: frontend/src/routes/admin/announcements/+page.svelte
3|CREATE: Inline form card titled `announcements.form.title` (admin-system), not a modal. Fields: title, body, severity, target type (all/project/user). For project or user targets you also pick a domain, then a project or user. Then starts_at/ends_at and an optional checkbox `sendWithAnnouncement` (admin-email). Submit: accent Button `announcements.actions.send` (calls `handleCreate` → `ctrl.create`). No data-tour.
4|DELETE: Row Button `announcements.actions.delete` (danger) → `confirmDialog(announcements.deleteDialog.body)` → `ctrl.confirmDelete()`. Async, list reloads.
5|OTHER_MUTATIONS: Status pill button toggles active/inactive (`announcements.status.active/inactive`, calls `ctrl.toggleActive`). Per-row `AnnouncementEmailAction` Button `sendAnnouncement` (admin-email) opens a confirmDialog and sends the announcement email.
6|EXISTING_TOUR: none
7|TOUR_MOUNT: no
8|NOTES: Only system admins can use the page (`unavailable` if !isSystemAdmin, logout in progress or project switching). If the email outcome is unknown (`emailUnknown`), the form is locked.
9|
10|ROUTE: /admin/application-credentials
11|FILE: frontend/src/routes/admin/application-credentials/+page.svelte
12|CREATE: First pick a domain in the DomainScope gate (SearchSelect `scope.domain`, domain-admin). The page renders `CredentialManagement kind="application"`. PageHeader primary Button `actions.create` (admin-identity) opens a Modal, but is disabled unless `ctrl.canCreate`. Modal fields: name, description, expiry (datetime-local), role checkboxes. Submit: Button `actions.save`. No data-tour.
13|DELETE: Row Button `actions.delete` (danger) → same Modal in delete mode with warning `credentials.deleteWarning` → danger Button `actions.delete`. Async.
14|OTHER_MUTATIONS: Details modal is read-only. After create, an "issued" modal shows the secret once (`credentials.onceOnly`).
15|EXISTING_TOUR: none
16|TOUR_MOUNT: no
17|NOTES: DomainScope only renders for system admins. Prerequisites: a domain, and a user picked in the `credential-user` select (otherwise the page shows `credentials.chooseUser`). Create also needs `ctrl.context` (user/project scope).
18|
19|ROUTE: /admin/chat
20|FILE: frontend/src/routes/admin/chat/+page.svelte
21|CREATE: `ChatConfiguration section="providers"`. Inline provider form, no modal. Fields: name, connection method (`provider-type`), API provider label, order, API base URL, API key (base URL and key are hidden for subscription choices). Submit: Button `configuration.addProvider` (calls `addProvider`). No data-tour.
22|DELETE: Per-provider text button `configuration.delete` → `confirmDialog(configuration.deleteThisProviderItsAssociatedModelsWillAlsoBe)`. This also deletes the provider's models.
23|OTHER_MUTATIONS: `pricing.editDisplay` (FormModal for provider metadata). `configuration.setUsageKey`/`changeUsageKey` (billing admin key FormModal; api_key providers only). `configuration.activate`/`deactivate`. `accounts.manage` (ProviderAccountsPanel Modal) covers: add/edit/delete accounts and credentials, selection policy, ChatGPT device auth connect/disconnect, probe, relay history. `configuration.refreshAll` refreshes billing.
24|EXISTING_TOUR: none
25|TOUR_MOUNT: no
26|NOTES: Subscription providers show an "experimental" warning.
27|
28|ROUTE: /admin/chat/models
29|FILE: frontend/src/routes/admin/chat/models/+page.svelte
30|CREATE: `ChatConfiguration section="models"`. Button `configuration.addModel` opens a Modal (aria `configuration.addModel`). Two methods: discover (select models → `configuration.reviewSelectedModels` → register active/inactive) or manual (Button calls `addModel`). No data-tour.
31|DELETE: Per-model text button `configuration.delete` → `confirmDialog(configuration.deleteThisModel)`. Bulk: select checkboxes → danger-outline Button `configuration.deleteSelected` → confirmDialog.
32|OTHER_MUTATIONS: `configuration.assignTitleModel`/`unassignTitleModel` (text models). `configuration.editPricing` (Modal). `pricing.editKind` (ModelKindEditor FormModal). `configuration.editCapabilities` (Modal, text models). `configuration.activate`/`deactivate`. Reorder by drag or up/down buttons (models reorder API).
33|EXISTING_TOUR: none
34|TOUR_MOUNT: no
35|NOTES: Add model is disabled until at least one provider exists. Filters: provider and kind.
36|
37|ROUTE: /admin/chat/quotas
38|FILE: frontend/src/routes/admin/chat/quotas/+page.svelte
39|CREATE: none. The default monthly quota form saves with Button `adminQuotas.saveDefault` (PUT).
40|DELETE: Row Button `adminQuotas.resetDefault` → `confirmDialog(adminQuotas.resetConfirm)`. This deletes the personal quota override.
41|OTHER_MUTATIONS: Row `adminQuotas.edit` → Modal with personal monthly/weekly limits → submit `adminQuotas.save` (PUT). `adminQuotas.usage` opens UserUsageDetailModal (read-only).
42|EXISTING_TOUR: none
43|TOUR_MOUNT: no
44|NOTES: Wrapped in DomainScope, so a domain must be selected. The user list is paginated.
45|
46|ROUTE: /admin/chat/stats
47|FILE: frontend/src/routes/admin/chat/stats/+page.svelte
48|CREATE: none
49|DELETE: none
50|OTHER_MUTATIONS: none (read-only stats; `stats.refresh`, load more users).
51|EXISTING_TOUR: none
52|TOUR_MOUNT: no
53|NOTES: Wrapped in AdminInventoryScope (domain/project picker). A 403 shows a warning alert.
54|
55|ROUTE: /admin/chat/tools
56|FILE: frontend/src/routes/admin/chat/tools/+page.svelte
57|CREATE: `ChatConfiguration section="tools"` renders `ChatExtensionsManager base="/api/v1/chat/admin"`. It has three inline forms: MCP server (Button `extensions.mcp.add`), custom HTTP tool (`extensions.tools.add`), skill (`extensions.skills.add`). No data-tour.
58|DELETE: Per-item text button `extensions.actions.delete` → confirmDialog (`removeItem`).
59|OTHER_MUTATIONS: `extensions.actions.activate`/`deactivate`. Load-policy select (preloaded/on_demand). MCP OAuth connect (`oauth/start`), or disconnect via the connected button plus confirm.
60|EXISTING_TOUR: none
61|TOUR_MOUNT: no
62|NOTES: In admin mode, every control requires `isSystemAdmin`.
63|
64|ROUTE: /admin/containers
65|FILE: frontend/src/routes/admin/containers/+page.svelte
66|CREATE: none
67|DELETE: In the detail SlidePanel (ContainerDetailPanel adminMode → ContainerActionsBar): button `container.delete` (containers-shell) → `confirmDialog(container.deleteConfirm)`. Async.
68|OTHER_MUTATIONS: `container.start` (when Stopped or Created) and `container.stop` (when Running), via `/api/v1/admin/containers`.
69|EXISTING_TOUR: admin-containers-header, admin-containers-list, admin-containers-ready, admin-containers-row (first row), admin-containers-detail (SlidePanel dataTour)
70|TOUR_MOUNT: yes (`tour="admin-containers"`)
71|NOTES: Inventory-scope route (layout adds the AdminProjectPicker domain/project filter). Clicking a row opens the detail. A container must already exist; you cannot create one here.
72|
73|ROUTE: /admin/database-instances
74|FILE: frontend/src/routes/admin/database-instances/+page.svelte
75|CREATE: Header button `actions.createInstance` (database ns) opens DbCreatePanel, a custom dialog `wizard.title` with 5 tabs: Details/Networking/Access/Init/Advanced, navigated with `actions.previous`/`actions.next`. Submit: Button `actions.create` (disabled unless `s.canCreate`). No data-tour.
76|DELETE: Row button `actions.delete` → `confirmDialog(instances.deleteConfirm)`. Async.
77|OTHER_MUTATIONS: Row `actions.restart` → `confirmDialog(instances.restartConfirm)`.
78|EXISTING_TOUR: none
79|TOUR_MOUNT: no
80|NOTES: Restart and delete only appear when `inst.project_id === current projectId`. Inventory-scope route. The name links to the detail page.
81|
82|ROUTE: /admin/database-instances/[id]
83|FILE: frontend/src/routes/admin/database-instances/[id]/+page.svelte
84|CREATE: Databases section: toggle `actions.add` → inline form (name) → `actions.create`. Users section: `actions.add` → name, password, databases CSV → `actions.create`. Backups section: `actions.createBackup` → name, description → `actions.backup`. No data-tour.
85|DELETE: DbInstanceHeader `actions.deleteInstance` → confirm `instances.deleteConfirm`. Per-database `actions.delete` (confirm `databases.deleteConfirm`), per-user (confirm `users.deleteConfirm`), per-backup (confirm `backups.deleteConfirm`).
86|OTHER_MUTATIONS: `actions.enableRoot` (DbConnectionInfoCard). Backup `actions.restore`, which uses `window.prompt(restore.namePrompt)` and creates a new instance.
87|EXISTING_TOUR: none
88|TOUR_MOUNT: no
89|NOTES: Every mutation is gated by `canMutate` (instance project === current projectId). Otherwise the page is read-only.
90|
91|ROUTE: /admin/domains
92|FILE: frontend/src/routes/admin/domains/+page.svelte
93|CREATE: Header primary Button `inventory.create` (domain-admin) opens FormModal with name, description, enabled checkbox. Submit: Button `actions.save` (`domainsApi.create`). No data-tour.
94|DELETE: none
95|OTHER_MUTATIONS: Row `actions.edit` → same FormModal (`domainsApi.update`). For reserved account/personal domains, name and enabled are disabled. `actions.inspect` links to `/admin/domains/{id}`.
96|EXISTING_TOUR: none
97|TOUR_MOUNT: no
98|NOTES: System admin only (otherwise shows `scope.denied`).
99|
100|ROUTE: /admin/domains/[id]
101|FILE: frontend/src/routes/admin/domains/[id]/+page.svelte
102|CREATE: none
103|DELETE: ComputePoolPanel: stale cap `verifyRemoveCap`, and per-project `removeCap`.
104|OTHER_MUTATIONS: ComputePoolPanel (adminMode): pool limits plus `enablePool` checkbox → `savePool`. Project caps (select project) → `saveCap`. DomainBudgetEditor: QuotaEditor save of ceilings, and per pending operation a "settled" checkbox → `reconcile`. DomainMonitoring is read-only (`monitor.manageUsers` links to /admin/users).
105|EXISTING_TOUR: none
106|TOUR_MOUNT: no
107|NOTES: DomainScope preselects the id. Saves require policy_ready with control_scope 'afterglow'. Caps are disabled while the pool is unmanaged. A `reloadRequired` state locks edits.
108|
109|ROUTE: /admin/drover
110|FILE: frontend/src/routes/admin/drover/+page.svelte
111|CREATE: none
112|DELETE: In the K3sClusterDetailPanel SlidePanel (adminMode, `/api/v1/admin/k3s-clusters`): delete cluster (confirm `detail.confirmDelete`). It can also delete configmaps, secrets, pods and services, each with its own confirm.
113|OTHER_MUTATIONS: Scale agents (confirm `detail.confirmScale`), stampede autoscale enable/disable, admin kubeconfig (confirm).
114|EXISTING_TOUR: none
115|TOUR_MOUNT: no
116|NOTES: Read-only list; clicking a row opens the detail. There is no cluster creation here.
117|
118|ROUTE: /admin/drover/templates
119|FILE: frontend/src/routes/admin/drover/templates/+page.svelte
120|CREATE: Header button `templates.create` (drover-pages) opens K3sClusterTemplateModal. Fields: name, description, k3s version, agents count, flavor id, OS type (Ubuntu/CoreOS), public checkbox. Submit: button `actions.create` (disabled until a name is entered). No data-tour.
121|DELETE: Card delete → Modal `templates.deleteTitle` → button `actions.delete`. Async, shows inline error.
122|OTHER_MUTATIONS: Card edit → same modal (PATCH; name is disabled), submit `actions.edit`.
123|EXISTING_TOUR: none
124|TOUR_MOUNT: no
125|NOTES: none
126|
127|ROUTE: /admin/events
128|FILE: frontend/src/routes/admin/events/+page.svelte
129|CREATE: none
130|DELETE: none
131|OTHER_MUTATIONS: none. Read-only audit list: filter form `events.applyFilters`/`events.reset`, `events.viewDetails` (detail plus timeline), load more.
132|EXISTING_TOUR: none
133|TOUR_MOUNT: no
134|NOTES: Wrapped in AdminInventoryScope.
135|
136|ROUTE: /admin/file-storage
137|FILE: frontend/src/routes/admin/file-storage/+page.svelte
138|CREATE: none
139|DELETE: Detail SlidePanel (AdminFileStorageDetailPanel): button `fileDetail.delete` → `confirmDialog(fileDetail.deleteConfirm)`. On failure it runs a delete diagnostic. If `force_delete_available`, a `fileDetail.forceDelete` button appears (confirm `fileDetail.forceDeleteConfirm`, admin force-delete API).
140|OTHER_MUTATIONS: `fileDetail.rerunDiagnostic`. Copy buttons.
141|EXISTING_TOUR: none
142|TOUR_MOUNT: no
143|NOTES: Delete only shows when share project === current projectId. Inventory-scope route; the timeseries is hidden when scoped.
144|
145|ROUTE: /admin/flavors
146|FILE: frontend/src/routes/admin/flavors/+page.svelte
147|CREATE: Header button `flavors.create.toolbarAction` (admin-compute) opens FlavorCreateModal (`flavors.create.title`). Fields: name, vCPU, RAM MB, disk GB, public switch. Submit: `flavors.create.action`. No data-tour.
148|DELETE: Row Button (danger) → `confirmDialog(flavors.delete.confirm)`. Disabled for managed flavors (`isManagedFlavor`).
149|OTHER_MUTATIONS: `flavors.manage.action` opens the FlavorManagePanel SlidePanel. Access tab: add/remove project access. Specs tab: add/edit/delete extra specs and the usage requirement. `gpuCatalog.title` opens GpuDeviceCatalogModal: add/delete devices (with confirm), template download, CSV import (replace needs confirm). FlavorAutomationPanel: `enableAutomation` → `saveAutomation`, plus `reconcile`. FlavorAutomationPolicyPanel: discover hosts, remove/reinclude host (confirm), add/remove profile → `saveProfiles`.
150|EXISTING_TOUR: none
151|TOUR_MOUNT: no
152|NOTES: Controls are disabled until `allowed()` (admin auth ready). Managed flavors are read-only (`managedReadonly`).
153|
154|ROUTE: /admin/floating-ips
155|FILE: frontend/src/routes/admin/floating-ips/+page.svelte
156|CREATE: Header button `floatingIpsPage.actions.create` (admin-network) opens Modal `floatingIpsPage.createDialog.title` with an external network select. Submit: `floatingIpsPage.createDialog.submit`. No data-tour.
157|DELETE: Row `floatingIpsPage.actions.delete` (unassigned only) → Modal `floatingIpsPage.deleteDialog.title` → `floatingIpsPage.actions.delete`. Async.
158|OTHER_MUTATIONS: none
159|EXISTING_TOUR: none
160|TOUR_MOUNT: no
161|NOTES: Requires an external network (otherwise shows `createDialog.noExternalNetworks`). Inventory-scope route.
162|
163|ROUTE: /admin/gpu
164|FILE: frontend/src/routes/admin/gpu/+page.svelte
165|CREATE: none
166|DELETE: none
167|OTHER_MUTATIONS: none
168|EXISTING_TOUR: none
169|TOUR_MOUNT: no
170|NOTES: Redirect only (+page.ts 308 → /admin/hypervisors). Not a tutorial surface.
171|
172|ROUTE: /admin/groups
173|FILE: frontend/src/routes/admin/groups/+page.svelte
174|CREATE: AdminGroupsPage header button `groupPage.create` opens GroupCreateModal (`groupCreate.title`) with name and description. Submit: `actions.create`. No data-tour.
175|DELETE: GroupCard `actions.delete` (danger-outline) → GroupDeleteConfirmModal (`groupDelete.title`) → `actions.delete`. Async.
176|OTHER_MUTATIONS: `actions.edit` → GroupEditModal → `groupEdit.submit`. `groupCard.members` expands the card: add a member (`actions.add` per user, or batch-add selected) and remove a member.
177|EXISTING_TOUR: none
178|TOUR_MOUNT: no
179|NOTES: Wrapped in DomainScope, so a domain is required.
180|
181|ROUTE: /admin/hypervisors
182|FILE: frontend/src/routes/admin/hypervisors/+page.svelte
183|CREATE: none
184|DELETE: Host removal in HypervisorDetailPanel → HypervisorRemovalReview. `hypervisors.removal.refresh` runs the removal check; then an approval form with submit `hypervisors.removal.remove` (danger). Destructive and async.
185|OTHER_MUTATIONS: `hypervisors.operations.disableScheduling` (reason required) and `enableScheduling`. `migrateAll` and `evacuateAll` (fenced checkbox required), confirmed with an intent submit button. Per-server `hypervisors.detail.move` opens HypervisorMigrateModal (live or cold migrate) → `hypervisors.migrate.action`. Server click opens InstanceDetailPanel (adminMode). HostHealthPanel has refresh only.
186|EXISTING_TOUR: none
187|TOUR_MOUNT: no
188|NOTES: Clicking a table row opens the host SlidePanel. Evacuation is highly destructive and needs the fenced confirmation.
189|
190|ROUTE: /admin/images
191|FILE: frontend/src/routes/admin/images/+page.svelte
192|CREATE: Header primary Button `images.upload` (admin-compute) opens ImageUploadModal (`uploadModal.title`). Fields: file dropzone, name, disk format, visibility, OS distro. Submit: Button `uploadModal.startUpload`. No data-tour on the submit.
193|DELETE: Row danger-outline `images.delete.action` (non-protected only) → `confirmDialog(images.delete.confirm)`. The ImageDetailPanel (isAdmin) also has a delete.
194|OTHER_MUTATIONS: `images.table.approveVerification`/`revokeVerification`. `images.table.deactivate`/`activate`. `images.edit.action` → ImageEditModal (name, OS distro, visibility) → save (PATCH).
195|EXISTING_TOUR: admin-images-header, admin-images-controls (ImageCatalogToolbar tourPrefix), admin-images-results, admin-images-ready
196|TOUR_MOUNT: yes (`tour="admin-images"`)
197|NOTES: Inventory-scope route. Repository/tag catalog view (`selectedRepository` → table).
198|
199|ROUTE: /admin/infrastructure-topology
200|FILE: frontend/src/routes/admin/infrastructure-topology/+page.svelte
201|CREATE: none
202|DELETE: none
203|OTHER_MUTATIONS: Trace submit (TopologyInspector form: target select → Button `submit`). Otherwise read-only graph: refresh, layers, zoom, inspector.
204|EXISTING_TOUR: none
205|TOUR_MOUNT: no
206|NOTES: Trace requires `host.observer_configured` and `ctrl.verified`.
207|
208|ROUTE: /admin/instances
209|FILE: frontend/src/routes/admin/instances/+page.svelte
210|CREATE: Header primary Button `instances.page.createVm` calls `openWizard()` (the global create-instance wizard; there is no local modal). No data-tour on the button itself; it sits inside admin-compute-header.
211|DELETE: Bulk: select rows → BulkSelectionOverlay `instances.bulk.delete`. Only offered when all selected are SHUTOFF (`canBulkDelete`); confirmed with `confirmInstanceDeletion`. Single delete lives in InstanceDetailPanel (adminMode).
212|OTHER_MUTATIONS: Bulk `instances.bulk.start` and `instances.bulk.stop` (confirmDialog). ERROR rows get `instances.table.recover` → RecoveryModal. The detail panel offers lifecycle actions, migrate, password, rename, resize, evacuate modals.
213|EXISTING_TOUR: admin-compute-header, admin-compute-filters, admin-compute-timeseries, admin-compute-list, admin-compute-ready, admin-compute-row / admin-compute-row-open (first row, AdminInstanceTable), admin-compute-detail (SlidePanel)
214|TOUR_MOUNT: yes (`tour="admin-compute"`)
215|NOTES: Inventory-scope route; the timeseries is hidden when scoped. Bulk action posts to `/api/v1/instances/bulk-action`.
216|
217|ROUTE: /admin/layers
218|FILE: frontend/src/routes/admin/layers/+page.svelte
219|CREATE: none
220|DELETE: none
221|OTHER_MUTATIONS: none
222|EXISTING_TOUR: none
223|TOUR_MOUNT: no
224|NOTES: Redirect only (+page.ts 308 → /admin/libraries).
225|
226|ROUTE: /admin/libraries
227|FILE: frontend/src/routes/admin/libraries/+page.svelte
228|CREATE: Header `workspace.createBuild` opens the Studio tab. Choose a source (image / profile / Dockerfile document) → `source.continue`. Optionally fetch a Dockerfile URL (`url.fetch`) and preview with `plan.preview`. Then submit `build.start` (inline build) or `import.start` (Dockerfile import). No data-tour on the submit; the section is admin-library-import.
229|DELETE: Profiles: delete button (`profiles.delete`) → `window.confirm(profiles.confirmDelete)`; blocked when there are active consumes. Artifacts: `artifacts.reviewDeletion` → Modal `delete.label` → `delete.execute`.
230|OTHER_MUTATIONS: Profile and artifact publication toggle (`publication.show`/`hide`; artifacts must be sealed). Build detail Modal → `buildDetail.cancel`. Import history `history.createVm` → consumer settings → consume (launches a VM). Tabs: catalog / studio / profiles / artifacts / builds / instances.
231|EXISTING_TOUR: admin-library-header, admin-library-ready (tabs), admin-library-import, admin-library-profile, admin-library-artifacts, admin-library-builds, admin-library-consumes
232|TOUR_MOUNT: yes (`tour="admin-library"`)
233|NOTES: Studio is admin-only (`studio.adminOnly`). Consume needs a flavor and usage schedule. Palimpsest-backed.
234|
235|ROUTE: /admin/loadbalancers
236|FILE: frontend/src/routes/admin/loadbalancers/+page.svelte
237|CREATE: none
238|DELETE: Select checkboxes → BulkSelectionOverlay `loadbalancersPage.actions.delete` → `confirmDialog(loadbalancersPage.deleteDialog.body)` → bulk delete. The detail panel also has an LB delete (with confirm).
239|OTHER_MUTATIONS: LoadBalancerDetailPanel SlidePanel: create/delete listeners, create/delete pools, add/remove members (each delete confirmed).
240|EXISTING_TOUR: none
241|TOUR_MOUNT: no
242|NOTES: Only LBs in the current project that are not Drover-owned can be selected (Drover LBs are protected). Inventory-scope route.
243|
244|ROUTE: /admin/monitoring
245|FILE: frontend/src/routes/admin/monitoring/+page.svelte
246|CREATE: none
247|DELETE: none
248|OTHER_MUTATIONS: none (read-only; tabs summary / instance metrics; refresh)
249|EXISTING_TOUR: admin-monitoring-header, admin-monitoring-summary, admin-monitoring-summary-ready, admin-monitoring-list, admin-monitoring-list-ready, admin-monitoring-row, admin-monitoring-back, admin-monitoring-metrics
250|TOUR_MOUNT: yes (`tour="admin-monitoring"`)
251|NOTES: none
252|
253|ROUTE: /admin/monitoring/aodh
254|FILE: frontend/src/routes/admin/monitoring/aodh/+page.svelte
255|CREATE: AodhDashboard Button `aodh.create` links to `/admin/monitoring/aodh/settings?create=1` (the form lives on the settings page).
256|DELETE: none on this page
257|OTHER_MUTATIONS: none (alarm list/detail, refresh, link to `aodh.settings`)
258|EXISTING_TOUR: none
259|TOUR_MOUNT: no
260|NOTES: Create and settings links are disabled unless `allowed`.
261|
262|ROUTE: /admin/monitoring/aodh/settings
263|FILE: frontend/src/routes/admin/monitoring/aodh/settings/+page.svelte
264|CREATE: Button `settings.create` opens FormModal `settings.create`. Fields: name, description, type, severity, enabled/repeat checkboxes. For gnocchi_resources_threshold: a guided rule (metric, resource type, aggregation, operator, threshold, granularity, periods, resource id) or advanced JSON rule. Also constraints and alarm/ok/insufficient action lists. Submit: `settings.save` (POST).
265|DELETE: Select an alarm → modal danger `settings.delete` → `confirmDialog(settings.deleteConfirm)`. Async; an uncertain outcome offers `settings.reread`.
266|OTHER_MUTATIONS: Edit (PUT) via selecting an alarm → `settings.save`. Trust+ actions need a confirm (`settings.trustConfirm`).
267|EXISTING_TOUR: none
268|TOUR_MOUNT: no
269|NOTES: Needs `allowed` (otherwise shows `settings.noAuthority`).
270|
271|ROUTE: /admin/monitoring/ceph
272|FILE: frontend/src/routes/admin/monitoring/ceph/+page.svelte
273|CREATE: none
274|DELETE: none
275|OTHER_MUTATIONS: none
276|EXISTING_TOUR: none
277|TOUR_MOUNT: no
278|NOTES: Grafana embed only (dashboardKey "ceph"). Read-only.
279|
280|ROUTE: /admin/monitoring/etcd
281|FILE: frontend/src/routes/admin/monitoring/etcd/+page.svelte
282|CREATE: none
283|DELETE: none
284|OTHER_MUTATIONS: none
285|EXISTING_TOUR: none
286|TOUR_MOUNT: no
287|NOTES: Grafana embed "etcd". Read-only.
288|
289|ROUTE: /admin/monitoring/gnocchi
290|FILE: frontend/src/routes/admin/monitoring/gnocchi/+page.svelte
291|CREATE: none
292|DELETE: none
293|OTHER_MUTATIONS: none (browse resources and metrics, `gnocchi.readMeasures`)
294|EXISTING_TOUR: none
295|TOUR_MOUNT: no
296|NOTES: Read-only telemetry browser.
297|
298|ROUTE: /admin/monitoring/haproxy
299|FILE: frontend/src/routes/admin/monitoring/haproxy/+page.svelte
300|CREATE: none
…
305|NOTES: Grafana embed "haproxy". Read-only.
…
458|NOTES: Inventory-scope route. Needs an existing network. Marker-based pagination.

[Showing lines 1-300 of 458. Use :301 to continue]
