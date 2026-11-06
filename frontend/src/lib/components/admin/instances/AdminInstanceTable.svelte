<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import type { AdminInstance } from '$lib/types/adminInstance';
	import Button from '$lib/components/ui/Button.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { Alert, ResourceIdentifier, TableShell } from '$lib/components/ui';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import type { TableView } from '$lib/utils/tableView.svelte';
	type OwnedInstance = AdminInstance & {
		project_name?: string | null;
		domain_id?: string | null;
		domain_name?: string | null;
		owner_status?: 'known' | 'unknown_owner' | 'deleted_project' | 'deleted_domain';
	};
	let {
		instances,
		view,
		selectedIds,
		selectableIds = new Set(instances.map((instance) => instance.id)),
		selectionDisabled = false,
		onOpen,
		onRecover,
		onToggleSelect,
		onToggleAll,
	}: {
		instances: OwnedInstance[];
		view: TableView<OwnedInstance>;
		selectedIds: ReadonlySet<string>;
		selectableIds?: ReadonlySet<string>;
		selectionDisabled?: boolean;
		onOpen: (inst: AdminInstance) => void;
		onRecover?: (inst: AdminInstance) => void;
		onToggleSelect: (id: string) => void;
		onToggleAll: () => void;
	} = $props();

	const allSelected = $derived(
		selectableIds.size > 0 && [...selectableIds].every((id) => selectedIds.has(id))
	);
	const hasSelection = $derived(selectedIds.size > 0);
	const partiallySelected = $derived(selectableIds.size > 0 && hasSelection && !allSelected);

	let expandedError = $state<string | null>(null);
</script>

