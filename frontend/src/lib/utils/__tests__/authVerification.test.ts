import { screen } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AuthMeResponse, LoginResponse } from '$lib/types/auth';

const mocks = vi.hoisted(() => ({ me: vi.fn(), protectedRead: vi.fn() }));
vi.mock('$lib/api/client', async () => ({
	ApiError: (await import('$lib/api/errors')).ApiError,
	api: { get: vi.fn((path: string, ...args: unknown[]) => path === '/api/v1/auth/me'
		? mocks.me(path, ...args) : mocks.protectedRead(path, ...args)) },
}));

const login: LoginResponse = {
	token: 'same-token', refresh_token: 'refresh', user_id: 'alice', username: 'Alice',
	project_id: 'project-a', project_name: 'Project A', expires_at: null,
	identity_domain_id: 'home', identity_domain_name: 'Home', domain_id: 'home', domain_name: 'Home',
	available_domains: [{ id: 'home', name: 'Home' }], roles: ['reader'],
	is_system_admin: false, is_domain_manager: true, can_write: false,
};
const me: AuthMeResponse = { ...login, auth_method: 'password' };

let cleanupConsumer: (() => void) | undefined;
function cleanup() { cleanupConsumer?.(); }

async function modules() {
	// Reload the renderer/runtime together with the store to model a new page,
	// rather than mixing old Svelte component internals with a fresh module graph.
	const consumer = await import('@testing-library/svelte/pure');
	cleanupConsumer = consumer.cleanup;
	const store = await import('$lib/stores/auth');
	const mapping = await import('../authSession');
	const Consumer = (await import('./AuthReadinessConsumer.svelte')).default;
	return { store, mapping, Consumer, render: consumer.render };
}
async function flush() {
	const { tick } = await import('svelte');
	await tick(); await Promise.resolve(); await tick();
}

