<script lang="ts">
	import K3sClusterCard from '$lib/components/dashboard/drover/K3sClusterCard.svelte';
	import type { K3sCluster } from '$lib/types/k3s';

	let {
		clusters,
		loading,
		deletingId,
		onSelect,
		onDownloadKubeconfig,
		onDelete,
		onOpenCreate,
		onOpenCreateIntent,
	}: {
		clusters: K3sCluster[];
		loading: boolean;
		deletingId: string | null;
		onSelect: (id: string) => void;
		onDownloadKubeconfig: (id: string, name: string) => void;
		onDelete: (id: string, name: string) => void;
		onOpenCreate: () => void;
		onOpenCreateIntent?: () => void;
	} = $props();
</script>

{#if loading}
	<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
		{#each Array(3) as _}
			<div class="animate-pulse h-48 bg-surface-base border border-line rounded-lg"></div>
		{/each}
	</div>
{:else if clusters.length === 0}
	<div class="text-center py-20 text-ink-3">
		<div class="text-5xl mb-4">☸</div>
		<p class="text-lg">Drover 클러스터가 없습니다</p>
		<button onclick={onOpenCreate} onpointerenter={onOpenCreateIntent} onfocus={onOpenCreateIntent} class="text-action-warm hover:text-action-warm-hover text-sm mt-2 inline-block">
			첫 클러스터를 생성하세요 →
		</button>
	</div>
{:else}
	<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
		{#each clusters as cluster (cluster.id)}
			<K3sClusterCard
				{cluster}
				deleting={deletingId === cluster.id}
				{onSelect}
				{onDownloadKubeconfig}
				{onDelete}
			/>
		{/each}
	</div>
{/if}
