<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
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
	<Button variant="ghost" size="sm" class="min-h-11 md:min-h-0" ariaLabel={t('services.sort.label', { label })}
		title={active && view.sortDirection === 'asc' ? t('services.sort.descending') : t('services.sort.ascending')} onclick={toggleSort}>
		{label}<span aria-hidden="true">{active ? (view.sortDirection === 'asc' ? '↑' : '↓') : '↕'}</span>
	</Button>
</th>
