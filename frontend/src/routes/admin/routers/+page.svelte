<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { AdminRouter, AdminNetwork } from '$lib/types/networks';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import AdminRoutersTable from '$lib/components/admin/routers/AdminRoutersTable.svelte';
	import AdminRouterCreateModal from '$lib/components/admin/routers/AdminRouterCreateModal.svelte';
	import AdminRouterEditModal from '$lib/components/admin/routers/AdminRouterEditModal.svelte';
	import AdminRouterDeleteModal from '$lib/components/admin/routers/AdminRouterDeleteModal.svelte';

	let routers = $state<AdminRouter[]>([]);
	let loading = $state(true);
	let showCreate = $state(false);
	let externalNets = $state<AdminNetwork[]>([]);
	let editRouter = $state<AdminRouter | null>(null);
	let deleteRouter = $state<AdminRouter | null>(null);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load() {
		loading = true;
		try {
			routers = await api.get<AdminRouter[]>('/api/v1/admin/all-routers', token, projectId);
		} catch {
			routers = [];
		} finally {
			loading = false;
		}
	}

	function prefetchExternalNetworks() {
		void api.prefetch('/api/v1/admin/all-networks', token, projectId);
	}

	async function openCreate() {
		showCreate = true;
		try {
			const nets = await api.get<AdminNetwork[]>('/api/v1/admin/all-networks', token, projectId);
			externalNets = nets.filter(n => n.is_external);
		} catch {
			externalNets = [];
		}
	}

	async function createRouter(form: { name: string; external_network_id: string }): Promise<string | true> {
		try {
			await api.post('/api/v1/admin/routers', { name: form.name, external_network_id: form.external_network_id || null }, token, projectId);
			await load();
			return true;
		} catch (e) { return e instanceof ApiError ? e.message : '생성 실패'; }
	}

	async function updateRouter(id: string, form: { name: string }): Promise<string | true> {
		try {
			await api.put(`/api/v1/admin/routers/${id}`, { name: form.name }, token, projectId);
			await load();
			return true;
		} catch (e) { return e instanceof ApiError ? e.message : '수정 실패'; }
	}

	async function deleteRouterFn(id: string): Promise<string | true> {
		try {
			await api.delete(`/api/v1/admin/routers/${id}`, token, projectId);
			await load();
			return true;
		} catch (e) { return e instanceof ApiError ? e.message : '삭제 실패'; }
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-routers',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60]
	});

	onMount(load);
</script>

<AdminRouterCreateModal bind:open={showCreate} externalNetworks={externalNets} onCreate={createRouter} />
<AdminRouterEditModal bind:router={editRouter} onUpdate={updateRouter} />
<AdminRouterDeleteModal bind:router={deleteRouter} onConfirm={deleteRouterFn} />

<div class="p-4 md:p-8 max-w-7xl mx-auto">
	<PageHeader breadcrumb="NETWORK / ROUTERS" title="라우터">
		{#snippet actions()}
			<button onclick={openCreate} onpointerenter={prefetchExternalNetworks} onfocus={prefetchExternalNetworks} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg">+ 생성</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading}
				onManualRefresh={load}
			/>
		{/snippet}
	</PageHeader>

	{#if loading}
		<div class="text-ink-3 text-sm">로딩 중...</div>
	{:else}
		<AdminRoutersTable {routers} onEdit={(r) => { editRouter = r; }} onDelete={(r) => { deleteRouter = r; }} />
		<div class="mt-3 text-xs text-ink-3">총 {routers.length}개 라우터</div>
	{/if}
</div>
