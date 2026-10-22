import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { get, writable, type Writable } from 'svelte/store';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/domain-auth';
import { ApiError } from '$lib/api/errors';
import { takePendingInvitationPath } from '$lib/utils/domainLogin';
import { pendingMcpConsentTicket, storeMcpConsentTicket } from '$lib/utils/mcpConsent';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), goto: vi.fn() }));
vi.mock('$app/stores', () => ({ page: writable({ params: { token: 'verified_onboarding_token_1234567890' } }) }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: null, userId: null, domainId: null, username: null }), authReady: writable(true), logoutInProgress: writable(false), projectSwitching: writable(false) }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError }));
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { page } from '$app/stores';
import Request from '../AccountEmailRequest.svelte';
import Registration from '../../../../routes/registrations/[token]/+page.svelte';
import Invitation from '../../../../routes/invitations/[token]/+page.svelte';

const account = { user_id: 'new-user', domain_id: 'personal-id', domain_name: 'Personal', identity_domain_id: 'account-id', identity_domain_name: 'account', personal_project_id: 'personal-project', personal_project_name: 'alice-c8f572', personal_domain_id: 'personal-id' };
const originalToken = 'verified_onboarding_token_1234567890';
const tokenPage = page as unknown as Writable<{ params: { token: string } }>;
beforeEach(() => {
	vi.resetAllMocks(); initLocale('en');
	sessionStorage.clear();
	auth.set({ token: null, userId: null, domainId: null, username: null } as never);
	authReady.set(true); logoutInProgress.set(false); projectSwitching.set(false);
	tokenPage.set({ params: { token: originalToken } });
	mocks.get.mockResolvedValue({ domain_id: 'joined-domain', domain_name: 'Shared name', email: 'alice@example.com', account_exists: false, expires_at: '2099-01-01T00:00:00Z', project_name: null });
	mocks.post.mockResolvedValue(account);
});
afterEach(cleanup);

function accountInput(label: string): HTMLInputElement {
	return screen.getByLabelText(text => text.replace(/\s*\*$/, '') === label) as HTMLInputElement;
}

async function fillAccount(name = 'alice', password = 'long-enough-password') {
	for (const [label, value] of [[t('onboarding.name'), name], [t('onboarding.password'), password], [t('onboarding.passwordConfirm'), password]]) {
		await fireEvent.input(accountInput(label), { target: { value } });
	}
}

