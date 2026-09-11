<script lang="ts">
	import type { Instance } from '$lib/types/compute';
	import InstanceRow from './InstanceRow.svelte';
	import { SelectionCheckbox, TableShell } from '$lib/components/ui';

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
		onAction: (kind: 'console' | 'shelve' | 'unshelve' | 'delete', instance: Instance) => Promise<void>;
		onToggleSelect: (id: string) => void;
		onToggleAll: () => void;
	} = $props();

	const allSelected = $derived(
		selectableIds.size > 0 && [...selectableIds].every((id) => selectedIds.has(id))
	);
	const hasSelection = $derived(selectedIds.size > 0);
	const partiallySelected = $derived(hasSelection && !allSelected);
</script>

<TableShell density="compact" class={hasSelection ? 'has-selection' : ''}>
	<table class="min-w-[64rem]" aria-label="인스턴스 목록">
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
						ariaLabel="전체 선택"
					/>
				</th>
				<th scope="col">이름</th>
				<th scope="col">상태</th>
				<th scope="col">이미지 / 플레이버</th>
				<th scope="col">IP</th>
				<th scope="col">라이브러리</th>
				<th scope="col">전략</th>
				<th scope="col"><span class="sr-only">작업</span></th>
			</tr>
		</thead>
		<tbody>
			{#each instances as inst (inst.id)}
				<InstanceRow
					instance={inst}
					isUnderutilized={underutilized[inst.id] ?? false}
					selected={selectedIds.has(inst.id)}
					selectable={selectableIds.has(inst.id)}
					{selectionDisabled}
					{onSelect}
					{onAction}
					onToggleSelect={() => onToggleSelect(inst.id)}
				/>
			{/each}
		</tbody>
	</table>
</TableShell>

