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
		first.setAuth({ token: 'tab-access', refreshToken: 'tab-refresh', domainId: 'domain-1', identityDomainId: 'domain-1', domainName: 'Tenant' });
		vi.resetModules();
		const reloaded = await import('../auth');
		expect(get(reloaded.auth)).toMatchObject({ token: 'tab-access', refreshToken: 'tab-refresh', domainId: 'domain-1', domainName: 'Tenant' });
	});

	it('requires a fresh login for a stored session without its bound domain', async () => {
		sessionStorage.setItem('afterglow_auth', JSON.stringify({ token: 'pre-domain-access', refreshToken: 'pre-domain-refresh', isDomainManager: true }));
		const mod = await import('../auth');
		expect(get(mod.auth).token).toBeNull();
		expect(get(mod.canManageDomain)).toBe(false);
		expect(sessionStorage.getItem('afterglow_auth')).toBeNull();
	});

	it('does not infer identity-domain binding from pre-cutover working-domain snapshots', async () => {
		sessionStorage.setItem('afterglow_auth', JSON.stringify({ token: 'pre-identity-access', domainId: 'domain-1', isDomainManager: true }));
		const mod = await import('../auth');
		expect(get(mod.auth).token).toBeNull();
		expect(sessionStorage.getItem('afterglow_auth')).toBeNull();
	});

	it('shows domain management only for a verified Default manager, independently of selected project and system admin', async () => {
		const mod = await import('../auth');
		mod.setAuth({ token: 'member', domainId: 'domain-1', isDomainManager: false, isSystemAdmin: false });
		expect(get(mod.canManageDomain)).toBe(false);
		mod.setAuth({ token: 'manager', domainId: 'domain-1', isDomainManager: true });
		expect(get(mod.canManageDomain)).toBe(true);
		mod.setAuth({ token: 'unbound', domainId: null, isDomainManager: true });
		expect(get(mod.canManageDomain)).toBe(false);
		mod.setAuth({ token: 'admin', domainId: null, isDomainManager: false, isSystemAdmin: true });
		expect(get(mod.canManageDomain)).toBe(false);
		mod.setAuth({ token: 'system-only', domainId: 'domain-1', projectId: 'project', isSystemAdmin: true, isDomainManager: false });
		expect(get(mod.canManageDomain)).toBe(false);
		mod.setAuth({ token: 'default-manager', domainId: 'domain-1', projectId: null, isSystemAdmin: false, isDomainManager: true });
		expect(get(mod.canManageDomain)).toBe(true);
		expect(get(mod.isAdmin)).toBe(false);
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
