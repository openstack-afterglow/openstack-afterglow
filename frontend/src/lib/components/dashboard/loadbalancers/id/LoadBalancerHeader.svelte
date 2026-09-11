<script lang="ts">
	import { goto } from '$app/navigation';
	import type { LoadBalancerDetail } from '$lib/types/loadbalancer';
	import { isDroverLoadBalancer } from '$lib/utils/droverLoadBalancer';

	let {
		lb,
		deleting,
		onDelete,
	}: {
		lb: LoadBalancerDetail;
		deleting: boolean;
		onDelete: () => void;
	} = $props();

	const isProtected = $derived(isDroverLoadBalancer(lb));
</script>

<button onclick={() => goto('/dashboard')} class="text-sm text-ink-2 hover:text-ink-1 mb-6 inline-flex items-center gap-1">
	← 대시보드
</button>

<div class="flex items-start justify-between mb-8">
	<div>
		<h1 class="text-2xl font-bold text-ink-0">{lb.name || lb.id.slice(0, 12)}</h1>
		{#if lb.description}
			<p class="text-ink-2 text-sm mt-1">{lb.description}</p>
		{/if}
		<div class="flex items-center gap-3 mt-2">
			<span class="px-2 py-0.5 rounded text-xs {lb.status === 'ACTIVE' ? 'text-green-400 bg-green-900/30' : 'text-yellow-400 bg-yellow-900/30'}">{lb.status}</span>
			<span class="px-2 py-0.5 rounded text-xs {lb.operating_status === 'ONLINE' ? 'text-green-400' : 'text-ink-2'}">{lb.operating_status}</span>
			{#if lb.vip_address}
				<span class="text-xs text-ink-3 font-mono">VIP: {lb.vip_address}</span>
			{/if}
		</div>
	</div>
	<button onclick={onDelete} disabled={deleting} class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors">{isProtected ? '강제 삭제' : '삭제'}</button>
</div>
