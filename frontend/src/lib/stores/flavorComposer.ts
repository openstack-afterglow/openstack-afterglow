import { get, writable, type Readable } from 'svelte/store';
import { auth, authReady, canWrite, logoutInProgress, projectSwitching } from './auth';
import { flavorComposerApi, type FlavorComposerAuthority } from '$lib/api/flavorComposer';
import { ApiError } from '$lib/api/errors';
import { flavorCreateBlock, type FlavorCapacityStatus, type FlavorComposition, type FlavorComposerSnapshot, type FlavorComposerOptions, type FlavorOption } from '$lib/types/flavor';
import { activateResourceDraft, claimResourceSelectionScope, defaultFlavorComposition, flavorResourceDraftKey, readResourceDraft, retainableFlavorComposition, resourceDraftReset, validFlavorComposition, writeResourceDraft, type FlavorComposerMode } from './flavorResourceDraft';

export interface ComposerState {
	mode: FlavorComposerMode;
	composition: FlavorComposition;
	quantityPending: Record<'vcpus' | 'ram_mb' | 'gpu_count', boolean>;
	quantityRevision: number;
	draftScope: string;
	selectedId: string | null;
	options: FlavorComposerOptions | null;
	history: FlavorOption[];
	loading: boolean;
	refreshing: boolean;
	error: string | null;
	backgroundError: string | null;
	historyLoading: boolean;
	historyError: string | null;
	saving: boolean;
	saveError: string | null;
	unknown: boolean;
	ready: boolean;
	canWrite: boolean;
}
const writes = new Map<string, 'pending' | 'unknown'>();
const writeTuples = new Map<string, FlavorComposition>();
const writeOperations = new Map<string, { id: string; identity: string; login: string | null | undefined }>();
const writeRevision = writable(0);
const initial = (): ComposerState => ({ mode: 'compose', composition: defaultFlavorComposition(), quantityPending: { vcpus: false, ram_mb: false, gpu_count: false }, quantityRevision: 0, draftScope: '', selectedId: null, options: null, history: [], loading: false, refreshing: false, error: null, backgroundError: null, historyLoading: false, historyError: null, saving: false, saveError: null, unknown: false, ready: false, canWrite: false });
const tupleKey = (value: FlavorComposition) => JSON.stringify([value.vcpus, value.ram_mb, value.gpu_profile_id, value.gpu_count]);

