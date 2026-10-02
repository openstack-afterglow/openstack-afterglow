import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '../auth';
import { DEFAULT_BETA_FEATURES, betaFeatures } from '../betaFeatures';
import { resetWizard, wizard } from '../wizard';
import { siteConfig } from '$lib/config/site';
import { api } from '$lib/api/client';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/mockup/transport', async (importOriginal) => {
	const actual = await importOriginal<typeof import('$lib/mockup/transport')>();
	return { ...actual, maybeMockInstanceCreateStream: () => null };
});

import VmCreateStoreLoadWrapper from './_VmCreateStoreLoadWrapper.svelte';

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason?: unknown) => void;
	const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
	return { promise, resolve, reject };
}

function jsonResponse(value: unknown): Response {
	return new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

describe('VM create real API-client scope races', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
		api.clearPrefetchCache();
		resetWizard();
		betaFeatures.set(DEFAULT_BETA_FEATURES);
		auth.set({ token: 'same-token', refreshToken: null, accessExpiresAt: null, userId: 'user', username: 'user', projectId: 'project-a', projectName: 'Project A', availableProjects: [], roles: [], isSystemAdmin: false, federated: false });
		siteConfig.update(config => ({ ...config, runtime: { ...config.runtime, api_base: 'https://afterglow.test' }, services: { ...config.services, manila: false } }));
	});

	it.each([false, true])('does not use a warm catalog for create capacity or request server refresh except manually (admin=%s)', async (adminMode) => {
		const targetProjectId = 'project/a?x=1';
		const catalogPath = adminMode
			? `/api/v1/admin/instances/flavors-for-project?project_id=${encodeURIComponent(targetProjectId)}`
			: '/api/v1/flavors';
		const capacityRequests: URL[] = [];
		const catalog = [{ id: 'catalog', name: 'warm-catalog', vcpus: 1, ram: 1024, disk: 20 }];
		const createFlavor = {
			id: 'create', name: 'create-capacity', vcpus: 1, ram: 1024, disk: 20,
			eligibility: {
				selectable: true, blockers: [],
				requirements: { instances: 1, cores: 1, ram_mb: 1024, gpus: {} },
				remaining: { instances: 5, cores: 8, ram_mb: 8192, gpus: {} },
				capacity: {
					status: 'available', checked_at: '2026-10-01T00:00:00+00:00', candidate_hosts: 1,
					cpu_resource_class: 'VCPU', remaining_vcpus: 8, remaining_ram_mb: 8192,
				},
			},
		};
		const createRequests: string[] = [];
		const pendingCreate = deferred<Response>();
		const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
			const url = new URL(String(input));
			if (url.pathname === '/api/v1/instances/async' || url.pathname === '/api/v1/admin/instances/async') {
				createRequests.push(url.pathname);
				return pendingCreate.promise;
			}
			if (url.pathname === '/api/v1/flavors' || url.pathname === '/api/v1/admin/instances/flavors-for-project') {
				if (url.searchParams.get('capacity') !== 'create') return Promise.resolve(jsonResponse(catalog));
				capacityRequests.push(url);
				expect(new Headers(init?.headers).get('X-Project-Id')).toBe('project-a');
				return Promise.resolve(jsonResponse([createFlavor]));
			}
			return Promise.resolve(jsonResponse([]));
		});
		vi.stubGlobal('fetch', fetch);
		await api.prefetch(catalogPath, 'same-token', 'project-a');
		const dispatched = fetch.mock.calls.length;
		expect(await api.get(catalogPath, 'same-token', 'project-a')).toEqual(catalog);
		expect(fetch.mock.calls).toHaveLength(dispatched);
		if (adminMode) wizard.update(state => ({ ...state, targetProjectId }));
		render(VmCreateStoreLoadWrapper, { adminMode });
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('create-capacity'));
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		await fireEvent.click(screen.getByTestId('refresh-periodic'));
		await vi.waitFor(() => expect(screen.getByTestId('background-refreshing').textContent).toBe('idle'));
		await fireEvent.click(screen.getByTestId('refresh-manual'));
		await vi.waitFor(() => expect(screen.getByTestId('refreshing').textContent).toBe('idle'));
		await fireEvent.click(screen.getByTestId('step-six'));
		await fireEvent.click(screen.getByTestId('deploy'));
		await vi.waitFor(() => expect(createRequests).toEqual([adminMode ? '/api/v1/admin/instances/async' : '/api/v1/instances/async']));
		expect(capacityRequests.map(url => url.searchParams.get('refresh'))).toEqual([null, null, 'true', null]);
		if (adminMode) expect(capacityRequests.every(url => url.searchParams.get('project_id') === targetProjectId)).toBe(true);
		await fireEvent.click(screen.getByTestId('destroy'));
		pendingCreate.reject(new DOMException('aborted', 'AbortError'));
	});

	it('cancels the obsolete A request and accepts a fresh A request after A to B to A', async () => {
		const firstA = deferred<Response>();
		const secondA = deferred<Response>();
		let aFlavorCalls = 0;
		const observedSignals: AbortSignal[] = [];
		vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
			const url = new URL(String(input));
			const projectId = new Headers(init?.headers).get('X-Project-Id');
			const signal = init?.signal;
			if (signal) observedSignals.push(signal);
			if (url.pathname === '/api/v1/flavors' && projectId === 'project-a') {
				aFlavorCalls += 1;
				const pending = aFlavorCalls === 1 ? firstA : secondA;
				signal?.addEventListener('abort', () => pending.reject(new DOMException('aborted', 'AbortError')), { once: true });
				return pending.promise;
			}
			if (url.pathname === '/api/v1/flavors' && projectId === 'project-b') {
				return Promise.resolve(jsonResponse([{ id: 'flavor-b', name: 'project-b-flavor', vcpus: 1, ram: 1024, disk: 20 }]));
			}
			if (url.pathname === '/api/v1/dashboard/quotas') {
				return Promise.resolve(jsonResponse({ compute: { cores: { limit: projectId === 'project-b' ? 8 : 4, in_use: 0 } } }));
			}
			return Promise.resolve(jsonResponse([]));
		}));

		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(aFlavorCalls).toBe(1));
		auth.update(state => ({ ...state, projectId: 'project-b', projectName: 'Project B' }));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('project-b-flavor'));
		auth.update(state => ({ ...state, projectId: 'project-a', projectName: 'Project A' }));
		await vi.waitFor(() => expect(aFlavorCalls).toBe(2));
		secondA.resolve(jsonResponse([{ id: 'flavor-a-new', name: 'project-a-new-flavor', vcpus: 2, ram: 2048, disk: 20 }]));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('project-a-new-flavor'));
		expect(observedSignals.some(signal => signal.aborted)).toBe(true);
	});
});
