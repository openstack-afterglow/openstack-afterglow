<script lang="ts">
	import { t } from '$lib/i18n/ns/object-storage';
	import { t as commonT } from '$lib/i18n/ns/common';
	import { untrack } from 'svelte';
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import FileIcon from '$lib/components/ui/FileIcon.svelte';
	import { formatObjectSize, formatDate, shortContentType } from '$lib/utils/format';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import { createArrivals } from './arrivals';

	// Rows fade in only the first time their name renders in this container (initial load, a newly
	// opened folder, an upload). Manual refresh, polling and filter typing remount rows that were
	// already shown — including rows of previously visited prefixes and re-expanded folders — without
	// replaying the entrance. Pass a parent-owned tracker so it also survives view switches that
	// unmount this table.
	let { arrivals = createArrivals() }: { arrivals?: ReturnType<typeof createArrivals> } = $props();

	const s = useObjectBrowser();
	const downloadPendingLabel = $derived(`${t('views.treeTable.download')}: ${commonT('state.processing')}`);
	let tableRef = $state<HTMLTableElement | null>(null);

	let arrivalContainer = untrack(() => s.containerName);
	$effect.pre(() => {
		const name = s.containerName;
		if (name === arrivalContainer) return;
		arrivalContainer = name;
		arrivals.reset();
	});
</script>

