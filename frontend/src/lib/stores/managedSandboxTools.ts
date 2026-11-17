import { derived, get, readable, type Readable } from 'svelte/store';
import { api } from '$lib/api/client';
import type { McpSettingsPage, McpTemplate } from '$lib/api/mcpCatalog';
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { serviceCapabilities } from '$lib/stores/servicePermissions';
import { sessionScopeKey } from '$lib/utils/authSession';
import { t } from '$lib/i18n/ns/mcp-gallery';

export type ManagedSandboxIssue = 'permission' | 'loading' | 'catalog_failed' | 'unavailable' | 'invalid_saved' | 'selection_changed' | 'owner_changed' | 'too_many';
export interface ManagedSandboxProfile {
	id: string;
	name: string;
	available: boolean | null;
	reason: string | null;
	tools: string[];
}
export interface ManagedSandboxToolState {
	ownerKey: string | null;
	selected: string[];
	profiles: ManagedSandboxProfile[];
	loading: boolean;
	preparing: boolean;
	catalogLoaded: boolean;
	catalogError: boolean;
	unavailable: string[];
	issue: ManagedSandboxIssue | null;
	canSelect: boolean;
	storageFailed: boolean;
}
export interface PreparedSandboxTools { names: string[]; ownerKey: string; revision: number }

export class ManagedSandboxSelectionError extends Error {
	constructor(public code: ManagedSandboxIssue, public names: string[] = []) {
		super(code);
		this.name = 'ManagedSandboxSelectionError';
	}
}

const PREFIX = 'afterglow:managed-sandbox-tools:v1:';
const empty = (): ManagedSandboxToolState => ({ ownerKey: null, selected: [], profiles: [], loading: false, preparing: false, catalogLoaded: false, catalogError: false, unavailable: [], issue: null, canSelect: false, storageFailed: false });
const canonical = (name: unknown): name is string => typeof name === 'string' && name.length > 0 && name.length <= 128 && /^[A-Za-z][A-Za-z0-9_]*$/.test(name);
function invalidNames(names: unknown): ManagedSandboxIssue | null {
	if (!Array.isArray(names) || !names.every(canonical) || new Set(names).size !== names.length) return 'invalid_saved';
	return names.length > 100 ? 'too_many' : null;
}

let active = false;
let revision = 0;
let epoch = 0;
let boundary = '';
let preferenceKey: string | null = null;
let permission = false;
let invalid: ManagedSandboxIssue | null = null;
let value = empty();
let publish: (state: ManagedSandboxToolState) => void = () => {};
let request: { controller: AbortController; promise: Promise<void> } | null = null;
let preparation: Promise<PreparedSandboxTools> | null = null;
let availabilityRevision = 0;
const issued = new WeakMap<PreparedSandboxTools, number>();

