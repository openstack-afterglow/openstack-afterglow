import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { createRawSnippet, tick } from 'svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth, authReady, authRecovery, clearAuth, projectSwitching, setAuth, setLoginAuth, setProject } from '$lib/stores/auth';
import { loginAuthState, refreshAuthState } from '$lib/utils/authSession';
import { createAuthVerificationController } from '$lib/utils/authVerification';
import type { AuthVerificationController } from '$lib/utils/authVerification';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { ApiError } from '$lib/api/errors';
import Layout from './+layout.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$app/navigation', () => ({ afterNavigate: vi.fn(), goto: vi.fn() }));
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ data: {}, url: new URL('http://localhost/admin'), state: {}, route: { id: '/admin' } }) };
});
// Hoisted mock factories run before static imports; load the real error class at that boundary.
vi.mock('$lib/api/client', async () => ({ api: { get: mocks.get }, ApiError: (await import('$lib/api/errors')).ApiError }));
vi.mock('$lib/tutorial/status', () => ({ loadTutorialStatuses: vi.fn() }));
// The navigation chrome is unrelated to this guard's authority transitions.
vi.mock('$lib/components/AdminSidebar.svelte', () => ({ default: () => ({}) }));
const children = createRawSnippet(() => ({ render: () => '<div><p>Protected administrator data</p><input aria-label="Unsubmitted administrator draft" /></div>' }));
const login = {
	token: 'same-token', user_id: 'alice', username: 'Alice', project_id: 'project', project_name: 'Project', expires_at: null,
	identity_domain_id: 'home', identity_domain_name: 'Home', domain_id: 'home', domain_name: 'Home', is_system_admin: true,
};
let verification: AuthVerificationController | undefined;
function renderAdmin() {
	verification = createAuthVerificationController();
	verification.setEnabled(true);
	return render(Layout, { children });
}

beforeEach(() => { mocks.get.mockReset(); clearAuth(); projectSwitching.set(false); sessionStorage.clear(); initLocale('en'); });
afterEach(() => { verification?.dispose(); verification = undefined; cleanup(); clearAuth(); projectSwitching.set(false); initLocale('ko'); });

