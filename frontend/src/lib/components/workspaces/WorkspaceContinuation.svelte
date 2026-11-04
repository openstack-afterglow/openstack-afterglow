<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { startLogout } from '$lib/utils/logout';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { t as tShell } from '$lib/i18n/ns/shell';
	import { takePendingInvitationPath } from '$lib/utils/domainLogin';
	import { postAuthDestination } from '$lib/utils/mcpConsent';
	import { t } from '$lib/i18n/ns/workspace-selector';
	import { t as tp } from '$lib/i18n/ns/public-entry';
	import AuthStudioShell from '$lib/components/auth/AuthStudioShell.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import WorkspaceBrowser from './WorkspaceBrowser.svelte';
	import { beginAuthExperience } from '$lib/components/auth/authExperience';
	let loggingOut = $state(false);
	let busy = $state(false);
	let live = false;
	let ownerEpoch = 0;
	// Only explicit continue/selection actions consume invitation or MCP intent; reads never navigate.
	function continueSession() {
		if (busy || get(projectSwitching)) return;
		continueAfterSelection();
	}
	// A successful selection owns its switch lock until its callback returns.
	function continueAfterSelection(sourceSelection = false) {
		if (!get(authReady) || !get(auth).token || get(logoutInProgress)) return;
		const state = get(auth);
		beginAuthExperience('page', sourceSelection ? 'load' : 'navigate', () => live, 'iam').state('loading');
		const fallback = state.projectId ? '/dashboard' : state.isDomainManager ? '/dashboard/iam/users' : state.isSystemAdmin ? '/admin' : '/select-project';
		void goto(takePendingInvitationPath() ?? postAuthDestination(fallback));
	}
	onMount(() => {
		live = true;
		let previous = '';
		const unsubscribe = auth.subscribe(state => {
			const next = sessionScopeKey(state);
			if (previous && next !== previous) ownerEpoch++;
			previous = next;
			if (!state.token && !loggingOut) void goto('/login', { replaceState: true });
		});
		return () => { live = false; ownerEpoch++; unsubscribe(); };
	});
	let logoutConfirming = false;
	async function logout() {
		if (busy || loggingOut || logoutConfirming || get(logoutInProgress) || get(projectSwitching)) return;
		const owner = sessionScopeKey(get(auth));
		const epoch = ownerEpoch;
		const observation = beginAuthExperience('page', 'sign_out', () => live && epoch === ownerEpoch);
		logoutConfirming = true;
		try {
			const prompt = tShell('logout.confirm');
			observation.message('shell', 'logout.confirm', 'warning');
			if (!await confirmDialog(prompt)) {
				beginAuthExperience('page', 'cancel', () => live && epoch === ownerEpoch).state('ready');
				return;
			}
			if (busy || get(logoutInProgress) || get(projectSwitching) || sessionScopeKey(get(auth)) !== owner) { observation.discard('scope_changed'); return; }
			loggingOut = true;
			if (observation.context) void startLogout({ experience: observation.context }); else void startLogout();
		} finally {
			logoutConfirming = false;
		}
	}
</script>

<svelte:head><title>{t('title')}</title></svelte:head>
<AuthStudioShell
	variant="account"
	wide
	localeId="workspace-entry-locale"
	themeId="workspace-entry-theme"
	footerNote={t('title')}
>
	<div class="auth-flow">
		<header class="auth-flow-heading"><h1>{t('title')}</h1></header>
		<div class="auth-flow-actions">
			<Button variant="secondary" onclick={continueSession} disabled={busy || !$authReady || !$auth.token || $logoutInProgress || $projectSwitching}>{t('continue')}</Button>
			<Button variant="secondary" onclick={logout} disabled={busy || $logoutInProgress || $projectSwitching}>{tp('selectProject.logout')}</Button>
		</div>
		{#if $authReady && $auth.token && !$logoutInProgress}
			<div class="workspace-entry-browser">
				<WorkspaceBrowser bind:busy mockup={$page.data.mockup?.active === true} onSelected={() => continueAfterSelection(true)} onClose={continueSession} />
			</div>
		{:else}
			<LoadingState variant="section" label={t('loading')} />
		{/if}
	</div>
</AuthStudioShell>

<style>
	.workspace-entry-browser { min-width: 0; }
	.workspace-entry-browser :global(.workspace-browser) { width: 100%; height: auto; }
	/* The standalone shell owns the page heading and scrolling; the chooser
	   retains its existing grouped content and actions without modal bounds. */
	.workspace-entry-browser :global(.workspace-browser > header h2) { display: none; }
	.workspace-entry-browser :global(.workspace-browser > header),
	.workspace-entry-browser :global(.workspace-browser > div),
	.workspace-entry-browser :global(.workspace-browser > footer) { padding-inline: 0; }
	.workspace-entry-browser :global(.workspace-browser > header) { padding-top: 0; }
</style>
