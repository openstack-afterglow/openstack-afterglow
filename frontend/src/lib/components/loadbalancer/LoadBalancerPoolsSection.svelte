<script lang="ts">
  import { t } from '$lib/i18n/ns/network-resources';
  import { useLoadbalancerDetailController } from '$lib/stores/loadbalancerDetailController.svelte';
  import PoolAddForm from './PoolAddForm.svelte';
  import PoolMembersPanel from './PoolMembersPanel.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import { createPendingAction } from '$lib/components/network/pendingAction.svelte';
  import { CompactResourceCard, Button, StatusChip } from '$lib/components/ui';

  const s = useLoadbalancerDetailController();
  const pending = createPendingAction();
</script>

<section class="bg-surface-base border border-line rounded-lg p-5 mb-4">
  <div class="flex items-center justify-between mb-4">
    <h3 class="font-semibold text-ink-0 text-sm">{t('lb.pools.title', { count: s.pools.length })}</h3>
    {#if s.canMutate}
    <button
      onclick={() => s.toggleAddPool()}
      class="text-warm-text hover:text-warm-text-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
    >{t('lb.actions.addWithPlus')}</button>
    {/if}
  </div>

  <PoolAddForm />

  {#if s.pools.length === 0}
    <p class="text-sm text-ink-2">{t('lb.pools.empty')}</p>
  {:else}
    <div class="space-y-2">
      {#each s.pools as pool}
        {@const deletingPool = pending.isActive(`delete:${pool.id}`, s.saving)}
        <div>
          <CompactResourceCard selected={s.selectedPoolId === pool.id}>
            <div class="flex items-center gap-2"><strong class="min-w-0 flex-1 break-all">{pool.name || pool.id.slice(0, 10)}</strong><StatusChip status={pool.status} /></div>
            <p class="text-xs text-ink-2">{pool.protocol} · {t('lb.algorithm.label', { algorithm: pool.lb_algorithm })}</p>
            {#snippet details()}<p class="font-mono break-all">ID: {pool.id}</p>{/snippet}
            {#snippet actions()}
              <Button size="sm" variant="secondary" onclick={() => s.togglePool(pool.id)} ariaExpanded={s.selectedPoolId === pool.id}>{s.selectedPoolId === pool.id ? t('lb.pools.collapse') : t('lb.pools.members')}</Button>
              {#if s.canMutate}
              <Button variant="danger-outline" size="sm" onclick={() => pending.run(`delete:${pool.id}`, () => s.deletePool(pool.id))} disabled={s.saving} ariaBusy={deletingPool}>{#if deletingPool}<ActivityIndicator size="xs" tone="danger" />{/if}{deletingPool ? t('lb.actions.deleting') : t('lb.actions.delete')}</Button>
              {/if}
            {/snippet}
          </CompactResourceCard>
          {#if s.selectedPoolId === pool.id}
            <PoolMembersPanel poolId={pool.id} />
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</section>
