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
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import WorkspaceBrowser from './WorkspaceBrowser.svelte';
	let loggingOut = $state(false);
	let busy = $state(false);
	// Only explicit continue/selection actions consume invitation or MCP intent; reads never navigate.
	function continueSession() {
		if (busy || get(projectSwitching)) return;
		continueAfterSelection();
	}
	// A successful selection owns its switch lock until its callback returns.
	function continueAfterSelection() {
		if (!get(authReady) || !get(auth).token || get(logoutInProgress)) return;
		const state = get(auth);
		const fallback = state.projectId ? '/dashboard' : state.isDomainManager ? '/dashboard/iam/users' : state.isSystemAdmin ? '/admin' : '/select-project';
		void goto(takePendingInvitationPath() ?? postAuthDestination(fallback));
	}
	onMount(() => auth.subscribe(state => { if (!state.token && !loggingOut) void goto('/login', { replaceState: true }); }));
	let logoutConfirming = false;
	async function logout() {
		if (busy || loggingOut || logoutConfirming || get(logoutInProgress) || get(projectSwitching)) return;
		const owner = sessionScopeKey(get(auth));
		logoutConfirming = true;
		try {
			if (!await confirmDialog(tShell('logout.confirm'))) return;
			if (busy || get(logoutInProgress) || get(projectSwitching) || sessionScopeKey(get(auth)) !== owner) return;
			loggingOut = true;
			void startLogout();
		} finally {
			logoutConfirming = false;
		}
	}
</script>

<svelte:head><title>{t('title')}</title></svelte:head>
<main id="main-content" tabindex="-1" class="min-h-screen bg-surface-canvas text-ink-0">
	<PageShell>
		<div class="mb-4 flex flex-wrap items-center justify-end gap-2">
			<Button variant="secondary" onclick={continueSession} disabled={busy || !$authReady || !$auth.token || $logoutInProgress || $projectSwitching}>{t('continue')}</Button>
			<Button variant="secondary" onclick={logout} disabled={busy || $logoutInProgress || $projectSwitching}>{tp('selectProject.logout')}</Button>
		</div>
		{#if $authReady && $auth.token && !$logoutInProgress}
			<div class="flex justify-center"><Card surface="base" padding="none"><WorkspaceBrowser bind:busy mockup={$page.data.mockup?.active === true} onSelected={continueAfterSelection} onClose={continueSession} /></Card></div>
		{:else}<LoadingState variant="surface" label={t('loading')}  />{/if}
	</PageShell>
</main>
