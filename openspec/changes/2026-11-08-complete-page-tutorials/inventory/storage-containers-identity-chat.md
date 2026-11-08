# Route inventory: storage, containers, DB, secrets, IAM, chat, home (dashboard)

Source: read-only subagent MiddleFalcon, 2026-11-08. Verify against source before relying on a line.

1|ROUTE: /dashboard (home)
2|FILE: frontend/src/routes/dashboard/+page.svelte
3|CREATE: none on this page. In the empty-state "start" card, `t('start.create')` (dashboard-home ns) links to /dashboard/compute/instances; it only shows when `$canWrite`, a token and a projectId are all present. `t('start.images')` links to /dashboard/compute/images and `t('start.guide')` to /docs.
4|DELETE: none
5|OTHER_MUTATIONS: none. Read-only cards: DashboardGreetingHeader, DashboardStatTiles, RecentInstancesCard, QuotaUsageCard, RangeToggle, UsageScheduleReminders, telemetry BklitCharts. Announcement links go to /dashboard/notifications?focus=<id>; `t('telemetry.openMonitoring')` goes to /dashboard/observability.
6|EXISTING_TOUR: `data-tour="dashboard-recent"`. It sits on the wrapper div until `startReady`, then moves to the inner start `<section>`. No tour in lib/tutorial/tours.ts uses it.
7|TOUR_MOUNT: no
8|NOTES: The tour list (TOUR_IDS) has no dashboard-home tour. Recent instances link to /dashboard/instances/{id}.
9|
10|ROUTE: /dashboard/file-storage
11|FILE: frontend/src/routes/dashboard/file-storage/+page.svelte
12|CREATE: PageHeader `<Button>` `t('list.createAction')` (file-storage ns); the empty state has `t('list.createCta')`. Both open `$lib/components/file-storage/wizard/FileStorageWizard.svelte`, which uses fileStorageWizardStore.
13|- Step 1 (Basic): `<Button onclick={s.goStep2}>` reads `wizard.actions.create`, or `wizard.actions.next` when DHSS is on and the protocol is NFS.
14|- Step 2 (Network): only appears when DHSS is on and the fileStorageShareNetworks beta is enabled. You can create a share network inline (`s.createInlineNetwork`), then submit with `<Button onclick={s.createFileStorage}>` `wizard.actions.create`.
15|- Step 3 (Access, after the share is created): add rules with `s.addAccessRule` (`wizard.actions.add`), then close with `wizard.actions.finish` or `wizard.actions.skip`.
16|- No data-tour anchors.
17|DELETE: `FileStorageCard` has a `danger-outline` button `t('storageCard.delete')`. The SlidePanel FileStorageDetailPanel has `t('actions.delete')`. Bulk delete is in BulkSelectionOverlay (`t('actions.delete')`, tone danger). All use the global `confirmDialog` (`list.deleteConfirm` / `list.bulkDeleteConfirm`), then async `api.delete /api/v1/file-storage/{id}` and an auto refresh.
18|OTHER_MUTATIONS: copy export path, open detail SlidePanel (`t('storageCard.details')`), bulk select
19|EXISTING_TOUR: none
20|TOUR_MOUNT: no
21|NOTES: Shows the Manila quota (`gigabytes`). With DHSS on, NFS needs a share network.
22|
23|ROUTE: /dashboard/file-storage/[id]
24|FILE: frontend/src/routes/dashboard/file-storage/[id]/+page.svelte
25|CREATE: Access rule: the AccessRulesSection toggle `t('accessRules.addToggle')` opens an inline form with IP/CIDR (NFS) or Ceph ID (CephX) and an ro/rw permission, submitted by `t('accessRules.add')`. Calls `api.post /api/v1/file-storage/{id}/access-rules` with access_type `ip` for NFS, otherwise `cephx`.
26|DELETE: FileStorageHeader `t('storageHeader.delete')` → confirmDialog(`detail.deleteConfirm`) → `api.delete` → goto /dashboard. Each rule has a revoke button `t('accessRules.delete')` → confirmDialog(`detail.revokeConfirm`).
27|OTHER_MUTATIONS: copy access key (`accessRules.copy`), auto refresh
28|EXISTING_TOUR: none
29|TOUR_MOUNT: no
30|NOTES: The back link goes to /dashboard, not to the list.
31|
32|ROUTE: /dashboard/file-storage/manage
33|FILE: frontend/src/routes/dashboard/file-storage/manage/+page.svelte
34|CREATE: PrebuiltLibraryGrid has a per-library build button labelled `t('list.createCta')`, or `prebuiltGrid.built` once built. It calls `api.post /api/v1/admin/file-storage/build?library_id=…[&auto_install=true]`. The header checkbox `t('manage.autoInstall')` controls auto_install.
35|DELETE: none
36|OTHER_MUTATIONS: none (FileStorageManageGrid is read-only)
37|EXISTING_TOUR: none
38|TOUR_MOUNT: no
39|NOTES: Effectively admin-only because it calls admin APIs (/api/v1/admin/file-storage, /api/v1/libraries). The route is not in nav.ts.
40|
41|ROUTE: /dashboard/file-storage/networks
42|FILE: frontend/src/routes/dashboard/file-storage/networks/+page.svelte
43|CREATE: Header `<button>` `t('networks.create')` opens `$lib/components/dashboard/file-storage/networks/ShareNetworkCreateModal.svelte`. You pick a name, Neutron network and subnet, then submit with `t('networkCreate.create')`, which is disabled until all three are set. Calls `api.post /api/v1/share-networks`.
44|DELETE: ShareNetworkTable row `t('networkTable.delete')` and bulk `t('actions.delete')` → confirmDialog(`networks.deleteConfirm` / `networks.bulkDeleteConfirm`) → async `api.delete`.
45|OTHER_MUTATIONS: none
46|EXISTING_TOUR: none
47|TOUR_MOUNT: no
48|NOTES: Behind the `$betaFeatures.fileStorageShareNetworks` beta flag; when off, the page shows BetaFeatureGate. Needs an existing Neutron network and subnet.
49|
50|ROUTE: /dashboard/file-storage/security-services
51|FILE: frontend/src/routes/dashboard/file-storage/security-services/+page.svelte
52|CREATE: Header `<button>` `t('security.create')` opens SecurityServiceCreateModal. Only the name is required; submit with `t('securityCreate.create')`. Calls `api.post /api/v1/security-services`.
53|DELETE: SecurityServiceTable row `t('securityTable.delete')` and bulk delete → confirmDialog(`security.deleteConfirm` / `security.bulkDeleteConfirm`) → async `api.delete`.
54|OTHER_MUTATIONS: Attach: row `t('securityTable.attachNetwork')` opens SecurityServiceAttachModal; pick a share network and confirm with `t('securityAttach.attach')`. Calls `POST /api/v1/security-services/{id}/attach?share_network_id=`.
55|EXISTING_TOUR: none
56|TOUR_MOUNT: no
57|NOTES: Behind the `$betaFeatures.fileStorageSecurityServices` beta flag. Attaching needs an existing share network.
58|
59|ROUTE: /dashboard/file-storage/snapshots
60|FILE: frontend/src/routes/dashboard/file-storage/snapshots/+page.svelte
61|CREATE: Header `<button>` `t('snapshots.create')`; the empty state SnapshotsEmptyState has `t('snapshotEmpty.create')`. Both open `$lib/components/file-storage/SnapshotCreateModal.svelte`: pick a share, enter a name and optional description, submit with `t('snapshotCreate.create')`. Calls `api.post /api/v1/share-snapshots`.
62|DELETE: SnapshotListTable row `t('snapshotTable.delete')` and bulk delete → confirmDialog(`snapshots.deleteConfirm` / `snapshots.bulkDeleteConfirm`) → async `api.delete`.
63|OTHER_MUTATIONS: none
64|EXISTING_TOUR: none
65|TOUR_MOUNT: no
66|NOTES: Behind the `$betaFeatures.fileStorageSnapshots` beta flag. Needs an existing file storage share whose backend supports snapshots.
67|
68|ROUTE: /dashboard/object-storage/buckets
69|FILE: frontend/src/routes/dashboard/object-storage/buckets/+page.svelte
70|CREATE: Header `<Button>` `t('buckets.dashboardPage.create')` (object-storage ns) opens `$lib/components/object-storage/BucketCreateDialog.svelte`; enter a name and submit with `t('buckets.createDialog.create')`. Calls `api.post /api/v1/object-storage {name}`.
71|DELETE:
72|- Soft delete: BucketCardGrid `t('views.bucketCardGrid.delete')` → confirmDialog(`buckets.dashboardPage.deleteConfirm`) → `api.delete /api/v1/object-storage/{name}`, which moves the bucket to Trash. Bulk move-to-trash is `t('buckets.dashboardPage.moveToTrash')`.
73|- In the Trash section: `t('buckets.dashboardPage.restore')` calls `POST /trash/containers/{name}/restore`. `t('buckets.dashboardPage.purge')` → confirmDialog(`purgeConfirm`) → permanent `DELETE /trash/containers/{name}`. Bulk restore/purge are available too.
74|OTHER_MUTATIONS: restore from trash, purge
75|EXISTING_TOUR: none
76|TOUR_MOUNT: no
77|NOTES: Shows account StatTiles (bucket count, object count, usage). The empty state has no CTA button.
78|
79|ROUTE: /dashboard/object-storage/buckets/[name]
80|FILE: frontend/src/routes/dashboard/object-storage/buckets/[name]/+page.svelte (renders `$lib/components/ObjectBrowser.svelte` with mode="user"; uses objectBrowser store)
81|CREATE:
82|- Folder: ObjectBrowserToolbar `t('browserToolbar.newFolder')` opens NewDirModal (`dialogs.newDir.*`).
83|- Upload: `t('browserToolbar.upload')` (primary) opens UploadModal; submit with `t('uploadModal.upload')`. Drag-and-drop onto ObjectDragOverlay also uploads.
84|DELETE: Per-object delete → confirmDialog(`dialogs.controller.delete.confirm`). ObjectBulkActionBar `t('views.bulkActionBar.delete')` → confirmDialog. The Trash tab (ObjectTrashView) has `t('dialogs.trash.restore')` and `t('dialogs.trash.purge')`.
85|OTHER_MUTATIONS: rename (RenameModal), move (MoveModal; bulk move is `t('views.bulkActionBar.move')`), download, metadata panel, preview, Files/Trash tabs
86|EXISTING_TOUR: none
87|TOUR_MOUNT: no
88|NOTES: Needs an existing bucket. Breadcrumb navigation goes through ObjectBrowserHeader.
89|
90|ROUTE: /dashboard/database/instances
91|FILE: frontend/src/routes/dashboard/database/instances/+page.svelte
92|CREATE: Header `<Button>` `tr('actions.createInstance')` (database ns) opens `$lib/components/database/DbCreatePanel.svelte`. It is a 5-tab wizard (DB_TABS: Details, Networking, Access, Init, Advanced) with `tr('actions.next')` / `tr('actions.previous')`; submit with `<Button onclick={s.createInstance}>` `tr('actions.create')`. No data-tour.
93|DELETE: DbInstancesTable row delete → confirmDialog(`instances.deleteConfirm`) → async `api.delete /api/v1/database-instances/{id}`. Bulk delete is available.
94|OTHER_MUTATIONS: Restart: row restart → confirmDialog with `confirmLabel: tr('actions.restart')` → `POST /{id}/restart`; bulk restart too. Clicking the name opens the DbInstanceDetailPanel SlidePanel, which has the same actions as the [id] route.
95|EXISTING_TOUR: none
96|TOUR_MOUNT: no
97|NOTES: The empty state (`instances.empty`) has no CTA. Trove; the nav item has service: null.
98|
99|ROUTE: /dashboard/database/instances/[id]
100|FILE: frontend/src/routes/dashboard/database/instances/[id]/+page.svelte (renders DbInstanceDetailPanel; uses dbInstanceDetailController)
101|CREATE:
102|- Database: DbDatabasesSection toggle → `tr('actions.create')` (createDb).
103|- User: DbUsersSection toggle → form with name, password, host and databases → `createUser`.
104|- Backup: DbBackupsSection `tr('actions.createBackup')` → name and description → `createBackup`.
105|DELETE: DbInstanceHeader delete (deleteInstance) → confirmDialog(`instances.deleteConfirm`), then navigates to the list. Databases (`databases.deleteConfirm`), users (`users.deleteConfirm`) and backups delete with their own confirms.
106|OTHER_MUTATIONS: attach floating IP (`attachFip`), detach floating IP with or without deleting it (confirmDialog `connection.detachConfirm` / `connection.deleteConfirm`), enable root (`enableRoot`), auto-backup policy save/enable/disable (`auto.*`), restore backup (DbRestoreModal, `tr('actions.startRestore')`)
107|EXISTING_TOUR: none
108|TOUR_MOUNT: no
109|NOTES: none
110|
111|ROUTE: /dashboard/database/backups
112|FILE: frontend/src/routes/dashboard/database/backups/+page.svelte
113|CREATE: none. Backups are created from the instance detail page.
114|DELETE: DbBackupsTable row delete → confirmDialog(`backups.deleteNamed`, or `backups.deleteNamedStuck` for stuck backups) → async `api.delete /api/v1/database-instances/backups/{id}`. Bulk delete is available.
115|OTHER_MUTATIONS: Restore: row restore opens `$lib/components/database/DbRestoreModal.svelte` (flavor, volume size, name); submit with `tr('actions.startRestore')`. Calls `POST /api/v1/database-instances/restore`.
116|EXISTING_TOUR: none
117|TOUR_MOUNT: no
118|NOTES: Needs an existing backup.
119|
120|ROUTE: /dashboard/containers/clusters
121|FILE: frontend/src/routes/dashboard/containers/clusters/+page.svelte
122|CREATE: Header `<button disabled={!$canWrite}>` `t('clusters.actions.create')` (containers-shell ns) opens `$lib/components/k3s/K3sClusterCreateModal.svelte` (drover ns): name, cluster template, node and master counts, optional keypair. Submit with `t('clusterCreate.create')`, disabled without `$canWrite`, a name and a template. Calls `api.post /api/v1/clusters`.
123|DELETE: K3sClusterListTable `t('overview.table.delete')` (drover ns) and bulk delete → confirmDialog(`clusters.deleteDialog.body` / `clusters.bulk.deleteDialog`) → async `api.delete /api/v1/clusters/{id}`.
124|OTHER_MUTATIONS: none
125|EXISTING_TOUR: none
126|TOUR_MOUNT: no
127|NOTES: This is Magnum K8s (nav service 'magnum'). It shows a serviceUnavailable panel when Magnum is missing. Needs `canWrite` and a cluster template (/api/v1/clusters/templates).
128|
129|ROUTE: /dashboard/containers/clusters/[id]
130|FILE: frontend/src/routes/dashboard/containers/clusters/[id]/+page.svelte
131|CREATE: none
132|DELETE: ClusterHeader `t('clusters.actions.delete')` → confirmDialog(`clusters.deleteDialog.body`) → `api.delete`.
133|OTHER_MUTATIONS: none (Detail/Resources/Events tabs are read-only)
134|EXISTING_TOUR: none
135|TOUR_MOUNT: no
136|NOTES: The Resources and Events tabs are disabled until the cluster has a `stack_id`.
137|
138|ROUTE: /dashboard/containers/instances
139|FILE: frontend/src/routes/dashboard/containers/instances/+page.svelte
140|CREATE: Header `<button>` `t('instances.list.create')` opens `$lib/components/dashboard/containers/instances/ContainerCreateModal.svelte`. Name and image are required; env vars and ports are optional (`instances.create.add`). Submit with `t('instances.actions.create')`. Calls `api.post /api/v1/containers`.
141|DELETE: ContainersTable `t('instances.actions.delete')` and bulk delete → confirmDialog(`instances.delete.confirm`) → async `api.delete /api/v1/containers/{uuid}`.
142|OTHER_MUTATIONS: start/stop per row and in bulk (`POST /{uuid}/start|stop`)
143|EXISTING_TOUR: none
144|TOUR_MOUNT: no
145|NOTES: Zun (nav service 'zun'). ZunServiceBanner and ZunServiceUnavailable appear when the service is down.
146|
147|ROUTE: /dashboard/containers/instances/[id]
148|FILE: frontend/src/routes/dashboard/containers/instances/[id]/+page.svelte
149|CREATE: none
150|DELETE: ContainerDetailHeader `t('instances.actions.delete')` → confirmDialog(`instances.delete.confirm`) → `api.delete`.
151|OTHER_MUTATIONS: start/stop (`POST /api/v1/containers/{id}/{action}`), open terminal (`instances.terminal.title`, ContainerTerminalPanel), logs panel
152|EXISTING_TOUR: none
153|TOUR_MOUNT: no
154|NOTES: Stop shows only while the container is Running; Start shows otherwise.
155|
156|ROUTE: /dashboard/drover
157|FILE: frontend/src/routes/dashboard/drover/+page.svelte
158|CREATE: DroverHeader `<Button dataTour="drover-create-open">` `t('header.create')` (drover-pages ns); the empty state DroverClusterGrid has `t('cluster.createFirst')`. Both open `$lib/components/dashboard/drover/K3sCreateClusterModal.svelte`. Submit is `<button data-tour="drover-create-submit">` `t('actions.create')`; it closes the modal immediately and creation runs through `ctrl.createCluster`.
159|DELETE: K3sClusterCard `t('actions.delete')` (only when canDelete) → confirmDialog(`list.confirmDelete`) through k3sClusterListController.
160|OTHER_MUTATIONS: download kubeconfig (card button), show/hide deleted toggle, detail SlidePanel (K3sClusterDetailPanel)
161|EXISTING_TOUR: drover-create-open, drover-create-form, drover-name, drover-os, drover-masters, drover-agents, drover-flavor, drover-create-submit. All are used by the `drover` tour in tours.ts.
162|TOUR_MOUNT: yes (DroverHeader mounts `<TutorialStartButton tour="drover" />`)
163|NOTES: Gated by `$k3sPermissions.editClusters`. Keypair selection only when `$k3sPermissions.adminCredentials`. Nav service 'k3s'.
164|
165|ROUTE: /dashboard/drover/[id]
166|FILE: frontend/src/routes/dashboard/drover/[id]/+page.svelte (renders K3sClusterDetailPanel; uses k3sClusterDetailController)
167|CREATE:
168|- Nodegroup: K3sNodegroupsSection inside K3sClusterMainPanel, with K3sNodegroupCreateModal.
169|- ConfigMap: `saveConfigMap` with isNew.
170|- Secret: `saveSecret` with isNew.
171|DELETE: cluster (`detail.confirmDelete`), nodegroup (inline confirm, `overview.nodegroups.cancel`), ConfigMap (`configMaps.confirmDelete`), Secret (`secrets.confirmDelete`), Pod (`detail.confirmDeletePod`), Service (`detail.confirmDeleteService`)
172|OTHER_MUTATIONS: scale agents (`detail.confirmScale`), attach/detach network interfaces, health check, kubeconfig download (admin kubeconfig needs a confirm), rollout restart and scale for deployments, edit nodegroups (K3sNodegroupEditModal), enable/disable Stampede, pod logs, cloud shell overlay
173|EXISTING_TOUR: none
174|TOUR_MOUNT: no
175|NOTES: Tabs are synced to `?tab=` and are main, configmaps, secrets, services, workloads, pods.
176|
177|ROUTE: /dashboard/secrets
178|FILE: frontend/src/routes/dashboard/secrets/+page.svelte
179|CREATE: Three header `<button>`s (dashboard-home ns), shown according to the active tab. Each also appears as an empty-state CTA. All use `$lib/components/ui/FormModal.svelte`.
180|- `t('secrets.actions.createSecret')`: name, type, payload; submitLabel `secrets.actions.create`.
181|- `t('secrets.actions.createContainer')`: name, type generic/rsa/certificate.
182|- `t('secrets.actions.createOrder')`: key type, algorithm, bit length; submitLabel `secrets.actions.request`.
183|- Calls go through `secretsApi` (`$lib/api/secrets`).
184|DELETE: Secret row `t('secrets.actions.delete')` (hidden for system_managed secrets) → confirmDialog(`secrets.confirm.deleteSecret`). Container delete → confirmDialog(`secrets.confirm.deleteContainer`). Bulk delete on each tab.
185|OTHER_MUTATIONS: show/hide payload (`showValue` / `hide`), copy payload
186|EXISTING_TOUR: none
187|TOUR_MOUNT: no
188|NOTES: Behind the `$betaFeatures.keyManager` beta flag (Barbican). Tabs: secrets, containers, orders, quota (read-only).
189|
190|ROUTE: /dashboard/my-resources
191|FILE: frontend/src/routes/dashboard/my-resources/+page.svelte
192|CREATE: none
193|DELETE: none
194|OTHER_MUTATIONS: none (read-only GET /api/v1/user-dashboard/summary; auto refresh)
195|EXISTING_TOUR: none
196|TOUR_MOUNT: no
197|NOTES: Read-only summary (MyResourcesSummary, ProjectUsageTable, ResourceInventoryCard). Not in nav.
198|
199|ROUTE: /dashboard/notifications
200|FILE: frontend/src/routes/dashboard/notifications/+page.svelte
201|CREATE: none
202|DELETE: none
203|OTHER_MUTATIONS: Loading the page automatically marks unread announcements as read (`POST /api/v1/announcements/{id}/read`). Expand/collapse toggles. UsageScheduleReminders (usage-schedule ns) offers `t('refresh')` and `t('manage')` links to instance detail.
204|EXISTING_TOUR: none
205|TOUR_MOUNT: no
206|NOTES: Supports `?focus=<announcementId>`. Not in nav.
207|
208|ROUTE: /dashboard/activity
209|FILE: frontend/src/routes/dashboard/activity/+page.svelte
210|CREATE: none
211|DELETE: none
212|OTHER_MUTATIONS: none (GET /api/v1/dashboard/activity?range=; period ToggleGroup; auto-refresh toggle)
213|EXISTING_TOUR: none
214|TOUR_MOUNT: no
215|NOTES: Read-only charts and an observation table. Not in nav.
216|
217|ROUTE: /dashboard/usage
218|FILE: frontend/src/routes/dashboard/usage/+page.svelte
219|CREATE: none
220|DELETE: none
221|OTHER_MUTATIONS: UsageExtensionReview (usage-schedule ns):
222|- Policy form `t('policySave')` → `PUT /api/v1/instances/usage-extension-policy`; only when `policy.can_manage`.
223|- Per-request `t('approve')` / `t('reject')` → `POST /usage-extension-requests/{id}/review`; only when `can_review` and the request is pending.
224|- Scope select (project/domain) only for `$auth.isDomainManager`.
225|EXISTING_TOUR: none
226|TOUR_MOUNT: no
227|NOTES: The approve/reject path needs a pending extension request and a reviewer role. Not in nav.
228|
229|ROUTE: /dashboard/usage-report
230|FILE: frontend/src/routes/dashboard/usage-report/+page.svelte
231|CREATE: none
232|DELETE: none
233|OTHER_MUTATIONS: none (GETs only: usage-report?range=7d|30d|90d, dashboard/quotas, chat/usage; auto-refresh toggle)
234|EXISTING_TOUR: none
235|TOUR_MOUNT: no
236|NOTES: Read-only. Not in nav.
237|
238|ROUTE: /dashboard/observability
239|FILE: frontend/src/routes/dashboard/observability/+page.svelte
240|CREATE: none
241|DELETE: none
242|OTHER_MUTATIONS: none. `t('observability.refresh')` reloads; selecting an instance shows MetricsPanel.
243|EXISTING_TOUR: none
244|TOUR_MOUNT: no
245|NOTES: Needs at least one instance in the project.
246|
247|ROUTE: /dashboard/iam
248|FILE: frontend/src/routes/dashboard/iam/+page.svelte
249|CREATE: none
250|DELETE: none
251|OTHER_MUTATIONS: none
252|EXISTING_TOUR: none
253|TOUR_MOUNT: no
254|NOTES: Placeholder only; +page.ts redirects (308) to /dashboard/iam/users.
255|
256|ROUTE: /dashboard/iam/users
257|FILE: frontend/src/routes/dashboard/iam/users/+page.svelte (renders `$lib/components/iam/DomainIamConsole.svelte`; domain-iam ns)
258|CREATE:
259|- Invitations tab (IamInvitations): email form submitted with `t('sendInvite')`, then a FormModal (`inviteProjectsTitle`) to pick projects, sent with `t('inviteProjectsSend')`.
260|- Login tab (IamLogin): `t('addProvider')` opens a FormModal (submit `t('save')`).
261|DELETE:
262|- Users tab: `t('evictionAction')` → confirmDialog(`evictionConfirm` + `evictionReadmission`). This evicts the user from the domain.
263|- Invitations: `t('revoke')` → confirmDialog(`revokeConfirm`).
264|- Login providers: `t('delete')` → confirmDialog(`deleteProviderConfirm`).
265|OTHER_MUTATIONS:
266|- Users: `t('editUser')` FormModal.
267|- Login: provider edit and enable/disable (`disableProviderConfirm`), login policy `t('savePolicy')`.
268|- Recovery tab: `t('recover')` → confirmDialog(`recoverConfirm`).
269|- Monitoring tab (workspace-iam ns): IamResources, IamForecast, IamQuotas. Quota actions: QuotaEditor `t('editDefaults')` / `t('editProject')` / `t('save')`; ComputePoolPanel `saveCap` / `removeCap`; GpuQuotaRequests `fulfill` / `reject`.
270|EXISTING_TOUR: none
271|TOUR_MOUNT: no
272|NOTES: Needs `state.isDomainManager` (nav capability 'domainManager'). Tabs: users, invitations, login, recovery, monitoring.
273|
274|ROUTE: /dashboard/iam/projects
275|FILE: frontend/src/routes/dashboard/iam/projects/+page.svelte (renders `$lib/components/iam/ProjectIamConsole.svelte` → IamProjects)
276|CREATE: `<Button variant="accent">` `workspaceT('newProject')` (workspace-selector ns) opens `$lib/components/projects/CreateProjectModal.svelte`. Only when `capability.can_create_project`.
277|DELETE: `t('projectRemove')` opens `$lib/components/admin/projects/AdminProjectDeleteModal.svelte`. It inspects dependent resources first (cleanup links); the danger `<Button onclick={confirmDelete}>` is enabled only after `canDelete`.
278|OTHER_MUTATIONS: `t('projectEdit')` → IamProjectEdit `t('save')`. `t('projectMembers')` → IamProjectMembers: `t('assignRoles')`, `t('editRoles')` (ProjectMemberRolesModal), `t('removeMember')` → confirmDialog(`removeConfirm`).
279|EXISTING_TOUR: none
280|TOUR_MOUNT: no
281|NOTES: Needs domain manager in a non-personal domain (nav capability 'projectManagement').
282|
283|ROUTE: /dashboard/iam/groups
284|FILE: frontend/src/routes/dashboard/iam/groups/+page.svelte (renders `$lib/components/iam/GroupIamConsole.svelte` → IamGroups; domain-iam-groups ns)
285|CREATE: `t('create')` opens a FormModal (title `createTitle`, submit `t('createSubmit')`).
286|DELETE: Group `t('delete')` → confirmDialog(`deleteConfirm`). Member `t('remove')` → confirmDialog(`removeConfirm`).
287|OTHER_MUTATIONS: `t('edit')` (save with `t('save')`); `t('members')` → IamGroupMembers add member (`t('add')`)
288|EXISTING_TOUR: none
289|TOUR_MOUNT: no
290|NOTES: Needs `isDomainManager` (nav capability 'domainManager').
291|
292|ROUTE: /dashboard/chat
293|FILE: frontend/src/routes/dashboard/chat/+page.svelte (renders `$lib/components/chat/ChatPanel.svelte`; supports `?workspace=<id>`)
294|CREATE:
295|- Conversation: ChatSidebar `t('sidebar.newChat')`. The conversation is actually created on first send (`ensureConversation` → `POST /api/v1/chat/conversations`).
296|- Project: CreateProjectDialog (submit `t('createProject.title')`) via `onCreateProject`, or `t('sidebar.newChatInProject')`.
297|- Agent: AgentManagerModal (`POST /api/v1/chat/agents`), opened from AgentPicker "manage". AgentHubModal clones agents (`/agents/{id}/clone`).
298|DELETE: Conversation: sidebar `t('sidebar.deleteConversation')` → confirmDialog(`panel.dialog.deleteNamedConversation`); needs `lumen-history_editor`. Project: sidebar `t('sidebar.removeProject')` → confirmDialog(`panel.dialog.deleteProject`). Agents: `agentManager.deleteConfirm`.
299|OTHER_MUTATIONS: fork from a message, switch active leaf, assign a conversation to a project, approve/deny tool calls (ChatToolApproval), edit agents, sources panel, model picker
300|EXISTING_TOUR: none
…
302|NOTES: Nav service 'chat'. Sending/creating needs `$serviceCapabilities('lumen-chat_user')`; deleting needs `lumen-history_editor`.
303|
…
418|NOTES: The modal's `t('settingsModal.allSettings')` link goes to /dashboard/account.

[Showing lines 1-300 of 418. Use :301 to continue]
