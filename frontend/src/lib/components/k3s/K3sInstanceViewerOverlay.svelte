<script lang="ts">
  import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
  import InstanceDetailPanel from '$lib/components/InstanceDetailPanel.svelte';

  const s = useK3sClusterDetailController();
</script>

<div class="absolute inset-0 z-10 bg-surface-canvas overflow-y-auto">
  <div class="px-4 pt-4">
    <button
      onclick={() => s.clearViewingInstance()}
      class="text-ink-2 hover:text-ink-0 text-sm transition-colors mb-2">
      ← 클러스터 상세
    </button>
  </div>
  <InstanceDetailPanel instanceId={s.viewingInstanceId!} onClose={() => s.clearViewingInstance()} />
</div>
