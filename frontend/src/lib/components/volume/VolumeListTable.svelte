<script lang="ts">
	import type { Volume } from '$lib/types/volume';
	import { formatStorage } from '$lib/utils/format';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import ActionMenu from '$lib/components/ui/ActionMenu.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	let {
		volumes,
		selectedVolumeId,
		deleting,
		autoBackupConfigs,
		autoBackupToggling,
		openActionMenu,
		selectedIds,
		selectableIds,
		selectionDisabled = false,
		onToggleSelect,
		onToggleAll,
		volumeBackupsEnabled = true,
		volumeSnapshotsEnabled = true,
		isSystemAdmin,
		onOpenDetail,
		onActionMenuOpen,
		onActionMenuClose,
		onBoot,
		onExtend,
		onBackup,
		onSnapshot,
		onTransfer,
		onForceDelete,
		onDelete,
		onToggleAutoBackup,
	}: {
		volumes: Volume[];
		selectedVolumeId: string | null;
		deleting: string | null;
		autoBackupConfigs: Set<string>;
		autoBackupToggling: string | null;
		openActionMenu: string | null;
		selectedIds: ReadonlySet<string>;
		selectableIds: ReadonlySet<string>;
		selectionDisabled?: boolean;
		onToggleSelect: (id: string) => void;
		onToggleAll: () => void;
		volumeBackupsEnabled?: boolean;
		volumeSnapshotsEnabled?: boolean;
		isSystemAdmin: boolean;
		onOpenDetail: (id: string) => void;
		onActionMenuOpen: (id: string) => void;
		onActionMenuClose: () => void;
		onBoot: (vol: Volume) => void;
		onExtend: (vol: Volume) => void;
		onBackup: (vol: Volume) => void;
		onSnapshot: (vol: Volume) => void;
		onTransfer: (id: string, name: string) => void;
		onForceDelete: (id: string, name: string) => void;
		onDelete: (id: string, name: string) => void;
		onToggleAutoBackup: (id: string) => void;
	} = $props();

	const volumeGridClass = $derived(volumeBackupsEnabled
		? 'grid grid-cols-[32px_1fr_60px_0px_32px_0px_0px_0px_0px] sm:grid-cols-[32px_1.6fr_70px_90px_100px_0px_0px_0px_0px] lg:grid-cols-[32px_1.6fr_70px_90px_100px_1fr_80px_80px_56px]'
		: 'grid grid-cols-[32px_1fr_60px_0px_32px_0px_0px_0px] sm:grid-cols-[32px_1.6fr_70px_90px_100px_0px_0px_0px] lg:grid-cols-[32px_1.6fr_70px_90px_100px_1fr_80px_56px]');
	const selectedSelectableCount = $derived([...selectedIds].filter((id) => selectableIds.has(id)).length);
</script>

