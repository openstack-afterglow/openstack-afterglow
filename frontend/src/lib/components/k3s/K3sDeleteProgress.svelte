<script lang="ts">
  import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';

  const s = useK3sClusterDetailController();
</script>

<div class="mb-4 bg-surface-base border border-line-2 rounded-xl p-4">
  <div class="flex items-center justify-between mb-2">
    <span class="text-sm text-ink-2">{s.deleteProgress!.msg}</span>
    <span class="text-xs text-ink-3">{s.deleteProgress!.pct}%</span>
  </div>
  <div class="bg-surface-sunken rounded-full h-1.5">
    <div class="bg-red-500 h-1.5 rounded-full transition-all duration-500" style="width: {s.deleteProgress!.pct}%"></div>
  </div>
  {#if s.deleteProgress!.error}
    <p class="text-xs text-red-400 mt-2">{s.deleteProgress!.error}</p>
  {/if}
</div>
