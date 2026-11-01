<script lang="ts">
	import { untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { page } from '$app/stores';
	import { afterNavigate } from '$app/navigation';
	import { isRouteChange, playRouteEntrance } from '$lib/utils/motion';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import VmCreatePanel from '$lib/components/VmCreatePanel.svelte';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { createPrivateViewScope } from '$lib/utils/privateViewScope';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { projectList } from '$lib/stores/projectList';
	import { wizardOpen } from '$lib/stores/wizard';
	import { loadTutorialStatuses } from '$lib/tutorial/status';
	import { getLocale } from '$lib/i18n/runtime.svelte';
	let { children } = $props();
	const privateViewScope = createPrivateViewScope();
	// Terminal routes own live sockets and scrollback; language is display state, not their lifetime.
	const pageLocaleKey = $derived(
		$page.route.id === '/dashboard/containers/instances/[id]'
		|| $page.route.id === '/dashboard/drover'
		|| $page.route.id === '/dashboard/drover/[id]'
			? $page.route.id
			: getLocale(),
	);
	let mainEl = $state<HTMLElement | null>(null);

	afterNavigate((nav) => {
		if (isRouteChange(nav)) playRouteEntrance(mainEl);
	});

	// Display snapshots belong to a logical login/scope, not rotating credentials.
	const displayOwner = $derived(JSON.stringify([!!$auth.token, sessionScopeKey($auth)]));
	$effect(() => {
		$privateViewScope;
		displayOwner;
		if (!$authReady) return;
		untrack(() => {
			const state = get(auth);
			if (!state.token) return;
			void loadTutorialStatuses();
			if (state.userId) projectList.prefetch(state.token, state.userId);
		});
	});
	// Successful logical-owner history is reused; a failed read can retry on renewal.
	$effect(() => {
		if (!$authReady || !$auth.token) return;
		untrack(() => void loadTutorialStatuses());
	});
</script>

<!-- One viewport-bounded workspace; main is the only content scroll owner. -->
<div class="flex h-[100dvh] overflow-hidden">
	<Sidebar />
	<main bind:this={mainEl} id="main-content" tabindex="-1" class="min-w-0 flex-1 overflow-y-auto pt-[var(--app-header-height)] focus:outline-none focus-visible:shadow-[var(--focus-ring)]">
		<div class={$authReady && !$projectSwitching ? 'contents' : 'hidden'} inert={!$authReady || $projectSwitching}>
			{#key `${pageLocaleKey}:${$privateViewScope}`}
				{#if !$projectSwitching}{@render children()}{/if}
			{/key}
		</div>
	</main>
</div>

{#if $wizardOpen}
	<VmCreatePanel />
{/if}
