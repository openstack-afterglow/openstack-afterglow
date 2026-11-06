<script lang="ts" generics="T extends { id: string }">
	import { untrack, type Snippet } from 'svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import { t } from '$lib/i18n/ns/admin-storage';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t as tc } from '$lib/i18n/ns/common';

	let {
		title,
		items,
		selected = $bindable(new Set<string>()),
		emptyMessage,
		headerNote,
		columns,
		row,
    cardSummary,
    cardDetails,
		cleanupDisabled = false,
		onCleanup,
	}: {
		title: string;
		items: T[];
		selected?: Set<string>;
		emptyMessage: string;
		headerNote?: Snippet;
		columns: TableColumn<T>[];
		row: Snippet<[T]>;
    cardSummary: Snippet<[T]>;
    cardDetails: Snippet<[T]>;
		cleanupDisabled?: boolean;
		onCleanup: () => void;
	} = $props();

	const view = createTableView<T>({ rows: () => items, columns: () => columns, locale: intlLocale });
	const allSelected = $derived(view.rows.length > 0 && view.rows.every((item) => selected.has(item.id)));
	const hasSelection = $derived(selected.size > 0);
	const partiallySelected = $derived(view.rows.some((item) => selected.has(item.id)) && !allSelected);

	$effect(() => {
		const visible = new Set(view.rows.map((item) => item.id));
		untrack(() => {
			const next = new Set([...selected].filter((id) => visible.has(id)));
			if (next.size !== selected.size) selected = next;
		});
	});

	function toggle(id: string) {
		const next = new Set(selected);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selected = next;
	}

	function toggleAll() {
		if (allSelected) selected = new Set();
		else selected = new Set(view.rows.map((item) => item.id));
	}
</script>

<section class="mb-8">
  <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
		<h2 class="text-base font-semibold text-ink-0">{t('orphanSection.title', { title, count: items.length })}</h2>
		<button
			onclick={onCleanup}
			disabled={cleanupDisabled || selected.size === 0}
      class="min-h-11 px-3 py-1.5 bg-red-600 hover:bg-red-500 text-ink-0 text-xs font-medium rounded-lg disabled:opacity-30 lg:min-h-0"
		>
			{t('orphanSection.cleanSelected', { count: selected.size })}
		</button>
	</div>

	{@render headerNote?.()}

	<TableViewControls {view} />
	{#if view.rows.length === 0}
		<div class="text-xs text-ink-2 bg-surface-base border border-line rounded-lg p-4">
			{items.length === 0 ? emptyMessage : tc('table.noMatches')}
		</div>
	{/if}
    <ResponsiveTable>
      {#snippet cards()}
        <div class="responsive-card-toolbar flex min-h-11 items-center gap-2"><SelectionCheckbox checked={allSelected} indeterminate={partiallySelected} onclick={toggleAll} ariaLabel={t('orphanSection.selectAll', { title })} /><span class="text-xs text-ink-2">{t('orphanSection.selectAll', { title })}</span></div>
        {#each view.rows as item (item.id)}
          <CompactResourceCard selected={selected.has(item.id)}>
            <div class="flex items-start gap-2"><SelectionCheckbox checked={selected.has(item.id)} onclick={() => toggle(item.id)} ariaLabel={t('orphanSection.selectItem', { id: item.id })} /><div class="min-w-0 flex-1 space-y-2">{@render cardSummary(item)}</div></div>
            {#snippet details()}{@render cardDetails(item)}{/snippet}
          </CompactResourceCard>
        {/each}
      {/snippet}
		<div class="overflow-x-auto">
			<table class="selection-table w-full text-sm" class:has-selection={hasSelection}>
				<thead>
					<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
						<th class="text-left py-2 pr-4 w-8">
							<div class="selection-header-reveal" class:is-selected={hasSelection}>
								<SelectionCheckbox
									checked={allSelected}
									indeterminate={partiallySelected}
									onclick={toggleAll}
									ariaLabel={t('orphanSection.selectAll', { title })}
								/>
							</div>
						</th>
						{#each columns as column (column.key)}<TableColumnHeader {view} columnKey={column.key} />{/each}
					</tr>
				</thead>
				<tbody>
					{#each view.rows as item (item.id)}
						<tr class="orphan-row border-b border-line/50 text-xs hover:bg-surface-sunken/30 transition-colors" class:is-selected={selected.has(item.id)}>
							<td class="py-2 pr-4">
								<div class="selection-reveal" class:is-selected={selected.has(item.id)}>
									<SelectionCheckbox
										checked={selected.has(item.id)}
										onclick={() => toggle(item.id)}
										ariaLabel={t('orphanSection.selectItem', { id: item.id })}
									/>
								</div>
							</td>
							{@render row(item)}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
    </ResponsiveTable>
</section>

<style>
	.selection-header-reveal,
	.selection-reveal {
		opacity: 0;
		pointer-events: none;
		transform: translateX(-4px);
		transition:
			opacity 0.16s ease,
			transform 0.16s ease;
	}

	.selection-table:hover .selection-header-reveal,
	.selection-table:focus-within .selection-header-reveal,
	.selection-table.has-selection .selection-header-reveal,
	.selection-header-reveal.is-selected,
	.orphan-row:hover .selection-reveal,
	.orphan-row:focus-within .selection-reveal,
	.orphan-row.is-selected .selection-reveal,
	.selection-reveal.is-selected {
		opacity: 1;
		pointer-events: auto;
		transform: translateX(0);
	}
</style>
