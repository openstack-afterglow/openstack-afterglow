<script lang="ts">
	import { createTableView, provideTableViewVisibility, type TableColumn, type TableSort } from '$lib/utils/tableView.svelte';
	import RegexSearch from '../RegexSearch.svelte';
	import TableColumnHeader from '../TableColumnHeader.svelte';
	import TableViewControls from '../TableViewControls.svelte';
	// Nested visible presentation must still inherit an outer owner's hidden mask.
	provideTableViewVisibility(() => true);
	let { native = false, combinedRange = false, onNativeChange, onRangeChange, onSortChange }: {
		native?: boolean;
		combinedRange?: boolean;
		onNativeChange?: (key: string, values: string[] | null) => void;
		onRangeChange?: (min: string, max: string) => void;
		onSortChange?: (sort: TableSort | null) => void;
	} = $props();
	let nativeName = $state<string[] | null>(null);
	let nativeStatus = $state<string[] | null>(null);
	let minimum = $state('');
	let maximum = $state('');
	let query = $state('');
	let compact = $state(false);
	let rows = $state([
		{ id: 'a', name: 'host10', status: 'active' as string | null },
		{ id: 'b', name: 'host2', status: 'paused' as string | null },
		{ id: 'c', name: 'host1', status: null as string | null },
		{ id: 'd', name: 'host0', status: '' as string | null },
	]);
	type Row = (typeof rows)[number];
	const columns = $derived<TableColumn<Row>[]>([
		{ key: 'name', label: 'Name', value: (row) => row.name, ...(native ? {
			filterMode: 'single' as const,
			filterFreeValue: true,
			filterSelection: () => nativeName,
			onFilterChange: (values: string[] | null) => { nativeName = values; onNativeChange?.('name', values); },
		} : {}) },
		{ key: 'status', label: 'Status', value: (row) => row.status, ...(native ? {
			filterMode: 'single' as const,
			filterOptions: () => [{ value: 'active', label: 'Active', count: 120 }, { value: 'paused', label: 'Paused', count: null }],
			filterSelection: () => nativeStatus,
			onFilterChange: (values: string[] | null) => { nativeStatus = values; onNativeChange?.('status', values); },
		} : {}) },
		...(native ? [{
			key: 'size', label: 'Size', value: () => 1,
			rangeFilter: { min: () => minimum, max: () => maximum, onchange: (min: string, max: string) => { minimum = min; maximum = max; onRangeChange?.(min, max); } },
			...(combinedRange ? {
				filterMode: 'single' as const,
				filterOptions: () => [{ value: '10', label: '10 GiB', count: null }, { value: '20', label: '20 GiB', count: null }],
				filterSelection: () => minimum && minimum === maximum ? [minimum] : null,
				onFilterChange: (values: string[] | null) => { minimum = values?.[0] ?? ''; maximum = values?.[0] ?? ''; onNativeChange?.('size', values); },
			} : {}),
		}] : []),
	]);
	const view = createTableView({ rows: () => rows, columns: () => columns, search: () => query, searchable: (row) => row.name, onSortChange: (sort) => onSortChange?.(sort) });
</script>

<RegexSearch id="fixture-search" label="Search" bind:value={query} />
<button onclick={() => compact = !compact}>Switch layout</button>
<button onclick={() => rows = [{ id: 'e', name: 'host99', status: 'active' }]}>Refresh</button>
<button>Outside</button>
{#if compact}
	<TableViewControls {view} class="" />
{:else}
	<table><thead><tr>{#each columns as column}<TableColumnHeader {view} columnKey={column.key} />{/each}</tr></thead>
		<tbody>{#each view.rows as row (row.id)}<tr><td>{row.name}</td><td>{row.status ?? 'Missing'}</td></tr>{/each}</tbody>
	</table>
{/if}
<output data-testid="visible-rows">{view.rows.map((row) => row.name).join(',')}</output>
