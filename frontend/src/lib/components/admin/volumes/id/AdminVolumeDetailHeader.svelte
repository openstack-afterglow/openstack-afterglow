<script lang="ts">
	import type { AdminVolumeDetail } from '$lib/types/volume';
	import { volumeStatusColor } from '$lib/utils/volumeStatusColor';
	import { formatNumber } from '$lib/utils/format';

	let {
		volume,
		deleting,
		onExtend,
		onResetStatus,
		onDelete,
	}: {
		volume: AdminVolumeDetail;
		deleting: boolean;
		onExtend: () => void;
		onResetStatus: () => void;
		onDelete: () => Promise<void>;
	} = $props();
</script>

<div class="flex items-start justify-between mb-6">
	<div>
		<h1 class="text-2xl font-bold text-ink-0">{volume.name || volume.id.slice(0, 12)}</h1>
		<div class="flex items-center gap-2 mt-1.5">
			<span class="px-2 py-0.5 rounded text-xs font-medium {volumeStatusColor[volume.status] ?? 'text-ink-2 bg-surface-sunken'}">
				{volume.status}
			</span>
			<span class="text-xs text-ink-3">{formatNumber(volume.size)} GB</span>
		</div>
	</div>
	<div class="flex items-center gap-2">
		<button
			onclick={onExtend}
			class="px-3 py-1.5 bg-surface-selected/40 hover:bg-surface-selected/40 border border-action-warm text-action-warm text-sm rounded-lg transition-colors"
		>확장</button>
		{#if volume.status === 'error' || volume.status === 'error_deleting'}
			<button
				onclick={onResetStatus}
				class="px-3 py-1.5 bg-yellow-900/40 hover:bg-yellow-800/40 border border-yellow-800 text-yellow-400 text-sm rounded-lg transition-colors"
			>상태 초기화</button>
		{/if}
		<button
			onclick={onDelete}
			disabled={deleting || volume.status === 'in-use'}
			class="px-3 py-1.5 bg-red-900/40 hover:bg-red-900/60 border border-red-800 text-red-400 text-sm rounded-lg transition-colors disabled:opacity-50"
		>{deleting ? '삭제 중...' : '삭제'}</button>
	</div>
</div>
