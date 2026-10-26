<script lang="ts">
	import Alert from '$lib/components/ui/Alert.svelte';
	import { t as scopeT } from '$lib/i18n/ns/domain-admin';
	let inventoryError = $state('');
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api as baseApi, ApiError } from '$lib/api/client';
	import { createAdminInventoryApi } from '$lib/api/adminInventoryScope';
	const api = createAdminInventoryApi(baseApi);
	onDestroy(api.dispose);
	import type { AdminRouter, AdminNetwork } from '$lib/types/networks';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import AdminRoutersTable from '$lib/components/admin/routers/AdminRoutersTable.svelte';
	import AdminRouterCreateModal from '$lib/components/admin/routers/AdminRouterCreateModal.svelte';
	import AdminRouterEditModal from '$lib/components/admin/routers/AdminRouterEditModal.svelte';
	import AdminRouterDeleteModal from '$lib/components/admin/routers/AdminRouterDeleteModal.svelte';
	import { t } from '$lib/i18n/ns/admin-network';

	let routers = $state<AdminRouter[]>([]);
	let loading = $state(true);
	let showCreate = $state(false);
	let externalNets = $state<AdminNetwork[]>([]);
	let editRouter = $state<AdminRouter | null>(null);
	let deleteRouter = $state<AdminRouter | null>(null);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load(force = false) {
		loading = true;
		inventoryError = '';
		try {
			routers = await api.get<AdminRouter[]>('/api/v1/admin/all-routers', token, projectId, { refresh: force });
		} catch (reason) {
			routers = []; inventoryError = reason instanceof Error ? reason.message : scopeT('state.unavailable');
		} finally {
			loading = false;
		}
	}

	function prefetchExternalNetworks() {
		if (api.isCurrent()) void baseApi.prefetch('/api/v1/admin/all-networks', token, projectId);
	}

	async function openCreate() {
		showCreate = true;
		try {
			const nets = await baseApi.get<AdminNetwork[]>('/api/v1/admin/all-networks', token, projectId);
			if (!api.isCurrent()) return;
			externalNets = nets.filter(n => n.is_external);
		} catch {
			if (api.isCurrent()) externalNets = [];
		}
	}

	async function createRouter(form: { name: string; external_network_id: string }): Promise<string | true> {
		try {
			await api.post('/api/v1/admin/routers', { name: form.name, external_network_id: form.external_network_id || null }, token, projectId);
			await load();
			return true;
		} catch (e) { return e instanceof ApiError ? e.message : t('routersPage.error.createFailed'); }
	}

	async function updateRouter(id: string, form: { name: string }): Promise<string | true> {
		try {
			await api.put(`/api/v1/admin/routers/${id}`, { name: form.name }, token, projectId);
			await load();
			return true;
		} catch (e) { return e instanceof ApiError ? e.message : t('routersPage.error.updateFailed'); }
	}

	async function deleteRouterFn(id: string): Promise<string | true> {
		try {
			await api.delete(`/api/v1/admin/routers/${id}`, token, projectId);
			await load();
			return true;
		} catch (e) { return e instanceof ApiError ? e.message : t('routersPage.error.deleteFailed'); }
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

<PageShell>
	<PageHeader breadcrumb={t('routersPage.breadcrumb')} title={t('routersPage.title')}>
		{#snippet actions()}
			<button onclick={openCreate} onpointerenter={prefetchExternalNetworks} onfocus={prefetchExternalNetworks} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg">{t('routersPage.actions.create')}</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading}
				onManualRefresh={ar.refresh}
			/>
		{/snippet}
	</PageHeader>

	{#if inventoryError}<Alert tone="danger">{inventoryError}</Alert>
	{:else if loading}
		<div class="text-ink-2 text-sm"><ActivityIndicator size="sm" label={t('routersPage.loading')} /></div>
	{:else}
		<AdminRoutersTable {routers} onEdit={(r) => { editRouter = r; }} onDelete={(r) => { deleteRouter = r; }} />
		<div class="mt-3 text-xs text-ink-2">{t('routersPage.summary.total', { count: routers.length })}</div>
	{/if}
</PageShell>
