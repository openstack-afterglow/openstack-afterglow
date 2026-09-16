<script lang="ts">
	import type { Cluster } from '$lib/types/cluster';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';

	let {
		clusters,
		deleting,
		selectedIds = new Set<string>(),
		selectableIds = new Set<string>(),
		selectionDisabled = false,
		onToggleSelect = () => {},
		onToggleAll = () => {},
		onDelete = async () => {},
		onNavigate,
	}: {
		clusters: Cluster[];
		deleting: string | null;
		selectedIds?: ReadonlySet<string>;
		selectableIds?: ReadonlySet<string>;
		selectionDisabled?: boolean;
		onToggleSelect?: (id: string) => void;
		onToggleAll?: () => void;
		onDelete?: (id: string, name: string) => Promise<void>;
		onNavigate: (id: string) => void;
	} = $props();
	const selectableCount = $derived(selectableIds.size);
	const selectedSelectableCount = $derived([...selectableIds].filter((id) => selectedIds.has(id)).length);
	const allSelected = $derived(selectableCount > 0 && selectedSelectableCount === selectableCount);
	const indeterminate = $derived(selectedSelectableCount > 0 && !allSelected);
</script>

<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="k3s-table__head text-xs uppercase tracking-wide">
				<th class="text-left py-3 pr-3"><div class="inline-flex items-center gap-2"><SelectionCheckbox checked={allSelected} indeterminate={indeterminate} disabled={selectionDisabled} ariaLabel="전체 클러스터 선택" onclick={onToggleAll} /><span>전체 선택</span><span class="k3s-table__selection-count normal-case" aria-live="polite">{selectedSelectableCount}개 선택됨</span></div></th>
				<th class="text-left py-3 pr-6">이름</th>
				<th class="text-left py-3 pr-6">상태</th>
				<th class="text-left py-3 pr-6">마스터</th>
				<th class="text-left py-3 pr-6">워커</th>
				<th class="text-left py-3 pr-6">API 주소</th>
				<th class="text-left py-3 pr-6">생성일</th>
				<th class="text-left py-3"></th>
			</tr>
		</thead>
		<tbody>
			{#each clusters as c (c.id)}
				<tr class="resource-selection-surface k3s-table__row transition-colors" data-selected={selectedIds.has(c.id)}>
					<td class="py-3 pr-3"><SelectionCheckbox checked={selectedIds.has(c.id)} disabled={selectionDisabled || !selectableIds.has(c.id)} ariaLabel={`${c.name} 선택`} onclick={() => onToggleSelect(c.id)} /></td>
					<td class="py-3 pr-6"><button onclick={() => onNavigate(c.id)} class="k3s-table__name font-medium transition-colors text-left max-md:block max-md:max-w-[66vw] max-md:truncate" title={c.name}>{c.name}</button></td>
					<td class="py-3 pr-6"><StatusChip status={c.status} /></td>
					<td class="k3s-table__meta py-3 pr-6 text-xs">{c.master_count}</td>
					<td class="k3s-table__meta py-3 pr-6 text-xs">{c.node_count}</td>
					<td class="k3s-table__meta py-3 pr-6 text-xs font-mono">{c.api_address ?? '-'}</td>
					<td class="k3s-table__meta py-3 pr-6 text-xs">{c.created_at?.slice(0, 10) ?? '-'}</td>
					<td class="py-3"><button onclick={() => onDelete(c.id, c.name)} disabled={deleting === c.id || selectionDisabled} class="k3s-table__delete text-xs disabled:opacity-40 transition-colors">{deleting === c.id ? '삭제 중...' : '삭제'}</button></td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.k3s-table__head {
		border-bottom: 1px solid var(--color-line);
		color: var(--color-ink-2);
	}

	.k3s-table__selection-count,
	.k3s-table__meta {
		color: var(--color-ink-2);
	}

	.k3s-table__row {
		border-bottom: 1px solid color-mix(in oklab, var(--color-line), transparent 45%);
	}

	.k3s-table__row:hover {
		background-color: color-mix(in oklab, var(--color-surface-sunken), transparent 45%);
	}

	.k3s-table__row[data-selected='true'] {
		background-color: var(--accent-soft);
	}

	.k3s-table__name {
		color: var(--color-ink-0);
	}

	.k3s-table__name:hover {
		color: var(--color-accent);
	}

	.k3s-table__delete {
		color: var(--color-state-danger);
	}

	.k3s-table__delete:hover {
		color: color-mix(in oklab, var(--color-state-danger) 88%, var(--color-ink-0));
	}
</style>
