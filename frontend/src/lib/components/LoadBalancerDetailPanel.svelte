<script lang="ts">
  import { auth } from '$lib/stores/auth';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import {
    createLoadbalancerDetailController,
    provideLoadbalancerDetailController,
  } from '$lib/stores/loadbalancerDetailController.svelte';
  import LoadBalancerDetailHeader from '$lib/components/loadbalancer/LoadBalancerDetailHeader.svelte';
  import LoadBalancerErrorTree from '$lib/components/loadbalancer/LoadBalancerErrorTree.svelte';
  import LoadBalancerListenersSection from '$lib/components/loadbalancer/LoadBalancerListenersSection.svelte';
  import LoadBalancerPoolsSection from '$lib/components/loadbalancer/LoadBalancerPoolsSection.svelte';

  interface Props {
    lbId: string;
    onClose?: () => void;
    onDeleted?: () => void;
  }

  let { lbId, onClose, onDeleted }: Props = $props();

  const s = createLoadbalancerDetailController({
    lbId: () => lbId,
    token: () => $auth.token ?? undefined,
    projectId: () => $auth.projectId ?? undefined,
    onDeleted: () => onDeleted?.(),
    onClose: () => onClose?.(),
  });
  provideLoadbalancerDetailController(s);

  const ar = createAutoRefresh(() => s.fetchAll(), {
    storageKey: 'lb-detail-panel',
    defaultActive: true,
    defaultInterval: 15,
    intervalOptions: [10, 15, 30, 60],
  });

  $effect(() => {
    if (lbId && $auth.projectId) s.fetchAll();
  });
</script>

<div class="p-6">
  <LoadBalancerDetailHeader {ar} {onClose} />

  {#if s.loading}
    <div class="space-y-4">
      {#each [1, 2, 3] as _}
        <div class="h-16 bg-surface-sunken rounded-lg animate-pulse"></div>
      {/each}
    </div>
  {:else if s.error}
    <div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{s.error}</div>
  {:else if s.lb}
    {#if s.isErrored}
      <LoadBalancerErrorTree node={s.statusTree} />
    {/if}
    <LoadBalancerListenersSection />
    <LoadBalancerPoolsSection />
  {/if}
</div>
