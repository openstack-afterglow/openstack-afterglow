import { browser } from '$app/environment';
import { derived, get } from 'svelte/store';
import { api, ApiError } from '$lib/api/client';
import { auth, authReady, logoutInProgress, projectSwitching, setAuth } from './auth';
import type { AvailableDomain, CreatedDomain, SessionTokenResponse } from '$lib/types/auth';
import { domainAuthState, sessionScopeKey } from '$lib/utils/authSession';
import { cloudShell } from './cloudShell.svelte';
import { emptyWorkspacePreferences, readWorkspacePreferences, saveWorkspacePreferences, workspacePreferenceKey, type ResourceKind, type ResourcePreference } from './workspacePreferences';

export interface WorkspaceProject { id: string; name: string; description?: string; domain_id?: string }
export interface WorkspaceInventory {
	domain: AvailableDomain; projects: WorkspaceProject[]; default_project_id: string;
	is_domain_manager: boolean; can_create_project: boolean;
}
const mutationOptions = { replayOnUnauthorized: false, suppressAuthRedirect: true, cache: 'no-store' as const };
interface WorkspaceRequest { generation: number; owner: string }

const DIRECTORY_TTL_MS = 30_000;
const MAX_WORKSPACE_SNAPSHOTS = 16;
let snapshotOwner = '';
let directorySnapshot: { rows: AvailableDomain[]; expiresAt: number } | null = null;
const workspaceSnapshots = new Map<string, { inventory: WorkspaceInventory; expiresAt: number }>();
function clearSnapshots() { directorySnapshot = null; workspaceSnapshots.clear(); }
export function invalidateWorkspaceDisplaySnapshots(): void { clearSnapshots(); }
// Display-only snapshots never replace the native checks on a scope commit or create.
if (browser) derived([auth, authReady, logoutInProgress, projectSwitching], ([state, verified, loggingOut, switching]) =>
	state.token && verified && !loggingOut && !switching
		? JSON.stringify([sessionScopeKey(state), state.isSystemAdmin, state.isDomainManager, state.canCreateDomain, state.canWrite, (state.availableDomains ?? []).map(row => [row.id, row.name, row.kind]).sort()])
		: ''
).subscribe(owner => {
	if (owner !== snapshotOwner) { clearSnapshots(); snapshotOwner = owner; }
});

