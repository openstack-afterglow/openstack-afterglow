<script lang="ts">
  import type { Snippet } from 'svelte';
  import BklitChart from '$lib/components/charts/BklitChart.svelte';
  import { t } from '$lib/i18n/ns/common';

  interface Props {
    value: number;
    max?: number;
    size?: number;
    stroke?: number;
    color?: string;
    track?: string;
    center?: Snippet;
    class?: string;
  }

  let {
    value,
    max = 100,
    size = 80,
    stroke = 8,
    color = 'var(--color-accent)',
    track = 'var(--color-surface-sunken)',
    center,
    class: className = '',
  }: Props = $props();

  const rawPercent = $derived(max > 0 ? (value / max) * 100 : 0);
  const pct = $derived(Number.isFinite(rawPercent) ? Math.max(0, Math.min(100, rawPercent)) : 0);
  const isUnlimited = $derived(max === -1);
  const valueText = $derived(`${value} / ${isUnlimited ? t('quota.unlimited') : max}`);
</script>

<div
  class="donut-wrap {className}"
  style="width:{size}px;height:{size}px"
  role={isUnlimited ? 'group' : 'meter'}
  aria-label={valueText}
  aria-valuemin={isUnlimited ? undefined : 0}
  aria-valuemax={isUnlimited ? undefined : 100}
  aria-valuenow={isUnlimited ? undefined : pct}
  aria-valuetext={isUnlimited ? undefined : valueText}
>
  <BklitChart
    spec={{ kind: 'ring', value: pct, max: 100, size, stroke, color, track }}
    height={size}
    width={size}
    decorative
  />
  {#if center}
    <div class="donut-center">
      {@render center()}
    </div>
  {/if}
</div>

<style>
  .donut-wrap {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .donut-center {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
  }
</style>
