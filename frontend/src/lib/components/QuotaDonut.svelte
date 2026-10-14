<script lang="ts">
  import { t } from '$lib/i18n/ns/shared';
  import BklitChart from '$lib/components/charts/BklitChart.svelte';
  import { TONE_CSS_VAR } from '$lib/design/tokens';

  interface Props {
    label: string;
    used: number;
    limit: number;
    unit?: string;
    size?: 'sm' | 'lg';
  }

  let { label, used, limit, unit = '', size = 'sm' }: Props = $props();

  const chartSize = $derived(size === 'lg' ? 112 : 64);
  const rawPercent = $derived(limit > 0 ? used / limit * 100 : 0);
  const pct = $derived(Number.isFinite(rawPercent) ? Math.max(0, Math.min(100, Math.round(rawPercent))) : 0);
  const tone = $derived(pct >= 100 ? 'danger' : pct > 80 ? 'warning' : 'accent');
  const valueText = $derived(
    limit > 0 ? `${fmt(used)} / ${fmt(limit)}`
    : limit === -1 ? t('quotaDonut.usedOfUnlimited', { used: fmt(used) })
    : fmt(used)
  );

  function fmt(v: number): string {
    if (v >= 1024 && unit === 'MB') return `${Math.round(v / 1024)}GB`;
    if (v >= 1024 && unit === 'GB') return `${Math.round(v / 1024)}TB`;
    return `${v}${unit}`;
  }
</script>

<div class="flex flex-col items-center gap-1">
  <div
    class="relative {size === 'lg' ? 'w-28 h-28' : 'w-16 h-16'}"
    data-tone={tone}
    role={limit > 0 ? 'meter' : 'group'}
    aria-label={label}
    aria-valuemin={limit > 0 ? 0 : undefined}
    aria-valuemax={limit > 0 ? 100 : undefined}
    aria-valuenow={limit > 0 ? pct : undefined}
    aria-valuetext={limit > 0 ? valueText : undefined}
  >
    <BklitChart
      spec={{
        kind: 'ring',
        value: pct,
        max: 100,
        size: chartSize,
        stroke: size === 'lg' ? 10 : 8,
        color: TONE_CSS_VAR[tone],
        track: 'var(--color-line-2)',
      }}
      height={chartSize}
      width={chartSize}
      decorative
    />
    <div class="absolute inset-0 flex items-center justify-center">
      <span class="{size === 'lg' ? 'text-base' : 'text-xs'} font-bold text-ink-0">{limit > 0 ? `${pct}%` : '-'}</span>
    </div>
  </div>
  <div class="text-center">
    <div class="{size === 'lg' ? 'text-sm' : 'text-xs'} text-ink-2 font-medium leading-tight">{label}</div>
    <div class="{size === 'lg' ? 'text-sm' : 'text-xs'} text-ink-2 leading-tight">
      {valueText}
    </div>
  </div>
</div>
