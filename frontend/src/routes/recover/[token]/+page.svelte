<script lang="ts">
	import { onDestroy, onMount, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { api, ApiError } from '$lib/api/client';
	import { auth, authReady, clearAuth, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { clearPasswordCreateContinuation, storePasswordCreateContinuation } from '$lib/utils/mcpConsent';
	import { cloudShell } from '$lib/stores/cloudShell.svelte';
	import { toast } from '$lib/stores/toast';
	import { isOnboardingToken } from '$lib/utils/domainLogin';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/domain-auth';
	import { t as account } from '$lib/i18n/ns/account';

	interface RecoveryInfo { kind: 'username' | 'password' | 'email_change' | 'password_create'; email: string; username?: string; identity_domain_id?: string; identity_domain_name?: string }
	const token = $derived(($page.params as Record<string, string>)['token'] ?? '');
	const entryHint = $derived($page.url?.searchParams.get('reauthenticated') === '1');
	let reauthenticated = $state(false);
	let proof = '';
	let info = $state<RecoveryInfo | null>(null);
	let loading = $state(true);
	let busy = $state(false);
	let changed = $state(false);
	let submitted = $state(false);
	let error = $state('');
	let password = $state('');
	let confirm = $state('');
	let live = true;
	let generation = 0;
	let authorityEpoch = 0;
	const sessionReady = $derived(!!$auth.token && $authReady && !$logoutInProgress && !$projectSwitching);
	// Presentation hint only: the backend checks a fresh federated session issued after the proof.
	const creationReady = $derived(sessionReady && reauthenticated);
	$effect(() => { const current = token, hint = entryHint; untrack(() => void inspect(current, hint)); });
	async function inspect(current: string, hint: boolean) {
		const boundary = ++generation;
		proof = ''; info = null; error = ''; loading = true; changed = false; busy = false; password = ''; confirm = '';
		submitted = false; reauthenticated = hint;
		if (!isOnboardingToken(current)) { loading = false; error = t('onboarding.linkInvalid'); return; }
		try {
			// Username tickets are consumed by this read: never cache or retry it automatically.
			const result = await api.get<RecoveryInfo>(`/api/v1/auth/recovery/${encodeURIComponent(current)}`, undefined, undefined, { refresh: true, cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false });
			if (live && boundary === generation) {
				info = result; proof = current;
				if (result.kind === 'password_create') {
					clearPasswordCreateContinuation();
					// Keep the proof only in memory while this page is open; outbound navigation has no token/referrer.
					try { history.replaceState(history.state, '', '/recover'); } catch { /* Referrer policy still protects navigation. */ }
				}
			}
		} catch (e) {
			if (live && boundary === generation) {
				clearPasswordCreateContinuation();
				error = t(e instanceof ApiError && [404, 410].includes(e.status) ? 'onboarding.linkInvalid' : 'recovery.failed');
			}
		} finally { if (live && boundary === generation) loading = false; }
	}
	function signIn() {
		if (busy || submitted || info?.kind !== 'password_create') return;
		password = ''; confirm = '';
		if (!storePasswordCreateContinuation(proof)) { error = account('password.createResumeFailed'); return; }
		proof = ''; busy = true;
		void goto('/login?reauthenticate=1').catch(() => { if (live) { busy = false; error = account('password.createResumeFailed'); } });
	}
	function finishCreation(known: boolean, revocationFailed = false) {
		proof = ''; password = ''; confirm = ''; clearPasswordCreateContinuation();
		const message = account(revocationFailed ? 'password.createSessionsFailed' : known ? 'password.created' : 'password.createOutcomeUnknown');
		logoutInProgress.set(true); clearAuth();
		if (known && !revocationFailed) toast.success(message, 0); else toast.error(message);
		void cloudShell.close('logout', { keepDock: false }).catch(() => {}).finally(() => {
			void goto('/login', { replaceState: true }).finally(() => logoutInProgress.set(false));
		});
	}
	async function complete(event: SubmitEvent) {
		event.preventDefault();
		if (!info || info.kind === 'username' || busy || changed || submitted) return;
		const creating = info.kind === 'password_create';
		if (creating && !creationReady) { password = ''; confirm = ''; error = account('password.createSignInHelp'); return; }
		if ((info.kind === 'password' || creating) && (password.length < 12 || password.length > 1024 || password !== confirm)) {
			error = password !== confirm ? t('onboarding.passwordMismatch') : t('onboarding.passwordTooShort'); return;
		}
		const boundary = generation, authority = authorityEpoch;
		const owner = get(auth);
		const body = info.kind === 'password' || creating ? { token: proof, new_password: password } : { token: proof };
		const path = creating ? '/api/v1/auth/recovery/password/create/complete' : info.kind === 'password' ? '/api/v1/auth/recovery/password/complete' : '/api/v1/auth/email/changes/accept';
		password = ''; confirm = ''; busy = true; error = ''; submitted = true;
		if (creating) { proof = ''; clearPasswordCreateContinuation(); }
		const current = () => live && boundary === generation && (!creating || authority === authorityEpoch);
		try {
			const result = await api.post<{ status?: string }>(path, body, creating ? owner.token ?? undefined : undefined, undefined, { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false });
			if (current()) { if (creating) finishCreation(result?.status === 'created'); else changed = true; }
		} catch (e) {
			if (current()) {
				if (creating) {
					const knownUnavailable = e instanceof ApiError && ['password_create_session_unavailable', 'password_create_native_unavailable', 'password_create_email_unavailable'].includes(e.code ?? '');
					if (e instanceof ApiError && e.status === 403 && e.code === 'password_create_reauthentication_required') {
						// This rejection is explicitly pre-consumption. Preserve only the email proof, never the password.
						proof = body.token; submitted = false; reauthenticated = false;
						error = account('password.createSignInHelp'); return;
					}
					if (e instanceof ApiError && e.status === 503 && e.code === 'password_create_sessions_failed') { finishCreation(true, true); return; }
					if (!(e instanceof ApiError) || e.status === 0 || (e.status >= 500 && !knownUnavailable) || e.code === 'password_create_outcome_unknown' || e.code === 'password_create_reconciliation_required') finishCreation(false);
					else if ([404, 410].includes(e.status)) error = t('onboarding.linkInvalid');
					else if (knownUnavailable || e.code === 'password_create_ineligible' || e.code === 'password_create_email_ambiguous') error = account('password.unavailable');
					else if (e.status === 401 || e.status === 403) error = account('password.createWrongUser');
					else if (e.code === 'password_create_identity_changed') error = account('password.createIdentityChanged');
					else if (e.code === 'password_create_invalid_password') error = account('password.createInvalidPassword');
					else error = account(e.code === 'password_already_exists' ? 'password.createExisting' : 'password.createFailed');
				} else error = t(e instanceof ApiError && [404, 410].includes(e.status) ? 'onboarding.linkInvalid' : 'recovery.failed');
			}
		} finally { if (current()) busy = false; }
	}
	onMount(() => {
		let previous = '';
		const owner = () => JSON.stringify([sessionScopeKey(get(auth)), !!get(auth).token, get(logoutInProgress), get(projectSwitching)]);
		const initialOwner = owner();
		let awaitingReadiness = !!get(auth).token && !get(authReady);
		const changed = () => {
			const state = get(auth);
			const next = JSON.stringify([sessionScopeKey(state), !!state.token, get(authReady), get(logoutInProgress), get(projectSwitching)]);
			if (next === previous) return;
			if (previous) {
				const initialSettlement = awaitingReadiness && get(authReady) && owner() === initialOwner;
				if (!initialSettlement) reauthenticated = false;
				awaitingReadiness = false;
			}
			previous = next; authorityEpoch++; password = ''; confirm = ''; busy = false;
		};
		const unsubscribers = [auth.subscribe(changed), authReady.subscribe(changed), logoutInProgress.subscribe(changed), projectSwitching.subscribe(changed)];
		return () => unsubscribers.forEach(unsubscribe => unsubscribe());
	});
	onDestroy(() => { live = false; generation++; authorityEpoch++; proof = ''; info = null; password = ''; confirm = ''; });
</script>
<svelte:head><meta name="referrer" content="no-referrer" /><meta name="robots" content="noindex, nofollow" /></svelte:head>
<main id="main-content" tabindex="-1" class="min-h-screen bg-surface-canvas {loading ? '' : 'py-8'} flex items-center justify-center">
	{#if loading}
		<LoadingState variant="surface" style="min-height: 100dvh" label={t('onboarding.processing')} />
	{:else}
	<PageShell class="flex justify-center"><div class="w-full max-w-md bg-surface-raised border border-line-2 rounded-xl p-5 sm:p-6 space-y-4">
		<h1 class="text-xl font-semibold text-ink-0">{info?.kind === 'password_create' ? account('password.createTitle') : t('recovery.title')}</h1>
			{#if error}<Alert tone="danger">{error}</Alert>{/if}
			{#if changed}<Alert tone="success">{t('recovery.changed')}</Alert>
			{:else if info?.kind === 'username'}
				<Alert tone="info">{t('recovery.usernameResult')}</Alert>
				<dl class="space-y-2 text-sm text-ink-1"><dt>{t('onboarding.name')}</dt><dd class="font-mono break-all">{info.username}</dd><dt>{t('select.identityDomain')}</dt><dd class="break-all">{info.identity_domain_name}</dd><dd class="font-mono break-all">{info.identity_domain_id}</dd></dl>
			{:else if info}
				<p class="text-sm text-ink-1 break-all">{info.email}</p>
				{#if info.kind === 'password_create'}<Alert tone="warning">{account('password.createWarning')}</Alert>{/if}
				{#if info.kind === 'password_create' && !creationReady && !submitted}
					{#if !error}<Alert tone="info">{account('password.createSignInHelp')}</Alert>{/if}
					<Button onclick={signIn} disabled={busy || $logoutInProgress || $projectSwitching}>{account('password.createSignIn')}</Button>
				{:else}
				<form onsubmit={complete} class="space-y-4">
					{#if info.kind === 'password' || info.kind === 'password_create'}
						<Field for="recover-password" label={t('onboarding.password')} help={t('onboarding.passwordHelp')} required><TextInput id="recover-password" type="password" autocomplete="new-password" bind:value={password} maxlength={1024} disabled={busy || submitted || (info.kind === 'password_create' && !creationReady)} required /></Field>
						<Field for="recover-confirm" label={t('onboarding.passwordConfirm')} required><TextInput id="recover-confirm" type="password" autocomplete="new-password" bind:value={confirm} maxlength={1024} disabled={busy || submitted || (info.kind === 'password_create' && !creationReady)} required /></Field>
					{:else}<Alert tone="info">{t('emailChange.confirm')}</Alert>{/if}
					<Button type="submit" disabled={busy || submitted || (info.kind === 'password_create' && !creationReady)} ariaBusy={busy}>{#if busy}<LoadingState variant="control" label={t('onboarding.processing')} />{:else}{info.kind === 'password_create' ? account('password.createSubmit') : info.kind === 'password' ? t('recovery.reset') : t('emailChange.accept')}{/if}</Button>
				</form>
				{/if}
			{/if}
			{#if info?.kind !== 'password_create' || submitted || sessionReady}<Button variant="link" href="/login" disabled={busy}>{t('common.backToLogin')}</Button>{/if}
			{#if !info || (error && submitted && info.kind !== 'password_create')}<Button variant="link" href="/recover">{t('recovery.requestAnother')}</Button>{/if}
	</div></PageShell>
	{/if}
</main>
