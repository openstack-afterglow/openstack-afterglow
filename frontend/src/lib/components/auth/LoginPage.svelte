<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { derived, get } from 'svelte/store';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth, logoutInProgress, projectSwitching, setLoginAuth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import AuthStudioShell from '$lib/components/auth/AuthStudioShell.svelte';
	import { siteConfig } from '$lib/config/site';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import type { LoginProviderOption, LoginOptions, LoginResponse } from '$lib/types/auth';
	import type { SignupOptions } from '$lib/types/enrollmentPolicy';
	import { loginAuthState, sessionScopeKey, type LoginAuthMapping } from '$lib/utils/authSession';
	import { loginDestination } from '$lib/utils/authFlow';
	import { freshLoginDestination, postAuthDestination, storeLumenSourceContinuation } from '$lib/utils/mcpConsent';
	import { isSafeAuthorizeUrl, storePendingProviderLogin } from '$lib/utils/domainLogin';
	import { LUMEN_SOURCE_QUERY } from '$lib/utils/lumenSourceNavigation';
	import { t } from '$lib/i18n/ns/public-entry';
	import { t as td } from '$lib/i18n/ns/domain-auth';

	// Entry redirects belong only to the session present when this page was created.
	const initialAuth = get(auth);
	let username = $state('');
	let password = $state('');
	let usernameInput = $state<HTMLInputElement | null>(null);
	let passwordInput = $state<HTMLInputElement | null>(null);
	let error = $state('');
	let personalRecovery = $state(false);
	let loading = $state(false);
	let sso = $state(false);
	let providersLoading = $state(true);
	let providers = $state<LoginProviderOption[]>([]);
	let providersError = $state(false);
	let providerLoading = $state<LoginProviderOption | null>(null);
	let signupButtonVisible = $state(false);
	let passwordVisible = $state(false);
	let generation = 0;
	let active = false;
	let publishing = false;
	const busy = $derived(loading || providerLoading !== null || $logoutInProgress || $projectSwitching);
	const providerNameCounts = $derived.by(() => {
		const counts = new Map<string, number>();
		for (const provider of providers) counts.set(provider.name, (counts.get(provider.name) ?? 0) + 1);
		return counts;
	});

	function invalidate() {
		generation++;
		username = ''; password = ''; error = '';
		passwordVisible = false;
		personalRecovery = false;
		loading = false; providerLoading = null;
	}

	onMount(() => {
		active = true;
		storeLumenSourceContinuation($page.url.searchParams.get(LUMEN_SOURCE_QUERY));
		// Subscribe synchronously so A -> B -> A identity/reauth changes cannot revive a response.
		let owner = '';
		const unsubscribe = derived([auth, logoutInProgress, projectSwitching, page], ([state, loggingOut, switching, entry]) =>
			JSON.stringify([sessionScopeKey(state), state.token, loggingOut, switching, entry.url.searchParams.get('reauthenticate') === '1'])
		).subscribe(key => {
			if (owner && key !== owner && !publishing) invalidate();
			owner = key;
		});
		if (initialAuth.token && $page.url.searchParams.get('reauthenticate') !== '1') {
			const fallback = $page.data.mockup?.active ? $page.data.mockup.homePath : loginDestination(initialAuth);
			void goto(postAuthDestination(fallback));
		} else {
			void discoverProviders();
			void discoverSignup();
		}
		return () => { active = false; invalidate(); unsubscribe(); };
	});

	async function discoverProviders() {
		// Public discovery belongs to this mounted page, not a credential/authorize attempt.
		try {
			const options = await api.get<LoginOptions>('/api/v1/auth/login-options', undefined, undefined,
				{ cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false });
			if (!active) return;
			providers = options.providers;
		} catch {
			if (active) providersError = true;
		} finally {
			if (active) providersLoading = false;
		}
	}

	async function discoverSignup() {
		// Visibility is public page-lifetime discovery, never an enrollment permission.
		try {
			const options = await api.get<SignupOptions>('/api/v1/auth/signup/options', undefined, undefined,
				{ cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false });
			if (active) signupButtonVisible = options.signup_button_visible === true
				&& options.signup_enabled === true && options.smtp_configured === true;
		} catch {
			if (active) signupButtonVisible = false;
		}
	}

	async function selectMethod(useSso: boolean) {
		if (!active || busy) return;
		password = '';
		passwordVisible = false;
		error = '';
		personalRecovery = false;
		sso = useSso;
		await tick();
		if (active && sso === useSso) document.getElementById(useSso ? 'login-sso-title' : 'login-username')?.focus();
	}

	function discardIssuedSession(token: string) {
		void api.post('/api/v1/auth/logout', {}, token, undefined, { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false }).catch(() => {});
	}

	function passwordErrorMessage(e: unknown): string {
		if (!(e instanceof ApiError)) return td('login.password.unavailable');
		if (e.code === 'personal_project_retry_available') return td('login.personalRecovery.retryHelp');
		if (e.code === 'personal_project_recovery_required') return td('login.personalRecovery.operatorHelp');
		if (e.status === 401) return td('login.password.invalid');
		if (e.status === 403) return td('login.password.forbidden');
		if (e.status === 429) return td('login.password.rateLimited');
		if (e.status === 503 || e.status === 0) return td('login.password.unavailable');
		return td('login.password.failed', { status: e.status });
	}
	async function login() {
		if (!active || busy || sso || !username || !password) return;
		const current = generation;
		loading = true;
		error = '';
		let data: LoginResponse;
		try {
			data = await api.post<LoginResponse>(
				personalRecovery ? '/api/v1/auth/personal-project/recovery' : '/api/v1/auth/login',
				{ username, password },
				undefined,
				undefined,
				{ suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false },
			);
		} catch (e) {
			if (!active || current !== generation) return;
			loading = false;
			if (e instanceof ApiError && (e.code === 'personal_project_retry_available' || e.code === 'personal_project_recovery_required')) {
				personalRecovery = true;
				password = '';
			}
			error = passwordErrorMessage(e);
			return;
		}
		if (!active || current !== generation) {
			discardIssuedSession(data.token);
			return;
		}
		let mapped: LoginAuthMapping;
		try {
			mapped = loginAuthState(data, { federated: false });
		} catch {
			discardIssuedSession(data.token);
			loading = false;
			error = td('login.sessionMismatch');
			return;
		}
		password = '';
		publishing = true;
		try { setLoginAuth(mapped.state); } finally { publishing = false; }
		await goto(freshLoginDestination(mapped.target));
	}

	async function startProvider(provider: LoginProviderOption) {
		if (!active || busy || !sso) return;
		const current = generation;
		providerLoading = provider;
		error = '';
		try {
			const res = await api.post<{ authorize_url: string }>(
				`/api/v1/auth/domains/${encodeURIComponent(provider.domain_id)}/providers/${encodeURIComponent(provider.id)}/authorize`,
				{},
				undefined,
				undefined,
				{ suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false },
			);
			if (!active || current !== generation) return;
			if (!isSafeAuthorizeUrl(res.authorize_url)) {
				providerLoading = null;
				error = td('login.provider.invalidUrl');
				return;
			}
			storePendingProviderLogin({ domainId: provider.domain_id, providerId: provider.id });
			window.location.assign(res.authorize_url);
		} catch {
			if (!active || current !== generation) return;
			providerLoading = null;
			error = td('login.provider.unavailable');
		}
	}


	function preventComposingSubmit(event: KeyboardEvent) {
		// Enter commits an IME candidate, not credentials. All other Enter presses
		// retain the browser's native implicit-submit action and the submit fences.
		if (event.key === 'Enter' && (event.isComposing || event.keyCode === 229)) {
			event.preventDefault();
		}
	}

	function submit(event: SubmitEvent) {
		event.preventDefault();
		// Password managers can fill the controls without emitting an input event.
		username = usernameInput?.value ?? username;
		password = passwordInput?.value ?? password;
		void login();
	}
