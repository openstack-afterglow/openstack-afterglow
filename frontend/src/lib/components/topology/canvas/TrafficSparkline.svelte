<script lang="ts">
	// 네트워크 사용량(rx/tx) 스파크라인. 백엔드가 준 30초 rate 윈도우 샘플을 그대로 그린다.
	//
	// 축·툴팁을 두지 않는 이유: 이건 패널 안 보조 시각화이고, 정확한 수치는 바로 아래 통계 행이
	// 담당한다. 색만으로 rx/tx 를 구분하지 않도록 범례에 "수신"·"송신" 글자를 함께 둔다.
	import type { TrafficHistoryPoint } from '$lib/types/topology';
	import { sparkPoints } from './canvasHelpers';

	interface Props {
		series: TrafficHistoryPoint[];
		/** 조회 구간 라벨(예: "15분") — 범례에 표시 */
		rangeLabel?: string;
	}

	let { series, rangeLabel = '' }: Props = $props();

	// viewBox 좌표계. 실제 크기는 CSS(width:100%, height)가 정한다.
	const W = 100;
	const H = 30;

	// rx/tx 를 같은 축에 올려야 비교가 된다 — 상한은 두 계열의 최대값.
	//
	// 이 상한은 화면에 숫자로 내보내지 않는다. 단방향 최대(예: 5.2M)를 통계 행의
	// 최대(rx+tx 합계, 예: 9.5M) 옆에 두면 두 "최대"가 모순으로 읽힌다.
	// 숫자는 통계 행이 단독으로 책임지고, 여기는 모양만 보여준다.
	const peak = $derived(series.reduce((m, p) => Math.max(m, p.rx_bps, p.tx_bps), 0));
	const rxPts = $derived(sparkPoints(series.map((p) => p.rx_bps), W, H, peak));
	const txPts = $derived(sparkPoints(series.map((p) => p.tx_bps), W, H, peak));
</script>

{#if series.length}
	<div class="spark">
		<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" aria-hidden="true">
			<line class="base" x1="0" y1={H} x2={W} y2={H} vector-effect="non-scaling-stroke" />
			<polyline class="tx" points={txPts} vector-effect="non-scaling-stroke" />
			<polyline class="rx" points={rxPts} vector-effect="non-scaling-stroke" />
		</svg>
		<p class="legend">
			<span class="key rx-key">▼ 수신</span>
			<span class="key tx-key">▲ 송신</span>
			{#if rangeLabel}<span class="range">{rangeLabel}</span>{/if}
		</p>
	</div>
{/if}

<style>
	.spark { min-width: 0; }
	svg {
		display: block;
		width: 100%;
		height: 2.25rem;
		overflow: visible;
	}
	.base { stroke: var(--color-line-1); stroke-width: 1; }
	polyline { fill: none; stroke-width: 1.5; stroke-linejoin: round; stroke-linecap: round; }
	.rx { stroke: var(--color-chart-1); }
	.tx { stroke: var(--color-chart-2); }
	.legend {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		margin: 0.25rem 0 0;
		font-size: 0.75rem;
		color: var(--color-ink-2);
	}
	.key { font-variant-numeric: tabular-nums; }
	.rx-key { color: var(--color-chart-1); }
	.tx-key { color: var(--color-chart-2); }
	.range { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
</style>
