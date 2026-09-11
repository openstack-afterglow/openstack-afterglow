<script lang="ts" generics="T extends { id: string }">
	import type { Snippet } from 'svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';

	let {
		title,
		items,
		selected = $bindable(new Set<string>()),
		emptyMessage,
		headerNote,
		headers,
		row,
		onCleanup,
	}: {
		title: string;
		items: T[];
		selected?: Set<string>;
		emptyMessage: string;
		headerNote?: Snippet;
		headers: Snippet;
		row: Snippet<[T]>;
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
	<div class="flex items-center justify-between mb-3">
		<h2 class="text-base font-semibold text-ink-0">{title} ({items.length})</h2>
		<button
			onclick={onCleanup}
			disabled={selected.size === 0}
			class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-ink-0 text-xs font-medium rounded-lg disabled:opacity-30"
		>
			선택 {selected.size}개 정리
		</button>
	</div>

	{@render headerNote?.()}

	{#if items.length === 0}
		<div class="text-xs text-ink-3 bg-surface-base border border-line rounded-lg p-4">
			{emptyMessage}
		</div>
	{:else}
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
									ariaLabel={`${title} 전체 선택`}
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
										ariaLabel={`${item.id} 선택`}
									/>
								</div>
							</td>
							{@render row(item)}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
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