function deriveOptions(snapshot: FlavorComposerSnapshot, tuple: FlavorComposition): FlavorComposerOptions {
	type Variant = FlavorComposerSnapshot['variants'][number];
	type Region = Variant['regions'][number];
	const axisFits = (value: number, axis: Region['vcpus']) => Number.isInteger(value) && axis.step > 0 && value >= axis.min && value <= axis.max && value % axis.step === 0;
	const fits = (region: Region, cpu: number, ram: number) => cpu >= 2 && cpu <= 128 && cpu % 2 === 0 && ram >= 1024 && ram <= 2097152 && ram % 1024 === 0 && axisFits(cpu, region.vcpus) && axisFits(ram, region.ram_mb);
	const usable = (variant: Variant | undefined) => snapshot.status !== 'unavailable' && variant?.status === 'available' && (variant.gpu_profile_id === null || snapshot.gpu_profiles.some(profile => profile.id === variant.gpu_profile_id));
	const variant = snapshot.variants.find(row => row.gpu_profile_id === tuple.gpu_profile_id && row.gpu_count === tuple.gpu_count);
	const regions = usable(variant) ? variant!.regions : [];
	const fitting = regions.find(region => fits(region, tuple.vcpus, tuple.ram_mb));
	const status: FlavorCapacityStatus = snapshot.status === 'unavailable' || variant?.status === 'unavailable' ? 'unavailable' : fitting && validFlavorComposition(tuple) ? 'available' : 'insufficient';
	const vcpus: number[] = [];
	const ram_mb: number[] = [];
	for (let cpu = 2; cpu <= 128; cpu += 2) if (regions.some(region => fits(region, cpu, tuple.ram_mb))) vcpus.push(cpu);
	for (let ram = 1024; ram <= 2097152; ram += 1024) if (regions.some(region => fits(region, tuple.vcpus, ram))) ram_mb.push(ram);
	const tupleStatus = (row: Variant | undefined): FlavorCapacityStatus => snapshot.status === 'unavailable' || row?.status === 'unavailable' ? 'unavailable' : usable(row) && row!.regions.some(region => fits(region, tuple.vcpus, tuple.ram_mb)) ? 'available' : 'insufficient';
	const gpu_profiles = snapshot.gpu_profiles.map(profile => {
		const variants = snapshot.variants.filter(row => row.gpu_profile_id === profile.id);
		const statuses = variants.map(tupleStatus);
		return { ...profile, status: statuses.includes('available') ? 'available' as const : statuses.includes('unavailable') ? 'unavailable' as const : 'insufficient' as const };
	});
	const gpu_counts = tuple.gpu_profile_id ? snapshot.variants.filter(row => row.gpu_profile_id === tuple.gpu_profile_id && tupleStatus(row) === 'available').map(row => row.gpu_count).sort((a, b) => a - b) : [];
	const base = variant?.preview;
	let selection: FlavorOption | null = null;
	if (base) {
		const eligibility = base.eligibility;
		selection = { ...base, id: 'composer-preview', name: '', display_name: null, vcpus: tuple.vcpus, ram: tuple.ram_mb, composition: { ...tuple }, eligibility: eligibility ? {
			...eligibility,
			selectable: status === 'available' && eligibility.selectable,
			requirements: { ...eligibility.requirements, cores: tuple.vcpus, ram_mb: tuple.ram_mb },
			blockers: [...eligibility.blockers.filter(blocker => !blocker.code.startsWith('host_capacity_')), ...(status === 'available' ? [] : [{ code: status === 'unavailable' ? 'host_capacity_unavailable' : 'host_capacity_insufficient' }])],
			capacity: eligibility.capacity ? { ...eligibility.capacity, status, checked_at: snapshot.checked_at, remaining_vcpus: fitting?.vcpus.max ?? null, remaining_ram_mb: fitting?.ram_mb.max ?? null } : null,
		} : null };
	}
	return { vcpus, ram_mb, gpu_profiles, gpu_counts, selection, checked_at: snapshot.checked_at, status };
}

export interface FlavorComposerController extends Readable<ComposerState> {
	configure(admin: boolean, targetProjectId: string | null): void;
	edit(patch: Partial<FlavorComposition>): void;
	setQuantityPending(resource: keyof ComposerState['quantityPending'], pending: boolean): void;
	selectGpu(profileId: string | null): void;
	setMode(mode: FlavorComposerMode): void;
	refresh(mode?: 'manual' | 'periodic'): Promise<boolean>;
	loadHistory(): Promise<boolean>;
	save(saved?: FlavorOption): Promise<boolean>;
	canSave(): boolean;
	rememberSelection(id: string): void;
	verifyUnknown(): Promise<void>;
	destroy(): void;
}

