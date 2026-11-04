<script lang="ts">
	import { onDestroy, onMount, untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { api, ApiError } from '$lib/api/client';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import AuthStudioShell from '$lib/components/auth/AuthStudioShell.svelte';
	import OnboardingAccountForm from '$lib/components/auth/OnboardingAccountForm.svelte';
	import AccountResultDetails from '$lib/components/auth/AccountResultDetails.svelte';
	import type { DomainAccountResult, DomainInvitationInfo } from '$lib/types/auth';
	import { isOnboardingToken, onboardingErrorKey, storePendingInvitation, signupApprovalState, type SignupApprovalState } from '$lib/utils/domainLogin';
	import { t } from '$lib/i18n/ns/domain-auth';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
	import { beginAuthExperience, observedAuthText, createAuthNoticePresenter, type ExperienceContext } from '$lib/components/auth/authExperience';
	import type { AuthExperience } from '$lib/components/auth/authExperience';

	const token = $derived(($page.params as Record<string, string>)['token'] ?? '');

	let info = $state<DomainInvitationInfo | null>(null);
	let loading = $state(true);
	let loadError = $state('');
	let actionError = $state('');
	let acting = $state(false);
	let accountExists = $state(false);
	let accepted = $state<DomainAccountResult | null>(null);
	let created = $state<DomainAccountResult | null>(null);
	let approval = $state<SignupApprovalState | null>(null);
	let createAbandoned = $state(false);
	let loadSerial = 0;
	let viewExperience = $state.raw<AuthExperience>();
	const presentNotice = createAuthNoticePresenter();
	$effect(() => {
		const key = !viewExperience || loading || loadError ? null
			: approval ? approval === 'pending' ? 'signup.approval.invitationPending' : 'signup.approval.invitationRejected'
			: created ? 'onboarding.created.body' : accepted ? 'invitation.accepted.body' : null;
		if (key) t(key, { project: '', domain: '' });
		presentNotice('result', viewExperience, 'domain-auth', key, created || accepted ? 'success' : approval === 'rejected' ? 'warning' : 'info');
	});

	const signedIn = $derived(!!info && !!$auth.token);
	let live = true;
	let sessionGeneration = 0;
	onMount(() => {
		let previous = '';
		return derived([auth, authReady, logoutInProgress, projectSwitching], ([state, ready, loggingOut, switching]) =>
			JSON.stringify([sessionScopeKey(state), !!state.token, ready, loggingOut, switching])
		).subscribe(key => {
			if (previous && key !== previous) {
				sessionGeneration++;
				accepted = null; actionError = ''; acting = false;
				created = null; approval = null; createAbandoned = true;
			}
			previous = key;
		});
	});

	$effect(() => {
		const current = token;
		untrack(() => void loadInfo(current));
	});

	async function loadInfo(current: string, action: 'load' | 'inspect' = 'load') {
		const serial = ++loadSerial;
		const owns = () => live && serial === loadSerial;
		const observation = beginAuthExperience('auth.invitation', action, owns, 'account');
		viewExperience = observation;
		const text = observedAuthText(observation, 'domain-auth', t);
		observation.state('loading', 0);
		info = null;
		accepted = null;
		created = null;
		approval = null;
		accountExists = false;
		actionError = '';
		loadError = '';
		if (!isOnboardingToken(current)) {
			loading = false;
			loadError = text('invitation.notFound');
			observation.validation('format'); observation.state('error'); void observation.applied();
			return;
		}
		loading = true;
		try {
			const result = await api.get<DomainInvitationInfo>(
				`/api/v1/auth/invitations/${encodeURIComponent(current)}`,
				undefined,
				undefined,
				{ refresh: true, suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false, ...observation.options },
			);
			if (serial !== loadSerial) { observation.discard(live ? 'stale' : 'unmounted'); return; }
			info = result;
			accountExists = result.account_exists;
			observation.state('ready', 1);
		} catch (e) {
			if (serial !== loadSerial) { observation.discard(live ? 'stale' : 'unmounted'); return; }
			const status = e instanceof ApiError ? e.status : null;
			loadError = status === 404 ? text('invitation.notFound') : status === 410 ? text('invitation.gone') : text(onboardingErrorKey(status));
			observation.state('error');
		} finally {
			if (serial === loadSerial) { loading = false; void observation.applied(); }
		}
	}

	async function createAccount(account: { name: string; password: string }, experience?: ExperienceContext) {
		if (!info || accountExists || approval || createAbandoned || $auth.token || $logoutInProgress || $projectSwitching) return;
		const current = token;
		const serial = loadSerial;
		const generation = sessionGeneration;
		const owns = () => live && serial === loadSerial && current === token && generation === sessionGeneration
			&& !$auth.token && !$logoutInProgress && !$projectSwitching;
		const observation = beginAuthExperience('auth.invitation', 'create', owns, 'account', experience);
		const text = observedAuthText(observation, 'domain-auth', t);
		observation.state('loading', 1);
		actionError = '';
		accountExists = false;
		try {
			const result = await api.post<DomainAccountResult>(
				'/api/v1/auth/invitations/accept',
				{ token: current, ...account },
				undefined,
				undefined,
				{ suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false, ...observation.options },
			);
			if (!owns()) { observation.discard(live ? 'stale' : 'unmounted'); return; }
			created = result;
			viewExperience = observation; observation.state('ready', 2); void observation.applied();
		} catch (e) {
			if (!owns()) { observation.discard(live ? 'stale' : 'unmounted'); return; }
			approval = e instanceof ApiError ? signupApprovalState(e) : null;
			if (approval) { created = null; storePendingInvitation(current); viewExperience = observation; observation.state('ready'); void observation.applied(); return; }
			const status = e instanceof ApiError ? e.status : null;
			accountExists = status === 409;
			actionError = text(onboardingErrorKey(status));
			observation.state('error'); void observation.applied();
		}
	}

	async function acceptExisting() {
		const sessionToken = $auth.token;
		const current = token;
		const serial = loadSerial;
		const generation = sessionGeneration;
		const session = sessionScopeKey($auth);
		const owns = () => live && serial === loadSerial && current === token
			&& generation === sessionGeneration && session === sessionScopeKey($auth)
			&& !!$auth.token && $authReady && !$logoutInProgress && !$projectSwitching;
		if (!sessionToken || !signedIn || acting || !owns()) return;
		const observation = beginAuthExperience('auth.invitation', 'approve', owns, 'account');
		const text = observedAuthText(observation, 'domain-auth', t);
		observation.state('loading', 1);
		acting = true;
		actionError = '';
		try {
			const result = await api.post<DomainAccountResult>(
				'/api/v1/auth/invitations/accept-existing',
				{ token: current },
				sessionToken,
				undefined,
				{ cache: 'no-store', replayOnUnauthorized: false, ...observation.options },
			);
			if (!owns()) { observation.discard(live ? 'stale' : 'unmounted'); return; }
			if (result.user_id !== $auth.userId || result.identity_domain_id !== $auth.identityDomainId) throw new Error('Invitation account mismatch');
			accepted = result;
			viewExperience = observation; observation.state('ready', 2);
		} catch (e) {
			if (!owns()) { observation.discard(live ? 'stale' : 'unmounted'); return; }
			const status = e instanceof ApiError ? e.status : null;
			actionError = status === 403 ? text('invitation.emailMismatch') : text(onboardingErrorKey(status));
			observation.state('error');
		} finally {
			if (owns()) { acting = false; void observation.applied(); }
		}
	}

	function signInToAccept() {
		if (!info) return;
		const observation = beginAuthExperience('auth.invitation', 'sign_in', () => live, 'account');
		observation.state('loading');
		storePendingInvitation(token);
		void goto('/login');
	}

	function fmtDate(iso: string): string {
		const date = new Date(iso);
		if (Number.isNaN(date.getTime())) return iso;
		return date.toLocaleString(intlLocale(), { dateStyle: 'long', timeStyle: 'short' });
	}
	onDestroy(() => { live = false; loadSerial++; info = null; accepted = null; created = null; });
</script>

<svelte:head><meta name="referrer" content="no-referrer" /></svelte:head>

<AuthStudioShell variant="account" wide localeId="invitation-token-locale" themeId="invitation-token-theme" footerNote={t('invitation.title')}>
	<div class="auth-flow">
		<header class="auth-flow-heading">
			<h1>{t('invitation.title')}</h1>
		</header>
		{#if loading}
			<LoadingState variant="section" label={t('invitation.loading')} />
		{:else}
			{#if loadError}
				<div class="auth-flow">
					<Alert tone="danger">{loadError}</Alert>
					<Button variant="secondary" href="/login" class="w-full">{t('common.backToLogin')}</Button>
				</div>
			{:else if approval}
				<div class="auth-flow">
					<Alert tone={approval === 'pending' ? 'info' : 'warning'} title={t(approval === 'pending' ? 'signup.approval.pendingTitle' : 'signup.approval.rejectedTitle')}>
						{t(approval === 'pending' ? 'signup.approval.invitationPending' : 'signup.approval.invitationRejected')}
					</Alert>
					<div class="auth-flow-actions">
						{#if approval === 'pending'}<Button onclick={() => loadInfo(token, 'inspect')} class="w-full">{t('signup.approval.reopenInvitation')}</Button>{/if}
						<Button href="/signup" class="w-full">{t('signup.approval.restart')}</Button>
						<Button variant="secondary" href="/login" class="w-full">{t('common.backToLogin')}</Button>
					</div>
				</div>
			{:else if created}
				<div class="auth-flow">
					<Alert tone="success" title={t('onboarding.created.title')}>
						{t('onboarding.created.body', { project: created.personal_project_name ?? '' })}
					</Alert>
					<AccountResultDetails result={created} admission={info ? { id: info.domain_id, name: info.domain_name } : undefined} />
					<Button href="/login" size="lg" class="w-full">{t('onboarding.created.signIn')}</Button>
				</div>
			{:else if accepted}
				<div class="auth-flow">
					<Alert tone="success" title={t('invitation.accepted.title')}>
						<RichText segments={t.rich('invitation.accepted.body', { domain: info?.domain_name ?? '' })} classes={{ strong: 'text-ink-0' }} />
					</Alert>
					<AccountResultDetails result={accepted} admission={info ? { id: info.domain_id, name: info.domain_name } : undefined} />
					<Button href="/select-domain" size="lg" class="w-full">{t('invitation.accepted.continue')}</Button>
				</div>
			{:else if info}
				<dl class="invitation-details">
					<div><dt>{t('invitation.domain')}</dt><dd>{info.domain_name}</dd></div>
					<div><dt>{t('invitation.email')}</dt><dd>{info.email}</dd></div>
					<div><dt>{t('invitation.project')}</dt><dd>{#if info.projects?.length}<ul class="space-y-2">{#each info.projects as project (project.project_id)}<li class="[overflow-wrap:anywhere]">{project.project_name}<span class="block text-xs text-ink-2">{project.project_id}</span><span class="block text-xs text-ink-2">{project.role_ids.join(', ')}</span></li>{/each}</ul>{:else}{info.project_name || t('invitation.noProject')}{/if}</dd></div>
					<div><dt>{t('invitation.expiresAt')}</dt><dd>{fmtDate(info.expires_at)}</dd></div>
				</dl>

				{#if actionError}
					<Alert tone="danger">{actionError}</Alert>
				{/if}

				{#if signedIn}
					<Button size="lg" class="w-full" disabled={acting || !$authReady || $logoutInProgress || $projectSwitching} ariaBusy={acting} onclick={acceptExisting}>
						{t('invitation.acceptExisting', { username: $auth.username ?? '' })}
					</Button>
					{#if acting}
						<LoadingState variant="inline" label={t('onboarding.processing')} class="mt-3" />
					{/if}
				{:else}
					{#if createAbandoned || $logoutInProgress || $projectSwitching}
						<Button href="/login" class="w-full">{t('common.backToLogin')}</Button>
					{:else if !accountExists}
						<h2 class="text-sm font-semibold text-ink-0">{t('invitation.createTitle')}</h2>
						{#key token}<OnboardingAccountForm idPrefix="invitation" submitLabel={t('invitation.create')} onSubmit={createAccount} />{/key}
					{/if}
					<div class="invitation-existing">
						<span>{accountExists ? t('onboarding.accountExists') : t('invitation.existingPrompt')}</span>
						<Button variant={accountExists ? 'primary' : 'link'} size="sm" onclick={signInToAccept}>{t('invitation.signInToAccept')}</Button>
					</div>
					<Button variant="link" size="sm" href="/recover">{t('recovery.title')}</Button>
				{/if}
			{/if}
		{/if}
	</div>
</AuthStudioShell>

<style>
	.invitation-details {
		display: grid;
		gap: 0.625rem;
		margin: 0 0 1.25rem;
		font-size: 0.875rem;
	}

	.invitation-details > div {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		gap: 0.25rem 1rem;
	}

	.invitation-details dt {
		color: var(--color-ink-2);
	}

	.invitation-details dd {
		margin: 0;
		min-width: 0;
		overflow-wrap: anywhere;
		color: var(--color-ink-0);
		text-align: end;
	}

	.invitation-existing {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		margin-top: 1.25rem;
		padding-top: 1rem;
		border-top: 1px solid var(--color-line);
		font-size: 0.875rem;
		color: var(--color-ink-2);
		text-align: center;
	}
</style>
