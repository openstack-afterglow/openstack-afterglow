<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { auth, authReady, logoutInProgress, projectSwitching, setLoginAuth } from '$lib/stores/auth';
	import { derived, get } from 'svelte/store';
	import { api, ApiError } from '$lib/api/client';
	import type { ProviderEntryTicket } from '$lib/api/errors';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import AuthStudioShell from '$lib/components/auth/AuthStudioShell.svelte';
	import type { LoginResponse, ProviderLinkResponse } from '$lib/types/auth';
	import { loginAuthState, sessionScopeKey, type LoginAuthMapping } from '$lib/utils/authSession';
	import { freshLoginDestination } from '$lib/utils/mcpConsent';
	import { takePendingProviderLogin, signupApprovalState, type SignupApprovalState } from '$lib/utils/domainLogin';
	import { t as translate } from '$lib/i18n/ns/domain-auth';
	import { beginAuthExperience, observedAuthText, createAuthNoticePresenter, type AuthExperience } from '$lib/components/auth/authExperience';
	const t = translate;

	let error = $state('');
	let approval = $state<SignupApprovalState | null>(null);
	let loading = $state(true);
	let linking = $state(false);
	let ticket = $state<{ link_token: string; domain_id: string } | null>(null);
	let entryTicket = $state<ProviderEntryTicket | null>(null);
	let linked = $state<ProviderLinkResponse | null>(null);
	let username = $state('');
	let password = $state('');
	let active = false;
	let abandoned = $state(false);
	let viewExperience = $state.raw<AuthExperience>();
	const presentNotice = createAuthNoticePresenter();
	$effect(() => {
		const key = !viewExperience || loading || abandoned || $logoutInProgress || $projectSwitching ? null
			: approval ? approval === 'pending' ? 'signup.approval.providerPending' : 'signup.approval.providerRejected'
			: linked ? 'link.complete' : entryTicket ? entryTicket.action === 'connect' ? 'entry.connectDescription' : 'entry.createDescription' : ticket ? 'link.description' : null;
		if (key) t(key, { domain: '' });
		presentNotice('result', viewExperience, 'domain-auth', key, linked ? 'success' : approval === 'rejected' ? 'warning' : 'info');
	});
	const callbackTitle = $derived(
		abandoned || $logoutInProgress || $projectSwitching ? t('common.backToLogin')
			: loading ? t('callback.processing')
			: approval ? t('login.sso.title')
			: linked ? t('link.completeTitle')
			: entryTicket ? t(entryTicket.action === 'connect' ? 'entry.connectTitle' : 'entry.createTitle')
			: ticket ? t('link.title')
			: t('link.signInAgain'),
	);
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
		native_binding_conflict: 'callback.nativeBindingConflict', account_email_conflict: 'callback.accountEmailConflict',
		account_changed: 'callback.accountChanged', invalid_entry_action: 'callback.accountChanged',
		account_ambiguous: 'callback.accountAmbiguous', account_disabled: 'callback.accountDisabled',
		invalid_entry_token: 'callback.invalidState',
	};
	function callbackErrorMessage(e: unknown, observation: AuthExperience): string {
		const t = observedAuthText(observation, 'domain-auth', translate);
		if (!(e instanceof ApiError)) return t('callback.unavailable');
		const key = e.code ? CODE_MESSAGES[e.code] : undefined;
		if (key) return t(key);
		if (e.status === 401) return ticket ? t('login.password.invalid') : t('callback.invalidState');
		if (e.status === 409) return t('callback.failed', { status: e.status });
		if (e.status === 502) return t('callback.providerError');
		if (e.status === 503 || e.status === 0) return t('callback.unavailable');
		return t('callback.failed', { status: e.status });
	}
	function terminalApproval(e: unknown, observation: AuthExperience): boolean {
		const decision = e instanceof ApiError ? signupApprovalState(e) : null;
		if (!decision) return false;
		approval = decision; ticket = null; entryTicket = null; linked = null; password = ''; username = ''; error = ''; loading = false; linking = false;
		observation.state('ready');
		viewExperience = observation;
		return true;
	}
	function discard(token: string) {
		void api.post('/api/v1/auth/logout', {}, token, undefined, { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false }).catch(() => {});
	}
	async function publish(data: LoginResponse, observation: AuthExperience) {
		if (!active || abandoned) { observation.discard(active ? 'stale' : 'unmounted'); discard(data.token); return; }
		const text = observedAuthText(observation, 'domain-auth', t);
		let mapped: LoginAuthMapping;
		try { mapped = loginAuthState(data, { federated: true }); }
		catch { discard(data.token); error = text('callback.foreignDomain'); loading = false; observation.validation('authority'); observation.state('error'); void observation.applied(); return; }
		ticket = null; entryTicket = null; password = ''; username = '';
		// Do not delay the one-use exchange handoff for diagnostic DOM observation.
		void observation.applied();
		setLoginAuth(mapped.state);
		beginAuthExperience('auth.callback', 'load', () => active).state('loading');
		await goto(freshLoginDestination(mapped.target), { replaceState: true });
	}
	async function confirmEntry(event: Event) {
		event.preventDefault();
		if (!entryTicket || linking || !active || abandoned) return;
		const observation = beginAuthExperience('auth.callback', 'approve', () => active && !abandoned);
		observation.state('loading', 1);
		const body = { entry_token: entryTicket.entry_token, action: entryTicket.action };
		linking = true; error = '';
		let rendered = false;
		try {
			const data = await api.post<LoginResponse>('/api/v1/auth/providers/entry', body, undefined, undefined, { signal: AbortSignal.timeout(120_000), suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false, ...observation.options });
			await publish(data, observation);
		} catch (e) {
			if (active && !abandoned) {
				if (terminalApproval(e, observation)) { rendered = true; return; }
				error = callbackErrorMessage(e, observation); observation.state('error'); rendered = true;
			}
			else observation.discard(active ? 'stale' : 'unmounted');
		} finally { entryTicket = null; if (active) { linking = false; if (rendered && !abandoned) void observation.applied(); } }
	}
	function cancelEntry() {
		if (!entryTicket) return;
		const observation = beginAuthExperience('auth.callback', 'cancel', () => active);
		entryTicket = null; abandoned = true; error = ''; linking = false;
		observation.state('disabled'); void observation.applied();
	}
	async function link(event: Event, authenticated = false) {
		event.preventDefault();
		if (!ticket || linking || !active || abandoned) return;
		if (authenticated ? (!$auth.token || !$authReady || $logoutInProgress || $projectSwitching) : (!username.trim() || !password)) return;
		const authority = authorityGeneration;
		const owns = () => active && !abandoned && (!authenticated || authority === authorityGeneration);
		const observation = beginAuthExperience('auth.callback', 'verify', owns);
		const text = observedAuthText(observation, 'domain-auth', t);
		observation.state('loading', 2);
		const body = authenticated ? { link_token: ticket.link_token } : { link_token: ticket.link_token, username: username.trim(), password };
		password = ''; linking = true; error = '';
		let rendered = false;
		try {
			const data = await api.post<ProviderLinkResponse>(authenticated ? '/api/v1/auth/providers/link/authenticated' : '/api/v1/auth/providers/link', body, authenticated ? $auth.token ?? undefined : undefined, undefined, { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false, ...observation.options });
			if (!active || abandoned) { observation.discard(active ? 'stale' : 'unmounted'); return; }
			ticket = null;
			if (authenticated && authority !== authorityGeneration) { error = text('callback.invalidState'); observation.discard('scope_changed'); return; }
			if (data.linked !== true || data.domain_id !== originDomain || !data.domain_name?.trim() || !data.provider_id || (expectedProvider && data.provider_id !== expectedProvider)) {
				error = text('callback.foreignDomain'); observation.validation('authority'); observation.state('error'); rendered = true; return;
			}
			username = '';
			linked = data;
			viewExperience = observation; observation.state('ready');
			rendered = true;
		} catch (e) {
			if (active && !abandoned) {
				if (terminalApproval(e, observation)) { rendered = true; return; }
				error = callbackErrorMessage(e, observation); observation.state('error'); rendered = true;
				ticket = null;
			}
			else observation.discard(active ? 'stale' : 'unmounted');
		} finally { if (active) { linking = false; if (rendered && owns()) void observation.applied(); } }
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
			abandoned = true; ticket = null; entryTicket = null; linked = null; approval = null; password = ''; username = ''; error = ''; loading = false; linking = false;
			settleReadiness?.();
		});
		const unsubscribeAuthority = derived([authReady, logoutInProgress, projectSwitching], values => JSON.stringify(values)).subscribe(() => { authorityGeneration++; });
		void complete();
		return () => { active = false; settleReadiness?.(); ticket = null; entryTicket = null; approval = null; password = ''; username = ''; unsubscribe(); unsubscribeAuthority(); };
		async function complete() {
			const observation = beginAuthExperience('auth.callback', 'load', () => active && !abandoned);
			viewExperience = observation;
			const text = observedAuthText(observation, 'domain-auth', t);
			observation.state('loading', 0);
			const params = $page.url.searchParams;
			const code = params.get('code');
			const state = params.get('state');
			const providerError = params.get('error');
			const pending = takePendingProviderLogin();
			originDomain = pending?.domainId ?? null;
			expectedProvider = pending?.providerId ?? null;
			try { history.replaceState(history.state, '', '/auth/callback'); } catch { /* API one-use state remains authoritative. */ }
			if ($logoutInProgress || $projectSwitching) { abandoned = true; loading = false; observation.discard('scope_changed'); return; }
			if (awaitingReadiness) await new Promise<void>(resolve => { settleReadiness = resolve; });
			settleReadiness = null;
			if (!active || abandoned) { observation.discard(active ? 'stale' : 'unmounted'); return; }
			if (providerError || !code || !state) { error = text(providerError ? 'callback.providerDenied' : 'callback.invalidRequest'); loading = false; observation.validation('format'); observation.state('error'); void observation.applied(); return; }
			const guardKey = `afterglow-provider-callback:${state}`;
			try {
				if (sessionStorage.getItem(guardKey)) { error = text('callback.invalidState'); loading = false; observation.validation('policy'); observation.state('error'); void observation.applied(); return; }
				sessionStorage.setItem(guardKey, '1');
			} catch { /* The server enforces one-use state. */ }
			try {
				// Federation includes several bounded native exchanges; never replay a timed-out code.
				const data = await api.post<LoginResponse>('/api/v1/auth/providers/callback', { code, state }, undefined, undefined, { signal: AbortSignal.timeout(120_000), suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false, ...observation.options });
				await publish(data, observation);
			} catch (e) {
				if (!active || abandoned) { observation.discard(active ? 'stale' : 'unmounted'); return; }
				if (terminalApproval(e, observation)) { void observation.applied(); return; }
				if (e instanceof ApiError && e.status === 409 && e.code === 'account_entry_required' && e.entryTicket) {
					if (originDomain && e.entryTicket.domain_id !== originDomain) error = text('callback.foreignDomain');
					else entryTicket = e.entryTicket;
				} else if (e instanceof ApiError && e.status === 409 && e.code === 'account_link_required' && e.linkTicket) {
					if (originDomain && e.linkTicket.domain_id !== originDomain) error = text('callback.foreignDomain');
					else { ticket = e.linkTicket; originDomain = ticket.domain_id; }
				} else error = callbackErrorMessage(e, observation);
				loading = false;
				observation.state(error ? 'error' : 'ready', entryTicket ? 1 : ticket ? 2 : 0);
				void observation.applied();
			}
		}
	});
