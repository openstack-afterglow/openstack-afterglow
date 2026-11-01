import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$app/navigation', () => ({ goto: vi.fn().mockResolvedValue(undefined) }));
vi.mock('$lib/stores/cloudShell.svelte', () => ({ cloudShell: { close: vi.fn().mockResolvedValue(undefined) } }));
const fetchMock = vi.fn();
// Each case reloads the real client/workflow singleton boundary after resetModules;
// static imports would retain completed logout and refresh coordinator state.
beforeEach(() => {
	vi.resetModules(); localStorage.clear(); sessionStorage.clear(); fetchMock.mockReset();
	vi.stubGlobal('fetch', fetchMock);
	vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { queueMicrotask(() => callback(0)); return 1; });
	vi.stubGlobal('cancelAnimationFrame', vi.fn());
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('logout workflow with the real API client', () => {
	it.each([false, true])('revokes server sessions with a renewed credential after expired access (all=%s)', async all => {
		const store = await import('$lib/stores/auth');
		store.setLoginAuth({ token: 'expired-access', refreshToken: 'valid-refresh', userId: 'alice',
			identityDomainId: 'home', domainId: 'team', projectId: 'project', accessExpiresAt: 1 });
		const path = all ? '/api/v1/auth/logout-all' : '/api/v1/auth/logout';
		const calls: Array<{ path: string; authorization: string | null }> = [];
		fetchMock.mockImplementation(async (url: string, options: RequestInit) => {
			const pathname = new URL(url).pathname;
			const authorization = new Headers(options.headers).get('Authorization');
			calls.push({ path: pathname, authorization });
			if (pathname === '/api/v1/auth/refresh') return Response.json({ token: 'renewed-access', refresh_token: 'renewed-refresh',
				user_id: 'alice', project_id: 'project', domain_id: 'team', identity_domain_id: 'home', identity_domain_name: 'Accounts',
				expires_at: new Date(Date.now() + 3600_000).toISOString() });
			if (pathname === path && authorization === 'Bearer renewed-access') return Response.json({ message: 'revoked' });
			return Response.json({ detail: 'Expired access' }, { status: 401 });
		});
		const workflow = await import('./logout');
		await workflow.startLogout({ all });
		expect(calls).toEqual([{ path, authorization: 'Bearer expired-access' },
			{ path: '/api/v1/auth/refresh', authorization: null }, { path, authorization: 'Bearer renewed-access' }]);
		expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'complete', server: 'done', local: 'done' });
		expect(get(store.auth)).toMatchObject({ token: null, refreshToken: null });
	});

	it.each(['network', '503'])('does not replay an unconfirmed logout after %s failure', async failure => {
		const store = await import('$lib/stores/auth');
		store.setLoginAuth({ token: 'access', refreshToken: 'refresh', userId: 'alice', identityDomainId: 'home', domainId: 'team', projectId: 'project' });
		fetchMock.mockImplementation(async () => {
			if (failure === 'network') throw new TypeError('Network unavailable');
			return Response.json({ detail: 'Unavailable' }, { status: 503 });
		});
		const workflow = await import('./logout');
		await workflow.startLogout();
		expect(fetchMock).toHaveBeenCalledTimes(1);
		expect(get(workflow.logoutProgress)).toMatchObject({ server: 'warning', local: 'done' });
		expect(get(store.auth).token).toBeNull();
	});

	it('signs out automatically after an auth outage without signing out other tabs', async () => {
		const store = await import('$lib/stores/auth');
		store.setLoginAuth({ token: 'access', refreshToken: 'refresh', userId: 'alice', identityDomainId: 'home', domainId: 'team', projectId: 'project' });
		const marker = localStorage.getItem(store.AUTH_LOGOUT_EVENT_KEY);
		fetchMock.mockResolvedValue(new Response('bad gateway', { status: 502 }));
		const workflow = await import('./logout');
		await workflow.startLogout({ broadcast: false });
		expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'complete', server: 'warning', local: 'done' });
		expect(get(store.auth).token).toBeNull();
		expect(sessionStorage.getItem(store.AUTH_STORAGE_KEY)).toBeNull();
		expect(localStorage.getItem(store.AUTH_LOGOUT_EVENT_KEY)).toBe(marker);
	});
});
