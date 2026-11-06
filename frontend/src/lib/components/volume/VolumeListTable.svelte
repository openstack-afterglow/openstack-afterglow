<script lang="ts">
 import TableColumnControl from '$lib/components/ui/TableColumnControl.svelte';
	import { t } from '$lib/i18n/ns/volume';
	import type { Volume } from '$lib/types/volume';
	import { formatStorage } from '$lib/utils/format';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import ActionMenu from '$lib/components/ui/ActionMenu.svelte';
	import VolumeOperationItems from '$lib/components/volume/VolumeOperationItems.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { ResourceIdentifier } from '$lib/components/ui';
	import type { TableView } from '$lib/utils/tableView.svelte';
	let {
		volumes,
		view,
		selectedVolumeId,
		deleting,
		openActionMenu,
		selectedIds,
		selectableIds,
		selectionDisabled = false,
		onToggleSelect,
		onToggleAll,
		volumeSnapshotsEnabled = true,
		isSystemAdmin,
		onOpenDetail,
		onActionMenuOpen,
		onActionMenuClose,
		onRename,
		onBoot,
		onExtend,
		onBackup,
		onSnapshot,
		onTransfer,
		onForceDelete,
		onDelete,
	}: {
		volumes: Volume[];
		view: TableView<Volume>;
		selectedVolumeId: string | null;
		deleting: string | null;
		openActionMenu: string | null;
		selectedIds: ReadonlySet<string>;
		selectableIds: ReadonlySet<string>;
		selectionDisabled?: boolean;
		onToggleSelect: (id: string) => void;
		onToggleAll: () => void;
		volumeSnapshotsEnabled?: boolean;
		isSystemAdmin: boolean;
		onOpenDetail: (id: string) => void;
		onActionMenuOpen: (id: string) => void;
		onActionMenuClose: () => void;
		onRename: (vol: Volume) => void;
		onBoot: (vol: Volume) => void;
		onExtend: (vol: Volume) => void;
		onBackup: (vol: Volume) => void;
		onSnapshot: (vol: Volume) => void;
		onTransfer: (id: string, name: string) => void;
		onForceDelete: (id: string, name: string) => void;
		onDelete: (id: string, name: string) => void;
	} = $props();

	const volumeGridClass = 'grid min-w-[72rem] grid-cols-[32px_minmax(220px,1.6fr)_112px_112px_136px_minmax(160px,1fr)_112px_100px_44px] gap-2';
	const selectedSelectableCount = $derived([...selectedIds].filter((id) => selectableIds.has(id)).length);
</script>

