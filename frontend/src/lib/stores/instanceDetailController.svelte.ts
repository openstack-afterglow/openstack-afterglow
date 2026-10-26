import { fromStore, get, writable } from 'svelte/store';
import { getContext, onDestroy, setContext, untrack } from 'svelte';
import { auth, canWrite } from '$lib/stores/auth';
import { api, ApiError } from '$lib/api/client';
import { createAutoRefresh, type AutoRefreshController } from '$lib/utils/autoRefresh.svelte';
import { isTransitional } from '$lib/utils/instanceStatus';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { toast } from '$lib/stores/toast';
import { t } from '$lib/i18n/ns/instance';
import { intlLocale } from '$lib/i18n/runtime.svelte';
import type { Instance } from '$lib/types/compute';
import type { FloatingIpDetail, PortInfo, NetworkInfo } from '$lib/types/networks';
import type { SecurityGroup } from '$lib/types/securityGroup';
import type { Volume as VolumeInfo } from '$lib/types/volume';
import type { FlavorOption } from '$lib/types/flavor';

// Selection setters publish synchronously: effects cannot observe same-tick A→B→A.
const instanceDetailSelectionRevision = writable(0);
export function invalidateInstanceDetailSelection() {
	instanceDetailSelectionRevision.update(revision => revision + 1);
}

interface VolumeAttachment {
	volume_id: string;
	name?: string | null;
	device?: string | null;
	delete_on_termination?: boolean;
	size?: number | null;
	status?: string | null;
}

export interface PasswordPrecheck {
	supported: boolean;
	reason: string | null;
	os_admin_user: string | null;
	server_status: string;
}

export interface InstanceDetailControllerOpts {
	instanceId: () => string;
	effectiveProjectId: () => string | undefined;
	adminMode: () => boolean;
	onDelete: () => void;
	onUpdated?: () => void;
}

interface MigrationInfo {
	id: string | null;
	source: string | null;
	dest: string | null;
	status: string | null;
	type: string | null;
	memory_percent: number | null;
}

interface MigrationStatus {
	host: string | null;
	migration: MigrationInfo | null;
	error: string | null;
}

interface InstanceMutationContext {
	id: string;
	status: string;
	flavorId: string | null | undefined;
	flavorName: string | null;
	token: string;
	userId: string | null | undefined;
	ownProjectId: string | undefined;
	effectiveProjectId: string | undefined;
	adminMode: boolean;
	isSystemAdmin: boolean;
}

