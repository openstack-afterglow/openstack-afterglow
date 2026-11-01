import { browser } from '$app/environment';
import { derived, get } from 'svelte/store';
import { api, ApiError, getBaseUrl } from '$lib/api/client';
import { siteConfig } from '$lib/config/site';
import { auth, authReady, logoutInProgress, projectSwitching, setAuth, type AuthState } from './auth';
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
const DISPLAY_RETENTION_MS = 120_000;
const MAX_WORKSPACE_SNAPSHOTS = 16;
const SNAPSHOT_STORAGE_KEY = 'afterglow_workspace_display_v1';
const MAX_SNAPSHOT_BYTES = 512_000;
type DirectorySnapshot = { rows: AvailableDomain[]; expiresAt: number };
type InventorySnapshot = { inventory: WorkspaceInventory; expiresAt: number };
let snapshotOwner = '';
let snapshotEpoch = 0;
let directorySnapshot: DirectorySnapshot | null = null;
const workspaceSnapshots = new Map<string, InventorySnapshot>();
function clearSnapshots() {
	directorySnapshot = null; workspaceSnapshots.clear(); snapshotEpoch++;
	try { sessionStorage.removeItem(SNAPSHOT_STORAGE_KEY); } catch { /* memory-only display cache */ }
}
export function invalidateWorkspaceDisplaySnapshots(): void { clearSnapshots(); }
function displayOwner(state: AuthState, baseUrl = getBaseUrl()): string {
	return state.token && state.userId && state.identityDomainId
		? JSON.stringify([baseUrl, sessionScopeKey(state), state.isSystemAdmin, state.isDomainManager, state.canCreateDomain, state.canWrite, state.federated, [...(state.roles ?? [])].sort(), (state.availableDomains ?? []).map(row => [row.id, row.name, row.kind]).sort()]) : '';
}
function validDomain(row: AvailableDomain): boolean {
	return !!row && typeof row.id === 'string' && !!row.id && typeof row.name === 'string' && (row.kind === undefined || ['personal', 'organization', 'legacy'].includes(row.kind));
}
function validDomains(rows: AvailableDomain[]): boolean {
	return Array.isArray(rows) && rows.every(validDomain) && new Set(rows.map(row => row.id)).size === rows.length;
}
function validInventory(result: WorkspaceInventory, selected: string): boolean {
	return !!result && validDomain(result.domain) && result.domain.id === selected && Array.isArray(result.projects)
		&& result.projects.every(row => !!row && typeof row.id === 'string' && !!row.id && typeof row.name === 'string' && (row.description === undefined || typeof row.description === 'string') && (!row.domain_id || row.domain_id === selected))
		&& new Set(result.projects.map(row => row.id)).size === result.projects.length && typeof result.default_project_id === 'string'
		&& typeof result.can_create_project === 'boolean' && typeof result.is_domain_manager === 'boolean';
}
function retained(expiresAt: number): boolean {
	return Number.isFinite(expiresAt) && expiresAt <= Date.now() + DIRECTORY_TTL_MS && expiresAt + DISPLAY_RETENTION_MS - DIRECTORY_TTL_MS > Date.now();
}
function displayDomain(row: AvailableDomain): AvailableDomain { return { id: row.id, name: row.name, ...(row.kind ? { kind: row.kind } : {}) }; }
function displayInventory(row: WorkspaceInventory): WorkspaceInventory {
	return { domain: displayDomain(row.domain), projects: row.projects.map(project => ({ id: project.id, name: project.name, ...(project.description === undefined ? {} : { description: project.description }), ...(project.domain_id ? { domain_id: project.domain_id } : {}) })), default_project_id: row.default_project_id, can_create_project: row.can_create_project, is_domain_manager: row.is_domain_manager };
}
function persistSnapshots() {
	if (!browser || !snapshotOwner || !get(auth).sessionId) return;
	try {
		const raw = JSON.stringify({ owner: snapshotOwner, directory: directorySnapshot, workspaces: [...workspaceSnapshots].filter(([, entry]) => retained(entry.expiresAt)) });
		if (raw.length <= MAX_SNAPSHOT_BYTES) sessionStorage.setItem(SNAPSHOT_STORAGE_KEY, raw);
		else sessionStorage.removeItem(SNAPSHOT_STORAGE_KEY);
	} catch { /* unavailable/full storage does not prevent browsing */ }
}
function restoreSnapshots(owner: string) {
	if (!get(auth).sessionId) { clearSnapshots(); return; }
	try {
		const raw = sessionStorage.getItem(SNAPSHOT_STORAGE_KEY);
		if (!raw) return;
		if (raw.length > MAX_SNAPSHOT_BYTES) throw new Error('Oversized display cache');
		const saved = JSON.parse(raw);
		if (saved.owner !== owner || !saved.directory || !retained(saved.directory.expiresAt) || !validDomains(saved.directory.rows) || !Array.isArray(saved.workspaces) || saved.workspaces.length > MAX_WORKSPACE_SNAPSHOTS) throw new Error('Invalid display cache');
		const restored = new Map<string, InventorySnapshot>();
		for (const entry of saved.workspaces) {
			if (!Array.isArray(entry) || entry.length !== 2 || typeof entry[0] !== 'string' || !entry[1] || !retained(entry[1].expiresAt) || !validInventory(entry[1].inventory, entry[0]) || !saved.directory.rows.some((row: AvailableDomain) => row.id === entry[0]) || restored.has(entry[0])) throw new Error('Invalid workspace cache');
			restored.set(entry[0], { inventory: displayInventory(entry[1].inventory), expiresAt: entry[1].expiresAt });
		}
		directorySnapshot = { rows: saved.directory.rows.map(displayDomain), expiresAt: saved.directory.expiresAt };
		for (const [id, entry] of restored) workspaceSnapshots.set(id, entry);
	} catch { clearSnapshots(); }
}
// Only the initial reload may retain storage while /me verifies the restored login.
// Every later readiness/owner boundary purges synchronously, including same-tick ABA.
let observedOwner = false;
let bootstrapOwner = '';
if (browser) derived([auth, authReady, logoutInProgress, projectSwitching, siteConfig], ([state, verified, loggingOut, switching]) => ({ owner: displayOwner(state), authority: displayOwner(state, ''), allowed: verified && !loggingOut && !switching, boundary: loggingOut || switching })).subscribe(({ owner, authority, allowed, boundary }) => {
	if (!observedOwner) {
		observedOwner = true;
		if (owner && !allowed && !boundary) { bootstrapOwner = authority; return; }
		if (owner && allowed) { snapshotOwner = owner; restoreSnapshots(owner); return; }
		clearSnapshots();
	}
	if (bootstrapOwner && authority === bootstrapOwner && !boundary && !allowed) return;
	if (bootstrapOwner && authority === bootstrapOwner && allowed) {
		bootstrapOwner = ''; snapshotOwner = owner; restoreSnapshots(owner); return;
	}
	if (bootstrapOwner) clearSnapshots();
	bootstrapOwner = '';
	const next = allowed ? owner : '';
	if (next !== snapshotOwner) { clearSnapshots(); snapshotOwner = next; }
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
	let activeRead: { target: string; recheckDirectory: boolean; forceRefresh: boolean; settlesUncertain: boolean; promise: Promise<void> } | null = null;
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
		const unsubscribe = derived([auth, authReady, logoutInProgress, projectSwitching, siteConfig], ([state, verified, loggingOut, switching]) => ({ state, verified, loggingOut, switching })).subscribe(({ state, verified, loggingOut, switching }) => {
			const key = JSON.stringify([displayOwner(state), !!state.token, verified, loggingOut, switching && !ownsSwitch]);
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
		if (activeRead?.target === target && activeRead.forceRefresh) { activeRead.settlesUncertain = true; return activeRead.promise; }
		clearSnapshots();
		return load(target, true, true, true);
	}
	function selectDomain(target: string): Promise<void> {
		if (activeRead?.target === target) return activeRead.promise;
		if (!directoryValid || !domains.some(row => row.id === target)) return Promise.resolve();
		return load(target, !directorySnapshot || directorySnapshot.expiresAt <= Date.now());
	}
	function load(target: string, recheckDirectory: boolean, settlesUncertain = false, forceRefresh = false): Promise<void> {
		if (!mounted || busy || !get(authReady) || get(logoutInProgress) || !get(auth).token || get(projectSwitching)) return Promise.resolve();
		if (activeRead?.target === target && (!forceRefresh || activeRead.forceRefresh) && (activeRead.recheckDirectory || !recheckDirectory)) { activeRead.settlesUncertain ||= settlesUncertain; return activeRead.promise; }
		reads?.abort(); reads = new AbortController();
		const request = capture(); const sequence = ++browseSequence; const signal = reads.signal;
		const token = get(auth).token!;
		const owner = snapshotOwner; const epoch = snapshotEpoch;
		const valid = () => current(request) && owner === snapshotOwner && epoch === snapshotEpoch && sequence === browseSequence && !signal.aborted;
		const cached = workspaceSnapshots.get(target);
		const displayRows = directorySnapshot && retained(directorySnapshot.expiresAt) ? directorySnapshot.rows : null;
		const canDisplay = !forceRefresh && displayRows && displayRows.some(row => row.id === target) && cached && retained(cached.expiresAt);
		if (canDisplay) {
			domains = structuredClone(displayRows); directoryValid = true; domainId = target;
			inventory = structuredClone(cached.inventory); ready = true; error = '';
			if (!recheckDirectory && cached.expiresAt > Date.now()) { loading = false; return Promise.resolve(); }
		} else {
			ready = false; inventory = null;
			if (recheckDirectory) { domains = []; directoryValid = false; }
		}
		loading = true; domainId = target; error = '';
		// Handle speculative failures immediately, including when the directory rejects or chooses a fallback.
		const workspace = (selected: string) => {
			const cached = workspaceSnapshots.get(selected);
			if (!recheckDirectory && cached && cached.expiresAt > Date.now()) return Promise.resolve({ ok: true as const, result: structuredClone(cached.inventory) });
			return api.get<WorkspaceInventory>(`/api/v1/auth/workspaces?domain_id=${encodeURIComponent(selected)}`, token, undefined, { refresh: forceRefresh, suppressAuthRedirect: true, signal })
				.then(result => ({ ok: true as const, result }), () => ({ ok: false as const }));
		};
		async function run() {
			try {
				const directory = recheckDirectory ? api.get<AvailableDomain[]>('/api/v1/auth/domains', token, undefined, { refresh: forceRefresh, suppressAuthRedirect: true, signal }) : null;
				const pending = target ? workspace(target) : null;
				const rows = directory ? await directory : directorySnapshot && directorySnapshot.expiresAt > Date.now() ? structuredClone(directorySnapshot.rows) : domains;
				if (!valid()) return;
				if (!validDomains(rows)) throw new Error('Invalid domain directory');
				domains = rows.map(displayDomain); directoryValid = true;
				if (recheckDirectory) {
					directorySnapshot = { rows: rows.map(displayDomain), expiresAt: Date.now() + DIRECTORY_TTL_MS };
					for (const id of workspaceSnapshots.keys()) if (!rows.some(row => row.id === id)) workspaceSnapshots.delete(id);
				}
				const selected = rows.some(row => row.id === target) ? target : rows[0]?.id ?? '';
				if (domainId !== selected || !rows.some(row => row.id === target)) { inventory = null; ready = false; }
				domainId = selected;
				if (recheckDirectory && activeRead) activeRead.target = selected;
				if (!selected) { ready = true; persistSnapshots(); if (settlesUncertain || activeRead?.settlesUncertain) uncertain = false; return; }
				const response = await (selected === target && pending ? pending : workspace(selected));
				if (!valid() || domainId !== selected) return;
				if (!response.ok) throw new Error('Workspace unavailable');
				const result = response.result;
				if (!validInventory(result, selected)) throw new Error('Invalid workspace directory');
				inventory = displayInventory(result); ready = true;
				if (recheckDirectory || !workspaceSnapshots.has(selected) || workspaceSnapshots.get(selected)!.expiresAt <= Date.now()) {
					workspaceSnapshots.delete(selected);
					workspaceSnapshots.set(selected, { inventory: displayInventory(result), expiresAt: Date.now() + DIRECTORY_TTL_MS });
					if (workspaceSnapshots.size > MAX_WORKSPACE_SNAPSHOTS) workspaceSnapshots.delete(workspaceSnapshots.keys().next().value!);
				}
				persistSnapshots();
				if (settlesUncertain || activeRead?.settlesUncertain) uncertain = false;
			} catch {
				if (valid()) { clearSnapshots(); error = 'loadFailed'; domains = []; directoryValid = false; inventory = null; ready = false; reads?.abort(); }
			} finally {
				if (current(request) && sequence === browseSequence) { loading = false; activeRead = null; }
			}
		}
		const promise = run();
		if (loading) activeRead = { target, recheckDirectory, forceRefresh, settlesUncertain, promise };
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
