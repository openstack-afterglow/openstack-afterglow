<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { auth, authReady, logoutInProgress, projectSwitching, setLoginAuth } from '$lib/stores/auth';
	import { derived, get } from 'svelte/store';
	import { api, ApiError } from '$lib/api/client';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import type { LoginResponse, ProviderLinkResponse } from '$lib/types/auth';
	import { loginAuthState, sessionScopeKey, type LoginAuthMapping } from '$lib/utils/authSession';
	import { freshLoginDestination } from '$lib/utils/mcpConsent';
	import { takePendingProviderLogin, signupApprovalState, type SignupApprovalState } from '$lib/utils/domainLogin';
	import { t } from '$lib/i18n/ns/domain-auth';

	let error = $state('');
	let approval = $state<SignupApprovalState | null>(null);
	let loading = $state(true);
	let linking = $state(false);
	let ticket = $state<{ link_token: string; domain_id: string } | null>(null);
	let linked = $state<ProviderLinkResponse | null>(null);
	let username = $state('');
	let password = $state('');
	let active = false;
	let abandoned = $state(false);
	// Registration origin remains bound for link results, not fresh session scope.
	let originDomain: string | null = null;
	let expectedProvider: string | null = null;
	const loginPath = '/login?reauthenticate=1';
	let authorityGeneration = 0;
	const CODE_MESSAGES: Record<string, Parameters<typeof t>[0]> = {
		invalid_state: 'callback.invalidState', provider_changed: 'callback.providerChanged',
		email_not_verified: 'callback.emailNotVerified', email_domain_not_allowed: 'callback.emailDomainNotAllowed',
		foreign_domain: 'callback.foreignDomain', provider_disabled: 'callback.providerDisabled',
		provider_error: 'callback.providerError', unavailable: 'callback.unavailable',
	};
	function callbackErrorMessage(e: unknown): string {
		if (!(e instanceof ApiError)) return t('callback.unavailable');
		const key = e.code ? CODE_MESSAGES[e.code] : undefined;
		if (key) return t(key);
		if (e.status === 401) return ticket ? t('login.password.invalid') : t('callback.invalidState');
		if (e.status === 409) return t('callback.providerChanged');
		if (e.status === 502) return t('callback.providerError');
		if (e.status === 503 || e.status === 0) return t('callback.unavailable');
		return t('callback.failed', { status: e.status });
	}
	function terminalApproval(e: unknown): boolean {
		const decision = e instanceof ApiError ? signupApprovalState(e) : null;
		if (!decision) return false;
		approval = decision; ticket = null; linked = null; password = ''; username = ''; error = ''; loading = false; linking = false;
		return true;
	}
	function discard(token: string) {
		void api.post('/api/v1/auth/logout', {}, token, undefined, { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false }).catch(() => {});
	}
	async function publish(data: LoginResponse) {
		if (!active || abandoned) { discard(data.token); return; }
		let mapped: LoginAuthMapping;
		try { mapped = loginAuthState(data, { federated: true }); }
		catch { discard(data.token); error = t('callback.foreignDomain'); loading = false; return; }
		ticket = null; password = ''; username = '';
		setLoginAuth(mapped.state);
		await goto(freshLoginDestination(mapped.target), { replaceState: true });
	}
	async function link(event: Event, authenticated = false) {
		event.preventDefault();
		if (!ticket || linking || !active || abandoned) return;
		if (authenticated ? (!$auth.token || !$authReady || $logoutInProgress || $projectSwitching) : (!username.trim() || !password)) return;
		const authority = authorityGeneration;
		const body = authenticated ? { link_token: ticket.link_token } : { link_token: ticket.link_token, username: username.trim(), password };
		password = ''; linking = true; error = '';
		try {
			const data = await api.post<ProviderLinkResponse>(authenticated ? '/api/v1/auth/providers/link/authenticated' : '/api/v1/auth/providers/link', body, authenticated ? $auth.token ?? undefined : undefined, undefined, { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false });
			if (!active || abandoned) return;
			ticket = null;
			if (authenticated && authority !== authorityGeneration) { error = t('callback.invalidState'); return; }
			if (data.linked !== true || data.domain_id !== originDomain || !data.domain_name?.trim() || !data.provider_id || (expectedProvider && data.provider_id !== expectedProvider)) {
				error = t('callback.foreignDomain'); return;
			}
			username = '';
			linked = data;
		} catch (e) {
			if (active && !abandoned) {
				if (terminalApproval(e)) return;
				error = callbackErrorMessage(e);
				ticket = null;
			}
		} finally { if (active) linking = false; }
	}
	onMount(() => {
		active = true;
		const sessionKey = () => JSON.stringify([sessionScopeKey(get(auth)), !!get(auth).token, get(logoutInProgress), get(projectSwitching)]);
		const ownerSession = sessionKey();
		const ownerKey = () => JSON.stringify([sessionKey(), get(authReady)]);
		let owner = ownerKey();
		let awaitingReadiness = !!get(auth).token && !get(authReady);
		let settleReadiness: (() => void) | null = null;
		const unsubscribe = derived([auth, authReady, logoutInProgress, projectSwitching], ownerKey).subscribe(key => {
			if (key === owner) return;
			// Root verification may finish a restored session before this one-use exchange starts.
			// After that initial settlement, any authority loss (including ABA) is terminal.
			if (awaitingReadiness && get(authReady) && sessionKey() === ownerSession) {
				owner = key; awaitingReadiness = false; settleReadiness?.(); return;
			}
			abandoned = true; ticket = null; linked = null; approval = null; password = ''; username = ''; error = ''; loading = false; linking = false;
			settleReadiness?.();
		});
		const unsubscribeAuthority = derived([authReady, logoutInProgress, projectSwitching], values => JSON.stringify(values)).subscribe(() => { authorityGeneration++; });
		void complete();
		return () => { active = false; settleReadiness?.(); ticket = null; approval = null; password = ''; username = ''; unsubscribe(); unsubscribeAuthority(); };
		async function complete() {
			const params = $page.url.searchParams;
			const code = params.get('code');
			const state = params.get('state');
			const providerError = params.get('error');
			const pending = takePendingProviderLogin();
			originDomain = pending?.domainId ?? null;
			expectedProvider = pending?.providerId ?? null;
			try { history.replaceState(history.state, '', '/auth/callback'); } catch { /* API one-use state remains authoritative. */ }
			if ($logoutInProgress || $projectSwitching) { abandoned = true; loading = false; return; }
			if (awaitingReadiness) await new Promise<void>(resolve => { settleReadiness = resolve; });
			settleReadiness = null;
			if (!active || abandoned) return;
			if (providerError || !code || !state) { error = t(providerError ? 'callback.providerDenied' : 'callback.invalidRequest'); loading = false; return; }
			const guardKey = `afterglow-provider-callback:${state}`;
			try {
				if (sessionStorage.getItem(guardKey)) { error = t('callback.invalidState'); loading = false; return; }
				sessionStorage.setItem(guardKey, '1');
			} catch { /* The server enforces one-use state. */ }
			try {
				// Federation includes several bounded native exchanges; never replay a timed-out code.
				const data = await api.post<LoginResponse>('/api/v1/auth/providers/callback', { code, state }, undefined, undefined, { signal: AbortSignal.timeout(120_000), suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false });
				await publish(data);
			} catch (e) {
				if (!active || abandoned) return;
				if (terminalApproval(e)) return;
				if (e instanceof ApiError && e.status === 409 && e.code === 'account_link_required' && e.linkTicket) {
					if (originDomain && e.linkTicket.domain_id !== originDomain) error = t('callback.foreignDomain');
					else { ticket = e.linkTicket; originDomain = ticket.domain_id; }
				} else error = callbackErrorMessage(e);
				loading = false;
			}
		}
	});
