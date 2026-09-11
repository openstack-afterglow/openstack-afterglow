<script lang="ts">
  import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';

  const s = useK3sClusterDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
  <h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">VM 목록</h3>
  <div class="space-y-2">
    {#if s.cluster!.server_vm_id}
      <div class="flex items-center justify-between py-2 border-b border-line">
        <div class="flex items-center gap-2">
          <span class="text-xs bg-purple-900/40 text-purple-400 border border-purple-800 rounded px-1.5 py-0.5">서버</span>
          <span class="text-xs text-ink-2 font-mono">{s.cluster!.server_vm_id.slice(0, 12)}...</span>
        </div>
        <button
          onclick={() => s.setViewingInstance(s.cluster!.server_vm_id)}
          class="text-xs text-action-warm hover:text-action-warm-hover transition-colors">
          인스턴스 보기 →
        </button>
      </div>
    {/if}
    {#each s.cluster!.agent_vm_ids as vmId, i}
      <div class="flex items-center justify-between py-2 {i < s.cluster!.agent_vm_ids.length - 1 ? 'border-b border-line' : ''}">
        <div class="flex items-center gap-2">
          <span class="text-xs bg-surface-selected/40 text-action-warm border border-action-warm rounded px-1.5 py-0.5">에이전트 {i + 1}</span>
          <span class="text-xs text-ink-2 font-mono">{vmId.slice(0, 12)}...</span>
        </div>
        <button
          onclick={() => s.setViewingInstance(vmId)}
          class="text-xs text-action-warm hover:text-action-warm-hover transition-colors">
          인스턴스 보기 →
        </button>
      </div>
    {/each}
    {#if !s.cluster!.server_vm_id && s.cluster!.agent_vm_ids.length === 0}
      <p class="text-xs text-ink-3 py-2">VM 정보가 없습니다.</p>
    {/if}
  </div>
</div>
