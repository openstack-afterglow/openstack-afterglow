<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import NetworkTopology from '$lib/components/NetworkTopology.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import type { NetworkDetail } from '$lib/types/networks';
	import NetworkDetailHeader from '$lib/components/dashboard/networks/NetworkDetailHeader.svelte';
	import NetworkInfoCard from '$lib/components/dashboard/networks/NetworkInfoCard.svelte';
	import SubnetTableSection from '$lib/components/dashboard/networks/SubnetTableSection.svelte';
	import ConnectedRouterTable from '$lib/components/dashboard/networks/ConnectedRouterTable.svelte';
	import { toast } from '$lib/stores/toast';

	let network = $state<NetworkDetail | null>(null);
	let loading = $state(true);
	let error = $state('');
	let deleting = $state(false);
	let addingSubnet = $state(false);
	let subnetError = $state('');
	let savingSubnet = $state(false);
	let editSubnetError = $state('');

	async function refreshCurrentNetwork() {
		const id = $page.params.id;
		if (id) await fetchNetwork(id);
	}

	const ar = createAutoRefresh(refreshCurrentNetwork, {
		storageKey: 'dashboard-network-network-detail',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [10, 15, 30, 60],
	});

	$effect(() => {
		const id = $page.params.id;
		if (!id || !$auth.token) return;
		untrack(() => fetchNetwork(id));
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
			goto('/dashboard/network/networks');
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

	async function saveSubnet(subnetId: string, form: { name: string; gateway: string; dhcp: boolean }): Promise<boolean> {
		savingSubnet = true;
		editSubnetError = '';
		try {
			await api.put(
				`/api/v1/networks/subnets/${subnetId}`,
				{
					name: form.name || null,
					gateway_ip: form.gateway || null,
					enable_dhcp: form.dhcp,
				},
				$auth.token ?? undefined,
				$auth.projectId ?? undefined
			);
			await fetchNetwork(network!.id);
			return true;
		} catch (e) {
			editSubnetError = e instanceof ApiError ? e.message : '서브넷 업데이트 실패';
			return false;
		} finally {
			savingSubnet = false;
		}
	}

	async function deleteSubnet(subnetId: string, subnetName: string) {
		if (!await confirmDialog(`서브넷 "${subnetName || subnetId.slice(0, 8)}"를 삭제하시겠습니까?`)) return;
		try {
			await api.delete(
				`/api/v1/networks/subnets/${subnetId}`,
				$auth.token ?? undefined,
				$auth.projectId ?? undefined
			);
			await fetchNetwork(network!.id);
		} catch (e) {
			toast.error('서브넷 삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}
</script>

<div class="p-4 md:p-6 max-w-5xl mx-auto">
	<div class="mb-6">
		<a href="/dashboard/network/networks" class="text-ink-2 hover:text-ink-1 text-sm transition-colors">
			← 네트워크 목록
		</a>
	</div>

	{#if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{error}</div>
	{:else if loading}
		<LoadingSkeleton variant="card" rows={5} />
	{:else if network}
		<NetworkDetailHeader
			{network}
			{deleting}
			refreshing={loading}
			bind:arActive={ar.active}
			bind:arInterval={ar.intervalSeconds}
			arIntervalOptions={ar.intervalOptions}
			onManualRefresh={refreshCurrentNetwork}
			onDelete={deleteNetwork}
		/>
		<NetworkInfoCard {network} />

		<!-- 네트워크 토폴로지 -->
		<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
			<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">네트워크 토폴로지</h2>
			<NetworkTopology {network} />
		</div>

		<SubnetTableSection
			{network}
			onAdd={addSubnet}
			onSave={saveSubnet}
			onDelete={deleteSubnet}
			{addingSubnet}
			{savingSubnet}
			addError={subnetError}
			saveError={editSubnetError}
			onClearAddError={() => { subnetError = ''; }}
			onClearSaveError={() => { editSubnetError = ''; }}
		/>

		{#if network.routers.length > 0}
			<ConnectedRouterTable routers={network.routers} />
		{/if}
	{/if}
</div>
