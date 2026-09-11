<script lang="ts">
  import { useK3sClusterDetailController, healthColor } from '$lib/stores/k3sClusterDetailController.svelte';
  import Button from '$lib/components/ui/Button.svelte';

  const s = useK3sClusterDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
  <div class="flex items-center justify-between mb-3">
    <h3 class="text-xs text-ink-3 uppercase tracking-wide">노드 현황</h3>
    {#if s.health}
      <div class="flex items-center gap-2">
        <span class="px-2 py-0.5 rounded border text-xs font-medium {healthColor[s.health.status] ?? 'text-ink-3 bg-surface-sunken border-line-2'}">
          {s.health.status}
        </span>
        <span class="text-xs text-ink-3">{new Date(s.health.checked_at).toLocaleTimeString('ko-KR')}</span>
      </div>
    {:else}
      <span class="text-xs text-ink-3">미확인</span>
    {/if}
  </div>

  {#if s.health && s.health.nodes.length > 0}
    <div class="space-y-2">
      {#each s.health.nodes as node}
        <div class="flex items-center justify-between py-1.5 border-b border-line last:border-0">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full {node.ready ? 'bg-green-400' : 'bg-red-400'}"></span>
            <span class="text-xs text-ink-2 font-mono">{node.name}</span>
            <span class="text-xs px-1.5 py-0.5 rounded {node.role === 'server' ? 'bg-purple-900/40 text-purple-400 border border-purple-800' : 'bg-surface-selected/40 text-action-warm border border-action-warm'}">
              {node.role}
            </span>
          </div>
          <div class="text-right">
            <span class="text-xs {node.ready ? 'text-green-400' : 'text-red-400'}">
              {node.ready ? 'Ready' : 'NotReady'}
            </span>
            {#if node.kubelet_version}
              <div class="text-xs text-ink-3 font-mono">{node.kubelet_version}</div>
            {/if}
          </div>
        </div>
      {/each}
    </div>

    {#if s.cluster!.status === 'ACTIVE'}
      <div class="flex items-center gap-1.5 mt-3 pt-3 border-t border-line">
        <span class="text-ink-2 text-xs">에이전트:</span>
        <button
          onclick={() => s.decrementScale()}
          class="w-5 h-5 flex items-center justify-center bg-surface-selected hover:bg-surface-selected text-ink-0 rounded text-xs transition-colors">−</button>
        <span class="text-ink-2 text-xs min-w-[2rem] text-center">
          {s.cluster!.agent_vm_ids.length} / {s.scalingTarget ?? s.cluster!.agent_count}
        </span>
        <button
          onclick={() => s.incrementScale()}
          class="w-5 h-5 flex items-center justify-center bg-surface-selected hover:bg-surface-selected text-ink-0 rounded text-xs transition-colors">+</button>
        {#if s.scalingTarget !== null && s.scalingTarget !== s.cluster!.agent_count}
          <Button onclick={() => s.applyScale()} disabled={s.scaling} size="sm" class="ml-1">
            {s.scaling ? '...' : '적용'}
          </Button>
        {/if}
      </div>
      {#if s.scaleError}
        <p class="text-red-400 text-xs mt-1">{s.scaleError}</p>
      {/if}
    {/if}
  {:else}
    <dl class="space-y-1.5 text-sm">
      <div class="flex justify-between">
        <dt class="text-ink-2 text-xs">서버(control plane)</dt>
        <dd class="text-ink-2 text-xs">1</dd>
      </div>
      <div class="flex justify-between items-center">
        <dt class="text-ink-2 text-xs">에이전트(worker)</dt>
        <dd class="flex items-center gap-1.5">
          {#if s.cluster!.status === 'ACTIVE'}
            <button
              onclick={() => s.decrementScale()}
              class="w-5 h-5 flex items-center justify-center bg-surface-selected hover:bg-surface-selected text-ink-0 rounded text-xs transition-colors">−</button>
            <span class="text-ink-2 text-xs min-w-[2rem] text-center">
              {s.cluster!.agent_vm_ids.length} / {s.scalingTarget ?? s.cluster!.agent_count}
            </span>
            <button
              onclick={() => s.incrementScale()}
              class="w-5 h-5 flex items-center justify-center bg-surface-selected hover:bg-surface-selected text-ink-0 rounded text-xs transition-colors">+</button>
            {#if s.scalingTarget !== null && s.scalingTarget !== s.cluster!.agent_count}
              <Button onclick={() => s.applyScale()} disabled={s.scaling} size="sm" class="ml-1">
                {s.scaling ? '...' : '적용'}
              </Button>
            {/if}
          {:else}
            <span class="text-ink-2 text-xs">{s.cluster!.agent_vm_ids.length} / {s.cluster!.agent_count} 생성됨</span>
          {/if}
        </dd>
      </div>
      <div class="flex justify-between">
        <dt class="text-ink-2 text-xs">생성일</dt>
        <dd class="text-ink-2 text-xs">{s.cluster!.created_at ? s.cluster!.created_at.split('T')[0] : '-'}</dd>
      </div>
      <div class="flex justify-between">
        <dt class="text-ink-2 text-xs">마지막 업데이트</dt>
        <dd class="text-ink-2 text-xs">{s.cluster!.updated_at ? s.cluster!.updated_at.split('T')[0] : '-'}</dd>
      </div>
    </dl>
    {#if s.health === null && s.cluster!.status === 'ACTIVE'}
      <p class="text-xs text-ink-3 mt-2">헬스 데이터 로드 중...</p>
    {/if}
    {#if s.scaleError}
      <p class="text-red-400 text-xs mt-2">{s.scaleError}</p>
    {/if}
  {/if}
</div>
