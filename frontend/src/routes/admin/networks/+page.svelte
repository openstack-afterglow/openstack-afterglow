<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { TsPoint } from '$lib/types/common';
	import type { AdminNetwork } from '$lib/types/networks';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import AdminNetworkTimeseries from '$lib/components/admin/networks/AdminNetworkTimeseries.svelte';
	import AdminNetworkTable from '$lib/components/admin/networks/AdminNetworkTable.svelte';
	import AdminNetworkCreateModal from '$lib/components/admin/networks/AdminNetworkCreateModal.svelte';
	import AdminNetworkEditModal from '$lib/components/admin/networks/AdminNetworkEditModal.svelte';
	import AdminNetworkDeleteModal from '$lib/components/admin/networks/AdminNetworkDeleteModal.svelte';

	let networks = $state<AdminNetwork[]>([]);
	let loading = $state(true);
	let tsData = $state<TsPoint[]>([]);
	let tsRange = $state('7d');
	let tsLoading = $state(true);

	let showCreate = $state(false);
	let editNet = $state<AdminNetwork | null>(null);
	let deleteNet = $state<AdminNetwork | null>(null);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function loadNetworks() {
		loading = true;
		try {
			networks = await api.get<AdminNetwork[]>('/api/v1/admin/all-networks', token, projectId);
		} catch {
			networks = [];
		} finally {
			loading = false;
		}
	}

	async function loadTimeseries(range: string, opts?: { background?: boolean }) {
		if (!opts?.background) tsLoading = true;
		try {
			tsData = await api.get<TsPoint[]>(`/api/v1/admin/timeseries/networks?range=${range}`, token, projectId);
		} catch {
			if (!opts?.background) tsData = [];
		} finally {
			if (!opts?.background) tsLoading = false;
		}
	}

	async function createNetwork(form: { name: string; cidr: string; is_external: boolean; is_shared: boolean; enable_dhcp: boolean }): Promise<string | true> {
		try {
			await api.post('/api/v1/admin/networks', {
				name: form.name,
				cidr: form.cidr || null,
				is_external: form.is_external,
				is_shared: form.is_shared,
				enable_dhcp: form.enable_dhcp,
			}, token, projectId);
			await loadNetworks();
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : '생성 실패';
		}
	}

	async function updateNetwork(id: string, form: { name: string; is_shared: boolean }): Promise<string | true> {
		try {
			await api.put(`/api/v1/admin/networks/${id}`, form, token, projectId);
			await loadNetworks();
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : '수정 실패';
		}
	}

	async function deleteNetwork(id: string): Promise<string | true> {
		try {
			await api.delete(`/api/v1/admin/networks/${id}`, token, projectId);
			await loadNetworks();
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : '삭제 실패';
		}
	}

	const ar = createAutoRefresh(
		() => { loadNetworks(); loadTimeseries(tsRange, { background: true }); },
		{ storageKey: 'admin-networks', defaultInterval: 30, intervalOptions: [15, 30, 60], invokeOnMount: false }
	);

	onMount(() => { loadNetworks(); loadTimeseries(tsRange); });
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<PageHeader breadcrumb="NETWORK / NETWORKS" title="네트워크">
		{#snippet actions()}
			<button onclick={() => { showCreate = true; }} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg">+ 생성</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading}
				onManualRefresh={loadNetworks}
			/>
		{/snippet}
	</PageHeader>

	<AdminNetworkTimeseries
		data={tsData}
		loading={tsLoading}
		range={tsRange}
		onRangeChange={(r) => { tsRange = r; loadTimeseries(r); }}
	/>

	{#if loading}
		<div class="text-ink-3 text-sm">로딩 중...</div>
	{:else}
		<AdminNetworkTable
			{networks}
			onRowClick={(id) => goto(`/admin/networks/${id}`)}
			onEdit={(n) => { editNet = n; }}
			onDelete={(n) => { deleteNet = n; }}
		/>
	{/if}
</div>

<AdminNetworkCreateModal bind:open={showCreate} onCreate={createNetwork} />
<AdminNetworkEditModal network={editNet} onClose={() => { editNet = null; }} onSave={updateNetwork} />
<AdminNetworkDeleteModal network={deleteNet} onClose={() => { deleteNet = null; }} onDelete={deleteNetwork} />
