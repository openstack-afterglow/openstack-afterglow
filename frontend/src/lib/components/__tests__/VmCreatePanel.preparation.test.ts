import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { closeWizard, openWizard, resetWizard, wizardOpen } from '$lib/stores/wizard';
import { siteConfig } from '$lib/config/site';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/vm-wizard';
import type { FlavorComposerSnapshot, FlavorOption } from '$lib/types/flavor';
import type { ImageInfo } from '$lib/types/compute';
import VmCreatePanel from '../VmCreatePanel.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), fetchWithAuth: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: mocks.post },
	ApiError: class extends Error {},
	fetchWithAuth: mocks.fetchWithAuth,
	getBaseUrl: () => 'https://test.invalid',
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/mockup/transport', () => ({ maybeMockInstanceCreateStream: () => null }));
vi.hoisted(() => {
	vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
});

type Lane = 'resources' | 'history' | 'catalog';
interface Deferred<T> {
	promise: Promise<T>;
	resolve: (value: T | PromiseLike<T>) => void;
	reject: (reason?: unknown) => void;
}
interface Round {
	resources: Deferred<FlavorComposerSnapshot>;
	history: Deferred<{ items: FlavorOption[] }>;
	catalog: Deferred<FlavorOption[]>;
}
function pendingRound() {
	return {
		resources: Promise.withResolvers<FlavorComposerSnapshot>(),
		history: Promise.withResolvers<{ items: FlavorOption[] }>(),
		catalog: Promise.withResolvers<FlavorOption[]>(),
	};
}
let rounds: Map<string, Round>;
let actorNumber = 0;

function snapshot(): FlavorComposerSnapshot {
	return {
		checked_at: '2026-11-01T00:00:00Z', status: 'available', gpu_profiles: [],
		variants: [{
			gpu_profile_id: null, gpu_count: 0, status: 'available', preview: null,
			regions: [{ vcpus: { min: 2, max: 8, step: 2 }, ram_mb: { min: 1024, max: 8192, step: 1024 } }],
		}],
	};
}
function laneFor(path: string): Lane | null {
	const pathname = new URL(path, 'https://test.invalid').pathname;
	if (pathname.endsWith('/composer-options')) return 'resources';
	if (pathname.endsWith('/compositions')) return 'history';
	if (pathname === '/api/v1/flavors') return 'catalog';
	return null;
}
function laneReads(lane: Lane) {
	return mocks.get.mock.calls.filter(([path]) => laneFor(path) === lane).length;
}
function respond(path: string, _token: string, projectId: string) {
	const lane = laneFor(path);
	if (lane) return rounds.get(projectId)![lane].promise;
	if (path === '/api/v1/dashboard/quotas') {
		return Promise.resolve({ native_compute: { instances: { limit: 10, in_use: 0 }, cores: { limit: 16, in_use: 0 }, ram: { limit: 32768, in_use: 0 } } });
	}
	if (path === '/api/v1/networks/default') return Promise.resolve({ network_id: null });
	return Promise.resolve([]);
}
function resolveLane(round: Round, lane: Lane) {
	if (lane === 'resources') round.resources.resolve(snapshot());
	if (lane === 'history') round.history.resolve({ items: [] });
	if (lane === 'catalog') round.catalog.resolve([]);
}
function resolveRound(round: Round) {
	for (const lane of ['resources', 'history', 'catalog'] as const) resolveLane(round, lane);
}
function taskState(id: string) {
	return screen.getByTestId('vm-resource-preparation')
		.querySelector(`[data-preparation-task="${id}"]`)?.getAttribute('data-state');
}
function expectHiddenForm() {
	expect(screen.queryByTestId('flavor-composer')).toBeNull();
	expect(screen.queryByRole('spinbutton', { name: t('composer.cores') })).toBeNull();
}
async function expectForm() {
	await waitFor(() => expect(screen.queryByTestId('vm-resource-preparation')).toBeNull());
	return screen.getByTestId('flavor-composer');
}
async function flush() {
	await tick();
	await vi.advanceTimersByTimeAsync(0);
	await tick();
}

