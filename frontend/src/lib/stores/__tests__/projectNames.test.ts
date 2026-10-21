// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
afterEach(() => { vi.restoreAllMocks(); });

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

	it('distinguishes a successful empty directory from failure without breaking map-only callers', async () => {
		apiGet.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce([]);
		const { projectNames } = await loadStore();
		await expect(projectNames.loadResult('token', 'project', 'user')).resolves.toEqual({ names: new Map(), failed: true });
		await expect(projectNames.loadResult('token', 'project', 'user')).resolves.toEqual({ names: new Map(), failed: false });
		await projectNames.loadResult('token', 'project', 'user');
		expect(apiGet).toHaveBeenCalledTimes(2);
	});

	it('coalesces owner requests per user scope and fences a previous user with the same token and project', async () => {
		const old = deferred<ProjectName[]>();
		apiGet.mockReturnValueOnce(old.promise).mockResolvedValueOnce([{ id: 'new', name: 'Current Owner' }]);
		const { projectNames } = await loadStore();
		const pending = projectNames.loadResult('token', 'project', 'old-user');
		const duplicate = projectNames.loadResult('token', 'project', 'old-user');
		expect(apiGet).toHaveBeenCalledOnce();
		const current = await projectNames.loadResult('token', 'project', 'new-user');
		expect(current.names.get('new')).toBe('Current Owner');
		old.resolve([{ id: 'old', name: 'Old Owner' }]);
		const [first, second] = await Promise.all([pending, duplicate]);
		expect(first.names).not.toBe(second.names);
		expect(get(projectNames)).toEqual(new Map([['new', 'Current Owner']]));
		await projectNames.loadResult('token', 'project', 'new-user');
		expect(apiGet).toHaveBeenCalledTimes(2);
	});
	it('shares full project metadata with name-only readers and expires the snapshot after thirty seconds', async () => {
		const clock = vi.spyOn(Date, 'now').mockReturnValue(1_000);
		apiGet.mockResolvedValue([{ id: 'p1', name: 'One', domain_id: 'domain-a' }]);
		const { projectNames } = await loadStore();
		const [names, metadata] = await Promise.all([projectNames.load('token', 'project'), projectNames.loadMetadata('token', 'project')]);
		expect(apiGet).toHaveBeenCalledOnce();
		expect(names.get('p1')).toBe('One');
		expect(metadata.projects).toEqual([{ id: 'p1', name: 'One', domain_id: 'domain-a' }]);
		clock.mockReturnValue(30_999);
		await projectNames.loadMetadata('token', 'project');
		expect(apiGet).toHaveBeenCalledOnce();
		clock.mockReturnValue(31_000);
		await projectNames.loadMetadata('token', 'project');
		expect(apiGet).toHaveBeenCalledTimes(2);
	});

	it('explicit refresh bypasses a pending metadata read and fences its stale publication', async () => {
		const old = deferred<Array<ProjectName & { domain_id: string }>>();
		apiGet.mockReturnValueOnce(old.promise).mockResolvedValueOnce([{ id: 'current', name: 'Current', domain_id: 'domain-b' }]);
		const { projectNames } = await loadStore();
		const pending = projectNames.loadMetadata('token', 'project');
		const refreshed = await projectNames.loadMetadata('token', 'project', undefined, true);
		expect(apiGet).toHaveBeenLastCalledWith('/api/v1/admin/projects/names', 'token', 'project', { refresh: true });
		expect(refreshed.projects[0].id).toBe('current');
		old.resolve([{ id: 'old', name: 'Old', domain_id: 'domain-a' }]);
		await pending;
		expect(get(projectNames)).toEqual(new Map([['current', 'Current']]));
		expect((await projectNames.loadMetadata('token', 'project')).projects[0].id).toBe('current');
	});
});
