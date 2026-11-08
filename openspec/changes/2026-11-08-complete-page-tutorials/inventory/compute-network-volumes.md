# Route inventory: compute, network, volumes (dashboard)

Source: read-only subagent FamousBobcat, 2026-11-08. Verify against source before relying on a line.

1|Inventory of the 33 target routes, one block each. Five legacy routes and `/dashboard/instances/[id]` 301-redirect from their `+page.server.ts` files, so their `+page.svelte` never renders. Only the instances, images and volumes pages and the Waygate workspace mount `TutorialStartButton`. i18n keys are given as `namespace:key`.
2|
3|```
4|ROUTE: /dashboard/compute/instances
5|FILE: frontend/src/routes/dashboard/compute/instances/+page.svelte
6|CREATE: PageHeader Button instance:list.createVmAction (dataTour="vm-create-open") → openWizard() → lib/components/VmCreatePanel.svelte (SlidePanel dataTour="wizard-panel"; inner data-tour="wizard-stepper", "wizard-body"); WizardFooter: next/deploy wrapper data-tour="wizard-next" (last step Button wizard:footer.create → onDeploy), cancel data-tour="wizard-cancel"
7|DELETE: row ActionMenu (InstanceRowActions) instance:rowActions.delete (only status SHUTOFF) → confirmInstanceDeletion (confirmDialog; typed requiredText gate instance:controller.delete.requiredText when auto-delete volumes) → api.delete /api/v1/instances/{id}; bulk: BulkSelectionOverlay instance:list.delete (shown only if every selected row is SHUTOFF) → POST /api/v1/instances/bulk-action {action:'delete'}; async, destructive
8|OTHER_MUTATIONS: row: console (ACTIVE), stop (ACTIVE, canWrite, confirmDialog), start/shelve (SHUTOFF, shelve confirm), unshelve (SHELVED*); bulk start/stop via /instances/bulk-action; row click opens InstanceDetailPanel SlidePanel (see /compute/instances/[id])
9|EXISTING_TOUR: vm-create-open; instance-list (only when wizard closed, not loading/refreshing, no error); wizard-panel/wizard-stepper/wizard-body/wizard-next/wizard-cancel live in the wizard components
10|TOUR_MOUNT: yes (tour="vm-create"; tours.ts vmCreateSteps: open → wizard raw steps 2,1,5,6 → instance-list)
11|NOTES: mutations require $canWrite and current scope revision; the wizard needs an image, flavor, network and keypair; delete/shelve confirms add instance:panel.stoppedQuotaWarning; auto-refresh control; sidebar is closed in tour prepare
12|```
13|```
14|ROUTE: /dashboard/compute/instances/[id]
15|FILE: frontend/src/routes/dashboard/compute/instances/[id]/+page.svelte (wraps lib/components/InstanceDetailPanel.svelte)
16|CREATE: none (sections: VolumesSection instance:volumes.createAndAttach / volumes.attach; NetworkSection network.addInterface / network.addFloatingIp)
17|DELETE: InstanceHeader instance:header.delete (SHUTOFF only) → confirmInstanceDeletion with typed requiredText → api.delete /api/v1/instances/{id}; destructive, async
18|OTHER_MUTATIONS: start/stop/reboot/shelve/unshelve (confirmDialog instance:controller.action.confirm); open console; resize (ResizeModal) + confirm/revert resize (VERIFY_RESIZE); change password (PasswordModal, if canChangePassword); rename (RenameModal); attach/create-and-attach/detach volume, toggle delete-on-termination; assign/release floating IP; attach/detach interface; edit port security groups; usage schedule extend (UsageScheduleSection)
19|EXISTING_TOUR: none
20|TOUR_MOUNT: no
21|NOTES: live/cold migration, evacuate, abort/force-complete are admin-only (shown only when adminProjectId is set); every mutation is gated by canMutate/ownsMutationContext; also embedded as a SlidePanel on the instances list and the topology page
22|```
23|```
24|ROUTE: /dashboard/compute/instances/[id]/console-log
25|FILE: frontend/src/routes/dashboard/compute/instances/[id]/console-log/+page.svelte
26|CREATE: none
27|DELETE: none
28|OTHER_MUTATIONS: none (reload button → load(); close button → window.close())
29|EXISTING_TOUR: none
30|TOUR_MOUNT: no
31|NOTES: read-only full console log, opened as a separate window from the instance detail console section
32|```
33|```
34|ROUTE: /dashboard/compute/images
35|FILE: frontend/src/routes/dashboard/compute/images/+page.svelte
36|CREATE: PageHeader Button images-keys:imagesPage.upload → lib/components/ImageUploadModal.svelte (submit images-keys:uploadModal.startUpload); also drag-and-drop ImageDropOverlay opens the same modal; no submit data-tour
37|DELETE: ImageCard images-keys:imageCard.delete → imagesController.deleteImage → confirmDialog(imagesController.deleteConfirm); bulk (tags view only) imagesPage.bulk.delete → confirmDialog(imagesPage.bulk.deleteConfirm); ImageDetailPanel delete (imageDetailController confirmDialog); destructive
38|OTHER_MUTATIONS: activate/deactivate (card toggle + bulk); edit (ImageEditModal, save imageEdit.save); repository/tag catalog browse
39|EXISTING_TOUR: images-header, images-controls (ImageCatalogToolbar tourPrefix), images-ready, images-results
40|TOUR_MOUNT: yes (tour="images", read-only browse tour; no create/delete steps)
41|NOTES: only images owned by the current project can be selected, edited or deleted; bulk actions only in the 'tags' view mode
42|```
43|```
44|ROUTE: /dashboard/compute/keypairs
45|FILE: frontend/src/routes/dashboard/compute/keypairs/+page.svelte
46|CREATE: PageHeader Button images-keys:keypairPage.actions.create (also KeypairEmptyState CTA) → lib/components/keypair/KeypairCreateModal.svelte (name, optional public key text/file; submit keypairCreate.actions.create; if generated, shows private key once, then keypairCreate.actions.confirm) → POST /api/v1/keypairs
47|DELETE: KeypairListTable keypairTable.actions.delete → confirmDialog(keypairPage.deleteDialog.body) → api.delete /api/v1/keypairs/{name}
48|OTHER_MUTATIONS: copy fingerprint
49|EXISTING_TOUR: none
50|TOUR_MOUNT: no
51|NOTES: not in sidebar nav (only reachable by URL); the nav SSH-keys entry is /dashboard/account/keypairs, which does the same CRUD
52|```
53|```
54|ROUTE: /dashboard/instances/[id]
55|FILE: frontend/src/routes/dashboard/instances/[id]/+page.svelte
56|CREATE: none
57|DELETE: none (same InstanceDetailPanel as /compute/instances/[id])
58|OTHER_MUTATIONS: same as /dashboard/compute/instances/[id]
59|EXISTING_TOUR: none
60|TOUR_MOUNT: no
61|NOTES: +page.server.ts 301-redirects to /dashboard/compute/instances/{id}; GlobalTopology still links here; point tutorials at the compute route
62|```
63|```
64|ROUTE: /dashboard/volumes
65|FILE: frontend/src/routes/dashboard/volumes/+page.svelte
66|CREATE: PageHeader Button volume:page.create (dataTour="volume-create-open"; also VolumesEmptyState emptyState.createFirst) → lib/components/volume/VolumeCreateModal.svelte (data-tour="volume-create-form"; fields createModal.nameLabel / sizeLabel; submit Button volume:createModal.create dataTour="volume-create-submit", disabled until name is non-empty and size ≥1)
67|DELETE: VolumeListTable row ActionMenu (VolumeOperationItems) volume:operationItems.delete (blocked while attached) → confirmDialog(listController.deleteConfirm) → api.delete /api/v1/volumes/{id}; bulk BulkSelectionOverlay page.delete → confirmDialog(page.bulkDeleteConfirm); snapshot tab row delete → confirmDialog(listController.deleteSnapshotConfirm); destructive, async
68|OTHER_MUTATIONS: rename (VolumeRenameModal), boot instance from volume (available+bootable), extend, backup, snapshot (beta), auto-backup settings link, transfer (send/receive/list; buttons need canWrite); force delete hidden here (isSystemAdmin=false)
69|EXISTING_TOUR: volume-create-open, volume-create-form, volume-create-submit, volume-list
70|TOUR_MOUNT: yes (tour="volume": open → form/submit → list)
71|NOTES: Snapshots tab and snapshot actions need beta flag volumeSnapshots (account/beta); row click opens VolumeDetailPanel SlidePanel; volume-list only renders when at least one volume exists (otherwise the empty state shows)
72|```
73|```
74|ROUTE: /dashboard/volumes/[id]
75|FILE: frontend/src/routes/dashboard/volumes/[id]/+page.svelte (wraps lib/components/VolumeDetailPanel.svelte)
76|CREATE: none (VolumeActions volume:volumeActions.attach → VolumeAttachModal, pick instance, submit attachModal.attach; only when status available)
77|DELETE: VolumeActions volume:volumeActions.delete (disabled while attached) → confirmDialog(detailController.deleteConfirm) → goto /dashboard/volumes; snapshot delete in VolumeSnapshotsSection (beta)
78|OTHER_MUTATIONS: rename, attach, ActionMenu: boot, extend, backup, snapshot (beta), transfer, auto-backup link; force delete only for system admin in error states
79|EXISTING_TOUR: none
80|TOUR_MOUNT: no
81|NOTES: the same panel is used as a SlidePanel on /dashboard/volumes
82|```
83|```
84|ROUTE: /dashboard/volumes/backups
85|FILE: frontend/src/routes/dashboard/volumes/backups/+page.svelte
86|CREATE: PageHeader Button volume:backupsPage.create → lib/components/volume/backups/VolumeBackupCreateModal.svelte (submit backupCreateModal.create) → POST /api/v1/volumes/backups; auto-backup policy: VolumeBackupPolicies autoPolicy.settings → VolumeBackupPolicyModal (autoPolicy.save)
87|DELETE: VolumeBackupListTable backupListTable.delete → confirmDialog(backupsPage.deleteConfirm) → api.delete /api/v1/volumes/backups/{id}; bulk backupsPage.delete; policy remove autoPolicy.remove; destructive
88|OTHER_MUTATIONS: restore (VolumeBackupRestoreModal backupRestoreModal.restore → POST …/restore; completion can link to instance creation); policy edit / pause / resume
89|EXISTING_TOUR: none
90|TOUR_MOUNT: no
91|NOTES: needs an existing volume; policy buttons need $canWrite; ?auto-backup={volumeId} deep link auto-opens the policy modal
92|```
93|```
94|ROUTE: /dashboard/volumes/snapshots
95|FILE: frontend/src/routes/dashboard/volumes/snapshots/+page.svelte
96|CREATE: PageHeader Button volume:snapshotsPage.create (also VolumeSnapshotsEmptyState) → lib/components/volume/snapshots/VolumeSnapshotCreateModal.svelte (volume, name, description, force; submit snapshotCreateModal.create) → POST /api/v1/volume-snapshots
97|DELETE: VolumeSnapshotsTable snapshotsTable.delete → confirmDialog(snapshotsPage.deleteConfirm); bulk → snapshotsPage.bulkDeleteConfirm
98|OTHER_MUTATIONS: none
99|EXISTING_TOUR: none
100|TOUR_MOUNT: no
101|NOTES: beta-gated: without betaFeatures.volumeSnapshots it renders BetaFeatureGate only; nav item is beta-flagged too; needs an existing volume
102|```
103|```
104|ROUTE: /dashboard/network/networks
105|FILE: frontend/src/routes/dashboard/network/networks/+page.svelte
106|CREATE: PageHeader Button network-pages:networks.createButton → lib/components/dashboard/network/networks/NetworkCreateModal.svelte (name, optional subnet networkCreate.addSubnet; submit networkCreate.create) → POST /api/v1/networks; floating IP: FloatingIpCard floatingIpCard.allocateButton → lib/components/network/FloatingIpAllocateModal.svelte (submit network-resources:network.floatingIp.allocate)
107|DELETE: NetworksTableCard networksTable.delete (owned only) → confirmDialog(networks.deleteConfirm + list.deleteImpact) → api.delete /api/v1/networks/{id}; bulk delete networks / release floating IPs (networks.bulk.deleteConfirm / releaseConfirm); destructive
108|OTHER_MUTATIONS: set default network (networksTable.setDefault → PUT /api/v1/networks/default); row opens NetworkDetailPanel SlidePanel (add subnet, connect/disconnect router)
109|EXISTING_TOUR: none
110|TOUR_MOUNT: no
111|NOTES: floating IP allocation needs an external network (floatingIpCard.noExternal); only project-owned networks are selectable
112|```
113|```
114|ROUTE: /dashboard/network/networks/[id]
115|FILE: frontend/src/routes/dashboard/network/networks/[id]/+page.svelte
116|CREATE: SubnetTableSection network-resources:network.subnets.addToggle → inline form (name, CIDR, gateway, DHCP, optional router; submit network.subnets.add) → POST /networks/{id}/subnets (+ router interface)
117|DELETE: NetworkDetailHeader network.actions.delete → confirmDialog(network-pages:networkDetail.deleteConfirm) → goto /dashboard/network/networks; subnet delete → confirmDialog(networkDetail.subnetDeleteConfirm)
118|OTHER_MUTATIONS: edit subnet (PUT /networks/subnets/{id}); connect router (ConnectedRouterTable network.routers.connectAdd → network.actions.connect); disconnect router (confirm)
119|EXISTING_TOUR: none
120|TOUR_MOUNT: no
121|NOTES: all mutations need canManageNetwork (project-owned, not external); only owned routers can be connected or disconnected
122|```
123|```
124|ROUTE: /dashboard/networks/[id]
125|FILE: frontend/src/routes/dashboard/networks/[id]/+page.svelte
126|CREATE: DashboardSubnetSection network.subnets.addToggle/add (unreachable)
127|DELETE: DashboardNetworkHeader network.actions.delete (unreachable)
128|OTHER_MUTATIONS: none reachable
129|EXISTING_TOUR: none
130|TOUR_MOUNT: no
131|NOTES: legacy; +page.server.ts 301-redirects to /dashboard/network/networks/{id}; do not write a tutorial for it
132|```
133|```
134|ROUTE: /dashboard/network/floating-ips
135|FILE: frontend/src/routes/dashboard/network/floating-ips/+page.svelte
136|CREATE: none (help text links to /dashboard/network/networks for allocation)
137|DELETE: row network-pages:floatingIps.actions.release → confirmDialog(floatingIps.release.confirm) → api.delete /api/v1/networks/floating-ips/{id}; bulk release (floatingIps.bulk.confirm / confirmSkipped); destructive
138|OTHER_MUTATIONS: none
139|EXISTING_TOUR: none
140|TOUR_MOUNT: no
141|NOTES: allocation happens on the networks page; a tutorial should send the user there first
142|```
143|```
144|ROUTE: /dashboard/network/routers
145|FILE: frontend/src/routes/dashboard/network/routers/+page.svelte
146|CREATE: PageHeader Button network-pages:routers.createButton → lib/components/network/routers/RouterCreateModal.svelte (name, optional external network; submit network-resources:router.create.submit) → POST /api/v1/routers
147|DELETE: bulk only (BulkSelectionOverlay routers.delete → confirmDialog(routers.bulkConfirm)); single delete in RouterDetailPanel RouterInfoSection router.actions.delete → confirmDialog(router.confirm.delete)
148|OTHER_MUTATIONS: card opens RouterDetailPanel SlidePanel: add/remove interface, set/remove gateway, "full view" link (router.header.fullView)
149|EXISTING_TOUR: none
150|TOUR_MOUNT: no
151|NOTES: RouterEmptyState has no create CTA; external networks are prefetched on intent
152|```
153|```
154|ROUTE: /dashboard/network/routers/[id]
155|FILE: frontend/src/routes/dashboard/network/routers/[id]/+page.svelte
156|CREATE: RouterInterfacesSection network-resources:router.interfaces.add (select network → subnet) → POST /routers/{id}/interfaces
157|DELETE: RouterDetailWithRefreshHeader network-pages:routerHeader.delete → confirmDialog(routerDetail.deleteConfirm) → goto list; remove interface → confirmDialog(routerDetail.removeInterfaceConfirm)
158|OTHER_MUTATIONS: set gateway (router.gateway.set → router.actions.set); remove gateway (confirm)
159|EXISTING_TOUR: none
160|TOUR_MOUNT: no
161|NOTES: needs an existing subnet (interface) and an external network (gateway)
162|```
163|```
164|ROUTE: /dashboard/routers/[id]
165|FILE: frontend/src/routes/dashboard/routers/[id]/+page.svelte
166|CREATE: unreachable
167|DELETE: unreachable
168|OTHER_MUTATIONS: none reachable
169|EXISTING_TOUR: none
170|TOUR_MOUNT: no
171|NOTES: legacy; 301-redirects to /dashboard/network/routers/{id}
172|```
173|```
174|ROUTE: /dashboard/network/loadbalancers
175|FILE: frontend/src/routes/dashboard/network/loadbalancers/+page.svelte
176|CREATE: header <a> network-pages:loadBalancers.actions.create (also empty-state loadBalancers.empty.create) → navigates to /dashboard/network/loadbalancers/new (not a modal)
177|DELETE: bulk only: BulkSelectionOverlay loadBalancers.actions.delete → confirmDialog(loadBalancers.bulk.confirmDelete); single delete in LoadBalancerDetailPanel header lb.actions.delete / lb.actions.forceDelete; async
178|OTHER_MUTATIONS: card loadBalancers.actions.detail opens LoadBalancerDetailPanel SlidePanel: listener add/delete, pool add/delete, member add/remove
179|EXISTING_TOUR: none
180|TOUR_MOUNT: no
181|NOTES: Drover-owned LBs (isDroverLoadBalancer) cannot be selected for bulk delete; their detail panel offers forceDelete instead
182|```
183|```
184|ROUTE: /dashboard/network/loadbalancers/new
185|FILE: frontend/src/routes/dashboard/network/loadbalancers/new/+page.svelte
186|CREATE: full-page form: loadBalancerCreate.form.name / network / subnet / description; submit network-pages:loadBalancerCreate.actions.create → POST /api/v1/loadbalancers → goto /dashboard/network/loadbalancers/{id}
187|DELETE: none
188|OTHER_MUTATIONS: none (cancel = loadBalancerCreate.actions.cancel)
189|EXISTING_TOUR: none
190|TOUR_MOUNT: no
191|NOTES: name and VIP subnet are required; needs a network with a subnet; ?network={id} preselects the network (used by topology)
192|```
193|```
194|ROUTE: /dashboard/network/loadbalancers/[id]
195|FILE: frontend/src/routes/dashboard/network/loadbalancers/[id]/+page.svelte
196|CREATE: ListenerSection network-resources:lb.actions.addWithPlus → lb.actions.create; PoolSection lb.actions.addWithPlus → create; members lb.members.addWithPlus → lb.actions.add
197|DELETE: LbDetailHeader lb.actions.delete / lb.actions.forceDelete (Drover-protected) → confirmDialog; listener / pool delete (lb.confirm.deleteListener / deletePool); member remove (lb.confirm.removeMember)
198|OTHER_MUTATIONS: select pool to show members
199|EXISTING_TOUR: none
200|TOUR_MOUNT: no
201|NOTES: controller networkLoadbalancerDetailController; add a listener and pool before members; ERROR status shows LbErrorStatusTree
202|```
203|```
204|ROUTE: /dashboard/loadbalancers/[id]
205|FILE: frontend/src/routes/dashboard/loadbalancers/[id]/+page.svelte
206|CREATE: unreachable
207|DELETE: unreachable
208|OTHER_MUTATIONS: none reachable
209|EXISTING_TOUR: none
210|TOUR_MOUNT: no
211|NOTES: legacy; 301-redirects to /dashboard/network/loadbalancers/{id}
212|```
213|```
214|ROUTE: /dashboard/network/security-groups
215|FILE: frontend/src/routes/dashboard/network/security-groups/+page.svelte
216|CREATE: header <button> network-pages:securityGroups.create (disabled when quota is unknown or exhausted) → lib/components/dashboard/network/security-groups/SecurityGroupCreateModal.svelte (name, description; submit securityGroupCreate.create) → POST /api/v1/security-groups; rule: SecurityGroupRulesPanel securityGroupRules.add → AddRuleForm (submit addRule.add)
217|DELETE: SecurityGroupRulesPanel securityGroupRules.delete (hidden for 'default') → confirmDialog(securityGroups.deleteConfirm); bulk securityGroups.delete ('default' excluded); rule delete securityGroupRules.remove
218|OTHER_MUTATIONS: edit rule (securityGroupRules.edit → addRule.save; implemented as delete+recreate with rollback)
219|EXISTING_TOUR: none
220|TOUR_MOUNT: no
221|NOTES: select a group in the list to open the rules panel; group and rule quotas are shown via QuotaBar
222|```
223|```
224|ROUTE: /dashboard/security-groups
225|FILE: frontend/src/routes/dashboard/security-groups/+page.svelte
226|CREATE: unreachable (legacy securityGroup.page.create)
227|DELETE: unreachable
228|OTHER_MUTATIONS: none reachable
229|EXISTING_TOUR: none
230|TOUR_MOUNT: no
231|NOTES: legacy; 301-redirects to /dashboard/network/security-groups
232|```
233|```
234|ROUTE: /dashboard/network/topology
235|FILE: frontend/src/routes/dashboard/network/topology/+page.svelte
236|CREATE: canvas view only: CanvasToolbar topology:toolbar.network / router / instance / loadBalancer / database → NetworkCreateModal / RouterCreateModal / openWizard (prefilled network) / goto loadbalancers/new?network= / DbCreatePanel; drag-to-connect → TopologyLinkModal (topologyLink.connect): VM↔network interface, router gateway, router↔network (can create a subnet)
237|DELETE: none on the page (deletes inside detail SlidePanels: RouterDetailPanel router delete, InstanceDetailPanel delete)
238|OTHER_MUTATIONS: createCable (POST request.url); view toggle lane/canvas (localStorage 'topology.view'); node click opens Instance/Router/LB/Network detail SlidePanels
239|EXISTING_TOUR: none on the user page (CanvasToolbar dataTour="topology-legend-toggle" is used only by the admin-network tour)
240|TOUR_MOUNT: no
241|NOTES: sidebar top-level item; default view is canvas (DEFAULT_TOPOLOGY_VIEW); the lane view (GlobalTopology) is read-only; the database create needs Trove
242|```
243|```
244|ROUTE: /dashboard/topology
245|FILE: frontend/src/routes/dashboard/topology/+page.svelte
246|CREATE: none
247|DELETE: none
248|OTHER_MUTATIONS: none (read-only GlobalTopology)
249|EXISTING_TOUR: none
250|TOUR_MOUNT: no
251|NOTES: legacy; 301-redirects to /dashboard/network/topology
252|```
253|```
254|ROUTE: /dashboard/network/waygate
255|FILE: frontend/src/routes/dashboard/network/waygate/+page.svelte (→ lib/components/waygate/WaygateWorkspace.svelte → WaygateProjectWorkspace.svelte)
256|CREATE: header Button waygate:project.actions.createServer → FormModal (ClientSettingsFields server-create; submit project.actions.create); clients: project.actions.issueClient → createClient; network attach project.actions.attachNetwork → submitAttach
257|DELETE: server row/detail project.actions.delete / deleteServer → confirmDialog(project.confirm.serverDelete); bulk → project.confirm.bulkDelete; client delete (project.confirm.clientDelete); network detach (project.confirm.networkDetach)
258|OTHER_MUTATIONS: save server defaults, client settings, enable/disable client, download config / QR, export/import server backup
259|EXISTING_TOUR: waygate-header, waygate-list, waygate-ready
260|TOUR_MOUNT: yes (tour="waygate", read-only header→list tour)
261|NOTES: nav service 'waygate'; needs waygateConfigured; per-capability gates: create=waygate-gateways_editor, delete=gateways_admin, clients edit/revoke=clients_editor/clients_admin, routing=routing_admin; backup needs revokeClients+route; without a project it shows workspace.selectProject
262|```
263|```
264|ROUTE: /dashboard/account
265|FILE: frontend/src/routes/dashboard/account/+page.svelte (layout account/+layout.svelte)
266|CREATE: none
267|DELETE: none
268|OTHER_MUTATIONS: ProfileSection (account:profile.save → PATCH /api/v1/profile; email change POST /auth/email/changes; profile image upload); PasswordSection (password change, create/recovery request); LoginPreferenceSection (loginPreference.save → PUT /profile/login-preference); EmailNotificationsSection (admin-email:save via emailApi)
269|EXISTING_TOUR: none
270|TOUR_MOUNT: no
271|NOTES: settings forms only, no resource CRUD; the password section changes by state (has a password / needs creation / unknown)
272|```
273|```
274|ROUTE: /dashboard/account/keypairs
275|FILE: frontend/src/routes/dashboard/account/keypairs/+page.svelte (→ lib/components/account/KeypairsSection.svelte)
276|CREATE: header button account:keypairs.add → inline modal (keypairs.name, keypairs.publicKey textarea or keypairs.chooseFile; submit keypairs.createAction) → POST /api/v1/keypairs; if no public key, the generated private key is shown once (keypairs.privateKey, then keypairs.confirm)
277|DELETE: row account:keypairs.delete → confirmDialog(keypairs.deleteConfirm) → api.delete /api/v1/keypairs/{name}
278|OTHER_MUTATIONS: copy fingerprint
279|EXISTING_TOUR: none
280|TOUR_MOUNT: no
281|NOTES: nav "SSH keys" entry; keypairs are a VM-create prerequisite; public-key file limited to 64 KiB with ssh-* prefix validation
282|```
283|```
284|ROUTE: /dashboard/account/beta
285|FILE: frontend/src/routes/dashboard/account/beta/+page.svelte (→ BetaFeaturesSection.svelte)
286|CREATE: none
287|DELETE: none
288|OTHER_MUTATIONS: toggles via setBetaFeature: volumeSnapshots, fileStorageSnapshots, shareNetworks, securityServices, keyManager
289|EXISTING_TOUR: none
290|TOUR_MOUNT: no
291|NOTES: stored locally (account:beta.localOnly); enabling volumeSnapshots is a prerequisite for the snapshot tutorials
292|```
293|```
294|ROUTE: /dashboard/account/sessions
295|FILE: frontend/src/routes/dashboard/account/sessions/+page.svelte (→ SecuritySection.svelte)
296|CREATE: none
297|DELETE: row account:security.remove → inline confirm security.confirm/security.cancel → api.delete /api/v1/auth/sessions/{jti}; removing the last session logs out
298|OTHER_MUTATIONS: logout all (security.logoutAll → inline confirm → startLogout({all:true})); destructive to the current session
299|EXISTING_TOUR: none
300|TOUR_MOUNT: no
301|NOTES: the tutorial must warn that these actions end sessions, possibly the user's own
302|```
…
332|```

[Showing lines 1-300 of 332. Use :301 to continue]
