<script lang="ts">
  import { t } from '$lib/i18n/ns/containers-shell';
  import type { StackResource } from '$lib/types/cluster';
  import { AnimatedNumber, ProgressTrack } from '$lib/components/ui';

  let { resources, isInProgress }: { resources: StackResource[]; isInProgress: boolean } = $props();

  const completedCount = $derived(resources.filter(r => r.resource_status.endsWith('_COMPLETE')).length);
  const progressPct = $derived(resources.length === 0 ? 0 : Math.round(completedCount / resources.length * 100));
</script>

{#if isInProgress && resources.length > 0}
  <div class="bg-surface-base border border-line rounded-xl p-4 mb-4">
    <div class="flex items-center justify-between mb-2 text-sm">
      <span class="text-ink-2">{t('clusters.progress.title')}</span>
      <span class="text-ink-0 font-medium"><AnimatedNumber value={progressPct} format={(value) => t('clusters.progress.percentage', { percent: Math.round(value) })} /></span>
    </div>
    <ProgressTrack
      value={progressPct}
      label={t('clusters.progress.title')}
      active
      valueText={t('clusters.progress.completed', { completed: completedCount, total: resources.length })}
    />
    <div class="text-xs text-ink-2 mt-1">
      {t('clusters.progress.completed', { completed: completedCount, total: resources.length })}
    </div>
  </div>
{/if}
