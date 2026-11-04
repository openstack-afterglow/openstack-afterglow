import { get } from 'svelte/store';
import { api, getBaseUrl } from '$lib/api/client';
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { siteConfig } from '$lib/config/site';
import { createPrivateViewScope } from '$lib/utils/privateViewScope';
import { createK3sProgress, type K3sProgressController } from './k3sProgress.svelte';
import { observedProjectPermissions } from './servicePermissions';

const STORAGE = 'afterglow_drover_operations_v1';
interface Entry { id: string; owner: string; name: string; progress: K3sProgressController; streaming: boolean; epoch: number; needsReadback: boolean; }
interface Operation { id: string; project_id: string; cluster_id: string; kind: string; status: string; error?: string; }
interface Event { operation_id: string; sequence: number; phase: string; message?: string; payload_json?: { step?: string; progress?: number; error?: string }; }

function ownerKey() {
	const state = get(auth);
	return JSON.stringify([getBaseUrl(), state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId,
		state.isSystemAdmin, state.isDomainManager, state.canWrite, [...state.roles].sort()]);
}
function available() {
	const authority = get(observedProjectPermissions);
	const denied = !authority.loading && !authority.error && authority.permissions
		&& !authority.permissions.service_permission_errors?.drover
		&& !Object.values(authority.permissions.service_permissions).flat().includes('drover-inventory_reader');
	return !!get(auth).token && get(authReady) && !get(projectSwitching) && !get(logoutInProgress) && !denied;
}

