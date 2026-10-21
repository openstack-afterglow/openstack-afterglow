<script lang="ts">
	import { t } from '$lib/i18n/ns/instance';
	import type { Instance } from '$lib/types/compute';
	import InstanceRow from './InstanceRow.svelte';
	import { ResponsiveTable, SelectionCheckbox, TableShell } from '$lib/components/ui';

	let {
		instances,
		underutilized = {},
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
	const partiallySelected = $derived(hasSelection && !allSelected);
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
<TableShell density="compact" class={hasSelection ? 'has-selection' : ''}>
	<table class="min-w-[64rem]" aria-label={t('table.instanceList')}>
		<colgroup>
			<col class="w-10" />
			<col />
			<col class="w-36" />
			<col class="w-52" />
			<col class="w-48" />
			<col class="w-32" />
			<col class="w-28" />
			<col class="w-12" />
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
				<th scope="col">{t('table.name')}</th>
				<th scope="col">{t('table.status')}</th>
				<th scope="col">{t('table.imageFlavor')}</th>
				<th scope="col">IP</th>
				<th scope="col">{t('table.library')}</th>
				<th scope="col">{t('table.strategy')}</th>
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

