import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

beforeEach(() => {
	vi.resetModules();
	localStorage.clear();
	sessionStorage.clear();
});

describe('tab-local credential persistence', () => {
	it('persists access and refresh tokens only in sessionStorage', async () => {
		const mod = await import('../auth');
		mod.setAuth({ token: 'secret-access', refreshToken: 'secret-refresh' });
		expect(JSON.parse(sessionStorage.getItem(mod.AUTH_STORAGE_KEY)!)).toMatchObject({
			token: 'secret-access', refreshToken: 'secret-refresh',
		});
		expect(localStorage.getItem(mod.AUTH_STORAGE_KEY)).toBeNull();
		expect(JSON.stringify(localStorage)).not.toContain('secret-');
	});

	it('discards legacy browser-wide credentials without restoring them', async () => {
		localStorage.setItem('afterglow_auth', JSON.stringify({ token: 'legacy-access', refreshToken: 'legacy-refresh' }));
		const mod = await import('../auth');
		expect(get(mod.auth).token).toBeNull();
		expect(localStorage.getItem('afterglow_auth')).toBeNull();
		expect(sessionStorage.getItem('afterglow_auth')).toBeNull();
	});

	it('restores credentials after a reload in the same tab', async () => {
		const first = await import('../auth');
		first.setAuth({ token: 'tab-access', refreshToken: 'tab-refresh' });
		vi.resetModules();
		const reloaded = await import('../auth');
		expect(get(reloaded.auth)).toMatchObject({ token: 'tab-access', refreshToken: 'tab-refresh' });
	});

	it('drops a dormant tab session after another tab revoked sessions', async () => {
		sessionStorage.setItem('afterglow_auth', JSON.stringify({ token: 'stale-access' }));
		localStorage.setItem('afterglow_auth_logout', 'new-secret-free-event');
		const mod = await import('../auth');
		expect(get(mod.auth).token).toBeNull();
		expect(sessionStorage.getItem('afterglow_auth')).toBeNull();
	});

	it('clears credentials and shares only a random logout marker', async () => {
		const mod = await import('../auth');
		mod.setAuth({ token: 'secret-access', refreshToken: 'secret-refresh', username: 'private-user' });
		mod.clearAuth();
		expect(get(mod.auth).token).toBeNull();
		expect(sessionStorage.getItem(mod.AUTH_STORAGE_KEY)).toBeNull();
		expect(localStorage.getItem(mod.AUTH_LOGOUT_EVENT_KEY)).toMatch(/^[\da-f-]{36}$/);
		expect(JSON.stringify(localStorage)).not.toMatch(/secret-|private-user/);
	});

	it('does not clear another logged-in tab SSR marker when a fresh tab initializes', async () => {
		document.cookie = 'afterglow_session=1; path=/';
		const mod = await import('../auth');
		expect(get(mod.auth).token).toBeNull();
		expect(document.cookie).toContain('afterglow_session=1');
	});

	it('ignores corrupt tab snapshots', async () => {
		sessionStorage.setItem('afterglow_auth', '{invalid json');
		const mod = await import('../auth');
		expect(get(mod.auth).token).toBeNull();
	});
});