</script>

<AuthStudioShell variant="login" localeId="login-locale" themeId="login-theme" footerNote={t('authStudio.login.footerNote')}>
	<div class="login-form-root motion-stagger">
		{#if sso}
			<section class="login-form" aria-labelledby="login-sso-title">
				<div class="login-heading">
					<p class="auth-eyebrow" aria-hidden="true">{t('authStudio.login.formEyebrow', { site: $siteConfig.site_name.toUpperCase() })}</p>
					<h1 id="login-sso-title" tabindex="-1">{td('login.sso.title')}</h1>
					<p>{td('login.sso.help')}</p>
				</div>
				{#if error}<Alert tone="danger">{error}</Alert>{/if}
				{#if providersLoading}
					<LoadingState variant="section" label={td('login.sso.loading')} class="login-activity"  />
				{:else if providersError}
					<Alert tone="warning">{td('login.providers.unavailable')}</Alert>
				{:else if providers.length === 0}
					<Alert tone="info">{td('login.sso.empty')}</Alert>
				{:else}
					<div class="login-providers">
						{#each providers as provider (`${provider.domain_id}:${provider.id}`)}
							<Button variant="secondary" size="lg" class="login-provider" disabled={busy} onclick={() => startProvider(provider)}>
								{td('login.provider.continue', { name: (providerNameCounts.get(provider.name) ?? 0) > 1 ? `${provider.name} · ${provider.domain_name}` : provider.name })}
							</Button>
						{/each}
					</div>
				{/if}
				{#if providerLoading}
					<LoadingState variant="section" label={td('login.provider.redirecting', { name: providerLoading.name })} class="login-activity motion-fade"  />
				{/if}
				<Button variant="ghost" size="lg" class="login-provider" disabled={busy} onclick={() => selectMethod(false)}>{td('login.sso.back')}</Button>
			</section>
		{:else}
			<div class="login-heading">
				<p class="auth-eyebrow" aria-hidden="true">{t('authStudio.login.formEyebrow', { site: $siteConfig.site_name.toUpperCase() })}</p>
				<h1>{t('authStudio.login.title')}</h1>
				<p>{t('authStudio.login.subtitle')}</p>
			</div>
			<form onsubmit={submit} class="login-form" novalidate>
				{#if error}
					<Alert tone="danger">{error}</Alert>
				{/if}

				<Field label={t('loginForm.username')} for="login-username" required>
					<TextInput id="login-username" bind:element={usernameInput} bind:value={username} autocomplete="username" placeholder={t('authStudio.login.usernamePlaceholder')} disabled={busy} required onkeydown={preventComposingSubmit} />
				</Field>
				<Field label={t('loginForm.password')} for="login-password" required>
					<div class="login-password">
						<TextInput id="login-password" bind:element={passwordInput} bind:value={password} type={passwordVisible ? 'text' : 'password'} autocomplete="current-password" placeholder={t('authStudio.login.passwordPlaceholder')} disabled={busy} required onkeydown={preventComposingSubmit} />
						<button type="button" class="login-visibility" aria-label={passwordVisible ? t('authStudio.login.hidePassword') : t('authStudio.login.showPassword')} disabled={busy} onclick={() => { passwordVisible = !passwordVisible; }}>
							<span aria-hidden="true">{passwordVisible ? '[ : ]' : '[ · ]'}</span>
						</button>
					</div>
				</Field>
				<Button type="submit" size="lg" class="login-submit" disabled={busy || personalRecovery && !password} ariaBusy={loading}>{personalRecovery ? td('login.personalRecovery.submit') : t('loginForm.signIn')}<span class="login-submit-arrow" aria-hidden="true">↗</span></Button>

				<div class="login-divider" aria-hidden="true"><span>{td('login.methods.or')}</span></div>
				<Button variant="secondary" size="lg" class="login-provider login-sso" disabled={busy} onclick={() => selectMethod(true)}><span class="login-terminal" aria-hidden="true">[ &gt;_ ]</span>{td('login.sso.open')}</Button>
				{#if loading}
					<LoadingState variant="section" label={t('loginForm.signingIn')} class="login-activity motion-fade"  />
				{/if}
			</form>

			<div class="login-bottom">
				<Button variant="link" size="sm" href="/recover" disabled={busy}>{td('recovery.title')}</Button>
				{#if signupButtonVisible}<span aria-hidden="true">·</span><Button variant="link" size="sm" href="/signup" disabled={busy}>{td('login.signup.open')}</Button>{/if}
			</div>
		{/if}
	</div>
</AuthStudioShell>

<style>
	.login-heading { margin-bottom: 1.25rem; }
	.login-heading h1 { margin: 0 0 0.65rem; font-size: 1.8rem; line-height: 1.35; font-weight: 500; letter-spacing: -0.055em; word-break: keep-all; overflow-wrap: anywhere; }
	.login-heading h1:focus { outline: none; }
	.login-heading p:last-child { margin: 0; font-size: 0.8125rem; line-height: 1.6; color: var(--color-ink-2); }
	.login-form { display: flex; flex-direction: column; gap: 0.9rem; }
	.login-form :global(.login-activity) { align-self: center; }
	.login-form :global(input) { height: 48px; font-size: 0.8125rem; }
	.login-password { position: relative; }
	.login-password :global(input) { padding-right: 3.5rem; }
	.login-visibility {
		position: absolute; top: 50%; right: 2px; transform: translateY(-50%);
		width: 46px; min-height: 44px; border: 0; background: transparent; cursor: pointer;
		color: var(--color-ink-2); font: 0.75rem var(--font-mono); white-space: pre;
	}
	.login-visibility:hover { color: var(--color-ink-0); }
	.login-visibility:focus-visible { outline: 2px solid var(--color-warm-2); outline-offset: 2px; border-radius: var(--radius-sm); }
	.login-form :global(.login-submit) {
		width: 100%; min-height: 48px; margin-top: 0.25rem; justify-content: space-between; padding-inline: 1rem;
		background: var(--color-action-warm); color: var(--color-action-on-warm); border-color: transparent;
		white-space: normal; overflow-wrap: anywhere;
	}
	.login-form :global(.login-submit:hover:not(:disabled)) { background: var(--color-action-warm-hover); }
	.login-submit-arrow { margin-left: 0.75rem; }
	.login-divider { display: flex; align-items: center; gap: 1rem; color: var(--color-ink-2); font-size: 0.6875rem; }
	.login-divider::before, .login-divider::after { content: ''; flex: 1; height: 1px; background: var(--color-line); }
	.login-providers { display: flex; flex-direction: column; gap: 0.5rem; }
	.login-form-root :global(.login-provider) { width: 100%; min-height: 48px; white-space: normal; overflow-wrap: anywhere; }
	.login-form :global(.login-sso) { gap: 0.75rem; background: transparent; }
	.login-terminal { font: 0.75rem var(--font-mono); color: var(--color-warm-2); }
	.login-bottom {
		display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem;
		margin-top: 1rem; padding-top: 0.5rem; border-top: 1px solid var(--color-line);
		color: var(--color-ink-2); font-size: 0.75rem;
	}
	.login-bottom :global(.btn-link) { min-height: 44px; padding-inline: 0; color: var(--color-warm-text); }
	@media (min-width: 1600px) { .login-heading h1 { font-size: 2rem; } }
	@media (max-width: 767px) {
		.login-heading { margin-bottom: 1rem; }
		.login-heading h1 { font-size: 1.4rem; }
		.login-heading p:last-child { font-size: 0.75rem; }
		.login-form :global(input), .login-form :global(.login-submit), .login-form-root :global(.login-provider) { min-height: 44px; height: auto; }
	}
	@media (max-height: 800px) {
		.login-heading { margin-bottom: 0.75rem; }
		.login-heading .auth-eyebrow, .login-heading p:last-child { display: none; }
		.login-heading h1 { font-size: 1.35rem; line-height: 1.3; margin: 0; }
		.login-form { gap: 0.6rem; }
		.login-form :global(input) { height: 44px; }
		.login-form :global(.login-submit), .login-form-root :global(.login-provider) { min-height: 44px; }
		.login-bottom { border-top: 0; padding: 0; margin-top: 0.25rem; }
	}
	@media (max-height: 620px) {
		.login-heading h1 { font-size: 1.2rem; }
		.login-form { gap: 0.4rem; }
	}
	/* Short landscape: paired inputs and paired sign-in/SSO actions (study layout). */
	@media (max-height: 440px) and (min-width: 480px) {
		.login-heading { margin-bottom: 0.35rem; }
		.login-heading h1 { font-size: 1.1rem; line-height: 1.2; }
		form.login-form { display: grid; grid-template-columns: 1fr 1fr; column-gap: 1rem; row-gap: 0.35rem; align-items: end; }
		form.login-form > :global(*) { grid-column: 1 / -1; }
		form.login-form > :global(.field), form.login-form > :global(.login-submit), form.login-form > :global(.login-sso) { grid-column: auto; }
		form.login-form :global(.login-submit) { margin-top: 0; }
		.login-divider { display: none; }
		.login-bottom { justify-content: center; gap: 1.5rem; margin-top: 0.25rem; }
	}
</style>
