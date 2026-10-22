import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type * as ClientModule from '$lib/api/client';
import { ApiError } from '$lib/api/client';
import { auth } from '../auth';
import { DEFAULT_BETA_FEATURES, betaFeatures } from '../betaFeatures';
import { resetWizard, wizard } from '../wizard';
import { siteConfig } from '$lib/config/site';

const { api, fetchWithAuth } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn() }, fetchWithAuth: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/api/client', async (importOriginal) => {
	const actual = await importOriginal<typeof ClientModule>();
	return { ...actual, api, fetchWithAuth };
});
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

function capacityFlavor(id: string, status: 'available' | 'insufficient' | 'unavailable' = 'available') {
	const available = status === 'available';
	return {
		id,
		name: id,
		vcpus: 4,
		ram: 8192,
		disk: 40,
		is_public: true,
		eligibility: {
			selectable: available,
			requirements: { instances: 1, cores: 4, ram_mb: 8192, gpus: {} },
			remaining: { instances: 5, cores: 16, ram_mb: 65536, gpus: {} },
			blockers: available ? [] : [{ code: `host_capacity_${status}` }],
			capacity: {
				status,
				checked_at: '2026-10-01T00:00:00+00:00',
				candidate_hosts: available ? 1 : 0,
				cpu_resource_class: 'VCPU',
				remaining_vcpus: available ? 12 : null,
				remaining_ram_mb: available ? 32768 : null,
			},
		},
	};
}

function flavorCalls(predicate: (path: string) => boolean = path => path === '/api/v1/flavors?capacity=create') {
	return api.get.mock.calls.filter(([path]) => predicate(path));
}

const isAdminFlavorPath = (path: string) => path.includes('/api/v1/admin/instances/flavors-for-project');

function adminApi(flavorsFor: (projectId: string | null) => Promise<unknown>) {
	return (path: string) => {
		if (path === '/api/v1/admin/projects/names') {
			return Promise.resolve([{ id: 'project-a', name: 'Project A' }, { id: 'project-b', name: 'Project B' }]);
		}
		if (isAdminFlavorPath(path)) {
			return flavorsFor(new URL(`https://afterglow.invalid${path}`).searchParams.get('project_id'));
		}
		if (path.startsWith('/api/v1/admin/quotas/')) return Promise.resolve({});
		return Promise.resolve([]);
	};
}

