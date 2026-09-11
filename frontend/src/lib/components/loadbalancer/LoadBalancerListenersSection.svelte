<script lang="ts">
  import { useLoadbalancerDetailController } from '$lib/stores/loadbalancerDetailController.svelte';
  import ListenerAddForm from './ListenerAddForm.svelte';

  const s = useLoadbalancerDetailController();
</script>

<section class="bg-surface-base border border-line rounded-lg p-5 mb-4">
  <div class="flex items-center justify-between mb-4">
    <h3 class="font-semibold text-ink-0 text-sm">리스너 ({s.listeners.length})</h3>
    <button
      onclick={() => s.toggleAddListener()}
      class="text-action-warm hover:text-action-warm-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
    >+ 추가</button>
  </div>

  <ListenerAddForm />

  {#if s.listeners.length === 0}
    <p class="text-sm text-ink-3">리스너가 없습니다.</p>
  {:else}
    <div class="space-y-2">
      {#each s.listeners as l}
        <div class="flex items-center justify-between bg-surface-sunken/50 rounded-lg px-4 py-3">
          <div class="text-sm">
            <span class="text-ink-0 font-medium">{l.name || l.id.slice(0, 10)}</span>
            <span class="ml-2 text-xs text-action-warm bg-surface-selected/30 px-1.5 py-0.5 rounded">{l.protocol}:{l.protocol_port}</span>
            <span class="ml-2 text-xs {l.status === 'ACTIVE' ? 'text-green-400' : 'text-yellow-400'}">{l.status}</span>
          </div>
          <button
            onclick={() => s.deleteListener(l.id)}
            disabled={s.saving}
            class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 transition-colors"
          >삭제</button>
        </div>
      {/each}
    </div>
  {/if}
</section>
