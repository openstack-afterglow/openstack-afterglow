import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '../auth';
import { DEFAULT_BETA_FEATURES, betaFeatures } from '../betaFeatures';
import { resetWizard } from '../wizard';
import { siteConfig } from '$lib/config/site';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api,
	ApiError: class ApiError extends Error {},
	getBaseUrl: () => '',
}));
vi.mock('$lib/mockup/transport', () => ({ maybeMockInstanceCreateStream: () => null }));

import VmCreateStoreLoadWrapper from './_VmCreateStoreLoadWrapper.svelte';

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason?: unknown) => void;
	const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
	return { promise, resolve, reject };
}

const image = { id: 'image-1', name: 'Ubuntu', status: 'active' };
const flavor = { id: 'flavor-1', name: 'small', vcpus: 1, ram: 1024, disk: 20 };

describe('VM create option loading boundaries', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		resetWizard();
		betaFeatures.set(DEFAULT_BETA_FEATURES);
		auth.set({ token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'user', username: 'user', projectId: 'project', projectName: 'project', availableProjects: [], roles: [], isSystemAdmin: false, federated: false });
		siteConfig.update(config => ({
			...config,
			services: { ...config.services, manila: true },
		}));
	});

	it('prefetches configuration after boot options settle without delaying step 1', async () => {
		const images = deferred<typeof image[]>();
		const volumes = deferred<unknown[]>();
		const flavors = deferred<typeof flavor[]>();
		const quota = deferred<unknown>();
		const configuration = deferred<unknown[]>();
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/images') return images.promise;
			if (path === '/api/v1/volumes') return volumes.promise;
			if (path === '/api/v1/flavors') return flavors.promise;
			if (path === '/api/v1/dashboard/quotas') return quota.promise;
			if (['/api/v1/networks', '/api/v1/keypairs', '/api/v1/security-groups', '/api/v1/networks/default', '/api/v1/file-storage'].includes(path)) return configuration.promise;
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		expect(api.get.mock.calls.map(([path]) => path)).toEqual(expect.arrayContaining([
			'/api/v1/images', '/api/v1/volumes', '/api/v1/flavors', '/api/v1/dashboard/quotas',
		]));
		expect(api.get.mock.calls.map(([path]) => path)).not.toEqual(expect.arrayContaining(['/api/v1/networks', '/api/v1/file-storage', '/api/v1/libraries']));

		images.resolve([image]);
		await Promise.resolve();
		expect(screen.getByTestId('loading').textContent).toBe('loading');
		volumes.resolve([]);
		await vi.waitFor(() => expect(api.get.mock.calls.map(([path]) => path)).toEqual(expect.arrayContaining([
			'/api/v1/networks', '/api/v1/keypairs', '/api/v1/security-groups', '/api/v1/networks/default', '/api/v1/file-storage',
		])));
		expect(screen.getByTestId('loading').textContent).toBe('ready');
		configuration.resolve([]);
		flavors.resolve([flavor]);
		quota.resolve({});
	});

	it('starts every public configuration endpoint together at step 5 without making file storage a gate', async () => {
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/images') return Promise.resolve([image]);
			if (path === '/api/v1/volumes') return Promise.resolve([]);
			if (path === '/api/v1/flavors') return Promise.resolve([flavor]);
			if (path === '/api/v1/dashboard/quotas') return Promise.resolve({});
			if (path === '/api/v1/file-storage') return Promise.reject(new Error('optional'));
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await Promise.resolve();
		await fireEvent.click(screen.getByTestId('step-five'));
		const paths = api.get.mock.calls.map(([path]) => path);
		expect(paths).toEqual(expect.arrayContaining([
			'/api/v1/networks', '/api/v1/keypairs', '/api/v1/security-groups', '/api/v1/networks/default', '/api/v1/file-storage',
		]));
	});

	it('skips the file-storage catalog when Manila is disabled', async () => {
		siteConfig.update(config => ({
			...config,
			services: { ...config.services, manila: false },
		}));
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/images') return Promise.resolve([image]);
			if (path === '/api/v1/volumes') return Promise.resolve([]);
			if (path === '/api/v1/flavors') return Promise.resolve([flavor]);
			if (path === '/api/v1/dashboard/quotas') return Promise.resolve({});
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(api.get.mock.calls.map(([path]) => path)).toContain('/api/v1/networks'));
		expect(api.get.mock.calls.map(([path]) => path)).not.toContain('/api/v1/file-storage');
	});

	it('reloads flavor eligibility and quota when the active project changes while open', async () => {
		auth.update(state => ({ ...state, projectId: 'project-a', projectName: 'Project A', token: 'token-a' }));
		api.get.mockImplementation((path: string, _token?: string, projectId?: string) => {
			if (path === '/api/v1/flavors') {
				return Promise.resolve([{ ...flavor, id: `flavor-${projectId}`, name: `${projectId}-flavor` }]);
			}
			if (path === '/api/v1/dashboard/quotas') {
				return Promise.resolve({ compute: { cores: { limit: projectId === 'project-a' ? 4 : 8, in_use: 0 } } });
			}
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('quota').textContent).toBe('4'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('project-a-flavor'));

		auth.update(state => ({ ...state, projectId: 'project-b', projectName: 'Project B', token: 'token-b' }));

		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('project-b-flavor'));
		await vi.waitFor(() => expect(screen.getByTestId('quota').textContent).toBe('8'));
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/dashboard/quotas').map(([, , projectId]) => projectId))
			.toEqual(['project-a', 'project-b']);
	});

	it('reloads target-project flavors when an administrator changes the selected project', async () => {
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/projects/names') {
				return Promise.resolve([
					{ id: 'project-a', name: 'Project A' },
					{ id: 'project-b', name: 'Project B' },
				]);
			}
			if (path === '/api/v1/admin/overview/projects') return Promise.resolve([]);
			if (path.includes('/api/v1/admin/instances/flavors-for-project')) {
				const projectId = new URL(`https://afterglow.invalid${path}`).searchParams.get('project_id');
				return Promise.resolve([{ ...flavor, id: `flavor-${projectId}`, name: `${projectId}-flavor` }]);
			}
			if (path.startsWith('/api/v1/admin/quotas/')) return Promise.resolve({});
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper, { adminMode: true });
		await fireEvent.click(screen.getByTestId('init'));
		await fireEvent.click(screen.getByTestId('project-a'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('project-a-flavor'));

		await fireEvent.click(screen.getByTestId('project-b'));

		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('project-b-flavor'));
	});

	it('starts a fresh public flavor request for a rapid A to B to A switch', async () => {
		auth.update(state => ({ ...state, projectId: 'project-a', projectName: 'Project A', token: 'token-a' }));
		const firstA = deferred<typeof flavor[]>();
		const secondA = deferred<typeof flavor[]>();
		let projectACalls = 0;
		api.get.mockImplementation((path: string, _token?: string, projectId?: string) => {
			if (path === '/api/v1/flavors' && projectId === 'project-a') {
				projectACalls += 1;
				return projectACalls === 1 ? firstA.promise : secondA.promise;
			}
			if (path === '/api/v1/flavors' && projectId === 'project-b') {
				return Promise.resolve([{ ...flavor, id: 'flavor-b', name: 'project-b-flavor' }]);
			}
			if (path === '/api/v1/dashboard/quotas') return Promise.resolve({});
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(projectACalls).toBe(1));

		auth.update(state => ({ ...state, projectId: 'project-b', projectName: 'Project B', token: 'token-b' }));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('project-b-flavor'));
		auth.update(state => ({ ...state, projectId: 'project-a', projectName: 'Project A', token: 'token-a-2' }));
		await vi.waitFor(() => expect(projectACalls).toBe(2));

		secondA.resolve([{ ...flavor, id: 'flavor-a-new', name: 'project-a-new-flavor' }]);
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('project-a-new-flavor'));
		firstA.resolve([{ ...flavor, id: 'flavor-a-old', name: 'project-a-old-flavor' }]);
		await Promise.resolve();
		expect(screen.getByTestId('flavor').textContent).toBe('project-a-new-flavor');
		const flavorSignals = api.get.mock.calls
			.filter(([path]) => path === '/api/v1/flavors')
			.map(([, , , options]) => options?.signal as AbortSignal);
		expect(flavorSignals).toHaveLength(3);
		expect(flavorSignals[0].aborted).toBe(true);
		expect(flavorSignals[1].aborted).toBe(true);
		expect(flavorSignals[2].aborted).toBe(false);
	});

	it('starts a fresh admin flavor request for a rapid A to B to A switch', async () => {
		const firstA = deferred<typeof flavor[]>();
		const secondA = deferred<typeof flavor[]>();
		let projectACalls = 0;
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/projects/names') {
				return Promise.resolve([
					{ id: 'project-a', name: 'Project A' },
					{ id: 'project-b', name: 'Project B' },
				]);
			}
			if (path === '/api/v1/admin/overview/projects') return Promise.resolve([]);
			if (path.includes('/api/v1/admin/instances/flavors-for-project')) {
				const projectId = new URL(`https://afterglow.invalid${path}`).searchParams.get('project_id');
				if (projectId === 'project-a') {
					projectACalls += 1;
					return projectACalls === 1 ? firstA.promise : secondA.promise;
				}
				return Promise.resolve([{ ...flavor, id: 'flavor-b', name: 'project-b-flavor' }]);
			}
			if (path.startsWith('/api/v1/admin/quotas/')) return Promise.resolve({});
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper, { adminMode: true });
		await fireEvent.click(screen.getByTestId('init'));
		await fireEvent.click(screen.getByTestId('project-a'));
		await vi.waitFor(() => expect(projectACalls).toBe(1));

		await fireEvent.click(screen.getByTestId('project-b'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('project-b-flavor'));
		await fireEvent.click(screen.getByTestId('project-a'));
		await vi.waitFor(() => expect(projectACalls).toBe(2));

		secondA.resolve([{ ...flavor, id: 'flavor-a-new', name: 'project-a-new-flavor' }]);
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('project-a-new-flavor'));
		firstA.resolve([{ ...flavor, id: 'flavor-a-old', name: 'project-a-old-flavor' }]);
		await Promise.resolve();
		expect(screen.getByTestId('flavor').textContent).toBe('project-a-new-flavor');
		const flavorSignals = api.get.mock.calls
			.filter(([path]) => path.includes('/api/v1/admin/instances/flavors-for-project'))
			.map(([, , , options]) => options?.signal as AbortSignal);
		expect(flavorSignals).toHaveLength(3);
		expect(flavorSignals[0].aborted).toBe(true);
		expect(flavorSignals[1].aborted).toBe(true);
		expect(flavorSignals[2].aborted).toBe(false);
	});

	it('aborts project transport and fences late writes after destroy', async () => {
		const images = deferred<typeof image[]>();
		const flavors = deferred<typeof flavor[]>();
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/images') return images.promise;
			if (path === '/api/v1/flavors') return flavors.promise;
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(api.get.mock.calls.some(([path]) => path === '/api/v1/flavors')).toBe(true));

		const projectSignals = api.get.mock.calls
			.map(([, , , options]) => options?.signal as AbortSignal | undefined)
			.filter((signal): signal is AbortSignal => Boolean(signal));
		expect(projectSignals.length).toBeGreaterThan(0);
		await fireEvent.click(screen.getByTestId('destroy'));
		expect(projectSignals.every(signal => signal.aborted)).toBe(true);

		images.resolve([image]);
		flavors.resolve([flavor]);
		await Promise.resolve();
		await Promise.resolve();
		expect(screen.getByTestId('flavor').textContent).toBe('none');
	});

	it('prevents a destroyed store from applying defaults into a reopened wizard', async () => {
		const oldNetworks = deferred<Array<{ id: string; name: string }>>();
		let networkCalls = 0;
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/images') return Promise.resolve([image]);
			if (path === '/api/v1/volumes') return Promise.resolve([]);
			if (path === '/api/v1/flavors') return Promise.resolve([flavor]);
			if (path === '/api/v1/dashboard/quotas') return Promise.resolve({});
			if (path === '/api/v1/networks') {
				networkCalls += 1;
				return networkCalls === 1 ? oldNetworks.promise : Promise.resolve([{ id: 'network-new', name: 'New network' }]);
			}
			if (path === '/api/v1/networks/default') return Promise.resolve({ network_id: 'network-new' });
			return Promise.resolve([]);
		});

		const first = render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(networkCalls).toBe(1));
		await fireEvent.click(screen.getByTestId('destroy'));
		first.unmount();

		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('network').textContent).toBe('New network'));
		oldNetworks.resolve([{ id: 'network-old', name: 'Old network' }]);
		await Promise.resolve();
		await Promise.resolve();
		expect(screen.getByTestId('network').textContent).toBe('New network');
	});
});
