<script lang="ts" generics="Row">
	import type { Snippet } from 'svelte';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { t } from '$lib/i18n/ns/common';
	import type { ObservationView } from './observationView.svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	let { rows = [], columns = [], model, loaded = false, children }: {
		rows?: readonly Row[];
		columns?: TableColumn<Row>[];
		model?: ObservationView<Row>;
		loaded?: boolean;
		children: Snippet<[ReturnType<typeof createTableView<Row>>]>;
	} = $props();
	const id = $props.id();
	let search = $state('');
	const ownView = createTableView<Row>({ rows: () => rows, columns: () => columns, search: () => search, locale: intlLocale });
	const view = $derived(model?.view ?? ownView);
</script>

<div class="min-w-0 space-y-3">
	<RegexSearch id={`${id}-search`} bind:value={() => model?.search ?? search, (value) => { if (model) model.search = value; else search = value; }} />
	{#if loaded}<p class="text-xs text-ink-2">{t(view.columns.some(column => column.onFilterChange || column.rangeFilter) ? 'table.mixedScope' : 'table.loadedScope')}</p>{/if}
	<TableViewControls {view} />
	{#if (model?.sourceCount ?? rows.length) > 0 && !view.rows.length}<p class="text-sm text-ink-2" role="status">{t('table.noMatches')}</p>{/if}
	{@render children(view)}
</div>
