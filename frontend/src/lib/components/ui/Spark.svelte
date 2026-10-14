<script lang="ts">
  import BklitChart from '$lib/components/charts/BklitChart.svelte';
  import type { ChartSpec } from '$lib/components/charts/types';
  type Mode = 'fixedWidth' | 'stretch';

  interface Props {
    data: number[];
    mode?: Mode;
    width?: number;
    height?: number;
    color?: string;
    area?: boolean;
    class?: string;
  }

  let {
    data = [],
    mode = 'stretch',
    width = 80,
    height = 28,
    color = 'var(--color-accent)',
    area = true,
    class: className = '',
  }: Props = $props();

  const spec = $derived.by((): ChartSpec => {
    const known = data.filter(Number.isFinite);
    const min = known.length ? Math.min(...known) : 0;
    const max = known.length ? Math.max(...known) : 0;
    return {
      kind: 'time-series',
      data: data.length >= 2 ? data.map((value, index) => ({ sample: index, value: Number.isFinite(value) ? value : null })) : [],
      xKey: 'sample',
      series: [{ key: 'value', label: '', color, area }],
      domain: min === max ? [min - 0.5, max + 0.5] : [min, max],
      compact: true,
      tooltips: false,
    };
  });
</script>

<BklitChart {spec} {height} width={mode === 'fixedWidth' ? width : undefined} decorative class={className} />
