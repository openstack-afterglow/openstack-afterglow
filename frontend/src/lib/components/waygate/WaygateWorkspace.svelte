<script lang="ts">
	import { t } from '$lib/i18n/ns/waygate';
	import { auth } from '$lib/stores/auth';
	import { createWaygateProjectScope } from '$lib/utils/waygateProjectScope';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import WaygateProjectWorkspace from './WaygateProjectWorkspace.svelte';
	import { onDestroy } from 'svelte';
	import { createPrivateViewScope } from '$lib/utils/privateViewScope';
	import { createWaygateViewState } from '$lib/utils/waygateView.svelte';

	let { admin = false }: { admin?: boolean } = $props();
	const scope = createWaygateProjectScope(auth);
	// Display conditions may survive bearer renewal; mutation workspaces may not.
	const privateViewScope = createPrivateViewScope();
	const viewState = createWaygateViewState();
	const stopDisplayScope = privateViewScope.subscribe(() => {
		// Clear in place: an authority-only change must not detach a live mutation owner.
		for (const state of [viewState.servers, viewState.clients, viewState.attachments]) {
			state.search = ''; state.sort = null; state.filters = {};
		}
		viewState.detailTarget = null;
	});
	onDestroy(stopDisplayScope);
</script>

{#key $scope}
	{#if $scope}
		<WaygateProjectWorkspace scope={$scope} {admin} {viewState} />
	{:else}
		<div>
			<PageHeader breadcrumb={admin ? t('workspace.breadcrumb.admin') : t('workspace.breadcrumb.network')} title={admin ? t('workspace.adminTitle') : 'Waygate'} />
			<Alert tone="info">{t('workspace.selectProject')}</Alert>
		</div>
	{/if}
{/key}
