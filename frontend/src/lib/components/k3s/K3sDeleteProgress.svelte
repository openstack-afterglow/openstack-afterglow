<script lang="ts">
  import { t } from '$lib/i18n/ns/drover';
  import ProgressTrack from '$lib/components/ui/ProgressTrack.svelte';
  import AnimatedNumber from '$lib/components/ui/AnimatedNumber.svelte';
  import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';

  const s = useK3sClusterDetailController();
</script>

<div class="mb-4 bg-surface-base border border-line-2 rounded-xl p-4">
  <div class="flex items-center justify-between mb-2">
    <span class="text-sm text-ink-2">{s.deleteProgress!.msg}</span>
    <span class="text-xs text-ink-2"><AnimatedNumber value={s.deleteProgress!.pct} />%</span>
  </div>
  <ProgressTrack value={s.deleteProgress!.pct} label={t('deleteProgress.label')} tone="danger" active={s.deleting && !s.deleteProgress!.error} />
  {#if s.deleteProgress!.error}
    <p class="text-xs text-red-400 mt-2">{s.deleteProgress!.error}</p>
  {/if}
</div>
