<script lang="ts">
  import {
    useLoadbalancerDetailController,
    provisioningColor,
  } from '$lib/stores/loadbalancerDetailController.svelte';
  import type { LbStatusNode } from '$lib/types/loadbalancer';
  import Self from './LoadBalancerErrorTree.svelte';

  interface Props {
    node?: LbStatusNode | null;
    depth?: number;
  }
  let { node = null, depth = 0 }: Props = $props();

  const s = useLoadbalancerDetailController();

  const labelByDepth: Record<number, string> = {
    1: '└ 리스너',
    2: '└ 풀',
    3: '└ 멤버',
  };
  const indentByDepth: Record<number, string> = {
    1: 'ml-4',
    2: 'ml-8',
    3: 'ml-12',
  };
  const labelWidthByDepth: Record<number, string> = {
    1: 'w-24',
    2: 'w-20',
    3: 'w-16',
  };
</script>

{#if depth === 0}
  <div class="bg-red-900/20 border border-red-800 rounded-lg p-5 mb-4">
    <h3 class="text-sm font-semibold text-red-400 mb-3">오류 상세 정보</h3>
    {#if node && s.lb}
      <div class="space-y-2 text-xs font-mono">
        <div class="flex items-center gap-3">
          <span class="text-ink-2 w-28 shrink-0">LB 상태</span>
          <span class="text-red-400">{node.provisioning_status ?? s.lb.status}</span>
          <span class="text-ink-3">{node.operating_status ?? s.lb.operating_status}</span>
        </div>
        {#if node.listeners}
          {#each node.listeners as listener}
            <Self node={listener} depth={1} />
            {#if listener.pools}
              {#each listener.pools as pool}
                <Self node={pool} depth={2} />
                {#if pool.members}
                  {#each pool.members as member}
                    <Self node={member} depth={3} />
                  {/each}
                {/if}
              {/each}
            {/if}
          {/each}
        {/if}
        {#if node.pools && (!node.listeners || node.listeners.length === 0)}
          {#each node.pools as pool}
            <Self node={pool} depth={2} />
            {#if pool.members}
              {#each pool.members as member}
                <Self node={member} depth={3} />
              {/each}
            {/if}
          {/each}
        {/if}
      </div>
    {:else}
      <p class="text-xs text-red-300">상태 트리를 불러오는 중이거나 조회할 수 없습니다.</p>
    {/if}
  </div>
{:else if node}
  <div class="{indentByDepth[depth]} flex items-center gap-3">
    <span class="text-ink-3 {labelWidthByDepth[depth]} shrink-0">{labelByDepth[depth]}</span>
    <span class="text-ink-2">{node.name || node.id?.slice(0, 12)}</span>
    <span class={provisioningColor(node.provisioning_status ?? '')}>{node.provisioning_status ?? '-'}</span>
  </div>
{/if}
