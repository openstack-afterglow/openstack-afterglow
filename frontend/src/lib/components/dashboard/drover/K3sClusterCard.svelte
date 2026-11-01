<script lang="ts">
	import { t } from '$lib/i18n/ns/drover-pages';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import AnimatedNumber from '$lib/components/ui/AnimatedNumber.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ClusterFailure from './ClusterFailure.svelte';
	import type { K3sCluster } from '$lib/types/k3s';
	import { k3sPermissions } from '$lib/stores/k3sPermissions';

	let {
		cluster,
		deleting,
		onSelect,
		onDownloadKubeconfig,
		onDelete,
	}: {
		cluster: K3sCluster;
		deleting: boolean;
		onSelect: (id: string) => void;
		onDownloadKubeconfig: (id: string, name: string) => void;
		onDelete: (id: string, name: string) => void;
	} = $props();

	const canDownload = $derived($k3sPermissions.credentials && cluster.status === 'ACTIVE');
	const canDelete = $derived($k3sPermissions.administerClusters && !deleting && cluster.status !== 'DELETING');
</script>

<div
	class="bg-surface-base border border-line rounded-lg p-5 transition-colors {cluster.deleted_at ? 'opacity-50' : 'cursor-pointer hover:border-line-2'}"
	onclick={() => !cluster.deleted_at && onSelect(cluster.id)}
	role="button"
	aria-disabled={cluster.deleted_at ? 'true' : 'false'}
	tabindex={cluster.deleted_at ? -1 : 0}
	onkeydown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !cluster.deleted_at) { e.preventDefault(); onSelect(cluster.id); } }}
>
	<!-- Header -->
	<div class="flex items-center gap-2.5 mb-3">
		<div class="cluster-badge w-[34px] h-[34px] rounded-[9px] flex items-center justify-center shrink-0">
			<svg xmlns="http://www.w3.org/2000/svg" class="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
				<path stroke-linejoin="round" stroke-width="1.8" d="M12 2.4 19.8 6.1 21.7 14.3 16.3 20.8H7.7l-5.4-6.5 1.9-8.2L12 2.4Z"/><circle cx="12" cy="12" r="4.1" stroke-width="1.8"/><circle cx="12" cy="12" r="0.85" fill="currentColor" stroke="none"/><path stroke-linecap="round" stroke-width="1.8" d="M12 9.8V6.2M13.72 10.63l2.81-2.25M14.14 12.49l3.51.8M12.95 13.98l1.57 3.25M11.05 13.98l-1.57 3.25M9.86 12.49l-3.51.8M10.28 10.63 7.47 8.38"/>
			</svg>
		</div>
		<div class="flex-1 min-w-0">
			<div class="text-ink-0 font-semibold text-sm truncate {cluster.deleted_at ? 'line-through text-ink-2' : ''}">
				{cluster.name}
			</div>
			<div class="text-xs text-ink-2 font-mono mt-0.5">
				{cluster.k3s_version || 'k3s'}
			</div>
		</div>
		<StatusChip status={cluster.status} />
	</div>

	<!-- Info grid -->
	<div class="grid grid-cols-2 gap-2 text-xs mb-3.5">
		<div>
			<div class="text-xs uppercase tracking-wider font-medium text-ink-2">{t('clusterCard.nodes')}</div>
			<div class="text-ink-1 mt-0.5"><AnimatedNumber value={cluster.agent_count + 1} /> (1+{cluster.agent_count})</div>
		</div>
		<div>
			<div class="text-xs uppercase tracking-wider font-medium text-ink-2">API</div>
			<div class="text-ink-1 mt-0.5 font-mono text-xs truncate">{cluster.api_address || '—'}</div>
		</div>
		{#if cluster.deleted_at}
			<div class="col-span-2">
				<div class="text-xs uppercase tracking-wider font-medium text-ink-2">{t('clusterCard.deleted')}</div>
				<div class="text-ink-2 mt-0.5 text-xs">{cluster.deleted_at.replace('T', ' ').slice(0, 16)}</div>
			</div>
		{:else if cluster.status_reason}
			<div class="col-span-2">
				{#if cluster.status === 'ERROR' || cluster.status === 'FAILED'}<ClusterFailure reason={cluster.status_reason} />{:else}<p class="break-words text-[0.8125rem] text-ink-2">{cluster.status_reason}</p>{/if}
			</div>
		{/if}
	</div>

	<!-- Actions -->
	<div class="flex gap-1.5" role="none" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
		<Button variant="secondary" size="sm" class="flex-1" onclick={() => canDownload && onDownloadKubeconfig(cluster.id, cluster.name)} disabled={!canDownload}>kubeconfig</Button>
		<Button variant="secondary" size="sm" onclick={() => !cluster.deleted_at && onSelect(cluster.id)} disabled={!!cluster.deleted_at}>{t('actions.details')}</Button>
		{#if !cluster.deleted_at}
			<Button variant="danger-outline" size="sm" onclick={() => canDelete && onDelete(cluster.id, cluster.name)} disabled={!canDelete}>
				{#if deleting}<LoadingState variant="control" label={t('state.deleting')} />{:else}{t('actions.delete')}{/if}
			</Button>
		{/if}
	</div>
</div>

<style>
	.cluster-badge {
		background: var(--color-surface-sunken);
		border: 1px solid var(--color-line);
		color: var(--color-ink-2);
	}
</style>