/** One mounted browser owns its requests; synchronous subscriptions fence even same-tick ABA. */
export function createWorkspaceController(onSelected: () => void) {
	let domains = $state<AvailableDomain[]>([]);
	let inventory = $state<WorkspaceInventory | null>(null);
	let domainId = $state('');
	let loading = $state(false);
	let ready = $state(false);
	let busy = $state(false);
	let error = $state<'loadFailed' | 'switchFailed' | 'createRejected' | 'createUncertain' | ''>('');
	let uncertain = $state(false);
	let preferences = $state(emptyWorkspacePreferences());
	let storageFailed = $state(false);
	let mounted = false;
	let generation = 0;
	let browseSequence = 0;
	let ownsSwitch = false;
	let reads: AbortController | null = null;
	// Mounted request ownership remains independent from the short display cache.
	let directoryValid = false;
	let activeRead: { target: string; recheckDirectory: boolean; settlesUncertain: boolean; promise: Promise<void> } | null = null;
	let mutation: AbortController | null = null;
	let preferenceKey = '';

	function capture(): WorkspaceRequest { return { generation, owner: sessionScopeKey(get(auth)) }; }
	function current(request: WorkspaceRequest) {
		const state = get(auth);
		return mounted && request.generation === generation && request.owner === sessionScopeKey(state)
			&& get(authReady) && !get(logoutInProgress) && !!state.token && (!get(projectSwitching) || ownsSwitch);
	}
	function invalidate() {
		generation++; browseSequence++; reads?.abort(); mutation?.abort();
		activeRead = null; directoryValid = false;
		domains = []; inventory = null; domainId = ''; ready = false; loading = false; busy = false;
		error = ''; uncertain = false; preferences = emptyWorkspacePreferences(); preferenceKey = ''; storageFailed = false;
	}
	function mount() {
		mounted = true;
		let previous = '';
		const unsubscribe = derived([auth, authReady, logoutInProgress, projectSwitching], ([state, verified, loggingOut, switching]) => ({ state, verified, loggingOut, switching })).subscribe(({ state, verified, loggingOut, switching }) => {
			const key = JSON.stringify([sessionScopeKey(state), !!state.token, verified, loggingOut, switching && !ownsSwitch, state.isSystemAdmin, state.isDomainManager, state.canWrite, (state.availableDomains ?? []).map(row => [row.id, row.name, row.kind]).sort(), state.canCreateDomain === true]);
			if (key === previous) return;
			previous = key;
			invalidate();
			if (state.token && state.userId && state.identityDomainId && verified && !loggingOut && (!switching || ownsSwitch)) {
				preferenceKey = workspacePreferenceKey(state.identityDomainId, state.userId);
				preferences = readWorkspacePreferences(preferenceKey);
				void load(state.domainId || '', !directorySnapshot || directorySnapshot.expiresAt <= Date.now());
			}
		});
		return () => { mounted = false; unsubscribe(); invalidate(); };
	}
	// Start from the active server-selected workspace, never the identity home or a display preference.
	function refresh(target = domainId || get(auth).domainId || ''): Promise<void> {
		if (!mounted || busy || !get(authReady) || get(logoutInProgress) || !get(auth).token || get(projectSwitching)) return Promise.resolve();
		if (activeRead?.target === target && activeRead.recheckDirectory) { activeRead.settlesUncertain = true; return activeRead.promise; }
		clearSnapshots();
		return load(target, true, true);
	}
	function selectDomain(target: string): Promise<void> {
		if (activeRead?.target === target) return activeRead.promise;
		if (!directoryValid || !domains.some(row => row.id === target)) return Promise.resolve();
		return load(target, !directorySnapshot || directorySnapshot.expiresAt <= Date.now());
	}
	function load(target: string, recheckDirectory: boolean, settlesUncertain = false): Promise<void> {
		if (!mounted || busy || !get(authReady) || get(logoutInProgress) || !get(auth).token || get(projectSwitching)) return Promise.resolve();
		if (activeRead?.target === target && (activeRead.recheckDirectory || !recheckDirectory)) { activeRead.settlesUncertain ||= settlesUncertain; return activeRead.promise; }
		reads?.abort(); reads = new AbortController();
		const request = capture(); const sequence = ++browseSequence; const signal = reads.signal;
		const token = get(auth).token!;
		const owner = snapshotOwner;
		const valid = () => current(request) && owner === snapshotOwner && sequence === browseSequence && !signal.aborted;
		loading = true; ready = false; inventory = null; domainId = target; error = '';
		if (recheckDirectory) { domains = []; directoryValid = false; }
		// Handle speculative failures immediately, including when the directory rejects or chooses a fallback.
		const workspace = (selected: string) => {
			const cached = workspaceSnapshots.get(selected);
			if (!recheckDirectory && cached && cached.expiresAt > Date.now()) return Promise.resolve({ ok: true as const, result: structuredClone(cached.inventory) });
			return api.get<WorkspaceInventory>(`/api/v1/auth/workspaces?domain_id=${encodeURIComponent(selected)}`, token, undefined, { refresh: true, suppressAuthRedirect: true, signal })
				.then(result => ({ ok: true as const, result }), () => ({ ok: false as const }));
		};
		async function run() {
			try {
				const directory = recheckDirectory ? api.get<AvailableDomain[]>('/api/v1/auth/domains', token, undefined, { refresh: true, suppressAuthRedirect: true, signal }) : null;
				const pending = target ? workspace(target) : null;
				const rows = directory ? await directory : directorySnapshot && directorySnapshot.expiresAt > Date.now() ? structuredClone(directorySnapshot.rows) : domains;
				if (!valid()) return;
				if (!Array.isArray(rows) || rows.some(row => !row || typeof row.id !== 'string' || !row.id || typeof row.name !== 'string' || (row.kind !== undefined && !['personal', 'organization', 'legacy'].includes(row.kind))) || new Set(rows.map(row => row.id)).size !== rows.length) throw new Error('Invalid domain directory');
				domains = rows; directoryValid = true;
				if (recheckDirectory) directorySnapshot = { rows: structuredClone(rows), expiresAt: Date.now() + DIRECTORY_TTL_MS };
				const selected = rows.some(row => row.id === target) ? target : rows[0]?.id ?? '';
				domainId = selected;
				if (recheckDirectory && activeRead) activeRead.target = selected;
				if (!selected) { ready = true; if (settlesUncertain || activeRead?.settlesUncertain) uncertain = false; return; }
				const response = await (selected === target && pending ? pending : workspace(selected));
				if (!valid() || domainId !== selected) return;
				if (!response.ok) throw new Error('Workspace unavailable');
				const result = response.result;
				if (!result || result.domain?.id !== selected || typeof result.domain.name !== 'string' || (result.domain.kind !== undefined && !['personal', 'organization', 'legacy'].includes(result.domain.kind)) || !Array.isArray(result.projects)
					|| result.projects.some(row => !row || typeof row.id !== 'string' || !row.id || typeof row.name !== 'string' || (row.domain_id && row.domain_id !== selected))
					|| new Set(result.projects.map(row => row.id)).size !== result.projects.length
					|| typeof result.can_create_project !== 'boolean' || typeof result.is_domain_manager !== 'boolean') throw new Error('Invalid workspace directory');
				inventory = result; ready = true;
				if (recheckDirectory || !workspaceSnapshots.has(selected) || workspaceSnapshots.get(selected)!.expiresAt <= Date.now()) {
					workspaceSnapshots.delete(selected);
					workspaceSnapshots.set(selected, { inventory: structuredClone(result), expiresAt: Date.now() + DIRECTORY_TTL_MS });
					if (workspaceSnapshots.size > MAX_WORKSPACE_SNAPSHOTS) workspaceSnapshots.delete(workspaceSnapshots.keys().next().value!);
				}
				if (settlesUncertain || activeRead?.settlesUncertain) uncertain = false;
			} catch {
				if (valid()) { clearSnapshots(); error = 'loadFailed'; inventory = null; ready = false; reads?.abort(); }
			} finally {
				if (current(request) && sequence === browseSequence) { loading = false; activeRead = null; }
			}
		}
		const promise = run();
		if (loading) activeRead = { target, recheckDirectory, settlesUncertain, promise };
		return promise;
	}
	function preference(kind: ResourceKind, id: string, change: ResourcePreference) {
		if (!ready || loading || busy || !preferenceKey || !(kind === 'domains' ? domains : inventory?.projects ?? []).some(row => row.id === id)) return;
		preferences = { ...preferences, [kind]: { ...preferences[kind], [id]: { ...preferences[kind][id], ...change } } };
		storageFailed = !saveWorkspacePreferences(preferenceKey, preferences);
	}
	function reorder(kind: ResourceKind, rows: { id: string }[], index: number, step: number) {
		if (!ready || loading || busy || !preferenceKey || index + step < 0 || index + step >= rows.length) return;
		const allowed = new Set((kind === 'domains' ? domains : inventory?.projects ?? []).map(row => row.id));
		if (rows.some(row => !allowed.has(row.id))) return;
		const ordered = [...rows]; [ordered[index], ordered[index + step]] = [ordered[index + step], ordered[index]];
		const next = { ...preferences[kind] };
		ordered.forEach((row, order) => { next[row.id] = { ...next[row.id], order }; });
		preferences = { ...preferences, [kind]: next }; storageFailed = !saveWorkspacePreferences(preferenceKey, preferences);
	}
	async function select(projectId: string | null) {
		const target = domainId; const directory = inventory;
		if (!ready || loading || busy || !directory || get(projectSwitching) || !get(auth).token || !domains.some(row => row.id === target)
			|| (projectId === null && directory.domain.kind === 'personal') || (projectId !== null && !directory.projects.some(row => row.id === projectId))) return;
		if (target === get(auth).domainId && projectId === get(auth).projectId) { onSelected(); return; }
		const request = capture(); const savedKey = preferenceKey;
		mutation = new AbortController(); const signal = mutation.signal;
		busy = true; ownsSwitch = true; projectSwitching.set(true); error = '';
		try {
			await cloudShell.close('project-switch', { keepDock: false });
			if (!current(request) || signal.aborted || domainId !== target) return;
			const response = await api.post<SessionTokenResponse>(projectId === null ? '/api/v1/auth/token/domain' : '/api/v1/auth/token/workspace', { domain_id: target, ...(projectId === null ? {} : { project_id: projectId }) }, get(auth).token!, undefined, { ...mutationOptions, signal });
			if (!current(request) || signal.aborted || domainId !== target) return;
			// Synchronize the mapper's membership snapshot without publishing an intermediate session.
			const next = domainAuthState(response, { ...get(auth), availableDomains: domains }, target);
			if (projectId !== null && next.projectId !== projectId) throw new Error('Unexpected project scope');
			const visited = Date.now();
			const nextPreferences = { ...preferences, domains: { ...preferences.domains, [target]: { ...preferences.domains[target], visited } }, projects: { ...preferences.projects } };
			if (next.projectId) nextPreferences.projects[next.projectId] = { ...nextPreferences.projects[next.projectId], visited };
			saveWorkspacePreferences(savedKey, nextPreferences);
			setAuth(next);
			onSelected();
		} catch { if (current(request) && !signal.aborted) error = 'switchFailed'; }
		finally { busy = false; ownsSwitch = false; projectSwitching.set(false); }
	}
	async function createDomain(name: string, description: string): Promise<boolean> {
		if (!ready || loading || busy || uncertain || !get(auth).canCreateDomain || !get(auth).token || get(projectSwitching)) return false;
		const request = capture(); mutation = new AbortController(); const signal = mutation.signal;
		busy = true; error = '';
		try {
			const row = await api.post<CreatedDomain>('/api/v1/auth/domains', { name: name.trim(), ...(description.trim() ? { description: description.trim() } : {}) }, get(auth).token!, undefined, { ...mutationOptions, signal });
			if (!current(request) || signal.aborted || !get(auth).canCreateDomain) return false;
			if (!row?.id || typeof row.name !== 'string' || row.enabled !== true || !row.default_project_id) throw new Error('Invalid created domain');
			busy = false;
			await refresh(row.id);
			return current(request) && ready;
		} catch (cause) {
			if (current(request) && !signal.aborted) { uncertain = !(cause instanceof ApiError && cause.status >= 400 && cause.status < 500 && cause.status !== 408); error = uncertain ? 'createUncertain' : 'createRejected'; }
			return false;
		} finally { if (current(request)) busy = false; }
	}
	return {
		get domains() { return domains; }, get inventory() { return inventory; }, get domainId() { return domainId; },
		get loading() { return loading; }, get ready() { return ready; }, get busy() { return busy; }, get error() { return error; },
		get uncertain() { return uncertain; }, get preferences() { return preferences; }, get storageFailed() { return storageFailed; },
		mount, refresh, selectDomain, select, createDomain, preference, reorder,
	};
}
