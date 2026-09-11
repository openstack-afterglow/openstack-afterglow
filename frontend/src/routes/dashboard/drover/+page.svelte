<script lang="ts">
	import { untrack } from 'svelte';
	import { auth, authReady } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import { createK3sProgress } from '$lib/stores/k3sProgress.svelte';
	import { createK3sClusterListController } from '$lib/stores/k3sClusterListController.svelte';
	import K3sClusterDetailPanel from '$lib/components/K3sClusterDetailPanel.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createDroverClusterPanel } from '$lib/utils/droverClusterPanel.svelte';
	import { K3S_CREATE_STEPS, K3S_DELETE_STEPS } from '$lib/components/k3sSteps';
	import K3sCreateClusterModal from '$lib/components/dashboard/drover/K3sCreateClusterModal.svelte';
	import K3sProgressModal from '$lib/components/dashboard/drover/K3sProgressModal.svelte';
	import DroverHeader from '$lib/components/dashboard/drover/DroverHeader.svelte';
	import DroverClusterGrid from '$lib/components/dashboard/drover/DroverClusterGrid.svelte';

	const progress = createK3sProgress();
	const activeSteps = $derived(progress.mode === 'delete' ? K3S_DELETE_STEPS : K3S_CREATE_STEPS);
	const panel = createDroverClusterPanel();

	const ctrl = createK3sClusterListController({
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
		progress,
	});

	function prefetchCreateDependencies() {
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		void api.prefetch('/api/v1/flavors', token, projectId);
		void api.prefetch('/api/v1/networks', token, projectId);
		void api.prefetch('/api/v1/keypairs', token, projectId);
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

{#if progress.visible}
	<K3sProgressModal
		controller={progress}
		activeSteps={activeSteps}
		onClose={() => { progress.visible = false; }}
		onViewCluster={(id) => { progress.visible = false; panel.open(id); }}
	/>
{/if}

{#if panel.selectedClusterId}
	<SlidePanel onClose={panel.close} ariaLabel="Drover 클러스터 상세">
		<K3sClusterDetailPanel clusterId={panel.selectedClusterId} onClose={panel.close} />
	</SlidePanel>
{/if}

<div class="p-4 md:p-8">
	<DroverHeader
		bind:showDeleted={ctrl.showDeleted}
		{ar}
		refreshing={ctrl.refreshing || ctrl.loading}
		onForceRefresh={ctrl.forceRefresh}
		onOpenCreate={() => { ctrl.showModal = true; }}
		onToggleDeleted={ctrl.toggleDeleted}
		onOpenCreateIntent={prefetchCreateDependencies}
	/>

	<p class="text-sm text-ink-3 mb-6">Nova VM + cloud-init으로 k3s Kubernetes 클러스터를 프로비저닝합니다.</p>

	{#if ctrl.error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{ctrl.error}</div>
	{/if}

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
</div>