beforeEach(() => {
	actorNumber += 1;
	localStorage.clear();
	resetWizard();
	initLocale('en');
	auth.set({
		...get(auth), token: 'access', sessionId: `preparation-${actorNumber}`, userId: `actor-${actorNumber}`,
		identityDomainId: 'home', domainId: 'domain', projectId: 'project-a',
		isSystemAdmin: false, canWrite: true, roles: ['member'],
	});
	authReady.set(true);
	projectSwitching.set(false);
	logoutInProgress.set(false);
	siteConfig.update(value => ({ ...value, services: { ...value.services, manila: false } }));
	rounds = new Map([['project-a', pendingRound()]]);
	mocks.get.mockReset().mockImplementation(respond);
	mocks.post.mockReset();
	mocks.fetchWithAuth.mockReset();
	openWizard();
});
afterEach(() => {
	cleanup();
	closeWizard();
	authReady.set(false);
	vi.useRealTimers();
	vi.restoreAllMocks();
});

describe('VM create initial resource preparation', () => {
	it('owns the panel edge-to-edge with an accessible overlay close, then restores loaded wizard chrome', async () => {
		const view = render(VmCreatePanel);
		await waitFor(() => expect(laneReads('resources')).toBe(1));
		const preparation = screen.getByTestId('vm-resource-preparation');
		const surface = view.container.querySelector('[data-vm-preparation-surface]')!;
		expect(preparation.parentElement).toBe(surface);
		expect(surface.classList.contains('p-4')).toBe(false);
		expect(surface.classList.contains('md:p-8')).toBe(false);
		expect(view.container.querySelector('.preparation-stage')).toBeNull();
		expect(preparation.querySelector('h2')?.classList.contains('sr-only')).toBe(true);
		expect(preparation.querySelector('#vm-preparation-help')?.classList.contains('sr-only')).toBe(true);
		expect(view.container.querySelector('[data-tour="wizard-stepper"]')).toBeNull();
		expect(view.container.querySelector('[data-tour="wizard-next"]')).toBeNull();
		const close = view.container.querySelector<HTMLButtonElement>('[data-slide-panel-close]')!;
		expect(close.classList.contains('absolute')).toBe(true);
		expect(close.classList.contains('sticky')).toBe(false);
		expect(close.getAttribute('aria-label')).toBeTruthy();
		await tick();
		expect(document.activeElement).toBe(close);
		resolveRound(rounds.get('project-a')!);
		await expectForm();
		expect(view.container.querySelector('[data-vm-preparation-surface]')).toBeNull();
		expect(close.classList.contains('sticky')).toBe(true);
		expect(view.container.querySelector('[data-tour="wizard-stepper"]')).toBeTruthy();
		expect(view.container.querySelector('[data-tour="wizard-next"]')).toBeTruthy();
	});

	it('keeps overlay close and Escape actionable during pending preparation without a cloud mutation', async () => {
		const view = render(VmCreatePanel);
		await waitFor(() => expect(laneReads('resources')).toBe(1));
		await fireEvent.click(view.container.querySelector('[data-slide-panel-close]')!);
		expect(get(wizardOpen)).toBe(false);
		openWizard();
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		expect(get(wizardOpen)).toBe(false);
		expect(mocks.post).not.toHaveBeenCalled();
		expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
	});
	it('preloads images during preparation and reuses them when catalog selection advances to the image step', async () => {
		const images = Promise.withResolvers<ImageInfo[]>();
		mocks.get.mockImplementation((path: string, token: string, projectId: string) =>
			path === '/api/v1/images' ? images.promise : respond(path, token, projectId));
		const round = rounds.get('project-a')!;
		const flavor: FlavorOption = {
			id: 'catalog-cpu', name: 'cpu.2c_4g', vcpus: 2, ram: 4096, disk: 0, is_public: true,
			is_gpu: false, gpu_count: 0, extra_specs: {},
			eligibility: {
				selectable: true, blockers: [],
				requirements: { instances: 1, cores: 2, ram_mb: 4096, gpus: {} },
				remaining: { instances: 10, cores: 16, ram_mb: 32768, gpus: {} },
				capacity: {
					status: 'available', checked_at: '2026-11-01T00:00:00Z', candidate_hosts: 1,
					cpu_resource_class: 'VCPU', remaining_vcpus: 16, remaining_ram_mb: 32768,
				},
			},
		};
		render(VmCreatePanel);
		await waitFor(() => expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/images')).toHaveLength(1));
		expectHiddenForm();
		expect(taskState('resources')).toBe('pending');
		images.resolve([{
			id: 'preloaded-ubuntu', name: 'ubuntu:24.04', repository: 'ubuntu', tag: '24.04',
			status: 'active', os_distro: 'ubuntu', created_at: '2026-11-01T00:00:00Z',
		}]);
		await tick();
		expectHiddenForm();
		round.resources.resolve(snapshot());
		round.history.resolve({ items: [] });
		round.catalog.resolve([flavor]);
		await expectForm();
		await fireEvent.click(screen.getByRole('button', { name: t('composer.catalog') }));
		await fireEvent.click(screen.getByRole('button', { name: t('flavor.selectLabel', { name: '2 vCPU · 4 GiB RAM' }) }));
		const repository = await screen.findByRole('button', { name: t('image.repositoryLabel', { name: 'ubuntu' }) });
		await fireEvent.click(repository);
		expect(screen.getByRole('button', { name: t('image.selectLabel', { name: 'ubuntu:24.04' }) })).toBeTruthy();
		expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/images')).toHaveLength(1);
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('keeps the entire flavor form absent and reports each real pending dependency until the last one settles', async () => {
		const round = rounds.get('project-a')!;
		render(VmCreatePanel);
		await waitFor(() => expect(laneReads('history')).toBe(1));
		expectHiddenForm();
		expect(screen.getByTestId('vm-resource-preparation').querySelector('[data-preparation-lanes]')?.getAttribute('aria-busy')).toBe('true');
		for (const id of ['resources', 'gpu', 'history', 'catalog']) expect(taskState(id)).toBe('pending');
		expect(taskState('auth')).toBeUndefined();
		expect(screen.queryByRole('progressbar')).toBeNull();

		round.resources.resolve(snapshot());
		await waitFor(() => expect(taskState('resources')).toBe('complete'));
		expect(taskState('gpu')).toBe('complete');
		expect(taskState('history')).toBe('pending');
		expect(taskState('catalog')).toBe('pending');
		expectHiddenForm();

		round.history.resolve({ items: [] });
		await waitFor(() => expect(taskState('history')).toBe('complete'));
		expect(taskState('catalog')).toBe('pending');
		expectHiddenForm();

		round.catalog.resolve([]);
		await expectForm();
		expect(screen.getByRole('spinbutton', { name: t('composer.cores') })).toBeTruthy();
		expect(mocks.post).not.toHaveBeenCalled();
		expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
	});

	it('shows authentication as pending without dispatching composer reads until the existing auth barrier opens', async () => {
		authReady.set(false);
		render(VmCreatePanel);
		await tick();
		expectHiddenForm();
		expect(taskState('auth')).toBe('pending');
		expect(laneReads('resources')).toBe(0);
		expect(laneReads('history')).toBe(0);
		resolveRound(rounds.get('project-a')!);
		await tick();
		expectHiddenForm();
		authReady.set(true);
		await expectForm();
		expect(laneReads('resources')).toBe(1);
		expect(laneReads('history')).toBe(1);
	});

	it.each(['resources', 'history', 'catalog'] as const)('makes a failed %s dependency explicit and retries only that lane on user action', async failedLane => {
		const initial = rounds.get('project-a')!;
		render(VmCreatePanel);
		await waitFor(() => expect(laneReads(failedLane)).toBe(1));
		for (const lane of ['resources', 'history', 'catalog'] as const) {
			if (lane === failedLane) initial[lane].reject(new Error('Dependency unavailable'));
			else resolveLane(initial, lane);
		}
		await waitFor(() => expect(taskState(failedLane)).toBe('failed'));
		expectHiddenForm();
		if (failedLane === 'resources') expect(taskState('gpu')).toBe('failed');
		const preparation = screen.getByTestId('vm-resource-preparation');
		expect(within(preparation).getByRole('alert')).toBeTruthy();
		const retry = within(preparation).getByRole<HTMLButtonElement>('button');
		await waitFor(() => expect(retry.disabled).toBe(false));
		const reads = Object.fromEntries((['resources', 'history', 'catalog'] as const).map(lane => [lane, laneReads(lane)]));
		await tick();
		expect(laneReads(failedLane)).toBe(reads[failedLane]);

		const retried = pendingRound();
		rounds.set('project-a', retried);
		await fireEvent.click(retry);
		await waitFor(() => expect(laneReads(failedLane)).toBe(reads[failedLane] + 1));
		expectHiddenForm();
		expect(taskState(failedLane)).toBe('pending');
		for (const lane of ['resources', 'history', 'catalog'] as const) {
			if (lane !== failedLane) expect(laneReads(lane)).toBe(reads[lane]);
		}
		resolveLane(retried, failedLane);
		await expectForm();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('retains the same editable form through pending and failed periodic background refreshes', async () => {
		vi.useFakeTimers();
		vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
		vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
		resolveRound(rounds.get('project-a')!);
		render(VmCreatePanel);
		await flush();
		const form = screen.getByTestId('flavor-composer');
		const cores = screen.getByRole<HTMLInputElement>('spinbutton', { name: t('composer.cores') });
		await fireEvent.input(cores, { target: { value: '6' } });
		const before = { resources: laneReads('resources'), history: laneReads('history'), catalog: laneReads('catalog') };
		const refresh = pendingRound();
		rounds.set('project-a', refresh);
		await vi.advanceTimersByTimeAsync(15000);
		await tick();
		for (const lane of ['resources', 'history', 'catalog'] as const) expect(laneReads(lane)).toBe(before[lane] + 1);
		expect(screen.queryByTestId('vm-resource-preparation')).toBeNull();
		expect(screen.getByTestId('flavor-composer')).toBe(form);
		expect(screen.getByRole('spinbutton', { name: t('composer.cores') })).toBe(cores);
		expect(cores.value).toBe('6');
		refresh.resources.reject(new Error('Background capacity unavailable'));
		refresh.history.reject(new Error('Background history unavailable'));
		refresh.catalog.reject(new Error('Background catalog unavailable'));
		await flush();
		expect(screen.queryByTestId('vm-resource-preparation')).toBeNull();
		expect(screen.getByTestId('flavor-composer')).toBe(form);
		expect(cores.value).toBe('6');
	});

	it('requires fresh preparation after the panel is closed and reopened rather than reusing its old readiness latch', async () => {
		resolveRound(rounds.get('project-a')!);
		const view = render(VmCreatePanel);
		await expectForm();
		closeWizard();
		view.unmount();
		const reopened = pendingRound();
		rounds.set('project-a', reopened);
		openWizard();
		render(VmCreatePanel);
		await waitFor(() => expect(laneReads('resources')).toBe(2));
		expectHiddenForm();
		expect(taskState('resources')).toBe('pending');
		expect(taskState('history')).toBe('pending');
		expect(taskState('catalog')).toBe('pending');
		resolveRound(reopened);
		await expectForm();
	});

	it('resets preparation for a new project scope and ignores late reads from the superseded scope', async () => {
		resolveRound(rounds.get('project-a')!);
		render(VmCreatePanel);
		await expectForm();
		const projectB = pendingRound();
		rounds.set('project-b', projectB);
		auth.update(value => ({ ...value, projectId: 'project-b' }));
		authReady.set(true);
		await waitFor(() => expect(mocks.get.mock.calls.some(([path, , project]) => laneFor(path) === 'history' && project === 'project-b')).toBe(true));
		await waitFor(() => expect(taskState('resources')).toBe('pending'));
		expectHiddenForm();
		const projectC = pendingRound();
		rounds.set('project-c', projectC);
		auth.update(value => ({ ...value, projectId: 'project-c' }));
		authReady.set(true);
		await waitFor(() => expect(mocks.get.mock.calls.some(([path, , project]) => laneFor(path) === 'history' && project === 'project-c')).toBe(true));
		resolveRound(projectB);
		await tick();
		expectHiddenForm();
		expect(taskState('resources')).toBe('pending');
		expect(taskState('history')).toBe('pending');
		expect(taskState('catalog')).toBe('pending');
		resolveRound(projectC);
		await expectForm();
	});
});
