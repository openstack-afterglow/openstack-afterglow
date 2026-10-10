import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import type { Writable } from 'svelte/store';
import type { AuthState } from '$lib/stores/auth';

const mocks = vi.hoisted(() => ({ goto: vi.fn(), fetch: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_API_BASE: 'http://localhost:8000' } }));
vi.mock('$lib/stores/auth', async () => {
	const { writable } = await import('svelte/store');
	const auth = writable<Partial<AuthState>>({});
	return {
		auth, authRecovery: writable({ phase: 'idle' }), logoutInProgress: writable(false),
		getMockupProfile: () => null, isMockAuthActive: () => false,
		setAuth: (state: Partial<AuthState>) => auth.update(current => ({ ...current, ...state })),
		clearAuth: () => auth.set({}),
	};
});
let identity: Writable<Partial<AuthState>>;
beforeEach(async () => {
	vi.resetModules();
	vi.clearAllMocks();
	localStorage.clear();
	identity = (await import('$lib/stores/auth')).auth;
	identity.set({ token: 'valid-first-party-session', projectId: 'project', isSystemAdmin: true, accessExpiresAt: null });
	vi.stubGlobal('window', { location: { pathname: '/admin/lumen', protocol: 'http:', hostname: 'localhost', href: '/admin/lumen' } });
	vi.stubGlobal('fetch', mocks.fetch);
	mocks.goto.mockResolvedValue(undefined);
	mocks.fetch.mockImplementation(async () => Response.json({ detail: 'Required service action denied', code: 'service_action_denied' }, { status: 403 }));
});
afterEach(() => { vi.unstubAllGlobals(); });

describe('platform administration versus service authorization', () => {
	it.each(['/api/v1/chat/admin/providers', '/api/v1/drover/admin/executions', '/api/v1/chat/conversations?next=/admin/overview'])('preserves a valid administrator session on service denial: %s', async path => {
		const { api } = await import('../client');
		await expect(api.get(path, 'valid-first-party-session', 'project')).rejects.toMatchObject({ status: 403 });
		await Promise.resolve();
		expect(get(identity).token).toBe('valid-first-party-session');
		expect(get(identity).isSystemAdmin).toBe(true);
		expect(mocks.goto).not.toHaveBeenCalled();
	});
	it('still removes stale platform-administrator access on a first-party admin denial', async () => {
		const { api } = await import('../client');
		await expect(api.get('/api/v1/admin/overview', 'valid-first-party-session', 'project')).rejects.toMatchObject({ status: 403 });
		await vi.waitFor(() => expect(get(identity).isSystemAdmin).toBe(false));
		expect(mocks.goto).toHaveBeenCalledWith('/dashboard');
		expect(get(identity).token).toBe('valid-first-party-session');
	});
});
