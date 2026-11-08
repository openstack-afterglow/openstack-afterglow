<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import type { LoadBalancerDetail } from '$lib/types/loadbalancer';
	import { isDroverLoadBalancer } from '$lib/utils/droverLoadBalancer';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { createPendingAction } from '$lib/components/network/pendingAction.svelte';

	let {
		lb,
		saving,
		onDelete,
		highlightDelete = false,
	}: {
		lb: LoadBalancerDetail;
		saving: boolean;
		onDelete: () => Promise<void>;
		/** True only for the load balancer a tutorial just created; anchors its delete button. */
		highlightDelete?: boolean;
	} = $props();

	const isProtected = $derived(isDroverLoadBalancer(lb));
	const pending = createPendingAction();
	const deletingLb = $derived(pending.isActive('delete', saving));
</script>

<div data-tour="load-balancers-detail" class="flex items-start justify-between mb-8">
	<div>
		<h1 class="text-2xl font-bold text-ink-0">{lb.name || lb.id.slice(0, 12)}</h1>
		{#if lb.description}
			<p class="text-ink-2 text-sm mt-1">{lb.description}</p>
		{/if}
		<div class="flex items-center gap-3 mt-2">
			<StatusChip status={lb.status} />
			<StatusChip status={lb.operating_status} />
			{#if lb.vip_address}
				<span class="text-xs text-ink-2 font-mono">VIP: {lb.vip_address}</span>
			{/if}
		</div>
	</div>
	<button data-tour={highlightDelete ? 'load-balancers-delete' : undefined} onclick={() => pending.run('delete', onDelete)} disabled={saving} aria-busy={deletingLb} class="inline-flex items-center gap-1.5 text-red-400 hover:text-red-300 disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors">{#if deletingLb}<LoadingState variant="control" label="" />{/if}{deletingLb ? t('network.actions.deleting') : isProtected ? t('lb.actions.forceDelete') : t('lb.actions.delete')}</button>
</div>
