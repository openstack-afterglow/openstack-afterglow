import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get, writable, type Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth, authReady, clearAuth, logoutInProgress, projectSwitching, setLoginAuth } from '$lib/stores/auth';
import { ApiError } from '$lib/api/errors';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/domain-auth';
import { storePendingInvitation, storePendingProviderLogin, takePendingInvitationPath } from '$lib/utils/domainLogin';
import { pendingMcpConsentTicket, storeMcpConsentTicket } from '$lib/utils/mcpConsent';
import { createAuthVerificationController } from '$lib/utils/authVerification';
import Page from './+page.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), goto: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
vi.mock('$app/stores', () => ({ page: writable({ url: new URL('http://localhost/auth/callback?code=code&state=state'), data: {} }) }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, post: mocks.post }, ApiError }));
import { page } from '$app/stores';
const callbackPage = page as unknown as Writable<{ url: URL; data: object }>;
const response = {
	token: 'provider-token', refresh_token: 'provider-refresh', user_id: 'alice', username: 'alice',
	project_id: 'default-home', project_name: 'Default', expires_at: null,
	identity_domain_id: 'home', identity_domain_name: 'Home', domain_id: 'home', domain_name: 'Home',
	available_domains: [{ id: 'home', name: 'Home' }, { id: 'team', name: 'Team' }], can_create_domain: true,
};
const linkResponse = { linked: true, domain_id: 'team', domain_name: 'Team', provider_id: 'provider' };
beforeEach(() => {
	vi.resetAllMocks();
	sessionStorage.clear();
	clearAuth();
	callbackPage.set({ url: new URL('http://localhost/auth/callback?code=code&state=state'), data: {} });
	logoutInProgress.set(false); projectSwitching.set(false);
	initLocale('en');
	storePendingProviderLogin({ domainId: 'team', providerId: 'provider' });
	mocks.post.mockResolvedValue(response);
	mocks.goto.mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); clearAuth(); sessionStorage.clear(); initLocale('ko'); });

