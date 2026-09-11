<script lang="ts">
	import type { SwiftContainer } from '$lib/types/objectStorage';
	import { formatStorage } from '$lib/utils/format';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';

	let {
		containers,
		deleting,
		refreshing,
		selectedIds,
		selectionDisabled = false,
		onToggleSelect,
		onDelete,
	}: {
		containers: SwiftContainer[];
		deleting: string | null;
		refreshing: boolean;
		selectedIds: ReadonlySet<string>;
		selectionDisabled?: boolean;
		onToggleSelect: (name: string) => void;
		onDelete: (name: string) => Promise<void>;
	} = $props();
</script>

<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
	{#each containers as c (c.name)}
		<article class="resource-selection-surface bg-surface-base border border-line rounded-lg p-5" data-selected={selectedIds.has(c.name)}>
			<div class="flex items-center gap-2.5 mb-3">
				<SelectionCheckbox
					checked={selectedIds.has(c.name)}
					disabled={selectionDisabled}
					ariaLabel={`${c.name} 선택`}
					onclick={() => onToggleSelect(c.name)}
				/>
				<div class="w-10 h-10 rounded-lg bg-violet-500/15 border border-violet-500/30 text-violet-400 flex items-center justify-center shrink-0">
					<svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>
					</svg>
				</div>
				<div class="flex-1 min-w-0">
					<div class="text-ink-0 font-semibold text-sm font-mono truncate">{c.name}</div>
					<div class="text-[11px] text-ink-3 mt-0.5">오브젝트 {c.count}개</div>
				</div>
			</div>
			<div class="grid grid-cols-2 gap-2 mb-3">
				<div>
					<div class="text-[11px] uppercase tracking-wider font-medium text-ink-3">오브젝트</div>
					<div class="text-ink-0 font-mono text-sm mt-0.5">{c.count}</div>
				</div>
				<div>
					<div class="text-[11px] uppercase tracking-wider font-medium text-ink-3">크기</div>
					<div class="text-ink-0 font-mono text-sm mt-0.5">{formatStorage(c.bytes / 1_000_000_000)}</div>
				</div>
			</div>
			<div class="pt-3 border-t border-line flex items-center justify-between">
				<a
					href="/dashboard/object-storage/buckets/{encodeURIComponent(c.name)}"
					class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
				>상세 보기 →</a>
				<button
					onclick={() => onDelete(c.name)}
					disabled={deleting === c.name || selectionDisabled}
					class="text-xs text-red-400 hover:text-red-300 disabled:text-ink-3 transition-colors"
				>{deleting === c.name ? '삭제 중...' : '삭제'}</button>
			</div>
		</article>
	{/each}
</div>