</script>
<svelte:head><meta name="referrer" content="no-referrer" /></svelte:head>
<main id="main-content" tabindex="-1" class="min-h-screen bg-surface-canvas flex items-center justify-center">
	<PageShell class="flex justify-center"><div class="w-full max-w-md">
		{#if abandoned || $logoutInProgress || $projectSwitching}
			<Button href={loginPath} class="w-full">{t('common.backToLogin')}</Button>
		{:else if loading}<div class="flex justify-center"><ActivityIndicator size="lg" label={t('callback.processing')} /></div>
		{:else}<div class="bg-surface-raised rounded-xl border border-line-2 p-6 sm:p-8 space-y-4">
			{#if error}<Alert tone="danger">{error}</Alert>{/if}
			{#if approval}
				<Alert tone={approval === 'pending' ? 'info' : 'warning'} title={t(approval === 'pending' ? 'signup.approval.pendingTitle' : 'signup.approval.rejectedTitle')}>
					{t(approval === 'pending' ? 'signup.approval.providerPending' : 'signup.approval.providerRejected')}
				</Alert>
				<Button href={loginPath} class="w-full">{t('link.signInAgain')}</Button>
			{:else}
			{#if linked}
				<h1 class="text-xl font-semibold text-ink-0">{t('link.completeTitle')}</h1>
				<Alert tone="success">{t('link.complete', { domain: linked.domain_name })}</Alert>
				<Button href={loginPath} class="w-full">{t('link.signInAgain')}</Button>
			{:else}
			{#if ticket}
				<h1 class="text-xl font-semibold text-ink-0">{t('link.title')}</h1>
				<Alert tone="info">{t('link.description')}</Alert>
				<form onsubmit={link} class="space-y-4">
					<Field for="link-username" label={t('onboarding.name')} required><TextInput id="link-username" bind:value={username} autocomplete="username" disabled={linking} required /></Field>
					<Field for="link-password" label={t('onboarding.password')} required><TextInput id="link-password" bind:value={password} type="password" autocomplete="current-password" disabled={linking} required /></Field>
					<Button type="submit" disabled={linking || !username.trim() || !password} ariaBusy={linking} class="w-full">{t('link.submit')}</Button>
				</form>
				{#if $auth.token}
					<p class="text-sm text-ink-2">{t('link.authenticatedHelp')}</p>
					<Button variant="secondary" class="w-full" disabled={linking || !$authReady || $logoutInProgress || $projectSwitching} onclick={(event) => link(event, true)}>{t('link.authenticated', { username: $auth.username ?? '' })}</Button>
				{/if}
				<Button variant="link" href="/recover" disabled={linking}>{t('recovery.title')}</Button>
			{/if}
			<Button variant="secondary" href={loginPath} disabled={linking} class="w-full">{t('common.backToLogin')}</Button>
			{/if}
			{/if}
		</div>{/if}
	</div></PageShell>
</main>
