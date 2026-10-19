<script lang="ts">
	import { onMount } from 'svelte';
	import { derived } from 'svelte/store';
	import { page } from '$app/stores';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { t } from '$lib/i18n/ns/workspace-selector';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import WorkspaceBrowser from '$lib/components/workspaces/WorkspaceBrowser.svelte';

	let open = $state(false);
	let busy = $state(false);
	function portal(node: HTMLElement) {
		document.body.appendChild(node);
		return { destroy: () => node.remove() };
	}
	onMount(() => {
		let previous = '';
		return derived([auth, authReady, logoutInProgress], ([state, ready, loggingOut]) => ({ state, ready, loggingOut })).subscribe(({ state, ready, loggingOut }) => {
			const key = JSON.stringify([sessionScopeKey(state), !!state.token, ready, loggingOut]);
			if (previous && key !== previous) open = false;
			previous = key;
		});
	});
</script>

<button type="button" onclick={() => { open = true; }} disabled={$projectSwitching || !$authReady || $logoutInProgress || !$auth.token} aria-haspopup="dialog" aria-expanded={open} aria-label={t('openSelector', { project: $auth.projectName || t('noProject'), domain: $auth.domainName || $auth.domainId || '—' })} title={`${$auth.domainName || $auth.domainId || ''} · ${$auth.projectName || t('noProject')}`} class="flex min-h-11 w-full min-w-0 items-center gap-2 rounded-md bg-surface-sunken px-2 py-1 text-left text-sm text-ink-1 transition-colors hover:bg-surface-selected focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)] disabled:opacity-50 md:min-h-8">
	<svg class="size-4 shrink-0 text-ink-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 7h7l2 2h9v11H3zM3 7V4h7l2 3" /></svg>
	<span class="min-w-0 flex-1">
		<span class="block truncate text-xs text-ink-2">{$auth.domainName || $auth.domainId || '—'}</span>
		<span class="block truncate">{$auth.projectName || t('noProject')}</span>
	</span>
	<svg class="size-3 shrink-0 text-ink-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m6 9 6 6 6-6" /></svg>
</button>

{#if open}
	<div use:portal>
		<Modal bind:open ariaLabel={t('title')} onClose={() => { open = false; }} dismissible={!busy && !$projectSwitching}>
			<Card surface="modal" padding="none">
				<WorkspaceBrowser bind:busy mockup={$page.data.mockup?.active === true} onSelected={() => { open = false; }} onClose={() => { if (!busy && !$projectSwitching) open = false; }} />
			</Card>
		</Modal>
	</div>
{/if}