describe('VM create option loading boundaries', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		resetWizard();
		betaFeatures.set(DEFAULT_BETA_FEATURES);
		auth.set({ token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'user', username: 'user', projectId: 'project', projectName: 'project', availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false });
		siteConfig.update(config => ({
			...config,
			services: { ...config.services, manila: true },
		}));
	});
	it('takes ordinary boots through flavor, image, configuration and review with stale beta preferences', async () => {
		localStorage.setItem('afterglow.beta.libraryConsume', 'true');
		localStorage.setItem('afterglow.beta.haDeploy', 'true');
		api.get.mockImplementation((path: string) => Promise.resolve(
			path === '/api/v1/images' ? [image] : path.includes('flavors') ? [capacityFlavor('f1')] : [],
		));
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('f1'));
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		expect(screen.getByTestId('step').textContent).toBe('1');
		await fireEvent.click(screen.getByTestId('select-image'));
		expect(screen.getByTestId('step').textContent).toBe('5');
		wizard.update(w => ({ ...w, keyName: 'key-1' }));
		await vi.waitFor(() => expect(screen.getByTestId('can-next').textContent).toBe('yes'));
		await fireEvent.click(screen.getByTestId('next'));
		expect(screen.getByTestId('step').textContent).toBe('6');
		await fireEvent.click(screen.getByTestId('previous'));
		expect(screen.getByTestId('step').textContent).toBe('5');
		await fireEvent.click(screen.getByTestId('previous'));
		expect(screen.getByTestId('step').textContent).toBe('1');
		expect(api.get.mock.calls.map(([path]) => path).some(path => path.startsWith('/api/v1/libraries'))).toBe(false);
	});



	it('allows flavor selection while the image catalog is still loading', async () => {
		const pendingImages = deferred<typeof image[]>();
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/images') return pendingImages.promise;
			if (path.includes('flavors')) return Promise.resolve([capacityFlavor('f1')]);
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('ready'));
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		expect(screen.getByTestId('step').textContent).toBe('1');
		expect(screen.getByTestId('loading').textContent).toBe('loading');
		pendingImages.resolve([image]);
		await vi.waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('ready'));
		await fireEvent.click(screen.getByTestId('select-image'));
		expect(screen.getByTestId('step').textContent).toBe('5');
	});

	it('starts every public configuration endpoint together at step 5 without making file storage a gate', async () => {
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/images') return Promise.resolve([image]);
			if (path === '/api/v1/volumes') return Promise.resolve([]);
			if (path === '/api/v1/flavors?capacity=create') return Promise.resolve([flavor]);
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
			if (path === '/api/v1/flavors?capacity=create') return Promise.resolve([flavor]);
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
			if (path === '/api/v1/flavors?capacity=create') {
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
			if (path === '/api/v1/flavors?capacity=create' && projectId === 'project-a') {
				projectACalls += 1;
				return projectACalls === 1 ? firstA.promise : secondA.promise;
			}
			if (path === '/api/v1/flavors?capacity=create' && projectId === 'project-b') {
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
			.filter(([path]) => path === '/api/v1/flavors?capacity=create')
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
			if (path === '/api/v1/flavors?capacity=create') return flavors.promise;
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(api.get.mock.calls.some(([path]) => path === '/api/v1/flavors?capacity=create')).toBe(true));

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
			if (path === '/api/v1/flavors?capacity=create') return Promise.resolve([flavor]);
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

	it.each([false, true])('uses create capacity requests and only manual server refresh (admin=%s)', async (adminMode) => {
		const initial = deferred<unknown[]>();
		const periodic = deferred<unknown[]>();
		const manual = deferred<unknown[]>();
		const targetProjectId = 'project/a?x=1';
		const path = adminMode
			? `/api/v1/admin/instances/flavors-for-project?project_id=${encodeURIComponent(targetProjectId)}&capacity=create`
			: '/api/v1/flavors?capacity=create';
		if (adminMode) wizard.update(state => ({ ...state, targetProjectId }));
		let calls = 0;
		api.get.mockImplementation((url: string) => {
			if (url !== path) return Promise.resolve([]);
			calls += 1;
			return [initial.promise, periodic.promise, manual.promise][calls - 1]
				?? Promise.resolve([capacityFlavor('f1', 'insufficient')]);
		});
		render(VmCreateStoreLoadWrapper, { adminMode });
		await fireEvent.click(screen.getByTestId('init'));
		await fireEvent.click(screen.getByTestId('refresh-periodic'));
		expect(calls).toBe(1);
		initial.resolve([capacityFlavor('f1')]);
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('f1'));
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		await fireEvent.click(screen.getByTestId('refresh-periodic'));
		await fireEvent.click(screen.getByTestId('refresh-periodic'));
		expect(calls).toBe(2);
		// selectFlavor advanced past step 2; check the flavor step's own gate while the periodic round is pending.
		await fireEvent.click(screen.getByTestId('step-two'));
		expect(calls).toBe(2);
		expect(screen.getByTestId('background-refreshing').textContent).toBe('refreshing');
		expect(screen.getByTestId('can-next').textContent).toBe('yes');
		await fireEvent.click(screen.getByTestId('refresh-manual'));
		expect(flavorCalls(url => url === path)[1][3].signal.aborted).toBe(true);
		expect(screen.getByTestId('background-refreshing').textContent).toBe('idle');
		await fireEvent.click(screen.getByTestId('refresh-periodic'));
		expect(calls).toBe(3);
		periodic.resolve([capacityFlavor('f1', 'insufficient')]);
		manual.resolve([capacityFlavor('f1')]);
		await vi.waitFor(() => expect(screen.getByTestId('refreshing').textContent).toBe('idle'));
		expect(screen.getByTestId('flavor-block').textContent).toBe('none');
		await fireEvent.click(screen.getByTestId('step-six'));
		await fireEvent.click(screen.getByTestId('deploy'));
		await vi.waitFor(() => expect(screen.getByTestId('step').textContent).toBe('2'));
		const requests = flavorCalls(url => url === path);
		expect(requests.map(([, , , options]) => options)).toEqual([
			{ signal: expect.any(AbortSignal) },
			{ signal: expect.any(AbortSignal) },
			{ signal: expect.any(AbortSignal), refresh: true },
			{ signal: expect.any(AbortSignal) },
		]);
		expect(requests.every(([, token, projectId]) => token === 'token' && projectId === 'project')).toBe(true);
		expect(fetchWithAuth).not.toHaveBeenCalled();
	});

	it('allows selection and progression during periodic refresh and retains a newly blocked selection', async () => {
		const periodic = deferred<unknown[]>();
		let calls = 0;
		api.get.mockImplementation((path: string) => {
			if (path !== '/api/v1/flavors?capacity=create') return Promise.resolve([]);
			return ++calls === 1 ? Promise.resolve([capacityFlavor('f1')]) : periodic.promise;
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('f1'));
		await fireEvent.click(screen.getByTestId('refresh-periodic'));
		expect(screen.getByTestId('background-refreshing').textContent).toBe('refreshing');
		expect(screen.getByTestId('refreshing').textContent).toBe('idle');
		// Selection is not locked by the background refresh (selectFlavor also advances past step 2).
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		expect(screen.getByTestId('selected-flavor').textContent).toBe('f1');
		// Progression from the flavor step is not locked either.
		await fireEvent.click(screen.getByTestId('step-two'));
		expect(screen.getByTestId('can-next').textContent).toBe('yes');
		await fireEvent.click(screen.getByTestId('next'));
		expect(screen.getByTestId('step').textContent).not.toBe('2');
		periodic.resolve([capacityFlavor('f1', 'insufficient'), capacityFlavor('f2')]);
		await vi.waitFor(() => expect(screen.getByTestId('background-refreshing').textContent).toBe('idle'));
		expect(screen.getByTestId('selected-flavor').textContent).toBe('f1');
		expect(screen.getByTestId('flavor-block').textContent).toBe('capacity_insufficient');
		await fireEvent.click(screen.getByTestId('step-six'));
		expect(screen.getByTestId('can-next').textContent).toBe('no');
	});

	it.each(['reset', 'destroy', 'project', 'manual', 'submit'])('keeps a snapshot usable after periodic failure and clears the warning on %s', async (transition) => {
		const periodic = deferred<unknown[]>();
		const nextSnapshot = deferred<unknown[]>();
		let calls = 0;
		api.get.mockImplementation((path: string) => {
			if (path !== '/api/v1/flavors?capacity=create') return Promise.resolve([]);
			calls += 1;
			return calls === 1 ? Promise.resolve([capacityFlavor('f1')]) : calls === 2 ? periodic.promise : nextSnapshot.promise;
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('f1'));
		await fireEvent.click(screen.getByTestId('refresh-periodic'));
		periodic.reject(new ApiError(503, 'placement down'));
		await vi.waitFor(() => expect(screen.getByTestId('background-refresh-error').textContent).toContain('503'));
		expect(screen.getByTestId('background-refreshing').textContent).toBe('idle');
		expect(screen.getByTestId('refresh-error').textContent).toBe('none');
		expect(screen.getByTestId('flavor').textContent).toBe('f1');
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		await fireEvent.click(screen.getByTestId('step-two'));
		expect(screen.getByTestId('can-next').textContent).toBe('yes');
		await fireEvent.click(screen.getByTestId('step-six'));
		expect(screen.getByTestId('can-next').textContent).toBe('yes');
		if (transition === 'project') {
			auth.update(state => ({ ...state, projectId: 'other-project' }));
		} else {
			const action = transition === 'manual' ? 'refresh-manual' : transition === 'submit' ? 'deploy' : transition;
			await fireEvent.click(screen.getByTestId(action));
		}
		await vi.waitFor(() => expect(screen.getByTestId('background-refresh-error').textContent).toBe('none'));
		expect(screen.getByTestId('background-refreshing').textContent).toBe('idle');
		nextSnapshot.resolve([capacityFlavor('f1', 'insufficient')]);
		await Promise.resolve();
		await Promise.resolve();
		expect(fetchWithAuth).not.toHaveBeenCalled();
	});

	it('fences selection during a manual capacity refresh and keeps a newly blocked selection', async () => {
		const refreshed = deferred<unknown[]>();
		let calls = 0;
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/flavors?capacity=create') {
				calls += 1;
				return calls === 1 ? Promise.resolve([capacityFlavor('f1')]) : refreshed.promise;
			}
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('f1'));
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		await fireEvent.click(screen.getByTestId('step-two'));
		expect(screen.getByTestId('step').textContent).toBe('2');
		expect(screen.getByTestId('can-next').textContent).toBe('yes');

		await fireEvent.click(screen.getByTestId('refresh-manual'));
		expect(screen.getByTestId('refreshing').textContent).toBe('refreshing');
		expect(screen.getByTestId('can-next').textContent).toBe('no');
		expect(screen.getByTestId('flavor').textContent).toBe('f1');
		expect(flavorCalls()[1][3]).toEqual(expect.objectContaining({ refresh: true }));

		await fireEvent.click(screen.getByTestId('refresh-periodic'));
		expect(flavorCalls()).toHaveLength(2);

		refreshed.resolve([capacityFlavor('f1', 'insufficient')]);
		await vi.waitFor(() => expect(screen.getByTestId('refreshing').textContent).toBe('idle'));
		expect(screen.getByTestId('selected-flavor').textContent).toBe('f1');
		expect(screen.getByTestId('flavor-block').textContent).toBe('capacity_insufficient');
		expect(screen.getByTestId('can-next').textContent).toBe('no');
	});

	it('blocks progression after a failed manual refresh until a later refresh succeeds', async () => {
		let calls = 0;
		const periodic = deferred<unknown[]>();
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/flavors?capacity=create') {
				calls += 1;
				if (calls === 2) return Promise.reject(new ApiError(503, 'placement down'));
				if (calls === 3) return periodic.promise;
				return Promise.resolve([capacityFlavor('f1')]);
			}
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('f1'));
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		await fireEvent.click(screen.getByTestId('step-two'));

		await fireEvent.click(screen.getByTestId('refresh-manual'));
		await vi.waitFor(() => expect(screen.getByTestId('refresh-error').textContent).toContain('503'));
		expect(screen.getByTestId('flavor').textContent).toBe('f1');
		expect(screen.getByTestId('can-next').textContent).toBe('no');

		await fireEvent.click(screen.getByTestId('refresh-periodic'));
		expect(screen.getByTestId('refresh-error').textContent).toContain('503');
		expect(screen.getByTestId('can-next').textContent).toBe('no');
		periodic.reject(new ApiError(502, 'still down'));
		await vi.waitFor(() => expect(screen.getByTestId('background-refresh-error').textContent).toContain('502'));
		expect(screen.getByTestId('refresh-error').textContent).toContain('503');
		expect(screen.getByTestId('can-next').textContent).toBe('no');
		await fireEvent.click(screen.getByTestId('refresh-periodic'));
		await vi.waitFor(() => expect(screen.getByTestId('refresh-error').textContent).toBe('none'));
		expect(screen.getByTestId('background-refresh-error').textContent).toBe('none');
		expect(screen.getByTestId('can-next').textContent).toBe('yes');
	});

	it.each(['manual', 'periodic'])('drops a late public %s refresh from the previous project after a switch', async (mode) => {
		auth.update(state => ({ ...state, projectId: 'project-a', projectName: 'Project A', token: 'token-a' }));
		const lateA = deferred<unknown[]>();
		let aCalls = 0;
		api.get.mockImplementation((path: string, _token?: string, projectId?: string) => {
			if (path === '/api/v1/flavors?capacity=create' && projectId === 'project-a') {
				aCalls += 1;
				return aCalls === 1 ? Promise.resolve([capacityFlavor('a-1')]) : lateA.promise;
			}
			if (path === '/api/v1/flavors?capacity=create') return Promise.resolve([capacityFlavor('b-1')]);
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('a-1'));
		await fireEvent.click(screen.getByTestId(`refresh-${mode}`));
		const refreshSignal = flavorCalls()[1][3].signal as AbortSignal;

		auth.update(state => ({ ...state, projectId: 'project-b', projectName: 'Project B', token: 'token-b' }));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('b-1'));
		expect(refreshSignal.aborted).toBe(true);
		expect(screen.getByTestId('refreshing').textContent).toBe('idle');
		expect(screen.getByTestId('background-refreshing').textContent).toBe('idle');
		expect(screen.getByTestId('background-refresh-error').textContent).toBe('none');

		lateA.resolve([capacityFlavor('a-late')]);
		await Promise.resolve();
		await Promise.resolve();
		expect(screen.getByTestId('flavor').textContent).toBe('b-1');
	});

	it.each(['manual', 'periodic'])('drops a late admin %s refresh for the previously selected target project', async (mode) => {
		const lateA = deferred<unknown[]>();
		let aCalls = 0;
		api.get.mockImplementation(adminApi((projectId) => {
			if (projectId === 'project-a') {
				aCalls += 1;
				return aCalls === 1 ? Promise.resolve([capacityFlavor('a-1')]) : lateA.promise;
			}
			return Promise.resolve([capacityFlavor('b-1')]);
		}));
		render(VmCreateStoreLoadWrapper, { adminMode: true });
		await fireEvent.click(screen.getByTestId('init'));
		await fireEvent.click(screen.getByTestId('project-a'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('a-1'));
		await fireEvent.click(screen.getByTestId(`refresh-${mode}`));
		expect(flavorCalls(isAdminFlavorPath)[1][0]).toContain('project_id=project-a');

		await fireEvent.click(screen.getByTestId('project-b'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('b-1'));
		lateA.resolve([capacityFlavor('a-late')]);
		await Promise.resolve();
		await Promise.resolve();
		expect(screen.getByTestId('flavor').textContent).toBe('b-1');
		expect(screen.getByTestId('refreshing').textContent).toBe('idle');
		expect(screen.getByTestId('background-refreshing').textContent).toBe('idle');
		expect(screen.getByTestId('background-refresh-error').textContent).toBe('none');
	});

	it.each(['manual', 'periodic'])('aborts and ignores a pending %s capacity refresh after destroy', async (mode) => {
		const late = deferred<unknown[]>();
		let calls = 0;
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/flavors?capacity=create') {
				calls += 1;
				return calls === 1 ? Promise.resolve([capacityFlavor('f1')]) : late.promise;
			}
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('f1'));
		await fireEvent.click(screen.getByTestId(`refresh-${mode}`));
		const signal = flavorCalls()[1][3].signal as AbortSignal;
		await fireEvent.click(screen.getByTestId('destroy'));
		expect(signal.aborted).toBe(true);
		expect(screen.getByTestId('background-refreshing').textContent).toBe('idle');
		expect(screen.getByTestId('background-refresh-error').textContent).toBe('none');
		late.resolve([capacityFlavor('late')]);
		await Promise.resolve();
		await Promise.resolve();
		expect(screen.getByTestId('flavor').textContent).toBe('f1');
	});

	it('revalidates before submit and returns to the flavor step without creating when newly blocked', async () => {
		let calls = 0;
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/flavors?capacity=create') {
				calls += 1;
				return Promise.resolve([capacityFlavor('f1', calls === 1 ? 'available' : 'insufficient')]);
			}
			return Promise.resolve([]);
		});
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('f1'));
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		await fireEvent.click(screen.getByTestId('step-six'));
		expect(screen.getByTestId('can-next').textContent).toBe('yes');

		await fireEvent.click(screen.getByTestId('deploy'));
		await vi.waitFor(() => expect(screen.getByTestId('step').textContent).toBe('2'));
		expect(flavorCalls()).toHaveLength(2);
		expect(fetchWithAuth).not.toHaveBeenCalled();
		expect(screen.getByTestId('selected-flavor').textContent).toBe('f1');
		expect(screen.getByTestId('flavor-block').textContent).toBe('capacity_insufficient');
	});

	it.each([false, true])('blocks stale dispatch when a selected native grant disappears (admin=%s)', async (adminMode) => {
		let calls = 0;
		const snapshots = () => Promise.resolve(++calls === 1 ? [capacityFlavor('private-choice')] : []);
		api.get.mockImplementation(adminMode ? adminApi(() => snapshots()) : (path: string) => path.includes('flavors') ? snapshots() : Promise.resolve([]));
		if (adminMode) wizard.update(state => ({ ...state, targetProjectId: 'project-a' }));
		render(VmCreateStoreLoadWrapper, { adminMode });
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('private-choice'));
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		await fireEvent.click(screen.getByTestId('step-six'));
		await fireEvent.click(screen.getByTestId('deploy'));
		await vi.waitFor(() => expect(screen.getByTestId('step').textContent).toBe('2'));
		expect(screen.getByTestId('selected-flavor').textContent).toBe('private-choice');
		expect(screen.getByTestId('flavor-block').textContent).toBe('missing');
		expect(fetchWithAuth).not.toHaveBeenCalled();
	});


	it('submits only after a fresh snapshot still admits the selection', async () => {
		const submitCheck = deferred<unknown[]>();
		const periodic = deferred<unknown[]>();
		let calls = 0;
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/flavors?capacity=create') {
				calls += 1;
				if (calls === 2) return periodic.promise;
				return calls === 1 ? Promise.resolve([capacityFlavor('f1')]) : submitCheck.promise;
			}
			return Promise.resolve([]);
		});
		fetchWithAuth.mockReturnValue(deferred<Response>().promise);
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('f1'));
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		await fireEvent.click(screen.getByTestId('step-six'));
		await fireEvent.click(screen.getByTestId('refresh-periodic'));

		await fireEvent.click(screen.getByTestId('deploy'));
		expect(flavorCalls()[1][3].signal.aborted).toBe(true);
		expect(screen.getByTestId('background-refreshing').textContent).toBe('idle');
		periodic.reject(new ApiError(503, 'late failure'));
		expect(screen.getByTestId('can-next').textContent).toBe('no');
		await fireEvent.click(screen.getByTestId('deploy'));
		expect(flavorCalls()).toHaveLength(3);
		expect(fetchWithAuth).not.toHaveBeenCalled();

		submitCheck.resolve([capacityFlavor('f1')]);
		await vi.waitFor(() => expect(fetchWithAuth).toHaveBeenCalledTimes(1));
		expect(fetchWithAuth.mock.calls[0][0]).toBe('/api/v1/instances/async');
		expect(screen.getByTestId('background-refresh-error').textContent).toBe('none');
	});

	it('keeps initial and submit failures blocking without creating an instance', async () => {
		let calls = 0;
		api.get.mockImplementation((path: string) => {
			if (path !== '/api/v1/flavors?capacity=create') return Promise.resolve([]);
			calls += 1;
			return calls === 3 ? Promise.resolve([capacityFlavor('f1')]) : Promise.reject(new ApiError(503, 'placement down'));
		});
		wizard.update(state => ({ ...state, step: 2 }));
		render(VmCreateStoreLoadWrapper);
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('ready'));
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		expect(screen.getByTestId('selected-flavor').textContent).toBe('none');
		expect(screen.getByTestId('can-next').textContent).toBe('no');
		await fireEvent.click(screen.getByTestId('refresh-periodic'));
		await vi.waitFor(() => expect(screen.getByTestId('background-refresh-error').textContent).toContain('503'));
		expect(screen.getByTestId('can-next').textContent).toBe('no');
		expect(screen.getByTestId('selected-flavor').textContent).toBe('none');
		await fireEvent.click(screen.getByTestId('refresh-periodic'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('f1'));
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		await fireEvent.click(screen.getByTestId('step-six'));
		await fireEvent.click(screen.getByTestId('deploy'));
		await vi.waitFor(() => expect(screen.getByTestId('step').textContent).toBe('2'));
		expect(screen.getByTestId('refresh-error').textContent).toContain('503');
		expect(screen.getByTestId('can-next').textContent).toBe('no');
		expect(screen.getByTestId('selected-flavor').textContent).toBe('f1');
		expect(fetchWithAuth).not.toHaveBeenCalled();
	});

	it('skips the create mutation when the admin target project changes during submit revalidation', async () => {
		const submitCheck = deferred<unknown[]>();
		let aCalls = 0;
		api.get.mockImplementation(adminApi((projectId) => {
			if (projectId === 'project-a') {
				aCalls += 1;
				return aCalls === 1 ? Promise.resolve([capacityFlavor('a-1')]) : submitCheck.promise;
			}
			return Promise.resolve([capacityFlavor('b-1')]);
		}));
		render(VmCreateStoreLoadWrapper, { adminMode: true });
		await fireEvent.click(screen.getByTestId('init'));
		await fireEvent.click(screen.getByTestId('project-a'));
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('a-1'));
		await fireEvent.click(screen.getByTestId('select-first-flavor'));
		await fireEvent.click(screen.getByTestId('step-six'));
		await fireEvent.click(screen.getByTestId('deploy'));
		await vi.waitFor(() => expect(aCalls).toBe(2));

		await fireEvent.click(screen.getByTestId('project-b'));
		submitCheck.resolve([capacityFlavor('a-1')]);
		await vi.waitFor(() => expect(screen.getByTestId('flavor').textContent).toBe('b-1'));
		await Promise.resolve();
		expect(fetchWithAuth).not.toHaveBeenCalled();
	});
	it('bounds native project quota badge reads to four and rejects same-tick authority ABA', async () => {
		const pending = Array.from({ length: 6 }, () => deferred<unknown>());
		let quotaCalls = 0;
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/projects/names') return Promise.resolve(Array.from({ length: 6 }, (_, index) => ({ id: `project-${index}`, name: `Project ${index}` })));
			if (path.startsWith('/api/v1/admin/quotas/')) return pending[quotaCalls++].promise;
			return Promise.resolve([]);
		});
		const original = { token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'user', username: 'user', projectId: 'project', projectName: 'project', availableProjects: [], roles: [], isSystemAdmin: true, federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false };
		auth.set(original);
		render(VmCreateStoreLoadWrapper, { adminMode: true });
		await fireEvent.click(screen.getByTestId('init'));
		await vi.waitFor(() => expect(quotaCalls).toBe(4));
		auth.set({ ...original, userId: 'replacement' }); auth.set(original);
		const quota = { compute: { instances: { limit: 2, in_use: 0 }, cores: { limit: 2, in_use: 0 }, ram: { limit: 4096, in_use: 0 } }, volume: { gigabytes: { limit: 1024, in_use: 0 } } };
		pending.forEach(request => request.resolve(quota));
		await vi.waitFor(() => expect(screen.getByTestId('admin-quota-loading').textContent).toBe('idle'));
		expect(quotaCalls).toBe(4);
		expect(screen.getByTestId('admin-quota-projects').textContent).toBe('');
		expect(api.get.mock.calls.some(([path]) => path === '/api/v1/admin/overview/projects')).toBe(false);
	});
});
