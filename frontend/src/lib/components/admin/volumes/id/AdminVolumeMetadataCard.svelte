<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import type { AdminVolumeDetail } from '$lib/types/volume';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableColumnControl from '$lib/components/ui/TableColumnControl.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { t as commonT } from '$lib/i18n/ns/common';

	let { metadata }: { metadata: AdminVolumeDetail['metadata'] } = $props();
	let search = $state('');
	const view = createTableView<[string, string]>({
		rows: () => Object.entries(metadata), search: () => search,
		columns: () => [
			{ key: 'key', label: commonT('table.key'), value: (row) => row[0] },
			{ key: 'value', label: commonT('table.value'), value: (row) => row[1] },
		],
	});
</script>

{#if Object.keys(metadata).length > 0}
	<div class="bg-surface-base border border-line rounded-xl p-4">
		<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('volumeDetail.metadata')}</h3>
		<RegexSearch id="admin-volume-metadata-search" bind:value={search} />
		<TableViewControls {view} />
		<div class="hidden grid-cols-2 gap-4 lg:grid">{#each view.columns as column (column.key)}<TableColumnControl {view} columnKey={column.key} />{/each}</div>
		<dl class="space-y-1.5 text-xs">
			{#each view.rows as [k, v] (k)}
				<div class="flex justify-between gap-4">
					<dt class="text-ink-2 font-mono">{k}</dt>
					<dd class="text-ink-2 font-mono text-right break-all">{v}</dd>
				</div>
			{/each}
		</dl>
	</div>
{/if}
