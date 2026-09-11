<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { goto } from '$app/navigation';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import RouterDetailWithRefreshHeader from '$lib/components/dashboard/network/routers/id/RouterDetailWithRefreshHeader.svelte';
	import RouterGatewaySection from '$lib/components/dashboard/routers/id/RouterGatewaySection.svelte';
	import RouterInterfacesSection from '$lib/components/dashboard/routers/id/RouterInterfacesSection.svelte';
	import type { RouterDetail } from '$lib/types/router';
	import type { Network } from '$lib/types/networks';
	import { toast } from '$lib/stores/toast';

	const id = $derived($page.params.id);

	let router = $state<RouterDetail | null>(null);
	let loading = $state(true);
	let error = $state('');
	let saving = $state(false);
	let availableNetworks = $state<Network[]>([]);
	let externalNetworks = $state<Network[]>([]);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function fetchRouter() {
		try {
			router = await api.get<RouterDetail>(`/api/v1/routers/${id}`, token, projectId);
			error = '';
		} catch (e) {
			error = e instanceof ApiError ? e.message : '라우터 조회 실패';
		} finally {
			loading = false;
		}
	}

	async function fetchNetworks() {
		try {
			const nets = await api.get<Network[]>('/api/v1/networks', token, projectId);
			availableNetworks = nets.filter(n => !n.is_external);
			externalNetworks = nets.filter(n => n.is_external);
		} catch {
			// 무시
		}
	}

	const ar = createAutoRefresh(() => fetchRouter(), {
		storageKey: 'dashboard-network-router-detail',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [10, 15, 30, 60],
	});

	$effect(() => {
		if ($auth.projectId) {
			fetchRouter();
			fetchNetworks();
		}
	});

	async function addInterface(subnetId: string): Promise<boolean> {
		saving = true;
		try {
			await api.post(`/api/v1/routers/${id}/interfaces`, { subnet_id: subnetId }, token, projectId);
			await fetchRouter();
			return true;
		} catch (e) {
			toast.error('인터페이스 추가 실패: ' + (e instanceof ApiError ? e.message : String(e)));
			return false;
		} finally {
			saving = false;
		}
	}

	async function removeInterface(subnetId: string): Promise<void> {
		if (!await confirmDialog('인터페이스를 제거하시겠습니까?')) return;
		saving = true;
		try {
			await api.delete(`/api/v1/routers/${id}/interfaces/${subnetId}`, token, projectId);
			await fetchRouter();
		} catch (e) {
			toast.error('인터페이스 제거 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			saving = false;
		}
	}

	async function setGateway(externalNetworkId: string): Promise<boolean> {
		saving = true;
		try {
			await api.post(`/api/v1/routers/${id}/gateway`, { external_network_id: externalNetworkId }, token, projectId);
			await fetchRouter();
			return true;
		} catch (e) {
			toast.error('게이트웨이 설정 실패: ' + (e instanceof ApiError ? e.message : String(e)));
			return false;
		} finally {
			saving = false;
		}
	}

	async function removeGateway(): Promise<void> {
		if (!await confirmDialog('외부 게이트웨이를 제거하시겠습니까?')) return;
		saving = true;
		try {
			await api.delete(`/api/v1/routers/${id}/gateway`, token, projectId);
			await fetchRouter();
		} catch (e) {
			toast.error('게이트웨이 제거 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			saving = false;
		}
	}

	async function deleteRouter(): Promise<void> {
		if (!await confirmDialog(`라우터 "${router?.name || id}"을 삭제하시겠습니까?`)) return;
		saving = true;
		try {
			await api.delete(`/api/v1/routers/${id}`, token, projectId);
			goto('/dashboard/network/routers');
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
			saving = false;
		}
	}
</script>

<div class="max-w-4xl mx-auto px-4 py-8 text-ink-1">
	{#if loading}
		<div class="text-ink-3">불러오는 중...</div>
	{:else if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{error}</div>
	{:else if router}
		<RouterDetailWithRefreshHeader
			{router}
			{saving}
			{ar}
			onManualRefresh={() => fetchRouter()}
			onDelete={deleteRouter}
			onBack={() => goto('/dashboard/network/routers')}
		/>
		<RouterGatewaySection
			{router}
			{externalNetworks}
			{saving}
			onSet={setGateway}
			onRemove={removeGateway}
		/>
		<RouterInterfacesSection
			{router}
			{availableNetworks}
			{saving}
			{token}
			{projectId}
			onAdd={addInterface}
			onRemove={removeInterface}
		/>
	{/if}
</div>
