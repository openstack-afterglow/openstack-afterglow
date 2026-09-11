<script lang="ts">
	import type { NetworkDetail } from '$lib/types/networks';

	let { network }: { network: NetworkDetail } = $props();
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-3">기본 정보</h2>
	<dl class="grid grid-cols-2 gap-x-8 gap-y-2">
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">ID</dt>
			<dd class="text-sm text-ink-2 font-mono">{network.id}</dd>
		</div>
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">서브넷 수</dt>
			<dd class="text-sm text-ink-2">{network.subnets.length}</dd>
		</div>
	</dl>
</div>
