<script lang="ts">
	import { t } from '$lib/i18n/ns/instance';
	import type { Instance } from '$lib/types/compute';
	import InstanceRow from './InstanceRow.svelte';
	import { nextInstanceSort, type InstanceSort, type InstanceSortKey } from './instanceSort';
	import { ResponsiveTable, SelectionCheckbox, TableShell } from '$lib/components/ui';

	let {
		instances,
		underutilized = {},
		sort = null,
		onSortChange,
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
		sort?: InstanceSort;
		onSortChange: (sort: InstanceSort) => void;
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
	const directionLabel = (direction: 'asc' | 'desc' | undefined) =>
		direction === 'asc' ? t('table.sortAscending') : direction === 'desc' ? t('table.sortDescending') : t('table.sortDefault');
</script>

{#snippet sortControl(key: InstanceSortKey, label: string, compact = false)}
	{@const direction = sort?.key === key ? sort.direction : undefined}
	<button
		type="button"
		class="sort-button"
		class:compact
		data-active={direction !== undefined}
		aria-pressed={compact ? direction !== undefined : undefined}
		aria-label={`${t('table.sortBy', { label })}: ${directionLabel(direction)}`}
		title={directionLabel(nextInstanceSort(sort, key)?.direction)}
		onclick={() => onSortChange(nextInstanceSort(sort, key))}
	>
		<span class="min-w-0 truncate">{label}</span>
		<svg class="sort-mark size-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
			{#if direction === 'asc'}<path d="m4 6 4-4 4 4M8 2v12" />
			{:else if direction === 'desc'}<path d="m4 10 4 4 4-4M8 14V2" />
			{:else}<path d="m2 5 3-3 3 3M5 2v12m3-3 3 3 3-3M11 14V2" />{/if}
		</svg>
	</button>
{/snippet}

{#snippet sortHeader(key: InstanceSortKey, label: string)}
	{@const direction = sort?.key === key ? sort.direction : undefined}
	<th scope="col" aria-sort={direction === 'asc' ? 'ascending' : direction === 'desc' ? 'descending' : 'none'}>
		{@render sortControl(key, label)}
	</th>
{/snippet}

<ResponsiveTable>
	{#snippet cards()}
		<div class="responsive-card-toolbar min-h-11 text-xs text-ink-2">
			<SelectionCheckbox checked={allSelected} indeterminate={partiallySelected} disabled={selectionDisabled || selectableIds.size === 0} onclick={onToggleAll} ariaLabel={t('table.selectAll')} />
			<span>{t('table.selectAll')}</span>
		</div>
		<div class="responsive-card-toolbar flex flex-wrap items-center gap-2" role="group" aria-label={t('table.sortColumns')}>
			<span class="text-xs text-ink-2">{t('table.sortColumns')}</span>
			{@render sortControl('name', t('table.name'), true)}
			{@render sortControl('status', t('table.status'), true)}
			{@render sortControl('image', t('table.imageFlavor'), true)}
			{@render sortControl('ip', 'IP', true)}
			{@render sortControl('library', t('table.library'), true)}
			{@render sortControl('strategy', t('table.strategy'), true)}
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
				{@render sortHeader('name', t('table.name'))}
				{@render sortHeader('status', t('table.status'))}
				{@render sortHeader('image', t('table.imageFlavor'))}
				{@render sortHeader('ip', 'IP')}
				{@render sortHeader('library', t('table.library'))}
				{@render sortHeader('strategy', t('table.strategy'))}
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
	.sort-button {
		display: inline-flex;
		max-width: 100%;
		align-items: center;
		gap: 0.375rem;
		margin-inline: -0.375rem;
		padding: 0.25rem 0.375rem;
		border-radius: var(--radius-sm);
		color: inherit;
		font: inherit;
		transition: color 120ms ease, background-color 120ms ease;
	}
	.sort-button:hover { color: var(--color-ink-0); background: var(--color-surface-selected); }
	.sort-button:focus-visible { outline: 2px solid var(--color-focus, currentColor); outline-offset: 1px; }
	.sort-button[data-active='true'] { color: var(--color-ink-0); }
	.sort-mark { flex-shrink: 0; opacity: 0.55; }
	.sort-button[data-active='true'] .sort-mark { opacity: 1; color: var(--color-warm-text, currentColor); }
	.sort-button.compact { min-height: var(--control-touch-height); margin: 0; padding-inline: 0.625rem; border: 1px solid var(--color-line); }
	.sort-button.compact[data-active='true'] { background: var(--color-surface-selected); }
</style>

