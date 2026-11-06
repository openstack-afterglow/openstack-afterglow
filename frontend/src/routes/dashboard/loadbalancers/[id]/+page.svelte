<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t } from '$lib/i18n/ns/network-resources';
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import { createLoadbalancerDetailController } from '$lib/stores/loadbalancerDetailController.svelte';
	import LoadBalancerHeader from '$lib/components/dashboard/loadbalancers/id/LoadBalancerHeader.svelte';
	import LbListenerSection from '$lib/components/dashboard/loadbalancers/id/LbListenerSection.svelte';
	import LbPoolSection from '$lib/components/dashboard/loadbalancers/id/LbPoolSection.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { provideTableViewVisibility } from '$lib/utils/tableView.svelte';

	const ctrl = createLoadbalancerDetailController({
		lbId: () => $page.params.id!,
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
	});

	$effect(() => { if ($auth.projectId) ctrl.fetchAll(); });
	provideTableViewVisibility(() => !ctrl.error && ctrl.lb?.id === $page.params.id);
</script>

<PageShell class="text-ink-1">
	{#if ctrl.error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{ctrl.error}</div>
	{/if}
	{#if ctrl.loading && ctrl.lb?.id !== $page.params.id}
		<LoadingState variant="surface" label={t('lb.state.loadingInfo')} />
	{/if}
	{#if ctrl.lb}
	{#key `${$auth.projectId ?? ''}:${ctrl.lb.id}`}
	<div hidden={Boolean(ctrl.error) || ctrl.lb.id !== $page.params.id}>
		{#if ctrl.loading}<LoadingState variant="inline" label={t('lb.state.loadingInfo')} />{/if}
		<LoadBalancerHeader
			lb={ctrl.lb}
			deleting={ctrl.saving}
			onDelete={ctrl.deleteLb}
		/>

		<LbListenerSection
			listeners={ctrl.listeners}
			pools={ctrl.pools}
			saving={ctrl.saving}
			error=""
			onAdd={ctrl.createListener}
			onDelete={ctrl.deleteListener}
		/>

		<LbPoolSection
			pools={ctrl.pools}
			selectedPoolId={ctrl.selectedPoolId}
			members={ctrl.selectedPoolMembers}
			memberView={ctrl.memberView}
			membersLoading={ctrl.saving}
			saving={ctrl.saving}
			error=""
			addingMember={ctrl.saving}
			addMemberError=""
			onAddPool={ctrl.createPool}
			onDeletePool={ctrl.deletePool}
			onSelectPool={(id) => {
				if (id) ctrl.togglePool(id);
				else if (ctrl.selectedPoolId) ctrl.togglePool(ctrl.selectedPoolId);
			}}
			onAddMember={ctrl.addMember}
			onRemoveMember={ctrl.removeMember}
		/>
	</div>
	{/key}
	{/if}
</PageShell>
