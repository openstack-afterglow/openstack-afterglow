<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import NetworkTopology from '$lib/components/NetworkTopology.svelte';
	import DashboardNetworkHeader from '$lib/components/dashboard/networks/id/DashboardNetworkHeader.svelte';
	import DashboardNetworkInfoCard from '$lib/components/dashboard/networks/id/DashboardNetworkInfoCard.svelte';
	import DashboardSubnetSection from '$lib/components/dashboard/networks/id/DashboardSubnetSection.svelte';
	import DashboardRouterTable from '$lib/components/dashboard/networks/id/DashboardRouterTable.svelte';
	import type { NetworkDetail } from '$lib/types/networks';
	import { toast } from '$lib/stores/toast';

	let network = $state<NetworkDetail | null>(null);
	let loading = $state(true);
	let error = $state('');
	let deleting = $state(false);
	let addingSubnet = $state(false);
	let subnetError = $state('');
	const canManageNetwork = $derived(
		Boolean(network && ($auth.isSystemAdmin || (network.project_id && network.project_id === $auth.projectId)) && !network.is_external)
	);

	$effect(() => {
		const id = $page.params.id;
		if (!id || !$auth.token) return;
		fetchNetwork(id);
	});

	async function fetchNetwork(id: string) {
		loading = true;
		error = '';
		try {
			network = await api.get<NetworkDetail>(
				`/api/v1/networks/${id}`,
				$auth.token ?? undefined,
				$auth.projectId ?? undefined
			);
		} catch (e) {
			error = e instanceof ApiError ? t('network.page.loadFailed', { status: e.status, error: e.message }) : t('network.page.serverError');
		} finally {
			loading = false;
		}
	}

	async function deleteNetwork() {
		if (!network) return;
		if (!canManageNetwork) {
			toast.warning(t('network.page.deleteOwnOnly'));
			return;
		}
		if (network.is_external) {
			toast.warning(t('network.page.deleteExternalForbidden'));
			return;
		}
		if (!await confirmDialog(t('network.page.deleteConfirm', { name: network.name || network.id }))) return;
		deleting = true;
		try {
			await api.delete(`/api/v1/networks/${network.id}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			goto('/dashboard');
		} catch (e) {
			toast.error(t('network.page.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			deleting = false;
		}
	}

	async function addSubnet(form: { name: string; cidr: string; gateway: string; dhcp: boolean }): Promise<boolean> {
		if (!canManageNetwork || !network || !form.cidr.trim()) return false;
		addingSubnet = true;
		subnetError = '';
		try {
			await api.post(
				`/api/v1/networks/${network.id}/subnets`,
				{
					name: form.name || `${network.name}-subnet`,
					cidr: form.cidr,
					gateway_ip: form.gateway || null,
					enable_dhcp: form.dhcp,
				},
				$auth.token ?? undefined,
				$auth.projectId ?? undefined
			);
			await fetchNetwork(network.id);
			return true;
		} catch (e) {
			subnetError = e instanceof ApiError ? e.message : t('network.errors.createSubnet');
			return false;
		} finally {
			addingSubnet = false;
		}
	}
</script>

<div class="p-4 md:p-6 max-w-5xl mx-auto">
	<div class="mb-6">
		<a href="/dashboard" class="text-ink-2 hover:text-ink-1 text-sm transition-colors">
			{t('network.page.backDashboard')}
		</a>
	</div>

	{#if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">
			{error}
		</div>
	{:else if loading}
		<LoadingSkeleton variant="card" rows={5} />
	{:else if network}
		<DashboardNetworkHeader {network} {deleting} canManage={canManageNetwork} onDelete={deleteNetwork} />
		<DashboardNetworkInfoCard {network} />
		<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
			<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">{t('network.page.topology')}</h2>
			<NetworkTopology {network} />
		</div>
		<DashboardSubnetSection
			subnets={network.subnet_details}
			networkName={network.name}
			allowAdd={canManageNetwork}
			{addingSubnet}
			addError={subnetError}
			onAdd={addSubnet}
		/>
		{#if network.routers.length > 0}
			<DashboardRouterTable routers={network.routers} />
		{/if}
	{/if}
</div>
