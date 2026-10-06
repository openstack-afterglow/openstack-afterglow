<script lang="ts">
  import { t } from '$lib/i18n/ns/network-resources';
  import { useLoadbalancerDetailController } from '$lib/stores/loadbalancerDetailController.svelte';
  import ListenerAddForm from './ListenerAddForm.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import { createPendingAction } from '$lib/components/network/pendingAction.svelte';

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
        <div class="flex items-center justify-between bg-surface-sunken/50 rounded-lg px-4 py-3">
          <div class="text-sm">
            <span class="text-ink-0 font-medium">{l.name || l.id.slice(0, 10)}</span>
            <span class="ml-2 text-xs text-warm-text bg-surface-selected/30 px-1.5 py-0.5 rounded">{l.protocol}:{l.protocol_port}</span>
            <span class="ml-2 text-xs {l.status === 'ACTIVE' ? 'text-green-400' : 'text-yellow-400'}">{l.status}</span>
          </div>
          <button
            onclick={() => pending.run(`delete:${l.id}`, () => s.deleteListener(l.id))}
            disabled={s.saving}
            aria-busy={deletingListener}
            class="inline-flex items-center gap-1.5 text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 transition-colors"
          >{#if deletingListener}<ActivityIndicator size="xs" tone="danger" />{/if}{deletingListener ? t('lb.actions.deleting') : t('lb.actions.delete')}</button>
        </div>
      {/each}
    </div>
  {/if}
</section>
