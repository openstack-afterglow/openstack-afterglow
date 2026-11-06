<script lang="ts">
 import { untrack } from 'svelte';
 import { intlLocale } from '$lib/i18n/runtime.svelte';
 import { t as commonT } from '$lib/i18n/ns/common';
 import { createTableView, type TableColumn, type TableViewState } from '$lib/utils/tableView.svelte';
 import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
 import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
 import RegexSearch from '$lib/components/ui/RegexSearch.svelte';

	import { t } from '$lib/i18n/ns/file-storage';
	import { useFileStorageDetailController } from '$lib/stores/fileStorageDetailController.svelte';
	import { ResponsiveTable, CompactResourceCard } from '$lib/components/ui';

	const s = useFileStorageDetailController();
 let { search = $bindable(''), tableState }: { search?: string; tableState: TableViewState } = $props();
 const searchId = $props.id();
 const entries = $derived(Object.entries(s.fileStorage?.metadata ?? {}));
 const columns = $derived<TableColumn<[string,string]>[]>([{ key: 'key', label: commonT('table.key'), value: row => row[0] },{ key: 'value', label: commonT('table.value'), value: row => row[1] }]);
 // Parent retains this object across error-gated remounts; scope resets mutate it in place.
 const view = createTableView({ state: untrack(() => tableState), locale: intlLocale,rows: () => entries, columns: () => columns, search: () => search, searchable: row => row});
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
	<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">{t('metadata.title')}</h3>
	<RegexSearch id={searchId} bind:value={search} />
<TableViewControls {view} />
{#if entries.length === 0}<p role="status" class="py-4 text-sm text-ink-2">{commonT('table.missing')}</p>
{:else if view.rows.length === 0}<p role="status" class="py-4 text-sm text-ink-2">{commonT('table.noMatches')}</p>{/if}
<ResponsiveTable>
		{#snippet cards()}
			{#each view.rows as [k, v] (k)}
				<CompactResourceCard><strong class="text-xs break-all">{k}</strong><p class="font-mono text-xs break-all text-ink-2 line-clamp-2">{v}</p>{#snippet details()}<p class="font-mono break-all whitespace-pre-wrap">{v}</p>{/snippet}</CompactResourceCard>
			{/each}
		{/snippet}
	<table class="w-full text-sm">
		<thead><tr><TableColumnHeader {view} columnKey="key" /><TableColumnHeader {view} columnKey="value" /></tr></thead>
 <tbody>
			{#each view.rows as [k, v]}
				<tr class="border-b border-line/50">
					<td class="py-2 pr-4 text-ink-2 text-xs w-1/3">{k}</td>
					<td class="py-2 text-ink-2 font-mono text-xs break-all">{v}</td>
				</tr>
			{/each}
		</tbody>
	</table>
	</ResponsiveTable>
</div>
