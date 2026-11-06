<script lang="ts">
	import { t } from '$lib/i18n/ns/instance';
	import type { Instance } from '$lib/types/compute';
	import InstanceRow from './InstanceRow.svelte';
	import type { createTableView } from '$lib/utils/tableView.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import { ResponsiveTable, SelectionCheckbox, TableShell } from '$lib/components/ui';

	let {
		instances,
		underutilized = {},
		view,
		selectedIds,
		selectableIds,
		selectionDisabled,
		onSelect,
		onAction,
		onToggleSelect,
		onToggleAll,
	}: {
		instances: Instance[];
		underutilized?: Record<string, boolean>;
		view: ReturnType<typeof createTableView<Instance>>;
		selectedIds: ReadonlySet<string>;
		selectableIds: ReadonlySet<string>;
		selectionDisabled: boolean;
		onSelect: (id: string) => void;
		onAction: (kind: 'console' | 'shelve' | 'unshelve' | 'delete' | 'start' | 'stop', instance: Instance) => Promise<void>;
		onToggleSelect: (id: string) => void;
		onToggleAll: () => void;
	} = $props();

	const allSelected = $derived(
		selectableIds.size > 0 && [...selectableIds].every((id) => selectedIds.has(id))
	);
	const hasSelection = $derived(selectedIds.size > 0);
	const partiallySelected = $derived(!allSelected && [...selectableIds].some((id) => selectedIds.has(id)));
	let actingIds = $state<ReadonlySet<string>>(new Set());
	async function act(kind: Parameters<typeof onAction>[0], instance: Instance) {
		if (actingIds.has(instance.id)) return;
		actingIds = new Set([...actingIds, instance.id]);
		try { await onAction(kind, instance); }
		finally { actingIds = new Set([...actingIds].filter((id) => id !== instance.id)); }
	}
</script>


<ResponsiveTable>
	{#snippet cards()}
		<div class="responsive-card-toolbar min-h-11 text-xs text-ink-2">
			<SelectionCheckbox checked={allSelected} indeterminate={partiallySelected} disabled={selectionDisabled || selectableIds.size === 0} onclick={onToggleAll} ariaLabel={t('table.selectAll')} />
			<span>{t('table.selectAll')}</span>
		</div>
		{#each instances as inst (inst.id)}
			<InstanceRow instance={inst} compact acting={actingIds.has(inst.id)} isUnderutilized={underutilized[inst.id] ?? false} selected={selectedIds.has(inst.id)} selectable={selectableIds.has(inst.id)} {selectionDisabled} {onSelect} onAction={act} onToggleSelect={() => onToggleSelect(inst.id)} />
		{/each}
	{/snippet}
<TableShell class={hasSelection ? 'has-selection' : ''}>
	<table class="instances-table" aria-label={t('table.instanceList')}>
		<colgroup>
			<col class="w-10" />
			<col />
			<col class="w-36" />
			<col />
			<col class="w-48" />
			<col class="w-32" />
			<col class="w-28" />
			<col class="w-20" />
		</colgroup>
		<thead>
			<tr>
				<th scope="col" class="text-left">
					<SelectionCheckbox
						checked={allSelected}
						indeterminate={partiallySelected}
						disabled={selectionDisabled || selectableIds.size === 0}
						onclick={onToggleAll}
						ariaLabel={t('table.selectAll')}
					/>
				</th>
				{#each ['name', 'status', 'image', 'ip', 'library', 'strategy'] as columnKey}
					<TableColumnHeader {view} {columnKey} />
				{/each}
				<th scope="col"><span class="sr-only">{t('table.actions')}</span></th>
			</tr>
		</thead>
		<tbody>
			{#each instances as inst (inst.id)}
				<InstanceRow
					instance={inst}
					acting={actingIds.has(inst.id)}
					isUnderutilized={underutilized[inst.id] ?? false}
					selected={selectedIds.has(inst.id)}
					selectable={selectableIds.has(inst.id)}
					{selectionDisabled}
					{onSelect}
					onAction={act}
					onToggleSelect={() => onToggleSelect(inst.id)}
				/>
			{/each}
		</tbody>
	</table>
</TableShell>
</ResponsiveTable>

<style>
	/* Preserve a usable desktop minimum. Flexible identity/image columns absorb wider shells;
	   action width includes its trigger and both cell paddings, without clipping any action. */
	:global(.table-shell) .instances-table {
		table-layout: fixed;
		min-width: 64rem;
	}
	:global(.table-shell) .instances-table :global(td:last-child),
	:global(.table-shell) .instances-table th:last-child { padding-inline: 0.75rem; }
</style>

