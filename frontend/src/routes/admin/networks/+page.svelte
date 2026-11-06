<script lang="ts">
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { onDestroy, untrack } from 'svelte';
	import { page } from '$app/stores';
	import { Alert, Button, Field, Pagination, ResourceToolbar, SelectInput } from '$lib/components/ui';
	import { projectNames } from '$lib/stores/projectNames';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { api as baseApi, ApiError } from '$lib/api/client';
	import { createAdminInventoryApi } from '$lib/api/adminInventoryScope';
	const api = createAdminInventoryApi(baseApi);
	onDestroy(api.dispose);
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
	let ownerDomains = $state<ReadonlyMap<string, string>>(new Map());
	let ownerWarning = $state(false);
	let search = $state('');
	let displayPage = $state(1);
	let pageSize = $state(20);
	let analyticsOpen = $state(false);
	let requestGeneration = 0;
	let timeseriesGeneration = 0;
	let scopeGeneration = 0;
	const columns: TableColumn<AdminNetwork>[] = $derived([
		{ key: 'name', label: t('adminNetworkTable.name'), value: (row) => row.name || row.id },
		{ key: 'owner', label: t('adminNetworkTable.owner'), value: (row) => row.project_id, format: (_value, row) => row.project_id ? ownerNames.get(row.project_id) ?? row.project_name ?? row.project_id : '—' },
		{ key: 'status', label: t('adminNetworkTable.status'), value: (row) => row.status },
		{ key: 'type', label: t('adminNetworkTable.type'), value: (row) => `${row.is_external ? t('adminNetworkTable.external') : t('adminNetworkTable.internal')}${row.is_shared ? ` · ${t('adminNetworkTable.shared')}` : ''}` },
		{ key: 'subnets', label: t('adminNetworkTable.subnets'), value: (row) => row.subnets.length },
	]);
	const view = createTableView({ locale: intlLocale, rows: () => networks, columns: () => columns, search: () => search,
		searchable: (row) => [row.name, row.id, row.project_id, row.project_name, row.project_id ? ownerNames.get(row.project_id) : '', row.status, row.is_external ? t('adminNetworkTable.external') : t('adminNetworkTable.internal'), row.is_shared ? t('adminNetworkTable.shared') : ''].filter((value) => value != null).map(String) });
	let viewOwner = '';
	$effect(() => {
		const owner = JSON.stringify([$auth.userId, $auth.projectId, Boolean($auth.token)]);
		if (owner !== viewOwner) { viewOwner = owner; search = ''; view.reset(); }
	});
	const filteredNetworks = $derived(view.rows);
	const hasFilters = $derived(Boolean(search || Object.keys(view.filters).length || view.sort));
	const pageCount = $derived(Math.max(1, Math.ceil(filteredNetworks.length / pageSize)));
	const visibleNetworks = $derived(filteredNetworks.slice((Math.min(displayPage, pageCount) - 1) * pageSize, Math.min(displayPage, pageCount) * pageSize));
	$effect(() => { search; view.filters; view.sort; pageSize; displayPage = 1; });
	$effect(() => { if (displayPage > pageCount) displayPage = pageCount; });

	function resetFilters() {
		search = '';
		view.reset();
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
			ownerDomains = new Map();
			ownerWarning = false;
			showCreate = false;
			editNet = deleteNet = null;
			loading = tsLoading = false;
			if (tok && pathname === '/admin/networks') {
				void loadNetworks();
				if (!api.scoped) void loadTimeseries(tsRange);
				void loadOwnerNames(scope, scopeGeneration, tok, project, user);
			}
		});
		return () => { ++scopeGeneration; ++requestGeneration; ++timeseriesGeneration; };
	});

	async function loadOwnerNames(scope: string, generation: number, tok: string, project?: string, user?: string) {
		const result = await projectNames.loadMetadata(tok, project, user);
		if (scope !== scopeKey() || generation !== scopeGeneration) return;
		ownerNames = new Map(result.projects.map((project) => [project.id, project.name]));
		ownerDomains = new Map(result.projects.filter((project) => project.domain_id).map((project) => [project.id, project.domain_id!]));
		ownerWarning = result.failed;
	}

	let showCreate = $state(false);
	let editNet = $state<AdminNetwork | null>(null);
	let deleteNet = $state<AdminNetwork | null>(null);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function loadNetworks(force = false) {
		if (!token || $page.url.pathname !== '/admin/networks') return;
		const generation = ++requestGeneration;
		const scope = scopeKey();
		const tok = token;
		const project = projectId;
		const owns = () => generation === requestGeneration && scope === scopeKey();
		loading = true;
		error = '';
		try {
			const rows = await api.get<AdminNetwork[]>('/api/v1/admin/all-networks', tok, project, { refresh: force });
			if (!owns()) return;
			networks = rows;
			hasInventory = true;
		} catch (e) {
			if (owns()) error = e instanceof ApiError ? e.message : t('networksPage.error.loadFailed');
		} finally {
			if (owns()) loading = false;
		}
	}

	async function loadTimeseries(range: string, opts?: { background?: boolean; force?: boolean }) {
		if (!token || $page.url.pathname !== '/admin/networks') return;
		const generation = ++timeseriesGeneration;
		const scope = scopeKey();
		const tok = token;
		const project = projectId;
		const owns = () => generation === timeseriesGeneration && scope === scopeKey() && range === tsRange;
		if (!opts?.background) tsLoading = true;
		tsError = '';
		try {
			const data = await api.get<TsPoint[]>(`/api/v1/admin/timeseries/networks?range=${range}`, tok, project, { refresh: opts?.force ?? false });
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

	async function refreshAll(force = false) {
		await Promise.allSettled([
			loadNetworks(force),
			...(!api.scoped ? [loadTimeseries(tsRange, { background: true, force })] : []),
		]);
	}

	const ar = createAutoRefresh(
		() => refreshAll(),
		{ storageKey: 'admin-networks', defaultInterval: 30, intervalOptions: [15, 30, 60], invokeOnMount: false }
	);

</script>

<PageShell>
	<PageHeader breadcrumb={t('networksPage.breadcrumb')} title={hasInventory ? `${t('networksPage.title')} (${networks.length})` : t('networksPage.title')}>
		{#snippet actions()}
			<Button variant="primary" onclick={() => { showCreate = true; }}>{t('networksPage.actions.create')}</Button>
		{/snippet}
	</PageHeader>
	<div class="flex flex-wrap items-center gap-3 text-[13px] text-ink-2 mb-3" aria-live="polite">
		{#if loading && hasInventory}<LoadingState variant="inline" label={t('networksPage.loading')} />{/if}
		<span>{api.scoped ? [api.filter.domainId, api.filter.projectId ? ownerNames.get(api.filter.projectId) || api.filter.projectId : ''].filter(Boolean).join(' / ') : t('portsFilterBar.allProjects')}</span>
		<span>{hasInventory ? t('networksPage.results', { shown: filteredNetworks.length, total: networks.length }) : loading ? t('networksPage.loading') : t('networksPage.resultsUnavailable')}</span>
		<Button href="/admin/subnets" variant="ghost" size="sm">{t('subnetSection.title')}</Button>
	</div>

	<ResourceToolbar label={t('networksPage.filters.label')} class="mb-3">
		<RegexSearch id="network-search" bind:value={search} label={t('networksPage.filters.search')} placeholder={t('networksPage.filters.searchPlaceholder')} />
		<Button variant="ghost" size="sm" disabled={!hasFilters} onclick={resetFilters}>{t('networksPage.filters.reset')}</Button>
		{#snippet actions()}
			<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={loading} onManualRefresh={() => refreshAll(true)} />
		{/snippet}
	</ResourceToolbar>
	<TableViewControls {view} />
	{#if error}
		<Alert tone="danger" title={t('networksPage.error.loadTitle')}>
			{error}
			{#snippet actions()}<Button variant="secondary" size="sm" onclick={() => refreshAll(true)}>{t('networksPage.retry')}</Button>{/snippet}
		</Alert>
	{/if}
	{#if ownerWarning}<Alert tone="warning" title={t('networksPage.ownerWarning')}>{t('networksPage.ownerWarningBody')}</Alert>{/if}
	{#if loading && !hasInventory}
		<LoadingState variant="surface" label={t('networksPage.loading')} />
	{:else}
	<AdminNetworkTable
		networks={visibleNetworks}
		{view}
		{ownerNames}
		{ownerDomains}
		emptyMessage={hasInventory ? (hasFilters ? t('networksPage.noMatches') : t('networksPage.empty')) : ''}
		onRowClick={(id) => goto(`/admin/networks/${id}`)}
		onEdit={(n) => { editNet = n; }}
		onDelete={(n) => { deleteNet = n; }}
	/>
	<div class="flex flex-wrap items-end justify-between gap-3">
		<Field label={t('list.pageSize')} for="admin-networks-page-size">
			<SelectInput id="admin-networks-page-size" bind:value={() => String(pageSize), (value) => pageSize = Number(value)}>{#each [20, 50, 100] as size}<option value={size}>{size}</option>{/each}</SelectInput>
		</Field>
		<Pagination class="!mt-0" page={displayPage} totalPages={pageCount} hasPrev={displayPage > 1} hasNext={displayPage < pageCount} onPrev={() => displayPage--} onNext={() => displayPage++} />
	</div>
	{/if}
	{#if !api.scoped}
		<details class="mt-4 rounded-lg border border-line bg-surface-base" bind:open={analyticsOpen}>
			<summary class="cursor-pointer px-4 py-3 text-sm font-medium text-ink-1">{t('list.analytics')}</summary>
			{#if analyticsOpen}<div class="px-4 pb-4"><AdminNetworkTimeseries data={tsData} loading={tsLoading} range={tsRange} onRangeChange={(r) => { tsRange = r; loadTimeseries(r); }} />{#if tsError}<Alert tone="warning" title={t('networksPage.timeseriesWarning')}>{tsError}</Alert>{/if}</div>{/if}
		</details>
	{:else}<p class="mt-4 text-[13px] text-ink-2">{t('list.scopedHistory')}</p>{/if}
</PageShell>

{#key currentScope}
	<AdminNetworkCreateModal bind:open={showCreate} onCreate={createNetwork} />
	<AdminNetworkEditModal network={editNet} onClose={() => { editNet = null; }} onSave={updateNetwork} />
	<AdminNetworkDeleteModal network={deleteNet} onClose={() => { deleteNet = null; }} onDelete={deleteNetwork} />
{/key}
