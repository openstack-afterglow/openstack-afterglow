import { get } from 'svelte/store';
import { getContext, setContext } from 'svelte';
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

export function createInstanceDetailController(opts: InstanceDetailControllerOpts): InstanceDetailController {
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

	// Detail actions: password and migration remain admin-only.
	let passwordPrecheck = $state<PasswordPrecheck | null>(null);
	let passwordPrecheckLoading = $state(false);
	// Resize is available in both writable user and admin detail modes.
	let resizeFlavors = $state<FlavorOption[]>([]);
	let resizeFlavorsLoading = $state(false);
	let resizeLoading = $state(false);
	let resizeError = $state('');
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
		const generation = ++fetchGeneration;
		const ownsRequest = () => (
			generation === fetchGeneration
			&& opts.instanceId() === id
			&& opts.effectiveProjectId() === requestProjectId
			&& tok() === requestToken
		);

		const instancePromise = api.get<Instance>(`/api/v1/instances/${id}`, requestToken, requestProjectId);
		const fipsPromise = api.get<FloatingIpDetail[]>('/api/v1/networks/floating-ips', requestToken, requestProjectId).catch(() => []);
		const interfacesPromise = api.get<PortInfo[]>(`/api/v1/instances/${id}/interfaces`, requestToken, requestProjectId).catch(() => []);
		const volumesPromise = api.get<VolumeAttachment[]>(`/api/v1/instances/${id}/volumes`, requestToken, requestProjectId).catch(() => []);
		const securityGroupsPromise = api.get<{ ports: PortInfo[]; security_groups: SecurityGroup[] }>(
			`/api/v1/instances/${id}/security-groups`,
			requestToken,
			requestProjectId,
			fetchOpts?.refreshSecurityGroups ? { refresh: true } : undefined,
		);
		const allVolumesPromise = api.get<VolumeInfo[]>('/api/v1/volumes', requestToken, requestProjectId).catch(() => []);
		const networksPromise = api.get<NetworkInfo[]>('/api/v1/networks', requestToken, requestProjectId).catch(() => []);
		const ownerPromise = api.get<{ display: string }>(`/api/v1/instances/${id}/owner`, requestToken, requestProjectId).catch(() => ({ display: '' }));

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
			if (opts.adminMode()) {
				void fetchPasswordPrecheck(id);
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
		if (!instance) return;
		logLoading = true;
		const length = full ? 0 : 200;
		try {
			const data = await api.get<{ output: string }>(
				`/api/v1/instances/${instance.id}/log?length=${length}`,
				tok(),
				ownPid()
			);
			consoleLog = data.output || t('controller.console.noLog');
		} catch {
			consoleLog = t('controller.console.logFailed');
		} finally {
			logLoading = false;
		}
	}

	async function toggleFullLog() {
		logFull = !logFull;
		await loadConsoleLog(logFull);
	}

	async function openConsole() {
		if (!instance || consoleOpening) return;
		const instanceId = instance.id;
		consoleOpening = true;
		consoleOpenError = '';
		consoleOpenMessage = t('controller.console.requestingUrl');
		try {
			const data = await api.get<{ url: string }>(`/api/v1/instances/${instanceId}/console`, tok(), ownPid());
			const url = data.url?.trim();
			if (!url) {
				consoleOpenError = t('controller.console.emptyUrl');
				toast.error(consoleOpenError);
				return;
			}
			consoleOpenMessage = t('controller.console.opening');
			window.open(url, '_blank', 'noopener,noreferrer');
		} catch {
			consoleOpenError = t('controller.console.urlFailed');
			toast.error(consoleOpenError);
		} finally {
			consoleOpening = false;
			consoleOpenMessage = '';
		}
	}

	async function performAction(action: 'start' | 'stop' | 'reboot' | 'shelve' | 'unshelve') {
		if (!instance) return;
		if (!(await confirmDialog(t('controller.action.confirm', { action })))) return;
		actioning = action;
		try {
			await api.post(`/api/v1/instances/${instance.id}/${action}`, {}, tok(), ownPid());
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(t('controller.action.failed', { action, message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function deleteInstance() {
		if (!instance) return;
		const autoDeleteVols = volumes.filter(v => v.delete_on_termination);
		const keepVols = volumes.filter(v => !v.delete_on_termination);
		const lines = [t('controller.delete.confirm', { name: instance.name })];
		if (autoDeleteVols.length) lines.push(t('controller.delete.autoDeleteVolumes', { volumes: autoDeleteVols.map(v => v.name || v.device).join(', ') }));
		if (keepVols.length) lines.push(t('controller.delete.keepVolumes', { volumes: keepVols.map(v => v.name || v.device).join(', ') }));
		if (instance.union_upper_volume_id) lines.push(t('controller.delete.upperVolumeNotice'));
		if (!(await confirmDialog(lines.join('\n')))) return;
		deleting = true;
		try {
			await api.delete(`/api/v1/instances/${instance.id}`, tok(), ownPid());
			opts.onDelete();
		} catch (e) {
			toast.error(t('controller.delete.failed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			deleting = false;
		}
	}

	async function assignFloatingIp(portId: string) {
		if (!instance) return;
		actioning = 'fip-assign-' + portId;
		try {
			await api.post(`/api/v1/instances/${instance.id}/floating-ip?port_id=${portId}`, {}, tok(), ownPid());
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
			await api.post(`/api/v1/networks/floating-ips/${fipId}/disassociate`, {}, tok(), ownPid());
			await api.delete(`/api/v1/networks/floating-ips/${fipId}`, tok(), ownPid());
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
			await api.post(`/api/v1/instances/${instance.id}/volumes`, { volume_id: volumeId }, tok(), ownPid());
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(t('controller.volume.attachFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function createAndAttachVolume(name: string, sizeGb: number) {
		if (!instance) return;
		actioning = 'create-vol';
		try {
			const vol = await api.post<VolumeInfo>('/api/v1/volumes', { name, size_gb: sizeGb }, tok(), ownPid());
			await api.post(`/api/v1/instances/${instance.id}/volumes`, { volume_id: vol.id }, tok(), ownPid());
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
			await api.delete(`/api/v1/instances/${instance.id}/volumes/${volumeId}`, tok(), ownPid());
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
			await api.patch(`/api/v1/instances/${instance.id}/volumes/${volumeId}`, { delete_on_termination: next }, tok(), ownPid());
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
			await api.post(`/api/v1/instances/${instance.id}/interfaces`, { net_id: netId }, tok(), ownPid());
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
			await api.delete(`/api/v1/instances/${instance.id}/interfaces/${portId}`, tok(), ownPid());
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
				`/api/v1/instances/${instance.id}/ports/${portId}/security-groups`,
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
	function canResize() { return get(canWrite); }
	function resizePath(action: 'resize' | 'confirm-resize' | 'revert-resize') {
		return `/api/v1/${opts.adminMode() ? 'admin/' : ''}instances/${instance!.id}/${action}`;
	}
	function resizeProjectId() { return opts.adminMode() ? ownPid() : opts.effectiveProjectId(); }
	function selectableResizeFlavor(flavorId: string) {
		return flavorId !== instance?.flavor_id && resizeFlavors.some(f =>
			f.id === flavorId && (!!instance?.flavor_id || f.name !== instance?.flavor_name) && f.eligibility?.selectable !== false
		);
	}

	async function loadResizeFlavors() {
		if (!instance || !canResize()) return;
		const id = instance.id;
		resizeFlavors = [];
		resizeError = '';
		resizeFlavorsLoading = true;
		try {
			const flavors = await api.get<FlavorOption[]>(
				`/api/v1/instances/${id}/resize-flavors`, tok(), resizeProjectId()
			);
			if (instance?.id === id) resizeFlavors = flavors;
		} catch (e) {
			if (instance?.id === id) resizeError = e instanceof ApiError ? e.message : t('controller.resize.flavorsFailed');
		} finally {
			resizeFlavorsLoading = false;
		}
	}

	async function doResize(flavorId: string): Promise<boolean> {
		if (!instance || !canResize() || !['ACTIVE', 'SHUTOFF'].includes(instance.status) || resizeFlavorsLoading || resizeLoading || !selectableResizeFlavor(flavorId)) return false;
		resizeLoading = true;
		resizeError = '';
		try {
			await api.post(resizePath('resize'), { flavor_id: flavorId }, tok(), resizeProjectId());
			await fetchInstance(instance.id, { silent: true });
			return true;
		} catch (e) {
			resizeError = e instanceof ApiError ? e.message : t('controller.resize.failed');
			return false;
		} finally {
			resizeLoading = false;
		}
	}

	async function revertResize() {
		if (!instance || !canResize() || instance.status !== 'VERIFY_RESIZE') return;
		if (!(await confirmDialog(t('controller.resize.revertConfirm')))) return;
		if (!canResize() || instance.status !== 'VERIFY_RESIZE' || actioning) return;
		actioning = 'revert-resize';
		try {
			await api.post(resizePath('revert-resize'), {}, tok(), resizeProjectId());
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(t('controller.resize.revertFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	async function confirmResize() {
		if (!instance || !canResize() || instance.status !== 'VERIFY_RESIZE') return;
		if (!(await confirmDialog(t('controller.resize.confirm')))) return;
		if (!canResize() || instance.status !== 'VERIFY_RESIZE' || actioning) return;
		actioning = 'confirm-resize';
		try {
			await api.post(resizePath('confirm-resize'), {}, tok(), resizeProjectId());
			await fetchInstance(instance.id, { silent: true });
		} catch (e) {
			toast.error(t('controller.resize.confirmFailed', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			actioning = null;
		}
	}

	// Admin: password precheck
	async function fetchPasswordPrecheck(serverId: string) {
		passwordPrecheckLoading = true;
		try {
			passwordPrecheck = await api.get<PasswordPrecheck>(
				`/api/v1/instances/${serverId}/admin-password/precheck`,
				tok(),
				ownPid()
			);
		} catch {
			passwordPrecheck = null;
		} finally {
			passwordPrecheckLoading = false;
		}
	}

	// Returns error string on failure, null on success
	async function doSetPassword(password: string): Promise<string | null> {
		if (!instance) return t('controller.password.noInstance');
		try {
			await api.post(`/api/v1/instances/${instance.id}/admin-password`, { new_password: password }, tok(), ownPid());
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
		get fixedIpsList() { return fixedIpsList; },
		get floatingIpsList() { return floatingIpsList; },
		get assignedPortIds() { return assignedPortIds; },
		get availableInterfaces() { return availableInterfaces; },
		get passwordPrecheck() { return passwordPrecheck; },
		get passwordPrecheckLoading() { return passwordPrecheckLoading; },
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
	readonly fixedIpsList: Instance['ip_addresses'];
	readonly floatingIpsList: Instance['ip_addresses'];
	readonly assignedPortIds: Set<string>;
	readonly availableInterfaces: PortInfo[];
	readonly passwordPrecheck: PasswordPrecheck | null;
	readonly passwordPrecheckLoading: boolean;
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
