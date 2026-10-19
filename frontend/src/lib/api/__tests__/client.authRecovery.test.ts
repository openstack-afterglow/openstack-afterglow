import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/stores/cloudShell.svelte', () => ({ cloudShell: { close: vi.fn().mockResolvedValue(undefined) } }));
const mockFetch = vi.fn();

beforeEach(() => {
	vi.resetModules();
	localStorage.clear();
	sessionStorage.clear();
	mockFetch.mockReset();
	vi.stubGlobal('fetch', mockFetch);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function session() {
	const store = await import('$lib/stores/auth');
	store.setAuth({ token: 'old-access', refreshToken: 'refresh', accessExpiresAt: 1, domainId: 'domain-1', identityDomainId: 'domain-1', domainName: 'Domain' });
	return { ...store, ...await import('../client') };
}

describe('authentication recovery state', () => {
	it('does not turn an ordinary resource outage into an authentication outage', async () => {
		const s = await session();
		s.setAuth({ token: 'old-access', accessExpiresAt: Math.floor(Date.now() / 1000) + 900 });
		mockFetch.mockResolvedValueOnce(Response.json({ detail: 'resource unavailable' }, { status: 503 }));
		await expect(s.api.get('/api/v1/volumes', 'old-access')).rejects.toMatchObject({ status: 503 });
		expect(get(s.authRecovery)).toBeNull();
		expect(get(s.auth).token).toBe('old-access');
	});
	it('exposes an outage, honors retry cooldown, and clears recovery after successful rotation', async () => {

		const s = await session();
		mockFetch.mockResolvedValueOnce(Response.json({ detail: 'unavailable' }, { status: 503 }));
		await expect(s.refreshSession()).rejects.toMatchObject({ status: 503 });
		const failure = get(s.authRecovery)!;
		expect(failure.token).toBe('old-access');
		expect(get(s.auth).refreshToken).toBe('refresh');
		await expect(s.refreshSession()).rejects.toMatchObject({ status: 503 });
		expect(mockFetch).toHaveBeenCalledOnce();
		vi.spyOn(Date, 'now').mockReturnValue(failure.retryAt + 1);
		mockFetch.mockResolvedValueOnce(Response.json({ token: 'new-access', refresh_token: 'new-refresh', domain_id: 'domain-1', identity_domain_id: 'domain-1', identity_domain_name: 'Domain', domain_name: 'Domain' }));
		await expect(s.refreshSession()).resolves.toBe('new-access');
		expect(get(s.authRecovery)).toBeNull();
		expect(get(s.auth).refreshToken).toBe('new-refresh');
	});

	it('does not let a late failed refresh block or clear a newly logged-in identity', async () => {
		const s = await session();
		const pending = Promise.withResolvers<Response>();
		mockFetch.mockReturnValueOnce(pending.promise);
		const refreshing = s.refreshSession();
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		s.clearAuth();
		s.setAuth({ token: 'different-user', refreshToken: 'different-refresh' });
		pending.resolve(Response.json({ detail: 'unavailable' }, { status: 503 }));
		await expect(refreshing).resolves.toBe('different-user');
		expect(get(s.authRecovery)).toBeNull();
		expect(get(s.auth).token).toBe('different-user');
	});

	it('publishes network failure without deleting the session and removes recovery on explicit logout', async () => {
		const s = await session();
		mockFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));
		await expect(s.refreshSession()).rejects.toThrow('Failed to fetch');
		expect(get(s.authRecovery)?.token).toBe('old-access');
		expect(get(s.auth).token).toBe('old-access');
		s.clearAuth();
		expect(get(s.authRecovery)).toBeNull();
		expect(localStorage.getItem('afterglow_auth')).toBeNull();
	});
	it('cancels a scoped MCP approval waiting for refresh before its old payload dispatches', async () => {
		// Module-boundary session helper recreates shared refresh state per test.
		const s = await session();
		const refresh = Promise.withResolvers<Response>();
		mockFetch.mockReturnValueOnce(refresh.promise);
		const controller = new AbortController();
		const pending = s.api.post('/api/v1/auth/mcp-oauth/consents/ticket/approve', {
			access_level: 'read', project_scope: 'selected', project_ids: ['old-project'],
		}, 'old-access', 'old-project', { signal: controller.signal, suppressAuthRedirect: true, cache: 'no-store' });
		const rejected = expect(pending).rejects.toMatchObject({ name: 'AbortError' });
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		expect(mockFetch.mock.calls[0][0]).toContain('/auth/refresh');
		controller.abort();
		await rejected;
		refresh.resolve(Response.json({ token: 'new-access', refresh_token: 'new-refresh', domain_id: 'domain-1', identity_domain_id: 'domain-1', identity_domain_name: 'Domain', domain_name: 'Domain' }));
		await s.refreshSession();
		expect(mockFetch).toHaveBeenCalledOnce();
	});

	it('never publishes a refreshed token for a different or missing domain', async () => {
		for (const body of [
			{ token: 'foreign-access', refresh_token: 'foreign-refresh', domain_id: 'domain-2', identity_domain_id: 'domain-1', identity_domain_name: 'Domain', domain_name: 'Other', is_domain_manager: true },
			{ token: 'foreign-identity', refresh_token: 'foreign-refresh', domain_id: 'domain-1', identity_domain_id: 'domain-2', identity_domain_name: 'Other' },
			{ token: 'domainless-access', refresh_token: 'domainless-refresh' },
		]) {
			vi.resetModules();
			sessionStorage.clear();
			const s = await session();
			mockFetch.mockResolvedValueOnce(Response.json(body));
			await expect(s.refreshSession()).resolves.toBeNull();
			expect(get(s.auth).token).toBeNull();
			expect(sessionStorage.getItem('afterglow_auth')).toBeNull();
		}
	});

	it('ends the session when refresh reports a revoked domain login policy, but keeps it through outages', async () => {
		const s = await session();
		mockFetch.mockResolvedValueOnce(Response.json({ detail: 'unavailable' }, { status: 503 }));
		await expect(s.refreshSession()).rejects.toMatchObject({ status: 503 });
		expect(get(s.auth).token).toBe('old-access');
		vi.spyOn(Date, 'now').mockReturnValue(get(s.authRecovery)!.retryAt + 1);
		mockFetch.mockResolvedValueOnce(Response.json({ detail: 'Sign-in method disabled', code: 'provider_disabled' }, { status: 403 }));
		await expect(s.refreshSession()).resolves.toBeNull();
		expect(get(s.auth).token).toBeNull();
	});

	it('treats a refresh for a deleted domain or provider as terminal', async () => {
		const s = await session();
		mockFetch.mockResolvedValueOnce(Response.json({ detail: 'Domain not found', code: 'domain_not_found' }, { status: 404 }));
		await expect(s.refreshSession()).resolves.toBeNull();
		expect(get(s.auth).token).toBeNull();
	});

	it('does not dispatch a request waiting on preflight refresh after another login replaced its session', async () => {
		const s = await session();
		s.setLoginAuth({ token: 'user-a-access', refreshToken: 'a-refresh', accessExpiresAt: 1, userId: 'user-a', domainId: 'domain-1', identityDomainId: 'domain-1', projectId: 'p1' });
		const refresh = Promise.withResolvers<Response>();
		mockFetch.mockReturnValueOnce(refresh.promise);
		const pending = s.api.post('/api/v1/volumes', { size: 1 }, 'user-a-access', 'p1');
		await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
		const future = Math.floor(Date.now() / 1000) + 900;
		s.setLoginAuth({ token: 'user-b-access', refreshToken: 'b-refresh', accessExpiresAt: future, userId: 'user-b', domainId: 'domain-1', identityDomainId: 'domain-1', projectId: 'p1' });
		refresh.resolve(Response.json({ token: 'a-rotated', refresh_token: 'a-refresh-2', domain_id: 'domain-1', identity_domain_id: 'domain-1', identity_domain_name: 'Domain', user_id: 'user-a' }));
		await expect(pending).rejects.toMatchObject({ status: 401 });
		expect(mockFetch).toHaveBeenCalledOnce();
		expect(get(s.auth).token).toBe('user-b-access');
	});

	it('never replays a rejected request under a different login, and never ends that login', async () => {
		const s = await session();
		const future = Math.floor(Date.now() / 1000) + 900;
		s.setLoginAuth({ token: 'user-a-access', refreshToken: 'a-refresh', accessExpiresAt: future, userId: 'user-a', domainId: 'domain-1', identityDomainId: 'domain-1', projectId: 'p1' });
		mockFetch.mockImplementationOnce(async () => {
			s.setLoginAuth({ token: 'user-b-access', refreshToken: 'b-refresh', accessExpiresAt: future, userId: 'user-b', domainId: 'domain-1', identityDomainId: 'domain-1', projectId: 'p1' });
			return Response.json({ detail: 'expired' }, { status: 401 });
		});
		await expect(s.api.post('/api/v1/volumes', { size: 1 }, 'user-a-access', 'p1')).rejects.toMatchObject({ status: 401 });
		expect(mockFetch).toHaveBeenCalledOnce();
		await Promise.resolve();
		expect(get(s.auth).token).toBe('user-b-access');
	});

	it('does not replay a request captured for another project after a rescope', async () => {
		const s = await session();
		const future = Math.floor(Date.now() / 1000) + 900;
		s.setLoginAuth({ token: 'p1-access', refreshToken: 'r', accessExpiresAt: future, userId: 'user-a', domainId: 'domain-1', identityDomainId: 'domain-1', projectId: 'p1' });
		mockFetch.mockImplementationOnce(async () => {
			s.setAuth({ token: 'p2-access', projectId: 'p2' });
			return Response.json({ detail: 'expired' }, { status: 401 });
		});
		await expect(s.api.post('/api/v1/volumes', { size: 1 }, 'p1-access', 'p1')).rejects.toMatchObject({ status: 401 });
		expect(mockFetch).toHaveBeenCalledOnce();
	});

	it('retries once with a token rotated by refresh within the same session and project', async () => {
		const s = await session();
		const future = Math.floor(Date.now() / 1000) + 900;
		s.setLoginAuth({ token: 'before-rotation', refreshToken: 'r', accessExpiresAt: future, userId: 'user-a', domainId: 'domain-1', identityDomainId: 'domain-1', projectId: 'p1' });
		mockFetch
			.mockImplementationOnce(async () => {
				s.setAuth({ token: 'after-rotation', accessExpiresAt: future });
				return Response.json({ detail: 'expired' }, { status: 401 });
			})
			.mockResolvedValueOnce(Response.json({ ok: true }));
		await expect(s.api.post('/api/v1/volumes', { size: 1 }, 'before-rotation', 'p1')).resolves.toEqual({ ok: true });
		expect(new Headers(mockFetch.mock.calls[1][1].headers).get('Authorization')).toBe('Bearer after-rotation');
	});

	it('does not replay domain creation after a rejected response even when a fresh token is available', async () => {
		const s = await session();
		const future = Math.floor(Date.now() / 1000) + 900;
		s.setAuth({ token: 'create-token', accessExpiresAt: future });
		mockFetch.mockImplementationOnce(async () => {
			s.setAuth({ token: 'rotated-token', accessExpiresAt: future });
			return Response.json({ detail: 'uncertain authentication' }, { status: 401 });
		});
		await expect(s.api.post('/api/v1/auth/domains', { name: 'New' }, 'create-token', undefined, { replayOnUnauthorized: false, suppressAuthRedirect: true, cache: 'no-store' })).rejects.toMatchObject({ status: 401 });
		expect(mockFetch).toHaveBeenCalledOnce();
		expect(get(s.auth).token).toBe('rotated-token');
	});

	it.each(['put', 'patch', 'delete'] as const)('does not repeat an accepted %s after a rejected reply and concurrent token refresh', async (method) => {
		const s = await session();
		const future = Math.floor(Date.now() / 1000) + 900;
		s.setLoginAuth({ token: 'allocation-token', refreshToken: 'refresh', accessExpiresAt: future, userId: 'manager', identityDomainId: 'home', domainId: 'tenant', projectId: 'default' });
		let nativeEffects = 0;
		mockFetch.mockImplementation(async () => {
			nativeEffects += 1;
			s.setAuth({ token: 'rotated-allocation-token', accessExpiresAt: future });
			return Response.json({ detail: 'reply authorization rejected' }, { status: 401 });
		});
		const opts = { replayOnUnauthorized: false, suppressAuthRedirect: true };
		const pending = method === 'delete'
			? s.api.delete('/api/v1/projects/empty', 'allocation-token', 'default', opts)
			: s.api[method]('/api/v1/iam/projects/work/quotas', { cores: 6 }, 'allocation-token', 'default', opts);
		await expect(pending).rejects.toMatchObject({ status: 401 });
		expect(nativeEffects).toBe(1);
		expect(get(s.auth).token).toBe('rotated-allocation-token');
	});
	it('keeps a pending workspace selection alive when the periodic refresh timer fires', async () => {
		const s = await session();
		const home = { id: 'home', name: 'Home' };
		const future = Math.floor(Date.now() / 1000) + 900;
		s.setLoginAuth({ token: 'old-access', refreshToken: 'refresh', accessExpiresAt: future,
			userId: 'alice', identityDomainId: home.id, domainId: home.id, projectId: 'first', availableDomains: [home] });
		s.acceptAuthVerification(s.getAuthVerificationEpoch(), {});
		const response = Promise.withResolvers<Response>();
		const selected = Promise.withResolvers<void>();
		mockFetch.mockImplementation(async (url: string) => {
			if (url.includes('/auth/workspaces')) return Response.json({ domain: home,
				projects: [{ id: 'second', name: 'Second' }], default_project_id: 'first', is_domain_manager: true, can_create_project: true });
			if (url.includes('/auth/domains')) return Response.json([home]);
			if (url.includes('/auth/token/workspace')) { selected.resolve(); return response.promise; }
			if (url.includes('/auth/refresh')) return Response.json({ detail: 'Session already rotated' }, { status: 401 });
			throw new Error(`Unexpected request: ${url}`);
		});
		const { createWorkspaceController } = await import('$lib/stores/workspaceController.svelte');
		const controller = createWorkspaceController(vi.fn());
		const dispose = controller.mount();
		try {
			await vi.waitFor(() => expect(controller.ready).toBe(true));
			const switching = controller.select('second');
			await selected.promise;
			vi.useFakeTimers();
			const refreshing = s.refreshSession();
			// Let a competing refresh reply arrive before the accepted scope reply.
			await vi.advanceTimersByTimeAsync(0);
			response.resolve(Response.json({ token: 'scoped-access', refresh_token: 'scoped-refresh', user_id: 'alice',
				domain_id: home.id, domain_name: home.name, identity_domain_id: home.id, identity_domain_name: home.name,
				project_id: 'second', project_name: 'Second', expires_at: new Date(future * 1000).toISOString() }));
			await switching;
			await expect(refreshing).resolves.toBe('scoped-access');
			expect(get(s.auth)).toMatchObject({ token: 'scoped-access', refreshToken: 'scoped-refresh', projectId: 'second' });
			expect(mockFetch.mock.calls.filter(([url]) => url.includes('/auth/refresh'))).toHaveLength(0);
		} finally { dispose(); s.projectSwitching.set(false); vi.useRealTimers(); }
	});

	it('does not refresh or clear a later login reusing the same credential values after a scope wait', async () => {
		const s = await session();
		const state = { token: 'same-access', refreshToken: 'same-refresh',
			accessExpiresAt: Math.floor(Date.now() / 1000) + 900,
			userId: 'alice', identityDomainId: 'home', domainId: 'home', projectId: 'first' };
		s.setLoginAuth(state);
		s.projectSwitching.set(true);
		mockFetch.mockResolvedValue(Response.json({ detail: 'Retired session' }, { status: 401 }));
		const refreshing = s.refreshSession();
		s.setLoginAuth(state);
		const currentSession = get(s.auth).sessionId;
		s.projectSwitching.set(false);
		await expect(refreshing).resolves.toBe('same-access');
		expect(get(s.auth)).toMatchObject({ token: 'same-access', sessionId: currentSession });
		expect(mockFetch).not.toHaveBeenCalled();
	});

	it('refreshes an expiring credential before dispatching a single scope mutation while the switch is owned', async () => {
		const s = await session();
		const refreshed = Promise.withResolvers<Response>();
		mockFetch.mockReturnValueOnce(refreshed.promise).mockResolvedValueOnce(Response.json({ project_id: 'second' }));
		s.projectSwitching.set(true);
		try {
			const selecting = s.api.post('/api/v1/auth/token/workspace', { domain_id: 'domain-1', project_id: 'second' },
				'old-access', undefined, { replayOnUnauthorized: false, suppressAuthRedirect: true });
			await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledOnce());
			expect(mockFetch.mock.calls[0][0]).toContain('/auth/refresh');
			const refreshing = s.refreshSession();
			refreshed.resolve(Response.json({ token: 'fresh-access', refresh_token: 'fresh-refresh', domain_id: 'domain-1',
				identity_domain_id: 'domain-1', identity_domain_name: 'Domain', expires_at: new Date(Date.now() + 900_000).toISOString() }));
			await expect(selecting).resolves.toEqual({ project_id: 'second' });
			await expect(refreshing).resolves.toBe('fresh-access');
			expect(mockFetch).toHaveBeenCalledTimes(2);
			expect(new Headers(mockFetch.mock.calls[1][1].headers).get('Authorization')).toBe('Bearer fresh-access');
			expect(get(s.auth).token).toBe('fresh-access');
		} finally { s.projectSwitching.set(false); }
	});

	it('never dispatches an old login mutation after a scope wait even when credential strings are reused', async () => {
		const s = await session();
		const state = { token: 'same-access', refreshToken: 'same-refresh', accessExpiresAt: 1,
			userId: 'alice', identityDomainId: 'home', domainId: 'home', projectId: 'first' };
		s.setLoginAuth(state);
		s.projectSwitching.set(true);
		vi.useFakeTimers();
		mockFetch.mockResolvedValue(Response.json({ accepted: true }));
		try {
			const pending = s.api.post('/api/v1/volumes', { size: 1 }, 'same-access', 'first');
			const rejected = expect(pending).rejects.toMatchObject({ status: 401 });
			await vi.advanceTimersByTimeAsync(0);
			s.clearAuth(); s.setLoginAuth(state);
			const currentSession = get(s.auth).sessionId;
			s.projectSwitching.set(false);
			await rejected;
			expect(mockFetch).not.toHaveBeenCalled();
			expect(get(s.auth)).toMatchObject({ token: 'same-access', sessionId: currentSession });
		} finally { s.projectSwitching.set(false); vi.useRealTimers(); }
	});

	it.each(['first', 'second'])('does not clear an accepted transition to %s when a non-replay IAM mutation gets a late old-token 401', async projectId => {
		const s = await session();
		s.setLoginAuth({ token: 'old-access', refreshToken: 'refresh', accessExpiresAt: Math.floor(Date.now() / 1000) + 900,
			userId: 'alice', identityDomainId: 'home', domainId: 'home', projectId: 'first' });
		const originalSession = get(s.auth).sessionId;
		const started = Promise.withResolvers<void>();
		const reply = Promise.withResolvers<Response>();
		mockFetch.mockImplementation(() => { started.resolve(); return reply.promise; });
		const pending = s.api.put('/api/v1/iam/projects/first/quotas', { cores: 2 }, 'old-access', 'first', { replayOnUnauthorized: false });
		const rejected = expect(pending).rejects.toMatchObject({ status: 401 });
		await started.promise;
		vi.useFakeTimers();
		try {
			s.projectSwitching.set(true);
			reply.resolve(Response.json({ detail: 'Retired JTI' }, { status: 401 }));
			await vi.advanceTimersByTimeAsync(0);
			expect(get(s.auth).token).toBe('old-access');
			s.setAuth({ token: 'scoped-access', refreshToken: 'scoped-refresh', projectId });
			s.projectSwitching.set(false);
			await rejected;
			await vi.advanceTimersByTimeAsync(0);
			expect(get(s.auth)).toMatchObject({ token: 'scoped-access', userId: 'alice', sessionId: originalSession, projectId });
			expect(mockFetch).toHaveBeenCalledOnce();
		} finally { s.projectSwitching.set(false); vi.useRealTimers(); }
	});

	it.each(['first', 'second'])('waits for an accepted transition to %s before disposing a retried request 401', async projectId => {
		const s = await session();
		s.setLoginAuth({ token: 'old-access', refreshToken: 'refresh', accessExpiresAt: Math.floor(Date.now() / 1000) + 900,
			userId: 'alice', identityDomainId: 'home', domainId: 'home', projectId: 'first' });
		const originalSession = get(s.auth).sessionId;
		const retried = Promise.withResolvers<void>();
		const reply = Promise.withResolvers<Response>();
		mockFetch.mockResolvedValueOnce(Response.json({ detail: 'Expired access' }, { status: 401 }))
			.mockResolvedValueOnce(Response.json({ token: 'refreshed-access', refresh_token: 'refreshed-refresh',
				domain_id: 'home', identity_domain_id: 'home', identity_domain_name: 'Home', user_id: 'alice',
				expires_at: new Date(Date.now() + 900_000).toISOString() }))
			.mockImplementationOnce(() => { retried.resolve(); return reply.promise; });
		let settled = false;
		const pending = s.api.get('/api/v1/volumes', 'old-access', 'first');
		const rejected = expect(pending).rejects.toMatchObject({ status: 401 });
		void pending.then(() => { settled = true; }, () => { settled = true; });
		await retried.promise;
		vi.useFakeTimers();
		try {
			s.projectSwitching.set(true);
			reply.resolve(Response.json({ detail: 'Retired JTI' }, { status: 401 }));
			await vi.advanceTimersByTimeAsync(0);
			expect(settled).toBe(false);
			expect(get(s.auth).token).toBe('refreshed-access');
			s.setAuth({ token: 'scoped-access', refreshToken: 'scoped-refresh', projectId });
			s.projectSwitching.set(false);
			await rejected;
			await vi.advanceTimersByTimeAsync(0);
			expect(get(s.auth)).toMatchObject({ token: 'scoped-access', userId: 'alice', sessionId: originalSession, projectId });
			expect(mockFetch).toHaveBeenCalledTimes(3);
		} finally { s.projectSwitching.set(false); vi.useRealTimers(); }
	});
});