</script>
<svelte:head><meta name="referrer" content="no-referrer" /></svelte:head>
<AuthStudioShell
	variant="account"
	localeId="callback-locale"
	themeId="callback-theme"
	footerNote={t('login.sso.title')}
>
	<div class="auth-flow">
		<header class="auth-flow-heading"><h1>{callbackTitle}</h1></header>
		{#if loading && !abandoned && !$logoutInProgress && !$projectSwitching}
			<LoadingState variant="section" label={t('callback.processing')} />
		{:else if abandoned || $logoutInProgress || $projectSwitching}
			<Button href={loginPath} class="w-full">{t('common.backToLogin')}</Button>
		{:else}
			{#if error}<Alert tone="danger">{error}</Alert>{/if}
			{#if approval}
				<Alert tone={approval === 'pending' ? 'info' : 'warning'} title={t(approval === 'pending' ? 'signup.approval.pendingTitle' : 'signup.approval.rejectedTitle')}>
					{t(approval === 'pending' ? 'signup.approval.providerPending' : 'signup.approval.providerRejected')}
				</Alert>
				<Button href={loginPath} class="w-full">{t('link.signInAgain')}</Button>
			{:else if linked}
				<Alert tone="success">{t('link.complete', { domain: linked.domain_name })}</Alert>
				<Button href={loginPath} class="w-full">{t('link.signInAgain')}</Button>
			{:else}
				{#if entryTicket}
					<Alert tone="info">{t(entryTicket.action === 'connect' ? 'entry.connectDescription' : 'entry.createDescription')}</Alert>
					{#if entryTicket.transfer_existing}<Alert tone="warning">{t('entry.transferExisting')}</Alert>{/if}
					<dl class="auth-flow-fields text-sm">
						<div><dt class="text-ink-2">{t('entry.email')}</dt><dd class="text-ink-0 break-words">{entryTicket.email}</dd></div>
						{#if entryTicket.action === 'connect'}<div><dt class="text-ink-2">{t('entry.username')}</dt><dd class="text-ink-0 break-words">{entryTicket.username}</dd></div>{/if}
					</dl>
					<form onsubmit={confirmEntry}>
						<Button type="submit" disabled={linking} ariaBusy={linking} class="w-full">{#if linking}<LoadingState variant="control" label={t('callback.processing')} />{:else}{t(entryTicket.action === 'connect' ? 'entry.connect' : 'entry.create')}{/if}</Button>
					</form>
				{:else if ticket}
					<Alert tone="info">{t('link.description')}</Alert>
					<form onsubmit={link} class="auth-flow">
						<div class="auth-flow-fields">
							<Field for="link-username" label={t('onboarding.name')} required><TextInput id="link-username" bind:value={username} autocomplete="username" disabled={linking} required /></Field>
							<Field for="link-password" label={t('onboarding.password')} required><TextInput id="link-password" bind:value={password} type="password" autocomplete="current-password" disabled={linking} required /></Field>
						</div>
						<Button type="submit" disabled={linking || !username.trim() || !password} ariaBusy={linking} class="w-full">{#if linking}<LoadingState variant="control" label={t('callback.processing')} />{:else}{t('link.submit')}{/if}</Button>
					</form>
					{#if $auth.token}
						<p class="text-sm text-ink-2">{t('link.authenticatedHelp')}</p>
						<Button variant="secondary" class="w-full" disabled={linking || !$authReady || $logoutInProgress || $projectSwitching} onclick={(event) => link(event, true)}>{t('link.authenticated', { username: $auth.username ?? '' })}</Button>
					{/if}
					<div class="auth-flow-links"><Button variant="link" href="/recover" disabled={linking}>{t('recovery.title')}</Button></div>
				{/if}
				<div class="auth-flow-actions">
					<Button variant="secondary" href={loginPath} onclick={cancelEntry} disabled={linking && !entryTicket} class="w-full">{t('common.backToLogin')}</Button>
				</div>
			{/if}
		{/if}
	</div>
</AuthStudioShell>
