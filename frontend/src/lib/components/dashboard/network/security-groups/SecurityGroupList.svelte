<script lang="ts">
	import type { SecurityGroup } from '$lib/types/securityGroup';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';

	let {
		groups,
		selectedSg = $bindable(),
		selectedIds,
		selectableIds,
		selectionDisabled,
		onToggleSelect,
		onToggleAll,
	}: {
		groups: SecurityGroup[];
		selectedSg: string | null;
		selectedIds: ReadonlySet<string>;
		selectableIds: ReadonlySet<string>;
		selectionDisabled: boolean;
		onToggleSelect: (id: string) => void;
		onToggleAll: () => void;
	} = $props();
	const selectedCount = $derived([...selectableIds].filter((id) => selectedIds.has(id)).length);
	const allSelected = $derived(selectableIds.size > 0 && selectedCount === selectableIds.size);
	const indeterminate = $derived(selectedCount > 0 && !allSelected);
</script>

<div class="flex items-center justify-end mb-2">
	<SelectionToolbar
		label="보안 그룹"
		ariaLabel="보안 그룹 전체 선택"
		checked={allSelected}
		indeterminate={indeterminate}
		selectedCount={selectedCount}
		disabled={selectionDisabled || selectableIds.size === 0}
		onToggle={onToggleAll}
	/>
</div>
<div class="flex flex-col gap-2">
	{#each groups as sg (sg.id)}
		<article
			class="resource-selection-surface p-3.5 rounded-lg border transition-colors {selectedSg === sg.name ? 'bg-action-warm/10 border-action-warm' : 'bg-[#0B1220] border-line hover:border-line-2'}"
			data-selected={selectedIds.has(sg.id)}
		>
			<div class="flex items-center gap-2">
				<SelectionCheckbox
					checked={selectedIds.has(sg.id)}
					disabled={selectionDisabled || sg.name === 'default'}
					unavailable={sg.name === 'default'}
					title={sg.name === 'default' ? '기본 보안 그룹은 삭제할 수 없습니다' : undefined}
					ariaLabel={`${sg.name} 선택`}
					onclick={() => onToggleSelect(sg.id)}
				/>
				<button
					type="button"
					onclick={() => selectedSg = sg.name}
					class="flex items-center gap-2 flex-1 min-w-0 text-left"
				>
				<div class="shrink-0 w-6 h-6 rounded-md {selectedSg === sg.name ? 'bg-action-warm/20 border border-action-warm/40' : 'bg-surface-sunken border border-line-2'} flex items-center justify-center">
					<svg class="w-3 h-3 {selectedSg === sg.name ? 'text-action-warm' : 'text-ink-2'}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
					</svg>
				</div>
				<div class="text-ink-0 font-medium text-[13px] font-mono truncate">{sg.name}</div>
				<span class="ml-auto text-[11px] text-ink-3 shrink-0">{sg.rules?.length ?? 0}</span>
				</button>
			</div>
			{#if sg.description}
				<div class="text-[11px] text-ink-2 mt-1.5 leading-snug truncate">{sg.description}</div>
			{/if}
		</article>
	{/each}
</div>
