<script lang="ts">
	import { onMount } from 'svelte';
	import type { ItemRow, LBItem } from './types.ts';

	interface Props {
		row?: ItemRow | null;
		lbItem?: LBItem | null;
		netColors: Map<string, string>;
		instNetBps: Map<string, { rx_bps: number; tx_bps: number }>;
		selected: boolean;
		onSelect: () => void;
		dataTour?: string;
	}

	let { row = null, lbItem = null, netColors, instNetBps, selected, onSelect, dataTour }: Props = $props();

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
		return '0';
	}

	function statusDot(status: string): string {
		if (status === 'ACTIVE') return 'bg-green-400';
		if (status === 'ERROR' || status === 'SHUTOFF') return 'bg-red-400';
		return 'bg-yellow-400 animate-pulse';
	}

	const ifaceRows = $derived.by(() => {
		if (!row) return [];
		const result: { netId: string; ips: string[]; fips: string[]; rx_bps: number; tx_bps: number }[] = [];
		for (const netId of row.connectedNetIds) {
			const ips = row.netIps.get(netId) ?? [];
			const fips = row.floatingNetIps.get(netId) ?? [];
			const bps = instNetBps.get(`${row.id}|${netId}`);
			result.push({ netId, ips, fips, rx_bps: bps?.rx_bps ?? 0, tx_bps: bps?.tx_bps ?? 0 });
		}
		return result;
	});

	const hasFloating = $derived(row ? row.floatingNetIps.size > 0 : false);
	const nicCount = $derived(row ? row.connectedNetIds.length : 0);
</script>

<button
	type="button"
	class="w-full text-left rounded-lg border transition-all focus:outline-none focus:ring-2 focus:ring-line-2 relative"
	data-tour={dataTour}
	class:shadow-lg={selected}
	style="
		border-color: {selected
			? '#3b82f6'
			: isLight ? '#d1d5db' : '#374151'};
		background: {selected
			? (isLight ? '#eff6ff' : 'rgb(17 24 39 / 0.95)')
			: (isLight ? '#ffffff' : 'rgb(31 41 55 / 1)')};
		box-shadow: {selected ? (isLight ? '0 4px 16px rgba(59,130,246,0.15)' : '0 4px 16px rgba(30,58,138,0.3)') : 'none'}
	"
	onclick={onSelect}
>
	<!-- Header -->
	<div class="flex items-center gap-2 px-3 py-2">
		<span class="w-2 h-2 rounded-full flex-shrink-0 {statusDot(row?.status ?? lbItem?.lb.provisioning_status ?? '')}"></span>

		{#if row?.type === 'router'}
			<svg class="w-4 h-4 flex-shrink-0 text-action-warm" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
				<circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="2" fill="currentColor" opacity="0.5"/>
				<path d="M8 2v2M8 12v2M2 8h2M12 8h2"/>
			</svg>
		{:else if lbItem}
			<svg class="w-4 h-4 flex-shrink-0 text-cyan-400" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
				<line x1="8" y1="2" x2="8" y2="14"/><line x1="3" y1="5" x2="13" y2="5"/><line x1="4" y1="11" x2="12" y2="11" opacity="0.6"/>
			</svg>
		{:else}
			<svg class="w-4 h-4 flex-shrink-0 text-ink-2" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3">
				<ellipse cx="8" cy="5" rx="5" ry="2"/><line x1="3" y1="5" x2="3" y2="11"/><line x1="13" y1="5" x2="13" y2="11"/>
				<path d="M3 11 a5 2 0 0 0 10 0"/>
			</svg>
		{/if}

		<span class="flex-1 text-xs font-semibold truncate"
		      style="color: {isLight ? '#111827' : '#f3f4f6'}">
			{row?.name ?? lbItem?.lb.name ?? ''}
		</span>

		<div class="flex items-center gap-1 flex-shrink-0">
			{#if hasFloating}
				<span class="text-[9px] px-1 rounded bg-orange-900/40 text-orange-400 font-mono">✦</span>
			{/if}
			{#if nicCount > 1}
				<span class="text-[9px] px-1 rounded bg-surface-selected/40 text-action-warm">{nicCount}NIC</span>
			{/if}
			{#if lbItem}
				<span class="text-[9px] px-1 rounded bg-cyan-900/40 text-cyan-400">{lbItem.lb.members.length}m</span>
			{/if}
		</div>
	</div>

	<!-- Interface rows -->
	{#if row && ifaceRows.length > 0}
		<div class="border-t" style="border-color: {isLight ? '#e5e7eb' : 'rgb(55 65 81 / 0.5)'}">
			{#each ifaceRows as iface}
				{@const col = netColors.get(iface.netId) ?? '#3b82f6'}
				{@const totalBps = iface.rx_bps + iface.tx_bps}
				<div
					class="flex items-center gap-2 px-3 py-1.5"
					style="border-left: 3px solid {col}"
					data-anchor-key="{row.id}|{iface.netId}"
				>
					<div class="flex-1 min-w-0">
						<div class="flex items-center gap-1 flex-wrap">
							{#each iface.ips as ip}
								<span class="text-[9px] font-mono" style="color: {isLight ? '#374151' : '#d1d5db'}">{ip}</span>
							{/each}
							{#each iface.fips as fip}
								<span class="text-[9px] font-mono text-orange-400">✦{fip}</span>
							{/each}
							{#if iface.ips.length === 0 && iface.fips.length === 0}
								<span class="text-[9px] italic" style="color: {isLight ? '#9ca3af' : '#4b5563'}">인터페이스</span>
							{/if}
						</div>
						<div class="flex gap-2 mt-0.5">
							<span class="text-[8px] font-mono"
							      style="color: {iface.rx_bps > 0 ? '#60a5fa' : (isLight ? '#9ca3af' : '#4b5563')}">
								↓{formatBps(iface.rx_bps)}
							</span>
							<span class="text-[8px] font-mono"
							      style="color: {iface.tx_bps > 0 ? '#34d399' : (isLight ? '#9ca3af' : '#4b5563')}">
								↑{formatBps(iface.tx_bps)}
							</span>
						</div>
					</div>
				</div>
			{/each}
		</div>
	{/if}

	<!-- LB VIP row -->
	{#if lbItem}
		{@const col = netColors.get(lbItem.vipNetId ?? '') ?? '#06b6d4'}
		<div class="border-t" style="border-color: {isLight ? '#e5e7eb' : 'rgb(55 65 81 / 0.5)'}">
			<div
				class="flex items-center gap-2 px-3 py-1.5"
				style="border-left: 3px solid {col}"
				data-anchor-key="lb|{lbItem.lb.id}|{lbItem.vipNetId}"
			>
				{#if lbItem.lb.vip_address}
					<span class="text-[9px] font-mono" style="color: {isLight ? '#374151' : '#d1d5db'}">VIP: {lbItem.lb.vip_address}</span>
				{/if}
			</div>
		</div>
	{/if}
</button>
