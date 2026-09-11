<script lang="ts">
	import { onMount } from 'svelte';
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
	}

	let { net, color, traffic = null, highlighted, dimmed, laneHeight, mode = 'full', onSelect }: Props = $props();

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
	function railWidthPx(totalBps: number): number {
		if (totalBps >= 1e8) return 7; // ≥100Mbps
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
	const typeLabel = $derived(net.is_external ? '외부' : net.is_shared ? '공유' : '내부');
</script>

{#if mode === 'rail'}
	<!-- rail 모드: 세로 라인만 (본문 캔버스 용도, 클릭 불가). 두께는 트래픽 사용량 따라 변동. -->
	<div class="flex flex-col items-center w-full" style="opacity: {dimmed ? 0.25 : 1}">
		<div
			class="rounded-full transition-all duration-300"
			style="width: {railWidthPx(totalBps)}px; height: {laneHeight}px; background: {color}; opacity: {highlighted ? 0.9 : 0.45}"
		></div>
	</div>
{:else}
	<button
		type="button"
		onclick={onSelect}
		class="flex flex-col items-center transition-opacity duration-200 w-full appearance-none bg-transparent border-0 p-0 cursor-pointer focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-line-2 rounded"
		style="opacity: {dimmed ? 0.25 : 1}"
	>
		<!-- Stat card -->
		<div
			class="rounded-lg border px-3 py-2 mb-0 text-center w-full transition-all"
			style="border-color: {color}; background: {highlighted
				? color + '22'
				: isLight ? 'rgba(255,255,255,0.95)' : 'rgb(17 24 39 / 0.9)'}"
		>
			<div class="text-xs font-semibold truncate" style="color: {color}">{net.name || net.id}</div>
			<div class="text-[9px] mt-0.5" style="color: {isLight ? '#6b7280' : '#6b7280'}">{typeLabel}</div>
			{#if cidr}
				<div class="text-[8px] font-mono mt-0.5" style="color: {isLight ? '#9ca3af' : '#4b5563'}">{cidr}</div>
			{/if}
			<div class="text-[8px] font-mono mt-1" style="color: {totalBps > 0 ? trafficColor(totalBps) : (isLight ? '#9ca3af' : '#374151')}">
				{#if netTraffic && totalBps > 0}
					↓{formatBps(netTraffic.rx_bps)} ↑{formatBps(netTraffic.tx_bps)}
				{:else}
					—
				{/if}
			</div>
			<!-- RX/TX mini-bar (log10 스케일, 트래픽 유무 무관하게 동일 높이) -->
			{#if netTraffic && totalBps > 0}
				<div class="mt-1 space-y-0.5">
					<div class="h-0.5 rounded-full overflow-hidden"
					     style="background: {isLight ? '#e5e7eb' : '#1f2937'}">
						<div class="h-full bg-blue-400 transition-all duration-500"
						     style="width: {rxPct}%"></div>
					</div>
					<div class="h-0.5 rounded-full overflow-hidden"
					     style="background: {isLight ? '#e5e7eb' : '#1f2937'}">
						<div class="h-full bg-green-400 transition-all duration-500"
						     style="width: {txPct}%"></div>
					</div>
				</div>
			{:else}
				<div class="mt-1 h-1.5"></div>
			{/if}
		</div>

		{#if mode === 'full'}
			<!-- Vertical line (full 모드 전용) — 두께는 트래픽 사용량 따라 변동 -->
			<div
				class="rounded-full transition-all duration-300"
				style="width: {railWidthPx(totalBps)}px; height: {laneHeight}px; background: {color}; opacity: {highlighted ? 0.9 : 0.45}"
			></div>
		{/if}
	</button>
{/if}
