<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-storage';
	import type { AdminVolumeDetail } from '$lib/types/volume';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';

	let { attachments }: { attachments: AdminVolumeDetail['attachments'] } = $props();
	let search = $state('');
	const view = createTableView<AdminVolumeDetail['attachments'][number]>({
		rows: () => attachments, search: () => search,
		columns: () => [
			{ key: 'server', label: t('volumeDetail.instanceId'), value: (row) => row.server_id },
			{ key: 'device', label: t('volumeDetail.device'), value: (row) => row.device },
		],
	});
</script>

{#if attachments.length > 0}
	<div class="bg-surface-base border border-line rounded-xl p-4 mb-4">
		<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('volumeDetail.attachments')}</h3>
		<RegexSearch id="admin-volume-attachments-search" bind:value={search} />
		<TableViewControls {view} />
		<ResponsiveTable>
			{#snippet cards()}
				{#each view.rows as att}
					<CompactResourceCard><p class="break-all font-mono text-xs text-ink-0">{t('volumeDetail.instanceId')}: {att.server_id}</p><p class="break-all text-xs text-ink-2">{t('volumeDetail.device')}: {att.device}</p></CompactResourceCard>
				{/each}
			{/snippet}
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
					{#each view.columns as column (column.key)}<TableColumnHeader {view} columnKey={column.key} />{/each}
				</tr>
			</thead>
			<tbody>
				{#each view.rows as att}
					<tr class="border-b border-line/50 text-xs">
						<td class="py-2 pr-4 font-mono text-ink-2">{att.server_id}</td>
						<td class="py-2 pr-4 text-ink-2">{att.device}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		</ResponsiveTable>
	</div>
{/if}