export function createInstanceDetailController(opts: InstanceDetailControllerOpts): InstanceDetailController {
	const identity = fromStore(auth);
	const writePermission = fromStore(canWrite);
	// Domain state
	let instance = $state<Instance | null>(null);
	let floatingIps = $state<FloatingIpDetail[]>([]);
	let interfaces = $state<PortInfo[]>([]);
	let volumes = $state<VolumeAttachment[]>([]);
	let allSecurityGroups = $state<SecurityGroup[]>([]);
	let securityGroupPorts = $state<PortInfo[]>([]);
	let securityGroupsLoading = $state(true);
	let securityGroupsError = $state('');
	let availableVolumes = $state<VolumeInfo[]>([]);
	let availableNetworks = $state<NetworkInfo[]>([]);
	let ownerDisplay = $state('');
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');
	let fetchGeneration = 0;
	let deleting = $state(false);
	let actioning = $state<string | null>(null);
	let consoleLog = $state('');
	let logLoading = $state(false);
	let logFull = $state(false);
	let consoleOpening = $state(false);
	let consoleOpenMessage = $state('');
	let consoleOpenError = $state('');
	let logGeneration = 0;
	let consoleGeneration = 0;

	let renameOpen = $state(false);
	let renameDraft = $state('');
	let renameError = $state('');
	let renameLoading = $state(false);
	let renameGeneration = 0;
	let renameAuthEpoch = 0;
	let renameContext: { id: string; projectId: string; ownProjectId: string | undefined; adminMode: boolean; token: string; userId: string | null | undefined; epoch: number } | null = null;
	const canRename = $derived(
		writePermission.current && !!identity.current.token && !!instance && instance.id === opts.instanceId()
		&& !!instance.project_id && instance.project_id === opts.effectiveProjectId()
		&& (!opts.adminMode() || identity.current.isSystemAdmin)
	);
	const unsubscribeRenameAuth = auth.subscribe(() => {
		renameAuthEpoch++;
		if (renameContext) closeRename();
	});
	const unsubscribeRenamePermission = canWrite.subscribe(() => {
		if (renameContext) closeRename();
	});
	const unsubscribeRenameSelection = instanceDetailSelectionRevision.subscribe(() => {
		if (renameContext) closeRename();
	});
	onDestroy(() => { unsubscribeRenameAuth(); unsubscribeRenamePermission(); unsubscribeRenameSelection(); closeRename(); });
	$effect.pre(() => {
		const id = opts.instanceId();
		const projectId = opts.effectiveProjectId();
		const adminMode = opts.adminMode();
		const allowed = canRename;
		untrack(() => {
			if (renameContext && (!allowed || renameContext.id !== id || renameContext.projectId !== projectId || renameContext.adminMode !== adminMode)) closeRename();
		});
	});

	function closeRename() {
		++renameGeneration;
		renameContext = null;
		renameOpen = false;
		renameDraft = '';
		renameError = '';
		renameLoading = false;
	}

	function openRename() {
		const caller = get(auth);
		if (!canRename || !instance?.project_id || instance.project_id !== opts.effectiveProjectId() || !caller.token
			|| (opts.adminMode() && !caller.isSystemAdmin) || mutationBusy() || renameLoading) return;
		++renameGeneration;
		renameContext = { id: instance.id, projectId: instance.project_id, ownProjectId: ownPid(), adminMode: opts.adminMode(), token: caller.token, userId: caller.userId, epoch: renameAuthEpoch };
		renameDraft = instance.name;
		renameError = '';
		renameOpen = true;
	}

	async function submitRename() {
		const context = renameContext;
		const generation = renameGeneration;
		const owns = () => !!context && renameOpen && generation === renameGeneration && context.epoch === renameAuthEpoch
			&& canRename && instance?.id === context.id && opts.instanceId() === context.id
			&& opts.effectiveProjectId() === context.projectId && ownPid() === context.ownProjectId
			&& opts.adminMode() === context.adminMode && get(auth).token === context.token && get(auth).userId === context.userId;
		if (!context || !owns() || renameLoading || mutationBusy()) return;
		const draft = renameDraft.trim();
		if (draft === instance?.name) { closeRename(); return; }
		const name = draft.replace(/[^\S\r\n]+/g, '-');
		if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$/.test(name)) {
			renameError = t('rename.invalidName');
			return;
		}
		if (name === instance?.name) { closeRename(); return; }
		renameLoading = true;
		renameError = '';
		try {
			const result = await api.put<{ id: string; name: string; project_id: string }>(
				`/api/v1/${context.adminMode ? 'admin/' : ''}instances/${context.id}/name`, { name }, context.token,
				context.adminMode ? context.ownProjectId : context.projectId, { replayOnUnauthorized: false },
			);
			if (!owns()) return;
			if (result.id !== context.id || result.project_id !== context.projectId || result.name !== name) {
				renameError = t('rename.failed');
				return;
			}
			++fetchGeneration;
			loading = false;
			refreshing = false;
			instance = { ...instance!, name: result.name };
			closeRename();
			opts.onUpdated?.();
		} catch (e) {
			if (owns()) renameError = e instanceof ApiError ? e.message : t('rename.failed');
		} finally {
			if (generation === renameGeneration) renameLoading = false;
		}
	}

	// Password capability belongs to the selected instance and caller context.
	let passwordPrecheck = $state<PasswordPrecheck | null>(null);
	let passwordPrecheckLoading = $state(false);
	let passwordPrecheckError = $state('');
	let passwordPrecheckGeneration = 0;
	const passwordPrecheckReason = $derived(
		passwordPrecheck?.supported === false && !opts.adminMode()
			? t('password.unsupportedInstance')
			: passwordPrecheck?.reason ?? null
	);
	const canChangePassword = $derived.by(() => {
		const caller = identity.current;
		if (!writePermission.current || !caller.token || !instance || instance.id !== opts.instanceId()) return false;
		if (opts.adminMode()) return caller.isSystemAdmin === true;
		return !!caller.userId && instance.user_id === caller.userId
			&& !!instance.project_id && instance.project_id === opts.effectiveProjectId();
	});
	// Resize is available in both writable user and admin detail modes.
	let resizeFlavors = $state<FlavorOption[]>([]);
	let resizeFlavorsLoading = $state(false);
	let resizeLoading = $state(false);
	let resizeError = $state('');
	let resizeFlavorContext: InstanceMutationContext | null = null;
	let resizeFlavorGeneration = 0;
	let migrateHosts = $state<{ name: string; state: string; status: string; cpu_model: string | null }[]>([]);
	let migrateLoading = $state(false);
	let migrateError = $state('');

	// 마이그레이션 추적 상태
	let migrationStatus = $state<MigrationStatus | null>(null);
	let migrationStatusLoading = $state(false);

	// Derived
	const fixedIpsList = $derived(instance?.ip_addresses.filter(ip => ip.type === 'fixed') ?? []);
	const floatingIpsList = $derived(instance?.ip_addresses.filter(ip => ip.type === 'floating') ?? []);
	const assignedPortIds = $derived(new Set(floatingIps.filter(f => f.port_id).map(f => f.port_id!)));
	const availableInterfaces = $derived(interfaces.filter(i => !assignedPortIds.has(i.id)));

	// AutoRefresh instances
	const detailPollAr = createAutoRefresh(() => {
		const id = opts.instanceId();
		if (!id || !get(auth).token) return;
		return fetchInstance(id, { silent: true });
	}, {
		storageKey: 'instance-detail',
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60, 120],
		invokeOnMount: false,
	});

	const consolePollAr = createAutoRefresh(() => loadConsoleLog(logFull), {
		storageKey: 'instance-detail-console',
		defaultActive: false,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
	});

	// 인스턴스 상태가 전이 중이면 상세 폴링을 4초로 가속, 안정되면 해제
	$effect(() => {
		detailPollAr.setBoost(isTransitional(instance?.status) ? 4 : null);
	});

	// Token/projectId helpers (read at call time — not reactive)
	function tok() { return get(auth).token ?? undefined; }
	function ownPid() { return get(auth).projectId ?? undefined; }
	function instancePath(id: string, adminMode = opts.adminMode()) {
		return `/api/v1/${adminMode ? 'admin/' : ''}instances/${id}`;
	}
	function detailProjectId() { return opts.adminMode() ? ownPid() : opts.effectiveProjectId(); }
	function captureReadContext() {
		const id = opts.instanceId();
		const token = tok();
		const adminMode = opts.adminMode();
		const projectId = opts.effectiveProjectId();
		const transportProjectId = detailProjectId();
		const ownProjectId = ownPid();
		const epoch = renameAuthEpoch;
		const selection = get(instanceDetailSelectionRevision);
		return { id, token, adminMode, transportProjectId, ownProjectId, current: () => opts.instanceId() === id
			&& tok() === token && opts.adminMode() === adminMode && opts.effectiveProjectId() === projectId
			&& detailProjectId() === transportProjectId && renameAuthEpoch === epoch
			&& ownPid() === ownProjectId
			&& get(instanceDetailSelectionRevision) === selection };
	}

	// Utility functions
	function sgNameById(id: string): string {
		return allSecurityGroups.find(sg => sg.id === id)?.name ?? id.slice(0, 8) + '...';
	}

	function securityGroupIdsForPort(port: PortInfo): string[] {
		return securityGroupPorts.find(item => item.id === port.id)?.security_group_ids
			?? port.security_group_ids ?? [];
	}

	function networkNameById(id: string): string {
		return availableNetworks.find(n => n.id === id)?.name ?? id.slice(0, 12) + '...';
	}

	function formatDate(dt: string | null): string {
		if (!dt) return '-';
		return new Date(dt).toLocaleString(intlLocale());
	}

	// Core fetch
	async function fetchInstance(id: string, fetchOpts?: { silent?: boolean; refreshSecurityGroups?: boolean }) {
		if (renameContext && (renameContext.id !== id || renameContext.projectId !== opts.effectiveProjectId() || renameContext.adminMode !== opts.adminMode())) closeRename();
		++passwordPrecheckGeneration;
		passwordPrecheck = null;
		passwordPrecheckLoading = false;
		passwordPrecheckError = '';
		if (fetchOpts?.silent) {
			refreshing = true;
		} else {
			loading = true;
			error = '';
			allSecurityGroups = [];
			securityGroupPorts = [];
			securityGroupsLoading = true;
			securityGroupsError = '';
		}
		if (fetchOpts?.refreshSecurityGroups) securityGroupsLoading = true;
		const requestToken = tok();
		const requestProjectId = opts.effectiveProjectId();
		const requestAdminMode = opts.adminMode();
		const transportProjectId = detailProjectId();
		const base = instancePath(id, requestAdminMode);
		const readContext = captureReadContext();
		const generation = ++fetchGeneration;
		const ownsRequest = () => (
			generation === fetchGeneration
			&& opts.instanceId() === id
			&& opts.effectiveProjectId() === requestProjectId
			&& tok() === requestToken
			&& opts.adminMode() === requestAdminMode
			&& detailProjectId() === transportProjectId
			&& readContext.current()
		);

		const instancePromise = api.get<Instance>(base, requestToken, transportProjectId);
		const fipsPromise = api.get<FloatingIpDetail[]>(requestAdminMode ? `${base}/floating-ips` : '/api/v1/networks/floating-ips', requestToken, transportProjectId).catch(() => []);
		const interfacesPromise = api.get<PortInfo[]>(`${base}/interfaces`, requestToken, transportProjectId).catch(() => []);
		const volumesPromise = api.get<VolumeAttachment[]>(`${base}/volumes`, requestToken, transportProjectId).catch(() => []);
		const securityGroupsPromise = api.get<{ ports: PortInfo[]; security_groups: SecurityGroup[] }>(
			`${base}/security-groups`,
			requestToken,
			transportProjectId,
			fetchOpts?.refreshSecurityGroups ? { refresh: true } : undefined,
		);
		const allVolumesPromise = api.get<VolumeInfo[]>(requestAdminMode ? `${base}/available-volumes` : '/api/v1/volumes', requestToken, transportProjectId).catch(() => []);
		const networksPromise = api.get<NetworkInfo[]>(requestAdminMode ? `${base}/networks` : '/api/v1/networks', requestToken, transportProjectId).catch(() => []);
		const ownerPromise = api.get<{ display: string }>(`${base}/owner`, requestToken, transportProjectId).catch(() => ({ display: '' }));

		void interfacesPromise.then((value) => { if (ownsRequest()) interfaces = value; });
		void volumesPromise.then((value) => { if (ownsRequest()) volumes = value; });
		void securityGroupsPromise.then((value) => {
			if (!ownsRequest()) return;
			allSecurityGroups = value.security_groups;
			securityGroupPorts = value.ports;
			securityGroupsError = '';
		}).catch((e) => {
			if (ownsRequest()) securityGroupsError = e instanceof ApiError ? e.message : t('controller.securityGroup.fetchFailed');
		}).finally(() => {
			if (ownsRequest()) securityGroupsLoading = false;
		});
		void networksPromise.then((value) => { if (ownsRequest()) availableNetworks = value; });
		void ownerPromise.then((value) => { if (ownsRequest()) ownerDisplay = value.display || ''; });
		void Promise.all([instancePromise, fipsPromise]).then(([loadedInstance, fips]) => {
			if (!ownsRequest()) return;
			const instanceIps = new Set(
				loadedInstance.ip_addresses.filter((ip) => ip.type === 'floating').map((ip) => ip.addr)
			);
			floatingIps = fips.filter((floatingIp) => instanceIps.has(floatingIp.floating_ip_address));
		}).catch(() => undefined);
		void Promise.all([volumesPromise, allVolumesPromise]).then(([attachments, allVolumes]) => {
			if (!ownsRequest()) return;
			const attachedIds = new Set(attachments.map((attachment) => attachment.volume_id));
			availableVolumes = allVolumes.filter((volume) => volume.status === 'available' && !attachedIds.has(volume.id));
		});

		try {
			const loadedInstance = await instancePromise;
			if (!ownsRequest()) return;
			instance = loadedInstance;
			error = '';
			if (canChangePassword) void fetchPasswordPrecheck(id);
			if (opts.adminMode()) {
				if (loadedInstance.status === 'MIGRATING') {
					void loadMigrationStatus(id);
				} else if (migrationStatus?.migration?.status !== 'running') {
					void loadMigrationStatus(id);
				}
			}
		} catch (e) {
			if (ownsRequest()) {
				error = e instanceof ApiError ? t('controller.error.fetchFailed', { status: e.status, message: e.message }) : t('controller.error.server');
			}
		} finally {
			if (ownsRequest()) {
				if (fetchOpts?.silent) refreshing = false;
				else loading = false;
			}
		}
	}

	function manualRefresh() {
		const id = opts.instanceId();
		if (id) fetchInstance(id, { silent: true });
	}

	async function loadConsoleLog(full = false) {
		if (!instance || instance.id !== opts.instanceId()) return;
		const context = captureReadContext();
		const generation = ++logGeneration;
		logLoading = true;
		const length = full ? 0 : 200;
		try {
			const data = await api.get<{ output: string }>(
				`${instancePath(context.id, context.adminMode)}/log?length=${length}`, context.token, context.ownProjectId,
			);
			if (context.current() && generation === logGeneration) consoleLog = data.output || t('controller.console.noLog');
		} catch {
			if (context.current() && generation === logGeneration) consoleLog = t('controller.console.logFailed');
		} finally {
			if (generation === logGeneration) logLoading = false;
		}
	}

	async function toggleFullLog() {
		logFull = !logFull;
		await loadConsoleLog(logFull);
	}

	async function openConsole() {
		if (!instance || instance.id !== opts.instanceId() || consoleOpening) return;
		const context = captureReadContext();
		const generation = ++consoleGeneration;
		consoleOpening = true;
		consoleOpenError = '';
		consoleOpenMessage = t('controller.console.requestingUrl');
		try {
			const data = await api.get<{ url: string }>(`${instancePath(context.id, context.adminMode)}/console`, context.token, context.ownProjectId);
			if (!context.current() || generation !== consoleGeneration) return;
			const url = data.url?.trim();
			if (!url) {
				consoleOpenError = t('controller.console.emptyUrl');
				toast.error(consoleOpenError);
				return;
			}
			consoleOpenMessage = t('controller.console.opening');
			window.open(url, '_blank', 'noopener,noreferrer');
		} catch {
			if (!context.current() || generation !== consoleGeneration) return;
			consoleOpenError = t('controller.console.urlFailed');
			toast.error(consoleOpenError);
		} finally {
			if (generation === consoleGeneration) {
				consoleOpening = false;
				consoleOpenMessage = '';
			}
		}
	}

	function captureMutationContext(): InstanceMutationContext | null {
		const caller = get(auth);
		if (!instance || instance.id !== opts.instanceId() || !caller.token || !get(canWrite)
			|| (opts.adminMode() && !caller.isSystemAdmin)) return null;
		return {
			id: instance.id,
			status: instance.status,
			flavorId: instance.flavor_id,
			flavorName: instance.flavor_name,
			token: caller.token,
			userId: caller.userId,
			ownProjectId: ownPid(),
			effectiveProjectId: opts.effectiveProjectId(),
			adminMode: opts.adminMode(),
			isSystemAdmin: caller.isSystemAdmin,
		};
	}

	function ownsMutationContext(context: InstanceMutationContext, checkState = true) {
		const caller = get(auth);
		return get(canWrite) && instance?.id === context.id && opts.instanceId() === context.id
			&& caller.token === context.token && caller.userId === context.userId
			&& caller.isSystemAdmin === context.isSystemAdmin && ownPid() === context.ownProjectId
			&& opts.effectiveProjectId() === context.effectiveProjectId && opts.adminMode() === context.adminMode
			&& (!checkState || (instance.status === context.status
				&& instance.flavor_id === context.flavorId && instance.flavor_name === context.flavorName));
	}

	function mutationBusy() { return !!actioning || deleting || resizeLoading; }

	async function performAction(action: 'start' | 'stop' | 'reboot' | 'shelve' | 'unshelve') {
		const context = captureMutationContext();
		if (!context || mutationBusy()) return;
		const statusAllowed = action === 'start' || action === 'shelve'
			? context.status === 'SHUTOFF'
			: action === 'unshelve'
				? context.status === 'SHELVED' || context.status === 'SHELVED_OFFLOADED'
				: context.status === 'ACTIVE';
		if (!statusAllowed) return;
		const message = t('controller.action.confirm', { action });
		if (!(await confirmDialog(action === 'stop' || action === 'shelve' ? `${message}\n${t('panel.stoppedQuotaWarning')}` : message))) return;
		if (!ownsMutationContext(context) || mutationBusy()) return;
		actioning = action;
		try {
			await api.post(`${instancePath(context.id, context.adminMode)}/${action}`, {}, context.token, context.ownProjectId);
			if (ownsMutationContext(context, false)) await fetchInstance(context.id, { silent: true });
		} catch (e) {
			if (ownsMutationContext(context, false)) toast.error(t('controller.action.failed', { action, message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function deleteInstance() {
		const context = captureMutationContext();
		if (!instance || !context || context.status !== 'SHUTOFF' || mutationBusy()) return;
		const autoDeleteVols = volumes.filter(v => v.delete_on_termination);
		const keepVols = volumes.filter(v => !v.delete_on_termination);
		const lines = [t('controller.delete.confirm', { name: instance.name })];
		if (autoDeleteVols.length) lines.push(t('controller.delete.autoDeleteVolumes', { volumes: autoDeleteVols.map(v => v.name || v.device).join(', ') }));
		if (keepVols.length) lines.push(t('controller.delete.keepVolumes', { volumes: keepVols.map(v => v.name || v.device).join(', ') }));
		if (instance.union_upper_volume_id) lines.push(t('controller.delete.upperVolumeNotice'));
		if (!(await confirmDialog(lines.join('\n')))) return;
		if (!ownsMutationContext(context) || mutationBusy()) return;
		deleting = true;
		try {
			await api.delete(instancePath(context.id, context.adminMode), context.token, context.ownProjectId);
			if (ownsMutationContext(context, false)) opts.onDelete();
		} catch (e) {
			if (ownsMutationContext(context, false)) toast.error(t('controller.delete.failed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			deleting = false;
		}
	}

	async function assignFloatingIp(portId: string) {
		if (!instance) return;
		actioning = 'fip-assign-' + portId;
		try {
			await api.post(`${instancePath(instance.id)}/floating-ip?port_id=${portId}`, {}, tok(), ownPid());
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(t('controller.floatingIp.assignFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function releaseFloatingIp(fipId: string) {
		if (!instance) return;
		if (!(await confirmDialog(t('controller.floatingIp.releaseConfirm')))) return;
		actioning = 'fip-release-' + fipId;
		try {
			if (opts.adminMode()) {
				await api.delete(`${instancePath(instance.id)}/floating-ips/${fipId}`, tok(), ownPid());
			} else {
				await api.post(`/api/v1/networks/floating-ips/${fipId}/disassociate`, {}, tok(), ownPid());
				await api.delete(`/api/v1/networks/floating-ips/${fipId}`, tok(), ownPid());
			}
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(t('controller.floatingIp.releaseFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function attachVolume(volumeId: string) {
		if (!instance) return;
		actioning = 'attach-vol';
		try {
			await api.post(`${instancePath(instance.id)}/volumes`, { volume_id: volumeId }, tok(), ownPid());
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(t('controller.volume.attachFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function createAndAttachVolume(name: string, sizeGb: number) {
		if (!instance || opts.adminMode()) return;
		actioning = 'create-vol';
		try {
			const vol = await api.post<VolumeInfo>('/api/v1/volumes', { name, size_gb: sizeGb }, tok(), ownPid());
			await api.post(`${instancePath(instance.id)}/volumes`, { volume_id: vol.id }, tok(), ownPid());
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(t('controller.volume.createAttachFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function detachVolume(volumeId: string) {
		if (!instance) return;
		if (!(await confirmDialog(t('controller.volume.detachConfirm')))) return;
		actioning = 'detach-' + volumeId;
		try {
			await api.delete(`${instancePath(instance.id)}/volumes/${volumeId}`, tok(), ownPid());
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(t('controller.volume.detachFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function setDeleteOnTermination(volumeId: string, next: boolean) {
		if (!instance) return;
		if (!(await confirmDialog(t('controller.volume.autoDeleteConfirm', { state: next ? 'enabled' : 'disabled' })))) return;
		actioning = 'dot-' + volumeId;
		try {
			await api.patch(`${instancePath(instance.id)}/volumes/${volumeId}`, { delete_on_termination: next }, tok(), ownPid());
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(t('controller.volume.changeFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function attachInterface(netId: string) {
		if (!instance) return;
		actioning = 'attach-iface';
		try {
			await api.post(`${instancePath(instance.id)}/interfaces`, { net_id: netId }, tok(), ownPid());
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(t('controller.interface.attachFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function detachInterface(portId: string) {
		if (!instance) return;
		if (!(await confirmDialog(t('controller.interface.detachConfirm')))) return;
		actioning = 'detach-iface-' + portId;
		try {
			await api.delete(`${instancePath(instance.id)}/interfaces/${portId}`, tok(), ownPid());
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(t('controller.interface.detachFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function saveSgEdit(portId: string, sgIds: string[]) {
		if (!instance) return;
		actioning = 'sg-' + portId;
		try {
			await api.post(
				`${instancePath(instance.id)}/ports/${portId}/security-groups`,
				{ security_group_ids: sgIds },
				tok(),
				ownPid()
			);
			await fetchInstance(instance.id, { silent: true, refreshSecurityGroups: true });
		} catch (e) {
			toast.error(t('controller.securityGroup.updateFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	// Admin detail keeps the administrative mutation path; project detail uses its own instance routes.
	function resizePath(context: InstanceMutationContext, action: 'resize' | 'confirm-resize' | 'revert-resize') {
		return `/api/v1/${context.adminMode ? 'admin/' : ''}instances/${context.id}/${action}`;
	}
	function resizeProjectId(context: InstanceMutationContext) {
		return context.adminMode ? context.ownProjectId : context.effectiveProjectId;
	}
	function selectableResizeFlavor(flavorId: string) {
		return flavorId !== instance?.flavor_id && resizeFlavors.some(f =>
			f.id === flavorId && (!!instance?.flavor_id || f.name !== instance?.flavor_name) && f.eligibility?.selectable !== false
		);
	}

	async function loadResizeFlavors() {
		const context = captureMutationContext();
		if (!context || context.status !== 'SHUTOFF' || mutationBusy()) return;
		const generation = ++resizeFlavorGeneration;
		resizeFlavorContext = null;
		resizeFlavors = [];
		resizeError = '';
		resizeFlavorsLoading = true;
		try {
			const flavors = await api.get<FlavorOption[]>(
				`${instancePath(context.id, context.adminMode)}/resize-flavors`, context.token, resizeProjectId(context)
			);
			if (generation === resizeFlavorGeneration && ownsMutationContext(context)) {
				resizeFlavors = flavors;
				resizeFlavorContext = context;
			}
		} catch (e) {
			if (generation === resizeFlavorGeneration && ownsMutationContext(context)) {
				resizeError = e instanceof ApiError ? e.message : t('controller.resize.flavorsFailed');
			}
		} finally {
			if (generation === resizeFlavorGeneration) resizeFlavorsLoading = false;
		}
	}

	async function doResize(flavorId: string): Promise<boolean> {
		const context = resizeFlavorContext;
		if (!context || context.status !== 'SHUTOFF' || !ownsMutationContext(context)
			|| resizeFlavorsLoading || mutationBusy() || !selectableResizeFlavor(flavorId)) return false;
		const flavor = resizeFlavors.find(f => f.id === flavorId)!;
		const ramLabel = flavor.ram >= 1024 ? `${(flavor.ram / 1024).toFixed(0)} GB` : `${flavor.ram} MB`;
		const flavorLabel = t('resize.flavorLabel', { name: flavor.name, vcpus: flavor.vcpus, ram: ramLabel });
		if (!(await confirmDialog(t('resize.confirmMessage', { flavorLabel })))) return false;
		if (resizeFlavorContext !== context || !ownsMutationContext(context)
			|| resizeFlavorsLoading || mutationBusy() || !selectableResizeFlavor(flavorId)) return false;
		resizeLoading = true;
		resizeError = '';
		try {
			await api.post(resizePath(context, 'resize'), { flavor_id: flavorId }, context.token, resizeProjectId(context));
			if (!ownsMutationContext(context, false)) return false;
			await fetchInstance(context.id, { silent: true });
			return true;
		} catch (e) {
			if (ownsMutationContext(context, false)) resizeError = e instanceof ApiError ? e.message : t('controller.resize.failed');
			return false;
		} finally {
			resizeLoading = false;
		}
	}

	async function revertResize() {
		const context = captureMutationContext();
		if (!context || context.status !== 'VERIFY_RESIZE' || mutationBusy()) return;
		if (!(await confirmDialog(t('controller.resize.revertConfirm')))) return;
		if (!ownsMutationContext(context) || mutationBusy()) return;
		actioning = 'revert-resize';
		try {
			await api.post(resizePath(context, 'revert-resize'), {}, context.token, resizeProjectId(context));
			if (ownsMutationContext(context, false)) await fetchInstance(context.id, { silent: true });
		} catch (e) {
			if (ownsMutationContext(context, false)) toast.error(t('controller.resize.revertFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function confirmResize() {
		const context = captureMutationContext();
		if (!context || context.status !== 'VERIFY_RESIZE' || mutationBusy()) return;
		if (!(await confirmDialog(t('controller.resize.confirm')))) return;
		if (!ownsMutationContext(context) || mutationBusy()) return;
		actioning = 'confirm-resize';
		try {
			await api.post(resizePath(context, 'confirm-resize'), {}, context.token, resizeProjectId(context));
			if (ownsMutationContext(context, false)) await fetchInstance(context.id, { silent: true });
		} catch (e) {
			if (ownsMutationContext(context, false)) toast.error(t('controller.resize.confirmFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function fetchPasswordPrecheck(serverId: string) {
		const generation = ++passwordPrecheckGeneration;
		passwordPrecheck = null;
		passwordPrecheckError = '';
		passwordPrecheckLoading = false;
		if (!canChangePassword || instance?.id !== serverId) return;
		const requestToken = tok();
		const requestProjectId = opts.effectiveProjectId();
		const context = captureReadContext();
		const ownsRequest = () => generation === passwordPrecheckGeneration
			&& opts.instanceId() === serverId && opts.effectiveProjectId() === requestProjectId
			&& tok() === requestToken && canChangePassword && context.current();
		passwordPrecheckLoading = true;
		try {
			const result = await api.get<PasswordPrecheck>(
				`${instancePath(serverId, context.adminMode)}/admin-password/precheck`, requestToken, context.transportProjectId
			);
			if (ownsRequest()) passwordPrecheck = result;
		} catch (e) {
			if (ownsRequest()) passwordPrecheckError = e instanceof ApiError ? e.message : t('controller.password.precheckFailed');
		} finally {
			if (ownsRequest()) passwordPrecheckLoading = false;
		}
	}

	// A successful HTTP response means Nova accepted the request, not guest login proof.
	async function doSetPassword(password: string): Promise<string | null> {
		if (!instance || instance.id !== opts.instanceId()) return t('controller.password.noInstance');
		if (!canChangePassword) return t('controller.password.notAllowed');
		if (instance.status !== 'ACTIVE' || passwordPrecheckLoading || !passwordPrecheck?.supported) {
			return passwordPrecheckReason || passwordPrecheckError || t('controller.password.unavailable');
		}
		const serverId = instance.id;
		const requestToken = tok();
		const requestProjectId = opts.effectiveProjectId();
		try {
			await api.post(`${instancePath(serverId)}/admin-password`, { new_password: password }, requestToken, detailProjectId());
			if (opts.instanceId() === serverId && opts.effectiveProjectId() === requestProjectId && tok() === requestToken) {
				toast.info(t('controller.password.requestSent'), 8000);
			}
			return null;
		} catch (e) {
			return e instanceof ApiError ? e.message : t('controller.password.failed');
		}
	}


	// Admin: migrate
	async function loadMigrateHosts(type: 'live' | 'cold' = 'live') {
		migrateHosts = [];
		migrateError = '';
		try {
			// server_id를 항상 전달해 소스 자신을 제외한다.
			// 라이브 마이그레이션: cpu_filter=true(기본) — 동일 CPU 모델 호스트만
			// 콜드 마이그레이션: cpu_filter=false — CPU 모델 무관 전체 호스트
			const params = new URLSearchParams();
			if (instance) params.set('server_id', instance.id);
			if (type === 'cold') params.set('cpu_filter', 'false');
			migrateHosts = await api.get<{ name: string; state: string; status: string; cpu_model: string | null }[]>(
				`/api/v1/admin/compute-hosts?${params.toString()}`,
				tok(),
				ownPid()
			);
		} catch {
			migrateHosts = [];
		}
	}

	async function doMigrate(type: 'live' | 'cold', host: string): Promise<boolean> {
		if (!instance) return false;
		migrateLoading = true;
		migrateError = '';
		try {
			if (type === 'live') {
				await api.post(`/api/v1/admin/instances/${instance.id}/live-migrate`, { host: host || null, block_migration: 'auto' }, tok(), ownPid());
			} else {
				await api.post(`/api/v1/admin/instances/${instance.id}/cold-migrate`, { host: host || null }, tok(), ownPid());
			}
			await fetchInstance(instance.id, { silent: true });
			return true;
		} catch (e) {
			migrateError = e instanceof ApiError ? e.message : t('controller.migration.failed');
			return false;
		} finally {
			migrateLoading = false;
		}
	}

	// Admin: migration status tracking
	async function loadMigrationStatus(serverId?: string) {
		const id = serverId ?? instance?.id;
		if (!id) return;
		migrationStatusLoading = true;
		try {
			migrationStatus = await api.get<MigrationStatus>(
				`/api/v1/admin/instances/${id}/migration-status`,
				tok(),
				ownPid()
			);
		} catch {
			// fail-soft — 폴링 중 오류는 무시하고 기존 상태 유지
		} finally {
			migrationStatusLoading = false;
		}
	}

	async function abortMigration(): Promise<void> {
		if (!instance) return;
		try {
			await api.post(`/api/v1/admin/instances/${instance.id}/live-migrate/abort`, {}, tok(), ownPid());
			toast.success(t('controller.migration.abortRequested'));
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : t('controller.migration.abortFailed'));
		}
	}

	async function forceCompleteMigration(): Promise<void> {
		if (!instance) return;
		try {
			await api.post(`/api/v1/admin/instances/${instance.id}/live-migrate/force-complete`, {}, tok(), ownPid());
			toast.success(t('controller.migration.forceCompleteRequested'));
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(e instanceof ApiError ? e.message : t('controller.migration.forceCompleteFailed'));
		}
	}

	return {
		get instance() { return instance; },
		get canRename() { return canRename; },
		get renameOpen() { return renameOpen; },
		get renameDraft() { return renameDraft; },
		set renameDraft(value: string) { renameDraft = value; },
		get renameError() { return renameError; },
		get renameLoading() { return renameLoading; },
		openRename,
		closeRename,
		submitRename,
		get floatingIps() { return floatingIps; },
		get interfaces() { return interfaces; },
		get volumes() { return volumes; },
		get allSecurityGroups() { return allSecurityGroups; },
		get securityGroupsLoading() { return securityGroupsLoading; },
		get securityGroupsError() { return securityGroupsError; },
		get availableVolumes() { return availableVolumes; },
		get availableNetworks() { return availableNetworks; },
		get ownerDisplay() { return ownerDisplay; },
		get loading() { return loading; },
		get refreshing() { return refreshing; },
		get error() { return error; },
		get deleting() { return deleting; },
		get actioning() { return actioning; },
		get consoleLog() { return consoleLog; },
		get logLoading() { return logLoading; },
		get logFull() { return logFull; },
		get consoleOpening() { return consoleOpening; },
		get consoleOpenMessage() { return consoleOpenMessage; },
		get consoleOpenError() { return consoleOpenError; },
		set logFull(v: boolean) { logFull = v; },
		get instanceId() { return opts.instanceId(); },
		get effectiveProjectId() { return opts.effectiveProjectId(); },
		get adminMode() { return opts.adminMode(); },
		get fixedIpsList() { return fixedIpsList; },
		get floatingIpsList() { return floatingIpsList; },
		get assignedPortIds() { return assignedPortIds; },
		get availableInterfaces() { return availableInterfaces; },
		get canChangePassword() { return canChangePassword; },
		get passwordPrecheck() { return passwordPrecheck; },
		get passwordPrecheckReason() { return passwordPrecheckReason; },
		get passwordPrecheckLoading() { return passwordPrecheckLoading; },
		get passwordPrecheckError() { return passwordPrecheckError; },
		get resizeFlavors() { return resizeFlavors; },
		get resizeFlavorsLoading() { return resizeFlavorsLoading; },
		selectableResizeFlavor,
		get resizeLoading() { return resizeLoading; },
		get resizeError() { return resizeError; },
		set resizeError(v: string) { resizeError = v; },
		get migrateHosts() { return migrateHosts; },
		get migrateLoading() { return migrateLoading; },
		get migrateError() { return migrateError; },
		set migrateError(v: string) { migrateError = v; },
		get migrationStatus() { return migrationStatus; },
		get migrationStatusLoading() { return migrationStatusLoading; },
		detailPollAr,
		consolePollAr,
		fetchInstance,
		manualRefresh,
		loadConsoleLog,
		toggleFullLog,
		openConsole,
		performAction,
		deleteInstance,
		assignFloatingIp,
		releaseFloatingIp,
		attachVolume,
		createAndAttachVolume,
		detachVolume,
		setDeleteOnTermination,
		attachInterface,
		detachInterface,
		saveSgEdit,
		loadResizeFlavors,
		doResize,
		revertResize,
		confirmResize,
		fetchPasswordPrecheck,
		doSetPassword,
		loadMigrateHosts,
		doMigrate,
		loadMigrationStatus,
		abortMigration,
		forceCompleteMigration,
		sgNameById,
		securityGroupIdsForPort,
		networkNameById,
		formatDate,
	};
}

export interface InstanceDetailController {
	readonly instance: Instance | null;
	readonly canRename: boolean;
	readonly renameOpen: boolean;
	renameDraft: string;
	readonly renameError: string;
	readonly renameLoading: boolean;
	openRename(): void;
	closeRename(): void;
	submitRename(): Promise<void>;
	readonly floatingIps: FloatingIpDetail[];
	readonly interfaces: PortInfo[];
	readonly volumes: VolumeAttachment[];
	readonly allSecurityGroups: SecurityGroup[];
	readonly securityGroupsLoading: boolean;
	readonly securityGroupsError: string;
	readonly availableVolumes: VolumeInfo[];
	readonly availableNetworks: NetworkInfo[];
	readonly ownerDisplay: string;
	readonly loading: boolean;
	readonly refreshing: boolean;
	readonly error: string;
	readonly deleting: boolean;
	readonly actioning: string | null;
	readonly consoleLog: string;
	readonly logLoading: boolean;
	logFull: boolean;
	readonly consoleOpening: boolean;
	readonly consoleOpenMessage: string;
	readonly consoleOpenError: string;
	readonly instanceId: string;
	readonly effectiveProjectId: string | undefined;
	readonly adminMode: boolean;
	readonly fixedIpsList: Instance['ip_addresses'];
	readonly floatingIpsList: Instance['ip_addresses'];
	readonly assignedPortIds: Set<string>;
	readonly availableInterfaces: PortInfo[];
	readonly canChangePassword: boolean;
	readonly passwordPrecheck: PasswordPrecheck | null;
	readonly passwordPrecheckReason: string | null;
	readonly passwordPrecheckLoading: boolean;
	readonly passwordPrecheckError: string;
	readonly resizeFlavors: FlavorOption[];
	readonly resizeFlavorsLoading: boolean;
	readonly resizeLoading: boolean;
	resizeError: string;
	readonly migrateHosts: { name: string; state: string; status: string; cpu_model: string | null }[];
	readonly migrateLoading: boolean;
	migrateError: string;
	readonly migrationStatus: MigrationStatus | null;
	readonly migrationStatusLoading: boolean;
	readonly detailPollAr: AutoRefreshController;
	readonly consolePollAr: AutoRefreshController;
	fetchInstance(id: string, options?: { silent?: boolean; refreshSecurityGroups?: boolean }): Promise<void>;
	manualRefresh(): void;
	loadConsoleLog(full?: boolean): Promise<void>;
	toggleFullLog(): Promise<void>;
	openConsole(): Promise<void>;
	performAction(action: 'start' | 'stop' | 'reboot' | 'shelve' | 'unshelve'): Promise<void>;
	deleteInstance(): Promise<void>;
	assignFloatingIp(portId: string): Promise<void>;
	releaseFloatingIp(fipId: string): Promise<void>;
	attachVolume(volumeId: string): Promise<void>;
	createAndAttachVolume(name: string, sizeGb: number): Promise<void>;
	detachVolume(volumeId: string): Promise<void>;
	setDeleteOnTermination(volumeId: string, next: boolean): Promise<void>;
	attachInterface(netId: string): Promise<void>;
	detachInterface(portId: string): Promise<void>;
	saveSgEdit(portId: string, sgIds: string[]): Promise<void>;
	loadResizeFlavors(): Promise<void>;
	selectableResizeFlavor(flavorId: string): boolean;
	doResize(flavorId: string): Promise<boolean>;
	revertResize(): Promise<void>;
	confirmResize(): Promise<void>;
	fetchPasswordPrecheck(serverId: string): Promise<void>;
	doSetPassword(password: string): Promise<string | null>;
	loadMigrateHosts(type?: 'live' | 'cold'): Promise<void>;
	doMigrate(type: 'live' | 'cold', host: string): Promise<boolean>;
	loadMigrationStatus(serverId?: string): Promise<void>;
	abortMigration(): Promise<void>;
	forceCompleteMigration(): Promise<void>;
	sgNameById(id: string): string;
	securityGroupIdsForPort(port: PortInfo): string[];
	networkNameById(id: string): string;
	formatDate(date: string | null): string;
}

const INSTANCE_DETAIL_KEY = Symbol('instance-detail');

export function provideInstanceDetailController(store: InstanceDetailController) {
	setContext(INSTANCE_DETAIL_KEY, store);
}

export function useInstanceDetailController(): InstanceDetailController {
	const store = getContext<InstanceDetailController | undefined>(INSTANCE_DETAIL_KEY);
	if (!store) throw new Error(t('controller.contextRequired'));
	return store;
}
