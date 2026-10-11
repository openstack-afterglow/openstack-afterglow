<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { untrack } from 'svelte';
	import { page } from '$app/stores';
	import { Alert, Button, Field, ResourceToolbar, SelectInput, TextInput } from '$lib/components/ui';
	import { projectNames } from '$lib/stores/projectNames';
	import { filterNetworks, type NetworkFlagFilter } from '$lib/components/admin/networks/networkList';
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
	import { t } from '$lib/i18n/ns/admin-network';

	let networks = $state<AdminNetwork[]>([]);
	let loading = $state(true);
	let tsData = $state<TsPoint[]>([]);
	let tsRange = $state('7d');
	let tsLoading = $state(true);
	let error = $state('');
	let tsError = $state('');
	let hasInventory = $state(false);
	let ownerNames = $state<ReadonlyMap<string, string>>(new Map());
	let ownerWarning = $state(false);
	let search = $state('');
	let external = $state<NetworkFlagFilter>('all');
	let shared = $state<NetworkFlagFilter>('all');
	let internal = $state<NetworkFlagFilter>('all');
	let requestGeneration = 0;
	let timeseriesGeneration = 0;
	let scopeGeneration = 0;
	const filteredNetworks = $derived(filterNetworks(networks, { search, external, shared, internal }, ownerNames, {
		external: t('adminNetworkTable.external'), shared: t('adminNetworkTable.shared'), internal: t('adminNetworkTable.internal'),
	}));
	const hasFilters = $derived(Boolean(search || external !== 'all' || shared !== 'all' || internal !== 'all'));

	function resetFilters() {
		search = '';
		external = shared = internal = 'all';
	}

	function scopeKey() {
		return JSON.stringify([$auth.token, $auth.userId, $auth.projectId, $page.url.pathname]);
	}
	const currentScope = $derived(scopeKey());

	$effect(() => {
		const scope = scopeKey();
		const tok = token;
		const project = projectId;
		const user = $auth.userId ?? undefined;
		const pathname = $page.url.pathname;
		untrack(() => {
			networks = [];
			tsData = [];
			hasInventory = false;
			error = tsError = '';
			ownerNames = new Map();
			ownerWarning = false;
			showCreate = false;
			editNet = deleteNet = null;
			loading = tsLoading = false;
			if (tok && pathname === '/admin/networks') {
				void loadNetworks();
				void loadTimeseries(tsRange);
				void loadOwnerNames(scope, scopeGeneration, tok, project, user);
			}
		});
		return () => { ++scopeGeneration; ++requestGeneration; ++timeseriesGeneration; };
	});

	async function loadOwnerNames(scope: string, generation: number, tok: string, project?: string, user?: string) {
		const result = await projectNames.loadResult(tok, project, user);
		if (scope !== scopeKey() || generation !== scopeGeneration) return;
		ownerNames = result.names;
		ownerWarning = result.failed;
	}

	let showCreate = $state(false);
	let editNet = $state<AdminNetwork | null>(null);
	let deleteNet = $state<AdminNetwork | null>(null);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function loadNetworks() {
		if (!token || $page.url.pathname !== '/admin/networks') return;
		const generation = ++requestGeneration;
		const scope = scopeKey();
		const tok = token;
		const project = projectId;
		const owns = () => generation === requestGeneration && scope === scopeKey();
		loading = true;
		error = '';
		try {
			const rows = await api.get<AdminNetwork[]>('/api/v1/admin/all-networks', tok, project);
			if (!owns()) return;
			networks = rows;
			hasInventory = true;
		} catch (e) {
			if (owns()) error = e instanceof ApiError ? e.message : t('networksPage.error.loadFailed');
		} finally {
			if (owns()) loading = false;
		}
	}

	async function loadTimeseries(range: string, opts?: { background?: boolean }) {
		if (!token || $page.url.pathname !== '/admin/networks') return;
		const generation = ++timeseriesGeneration;
		const scope = scopeKey();
		const tok = token;
		const project = projectId;
		const owns = () => generation === timeseriesGeneration && scope === scopeKey() && range === tsRange;
		if (!opts?.background) tsLoading = true;
		tsError = '';
		try {
			const data = await api.get<TsPoint[]>(`/api/v1/admin/timeseries/networks?range=${range}`, tok, project);
			if (owns()) tsData = data;
		} catch {
			if (owns()) tsError = t('networksPage.error.timeseriesFailed');
		} finally {
			if (owns()) tsLoading = false;
		}
	}

	async function createNetwork(form: { name: string; cidr: string; is_external: boolean; is_shared: boolean; enable_dhcp: boolean }): Promise<string | true> {
		const scope = scopeKey();
		const generation = scopeGeneration;
		try {
			await api.post('/api/v1/admin/networks', {
				name: form.name,
				cidr: form.cidr || null,
				is_external: form.is_external,
				is_shared: form.is_shared,
				enable_dhcp: form.enable_dhcp,
			}, token, projectId);
			if (scope !== scopeKey() || generation !== scopeGeneration) return t('networksPage.error.scopeChanged');
			await loadNetworks();
			if (scope !== scopeKey() || generation !== scopeGeneration) return t('networksPage.error.scopeChanged');
			return true;
		} catch (e) {
			if (scope !== scopeKey() || generation !== scopeGeneration) return t('networksPage.error.scopeChanged');
			return e instanceof ApiError ? e.message : t('networksPage.error.createFailed');
		}
	}

	async function updateNetwork(id: string, form: { name: string; is_shared: boolean }): Promise<string | true> {
		const scope = scopeKey();
		const generation = scopeGeneration;
		try {
			await api.put(`/api/v1/admin/networks/${id}`, form, token, projectId);
			if (scope !== scopeKey() || generation !== scopeGeneration) return t('networksPage.error.scopeChanged');
			await loadNetworks();
			if (scope !== scopeKey() || generation !== scopeGeneration) return t('networksPage.error.scopeChanged');
			return true;
		} catch (e) {
			if (scope !== scopeKey() || generation !== scopeGeneration) return t('networksPage.error.scopeChanged');
			return e instanceof ApiError ? e.message : t('networksPage.error.updateFailed');
		}
	}

	async function deleteNetwork(id: string): Promise<string | true> {
		const scope = scopeKey();
		const generation = scopeGeneration;
		try {
			await api.delete(`/api/v1/admin/networks/${id}`, token, projectId);
			if (scope !== scopeKey() || generation !== scopeGeneration) return t('networksPage.error.scopeChanged');
			await loadNetworks();
			if (scope !== scopeKey() || generation !== scopeGeneration) return t('networksPage.error.scopeChanged');
			return true;
		} catch (e) {
			if (scope !== scopeKey() || generation !== scopeGeneration) return t('networksPage.error.scopeChanged');
			return e instanceof ApiError ? e.message : t('networksPage.error.deleteFailed');
		}
	}

	const ar = createAutoRefresh(
		() => { loadNetworks(); loadTimeseries(tsRange, { background: true }); },
		{ storageKey: 'admin-networks', defaultInterval: 30, intervalOptions: [15, 30, 60], invokeOnMount: false }
	);

