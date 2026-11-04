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
	projectSwitching: { subscribe: (run: (switching: boolean) => void) => { run(false); return () => {}; } },
	getAuthVerificationEpoch: () => 0,
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

	it.each(['leader', 'waiter'])('cancels only the %s while another reader receives an independent snapshot', async cancelledReader => {
		const response = deferred<MockJsonResponse<{ rows: number[] }>>();
		mockFetch.mockReturnValueOnce(response.promise);
		const { api } = await loadClient();
		const leader = new AbortController();
		const waiter = new AbortController();
		const first = api.get<{ rows: number[] }>('/api/v1/items', 'token', 'project', { signal: leader.signal });
		const second = api.get<{ rows: number[] }>('/api/v1/items', 'token', 'project', { signal: waiter.signal });
		const rejected = expect(cancelledReader === 'leader' ? first : second).rejects.toMatchObject({ name: 'AbortError' });
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		(cancelledReader === 'leader' ? leader : waiter).abort();
		await rejected;
		response.resolve(jsonResponse({ rows: [1, 2] }));
		await expect(cancelledReader === 'leader' ? second : first).resolves.toEqual({ rows: [1, 2] });
		expect(mockFetch).toHaveBeenCalledOnce();
	});

	it('queues one forced refresh after an ordinary read and isolates cancelled force subscribers', async () => {
		const old = deferred<MockJsonResponse<{ revision: string }>>();
		const fresh = deferred<MockJsonResponse<{ revision: string }>>();
		mockFetch.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
		const { api } = await loadClient();
		const ordinary = api.get('/api/v1/items', 'token', 'project');
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		const cancelled = new AbortController();
		const first = api.get('/api/v1/items', 'token', 'project', { refresh: true, signal: cancelled.signal });
		const rejected = expect(first).rejects.toMatchObject({ name: 'AbortError' });
		const refreshed = Array.from({ length: 8 }, () => api.get('/api/v1/items', 'token', 'project', { refresh: true }));
		const joined = api.get('/api/v1/items', 'token', 'project');
		cancelled.abort();
		await rejected;
		expect(mockFetch).toHaveBeenCalledOnce();
		old.resolve(jsonResponse({ revision: 'old' }));
		await expect(ordinary).resolves.toEqual({ revision: 'old' });
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
		fresh.resolve(jsonResponse({ revision: 'current' }));
		for (const result of await Promise.all([...refreshed, joined])) expect(result).toEqual({ revision: 'current' });
		expect(mockFetch).toHaveBeenCalledTimes(2);
	});

	it('detaches pre-mutation pending reads before a post-mutation read', async () => {
		const old = deferred<MockJsonResponse<{ revision: string }>>();
		mockFetch.mockReturnValueOnce(old.promise)
			.mockResolvedValueOnce(jsonResponse({ updated: true }))
			.mockResolvedValueOnce(jsonResponse({ revision: 'current' }));
		const { api } = await loadClient();
		const pending = api.get('/api/v1/items', 'token', 'project');
		const rejected = expect(pending).rejects.toMatchObject({ name: 'AbortError' });
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		await api.post('/api/v1/items', { update: true }, 'token', 'project');
		await expect(api.get('/api/v1/items', 'token', 'project')).resolves.toEqual({ revision: 'current' });
		old.resolve(jsonResponse({ revision: 'old' }));
		await rejected;
		expect(mockFetch).toHaveBeenCalledTimes(3);
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

describe('explicit semantic read contexts preserve physical cache/coalescing truth', () => {
	async function observe(getOwner: () => { token: string | null; userId: string | null; domainId: string | null; projectId: string | null } = () => ({ token: null, userId: null, domainId: null, projectId: null })) {
		// Module reset above isolates private cache registries; collector must share that fresh module instance.
		const experience = await import('$lib/utils/experience');
		const collector = experience.installExperienceCollector({
			getOwner,
			getRoute: () => '/login', getBaseUrl: () => 'http://localhost:8000',
			isEnabled: () => true, isSuppressed: () => false, subscribeOwner: () => () => {},
		});
		const events = () => mockFetch.mock.calls.filter(([url]) => String(url).endsWith('/experience-events')).flatMap(([, init]) => JSON.parse(init.body).events);
		return { ...experience, collector, events };
	}
	function telemetry(url: string, init?: RequestInit) {
		if (url.endsWith('/experience-contract')) return Response.json({ schema_version: 2, enabled: true, redaction_revision: 1, max_batch_events: 20, max_body_bytes: 32768 });
		const count = JSON.parse(String(init?.body)).events.length;
		return Response.json({ schema_version: 2, accepted: count, duplicates: 0 }, { status: 201 });
	}
	it('coalesces two explicit action consumers into one unlinked physical span and records both safe links', async () => {
		const pending = Promise.withResolvers<Response>();
		mockFetch.mockImplementation((url, init) => String(url).includes('/activity/experience-') ? Promise.resolve(telemetry(String(url), init)) : pending.promise);
		const { api } = await loadClient();
		const tracing = await observe();
		try {
			const one = tracing.beginExperienceAction('compute', 'refresh', 'resource.list')!;
			const two = tracing.beginExperienceAction('compute', 'load', 'resource.list')!;
			const a = api.withExperience(one).get('/api/v1/items');
			const b = api.withExperience(two).get('/api/v1/items');
			await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
			const headers = new Headers(mockFetch.mock.calls[0][1].headers);
			expect(headers.has('X-Afterglow-Experience-Action')).toBe(false);
			pending.resolve(Response.json({ values: ['safe'] })); const [left, right] = await Promise.all([a, b]);
			expect(left).toEqual(right); expect(left).not.toBe(right);
			await tracing.collector.flush();
			const links = tracing.events().filter(row => row.action_id && row.event_type === 'result.received');
			expect(links).toHaveLength(2);
			expect(new Set(links.map(row => row.payload.transport))).toEqual(new Set(['network', 'shared']));
			expect(links.every(row => row.payload.physical_span_id === headers.get('X-Afterglow-Experience-Span'))).toBe(true);
			expect(tracing.events().some(row => row.event_type === 'result.applied' || row.event_type === 'result.committed')).toBe(false);
			expect(mockFetch.mock.calls.filter(([url]) => String(url).includes('/api/v1/items'))).toHaveLength(1);
		} finally { tracing.collector.destroy(); }
	});
	it.each([false, true])('links both failed shared GET consumers to the received physical response without changing rejection or dispatches (refresh=%s)', async refresh => {
		const pending = Promise.withResolvers<Response>();
		mockFetch.mockImplementation((url, init) => String(url).includes('/activity/experience-') ? Promise.resolve(telemetry(String(url), init)) : pending.promise);
		const { api } = await loadClient();
		const tracing = await observe();
		try {
			const one = tracing.beginExperienceAction('iam', 'refresh', 'resource.list')!;
			const two = tracing.beginExperienceAction('iam', 'load', 'resource.list')!;
			const a = api.withExperience(one).get('/api/v1/auth/workspaces', undefined, undefined, { refresh });
			const b = api.withExperience(two).get('/api/v1/auth/workspaces', undefined, undefined, { refresh });
			const settled = Promise.allSettled([a, b]);
			await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
			const headers = new Headers(mockFetch.mock.calls[0][1].headers);
			const requestId = 'req-1234567890abcdef1234567890abcdef';
			pending.resolve(Response.json({ detail: 'private-directory-error' }, { status: 503, headers: { 'X-Request-Id': requestId } }));
			const [left, right] = await settled;
			expect(left.status).toBe('rejected'); expect(right.status).toBe('rejected');
			if (left.status !== 'rejected' || right.status !== 'rejected') throw new Error('Expected both original HTTP failures');
			expect(left.reason).toBe(right.reason);
			expect(left.reason).toMatchObject({ status: 503, message: 'private-directory-error' });
			await tracing.collector.flush();
			const physical = tracing.events().find(row => !row.action_id && row.event_type === 'result.received' && row.span_id === headers.get('X-Afterglow-Experience-Span'));
			expect(physical.payload).toMatchObject({ request_id: requestId, http_status: 503 });
			const links = tracing.events().filter(row => row.action_id && row.event_type === 'result.received');
			expect(links).toHaveLength(2);
			expect(new Set(links.map(row => row.action_id))).toEqual(new Set([one.actionId, two.actionId]));
			expect(new Set(links.map(row => row.payload.transport))).toEqual(new Set(['network', 'shared']));
			for (const link of links) {
				expect(link.payload).toMatchObject({ physical_span_id: physical.span_id, http_status: 503, stage: 'response' });
				expect(link.segment_id).toBe(physical.segment_id);
				expect(link.page_view_id).toBe(physical.page_view_id);
			}
			expect(tracing.events().some(row => row.event_type === 'result.applied' || row.event_type === 'result.committed')).toBe(false);
			expect(JSON.stringify(tracing.events())).not.toContain('private-directory-error');
			expect(mockFetch.mock.calls.filter(([url]) => String(url).includes('/api/v1/auth/workspaces'))).toHaveLength(1);
		} finally { tracing.collector.destroy(); }
	});
	it('preserves a rejected shared transport error without inventing received-response links', async () => {
		const pending = Promise.withResolvers<Response>();
		mockFetch.mockImplementation((url, init) => String(url).includes('/activity/experience-') ? Promise.resolve(telemetry(String(url), init)) : pending.promise);
		const { api } = await loadClient(); const tracing = await observe();
		try {
			const one = tracing.beginExperienceAction('iam', 'load', 'resource.list')!;
			const two = tracing.beginExperienceAction('iam', 'load', 'resource.list')!;
			const settled = Promise.allSettled([api.withExperience(one).get('/api/v1/items'), api.withExperience(two).get('/api/v1/items')]);
			await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
			const error = new TypeError('private-network-failure'); pending.reject(error);
			for (const result of await settled) { expect(result.status).toBe('rejected'); if (result.status === 'rejected') expect(result.reason).toBe(error); }
			await tracing.collector.flush();
			expect(tracing.events().some(row => row.event_type === 'result.received')).toBe(false);
			expect(mockFetch.mock.calls.filter(([url]) => String(url).includes('/api/v1/items'))).toHaveLength(1);
		} finally { tracing.collector.destroy(); }
	});
	it.each(['owner_changed', 'destroyed'] as const)('keeps failed shared response links behind the existing collector %s fence', async boundary => {
		const pending = Promise.withResolvers<Response>();
		mockFetch.mockImplementation((url, init) => String(url).includes('/activity/experience-') ? Promise.resolve(telemetry(String(url), init)) : pending.promise);
		const { api } = await loadClient();
		let userId: string | null = null;
		const tracing = await observe(() => ({ token: null, userId, domainId: null, projectId: null }));
		try {
			const one = tracing.beginExperienceAction('iam', 'load', 'resource.list')!;
			const two = tracing.beginExperienceAction('iam', 'load', 'resource.list')!;
			const settled = Promise.allSettled([api.withExperience(one).get('/api/v1/items'), api.withExperience(two).get('/api/v1/items')]);
			await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
			if (boundary === 'owner_changed') { userId = 'private-new-owner'; tracing.collector.syncOwner(); }
			else tracing.collector.destroy();
			pending.resolve(Response.json({ detail: 'private-late-error' }, { status: 503 }));
			for (const result of await settled) { expect(result.status).toBe('rejected'); if (result.status === 'rejected') expect(result.reason).toMatchObject({ status: 503 }); }
			await tracing.collector.flush();
			expect(tracing.events().some(row => row.action_id === one.actionId || row.action_id === two.actionId)).toBe(false);
			expect(mockFetch.mock.calls.filter(([url]) => String(url).includes('/api/v1/items'))).toHaveLength(1);
		} finally { tracing.collector.destroy(); }
	});
	it('keeps prefetched warm reads off the network and labels cache receipt without fake HTTP/server references', async () => {
		mockFetch.mockImplementation((url, init) => Promise.resolve(String(url).includes('/activity/experience-') ? telemetry(String(url), init) : Response.json({ nested: { safe: true } })));
		const { api } = await loadClient(); const tracing = await observe();
		try {
			await api.prefetch('/api/v1/items');
			const ctx = tracing.beginExperienceAction('compute', 'load', 'resource.list')!;
			await api.withExperience(ctx).get('/api/v1/items');
			await tracing.collector.flush();
			const cached = tracing.events().find(row => row.action_id === ctx.actionId && row.event_type === 'result.received');
			expect(cached.payload).toEqual({ transport: 'cache', stage: 'response' });
			expect(mockFetch.mock.calls.filter(([url]) => String(url).includes('/api/v1/items'))).toHaveLength(1);
		} finally { tracing.collector.destroy(); }
	});
	it('retains forced/no-store request policy and non-replay mutation options with a bound context', async () => {
		mockFetch.mockImplementation((url, init) => Promise.resolve(String(url).includes('/activity/experience-') ? telemetry(String(url), init) : Response.json({ ok: true }, { status: 202 })));
		const { api } = await loadClient(); const tracing = await observe();
		try {
			const ctx = tracing.beginExperienceAction('compute', 'create', 'compute.create')!;
			const bound = api.withExperience(ctx);
			await bound.get('/api/v1/items', undefined, undefined, { refresh: true });
			await bound.get('/api/v1/items', undefined, undefined, { cache: 'no-store', replayOnUnauthorized: false });
			const beforeDispatch = vi.fn();
			await bound.post('/api/v1/items', { secret: 'private-body' }, undefined, undefined, { replayOnUnauthorized: false, beforeDispatch });
			expect(beforeDispatch).toHaveBeenCalled();
			const business = mockFetch.mock.calls.filter(([url]) => String(url).includes('/api/v1/items'));
			expect(business).toHaveLength(3); expect(String(business[0][0])).toContain('refresh=true');
			expect(business[1][1].cache).toBe('no-store'); expect(business[2][1].method).toBe('POST');
			expect(new Headers(business[2][1].headers).get('X-Afterglow-Experience-Action')).toBe(ctx.actionId);
			await tracing.collector.flush();
			expect(JSON.stringify(tracing.events())).not.toContain('private-body');
			expect(tracing.events().some(row => row.event_type === 'result.committed')).toBe(false);
		} finally { tracing.collector.destroy(); }
	});
	it('links an independently re-read clone-fallback waiter to its own physical request rather than the original dispatch', async () => {
		let reads = 0;
		mockFetch.mockImplementation((url, init) => {
			if (String(url).includes('/activity/experience-')) return Promise.resolve(telemetry(String(url), init));
			++reads;
			const response = Response.json({ safe: true });
			if (reads === 1) vi.spyOn(response, 'json').mockResolvedValue({ uncloneable: () => true });
			return Promise.resolve(response);
		});
		const { api } = await loadClient(); const tracing = await observe();
		try {
			const one = tracing.beginExperienceAction('compute', 'load', 'resource.list')!;
			const two = tracing.beginExperienceAction('compute', 'load', 'resource.list')!;
			await Promise.all([api.withExperience(one).get('/api/v1/items'), api.withExperience(two).get('/api/v1/items')]);
			const business = mockFetch.mock.calls.filter(([url]) => String(url).includes('/api/v1/items'));
			expect(business).toHaveLength(2);
			await tracing.collector.flush();
			const receipt = tracing.events().find(row => row.action_id === two.actionId && row.event_type === 'result.received');
			expect(receipt.payload.transport).toBe('network');
			expect(receipt.payload.physical_span_id).toBe(new Headers(business[1][1].headers).get('X-Afterglow-Experience-Span'));
			expect(receipt.payload.physical_span_id).not.toBe(new Headers(business[0][1].headers).get('X-Afterglow-Experience-Span'));
		} finally { tracing.collector.destroy(); }
	});
});
