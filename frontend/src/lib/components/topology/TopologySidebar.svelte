<script lang="ts">
	import ResourceCard from './ResourceCard.svelte';
	import type { ItemRow, LBItem, TopologyLoadBalancer } from './types.ts';

	let {
		routerRows,
		filteredLbItems,
		instanceRows,
		selectedId,
		hoveredId = $bindable<string | null>(null),
		netColors,
		instNetBps,
		isLight,
		groupCollapsed = $bindable({ router: false, lb: false, instance: false }),
		onSelectRow,
		onSelectLb,
		onScheduleMeasure,
		onIntentRow,
		onCancelIntent,
	}: {
		routerRows: ItemRow[];
		filteredLbItems: LBItem[];
		instanceRows: ItemRow[];
		selectedId: string | null;
		hoveredId?: string | null;
		netColors: Map<string, string>;
		instNetBps: Map<string, { rx_bps: number; tx_bps: number }>;
		isLight: boolean;
		groupCollapsed?: { router: boolean; lb: boolean; instance: boolean };
		onSelectRow: (row: ItemRow) => void;
		onSelectLb: (lb: TopologyLoadBalancer) => void;
		onScheduleMeasure: () => void;
		onIntentRow?: (row: ItemRow) => void;
		onCancelIntent?: () => void;
	} = $props();
</script>

{#if routerRows.length > 0}
	<button
		type="button"
		class="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide px-1 w-full text-left transition-colors
		{isLight ? 'text-ink-3 hover:text-gray-800' : 'text-ink-3 hover:text-ink-2'}"
		onclick={() => { groupCollapsed.router = !groupCollapsed.router; onScheduleMeasure(); }}
	>
		<span style="color: {isLight ? '#9ca3af' : '#4b5563'}">{groupCollapsed.router ? '▸' : '▾'}</span>
		라우터 ({routerRows.length})
	</button>
	{#if !groupCollapsed.router}
		{#each routerRows as row, index (row.id)}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				onmouseenter={() => { hoveredId = row.id; onIntentRow?.(row); }}
				onmouseleave={() => { hoveredId = null; onCancelIntent?.(); }}
				onfocusin={() => onIntentRow?.(row)}
				onfocusout={onCancelIntent}
			>
				<ResourceCard
					{row}
					{netColors}
					{instNetBps}
					selected={selectedId === row.id}
					onSelect={() => onSelectRow(row)}
					dataTour={index === 0 ? 'admin-network-resource' : undefined}
				/>
			</div>
		{/each}
	{/if}
{/if}

{#if filteredLbItems.length > 0}
	<button
		type="button"
		class="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide px-1 mt-1 w-full text-left transition-colors
		{isLight ? 'text-ink-3 hover:text-gray-800' : 'text-ink-3 hover:text-ink-2'}"
		onclick={() => { groupCollapsed.lb = !groupCollapsed.lb; onScheduleMeasure(); }}
	>
		<span style="color: {isLight ? '#9ca3af' : '#4b5563'}">{groupCollapsed.lb ? '▸' : '▾'}</span>
		로드밸런서 ({filteredLbItems.length})
	</button>
	{#if !groupCollapsed.lb}
		{#each filteredLbItems as { lb, vipNetId } (lb.id)}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				onmouseenter={() => { hoveredId = lb.id; }}
				onmouseleave={() => { hoveredId = null; }}
			>
				<ResourceCard
					lbItem={{ lb, vipNetId }}
					{netColors}
					{instNetBps}
					selected={selectedId === lb.id}
					onSelect={() => onSelectLb(lb)}
				/>
			</div>
		{/each}
	{/if}
{/if}

{#if instanceRows.length > 0}
	<button
		type="button"
		class="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide px-1 mt-1 w-full text-left transition-colors
		{isLight ? 'text-ink-3 hover:text-gray-800' : 'text-ink-3 hover:text-ink-2'}"
		onclick={() => { groupCollapsed.instance = !groupCollapsed.instance; onScheduleMeasure(); }}
	>
		<span style="color: {isLight ? '#9ca3af' : '#4b5563'}">{groupCollapsed.instance ? '▸' : '▾'}</span>
		인스턴스 ({instanceRows.length})
	</button>
	{#if !groupCollapsed.instance}
		{#each instanceRows as row (row.id)}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				onmouseenter={() => { hoveredId = row.id; onIntentRow?.(row); }}
				onmouseleave={() => { hoveredId = null; onCancelIntent?.(); }}
				onfocusin={() => onIntentRow?.(row)}
				onfocusout={onCancelIntent}
			>
				<ResourceCard
					{row}
					{netColors}
					{instNetBps}
					selected={selectedId === row.id}
					onSelect={() => onSelectRow(row)}
				/>
			</div>
		{/each}
	{/if}
{/if}

{#if routerRows.length === 0 && filteredLbItems.length === 0 && instanceRows.length === 0}
	<div class="text-xs px-2 py-4" style="color: {isLight ? '#9ca3af' : '#4b5563'}">리소스 없음</div>
{/if}
