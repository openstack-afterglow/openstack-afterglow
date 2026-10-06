<script lang="ts">
	import { t } from '$lib/i18n/ns/topology';
	import { onMount } from 'svelte';
	import { enterStep } from './firstArrival.svelte.ts';
	import type { TopologyNetwork, TopologyTraffic } from './types.ts';

	interface Props {
		net: TopologyNetwork;
		color: string;
		traffic?: TopologyTraffic | null;
		highlighted: boolean;
		dimmed: boolean;
		laneHeight: number;
		// 'card' = 헤더 카드만 (sticky 헤더 행 용도)
		// 'rail' = 세로 라인만 (본문 캔버스 용도)
		// 'full' = 카드 + 라인 (기본, 단일 컴포넌트로 사용)
		mode?: 'card' | 'rail' | 'full';
		onSelect?: () => void;
		/** 스코프 첫 도착의 진입 창. 참이면 카드는 페이드, 레일은 위에서부터 자란다. */
		entering?: boolean;
		/** 레인 순서(진입 cascade 단계) */
		enterIndex?: number;
	}

	let { net, color, traffic = null, highlighted, dimmed, laneHeight, mode = 'full', onSelect, entering = false, enterIndex = 0 }: Props = $props();

	let isLight = $state(false);
	onMount(() => {
		isLight = document.documentElement.classList.contains('light');
		const obs = new MutationObserver(() => {
			isLight = document.documentElement.classList.contains('light');
		});
		obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
		return () => obs.disconnect();
	});

	function formatBps(bps: number): string {
		if (bps >= 1e9) return `${(bps / 1e9).toFixed(1)}G`;
		if (bps >= 1e6) return `${(bps / 1e6).toFixed(1)}M`;
		if (bps >= 1e3) return `${(bps / 1e3).toFixed(0)}k`;
		if (bps > 0) return `${bps.toFixed(0)}b`;
		return '0b';
	}

	function trafficColor(totalBps: number): string {
		if (totalBps >= 1e8) return '#ef4444';
		if (totalBps >= 1e7) return '#f97316';
		if (totalBps >= 1e6) return '#fbbf24';
		if (totalBps >= 1e5) return '#4ade80';
		return '#64748b';
	}

	// 세로 라인 굵기 — 트래픽 사용량에 따라 2~7px 범위에서 단계적으로 증가
	const RAIL_MAX_PX = 7;
	function railWidthPx(totalBps: number): number {
		if (totalBps >= 1e8) return RAIL_MAX_PX; // ≥100Mbps
		if (totalBps >= 1e7) return 6; // ≥10Mbps
		if (totalBps >= 1e6) return 5; // ≥1Mbps
		if (totalBps >= 1e5) return 4; // ≥100kbps
		if (totalBps >= 1e4) return 3; // ≥10kbps
		return 2;
	}

	// log10 스케일: 1bps=0%, 1Gbps=100%
	function bpsToPct(bps: number): number {
		if (bps <= 1) return 0;
		return Math.min(100, (Math.log10(bps) / 9) * 100);
	}

	const netTraffic = $derived(traffic?.networks?.[net.id] ?? null);
	const totalBps = $derived(netTraffic ? netTraffic.rx_bps + netTraffic.tx_bps : 0);
	const rxPct = $derived(netTraffic ? bpsToPct(netTraffic.rx_bps) : 0);
	const txPct = $derived(netTraffic ? bpsToPct(netTraffic.tx_bps) : 0);
	const cidr = $derived(net.subnet_details[0]?.cidr ?? '');
	const typeLabel = $derived(net.is_external ? t('kind.external') : net.is_shared ? t('kind.shared') : t('kind.internal'));
	const railW = $derived(railWidthPx(totalBps));
	const step = $derived(enterStep(enterIndex));
</script>

<!--
	레일은 SVG 선이다: 굵기는 stroke-width(레이아웃 폭 전환 없음), 진입은 래퍼의 scaleY(위에서부터),
	실측 트래픽이 0 이 아니면 그 위로 흐름 점선이 지나간다. 둥근 끝 포함 전체 길이가 laneHeight 와 같다.
