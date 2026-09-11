<script lang="ts">
	import type { RouterDetail } from '$lib/types/router';

	let {
		router,
		saving,
		onDelete,
		onBack,
	}: {
		router: RouterDetail;
		saving: boolean;
		onDelete: () => Promise<void>;
		onBack: () => void;
	} = $props();
</script>

<button onclick={onBack} class="text-sm text-ink-2 hover:text-ink-1 mb-6 inline-flex items-center gap-1">
	← 대시보드
</button>

<div class="flex items-start justify-between mb-8">
	<div>
		<h1 class="text-2xl font-bold text-ink-0">{router.name || router.id.slice(0, 12)}</h1>
		<div class="flex items-center gap-3 mt-2">
			<span class="px-2 py-0.5 rounded text-xs font-medium {router.status === 'ACTIVE' ? 'text-green-400 bg-green-900/30' : 'text-ink-2 bg-surface-sunken'}">
				{router.status}
			</span>
			<span class="text-xs text-ink-3 font-mono">{router.id}</span>
		</div>
	</div>
	<button
		onclick={onDelete}
		disabled={saving}
		class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
	>삭제</button>
</div>
