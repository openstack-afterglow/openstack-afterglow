<script lang="ts">
  import { useLoadbalancerDetailController } from '$lib/stores/loadbalancerDetailController.svelte';
  import PoolAddForm from './PoolAddForm.svelte';
  import PoolMembersPanel from './PoolMembersPanel.svelte';

  const s = useLoadbalancerDetailController();
</script>

<section class="bg-surface-base border border-line rounded-lg p-5 mb-4">
  <div class="flex items-center justify-between mb-4">
    <h3 class="font-semibold text-ink-0 text-sm">풀 ({s.pools.length})</h3>
    <button
      onclick={() => s.toggleAddPool()}
      class="text-action-warm hover:text-action-warm-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
    >+ 추가</button>
  </div>

  <PoolAddForm />

  {#if s.pools.length === 0}
    <p class="text-sm text-ink-3">풀이 없습니다.</p>
  {:else}
    <div class="space-y-2">
      {#each s.pools as pool}
        <div>
          <div
            onclick={() => s.togglePool(pool.id)}
            onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && s.togglePool(pool.id)}
            role="button"
            tabindex="0"
            class="flex items-center justify-between bg-surface-sunken/50 hover:bg-surface-sunken rounded-lg px-4 py-3 cursor-pointer transition-colors {s.selectedPoolId === pool.id ? 'border border-action-warm' : ''}"
          >
            <div class="text-sm">
              <span class="text-ink-0 font-medium">{pool.name || pool.id.slice(0, 10)}</span>
              <span class="ml-2 text-xs text-purple-300 bg-purple-900/30 px-1.5 py-0.5 rounded">{pool.protocol}</span>
              <span class="ml-2 text-xs text-ink-3">{pool.lb_algorithm}</span>
              <span class="ml-2 text-xs {pool.status === 'ACTIVE' ? 'text-green-400' : 'text-yellow-400'}">{pool.status}</span>
            </div>
            <div class="flex gap-2">
              <span class="text-xs text-ink-3">{s.selectedPoolId === pool.id ? '▲ 접기' : '▼ 멤버'}</span>
              <button
                onclick={(e) => { e.stopPropagation(); s.deletePool(pool.id); }}
                disabled={s.saving}
                class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 transition-colors"
              >삭제</button>
            </div>
          </div>
          {#if s.selectedPoolId === pool.id}
            <PoolMembersPanel poolId={pool.id} />
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</section>