-->
{#snippet rail()}
	<div class="rail" class:rail-enter={entering} style:--motion-index={entering ? step : undefined}>
		<svg width={RAIL_MAX_PX} height={laneHeight} aria-hidden="true" class="rail-svg" style:opacity={highlighted ? 0.9 : 0.45}>
			<line
				x1={RAIL_MAX_PX / 2} y1={railW / 2}
				x2={RAIL_MAX_PX / 2} y2={Math.max(railW / 2, laneHeight - railW / 2)}
				stroke={color}
				stroke-width={railW}
				stroke-linecap="round"
			/>
			{#if netTraffic && totalBps > 0}
				<line
					class="motion-flow rail-flow"
					x1={RAIL_MAX_PX / 2} y1={railW / 2}
					x2={RAIL_MAX_PX / 2} y2={Math.max(railW / 2, laneHeight - railW / 2)}
					stroke-width={railW}
					stroke-linecap="butt"
				/>
			{/if}
		</svg>
	</div>
{/snippet}

{#if mode === 'rail'}
	<!-- rail 모드: 세로 라인만 (본문 캔버스 용도, 클릭 불가). 두께는 트래픽 사용량 따라 변동. -->
	<div class="flex flex-col items-center w-full" style="opacity: {dimmed ? 0.25 : 1}">
		{@render rail()}
	</div>
{:else}
	<button
		type="button"
		onclick={onSelect}
		class="flex flex-col items-center transition-opacity duration-200 w-full appearance-none bg-transparent border-0 p-0 cursor-pointer focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-line-2 rounded"
		class:motion-fade={entering}
		style="opacity: {dimmed ? 0.25 : 1}"
		style:--motion-index={entering ? step : undefined}
	>
		<!-- Stat card -->
		<div
			class="rounded-lg border px-3 py-2 mb-0 text-center w-full transition-all"
			style="border-color: {color}; background: {highlighted
				? color + '22'
				: isLight ? 'rgba(255,255,255,0.95)' : 'rgb(17 24 39 / 0.9)'}"
		>
			<div class="text-xs font-semibold truncate" style="color: {color}">{net.name || net.id}</div>
			<div class="text-xs mt-0.5" style="color: {isLight ? '#6b7280' : '#6b7280'}">{typeLabel}</div>
			{#if cidr}
				<div class="text-xs font-mono mt-0.5" style="color: {isLight ? '#9ca3af' : '#4b5563'}">{cidr}</div>
			{/if}
			<div class="text-xs font-mono mt-1" style="color: {totalBps > 0 ? trafficColor(totalBps) : (isLight ? '#9ca3af' : '#374151')}">
				{#if netTraffic && totalBps > 0}
					↓{formatBps(netTraffic.rx_bps)} ↑{formatBps(netTraffic.tx_bps)}
				{:else}
					—
				{/if}
			</div>
			<!-- RX/TX mini-bar (log10 스케일, 트래픽 유무 무관하게 동일 높이). 채움은 scaleX 로 움직인다. -->
			{#if netTraffic && totalBps > 0}
				<div class="mt-1 space-y-0.5">
					<div class="h-0.5 rounded-full overflow-hidden"
					     style="background: {isLight ? '#e5e7eb' : '#1f2937'}">
						<div class="rate-fill rate-rx" style:transform="scaleX({rxPct / 100})"></div>
					</div>
					<div class="h-0.5 rounded-full overflow-hidden"
					     style="background: {isLight ? '#e5e7eb' : '#1f2937'}">
						<div class="rate-fill rate-tx" style:transform="scaleX({txPct / 100})"></div>
					</div>
				</div>
			{:else}
				<div class="mt-1 h-1.5"></div>
			{/if}
		</div>

		{#if mode === 'full'}
			<!-- Vertical line (full 모드 전용) — 두께는 트래픽 사용량 따라 변동 -->
			{@render rail()}
		{/if}
	</button>
{/if}

<style>
	.rail { display: flex; justify-content: center; transform-origin: top; }
	.rail-enter {
		animation: motion-grow-y var(--motion-duration-data) var(--motion-ease-emphasized) backwards;
		animation-delay: calc(var(--motion-duration-stagger) * var(--motion-index, 0));
	}
	.rail-svg { display: block; overflow: visible; transition: opacity var(--motion-duration-base) var(--motion-ease-standard); }
	.rail-flow { stroke: var(--motion-sheen); }
	.rate-fill {
		height: 100%;
		width: 100%;
		transform-origin: left;
		animation: motion-grow-x var(--motion-duration-data) var(--motion-ease-emphasized) backwards;
		transition: transform var(--motion-duration-data) var(--motion-ease-emphasized);
	}
	.rate-rx { background: var(--color-chart-1); }
	.rate-tx { background: var(--color-chart-2); }
</style>
