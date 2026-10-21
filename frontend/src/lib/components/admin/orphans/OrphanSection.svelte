<script lang="ts" generics="T extends { id: string }">
	import type { Snippet } from 'svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import { t } from '$lib/i18n/ns/admin-storage';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';

	let {
		title,
		items,
		selected = $bindable(new Set<string>()),
		emptyMessage,
		headerNote,
		headers,
		row,
    cardSummary,
    cardDetails,
		onCleanup,
	}: {
		title: string;
		items: T[];
		selected?: Set<string>;
		emptyMessage: string;
		headerNote?: Snippet;
		headers: Snippet;
		row: Snippet<[T]>;
    cardSummary: Snippet<[T]>;
    cardDetails: Snippet<[T]>;
		onCleanup: () => void;
	} = $props();

	const allSelected = $derived(items.length > 0 && selected.size === items.length);
	const hasSelection = $derived(selected.size > 0);
	const partiallySelected = $derived(hasSelection && !allSelected);

	function toggle(id: string) {
		const next = new Set(selected);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selected = next;
	}

	function toggleAll() {
		if (selected.size === items.length) selected = new Set();
		else selected = new Set(items.map((i) => i.id));
	}
</script>

<section class="mb-8">
  <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
		<h2 class="text-base font-semibold text-ink-0">{t('orphanSection.title', { title, count: items.length })}</h2>
		<button
			onclick={onCleanup}
			disabled={selected.size === 0}
      class="min-h-11 px-3 py-1.5 bg-red-600 hover:bg-red-500 text-ink-0 text-xs font-medium rounded-lg disabled:opacity-30 lg:min-h-0"
		>
			{t('orphanSection.cleanSelected', { count: selected.size })}
		</button>
	</div>

	{@render headerNote?.()}

	{#if items.length === 0}
		<div class="text-xs text-ink-2 bg-surface-base border border-line rounded-lg p-4">
			{emptyMessage}
		</div>
	{:else}
    <ResponsiveTable>
      {#snippet cards()}
        <div class="responsive-card-toolbar flex min-h-11 items-center gap-2"><SelectionCheckbox checked={allSelected} indeterminate={partiallySelected} onclick={toggleAll} ariaLabel={t('orphanSection.selectAll', { title })} /><span class="text-xs text-ink-2">{t('orphanSection.selectAll', { title })}</span></div>
        {#each items as item (item.id)}
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
						{@render headers()}
					</tr>
				</thead>
				<tbody>
					{#each items as item (item.id)}
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
	{/if}
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
