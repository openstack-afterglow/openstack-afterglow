// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

const { apiGet, mockScope, revisionListeners } = vi.hoisted(() => ({
	apiGet: vi.fn(),
	mockScope: { profile: null as 'on' | 'admin' | null, revision: 0 },
	revisionListeners: new Set<() => void>(),
}));

vi.mock('$lib/api/client', () => ({ api: { get: apiGet } }));
vi.mock('$lib/mockup/transport', () => ({
	getActiveMockupProfile: () => mockScope.profile,
}));
vi.mock('$lib/mockup/state', () => ({
	getMockupRevision: () => mockScope.revision,
	onMockupRevisionChange: (listener: () => void) => {
		revisionListeners.add(listener);
		return () => revisionListeners.delete(listener);
	},
}));

type ProjectName = { id: string; name: string };

type Deferred<T> = {
	promise: Promise<T>;
	resolve: (value: T) => void;
};

function deferred<T>(): Deferred<T> {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((done) => { resolve = done; });
	return { promise, resolve };
}

async function loadStore() {
	// Module reset is intentional: each test needs a fresh module-private cache generation.
	return import('../projectNames');
}

beforeEach(() => {
	vi.resetModules();
	apiGet.mockReset();
	mockScope.profile = null;
	mockScope.revision = 0;
	revisionListeners.clear();
});

describe('projectNames store', () => {
	it('loads once per exact scope and returns a fresh map to every caller', async () => {
		apiGet.mockResolvedValue([{ id: 'p1', name: 'Project One' }]);
		const { projectNames } = await loadStore();

		const first = await projectNames.load('token', 'project');
		const second = await projectNames.load('token', 'project');

		expect(apiGet).toHaveBeenCalledOnce();
		expect(apiGet).toHaveBeenCalledWith('/api/v1/admin/projects/names', 'token', 'project');
		expect(first).toEqual(new Map([['p1', 'Project One']]));
		expect(second).toEqual(first);
		expect(second).not.toBe(first);
		(first as Map<string, string>).set('p2', 'Caller mutation');
		expect(get(projectNames)).toEqual(new Map([['p1', 'Project One']]));
	});

	it('coalesces an exact pending scope while isolating returned maps', async () => {
		const request = deferred<ProjectName[]>();
		apiGet.mockReturnValueOnce(request.promise);
		const { projectNames } = await loadStore();

		const first = projectNames.load('token', 'project');
		const second = projectNames.load('token', 'project');
		expect(apiGet).toHaveBeenCalledOnce();
		request.resolve([{ id: 'p1', name: 'One' }]);
		const [a, b] = await Promise.all([first, second]);
		expect(a).not.toBe(b);
	});

	it('separates token, project, mock profile, and mock revision scopes', async () => {
		apiGet.mockResolvedValue([{ id: 'p1', name: 'One' }]);
		const { projectNames } = await loadStore();

		await projectNames.load('token-a', 'project-a');
		await projectNames.load('token-b', 'project-a');
		await projectNames.load('token-b', 'project-b');
		mockScope.profile = 'admin';
		await projectNames.load('token-b', 'project-b');
		mockScope.revision += 1;
		await projectNames.load('token-b', 'project-b');

		expect(apiGet).toHaveBeenCalledTimes(5);
	});

	it('generation-fences a slower old scope from overwriting a newer scope', async () => {
		const oldRequest = deferred<ProjectName[]>();
		const newRequest = deferred<ProjectName[]>();
		apiGet.mockReturnValueOnce(oldRequest.promise).mockReturnValueOnce(newRequest.promise);
		const { projectNames } = await loadStore();

		const oldLoad = projectNames.load('token', 'old-project');
		const newLoad = projectNames.load('token', 'new-project');
		newRequest.resolve([{ id: 'new', name: 'New' }]);
		await newLoad;
		oldRequest.resolve([{ id: 'old', name: 'Old' }]);
		await oldLoad;

		expect(get(projectNames)).toEqual(new Map([['new', 'New']]));
	});

	it('fences a pending result when mock state resets', async () => {
		const request = deferred<ProjectName[]>();
		apiGet.mockReturnValueOnce(request.promise);
		const { projectNames } = await loadStore();
		const pending = projectNames.load('token', 'project');

		mockScope.revision += 1;
		for (const listener of revisionListeners) listener();
		request.resolve([{ id: 'stale', name: 'Stale' }]);
		await pending;

		expect(get(projectNames).size).toBe(0);
	});

	it('keeps failures retryable', async () => {
		apiGet
			.mockRejectedValueOnce(new Error('offline'))
			.mockResolvedValueOnce([{ id: 'p1', name: 'Recovered' }]);
		const { projectNames } = await loadStore();

		await expect(projectNames.load('token', 'project')).resolves.toEqual(new Map());
		await expect(projectNames.load('token', 'project')).resolves.toEqual(new Map([['p1', 'Recovered']]));
		expect(apiGet).toHaveBeenCalledTimes(2);
	});

	it('invalidates only the captured exact scope', async () => {
		apiGet.mockResolvedValue([
			{ id: 'p1', name: 'One' },
		]);
		const { projectNames } = await loadStore();
		const oldScope = projectNames.scope('token', 'old-project');
		await projectNames.load('token', 'old-project');
		await projectNames.load('token', 'new-project');

		projectNames.invalidate(oldScope);
		expect(get(projectNames)).toEqual(new Map([['p1', 'One']]));
		await projectNames.load('token', 'new-project');
		expect(apiGet).toHaveBeenCalledTimes(2);

		projectNames.invalidate();
		expect(get(projectNames).size).toBe(0);
		await projectNames.load('token', 'new-project');
		expect(apiGet).toHaveBeenCalledTimes(3);
	});
});
