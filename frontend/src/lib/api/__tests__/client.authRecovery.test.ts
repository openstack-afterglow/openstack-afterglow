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
});