function availableNames(): Set<string> {
	return new Set(value.profiles.filter(profile => profile.available === true).flatMap(profile => profile.tools));
}
function update(patch: Partial<ManagedSandboxToolState> = {}) {
	if (patch.profiles && JSON.stringify(patch.profiles.map(profile => [profile.id, profile.available, profile.tools])) !== JSON.stringify(value.profiles.map(profile => [profile.id, profile.available, profile.tools]))) ++availabilityRevision;
	if (patch.catalogError && !value.catalogError) ++availabilityRevision;
	const next = { ...value, ...patch };
	const available = new Set(next.profiles.filter(profile => profile.available === true).flatMap(profile => profile.tools));
	next.unavailable = next.selected.filter(name => !available.has(name));
	next.canSelect = active && next.ownerKey !== null && permission && next.catalogLoaded && !next.catalogError && !next.loading;
	next.issue = invalid ?? (next.selected.length === 0 ? null : !permission ? 'permission' : next.loading ? 'loading' : next.catalogError ? 'catalog_failed' : !next.catalogLoaded ? 'loading' : next.unavailable.length ? 'unavailable' : null);
	// Consumers cannot mutate selection or availability behind the revision fence.
	next.selected = Object.freeze([...next.selected]) as string[];
	next.profiles = Object.freeze(next.profiles.map(profile => Object.freeze({ ...profile, tools: Object.freeze([...profile.tools]) as string[] }))) as ManagedSandboxProfile[];
	next.unavailable = Object.freeze(next.unavailable) as string[];
	value = Object.freeze(next);
	publish(value);
}
function invalidate(code: ManagedSandboxIssue) {
	++epoch;
	++revision;
	request?.controller.abort(new ManagedSandboxSelectionError(code));
	request = null;
	preparation = null;
}
function loadPreference() {
	invalid = null;
	let selected: string[] = [];
	let storageFailed = false;
	try {
		const raw = localStorage.getItem(preferenceKey!);
		if (raw !== null) {
			let saved: unknown;
			try { saved = JSON.parse(raw); } catch { invalid = 'invalid_saved'; }
			if (!invalid) {
				if (!saved || typeof saved !== 'object' || Array.isArray(saved) || !('version' in saved) || saved.version !== 1 || !('selected' in saved)) invalid = 'invalid_saved';
				else {
					const names = saved.selected;
					invalid = invalidNames(names);
					if (!invalid && Array.isArray(names)) selected = [...names];
				}
			}
		}
	} catch { storageFailed = true; invalid = 'invalid_saved'; }
	update({ selected, storageFailed });
}
function persist() {
	try {
		// Explicit whitelist: never persist auth, catalog, runtime or request frames.
		localStorage.setItem(preferenceKey!, JSON.stringify({ version: 1, selected: [...value.selected] }));
		update({ storageFailed: false });
	} catch { update({ storageFailed: true }); }
}
function checkOwner(owner: string | null, capturedRevision: number) {
	if (!active || !owner || value.ownerKey !== owner) throw new ManagedSandboxSelectionError('owner_changed');
	if (capturedRevision !== revision) throw new ManagedSandboxSelectionError('selection_changed');
}
function checkRequest(owner: string, capturedEpoch: number, signal: AbortSignal) {
	if (signal.aborted) throw signal.reason;
	if (!active || value.ownerKey !== owner || capturedEpoch !== epoch) throw new ManagedSandboxSelectionError('owner_changed');
	if (!permission) throw new ManagedSandboxSelectionError('permission', [...value.selected]);
}
/** Cancellation settles preparations even when a transport ignores AbortSignal. */
function abortable<T>(pending: Promise<T>, signal: AbortSignal): Promise<T> {
	const { promise, resolve, reject } = Promise.withResolvers<T>();
	const abort = () => reject(signal.reason);
	if (signal.aborted) { reject(signal.reason); return promise; }
	signal.addEventListener('abort', abort, { once: true });
	pending.then(resolve, reject).finally(() => signal.removeEventListener('abort', abort));
	return promise;
}
function profilesFrom(entries: McpTemplate[]): ManagedSandboxProfile[] {
	const profiles = new Map<string, ManagedSandboxProfile>();
	for (const entry of entries) {
		if (entry.access !== 'managed') continue;
		const managed = entry.managed;
		const id = managed?.profile ?? entry.managed_profile;
		if (typeof id !== 'string' || !id) continue;
		const tools = managed?.tools ?? [];
		if (!Array.isArray(tools) || !tools.every(canonical) || new Set(tools).size !== tools.length || profiles.has(id)) throw new Error('invalid_catalog');
		profiles.set(id, { id, name: entry.name, available: managed?.available === true ? true : managed?.available === false ? false : null, reason: typeof managed?.reason === 'string' ? managed.reason : null, tools: [...tools] });
	}
	return [...profiles.values()];
}
function readCatalog(fresh: boolean): Promise<void> {
	if (request && !fresh) return request.promise;
	const owner = value.ownerKey;
	if (!active || !owner) return Promise.reject(new ManagedSandboxSelectionError('owner_changed'));
	if (!permission) return Promise.reject(new ManagedSandboxSelectionError('permission', [...value.selected]));
	request?.controller.abort(new ManagedSandboxSelectionError('selection_changed'));
	const controller = new AbortController();
	const capturedEpoch = epoch;
	const task = { controller, promise: Promise.resolve() };
	request = task;
	update({ loading: true, catalogError: false });
	task.promise = (async () => {
		try {
			const entries: McpTemplate[] = [];
			let offset = 0;
			for (;;) {
				checkRequest(owner, capturedEpoch, controller.signal);
				// Read credentials for each page; token renewal does not change logical ownership.
				const current = get(auth);
				const page = await abortable(api.get<McpSettingsPage>(`/api/v1/chat/mcp-settings?access=managed&offset=${offset}&limit=100`, current.token!, current.projectId!, { cache: 'no-store', refresh: true, signal: controller.signal, replayOnUnauthorized: false }), controller.signal);
				checkRequest(owner, capturedEpoch, controller.signal);
				if (!Array.isArray(page.entries) || (page.domain_id !== null && page.domain_id !== current.domainId)) throw new Error('invalid_catalog');
				entries.push(...page.entries);
				if (page.next_offset === null) break;
				if (!Number.isSafeInteger(page.next_offset) || page.next_offset <= offset) throw new Error('invalid_catalog');
				offset = page.next_offset;
			}
			const profiles = profilesFrom(entries);
			checkRequest(owner, capturedEpoch, controller.signal);
			update({ profiles, catalogLoaded: true, catalogError: false, loading: false });
		} catch (error) {
			if (!controller.signal.aborted && active && value.ownerKey === owner && capturedEpoch === epoch) update({ loading: false, catalogLoaded: false, catalogError: true });
			throw error instanceof ManagedSandboxSelectionError ? error : new ManagedSandboxSelectionError('catalog_failed');
		} finally { if (request === task) request = null; }
	})();
	return task.promise;
}

