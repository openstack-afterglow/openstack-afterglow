<script lang="ts">
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import type { FileStorage } from '$lib/types/fileStorage';

	const statusColor: Record<string, string> = {
		available: 'text-green-400 bg-green-900/30',
		creating: 'text-yellow-400 bg-yellow-900/30',
		deleting: 'text-orange-400 bg-orange-900/30',
		error: 'text-red-400 bg-red-900/30',
	};

	let {
		fileStorage, deleting, loading,
		arActive = $bindable(), arInterval = $bindable(), arIntervalOptions,
		onManualRefresh, onDelete,
	}: {
		fileStorage: FileStorage;
		deleting: boolean;
		loading: boolean;
		arActive: boolean;
		arInterval: number;
		arIntervalOptions: number[];
		onManualRefresh: () => void;
		onDelete: () => void;
	} = $props();
</script>

<div class="flex items-start justify-between mb-6">
	<div>
		<h1 class="text-2xl font-bold text-ink-0">{fileStorage.name || fileStorage.id}</h1>
		<div class="flex items-center gap-2 mt-2">
			<span
				class="px-2 py-0.5 rounded text-xs font-medium {statusColor[fileStorage.status] ?? 'text-ink-2 bg-surface-sunken'}"
			>
				{fileStorage.status}
			</span>
			<span class="px-1.5 py-0.5 bg-purple-900/40 text-purple-300 rounded text-xs">
				{fileStorage.share_proto}
			</span>
		</div>
	</div>
	<div class="flex items-center gap-2">
		<AutoRefreshControl
			bind:active={arActive}
			bind:intervalSeconds={arInterval}
			intervalOptions={arIntervalOptions}
			refreshing={loading}
			{onManualRefresh}
		/>
		<button
			onclick={onDelete}
			disabled={deleting}
			class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
		>
			{deleting ? '삭제 중...' : '삭제'}
		</button>
	</div>
</div>
