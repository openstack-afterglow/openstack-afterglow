<script lang="ts">
  import { t } from '$lib/i18n/ns/network-resources';
  import { useLoadbalancerDetailController } from '$lib/stores/loadbalancerDetailController.svelte';
  import ListenerAddForm from './ListenerAddForm.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import { createPendingAction } from '$lib/components/network/pendingAction.svelte';
  import { CompactResourceCard, Button, StatusChip } from '$lib/components/ui';

  const s = useLoadbalancerDetailController();
  const pending = createPendingAction();
</script>

<section class="bg-surface-base border border-line rounded-lg p-5 mb-4">
  <div class="flex items-center justify-between mb-4">
    <h3 class="font-semibold text-ink-0 text-sm">{t('lb.listeners.title', { count: s.listeners.length })}</h3>
    <button
      onclick={() => s.toggleAddListener()}
      class="text-warm-text hover:text-warm-text-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
    >{t('lb.actions.addWithPlus')}</button>
  </div>

  <ListenerAddForm />

  {#if s.listeners.length === 0}
    <p class="text-sm text-ink-2">{t('lb.listeners.empty')}</p>
  {:else}
    <div class="space-y-2">
      {#each s.listeners as l}
        {@const deletingListener = pending.isActive(`delete:${l.id}`, s.saving)}
        <CompactResourceCard>
          <div class="flex items-center gap-2"><strong class="min-w-0 flex-1 break-all">{l.name || l.id.slice(0, 10)}</strong><StatusChip status={l.status} /></div>
          <p class="font-mono text-xs text-ink-2">{l.protocol}:{l.protocol_port}</p>
          {#snippet details()}<p class="font-mono break-all">ID: {l.id}</p>{/snippet}
          {#snippet actions()}<Button variant="danger-outline" size="sm" onclick={() => pending.run(`delete:${l.id}`, () => s.deleteListener(l.id))} disabled={s.saving} ariaBusy={deletingListener}>{#if deletingListener}<ActivityIndicator size="xs" tone="danger" />{/if}{deletingListener ? t('lb.actions.deleting') : t('lb.actions.delete')}</Button>{/snippet}
        </CompactResourceCard>
      {/each}
    </div>
  {/if}
</section>
