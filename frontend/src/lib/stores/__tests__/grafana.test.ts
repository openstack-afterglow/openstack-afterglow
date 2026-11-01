// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get, writable } from 'svelte/store';

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
vi.mock('$lib/stores/auth', () => {
	const auth = writable({ token: 'token', projectId: 'project', userId: 'user-a', sessionId: 'session-a', isSystemAdmin: true, roles: ['member'] });
	let epoch = 0;
	auth.subscribe(() => { epoch += 1; });
	return { auth, getAuthVerificationEpoch: () => epoch };
});

type DashboardResponse = { grafana_url: string; dashboards: Record<string, string> };

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void };

function deferred<T>(): Deferred<T> {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((done) => { resolve = done; });
	return { promise, resolve };
}

async function loadStore() {
	// Module reset is intentional: each test needs a fresh module-private scope cache.
	return import('../grafana');
}

beforeEach(() => {
	vi.resetModules();
	apiGet.mockReset();
	mockScope.profile = null;
	mockScope.revision = 0;
	revisionListeners.clear();
});

describe('Grafana context cache', () => {
	it('coalesces an exact scope and returns isolated contexts', async () => {
		const request = deferred<DashboardResponse>();
		apiGet.mockReturnValueOnce(request.promise);
		const { loadGrafanaContext } = await loadStore();

		const first = loadGrafanaContext('token', 'project');
		const second = loadGrafanaContext('token', 'project');
		expect(apiGet).toHaveBeenCalledOnce();
		request.resolve({ grafana_url: 'https://grafana.example.test/', dashboards: { node: 'node-uid' } });
		const [a, b] = await Promise.all([first, second]);

		expect(a).toEqual({ grafanaUrl: 'https://grafana.example.test', dashboards: { node: 'node-uid' } });
		expect(a).not.toBe(b);
		expect(a?.dashboards).not.toBe(b?.dashboards);
		if (a) a.dashboards.node = 'caller-change';
		expect(b?.dashboards.node).toBe('node-uid');
	});

	it('caches a successful empty context for the exact scope', async () => {
		apiGet.mockResolvedValue({ grafana_url: '', dashboards: {} });
		const { loadGrafanaContext } = await loadStore();

		await expect(loadGrafanaContext('token', 'project')).resolves.toBeNull();
		await expect(loadGrafanaContext('token', 'project')).resolves.toBeNull();
		expect(apiGet).toHaveBeenCalledOnce();
	});

	it('separates token, project, profile, and revision scopes', async () => {
		apiGet.mockResolvedValue({ grafana_url: '', dashboards: {} });
		const { loadGrafanaContext } = await loadStore();

		await loadGrafanaContext('a', 'one');
		await loadGrafanaContext('b', 'one');
		await loadGrafanaContext('b', 'two');
		mockScope.profile = 'admin';
		await loadGrafanaContext('b', 'two');
		mockScope.revision += 1;
		await loadGrafanaContext('b', 'two');
		expect(apiGet).toHaveBeenCalledTimes(5);
	});

	it('does not let a slower old scope overwrite a newer context', async () => {
		const oldRequest = deferred<DashboardResponse>();
		const newRequest = deferred<DashboardResponse>();
		apiGet.mockReturnValueOnce(oldRequest.promise).mockReturnValueOnce(newRequest.promise);
		const { grafanaStore, loadGrafanaContext } = await loadStore();

		const oldLoad = loadGrafanaContext('token', 'old');
		const newLoad = loadGrafanaContext('token', 'new');
		newRequest.resolve({ grafana_url: 'https://new.example.test', dashboards: { node: 'new' } });
		await newLoad;
		oldRequest.resolve({ grafana_url: 'https://old.example.test', dashboards: { node: 'old' } });
		await oldLoad;

		expect(get(grafanaStore).ctx?.grafanaUrl).toBe('https://new.example.test');
	});

	it('synchronously fences a pending load on mock reset', async () => {
		const request = deferred<DashboardResponse>();
		apiGet.mockReturnValueOnce(request.promise);
		const { grafanaStore, loadGrafanaContext } = await loadStore();
		const pending = loadGrafanaContext('token', 'project');

		mockScope.revision += 1;
		for (const listener of revisionListeners) listener();
		request.resolve({ grafana_url: 'https://stale.example.test', dashboards: { node: 'stale' } });
		await pending;

		expect(get(grafanaStore)).toEqual({ ctx: null, loading: false, error: false });
	});

	it('keeps failures retryable and explicit invalidation reloads', async () => {
		apiGet
			.mockRejectedValueOnce(new Error('offline'))
			.mockResolvedValue({ grafana_url: 'https://ok.example.test', dashboards: { node: 'ok' } });
		const { invalidateGrafanaContext, loadGrafanaContext } = await loadStore();

		await expect(loadGrafanaContext('token', 'project')).resolves.toBeNull();
		await expect(loadGrafanaContext('token', 'project')).resolves.toMatchObject({ grafanaUrl: 'https://ok.example.test' });
		invalidateGrafanaContext();
		await loadGrafanaContext('token', 'project');
		expect(apiGet).toHaveBeenCalledTimes(3);
	});

	it('starts a fresh real-store catalog after semantic auth A -> B -> A before the old read rejects', async () => {
		const previous = Promise.withResolvers<DashboardResponse>();
		apiGet.mockReturnValueOnce(previous.promise).mockResolvedValue({ grafana_url: 'https://fresh.example.test', dashboards: { node: 'fresh' } });
		const { loadGrafanaContext, grafanaStore } = await loadStore();
		// resetModules intentionally gives the same live auth singleton used by the fresh catalog module.
		const { auth } = await import('../auth');
		const oldLoad = loadGrafanaContext('token', 'project');
		auth.update(state => ({ ...state, projectId: 'other-project' }));
		auth.update(state => ({ ...state, projectId: 'project' }));
		const freshLoad = loadGrafanaContext('token', 'project');
		expect(apiGet).toHaveBeenCalledTimes(2);
		previous.reject(new DOMException('Retired API auth epoch', 'AbortError'));
		await expect(oldLoad).resolves.toBeNull();
		await expect(freshLoad).resolves.toMatchObject({ grafanaUrl: 'https://fresh.example.test' });
		expect(get(grafanaStore).ctx?.grafanaUrl).toBe('https://fresh.example.test');
	});
});