export const managedSandboxTools: Readable<ManagedSandboxToolState> = readable(empty(), set => {
	publish = set;
	active = true;
	boundary = '';
	const stop = derived([auth, authReady, logoutInProgress, projectSwitching, serviceCapabilities], ([owner, ready, logout, switching, can]) => {
		const verified = ready && !logout && !switching && !!owner.token && [owner.sessionId, owner.userId, owner.identityDomainId, owner.domainId, owner.projectId].every(part => typeof part === 'string' && part.trim().length > 0);
		return { owner: verified ? sessionScopeKey(owner) : null, preference: verified ? PREFIX + JSON.stringify([owner.userId, owner.identityDomainId, owner.domainId, owner.projectId]) : null, permitted: verified && can('lumen-tools_user') };
	}).subscribe(scope => {
		const key = JSON.stringify([scope.owner, scope.permitted]);
		if (key === boundary) return;
		boundary = key;
		const sameOwner = scope.owner !== null && value.ownerKey === scope.owner;
		invalidate(sameOwner ? 'permission' : 'owner_changed');
		permission = scope.permitted;
		preferenceKey = scope.preference;
		if (!sameOwner) {
			invalid = null;
			// Publish owner and saved intent atomically: never expose a transient empty selection.
			value = { ...empty(), ownerKey: scope.owner };
			if (scope.owner) loadPreference(); else update();
		}
		else update({ catalogLoaded: false, catalogError: false, loading: false, preparing: false });
		if (scope.owner && permission) void readCatalog(false).catch(() => {});
	});
	return () => {
		active = false;
		invalidate('owner_changed');
		stop();
		permission = false;
		preferenceKey = null;
		invalid = null;
		value = empty();
		set(value);
		publish = () => {};
	};
});

