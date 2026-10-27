<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import { ApiError } from '$lib/api/client';
	import { domainIam, type IamContext, type IamSession } from '$lib/api/domainIam';
	import { t } from '$lib/i18n/ns/domain-iam';
	import { t as workspaceT } from '$lib/i18n/ns/workspace-iam';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import IamUsers from './IamUsers.svelte';
	import IamInvitations from './IamInvitations.svelte';
	import IamLogin from './IamLogin.svelte';
	import IamRecovery from './IamRecovery.svelte';
	import IamQuotas from './IamQuotas.svelte';
	import IamResources from './IamResources.svelte';
	import IamForecast from './IamForecast.svelte';
	let session = $state.raw<IamSession | null>(null);
	let verifiedSession = $state.raw<IamSession | null>(null);
	let context = $state<IamContext | null>(null);
	let checking = $state(false);
	let error = $state('');
	let tab = $state<'users' | 'invitations' | 'login' | 'recovery' | 'monitoring'>('users');
	let revision = $state(0);
	let request = 0;
	let verification = 0;
	let liveToken = '';
	let sessionOwner = '';
	const unsubscribe = derived([auth, authReady, projectSwitching, logoutInProgress], ([state, ready, switching, loggingOut]) => ({ state, ready, switching, loggingOut })).subscribe(({ state, ready, switching, loggingOut }) => {
		const eligible = ready && !switching && !loggingOut && state.token && state.userId && state.domainId && state.isDomainManager === true;
		const owner = JSON.stringify([state.sessionId ?? null, state.userId, state.identityDomainId ?? null, state.domainId]);
		if (eligible && sessionOwner === owner && session) { liveToken = state.token!; return; }
		request++;
		liveToken = eligible ? state.token! : '';
		sessionOwner = eligible ? owner : '';
		session = eligible ? { token: () => liveToken, userId: state.userId!, domainId: state.domainId!, isCurrent: () => false, canSubmit: () => false } : null;
		context = null; verifiedSession = null; checking = false; error = ''; revision++;
	});
	async function verify(target: IamSession) {
		if (session !== target) return;
		const pending = ++verification;
		const boundary = request;
		checking = true; error = '';
		try {
			const result = await domainIam(target).context();
			if (session !== target || request !== boundary || verification !== pending) return;
			if (result.domain_id !== target.domainId) { revoked(t('domainMismatch')); return; }
			if (result.is_domain_manager !== true) { revoked(); return; }
			context = result;
			if (!verifiedSession) verifiedSession = {
				...target,
				isCurrent: () => session === target && request === boundary && context !== null,
				canSubmit: () => !checking && !error
			};
		} catch (cause) {
			if (session === target && request === boundary && verification === pending) {
				if (cause instanceof ApiError && cause.status === 403) revoked();
				else error = cause instanceof Error ? cause.message : t('loadFailed');
			}
		} finally { if (session === target && request === boundary && verification === pending) checking = false; }
	}
	function revoked(message = t('denied')) { request++; context = null; verifiedSession = null; checking = false; error = message; revision++; }
	function focus() { if (session) void verify(session); }
	function visible() { if (document.visibilityState === 'visible') focus(); }
	$effect(() => { const target = session; if (target) untrack(() => void verify(target)); });
	onDestroy(() => { unsubscribe(); session = null; request++; });
</script>

<svelte:window onfocus={focus} />
<svelte:document onvisibilitychange={visible} />
<PageShell>
	<PageHeader breadcrumb={t('title')} title={t('usersTitle')} subtitle={t('usersSubtitle')}>
		{#snippet actions()}<Button variant="secondary" disabled={checking || !session} onclick={focus}>{t('refresh')}</Button>{/snippet}
	</PageHeader>
	{#if checking}<ActivityIndicator label={t('verifying')} />
	{:else if error}<Alert tone="danger">{error}</Alert>
	{:else if !session}<Alert tone="warning">{t('denied')}</Alert>{/if}
	{#if session && context && verifiedSession}
		<div class="mb-4 rounded-lg border border-line bg-surface-base p-3 text-sm text-ink-1 [overflow-wrap:anywhere]">
			<strong>{t('domain')}</strong> · {context.domain_name} <code class="text-xs text-ink-2">{context.domain_id}</code>
			<p class="mt-1 text-xs text-ink-2">{t('domainHelp')}</p>
		</div>
		<nav class="mb-4 flex flex-wrap gap-2" aria-label={t('sections')}>
			{#each ['users', 'invitations', 'login', 'recovery'] as section}
				<Button variant={tab === section ? 'secondary' : 'ghost'} ariaPressed={tab === section} onclick={() => tab = section as typeof tab}>{t(section as 'users' | 'invitations' | 'login' | 'recovery')}</Button>
			{/each}
			<Button variant={tab === 'monitoring' ? 'secondary' : 'ghost'} ariaPressed={tab === 'monitoring'} onclick={() => tab = 'monitoring'}>{workspaceT('monitoringTitle')}</Button>
		</nav>
		{#key revision}
			{#if tab === 'users'}<IamUsers session={verifiedSession} blocked={checking || !!error} onDenied={() => revoked()} />
			{:else if tab === 'invitations'}<IamInvitations session={verifiedSession} blocked={checking || !!error} onDenied={() => revoked()} />
			{:else if tab === 'login'}<IamLogin session={verifiedSession} blocked={checking || !!error} onDenied={() => revoked()} />
			{:else if tab === 'monitoring'}
				<div class="space-y-8">
					<p class="text-sm text-ink-2">{workspaceT('monitoringHelp')}</p>
					<nav class="flex flex-wrap gap-2" aria-label={workspaceT('monitoringSections')}>
						<Button variant="ghost" href="#iam-monitoring-overview">{workspaceT('monitoringOverview')}</Button>
						<Button variant="ghost" href="#iam-monitoring-forecast">{workspaceT('monitoringForecast')}</Button>
						<Button variant="ghost" href="#iam-monitoring-allocation">{workspaceT('monitoringAllocation')}</Button>
					</nav>
					<section id="iam-monitoring-overview" class="scroll-mt-20"><IamResources session={verifiedSession} blocked={checking || !!error} onDenied={focus} /></section>
					<section id="iam-monitoring-forecast" class="scroll-mt-20"><IamForecast session={verifiedSession} blocked={checking || !!error} onDenied={focus} /></section>
					<section id="iam-monitoring-allocation" class="scroll-mt-20"><IamQuotas session={verifiedSession} blocked={checking || !!error} onDenied={focus} /></section>
				</div>
			{:else}<IamRecovery session={verifiedSession} blocked={checking || !!error} onDenied={() => revoked()} />{/if}
		{/key}
	{/if}
</PageShell>
