<script lang="ts">
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
			error = e instanceof ApiError ? `조회 실패 (${e.status}): ${e.message}` : '서버 오류';
		} finally {
			loading = false;
		}
	}

	async function deleteNetwork() {
		if (!network) return;
		if (network.is_external || network.is_shared) {
			toast.warning('외부/공유 네트워크는 삭제할 수 없습니다.');
			return;
		}
		if (!await confirmDialog(`네트워크 "${network.name || network.id}"를 삭제하시겠습니까?`)) return;
		deleting = true;
		try {
			await api.delete(`/api/v1/networks/${network.id}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			goto('/dashboard');
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			deleting = false;
		}
	}

	async function addSubnet(form: { name: string; cidr: string; gateway: string; dhcp: boolean }): Promise<boolean> {
		if (!network || !form.cidr.trim()) return false;
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
			subnetError = e instanceof ApiError ? e.message : '서브넷 생성 실패';
			return false;
		} finally {
			addingSubnet = false;
		}
	}
</script>

<div class="p-4 md:p-6 max-w-5xl mx-auto">
	<div class="mb-6">
		<a href="/dashboard" class="text-ink-2 hover:text-ink-1 text-sm transition-colors">
			← 대시보드
		</a>
	</div>

	{#if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">
			{error}
		</div>
	{:else if loading}
		<LoadingSkeleton variant="card" rows={5} />
	{:else if network}
		<DashboardNetworkHeader {network} {deleting} onDelete={deleteNetwork} />
		<DashboardNetworkInfoCard {network} />
		<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
			<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">네트워크 토폴로지</h2>
			<NetworkTopology {network} />
		</div>
		<DashboardSubnetSection
			subnets={network.subnet_details}
			networkName={network.name}
			allowAdd={!network.is_external}
			{addingSubnet}
			addError={subnetError}
			onAdd={addSubnet}
		/>
		{#if network.routers.length > 0}
			<DashboardRouterTable routers={network.routers} />
		{/if}
	{/if}
</div>
