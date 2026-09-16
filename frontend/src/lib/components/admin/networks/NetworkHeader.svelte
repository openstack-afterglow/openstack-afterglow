<script lang="ts">
	import { getNetworkStatusClass } from '$lib/utils/networkStatus';
	import type { NetworkDetail } from '$lib/types/networks';

	let {
		network,
		deleting,
		onDelete,
	}: {
		network: NetworkDetail;
		deleting: boolean;
		onDelete: () => void;
	} = $props();
</script>

<div class="flex items-start justify-between mb-6">
	<div>
		<h1 class="text-2xl font-bold text-ink-0">{network.name || network.id}</h1>
		<div class="flex items-center gap-2 mt-2">
			<span class="px-2 py-0.5 rounded text-xs font-medium {getNetworkStatusClass(network.status)}">
				{network.status}
			</span>
			{#if network.is_external}
				<span class="px-1.5 py-0.5 bg-orange-900/40 text-orange-300 rounded text-xs">외부</span>
			{/if}
			{#if network.is_shared}
				<span class="px-1.5 py-0.5 bg-teal-900/40 text-teal-300 rounded text-xs">공유</span>
			{/if}
		</div>
	</div>
	<button
		onclick={onDelete}
		disabled={deleting}
		class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
	>
		{deleting ? '삭제 중...' : '삭제'}
	</button>
</div>