export function setManagedSandboxTools(names: string[]): boolean {
	if (!active || !value.ownerKey) return false;
	const problem = invalidNames(names);
	if (problem) { invalid = problem; update(); return false; }
	const additions = names.filter(name => !value.selected.includes(name));
	if (additions.length && (!value.canSelect || additions.some(name => !availableNames().has(name)))) return false;
	if (!invalid && names.length === value.selected.length && names.every((name, index) => name === value.selected[index])) return true;
	invalidate('selection_changed');
	invalid = null;
	update({ selected: [...names], loading: false, preparing: false });
	persist();
	if (!value.catalogLoaded && permission) void readCatalog(false).catch(() => {});
	return true;
}
export function toggleManagedSandboxTool(name: string, selected: boolean): boolean {
	if (!canonical(name)) return false;
	return setManagedSandboxTools(selected ? value.selected.includes(name) ? [...value.selected] : [...value.selected, name] : value.selected.filter(current => current !== name));
}
export function toggleManagedSandboxProfile(profileId: string, selected: boolean): boolean {
	const profile = value.profiles.find(current => current.id === profileId);
	if (!profile || (selected && (profile.available !== true || !profile.tools.length))) return false;
	return setManagedSandboxTools(selected ? [...new Set([...value.selected, ...profile.tools])] : value.selected.filter(name => !profile.tools.includes(name)));
}
export async function refreshManagedSandboxTools(): Promise<void> {
	if (!active || !value.ownerKey || !permission) return;
	try { await readCatalog(false); } catch { /* Sanitized catalogError is observable in the store. */ }
}
export function prepareManagedSandboxTools(): Promise<PreparedSandboxTools> {
	if (preparation) return preparation;
	const owner = value.ownerKey;
	const capturedRevision = revision;
	try {
		checkOwner(owner, capturedRevision);
		if (invalid) throw new ManagedSandboxSelectionError(invalid);
		if (value.selected.length && !permission) throw new ManagedSandboxSelectionError('permission', [...value.selected]);
	} catch (error) { return Promise.reject(error); }
	const names = [...value.selected];
	const finish = () => {
		checkOwner(owner, capturedRevision);
		if (invalid) throw new ManagedSandboxSelectionError(invalid);
		if (names.length && !permission) throw new ManagedSandboxSelectionError('permission', names);
		const unavailable = names.filter(name => !availableNames().has(name));
		if (unavailable.length) throw new ManagedSandboxSelectionError('unavailable', unavailable);
		const frame = Object.freeze({ names: Object.freeze(names) as string[], ownerKey: owner!, revision: capturedRevision });
		issued.set(frame, availabilityRevision);
		return frame;
	};
	if (!names.length) return Promise.resolve(finish());
	update({ preparing: true });
	const task = readCatalog(true).then(finish).finally(() => {
		if (preparation === task) { preparation = null; update({ preparing: false }); }
	});
	preparation = task;
	return task;
}
export function assertPreparedSandboxTools(prepared: PreparedSandboxTools): void {
	checkOwner(prepared.ownerKey, prepared.revision);
	if (!issued.has(prepared)) throw new ManagedSandboxSelectionError('selection_changed');
	if (prepared.names.length && issued.get(prepared) !== availabilityRevision) throw new ManagedSandboxSelectionError('selection_changed');
	if (invalid) throw new ManagedSandboxSelectionError(invalid);
	if (!prepared.names.length) return;
	if (!permission) throw new ManagedSandboxSelectionError('permission', [...prepared.names]);
	if (value.loading) throw new ManagedSandboxSelectionError('loading');
	if (value.catalogError || !value.catalogLoaded) throw new ManagedSandboxSelectionError('catalog_failed');
	const unavailable = prepared.names.filter(name => !availableNames().has(name));
	if (unavailable.length) throw new ManagedSandboxSelectionError('unavailable', unavailable);
}
export function managedSandboxIssueMessage(code: ManagedSandboxIssue, names: readonly string[] = []): string {
	return t(`selectionIssue.${code}`, code === 'unavailable' ? { names: names.join(', ') } : {});
}
