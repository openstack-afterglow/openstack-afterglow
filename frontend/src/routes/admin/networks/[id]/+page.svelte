<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import NetworkHeader from '$lib/components/admin/networks/NetworkHeader.svelte';
	import NetworkInfoCard from '$lib/components/admin/networks/NetworkInfoCard.svelte';
	import SubnetSection from '$lib/components/admin/networks/SubnetSection.svelte';
	import RouterTable from '$lib/components/admin/networks/RouterTable.svelte';
	import type { AdminNetworkDetail } from '$lib/types/networks';
	import { toast } from '$lib/stores/toast';

	let network = $state<AdminNetworkDetail | null>(null);
	let loading = $state(true);
	let error = $state('');
	let deleting = $state(false);
	let addingSubnet = $state(false);
	let subnetError = $state('');
	let savingSubnet = $state(false);
	let editSubnetError = $state('');
	let deletingSubnetId = $state<string | null>(null);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	$effect(() => {
		const id = $page.params.id;
		if (!id || !$auth.token) return;
		fetchNetwork(id);
	});

	async function fetchNetwork(id: string) {
		loading = true;
		error = '';
		try {
			network = await api.get<AdminNetworkDetail>(`/api/v1/admin/networks/${id}`, token, projectId);
		} catch (e) {
			error = e instanceof ApiError ? `조회 실패 (${e.status}): ${e.message}` : '서버 오류';
		} finally {
			loading = false;
		}
	}

	async function deleteNetwork() {
		if (!network) return;
		if (!await confirmDialog(`네트워크 "${network.name || network.id}"를 삭제하시겠습니까?`)) return;
		deleting = true;
		try {
			await api.delete(`/api/v1/admin/networks/${network.id}`, token, projectId);
			goto('/admin/networks');
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
				token, projectId
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
				token, projectId
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
		deletingSubnetId = subnetId;
		try {
			await api.delete(`/api/v1/networks/subnets/${subnetId}`, token, projectId);
			await fetchNetwork(network!.id);
		} catch (e) {
			toast.error('서브넷 삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			deletingSubnetId = null;
		}
	}
</script>

<div class="p-4 md:p-6 max-w-5xl mx-auto">
	<div class="mb-6">
		<a href="/admin/networks" class="text-ink-2 hover:text-ink-1 text-sm transition-colors">
			← 네트워크 목록
		</a>
	</div>

	{#if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">
			{error}
		</div>
	{:else if loading}
		<LoadingSkeleton variant="card" rows={5} />
	{:else if network}
		<NetworkHeader {network} {deleting} onDelete={deleteNetwork} />
		<NetworkInfoCard {network} />
		<SubnetSection
			subnets={network.subnet_details}
			onAdd={addSubnet}
			onSave={saveSubnet}
			onDelete={deleteSubnet}
			{deletingSubnetId}
			addError={subnetError}
			saveError={editSubnetError}
			{addingSubnet}
			{savingSubnet}
		/>
		{#if network.routers.length > 0}
			<RouterTable routers={network.routers} />
		{/if}
	{/if}
</div>
