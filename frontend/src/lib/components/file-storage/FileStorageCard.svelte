<script lang="ts">
	import type { FileStorage } from '$lib/types/fileStorage';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { formatIsoDateTime } from '$lib/utils/format';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';

	let {
		fs, quotaLimit, copiedExport, deleting, selected = false, selectable = true, selectionDisabled = false,
		onOpenDetail, onCopyExport, onDelete, onToggleSelect,
	}: {
		fs: FileStorage; quotaLimit: number; copiedExport: string | null; deleting: string | null;
		selected?: boolean; selectable?: boolean; selectionDisabled?: boolean;
		onOpenDetail: (id: string) => void; onCopyExport: (path: string, id: string) => void;
		onDelete: (id: string, name: string) => void; onToggleSelect: () => void;
	} = $props();
</script>

<article class="resource-selection-surface bg-surface-base border border-line rounded-lg p-5" data-selected={selected}>
	<div class="flex items-center gap-2.5 mb-3.5">
		<SelectionCheckbox checked={selected} disabled={!selectable || selectionDisabled} unavailable={!selectable} onclick={onToggleSelect} ariaLabel={`${fs.name || fs.id} 선택`} />
		<div class="w-10 h-10 rounded-lg bg-teal-500/15 border border-teal-500/30 text-teal-400 flex items-center justify-center shrink-0">
			<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
			</svg>
		</div>
		<div class="flex-1 min-w-0">
			<div class="text-ink-0 text-[14px] font-semibold font-mono truncate">
				{fs.name || fs.id.slice(0, 8)}
			</div>
			<div class="text-[11px] text-ink-3 mt-0.5">
				{fs.share_proto}
				{#if fs.library_name}
					· <span class="text-action-warm">{fs.library_name}{fs.library_version ? ` v${fs.library_version}` : ''}</span>
				{/if}
				{#if fs.created_at}
					· <span class="text-ink-3">{formatIsoDateTime(fs.created_at)}</span>
				{/if}
			</div>
		</div>
		<StatusChip status={fs.status} />
	</div>

	<div>
		<div class="flex justify-between text-[11px] text-ink-2 mb-1.5">
			<span>할당 크기</span>
			<span class="text-ink-0 font-medium">{fs.size} GB</span>
		</div>
		<div class="h-1.5 bg-surface-sunken rounded-full overflow-hidden">
			<div class="h-full rounded-full transition-all" style="width: {quotaLimit > 0 ? Math.min(100, Math.round(fs.size / quotaLimit * 100)) : 0}%; background: var(--gradient-usage)"></div>
		</div>
	</div>

	<!-- creating 상태일 때 progress 표시 -->
	{#if fs.status === 'creating' && fs.progress}
		{@const pct = (() => { const m = fs.progress.match(/^(\d+(?:\.\d+)?)%$/); return m ? parseFloat(m[1]) : 0; })()}
		<div class="mt-3 flex items-center gap-2">
			<div class="flex-1 h-1 bg-surface-sunken rounded-full overflow-hidden">
				<div class="h-full rounded-full bg-yellow-500 transition-all" style="width: {pct}%"></div>
			</div>
			<span class="text-[10px] text-yellow-400 shrink-0">{fs.progress}</span>
		</div>
	{/if}

	<div class="mt-3.5 flex items-center gap-2 pt-3 border-t border-line">
		<button
			onclick={() => onOpenDetail(fs.id)}
			class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
		>상세</button>
		<div class="flex-1"></div>
		<button
			onclick={(e) => { e.stopPropagation(); onDelete(fs.id, fs.name); }}
			disabled={deleting === fs.id}
			class="text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 text-red-400 hover:text-red-300 disabled:text-ink-3 disabled:border-line-2 transition-colors"
		>{deleting === fs.id ? '삭제 중...' : '삭제'}</button>
	</div>
</article>
