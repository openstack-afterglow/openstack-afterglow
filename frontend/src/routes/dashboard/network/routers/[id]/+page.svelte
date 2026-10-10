<script lang="ts">
	import { t } from '$lib/i18n/ns/network-pages';
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
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

	const id = $derived($page.params.id);

	let router = $state<RouterDetail | null>(null);
	let loading = $state(true);
	let error = $state('');
	let saving = $state(false);
	let availableNetworks = $state<Network[]>([]);
	let externalNetworks = $state<Network[]>([]);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const canManageRouter = $derived(
		Boolean(router && ($auth.isSystemAdmin || (router.project_id && router.project_id === projectId)))
	);
	async function fetchRouter() {
		try {
			router = await api.get<RouterDetail>(`/api/v1/routers/${id}`, token, projectId);
			error = '';
		} catch (e) {
			error = e instanceof ApiError ? e.message : t('routerDetail.loadFailed');
		} finally {
			loading = false;
		}
	}

	async function fetchNetworks() {
		try {
			const nets = await api.get<Network[]>('/api/v1/networks', token, projectId);
			availableNetworks = nets.filter(n => !n.is_external && n.project_id === projectId);
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
		if (!canManageRouter) return false;
		saving = true;
		try {
			await api.post(`/api/v1/routers/${id}/interfaces`, { subnet_id: subnetId }, token, projectId);
			await fetchRouter();
			return true;
		} catch (e) {
			toast.error(t('routerDetail.addInterfaceFailed', { error: e instanceof ApiError ? e.message : String(e) }));
			return false;
		} finally {
			saving = false;
		}
	}

	async function removeInterface(subnetId: string): Promise<void> {
		if (!canManageRouter) return;
		if (!await confirmDialog(t('routerDetail.removeInterfaceConfirm'))) return;
		saving = true;
		try {
			await api.delete(`/api/v1/routers/${id}/interfaces/${subnetId}`, token, projectId);
			await fetchRouter();
		} catch (e) {
			toast.error(t('routerDetail.removeInterfaceFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			saving = false;
		}
	}

	async function setGateway(externalNetworkId: string): Promise<boolean> {
		if (!canManageRouter) return false;
		saving = true;
		try {
			await api.post(`/api/v1/routers/${id}/gateway`, { external_network_id: externalNetworkId }, token, projectId);
			await fetchRouter();
			return true;
		} catch (e) {
			toast.error(t('routerDetail.setGatewayFailed', { error: e instanceof ApiError ? e.message : String(e) }));
			return false;
		} finally {
			saving = false;
		}
	}

	async function removeGateway(): Promise<void> {
		if (!canManageRouter) return;
		if (!await confirmDialog(t('routerDetail.removeGatewayConfirm'))) return;
		saving = true;
		try {
			await api.delete(`/api/v1/routers/${id}/gateway`, token, projectId);
			await fetchRouter();
		} catch (e) {
			toast.error(t('routerDetail.removeGatewayFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			saving = false;
		}
	}

	async function deleteRouter(): Promise<void> {
		if (!canManageRouter) return;
		if (!await confirmDialog(t('routerDetail.deleteConfirm', { name: router?.name || id }))) return;
		saving = true;
		try {
			await api.delete(`/api/v1/routers/${id}`, token, projectId);
			goto('/dashboard/network/routers');
		} catch (e) {
			toast.error(t('routerDetail.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
			saving = false;
		}
	}
</script>

<!-- loading은 첫 조회에만 켜지므로 섹션 진입은 최초 도착에서만 재생된다. -->
<div class="motion-stagger max-w-4xl mx-auto px-4 py-8 text-ink-1">
	{#if loading}
		<ActivityIndicator label={t('routerDetail.loading')} />
	{:else if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">{error}</div>
	{:else if router}
		<RouterDetailWithRefreshHeader
			{router}
			{saving}
			{ar}
			onManualRefresh={() => fetchRouter()}
			canManage={canManageRouter}
			onDelete={deleteRouter}
			onBack={() => goto('/dashboard/network/routers')}
		/>
		<RouterGatewaySection
			{router}
			{externalNetworks}
			{saving}
			canManage={canManageRouter}
			onSet={setGateway}
			onRemove={removeGateway}
		/>
		<RouterInterfacesSection
			{router}
			{availableNetworks}
			{saving}
			{token}
			{projectId}
			canManage={canManageRouter}
			onAdd={addInterface}
			onRemove={removeInterface}
		/>
	{/if}
</div>
