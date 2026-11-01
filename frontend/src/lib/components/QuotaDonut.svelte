<script lang="ts">
  import { t } from '$lib/i18n/ns/common';
  import BklitChart from '$lib/components/charts/BklitChart.svelte';
  import { TONE_CSS_VAR, type DesignTone } from '$lib/design/tokens';
  import { intlLocale } from '$lib/i18n/runtime.svelte';

  interface Props {
    label: string;
    used: number | null | undefined;
    limit: number | null | undefined;
    unit?: string;
    size?: 'sm' | 'lg';
    tone?: DesignTone;
  }

  let { label, used, limit, unit = '', size = 'sm', tone: requestedTone }: Props = $props();

  const chartSize = $derived(size === 'lg' ? 112 : 64);
  const hasUsed = $derived(used != null && Number.isFinite(used));
  const zeroQuota = $derived(limit === 0 && hasUsed);
  const bounded = $derived(limit != null && Number.isFinite(limit) && limit > 0 && hasUsed);
  const rawPercent = $derived(bounded ? used! / limit! * 100 : null);
  const observedPercent = $derived(rawPercent != null && Number.isFinite(rawPercent) ? rawPercent : null);
  const visualPercent = $derived(observedPercent == null ? 0 : Math.max(0, Math.min(100, observedPercent)));
  const tone = $derived(requestedTone ?? (zeroQuota && used! > 0 ? 'danger' : observedPercent == null ? 'neutral' : observedPercent >= 100 ? 'danger' : observedPercent > 80 ? 'warning' : 'accent'));
  const displayPercent = $derived(observedPercent == null ? null : (observedPercent > 100 ? Math.ceil(observedPercent * 10) : Math.floor(observedPercent * 10)) / 10);
  const percentText = $derived(displayPercent == null ? '—' : `${displayPercent.toLocaleString(intlLocale(), { maximumFractionDigits: 1 })}%`);
  const valueText = $derived(
    `${hasUsed ? fmt(used!) : t('quota.unknown')} / ${limit === -1 ? t('quota.unlimited') : limit != null && Number.isFinite(limit) ? fmt(limit) : t('quota.unknown')}`
  );
  const accessibleValue = $derived(observedPercent == null ? `${valueText}${zeroQuota && used! > 0 ? ` · ${t('quota.overLimit')}` : ''}` : `${valueText} · ${percentText}`);

  function fmt(v: number): string {
    if (v >= 1024 && unit === 'MB') return `${Math.round(v / 1024)}GB`;
    if (v >= 1024 && unit === 'GB') return `${Math.round(v / 1024)}TB`;
    return `${v}${unit}`;
  }
</script>

<div class="flex min-w-0 max-w-full flex-col items-center gap-1">
  <div
    class="relative {size === 'lg' ? 'w-28 h-28' : 'w-16 h-16'}"
    data-tone={tone}
    role={observedPercent == null ? 'group' : 'meter'}
    aria-label={observedPercent == null ? `${label}: ${accessibleValue}` : label}
    aria-valuemin={observedPercent == null ? undefined : Math.min(0, observedPercent)}
    aria-valuemax={observedPercent == null ? undefined : Math.max(100, observedPercent)}
    aria-valuenow={observedPercent ?? undefined}
    aria-valuetext={observedPercent == null ? undefined : accessibleValue}
  >
    <BklitChart
      spec={{
        kind: 'ring',
        value: visualPercent,
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
      <span class="{size === 'lg' ? 'text-base' : 'text-xs'} font-semibold tabular-nums text-ink-0 text-center" aria-hidden="true">{percentText}</span>
    </div>
  </div>
  <div class="min-w-0 max-w-full text-center">
    <div class="{size === 'lg' ? 'text-sm' : 'text-xs'} text-ink-2 font-medium leading-tight">{label}</div>
    <div class="text-sm text-ink-2 leading-tight tabular-nums">
      {valueText}
      {#if zeroQuota && used! > 0}<span class="block text-[length:var(--type-support)]">{t('quota.overLimit')}</span>{/if}
    </div>
  </div>
</div>
