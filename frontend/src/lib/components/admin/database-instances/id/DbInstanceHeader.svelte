<script lang="ts">
	import type { DbInstance } from '$lib/types/database';

	const statusColor: Record<string, string> = {
		ACTIVE: 'text-green-400',
		BUILD: 'text-yellow-400',
		ERROR: 'text-red-400',
		SHUTDOWN: 'text-ink-2'
	};

	let {
		instance,
		deleting,
		onDelete,
	}: {
		instance: DbInstance;
		deleting: boolean;
		onDelete: () => void;
	} = $props();
</script>

<div class="flex items-start justify-between mb-6">
	<div>
		<h1 class="text-2xl font-bold text-ink-0">{instance.name}</h1>
		<span class="text-xs font-medium {statusColor[instance.status] ?? 'text-ink-2'}">{instance.status}</span>
	</div>
	<button onclick={onDelete} disabled={deleting}
		class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-red-900 hover:border-red-700 transition-colors">
		{deleting ? '삭제 중...' : '인스턴스 삭제'}
	</button>
</div>
