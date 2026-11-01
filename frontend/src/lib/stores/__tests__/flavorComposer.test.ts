import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { auth, authReady, logoutInProgress, projectSwitching } from '../auth';
import { createFlavorComposer, type FlavorComposerController } from '../flavorComposer';
import { flavorResourceDraftKey, readResourceDraft, writeResourceDraft, clearActiveResourceDraft, defaultFlavorComposition } from '../flavorResourceDraft';
import { ApiError } from '$lib/api/errors';
import type { FlavorComposerSnapshot, FlavorOption, FlavorComposition } from '$lib/types/flavor';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api }));
const controllers: FlavorComposerController[] = [];
let loginRevision = 0;
function deferred<T>() { return Promise.withResolvers<T>(); }
function flavor(composition: FlavorComposition = defaultFlavorComposition(), id = 'native-saved'): FlavorOption {
	return { id, name: 'cpu.2c_4g', vcpus: composition.vcpus, ram: composition.ram_mb, disk: 0, is_public: false, composition,
		eligibility: { selectable: true, requirements: { instances: 1, cores: composition.vcpus, ram_mb: composition.ram_mb, gpus: {} }, remaining: { instances: 10, cores: 128, ram_mb: 131072, gpus: {} }, blockers: [], capacity: { status: 'available', checked_at: '2026-10-31T10:00:00Z', candidate_hosts: 1, cpu_resource_class: 'VCPU', remaining_vcpus: 128, remaining_ram_mb: 131072 } } };
}
function options(): FlavorComposerSnapshot {
	return { checked_at: '2026-10-31T10:00:00Z', status: 'available', gpu_profiles: [{ id: 'rtx', name: 'RTX' }], variants: [
		{ gpu_profile_id: null, gpu_count: 0, status: 'available', regions: [{ vcpus: { min: 2, max: 128, step: 2 }, ram_mb: { min: 1024, max: 8192, step: 1024 } }], preview: flavor() },
		...[1, 2, 3, 4].map(gpu_count => ({ gpu_profile_id: 'rtx', gpu_count, status: 'available' as const, regions: [{ vcpus: { min: 2, max: 128, step: 2 }, ram_mb: { min: 1024, max: 8192, step: 1024 } }], preview: flavor({ ...defaultFlavorComposition(), gpu_profile_id: 'rtx', gpu_count }) })),
	] };
}
function respond(path: string) {
	const url = new URL(path, 'https://test.invalid');
	if (url.pathname.endsWith('compositions')) return Promise.resolve({ items: [] });
	if (url.pathname.includes('/compositions/operations/')) return Promise.reject(new ApiError(503, 'receipt unavailable'));
	return Promise.resolve(options());
}
function controller(admin = false, project: string | null = null) {
	const callbacks = { invalidate: vi.fn(), scopeChanged: vi.fn(), select: vi.fn(), restore: vi.fn() };
	const value = createFlavorComposer(callbacks); controllers.push(value); value.configure(admin, project);
	return { value, callbacks };
}
async function loaded(value: FlavorComposerController) { await vi.waitFor(() => expect(get(value).options).not.toBeNull()); }

beforeEach(() => {
	localStorage.clear(); api.get.mockReset().mockImplementation(respond); api.post.mockReset().mockImplementation((_path, composition, _token, _project, request) => { request.beforeDispatch(); return Promise.resolve(flavor(composition)); });
	auth.set({ ...get(auth), token: 'access-a', sessionId: `login-${++loginRevision}`, userId: 'composer-user', identityDomainId: 'home-a', domainId: 'domain-a', projectId: 'composer-project', isSystemAdmin: true, canWrite: true, roles: ['member'] });
	logoutInProgress.set(false); projectSwitching.set(false); authReady.set(true);
});
afterEach(() => { controllers.splice(0).forEach(value => value.destroy()); authReady.set(false); projectSwitching.set(false); logoutInProgress.set(false); });

