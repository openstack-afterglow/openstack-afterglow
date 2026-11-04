<script lang="ts">
	import { onDestroy, onMount, untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { page } from '$app/stores';
	import { api, ApiError } from '$lib/api/client';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import AuthStudioShell from '$lib/components/auth/AuthStudioShell.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import OnboardingAccountForm from '$lib/components/auth/OnboardingAccountForm.svelte';
	import type { DomainAccountResult } from '$lib/types/auth';
	import { isOnboardingToken, onboardingErrorKey, registrationConflictKind, signupApprovalState, type SignupApprovalState } from '$lib/utils/domainLogin';
	import { t } from '$lib/i18n/ns/domain-auth';
	import AccountResultDetails from '$lib/components/auth/AccountResultDetails.svelte';
	import { beginAuthExperience, observedAuthText, createAuthNoticePresenter, type ExperienceContext } from '$lib/components/auth/authExperience';
	import type { AuthExperience } from '$lib/components/auth/authExperience';

	interface RegistrationInfo { email: string; account_exists: boolean; identity_domain_id?: string; identity_domain_name?: string }
	const token = $derived(($page.params as Record<string, string>)['token'] ?? '');
	let info = $state<RegistrationInfo | null>(null);
	let created = $state<DomainAccountResult | null>(null);
	let error = $state('');
	let approval = $state<SignupApprovalState | null>(null);
	let abandoned = $state(false);
	let loading = $state(true);
	let live = true;
	let generation = 0;
	let viewExperience = $state.raw<AuthExperience>();
	const presentNotice = createAuthNoticePresenter();
	$effect(() => {
		const key = !viewExperience || loading || abandoned || $auth.token || $logoutInProgress || $projectSwitching ? null
			: approval ? approval === 'pending' ? 'signup.approval.emailPending' : 'signup.approval.emailRejected'
			: created ? 'onboarding.created.body' : info?.account_exists ? 'onboarding.accountExists' : null;
		if (key) t(key, { project: '' });
		presentNotice('result', viewExperience, 'domain-auth', key, created ? 'success' : approval === 'rejected' ? 'warning' : 'info');
	});
	onMount(() => {
		let previous = '';
		return derived([auth, authReady, logoutInProgress, projectSwitching], ([state, ready, loggingOut, switching]) =>
			JSON.stringify([sessionScopeKey(state), !!state.token, ready, loggingOut, switching])
		).subscribe(key => {
			if (previous && key !== previous) {
				abandoned = true; generation++; info = null; created = null; approval = null; error = ''; loading = false;
			}
			previous = key;
		});
	});
	$effect(() => { const current = token; untrack(() => void inspect(current)); });
	async function inspect(current: string, experience?: ExperienceContext) {
		const boundary = ++generation;
		const owns = () => live && !abandoned && boundary === generation;
		const observation = beginAuthExperience('auth.signup', 'load', owns, 'account', experience);
		viewExperience = observation;
		const text = observedAuthText(observation, 'domain-auth', t);
		observation.state('loading', 0);
		created = null; info = null; approval = null; error = ''; loading = true;
		if (abandoned || $auth.token || $logoutInProgress || $projectSwitching) { loading = false; observation.discard('scope_changed'); return; }
		if (!isOnboardingToken(current)) { error = text('onboarding.linkInvalid'); loading = false; observation.validation('format'); observation.state('error'); void observation.applied(); return; }
		try {
			const result = await api.get<RegistrationInfo>(`/api/v1/auth/registrations/${encodeURIComponent(current)}`, undefined, undefined, { refresh: true, suppressAuthRedirect: true, cache: 'no-store', ...observation.options });
			if (!owns()) { observation.discard(live ? 'stale' : 'unmounted'); return; }
			info = result;
			observation.state('ready', 1);
		} catch (e) {
			if (owns()) {
				approval = e instanceof ApiError ? signupApprovalState(e) : null;
				if (!approval) error = text(onboardingErrorKey(e instanceof ApiError ? e.status : null));
				observation.state(approval ? 'ready' : 'error');
			} else observation.discard(live ? 'stale' : 'unmounted');
		} finally { if (owns()) { loading = false; void observation.applied(); } }
	}
	async function createAccount(account: { name: string; password: string }, experience?: ExperienceContext) {
		if (!info || info.account_exists || approval || abandoned || $auth.token || $logoutInProgress || $projectSwitching) return;
		const current = token;
		const boundary = generation;
		const owns = () => live && !abandoned && current === token && boundary === generation;
		const observation = beginAuthExperience('auth.signup', 'create', owns, 'account', experience);
		const text = observedAuthText(observation, 'domain-auth', t);
		observation.state('loading', 1);
		error = '';
		try {
			const result = await api.post<DomainAccountResult>('/api/v1/auth/registrations/accept', { token: current, ...account }, undefined, undefined, { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false, ...observation.options });
			if (owns()) { created = result; info = null; viewExperience = observation; observation.state('ready', 2); void observation.applied(); }
			else observation.discard(live ? 'stale' : 'unmounted');
		} catch (e) {
			if (!owns()) { observation.discard(live ? 'stale' : 'unmounted'); return; }
			approval = e instanceof ApiError ? signupApprovalState(e) : null;
			if (approval) { info = null; created = null; viewExperience = observation; observation.state('ready'); void observation.applied(); return; }
			const conflict = e instanceof ApiError ? registrationConflictKind(e) : null;
			if (conflict === 'username') { error = text('onboarding.usernameUnavailable'); observation.state('error'); void observation.applied(); return; }
			if (conflict === 'email' && info) { info = { ...info, account_exists: true }; viewExperience = observation; observation.state('ready'); void observation.applied(); return; }
			if (conflict === 'recovery') { info = null; error = text('onboarding.unavailable'); observation.state('error'); void observation.applied(); return; }
			// A newly detected existing email is never treated as permission to create/reset.
			if (e instanceof ApiError && e.status === 409) {
				await inspect(current, observation.context);
				if (live && !abandoned && current === token && boundary === generation - 1 && info && !info.account_exists) {
					const inspectedGeneration = generation;
					const inspected = beginAuthExperience('auth.signup', 'load', () => live && !abandoned && current === token && inspectedGeneration === generation, 'account', observation.context);
					error = observedAuthText(inspected, 'domain-auth', t)('onboarding.invalidInput');
					inspected.state('error'); void inspected.applied();
				}
				return;
			}
			error = text(onboardingErrorKey(e instanceof ApiError ? e.status : null));
			observation.state('error'); void observation.applied();
		}
	}
	onDestroy(() => { live = false; generation++; info = null; created = null; approval = null; });
</script>
<svelte:head><meta name="referrer" content="no-referrer" /></svelte:head>
<AuthStudioShell variant="account" wide localeId="registration-token-locale" themeId="registration-token-theme" footerNote={t('registration.title')}>
	<div class="auth-flow">
		<header class="auth-flow-heading">
			<h1>{t('registration.title')}</h1>
		</header>
		{#if loading && !abandoned && !$auth.token && !$logoutInProgress && !$projectSwitching}
			<LoadingState variant="section" label={t('onboarding.processing')} />
		{:else}
			{#if abandoned || $auth.token || $logoutInProgress || $projectSwitching}
				<div class="auth-flow-actions">
					<Button href="/login" class="w-full">{t('common.backToLogin')}</Button>
					{#if !$auth.token}<Button variant="secondary" href="/signup" class="w-full">{t('signup.approval.restart')}</Button>{/if}
				</div>
			{:else if approval}
				<Alert tone={approval === 'pending' ? 'info' : 'warning'} title={t(approval === 'pending' ? 'signup.approval.pendingTitle' : 'signup.approval.rejectedTitle')}>
					{t(approval === 'pending' ? 'signup.approval.emailPending' : 'signup.approval.emailRejected')}
				</Alert>
				<div class="auth-flow-actions">
					<Button href="/signup" class="w-full">{t('signup.approval.restart')}</Button>
					<Button variant="secondary" href="/login" class="w-full">{t('common.backToLogin')}</Button>
				</div>
			{:else if created}
				<Alert tone="success" title={t('onboarding.created.title')}>{t('onboarding.created.body', { project: created.personal_project_name ?? '' })}</Alert>
				<AccountResultDetails result={created} />
				<Button href="/login" class="w-full">{t('onboarding.created.signIn')}</Button>
			{:else}
				{#if error}<Alert tone="danger">{error}</Alert>{/if}
				{#if info?.account_exists}
					<Alert tone="info">{t('onboarding.accountExists')}</Alert>
					<p class="text-sm text-ink-2">{t('signup.existing')}</p>
					<div class="auth-flow-actions">
						<Button href="/login" class="w-full">{t('onboarding.created.signIn')}</Button>
						<Button variant="link" href="/recover">{t('recovery.title')}</Button>
					</div>
				{:else if info}
					<p class="text-sm text-ink-1 break-all">{info.email}</p>
					<p class="text-sm text-ink-2">{t('registration.description')}</p>
					{#key token}<OnboardingAccountForm idPrefix="registration" submitLabel={t('registration.submit')} onSubmit={createAccount} />{/key}
				{:else}<Button variant="secondary" href="/signup">{t('login.signup.open')}</Button>{/if}
			{/if}
		{/if}
	</div>
</AuthStudioShell>
