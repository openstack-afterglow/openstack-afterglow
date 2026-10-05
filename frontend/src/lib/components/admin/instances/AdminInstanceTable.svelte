<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-compute';
	import { projectNames } from '$lib/stores/projectNames';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import type { AdminInstance } from '$lib/types/adminInstance';

	let {
		instances,
		markerStack,
		nextMarker,
		refreshing,
		selectedIds,
		selectableIds = new Set(instances.map((instance) => instance.id)),
		selectionDisabled = false,
		onOpen,
		onPrev,
		onNext,
		onintent,
		onRecover,
		onToggleSelect,
		onToggleAll,
	}: {
		instances: AdminInstance[];
		markerStack: string[];
		nextMarker: string | null;
		refreshing: boolean;
		selectedIds: ReadonlySet<string>;
		selectableIds?: ReadonlySet<string>;
		selectionDisabled?: boolean;
		onOpen: (inst: AdminInstance) => void;
		onPrev: () => void;
		onNext: () => void;
		onintent?: () => void;
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
	let copiedProjectId = $state<string | null>(null);

	function copyProjectId(id: string) {
		navigator.clipboard.writeText(id).then(() => {
			copiedProjectId = id;
			setTimeout(() => { copiedProjectId = null; }, 1500);
		});
	}
</script>

<div class="overflow-x-auto">
	<table class="selection-table w-full text-sm">
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
				<th class="text-left py-2 pr-4">{t('instances.table.name')}</th>
				<th class="text-left py-2 pr-4">{t('instances.table.status')}</th>
				<th class="text-left py-2 pr-4">{t('instances.table.flavor')}</th>
				<th class="text-left py-2 pr-4">{t('instances.table.host')}</th>
				<th class="text-left py-2 pr-4">{t('instances.table.project')}</th>
				<th class="text-left py-2">{t('instances.table.createdAt')}</th>
			</tr>
		</thead>
		<tbody>
			{#each instances as s, index (s.id)}
				<tr
					class="resource-selection-surface instance-admin-row border-b border-line/50 text-xs transition-colors {selectedIds.has(s.id) ? 'is-selected bg-surface-selected/10' : ''}"
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
						<button type="button" data-tour={index === 0 ? 'admin-compute-row-open' : undefined} onclick={() => onOpen(s)} class="block w-full py-2 pr-4 font-medium text-ink-0 hover:text-warm-text-hover transition-colors text-left" title={s.name || s.id}><span class="max-md:block max-md:max-w-[66vw] max-md:truncate">{s.name || s.id.slice(0, 8)}</span></button>
					</td>
					<td class="py-2 pr-4">
						<div class="flex items-center gap-1.5">
							<StatusChip status={s.status} />
							{#if s.status === 'ERROR' && s.fault}
								<button
									onclick={(e) => { e.stopPropagation(); expandedError = expandedError === s.id ? null : s.id; }}
									class="text-red-500 hover:text-red-300 text-xs underline"
									title={s.fault}
								>{t('instances.table.reason')}</button>
							{/if}
							{#if s.status === 'ERROR' && onRecover}
								<button
									onclick={(e) => { e.stopPropagation(); onRecover(s); }}
									class="text-warm-text hover:text-warm-text-hover text-xs underline"
									title={t('instances.table.recoveryHelp')}
								>{t('instances.table.recover')}</button>
							{/if}
						</div>
						{#if expandedError === s.id && s.fault}
							<div class="mt-1 text-red-400 bg-red-900/20 border border-red-900/50 rounded px-2 py-1 text-xs max-w-xs break-words">
								{s.fault}
							</div>
						{/if}
					</td>
					<td class="py-2 pr-4 text-ink-2">{s.flavor || '-'}</td>
					<td class="py-2 pr-4 text-ink-2">{s.host || '-'}</td>
					<td class="py-2 pr-4">
						<button
							onclick={(e) => { e.stopPropagation(); if (s.project_id) copyProjectId(s.project_id); }}
							class="text-ink-2 hover:text-warm-text-hover transition-colors cursor-pointer text-left"
							title={s.project_id ?? ''}
						>
							{#if copiedProjectId === s.project_id}
								<span class="text-green-400 text-xs">{t('instances.table.copied')}</span>
							{:else}
								<span class="text-xs">{s.project_id ? ($projectNames.get(s.project_id) ?? s.project_id.slice(0, 8)) : '-'}</span>
							{/if}
						</button>
					</td>
					<td class="py-2 text-ink-2">{s.created_at?.slice(0, 10) ?? '-'}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<Pagination
	page={markerStack.length + 1}
	hasPrev={markerStack.length > 0}
	hasNext={!!nextMarker}
	{onPrev}
	{onNext}
	{onintent}
/>