{#if s.loading}
	<LoadingSkeleton variant="table" rows={5} />
{:else if s.treeRows.length === 0}
	<div class="text-ink-2 text-sm py-8 text-center">
		<svg class="w-12 h-12 mx-auto text-ink-2 mb-3" viewBox="0 0 20 20" fill="currentColor">
			<path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/>
		</svg>
		{#if s.filterText.trim()}
			<p>{t('views.treeTable.noResults')}</p>
			<p class="text-ink-2 text-xs mt-1">{t('views.treeTable.searchHint')}</p>
		{:else}
			<p>{t('views.treeTable.noObjects')}</p>
			<p class="text-ink-2 text-xs mt-1">{t('views.treeTable.emptyHint')}</p>
		{/if}
	</div>
{:else}
	<div class="overflow-x-auto">
		<table class="w-full text-sm table-fixed" bind:this={tableRef}>
			<colgroup>
				<col style="width: 2.5rem" />
				<col style="width: {s.colWidths.name}%" />
				<col style="width: {s.colWidths.bytes}%" />
				<col style="width: {s.colWidths.type}%" />
				<col style="width: {s.colWidths.modified}%" />
				<col style="width: {s.colWidths.action}%" />
			</colgroup>
			<thead>
				<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
					<th class="py-3 px-4 w-10">
						<SelectionCheckbox
							checked={s.visibleSelectedCount > 0 && s.visibleSelectedCount === s.visibleObjectCount}
							indeterminate={s.visibleSelectedCount > 0 && s.visibleSelectedCount < s.visibleObjectCount}
							disabled={s.bulkDeleting || s.bulkMoving}
							ariaLabel={t('views.treeTable.selectAllVisible')}
							onclick={s.toggleSelectAll}
						/>
					</th>
					<th class="text-left py-3 px-4 font-medium relative">
						<button onclick={() => s.toggleSort('name')} class="hover:text-ink-2 transition-colors">{t('views.treeTable.nameSort', { icon: s.sortIcon('name') })}</button>
						<button type="button" aria-label={t('views.treeTable.resizeName')} class="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-indigo-500/40 active:bg-indigo-500/60" onmousedown={(e) => s.onResizeStart(e, 'name', tableRef)}></button>
					</th>
					<th class="text-left py-3 px-4 font-medium relative">
						<button onclick={() => s.toggleSort('bytes')} class="hover:text-ink-2 transition-colors">{t('views.treeTable.sizeSort', { icon: s.sortIcon('bytes') })}</button>
						<button type="button" aria-label={t('views.treeTable.resizeSize')} class="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-indigo-500/40 active:bg-indigo-500/60" onmousedown={(e) => s.onResizeStart(e, 'bytes', tableRef)}></button>
					</th>
					<th class="text-left py-3 px-4 font-medium relative">
						{t('views.treeTable.type')}
						<button type="button" aria-label={t('views.treeTable.resizeType')} class="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-indigo-500/40 active:bg-indigo-500/60" onmousedown={(e) => s.onResizeStart(e, 'type', tableRef)}></button>
					</th>
					<th class="text-left py-3 px-4 font-medium relative">
						<button onclick={() => s.toggleSort('last_modified')} class="hover:text-ink-2 transition-colors">{t('views.treeTable.modifiedSort', { icon: s.sortIcon('last_modified') })}</button>
						<button type="button" aria-label={t('views.treeTable.resizeModified')} class="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-indigo-500/40 active:bg-indigo-500/60" onmousedown={(e) => s.onResizeStart(e, 'modified', tableRef)}></button>
					</th>
					<th class="text-right py-3 px-4 font-medium">{t('views.treeTable.actions')}</th>
				</tr>
			</thead>
			<tbody>
				{#each s.treeRows as row (row.obj.name)}
					{@const obj = row.obj}
					{@const isDir = row.isDir}
					{@const rowLabel = row.fullPath ? obj.name : (s.baseName(obj.name) || obj.name)}
					{@const downloadPreparing = s.downloading === obj.name}
					{@const order = arrivals.next(obj.name)}
					<tr
						class="resource-selection-surface group border-b border-line/50 hover:bg-surface-sunken/30 transition-colors cursor-pointer"
						class:motion-fade={order !== null}
						style:--motion-index={order}
						data-selected={s.selected.has(obj.name)}
						onclick={(e) => {
							const target = e.target as HTMLElement;
							if (target.closest('button, input, a, label')) return;
							if (isDir && !row.fullPath) s.navigatePrefix(obj.name);
							else s.toggleSelect(obj.name);
						}}
					>
						<td class="py-3 px-4">
							<SelectionCheckbox
								checked={s.selected.has(obj.name)}
								disabled={s.bulkDeleting || s.bulkMoving}
								ariaLabel={t('views.treeTable.select', { name: rowLabel })}
								onclick={() => s.toggleSelect(obj.name)}
							/>
						</td>
						<td class="py-3 px-4">
							<div class="flex items-center gap-2.5" style="padding-left: {row.depth * 16}px">
								{#if isDir && !row.fullPath && (!s.filterText.trim() || s.searchScope === 'expanded')}
									<button
										onclick={(e) => { e.stopPropagation(); s.toggleExpand(obj.name); }}
										title={row.isLoading ? `${t('views.treeTable.folder')} ${rowLabel}: ${commonT('state.loading')}` : row.isExpanded ? t('views.treeTable.collapse') : t('views.treeTable.expand')}
										aria-busy={row.isLoading}
										class="w-4 h-4 shrink-0 flex items-center justify-center text-ink-2 hover:text-ink-1 transition-colors"
									>
										{#if row.isLoading}
											<ActivityIndicator variant="spinner" size="xs" />
										{:else}
											<svg class="w-3 h-3 transition-transform {row.isExpanded ? 'rotate-90' : ''}" viewBox="0 0 20 20" fill="currentColor">
												<path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
											</svg>
										{/if}
									</button>
								{:else}
									<span class="w-4 h-4 shrink-0"></span>
								{/if}
								<FileIcon name={obj.name} contentType={obj.content_type} {isDir} />
								{#if isDir && !row.fullPath}
									<button onclick={() => s.navigatePrefix(obj.name)} class="text-ink-0 hover:text-indigo-300 text-left truncate max-w-md font-medium hover:underline">{rowLabel}</button>
								{:else}
									<button onclick={() => s.showMeta(obj.name)} class="text-ink-1 hover:text-ink-0 text-left truncate max-w-md hover:underline {row.fullPath ? 'font-mono text-xs' : ''}">{rowLabel}</button>
								{/if}
							</div>
						</td>
						<td class="py-3 px-4 text-ink-2 whitespace-nowrap">
							{isDir ? t('views.treeTable.unavailable') : formatObjectSize(obj.bytes)}
						</td>
						<td class="py-3 px-4 text-ink-2 text-xs whitespace-nowrap" title={isDir ? t('views.treeTable.folderTitle') : obj.content_type || t('views.treeTable.unavailable')}>
							{isDir ? t('views.treeTable.folder') : shortContentType(obj.content_type)}
						</td>
						<td class="py-3 px-4 text-ink-2 text-xs whitespace-nowrap">{isDir ? t('views.treeTable.unavailable') : formatDate(obj.last_modified)}</td>
						<td class="py-3 px-4 text-right">
							<div class="flex items-center justify-end gap-0.5 transition-opacity {downloadPreparing ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}">
								{#if !isDir && s.isPreviewable(obj.content_type)}
									<button onclick={() => s.openPreview(obj)} title={t('views.treeTable.preview')} class="p-1.5 text-ink-2 hover:text-ink-0 hover:bg-surface-selected rounded transition-colors">
										<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path d="M10 12a2 2 0 100-4 2 2 0 000 4z"/><path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd"/></svg>
									</button>
								{/if}
								{#if !isDir}
									<button
										onclick={() => s.downloadObject(obj.name)}
										disabled={downloadPreparing}
										aria-busy={downloadPreparing}
										aria-label={downloadPreparing ? downloadPendingLabel : t('views.treeTable.download')}
										title={downloadPreparing ? downloadPendingLabel : t('views.treeTable.download')}
										class="p-1.5 text-ink-2 hover:text-ink-0 hover:bg-surface-selected rounded transition-colors disabled:cursor-default"
									>
										{#if downloadPreparing}
											<ActivityIndicator variant="download" size="sm" />
										{:else}
											<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
										{/if}
									</button>
								{/if}
								<button onclick={() => s.openRename(obj.name)} title={t('views.treeTable.rename')} class="p-1.5 text-ink-2 hover:text-ink-0 hover:bg-surface-selected rounded transition-colors">
									<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z"/></svg>
								</button>
								<button onclick={() => s.openMove(obj.name)} title={t('views.treeTable.move')} class="p-1.5 text-ink-2 hover:text-ink-0 hover:bg-surface-selected rounded transition-colors">
									<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path d="M8 5a1 1 0 000 2h5.586l-1.293 1.293a1 1 0 001.414 1.414l3-3a1 1 0 000-1.414l-3-3a1 1 0 10-1.414 1.414L13.586 5H8zM12 15a1 1 0 100-2H6.414l1.293-1.293a1 1 0 10-1.414-1.414l-3 3a1 1 0 000 1.414l3 3a1 1 0 001.414-1.414L6.414 15H12z"/></svg>
								</button>
								<button onclick={() => s.deleteObject(obj.name)} title={t('views.treeTable.delete')} class="p-1.5 text-red-400 hover:text-red-300 hover:bg-surface-selected rounded transition-colors">
									<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>
								</button>
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
