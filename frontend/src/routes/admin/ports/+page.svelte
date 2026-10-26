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
	import { projectNames } from '$lib/stores/projectNames';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createIntentPrefetchScheduler } from '$lib/utils/intentPrefetch';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import PortsTable from '$lib/components/admin/ports/PortsTable.svelte';
	import PortCreateModal from '$lib/components/admin/ports/PortCreateModal.svelte';
	import PortEditModal from '$lib/components/admin/ports/PortEditModal.svelte';
	import PortDeleteModal from '$lib/components/admin/ports/PortDeleteModal.svelte';
	import PortsFilterBar from '$lib/components/admin/ports/PortsFilterBar.svelte';
	import type { PortInfo, NetworkInfo } from '$lib/types/networks';
	import type { PagedResponse } from '$lib/types/adminPort';
	import { t } from '$lib/i18n/ns/admin-network';

	let ports = $state<PortInfo[]>([]);
	let loading = $state(true);
	let pageSize = $state(20);
	let markerStack = $state<string[]>([]);
	let nextMarker = $state<string | null>(null);
	let filter = $state('');
	let allNetworks = $state<NetworkInfo[]>([]);

	let editPort = $state<PortInfo | null>(null);
	let updating = $state(false);
	let editError = $state('');
	let deletePort = $state<PortInfo | null>(null);
	let showCreate = $state(false);
	let creating = $state(false);
	let createError = $state('');
	let loadGeneration = 0;

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const nextPrefetch = createIntentPrefetchScheduler();
	function listPath(marker?: string): string {
		const params = new URLSearchParams({ limit: String(pageSize) });
		if (marker) params.set('marker', marker);
		return `/api/v1/admin/all-ports?${params}`;
	}
	function prefetchNext() {
		if (!nextMarker) return;
		const path = listPath(nextMarker);
		const key = JSON.stringify([path, token ?? null, projectId ?? null]);
		nextPrefetch.intent(key, (signal) => api.prefetch(path, token, projectId, { signal }));
	}

	const filtered = $derived(
		filter
			? ports.filter(p =>
				p.name?.includes(filter) ||
				p.device_owner?.includes(filter) ||
				p.fixed_ips.some(ip => ip.ip_address?.includes(filter)) ||
				(p.project_id && ($projectNames.get(p.project_id) ?? p.project_id)?.includes(filter))
			)
			: ports
	);

	async function load(marker?: string, force = false) {
		const generation = ++loadGeneration;
		const requestToken = $auth.token ?? undefined;
		const requestProjectId = $auth.projectId ?? undefined;
		const requestPageSize = pageSize;
		const requestPath = listPath(marker);
		const owns = () => generation === loadGeneration
			&& ($auth.token ?? undefined) === requestToken
			&& ($auth.projectId ?? undefined) === requestProjectId
			&& pageSize === requestPageSize
			&& listPath(marker) === requestPath;
		nextPrefetch.cancel();
		loading = true;
		inventoryError = '';
		try {
			const res = await api.get<PagedResponse<PortInfo>>(requestPath, requestToken, requestProjectId, force ? { refresh: true } : undefined);
			if (!owns()) return;
			ports = res.items || [];
			nextMarker = res.next_marker;
			const path = nextMarker ? listPath(nextMarker) : null;
			const key = path ? JSON.stringify([path, requestToken ?? null, requestProjectId ?? null]) : null;
			nextPrefetch.schedule(key, (signal) => path ? api.prefetch(path, requestToken, requestProjectId, { signal }) : undefined);
		} catch (reason) {
			if (owns()) { ports = []; inventoryError = reason instanceof Error ? reason.message : scopeT('state.unavailable'); }
		} finally {
			if (owns()) loading = false;
		}
	}


	async function loadNetworks() {
		try {
			const networks = await baseApi.get<NetworkInfo[]>('/api/v1/admin/all-networks', token, projectId);
			if (api.isCurrent()) allNetworks = networks;
		} catch { if (api.isCurrent()) allNetworks = []; }
	}

	async function updatePort(name: string): Promise<boolean> {
		if (!editPort) return false;
		updating = true; editError = '';
		try {
			await api.put(`/api/v1/admin/ports/${editPort.id}`, { name }, token, projectId);
			editPort = null;
			await load(markerStack[markerStack.length - 1]);
			return true;
		} catch (e) { editError = e instanceof ApiError ? e.message : t('portsPage.error.updateFailed'); return false; } finally { updating = false; }
	}

	async function doDelete(id: string): Promise<string | true> {
		try {
			await api.delete(`/api/v1/admin/ports/${id}`, token, projectId);
			await load(markerStack[markerStack.length - 1]);
			return true;
		} catch (e) { return e instanceof ApiError ? e.message : t('portsPage.error.deleteFailed'); }
	}

	async function createPort(form: { network_id: string; name: string; project_id: string; fixed_ip: string }): Promise<boolean> {
		creating = true; createError = '';
		try {
			await api.post('/api/v1/admin/ports', {
				network_id: form.network_id,
				name: form.name || undefined,
				project_id: form.project_id || undefined,
				fixed_ip: form.fixed_ip || undefined,
			}, token, projectId);
			showCreate = false;
			markerStack = []; nextMarker = null;
			await load();
			return true;
		} catch (e) { createError = e instanceof ApiError ? e.message : t('portsPage.error.createFailed'); return false; } finally { creating = false; }
	}

	const ar = createAutoRefresh(
		() => load(markerStack[markerStack.length - 1]),
		{ storageKey: 'admin-ports', defaultInterval: 30, intervalOptions: [15, 30, 60], invokeOnMount: false }
	);

	onMount(() => {
		if (window.matchMedia('(max-width: 767px)').matches) pageSize = 10;
		load();
		void projectNames.load(token, projectId);
		loadNetworks();
	});
	onDestroy(() => { loadGeneration += 1; nextPrefetch.cancel(); });
