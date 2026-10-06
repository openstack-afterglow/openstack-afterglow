<script lang="ts">
  import { t } from '$lib/i18n/ns/network-resources';
  import { useLoadbalancerDetailController } from '$lib/stores/loadbalancerDetailController.svelte';
  import DetailHeader from '$lib/components/ui/DetailHeader.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import { createPendingAction } from '$lib/components/network/pendingAction.svelte';

  interface Props {
    ar: { active: boolean; intervalSeconds: number; intervalOptions: number[] };
    onClose?: () => void;
  }
  let { ar = $bindable(), onClose }: Props = $props();

  const s = useLoadbalancerDetailController();
  const pending = createPendingAction();
  const deletingLb = $derived(pending.isActive('delete', s.saving));
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
        <span class="text-xs text-ink-2 font-mono">VIP: {s.lb.vip_address}</span>
      {/if}
    {/snippet}
    {#snippet actions()}
      <button
        onclick={() => pending.run('delete', () => s.deleteLb())}
        disabled={s.saving}
        aria-busy={deletingLb}
        class="inline-flex items-center gap-1.5 text-red-400 hover:text-red-300 disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
      >{#if deletingLb}<ActivityIndicator size="xs" tone="danger" />{/if}{deletingLb ? t('lb.actions.deleting') : s.isProtected ? t('lb.actions.forceDelete') : t('lb.actions.delete')}</button>
    {/snippet}
  </DetailHeader>
{/if}
