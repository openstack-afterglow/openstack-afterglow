import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '../auth';
import { DEFAULT_BETA_FEATURES, betaFeatures } from '../betaFeatures';
import { resetWizard } from '../wizard';
import { siteConfig } from '$lib/config/site';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
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
		resetWizard();
		betaFeatures.set(DEFAULT_BETA_FEATURES);
		auth.set({ token: 'same-token', refreshToken: null, accessExpiresAt: null, userId: 'user', username: 'user', projectId: 'project-a', projectName: 'Project A', availableProjects: [], roles: [], isSystemAdmin: false, federated: false });
		siteConfig.update(config => ({ ...config, runtime: { ...config.runtime, api_base: 'https://afterglow.test' }, services: { ...config.services, manila: false } }));
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
