<script lang="ts">
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import ActionMenu from '$lib/components/ui/ActionMenu.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';

	interface Snapshot {
		id: string;
		name: string;
		status: string;
		volume_id: string;
		size: number;
		description: string;
		created_at: string | null;
	}

	let {
		snapshots,
		deleting,
		openSnapshotActionMenu,
		selectedIds,
		selectableIds,
		selectionDisabled,
		onToggleSelect,
		onToggleAll,
		onActionMenuOpen,
		onActionMenuClose,
		onDelete,
	}: {
		snapshots: Snapshot[];
		deleting: string | null;
		openSnapshotActionMenu: string | null;
		selectedIds: ReadonlySet<string>;
		selectableIds: ReadonlySet<string>;
		selectionDisabled: boolean;
		onToggleSelect: (id: string) => void;
		onToggleAll: () => void;
		onActionMenuOpen: (id: string) => void;
		onActionMenuClose: () => void;
		onDelete: (id: string, name: string) => void;
	} = $props();
	const selectedSelectableCount = $derived([...selectedIds].filter((id) => selectableIds.has(id)).length);
</script>

{#if snapshots.length === 0}
	<div class="text-center py-16 text-ink-3">
		<p class="text-sm">스냅샷이 없습니다</p>
	</div>
{:else}
	<div class="bg-[#0B1220] border border-line rounded-lg overflow-hidden">
		<div class="grid grid-cols-[32px_1.6fr_1.2fr_80px_140px_110px_56px] px-4 py-2.5 border-b border-line text-[11px] uppercase tracking-wider text-ink-3 font-medium">
			<div><SelectionCheckbox checked={selectableIds.size > 0 && selectedSelectableCount === selectableIds.size} indeterminate={selectedSelectableCount > 0 && selectedSelectableCount < selectableIds.size} disabled={selectionDisabled || selectableIds.size === 0} onclick={onToggleAll} ariaLabel="전체 선택" /></div>
			<div>이름</div>
			<div>원본 볼륨</div>
			<div>크기</div>
			<div>생성됨</div>
			<div>상태</div>
			<div></div>
		</div>
		{#each snapshots as snap (snap.id)}
			<div class="resource-selection-surface grid grid-cols-[32px_1.6fr_1.2fr_80px_140px_110px_56px] px-4 py-3 text-[13px] items-center border-b border-line hover:bg-surface-sunken/30 transition-colors last:border-b-0" data-selected={selectedIds.has(snap.id)}>
				<div><SelectionCheckbox checked={selectedIds.has(snap.id)} disabled={selectionDisabled} onclick={() => onToggleSelect(snap.id)} ariaLabel={`${snap.name || snap.id} 선택`} /></div>
				<div class="min-w-0">
					<div class="text-ink-0 font-medium truncate">{snap.name || snap.id.slice(0, 12)}</div>
					<div class="text-[11px] text-ink-3 font-mono truncate">{snap.id.slice(0, 8)}…</div>
				</div>
				<div class="text-ink-2 font-mono text-[12px] truncate">{snap.volume_id.slice(0, 12)}…</div>
				<div class="text-ink-2 font-mono text-[12px]">{snap.size} GB</div>
				<div class="text-ink-2 text-[12px]">
					{snap.created_at ? new Date(snap.created_at).toLocaleString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}
				</div>
				<div><StatusChip status={snap.status} /></div>
				<div class="flex justify-end" role="none">
					<ActionMenu
						open={openSnapshotActionMenu === snap.id}
						ariaLabel={`${snap.name || snap.id} 스냅샷 작업`}
						onopen={() => onActionMenuOpen(snap.id)}
						onclose={onActionMenuClose}
					>
						<button
							onclick={() => { onActionMenuClose(); onDelete(snap.id, snap.name); }}
							disabled={deleting === snap.id}
							class="w-full text-left px-3 py-1.5 text-[13px] text-red-400 hover:text-red-300 hover:bg-surface-sunken disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
						>
							<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
							</svg>
							{deleting === snap.id ? '삭제 중...' : '삭제'}
						</button>
					</ActionMenu>
				</div>
			</div>
		{/each}
	</div>
{/if}
