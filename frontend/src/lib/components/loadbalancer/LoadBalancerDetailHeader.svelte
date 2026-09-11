<script lang="ts">
  import { useLoadbalancerDetailController } from '$lib/stores/loadbalancerDetailController.svelte';
  import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';

  interface Props {
    ar: { active: boolean; intervalSeconds: number; intervalOptions: number[] };
    onClose?: () => void;
  }
  let { ar = $bindable(), onClose }: Props = $props();

  const s = useLoadbalancerDetailController();
</script>

<div class="flex items-center justify-between mb-4">
  <!-- 닫기 버튼은 SlidePanel 이 제공한다(`[data-slide-panel-close]`). 이 패널은 SlidePanel 안에서만 쓰인다. -->
  <AutoRefreshControl
    bind:active={ar.active}
    bind:intervalSeconds={ar.intervalSeconds}
    intervalOptions={ar.intervalOptions}
    refreshing={s.loading}
    onManualRefresh={() => s.fetchAll()}
  />
</div>

{#if s.lb}
  <DetailHeader
    title={s.lb.name || s.lb.id.slice(0, 12)}
    subtitle={s.lb.description ?? undefined}
    status={s.lb.status}
    secondaryStatus={s.lb.operating_status}
  >
    {#snippet meta()}
      {#if s.lb?.vip_address}
        <span class="text-xs text-ink-3 font-mono">VIP: {s.lb.vip_address}</span>
      {/if}
    {/snippet}
    {#snippet actions()}
      <button
        onclick={() => s.deleteLb()}
        disabled={s.saving}
        class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
      >{s.isProtected ? '강제 삭제' : '삭제'}</button>
    {/snippet}
  </DetailHeader>
{/if}