<div class="bg-[#0B1220] border border-line rounded-lg overflow-hidden">
	<div class="{volumeGridClass} px-4 py-2.5 border-b border-line text-[11px] uppercase tracking-wider text-ink-3 font-medium">
		<div><SelectionCheckbox checked={selectableIds.size > 0 && selectedSelectableCount === selectableIds.size} indeterminate={selectedSelectableCount > 0 && selectedSelectableCount < selectableIds.size} disabled={selectionDisabled || selectableIds.size === 0} onclick={onToggleAll} ariaLabel="전체 선택" /></div>
		<div>이름</div>
		<div>크기</div>
		<div class="hidden sm:block">유형</div>
		<div class="whitespace-nowrap">상태</div>
		<div class="hidden lg:block">연결</div>
		<div class="hidden lg:block">부트</div>
		{#if volumeBackupsEnabled}<div class="hidden lg:block text-center whitespace-nowrap">자동 백업</div>{/if}
		<div class="hidden lg:block"></div>
	</div>
	{#each volumes as vol (vol.id)}
		<div
			class="resource-selection-surface {volumeGridClass} px-4 py-3 text-[13px] items-center border-b border-line transition-colors last:border-b-0 {selectedVolumeId === vol.id ? 'bg-surface-sunken/30' : ''}"
			data-selected={selectedIds.has(vol.id)}
		>
			<SelectionCheckbox
				checked={selectedIds.has(vol.id)}
				disabled={selectionDisabled || !selectableIds.has(vol.id)}
				unavailable={!selectableIds.has(vol.id)}
				ariaLabel={`${vol.name || vol.id.slice(0, 8)} 선택`}
				title={vol.attachments.length > 0 ? '연결된 볼륨은 삭제할 수 없습니다' : undefined}
				onclick={() => onToggleSelect(vol.id)}
			/>
			<!-- 이름 -->
			<button
				type="button"
				onclick={() => onOpenDetail(vol.id)}
				class="flex items-center gap-2.5 min-w-0 w-full text-left text-ink-0 hover:text-action-warm-hover transition-colors cursor-pointer"
			>
				<div class="hidden sm:flex shrink-0 w-7 h-7 rounded-md bg-cyan-500/15 border border-cyan-500/30 items-center justify-center">
					<svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
					</svg>
				</div>
				<div class="min-w-0 flex-1">
					{#if vol.name}
						<span class="block font-medium truncate">{vol.name}</span>
					{:else}
						<span class="block font-mono text-xs truncate">{vol.id}</span>
					{/if}
					<div class="text-[11px] text-ink-3 font-mono truncate">{vol.id.slice(0, 8)}…</div>
				</div>
			</button>
			<!-- 크기 -->
			<div class="text-ink-2 font-mono text-[12px]">{formatStorage(vol.size)}</div>
			<!-- 유형 -->
			<div class="hidden sm:block">
				<span class="text-[11px] px-2 py-0.5 rounded-md bg-surface-sunken border border-line-2 text-ink-2 font-mono">
					{vol.volume_type ?? '기본'}
				</span>
			</div>
			<!-- 상태 -->
			<div><StatusChip status={vol.status} /></div>
			<!-- 연결 -->
			<div class="hidden lg:block text-[12px]">
				{#if vol.attachments.length > 0}
					<span class="text-action-warm">{vol.attachments.length}개 연결</span>
				{:else}
					<span class="text-ink-3">미연결</span>
				{/if}
			</div>
			<!-- 부트 -->
			<div class="hidden lg:flex flex-col gap-0.5">
				{#if vol.bootable}
					<span class="text-[11px] px-2 py-0.5 rounded-md bg-surface-selected/30 border border-action-warm text-action-warm w-fit">부트</span>
					{#if vol.volume_image_metadata?.os_distro}
						<span class="text-[10px] text-ink-3 font-mono">{vol.volume_image_metadata.os_distro}{vol.volume_image_metadata.os_version ? ' ' + vol.volume_image_metadata.os_version : ''}</span>
					{/if}
				{/if}
			</div>
			{#if volumeBackupsEnabled}
				<!-- 자동 백업 토글 -->
				<div class="hidden lg:flex justify-center" onclick={(e) => e.stopPropagation()} role="none">
					<button
						onclick={(e) => { e.stopPropagation(); onToggleAutoBackup(vol.id); }}
						disabled={autoBackupToggling === vol.id}
						title={autoBackupConfigs.has(vol.id) ? '자동 백업 비활성화' : '자동 백업 활성화'}
						class="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out disabled:opacity-50 {autoBackupConfigs.has(vol.id) ? 'bg-action-warm' : 'bg-surface-selected'}"
					>
						<span class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-surface-base shadow ring-0 transition duration-200 ease-in-out {autoBackupConfigs.has(vol.id) ? 'translate-x-4' : 'translate-x-0'}"></span>
					</button>
				</div>
			{/if}
			<!-- 액션 드롭다운 -->
			<div class="hidden lg:flex justify-end" role="none">
				<ActionMenu
					open={openActionMenu === vol.id}
					ariaLabel={`${vol.name || vol.id} 볼륨 작업`}
					onopen={() => onActionMenuOpen(vol.id)}
					onclose={onActionMenuClose}
				>
					<button
						onclick={() => { onActionMenuClose(); onOpenDetail(vol.id); }}
						class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors flex items-center gap-2"
					>
						<svg class="w-3.5 h-3.5 text-action-warm" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
						연결
					</button>
					{#if vol.status === 'available' && vol.bootable}
						<button
							onclick={() => { onActionMenuClose(); onBoot(vol); }}
							class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors flex items-center gap-2"
						>
							<svg class="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3l14 9-14 9V3z" /></svg>
							이 볼륨으로 VM 부팅
						</button>
					{/if}
					{#if vol.status === 'available' || vol.status === 'in-use'}
						<button
							onclick={() => { onActionMenuClose(); onExtend(vol); }}
							class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors flex items-center gap-2"
						>
							<svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" /></svg>
							용량 확장
						</button>
					{/if}
					{#if volumeSnapshotsEnabled}
						<button
							onclick={() => { onActionMenuClose(); onSnapshot(vol); }}
							class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors flex items-center gap-2"
						>
							<svg class="w-3.5 h-3.5 text-action-warm" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
							스냅샷 생성
						</button>
					{/if}
					{#if volumeBackupsEnabled && (vol.status === 'available' || vol.status === 'in-use')}
						<button
							onclick={() => { onActionMenuClose(); onBackup(vol); }}
							class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors flex items-center gap-2"
						>
							<svg class="w-3.5 h-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" /></svg>
							백업 생성
						</button>
					{/if}
					{#if vol.status === 'available'}
						<button
							onclick={() => { onActionMenuClose(); onTransfer(vol.id, vol.name); }}
							class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors flex items-center gap-2"
						>
							<svg class="w-3.5 h-3.5 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" /></svg>
							이전
						</button>
					{/if}
					<div class="border-t border-line my-1"></div>
					{#if (vol.status === 'error' || vol.status === 'error_deleting' || vol.status === 'deleting') && isSystemAdmin}
						<button
							onclick={() => { onActionMenuClose(); onForceDelete(vol.id, vol.name); }}
							disabled={deleting === vol.id || selectionDisabled}
							class="w-full text-left px-3 py-1.5 text-[13px] text-rose-400 hover:text-rose-300 hover:bg-surface-sunken disabled:opacity-50 transition-colors flex items-center gap-2"
						>
							<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
							{deleting === vol.id ? '삭제 중...' : '강제 삭제'}
						</button>
					{/if}
					<button
						onclick={() => { onActionMenuClose(); onDelete(vol.id, vol.name); }}
						disabled={deleting === vol.id || selectionDisabled || vol.attachments.length > 0}
						title={selectionDisabled ? '일괄 작업이 진행 중입니다' : vol.attachments.length > 0 ? '연결된 볼륨은 삭제할 수 없습니다' : ''}
						class="w-full text-left px-3 py-1.5 text-[13px] text-red-400 hover:text-red-300 hover:bg-surface-sunken disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
					>
						<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
						{deleting === vol.id ? '삭제 중...' : '삭제'}
					</button>
				</ActionMenu>
			</div>
		</div>
	{/each}
</div>