{#snippet ownership(instance: OwnedInstance)}
	<div class="text-sm text-ink-2">{instance.project_name || (instance.owner_status === 'deleted_project' ? t('instances.table.deletedProject') : instance.owner_status === 'unknown_owner' || !instance.project_id ? t('instances.table.unknownOwner') : '—')}</div>
	<ResourceIdentifier id={instance.project_id} />
	{#if instance.domain_name || instance.domain_id}
		<div class="mt-1 flex flex-wrap items-center gap-1 text-xs text-ink-2"><span>{t('instances.table.domain')}: {instance.domain_name || (instance.owner_status === 'deleted_domain' ? t('instances.table.deletedDomain') : '—')}</span>{#if instance.domain_id}<ResourceIdentifier id={instance.domain_id} />{/if}</div>
	{:else if instance.owner_status === 'deleted_domain'}
		<p class="text-xs text-ink-2">{t('instances.table.deletedDomain')}</p>
	{/if}
{/snippet}

<ResponsiveTable>
	{#snippet cards()}
		<div class="responsive-card-toolbar min-h-11 text-xs text-ink-2"><SelectionCheckbox checked={allSelected} indeterminate={partiallySelected} disabled={selectionDisabled || selectableIds.size === 0} onclick={onToggleAll} ariaLabel={t('instances.table.selectAll')} />{t('instances.table.selectAll')}</div>
		{#each instances as s, index (s.id)}
			<CompactResourceCard selected={selectedIds.has(s.id)}>
				<div class="flex items-start gap-2" data-tour={index === 0 ? 'admin-compute-row' : undefined}>
					<SelectionCheckbox checked={selectedIds.has(s.id)} disabled={selectionDisabled || !selectableIds.has(s.id)} unavailable={!selectableIds.has(s.id)} title={!selectableIds.has(s.id) ? t('instances.table.unselectable') : undefined} onclick={() => onToggleSelect(s.id)} ariaLabel={t('instances.table.select', { name: s.name || s.id })} />
					<button type="button" data-tour={index === 0 ? 'admin-compute-row-open' : undefined} class="min-h-11 min-w-0 flex-1 line-clamp-2 break-words text-left font-medium text-ink-0 underline-offset-4 hover:text-warm-text-hover hover:underline" title={s.name || s.id} onclick={() => onOpen(s)}>{s.name || s.id.slice(0, 8)}</button><StatusChip status={s.status} kind="server" />
				</div>
				<ResourceIdentifier id={s.id} />
				<div class="space-y-1 break-words text-xs text-ink-2"><p>{t('instances.table.flavor')}: {s.flavor_display_name ?? (s.flavor || '—')}</p><p>{t('instances.table.host')}: {s.host || '—'}</p><p>{t('instances.table.project')}</p>{@render ownership(s)}</div>
				{#snippet actions()}{#if s.status === 'ERROR' && onRecover}<Button variant="secondary" size="sm" onclick={() => onRecover(s)}>{t('instances.table.recover')}</Button>{/if}{/snippet}
				{#snippet details()}<div class="space-y-2 break-words text-xs text-ink-2"><ResourceIdentifier id={s.id} compact={false} /><p>{t('instances.table.createdAt')}: {s.created_at?.slice(0, 10) ?? '—'}</p>{#if s.fault}<p>{s.fault}</p>{/if}</div>{/snippet}
			</CompactResourceCard>
		{/each}
	{/snippet}
<TableShell class={hasSelection ? 'has-selection' : ''}>
	<table class="selection-table w-full text-sm" aria-label={t('instances.page.title')}>
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				<th class="py-2 pr-2 w-8">
					<SelectionCheckbox
						checked={allSelected}
						indeterminate={partiallySelected}
						disabled={selectionDisabled || selectableIds.size === 0}
						onclick={onToggleAll}
						ariaLabel={t('instances.table.selectAll')}
					/>
				</th>
				{#each view.columns as column (column.key)}
					<TableColumnHeader {view} columnKey={column.key} />
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each instances as s, index (s.id)}
				<tr
					class="resource-selection-surface instance-admin-row border-b border-line/50 text-sm transition-colors {selectedIds.has(s.id) ? 'is-selected bg-surface-selected/10' : ''}"
					data-selected={selectedIds.has(s.id)}
					data-tour={index === 0 ? 'admin-compute-row' : undefined}
				>
					<td class="py-2 pr-2">
						<SelectionCheckbox
							checked={selectedIds.has(s.id)}
							disabled={selectionDisabled || !selectableIds.has(s.id)}
							unavailable={!selectableIds.has(s.id)}
							title={!selectableIds.has(s.id) ? t('instances.table.unselectable') : undefined}
							onclick={() => onToggleSelect(s.id)}
							ariaLabel={t('instances.table.select', { name: s.name || s.id })}
						/>
					</td>
					<td class="p-0">
						<button type="button" data-tour={index === 0 ? 'admin-compute-row-open' : undefined} onclick={() => onOpen(s)} class="block w-full py-1 pr-4 font-medium text-ink-0 underline-offset-4 hover:text-warm-text-hover hover:underline transition-colors text-left" title={s.name || s.id}><span class="block max-w-56 truncate">{s.name || s.id.slice(0, 8)}</span></button>
						<ResourceIdentifier id={s.id} />
					</td>
					<td class="py-2 pr-4">
						<div class="flex items-center gap-1.5">
							<StatusChip status={s.status} kind="server" />
							{#if s.status === 'ERROR' && s.fault}
								<Button
									onclick={(e) => { e.stopPropagation(); expandedError = expandedError === s.id ? null : s.id; }}
									variant="link" size="sm"
									title={s.fault}
								>{t('instances.table.reason')}</Button>
							{/if}
							{#if s.status === 'ERROR' && onRecover}
								<Button
									onclick={(e) => { e.stopPropagation(); onRecover(s); }}
									variant="link" size="sm"
									title={t('instances.table.recoveryHelp')}
								>{t('instances.table.recover')}</Button>
							{/if}
						</div>
						{#if expandedError === s.id && s.fault}
							<Alert tone="danger" class="mt-1 max-w-xs break-words">{s.fault}</Alert>
						{/if}
					</td>
					<td class="py-2 pr-4 text-ink-2">{s.flavor_display_name ?? (s.flavor || '-')}</td>
					<td class="py-2 pr-4 text-ink-2">{s.host || '-'}</td>
					<td class="py-2 pr-4">
						{@render ownership(s)}
					</td>
					<td class="py-2 text-ink-2">{s.created_at?.slice(0, 10) ?? '-'}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</TableShell>
</ResponsiveTable>

