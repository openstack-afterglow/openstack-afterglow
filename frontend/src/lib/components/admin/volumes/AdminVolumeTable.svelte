<script lang="ts">
	import { projectNames } from '$lib/stores/projectNames';
	import { formatNumber } from '$lib/utils/format';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import ActionMenu from '$lib/components/ui/ActionMenu.svelte';

	interface AdminVolume {
		id: string;
		name: string;
		status: string;
		size: number;
		project_id: string | null;
		created_at: string | null;
		bootable?: boolean;
	}

	let {
		volumes,
		selectedVolumeId,
		openActionMenu,
		copiedProjectId,
		onSelect,
		onActionMenuOpen,
		onActionMenuClose,
		onCopyProjectId,
		onEdit,
		onExtend,
		onTransfer,
		onReset,
		onForceDelete,
		onDelete,
		onBootFromVolume,
	}: {
		volumes: AdminVolume[];
		selectedVolumeId: string | null;
		openActionMenu: string | null;
		copiedProjectId: string | null;
		onSelect: (id: string) => void;
		onActionMenuOpen: (id: string) => void;
		onActionMenuClose: () => void;
		onCopyProjectId: (id: string) => void;
		onEdit: (v: AdminVolume) => void;
		onExtend: (v: AdminVolume) => void;
		onTransfer: (v: AdminVolume) => void;
		onReset: (v: AdminVolume) => void;
		onForceDelete: (v: AdminVolume) => void;
		onDelete: (v: AdminVolume) => void;
		onBootFromVolume: (v: AdminVolume) => void;
	} = $props();
</script>

<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				<th class="text-left py-2 pr-4">이름</th>
				<th class="text-left py-2 pr-4">상태</th>
				<th class="text-left py-2 pr-4">크기</th>
				<th class="text-left py-2 pr-4">프로젝트</th>
				<th class="text-left py-2 pr-4">생성일</th>
				<th class="text-left py-2">액션</th>
			</tr>
		</thead>
		<tbody>
			{#each volumes as v, index (v.id)}
				<tr
					class="border-b border-line/50 text-xs transition-colors {selectedVolumeId === v.id ? 'bg-surface-sunken/50' : ''}"
					data-tour={index === 0 ? 'admin-storage-row' : undefined}
				>
					<td class="p-0">
						<button type="button" data-tour={index === 0 ? 'admin-storage-row-open' : undefined} onclick={() => onSelect(v.id)} class="block w-full py-2 pr-4 font-medium text-ink-0 hover:text-action-warm-hover transition-colors text-left" title={v.name || v.id}><span class="max-md:block max-md:max-w-[66vw] max-md:truncate">{v.name || v.id.slice(0, 8)}</span></button>
					</td>
					<td class="py-2 pr-4"><StatusChip status={v.status} /></td>
					<td class="py-2 pr-4 text-ink-2">{formatNumber(v.size)} GB</td>
					<td class="py-2 pr-4">
						<button
							onclick={(e) => { e.stopPropagation(); if (v.project_id) onCopyProjectId(v.project_id); }}
							class="text-ink-2 hover:text-action-warm-hover transition-colors cursor-pointer text-left"
							title={v.project_id ?? ''}
						>
							{#if copiedProjectId === v.project_id}
								<span class="text-green-400 text-xs">복사됨</span>
							{:else}
								<span class="text-xs">{v.project_id ? ($projectNames.get(v.project_id) ?? v.project_id.slice(0, 8)) : '-'}</span>
							{/if}
						</button>
					</td>
					<td class="py-2 pr-4 text-ink-3">{v.created_at?.slice(0, 10) ?? '-'}</td>
					<td class="py-2" onclick={(e) => e.stopPropagation()}>
						<div class="flex justify-end">
							<ActionMenu
								open={openActionMenu === v.id}
								ariaLabel={`${v.name || v.id} 볼륨 작업`}
								onopen={() => onActionMenuOpen(v.id)}
								onclose={onActionMenuClose}
							>
								<button
									onclick={() => { onActionMenuClose(); onEdit(v); }}
									class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors"
								>수정</button>
								<button
									onclick={() => { onActionMenuClose(); onExtend(v); }}
									class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors"
								>확장</button>
								{#if v.status === 'available' && v.bootable}
									<button
										onclick={() => { onActionMenuClose(); onBootFromVolume(v); }}
										class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors"
									>이 볼륨으로 VM 생성</button>
								{/if}
								{#if v.status === 'available'}
									<button
										onclick={() => { onActionMenuClose(); onTransfer(v); }}
										class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors"
									>이전</button>
								{/if}
								<button
									onclick={() => { onActionMenuClose(); onReset(v); }}
									class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors"
								>상태변경</button>
								{#if /^(error|deleting)/i.test(v.status ?? '')}
									<button
										onclick={() => { onActionMenuClose(); onSelect(v.id); }}
										class="volume-recovery-action w-full text-left px-3 py-1.5 text-[13px] transition-colors"
									>복구 진단</button>
									<button
										onclick={() => { onActionMenuClose(); onForceDelete(v); }}
										class="w-full text-left px-3 py-1.5 text-[13px] text-rose-400 hover:text-rose-300 hover:bg-surface-sunken transition-colors"
									>강제삭제</button>
								{/if}
								<button
									onclick={() => { onActionMenuClose(); onDelete(v); }}
									class="w-full text-left px-3 py-1.5 text-[13px] text-red-400 hover:text-red-300 hover:bg-surface-sunken transition-colors"
								>삭제</button>
							</ActionMenu>
						</div>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.volume-recovery-action {
		color: var(--color-state-warning);
	}

	.volume-recovery-action:hover {
		color: color-mix(in oklab, var(--color-state-warning) 82%, var(--color-ink-0));
		background: var(--color-surface-sunken);
	}
</style>