export function createK3sOperations() {
	let entries = $state.raw<Entry[]>([]);
	let epoch = 0;
	let restored = false;
	let polling = false;
	let timer: ReturnType<typeof setInterval> | undefined;
	let subscriptions: (() => void)[] = [];
	function save() {
		if (typeof sessionStorage === 'undefined') return;
		try {
			sessionStorage.setItem(STORAGE, JSON.stringify(entries.map(entry => {
				const p = entry.progress;
				return { id: entry.id, owner: entry.owner, name: entry.name, mode: p.mode, step: p.step, pct: Number.isFinite(p.pct) ? p.pct : null,
					clusterId: p.createdClusterId, operationId: p.operationId, sequence: p.sequence, elapsed: p.elapsedSeconds, timings: p.stepTimings, refusalSummary: p.refusalSummary };
			})));
		} catch { /* Observation remains available in memory when tab storage is disabled. */ }
	}
	function restore() {
		if (restored || typeof sessionStorage === 'undefined') return;
		restored = true;
		try {
			const saved: unknown = JSON.parse(sessionStorage.getItem(STORAGE) ?? '[]');
			if (!Array.isArray(saved)) return;
			for (const value of saved) {
				if (!value || typeof value.id !== 'string' || typeof value.owner !== 'string' || typeof value.name !== 'string'
					|| !['create', 'delete'].includes(value.mode) || typeof value.step !== 'string'
					|| (value.operationId !== null && typeof value.operationId !== 'string')) continue;
				const progress = createK3sProgress();
				progress.restore({ ...value, sequence: Number.isFinite(value.sequence) ? value.sequence : 0,
					elapsed: Number.isFinite(value.elapsed) ? value.elapsed : 0, timings: value.timings && typeof value.timings === 'object' ? value.timings : {} });
				progress.setObserver(save);
				entries = [...entries, { id: value.id, owner: value.owner, name: value.name, progress, streaming: false, epoch, needsReadback: progress.isTerminal && !!progress.operationId }];
			}
		} catch { /* Invalid tab metadata cannot authorize an operation or replay a write. */ }
	}
	function current(entry: Entry, capturedEpoch = epoch) {
		return available() && entry.owner === ownerKey() && capturedEpoch === epoch && entries.includes(entry);
	}
	async function poll() {
		if (polling || !available()) return;
		polling = true;
		const capturedEpoch = epoch;
		try {
			for (const entry of entries) {
				const p = entry.progress;
				if (!current(entry, capturedEpoch) || entry.streaming || (p.isTerminal && !entry.needsReadback) || !p.operationId) continue;
				const operationId = p.operationId;
				const token = get(auth).token!;
				const project = get(auth).projectId!;
				try {
					const path = `/api/v1/k3s/operations/${encodeURIComponent(operationId)}`;
					const operation = await api.get<Operation>(path, token, project, { refresh: true });
					if (!current(entry, capturedEpoch)) continue;
					if (operation.id !== operationId || operation.project_id !== project || operation.kind !== p.mode
						|| (p.createdClusterId && operation.cluster_id !== p.createdClusterId)) { p.disconnect(); continue; }
					let events: Event[] = [];
					try { events = await api.get<Event[]>(`${path}/events?since_sequence=${p.sequence}`, get(auth).token!, project, { refresh: true }); }
					catch (e) { if (!['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(operation.status)) throw e; }
					if (!current(entry, capturedEpoch)) continue;
					for (const event of events) {
						if (event.operation_id !== operationId || !Number.isFinite(event.sequence)) continue;
						const data = event.payload_json ?? {};
						const stage = data.step ?? event.phase;
						// Terminal authority belongs to the operation snapshot, not an out-of-order event.
						if (['completed', 'failed', 'cancelled'].includes(stage)) continue;
						p.apply({ step: stage, progress: data.progress ?? NaN, message: event.message ?? '', cluster_id: operation.cluster_id,
							operation_id: operationId, sequence: event.sequence });
					}
					if (['QUEUED', 'RUNNING', 'WAITING_CALLBACK'].includes(operation.status)) p.confirmRunning();
					if (operation.status === 'SUCCEEDED') p.apply({ step: 'completed', progress: 100, message: '', cluster_id: operation.cluster_id });
					else if (operation.status === 'FAILED' || operation.status === 'CANCELLED') p.failWith(operation.error || operation.status);
					if (['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(operation.status)) entry.needsReadback = false;
				} catch (e) { if (current(entry, capturedEpoch)) p.disconnect(e instanceof Error ? e.message : String(e)); }
			}
		} finally { polling = false; }
	}
	return {
		get entries() { return available() ? entries.filter(entry => entry.owner === ownerKey()) : []; },
		track(progress: K3sProgressController, name: string) {
			const entry: Entry = { id: crypto.randomUUID(), owner: ownerKey(), name, progress, streaming: true, epoch, needsReadback: false };
			entries = [...entries, entry]; progress.setObserver(save); save(); return true;
		},
		owns(progress: K3sProgressController) { return entries.some(entry => entry.progress === progress && entry.epoch === epoch && current(entry)); },
		handoff(progress: K3sProgressController) {
			const entry = entries.find(entry => entry.progress === progress);
			if (!entry) return;
			entry.streaming = false;
			if (!progress.isTerminal) progress.disconnect();
			save(); void poll();
		},
		dismiss(id: string) { entries = entries.filter(entry => entry.id !== id || !entry.progress.isTerminal); save(); },
		refresh: poll,
		mount() {
			if (timer) return () => {};
			restore();
			const scope = createPrivateViewScope();
			let first = true;
			subscriptions.push(scope.subscribe(() => {
				if (first) { first = false; return; }
				epoch++;
				for (const entry of entries) { entry.streaming = false; entry.progress.visible = false; entry.progress.disconnect(); }
			}));
			subscriptions.push(auth.subscribe(state => {
				if (!state.token) { epoch++; for (const entry of entries) entry.progress.end(); entries = []; save(); }
			}));
			subscriptions.push(authReady.subscribe(ready => { if (ready) void poll(); }));
			let initialBase = getBaseUrl();
			subscriptions.push(siteConfig.subscribe(() => {
				const base = getBaseUrl();
				if (base === initialBase) return;
				initialBase = base; epoch++;
				for (const entry of entries) { entry.streaming = false; entry.progress.visible = false; entry.progress.disconnect(); }
			}));
			timer = setInterval(() => { void poll(); }, 5000);
			void poll();
			return () => { clearInterval(timer); timer = undefined; subscriptions.forEach(stop => stop()); subscriptions = []; };
		},
	};
}
export const k3sOperations = createK3sOperations();
