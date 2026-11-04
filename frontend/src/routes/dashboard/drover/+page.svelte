<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t } from '$lib/i18n/ns/drover-pages';
	import { untrack } from 'svelte';
	import { auth, authReady } from '$lib/stores/auth';
	import { k3sPermissions } from '$lib/stores/k3sPermissions';
	import { api } from '$lib/api/client';
	import { createK3sClusterListController } from '$lib/stores/k3sClusterListController.svelte';
	import K3sClusterDetailPanel from '$lib/components/K3sClusterDetailPanel.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createDroverClusterPanel } from '$lib/utils/droverClusterPanel.svelte';
	import K3sCreateClusterModal from '$lib/components/dashboard/drover/K3sCreateClusterModal.svelte';
	import DroverHeader from '$lib/components/dashboard/drover/DroverHeader.svelte';
	import DroverClusterGrid from '$lib/components/dashboard/drover/DroverClusterGrid.svelte';
	import { Alert, Button } from '$lib/components/ui';

	const panel = createDroverClusterPanel();

	const ctrl = createK3sClusterListController({
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
		userId: () => $auth.userId,
	});

	function prefetchCreateDependencies() {
		if (!$k3sPermissions.editClusters) return;
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		void api.prefetch('/api/v1/flavors', token, projectId);
		void api.prefetch('/api/v1/networks', token, projectId);
        if ($k3sPermissions.adminCredentials) void api.prefetch('/api/v1/keypairs', token, projectId);
		void api.prefetch('/api/v1/k3s/cluster-templates', token, projectId);
	}

	const ar = createAutoRefresh(() => ctrl.fetchClusters(), {
		storageKey: 'dashboard-drover',
		defaultActive: true,
		defaultInterval: 10,
		intervalOptions: [10, 15, 30, 60],
		invokeOnMount: false,
	});

	$effect(() => {
		const pid = $auth.projectId;
		const ready = $authReady;
		if (!pid || !ready) return;
		ctrl.loading = true;
		untrack(() => ctrl.fetchClusters());
	});
</script>

<K3sCreateClusterModal
	bind:open={ctrl.showModal}
	token={$auth.token ?? undefined}
	projectId={$auth.projectId ?? undefined}
	createError={ctrl.createError}
	creating={ctrl.creating}
	onCreate={ctrl.createCluster}
/>


{#if panel.selectedClusterId}
	<SlidePanel onClose={panel.close} ariaLabel={t('cluster.detailLabel')}>
		<K3sClusterDetailPanel clusterId={panel.selectedClusterId} onClose={panel.close} />
	</SlidePanel>
{/if}

<PageShell>
	<DroverHeader
		bind:showDeleted={ctrl.showDeleted}
		{ar}
		refreshing={ctrl.refreshing || ctrl.loading}
		onForceRefresh={ctrl.forceRefresh}
		onOpenCreate={() => { ctrl.showModal = true; }}
		onToggleDeleted={ctrl.toggleDeleted}
		onOpenCreateIntent={prefetchCreateDependencies}
	/>

	<p class="text-sm text-ink-2 mb-6">{t('dashboard.description')}</p>

	{#if ctrl.error}
		<Alert tone="danger" title={t('clusterError.loadFailed')} class="mb-4">{ctrl.error}{#snippet actions()}<Button variant="secondary" size="sm" onclick={ctrl.forceRefresh} disabled={ctrl.refreshing}>{t('clusterError.reload')}</Button>{/snippet}</Alert>
	{/if}

	{#if ctrl.loading || ctrl.clusters.length > 0 || !ctrl.error}
	<DroverClusterGrid
		clusters={ctrl.clusters}
		loading={ctrl.loading}
		deletingId={ctrl.deleting}
		onSelect={panel.open}
		onDownloadKubeconfig={ctrl.downloadKubeconfig}
		onDelete={ctrl.deleteCluster}
		onOpenCreate={() => { ctrl.showModal = true; }}
		onOpenCreateIntent={prefetchCreateDependencies}
	/>
	{/if}
</PageShell>
