<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { derived, get } from 'svelte/store';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth, logoutInProgress, projectSwitching, setLoginAuth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoginBrandHeader from '$lib/components/auth/LoginBrandHeader.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import type { LoginProviderOption, LoginOptions, LoginResponse } from '$lib/types/auth';
	import type { SignupOptions } from '$lib/types/enrollmentPolicy';
	import { loginAuthState, sessionScopeKey, type LoginAuthMapping } from '$lib/utils/authSession';
	import { loginDestination } from '$lib/utils/authFlow';
	import { freshLoginDestination, postAuthDestination } from '$lib/utils/mcpConsent';
	import { isSafeAuthorizeUrl, storePendingProviderLogin } from '$lib/utils/domainLogin';
	import { t } from '$lib/i18n/ns/public-entry';
	import { t as td } from '$lib/i18n/ns/domain-auth';
	import LocaleSelect from '$lib/i18n/LocaleSelect.svelte';

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
		personalRecovery = false;
		loading = false; providerLoading = null;
	}

	onMount(() => {
		active = true;
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

<div class="login-page">
	<div class="login-locale">
		<LocaleSelect id="login-locale" variant="labelled" />
	</div>
	<PageShell class="self-center">
	<div class="login-shell motion-stagger">
		<LoginBrandHeader />
		<div class="login-card">
			{#if sso}
				<section class="login-form" aria-labelledby="login-sso-title">
					<div class="space-y-2">
						<h2 id="login-sso-title" tabindex="-1" class="text-xl font-semibold">{td('login.sso.title')}</h2>
						<p class="text-sm text-ink-2">{td('login.sso.help')}</p>
					</div>
					{#if error}<Alert tone="danger">{error}</Alert>{/if}
					{#if providersLoading}
						<ActivityIndicator label={td('login.sso.loading')} class="login-activity" />
					{:else if providersError}
						<Alert tone="warning">{td('login.providers.unavailable')}</Alert>
					{:else if providers.length === 0}
						<Alert tone="info">{td('login.sso.empty')}</Alert>
					{:else}
						<div class="login-providers">
							{#each providers as provider (`${provider.domain_id}:${provider.id}`)}
								<Button variant="secondary" size="lg" class="login-provider min-h-11" disabled={busy} onclick={() => startProvider(provider)}>
									{td('login.provider.continue', { name: (providerNameCounts.get(provider.name) ?? 0) > 1 ? `${provider.name} · ${provider.domain_name}` : provider.name })}
								</Button>
							{/each}
						</div>
					{/if}
					{#if providerLoading}
						<ActivityIndicator label={td('login.provider.redirecting', { name: providerLoading.name })} class="login-activity motion-fade" />
					{/if}
					<Button variant="ghost" size="lg" class="login-provider min-h-11" disabled={busy} onclick={() => selectMethod(false)}>{td('login.sso.back')}</Button>
				</section>
			{:else}
				<form onsubmit={submit} class="login-form" novalidate>
					{#if error}
						<Alert tone="danger">{error}</Alert>
					{/if}

					<Field label={t('loginForm.username')} for="login-username" required>
						<TextInput id="login-username" bind:element={usernameInput} bind:value={username} autocomplete="username" disabled={busy} required onkeydown={preventComposingSubmit} />
					</Field>
					<Field label={t('loginForm.password')} for="login-password" required>
						<TextInput id="login-password" bind:element={passwordInput} bind:value={password} type="password" autocomplete="current-password" disabled={busy} required onkeydown={preventComposingSubmit} />
					</Field>
					<Button type="submit" size="lg" class="login-submit" disabled={busy || personalRecovery && !password} ariaBusy={loading}>{personalRecovery ? td('login.personalRecovery.submit') : t('loginForm.signIn')}</Button>

					<div class="login-divider" aria-hidden="true"><span>{td('login.methods.or')}</span></div>
					<Button variant="secondary" size="lg" class="login-provider min-h-11" disabled={busy} onclick={() => selectMethod(true)}>{td('login.sso.open')}</Button>
					{#if loading}
						<ActivityIndicator label={t('loginForm.signingIn')} class="login-activity motion-fade" />
					{/if}
				</form>

				<div class="login-signup flex flex-wrap justify-center gap-3">
					{#if signupButtonVisible}<Button variant="link" size="sm" href="/signup" disabled={busy}>{td('login.signup.open')}</Button>{/if}
					<Button variant="link" size="sm" href="/recover" disabled={busy}>{td('recovery.title')}</Button>
				</div>
			{/if}
		</div>
	</div>
	</PageShell>
</div>

<style>
	.login-page {
		min-height: 100dvh;
		display: grid;
		grid-template-rows: auto 1fr;
		justify-items: center;
		background: var(--color-surface-canvas);
		color: var(--color-ink-0);
	}

	.login-locale {
		justify-self: end;
		margin: 1rem;
	}

	.login-shell {
		width: 100%;
		max-width: 28rem;
		margin-inline: auto;
		align-self: center;
	}

	.login-card {
		border: 1px solid var(--color-line-2);
		border-radius: 0.75rem;
		background: var(--color-surface-raised);
		padding: 2rem;
	}

	.login-form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.login-form :global(.login-activity) {
		align-self: center;
	}


	.login-divider {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		font-size: 0.75rem;
		color: var(--color-ink-2);
	}

	.login-divider::before,
	.login-divider::after {
		content: '';
		flex: 1;
		border-top: 1px solid var(--color-line-2);
	}

	.login-providers {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.login-card :global(.login-provider) {
		white-space: normal;
		overflow-wrap: anywhere;
	}

	.login-signup {
		margin-top: 1.25rem;
		padding-top: 1.25rem;
		border-top: 1px solid var(--color-line);
	}


	@media (max-width: 479px) {
		.login-card {
			padding: 1.25rem;
		}
	}
</style>
