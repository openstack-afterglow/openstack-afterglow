import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { tick } from 'svelte';
import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
import { closeWizard, openWizard, resetWizard, wizard, wizardPassword } from '$lib/stores/wizard';
import { siteConfig } from '$lib/config/site';
import { t } from '$lib/i18n/ns/vm-wizard';
import { flavorResourceDraftKey, writeResourceDraft } from '$lib/stores/flavorResourceDraft';
import { ApiError } from '$lib/api/errors';
import type { FlavorComposition, FlavorComposerSnapshot, FlavorOption } from '$lib/types/flavor';
import type { VmCreateStore } from '$lib/stores/vmCreateStore.svelte';
import Harness from './_FlavorComposerHarness.svelte';
import { consumerFlavorLabel } from '$lib/utils/flavorDisplay';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), fetchWithAuth: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, post: mocks.post }, ApiError: class extends Error {}, fetchWithAuth: mocks.fetchWithAuth, getBaseUrl: () => 'https://test.invalid' }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/mockup/transport', () => ({ maybeMockInstanceCreateStream: () => null }));
vi.hoisted(() => { vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener() {}, removeEventListener() {} })); });
const initialTuple: FlavorComposition = { vcpus: 2, ram_mb: 4096, gpu_profile_id: null, gpu_count: 0 };
function native(composition: FlavorComposition = initialTuple, id = 'saved-native'): FlavorOption {
	return { id, name: `${composition.gpu_profile_id ? 'gpu' : 'cpu'}.${composition.vcpus}c_${composition.ram_mb / 1024}g`, vcpus: composition.vcpus, ram: composition.ram_mb, disk: 0, is_public: false, composition,
		eligibility: { selectable: true, requirements: { instances: 1, cores: composition.vcpus, ram_mb: composition.ram_mb, gpus: {} }, remaining: { instances: 5, cores: 8, ram_mb: 32768, gpus: {} }, blockers: [], capacity: { status: 'available', checked_at: '2026-10-31T00:00:00Z', candidate_hosts: 1, cpu_resource_class: 'VCPU', remaining_vcpus: 8, remaining_ram_mb: 32768 } } };
}
function available(): FlavorComposerSnapshot {
	const regions = [1024, 2048, 4096, 8192].map(ram => ({ vcpus: { min: 2, max: 8, step: 2 }, ram_mb: { min: ram, max: ram, step: 1024 } }));
	return { checked_at: '2026-10-31T00:00:00Z', status: 'available', gpu_profiles: [{ id: 'rtx-6000', name: 'RTX 6000' }, { id: 'exhausted', name: 'Exhausted GPU' }], variants: [
		{ gpu_profile_id: null, gpu_count: 0, status: 'available', regions, preview: native(initialTuple, 'composer-preview') },
		...[1, 2, 3, 4, 5].map(gpu_count => ({ gpu_profile_id: 'rtx-6000', gpu_count, status: 'available' as const, regions, preview: native({ ...initialTuple, gpu_profile_id: 'rtx-6000', gpu_count }, 'composer-preview') })),
		{ gpu_profile_id: 'exhausted', gpu_count: 1, status: 'insufficient', regions: [], preview: null },
	] };
}
let currentOptions: () => FlavorComposerSnapshot;
let history: FlavorOption[];
let inventory: FlavorOption[];
let actorNumber = 0;
function respond(path: string) {
	const url = new URL(path, 'https://test.invalid');
	if (url.pathname.endsWith('composer-options')) return Promise.resolve(currentOptions());
	if (url.pathname.endsWith('compositions')) return Promise.resolve({ items: history });
	if (url.pathname.endsWith('/flavors') || url.pathname.endsWith('flavors-for-project')) return Promise.resolve(inventory);
	if (url.pathname === '/api/v1/dashboard/quotas') return Promise.resolve({ native_compute: { instances: { limit: 10, in_use: 2 }, cores: { limit: -1, in_use: 4 }, ram: { limit: 32768, in_use: 4096 } }, storage: { gigabytes: { limit: 100, in_use: 10 } } });
	if (url.pathname === '/api/v1/admin/projects/names') return Promise.resolve([{ id: 'target-a', name: 'Target A' }, { id: 'target-b', name: 'Target B' }]);
	return Promise.resolve([]);
}
async function ready() { await waitFor(() => expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(false)); }
async function chooseGpu(label: string) {
	await fireEvent.click(screen.getByRole('button', { name: t('composer.gpuType') }));
	await fireEvent.click(screen.getByRole('option', { name: label }));
}
function quantity(label: 'composer.cores' | 'composer.ram' | 'composer.gpuCount') { return screen.getByRole('spinbutton', { name: t(label) }) as HTMLInputElement; }
function slider(label: 'composer.cores' | 'composer.ram' | 'composer.gpuCount') { return screen.getByRole('slider', { name: t(label) }) as HTMLInputElement; }

