<script lang="ts" generics="Row">
	import type { TableView } from '$lib/utils/tableView.svelte';
	import TableColumnControl from './TableColumnControl.svelte';
	let { view, columnKey, class: className = '' }: { view: TableView<Row>; columnKey: string; class?: string } = $props();
</script>

<th scope="col" aria-sort={view.direction(columnKey)} class={className}>
	<TableColumnControl {view} {columnKey} />
</th>
