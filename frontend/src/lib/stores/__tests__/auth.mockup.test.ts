// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

import { MOCKUP_SESSION_KEY, MOCKUP_STORAGE_KEY } from '$lib/mockup/contracts';
import type { AuthState } from '../auth';

const storage: Record<string, string> = {};
const cookieWrites: string[] = [];
let cookieString = '';

const localStorageMock = {
	getItem: vi.fn((key: string) => storage[key] ?? null),
	setItem: vi.fn((key: string, value: string) => {
		storage[key] = value;
	}),
	removeItem: vi.fn((key: string) => {
		delete storage[key];
	}),
	clear: vi.fn(() => {
		for (const key of Object.keys(storage)) delete storage[key];
	}),
};

const sessionStorageMock = {
	getItem: vi.fn((key: string) => storage[`session:${key}`] ?? null),
	setItem: vi.fn((key: string, value: string) => {
		storage[`session:${key}`] = value;
	}),
	removeItem: vi.fn((key: string) => {
		delete storage[`session:${key}`];
	}),
	clear: vi.fn(() => {
		for (const key of Object.keys(storage)) {
			if (key.startsWith('session:')) delete storage[key];
		}
	}),
};
const originalDocument = globalThis.document;

function makeState(overrides: Partial<AuthState>): AuthState {
	return {
		token: null,
		refreshToken: null,
		accessExpiresAt: null,
		userId: null,
		username: null,
		projectId: null,
		projectName: null,
		availableProjects: [],
		roles: [],
		isSystemAdmin: false,
		federated: false,
		...overrides,
	};
}

beforeEach(() => {
	vi.resetModules();
	vi.stubGlobal('localStorage', localStorageMock);
	vi.stubGlobal('sessionStorage', sessionStorageMock);
	vi.stubGlobal('location', { protocol: 'http:' });
	vi.stubGlobal('window', {
		localStorage: localStorageMock,
		sessionStorage: sessionStorageMock,
		addEventListener: vi.fn(),
	});
	Object.defineProperty(globalThis, 'document', {
		value: {
			get cookie() {
				return cookieString;
			},
			set cookie(value: string) {
				cookieWrites.push(value);
				cookieString = value;
			},
		},
		configurable: true,
	});
	localStorageMock.clear();
	localStorageMock.getItem.mockClear();
	localStorageMock.setItem.mockClear();
	localStorageMock.removeItem.mockClear();
	localStorageMock.clear.mockClear();
	cookieWrites.length = 0;
	cookieString = '';
});

afterEach(() => {
	vi.unstubAllGlobals();
	Object.defineProperty(globalThis, 'document', {
		value: originalDocument,
		configurable: true,
	});
});