beforeEach(() => {
	actorNumber += 1; localStorage.clear(); resetWizard(); history = []; inventory = []; currentOptions = available;
	auth.set({ ...get(auth), token: 'access', sessionId: `composer-${actorNumber}`, userId: `actor-${actorNumber}`, identityDomainId: 'home', domainId: 'domain', projectId: 'project-a', isSystemAdmin: true, canWrite: true, roles: ['member'] }); authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
	siteConfig.update(value => ({ ...value, services: { ...value.services, manila: false } }));
	mocks.get.mockReset().mockImplementation(respond); mocks.fetchWithAuth.mockReset(); mocks.post.mockReset().mockImplementation((_path, composition, _token, _project, opts) => { opts.beforeDispatch(); const result = native(composition); history = [result]; return Promise.resolve(result); });
});
afterEach(() => { cleanup(); authReady.set(false); vi.useRealTimers(); });

describe('VM flavor composer rendered behavior', () => {
	it('has one footer continuation, previews native use-plus-delta, and advances exactly once after native save without VM creation', async () => {
		render(Harness); await ready();
		expect(quantity('composer.cores').value).toBe('2'); expect(quantity('composer.ram').value).toBe('4');
		const cpu = screen.getByRole('group', { name: 'vCPU' }); expect(cpu.textContent).toContain('4'); expect(cpu.textContent).toContain('6'); expect(cpu.textContent).toContain('∞');
		const ram = screen.getByRole('group', { name: 'RAM' }); expect(ram.textContent).toContain('4'); expect(ram.textContent).toContain('8');
		expect(screen.queryByPlaceholderText(t('flavor.searchPlaceholder'))).toBeNull(); expect(mocks.post).not.toHaveBeenCalled();
		expect(screen.getAllByRole('button', { name: t('composer.saveContinue') })).toHaveLength(1);
		expect(within(screen.getByTestId('flavor-composer')).queryByRole('button', { name: t('composer.saveContinue') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('footer.next') })).toBeNull();
		// A second advancement would reach configuration when the boot choice is already ready.
		wizard.update(value => ({ ...value, imageId: 'ubuntu', imageName: 'Ubuntu' }));
		const steps: number[] = [];
		const stop = wizard.subscribe(value => { if (steps.at(-1) !== value.step) steps.push(value.step); });
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') }));
		await waitFor(() => expect(screen.getByTestId('native-selected').textContent).toBe('saved-native')); expect(screen.getByTestId('native-flavors').textContent).toContain('saved-native'); expect(screen.getByTestId('wizard-step').textContent).toBe('1');
		expect(mocks.post).toHaveBeenCalledTimes(1); expect(mocks.post.mock.calls[0][0]).toMatch(/^\/api\/v1\/flavors\/compositions\?operation_id=[0-9a-f-]+$/); expect(mocks.post.mock.calls[0][4].replayOnUnauthorized).toBe(false); expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
		expect(steps).toEqual([2, 1]); stop();
		expect(screen.queryByRole('button', { name: t('composer.saveContinue') })).toBeNull();
		expect(screen.getByRole('button', { name: t('footer.next') })).toBeTruthy();
	});
	it('keeps one busy footer action and never dispatches a repeated click', async () => {
		const pending = Promise.withResolvers<FlavorOption>();
		mocks.post.mockImplementation((_path, _body, _token, _project, opts) => { opts.beforeDispatch(); return pending.promise; });
		let store!: VmCreateStore; render(Harness, { onStore: value => { store = value; } }); await ready();
		const action = screen.getByRole('button', { name: t('composer.saveContinue') });
		await fireEvent.click(action);
		const busy = screen.getByRole('button', { name: t('composer.saving') }) as HTMLButtonElement;
		expect(busy.disabled).toBe(true); expect(busy.getAttribute('aria-busy')).toBe('true');
		await fireEvent.click(busy); expect(await store.composer.save()).toBe(false);
		expect(mocks.post).toHaveBeenCalledTimes(1); expect(get(wizard).step).toBe(2);
		pending.resolve(native()); await waitFor(() => expect(get(wizard).step).toBe(1));
		expect(mocks.post).toHaveBeenCalledTimes(1);
	});
	it('preserves the exact tuple and flavor step after a 409 without replaying the mutation', async () => {
		mocks.post.mockImplementation((_path, _body, _token, _project, opts) => { opts.beforeDispatch(); return Promise.reject(new ApiError(409, 'Another role change is in progress')); });
		let store!: VmCreateStore; render(Harness, { onStore: value => { store = value; } }); await ready();
		await fireEvent.input(quantity('composer.cores'), { target: { value: '6' } });
		await fireEvent.input(quantity('composer.ram'), { target: { value: '8' } });
		await chooseGpu('RTX 6000 rtx-6000'); await ready();
		const tuple = { ...get(store.composer).composition };
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') }));
		await screen.findByText('Another role change is in progress'); await ready();
		expect(get(store.composer).composition).toEqual(tuple); expect(mocks.post.mock.calls[0][1]).toEqual(tuple);
		expect(quantity('composer.cores').value).toBe('6'); expect(quantity('composer.ram').value).toBe('8'); expect(quantity('composer.gpuCount').value).toBe('1');
		expect(get(wizard).step).toBe(2); expect(get(wizard).flavorId).toBeNull(); expect(mocks.post).toHaveBeenCalledTimes(1);
		expect(get(store.composer).unknown).toBe(false);
	});
	it.each(['composer.ram', 'composer.gpuCount'] as const)('blocks the footer and controller from submitting a stale tuple while %s is blank', async label => {
		let store!: VmCreateStore; render(Harness, { onStore: value => { store = value; } }); await ready();
		if (label === 'composer.gpuCount') { await chooseGpu('RTX 6000 rtx-6000'); await ready(); }
		await fireEvent.input(quantity(label), { target: { value: '' } });
		expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		expect(store.composer.canSave()).toBe(false); expect(await store.composer.save()).toBe(false);
		expect(mocks.post).not.toHaveBeenCalled(); expect(get(wizard).step).toBe(2);
	});
	it('clears pending numeric readiness across mode and target lifecycle and fences a late target save', async () => {
		const pending = Promise.withResolvers<FlavorOption>();
		let store!: VmCreateStore; render(Harness, { adminMode: true, onStore: value => { store = value; } });
		await fireEvent.click(screen.getByRole('button', { name: 'Target A' })); await ready();
		await fireEvent.input(quantity('composer.cores'), { target: { value: '' } });
		await fireEvent.click(screen.getByRole('button', { name: t('composer.catalog') }));
		expect(screen.queryByRole('button', { name: t('composer.saveContinue') })).toBeNull();
		expect((screen.getByRole('button', { name: t('footer.next') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('composer.direct') })); await ready();
		expect(quantity('composer.cores').value).toBe('2');
		mocks.post.mockImplementation((_path, _body, _token, _project, opts) => { opts.beforeDispatch(); return pending.promise; });
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') }));
		await fireEvent.click(screen.getByRole('button', { name: 'Target B' })); await ready();
		pending.resolve(native(initialTuple, 'target-a-native')); await tick(); await tick();
		expect(get(wizard).flavorId).toBeNull(); expect(get(wizard).step).toBe(2); expect(store.flavors.some(flavor => flavor.id === 'target-a-native')).toBe(false);
		expect(mocks.post).toHaveBeenCalledTimes(1); expect(get(store.composer).quantityPending).toEqual({ vcpus: false, ram_mb: false, gpu_count: false });
	});
	it('uses conditional exact options, retains an invalid value visibly, and offers a non-authorizing minimum reset', async () => {
		const key = flavorResourceDraftKey(get(auth).userId, 'home', 'project-a', false)!;
		writeResourceDraft(key, { mode: 'compose', selectedId: null, composition: { vcpus: 128, ram_mb: 2097152, gpu_profile_id: null, gpu_count: 0 } });
		currentOptions = () => ({ ...available(), variants: available().variants.map(row => ({ ...row, regions: [], preview: null, status: 'insufficient' as const })) });
		render(Harness); await waitFor(() => expect(quantity('composer.cores').getAttribute('aria-invalid')).toBe('true'));
		expect(quantity('composer.cores').value).toBe('128'); expect(slider('composer.cores').disabled).toBe(true); expect(quantity('composer.ram').value).toBe('2048'); expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('composer.resetResources') })); await tick(); expect(quantity('composer.cores').value).toBe('2'); expect(quantity('composer.ram').value).toBe('1'); expect(screen.getByTestId('native-selected').textContent).toBe('none'); expect(mocks.post).not.toHaveBeenCalled();
	});
	it('synchronizes direct GiB input and discrete slider choices without silently rounding unavailable values', async () => {
		render(Harness); await ready();
		await fireEvent.input(quantity('composer.ram'), { target: { value: '8' } }); await ready();
		expect(slider('composer.ram').getAttribute('aria-valuetext')).toBe('8 GiB');
		await fireEvent.input(slider('composer.ram'), { target: { value: '2' } });
		expect(quantity('composer.ram').value).toBe('4'); expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.change(slider('composer.ram'), { target: { value: '2' } }); await ready();
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') }));
		await waitFor(() => expect(mocks.post.mock.calls[0]?.[1].ram_mb).toBe(4096));
	});
	it.each(['', '0', '1', '1.5', '3', '129'])('blocks an incomplete or out-of-contract CPU input %s from saving the previous tuple', async value => {
		render(Harness); await ready(); await fireEvent.input(quantity('composer.cores'), { target: { value } });
		expect(quantity('composer.cores').getAttribute('aria-invalid')).toBe('true');
		expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') })); expect(mocks.post).not.toHaveBeenCalled();
		await fireEvent.input(quantity('composer.cores'), { target: { value: '6' } }); await ready();
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') })); await waitFor(() => expect(mocks.post.mock.calls[0]?.[1].vcpus).toBe(6));
	});
	it('clears an already selected native flavor when its numeric draft becomes incomplete', async () => {
		render(Harness); await ready(); await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') }));
		await waitFor(() => expect(get(wizard).flavorId).toBe('saved-native'));
		await fireEvent.click(screen.getByRole('button', { name: t('footer.previous') })); await ready();
		await fireEvent.input(quantity('composer.cores'), { target: { value: '' } });
		expect(get(wizard).flavorId).toBeNull(); expect(quantity('composer.cores').value).toBe('');
		expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		expect(mocks.post).toHaveBeenCalledTimes(1);
	});
	it('keeps focused slider editing local and operable with an immediate preview and no GET', async () => {
		render(Harness); await ready(); const reads = mocks.get.mock.calls.filter(([path]) => path.includes('composer-options') || path === '/api/v1/flavors?capacity=create' || path === '/api/v1/dashboard/quotas').length;
		const range = slider('composer.cores'); range.focus(); expect(quantity('composer.cores').step).toBe('2'); expect(quantity('composer.cores').min).toBe('2'); expect(quantity('composer.cores').max).toBe('128');
		await fireEvent.input(range, { target: { value: '2' } });
		expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.change(range, { target: { value: '2' } }); await ready();
		expect(document.activeElement).toBe(range); expect(range.disabled).toBe(false); expect(quantity('composer.cores').value).toBe('6'); expect(mocks.get.mock.calls.filter(([path]) => path.includes('composer-options') || path === '/api/v1/flavors?capacity=create' || path === '/api/v1/dashboard/quotas')).toHaveLength(reads);
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') })); await waitFor(() => expect(mocks.post.mock.calls[0]?.[1].vcpus).toBe(6));
	});
	it('moves only through allowed sparse CPU stops and retains a value after remaining capacity shrinks', async () => {
		let values = [4, 8, 12];
		currentOptions = () => ({ ...available(), variants: available().variants.map(row => ({ ...row, regions: values.map(cpu => ({ vcpus: { min: cpu, max: cpu, step: 2 }, ram_mb: { min: 1024, max: 8192, step: 1024 } })) })) });
		render(Harness); await waitFor(() => expect(quantity('composer.cores').getAttribute('aria-invalid')).toBe('true'));
		await fireEvent.input(slider('composer.cores'), { target: { value: '0' } }); expect(quantity('composer.cores').value).toBe('4');
		await fireEvent.change(slider('composer.cores'), { target: { value: '0' } }); await ready();
		values = [2]; await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await waitFor(() => expect(quantity('composer.cores').getAttribute('aria-invalid')).toBe('true'));
		expect(quantity('composer.cores').value).toBe('4'); expect(slider('composer.cores').disabled).toBe(true);
		await fireEvent.input(quantity('composer.cores'), { target: { value: '2' } }); await ready();
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') })); await waitFor(() => expect(mocks.post.mock.calls[0]?.[1].vcpus).toBe(2));
	});
	it('searches only available GPU models, supports keyboard selection, and keeps a withdrawn count visibly blocked', async () => {
		render(Harness); await ready(); const reads = mocks.get.mock.calls.filter(([path]) => path.includes('composer-options') || path === '/api/v1/flavors?capacity=create' || path === '/api/v1/dashboard/quotas').length;
		await fireEvent.click(screen.getByRole('button', { name: t('composer.gpuType') }));
		expect(screen.queryByRole('option', { name: /Exhausted GPU/ })).toBeNull();
		const search = screen.getByRole('combobox', { expanded: true });
		await fireEvent.input(search, { target: { value: 'rtx-6000' } });
		expect(within(screen.getByRole('listbox')).getAllByRole('option')).toHaveLength(1);
		await fireEvent.keyDown(search, { key: 'Enter' }); await ready();
		expect(quantity('composer.gpuCount').value).toBe('1');
		expect(document.activeElement).toBe(screen.getByRole('button', { name: t('composer.gpuType') }));
		await fireEvent.input(slider('composer.gpuCount'), { target: { value: '2' } }); expect(quantity('composer.gpuCount').value).toBe('3');
		await fireEvent.change(slider('composer.gpuCount'), { target: { value: '2' } }); await ready();
		expect(mocks.get.mock.calls.filter(([path]) => path.includes('composer-options') || path === '/api/v1/flavors?capacity=create' || path === '/api/v1/dashboard/quotas')).toHaveLength(reads);
		currentOptions = () => ({ ...available(), variants: available().variants.map(row => row.gpu_count > 2 ? { ...row, status: 'insufficient' as const, regions: [] } : row) });
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' })); await waitFor(() => expect(quantity('composer.gpuCount').getAttribute('aria-invalid')).toBe('true'));
		expect(quantity('composer.gpuCount').value).toBe('3'); expect(screen.getAllByText(t('composer.unavailable')).length).toBeGreaterThan(0); expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		await chooseGpu(t('composer.noGpu')); await waitFor(() => expect(quantity('composer.gpuCount').value).toBe('0')); expect(quantity('composer.gpuCount').disabled).toBe(true);
	});
	it('freshly POSTs a saved tuple when reused, and keeps unavailable saved rows disabled', async () => {
		const saved = native({ vcpus: 6, ram_mb: 8192, gpu_profile_id: 'rtx-6000', gpu_count: 3 }, 'prior-native'); history = [saved, { ...native(initialTuple, 'blocked'), name: 'blocked', eligibility: null }];
		render(Harness); await ready(); await fireEvent.click(screen.getByRole('button', { name: t('composer.saved') })); await waitFor(() => expect(screen.getAllByRole('button', { name: t('composer.reuse') })).toHaveLength(2));
		const list = within(screen.getByTestId('flavor-composer')).getByRole('list');
		expect(list.textContent).toContain('6 vCPU · 8 GiB RAM · GPU × 3');
		expect(list.innerHTML).not.toContain(saved.name); expect(list.innerHTML).not.toContain(saved.id);
		const buttons = screen.getAllByRole('button', { name: t('composer.reuse') }) as HTMLButtonElement[]; expect(buttons[1].disabled).toBe(true); expect(mocks.post).not.toHaveBeenCalled(); await fireEvent.click(buttons[0]);
		await waitFor(() => expect(screen.getByTestId('native-selected').textContent).toBe('saved-native')); expect(mocks.post.mock.calls[0][1]).toEqual(saved.composition);
	});
	it('keeps the conventional catalog selectable as a secondary mode', async () => {
		inventory = [native(initialTuple, 'manual-native')]; render(Harness); await ready(); await fireEvent.click(screen.getByRole('button', { name: t('composer.catalog') }));
		await fireEvent.click(await screen.findByRole('button', { name: t('flavor.selectLabel', { name: consumerFlavorLabel(inventory[0]) }) })); await waitFor(() => expect(screen.getByTestId('native-selected').textContent).toBe('manual-native')); expect(mocks.post).not.toHaveBeenCalled();
	});
	it('restores resource edits and mode after navigation/reload, does not persist passwords/cloud-init/consent, and clears only on Reset', async () => {
		let view = render(Harness); await ready(); await fireEvent.input(quantity('composer.cores'), { target: { value: '6' } }); await ready();
		wizardPassword.set({ password: 'never-store-this', confirmation: 'never-store-this' }); wizard.update(value => ({ ...value, cloudInit: 'secret-cloud-init', volumeProtectionForce: true }));
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saved') })); view.unmount();
		const key = flavorResourceDraftKey(get(auth).userId, 'home', 'project-a', false)!; const stored = localStorage.getItem(key)!; expect(stored).not.toContain('secret'); expect(stored).not.toContain('never-store'); expect(stored).not.toContain('consent'); expect(stored).not.toContain('volumeProtection');
		view = render(Harness); await waitFor(() => expect(screen.getByRole('button', { name: t('composer.saved') }).getAttribute('aria-pressed')).toBe('true')); await fireEvent.click(screen.getByRole('button', { name: t('composer.direct') })); await ready(); expect(quantity('composer.cores').value).toBe('6'); expect(mocks.post).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'Reset wizard' })); await ready(); expect(quantity('composer.cores').value).toBe('2'); expect(localStorage.getItem(key)).toBeNull();
	});
	it.each(['post', 'receipt', 'unknown'] as const)('fences navigation and alternate native selection while resolution is %s', async phase => {
		const pending = Promise.withResolvers<FlavorOption>();
		const alternate = native(initialTuple, 'alternate-native'); inventory = [alternate];
		if (phase === 'post') mocks.post.mockImplementation((_path, _body, _token, _project, opts) => { opts.beforeDispatch(); return pending.promise; });
		else {
			mocks.post.mockImplementation((_path, _body, _token, _project, opts) => { opts.beforeDispatch(); return Promise.reject(new ApiError(503, 'response lost')); });
			mocks.get.mockImplementation(path => path.includes('/compositions/operations/') ? phase === 'receipt' ? pending.promise : Promise.reject(new ApiError(503, 'receipt unavailable')) : respond(path));
		}
		let store!: VmCreateStore;
		render(Harness, { navigationControls: true, onStore: value => { store = value; } }); await ready();
		const steps: number[] = [];
		const stop = wizard.subscribe(value => { if (steps.at(-1) !== value.step) steps.push(value.step); });
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') }));
		await waitFor(() => expect(phase === 'unknown' ? get(store.composer).unknown : get(store.composer).saving).toBe(true));
		await fireEvent.click(screen.getByRole('button', { name: new RegExp(t('steps.image')) }));
		for (const label of ['Previous step', 'Next step', 'Jump to configuration', 'Jump by visible step', 'Reset wizard', t('composer.catalog')]) {
			await fireEvent.click(screen.getByRole('button', { name: label }));
		}
		store.selectFlavor(alternate.id, alternate.name);
		store.selectImage('unrelated-image', 'Unrelated image');
		expect(get(wizard)).toMatchObject({ step: 2, flavorId: null, imageId: null });
		expect(get(store.composer).mode).toBe('compose');
		expect(mocks.post).toHaveBeenCalledTimes(1);
		if (phase === 'unknown') {
			mocks.get.mockImplementation(path => path.includes('/compositions/operations/') ? Promise.resolve(native()) : respond(path));
			await fireEvent.click(screen.getByRole('button', { name: t('composer.verifySaved') }));
		} else pending.resolve(native());
		await waitFor(() => expect(get(wizard).flavorId).toBe('saved-native'));
		expect(steps).toEqual([2, 1]); stop();
		expect(mocks.post).toHaveBeenCalledTimes(1);
	});
	it('does not select or advance a late completion after external step replacement', async () => {
		const pending = Promise.withResolvers<FlavorOption>();
		mocks.post.mockImplementation((_path, _body, _token, _project, opts) => { opts.beforeDispatch(); return pending.promise; });
		let store!: VmCreateStore; render(Harness, { onStore: value => { store = value; } }); await ready();
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') }));
		wizard.update(value => ({ ...value, step: 5 }));
		pending.resolve(native());
		await waitFor(() => expect(get(store.composer).saving).toBe(false));
		expect(get(wizard)).toMatchObject({ step: 5, flavorId: null });
		expect(store.flavors.some(flavor => flavor.id === 'saved-native')).toBe(false);
		expect(mocks.post).toHaveBeenCalledTimes(1);
	});
	it('continues automatically after a lost response resolves by its exact receipt without another mutation', async () => {
		const receipt = Promise.withResolvers<FlavorOption>();
		mocks.get.mockImplementation(path => path.includes('/compositions/operations/') ? receipt.promise : respond(path));
		mocks.post.mockImplementation((_path, _body, _token, _project, opts) => { opts.beforeDispatch(); return Promise.reject(new ApiError(503, 'response lost')); });
		render(Harness); await ready();
		const steps: number[] = [];
		const stop = wizard.subscribe(value => { if (steps.at(-1) !== value.step) steps.push(value.step); });
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') }));
		await waitFor(() => expect(mocks.get.mock.calls.some(([path]) => path.includes('/compositions/operations/'))).toBe(true));
		expect(get(wizard).step).toBe(2);
		expect((screen.getByRole('button', { name: t('composer.saving') }) as HTMLButtonElement).disabled).toBe(true);
		receipt.resolve(native());
		await waitFor(() => expect(get(wizard).flavorId).toBe('saved-native'));
		expect(steps).toEqual([2, 1]); stop();
		expect(mocks.post).toHaveBeenCalledTimes(1); expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
	});
	it('keeps unknown resolution fenced and selects the exact receipt once on explicit read-only retry', async () => {
		authReady.set(false); render(Harness); await tick(); expect(quantity('composer.cores').disabled).toBe(true); expect(mocks.post).not.toHaveBeenCalled();
		authReady.set(true); await ready();
		let receiptAvailable = false;
		mocks.get.mockImplementation(path => path.includes('/compositions/operations/') ? receiptAvailable ? Promise.resolve(native()) : Promise.reject(new ApiError(503, 'receipt unavailable')) : respond(path));
		mocks.post.mockImplementation((_path, _body, _token, _project, opts) => { opts.beforeDispatch(); return Promise.reject(new ApiError(503, 'unknown')); });
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') }));
		await screen.findByText(t('composer.unknownTitle'));
		expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		expect(mocks.post).toHaveBeenCalledTimes(1);
		receiptAvailable = true;
		await fireEvent.click(screen.getByRole('button', { name: t('composer.verifySaved') }));
		await waitFor(() => expect(get(wizard).flavorId).toBe('saved-native'));
		expect(get(wizard).step).toBe(1);
		expect(mocks.post).toHaveBeenCalledTimes(1);
		const operationId = new URL(mocks.post.mock.calls[0][0], 'https://test.invalid').searchParams.get('operation_id');
		expect(mocks.get.mock.calls.filter(([path]) => path.includes('/compositions/operations/')).map(([path]) => path)).toEqual([
			`/api/v1/flavors/compositions/operations/${operationId}`,
			`/api/v1/flavors/compositions/operations/${operationId}`,
		]);
	});
	it('merges a freshly revalidated saved native flavor when catalog discovery has not caught up, never a stale history row', async () => {
		inventory = [{ ...native(initialTuple), eligibility: null }];
		let store!: VmCreateStore; render(Harness, { onStore: value => { store = value; } }); await ready(); await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') })); await waitFor(() => expect(screen.getByTestId('native-selected').textContent).toBe('saved-native'));
		await store.refreshFlavorOptions('manual'); expect(store.flavors.map(value => value.id)).toContain('saved-native'); expect(store.canNext).toBe(false); // Image has not been selected.
		inventory = [native(initialTuple)]; history = [{ ...history[0], eligibility: null }]; await store.refreshFlavorOptions('manual'); expect(store.selectedFlavorBlock).toBe('unchecked');
		await screen.findByText(t('flavor.selected.unavailableBody', { name: consumerFlavorLabel(native()) }));
		history = []; await store.refreshFlavorOptions('manual'); expect(store.selectedFlavorBlock).toBe('missing');
	});
	it('fences an in-flight save through unmount and does not replay or select it after reopening', async () => {
		const pending = Promise.withResolvers<FlavorOption>();
		mocks.post.mockImplementation((_path, _body, _token, _project, opts) => { opts.beforeDispatch(); return pending.promise; });
		const first = render(Harness); await ready(); await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') }));
		first.unmount(); render(Harness); await tick(); expect(mocks.post).toHaveBeenCalledTimes(1);
		pending.resolve(native()); await ready(); expect(screen.getByTestId('native-selected').textContent).toBe('none'); expect(mocks.post).toHaveBeenCalledTimes(1); expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
	});
	it('clears a closed wizard selection across project changes and restores only the matching project draft', async () => {
		let view = render(Harness); await ready(); await fireEvent.input(quantity('composer.cores'), { target: { value: '6' } }); await ready();
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') })); await waitFor(() => expect(get(wizard).flavorId).toBe('saved-native'));
		const saved = history[0]; closeWizard(); view.unmount();
		auth.update(actor => ({ ...actor, projectId: 'project-b' })); authReady.set(true); history = []; inventory = [saved]; openWizard();
		view = render(Harness); await ready(); expect(get(wizard).flavorId).toBeNull(); expect(screen.getByTestId('can-next').textContent).toBe('no'); expect(quantity('composer.cores').value).toBe('2');
		closeWizard(); view.unmount(); auth.update(actor => ({ ...actor, projectId: 'project-a' })); authReady.set(true); history = [saved]; openWizard();
		render(Harness); await ready(); await waitFor(() => expect(get(wizard).flavorId).toBe('saved-native')); expect(quantity('composer.cores').value).toBe('6'); expect(mocks.post).toHaveBeenCalledTimes(1);
	});
	it('uses exactly one periodic refresh owner for the composed preview and catalog', async () => {
		vi.useFakeTimers(); vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
		render(Harness); await tick(); await vi.advanceTimersByTimeAsync(0);
		const optionsBefore = mocks.get.mock.calls.filter(([path]) => path.includes('composer-options')).length;
		const catalogBefore = mocks.get.mock.calls.filter(([path]) => path === '/api/v1/flavors?capacity=create').length;
		await vi.advanceTimersByTimeAsync(15000);
		expect(mocks.get.mock.calls.filter(([path]) => path.includes('composer-options')).length - optionsBefore).toBe(1);
		expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/flavors?capacity=create').length - catalogBefore).toBe(1);
	});
	it('accepts a pending initial snapshot for the latest numeric draft rather than the initial tuple', async () => {
		const pending = Promise.withResolvers<FlavorComposerSnapshot>();
		mocks.get.mockImplementation(path => path.includes('composer-options') ? pending.promise : respond(path));
		render(Harness); await tick(); await fireEvent.input(quantity('composer.cores'), { target: { value: '6' } });
		expect(quantity('composer.cores').value).toBe('6'); expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		pending.resolve(available()); await ready(); expect(quantity('composer.cores').value).toBe('6'); expect(mocks.get.mock.calls.filter(([path]) => path.includes('composer-options'))).toHaveLength(1);
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') })); await waitFor(() => expect(mocks.post.mock.calls[0]?.[1].vcpus).toBe(6));
	});
	it('retains an old odd CPU draft visibly and disables odd saved compositions until explicit repair', async () => {
		const odd = { ...initialTuple, vcpus: 1 }; const key = flavorResourceDraftKey(get(auth).userId, 'home', 'project-a', false)!;
		writeResourceDraft(key, { mode: 'compose', selectedId: null, composition: odd }); history = [native(odd, 'legacy-native')];
		render(Harness); await waitFor(() => expect(quantity('composer.cores').getAttribute('aria-invalid')).toBe('true')); expect(quantity('composer.cores').value).toBe('1');
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') })); expect(mocks.post).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saved') })); expect((await screen.findByRole('button', { name: t('composer.reuse') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('composer.direct') })); const reads = mocks.get.mock.calls.filter(([path]) => path.includes('composer-options')).length;
		await fireEvent.click(screen.getByRole('button', { name: t('composer.resetResources') })); await ready(); expect(quantity('composer.cores').value).toBe('2'); expect(quantity('composer.ram').value).toBe('1'); expect(mocks.get.mock.calls.filter(([path]) => path.includes('composer-options'))).toHaveLength(reads);
	});
	it('keeps typed odd CPU visible-invalid across RAM and GPU edits without rounding or POST', async () => {
		render(Harness); await ready(); const reads = mocks.get.mock.calls.filter(([path]) => path.includes('composer-options')).length;
		await chooseGpu('RTX 6000 rtx-6000');
		await fireEvent.input(quantity('composer.cores'), { target: { value: '3' } });
		await fireEvent.input(quantity('composer.ram'), { target: { value: '8' } });
		expect(quantity('composer.cores').value).toBe('3'); expect(quantity('composer.cores').getAttribute('aria-invalid')).toBe('true');
		await chooseGpu(t('composer.noGpu'));
		expect(quantity('composer.cores').value).toBe('3'); expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') })); expect(mocks.post).not.toHaveBeenCalled(); expect(mocks.get.mock.calls.filter(([path]) => path.includes('composer-options'))).toHaveLength(reads);
		await fireEvent.input(quantity('composer.cores'), { target: { value: '4' } }); await ready();
		await chooseGpu('RTX 6000 rtx-6000'); await ready();
		await fireEvent.click(screen.getByRole('button', { name: t('composer.saveContinue') })); await waitFor(() => expect(mocks.post.mock.calls[0]?.[1]).toMatchObject({ vcpus: 4, ram_mb: 8192, gpu_profile_id: 'rtx-6000', gpu_count: 1 }));
	});
	it.each(['', '1.5', '129'])('preserves malformed CPU %s through unrelated edits and polling until explicit repair', async value => {
		render(Harness); await ready();
		await fireEvent.input(quantity('composer.cores'), { target: { value } });
		await fireEvent.input(quantity('composer.ram'), { target: { value: '8' } });
		await chooseGpu('RTX 6000 rtx-6000');
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		expect(quantity('composer.cores').value).toBe(value);
		expect(quantity('composer.cores').getAttribute('aria-invalid')).toBe('true');
		expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		expect(mocks.post).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: t('composer.resetResources') })); await ready();
		expect(quantity('composer.cores').value).toBe('2');
	});
	it('reopens normal direct composition without GPU but preserves CPU and RAM', async () => {
		const view = render(Harness); await ready();
		await fireEvent.input(quantity('composer.cores'), { target: { value: '6' } });
		await fireEvent.input(quantity('composer.ram'), { target: { value: '8' } });
		await chooseGpu('RTX 6000 rtx-6000'); await ready();
		view.unmount(); render(Harness); await ready();
		expect(quantity('composer.cores').value).toBe('6'); expect(quantity('composer.ram').value).toBe('8');
		expect(quantity('composer.gpuCount').value).toBe('0'); expect(screen.getByRole('button', { name: t('composer.gpuType') }).textContent).toContain(t('composer.noGpu'));
		expect(mocks.post).not.toHaveBeenCalled();
	});
	it('removes a withdrawn GPU model from search while retaining its named blocking error', async () => {
		render(Harness); await ready(); await chooseGpu('RTX 6000 rtx-6000');
		currentOptions = () => ({ ...available(), gpu_profiles: [] });
		await fireEvent.click(screen.getByRole('button', { name: '지금 새로고침' }));
		await waitFor(() => expect(screen.getAllByText(`rtx-6000 — ${t('composer.unavailable')}`).length).toBeGreaterThan(0));
		expect(quantity('composer.gpuCount').value).toBe('1');
		await fireEvent.click(screen.getByRole('button', { name: t('composer.gpuType') }));
		expect(screen.queryByRole('option', { name: /rtx/i })).toBeNull();
		await fireEvent.keyDown(screen.getByRole('combobox', { expanded: true }), { key: 'Escape' });
		expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		expect(mocks.post).not.toHaveBeenCalled();
	});
	it('keeps unavailable typed GPU counts visible-invalid without turning them into selectable slider stops', async () => {
		render(Harness); await ready(); await chooseGpu('RTX 6000 rtx-6000');
		const reads = mocks.get.mock.calls.length;
		await fireEvent.input(quantity('composer.gpuCount'), { target: { value: '6' } });
		expect(quantity('composer.gpuCount').value).toBe('6'); expect(quantity('composer.gpuCount').getAttribute('aria-invalid')).toBe('true');
		expect(slider('composer.gpuCount').max).toBe('4');
		expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		expect(mocks.get).toHaveBeenCalledTimes(reads); expect(mocks.post).not.toHaveBeenCalled();
	});
	it('repairs a blank GPU count when explicitly switching to another model with the same valid count', async () => {
		currentOptions = () => {
			const snapshot = available();
			snapshot.gpu_profiles.push({ id: 'second', name: 'Second GPU' });
			snapshot.variants.push({ ...snapshot.variants[1], gpu_profile_id: 'second', gpu_count: 1 });
			return snapshot;
		};
		render(Harness); await ready(); await chooseGpu('RTX 6000 rtx-6000'); await ready();
		const reads = mocks.get.mock.calls.length;
		await fireEvent.input(quantity('composer.gpuCount'), { target: { value: '' } });
		expect(quantity('composer.gpuCount').value).toBe('');
		expect((screen.getByRole('button', { name: t('composer.saveContinue') }) as HTMLButtonElement).disabled).toBe(true);
		await chooseGpu('Second GPU second'); await ready();
		expect(quantity('composer.gpuCount').value).toBe('1');
		expect(mocks.get).toHaveBeenCalledTimes(reads); expect(mocks.post).not.toHaveBeenCalled();
	});
});
