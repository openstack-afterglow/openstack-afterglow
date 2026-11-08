<script lang="ts" generics="Row">
	import type { TableView } from '$lib/utils/tableView.svelte';
	import { tableDesktop } from '$lib/utils/tableBreakpoint';
	import { mobileViewport } from '$lib/utils/mobileViewport';
	import { t } from '$lib/i18n/ns/common';
	import TableColumnControl from './TableColumnControl.svelte';
	import TableFilterSheet from './TableFilterSheet.svelte';
	import Button from './Button.svelte';
	let { view, class: className = 'lg:hidden' }: { view: TableView<Row>; class?: string } = $props();
	const hasControls = $derived(view.columns.some((column) => column.sortable !== false || column.filterable !== false));
</script>

{#if !className.split(/\s+/).includes('lg:hidden') || !tableDesktop.current}
{#if mobileViewport.current}
	{#if hasControls}
		<div class="table-view-controls {className}" role="group" aria-label={t('table.controls')}>
			<TableFilterSheet {view} />
		</div>
	{/if}
{:else}
<div class="table-view-controls {className}" role="group" aria-label={t('table.controls')}>
	{#each view.columns as column (column.key)}
		{#if column.sortable !== false || column.filterable !== false}
			<TableColumnControl {view} columnKey={column.key} />
		{/if}
	{/each}
	{#if view.sort || Object.keys(view.filters).length || view.columns.some((column) => column.rangeFilter && (column.rangeFilter.min() || column.rangeFilter.max()))}
		<Button variant="ghost" size="xs" onclick={() => view.reset()}>{t('table.resetView')}</Button>
	{/if}
</div>
{/if}

{/if}
<style>
	.table-view-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 0.375rem 0.75rem; min-width: 0; margin-block: 0.5rem; }
</style>