beforeEach(() => {
	vi.resetModules();
	vi.useFakeTimers();
	localStorage.clear(); sessionStorage.clear();
	mocks.me.mockReset().mockResolvedValue(me);
	mocks.protectedRead.mockReset().mockResolvedValue({});
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('root authentication readiness transitions', () => {
	it.each([
		['dashboard', 'project-a', login.available_domains, '/dashboard'],
		['project chooser', '', login.available_domains, '/select-project'],
		['multi-domain dashboard', 'project-a', [{ id: 'home', name: 'Home' }, { id: 'team', name: 'Team' }], '/dashboard'],
		['domain chooser', '', [{ id: 'home', name: 'Home' }, { id: 'team', name: 'Team' }], '/select-domain'],
	] as const)('publishes fresh readiness with existing-session %s destination, but reload verifies before protected reads', async (_name, project, domains, target) => {
		const first = await modules();
		first.render(first.Consumer);
		const mapped = first.mapping.loginAuthState({ ...login, project_id: project, available_domains: [...domains!] }, { federated: false });
		first.store.setLoginAuth(mapped.state);
		await flush();
		expect(mapped.target).toBe('/select-domain');
		expect(screen.getByRole('status').textContent).toContain(target);
		expect(get(first.store.authReady)).toBe(true);
		expect(mocks.me).not.toHaveBeenCalled();
		expect(mocks.protectedRead).toHaveBeenCalledOnce();
		cleanup();
		vi.resetModules();
		const reloaded = await modules();
		const pending = Promise.withResolvers<AuthMeResponse>();
		mocks.me.mockReturnValueOnce(pending.promise);
		mocks.protectedRead.mockClear();
		reloaded.render(reloaded.Consumer);
		await flush();
		expect(screen.getByRole('status').textContent).toBe('Verifying session');
		expect(mocks.me).toHaveBeenCalledOnce();
		expect(mocks.protectedRead).not.toHaveBeenCalled();
		pending.resolve({ ...me, project_id: project || null, available_domains: [...domains!] });
		await flush();
		expect(screen.getByRole('status').textContent).toContain(target);
		expect(mocks.protectedRead).toHaveBeenCalledOnce();
	});

	it.each(['partial login', 'copied mapping', 'generic replacement', 'reused mapping'] as const)('does not grant fresh readiness to %s', async (kind) => {
		const { store, mapping, Consumer, render } = await modules();
		const mapped = mapping.loginAuthState(login, { federated: false });
		if (kind === 'partial login') store.setLoginAuth({ token: login.token });
		else if (kind === 'copied mapping') store.setLoginAuth({ ...mapped.state });
		else {
			store.setLoginAuth(mapped.state);
			if (kind === 'generic replacement') store.setAuth({ token: login.token });
			else store.setLoginAuth(mapped.state);
		}
		const pending = Promise.withResolvers<AuthMeResponse>();
		mocks.me.mockReturnValueOnce(pending.promise);
		render(Consumer); await flush();
		expect(screen.getByRole('status').textContent).toBe('Verifying session');
		expect(mocks.me).toHaveBeenCalledOnce();
		expect(mocks.protectedRead).not.toHaveBeenCalled();
	});

	it('retains an established draft through native refresh while verifying its new token', async () => {
		const { store, mapping, Consumer, render } = await modules();
		store.setLoginAuth(mapping.loginAuthState(login, { federated: false }).state);
		render(Consumer); await flush();
		const draft = screen.getByRole('textbox', { name: 'Unsubmitted draft' }) as HTMLInputElement;
		draft.value = 'Keep this unsent work';
		const pending = Promise.withResolvers<AuthMeResponse>();
		mocks.me.mockReturnValueOnce(pending.promise);
		store.setAuth(mapping.refreshAuthState({ ...login, token: 'rotated', refresh_token: 'rotated-refresh' }, get(store.auth)));
		await flush();
		expect(screen.getByRole('status').textContent).toContain('/dashboard');
		expect(screen.getByRole('textbox', { name: 'Unsubmitted draft' })).toBe(draft);
		expect(draft.value).toBe('Keep this unsent work');
		expect(mocks.me).toHaveBeenCalledOnce();
		expect(store.hasVerifiedAuth()).toBe(false);
		pending.resolve(me); await flush();
		expect(store.hasVerifiedAuth()).toBe(true);
		expect(draft.value).toBe('Keep this unsent work');
	});

	it('verifies a refreshed projectless continuation without sending the revoked project or retrying', async () => {
		const { store, mapping, Consumer, render } = await modules();
		store.setLoginAuth(mapping.loginAuthState(login, { federated: false }).state);
		render(Consumer); await flush();
		const previous = get(store.auth);
		const projectless = { ...me, project_id: '', project_name: '', roles: [] };
		const pending = Promise.withResolvers<AuthMeResponse>();
		mocks.me.mockReturnValueOnce(pending.promise).mockResolvedValue(projectless);
		store.setAuth(mapping.refreshAuthState({ ...login, token: 'rotated', project_id: '', project_name: '', roles: [] }, previous));
		await flush();
		expect(get(store.auth)).toMatchObject({ token: 'rotated', projectId: null, projectName: null, roles: [],
			userId: previous.userId, domainId: previous.domainId, identityDomainId: previous.identityDomainId, sessionId: previous.sessionId });
		expect(get(store.authReady)).toBe(true);
		expect(mocks.me).toHaveBeenCalledOnce();
		expect(mocks.me).toHaveBeenCalledWith('/api/v1/auth/me', 'rotated', undefined,
			expect.objectContaining({ refresh: true, suppressAuthRedirect: true }));
		pending.resolve(projectless); await flush();
		expect(store.hasVerifiedAuth()).toBe(true);
		expect(screen.getByRole('status').textContent).toContain('/select-project');
		expect(get(store.authRecovery)).toBeNull();
		await vi.advanceTimersByTimeAsync(5000); await flush();
		expect(mocks.me).toHaveBeenCalledOnce();
	});

	it.each(['', null])('accepts authoritative /me project revocation (%s) and settles projectless readiness', async (project_id) => {
		const { store, mapping, Consumer, render } = await modules();
		// A copied login mapping models restored credentials that require /me.
		store.setLoginAuth({ ...mapping.loginAuthState(login, { federated: false }).state });
		const previous = get(store.auth);
		mocks.me.mockResolvedValue({ ...me, project_id, project_name: 'Stale project name', roles: [] });
		render(Consumer); await flush(); await flush();
		expect(get(store.auth)).toMatchObject({ projectId: null, projectName: null, roles: [], userId: previous.userId,
			domainId: previous.domainId, identityDomainId: previous.identityDomainId, sessionId: previous.sessionId });
		expect(get(store.authReady)).toBe(true);
		expect(store.hasVerifiedAuth()).toBe(true);
		expect(screen.getByRole('status').textContent).toContain('/select-project');
		// The scope-key change rechecks once, now without an explicit project.
		expect(mocks.me.mock.calls.map(call => call[2])).toEqual(['project-a', undefined]);
		await vi.advanceTimersByTimeAsync(5000); await flush();
		expect(mocks.me).toHaveBeenCalledTimes(2);
		expect(get(store.authRecovery)).toBeNull();
	});

	it.each(['copy', 'reuse', 'different login', 'unverified source'] as const)('does not retain readiness from a continuation with %s', async (boundary) => {
		const { store, mapping, Consumer, render } = await modules();
		store.setLoginAuth(mapping.loginAuthState(login, { federated: false }).state);
		const update = mapping.refreshAuthState({ ...login, token: 'rotated' }, get(store.auth));
		if (boundary === 'reuse') store.setAuth(update);
		if (boundary === 'different login') store.setLoginAuth(mapping.loginAuthState(login, { federated: false }).state);
		if (boundary === 'unverified source') store.setAuth({ token: login.token });
		const pending = Promise.withResolvers<AuthMeResponse>();
		mocks.me.mockReturnValue(pending.promise);
		store.setAuth(boundary === 'copy' ? { ...update } : update);
		render(Consumer); await flush();
		expect(screen.getByRole('status').textContent).toBe('Verifying session');
		expect(screen.queryByRole('textbox', { name: 'Unsubmitted draft' })).toBeNull();
		expect(mocks.protectedRead).not.toHaveBeenCalled();
		expect(mocks.me).toHaveBeenCalledOnce();
	});

	it.each(['token', 'userId', 'identityDomainId', 'domainId', 'projectId'] as const)('revokes the fresh proof synchronously on changed %s and same-tick ABA', async (field) => {
		const { store, mapping, Consumer, render } = await modules();
		store.setLoginAuth(mapping.loginAuthState(login, { federated: false }).state);
		render(Consumer); await flush();
		const original = get(store.auth);
		const pending = Promise.withResolvers<AuthMeResponse>();
		mocks.me.mockReturnValue(pending.promise);
		// Direct store updates exercise the same synchronous fence as setProject,
		// without relying on generic setAuth's explicit invalidation.
		store.auth.update(state => ({ ...state, [field]: 'other' }));
		expect(get(store.authReady)).toBe(false);
		store.auth.set(original);
		await flush();
		expect(screen.getByRole('status').textContent).toBe('Verifying session');
		expect(mocks.me).toHaveBeenCalledTimes(2);
		pending.resolve(me); await flush();
		expect(screen.getByRole('status').textContent).toContain('/dashboard');
	});

	it.each(['success', '401', 'outage'] as const)('discards pre-ABA scope %s until the current verification finishes', async (result) => {
		const { store, mapping, Consumer, render } = await modules();
		store.setLoginAuth({ ...mapping.loginAuthState(login, { federated: false }).state });
		const old = Promise.withResolvers<AuthMeResponse>();
		const current = Promise.withResolvers<AuthMeResponse>();
		mocks.me.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise).mockReturnValueOnce(current.promise);
		render(Consumer); await flush();
		const original = get(store.auth);
		store.setProject('project-b', 'Project B');
		store.auth.set(original);
		if (result === 'success') old.resolve({ ...me, is_system_admin: true });
		else if (result === '401') old.reject(new (await import('$lib/api/client')).ApiError(401, 'expired'));
		else old.reject(new Error('offline'));
		await flush();
		expect(screen.getByRole('status').textContent).toBe('Verifying session');
		expect(get(store.auth).isSystemAdmin).toBe(false);
		expect(get(store.authRecovery)).toBeNull();
		expect(mocks.protectedRead).not.toHaveBeenCalled();
		current.resolve(me); await flush();
		expect(screen.getByRole('status').textContent).toContain('/dashboard');
		expect(get(store.auth).isSystemAdmin).toBe(false);
	});

	it('cancels an outage retry on logout and on consumer disposal', async () => {
		const { store, mapping, Consumer, render } = await modules();
		const start = async () => {
			store.setLoginAuth({ ...mapping.loginAuthState(login, { federated: false }).state });
			mocks.me.mockRejectedValueOnce(new Error('offline'));
			render(Consumer); await flush();
		};
		await start();
		store.clearAuth(); await flush();
		await vi.advanceTimersByTimeAsync(5000);
		expect(screen.getByRole('status').textContent).toBe('Signed out');
		expect(get(store.authRecovery)).toBeNull();
		expect(mocks.me).toHaveBeenCalledOnce();
		cleanup();
		await start();
		cleanup();
		await vi.advanceTimersByTimeAsync(5000);
		expect(mocks.me).toHaveBeenCalledTimes(2);
	});

	it.each(['success', 'invalid metadata', '401', 'outage'] as const)('ignores stale /me %s after logout and a same-token new login', async (result) => {
		const { store, mapping, Consumer, render } = await modules();
		store.setLoginAuth({ ...mapping.loginAuthState(login, { federated: false }).state });
		const old = Promise.withResolvers<AuthMeResponse>();
		mocks.me.mockReturnValueOnce(old.promise);
		render(Consumer); await flush();
		const signal = mocks.me.mock.calls[0][3].signal as AbortSignal;
		store.clearAuth();
		store.setLoginAuth(mapping.loginAuthState({ ...login, user_id: 'bob' }, { federated: true }).state);
		expect(signal.aborted).toBe(true);
		if (result === 'success') old.resolve({ ...me, is_system_admin: true });
		else if (result === 'invalid metadata') old.resolve({ ...me, domain_id: 'foreign' });
		else if (result === '401') old.reject(new (await import('$lib/api/client')).ApiError(401, 'expired'));
		else old.reject(new Error('offline'));
		await flush();
		await vi.advanceTimersByTimeAsync(5000);
		expect(screen.getByRole('status').textContent).toContain('/dashboard · bob');
		expect(get(store.auth)).toMatchObject({ token: login.token, userId: 'bob', federated: true, isSystemAdmin: false });
		expect(get(store.authRecovery)).toBeNull();
		expect(mocks.me).toHaveBeenCalledOnce();
	});

	it.each(['401', 'foreign home', 'foreign working domain', 'foreign project', 'foreign user'] as const)('rejects invalid restored %s without protected reads', async (kind) => {
		let loaded = await modules();
		loaded.store.setLoginAuth(loaded.mapping.loginAuthState(login, { federated: false }).state);
		vi.resetModules(); loaded = await modules();
		if (kind === '401') mocks.me.mockRejectedValueOnce(new (await import('$lib/api/client')).ApiError(401, 'expired'));
		else mocks.me.mockResolvedValueOnce({ ...me, ...(kind === 'foreign home' ? { identity_domain_id: 'foreign' }
			: kind === 'foreign working domain' ? { domain_id: 'foreign' } : kind === 'foreign project' ? { project_id: 'foreign' } : { user_id: 'foreign' }) });
		loaded.render(loaded.Consumer); await flush();
		expect(screen.getByRole('status').textContent).toBe('Signed out');
		expect(get(loaded.store.authRecovery)).toBeNull();
		expect(mocks.protectedRead).not.toHaveBeenCalled();
		expect(sessionStorage.getItem(loaded.store.AUTH_STORAGE_KEY)).toBeNull();
	});

	it('keeps restored outage retry scoped and clears recovery for a new login', async () => {
		const { store, mapping, Consumer, render } = await modules();
		store.setLoginAuth({ ...mapping.loginAuthState(login, { federated: false }).state });
		mocks.me.mockRejectedValueOnce(new Error('offline'));
		render(Consumer); await flush();
		expect(screen.getByRole('status').textContent).toBe('Verifying session');
		expect(get(store.authRecovery)?.token).toBe(login.token);
		expect(mocks.protectedRead).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(5000); await flush();
		expect(mocks.me).toHaveBeenCalledTimes(2);
		expect(screen.getByRole('status').textContent).toContain('/dashboard');
		expect(get(store.authRecovery)).toBeNull();
		store.authRecovery.set({ token: login.token, retryAt: Date.now() + 5000 });
		store.clearAuth();
		store.setLoginAuth(mapping.loginAuthState(login, { federated: false }).state);
		expect(get(store.authRecovery)).toBeNull();
	});

	it('never transfers mock readiness into restored real credentials', async () => {
		const { store, mapping, Consumer, render } = await modules();
		store.setLoginAuth(mapping.loginAuthState(login, { federated: false }).state);
		store.enterMockAuth({ ...get(store.auth), token: 'mock' });
		const pending = Promise.withResolvers<AuthMeResponse>();
		mocks.me.mockReturnValueOnce(pending.promise);
		render(Consumer); await flush();
		mocks.protectedRead.mockClear();
		store.exitMockAuth(); await flush();
		expect(screen.getByRole('status').textContent).toBe('Verifying session');
		expect(mocks.me).toHaveBeenCalledOnce();
		expect(mocks.protectedRead).not.toHaveBeenCalled();
		pending.resolve(me); await flush();
		expect(screen.getByRole('status').textContent).toContain('/dashboard');
	});
});
