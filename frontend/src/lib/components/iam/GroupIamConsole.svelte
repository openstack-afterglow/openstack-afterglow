<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import { ApiError } from '$lib/api/client';
	import { domainIam, type IamContext, type IamSession } from '$lib/api/domainIam';
	import { t } from '$lib/i18n/ns/domain-iam-groups';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import IamGroups from './IamGroups.svelte';
	let session = $state.raw<IamSession | null>(null);
	let verifiedSession = $state.raw<IamSession | null>(null);
	let context = $state<IamContext | null>(null);
	let checking = $state(false);
	let error = $state('');
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
	<PageHeader breadcrumb={t('title')} title={t('pageTitle')} subtitle={t('pageSubtitle')}>
		{#snippet actions()}<Button variant="secondary" disabled={checking || !session} onclick={focus}>{t('refresh')}</Button>{/snippet}
	</PageHeader>
	{#if checking}<LoadingState variant={context && verifiedSession ? 'inline' : 'surface'} label={t('verifying')} />
	{:else if error}<Alert tone="danger">{error}</Alert>
	{:else if !session}<Alert tone="warning">{t('denied')}</Alert>{/if}
	{#if session && context && verifiedSession}
		{#key revision}
			<!-- Group boundary 403s are target errors; only a failed re-verification revokes the page. -->
			<IamGroups session={verifiedSession} blocked={checking || !!error} onDenied={focus} />
		{/key}
	{/if}
</PageShell>
