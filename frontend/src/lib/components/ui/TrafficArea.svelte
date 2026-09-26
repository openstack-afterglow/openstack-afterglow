<script lang="ts">
	import type { Snippet } from 'svelte';
	import { trafficAreaGeometry, type TrafficAreaPoint } from './trafficArea';
	import { formatTrafficBytes } from '$lib/utils/waygateTraffic';

	interface Props {
		samples: TrafficAreaPoint[];
		rxLabel: string;
		txLabel: string;
		fresh: boolean;
		children: Snippet;
	}
	let { samples, rxLabel, txLabel, fresh, children }: Props = $props();
	const chart = $derived(trafficAreaGeometry(samples));
	const hasGraph = $derived(chart.rx.length > 0 || chart.tx.length > 0);
</script>

<div class="traffic-area">
	<div class="plot">
		{#if hasGraph}
			<svg viewBox="0 0 {chart.width} {chart.height}" preserveAspectRatio="none" aria-hidden="true">
			<line class="baseline" x1="0" y1={chart.height} x2={chart.width} y2={chart.height} />
			{#key chart.last}
				<g class:arrival={fresh}>
					{#each chart.rx as path}
						<path class="rx area" d={path.area} />
						<path class="rx line" d={path.line} vector-effect="non-scaling-stroke" />
					{/each}
					{#each chart.tx as path}
						<path class="tx area" d={path.area} />
						<path class="tx line" d={path.line} vector-effect="non-scaling-stroke" />
					{/each}
				</g>
			{/key}
			</svg>
		{/if}
		<div class="foreground">{@render children()}</div>
	</div>
	<div class="legend">
		<span class="rx-label">▼ {rxLabel} · 실선</span>
		<span class="tx-label">▲ {txLabel} · 점선</span>
	</div>
	{#if hasGraph}
		<p class="scale">0 – {formatTrafficBytes(chart.peak)}/s · 최근 {Math.round((chart.last - chart.first) / 1000)}초 · 보고 간 평균 속도</p>
	{:else}
		<p class="empty">연속된 상태 보고가 쌓이면 실제 트래픽 그래프가 표시됩니다.</p>
	{/if}
</div>

<style>
	.traffic-area { min-width: 0; overflow: hidden; }
	.plot { position: relative; isolation: isolate; min-height: 5rem; }
	.foreground { position: relative; z-index: 1; padding-block: 0.75rem; }
	.legend { display: flex; flex-wrap: wrap; gap: 0.25rem 1rem; font-size: 0.75rem; }
	.rx-label { color: var(--color-chart-1); }
	.tx-label { color: var(--color-chart-2); }
	svg { position: absolute; inset: 0; display: block; width: 100%; height: 100%; opacity: 0.24; pointer-events: none; }
	.baseline { stroke: var(--color-line); }
	.rx { color: var(--color-chart-1); }
	.tx { color: var(--color-chart-2); }
	.area { fill: currentColor; opacity: 0.1; }
	.line { fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linejoin: round; }
	.tx.line { stroke-dasharray: 4 3; }
	.scale, .empty { margin: 0.5rem 0 0; color: var(--color-ink-2); font-size: 0.75rem; font-variant-numeric: tabular-nums; }
	.empty { padding-block: 0.5rem; }
	.arrival { animation: report-arrival var(--motion-duration-data) var(--motion-ease-out); }
	@keyframes report-arrival { from { opacity: 0.65; transform: translateX(0.5rem); } to { opacity: 1; transform: translateX(0); } }
	@media (prefers-reduced-motion: reduce) { .arrival { animation: none; } }
</style>