describe('administrator session readiness', () => {
	it('opens a fully mapped fresh administrator login without repeating /me', async () => {
		setLoginAuth(loginAuthState(login, { federated: false }).state);
		renderAdmin();
		expect(await screen.findByText('Protected administrator data')).toBeTruthy();
		expect(get(authReady)).toBe(true);
		expect(mocks.get).not.toHaveBeenCalled();
	});

	it('does not use incomplete login flags as administrator proof', async () => {
		const pending = Promise.withResolvers<typeof login>();
		mocks.get.mockReturnValueOnce(pending.promise);
		setLoginAuth({ ...loginAuthState(login, { federated: false }).state });
		renderAdmin();
		await tick();
		expect(mocks.get).toHaveBeenCalledOnce();
		expect(screen.queryByText('Protected administrator data')).toBeNull();
		pending.resolve(login);
		expect(await screen.findByText('Protected administrator data')).toBeTruthy();
	});

	it.each(['success', '401'] as const)('ignores old administrator /me %s after a same-token new login', async (result) => {
		const pending = Promise.withResolvers<typeof login>();
		mocks.get.mockReturnValueOnce(pending.promise);
		setLoginAuth({ ...loginAuthState(login, { federated: false }).state });
		renderAdmin();
		await tick();
		expect(mocks.get).toHaveBeenCalledOnce();
		clearAuth();
		setLoginAuth(loginAuthState({ ...login, user_id: 'bob', is_system_admin: false }, { federated: false }).state);
		if (result === 'success') pending.resolve(login);
		else pending.reject(new ApiError(401, 'expired'));
		await tick(); await Promise.resolve(); await tick();
		expect(get(auth)).toMatchObject({ token: login.token, userId: 'bob', isSystemAdmin: false });
		expect(get(authReady)).toBe(true);
		expect(screen.queryByText('Protected administrator data')).toBeNull();
		expect(mocks.get).toHaveBeenCalledOnce();
	});

	it('retains the mounted administrator draft during root verification of a native refresh', async () => {
		setLoginAuth(loginAuthState(login, { federated: false }).state);
		renderAdmin();
		const draft = await screen.findByRole('textbox', { name: 'Unsubmitted administrator draft' }) as HTMLInputElement;
		draft.value = 'Keep this unsent change';
		const pending = Promise.withResolvers<typeof login>();
		mocks.get.mockReturnValueOnce(pending.promise);
		setAuth(refreshAuthState({ ...login, token: 'rotated-token' }, get(auth)));
		await tick();
		expect(get(authReady)).toBe(true);
		expect(mocks.get).toHaveBeenCalledOnce();
		expect(screen.getByRole('textbox', { name: 'Unsubmitted administrator draft' })).toBe(draft);
		expect(draft.value).toBe('Keep this unsent change');
		pending.resolve({ ...login, token: 'rotated-token' });
		await tick(); await Promise.resolve(); await tick();
		expect(screen.getByRole('textbox', { name: 'Unsubmitted administrator draft' })).toBe(draft);
	});

	it('removes administrator data when root verification confirms a revoked grant', async () => {
		setLoginAuth(loginAuthState(login, { federated: false }).state);
		renderAdmin();
		await screen.findByText('Protected administrator data');
		const pending = Promise.withResolvers<typeof login>();
		mocks.get.mockReturnValueOnce(pending.promise);
		setAuth(refreshAuthState({ ...login, token: 'rotated-token' }, get(auth)));
		pending.resolve({ ...login, is_system_admin: false });
		await waitFor(() => expect(get(auth).isSystemAdmin).toBe(false));
		expect(screen.queryByText('Protected administrator data')).toBeNull();
		expect(get(auth).token).toBe('rotated-token');
	});

	it('masks the old workspace as soon as an explicit scope change starts', async () => {
		setLoginAuth(loginAuthState(login, { federated: false }).state);
		renderAdmin();
		await screen.findByText('Protected administrator data');
		projectSwitching.set(true);
		await tick();
		expect(screen.queryByText('Protected administrator data')).toBeNull();
		projectSwitching.set(false);
		expect(await screen.findByText('Protected administrator data')).toBeTruthy();
		expect(mocks.get).not.toHaveBeenCalled();
	});

	it.each(['401', 'outage'] as const)('fails closed when root verification reports %s', async (result) => {
		setLoginAuth({ ...loginAuthState(login, { federated: false }).state });
		mocks.get.mockRejectedValueOnce(result === '401' ? new ApiError(401, 'expired') : new ApiError(503, 'unavailable'));
		renderAdmin();
		await waitFor(() => expect(result === '401' ? get(auth).token : get(authRecovery)?.token).toBe(result === '401' ? null : login.token));
		expect(get(authReady)).toBe(false);
		expect(screen.queryByText('Protected administrator data')).toBeNull();
		expect(mocks.get).toHaveBeenCalledOnce();
	});

	it('cannot reuse a verified administrator view through an unverified same-tick scope ABA', async () => {
		setLoginAuth(loginAuthState(login, { federated: false }).state);
		renderAdmin();
		await screen.findByText('Protected administrator data');
		const original = get(auth);
		const old = Promise.withResolvers<typeof login>();
		const current = Promise.withResolvers<typeof login>();
		mocks.get.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
		setProject('other-project', 'Other');
		auth.set(original);
		old.resolve({ ...login, is_system_admin: true });
		await tick(); await Promise.resolve(); await tick();
		expect(get(authReady)).toBe(false);
		expect(screen.queryByText('Protected administrator data')).toBeNull();
		current.resolve({ ...login, is_system_admin: false });
		await waitFor(() => expect(get(authReady)).toBe(true));
		expect(screen.queryByText('Protected administrator data')).toBeNull();
	});
});
