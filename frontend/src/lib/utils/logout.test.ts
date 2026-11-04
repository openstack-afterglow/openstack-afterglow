import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type * as AuthModule from '$lib/stores/auth';
import type * as LogoutModule from './logout';
import type { ExperienceContext } from './experience';

const mocks = vi.hoisted(() => ({ goto: vi.fn(), close: vi.fn(), post: vi.fn(), begin: vi.fn(), end: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
vi.mock('$lib/api/client', () => ({ api: { post: mocks.post }, beginSessionRevocation: mocks.begin, endSessionRevocation: mocks.end }));
vi.mock('$lib/stores/cloudShell.svelte', () => ({ cloudShell: { close: mocks.close } }));

let authModule: typeof AuthModule;
let workflow: typeof LogoutModule;

beforeEach(async () => {
	vi.resetModules(); vi.resetAllMocks(); localStorage.clear(); sessionStorage.clear();
	document.cookie = 'afterglow_session=; path=/; max-age=0';
	vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { queueMicrotask(() => callback(0)); return 1; });
	vi.stubGlobal('cancelAnimationFrame', vi.fn());
	mocks.goto.mockResolvedValue(undefined); mocks.close.mockResolvedValue(undefined);
	mocks.post.mockResolvedValue({ message: 'Logged out' }); mocks.begin.mockResolvedValue(null);
	// Each case exercises a new module lifetime; static imports would retain the completed single-flight.
	authModule = await import('$lib/stores/auth');
	authModule.setLoginAuth({ token: 'access-old', refreshToken: 'refresh-old', userId: 'alice', identityDomainId: 'home', domainId: 'team', projectId: 'project' });
	workflow = await import('./logout');
});
afterEach(() => { authModule.clearAuth(); authModule.logoutInProgress.set(false); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('visible logout workflow', () => {
	it('navigates and fences immediately, shows real pending work, and revokes the freshest refresh result', async () => {
		const refresh = Promise.withResolvers<string | null>();
		const request = Promise.withResolvers<unknown>();
		mocks.begin.mockReturnValue(refresh.promise); mocks.post.mockReturnValue(request.promise);
		const logout = workflow.startLogout();
		expect(get(authModule.logoutInProgress)).toBe(true);
		expect(mocks.begin).toHaveBeenCalledOnce();
		expect(mocks.goto).toHaveBeenCalledExactlyOnceWith('/logout', { replaceState: true });
		expect(mocks.close).not.toHaveBeenCalled(); expect(mocks.post).not.toHaveBeenCalled();
		expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'running', shell: 'pending', server: 'pending', local: 'pending' });
		await vi.waitFor(() => expect(get(workflow.logoutProgress)).toMatchObject({ shell: 'done', server: 'active', local: 'pending' }));
		expect(get(authModule.auth).refreshToken).toBe('refresh-old');
		authModule.setAuth({ token: 'access-fresh', refreshToken: 'refresh-fresh' }); refresh.resolve('access-fresh');
		await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/logout', {}, 'access-fresh', 'project', { suppressAuthRedirect: true }));
		expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'running', server: 'active', local: 'pending' });
		expect(get(authModule.auth).refreshToken).toBe('refresh-fresh');
		request.resolve({ message: 'Logged out' }); await logout;
		expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'complete', shell: 'done', server: 'done', local: 'done', serverNotRequired: false });
		expect(get(authModule.auth)).toMatchObject({ token: null, refreshToken: null });
		expect(sessionStorage.getItem(authModule.AUTH_STORAGE_KEY)).toBeNull();
		expect(document.cookie).not.toContain('afterglow_session=');
		expect(mocks.goto).toHaveBeenCalledOnce(); expect(mocks.end).toHaveBeenCalledOnce();
		expect(get(authModule.logoutInProgress)).toBe(false);
	});

	it('coalesces concurrent calls and route remounts without upgrading the first operation', async () => {
		const request = Promise.withResolvers<unknown>(); mocks.post.mockReturnValue(request.promise);
		const first = workflow.startLogout();
		expect(workflow.startLogout({ all: true })).toBe(first);
		expect(workflow.ensureLogoutStarted()).toBe(first);
		await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
		request.resolve({}); await first;
		expect(workflow.ensureLogoutStarted()).toBe(first);
		expect(mocks.goto).toHaveBeenCalledOnce(); expect(mocks.begin).toHaveBeenCalledOnce();
		expect(mocks.close).toHaveBeenCalledExactlyOnceWith('logout', { keepDock: false });
		expect(mocks.post.mock.calls[0][0]).toBe('/api/v1/auth/logout');
	});

	it('retains the server failure and still clears access, refresh and persisted credentials', async () => {
		mocks.post.mockRejectedValue(new Error('Network unavailable'));
		await workflow.startLogout({ all: true });
		expect(mocks.post.mock.calls[0][0]).toBe('/api/v1/auth/logout-all');
		expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'complete', all: true, server: 'warning', local: 'done' });
		expect(get(authModule.auth)).toMatchObject({ token: null, refreshToken: null });
		expect(sessionStorage.getItem(authModule.AUTH_STORAGE_KEY)).toBeNull();
		expect(mocks.goto.mock.calls.map(call => call[0])).toEqual(['/logout']);
	});

	it('settles a failed in-flight refresh before revoking the surviving token and clearing locally', async () => {
		const refresh = Promise.withResolvers<string | null>(); mocks.begin.mockReturnValue(refresh.promise);
		const logout = workflow.startLogout();
		refresh.reject(new Error('Refresh timed out')); await logout;
		expect(mocks.post.mock.calls[0][2]).toBe('access-old');
		expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'complete', server: 'done', local: 'done' });
		expect(get(authModule.auth).refreshToken).toBeNull();
	});

	it('does not claim server revocation for direct access without a token', async () => {
		authModule.clearAuth(); document.cookie = 'afterglow_session=1; path=/';
		await workflow.ensureLogoutStarted();
		expect(mocks.goto).not.toHaveBeenCalled(); expect(mocks.post).not.toHaveBeenCalled();
		expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'complete', server: 'done', serverNotRequired: true, local: 'done' });
		expect(document.cookie).not.toContain('afterglow_session=');
	});

	it('continues revocation and local removal after connection cleanup rejects', async () => {
		mocks.close.mockRejectedValue(new Error('Socket close failed'));
		await workflow.startLogout();
		expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'complete', shell: 'warning', server: 'done', local: 'done' });
		expect(mocks.post).toHaveBeenCalledOnce();
	});

	it('does not revoke or clear a new login that replaced the owner while refresh was pending', async () => {
		const refresh = Promise.withResolvers<string | null>(); mocks.begin.mockReturnValue(refresh.promise);
		const logout = workflow.startLogout();
		await vi.waitFor(() => expect(get(workflow.logoutProgress).server).toBe('active'));
		authModule.setLoginAuth({ token: 'access-bob', refreshToken: 'refresh-bob', userId: 'bob', identityDomainId: 'home', domainId: 'team', projectId: 'project' });
		refresh.resolve(null); await logout;
		expect(mocks.post).not.toHaveBeenCalled();
		expect(get(authModule.auth)).toMatchObject({ token: 'access-bob', refreshToken: 'refresh-bob' });
		expect(JSON.parse(sessionStorage.getItem(authModule.AUTH_STORAGE_KEY)!)).toMatchObject({ token: 'access-bob' });
		expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'complete', server: 'warning', local: 'warning' });
	});

	it('does not clear even a same-user fresh login after an older logout POST finishes', async () => {
		const request = Promise.withResolvers<unknown>(); mocks.post.mockReturnValue(request.promise);
		const logout = workflow.startLogout();
		await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
		const old = get(authModule.auth);
		authModule.setLoginAuth({ ...old, token: 'new-login', refreshToken: 'new-refresh' });
		expect(get(authModule.auth).sessionId).not.toBe(old.sessionId);
		request.resolve({}); await logout;
		expect(get(authModule.auth)).toMatchObject({ token: 'new-login', refreshToken: 'new-refresh' });
		expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'complete', server: 'done', local: 'warning' });
	});

	it('starts cleanup for a later direct logout after a new login without repeating an unchanged completed visit', async () => {
		await workflow.startLogout();
		const calls = mocks.post.mock.calls.length;
		await workflow.ensureLogoutStarted();
		expect(mocks.post.mock.calls.length).toBe(calls);
		authModule.setLoginAuth({ token: 'later-access', refreshToken: 'later-refresh', userId: 'alice', identityDomainId: 'home', domainId: 'team', projectId: 'project' });
		await workflow.ensureLogoutStarted();
		expect(mocks.post.mock.calls.at(-1)?.[2]).toBe('later-access');
		expect(get(authModule.auth)).toMatchObject({ token: null, refreshToken: null });
	});

	it('exits tutorial auth without revoking or erasing the separate restored real login', async () => {
		const real = get(authModule.auth);
		authModule.enterMockAuth({ ...real, token: 'mock-token', refreshToken: 'mock-refresh', sessionId: 'tutorial' }, 'on');
		await workflow.startLogout();
		expect(mocks.post).not.toHaveBeenCalled();
		expect(authModule.isMockAuthActive()).toBe(false);
		expect(get(authModule.auth)).toMatchObject({ token: real.token, refreshToken: real.refreshToken, sessionId: real.sessionId });
		expect(sessionStorage.getItem('afterglow_mock_auth')).toBeNull();
		expect(sessionStorage.getItem('afterglow_mockup_profile')).toBeNull();
		expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'complete', serverNotRequired: true, local: 'done', loginHref: '/login?tutorial=off' });
	});

	it('does not report confirmed removal when browser persistence refuses cleanup', async () => {
		vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('Storage denied'); });
		await workflow.startLogout();
		expect(get(authModule.auth).token).toBeNull();
		expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'complete', local: 'warning' });
	});
});

it('carries an explicit logout context through the freshest-token revocation without replacing a single-flight cleanup', async () => {
	const context = Object.freeze({ segmentId: 'source-logout-segment' }) as unknown as ExperienceContext;
	const replacement = Object.freeze({ segmentId: 'unrelated-segment' }) as unknown as ExperienceContext;
	const request = Promise.withResolvers<unknown>(); mocks.post.mockReturnValue(request.promise);
	const original = workflow.startLogout({ experience: context });
	expect(workflow.startLogout({ all: true, experience: replacement })).toBe(original);
	expect(workflow.ensureLogoutStarted(replacement)).toBe(original);
	await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/logout', {}, 'access-old', 'project', { suppressAuthRedirect: true, experience: context }));
	expect(get(workflow.logoutProgress)).toMatchObject({ server: 'active', local: 'pending' });
	request.resolve({}); await original;
	expect(get(workflow.logoutProgress)).toMatchObject({ phase: 'complete', server: 'done', local: 'done' });
	expect(get(authModule.auth).token).toBeNull();
});
