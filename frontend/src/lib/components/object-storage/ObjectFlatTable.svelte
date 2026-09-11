<script lang="ts">
	import { useObjectBrowser } from '$lib/stores/objectBrowser.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import FileIcon from '$lib/components/ui/FileIcon.svelte';
	import { formatStorage, formatDate, shortContentType } from '$lib/utils/format';

	const s = useObjectBrowser();

	let tableRef = $state<HTMLTableElement | null>(null);
</script>

{#if s.loading}
	<LoadingSkeleton variant="table" rows={5} />
{:else if s.objects.length === 0}
	<div class="text-ink-3 text-sm py-8 text-center">
		<svg class="w-12 h-12 mx-auto text-ink-3 mb-3" viewBox="0 0 20 20" fill="currentColor">
			<path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/>
		</svg>
		<p>오브젝트가 없습니다</p>
		<p class="text-ink-3 text-xs mt-1">파일을 업로드하거나 새 폴더를 만들어보세요</p>
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
				<tr class="border-b border-line text-ink-3 text-xs uppercase tracking-wide">
					<th class="py-3 px-4 w-10">
						<input
							type="checkbox"
							checked={s.selectedCount > 0 && s.selectedCount === s.filteredObjects.length}
							onchange={s.toggleSelectAll}
							class="w-3.5 h-3.5 rounded border-line-2 bg-surface-sunken accent-indigo-500 cursor-pointer"
						/>
					</th>
					<th class="text-left py-3 px-4 font-medium relative">
						<button onclick={() => s.toggleSort('name')} class="hover:text-ink-2 transition-colors">이름 {s.sortIcon('name')}</button>
						<button type="button" aria-label="이름 열 너비 조절" class="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-indigo-500/40 active:bg-indigo-500/60" onmousedown={(e) => s.onResizeStart(e, 'name', tableRef)}></button>
					</th>
					<th class="text-left py-3 px-4 font-medium relative">
						<button onclick={() => s.toggleSort('bytes')} class="hover:text-ink-2 transition-colors">크기 {s.sortIcon('bytes')}</button>
						<button type="button" aria-label="크기 열 너비 조절" class="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-indigo-500/40 active:bg-indigo-500/60" onmousedown={(e) => s.onResizeStart(e, 'bytes', tableRef)}></button>
					</th>
					<th class="text-left py-3 px-4 font-medium relative">
						타입
						<button type="button" aria-label="타입 열 너비 조절" class="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-indigo-500/40 active:bg-indigo-500/60" onmousedown={(e) => s.onResizeStart(e, 'type', tableRef)}></button>
					</th>
					<th class="text-left py-3 px-4 font-medium relative">
						<button onclick={() => s.toggleSort('last_modified')} class="hover:text-ink-2 transition-colors">수정일 {s.sortIcon('last_modified')}</button>
						<button type="button" aria-label="수정일 열 너비 조절" class="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-indigo-500/40 active:bg-indigo-500/60" onmousedown={(e) => s.onResizeStart(e, 'modified', tableRef)}></button>
					</th>
					<th class="text-right py-3 px-4 font-medium">액션</th>
				</tr>
			</thead>
			<tbody>
				{#each s.filteredObjects as obj (obj.name)}
					{@const isDir = s.isDirectory(obj)}
					{@const relName = s.displayName(obj.name)}
					<tr
						class="group border-b border-line/50 hover:bg-surface-sunken/30 transition-colors cursor-pointer {s.selected.has(obj.name) ? 'bg-indigo-950/20' : ''}"
						onclick={(e) => {
							const t = e.target as HTMLElement;
							if (t.closest('button, input, a, label')) return;
							s.toggleSelect(obj.name);
						}}
					>
						<td class="py-3 px-4">
							<input type="checkbox" checked={s.selected.has(obj.name)} onchange={() => s.toggleSelect(obj.name)} class="w-3.5 h-3.5 rounded border-line-2 bg-surface-sunken accent-indigo-500 cursor-pointer" />
						</td>
						<td class="py-3 px-4">
							<div class="flex items-center gap-2.5">
								<FileIcon name={obj.name} contentType={obj.content_type} {isDir} />
								{#if isDir}
									<button onclick={() => s.navigatePrefix(obj.name)} class="text-ink-0 hover:text-indigo-300 text-left truncate max-w-md font-medium hover:underline">{relName || obj.name}</button>
								{:else}
									<button onclick={() => s.showMeta(obj.name)} class="text-ink-1 hover:text-ink-0 text-left truncate max-w-md hover:underline">{relName || obj.name}</button>
								{/if}
							</div>
						</td>
						<td class="py-3 px-4 text-ink-2 whitespace-nowrap">
							{isDir ? '-' : obj.bytes >= 1073741824
								? formatStorage(Math.round(obj.bytes / 1073741824))
								: obj.bytes >= 1048576 ? `${(obj.bytes / 1048576).toFixed(1)} MB`
								: `${(obj.bytes / 1024).toFixed(1)} KB`}
						</td>
						<td class="py-3 px-4 text-ink-3 text-xs whitespace-nowrap" title={isDir ? 'folder' : obj.content_type || '-'}>
							{isDir ? '폴더' : shortContentType(obj.content_type)}
						</td>
						<td class="py-3 px-4 text-ink-3 text-xs whitespace-nowrap">{isDir ? '-' : formatDate(obj.last_modified)}</td>
						<td class="py-3 px-4 text-right">
							<div class="flex items-center justify-end gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
								{#if !isDir && s.isPreviewable(obj.content_type)}
									<button onclick={() => s.openPreview(obj)} title="미리보기" class="p-1.5 text-ink-2 hover:text-ink-0 hover:bg-surface-selected rounded transition-colors">
										<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path d="M10 12a2 2 0 100-4 2 2 0 000 4z"/><path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd"/></svg>
									</button>
								{/if}
								{#if !isDir}
									<button onclick={() => s.downloadObject(obj.name)} title="다운로드" class="p-1.5 text-ink-2 hover:text-ink-0 hover:bg-surface-selected rounded transition-colors">
										<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
									</button>
								{/if}
								<button onclick={() => s.openRename(obj.name)} title="이름변경" class="p-1.5 text-ink-2 hover:text-ink-0 hover:bg-surface-selected rounded transition-colors">
									<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z"/></svg>
								</button>
								<button onclick={() => s.openMove(obj.name)} title="이동" class="p-1.5 text-ink-2 hover:text-ink-0 hover:bg-surface-selected rounded transition-colors">
									<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path d="M8 5a1 1 0 000 2h5.586l-1.293 1.293a1 1 0 001.414 1.414l3-3a1 1 0 000-1.414l-3-3a1 1 0 10-1.414 1.414L13.586 5H8zM12 15a1 1 0 100-2H6.414l1.293-1.293a1 1 0 10-1.414-1.414l-3 3a1 1 0 000 1.414l3 3a1 1 0 001.414-1.414L6.414 15H12z"/></svg>
								</button>
								<button onclick={() => s.deleteObject(obj.name)} title="삭제" class="p-1.5 text-red-400 hover:text-red-300 hover:bg-surface-selected rounded transition-colors">
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
