import { beforeEach, describe, expect, it, vi } from 'vitest';

const { authState, authSubscribers, mockFetch, mockProfile, noMockMatch } = vi.hoisted(() => ({
	authState: {
		value: {
			token: null as string | null,
			refreshToken: null as string | null,
			accessExpiresAt: null as number | null,
			projectId: null as string | null,
		},
	},
	authSubscribers: new Set<(state: {
		token: string | null;
		refreshToken: string | null;
		accessExpiresAt: number | null;
		projectId: string | null;
	}) => void>(),
	mockFetch: vi.fn(),
	mockProfile: { value: null as 'on' | 'admin' | null },
	noMockMatch: Symbol('no-mock-match'),
}));

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/config/site', async () => {
	const { writable } = await import('svelte/store');
	return {
		siteConfig: writable({ runtime: { api_base: 'http://localhost:8000' } }),
	};
});
vi.mock('$lib/stores/auth', () => ({
	auth: {
		subscribe(run: (state: typeof authState.value) => void) {
			authSubscribers.add(run);
			run(authState.value);
			return () => authSubscribers.delete(run);
		},
		update(updater: (state: typeof authState.value) => typeof authState.value) {
			authState.value = updater(authState.value);
			for (const subscriber of authSubscribers) subscriber(authState.value);
		},
	},
	logoutInProgress: {
		subscribe(run: (value: boolean) => void) {
			run(false);
			return () => undefined;
		},
	},
	getMockupProfile: () => mockProfile.value,
	isMockAuthActive: () => mockProfile.value !== null,
	setAuth: vi.fn(),
	clearAuth: vi.fn(),
}));
vi.mock('$lib/mockup/transport', () => ({
	getActiveMockupProfile: () => mockProfile.value,
	maybeMockBlob: vi.fn(async () => noMockMatch),
	maybeMockJson: vi.fn(async () => noMockMatch),
	maybeMockK3sStream: vi.fn(() => null),
	symbolNoMatch: noMockMatch,
}));


vi.stubGlobal('fetch', mockFetch);

type Deferred<T> = {
	promise: Promise<T>;
	resolve: (value: T) => void;
	reject: (reason?: unknown) => void;
};

interface MockJsonResponse<T> {
	ok: boolean;
	status: number;
	statusText: string;
	json: () => Promise<T>;
	text: () => Promise<string>;
}

function deferred<T>(): Deferred<T> {
	return Promise.withResolvers<T>();
}

function jsonResponse<T>(data: T, status = 200): MockJsonResponse<T> {
	return {
		ok: status >= 200 && status < 300,
		status,
		statusText: status >= 200 && status < 300 ? 'OK' : 'Error',
		json: async () => data,
		text: async () => JSON.stringify(data),
	};
}

// Module reset is intentional: every case needs empty module-private request registries.
async function loadClient() {
	return import('../client');
}

beforeEach(() => {
	vi.useRealTimers();
	vi.resetModules();
	mockFetch.mockReset();
	authSubscribers.clear();
	authState.value = {
		token: null,
		refreshToken: null,
		accessExpiresAt: null,
		projectId: null,
	};
	mockProfile.value = null;
});

