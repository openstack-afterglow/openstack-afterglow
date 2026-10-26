<script lang="ts">
	import { onDestroy, onMount, untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { api, ApiError } from '$lib/api/client';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import OnboardingAccountForm from '$lib/components/auth/OnboardingAccountForm.svelte';
	import AccountResultDetails from '$lib/components/auth/AccountResultDetails.svelte';
	import type { DomainAccountResult, DomainInvitationInfo } from '$lib/types/auth';
	import { isOnboardingToken, onboardingErrorKey, storePendingInvitation, signupApprovalState, type SignupApprovalState } from '$lib/utils/domainLogin';
	import { t } from '$lib/i18n/ns/domain-auth';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import RichText from '$lib/i18n/RichText.svelte';

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

	async function loadInfo(current: string) {
		const serial = ++loadSerial;
		info = null;
		accepted = null;
		created = null;
		approval = null;
		accountExists = false;
		actionError = '';
		loadError = '';
		if (!isOnboardingToken(current)) {
			loading = false;
			loadError = t('invitation.notFound');
			return;
		}
		loading = true;
		try {
			const result = await api.get<DomainInvitationInfo>(
				`/api/v1/auth/invitations/${encodeURIComponent(current)}`,
				undefined,
				undefined,
				{ refresh: true, suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false },
			);
			if (serial !== loadSerial) return;
			info = result;
			accountExists = result.account_exists;
		} catch (e) {
			if (serial !== loadSerial) return;
			const status = e instanceof ApiError ? e.status : null;
			loadError = status === 404 ? t('invitation.notFound') : status === 410 ? t('invitation.gone') : t(onboardingErrorKey(status));
		} finally {
			if (serial === loadSerial) loading = false;
		}
	}

	async function createAccount(account: { name: string; password: string }) {
		if (!info || accountExists || approval || createAbandoned || $auth.token || $logoutInProgress || $projectSwitching) return;
		const current = token;
		const serial = loadSerial;
		const generation = sessionGeneration;
		const owns = () => live && serial === loadSerial && current === token && generation === sessionGeneration
			&& !$auth.token && !$logoutInProgress && !$projectSwitching;
		actionError = '';
		accountExists = false;
		try {
			const result = await api.post<DomainAccountResult>(
				'/api/v1/auth/invitations/accept',
				{ token: current, ...account },
				undefined,
				undefined,
				{ suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false },
			);
			if (!owns()) return;
			created = result;
		} catch (e) {
			if (!owns()) return;
			approval = e instanceof ApiError ? signupApprovalState(e) : null;
			if (approval) { created = null; storePendingInvitation(current); return; }
			const status = e instanceof ApiError ? e.status : null;
			accountExists = status === 409;
			actionError = t(onboardingErrorKey(status));
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
		acting = true;
		actionError = '';
		try {
			const result = await api.post<DomainAccountResult>(
				'/api/v1/auth/invitations/accept-existing',
				{ token: current },
				sessionToken,
				undefined,
				{ cache: 'no-store', replayOnUnauthorized: false },
			);
			if (!owns()) return;
			if (result.user_id !== $auth.userId || result.identity_domain_id !== $auth.identityDomainId) throw new Error('Invitation account mismatch');
			accepted = result;
		} catch (e) {
			if (!owns()) return;
			const status = e instanceof ApiError ? e.status : null;
			actionError = status === 403 ? t('invitation.emailMismatch') : t(onboardingErrorKey(status));
		} finally {
			if (owns()) acting = false;
		}
	}

	function signInToAccept() {
		if (!info) return;
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

<main id="main-content" tabindex="-1" class="min-h-screen bg-surface-canvas flex items-center justify-center py-8">
	<PageShell class="flex justify-center">
	<div class="w-full max-w-md">
		<h1 class="text-center text-xl font-semibold text-ink-0 mb-6 motion-enter">{t('invitation.title')}</h1>

		<div class="bg-surface-raised border border-line-2 rounded-xl p-5 sm:p-6 motion-enter" style="--motion-index: 1">
			{#if loading}
				<div class="flex justify-center py-6"><ActivityIndicator label={t('invitation.loading')} /></div>
			{:else if loadError}
				<div class="space-y-4">
					<Alert tone="danger">{loadError}</Alert>
					<Button variant="secondary" href="/login" class="w-full">{t('common.backToLogin')}</Button>
				</div>
			{:else if approval}
				<div class="space-y-4">
					<Alert tone={approval === 'pending' ? 'info' : 'warning'} title={t(approval === 'pending' ? 'signup.approval.pendingTitle' : 'signup.approval.rejectedTitle')}>
						{t(approval === 'pending' ? 'signup.approval.invitationPending' : 'signup.approval.invitationRejected')}
					</Alert>
					{#if approval === 'pending'}<Button onclick={() => loadInfo(token)} class="w-full">{t('signup.approval.reopenInvitation')}</Button>{/if}
					<Button href="/signup" class="w-full">{t('signup.approval.restart')}</Button>
					<Button variant="secondary" href="/login" class="w-full">{t('common.backToLogin')}</Button>
				</div>
			{:else if created}
				<div class="space-y-4">
					<Alert tone="success" title={t('onboarding.created.title')}>
						{t('onboarding.created.body', { project: created.personal_project_name ?? '' })}
					</Alert>
					<AccountResultDetails result={created} admission={info ? { id: info.domain_id, name: info.domain_name } : undefined} />
					<Button href="/login" size="lg" class="w-full">{t('onboarding.created.signIn')}</Button>
				</div>
			{:else if accepted}
				<div class="space-y-4">
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
					<Alert tone="danger" class="mb-4">{actionError}</Alert>
				{/if}

				{#if signedIn}
					<Button size="lg" class="w-full" disabled={acting || !$authReady || $logoutInProgress || $projectSwitching} ariaBusy={acting} onclick={acceptExisting}>
						{t('invitation.acceptExisting', { username: $auth.username ?? '' })}
					</Button>
					{#if acting}
						<ActivityIndicator label={t('onboarding.processing')} class="mt-3" />
					{/if}
				{:else}
					{#if createAbandoned || $logoutInProgress || $projectSwitching}
						<Button href="/login" class="w-full">{t('common.backToLogin')}</Button>
					{:else if !accountExists}
						<h2 class="text-sm font-semibold text-ink-0 mb-3">{t('invitation.createTitle')}</h2>
						{#key token}<OnboardingAccountForm idPrefix="invitation" submitLabel={t('invitation.create')} onSubmit={createAccount} />{/key}
					{/if}
					<div class="invitation-existing">
						<span>{accountExists ? t('onboarding.accountExists') : t('invitation.existingPrompt')}</span>
						<Button variant={accountExists ? 'primary' : 'link'} size="sm" onclick={signInToAccept}>{t('invitation.signInToAccept')}</Button>
					</div>
					<Button variant="link" size="sm" href="/recover">{t('recovery.title')}</Button>
				{/if}
			{/if}
		</div>
	</div>
	</PageShell>
</main>

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