describe('provider home-first handoff', () => {
	it('accepts a credential home different from the pending provider origin and preserves invitation and MCP intents', async () => {
		storePendingInvitation('i'.repeat(32));
		storeMcpConsentTicket('m'.repeat(32));
		render(Page);
		await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/select-domain', { replaceState: true }));
		expect(get(auth)).toMatchObject({ token: 'provider-token', identityDomainId: 'home', domainId: 'home', projectId: response.project_id, federated: true, availableDomains: response.available_domains });
		expect(takePendingInvitationPath()).toBe(`/invitations/${'i'.repeat(32)}`);
		expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
	});

	it.each([
		['project-a', false], ['', false], ['project-a', true], ['', true],
	] as const)('publishes provider readiness before choosing a domain for home project=%s multiple=%s', async (project, multiple) => {
		const verification = createAuthVerificationController();
		verification.setEnabled(true);
		try {
			mocks.post.mockResolvedValueOnce({ ...response, project_id: project, default_project_id: 'hint-only',
				available_domains: multiple ? response.available_domains : [{ id: 'home', name: 'Home' }] });
			storePendingInvitation('i'.repeat(32)); storeMcpConsentTicket('m'.repeat(32));
			mocks.goto.mockImplementation(async () => { expect(get(authReady)).toBe(true); });
			render(Page);
			await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/select-domain', { replaceState: true }));
			expect(get(authReady)).toBe(true);
			expect(get(auth)).toMatchObject({ projectId: project || null, projectName: project ? response.project_name : null, domainId: 'home', identityDomainId: 'home', federated: true });
			expect(takePendingInvitationPath()).toBe(`/invitations/${'i'.repeat(32)}`);
			expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
			expect(mocks.get).not.toHaveBeenCalled();
		} finally { verification.dispose(); }
	});

	it('accepts a home-consistent fresh response when tab-local pending storage is unavailable', async () => {
		sessionStorage.removeItem('afterglow_provider_login');
		render(Page);
		await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/select-domain', { replaceState: true }));
		expect(get(auth)).toMatchObject({ token: response.token, domainId: 'home', identityDomainId: 'home' });
	});

	it('confirms original-account attachment without logging in or consuming continuation intents', async () => {
		storePendingInvitation('i'.repeat(32));
		storeMcpConsentTicket('m'.repeat(32));
		mocks.post.mockRejectedValueOnce(new ApiError(409, 'account_link_required', 'account_link_required', { link_token: 'secret-link-ticket', domain_id: 'team' }));
		const pending = Promise.withResolvers<typeof linkResponse>();
		mocks.post.mockReturnValueOnce(pending.promise);
		render(Page);
		await fireEvent.input(await screen.findByLabelText(/^Username/), { target: { value: 'alice' } });
		const password = screen.getByLabelText(/^Password/) as HTMLInputElement;
		await fireEvent.input(password, { target: { value: 'original-password' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Verify and connect' }));
		expect(mocks.post).toHaveBeenNthCalledWith(2, '/api/v1/auth/providers/link',
			{ link_token: 'secret-link-ticket', username: 'alice', password: 'original-password' }, undefined, undefined,
			expect.objectContaining({ cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false }));
		expect(password.value).toBe('');
		expect(screen.queryByRole('heading', { name: 'Account connected' })).toBeNull();
		pending.resolve(linkResponse);
		expect(await screen.findByRole('heading', { name: 'Account connected' })).toBeTruthy();
		expect(screen.getByRole('link', { name: 'Sign in again' }).getAttribute('href')).toBe('/login?reauthenticate=1');
		expect(screen.queryByLabelText(/^Password/)).toBeNull();
		expect(document.body.textContent).not.toContain('secret-link-ticket');
		expect(JSON.stringify(sessionStorage)).not.toContain('secret-link-ticket');
		expect(get(auth).token).toBeNull();
		expect(mocks.goto).not.toHaveBeenCalled();
		expect(takePendingInvitationPath()).toBe(`/invitations/${'i'.repeat(32)}`);
		expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
	});

	it('clears a rejected proof password and never reports or publishes success', async () => {
		mocks.post.mockRejectedValueOnce(new ApiError(409, '', 'account_link_required', { link_token: 'ticket', domain_id: 'team' }));
		mocks.post.mockRejectedValueOnce(new ApiError(401, 'must not render submitted-password'));
		render(Page);
		await fireEvent.input(await screen.findByLabelText(/^Username/), { target: { value: 'alice' } });
		const password = screen.getByLabelText(/^Password/) as HTMLInputElement;
		await fireEvent.input(password, { target: { value: 'submitted-password' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Verify and connect' }));
		expect(await screen.findByText('The username or email address, or password, is incorrect.')).toBeTruthy();
		expect(password.value).toBe('');
		expect(document.body.textContent).not.toContain('submitted-password');
		expect(get(auth).token).toBeNull();
		expect(mocks.goto).not.toHaveBeenCalled();
	});

	it('keeps the original signed-in session while confirming external-only account attachment', async () => {
		setLoginAuth({ token: 'original-native-session', userId: 'alice', username: 'alice', identityDomainId: 'home', domainId: 'home' });
		authReady.set(true);
		mocks.post.mockRejectedValueOnce(new ApiError(409, '', 'account_link_required', { link_token: 'authenticated-ticket', domain_id: 'team' }));
		mocks.post.mockResolvedValueOnce(linkResponse);
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: 'Approve connection as signed-in alice' }));
		expect(mocks.post).toHaveBeenNthCalledWith(2, '/api/v1/auth/providers/link/authenticated',
			{ link_token: 'authenticated-ticket' }, 'original-native-session', undefined,
			expect.objectContaining({ cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false }));
		expect(await screen.findByRole('heading', { name: 'Account connected' })).toBeTruthy();
		expect(mocks.goto).not.toHaveBeenCalled();
		expect(get(auth)).toMatchObject({ token: 'original-native-session', userId: 'alice', identityDomainId: 'home', domainId: 'home' });
		expect(screen.getByRole('link', { name: 'Sign in again' }).getAttribute('href')).toBe('/login?reauthenticate=1');
	});

	it.each([0, 503])('does not infer attachment success or replay after unconfirmed link failure %s', async (status) => {
		mocks.post.mockRejectedValueOnce(new ApiError(409, '', 'account_link_required', { link_token: 'ticket', domain_id: 'team' }));
		mocks.post.mockRejectedValueOnce(new ApiError(status, 'private-provider-error'));
		render(Page);
		await fireEvent.input(await screen.findByLabelText(/^Username/), { target: { value: 'alice' } });
		await fireEvent.input(screen.getByLabelText(/^Password/), { target: { value: 'original-password' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Verify and connect' }));
		await screen.findByRole('alert');
		expect(screen.queryByRole('heading', { name: 'Account connected' })).toBeNull();
		expect(screen.queryByLabelText(/^Password/)).toBeNull();
		expect(get(auth).token).toBeNull();
		expect(mocks.post).toHaveBeenCalledTimes(2);
		expect(mocks.goto).not.toHaveBeenCalled();
	});

	it('rejects an account-link ticket outside the pending provider registration domain', async () => {
		mocks.post.mockRejectedValueOnce(new ApiError(409, '', 'account_link_required', { link_token: 'foreign-ticket', domain_id: 'other-team' }));
		render(Page);
		await screen.findByRole('alert');
		expect(screen.queryByLabelText(/^Password/)).toBeNull();
		expect(screen.queryByRole('button', { name: 'Verify and connect' })).toBeNull();
		expect(document.body.textContent).not.toContain('foreign-ticket');
		expect(mocks.post).toHaveBeenCalledOnce(); expect(get(auth).token).toBeNull();
	});

	it.each([
		{ ...linkResponse, domain_id: 'other-domain' },
		{ ...linkResponse, provider_id: 'other-provider' },
		{ ...linkResponse, provider_id: '' },
		{ ...linkResponse, domain_name: ' ' },
		{ ...linkResponse, linked: false },
	])('rejects a link result outside the requested connection $domain_id/$provider_id/$linked', async (result) => {
		mocks.post.mockRejectedValueOnce(new ApiError(409, '', 'account_link_required', { link_token: 'ticket', domain_id: 'team' }));
		mocks.post.mockResolvedValueOnce(result);
		render(Page);
		await fireEvent.input(await screen.findByLabelText(/^Username/), { target: { value: 'alice' } });
		await fireEvent.input(screen.getByLabelText(/^Password/), { target: { value: 'original-password' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Verify and connect' }));
		await screen.findByRole('alert');
		expect(screen.queryByRole('heading', { name: 'Account connected' })).toBeNull();
		expect(get(auth).token).toBeNull();
	});

	it.each(['replacement', 'authority', 'unmount'] as const)('discards link completion after %s changes', async (change) => {
		setLoginAuth({ token: 'original-native-session', userId: 'alice', username: 'alice', identityDomainId: 'home', domainId: 'home' });
		authReady.set(true);
		const pending = Promise.withResolvers<typeof linkResponse>();
		mocks.post.mockRejectedValueOnce(new ApiError(409, '', 'account_link_required', { link_token: 'ticket', domain_id: 'team' }));
		mocks.post.mockReturnValueOnce(pending.promise);
		const rendered = render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: 'Approve connection as signed-in alice' }));
		if (change === 'replacement') setLoginAuth({ token: 'bob-session', userId: 'bob', identityDomainId: 'home', domainId: 'home' });
		else if (change === 'authority') authReady.set(false);
		else rendered.unmount();
		pending.resolve(linkResponse);
		await pending.promise;
		await tick();
		expect(screen.queryByRole('heading', { name: 'Account connected' })).toBeNull();
		expect(get(auth).token).toBe(change === 'replacement' ? 'bob-session' : 'original-native-session');
		expect(mocks.goto).not.toHaveBeenCalled();
	});

	it.each(['identity', 'readiness'] as const)('clears link credentials and ignores a pending proof after same-tick %s ABA', async kind => {
		const pending = Promise.withResolvers<typeof linkResponse>();
		mocks.post.mockRejectedValueOnce(new ApiError(409, '', 'account_link_required', { link_token: 'secret-ticket', domain_id: 'team' }));
		mocks.post.mockReturnValueOnce(pending.promise);
		render(Page);
		await fireEvent.input(await screen.findByLabelText(/^Username/), { target: { value: 'private-user' } });
		await fireEvent.input(screen.getByLabelText(/^Password/), { target: { value: 'private-password' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Verify and connect' }));
		if (kind === 'identity') {
			const original = get(auth);
			auth.set({ ...original, userId: 'bob', identityDomainId: 'another-home' }); auth.set(original);
		} else {
			const original = get(authReady); authReady.set(!original); authReady.set(original);
		}
		await tick();
		expect(screen.queryByLabelText(/^Username/)).toBeNull(); expect(screen.queryByLabelText(/^Password/)).toBeNull();
		pending.resolve(linkResponse); await pending.promise; await tick();
		expect(screen.queryByRole('heading', { name: 'Account connected' })).toBeNull();
		expect(document.body.textContent).not.toMatch(/secret-ticket|private-user|private-password/);
		expect(get(auth).token).toBeNull(); expect(mocks.goto).not.toHaveBeenCalled();
	});

	it.each([
		{ ...response, identity_domain_id: undefined },
		{ ...response, domain_id: undefined },
		{ ...response, identity_domain_name: undefined },
		{ ...response, domain_id: 'team', domain_name: 'Team' },
		{ ...response, identity_domain_id: 'foreign-home' },
	])('revokes a fresh provider response with incomplete identity or foreign working scope $domain_id/$identity_domain_id', async result => {
		mocks.post.mockImplementation((path: string) => Promise.resolve(path.endsWith('/providers/callback') ? result : {}));
		render(Page);
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/logout', {}, response.token, undefined,
			expect.objectContaining({ cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false })));
		expect(get(auth).token).toBeNull(); expect(mocks.goto).not.toHaveBeenCalled();
	});

	it('publishes personal landing separate from account identity and provider organization origin', async () => {
		const personal = { id: 'personal', name: 'Personal', kind: 'personal' };
		mocks.post.mockResolvedValueOnce({ ...response, domain_id: personal.id, domain_name: personal.name,
			identity_domain_id: 'account', identity_domain_name: 'account', project_id: 'personal-primary', project_name: 'alice-c8f572',
			available_domains: [personal, { id: 'team', name: 'Team', kind: 'organization' }] });
		render(Page);
		await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/select-domain', { replaceState: true }));
		expect(get(auth)).toMatchObject({ identityDomainId: 'account', domainId: 'personal', projectId: 'personal-primary', federated: true });
		expect(get(auth).availableDomains?.map(row => row.id)).toEqual(['personal', 'team']);
	});

	it.each(['login', 'aba', 'unmount'] as const)('revokes rather than publishing a late provider response after %s', async (kind) => {
		const pending = Promise.withResolvers<typeof response>();
		mocks.post.mockImplementation((path: string) => path.endsWith('/providers/callback') ? pending.promise : Promise.resolve({}));
		const rendered = render(Page);
		await waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
		if (kind === 'unmount') rendered.unmount();
		else {
			setLoginAuth({ token: 'new-login', userId: 'bob', identityDomainId: 'home', domainId: 'home' });
			if (kind === 'aba') clearAuth();
		}
		pending.resolve(response);
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/logout', {}, response.token, undefined, expect.objectContaining({ cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false })));
		expect(get(auth).token).toBe(kind === 'login' ? 'new-login' : null);
		expect(mocks.goto).not.toHaveBeenCalled();
	});
});

describe('restored-session provider callback readiness', () => {
	it('waits for root verification before exchanging once and preserves invitation and MCP intent', async () => {
		setLoginAuth({ token: 'restored-session', userId: 'alice', identityDomainId: 'home', domainId: 'home' });
		authReady.set(false);
		storePendingInvitation('i'.repeat(32)); storeMcpConsentTicket('m'.repeat(32));
		const pending = Promise.withResolvers<typeof response>();
		mocks.post.mockReturnValueOnce(pending.promise);
		render(Page); await tick();
		expect(mocks.post).not.toHaveBeenCalled();
		expect(mocks.get).not.toHaveBeenCalled();
		expect(sessionStorage.getItem('afterglow-provider-callback:state')).toBeNull();
		expect(screen.getByRole('status')).toBeTruthy();
		authReady.set(true);
		await waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/providers/callback', { code: 'code', state: 'state' }, undefined, undefined, expect.objectContaining({ cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false }));
		pending.resolve(response);
		await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/select-domain', { replaceState: true }));
		expect(get(auth).token).toBe(response.token);
		expect(takePendingInvitationPath()).toBe(`/invitations/${'i'.repeat(32)}`);
		expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
		expect(mocks.post).toHaveBeenCalledOnce();
		expect(mocks.get).not.toHaveBeenCalled();
	});

	it.each(['owner', 'scope', 'readiness', 'unmount'] as const)('never exchanges a waiting code after %s changes, including same-tick ABA', async kind => {
		setLoginAuth({ token: 'restored-session', userId: 'alice', identityDomainId: 'home', domainId: 'home' });
		authReady.set(false);
		const restored = get(auth);
		const rendered = render(Page); await tick();
		expect(mocks.post).not.toHaveBeenCalled();
		if (kind === 'unmount') rendered.unmount();
		else if (kind === 'readiness') { authReady.set(true); authReady.set(false); }
		else {
			auth.set({ ...restored, ...(kind === 'owner' ? { sessionId: 'replacement-session' } : { projectId: 'another-project' }) });
			auth.set(restored);
		}
		authReady.set(true); await tick();
		expect(mocks.post).not.toHaveBeenCalled();
		expect(mocks.get).not.toHaveBeenCalled();
		expect(mocks.goto).not.toHaveBeenCalled();
		expect(get(auth).token).toBe('restored-session');
		expect(screen.queryByLabelText(/^Password/)).toBeNull();
		if (kind !== 'unmount') expect(screen.getByRole('link', { name: 'Back to sign-in' }).getAttribute('href')).toBe('/login?reauthenticate=1');
	});
});

describe('provider signup approval states', () => {
	it.each(['en', 'ko', 'ja', 'zh-CN'] as const)('shows localized decisions and a fresh login without publishing tokens in %s', async locale => {
		initLocale(locale);
		for (const decision of ['pending', 'rejected'] as const) {
			for (const encoding of ['code', 'detail'] as const) {
				sessionStorage.clear();
				storePendingProviderLogin({ domainId: 'team', providerId: 'provider' });
				storePendingInvitation('i'.repeat(32)); storeMcpConsentTicket('m'.repeat(32));
				const code = `signup_approval_${decision}`;
				mocks.post.mockRejectedValueOnce(new ApiError(403, encoding === 'detail' ? code : 'private-provider-message', encoding === 'code' ? code : undefined));
				const calls = mocks.post.mock.calls.length;
				const rendered = render(Page);
				await screen.findByText(t(decision === 'pending' ? 'signup.approval.pendingTitle' : 'signup.approval.rejectedTitle'));
				const status = screen.getByRole('status');
				expect(status.textContent).toContain(t(decision === 'pending' ? 'signup.approval.pendingTitle' : 'signup.approval.rejectedTitle'));
				expect(status.textContent).toContain(t(decision === 'pending' ? 'signup.approval.providerPending' : 'signup.approval.providerRejected'));
				const fresh = screen.getByRole('link', { name: t('link.signInAgain') });
				expect(fresh.getAttribute('href')).toBe('/login?reauthenticate=1');
				await fireEvent.click(fresh);
				expect(mocks.post).toHaveBeenCalledTimes(calls + 1);
				expect(mocks.post).toHaveBeenLastCalledWith('/api/v1/auth/providers/callback', { code: 'code', state: 'state' }, undefined, undefined, expect.objectContaining({ cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false }));
				expect(get(auth).token).toBeNull();
				expect(mocks.goto).not.toHaveBeenCalled();
				expect(document.body.textContent).not.toContain('private-provider-message');
				expect(screen.queryByLabelText(t('onboarding.password'))).toBeNull();
				expect(screen.queryByText(t('callback.processing'))).toBeNull();
				expect(takePendingInvitationPath()).toBe(`/invitations/${'i'.repeat(32)}`);
				expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
				rendered.unmount();
			}
		}
	});

	it('does not replay a blocked callback when reopened, even after approval changes', async () => {
		mocks.post.mockRejectedValueOnce(new ApiError(403, '', 'signup_approval_pending'));
		const blocked = render(Page); await screen.findByText('Sign-up awaiting approval');
		blocked.unmount();
		mocks.post.mockResolvedValueOnce(response);
		render(Page);
		expect(await screen.findByText('The sign-in request expired or was not started in this browser. Sign in again.')).toBeTruthy();
		expect(mocks.post).toHaveBeenCalledOnce();
		expect(get(auth).token).toBeNull();
		expect(mocks.goto).not.toHaveBeenCalled();
	});

	it.each(['pending', 'rejected'] as const)('clears an outstanding link ticket and credentials on a %s decision', async decision => {
		mocks.post.mockRejectedValueOnce(new ApiError(409, '', 'account_link_required', { link_token: 'secret-ticket', domain_id: 'team' }));
		mocks.post.mockRejectedValueOnce(new ApiError(403, '', `signup_approval_${decision}`));
		render(Page);
		await fireEvent.input(await screen.findByLabelText(/^Username/), { target: { value: 'private-user' } });
		const password = screen.getByLabelText(/^Password/) as HTMLInputElement;
		await fireEvent.input(password, { target: { value: 'private-password' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Verify and connect' }));
		await screen.findByText(t(decision === 'pending' ? 'signup.approval.pendingTitle' : 'signup.approval.rejectedTitle'));
		expect(screen.getByRole('status').textContent).toContain(t(decision === 'pending' ? 'signup.approval.providerPending' : 'signup.approval.providerRejected'));
		expect(password.value).toBe('');
		expect(screen.queryByLabelText(/^Username/)).toBeNull();
		expect(screen.queryByRole('button', { name: 'Verify and connect' })).toBeNull();
		expect(screen.queryByText('Account connected')).toBeNull();
		expect(document.body.textContent).not.toMatch(/secret-ticket|private-password|private-user/);
		expect(get(auth).token).toBeNull(); expect(mocks.goto).not.toHaveBeenCalled();
		expect(mocks.post).toHaveBeenCalledTimes(2);
	});

	it.each(['login', 'aba', 'unmount'] as const)('does not expose a late approval decision after %s', async kind => {
		const pending = Promise.withResolvers<typeof response>(); mocks.post.mockReturnValueOnce(pending.promise);
		const rendered = render(Page); await waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
		if (kind === 'unmount') rendered.unmount();
		else {
			setLoginAuth({ token: 'new-login', userId: 'bob', identityDomainId: 'home', domainId: 'home' });
			if (kind === 'aba') clearAuth();
		}
		pending.reject(new ApiError(403, '', 'signup_approval_pending')); await tick();
		expect(screen.queryByText('Sign-up awaiting approval')).toBeNull();
		expect(screen.queryByText('Account connected')).toBeNull();
		expect(screen.queryByLabelText(/^Password/)).toBeNull();
		expect(get(auth).token).toBe(kind === 'login' ? 'new-login' : null);
		expect(mocks.goto).not.toHaveBeenCalled();
	});

	it.each(['readiness', 'logout', 'scope'] as const)('revokes a late token after same-tick %s authority ABA', async kind => {
		const pending = Promise.withResolvers<typeof response>();
		mocks.post.mockImplementation((path: string) => path.endsWith('/providers/callback') ? pending.promise : Promise.resolve({}));
		const initial = kind === 'readiness';
		const authority = kind === 'readiness' ? authReady : kind === 'logout' ? logoutInProgress : projectSwitching;
		authority.set(initial);
		render(Page); await waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
		authority.set(!initial); authority.set(initial);
		pending.resolve(response);
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/logout', {}, response.token, undefined, expect.objectContaining({ cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false })));
		expect(get(auth).token).toBeNull();
		expect(screen.queryByText('Sign-up awaiting approval')).toBeNull();
		expect(mocks.goto).not.toHaveBeenCalled();
	});
});

describe('fresh provider sign-in after approval', () => {
	it('exchanges only a new provider code and keeps preserved intents pending at the domain chooser', async () => {
		storePendingInvitation('i'.repeat(32)); storeMcpConsentTicket('m'.repeat(32));
		mocks.post.mockRejectedValueOnce(new ApiError(403, '', 'signup_approval_pending'));
		const blocked = render(Page); await screen.findByText('Sign-up awaiting approval');
		expect(get(auth).token).toBeNull();
		blocked.unmount();
		storePendingProviderLogin({ domainId: 'team', providerId: 'provider' });
		callbackPage.set({ url: new URL('http://localhost/auth/callback?code=new-code&state=new-state'), data: {} });
		mocks.post.mockResolvedValueOnce(response);
		render(Page);
		await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/select-domain', { replaceState: true }));
		expect(mocks.post).toHaveBeenCalledTimes(2);
		expect(mocks.post).toHaveBeenNthCalledWith(2, '/api/v1/auth/providers/callback', { code: 'new-code', state: 'new-state' }, undefined, undefined, expect.objectContaining({ cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false }));
		expect(get(auth).token).toBe(response.token);
		expect(takePendingInvitationPath()).toBe(`/invitations/${'i'.repeat(32)}`);
		expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
	});
});
