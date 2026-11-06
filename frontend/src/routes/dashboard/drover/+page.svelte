<script lang="ts">
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import type { K3sCluster } from '$lib/types/k3s';
	import { t as td } from '$lib/i18n/ns/drover';
	import { t as tc } from '$lib/i18n/ns/common';
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

	let search = $state('');
	const columns = $derived<TableColumn<K3sCluster>[]>([
		{ key: 'name', label: td('overview.table.name'), value: row => row.name },
		{ key: 'status', label: td('overview.table.status'), value: row => row.status },
		{ key: 'agents', label: td('overview.table.worker'), value: row => row.agent_count },
		{ key: 'created_at', label: td('overview.table.createdAt'), value: row => row.created_at ? Date.parse(row.created_at) : null },
	]);
	const view = createTableView({ rows: () => ctrl.clusters, columns: () => columns, search: () => search });
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

	<RegexSearch id="drover-cluster-search" bind:value={search} />
	<TableViewControls {view} class="" />
	{#if ctrl.error}
		<Alert tone="danger" title={t('clusterError.loadFailed')} class="mb-4">{ctrl.error}{#snippet actions()}<Button variant="secondary" size="sm" onclick={ctrl.forceRefresh} disabled={ctrl.refreshing}>{t('clusterError.reload')}</Button>{/snippet}</Alert>
	{/if}

	{#if ctrl.loading || ctrl.clusters.length > 0 || !ctrl.error}
	{#if !ctrl.loading && ctrl.clusters.length > 0 && view.rows.length === 0}
		<p class="py-6 text-sm text-ink-2">{tc('table.noMatches')}</p>
	{:else}
	<DroverClusterGrid
		clusters={view.rows}
		loading={ctrl.loading}
		deletingId={ctrl.deleting}
		onSelect={panel.open}
		onDownloadKubeconfig={ctrl.downloadKubeconfig}
		onDelete={ctrl.deleteCluster}
		onOpenCreate={() => { ctrl.showModal = true; }}
		onOpenCreateIntent={prefetchCreateDependencies}
	/>
	{/if}
	{/if}
</PageShell>
