<script lang="ts">
	import { onMount } from 'svelte';
	import { derived } from 'svelte/store';
	import { page } from '$app/stores';
	import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { t } from '$lib/i18n/ns/workspace-selector';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import WorkspaceBrowser from './WorkspaceBrowser.svelte';

	let { open = $bindable(false), createDomain = false }: { open?: boolean; createDomain?: boolean } = $props();
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

{#if open}
	<div use:portal>
		<Modal bind:open ariaLabel={t('title')} onClose={() => { open = false; }} dismissible={!busy && !$projectSwitching}>
			<Card surface="modal" padding="none">
				<WorkspaceBrowser bind:busy {createDomain} mockup={$page.data.mockup?.active === true} onSelected={() => { open = false; }} onClose={() => { if (!busy && !$projectSwitching) open = false; }} />
			</Card>
		</Modal>
	</div>
{/if}
