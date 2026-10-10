import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

const listeners: EventListenerOrEventListenerObject[] = [];
const originalAddEventListener = window.addEventListener.bind(window);

afterEach(() => {
	for (const listener of listeners.splice(0)) window.removeEventListener('storage', listener);
	vi.restoreAllMocks();
});

beforeEach(() => {
	vi.resetModules();
	localStorage.clear();
	sessionStorage.clear();
	vi.spyOn(window, 'addEventListener').mockImplementation((type, listener, options) => {
		if (type === 'storage') listeners.push(listener);
		originalAddEventListener(type, listener, options);
	});
});

describe('secret-free cross-tab revocation', () => {
	it('never adopts credentials from a browser-wide storage event', async () => {
		const mod = await import('../auth');
		mod.setAuth({ token: 'my-access', refreshToken: 'my-refresh' });
		window.dispatchEvent(new StorageEvent('storage', {
			key: 'afterglow_auth', newValue: JSON.stringify({ token: 'other-access', refreshToken: 'other-refresh' }),
		}));
		expect(get(mod.auth)).toMatchObject({ token: 'my-access', refreshToken: 'my-refresh' });
	});

	it('clears tab-local credentials when another tab publishes a logout marker', async () => {
		const mod = await import('../auth');
		mod.setLoginAuth({ token: 'my-access', refreshToken: 'my-refresh' });
		mod.authReady.set(true);
		localStorage.setItem(mod.AUTH_LOGOUT_EVENT_KEY, 'logout-event');
		window.dispatchEvent(new StorageEvent('storage', {
			key: mod.AUTH_LOGOUT_EVENT_KEY, newValue: 'logout-event', storageArea: localStorage,
		}));
		expect(get(mod.auth).token).toBeNull();
		expect(get(mod.authReady)).toBe(false);
		expect(sessionStorage.getItem(mod.AUTH_STORAGE_KEY)).toBeNull();
		// Receiving revocation does not publish another marker.
		expect(localStorage.getItem(mod.AUTH_LOGOUT_EVENT_KEY)).toBe('logout-event');
	});

	it('ignores sessionStorage events from an iframe', async () => {
		const mod = await import('../auth');
		mod.setAuth({ token: 'my-access' });
		window.dispatchEvent(new StorageEvent('storage', {
			key: mod.AUTH_LOGOUT_EVENT_KEY, newValue: 'iframe-event', storageArea: sessionStorage,
		}));
		expect(get(mod.auth).token).toBe('my-access');
	});

	it('does not revoke a fresh login for an already acknowledged marker', async () => {
		const mod = await import('../auth');
		localStorage.setItem(mod.AUTH_LOGOUT_EVENT_KEY, 'earlier-logout');
		mod.setLoginAuth({ token: 'fresh-access' });
		window.dispatchEvent(new StorageEvent('storage', { key: mod.AUTH_LOGOUT_EVENT_KEY, newValue: 'earlier-logout' }));
		expect(get(mod.auth).token).toBe('fresh-access');
	});

	it.each(['refresh', 'rescope', 'roles'])(
		'does not acknowledge a queued logout during routine %s updates', async (kind) => {
			const mod = await import('../auth');
			mod.setLoginAuth({ token: 'before-access', refreshToken: 'before-refresh' });
			localStorage.setItem(mod.AUTH_LOGOUT_EVENT_KEY, 'queued-logout');
			if (kind === 'refresh') mod.setAuth({ token: 'refreshed-access', refreshToken: 'refreshed-refresh' });
			else if (kind === 'rescope') mod.setProject('new-project', 'New Project');
			else mod.auth.update((state) => ({ ...state, roles: ['member'] }));
			expect(sessionStorage.getItem('afterglow_auth_logout_seen')).toBeNull();
			window.dispatchEvent(new StorageEvent('storage', {
				key: mod.AUTH_LOGOUT_EVENT_KEY, newValue: 'queued-logout', storageArea: localStorage,
			}));
			expect(get(mod.auth).token).toBeNull();
			expect(sessionStorage.getItem(mod.AUTH_STORAGE_KEY)).toBeNull();
		},
	);

	it('ignores an older M1 event after a fresh login acknowledged the latest M2', async () => {
		const mod = await import('../auth');
		mod.setLoginAuth({ token: 'before-access' });
		localStorage.setItem(mod.AUTH_LOGOUT_EVENT_KEY, 'M1');
		localStorage.setItem(mod.AUTH_LOGOUT_EVENT_KEY, 'M2');
		mod.setLoginAuth({ token: 'fresh-access', refreshToken: 'fresh-refresh' });
		for (const marker of ['M1', 'M2']) {
			window.dispatchEvent(new StorageEvent('storage', {
				key: mod.AUTH_LOGOUT_EVENT_KEY, newValue: marker, storageArea: localStorage,
			}));
		}
		expect(get(mod.auth)).toMatchObject({ token: 'fresh-access', refreshToken: 'fresh-refresh' });
		expect(sessionStorage.getItem('afterglow_auth_logout_seen')).toBe('M2');
	});

	it('keeps a newer queued M2 logout effective after the session only acknowledged M1', async () => {
		const mod = await import('../auth');
		localStorage.setItem(mod.AUTH_LOGOUT_EVENT_KEY, 'M1');
		mod.setLoginAuth({ token: 'session-after-M1' });
		localStorage.setItem(mod.AUTH_LOGOUT_EVENT_KEY, 'M2');
		mod.setAuth({ token: 'routine-refresh-after-M2' });
		window.dispatchEvent(new StorageEvent('storage', { key: mod.AUTH_LOGOUT_EVENT_KEY, newValue: 'M1' }));
		expect(get(mod.auth).token).toBe('routine-refresh-after-M2');
		window.dispatchEvent(new StorageEvent('storage', { key: mod.AUTH_LOGOUT_EVENT_KEY, newValue: 'M2' }));
		expect(get(mod.auth).token).toBeNull();
	});
});
