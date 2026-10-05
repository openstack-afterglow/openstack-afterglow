<script lang="ts">
  import { t } from '$lib/i18n/ns/containers-shell';
  import type { StackResource } from '$lib/types/cluster';

  let { resources, isInProgress }: { resources: StackResource[]; isInProgress: boolean } = $props();

  const progressPct = $derived(
    resources.length === 0
      ? 0
      : Math.round(resources.filter(r => r.resource_status.endsWith('_COMPLETE')).length / resources.length * 100)
  );
</script>

{#if isInProgress && resources.length > 0}
  <div class="bg-surface-base border border-line rounded-xl p-4 mb-4">
    <div class="flex items-center justify-between mb-2 text-sm">
      <span class="text-ink-2">{t('clusters.progress.title')}</span>
      <span class="text-ink-0 font-medium">{t('clusters.progress.percentage', { percent: progressPct })}</span>
    </div>
    <div class="w-full bg-surface-sunken rounded-full h-2">
      <div class="bg-action-warm h-2 rounded-full transition-all duration-500" style="width:{progressPct}%"></div>
    </div>
    <div class="text-xs text-ink-2 mt-1">
      {t('clusters.progress.completed', { completed: resources.filter(r => r.resource_status.endsWith('_COMPLETE')).length, total: resources.length })}
    </div>
  </div>
{/if}
