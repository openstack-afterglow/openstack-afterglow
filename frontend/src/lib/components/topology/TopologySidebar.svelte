<script lang="ts">
	import { t } from '$lib/i18n/ns/topology';
	import { enterStep } from './firstArrival.svelte.ts';
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
		entering = false,
		sidebarOrder,
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
		/** 스코프 첫 도착의 진입 창. 참이면 카드가 사이드바 순서대로 cascade 로 들어온다. */
		entering?: boolean;
		/** 리소스 id → 사이드바 순서 */
		sidebarOrder: Map<string, number>;
	} = $props();
</script>

{#if routerRows.length > 0}
	<button
		type="button"
		class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide px-1 w-full text-left transition-colors
		{isLight ? 'text-ink-2 hover:text-gray-800' : 'text-ink-2 hover:text-ink-2'}"
		onclick={() => { groupCollapsed.router = !groupCollapsed.router; onScheduleMeasure(); }}
	>
		<span style="color: {isLight ? '#9ca3af' : '#4b5563'}">{groupCollapsed.router ? '▸' : '▾'}</span>
		{t('sidebar.routers', { count: routerRows.length })}
	</button>
	{#if !groupCollapsed.router}
		{#each routerRows as row, index (row.id)}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class:motion-enter={entering}
				style:--motion-index={entering ? enterStep(sidebarOrder.get(row.id) ?? 0) : undefined}
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
		class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide px-1 mt-1 w-full text-left transition-colors
		{isLight ? 'text-ink-2 hover:text-gray-800' : 'text-ink-2 hover:text-ink-2'}"
		onclick={() => { groupCollapsed.lb = !groupCollapsed.lb; onScheduleMeasure(); }}
	>
		<span style="color: {isLight ? '#9ca3af' : '#4b5563'}">{groupCollapsed.lb ? '▸' : '▾'}</span>
		{t('sidebar.loadBalancers', { count: filteredLbItems.length })}
	</button>
	{#if !groupCollapsed.lb}
		{#each filteredLbItems as { lb, vipNetId } (lb.id)}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class:motion-enter={entering}
				style:--motion-index={entering ? enterStep(sidebarOrder.get(lb.id) ?? 0) : undefined}
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
		class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide px-1 mt-1 w-full text-left transition-colors
		{isLight ? 'text-ink-2 hover:text-gray-800' : 'text-ink-2 hover:text-ink-2'}"
		onclick={() => { groupCollapsed.instance = !groupCollapsed.instance; onScheduleMeasure(); }}
	>
		<span style="color: {isLight ? '#9ca3af' : '#4b5563'}">{groupCollapsed.instance ? '▸' : '▾'}</span>
		{t('sidebar.instances', { count: instanceRows.length })}
	</button>
	{#if !groupCollapsed.instance}
		{#each instanceRows as row (row.id)}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class:motion-enter={entering}
				style:--motion-index={entering ? enterStep(sidebarOrder.get(row.id) ?? 0) : undefined}
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
	<div class="text-xs px-2 py-4" style="color: {isLight ? '#9ca3af' : '#4b5563'}">{t('empty.resources')}</div>
{/if}
