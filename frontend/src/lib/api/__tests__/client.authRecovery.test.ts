import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
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
	store.setAuth({ token: 'old-access', refreshToken: 'refresh', accessExpiresAt: 1 });
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
		mockFetch.mockResolvedValueOnce(Response.json({ token: 'new-access', refresh_token: 'new-refresh' }));
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
		refresh.resolve(Response.json({ token: 'new-access', refresh_token: 'new-refresh' }));
		await s.refreshSession();
		expect(mockFetch).toHaveBeenCalledOnce();
	});
});
