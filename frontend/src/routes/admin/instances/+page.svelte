<script lang="ts">
	import Alert from '$lib/components/ui/Alert.svelte';
	import { t as scopeT } from '$lib/i18n/ns/domain-admin';
	let inventoryError = $state('');
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t } from '$lib/i18n/ns/admin-compute';
	import { t as instanceT } from '$lib/i18n/ns/instance';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api as baseApi } from '$lib/api/client';
	import { createAdminInventoryApi } from '$lib/api/adminInventoryScope';
	const api = createAdminInventoryApi(baseApi);
	onDestroy(api.dispose);
	import TimeSeriesChart from '$lib/components/TimeSeriesChart.svelte';
	import InstanceDetailPanel from '$lib/components/InstanceDetailPanel.svelte';
	import { invalidateInstanceDetailSelection } from '$lib/stores/instanceDetailController.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createIntentPrefetchScheduler } from '$lib/utils/intentPrefetch';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { openWizard } from '$lib/stores/wizard';
	import AdminInstanceFilters from '$lib/components/admin/instances/AdminInstanceFilters.svelte';
	import AdminInstanceTable from '$lib/components/admin/instances/AdminInstanceTable.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import { toast } from '$lib/stores/toast';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { isTransitional } from '$lib/utils/instanceStatus';
	import RecoveryModal from '$lib/components/admin/instances/RecoveryModal.svelte';
	import type { AdminInstance, PagedResponse, TsPoint } from '$lib/types/adminInstance';
	import { Button, EmptyState, Pagination, SelectInput } from '$lib/components/ui';
	import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import type { ResourceSort } from '$lib/utils/resourceSort';

	let allInstances = $state<AdminInstance[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let pageSize = $state(20);
	let pageSizeInput = $state('20');
	$effect(() => { pageSizeInput = String(pageSize); });
	let markerStack = $state<string[]>([]);
	let nextMarker = $state<string | null>(null);
	let availableHosts = $state<string[]>([]);
	let hostFilter = $state('');
	let statusFilter = $state('');
	let nameSearch = $state('');
	let sort = $state<ResourceSort>('created_desc');
	let tsData = $state<TsPoint[]>([]);
	let tsRange = $state('7d');
	let tsLoading = $state(true);
	let selectedInstanceId = $state<string | null>(null);
	let selectedProjectId = $state<string | null>(null);

	interface InstanceHealth {
		total: number;
		active: number;
		error: number;
		with_alerts: number;
		gpu_count: number;
	}
	let health = $state<InstanceHealth | null>(null);

	const token = $derived($auth.token ?? undefined);
	const selection = createResourceSelection();
	let bulkActioning = $state(false);
	let recoveryInst = $state<AdminInstance | null>(null);
	let projectEffectReady = $state(false);
	let lastProjectId = $state<string | undefined>(undefined);
	let loadGeneration = 0;
	let scopeRevision = $state(0);
	let instancesRevision = $state(-1);
	let instancesPath = $state('');
	const unsubscribeAuth = auth.subscribe(() => { scopeRevision += 1; });

	function targetsStopped(ids: readonly string[]) {
		if (!$auth.token || !$auth.isSystemAdmin || instancesRevision !== scopeRevision || ids.length === 0
			|| instancesPath !== listPath(markerStack[markerStack.length - 1])) return false;
		return ids.every((id) => {
			const row = allInstances.find((instance) => instance.id === id);
			return row?.status === 'SHUTOFF';
		});
	}
	const canBulkDelete = $derived(targetsStopped([...selection.ids]));

	const selectableIds = $derived(new Set(allInstances.map((instance) => instance.id)));
	const projectId = $derived($auth.projectId ?? undefined);
	const nextPrefetch = createIntentPrefetchScheduler();
	function listPath(marker?: string): string {
		const params = new URLSearchParams({ limit: String(pageSize), sort });
		if (marker) params.set('marker', marker);
		if (hostFilter) params.set('host', hostFilter);
		if (statusFilter) params.set('status', statusFilter);
		if (nameSearch) params.set('name', nameSearch);
		return `/api/v1/admin/all-instances?${params}`;
	}
	function prefetchNext() {
		if (!nextMarker) return;
		const path = listPath(nextMarker);
		const key = JSON.stringify([path, token ?? null, projectId ?? null]);
		nextPrefetch.intent(key, (signal) => api.prefetch(path, token, projectId, { signal }));
	}

	async function load(marker?: string, opts?: { clearSelection?: boolean; refresh?: boolean }) {
		const generation = ++loadGeneration;
		const requestToken = $auth.token ?? undefined;
		const requestProjectId = $auth.projectId ?? undefined;
		const requestPageSize = pageSize;
		const requestHostFilter = hostFilter;
		const requestStatusFilter = statusFilter;
		const requestNameSearch = nameSearch;
		const requestPath = listPath(marker);
		if (opts?.clearSelection) scopeRevision += 1;
		const requestRevision = scopeRevision;
		const owns = () => generation === loadGeneration
			&& api.isCurrent() && requestRevision === scopeRevision
			&& ($auth.token ?? undefined) === requestToken
			&& ($auth.projectId ?? undefined) === requestProjectId
			&& pageSize === requestPageSize
			&& hostFilter === requestHostFilter
			&& statusFilter === requestStatusFilter
			&& nameSearch === requestNameSearch
			&& listPath(marker) === requestPath;
		nextPrefetch.cancel();
		if (opts?.clearSelection) {
			selection.clear();
			allInstances = [];
			closeDetail();
			closeRecovery();
		}
		allInstances.length === 0 ? (loading = true) : (refreshing = true);
		inventoryError = '';
		try {
			const res = await api.get<PagedResponse<AdminInstance>>(requestPath, requestToken, requestProjectId, opts?.refresh ? { refresh: true } : undefined);
			if (!owns()) return;
			allInstances = res.items;
			instancesRevision = requestRevision;
			instancesPath = requestPath;
			nextMarker = res.next_marker;
			selection.retain(res.items.map((instance) => instance.id));
			const path = nextMarker ? listPath(nextMarker) : null;
			const key = path ? JSON.stringify([path, requestToken ?? null, requestProjectId ?? null]) : null;
			nextPrefetch.schedule(key, (signal) => path ? api.prefetch(path, requestToken, requestProjectId, { signal }) : undefined);
		} catch (reason) {
			if (owns()) { allInstances = []; inventoryError = reason instanceof Error ? reason.message : scopeT('state.unavailable'); }
		} finally {
			if (owns()) {
				loading = false;
				refreshing = false;
			}
		}
	}

	async function loadHosts() {
		try {
			const hvs = await api.get<{ id: string; name: string }[]>('/api/v1/admin/hypervisors', token, projectId);
			availableHosts = hvs.map(h => h.name).sort();
		} catch { availableHosts = []; }
	}

	async function loadTimeseries(range: string, opts?: { background?: boolean }) {
		if (!opts?.background) tsLoading = true;
		try { tsData = await api.get<TsPoint[]>(`/api/v1/admin/timeseries/instances?range=${range}`, token, projectId); }
		catch { if (!opts?.background) tsData = []; }
		finally { if (!opts?.background) tsLoading = false; }
	}

	async function loadHealth() {
		try {
			health = await api.get<InstanceHealth>('/api/v1/admin/instances/health', token, projectId);
		} catch { health = null; }
	}

	function openDetail(inst: AdminInstance) { invalidateInstanceDetailSelection(); selectedInstanceId = inst.id; selectedProjectId = inst.project_id; }
	function closeDetail() { invalidateInstanceDetailSelection(); selectedInstanceId = null; selectedProjectId = null; }
	function openRecovery(inst: AdminInstance) { recoveryInst = inst; }
	function closeRecovery() { recoveryInst = null; }
	function onFilterChange() {
		markerStack = [];
		nextMarker = null;
		void load(undefined, { clearSelection: true });
	}
	function onPrev() {
		const prev = markerStack.slice(0, -1);
		markerStack = prev;
		void load(prev[prev.length - 1], { clearSelection: true });
	}
	function onNext() {
		if (!nextMarker) return;
		markerStack = [...markerStack, nextMarker];
		void load(nextMarker, { clearSelection: true });
	}

	const ar = createAutoRefresh(
		async () => { await Promise.allSettled([load(markerStack[markerStack.length - 1]), loadTimeseries(tsRange, { background: true })]); },
		{ storageKey: 'admin-instances', defaultActive: true, defaultInterval: 15, intervalOptions: [10, 15, 30, 60], invokeOnMount: false }
	);

	$effect(() => {
		const hasTransitional = allInstances.some(i => isTransitional(i.status));
		ar.setBoost(hasTransitional ? 4 : null);
	});
	$effect(() => {
		const currentProjectId = $auth.projectId ?? undefined;
		if (!projectEffectReady) return;
		if (currentProjectId === lastProjectId) return;
		lastProjectId = currentProjectId;
		markerStack = [];
		nextMarker = null;
		selection.clear();
		void load();
		void loadTimeseries(tsRange);
		void loadHosts();
		void loadHealth();
	});

	async function bulkAction(action: 'start' | 'stop' | 'delete') {
		const ids = [...selection.ids];
		const requestToken = $auth.token ?? undefined;
		const requestProjectId = $auth.projectId ?? undefined;
		const revision = scopeRevision;
		const selectedIds = selection.ids;
		const targetProjects = ids.map((id) => allInstances.find((row) => row.id === id)?.project_id);
		const targetStates = ids.map((id) => allInstances.find((row) => row.id === id)?.status);
		const owns = () => revision === scopeRevision && !!$auth.token && $auth.isSystemAdmin
			&& instancesRevision === scopeRevision && ids.length > 0
			&& instancesPath === listPath(markerStack[markerStack.length - 1])
			&& selection.ids === selectedIds && selection.ids.size === ids.length && ids.every((id) => selection.ids.has(id))
			&& ids.every((id, index) => {
				const row = allInstances.find((instance) => instance.id === id);
				return !!row && row.project_id === targetProjects[index] && row.status === targetStates[index]
					&& (action !== 'delete' || row.status === 'SHUTOFF');
			});
		if (bulkActioning || !owns()) return;
		if (
			(action === 'stop' || action === 'delete')
			&& !await confirmDialog(
				action === 'delete'
					? `${t('instances.bulk.deleteConfirm', { count: ids.length })}\n\n${instanceT('panel.stoppedQuotaWarning')}`
					: `${t('instances.bulk.stopConfirm', { count: ids.length })}\n\n${instanceT('panel.stoppedQuotaWarning')}`,
			)
		) return;
		if (!owns()) return;

		bulkActioning = true;
		try {
			const res = await api.post<{ results: { id: string; ok: boolean }[] }>(
				'/api/v1/instances/bulk-action',
				{ action, instance_ids: ids },
				requestToken,
				requestProjectId,
			);
			const successfulIds = res.results.filter((result) => result.ok).map((result) => result.id);
			const failed = ids.length - successfulIds.length;
			if (successfulIds.length > 0) toast.success(t('instances.bulk.success', { count: successfulIds.length, action }));
			if (failed > 0) toast.error(t('instances.bulk.failedCount', { count: failed }));
			if (($auth.projectId ?? undefined) === requestProjectId) {
				selection.remove(successfulIds);
				ar.setBoost(4);
				void load(markerStack[markerStack.length - 1]);
			}
		} catch {
			if (!api.isCurrent()) return;
			toast.error(t('instances.bulk.failed', { action }));
		} finally {
			bulkActioning = false;
		}
	}

	onMount(() => {
		if (window.matchMedia('(max-width: 767px)').matches) pageSize = 10;
		lastProjectId = $auth.projectId ?? undefined;
		projectEffectReady = true;
		void load(undefined, { clearSelection: true });
		void loadTimeseries(tsRange);
		void loadHosts();
		void loadHealth();
	});
	onDestroy(() => { unsubscribeAuth(); scopeRevision += 1; loadGeneration += 1; nextPrefetch.cancel(); invalidateInstanceDetailSelection(); });
</script>

<PageShell class="bulk-selection-page space-y-4">
	<div data-tour="admin-compute-header">
	<PageHeader breadcrumb={t('instances.page.breadcrumb')} title={health ? t('instances.page.titleWithCount', { count: health.total }) : t('instances.page.title')}>
		{#snippet actions()}
			<Button onclick={() => openWizard()} variant="primary" size="sm">
				<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
				</svg>
				{t('instances.page.createVm')}
			</Button>
		{/snippet}
	</PageHeader>
	</div>

	{#if health}
		<p class="text-sm tabular-nums text-ink-2" data-testid="admin-instance-summary">{t('instances.page.summary', { total: health.total, active: health.active, errors: health.error, alerts: health.with_alerts, gpu: health.gpu_count })}</p>
	{/if}

	<div data-tour="admin-compute-filters">
	<AdminInstanceFilters
		{availableHosts}
		bind:hostFilter
		bind:statusFilter
		bind:nameSearch
		bind:sort
		onChange={onFilterChange}
	>
		{#snippet actions()}
			<TutorialStartButton tour="admin-compute" compactOnMobile />
			<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={loading || refreshing} onManualRefresh={() => { void load(markerStack.at(-1), { refresh: true }); void loadHealth(); void loadHosts(); }} />
		{/snippet}
	</AdminInstanceFilters>
	</div>

	{#if !api.scoped}
	<details class="rounded-lg border border-line bg-surface-base" data-tour="admin-compute-timeseries">
		<summary class="min-h-11 cursor-pointer px-4 py-3 text-sm font-medium text-ink-1">{t('instances.page.showUsageTrend')}</summary>
		<div class="px-4 pb-4">
		{#if tsLoading}
			<LoadingState variant="section" label={t('instances.page.chartLoading')} />
		{:else}
			<TimeSeriesChart
				data={tsData}
				title={t('instances.page.chartTitle')}
				mainKey="total"
				extraKeys={['active', 'shutoff', 'error', 'shelved']}
				currentRange={tsRange}
				onRangeChange={(r) => { tsRange = r; loadTimeseries(r); }}
			/>
		{/if}
		</div>
	</details>
	{/if}


	<div data-tour="admin-compute-list">
	{#if inventoryError}<Alert tone="danger">{inventoryError}</Alert>
	{:else if loading}
		<LoadingState variant="surface" />
	{:else}
		{#if allInstances.length === 0}
			<EmptyState headline={t(hostFilter || statusFilter || nameSearch ? 'instances.page.filteredEmpty' : 'instances.page.empty')} description={t(hostFilter || statusFilter || nameSearch ? 'instances.page.filteredEmptyDescription' : 'instances.page.emptyDescription')}>
				{#snippet cta()}{#if hostFilter || statusFilter || nameSearch}<Button variant="secondary" onclick={() => { hostFilter = ''; statusFilter = ''; nameSearch = ''; onFilterChange(); }}>{t('instances.page.clearFilters')}</Button>{/if}{/snippet}
			</EmptyState>
		{/if}
		<div data-tour="admin-compute-ready">
		<AdminInstanceTable
			instances={allInstances}
			selectedIds={selection.ids}
			{selectableIds}
			selectionDisabled={bulkActioning}
			onOpen={openDetail}
			onRecover={openRecovery}
			onToggleSelect={(id) => selection.toggle(id)}
			onToggleAll={() => selection.toggleAll(selectableIds)}
		/>
		</div>
	{/if}
	</div>
	<footer class="flex flex-wrap items-end justify-between gap-3 pt-3" data-testid="admin-instance-list-footer">
		{#if !loading && !inventoryError}<p class="text-sm tabular-nums text-ink-2">{t('instances.page.loadedCount', { count: allInstances.length })}</p>{/if}
		<div class="flex items-center gap-2"><label for="admin-instance-page-size" class="text-xs text-ink-2">{t('instances.page.pageSize')}</label><SelectInput id="admin-instance-page-size" bind:value={pageSizeInput} onchange={(event) => { pageSizeInput = (event.currentTarget as HTMLSelectElement).value; pageSize = Number(pageSizeInput); onFilterChange(); }}>{#each [10, 20, 30] as size}<option value={String(size)}>{size}</option>{/each}</SelectInput></div>
		<Pagination class="!mt-0" page={markerStack.length + 1} hasPrev={!loading && markerStack.length > 0} hasNext={!loading && !inventoryError && !!nextMarker} {onPrev} {onNext} onintent={prefetchNext} />
	</footer>

	<BulkSelectionOverlay
		count={selection.count}
		ariaLabel={t('instances.bulk.label')}
		actions={[
			{ key: 'start', label: t('instances.bulk.start'), tone: 'success', onAction: () => bulkAction('start') },
			{ key: 'stop', label: t('instances.bulk.stop'), tone: 'warning', onAction: () => bulkAction('stop') },
			...(canBulkDelete ? [{ key: 'delete', label: t('instances.bulk.delete'), tone: 'danger' as const, onAction: () => bulkAction('delete') }] : []),
		]}
		busy={bulkActioning}
		onClear={() => selection.clear()}
	/>
</PageShell>

{#if selectedInstanceId}
	<SlidePanel onClose={closeDetail} ariaLabel={t('instances.page.detailLabel')} dataTour="admin-compute-detail">
		<InstanceDetailPanel instanceId={selectedInstanceId} adminMode={true} adminProjectId={selectedProjectId} onClose={closeDetail} showHost={true} onUpdated={() => void load(markerStack.at(-1))} />
	</SlidePanel>
{/if}

{#if recoveryInst}
	<RecoveryModal
		serverId={recoveryInst.id}
		serverName={recoveryInst.name || recoveryInst.id.slice(0, 8)}
		onClose={closeRecovery}
		onRecovered={() => { closeRecovery(); markerStack = []; nextMarker = null; void load(undefined, { clearSelection: true }); }}
	/>
{/if}
