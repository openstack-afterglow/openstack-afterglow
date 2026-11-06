<script lang="ts">
	import { t } from '$lib/i18n/ns/drover';
	import { t as tc } from '$lib/i18n/ns/common';
	import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
	import { Button, CompactResourceCard, ResponsiveTable } from '$lib/components/ui';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import TableColumnControl from '$lib/components/ui/TableColumnControl.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';

	const s = useK3sClusterDetailController();
	type VmRow = { id: string; label: string };
	const rows = $derived<VmRow[]>([
		...(s.cluster?.server_vm_id ? [{ id: s.cluster.server_vm_id, label: t('overview.vms.server') }] : []),
		...(s.cluster?.agent_vm_ids ?? []).map((id, index) => ({ id, label: t('overview.vms.agent', { number: index + 1 }) })),
	]);
	const tableState = s.tableState('vms');
	const columns = $derived<TableColumn<VmRow>[]>([
		{ key: 'label', label: tc('table.name'), value: row => row.label },
		{ key: 'id', label: 'ID', value: row => row.id },
	]);
	const view = createTableView({ rows: () => rows, columns: () => columns, search: () => tableState.search, state: tableState.state });
</script>

<div class="bg-surface-base border border-line rounded-xl p-4">
	<h3 class="text-xs text-ink-2 uppercase tracking-wide mb-3">{t('overview.vms.title')}</h3>
	<RegexSearch id="k3s-vms-search" bind:value={tableState.search} />
	<TableViewControls {view} />
	<ResponsiveTable>
		{#snippet cards()}
			{#each view.rows as row (row.id)}
				<CompactResourceCard>
					<strong class="text-sm">{row.label}</strong>
					{#snippet details()}<p class="text-xs font-mono break-all">{row.id}</p>{/snippet}
					{#snippet actions()}<Button variant="link" size="xs" onclick={() => s.setViewingInstance(row.id)}>{t('overview.vms.viewInstance')}</Button>{/snippet}
				</CompactResourceCard>
			{:else}<p class="text-xs text-ink-2">{rows.length ? tc('table.noMatches') : t('overview.vms.empty')}</p>{/each}
		{/snippet}
		<div class="space-y-2">
			<div class="grid grid-cols-[1fr_2fr_auto] gap-2 text-xs text-ink-2">
				{#each columns as column}<TableColumnControl {view} columnKey={column.key} />{/each}<span></span>
			</div>
			{#each view.rows as row (row.id)}
				<div class="grid grid-cols-[1fr_2fr_auto] items-center gap-2 border-b border-line py-2 text-xs">
					<span>{row.label}</span><span class="font-mono break-all text-ink-2">{row.id}</span>
					<Button variant="link" size="xs" onclick={() => s.setViewingInstance(row.id)}>{t('overview.vms.viewInstance')}</Button>
				</div>
			{:else}<p class="text-xs text-ink-2">{rows.length ? tc('table.noMatches') : t('overview.vms.empty')}</p>{/each}
		</div>
	</ResponsiveTable>
</div>
