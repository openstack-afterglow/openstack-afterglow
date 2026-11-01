<script lang="ts">
  import { t } from '$lib/i18n/ns/shared';
  import BklitChart from '$lib/components/charts/BklitChart.svelte';
  import type { ChartSpec, ChartSeries } from '$lib/components/charts/types';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';

  interface DataPoint {
    ts: number;
    total?: number;
    active?: number;
    shutoff?: number;
    error?: number;
    shelved?: number;
    in_use?: number;
    available?: number;
    [key: string]: number | null | undefined;
  }

  interface Props {
    data: DataPoint[];
    title: string;
    mainKey?: string;      // 주요 지표 키 (기본: 'total')
    extraKeys?: string[];  // 추가로 표시할 키 목록
    onRangeChange?: (range: string) => void;
    currentRange?: string;
  }

  let { data, title, mainKey = 'total', extraKeys = [], onRangeChange, currentRange = '7d' }: Props = $props();

  const RANGES = ['1d', '2d', '7d', '30d'];
  const RANGE_DAYS: Record<string, number> = { '1d': 1, '2d': 2, '7d': 7, '30d': 30 };

  const EXTRA_COLORS: Record<string, string> = {
    active:    'var(--color-state-success)',
    shutoff:   'var(--color-state-neutral)',
    error:     'var(--color-state-danger)',
    shelved:   'var(--color-chart-5)',
    in_use:    'var(--color-chart-1)',
    available: 'var(--color-chart-2)',
    other:     'var(--color-chart-4)',
    routers:   'var(--color-chart-3)',
    floating_ips_used: 'var(--color-chart-4)',
  };

  const SERIES_LABELS: Record<string, Parameters<typeof t>[0]> = {
    total: 'timeSeries.total', active: 'timeSeries.active', shutoff: 'timeSeries.shutoff', error: 'timeSeries.error',
    shelved: 'timeSeries.shelved', in_use: 'timeSeries.inUse', available: 'timeSeries.available',
    other: 'timeSeries.other', routers: 'timeSeries.routers', floating_ips_used: 'timeSeries.floatingIps',
  };
  function seriesLabel(key: string): string { return SERIES_LABELS[key] ? t(SERIES_LABELS[key]) : key; }


  function getVal(d: DataPoint, key: string): number | null {
    const value = d[key];
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
  }

  const points = $derived(data.length > 0 ? data : []);

  const maxVal = $derived(Math.max(1, ...[mainKey, ...extraKeys].flatMap(key =>
    points.map(point => getVal(point, key)).filter((value): value is number => value !== null)
  )));

  // Missing observations cannot become zero or a synthetic change in value.
  const latestVal = $derived(points.length > 0 ? getVal(points[points.length - 1], mainKey) : null);
  const prevVal = $derived(points.length > 1 ? getVal(points[points.length - 2], mainKey) : null);
  const delta = $derived(latestVal !== null && prevVal !== null ? latestVal - prevVal : null);

  const chartSeries = $derived<ChartSeries[]>([
    { key: mainKey, label: seriesLabel(mainKey), color: 'var(--color-chart-1)', area: true },
    ...extraKeys.filter(key => EXTRA_COLORS[key]).map(key => ({ key, label: seriesLabel(key), color: EXTRA_COLORS[key], dashed: true })),
  ]);
  const spec = $derived<ChartSpec>({
    kind: 'time-series',
    data: points.map(point => Object.fromEntries([
      ['timestamp', point.ts * 1000],
      ...chartSeries.map(series => [series.key, getVal(point, series.key)]),
    ])),
    xKey: 'timestamp', series: chartSeries, domain: [0, maxVal],
    formatValue: value => value.toLocaleString(intlLocale()),
  });
</script>

<div class="bg-surface-base border border-line rounded-xl p-5">
  <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
    <div class="flex items-center gap-3">
      <h3 class="text-sm font-semibold text-ink-2">{title}</h3>
      {#if points.length > 0}
        <span class="text-xl font-bold text-ink-0">{latestVal?.toLocaleString(intlLocale()) ?? '—'}</span>
        {#if delta !== null && delta > 0}
          <span class="text-xs text-state-success-text bg-state-success/10 px-1.5 py-0.5 rounded">+{delta}</span>
        {:else if delta !== null && delta < 0}
          <span class="text-xs text-state-danger-text bg-state-danger/10 px-1.5 py-0.5 rounded">{delta}</span>
        {/if}
      {/if}
    </div>
    <ToggleGroup value={currentRange} options={RANGES.map(range => ({ value: range, label: t('timeSeries.rangeDays', { days: RANGE_DAYS[range] }) }))} onchange={(range) => onRangeChange?.(range)} ariaLabel={title} size="sm" />
  </div>

  {#if points.length === 0}
    <div class="flex items-center justify-center h-24 text-ink-2 text-sm">
      {t('timeSeries.empty')}
    </div>
  {:else}
    <BklitChart {spec} height={180} label={title} />

    <!-- 범례 -->
    {#if extraKeys.length > 0}
      <div class="flex flex-wrap gap-3 mt-2">
        <div class="flex items-center gap-1">
          <div class="w-4 h-0.5 bg-chart-1"></div>
          <span class="text-[0.8125rem] text-ink-2">{seriesLabel(mainKey)}</span>
        </div>
        {#each extraKeys as key}
          {#if EXTRA_COLORS[key]}
            <div class="flex items-center gap-1">
              <div class="w-4 h-0.5" style="background:{EXTRA_COLORS[key]}; opacity:0.7; border-top: 1px dashed {EXTRA_COLORS[key]}"></div>
              <span class="text-[0.8125rem] text-ink-2">{seriesLabel(key)}</span>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  {/if}
</div>