</script>

<PageShell>
	<PageHeader breadcrumb={t('networksPage.breadcrumb')} title={t('networksPage.title')}>
		{#snippet actions()}
			<button onclick={() => { showCreate = true; }} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg">{t('networksPage.actions.create')}</button>
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

	{#if tsError}<Alert tone="warning" title={t('networksPage.timeseriesWarning')}>{tsError}</Alert>{/if}

	<ResourceToolbar label={t('networksPage.filters.label')} class="mb-3">
		<Field label={t('networksPage.filters.search')} for="network-search" class="w-full md:flex-1 md:min-w-64">
			<TextInput id="network-search" type="search" bind:value={search} placeholder={t('networksPage.filters.searchPlaceholder')} />
		</Field>
		<Field label={t('adminNetworkTable.external')} for="network-external" class="w-full sm:w-auto">
			<SelectInput id="network-external" bind:value={() => external, (value) => external = value as NetworkFlagFilter}>
				<option value="all">{t('networksPage.filters.all')}</option>
				<option value="yes">{t('networksPage.filters.yes')}</option>
				<option value="no">{t('networksPage.filters.no')}</option>
			</SelectInput>
		</Field>
		<Field label={t('adminNetworkTable.shared')} for="network-shared" class="w-full sm:w-auto">
			<SelectInput id="network-shared" bind:value={() => shared, (value) => shared = value as NetworkFlagFilter}>
				<option value="all">{t('networksPage.filters.all')}</option>
				<option value="yes">{t('networksPage.filters.yes')}</option>
				<option value="no">{t('networksPage.filters.no')}</option>
			</SelectInput>
		</Field>
		<Field label={t('adminNetworkTable.internal')} for="network-internal" class="w-full sm:w-auto">
			<SelectInput id="network-internal" bind:value={() => internal, (value) => internal = value as NetworkFlagFilter}>
				<option value="all">{t('networksPage.filters.all')}</option>
				<option value="yes">{t('networksPage.filters.yes')}</option>
				<option value="no">{t('networksPage.filters.no')}</option>
			</SelectInput>
		</Field>
		<Button variant="ghost" size="sm" disabled={!hasFilters} onclick={resetFilters}>{t('networksPage.filters.reset')}</Button>
	</ResourceToolbar>
	<div class="flex items-center gap-2 text-xs text-ink-2 mb-3" aria-live="polite">
		{#if loading}<ActivityIndicator size="xs" label={t('networksPage.loading')} />{/if}
		{#if hasInventory}
			<span>{t('networksPage.results', { shown: filteredNetworks.length, total: networks.length })}</span>
		{:else}
			<span>{loading ? t('networksPage.loading') : t('networksPage.resultsUnavailable')}</span>
		{/if}
	</div>
	{#if error}
		<Alert tone="danger" title={t('networksPage.error.loadTitle')}>
			{error}
			{#snippet actions()}<Button variant="secondary" size="sm" onclick={loadNetworks}>{t('networksPage.retry')}</Button>{/snippet}
		</Alert>
	{/if}
	{#if ownerWarning}<Alert tone="warning" title={t('networksPage.ownerWarning')}>{t('networksPage.ownerWarningBody')}</Alert>{/if}
	<AdminNetworkTable
		networks={filteredNetworks}
		{ownerNames}
		emptyMessage={hasInventory ? (hasFilters ? t('networksPage.noMatches') : t('networksPage.empty')) : ''}
		onRowClick={(id) => goto(`/admin/networks/${id}`)}
		onEdit={(n) => { editNet = n; }}
		onDelete={(n) => { deleteNet = n; }}
	/>
</PageShell>

{#key currentScope}
	<AdminNetworkCreateModal bind:open={showCreate} onCreate={createNetwork} />
	<AdminNetworkEditModal network={editNet} onClose={() => { editNet = null; }} onSave={updateNetwork} />
	<AdminNetworkDeleteModal network={deleteNet} onClose={() => { deleteNet = null; }} onDelete={deleteNetwork} />
{/key}
