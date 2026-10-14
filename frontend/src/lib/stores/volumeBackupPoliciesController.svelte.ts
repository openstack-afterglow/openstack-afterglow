import { untrack } from 'svelte';
import { derived, get } from 'svelte/store';
import { auth, canWrite, projectSwitching } from '$lib/stores/auth';
import { api, ApiError } from '$lib/api/client';
import { t } from '$lib/i18n/ns/volume';
import type { Volume } from '$lib/types/volume';
import type { VolumeBackupPolicy, VolumeBackupPolicyInput } from '$lib/types/volumeBackupPolicy';
import { policyInput } from '$lib/types/volumeBackupPolicy';
import { confirmDialog } from '$lib/stores/confirm.svelte';

const base = '/api/v1/volumes/backups/auto-backup';

export interface VolumeBackupPoliciesController {
	readonly policies: VolumeBackupPolicy[];
	readonly volumes: Volume[];
	readonly loading: boolean;
	readonly error: string;
	readonly volumesError: string;
	readonly mutationError: string;
	readonly busy: boolean;
	readonly generation: number;
	readonly editor: string | null;
	readonly resuming: boolean;
	refresh(): Promise<void>;
	open(volumeId?: string): void;
	close(): void;
	save(volumeId: string, input: VolumeBackupPolicyInput): Promise<true | string>;
	setEnabled(policy: VolumeBackupPolicy, enabled: boolean): Promise<void>;
	remove(policy: VolumeBackupPolicy): Promise<void>;
}

interface PolicyRequestScope {
	token: string | null;
	projectId: string | null;
	userId: string | null;
	generation: number;
}

export function createVolumeBackupPoliciesController(): VolumeBackupPoliciesController {
	let policies = $state<VolumeBackupPolicy[]>([]);
	let volumes = $state<Volume[]>([]);
	let loading = $state(false);
	let error = $state('');
	let volumesError = $state('');
	let mutationError = $state('');
	let busy = $state(false);
	let editor = $state<string | null>(null);
	let resuming = $state(false);
	let generation = $state(0);
	let loadSequence = 0;

	function scope(): PolicyRequestScope {
		const { token, projectId, userId } = get(auth);
		return { token, projectId, userId, generation };
	}
	function current(s: PolicyRequestScope) {
		const now = get(auth);
		return !get(projectSwitching) && s.generation === generation && s.token === now.token && s.projectId === now.projectId && s.userId === now.userId;
	}

	async function refresh() {
		const s = scope();
		if (!s.token || !s.projectId || get(projectSwitching) || busy) return;
		const sequence = ++loadSequence;
		loading = true;
		await Promise.all([
			api.post<VolumeBackupPolicy[]>(`${base}/configs`, {}, s.token, s.projectId).then((rows) => {
				if (!current(s) || sequence !== loadSequence) return;
				if (rows.some((row) => row.project_id !== s.projectId)) throw new Error('Policy scope mismatch');
				policies = rows;
				error = '';
			}).catch(() => {
				if (current(s) && sequence === loadSequence) error = t('autoPolicy.loadFailed');
			}),
			api.get<Volume[]>('/api/v1/volumes', s.token, s.projectId).then((rows) => {
				if (!current(s) || sequence !== loadSequence) return;
				volumes = rows;
				volumesError = '';
			}).catch(() => {
				if (current(s) && sequence === loadSequence) volumesError = t('autoPolicy.volumesFailed');
			}),
		]);
		if (current(s) && sequence === loadSequence) loading = false;
	}

	$effect(() => {
		let previous = '';
		return derived([auth, projectSwitching, canWrite], ([value, switching, writable]) => ({ value, switching, writable })).subscribe(({ value, switching, writable }) => {
			const key = JSON.stringify([value.token, value.projectId, value.userId, switching, writable]);
			if (key === previous) return;
			previous = key;
			untrack(() => {
				generation++;
				loadSequence++;
				policies = []; volumes = []; error = ''; volumesError = ''; mutationError = '';
				busy = false; editor = null; loading = Boolean(value.projectId && value.token);
				if (value.projectId && value.token && !switching) void refresh();
			});
		});
	});

	function open(volumeId = '') {
		const s = scope();
		if (!s.token || !s.projectId || !current(s) || !get(canWrite) || loading || error || volumesError || busy) return;
		editor = volumeId;
		resuming = false;
		mutationError = '';
	}

	async function save(volumeId: string, input: VolumeBackupPolicyInput): Promise<true | string> {
		const s = scope();
		if (!s.token || !s.projectId || !current(s) || !get(canWrite) || busy || loading || error || volumesError) return t('autoPolicy.saveFailed');
		busy = true;
		mutationError = '';
		try {
			const saved = await api.post<VolumeBackupPolicy>(`${base}/${encodeURIComponent(volumeId)}`, input, s.token, s.projectId);
			if (!current(s) || !get(canWrite)) return t('autoPolicy.saveFailed');
			if (saved.project_id !== s.projectId || saved.volume_id !== volumeId) throw new Error('Policy scope mismatch');
			policies = [...policies.filter((row) => row.volume_id !== volumeId), saved];
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : t('autoPolicy.saveFailed');
		} finally {
			if (current(s)) busy = false;
		}
	}

	async function setEnabled(policy: VolumeBackupPolicy, enabled: boolean) {
		const s = scope();
		const volume = volumes.find((row) => row.id === policy.volume_id);
		if (enabled && volume?.status === 'in-use' && !policy.force) { open(policy.volume_id); resuming = editor === policy.volume_id; return; }
		const result = await save(policy.volume_id, { ...policyInput(policy), enabled });
		if (current(s) && result !== true) mutationError = result;
	}

	async function remove(policy: VolumeBackupPolicy) {
		const s = scope();
		if (!s.token || !s.projectId || !current(s) || !get(canWrite) || busy || loading || error) return;
		const name = volumes.find((row) => row.id === policy.volume_id)?.name || policy.volume_id;
		if (!await confirmDialog(t('autoPolicy.removeConfirm', { name }))) return;
		if (!current(s) || !get(canWrite) || busy || loading || error) return;
		busy = true; mutationError = '';
		try {
			await api.delete(`${base}/${encodeURIComponent(policy.volume_id)}`, s.token ?? undefined, s.projectId ?? undefined);
			if (current(s) && get(canWrite)) policies = policies.filter((row) => row.volume_id !== policy.volume_id);
		} catch (e) {
			if (current(s)) mutationError = e instanceof ApiError ? e.message : t('autoPolicy.removeFailed');
		} finally { if (current(s)) busy = false; }
	}

	return {
		get policies() { return policies; }, get volumes() { return volumes; },
		get loading() { return loading; }, get error() { return error; }, get volumesError() { return volumesError; },
		get mutationError() { return mutationError; }, get busy() { return busy; }, get generation() { return generation; },
		get resuming() { return resuming; },
		get editor() { return editor; }, close() { editor = null; }, refresh, open, save, setEnabled, remove,
	};
}