{#snippet volumeActions(vol: Volume)}
	<ActionMenu
		open={openActionMenu === vol.id}
		ariaLabel={t('listTable.volumeActions', { name: vol.name || vol.id })}
		onopen={() => onActionMenuOpen(vol.id)}
		onclose={onActionMenuClose}
	>
		<button
			onclick={() => { onActionMenuClose(); onOpenDetail(vol.id); }}
			class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors flex items-center gap-2"
		>
			<svg class="w-3.5 h-3.5 text-warm-text" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
			{t('listTable.attach')}
		</button>
		<VolumeOperationItems
			volume={vol}
			onclose={onActionMenuClose}
			{onRename} {onBoot} {onExtend} {onBackup} {onSnapshot}
			onTransfer={(v) => onTransfer(v.id, v.name)}
			onForceDelete={(v) => onForceDelete(v.id, v.name)}
			onDelete={(v) => onDelete(v.id, v.name)}
			{volumeSnapshotsEnabled} {isSystemAdmin}
			deleting={deleting === vol.id}
			{selectionDisabled}
		/>
	</ActionMenu>
{/snippet}

<ResponsiveTable>
	{#snippet cards()}
		<div class="responsive-card-toolbar">
			<SelectionCheckbox checked={selectableIds.size > 0 && selectedSelectableCount === selectableIds.size} indeterminate={selectedSelectableCount > 0 && selectedSelectableCount < selectableIds.size} disabled={selectionDisabled || selectableIds.size === 0} onclick={onToggleAll} ariaLabel={t('listTable.selectAll')} />
			<span class="text-xs text-ink-2">{t('listTable.selectAll')}</span>
		</div>
		{#each volumes as vol (vol.id)}
			<CompactResourceCard selected={selectedIds.has(vol.id)} class={selectedVolumeId === vol.id ? 'ring-1 ring-line-2' : ''}>
				<div class="flex items-start gap-2 min-w-0">
					<SelectionCheckbox checked={selectedIds.has(vol.id)} disabled={selectionDisabled || !selectableIds.has(vol.id)} unavailable={!selectableIds.has(vol.id)} ariaLabel={t('listTable.selectVolume', { name: vol.name || vol.id.slice(0, 8) })} title={vol.attachments.length > 0 ? t('listTable.attachedDeleteUnavailable') : undefined} onclick={() => onToggleSelect(vol.id)} />
					<button type="button" onclick={() => onOpenDetail(vol.id)} class="min-w-0 flex-1 min-h-11 text-left font-medium text-ink-0 hover:text-warm-text-hover break-all">{vol.name || vol.id}</button>
					<StatusChip status={vol.status} kind="volume" />
				</div>
				{#if deleting === vol.id}<span class="inline-flex items-center gap-1 text-xs text-state-danger-text"><LoadingState variant="control" label="" />{t('operationItems.deleting')}</span>{/if}
				<ResourceIdentifier id={vol.id} />
				<dl>
					<div><dt>{t('listTable.size')}</dt><dd>{formatStorage(vol.size)}</dd></div>
					<div><dt>{t('listTable.type')}</dt><dd>{vol.volume_type ?? t('listTable.defaultType')}</dd></div>
					<div><dt>{t('listTable.attachments')}</dt><dd>{vol.attachments.length > 0 ? t('listTable.attachmentCount', { count: vol.attachments.length }) : t('listTable.unattached')}</dd></div>
				</dl>
				{#snippet details()}
					{#if vol.bootable}
						<p>{t('listTable.boot')}{#if vol.volume_image_metadata?.os_distro} · {vol.volume_image_metadata.os_distro}{vol.volume_image_metadata.os_version ? ' ' + vol.volume_image_metadata.os_version : ''}{/if}</p>
					{/if}
				{/snippet}
				{#snippet actions()}
					<a href={`/dashboard/volumes/backups?auto-backup=${encodeURIComponent(vol.id)}`} class="inline-flex items-center min-h-11 text-xs text-warm-text hover:text-warm-text-hover">{t('autoPolicy.settings')}</a>
					{@render volumeActions(vol)}
				{/snippet}
			</CompactResourceCard>
		{/each}
	{/snippet}
<div class="min-w-0 max-w-full bg-surface-base border border-line rounded-lg overflow-x-auto" role="region" tabindex="0" aria-label={t('page.title')}>
	<div class="{volumeGridClass} px-4 py-2.5 border-b border-line text-[13px] text-ink-2 font-medium">
		<div><SelectionCheckbox checked={selectableIds.size > 0 && selectedSelectableCount === selectableIds.size} indeterminate={selectedSelectableCount > 0 && selectedSelectableCount < selectableIds.size} disabled={selectionDisabled || selectableIds.size === 0} onclick={onToggleAll} ariaLabel={t('listTable.selectAll')} /></div>
		<div><TableColumnControl {view} columnKey="name" /></div>
		<div class="text-right"><TableColumnControl {view} columnKey="size" /></div>
		<div class="hidden sm:block"><TableColumnControl {view} columnKey="type" /></div>
		<div class="whitespace-nowrap"><TableColumnControl {view} columnKey="status" /></div>
		<div class="hidden lg:block"><TableColumnControl {view} columnKey="attachments" /></div>
		<div class="hidden lg:block"><TableColumnControl {view} columnKey="bootable" /></div>
		<div class="hidden lg:block text-center whitespace-nowrap">{t('listTable.autoBackup')}</div>
		<div class="hidden lg:block"></div>
	</div>
	{#each volumes as vol (vol.id)}
		<div
			class="resource-selection-surface {volumeGridClass} min-h-11 px-4 py-1 text-sm items-center border-b border-line transition-colors last:border-b-0 {selectedVolumeId === vol.id ? 'bg-surface-sunken/30' : ''}"
			data-selected={selectedIds.has(vol.id)}
		>
			<SelectionCheckbox
				checked={selectedIds.has(vol.id)}
				disabled={selectionDisabled || !selectableIds.has(vol.id)}
				unavailable={!selectableIds.has(vol.id)}
				ariaLabel={t('listTable.selectVolume', { name: vol.name || vol.id.slice(0, 8) })}
				title={vol.attachments.length > 0 ? t('listTable.attachedDeleteUnavailable') : undefined}
				onclick={() => onToggleSelect(vol.id)}
			/>
			<!-- 이름 -->
			<div class="min-w-0 flex items-center gap-2">
				<button type="button" onclick={() => onOpenDetail(vol.id)} class="min-w-0 flex-1 text-left font-medium text-ink-0 hover:text-warm-text-hover truncate" title={vol.name || vol.id}>{vol.name || vol.id.slice(0, 8)}</button>
				<ResourceIdentifier id={vol.id} class="shrink-0" />
				{#if deleting === vol.id}<span class="inline-flex items-center gap-1 text-xs text-state-danger-text"><LoadingState variant="control" label="" />{t('operationItems.deleting')}</span>{/if}
			</div>
			<!-- 크기 -->
			<div class="text-right text-ink-1 tabular-nums">{formatStorage(vol.size)}</div>
			<!-- 유형 -->
			<div class="hidden sm:block">
				<span class="text-[13px] text-ink-2">
					{vol.volume_type ?? t('listTable.defaultType')}
				</span>
			</div>
			<!-- 상태 -->
			<div><StatusChip status={vol.status} kind="volume" /></div>
			<!-- 연결 -->
			<div class="hidden lg:block text-xs">
				{#if vol.attachments.length > 0}
					<span class="text-warm-text">{t('listTable.attachmentCount', { count: vol.attachments.length })}</span>
				{:else}
					<span class="text-ink-2">{t('listTable.unattached')}</span>
				{/if}
			</div>
			<!-- 부트 -->
			<div class="hidden lg:flex flex-col gap-0.5">
				{#if vol.bootable}
					<span class="text-xs px-2 py-0.5 rounded-md bg-surface-selected/30 border border-action-warm text-warm-text w-fit">{t('listTable.boot')}</span>
					{#if vol.volume_image_metadata?.os_distro}
						<span class="text-xs text-ink-2 font-mono">{vol.volume_image_metadata.os_distro}{vol.volume_image_metadata.os_version ? ' ' + vol.volume_image_metadata.os_version : ''}</span>
					{/if}
				{/if}
			</div>
			<!-- 자동 백업 설정 -->
			<div class="hidden lg:flex items-center justify-center">
				<a
					href={`/dashboard/volumes/backups?auto-backup=${encodeURIComponent(vol.id)}`}
					class="w-full min-w-0 whitespace-normal break-words text-xs text-center text-warm-text hover:text-warm-text-hover transition-colors"
				>
					{t('autoPolicy.settings')}
				</a>
			</div>
			<!-- 액션 드롭다운 -->
			<div class="flex justify-end" role="none">
				{@render volumeActions(vol)}
			</div>
		</div>
	{/each}
</div>
</ResponsiveTable>
