<script lang="ts">
	import { t as tl } from '$lib/i18n/ns/common';
	import PageShell from '$lib/components/ui/PageShell.svelte';
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
	import { t } from '$lib/i18n/ns/network-pages';
	import { createdLoadBalancer } from '$lib/tutorial/createdLoadBalancer.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { provideTableViewVisibility } from '$lib/utils/tableView.svelte';

	const ctrl = createNetworkLoadbalancerDetailController({
		lbId: () => $page.params.id!,
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
	});

	const ar = createAutoRefresh((force) => ctrl.fetchAll(force), {
		storageKey: 'dashboard-network-lb-detail',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
	});

	$effect(() => { if ($auth.projectId) untrack(() => ctrl.fetchAll()); });
	$effect(() => { ctrl.loadPoolMembers(); });
	provideTableViewVisibility(() => !ctrl.error && ctrl.lb?.id === $page.params.id);
</script>

<PageShell class="text-ink-1">
	<div class="flex items-center justify-between mb-6">
		<button onclick={() => goto('/dashboard/network/loadbalancers')} class="text-sm text-ink-2 hover:text-ink-1 inline-flex items-center gap-1">
			{t('loadBalancerDetail.backToList')}
		</button>
		<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={ctrl.loading}
			onManualRefresh={ar.refresh}
		/>
	</div>

	{#if ctrl.error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{ctrl.error}</div>
	{/if}
	{#if ctrl.loading && ctrl.lb?.id !== $page.params.id}
		<LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('loadBalancers.title') })} />
	{/if}
	{#if ctrl.lb}
	{#key `${$auth.projectId ?? ''}:${ctrl.lb.id}`}
	<div hidden={Boolean(ctrl.error) || ctrl.lb.id !== $page.params.id}>
		{#if ctrl.loading}<LoadingState variant="inline" label={tl('state.loadingNamed', { name: t('loadBalancers.title') })} />{/if}
		<!-- Tutorial delete anchor: only the load balancer created in this tab, once Octavia accepts deletes. -->
		<LbDetailHeader lb={ctrl.lb} saving={ctrl.saving} onDelete={ctrl.deleteLb} highlightDelete={createdLoadBalancer.id === ctrl.lb.id && (ctrl.lb.status === 'ACTIVE' || ctrl.lb.status === 'ERROR')} />

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
	</div>
	{/key}
	{/if}
</PageShell>
