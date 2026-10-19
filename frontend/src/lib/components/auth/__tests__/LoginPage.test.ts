import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { readable, writable, get, type Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { auth, authReady, clearAuth, logoutInProgress, projectSwitching, setLoginAuth } from '$lib/stores/auth';
import { pendingMcpConsentTicket, storeMcpConsentTicket } from '$lib/utils/mcpConsent';
import { storePendingInvitation, storePendingProviderLogin, takePendingInvitationPath, takePendingProviderLogin } from '$lib/utils/domainLogin';
import { siteConfig } from '$lib/config/site';
import { createAuthVerificationController } from '$lib/utils/authVerification';
import type { LoginOptions, LoginResponse } from '$lib/types/auth';

const mocks = vi.hoisted(() => ({ get: vi.fn(), optionsGet: vi.fn(), post: vi.fn(), goto: vi.fn() }));

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
vi.mock('$app/stores', () => ({
	page: writable({ data: { mockup: { active: false } }, url: new URL('http://localhost/login') }),
}));
vi.mock('$lib/stores/theme', () => ({ resolvedTheme: readable('dark') }));
vi.mock('$lib/api/client', () => ({
	ApiError: class ApiError extends Error {
		constructor(public status: number, message: string, public code?: string) { super(message); }
	},
	api: { get: mocks.get, post: mocks.post },
}));

import { ApiError } from '$lib/api/client';
import { page } from '$app/stores';
import LoginPage from '../LoginPage.svelte';

const options: LoginOptions = { providers: [
	{ id: 'configured-oidc', name: 'Team SSO', kind: 'oidc', domain_id: 'team', domain_name: 'Team' },
	{ id: 'configured-saml', name: 'Lab SAML', kind: 'saml', domain_id: 'lab', domain_name: 'Lab' },
] };
const response: LoginResponse = {
	token: 'fresh', user_id: 'alice', username: 'Alice', project_id: 'home-project', project_name: 'Default', expires_at: null,
	identity_domain_id: 'home', identity_domain_name: 'Home', domain_id: 'home', domain_name: 'Home',
	available_domains: [{ id: 'home', name: 'Home' }, { id: 'team', name: 'Team' }],
};
const requestOptions = { cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false };
const loginPage = page as unknown as Writable<{ data: { mockup: { active: boolean } }; url: URL }>;

async function fillCredentials() {
	const username = screen.getByLabelText(/^Username or email/) as HTMLInputElement;
	const password = screen.getByLabelText(/^Password/) as HTMLInputElement;
	await fireEvent.input(username, { target: { value: 'alice@example.test' } });
	await fireEvent.input(password, { target: { value: 'secret' } });
	return { username, password, button: screen.getByRole('button', { name: /^sign in$/i }) as HTMLButtonElement };
}

async function openSso() {
	await fireEvent.click(screen.getByRole('button', { name: 'Sign in with SSO' }));
}

const changes = ['unmount', 'identity', 'identity ABA', 'token ABA', 'reauthenticate', 'reauthenticate ABA', 'logout ABA', 'scope ABA'] as const;
type Change = typeof changes[number];
function invalidate(change: Change, unmount: () => void) {
	const original = get(auth);
	const entry = get(loginPage);
	if (change === 'unmount') unmount();
	else if (change.startsWith('reauthenticate')) {
		loginPage.set({ ...entry, url: new URL('http://localhost/login?reauthenticate=1') });
		if (change.endsWith('ABA')) loginPage.set(entry);
	} else if (change === 'logout ABA' || change === 'scope ABA') {
		const flag = change === 'logout ABA' ? logoutInProgress : projectSwitching;
		flag.set(true); flag.set(false);
	} else {
		auth.set({ ...original, ...(change === 'token ABA' ? { token: 'rotated' }
			: { token: 'replacement', userId: 'bob', identityDomainId: 'other-home', domainId: 'other-home' }) });
		if (change.endsWith('ABA')) auth.set(original);
	}
}

beforeEach(() => {
	mocks.optionsGet.mockReset().mockResolvedValue(options);
	mocks.get.mockReset().mockImplementation((path: string, ...args: unknown[]) => {
		if (path === '/api/v1/auth/login-options') return mocks.optionsGet(path, ...args);
		if (path === '/api/v1/site-config') return Promise.resolve(get(siteConfig));
		throw new Error(`Unexpected GET in login fixture: ${path}`);
	});
	mocks.post.mockReset();
	mocks.goto.mockReset().mockResolvedValue(undefined);
	initLocale('en'); clearAuth(); sessionStorage.clear();
	logoutInProgress.set(false); projectSwitching.set(false);
	loginPage.set({ data: { mockup: { active: false } }, url: new URL('http://localhost/login') });
});
afterEach(() => { cleanup(); clearAuth(); logoutInProgress.set(false); projectSwitching.set(false); sessionStorage.clear(); initLocale('ko'); });

describe('public home-first login', () => {
	it('shows credentials, unique-email help, signup and recovery without a domain form or waiting for discovery', async () => {
		mocks.optionsGet.mockReturnValueOnce(Promise.withResolvers<LoginOptions>().promise);
		render(LoginPage);
		expect(screen.getByLabelText(/^Username or email/)).toBeTruthy();
		expect(screen.getByLabelText(/^Password/)).toBeTruthy();
		expect(screen.queryByLabelText(/^Domain/i)).toBeNull();
		expect(screen.getByText('Use a globally unique email address (recommended) or username. Duplicate usernames or email addresses cannot sign in.')).toBeTruthy();
		expect(screen.getByRole('link', { name: 'Sign up with email' }).getAttribute('href')).toBe('/signup');
		expect(screen.getByRole('link', { name: 'Recover account' }).getAttribute('href')).toBe('/recover');
		await waitFor(() => expect(mocks.optionsGet).toHaveBeenCalledWith('/api/v1/auth/login-options', undefined, undefined, requestOptions));
	});

	it('keeps provider choices off the main form until SSO is explicitly opened, without selecting a domain', async () => {
		render(LoginPage);
		await waitFor(() => expect(mocks.optionsGet).toHaveBeenCalledOnce());
		expect(screen.queryByRole('button', { name: 'Continue with Team SSO' })).toBeNull();
		await openSso();
		for (const provider of options.providers) expect(await screen.findByRole('button', { name: `Continue with ${provider.name}` })).toBeTruthy();
		expect(screen.queryByLabelText(/^Password/)).toBeNull();
		expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Organization SSO' }));
		expect(mocks.optionsGet).toHaveBeenCalledOnce();
		expect(mocks.post).not.toHaveBeenCalled();
		expect(screen.queryByLabelText(/^Domain/i)).toBeNull();
	});

	it('clears the password when changing methods, restores focus and preserves continuation intents without changing auth', async () => {
		storeMcpConsentTicket('m'.repeat(32)); storePendingInvitation('i'.repeat(32));
		render(LoginPage);
		await fillCredentials();
		const original = get(auth);
		await openSso();
		await fireEvent.click(screen.getByRole('button', { name: 'Back to password sign-in' }));
		const username = screen.getByLabelText(/^Username or email/) as HTMLInputElement;
		expect(username.value).toBe('alice@example.test');
		expect((screen.getByLabelText(/^Password/) as HTMLInputElement).value).toBe('');
		expect(document.activeElement).toBe(username);
		expect(get(auth)).toEqual(original);
		expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
		expect(takePendingInvitationPath()).toBe(`/invitations/${'i'.repeat(32)}`);
		expect(mocks.post).not.toHaveBeenCalled(); expect(mocks.goto).not.toHaveBeenCalled();
	});

	it('keeps discovery loading separate from credential locks and reuses the catalog across method changes', async () => {
		const pending = Promise.withResolvers<LoginOptions>(); mocks.optionsGet.mockReturnValueOnce(pending.promise);
		render(LoginPage);
		await openSso();
		expect(screen.getByText('Loading SSO sign-in options…')).toBeTruthy();
		expect(screen.queryByText('No SSO sign-in options are available right now.')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Back to password sign-in' }));
		await openSso();
		pending.resolve(options);
		expect(await screen.findByRole('button', { name: 'Continue with Team SSO' })).toBeTruthy();
		expect(mocks.optionsGet).toHaveBeenCalledOnce(); expect(mocks.post).not.toHaveBeenCalled();
	});

	it('shows an unavailable SSO choice list as empty only after successful discovery and allows return to credentials', async () => {
		mocks.optionsGet.mockResolvedValueOnce({ providers: [] });
		render(LoginPage);
		await openSso();
		expect(await screen.findByText('No SSO sign-in options are available right now.')).toBeTruthy();
		expect(screen.queryByText('Public sign-in providers cannot be discovered right now. Try again shortly.')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Back to password sign-in' }));
		expect(screen.getByLabelText(/^Password/)).toBeTruthy(); expect(mocks.post).not.toHaveBeenCalled();
	});

	it('disambiguates equal provider names by origin and authorizes only the chosen registration', async () => {
		mocks.optionsGet.mockResolvedValueOnce({ providers: options.providers.map(provider => ({ ...provider, name: 'GitLab' })) });
		mocks.post.mockRejectedValueOnce(new ApiError(503, 'private-authorize-error'));
		render(LoginPage); await openSso();
		expect(await screen.findByRole('button', { name: 'Continue with GitLab · Team' })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'Continue with GitLab · Lab' }));
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/domains/lab/providers/configured-saml/authorize', {}, undefined, undefined, requestOptions);
		expect(await screen.findByText('This sign-in method is not available right now.')).toBeTruthy();
		expect(document.body.textContent).not.toContain('private-authorize-error');
		await fireEvent.click(screen.getByRole('button', { name: 'Back to password sign-in' }));
		expect(screen.queryByText('This sign-in method is not available right now.')).toBeNull();
	});

	it('keeps password login available when public provider discovery fails without exposing server text', async () => {
		mocks.optionsGet.mockRejectedValueOnce(new ApiError(503, 'private-provider-error'));
		mocks.post.mockResolvedValueOnce(response);
		render(LoginPage);
		await openSso();
		expect(await screen.findByText('Public sign-in providers cannot be discovered right now. Try again shortly.')).toBeTruthy();
		expect(document.body.textContent).not.toContain('private-provider-error');
		await fireEvent.click(screen.getByRole('button', { name: 'Back to password sign-in' }));
		const { password, button } = await fillCredentials();
		password.form!.requestSubmit(button);
		await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/select-domain'));
	});

	it('submits credentials natively once before disabled controls render, and disables all methods while pending', async () => {
		const pending = Promise.withResolvers<LoginResponse>();
		mocks.post.mockReturnValueOnce(pending.promise);
		render(LoginPage);
		const provider = screen.getByRole('button', { name: 'Sign in with SSO' }) as HTMLButtonElement;
		const { username, password, button } = await fillCredentials();
		const form = password.form!;
		expect(username.form).toBe(form); expect(button.form).toBe(form); expect(button.type).toBe('submit');
		expect(Array.from(form.elements).filter(control => control instanceof HTMLButtonElement && control.type === 'submit')).toEqual([button]);
		const submitted = vi.fn(); form.addEventListener('submit', submitted);
		// jsdom has no implicit Enter default action; requestSubmit dispatches a native SubmitEvent.
		form.requestSubmit(button); form.requestSubmit(button);
		await waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
		expect(submitted).toHaveBeenCalledTimes(2);
		expect(submitted.mock.calls[0][0].submitter).toBe(button);
		expect(submitted.mock.calls[0][0].defaultPrevented).toBe(true);
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/login', { username: 'alice@example.test', password: 'secret' }, undefined, undefined, requestOptions);
		await waitFor(() => expect(button.disabled).toBe(true));
		expect(username.disabled).toBe(true); expect(password.disabled).toBe(true); expect(provider.disabled).toBe(true);
		await fireEvent.click(provider); expect(mocks.post).toHaveBeenCalledOnce();
		pending.reject(new ApiError(401, 'private-credential-error'));
		expect(await screen.findByText('The username or email address, or password, is incorrect.')).toBeTruthy();
		expect(button.disabled).toBe(false); expect(provider.disabled).toBe(false);
		expect(mocks.goto).not.toHaveBeenCalled(); expect(document.body.textContent).not.toContain('private-credential-error');
	});

	it('does not submit missing credentials through the native form', async () => {
		render(LoginPage);
		const password = screen.getByLabelText(/^Password/) as HTMLInputElement;
		await fireEvent.input(screen.getByLabelText(/^Username or email/), { target: { value: 'alice' } });
		password.form!.requestSubmit();
		expect(mocks.post).not.toHaveBeenCalled();
		expect((screen.getByRole('button', { name: /^sign in$/i }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('cancels composing and IME229 commit Enter in both credentials while ordinary Enter remains native', async () => {
		mocks.post.mockRejectedValueOnce(new ApiError(401, 'invalid'));
		render(LoginPage);
		const { username, password, button } = await fillCredentials();
		for (const input of [username, password]) {
			for (const options of [{ isComposing: true }, { keyCode: 229 }]) {
				const event = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true, ...options });
				await fireEvent(input, event); expect(event.defaultPrevented).toBe(true);
			}
			const enter = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
			await fireEvent(input, enter); expect(enter.defaultPrevented).toBe(false);
		}
		expect(mocks.post).not.toHaveBeenCalled();
		password.form!.requestSubmit(button);
		await waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
	});

	it('authorizes against the clicked provider origin once and locks provider selection and back navigation while pending', async () => {
		const pending = Promise.withResolvers<{ authorize_url: string }>();
		mocks.post.mockReturnValueOnce(pending.promise);
		render(LoginPage); await openSso();
		const provider = await screen.findByRole('button', { name: 'Continue with Lab SAML' }) as HTMLButtonElement;
		const back = screen.getByRole('button', { name: 'Back to password sign-in' }) as HTMLButtonElement;
		await fireEvent.click(provider); await fireEvent.click(provider); await fireEvent.click(back);
		expect(mocks.post).toHaveBeenCalledOnce();
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/domains/lab/providers/configured-saml/authorize', {}, undefined, undefined, requestOptions);
		expect(provider.disabled).toBe(true); expect(back.disabled).toBe(true);
		expect(screen.queryByLabelText(/^Password/)).toBeNull();
		pending.resolve({ authorize_url: 'javascript:alert(1)' });
		await waitFor(() => expect(provider.disabled).toBe(false));
		expect(back.disabled).toBe(false);
		expect(takePendingProviderLogin()).toBeNull(); expect(get(auth).token).toBeNull();
	});

	it.each(changes)('discards a late password session and clears credentials after %s, including synchronous ABA', async change => {
		const pending = Promise.withResolvers<LoginResponse>();
		mocks.post.mockImplementation((path: string) => path === '/api/v1/auth/login' ? pending.promise : Promise.resolve({}));
		const rendered = render(LoginPage);
		const { username, password, button } = await fillCredentials();
		password.form!.requestSubmit(button);
		expect(mocks.post).toHaveBeenCalledOnce();
		invalidate(change, rendered.unmount);
		await tick();
		if (change !== 'unmount') { expect(username.value).toBe(''); expect(password.value).toBe(''); }
		const currentToken = get(auth).token;
		pending.resolve(response);
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/logout', {}, response.token, undefined, requestOptions));
		expect(get(auth).token).toBe(currentToken); expect(mocks.goto).not.toHaveBeenCalled();
	});

	it.each(changes)('does not expose late password errors after %s', async change => {
		const pending = Promise.withResolvers<LoginResponse>(); mocks.post.mockReturnValueOnce(pending.promise);
		const rendered = render(LoginPage);
		const { password, button } = await fillCredentials(); password.form!.requestSubmit(button);
		invalidate(change, rendered.unmount);
		pending.reject(new ApiError(401, 'stale-error'));
		await tick(); await Promise.resolve(); await tick();
		expect(screen.queryByText('The username or email address, or password, is incorrect.')).toBeNull();
		expect(mocks.goto).not.toHaveBeenCalled(); expect(mocks.post).toHaveBeenCalledOnce();
	});

	it.each(changes.filter(change => change !== 'unmount'))('keeps slow public discovery usable after %s', async change => {
		const pending = Promise.withResolvers<LoginOptions>(); mocks.optionsGet.mockReturnValueOnce(pending.promise);
		const rendered = render(LoginPage);
		await waitFor(() => expect(mocks.optionsGet).toHaveBeenCalledOnce());
		invalidate(change, rendered.unmount); pending.resolve(options);
		await pending.promise; await tick();
		await openSso();
		expect(await screen.findByRole('button', { name: 'Continue with Team SSO' })).toBeTruthy();
		expect(mocks.optionsGet).toHaveBeenCalledOnce();
		expect(mocks.post).not.toHaveBeenCalled(); expect(mocks.goto).not.toHaveBeenCalled();
	});

	it.each([logoutInProgress, projectSwitching])('renders a slow public catalog during a session lock and enables it after release', async flag => {
		const pending = Promise.withResolvers<LoginOptions>(); mocks.optionsGet.mockReturnValueOnce(pending.promise);
		render(LoginPage);
		await waitFor(() => expect(mocks.optionsGet).toHaveBeenCalledOnce());
		await openSso();
		flag.set(true); pending.resolve(options);
		const provider = await screen.findByRole('button', { name: 'Continue with Team SSO' }) as HTMLButtonElement;
		expect(provider.disabled).toBe(true);
		flag.set(false); await tick();
		expect(provider.disabled).toBe(false);
		expect(mocks.optionsGet).toHaveBeenCalledOnce();
		expect(mocks.post).not.toHaveBeenCalled(); expect(mocks.goto).not.toHaveBeenCalled();
	});

	it.each(changes)('does not store a pending redirect from late provider authorization after %s', async change => {
		const pending = Promise.withResolvers<{ authorize_url: string }>(); mocks.post.mockReturnValueOnce(pending.promise);
		const rendered = render(LoginPage);
		await openSso();
		await fireEvent.click(await screen.findByRole('button', { name: 'Continue with Team SSO' }));
		invalidate(change, rendered.unmount);
		pending.resolve({ authorize_url: 'https://idp.example.test/authorize' });
		await pending.promise; await tick();
		expect(takePendingProviderLogin()).toBeNull(); expect(mocks.post).toHaveBeenCalledOnce(); expect(mocks.goto).not.toHaveBeenCalled();
	});

	it.each([['home-project', false], ['', false], ['home-project', true], ['', true]] as const)(
		'publishes fresh password readiness and chooses a domain for home project=%s multiple=%s without /me or consuming intents', async (project, multiple) => {
			const verification = createAuthVerificationController(); verification.setEnabled(true);
			try {
				mocks.post.mockResolvedValueOnce({ ...response, project_id: project, default_project_id: 'hint-only', available_domains: multiple ? response.available_domains : [{ id: 'home', name: 'Home' }] });
				storeMcpConsentTicket('m'.repeat(32)); storePendingInvitation('i'.repeat(32));
				mocks.goto.mockImplementation(async () => { expect(get(authReady)).toBe(true); });
				render(LoginPage);
				const { password, button } = await fillCredentials(); password.form!.requestSubmit(button);
				await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/select-domain'));
				expect(get(authReady)).toBe(true);
				expect(get(auth)).toMatchObject({ projectId: project || null, projectName: project ? 'Default' : null, domainId: 'home', identityDomainId: 'home', federated: false });
				expect(mocks.get.mock.calls.some(([path]) => path === '/api/v1/auth/me')).toBe(false);
				expect(pendingMcpConsentTicket()).toBe('m'.repeat(32)); expect(takePendingInvitationPath()).toBe(`/invitations/${'i'.repeat(32)}`);
			} finally { verification.dispose(); }
		},
	);

	it('keeps the successful login pending during navigation so a second native submit cannot send again', async () => {
		const navigation = Promise.withResolvers<void>(); mocks.goto.mockReturnValueOnce(navigation.promise);
		mocks.post.mockResolvedValueOnce(response);
		render(LoginPage);
		const { password, button } = await fillCredentials(); password.form!.requestSubmit(button);
		await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/select-domain'));
		expect(button.disabled).toBe(true); expect(password.value).toBe('');
		await fireEvent.input(password, { target: { value: 'another-secret' } });
		password.form!.requestSubmit(button);
		expect(mocks.post).toHaveBeenCalledOnce(); expect(mocks.goto).toHaveBeenCalledOnce();
		navigation.resolve();
	});

	it('allows public reauthenticate=1 while signed in without a domain and preserves the original session until fresh success', async () => {
		setLoginAuth({ token: 'original', userId: 'alice', identityDomainId: 'home', domainId: 'team', projectId: 'team-project' });
		loginPage.set({ data: { mockup: { active: false } }, url: new URL('http://localhost/login?reauthenticate=1') });
		mocks.post.mockResolvedValueOnce(response);
		render(LoginPage);
		expect(screen.getByRole('button', { name: 'Sign in with SSO' })).toBeTruthy();
		expect(get(auth)).toMatchObject({ token: 'original', domainId: 'team' }); expect(mocks.goto).not.toHaveBeenCalled();
		const { password, button } = await fillCredentials(); password.form!.requestSubmit(button);
		await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/select-domain'));
		expect(get(auth)).toMatchObject({ token: 'fresh', identityDomainId: 'home', domainId: 'home' });
	});

	it.each([
		['project-a', false, false, '/dashboard'], ['', false, false, '/select-project'],
		['project-a', true, false, '/dashboard'], ['', true, false, '/select-domain'],
		['project-a', true, true, '/oauth/mcp/authorize'], ['', true, true, '/select-domain'],
	] as const)('keeps existing-session navigation normal for project=%s multiple=%s consent=%s', async (projectId, multiple, consent, target) => {
		setLoginAuth({ token: 'existing', userId: 'u', identityDomainId: 'home', domainId: 'team', projectId,
			availableDomains: multiple ? response.available_domains : [{ id: 'team', name: 'Team' }] });
		storePendingInvitation('i'.repeat(32)); if (consent) storeMcpConsentTicket('m'.repeat(32));
		render(LoginPage);
		await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith(target));
		expect(mocks.optionsGet).not.toHaveBeenCalled(); expect(mocks.post).not.toHaveBeenCalled();
		expect(takePendingInvitationPath()).toBe(`/invitations/${'i'.repeat(32)}`);
		if (consent) expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
	});

	it('rejects and revokes a fresh password response whose working domain is not its identity home', async () => {
		mocks.post.mockImplementation(async (path: string) => path === '/api/v1/auth/login' ? { ...response, domain_id: 'team', domain_name: 'Team' } : {});
		render(LoginPage);
		const { password, button } = await fillCredentials(); password.form!.requestSubmit(button);
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/logout', {}, response.token, undefined, requestOptions));
		expect(get(auth).token).toBeNull(); expect(mocks.goto).not.toHaveBeenCalled();
	});

	it.each([{ domainId: '', providerId: 'provider' }, { domainId: 'team', providerId: '' }])('consumes but rejects malformed pending provider origin $domainId/$providerId', pending => {
		storePendingProviderLogin(pending);
		expect(takePendingProviderLogin()).toBeNull();
		expect(sessionStorage.getItem('afterglow_provider_login')).toBeNull();
	});
});
