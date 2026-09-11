<script lang="ts">
	import { untrack } from 'svelte';
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import { goto } from '$app/navigation';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createNetworkLoadbalancerDetailController } from '$lib/stores/networkLoadbalancerDetailController.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import LbDetailHeader from '$lib/components/dashboard/loadbalancers/LbDetailHeader.svelte';
	import LbErrorStatusTree from '$lib/components/dashboard/loadbalancers/LbErrorStatusTree.svelte';
	import ListenerSection from '$lib/components/dashboard/loadbalancers/ListenerSection.svelte';
	import PoolSection from '$lib/components/dashboard/loadbalancers/PoolSection.svelte';

	const ctrl = createNetworkLoadbalancerDetailController({
		lbId: () => $page.params.id!,
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
	});

	const ar = createAutoRefresh(() => ctrl.fetchAll(), {
		storageKey: 'dashboard-network-lb-detail',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
	});

	$effect(() => { if ($auth.projectId) untrack(() => ctrl.fetchAll()); });
	$effect(() => { ctrl.loadPoolMembers(); });
</script>

<div class="max-w-4xl mx-auto px-4 py-8 text-ink-1">
	<div class="flex items-center justify-between mb-6">
		<button onclick={() => goto('/dashboard/network/loadbalancers')} class="text-sm text-ink-2 hover:text-ink-1 inline-flex items-center gap-1">
			← 로드밸런서 목록
		</button>
		<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={ctrl.loading}
			onManualRefresh={() => ctrl.fetchAll()}
		/>
	</div>

	{#if ctrl.loading}
		<div class="text-ink-3">불러오는 중...</div>
	{:else if ctrl.error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{ctrl.error}</div>
	{:else if ctrl.lb}
		<LbDetailHeader lb={ctrl.lb} saving={ctrl.saving} onDelete={ctrl.deleteLb} />

		{#if ctrl.lb.status === 'ERROR' || ctrl.lb.status?.includes('ERROR')}
			<LbErrorStatusTree lb={ctrl.lb} statusTree={ctrl.statusTree} />
		{/if}

		<ListenerSection
			listeners={ctrl.listeners}
			saving={ctrl.saving}
			onCreate={ctrl.createListener}
			onDelete={ctrl.deleteListener}
		/>

		<PoolSection
			pools={ctrl.pools}
			members={ctrl.selectedPoolMembers}
			saving={ctrl.saving}
			bind:selectedPoolId={ctrl.selectedPoolId}
			onCreatePool={ctrl.createPool}
			onDeletePool={ctrl.deletePool}
			onAddMember={ctrl.addMember}
			onRemoveMember={ctrl.removeMember}
		/>
	{/if}
</div>