export function createFlavorComposer(
	callbacks: { invalidate: () => void; authorityInvalidated?: () => void; scopeChanged?: () => void; scopeReady?: () => void; select: (flavor: FlavorOption) => void; restore: (id: string, mode: FlavorComposerMode) => void },
	{ resizeInstanceId = null }: { resizeInstanceId?: string | null } = {},
): FlavorComposerController {
	const state = writable<ComposerState>(initial());
	// A resize composer is modal-scoped: it never persists, restores or claims the
	// VM wizard's shared draft, active key or reset broadcast.
	const resize = Boolean(resizeInstanceId);
	let surface = { admin: false, targetProjectId: null as string | null, configured: false };
	let identity = '';
	let storageKey: string | null = null;
	let epoch = 0;
	let request = 0;
	let historyRequest = 0;
	let destroyed = false;
	let optionsController: AbortController | null = null;
	let historyController: AbortController | null = null;
	let saveController: AbortController | null = null;
	let authority: FlavorComposerAuthority | null = null;
	let wasReady = false;
	let snapshot: FlavorComposerSnapshot | null = null;
	const initializedScopes = new Set<string>();
	function persist() {
		if (resize) return;
		const value = get(state);
		writeResourceDraft(storageKey, { mode: value.mode, composition: value.composition, selectedId: value.selectedId });
	}
	function abortReads() { optionsController?.abort(); historyController?.abort(); request += 1; historyRequest += 1; }
	function sync() {
		if (destroyed || !surface.configured) return;
		const actor = get(auth);
		const target = surface.admin ? surface.targetProjectId : actor.projectId;
		const draftKey = flavorResourceDraftKey(actor.userId, actor.identityDomainId, target, surface.admin);
		const key = draftKey && resize ? `${draftKey}:resize:${resizeInstanceId}` : draftKey;
		const previousOperation = key ? writeOperations.get(key) : undefined;
		if (key && previousOperation && previousOperation.login !== actor.sessionId) {
			// New logical logins cannot recover the previous login's private receipt.
			// Drop only its local lock, never replay its still-durable server intent.
			writes.delete(key); writeTuples.delete(key); writeOperations.delete(key);
		}
		const writeAllowed = surface.admin ? actor.isSystemAdmin : (actor.canWrite ?? get(canWrite));
		const nextIdentity = JSON.stringify([actor.sessionId, actor.userId, actor.identityDomainId, actor.domainId, actor.projectId, actor.isSystemAdmin, writeAllowed, [...actor.roles].sort(), Boolean(actor.token), surface.admin, target]);
		const previousSelectionScopeChanged = resize ? false : claimResourceSelectionScope(nextIdentity);
		const ready = Boolean(actor.token && key && get(authReady) && !get(logoutInProgress) && !get(projectSwitching) && (!surface.admin || actor.isSystemAdmin));
		const changed = nextIdentity !== identity;
		if (changed || (wasReady && !ready)) {
			epoch += 1;
			if (wasReady && !ready) callbacks.authorityInvalidated?.();
			abortReads(); saveController?.abort();
			snapshot = null;
			if (identity || previousSelectionScopeChanged) callbacks.invalidate();
			if (changed) {
				if (identity) callbacks.scopeChanged?.();
				identity = nextIdentity; storageKey = key; if (!resize) activateResourceDraft(key);
				const draft = resize ? null : readResourceDraft(key);
				const protectedTuple = key ? writeTuples.get(key) : undefined;
				const initializationKey = JSON.stringify([actor.sessionId, key]);
				const freshDirect = Boolean(key && !initializedScopes.has(initializationKey) && !protectedTuple && (!draft || draft.mode === 'compose'));
				if (key) initializedScopes.add(initializationKey);
				const composition = { ...(protectedTuple ?? draft?.composition ?? defaultFlavorComposition()) };
				if (freshDirect) { composition.gpu_profile_id = null; composition.gpu_count = 0; }
				const selectedId = freshDirect && draft?.composition.gpu_profile_id ? null : draft?.selectedId ?? null;
				state.set({ ...initial(), ...(draft ? { mode: draft.mode } : {}), quantityRevision: epoch, composition, draftScope: initializationKey, selectedId, unknown: key ? writes.get(key) === 'unknown' : false, saving: key ? writes.get(key) === 'pending' : false });
				if (freshDirect && draft) {
					if (draft.composition.gpu_profile_id) callbacks.invalidate();
					persist();
				}
			} else state.update(value => ({ ...value, quantityPending: initial().quantityPending, quantityRevision: epoch, options: null, history: [], ready: false, loading: false, refreshing: false, historyLoading: false, error: null, backgroundError: null, historyError: null, saveError: null }));
		}
		authority = ready ? { token: actor.token!, projectId: actor.projectId ?? '', targetProjectId: target!, admin: surface.admin, instanceId: resizeInstanceId } : null;
		state.update(value => ({ ...value, ready, canWrite: writeAllowed }));
		if (ready && (!wasReady || changed)) {
			const selected = get(state).selectedId;
			if (selected) callbacks.restore(selected, get(state).mode);
			callbacks.scopeReady?.();
			void refresh('manual'); void loadHistory();
		}
		wasReady = ready;
	}
	const stops = [auth.subscribe(sync), authReady.subscribe(sync), logoutInProgress.subscribe(sync), projectSwitching.subscribe(sync)];
	stops.push(writeRevision.subscribe(() => {
		if (destroyed || !storageKey) return;
		const previous = get(state);
		const saving = writes.get(storageKey) === 'pending';
		state.update(value => ({ ...value, saving, unknown: writes.get(storageKey!) === 'unknown' }));
		if (previous.saving && !saving && !previous.options && authority) { void refresh(); void loadHistory(); }
	}));
	let resetRevision = get(resourceDraftReset);
	stops.push(resourceDraftReset.subscribe(revision => {
		if (resize || revision === resetRevision || destroyed) return;
		const previous = get(state);
		resetRevision = revision; epoch += 1; abortReads(); saveController?.abort(); callbacks.invalidate();
		const composition = { ...((storageKey ? writeTuples.get(storageKey) : undefined) ?? defaultFlavorComposition()) };
		state.set({ ...initial(), quantityRevision: epoch, composition, draftScope: previous.draftScope, options: snapshot ? deriveOptions(snapshot, composition) : null, error: previous.error, backgroundError: previous.backgroundError, ready: Boolean(authority), canWrite: previous.canWrite, saving: storageKey ? writes.get(storageKey) === 'pending' : false, unknown: storageKey ? writes.get(storageKey) === 'unknown' : false });
		if (authority) { if (!snapshot || previous.refreshing) void refresh('manual'); void loadHistory(); }
	}));
	function configure(admin: boolean, targetProjectId: string | null) {
		if (surface.configured && surface.admin === admin && surface.targetProjectId === targetProjectId) return;
		surface = { admin, targetProjectId, configured: true }; sync();
	}
	async function refresh(mode: 'manual' | 'periodic' = 'manual') {
		if (!authority || destroyed || get(state).saving) return false;
		if (mode === 'periodic' && (get(state).loading || get(state).refreshing)) return false;
		optionsController?.abort(); const controller = new AbortController(); optionsController = controller;
		const id = ++request; const generation = epoch; const actor = authority;
		const current = () => !destroyed && generation === epoch && id === request && Boolean(authority);
		state.update(value => ({ ...value, loading: !value.options, refreshing: true, error: mode === 'manual' ? null : value.error, backgroundError: null }));
		try {
			const result = await flavorComposerApi.options(actor, controller.signal);
			if (!current()) return false;
			snapshot = result;
			state.update(value => ({ ...value, options: deriveOptions(result, value.composition), error: null, backgroundError: null })); return true;
		} catch (error) {
			if (!current()) return false;
			const message = error instanceof Error ? error.message : String(error);
			state.update(value => mode === 'periodic' && value.options ? { ...value, backgroundError: message } : { ...value, error: message }); return false;
		} finally { if (current()) state.update(value => ({ ...value, loading: false, refreshing: false })); }
	}
	async function loadHistory() {
		if (!authority || destroyed) return false;
		historyController?.abort(); const controller = new AbortController(); historyController = controller;
		const id = ++historyRequest; const generation = epoch; const actor = authority;
		const current = () => !destroyed && generation === epoch && id === historyRequest && Boolean(authority);
		state.update(value => ({ ...value, historyLoading: true, historyError: null }));
		try {
			const result = await flavorComposerApi.history(actor, controller.signal);
			if (!current()) return false;
			state.update(value => ({ ...value, history: result.items })); return true;
		} catch (error) {
			if (current()) state.update(value => ({ ...value, historyError: error instanceof Error ? error.message : String(error) })); return false;
		} finally { if (current()) state.update(value => ({ ...value, historyLoading: false })); }
	}
	function edit(patch: Partial<FlavorComposition>) {
		if (!authority || get(state).saving || get(state).unknown) return;
		const composition = { ...get(state).composition, ...patch };
		if (!retainableFlavorComposition(composition)) {
			callbacks.invalidate();
			state.update(value => ({ ...value, selectedId: null }));
			return;
		}
		callbacks.invalidate();
		state.update(value => ({ ...value, composition, options: snapshot ? deriveOptions(snapshot, composition) : null, selectedId: null, saveError: null })); persist();
	}
	function setQuantityPending(resource: keyof ComposerState['quantityPending'], pending: boolean) {
		if (destroyed || get(state).quantityPending[resource] === pending) return;
		if (pending) callbacks.invalidate();
		state.update(value => ({ ...value, quantityPending: { ...value.quantityPending, [resource]: pending }, ...(pending ? { selectedId: null } : {}) }));
	}
	function selectGpu(profileId: string | null) {
		if (!authority || get(state).saving || get(state).unknown) return;
		if (profileId === null) { edit({ gpu_profile_id: null, gpu_count: 0 }); return; }
		if (!snapshot || !get(state).options?.gpu_profiles.some(profile => profile.id === profileId && profile.status === 'available')) return;
		const current = get(state).composition;
		const candidate = { ...current, gpu_profile_id: profileId };
		const counts = deriveOptions(snapshot, candidate).gpu_counts;
		const count = counts.includes(current.gpu_count) ? current.gpu_count : counts[0];
		if (count !== undefined) edit({ gpu_profile_id: profileId, gpu_count: count });
	}
	function setMode(mode: FlavorComposerMode) {
		if (!authority || get(state).saving || get(state).unknown || get(state).mode === mode) return;
		callbacks.invalidate();
		state.update(value => ({ ...value, mode, quantityPending: initial().quantityPending, selectedId: null })); persist();
		if (mode === 'saved') void loadHistory();
	}
	function rememberSelection(id: string) { if (get(state).saving || get(state).unknown) return; state.update(value => ({ ...value, selectedId: id })); persist(); }
	function canSave() {
		const value = get(state); const options = value.options;
		return Boolean(authority && !destroyed && value.mode === 'compose' && !Object.values(value.quantityPending).some(Boolean) && validFlavorComposition(value.composition) && value.canWrite && !value.saving && !value.unknown && !value.loading && !value.refreshing && !value.error && !value.backgroundError && options?.status === 'available' && options.selection && flavorCreateBlock(options.selection) === null);
	}
	async function save(saved?: FlavorOption) {
		const value = get(state);
		const composition = saved?.composition ?? value.composition;
		if (value.unknown) return false;
		if (!authority || !storageKey || destroyed || !value.canWrite || value.saving || value.unknown || writes.has(storageKey)) return false;
		if (saved ? (!saved.composition || !validFlavorComposition(saved.composition) || flavorCreateBlock(saved) !== null) : !canSave()) return false;
		const generation = epoch; const key = storageKey; const actor = authority;
		const operation = { id: crypto.randomUUID(), identity, login: get(auth).sessionId };
		const controller = new AbortController(); saveController = controller;
		const current = () => !destroyed && generation === epoch && Boolean(authority);
		let dispatched = false;
		optionsController?.abort(); request += 1;
		writes.set(key, 'pending'); writeTuples.set(key, { ...composition }); callbacks.invalidate();
		writeOperations.set(key, operation);
		writeRevision.update(value => value + 1);
		state.update(value => ({ ...value, composition: { ...composition }, selectedId: null, options: saved ? null : value.options, saving: true, saveError: null }));
		persist();
		try {
			const flavor = await flavorComposerApi.save(actor, composition, operation.id, controller.signal, () => { if (!current()) throw new DOMException('Aborted', 'AbortError'); dispatched = true; });
			if (writeOperations.get(key) !== operation) return false;
			if (!flavor?.id?.trim() || flavor.id === 'composer-preview' || !flavor.composition || tupleKey(flavor.composition) !== tupleKey(composition) || flavor.vcpus !== composition.vcpus || flavor.ram !== composition.ram_mb) throw new ApiError(503, 'flavor_composition_native_outcome_unknown');
			writes.delete(key);
			writeTuples.delete(key);
			writeOperations.delete(key);
			writeRevision.update(value => value + 1);
			if (!current()) return false;
			if (flavorCreateBlock(flavor) !== null) {
				state.update(value => ({ ...value, options: value.options ? { ...value.options, selection: { ...flavor, id: 'composer-preview' }, status: flavor.eligibility?.capacity?.status ?? 'unavailable' } : null }));
				void loadHistory(); return false;
			}
			state.update(value => ({ ...value, composition: { ...composition }, selectedId: flavor.id })); persist(); callbacks.select(flavor); return true;
		} catch (error) {
			const unknown = dispatched && (!(error instanceof ApiError) || error.status === 0 || error.status >= 500);
			if (writeOperations.get(key) !== operation) return false;
			if (unknown) {
				// Keep the single original mutation pending while checking its exact
				// receipt. Never send another POST, even if the first response was lost.
				if (current() && await resolveOperation(key, generation, controller, true)) return true;
				if (writeOperations.get(key) !== operation) return false;
				writes.set(key, 'unknown'); writeTuples.set(key, { ...composition });
			} else { writes.delete(key); writeTuples.delete(key); writeOperations.delete(key); }
			writeRevision.update(value => value + 1);
			if (current()) state.update(value => ({ ...value, unknown, saveError: unknown ? value.saveError : error instanceof Error ? error.message : String(error) }));
			return false;
		} finally { if (current()) state.update(value => ({ ...value, saving: false })); }
	}
	async function resolveOperation(key: string, generation: number, controller: AbortController, wait: boolean) {
		const operation = writeOperations.get(key); const expected = writeTuples.get(key);
		if (!operation || !expected || operation.identity !== identity || !authority) return false;
		const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(120_000)]);
		const current = () => !destroyed && generation === epoch && Boolean(authority) && get(state).canWrite && writeOperations.get(key) === operation && operation.identity === identity;
		try {
			do {
				if (!current()) return false;
				const result = await flavorComposerApi.resolve(authority!, operation.id, signal);
				if (!current()) return false;
				if (result !== null) {
					if (!result.composition || tupleKey(result.composition) !== tupleKey(expected) || result.vcpus !== expected.vcpus || result.ram !== expected.ram_mb || !result.id || result.id === 'composer-preview' || flavorCreateBlock(result) !== null) return false;
					writes.delete(key); writeTuples.delete(key); writeOperations.delete(key);
					writeRevision.update(value => value + 1);
					state.update(value => ({ ...value, composition: { ...expected }, selectedId: result.id, saveError: null }));
					persist(); callbacks.select(result); return true;
				}
				if (!wait) return false;
				const delay = Promise.withResolvers<void>();
				const abort = () => { clearTimeout(timer); delay.reject(signal.reason); };
				const timer = setTimeout(() => { signal.removeEventListener('abort', abort); delay.resolve(); }, 2000);
				signal.addEventListener('abort', abort, { once: true });
				if (signal.aborted) abort();
				await delay.promise;
			} while (!signal.aborted);
		} catch (error) {
			if (current() && error instanceof ApiError && error.status > 0 && error.status < 500) state.update(value => ({ ...value, saveError: error.message }));
		}
		return false;
	}
	async function verifyUnknown() {
		if (!authority || get(state).saving || !get(state).canWrite || !get(state).unknown || !storageKey) return;
		const generation = epoch; const key = storageKey;
		const operation = writeOperations.get(key);
		const controller = new AbortController(); saveController = controller;
		writes.set(key, 'pending'); writeRevision.update(value => value + 1);
		if (!await resolveOperation(key, generation, controller, false) && operation && writeOperations.get(key) === operation) {
			writes.set(key, 'unknown'); writeRevision.update(value => value + 1);
		}
	}
	function destroy() { if (destroyed) return; destroyed = true; snapshot = null; epoch += 1; abortReads(); saveController?.abort(); stops.forEach(stop => stop()); if (!resize) activateResourceDraft(null); }
	return { subscribe: state.subscribe, configure, edit, setQuantityPending, selectGpu, setMode, refresh, loadHistory, save, canSave, rememberSelection, verifyUnknown, destroy };
}
