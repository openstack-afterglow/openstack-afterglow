<script lang="ts">
	import { projectNames } from '$lib/stores/projectNames';
	import { formatNumber } from '$lib/utils/format';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import ActionMenu from '$lib/components/ui/ActionMenu.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import { t } from '$lib/i18n/ns/admin-storage';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	import type { AdminVolume } from '$lib/types/volume';

	function domainLabel(volume: AdminVolume): string {
		if (volume.owner_status && volume.owner_status !== 'known') return t(`volumeList.owner.${volume.owner_status}`);
		return volume.domain_name || volume.domain_id || t('volumeList.owner.unknown_owner');
	}
	function projectLabel(volume: AdminVolume): string {
		return volume.project_name || (volume.project_id ? ($projectNames.get(volume.project_id) ?? volume.project_id) : t('volumeList.owner.unknown_owner'));
	}

	let {
		volumes,
		selectedVolumeId,
		openActionMenu,
		copiedProjectId,
		selectedIds,
		selectableIds = new Set(volumes.map((volume) => volume.id)),
		selectionDisabled = false,
		onSelect,
		onToggleSelect,
		onToggleAll,
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
		selectedIds: ReadonlySet<string>;
		selectableIds?: ReadonlySet<string>;
		selectionDisabled?: boolean;
		onSelect: (id: string) => void;
		onToggleSelect: (id: string) => void;
		onToggleAll: () => void;
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

	const selectedSelectableCount = $derived([...selectedIds].filter((id) => selectableIds.has(id)).length);
	const allSelected = $derived(selectableIds.size > 0 && selectedSelectableCount === selectableIds.size);
	const partiallySelected = $derived(selectedSelectableCount > 0 && !allSelected);
</script>

<ResponsiveTable>
	{#snippet cards()}
		<div class="responsive-card-toolbar min-h-11 text-xs text-ink-2"><SelectionCheckbox checked={allSelected} indeterminate={partiallySelected} disabled={selectionDisabled || selectableIds.size === 0} onclick={onToggleAll} ariaLabel={t('volumeList.selectPage')} />{t('volumeList.selectPage')}</div>
		{#each volumes as v, index (v.id)}
			<CompactResourceCard selected={selectedIds.has(v.id)}>
				<div class="flex items-start gap-2" data-tour={index === 0 ? 'admin-storage-row' : undefined}><SelectionCheckbox checked={selectedIds.has(v.id)} disabled={selectionDisabled || !selectableIds.has(v.id)} unavailable={!selectableIds.has(v.id)} onclick={() => onToggleSelect(v.id)} ariaLabel={t('volumeList.selectVolume', { name: v.name || v.id })} /><button type="button" data-tour={index === 0 ? 'admin-storage-row-open' : undefined} class="min-h-11 min-w-0 flex-1 break-all text-left font-medium text-ink-0" onclick={() => onSelect(v.id)}>{v.name || v.id.slice(0, 8)}</button><StatusChip status={v.status} /></div>
				<p class="break-all text-xs text-ink-2">{formatNumber(v.size)} GiB · {v.volume_type || '—'}</p>
				<p class="break-all text-xs text-ink-2">{domainLabel(v)} · {projectLabel(v)}</p>
				{#snippet actions()}
					<ActionMenu open={openActionMenu === v.id} ariaLabel={t('volumeList.volumeActions', { name: v.name || v.id })} onopen={() => onActionMenuOpen(v.id)} onclose={onActionMenuClose}>
						<Button variant="link" onclick={() => { onActionMenuClose(); onEdit(v); }}>{t('volumeList.action.edit')}</Button>
						<Button variant="link" onclick={() => { onActionMenuClose(); onExtend(v); }}>{t('volumeList.action.extend')}</Button>
						{#if v.status === 'available' && v.bootable}<Button variant="link" onclick={() => { onActionMenuClose(); onBootFromVolume(v); }}>{t('volumeList.action.bootFromVolume')}</Button>{/if}
						{#if v.status === 'available'}<Button variant="link" onclick={() => { onActionMenuClose(); onTransfer(v); }}>{t('volumeList.action.transfer')}</Button>{/if}
						<Button variant="link" onclick={() => { onActionMenuClose(); onReset(v); }}>{t('volumeList.action.resetStatus')}</Button>
						{#if /^(error|deleting)/i.test(v.status ?? '')}<Button variant="link" onclick={() => { onActionMenuClose(); onSelect(v.id); }}>{t('volumeList.action.recovery')}</Button><Button variant="link" onclick={() => { onActionMenuClose(); onForceDelete(v); }}>{t('volumeList.action.forceDelete')}</Button>{/if}
						<Button variant="link" onclick={() => { onActionMenuClose(); onDelete(v); }}>{t('volumeList.action.delete')}</Button>
					</ActionMenu>
				{/snippet}
				{#snippet details()}<div class="space-y-2 break-all text-xs text-ink-2"><p class="font-mono">{v.id}</p><p>{t('volumeList.column.domain')}: {v.domain_id ?? '—'}</p><p>{t('volumeList.column.createdAt')}: {v.created_at?.slice(0, 10) ?? '-'}</p>{#if v.project_id}<Button variant="link" size="sm" onclick={() => onCopyProjectId(v.project_id!)}>{copiedProjectId === v.project_id ? t('volumeList.copied') : v.project_id}</Button>{/if}</div>{/snippet}
			</CompactResourceCard>
		{/each}
	{/snippet}
<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				<th class="py-2 pr-2 w-8">
					<SelectionCheckbox
						checked={allSelected}
						indeterminate={partiallySelected}
						disabled={selectionDisabled || selectableIds.size === 0}
						onclick={onToggleAll}
						ariaLabel={t('volumeList.selectPage')}
					/>
				</th>
				<th class="text-left py-2 pr-4">{t('volumeList.column.name')}</th>
				<th class="text-left py-2 pr-4">{t('volumeList.column.status')}</th>
				<th class="text-left py-2 pr-4">{t('volumeList.column.size')}</th>
				<th class="text-left py-2 pr-4">{t('volumeDetail.volumeType')}</th>
				<th class="text-left py-2 pr-4">{t('volumeList.column.domain')}</th>
				<th class="text-left py-2 pr-4">{t('volumeList.column.project')}</th>
				<th class="text-left py-2 pr-4">{t('volumeList.column.createdAt')}</th>
				<th class="text-left py-2">{t('volumeList.column.actions')}</th>
			</tr>
		</thead>
		<tbody>
			{#each volumes as v, index (v.id)}
				<tr
					class="resource-selection-surface border-b border-line/50 text-xs transition-colors {selectedIds.has(v.id) ? 'is-selected bg-surface-selected/10' : selectedVolumeId === v.id ? 'bg-surface-sunken/50' : ''}"
					data-selected={selectedIds.has(v.id)}
					data-tour={index === 0 ? 'admin-storage-row' : undefined}
				>
					<td class="py-2 pr-2">
						<SelectionCheckbox
							checked={selectedIds.has(v.id)}
							disabled={selectionDisabled || !selectableIds.has(v.id)}
							unavailable={!selectableIds.has(v.id)}
							onclick={() => onToggleSelect(v.id)}
							ariaLabel={t('volumeList.selectVolume', { name: v.name || v.id })}
						/>
					</td>
					<td class="p-0">
						<button type="button" data-tour={index === 0 ? 'admin-storage-row-open' : undefined} onclick={() => onSelect(v.id)} class="block w-full py-2 pr-4 font-medium text-ink-0 hover:text-warm-text-hover transition-colors text-left" title={v.name || v.id}><span class="max-md:block max-md:max-w-[66vw] max-md:truncate">{v.name || v.id.slice(0, 8)}</span></button>
					</td>
					<td class="py-2 pr-4"><StatusChip status={v.status} /></td>
					<td class="py-2 pr-4 text-ink-2">{formatNumber(v.size)} GiB</td>
					<td class="py-2 pr-4 text-ink-2">{v.volume_type || '—'}</td>
					<td class="py-2 pr-4 text-ink-2"><span title={v.domain_id ?? undefined}>{domainLabel(v)}</span></td>
					<td class="py-2 pr-4">
						<button
							onclick={(e) => { e.stopPropagation(); if (v.project_id) onCopyProjectId(v.project_id); }}
							class="text-ink-2 hover:text-warm-text-hover transition-colors cursor-pointer text-left"
							title={v.project_id ?? ''}
						>
							{#if copiedProjectId === v.project_id}
								<span class="text-green-400 text-xs">{t('volumeList.copied')}</span>
							{:else}
								<span class="text-xs">{projectLabel(v)}</span>
							{/if}
						</button>
					</td>
					<td class="py-2 pr-4 text-ink-2">{v.created_at?.slice(0, 10) ?? '-'}</td>
					<td class="py-2" onclick={(e) => e.stopPropagation()}>
						<div class="flex justify-end">
							<ActionMenu
								open={openActionMenu === v.id}
								ariaLabel={t('volumeList.volumeActions', { name: v.name || v.id })}
								onopen={() => onActionMenuOpen(v.id)}
								onclose={onActionMenuClose}
							>
								<button
									onclick={() => { onActionMenuClose(); onEdit(v); }}
									class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors"
								>{t('volumeList.action.edit')}</button>
								<button
									onclick={() => { onActionMenuClose(); onExtend(v); }}
									class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors"
								>{t('volumeList.action.extend')}</button>
								{#if v.status === 'available' && v.bootable}
									<button
										onclick={() => { onActionMenuClose(); onBootFromVolume(v); }}
										class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors"
									>{t('volumeList.action.bootFromVolume')}</button>
								{/if}
								{#if v.status === 'available'}
									<button
										onclick={() => { onActionMenuClose(); onTransfer(v); }}
										class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors"
									>{t('volumeList.action.transfer')}</button>
								{/if}
								<button
									onclick={() => { onActionMenuClose(); onReset(v); }}
									class="w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors"
								>{t('volumeList.action.resetStatus')}</button>
								{#if /^(error|deleting)/i.test(v.status ?? '')}
									<button
										onclick={() => { onActionMenuClose(); onSelect(v.id); }}
										class="volume-recovery-action w-full text-left px-3 py-1.5 text-[13px] transition-colors"
									>{t('volumeList.action.recovery')}</button>
									<button
										onclick={() => { onActionMenuClose(); onForceDelete(v); }}
										class="w-full text-left px-3 py-1.5 text-[13px] text-rose-400 hover:text-rose-300 hover:bg-surface-sunken transition-colors"
									>{t('volumeList.action.forceDelete')}</button>
								{/if}
								<button
									onclick={() => { onActionMenuClose(); onDelete(v); }}
									class="w-full text-left px-3 py-1.5 text-[13px] text-red-400 hover:text-red-300 hover:bg-surface-sunken transition-colors"
								>{t('volumeList.action.delete')}</button>
							</ActionMenu>
						</div>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
</ResponsiveTable>

<style>
	.volume-recovery-action {
		color: var(--color-state-warning);
	}

	.volume-recovery-action:hover {
		color: color-mix(in oklab, var(--color-state-warning) 82%, var(--color-ink-0));
		background: var(--color-surface-sunken);
	}
</style>
