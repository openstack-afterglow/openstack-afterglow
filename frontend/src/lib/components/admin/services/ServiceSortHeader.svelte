<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import type { ServiceListState } from './serviceList';

	let { view = $bindable(), column, label }: {
		view: ServiceListState;
		column: string;
		label: string;
	} = $props();
	const active = $derived(view.sortKey === column);

	function toggleSort() {
		if (active) view.sortDirection = view.sortDirection === 'asc' ? 'desc' : 'asc';
		else {
			view.sortKey = column;
			view.sortDirection = 'asc';
		}
	}
</script>

<th scope="col" aria-sort={active ? (view.sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}>
	<Button variant="ghost" size="sm" class="min-h-11 md:min-h-0" ariaLabel="{label} 정렬"
		title={active && view.sortDirection === 'asc' ? '내림차순 정렬' : '오름차순 정렬'} onclick={toggleSort}>
		{label}<span aria-hidden="true">{active ? (view.sortDirection === 'asc' ? '↑' : '↓') : '↕'}</span>
	</Button>
</th>
