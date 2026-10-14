<script lang="ts">
  import { t } from '$lib/i18n/ns/palimpsest-admin';
  import BklitChart from '$lib/components/charts/BklitChart.svelte';
  import type { ChartSpec } from '$lib/components/charts/types';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  interface TsPoint {
    ts: number;
    [key: string]: number | undefined;
  }

  interface Props {
    data: TsPoint[];
    title?: string;
    currentRange?: string;
    onRangeChange?: (range: string) => void;
  }

  let {
    data,
    title,
    currentRange = '7d',
    onRangeChange
  }: Props = $props();

  const shownTitle = $derived(title ?? t('chart.title'));

  const RANGES = ['1d', '2d', '7d', '30d'];
  const RANGE_DAYS: Record<string, number> = { '1d': 1, '2d': 2, '7d': 7, '30d': 30 };


  // 최신 스냅샷에서 사용 키 추출 (lib: / layer: 접두어 제거)
  const latestPoint = $derived(data.length > 0 ? data[data.length - 1] : null);

  const topKeys = $derived.by(() => {
    if (!latestPoint) return [] as { key: string; label: string }[];
    const entries = Object.entries(latestPoint)
      .filter(([key, value]) => key !== 'ts' && key.includes(':') && typeof value === 'number' && Number.isFinite(value))
      .sort(([, a], [, b]) => b! - a!)
      .slice(0, 8);
    return entries.map(([key]) => {
      const name = key.replace(/^(lib|layer):/, '');
      const duplicate = entries.some(([peer]) => peer !== key && peer.replace(/^(lib|layer):/, '') === name);
      return { key, label: duplicate ? key : name };
    });
  });

  // 최신 사용량 합계
  const totalUsage = $derived(
    topKeys.reduce((sum, { key }) => sum + ((latestPoint?.[key] as number) ?? 0), 0)
  );
  const spec = $derived<ChartSpec>({
    kind: 'bar',
    data: topKeys.map(({ key, label }) => ({ name: label, usage: latestPoint?.[key] ?? null })),
    xKey: 'name',
    series: [{ key: 'usage', label: t('chart.activeVm'), color: 'var(--color-chart-1)' }],
    orientation: 'horizontal', domain: [0, totalUsage || 1],
    formatValue: value => value.toLocaleString(intlLocale()),
  });
</script>

<div class="bg-surface-base border border-line rounded-xl p-5">
  <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
    <div class="flex items-center gap-3">
      <h3 class="text-sm font-semibold text-ink-2">{shownTitle}</h3>
      {#if totalUsage > 0}
        <span class="text-xl font-bold text-ink-0">{totalUsage}</span>
        <span class="text-xs text-ink-2">{t('chart.activeVm')}</span>
      {/if}
    </div>
    <div class="flex gap-1">
      {#each RANGES as r}
        <button
          type="button"
          aria-pressed={currentRange === r}
          onclick={() => onRangeChange?.(r)}
          class="min-h-11 md:min-h-8 text-xs px-2 py-0.5 rounded transition-colors focus-visible:outline focus-visible:outline-accent {currentRange === r ? 'bg-action-warm text-[var(--color-action-on-warm)]' : 'text-ink-2 hover:text-ink-0'}"
        >{t('chart.days', { count: RANGE_DAYS[r] })}</button>
      {/each}
    </div>
  </div>

  {#if data.length === 0 || topKeys.length === 0}
    <div class="flex items-center justify-center h-24 text-ink-2 text-sm">
      {t('chart.empty')}
    </div>
  {:else}
    <BklitChart {spec} height={Math.max(120, topKeys.length * 32 + 16)} label={shownTitle} />
  {/if}
</div>
