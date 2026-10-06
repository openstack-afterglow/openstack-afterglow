<script lang="ts">
	import { t } from '$lib/i18n/ns/drover-pages';
	import { t as tc } from '$lib/i18n/ns/common';
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
	<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5" role="status" aria-label={tc('state.loadingNamed', { name: t('cluster.title') })} aria-busy="true">
		{#each Array(3) as _}
			<div class="motion-skeleton h-48 border border-line rounded-lg"></div>
		{/each}
	</div>
{:else if clusters.length === 0}
	<div class="text-center py-20 text-ink-2">
		<div class="text-5xl mb-4">☸</div>
		<p class="text-lg">{t('cluster.empty')}</p>
		<button onclick={onOpenCreate} onpointerenter={onOpenCreateIntent} onfocus={onOpenCreateIntent} class="text-warm-text hover:text-warm-text-hover text-sm mt-2 inline-block">
			{t('cluster.createFirst')}
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