describe('onboarding immutable identity and joined workspace', () => {
	it.each([
		['registration', Registration, 'Create account'],
		['invitation', Invitation, 'Create account and accept'],
	] as const)('creates a personal project through %s and separates identity, personal project and organization admission', async (kind, Component, submitLabel) => {
		render(Component);
		await screen.findByRole('textbox', { name: 'Username' });
		await fillAccount();
		await fireEvent.click(screen.getByRole('button', { name: submitLabel }));
		const signIn = await screen.findByRole('link', { name: 'Sign in' });
		expect(signIn.getAttribute('href')).toBe('/login');
		expect(mocks.post).toHaveBeenCalledWith(`/api/v1/auth/${kind === 'registration' ? 'registrations' : 'invitations'}/accept`, { token: 'verified_onboarding_token_1234567890', name: 'alice', password: 'long-enough-password' }, undefined, undefined, { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false });
		for (const value of [account.identity_domain_id, account.personal_project_id, account.personal_project_name, account.personal_domain_id]) expect(screen.getByText(value)).toBeTruthy();
		if (kind === 'invitation') expect(screen.getByText('joined-domain')).toBeTruthy();
		else expect(screen.queryByText('joined-domain')).toBeNull();
	});

	it('shows original account sign-in and recovery, never duplicate create for a verified existing email', async () => {
		mocks.get.mockResolvedValueOnce({ email: 'alice@example.com', account_exists: true, identity_domain_id: 'original-home' });
		render(Registration);
		expect((await screen.findByRole('link', { name: 'Sign in' })).getAttribute('href')).toBe('/login');
		expect(screen.getByRole('link', { name: 'Recover account' }).getAttribute('href')).toBe('/recover');
		expect(screen.queryByLabelText('Username')).toBeNull();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('allows a corrected username only with a newly entered password', async () => {
		mocks.post.mockRejectedValueOnce(new ApiError(409, 'Username already belongs to an account'));
		render(Registration);
		await screen.findByRole('textbox', { name: t('onboarding.name') });
		await fillAccount();
		await fireEvent.click(screen.getByRole('button', { name: t('registration.submit') }));
		await screen.findByText(t('onboarding.usernameUnavailable'));
		expect(accountInput(t('onboarding.name')).value).toBe('alice');
		for (const label of [t('onboarding.password'), t('onboarding.passwordConfirm')]) {
			expect(accountInput(label).value).toBe('');
		}
		await fireEvent.input(accountInput(t('onboarding.name')), { target: { value: 'alice-new' } });
		await fireEvent.click(screen.getByRole('button', { name: t('registration.submit') }));
		expect(mocks.post).toHaveBeenCalledOnce();
		await fillAccount('alice-new', 'fresh-long-password');
		await fireEvent.click(screen.getByRole('button', { name: t('registration.submit') }));
		expect((await screen.findByRole('link', { name: t('onboarding.created.signIn') })).getAttribute('href')).toBe('/login');
		expect(mocks.post).toHaveBeenCalledTimes(2);
		expect(mocks.post).toHaveBeenNthCalledWith(2, '/api/v1/auth/registrations/accept',
			{ token: originalToken, name: 'alice-new', password: 'fresh-long-password' }, undefined, undefined,
			{ suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false });
		expect(mocks.get).toHaveBeenCalledOnce();
		expect(get(auth).token).toBeNull();
	});

	it('replaces creation with sign-in and recovery when another account takes the verified email', async () => {
		mocks.post.mockRejectedValueOnce(new ApiError(409, 'Account already exists; sign in to accept an invitation'));
		render(Registration);
		await screen.findByRole('textbox', { name: 'Username' });
		await fillAccount();
		const password = screen.getByLabelText(/^Password/) as HTMLInputElement;
		await fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
		expect((await screen.findByRole('link', { name: 'Sign in' })).getAttribute('href')).toBe('/login');
		expect(screen.getByRole('link', { name: 'Recover account' }).getAttribute('href')).toBe('/recover');
		expect(password.value).toBe('');
		expect(screen.queryByRole('button', { name: 'Create account' })).toBeNull();
		expect(screen.queryByLabelText(/^Password/)).toBeNull();
		expect(mocks.post).toHaveBeenCalledOnce();
		expect(mocks.get).toHaveBeenCalledOnce();
		expect(get(auth).token).toBeNull();
	});

	it('rechecks an unclassified conflict without replaying credentials or exposing server text', async () => {
		mocks.post.mockRejectedValueOnce(new ApiError(409, 'private-directory-conflict'));
		mocks.get.mockResolvedValueOnce({ email: 'alice@example.com', account_exists: false })
			.mockResolvedValueOnce({ email: 'alice@example.com', account_exists: true });
		render(Registration);
		await screen.findByRole('textbox', { name: 'Username' }); await fillAccount();
		await fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
		await screen.findByRole('link', { name: 'Sign in' });
		expect(screen.getByRole('link', { name: 'Recover account' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'Create account' })).toBeNull();
		expect(document.body.textContent).not.toContain('private-directory-conflict');
		expect(mocks.post).toHaveBeenCalledOnce();
		expect(mocks.get).toHaveBeenCalledTimes(2);
	});

	it.each(['code', 'detail'] as const)('does not reopen creation after an uncertain enrollment %s response', async encoding => {
		const code = 'signup_enrollment_recovery_required';
		mocks.post.mockRejectedValueOnce(new ApiError(409, encoding === 'detail' ? code : 'private-server-message', encoding === 'code' ? code : undefined));
		render(Registration);
		await screen.findByRole('textbox', { name: 'Username' }); await fillAccount();
		const password = screen.getByLabelText(/^Password/) as HTMLInputElement;
		await fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
		await screen.findByText(t('onboarding.unavailable'));
		expect(password.value).toBe('');
		expect(screen.queryByRole('button', { name: 'Create account' })).toBeNull();
		expect(screen.queryByLabelText(/^Password/)).toBeNull();
		expect(document.body.textContent).not.toContain('private-server-message');
		expect(mocks.post).toHaveBeenCalledOnce();
		expect(mocks.get).toHaveBeenCalledOnce();
	});

	it('routes a verified existing invitee to home-first sign-in without presenting duplicate create', async () => {
		mocks.get.mockResolvedValueOnce({ domain_id: 'joined-domain', domain_name: 'Team', email: 'alice@example.com', account_exists: true, identity_domain_id: 'original-home', expires_at: '2099-01-01T00:00:00Z', project_name: null });
		render(Invitation);
		await fireEvent.click(await screen.findByRole('button', { name: 'Sign in to accept' }));
		expect(mocks.goto).toHaveBeenCalledWith('/login');
		expect(takePendingInvitationPath()).toBe(`/invitations/${originalToken}`);
		expect(screen.queryByLabelText(/^Username/)).toBeNull();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('allows the original account to accept a foreign working-domain invitation without a new identity', async () => {
		const session = { token: 'home-token', userId: 'existing-user', domainId: 'personal-id', identityDomainId: 'original-home', username: 'alice' };
		auth.set(session as never);
		mocks.post.mockResolvedValueOnce({ ...account, user_id: session.userId, identity_domain_id: session.identityDomainId, identity_domain_name: 'Original home' });
		render(Invitation);
		await fireEvent.click(await screen.findByRole('button', { name: 'Accept as alice' }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/invitations/accept-existing', { token: 'verified_onboarding_token_1234567890' }, 'home-token', undefined, { cache: 'no-store', replayOnUnauthorized: false });
		expect(get(auth)).toEqual(session);
		expect(screen.getByText(session.identityDomainId)).toBeTruthy();
		expect((await screen.findByRole('link', { name: 'Choose working domain and project' })).getAttribute('href')).toBe('/select-domain');
	});
	it('publishes one-use acceptance after same-session bearer rotation', async () => {
		const session = { token: 'old-token', sessionId: 'session', userId: 'existing-user', domainId: 'home-domain', identityDomainId: 'home-domain', username: 'alice' };
		auth.set(session as never);
		const result = Promise.withResolvers<typeof account>();
		mocks.post.mockImplementation(() => {
			auth.set({ ...session, token: 'refreshed-token' } as never);
			return result.promise;
		});
		render(Invitation);
		await fireEvent.click(await screen.findByRole('button', { name: 'Accept as alice' }));
		result.resolve({ ...account, user_id: session.userId, identity_domain_id: session.identityDomainId });
		expect(await screen.findByRole('link', { name: 'Choose working domain and project' })).toBeTruthy();
		expect(mocks.post).toHaveBeenCalledOnce();
	});

	it.each(['user', 'identity'] as const)('does not publish a successful invitation response for a foreign %s', async field => {
		const session = { token: 'original-token', sessionId: 'session', userId: 'existing-user', identityDomainId: 'original-home', domainId: 'personal-id', username: 'alice' };
		auth.set(session as never);
		mocks.post.mockResolvedValueOnce({ ...account, user_id: field === 'user' ? 'other-user' : session.userId,
			identity_domain_id: field === 'identity' ? 'other-home' : session.identityDomainId, personal_project_name: 'foreign-result' });
		render(Invitation);
		await fireEvent.click(await screen.findByRole('button', { name: 'Accept as alice' }));
		await screen.findByText(t('onboarding.unavailable'));
		expect(screen.queryByText('foreign-result')).toBeNull();
		expect(screen.queryByRole('link', { name: 'Choose working domain and project' })).toBeNull();
		expect(get(auth)).toEqual(session);
		expect(mocks.post).toHaveBeenCalledOnce();
	});

	it.each(['replacement', 'same-tick logout/login'])('discards consumed acceptance after %s', async (change) => {
		const session = { token: 'old-token', sessionId: 'session', userId: 'existing-user', domainId: 'home-domain', identityDomainId: 'home-domain', username: 'alice' };
		auth.set(session as never);
		const result = Promise.withResolvers<typeof account>();
		mocks.post.mockReturnValue(result.promise);
		render(Invitation);
		await fireEvent.click(await screen.findByRole('button', { name: 'Accept as alice' }));
		if (change === 'replacement') auth.set({ ...session, sessionId: 'another-session' } as never);
		else { auth.set({ ...session, token: null } as never); auth.set(session as never); }
		result.resolve({ ...account, user_id: session.userId });
		await waitFor(() => expect((screen.getByRole('button', { name: 'Accept as alice' }) as HTMLButtonElement).disabled).toBe(false));
		expect(screen.queryByRole('link', { name: 'Choose working domain and project' })).toBeNull();
	});
});

describe('public registration approval decisions', () => {
	it.each(['en', 'ko', 'ja', 'zh-CN'] as const)('renders localized verify decisions without account or login success in %s', async locale => {
		initLocale(locale);
		for (const decision of ['pending', 'rejected'] as const) {
			for (const encoding of ['code', 'detail'] as const) {
				const code = `signup_approval_${decision}`;
				mocks.get.mockRejectedValueOnce(new ApiError(403, encoding === 'detail' ? code : 'private-server-message', encoding === 'code' ? code : undefined));
				const rendered = render(Registration);
				await screen.findByText(t(decision === 'pending' ? 'signup.approval.pendingTitle' : 'signup.approval.rejectedTitle'));
				const status = screen.getByRole('status');
				expect(status.textContent).toContain(t(decision === 'pending' ? 'signup.approval.pendingTitle' : 'signup.approval.rejectedTitle'));
				expect(status.textContent).toContain(t(decision === 'pending' ? 'signup.approval.emailPending' : 'signup.approval.emailRejected'));
				expect(screen.getByRole('link', { name: t('signup.approval.restart') }).getAttribute('href')).toBe('/signup');
				expect(screen.queryByLabelText(t('onboarding.name'))).toBeNull();
				expect(screen.queryByRole('link', { name: t('onboarding.created.signIn') })).toBeNull();
				expect(document.body.textContent).not.toContain('private-server-message');
				expect(get(auth).token).toBeNull();
				expect(mocks.post).not.toHaveBeenCalled();
				rendered.unmount();
			}
		}
	});

	it.each(['pending', 'rejected'] as const)('clears credentials and removes accept flow after %s, with no automatic replay', async decision => {
		mocks.post.mockRejectedValueOnce(new ApiError(403, `signup_approval_${decision}`));
		render(Registration);
		await screen.findByRole('textbox', { name: 'Username' });
		await fillAccount();
		const password = screen.getByLabelText(/^Password/) as HTMLInputElement;
		const confirm = screen.getByLabelText(/^Confirm password/) as HTMLInputElement;
		await fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
		await screen.findByText(t(decision === 'pending' ? 'signup.approval.pendingTitle' : 'signup.approval.rejectedTitle'));
		expect(screen.getByRole('status').textContent).toContain(t(decision === 'pending' ? 'signup.approval.emailPending' : 'signup.approval.emailRejected'));
		expect(password.value).toBe(''); expect(confirm.value).toBe('');
		expect(screen.queryByLabelText(/^Username/)).toBeNull();
		expect(screen.queryByText('Account created')).toBeNull();
		expect(screen.queryByRole('button', { name: 'Create account' })).toBeNull();
		expect(screen.getByRole('link', { name: 'Start a new email verification' }).getAttribute('href')).toBe('/signup');
		expect(get(auth).token).toBeNull();
		expect(mocks.post).toHaveBeenCalledOnce();
		expect(mocks.get).toHaveBeenCalledOnce();
	});

	it('starts with a fresh email request and new token after approval instead of reusing blocked credentials', async () => {
		mocks.post.mockRejectedValueOnce(new ApiError(403, '', 'signup_approval_pending'));
		const blocked = render(Registration);
		await screen.findByRole('textbox', { name: 'Username' }); await fillAccount();
		await fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
		expect((await screen.findByRole('link', { name: 'Start a new email verification' })).getAttribute('href')).toBe('/signup');
		blocked.unmount();
		mocks.get.mockResolvedValueOnce({ signup_enabled: true, smtp_configured: true, recovery_enabled: true });
		const request = render(Request, { signup: true });
		await fireEvent.input(await screen.findByLabelText(/^Email/), { target: { value: 'alice@example.com' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Send verification link' }));
		await screen.findByText('If this address can sign up, a verification link has been sent. Check your inbox.');
		expect(mocks.post).toHaveBeenNthCalledWith(2, '/api/v1/auth/registrations', { email: 'alice@example.com' }, undefined, undefined, expect.objectContaining({ replayOnUnauthorized: false }));
		request.unmount();
		const freshToken = 'approved_new_email_token_1234567890';
		tokenPage.set({ params: { token: freshToken } });
		render(Registration);
		await screen.findByRole('textbox', { name: 'Username' });
		expect((screen.getByLabelText(/^Password/) as HTMLInputElement).value).toBe('');
		expect((screen.getByLabelText(/^Username/) as HTMLInputElement).value).toBe('');
		await fillAccount(); await fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
		expect((await screen.findByRole('link', { name: 'Sign in' })).getAttribute('href')).toBe('/login');
		expect(mocks.post).toHaveBeenNthCalledWith(3, '/api/v1/auth/registrations/accept', expect.objectContaining({ token: freshToken }), undefined, undefined, expect.objectContaining({ replayOnUnauthorized: false }));
		expect(get(auth).token).toBeNull();
	});

	it.each(['verify', 'accept'] as const)('hides late %s results after login or same-tick ABA', async phase => {
		for (const aba of [false, true]) {
			const result = Promise.withResolvers<typeof account>();
			if (phase === 'verify') mocks.get.mockReturnValueOnce(result.promise);
			else mocks.post.mockReturnValueOnce(result.promise);
			const calls = mocks.get.mock.calls.length;
			const rendered = render(Registration);
			if (phase === 'accept') {
				await screen.findByRole('textbox', { name: 'Username' }); await fillAccount();
				await fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
			} else await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(calls + 1));
			auth.set({ token: 'other-token', sessionId: 'other-session', userId: 'other', domainId: 'other-domain' } as never);
			if (aba) auth.set({ token: null, userId: null, domainId: null, username: null } as never);
			result.resolve({ ...account, email: 'must-not-appear@example.com', account_exists: false } as typeof account);
			await result.promise; await tick();
			expect(screen.queryByLabelText(/^Username/)).toBeNull();
			expect(screen.queryByText('Account created')).toBeNull();
			expect(document.body.textContent).not.toContain('must-not-appear@example.com');
			expect(screen.getByRole('link', { name: 'Back to sign-in' })).toBeTruthy();
			rendered.unmount(); auth.set({ token: null, userId: null, domainId: null, username: null } as never);
		}
	});

	it.each(['readiness', 'logout', 'scope'] as const)('drops accept decisions after a same-tick %s authority ABA', async kind => {
		const result = Promise.withResolvers<typeof account>(); mocks.post.mockReturnValueOnce(result.promise);
		render(Registration); await screen.findByRole('textbox', { name: 'Username' }); await fillAccount();
		await fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
		const authority = kind === 'readiness' ? authReady : kind === 'logout' ? logoutInProgress : projectSwitching;
		const initial = kind === 'readiness'; authority.set(!initial); authority.set(initial);
		result.reject(new ApiError(403, '', 'signup_approval_pending'));
		await tick();
		expect(screen.queryByText('Sign-up awaiting approval')).toBeNull();
		expect(screen.queryByLabelText(/^Password/)).toBeNull();
		expect(screen.queryByText('Account created')).toBeNull();
		expect(screen.getByRole('link', { name: 'Back to sign-in' })).toBeTruthy();
	});
});

describe('new invited human approval', () => {
	it.each(['pending', 'rejected'] as const)('shows %s without consuming the invitation and keeps continuation for fresh signup', async decision => {
		mocks.post.mockRejectedValueOnce(new ApiError(403, `signup_approval_${decision}`));
		storeMcpConsentTicket('m'.repeat(32));
		render(Invitation);
		await screen.findByRole('textbox', { name: 'Username' }); await fillAccount();
		const password = screen.getByLabelText(/^Password/) as HTMLInputElement;
		await fireEvent.click(screen.getByRole('button', { name: 'Create account and accept' }));
		await screen.findByText(t(decision === 'pending' ? 'signup.approval.pendingTitle' : 'signup.approval.rejectedTitle'));
		expect(screen.getByRole('status').textContent).toContain(t(decision === 'pending' ? 'signup.approval.invitationPending' : 'signup.approval.invitationRejected'));
		expect(password.value).toBe('');
		expect(screen.queryByLabelText(/^Username/)).toBeNull();
		expect(screen.queryByText('Invitation accepted')).toBeNull();
		expect(screen.queryByText('Account created')).toBeNull();
		expect(screen.getByRole('link', { name: 'Start a new email verification' }).getAttribute('href')).toBe('/signup');
		expect(takePendingInvitationPath()).toBe(`/invitations/${originalToken}`);
		expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
		expect(mocks.post).toHaveBeenCalledOnce();
		expect(get(auth).token).toBeNull();
	});

	it('reopens an approved invitation without replaying blocked credentials or requiring public signup', async () => {
		mocks.post.mockRejectedValueOnce(new ApiError(403, '', 'signup_approval_pending'));
		render(Invitation);
		await screen.findByRole('textbox', { name: 'Username' }); await fillAccount();
		await fireEvent.click(screen.getByRole('button', { name: 'Create account and accept' }));
		await fireEvent.click(await screen.findByRole('button', { name: 'Reopen invitation after approval' }));
		expect((await screen.findByRole('textbox', { name: 'Username' }) as HTMLInputElement).value).toBe('');
		expect((screen.getByLabelText(/^Password/) as HTMLInputElement).value).toBe('');
		expect(mocks.get).toHaveBeenCalledTimes(2);
		expect(mocks.get.mock.calls[1][0]).toBe(`/api/v1/auth/invitations/${originalToken}`);
		expect(mocks.post).toHaveBeenCalledOnce();
		await fillAccount();
		await fireEvent.click(screen.getByRole('button', { name: 'Create account and accept' }));
		await screen.findByText('Account created');
		expect(mocks.post).toHaveBeenCalledTimes(2);
		expect(get(auth).token).toBeNull();
	});

	it('never exposes a late new-human decision after a same-tick auth ABA', async () => {
		const pending = Promise.withResolvers<typeof account>(); mocks.post.mockReturnValueOnce(pending.promise);
		render(Invitation); await screen.findByRole('textbox', { name: 'Username' }); await fillAccount();
		await fireEvent.click(screen.getByRole('button', { name: 'Create account and accept' }));
		auth.set({ token: 'other-session', userId: 'other', domainId: 'other' } as never);
		auth.set({ token: null, userId: null, domainId: null, username: null } as never);
		pending.reject(new ApiError(403, '', 'signup_approval_pending')); await tick();
		expect(screen.queryByText('Sign-up awaiting approval')).toBeNull();
		expect(screen.queryByLabelText(/^Password/)).toBeNull();
		expect(takePendingInvitationPath()).toBeNull();
		expect(mocks.post).toHaveBeenCalledOnce();
	});
});