describe('auth mockup persistence', () => {
	it('boots from a tab-scoped mock profile and ignores a legacy cross-tab snapshot', async () => {
		storage.afterglow_auth = JSON.stringify(
			makeState({ token: 'real-token', refreshToken: 'real-refresh', projectId: 'real-project' }),
		);
		storage[MOCKUP_STORAGE_KEY] = JSON.stringify(
			makeState({ token: 'legacy-cross-tab-token', projectId: 'wrong-project' }),
		);
		storage[`session:${MOCKUP_STORAGE_KEY}`] = JSON.stringify(
			makeState({ token: 'mock-token', refreshToken: 'mock-refresh', projectId: 'mock-project' }),
		);
		storage[`session:${MOCKUP_SESSION_KEY}`] = 'on';

		// Dynamic import re-evaluates auth.ts after the tab-local session fixture is installed.
		const mod = await import('../auth');

		expect(mod.isMockAuthActive()).toBe(true);
		expect(get(mod.auth)).toMatchObject({
			token: 'mock-token',
			refreshToken: 'mock-refresh',
			projectId: 'mock-project',
		});
		expect(storage.afterglow_auth).toContain('real-token');
		expect(cookieWrites).toEqual([]);
	});

	it('starts a query-activated mock before real auth persistence can run', async () => {
		storage.afterglow_auth = JSON.stringify(
			makeState({ token: 'real-token', refreshToken: 'real-refresh', projectId: 'real-project' }),
		);
		Object.assign(globalThis.window, { location: { search: '?tutorial=on' } });

		// Dynamic import evaluates initial auth persistence against the activation query.
		const mod = await import('../auth');

		expect(get(mod.auth).token).toBeNull();
		expect(mod.getMockupProfile()).toBe('on');
		expect(storage[`session:${MOCKUP_SESSION_KEY}`]).toBe('on');
		expect(storage.afterglow_auth).toContain('real-token');
		expect(localStorageMock.setItem).not.toHaveBeenCalled();
		expect(cookieWrites).toEqual([]);
	});

	it('lets explicit tutorial=off clear a stored mock snapshot before auth initialization', async () => {
		storage[`session:${MOCKUP_STORAGE_KEY}`] = JSON.stringify(makeState({ token: 'mock-token' }));
		storage[`session:${MOCKUP_SESSION_KEY}`] = 'on';
		storage.afterglow_auth = JSON.stringify(makeState({ token: 'real-token' }));
		Object.assign(globalThis.window, { location: { search: '?tutorial=off' } });

		// Dynamic import verifies the explicit exit wins over tab-scoped restoration.
		const mod = await import('../auth');

		expect(mod.getMockupProfile()).toBeNull();
		expect(get(mod.auth).token).toBe('real-token');
		expect(storage[`session:${MOCKUP_STORAGE_KEY}`]).toBeUndefined();
		expect(storage[`session:${MOCKUP_SESSION_KEY}`]).toBeUndefined();
	});

	it('clears a stored mock before invalid query initialization can fall through to live APIs', async () => {
		storage[`session:${MOCKUP_STORAGE_KEY}`] = JSON.stringify(makeState({ token: 'mock-token' }));
		storage[`session:${MOCKUP_SESSION_KEY}`] = 'on';
		storage.afterglow_auth = JSON.stringify(makeState({ token: 'real-token' }));
		Object.assign(globalThis.window, { location: { search: '?tutorial=bogus' } });

		// Dynamic import verifies malformed explicit activation never reuses the mock bearer.
		const mod = await import('../auth');

		expect(mod.getMockupProfile()).toBeNull();
		expect(get(mod.auth).token).toBe('real-token');
		expect(storage[`session:${MOCKUP_STORAGE_KEY}`]).toBeUndefined();
		expect(storage[`session:${MOCKUP_SESSION_KEY}`]).toBeUndefined();
	});

	it.each([
		{ storedProfile: 'on', queryProfile: 'admin' },
		{ storedProfile: 'admin', queryProfile: 'on' },
	] as const)('clears a stale $storedProfile snapshot before query bootstraps $queryProfile', async ({ storedProfile, queryProfile }) => {
		storage[`session:${MOCKUP_STORAGE_KEY}`] = JSON.stringify(makeState({ token: `${storedProfile}-token` }));
		storage[`session:${MOCKUP_SESSION_KEY}`] = storedProfile;
		Object.assign(globalThis.window, { location: { search: `?tutorial=${queryProfile}` } });

		// Dynamic import verifies a query profile never inherits another profile's identity.
		const mod = await import('../auth');

		expect(mod.getMockupProfile()).toBe(queryProfile);
		expect(get(mod.auth).token).toBeNull();
		expect(storage[`session:${MOCKUP_STORAGE_KEY}`]).toBeUndefined();
	});

	it('restores a same-profile mock snapshot as ready without replacing its selected project', async () => {
		storage[`session:${MOCKUP_STORAGE_KEY}`] = JSON.stringify(
			makeState({ token: 'tutorial-token', projectId: 'mock-project-2', projectName: 'Research Project' }),
		);
		storage[`session:${MOCKUP_SESSION_KEY}`] = 'on';
		Object.assign(globalThis.window, { location: { search: '?tutorial=on' } });

		// Dynamic import verifies a tab refresh preserves both ready state and project selection.
		const mod = await import('../auth');

		expect(mod.getMockupProfile()).toBe('on');
		expect(get(mod.auth)).toMatchObject({ token: 'tutorial-token', projectId: 'mock-project-2' });
		expect(get(mod.authReady)).toBe(true);
	});

	it('enterMockAuth persists only mock storage and does not touch the real auth cookie/session marker', async () => {
		// Dynamic import required: auth.ts derives its initial persistence mode from cookie/localStorage at module evaluation time.
		const mod = await import('../auth');
		const realPersisted = JSON.stringify(
			makeState({ token: 'real-token', refreshToken: 'real-refresh', projectId: 'real-project' }),
		);
		storage.afterglow_auth = realPersisted;
		cookieWrites.length = 0;
		localStorageMock.setItem.mockClear();
		localStorageMock.removeItem.mockClear();

		mod.enterMockAuth(
			makeState({
				token: 'mock-token',
				refreshToken: 'mock-refresh',
				userId: 'mock-user-1',
				username: 'demo-user',
				projectId: 'mock-project-1',
				projectName: 'Sample Cloud Demo',
				roles: ['member'],
			}),
			'on',
		);

		expect(storage.afterglow_auth).toBe(realPersisted);
		expect(JSON.parse(storage[`session:${MOCKUP_STORAGE_KEY}`] ?? '{}')).toMatchObject({
			token: 'mock-token',
			projectId: 'mock-project-1',
		});
		expect(cookieWrites).toEqual([]);
		expect(storage[`session:${MOCKUP_SESSION_KEY}`]).toBe('on');
		expect(get(mod.authReady)).toBe(true);
	});

	it('exitMockAuth restores the real persisted auth snapshot and clears mock storage', async () => {
		// Dynamic import required: auth.ts derives its initial persistence mode from cookie/localStorage at module evaluation time.
		const mod = await import('../auth');
		storage.afterglow_auth = JSON.stringify(
			makeState({
				token: 'real-token',
				refreshToken: 'real-refresh',
				userId: 'real-user-1',
				username: 'real-user',
				projectId: 'real-project',
				projectName: 'Real Project',
				roles: ['member'],
			}),
		);
		mod.enterMockAuth(
			makeState({
				token: 'mock-token',
				refreshToken: 'mock-refresh',
				projectId: 'mock-project-1',
				projectName: 'Mock Project',
			}),
			'on',
		);

		mod.exitMockAuth();

		expect(mod.isMockAuthActive()).toBe(false);
		expect(get(mod.auth)).toMatchObject({
			token: 'real-token',
			refreshToken: 'real-refresh',
			projectId: 'real-project',
			projectName: 'Real Project',
		});
		expect(localStorage.getItem(MOCKUP_STORAGE_KEY)).toBeNull();
		expect(storage[`session:${MOCKUP_STORAGE_KEY}`]).toBeUndefined();
		expect(storage[`session:${MOCKUP_SESSION_KEY}`]).toBeUndefined();
		expect(get(mod.authReady)).toBe(false);
	});

	it('exitMockAuth falls back to the logged-out state when no real auth snapshot exists', async () => {
		// Dynamic import required: auth.ts derives its initial persistence mode from cookie/localStorage at module evaluation time.
		const mod = await import('../auth');
		mod.enterMockAuth(
			makeState({
				token: 'mock-token',
				refreshToken: 'mock-refresh',
				projectId: 'mock-project-1',
				projectName: 'Mock Project',
			}),
		);
		delete storage.afterglow_auth;

		mod.exitMockAuth();

		expect(get(mod.auth)).toMatchObject({
			token: null,
			refreshToken: null,
			projectId: null,
			projectName: null,
			roles: [],
		});
		expect(localStorage.getItem(MOCKUP_STORAGE_KEY)).toBeNull();
		expect(get(mod.authReady)).toBe(false);
	});
});