describe('scoped GET transport', () => {
	it('canonicalizes transport query pairs and preserves logical query order', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ ok: true }));
		const { api } = await loadClient();

		await api.get('/api/v1/items?a=1&cache=false&refresh=false&cache=true&b=2');
		await api.get('/api/v1/items?a=1&cache=true&refresh=true&b=2');

		expect(mockFetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/items?a=1&b=2&cache=true');
		expect(mockFetch.mock.calls[1][0]).toBe('http://localhost:8000/api/v1/items?a=1&b=2&refresh=true');
	});

	it('shares identical ordinary no-signal GETs and isolates every subscriber', async () => {
		const response = deferred<MockJsonResponse<{ rows: number[] }>>();
		mockFetch.mockReturnValueOnce(response.promise);
		const { api } = await loadClient();

		const first = api.get<{ rows: number[] }>('/api/v1/items', 'token', 'project');
		const second = api.get<{ rows: number[] }>('/api/v1/items', 'token', 'project');
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		response.resolve(jsonResponse({ rows: [1] }));

		const [a, b] = await Promise.all([first, second]);
		expect(a).toEqual({ rows: [1] });
		expect(b).toEqual({ rows: [1] });
		expect(a).not.toBe(b);
		a.rows.push(2);
		expect(b.rows).toEqual([1]);
	});

	it('does not join signal-owned ordinary requests', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ ok: true }));
		const { api } = await loadClient();

		await Promise.all([
			api.get('/api/v1/items', undefined, undefined, { signal: new AbortController().signal }),
			api.get('/api/v1/items'),
		]);

		expect(mockFetch).toHaveBeenCalledTimes(2);
	});

	it('rejects an already-aborted visible caller before warm consumption', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ ok: true }));
		const { api } = await loadClient();
		await api.prefetch('/api/v1/items');
		const controller = new AbortController();
		controller.abort();

		await expect(api.get('/api/v1/items', undefined, undefined, { signal: controller.signal }))
			.rejects.toMatchObject({ name: 'AbortError' });
		expect(mockFetch).toHaveBeenCalledOnce();
	});

	it('returns the original only to a joined leader when cloning fails and retries waiters independently', async () => {
		const firstResponse = deferred<MockJsonResponse<{ fn: () => string }>>();
		mockFetch
			.mockReturnValueOnce(firstResponse.promise)
			.mockResolvedValueOnce(jsonResponse({ retried: 1 }))
			.mockResolvedValueOnce(jsonResponse({ retried: 2 }));
		const { api } = await loadClient();
		const original = { fn: () => 'not cloneable' };

		const leader = api.get('/api/v1/uncloneable');
		const waiterA = api.get('/api/v1/uncloneable');
		const waiterB = api.get('/api/v1/uncloneable');
		firstResponse.resolve(jsonResponse(original));

		await expect(leader).resolves.toBe(original);
		await expect(waiterA).resolves.toEqual({ retried: 1 });
		await expect(waiterB).resolves.toEqual({ retried: 2 });
		expect(mockFetch).toHaveBeenCalledTimes(3);
	});
});

