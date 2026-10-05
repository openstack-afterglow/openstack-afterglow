<script lang="ts">
	import { onMount } from 'svelte';
	import DashboardLayout from '../dashboard/+layout.svelte';
	import AdminLayout from '../admin/+layout.svelte';
	import ContainerTerminalPanel from '$lib/components/dashboard/containers/instances/id/ContainerTerminalPanel.svelte';
	import K3sCloudShellOverlay from '$lib/components/k3s/K3sCloudShellOverlay.svelte';
	import { createK3sClusterDetailController, provideK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';

	let { admin = false, kind = 'container' }: { admin?: boolean; kind?: 'container' | 'k3s' } = $props();
	const Layout = $derived(admin ? AdminLayout : DashboardLayout);
	const controller = createK3sClusterDetailController({
		clusterId: () => 'cluster',
		token: () => 'synthetic-token',
		projectId: () => 'project',
		adminMode: () => admin,
	});
	provideK3sClusterDetailController(controller);
	onMount(() => {
		if (kind === 'k3s') void controller.loadCluster();
	});
</script>

<Layout>
	{#if kind === 'container'}
		<ContainerTerminalPanel open={true} containerId="container" token="synthetic-token" projectId="project" />
	{:else if controller.cluster}
		<K3sCloudShellOverlay />
	{/if}
</Layout>
