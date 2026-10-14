<script lang="ts">
	import type { Snippet } from 'svelte';
	import { trafficAreaSeries, type TrafficAreaPoint } from './trafficArea';
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	import type { ChartSpec } from '$lib/components/charts/types';
	import { formatTrafficBytes } from '$lib/utils/waygateTraffic';
	import { t } from '$lib/i18n/ns/common';

	interface Props {
		samples: TrafficAreaPoint[];
		rxLabel: string;
		txLabel: string;
		fresh: boolean;
		children: Snippet;
	}
	let { samples, rxLabel, txLabel, fresh, children }: Props = $props();
	let plotHeight = $state(80);
	const chart = $derived(trafficAreaSeries(samples));
	const spec = $derived<ChartSpec>({
		kind: 'time-series', data: chart.data, xKey: 'timestamp',
		series: [
			{ key: 'rxRate', label: rxLabel, color: 'var(--color-chart-1)', area: true },
			{ key: 'txRate', label: txLabel, color: 'var(--color-chart-2)', area: true, dashed: true },
		],
		domain: [0, chart.peak || 1], compact: true, tooltips: false,
	});
</script>

<div class="traffic-area">
	<div class="plot" bind:clientHeight={plotHeight}>
		{#if chart.hasGraph}
			<div class="background" class:arrival={fresh}>
				<BklitChart {spec} height={plotHeight || 80} decorative />
			</div>
		{/if}
		<div class="foreground">{@render children()}</div>
	</div>
	<div class="legend">
		<span class="rx-label">{t('traffic.rxLegend', { label: rxLabel })}</span>
		<span class="tx-label">{t('traffic.txLegend', { label: txLabel })}</span>
	</div>
	{#if chart.hasGraph}
		<p class="scale">{t('traffic.scale', { peak: formatTrafficBytes(chart.peak), seconds: Math.round((chart.last - chart.first) / 1000) })}</p>
	{:else}
		<p class="empty">{t('traffic.empty')}</p>
	{/if}
</div>

<style>
	.traffic-area { min-width: 0; overflow: hidden; }
	.plot { position: relative; isolation: isolate; min-height: 5rem; }
	.foreground { position: relative; z-index: 1; padding-block: 0.75rem; }
	.legend { display: flex; flex-wrap: wrap; gap: 0.25rem 1rem; font-size: 0.75rem; }
	.rx-label { color: var(--color-chart-1); }
	.tx-label { color: var(--color-chart-2); }
	.background { position: absolute; inset: 0; opacity: 0.24; pointer-events: none; }
	.scale, .empty { margin: 0.5rem 0 0; color: var(--color-ink-2); font-size: 0.75rem; font-variant-numeric: tabular-nums; }
	.empty { padding-block: 0.5rem; }
	.arrival { animation: report-arrival var(--motion-duration-data) var(--motion-ease-out); }
	@keyframes report-arrival { from { opacity: 0.65; transform: translateX(0.5rem); } to { opacity: 1; transform: translateX(0); } }
	@media (prefers-reduced-motion: reduce) { .arrival { animation: none; } }
</style>