describe('explicit scoped prefetch', () => {
	it('reuses a successful warm value without extending it and returns fresh clones', async () => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2026-07-18T00:00:00Z'));
		mockFetch.mockResolvedValue(jsonResponse({ rows: [1] }));
		const { api } = await loadClient();

		await api.prefetch('/api/v1/items', 'token', 'project', { ttlMs: 1_000 });
		vi.advanceTimersByTime(500);
		await api.prefetch('/api/v1/items', 'token', 'project', { ttlMs: 50_000 });
		const first = await api.get<{ rows: number[] }>('/api/v1/items', 'token', 'project');
		const second = await api.get<{ rows: number[] }>('/api/v1/items', 'token', 'project');
		expect(mockFetch).toHaveBeenCalledOnce();
		first.rows.push(2);
		expect(second.rows).toEqual([1]);

		vi.advanceTimersByTime(501);
		await api.get('/api/v1/items', 'token', 'project');
		expect(mockFetch).toHaveBeenCalledTimes(2);
	});

	it('performs ttl zero speculation without publishing', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ ok: true }));
		const { api } = await loadClient();
		await api.prefetch('/api/v1/items', undefined, undefined, { ttlMs: 0 });
		await api.get('/api/v1/items');
		expect(mockFetch).toHaveBeenCalledTimes(2);
	});

	it('does not publish a speculative value that cannot be cloned', async () => {
		mockFetch
			.mockResolvedValueOnce(jsonResponse({ handler: () => 'uncloneable' }))
			.mockResolvedValueOnce(jsonResponse({ source: 'visible' }));
		const { api } = await loadClient();

		await api.prefetch('/api/v1/items');
		await expect(api.get('/api/v1/items')).resolves.toEqual({ source: 'visible' });

		expect(mockFetch).toHaveBeenCalledTimes(2);
	});

	it('shares only identical no-signal speculative identities', async () => {
		const shared = deferred<MockJsonResponse<{ ok: boolean }>>();
		mockFetch
			.mockReturnValueOnce(shared.promise)
			.mockResolvedValue(jsonResponse({ ok: true }));
		const { api } = await loadClient();

		const sameA = api.prefetch('/api/v1/shared', undefined, undefined, { ttlMs: 100 });
		const sameB = api.prefetch('/api/v1/shared', undefined, undefined, { ttlMs: 100 });
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		const differentTtl = api.prefetch('/api/v1/shared', undefined, undefined, { ttlMs: 200 });
		const signalled = api.prefetch('/api/v1/shared', undefined, undefined, {
			ttlMs: 100,
			signal: new AbortController().signal,
		});
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(3));
		shared.resolve(jsonResponse({ ok: true }));
		await Promise.all([sameA, sameB, differentTtl, signalled]);
	});

	it('keeps warm values isolated by token, project, mock profile, and API base URL', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ ok: true }));
		const { api } = await loadClient();
		const { siteConfig } = await import('$lib/config/site');

		await api.prefetch('/api/v1/scoped', 'token-a', 'project-a');
		await api.get('/api/v1/scoped', 'token-b', 'project-a');
		await api.get('/api/v1/scoped', 'token-a', 'project-b');
		mockProfile.value = 'admin';
		await api.get('/api/v1/scoped', 'token-a', 'project-a');
		siteConfig.update((config) => ({
			...config,
			runtime: { ...config.runtime, api_base: 'https://api.example.test' },
		}));
		await api.get('/api/v1/scoped', 'token-a', 'project-a');

		expect(mockFetch).toHaveBeenCalledTimes(5);
		expect(mockFetch.mock.calls[4][0]).toBe('https://api.example.test/api/v1/scoped?cache=true');
	});

	it('lets a redirect-enabled visible GET consume a redirect-suppressed warm success', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ ok: true }));
		const { api } = await loadClient();

		await api.prefetch('/api/v1/items');
		await expect(api.get('/api/v1/items')).resolves.toEqual({ ok: true });

		expect(mockFetch).toHaveBeenCalledOnce();
	});

	it('suppresses speculative 401 handling but preserves normal visible handling', async () => {
		window.history.pushState({}, '', '/dashboard');
		mockFetch.mockResolvedValue(jsonResponse({ detail: 'expired' }, 401));
		const { api } = await loadClient();
		const { clearAuth } = await import('$lib/stores/auth');

		await expect(api.prefetch('/api/v1/items')).resolves.toBeUndefined();
		expect(clearAuth).not.toHaveBeenCalled();

		await expect(api.get('/api/v1/items')).rejects.toMatchObject({ status: 401 });
		await vi.waitFor(() => expect(clearAuth).toHaveBeenCalledOnce());
	});

	it('keeps visible GET independent from pending speculation and fences stale publication', async () => {
		const speculative = deferred<MockJsonResponse<{ source: string }>>();
		mockFetch
			.mockReturnValueOnce(speculative.promise)
			.mockResolvedValueOnce(jsonResponse({ source: 'visible' }))
			.mockResolvedValueOnce(jsonResponse({ source: 'later' }));
		const { api } = await loadClient();

		const prefetch = api.prefetch('/api/v1/items');
		const visible = api.get<{ source: string }>('/api/v1/items');
		await expect(visible).resolves.toEqual({ source: 'visible' });
		speculative.resolve(jsonResponse({ source: 'stale' }));
		await prefetch;
		await expect(api.get('/api/v1/items')).resolves.toEqual({ source: 'later' });
		expect(mockFetch).toHaveBeenCalledTimes(3);
	});

	it('does not publish an aborted mock-insensitive speculation', async () => {
		const speculative = deferred<MockJsonResponse<{ source: string }>>();
		mockFetch
			.mockReturnValueOnce(speculative.promise)
			.mockResolvedValueOnce(jsonResponse({ source: 'visible' }));
		const { api } = await loadClient();
		const controller = new AbortController();
		const prefetch = api.prefetch('/api/v1/items', undefined, undefined, { signal: controller.signal });
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		controller.abort();
		speculative.resolve(jsonResponse({ source: 'cancelled' }));
		await prefetch;

		await expect(api.get('/api/v1/items')).resolves.toEqual({ source: 'visible' });
		expect(mockFetch).toHaveBeenCalledTimes(2);
	});

	it('suppresses speculative failures and refuses refresh paths', async () => {
		mockFetch.mockRejectedValueOnce(new Error('offline'));
		const { api } = await loadClient();
		await expect(api.prefetch('/api/v1/items')).resolves.toBeUndefined();
		await expect(api.prefetch('/api/v1/items?refresh=true')).resolves.toBeUndefined();
		expect(mockFetch).toHaveBeenCalledOnce();
	});

	it('invalidates exact path, mutation, scope, and mock revision values', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ value: 1 }));
		const { api } = await loadClient();
		const { resetMockupState } = await import('$lib/mockup/state');

		await api.prefetch('/api/v1/items?a=1', 'token', 'project');
		api.clearPrefetchCache({ token: 'token', projectId: 'project', path: '/api/v1/items?a=2' });
		await api.get('/api/v1/items?a=1', 'token', 'project');
		expect(mockFetch).toHaveBeenCalledOnce();
		api.clearPrefetchCache({ token: 'token', projectId: 'project', path: '/api/v1/items?a=1' });
		await api.get('/api/v1/items?a=1', 'token', 'project');

		await api.post('/api/v1/items', {}, 'token', 'project');
		await api.get('/api/v1/items?a=1', 'token', 'project');
		await api.prefetch('/api/v1/scoped', 'token', 'project');
		await api.get('/api/v1/scoped', 'token', 'other-project');
		await api.prefetch('/api/v1/reset', 'token', 'project');
		resetMockupState();
		await api.get('/api/v1/reset', 'token', 'project');
		expect(mockFetch).toHaveBeenCalledTimes(8);
	});

	it('evicts normal warm data before an explicit refresh dispatch', async () => {
		mockFetch
			.mockResolvedValueOnce(jsonResponse({ source: 'warm' }))
			.mockResolvedValueOnce(jsonResponse({ source: 'refresh' }))
			.mockResolvedValueOnce(jsonResponse({ source: 'visible' }));
		const { api } = await loadClient();
		await api.prefetch('/api/v1/items', 'token', 'project');

		await expect(api.get('/api/v1/items', 'token', 'project', { refresh: true })).resolves.toEqual({ source: 'refresh' });
		await expect(api.get('/api/v1/items', 'token', 'project')).resolves.toEqual({ source: 'visible' });
		expect(mockFetch).toHaveBeenCalledTimes(3);
	});

	it('fences a speculative response that settles after a mutation', async () => {
		const speculative = deferred<MockJsonResponse<{ source: string }>>();
		mockFetch
			.mockReturnValueOnce(speculative.promise)
			.mockResolvedValueOnce(jsonResponse({ ok: true }))
			.mockResolvedValueOnce(jsonResponse({ source: 'visible' }));
		const { api } = await loadClient();

		const prefetch = api.prefetch('/api/v1/items', 'token', 'project');
		await api.post('/api/v1/items', {}, 'token', 'project');
		speculative.resolve(jsonResponse({ source: 'stale' }));
		await prefetch;

		await expect(api.get('/api/v1/items', 'token', 'project')).resolves.toEqual({ source: 'visible' });
		expect(mockFetch).toHaveBeenCalledTimes(3);
	});

	it('invalidates the observed auth scope when token or project changes', async () => {
		authState.value = {
			token: 'token-a',
			refreshToken: null,
			accessExpiresAt: null,
			projectId: 'project-a',
		};
		mockFetch.mockResolvedValue(jsonResponse({ ok: true }));
		const { api } = await loadClient();
		const { auth } = await import('$lib/stores/auth');

		await api.prefetch('/api/v1/items', 'token-a', 'project-a');
		auth.update((state) => ({ ...state, token: 'token-b' }));
		await api.get('/api/v1/items', 'token-a', 'project-a');

		expect(mockFetch).toHaveBeenCalledTimes(2);
	});

	it('caps active speculative leaders at 64', async () => {
		const pending: Array<Deferred<MockJsonResponse<{ ok: boolean }>>> = [];
		mockFetch.mockImplementation((url: string | URL | Request) => {
			if (String(url).includes('/api/v1/visible')) return Promise.resolve(jsonResponse({ ok: true }));
			const item = deferred<MockJsonResponse<{ ok: boolean }>>();
			pending.push(item);
			return item.promise;
		});
		const { api } = await loadClient();
		const requests = Array.from({ length: 65 }, (_, index) => api.prefetch(`/api/v1/items/${index}`));
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(64));
		await expect(api.get('/api/v1/visible')).resolves.toEqual({ ok: true });
		expect(mockFetch).toHaveBeenCalledTimes(65);
		for (const item of pending) item.resolve(jsonResponse({ ok: true }));
		await Promise.all(requests);
	});

	it('keeps only 64 resolved warm entries', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ ok: true }));
		const { api } = await loadClient();
		for (let index = 0; index < 65; index += 1) {
			await api.prefetch(`/api/v1/items/${index}`);
		}
		await api.get('/api/v1/items/0');
		expect(mockFetch).toHaveBeenCalledTimes(66);
	});
});