describe('resource composer behavior', () => {
	it('loads the complete snapshot without tuple query or native write, then saves only one flavor', async () => {
		const { value, callbacks } = controller(); await loaded(value);
		const path = new URL(api.get.mock.calls[0][0], 'https://test.invalid');
		expect(path.pathname).toBe('/api/v1/flavors/composer-options'); expect(path.search).toBe('');
		expect(api.post).not.toHaveBeenCalled(); expect(value.canSave()).toBe(true);
		expect(await value.save()).toBe(true);
		expect(api.post).toHaveBeenCalledTimes(1); expect(new URL(api.post.mock.calls[0][0], 'https://test.invalid').pathname).toBe('/api/v1/flavors/compositions'); expect(api.post.mock.calls[0][1]).toEqual(defaultFlavorComposition()); expect(api.post.mock.calls[0][4]).toMatchObject({ replayOnUnauthorized: false, timeoutMs: 120_000 });
		expect(callbacks.select).toHaveBeenCalledWith(expect.objectContaining({ id: 'native-saved', eligibility: expect.any(Object) }));
		expect(api.post.mock.calls.some(([path]) => path.includes('/instances'))).toBe(false);
	});
	it.each(['vcpus', 'ram_mb', 'gpu_count'] as const)('owns pending %s readiness for both rendering and mutation dispatch', async resource => {
		const { value, callbacks } = controller(); await loaded(value);
		const tuple = { ...get(value).composition }; value.rememberSelection('previous-native'); callbacks.invalidate.mockClear();
		value.setQuantityPending(resource, true);
		expect(get(value).quantityPending[resource]).toBe(true); expect(value.canSave()).toBe(false);
		expect(get(value).selectedId).toBeNull(); expect(callbacks.invalidate).toHaveBeenCalledOnce();
		expect(await value.save()).toBe(false); expect(api.post).not.toHaveBeenCalled(); expect(get(value).composition).toEqual(tuple);
		await value.refresh('periodic'); expect(value.canSave()).toBe(false);
		value.setQuantityPending(resource, false); expect(value.canSave()).toBe(true);
	});
	it('resets pending input state on mode, authority and target changes without retaining permission to save', async () => {
		const { value } = controller(true, 'target-a'); await loaded(value);
		value.setQuantityPending('vcpus', true); value.setMode('catalog');
		expect(get(value).quantityPending.vcpus).toBe(false); expect(value.canSave()).toBe(false); expect(await value.save()).toBe(false);
		value.setMode('compose'); expect(value.canSave()).toBe(true); value.setQuantityPending('ram_mb', true);
		const revision = get(value).quantityRevision; authReady.set(false);
		expect(get(value).quantityPending.ram_mb).toBe(false); expect(get(value).quantityRevision).toBeGreaterThan(revision); expect(value.canSave()).toBe(false);
		authReady.set(true); await loaded(value); expect(value.canSave()).toBe(true);
		value.setQuantityPending('gpu_count', true); value.configure(true, 'target-b');
		expect(get(value).quantityPending.gpu_count).toBe(false); expect(value.canSave()).toBe(false);
		await loaded(value); expect(value.canSave()).toBe(true); expect(api.post).not.toHaveBeenCalled();
	});
	it('derives many edits immediately without GET and invalidates the prior native reference', async () => {
		const { value, callbacks } = controller(); await loaded(value); value.rememberSelection('prior'); const reads = api.get.mock.calls.length;
		for (let vcpus = 2; vcpus <= 128; vcpus += 2) { value.edit({ vcpus }); expect(get(value).options?.selection?.vcpus).toBe(vcpus); expect(value.canSave()).toBe(true); }
		value.edit({ gpu_profile_id: 'rtx', gpu_count: 3, ram_mb: 8192, vcpus: 6 });
		expect(get(value).selectedId).toBeNull(); expect(callbacks.invalidate).toHaveBeenCalled(); expect(value.canSave()).toBe(true);
		expect(api.get).toHaveBeenCalledTimes(reads);
		expect(get(value).options?.selection).toMatchObject({ id: 'composer-preview', vcpus: 6, ram: 8192, composition: { vcpus: 6, ram_mb: 8192, gpu_profile_id: 'rtx', gpu_count: 3 }, eligibility: { requirements: { cores: 6, ram_mb: 8192 }, capacity: { status: 'available' } } });
		expect(await value.save()).toBe(true); expect(api.post.mock.calls[0][1]).toEqual(get(value).composition);
	});
	it('retains invalid coordinates and never converts exhausted capacity into a selectable shape', async () => {
		api.get.mockImplementation(path => String(path).endsWith('/compositions') ? Promise.resolve({ items: [] }) : Promise.resolve({ ...options(), status: 'insufficient', variants: options().variants.map(row => ({ ...row, regions: [], status: 'insufficient', preview: null })) }));
		const { value } = controller(); await loaded(value);
		expect(get(value).composition).toEqual(defaultFlavorComposition()); expect(value.canSave()).toBe(false);
		value.edit({ vcpus: 1, ram_mb: 1024, gpu_profile_id: null, gpu_count: 0 });
		expect(get(value).composition).toEqual({ vcpus: 1, ram_mb: 1024, gpu_profile_id: null, gpu_count: 0 }); expect(api.post).not.toHaveBeenCalled();
	});
	it('keeps a last successful background snapshot but locks a failed manual check', async () => {
		const { value } = controller(); await loaded(value); const first = get(value).options;
		api.get.mockRejectedValue(new Error('capacity offline'));
		expect(await value.refresh('periodic')).toBe(false); expect(get(value).options).toBe(first); expect(get(value).backgroundError).toBe('capacity offline'); expect(get(value).error).toBeNull();
		expect(value.canSave()).toBe(false); value.edit({ vcpus: 6 }); expect(value.canSave()).toBe(false); expect(get(value).backgroundError).toBe('capacity offline');
		expect(await value.refresh('manual')).toBe(false); expect(get(value).error).toBe('capacity offline'); expect(value.canSave()).toBe(false);
	});
	it('requires a fresh composition POST for a saved row and returns its newly assessed flavor', async () => {
		const saved = flavor({ vcpus: 6, ram_mb: 8192, gpu_profile_id: 'rtx', gpu_count: 3 }, 'gpu-saved');
		api.get.mockImplementation(path => String(path).endsWith('/compositions') ? Promise.resolve({ items: [saved] }) : respond(path));
		api.post.mockImplementation((_path, composition, _token, _project, request) => { request.beforeDispatch(); return Promise.resolve(flavor(composition, 'fresh-native')); });
		const { value, callbacks } = controller(); await loaded(value); await value.loadHistory(); expect(get(value).history).toEqual([saved]);
		expect(await value.save(saved)).toBe(true); expect(api.post.mock.calls[0][1]).toEqual(saved.composition); expect(callbacks.select).toHaveBeenCalledWith(expect.objectContaining({ id: 'fresh-native' }));
	});
	it('isolates admin target endpoints and fences target A to B to A responses', async () => {
		const late = deferred<FlavorComposerSnapshot>(); let first = true;
		api.get.mockImplementation(path => String(path).includes('flavor-composer-options') && first ? (first = false, late.promise) : respond(path));
		const { value } = controller(true, 'target-a'); value.configure(true, 'target-b'); value.configure(true, 'target-a'); await loaded(value);
		late.resolve({ ...options(), status: 'unavailable', variants: [] }); await Promise.resolve();
		expect(get(value).options?.status).toBe('available');
		await value.save(); const [path, , , headerProject] = api.post.mock.calls[0]; const url = new URL(path, 'https://test.invalid'); expect(url.pathname).toBe('/api/v1/admin/instances/flavor-compositions'); expect(url.searchParams.get('project_id')).toBe('target-a'); expect(url.searchParams.get('operation_id')).toBeTruthy(); expect(headerProject).toBe('composer-project');
	});
	it.each(['verification', 'switch', 'logout', 'actor', 'destroy'] as const)('discards a late save after %s loss and refuses overlapping writes', async loss => {
		const pending = deferred<FlavorOption>(); api.post.mockImplementation((_path, _composition, _token, _project, request) => { request.beforeDispatch(); return pending.promise; });
		const { value, callbacks } = controller(); await loaded(value); const saving = value.save(); expect(await value.save()).toBe(false); expect(api.post).toHaveBeenCalledTimes(1);
		if (loss === 'verification') { authReady.set(false); authReady.set(true); }
		if (loss === 'switch') { projectSwitching.set(true); projectSwitching.set(false); }
		if (loss === 'logout') { logoutInProgress.set(true); logoutInProgress.set(false); }
		if (loss === 'actor') { const actor = get(auth); auth.set({ ...actor, userId: 'other' }); auth.set(actor); authReady.set(true); }
		if (loss === 'destroy') value.destroy();
		pending.resolve(flavor()); expect(await saving).toBe(false); expect(callbacks.select).not.toHaveBeenCalled();
	});
	it('retains a tuple through bearer renewal but gates all actions while root verification is pending', async () => {
		const { value } = controller(); await loaded(value); value.edit({ vcpus: 6 }); await loaded(value);
		auth.update(actor => ({ ...actor, token: 'access-renewed' })); expect(get(value).composition.vcpus).toBe(6); expect(value.canSave()).toBe(false); expect(await value.save()).toBe(false);
		authReady.set(true); await loaded(value); expect(value.canSave()).toBe(true); expect(get(value).composition.vcpus).toBe(6);
	});
	it('recovers a lost response automatically by exact operation and selects once without replay', async () => {
		api.post.mockImplementation((_path, _composition, _token, _project, request) => { request.beforeDispatch(); return Promise.reject(new ApiError(503, 'response lost')); });
		api.get.mockImplementation(path => String(path).includes('/operations/') ? Promise.resolve(flavor()) : respond(path));
		const { value, callbacks } = controller(); await loaded(value);
		expect(await value.save()).toBe(true); expect(api.post).toHaveBeenCalledTimes(1);
		const operation = new URL(api.post.mock.calls[0][0], 'https://test.invalid').searchParams.get('operation_id');
		expect(api.get.mock.calls.some(([path]) => path === `/api/v1/flavors/compositions/operations/${operation}`)).toBe(true);
		expect(callbacks.select).toHaveBeenCalledOnce(); expect(callbacks.select).toHaveBeenCalledWith(expect.objectContaining({ id: 'native-saved' }));
		await value.verifyUnknown(); expect(callbacks.select).toHaveBeenCalledOnce(); expect(get(value).unknown).toBe(false);
	});
	it('waits for a delayed publication receipt while retaining one pending write', async () => {
		const { value, callbacks } = controller(); await loaded(value);
		let reads = 0;
		api.post.mockImplementation((_path, _composition, _token, _project, request) => { request.beforeDispatch(); return Promise.reject(new ApiError(503, 'response lost')); });
		api.get.mockImplementation(path => String(path).includes('/operations/') ? Promise.resolve(++reads === 1 ? null : flavor()) : respond(path));
		vi.useFakeTimers();
		try {
			const saving = value.save(); await vi.advanceTimersByTimeAsync(0);
			expect(get(value).saving).toBe(true); expect(callbacks.select).not.toHaveBeenCalled(); expect(await value.save()).toBe(false);
			await vi.advanceTimersByTimeAsync(2000); expect(await saving).toBe(true);
			expect(reads).toBe(2); expect(api.post).toHaveBeenCalledTimes(1); expect(callbacks.select).toHaveBeenCalledOnce();
		} finally { vi.useRealTimers(); }
	});
	it.each(['empty ID', 'preview ID', 'wrong tuple'] as const)('recovers a malformed successful acknowledgment with %s using the same operation', async malformed => {
		const { value, callbacks } = controller(); await loaded(value);
		api.post.mockImplementation((_path, composition, _token, _project, request) => { request.beforeDispatch(); return Promise.resolve(malformed === 'wrong tuple' ? flavor({ ...composition, vcpus: 4 }) : flavor(composition, malformed === 'empty ID' ? '' : 'composer-preview')); });
		api.get.mockImplementation(path => path.includes('/operations/') ? Promise.resolve(flavor()) : respond(path));
		expect(await value.save()).toBe(true); expect(api.post).toHaveBeenCalledTimes(1); expect(callbacks.select).toHaveBeenCalledOnce(); expect(get(value).unknown).toBe(false);
	});
	it('isolates a new logical login from a late previous operation without replaying it', async () => {
		const old = deferred<FlavorOption>(); const fresh = deferred<FlavorOption>();
		api.post.mockImplementationOnce((_path, _body, _token, _project, request) => { request.beforeDispatch(); return old.promise; });
		const { value, callbacks } = controller(); await loaded(value); const first = value.save();
		auth.update(actor => ({ ...actor, sessionId: 'new-logical-login' })); authReady.set(true); await loaded(value);
		expect(get(value).unknown).toBe(false); expect(get(value).saving).toBe(false);
		api.post.mockImplementationOnce((_path, _body, _token, _project, request) => { request.beforeDispatch(); return fresh.promise; });
		const second = value.save(); old.reject(new ApiError(503, 'old response lost')); expect(await first).toBe(false);
		expect(get(value).saving).toBe(true); expect(get(value).unknown).toBe(false);
		fresh.resolve(flavor()); expect(await second).toBe(true); expect(callbacks.select).toHaveBeenCalledOnce(); expect(api.post).toHaveBeenCalledTimes(2);
	});
	it('retains an unconfirmed operation and explicit GET recheck selects without history heuristics', async () => {
		api.post.mockImplementation((_path, _composition, _token, _project, request) => { request.beforeDispatch(); return Promise.reject(new ApiError(503, 'dispatch unknown')); });
		const { value, callbacks } = controller(); await loaded(value); expect(await value.save()).toBe(false);
		expect(get(value).unknown).toBe(true); expect(await value.save()).toBe(false); expect(api.post).toHaveBeenCalledTimes(1);
		api.get.mockImplementation(path => String(path).includes('/operations/') ? Promise.resolve(flavor()) : respond(path));
		await value.verifyUnknown(); expect(get(value).unknown).toBe(false); expect(get(value).selectedId).toBe('native-saved'); expect(callbacks.select).toHaveBeenCalledOnce(); expect(api.post).toHaveBeenCalledTimes(1);
	});
	it.each(['wrong tuple', 'revoked permission', 'changed scope'] as const)('does not select ambiguous recovery after %s', async loss => {
		const receipt = deferred<FlavorOption>();
		api.post.mockImplementation((_path, _composition, _token, _project, request) => { request.beforeDispatch(); return Promise.reject(new ApiError(503, 'response lost')); });
		api.get.mockImplementation(path => String(path).includes('/operations/') ? receipt.promise : respond(path));
		const { value, callbacks } = controller(); await loaded(value); const saving = value.save();
		await vi.waitFor(() => expect(api.get.mock.calls.some(([path]) => String(path).includes('/operations/'))).toBe(true));
		if (loss === 'revoked permission') auth.update(actor => ({ ...actor, canWrite: false, roles: ['reader'] }));
		if (loss === 'changed scope') { projectSwitching.set(true); projectSwitching.set(false); }
		receipt.resolve(loss === 'wrong tuple' ? flavor({ ...defaultFlavorComposition(), vcpus: 4 }) : flavor());
		expect(await saving).toBe(false); expect(callbacks.select).not.toHaveBeenCalled(); expect(api.post).toHaveBeenCalledTimes(1);
	});
	it('restores only safe resources across remount, isolates identity/project/surface, and explicitly resets storage', async () => {
		const { value } = controller(); await loaded(value); value.edit({ vcpus: 6, ram_mb: 8192 }); value.setMode('saved'); value.rememberSelection('native-ref');
		const key = flavorResourceDraftKey('composer-user', 'home-a', 'composer-project', false)!;
		expect(JSON.parse(localStorage.getItem(key)!)).toEqual({ mode: 'saved', composition: { ...defaultFlavorComposition(), vcpus: 6, ram_mb: 8192 }, selectedId: 'native-ref' });
		value.destroy(); const restored = controller(); await loaded(restored.value); expect(get(restored.value).composition.vcpus).toBe(6); expect(restored.callbacks.restore).toHaveBeenCalledWith('native-ref', 'saved'); expect(api.post).not.toHaveBeenCalled();
		expect(readResourceDraft(flavorResourceDraftKey('different', 'home-a', 'composer-project', false))).toBeNull(); expect(readResourceDraft(flavorResourceDraftKey('composer-user', 'home-b', 'composer-project', false))).toBeNull(); expect(readResourceDraft(flavorResourceDraftKey('composer-user', 'home-a', 'other', false))).toBeNull(); expect(readResourceDraft(flavorResourceDraftKey('composer-user', 'home-a', 'composer-project', true))).toBeNull();
		writeResourceDraft(key, { ...get(restored.value), password: 'secret', cloudInit: 'secret', usageSchedule: { consent: true } } as never); expect(localStorage.getItem(key)).not.toContain('secret'); expect(localStorage.getItem(key)).not.toContain('consent');
		clearActiveResourceDraft(); expect(localStorage.getItem(key)).toBeNull(); expect(get(restored.value).composition).toEqual(defaultFlavorComposition());
	});
	it('discards a same-scope late save after write capability revocation', async () => {
		const pending = Promise.withResolvers<FlavorOption>();
		api.post.mockImplementation((_path, _body, _token, _project, request) => { request.beforeDispatch(); return pending.promise; });
		const { value, callbacks } = controller(); await loaded(value); const saving = value.save();
		auth.update(actor => ({ ...actor, canWrite: false, roles: ['reader'] }));
		pending.resolve(flavor()); expect(await saving).toBe(false); expect(callbacks.select).not.toHaveBeenCalled(); expect(value.canSave()).toBe(false); expect(get(value).canWrite).toBe(false); expect(await value.save()).toBe(false);
	});
	it('fences late read errors after scope ABA and blocks a delayed mutation preflight', async () => {
		const lateRead = Promise.withResolvers<FlavorComposerSnapshot>();
		const { value, callbacks } = controller(); await loaded(value);
		api.get.mockReturnValueOnce(lateRead.promise); const reading = value.refresh();
		const actor = get(auth); auth.set({ ...actor, userId: 'temporary-actor' }); auth.set(actor); authReady.set(true); await loaded(value);
		lateRead.reject(new Error('obsolete private error')); await reading; expect(get(value).error).toBeNull();
		const preflight = Promise.withResolvers<void>(); let dispatched = false;
		api.post.mockImplementation(async (_path, _body, _token, _project, request) => { await preflight.promise; request.beforeDispatch(); dispatched = true; return flavor(); });
		const saving = value.save(); projectSwitching.set(true); projectSwitching.set(false); preflight.resolve();
		expect(await saving).toBe(false); expect(dispatched).toBe(false); expect(callbacks.select).not.toHaveBeenCalled();
	});
	it('derives the latest tuple when the pending initial snapshot arrives without aborting it', async () => {
		const pending = deferred<FlavorComposerSnapshot>();
		api.get.mockImplementation(path => String(path).includes('composer-options') ? pending.promise : Promise.resolve({ items: [] }));
		const { value } = controller(); const signal = api.get.mock.calls[0][3].signal;
		value.edit({ vcpus: 6, ram_mb: 8192 }); value.edit({ gpu_profile_id: 'rtx', gpu_count: 3 });
		expect(signal.aborted).toBe(false); expect(api.get.mock.calls.filter(([path]) => path.includes('composer-options'))).toHaveLength(1);
		pending.resolve(options()); await loaded(value);
		expect(get(value).options?.selection?.composition).toEqual(get(value).composition); expect(value.canSave()).toBe(true);
	});
	it('preserves sparse and correlated regions and exact GPU counts', async () => {
		const snapshot = options(); const cpu = snapshot.variants[0];
		cpu.regions = [{ vcpus: { min: 4, max: 12, step: 4 }, ram_mb: { min: 2048, max: 4096, step: 2048 } }, { vcpus: { min: 2, max: 2, step: 2 }, ram_mb: { min: 8192, max: 8192, step: 1024 } }];
		snapshot.variants.find(row => row.gpu_count === 3)!.regions = [{ vcpus: { min: 2, max: 4, step: 2 }, ram_mb: { min: 1024, max: 4096, step: 1024 } }];
		api.get.mockImplementation(path => path.endsWith('composer-options') ? Promise.resolve(snapshot) : respond(path));
		const { value } = controller(); await loaded(value); expect(get(value).options?.vcpus).toEqual([4, 8, 12]); expect(value.canSave()).toBe(false);
		value.edit({ vcpus: 4 }); expect(get(value).options?.ram_mb).toEqual([2048, 4096]); expect(value.canSave()).toBe(true);
		value.edit({ ram_mb: 8192 }); expect(value.canSave()).toBe(false); expect(get(value).options?.vcpus).toEqual([2]);
		value.edit({ gpu_profile_id: 'rtx', gpu_count: 3, vcpus: 6, ram_mb: 4096 });
		expect(get(value).options?.gpu_profiles[0].status).toBe('available'); expect(get(value).options?.gpu_counts).toEqual([1, 2, 4]); expect(get(value).composition.gpu_count).toBe(3); expect(value.canSave()).toBe(false);
		value.edit({ gpu_count: 2 }); expect(value.canSave()).toBe(true);
	});
	it('retains legacy odd drafts and history without permitting a composition POST, then repairs explicitly', async () => {
		const odd = { ...defaultFlavorComposition(), vcpus: 1 }; const key = flavorResourceDraftKey('composer-user', 'home-a', 'composer-project', false)!;
		writeResourceDraft(key, { mode: 'compose', composition: odd, selectedId: null });
		const { value } = controller(); await loaded(value); expect(get(value).composition.vcpus).toBe(1); expect(value.canSave()).toBe(false); expect(await value.save()).toBe(false); expect(await value.save(flavor(odd))).toBe(false);
		value.edit({ vcpus: 3 }); expect(get(value).composition.vcpus).toBe(3); expect(value.canSave()).toBe(false); expect(await value.save()).toBe(false); expect(api.post).not.toHaveBeenCalled();
		const reads = api.get.mock.calls.filter(([path]) => path.includes('composer-options')).length; clearActiveResourceDraft(); expect(get(value).composition.vcpus).toBe(2); expect(value.canSave()).toBe(true); expect(api.get.mock.calls.filter(([path]) => path.includes('composer-options'))).toHaveLength(reads);
	});
	it('keeps snapshot previews advisory when the fresh save rejects capacity', async () => {
		const { value, callbacks } = controller(); await loaded(value); value.edit({ vcpus: 6 });
		api.post.mockImplementation((_path, composition, _token, _project, request) => { request.beforeDispatch(); return Promise.resolve({ ...flavor(composition), eligibility: { ...flavor(composition).eligibility!, selectable: false, capacity: { ...flavor(composition).eligibility!.capacity!, status: 'insufficient' } } }); });
		expect(await value.save()).toBe(false); expect(callbacks.select).not.toHaveBeenCalled(); expect(value.canSave()).toBe(false); expect(get(value).selectedId).toBeNull();
	});
	it('applies an in-flight manual refresh to the latest tuple and never enables an unavailable replacement', async () => {
		const { value } = controller(); await loaded(value); const pending = deferred<FlavorComposerSnapshot>();
		api.get.mockReturnValueOnce(pending.promise); const reading = value.refresh(); const reads = api.get.mock.calls.length;
		value.edit({ vcpus: 6, ram_mb: 8192 }); expect(value.canSave()).toBe(false); expect(get(value).refreshing).toBe(true); expect(api.get).toHaveBeenCalledTimes(reads);
		pending.resolve(options()); expect(await reading).toBe(true); expect(get(value).options?.selection?.composition).toEqual(get(value).composition); expect(value.canSave()).toBe(true);
		api.get.mockResolvedValueOnce({ ...options(), status: 'unavailable' }); expect(await value.refresh()).toBe(true); expect(value.canSave()).toBe(false);
		value.edit({ vcpus: 2 }); expect(value.canSave()).toBe(false); expect(await value.save()).toBe(false); expect(api.post).not.toHaveBeenCalled();
	});
	it('keeps only the exact GPU variant base metadata while deriving CPU and RAM requirements', async () => {
		const snapshot = options(); const gpu = snapshot.variants.find(row => row.gpu_count === 3)!;
		gpu.preview = { ...gpu.preview!, extra_specs: { 'pci_passthrough:alias': 'primary:3,companion:3' }, gpu_primary_aliases: [{ name: 'primary', count: 3, resource_class: 'CUSTOM_GPU', profile_name: 'RTX' }], eligibility: { ...gpu.preview!.eligibility!, requirements: { instances: 1, cores: 2, ram_mb: 4096, gpus: { CUSTOM_GPU: 3, CUSTOM_AUDIO: 3 } } } };
		api.get.mockImplementation(path => path.endsWith('composer-options') ? Promise.resolve(snapshot) : respond(path));
		const { value } = controller(); await loaded(value); value.edit({ vcpus: 6, ram_mb: 8192, gpu_profile_id: 'rtx', gpu_count: 3 });
		expect(get(value).options?.selection).toMatchObject({ id: 'composer-preview', extra_specs: { 'pci_passthrough:alias': 'primary:3,companion:3' }, gpu_primary_aliases: [{ count: 3 }], eligibility: { requirements: { cores: 6, ram_mb: 8192, gpus: { CUSTOM_GPU: 3, CUSTOM_AUDIO: 3 } }, remaining: gpu.preview.eligibility!.remaining } });
		value.edit({ gpu_count: 2 }); expect(get(value).options?.selection?.extra_specs).toBeUndefined(); expect(gpu.preview.eligibility!.requirements.cores).toBe(2);
	});
	it('starts each normal direct controller without GPU and preserves explicit session selections through polling and bearer renewal', async () => {
		const key = flavorResourceDraftKey('composer-user', 'home-a', 'composer-project', false)!;
		writeResourceDraft(key, { mode: 'compose', composition: { vcpus: 6, ram_mb: 8192, gpu_profile_id: 'rtx', gpu_count: 3 }, selectedId: 'old-native' });
		const first = controller(); await loaded(first.value);
		expect(get(first.value).composition).toEqual({ vcpus: 6, ram_mb: 8192, gpu_profile_id: null, gpu_count: 0 });
		expect(get(first.value).selectedId).toBeNull(); expect(first.callbacks.restore).not.toHaveBeenCalled();
		first.value.selectGpu('rtx'); first.value.edit({ gpu_count: 3 });
		const reads = api.get.mock.calls.length; first.value.edit({ vcpus: 8 });
		expect(api.get).toHaveBeenCalledTimes(reads); await first.value.refresh('periodic');
		auth.update(actor => ({ ...actor, token: 'next-bearer' })); authReady.set(true); await loaded(first.value);
		expect(get(first.value).composition).toMatchObject({ gpu_profile_id: 'rtx', gpu_count: 3 });
		first.value.destroy(); const second = controller(); await loaded(second.value);
		expect(get(second.value).composition).toEqual({ vcpus: 8, ram_mb: 8192, gpu_profile_id: null, gpu_count: 0 });
	});
	it('chooses a currently valid count when changing model, including profiles available only above count one', async () => {
		const snapshot = options();
		snapshot.gpu_profiles.push({ id: 'other', name: 'Other' });
		snapshot.variants.push({ ...snapshot.variants[1], gpu_profile_id: 'other', gpu_count: 2 });
		api.get.mockImplementation(path => path.endsWith('composer-options') ? Promise.resolve(snapshot) : respond(path));
		const { value } = controller(); await loaded(value); value.selectGpu('rtx'); value.edit({ gpu_count: 3 });
		const reads = api.get.mock.calls.length; value.selectGpu('other');
		expect(get(value).composition).toMatchObject({ gpu_profile_id: 'other', gpu_count: 2 }); expect(value.canSave()).toBe(true);
		value.selectGpu('foreign'); expect(get(value).composition.gpu_profile_id).toBe('other');
		expect(api.get).toHaveBeenCalledTimes(reads);
	});
	it('keeps an unknown GPU write original tuple through reset, close and reopen and only recovers the exact native tuple', async () => {
		api.post.mockImplementation((_path, _composition, _token, _project, request) => { request.beforeDispatch(); return Promise.reject(new ApiError(503, 'unknown')); });
		const first = controller(); await loaded(first.value); first.value.edit({ vcpus: 6, gpu_profile_id: 'rtx', gpu_count: 3 });
		const original = { ...get(first.value).composition }; expect(await first.value.save()).toBe(false);
		first.value.selectGpu(null); first.value.edit({ vcpus: 2 }); clearActiveResourceDraft();
		expect(get(first.value).composition).toEqual(original); expect(get(first.value).unknown).toBe(true);
		first.value.destroy(); const second = controller(); await loaded(second.value);
		expect(get(second.value).composition).toEqual(original); expect(get(second.value).unknown).toBe(true);
		const recovered = flavor(original, 'exact-native');
		api.get.mockImplementation(path => path.includes('/operations/') ? Promise.resolve(recovered) : respond(path));
		await second.value.verifyUnknown(); expect(get(second.value).selectedId).toBe('exact-native');
		expect(second.callbacks.select).toHaveBeenCalledWith(recovered); expect(get(second.value).unknown).toBe(false); expect(api.post).toHaveBeenCalledTimes(1);
	});
	it('does not rewrite GPU compositions referenced in saved or catalog modes on initialization', async () => {
		const key = flavorResourceDraftKey('composer-user', 'home-a', 'composer-project', false)!;
		for (const mode of ['saved', 'catalog'] as const) {
			const composition = { vcpus: 6, ram_mb: 8192, gpu_profile_id: 'rtx', gpu_count: 3 };
			writeResourceDraft(key, { mode, composition, selectedId: 'native-gpu' });
			const instance = controller(); await loaded(instance.value);
			expect(get(instance.value).composition).toEqual(composition); expect(instance.callbacks.restore).toHaveBeenCalledWith('native-gpu', mode); instance.value.destroy();
		}
	});
	it('retains withdrawn GPU coordinates visibly blocked even when a stale variant still exists', async () => {
		const { value } = controller(); await loaded(value); value.selectGpu('rtx');
		api.get.mockResolvedValueOnce({ ...options(), gpu_profiles: [] }); await value.refresh();
		expect(get(value).composition.gpu_profile_id).toBe('rtx'); expect(get(value).options?.gpu_counts).toEqual([]); expect(value.canSave()).toBe(false);
	});
});
