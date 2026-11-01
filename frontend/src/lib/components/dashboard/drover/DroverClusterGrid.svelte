<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/drover-pages';
	import { t as tc } from '$lib/i18n/ns/common';
	import K3sClusterCard from '$lib/components/dashboard/drover/K3sClusterCard.svelte';
	import { Button, EmptyState } from '$lib/components/ui';
	import type { K3sCluster } from '$lib/types/k3s';
	import { k3sPermissions } from '$lib/stores/k3sPermissions';

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
	<LoadingState variant="surface" label={tc('state.loadingNamed', { name: t('cluster.title') })} />
{:else if clusters.length === 0}
	<EmptyState headline={t('cluster.empty')}>
		{#snippet cta()}<Button variant="primary" disabled={!$k3sPermissions.editClusters} onclick={onOpenCreate} onintent={onOpenCreateIntent}>{t('cluster.createFirst')}</Button>{/snippet}
	</EmptyState>
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
