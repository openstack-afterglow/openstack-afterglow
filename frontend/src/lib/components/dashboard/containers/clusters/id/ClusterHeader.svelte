<script lang="ts">
  import { t } from '$lib/i18n/ns/containers-shell';
  import { goto } from '$app/navigation';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import type { Cluster } from '$lib/types/cluster';
  import type { AutoRefreshController } from '$lib/utils/autoRefresh.svelte';

  let {
    cluster,
    refreshing,
    ar,
    onManualRefresh,
    onDelete,
  }: {
    cluster: Cluster;
    refreshing: boolean;
    ar: AutoRefreshController;
    onManualRefresh: () => void;
    onDelete: () => void;
  } = $props();
</script>

<div class="flex items-center gap-3 mb-6">
  <button onclick={() => goto('/dashboard/containers/clusters')} class="text-ink-2 hover:text-ink-0 transition-colors text-sm">{t('clusters.header.backToList')}</button>
</div>

<div class="flex items-start justify-between mb-4">
  <div>
    <h1 class="text-2xl font-bold text-ink-0">{cluster.name}</h1>
    <p class="text-ink-2 text-sm mt-0.5 font-mono">{t('clusters.header.id', { id: cluster.id })}</p>
    {#if cluster.stack_id}
      <p class="text-ink-2 text-xs mt-0.5 font-mono">{t('clusters.header.stackId', { id: cluster.stack_id })}</p>
    {/if}
  </div>
  <div class="flex items-center gap-2">
    <AutoRefreshControl
      bind:active={ar.active}
      bind:intervalSeconds={ar.intervalSeconds}
      intervalOptions={ar.intervalOptions}
      {refreshing}
      {onManualRefresh}
    />
    <button onclick={onDelete} class="px-4 py-1.5 text-sm text-red-400 border border-red-800 hover:bg-red-900/30 rounded-lg transition-colors">{t('clusters.actions.delete')}</button>
  </div>
</div>