</script>


<PortCreateModal
	bind:open={showCreate}
	{allNetworks}
	{creating}
	error={createError}
	onCreate={createPort}
/>
<PortEditModal
	bind:target={editPort}
	{updating}
	error={editError}
	onSave={updatePort}
/>
<PortDeleteModal bind:port={deletePort} onConfirm={doDelete} />

<PageShell>
	<PageHeader breadcrumb={t('portsPage.breadcrumb')} title={t('portsPage.title')}>
		{#snippet actions()}
			<button onclick={() => { showCreate = true; createError = ''; }} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg">{t('portsPage.actions.create')}</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading}
				onManualRefresh={() => { markerStack = []; nextMarker = null; return load(undefined, true); }}
			/>
			<div class="flex items-center gap-1 text-xs text-ink-2 max-md:hidden">
				{t('portsPage.pageSize')}
				{#each [10, 20, 30] as n}
					<button
						onclick={() => { pageSize = n; markerStack = []; nextMarker = null; load(); }}
						class="px-2 py-0.5 rounded {pageSize === n ? 'bg-action-warm text-ink-0' : 'bg-surface-sunken hover:bg-surface-selected text-ink-2'}"
					>{n}</button>
				{/each}
			</div>
		{/snippet}
	</PageHeader>

	<PortsFilterBar
		bind:search={filter}
	/>

	{#if inventoryError}<Alert tone="danger">{inventoryError}</Alert>
	{:else if loading}
		<div class="text-ink-2 text-sm"><ActivityIndicator size="sm" label={t('portsPage.loading')} /></div>
	{:else}
		<PortsTable
			ports={filtered}
			{markerStack}
			{nextMarker}
			onEdit={(p) => { editPort = p; editError = ''; }}
			onDelete={(p) => { deletePort = p; }}
			onPrev={() => {
				const prev = markerStack.slice(0, -1);
				const marker = prev[prev.length - 1];
				markerStack = prev;
				load(marker);
			}}
			onNext={() => {
				if (!nextMarker) return;
				markerStack = [...markerStack, nextMarker];
				load(nextMarker);
			}}
			onintent={prefetchNext}
		/>
	{/if}
</PageShell>
