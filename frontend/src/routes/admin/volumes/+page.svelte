<script lang="ts">
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import { t as volumeT } from '$lib/i18n/ns/volume';
	import { t as scopeT } from '$lib/i18n/ns/domain-admin';
	let inventoryError = $state('');
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { onDestroy, onMount, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api as baseApi } from '$lib/api/client';
	import { createAdminInventoryApi } from '$lib/api/adminInventoryScope';
	import { adminInventoryScope } from '$lib/stores/adminInventoryScope';
	const api = createAdminInventoryApi(baseApi);
	onDestroy(api.dispose);
	import type { PagedResponse, TsPoint } from '$lib/types/common';
	import type { AdminVolume, AdminVolumeStatusSummary as VolumeStatusSummary } from '$lib/types/volume';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { projectNames } from '$lib/stores/projectNames';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import ResourceToolbar from '$lib/components/ui/ResourceToolbar.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createIntentPrefetchScheduler } from '$lib/utils/intentPrefetch';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { openWizard } from '$lib/stores/wizard';
	import AdminVolumeFilters from '$lib/components/admin/volumes/AdminVolumeFilters.svelte';
	import AdminVolumeTable from '$lib/components/admin/volumes/AdminVolumeTable.svelte';
	import AdminVolumeEditModal from '$lib/components/admin/volumes/AdminVolumeEditModal.svelte';
	import AdminVolumeDeleteModal from '$lib/components/admin/volumes/AdminVolumeDeleteModal.svelte';
	import AdminVolumeExtendModal from '$lib/components/admin/volumes/AdminVolumeExtendModal.svelte';
	import AdminVolumeResetStatusModal from '$lib/components/admin/volumes/AdminVolumeResetStatusModal.svelte';
	import AdminVolumeForceDeleteModal from '$lib/components/admin/volumes/AdminVolumeForceDeleteModal.svelte';
	import AdminVolumeTransferModal from '$lib/components/admin/volumes/AdminVolumeTransferModal.svelte';
	import AdminVolumeTimeseries from '$lib/components/admin/volumes/AdminVolumeTimeseries.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import AdminVolumePageSizeToggle from '$lib/components/admin/volumes/AdminVolumePageSizeToggle.svelte';
	import AdminVolumeDetailSlide from '$lib/components/admin/volumes/AdminVolumeDetailSlide.svelte';
	import AdminVolumeStatusSummary from '$lib/components/admin/volumes/AdminVolumeStatusSummary.svelte';
	import AdminVolumeDomainSummary from '$lib/components/admin/volumes/AdminVolumeDomainSummary.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import { t } from '$lib/i18n/ns/admin-storage';
	import type { ResourceSort } from '$lib/utils/resourceSort';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	let view = $state<'volumes' | 'capacity'>('volumes');
	$effect(() => { view = page.url.searchParams.get('tab') === 'capacity' ? 'capacity' : 'volumes'; });
	function changeView(next: string) {
		view = next === 'capacity' ? 'capacity' : 'volumes';
		const url = new URL(page.url);
		if (next === 'capacity') url.searchParams.set('tab', 'capacity');
		else url.searchParams.delete('tab');
		void goto(url, { noScroll: true, keepFocus: true });
	}

	let allVolumes = $state<AdminVolume[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let pageSize = $state(20);
	let markerStack = $state<string[]>([]);
	let nextMarker = $state<string | null>(null);
	let tsData = $state<TsPoint[]>([]);
	let tsRange = $state('7d');
	let tsLoading = $state(true);
	let tsError = $state('');
	let statusSummary = $state<VolumeStatusSummary | null>(null);
	let statusSummaryLoading = $state(true);

	let openActionMenu = $state<string | null>(null);
	let selectedVolumeId = $state<string | null>(null);

	let statusFilter = $state('');
	let nameSearch = $state('');
	let volumeType = $state('');
	let minSize = $state('');
	let maxSize = $state('');
	let sort = $state<ResourceSort>('created_desc');

	let editVolume = $state<AdminVolume | null>(null);
	let deleteVolume = $state<AdminVolume | null>(null);
	let extendVolume = $state<AdminVolume | null>(null);
	let resetVolume = $state<AdminVolume | null>(null);
	let forceDeleteVolume = $state<AdminVolume | null>(null);
	let transferVolume = $state<AdminVolume | null>(null);
	let receiveTransfer = $state(false);
	let loadGeneration = 0;
	let resultBoundary = 0;
	let statusSummaryGeneration = 0;
	let timeseriesGeneration = 0;
	let bulkDeleting = $state(false);
	let projectEffectReady = $state(false);
	let lastProjectId = $state<string | undefined>(undefined);
	const selection = createResourceSelection();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const selectableIds = $derived(new Set(allVolumes.map((volume) => volume.id)));
	const statusOptions = $derived(
		(statusSummary?.statuses ?? [])
			.filter((item) => item.count > 0)
			.map((item) => item.status),
	);
	const nextPrefetch = createIntentPrefetchScheduler();
	function filterParams(): URLSearchParams {
		const params = new URLSearchParams();
		if (statusFilter) params.set('status', statusFilter);
		if (nameSearch) params.set('name', nameSearch);
		if (volumeType) params.set('volume_type', volumeType);
		if (minSize !== '') params.set('min_size', minSize);
		if (maxSize !== '') params.set('max_size', maxSize);
		return params;
	}
	function summaryPath(): string {
		const query = filterParams().toString();
		return `/api/v1/admin/volumes/status-summary${query ? `?${query}` : ''}`;
	}
	function listPath(marker?: string): string {
		const params = new URLSearchParams({ limit: String(pageSize), sort });
		if (marker) params.set('marker', marker);
		for (const [key, value] of filterParams()) params.set(key, value);
		return `/api/v1/admin/all-volumes?${params}`;
	}
	function prefetchNext() {
		if (!nextMarker) return;
		const path = listPath(nextMarker);
		const key = JSON.stringify([path, token ?? null, projectId ?? null]);
		nextPrefetch.intent(key, (signal) => api.prefetch(path, token, projectId, { signal }));
	}


	async function loadTimeseries(range: string, opts?: { background?: boolean }) {
		const generation = ++timeseriesGeneration;
		const owns = () => api.isCurrent() && generation === timeseriesGeneration;
		if (!opts?.background) tsLoading = true;
		try {
			const result = await api.get<TsPoint[]>(`/api/v1/admin/timeseries/volumes?range=${range}`, token, projectId);
			if (owns()) tsData = result;
			if (owns()) tsError = '';
		} catch {
			if (owns()) tsError = t('volumeList.chartFailed');
		} finally {
			if (owns() && !opts?.background) tsLoading = false;
		}
	}

	async function loadStatusSummary(opts?: { background?: boolean; reloadOnReset?: boolean }): Promise<boolean> {
		const generation = ++statusSummaryGeneration;
		const requestProjectId = $auth.projectId ?? undefined;
		const requestToken = $auth.token ?? undefined;
		const requestPath = summaryPath();
		const owns = () => api.isCurrent() && generation === statusSummaryGeneration
			&& ($auth.token ?? undefined) === requestToken
			&& ($auth.projectId ?? undefined) === requestProjectId
			&& summaryPath() === requestPath;
		if (!opts?.background && statusSummary === null) statusSummaryLoading = true;
		try {
			const summary = await api.get<VolumeStatusSummary>(
				requestPath,
				requestToken,
				requestProjectId,
			);
			if (!owns()) return false;
			statusSummary = summary;
			const activeStatusDisappeared = statusFilter !== ''
				&& !summary.statuses.some((item) => item.status === statusFilter && item.count > 0);
			if (activeStatusDisappeared) {
				statusSummaryLoading = false;
				statusSummary = { ...summary, filtered_total: summary.total, filtered_gb: summary.total_gb };
				statusFilter = '';
				resetResultBoundary();
				if (opts?.reloadOnReset !== false) void load(undefined, { clearSelection: true });
				void loadStatusSummary({ background: true });
			}
			return activeStatusDisappeared;
		} catch {
			if (owns()) statusSummary = null;
			return false;
		} finally {
			if (owns()) statusSummaryLoading = false;
		}
	}

	function resetResultBoundary() {
		resultBoundary += 1;
		loadGeneration += 1;
		nextPrefetch.cancel();
		markerStack = [];
		nextMarker = null;
		selection.clear();
		selectedVolumeId = null;
		openActionMenu = null;
		editVolume = deleteVolume = extendVolume = resetVolume = forceDeleteVolume = null;
	}

	function applyStatusFilter(status: string) {
		statusFilter = status;
		if (view !== 'volumes') changeView('volumes');
		onFilterChange();
	}

	function onFilterChange() {
		invalidateSearch();
		void load(undefined, { clearSelection: true });
		void loadStatusSummary();
	}

	function drillIntoDomain(domainId: string) {
		const url = new URL(page.url);
		url.searchParams.set('domain_id', domainId);
		url.searchParams.delete('project_id');
		url.searchParams.delete('tab');
		if (api.filter.domainId === domainId && !api.filter.projectId) {
			statusFilter = ''; nameSearch = ''; volumeType = ''; minSize = ''; maxSize = '';
			onFilterChange();
		}
		view = 'volumes';
		void goto(url, { noScroll: true, keepFocus: true });
	}

	function invalidateSearch() {
		resetResultBoundary();
		statusSummaryGeneration += 1;
		statusSummary = null;
		statusSummaryLoading = true;
		allVolumes = [];
		loading = true;
	}

	let scopeRevision = api.filter.revision;
	const unsubscribeScope = adminInventoryScope.subscribe((scope) => {
		if (scope.revision === scopeRevision) return;
		scopeRevision = scope.revision;
		invalidateSearch();
	});
	onDestroy(unsubscribeScope);

	async function load(marker?: string, opts?: { clearSelection?: boolean; refresh?: boolean }) {
		const generation = ++loadGeneration;
		const requestToken = $auth.token ?? undefined;
		const requestProjectId = $auth.projectId ?? undefined;
		const requestPageSize = pageSize;
		const requestStatusFilter = statusFilter;
		const requestNameSearch = nameSearch;
		const requestPath = listPath(marker);
		const owns = () => api.isCurrent() && generation === loadGeneration
			&& ($auth.token ?? undefined) === requestToken
			&& ($auth.projectId ?? undefined) === requestProjectId
			&& pageSize === requestPageSize
			&& statusFilter === requestStatusFilter
			&& nameSearch === requestNameSearch
			&& listPath(marker) === requestPath;
		nextPrefetch.cancel();
		if (opts?.clearSelection) {
			resultBoundary += 1;
			selection.clear();
			allVolumes = [];
			selectedVolumeId = null;
			openActionMenu = null;
		}
		if (allVolumes.length === 0) loading = true;
		else refreshing = true;
		inventoryError = '';
		try {
			const res = await api.get<PagedResponse<AdminVolume>>(requestPath, requestToken, requestProjectId, opts?.refresh ? { refresh: true } : undefined);
			if (!owns()) return;
			allVolumes = res.items;
			nextMarker = res.next_marker;
			selection.retain(res.items.map((volume) => volume.id));
			const path = nextMarker ? listPath(nextMarker) : null;
			const key = path ? JSON.stringify([path, requestToken ?? null, requestProjectId ?? null]) : null;
			nextPrefetch.schedule(key, (signal) => path ? api.prefetch(path, requestToken, requestProjectId, { signal }) : undefined);
		} catch (reason) {
			if (owns()) {
				allVolumes = [];
				inventoryError = reason instanceof Error ? reason.message : scopeT('state.unavailable');
				selection.clear();
			}
		} finally {
			if (owns()) {
				loading = false;
				refreshing = false;
			}
		}
	}

	async function bulkDeleteSelectedVolumes() {
		if (bulkDeleting || loading) return;
		const ids = [...selection.ids];
		if (ids.length === 0) return;
		const boundary = resultBoundary;
		const requestProjectId = $auth.projectId ?? undefined;
		const requestUserId = $auth.userId;
		bulkDeleting = true;
		try {
			if (!await confirmDialog(t('volumeList.bulkDelete.confirm', { count: ids.length }))) return;
			if (!api.isCurrent() || boundary !== resultBoundary || requestProjectId !== ($auth.projectId ?? undefined)
				|| requestUserId !== $auth.userId || ids.some(id => !selection.ids.has(id))) return;
			const requestToken = $auth.token ?? undefined;
			const response = await api.post<{ results: { id: string; ok: boolean; error: string | null }[] }>(
				'/api/v1/admin/volumes/bulk-delete',
				{ volume_ids: ids },
				requestToken,
				requestProjectId,
			);
			if (!api.isCurrent() || boundary !== resultBoundary || requestUserId !== $auth.userId
				|| requestProjectId !== ($auth.projectId ?? undefined)) return;
			const successfulIds = response.results.filter((result) => result.ok).map((result) => result.id);
			const failed = response.results.length - successfulIds.length;
			if (successfulIds.length > 0) toast.success(t('volumeList.bulkDelete.success', { count: successfulIds.length }));
			if (failed > 0) toast.error(t('volumeList.bulkDelete.partialFailure', { count: failed }));
			if (($auth.projectId ?? undefined) !== requestProjectId) return;
			selection.remove(successfulIds);
			const statusReset = await loadStatusSummary({ background: true, reloadOnReset: false });
			await Promise.all([
				load(statusReset ? undefined : markerStack[markerStack.length - 1]),
				loadTimeseries(tsRange, { background: true }),
			]);
		} catch {
			if (!api.isCurrent() || boundary !== resultBoundary || requestUserId !== $auth.userId
				|| requestProjectId !== ($auth.projectId ?? undefined)) return;
			toast.error(t('volumeList.bulkDelete.failed'));
		} finally {
			bulkDeleting = false;
		}
	}

	const bulkActions = $derived<BulkSelectionAction[]>([
		{ key: 'delete', label: t('volumeList.action.delete'), tone: 'danger', onAction: bulkDeleteSelectedVolumes },
	]);

	function refreshCurrentVolumeState() {
		void load(markerStack[markerStack.length - 1]);
		void loadStatusSummary();
		void loadTimeseries(tsRange, { background: true });
	}

	const ar = createAutoRefresh(
		async () => { await Promise.allSettled([load(markerStack[markerStack.length - 1]), loadTimeseries(tsRange, { background: true }), loadStatusSummary({ background: true })]); },
		{ storageKey: 'admin-volumes', defaultActive: true, defaultInterval: 30, intervalOptions: [15, 30, 60], invokeOnMount: false },
	);

	$effect(() => {
		const currentProjectId = $auth.projectId ?? undefined;
		if (!projectEffectReady) return;
		if (currentProjectId === lastProjectId) return;
		lastProjectId = currentProjectId;
		untrack(() => {
			resetResultBoundary();
			statusSummary = null;
			void load(undefined, { clearSelection: true });
			void loadTimeseries(tsRange);
			void loadStatusSummary();
			projectNames.load($auth.token ?? undefined, currentProjectId);
		});
	});

	onMount(() => {
		if (window.matchMedia('(max-width: 767px)').matches) pageSize = 10;
		lastProjectId = $auth.projectId ?? undefined;
		projectEffectReady = true;
		void load(undefined, { clearSelection: true });
		void loadTimeseries(tsRange);
		void loadStatusSummary();
		projectNames.load(token, projectId);
	});

	onDestroy(() => { resultBoundary += 1; loadGeneration += 1; statusSummaryGeneration += 1; timeseriesGeneration += 1; nextPrefetch.cancel(); });
</script>

<PageShell class="bulk-selection-page">
	<div data-tour="admin-storage-header">
	<PageHeader breadcrumb={t('volumeList.breadcrumb')} title={statusSummaryLoading || !statusSummary ? t('volumeList.title') : t('volumeList.titleWithCount', { title: t('volumeList.title'), count: statusSummary.total })}>
		{#snippet actions()}
			<Button variant="outline" onclick={() => { receiveTransfer = true; }}>{volumeT('transferModal.receiveTitle')}</Button>
		{/snippet}
	</PageHeader>
	</div>


	<div data-tour="admin-storage-status">
	<AdminVolumeStatusSummary
		summary={statusSummary}
		activeStatus={statusFilter}
		loading={statusSummaryLoading}
		onSelect={applyStatusFilter}
	/>
	</div>

	<Tabs id="admin-volume-tabs" value={view} items={[{ value: 'volumes', label: t('volumeList.resourceTab'), panelId: 'admin-volume-list-panel' }, { value: 'capacity', label: t('volumeList.capacityTab'), panelId: 'admin-volume-capacity-panel' }]} onchange={changeView} ariaLabel={t('volumeList.views')} />
	<div data-tour="admin-storage-filters">
	{#snippet volumeFilters()}
		<AdminVolumeFilters
			bind:statusFilter
			bind:nameSearch
			bind:volumeType
			bind:minSize
			bind:maxSize
			bind:sort
			statusOptions={statusOptions}
			onChange={onFilterChange}
			onInvalidate={invalidateSearch}
		/>
	{/snippet}
	<ResourceToolbar label={volumeT('page.toolbar')} class="mb-4" filters={volumeFilters} controlsHidden={view !== 'volumes'}>
	{#snippet actions()}
		<TutorialStartButton tour="admin-storage" compactOnMobile />
		<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={loading || refreshing} onManualRefresh={() => { void load(markerStack[markerStack.length - 1], { refresh: true }); void loadStatusSummary(); void loadTimeseries(tsRange); }} />
	{/snippet}
	</ResourceToolbar>
	</div>
	<div id="admin-volume-list-panel" role="tabpanel" aria-labelledby="admin-volume-tabs-volumes" tabindex="0" hidden={view !== 'volumes'}>

	<div data-tour="admin-storage-list">
	{#if inventoryError}<Alert tone="danger">{inventoryError}</Alert>
	{:else if loading}
		<LoadingState variant="surface" />
	{:else}
		<div data-tour="admin-storage-ready">
		{#if allVolumes.length === 0}<p class="py-6 text-sm text-ink-2" role="status">{t('volumeList.empty')}</p>{/if}
			<AdminVolumeTable
				volumes={allVolumes}
				{selectedVolumeId}
				{openActionMenu}
				selectedIds={selection.ids}
				{selectableIds}
				selectionDisabled={bulkDeleting}
				onSelect={(id) => (selectedVolumeId = id)}
				onToggleSelect={(id) => selection.toggle(id)}
				onToggleAll={() => selection.toggleAll(selectableIds)}
				onActionMenuOpen={(id) => (openActionMenu = id)}
				onActionMenuClose={() => (openActionMenu = null)}
				onEdit={(v) => (editVolume = v)}
				onExtend={(v) => (extendVolume = v)}
				onTransfer={(v) => (transferVolume = v)}
				onReset={(v) => (resetVolume = v)}
				onForceDelete={(v) => (forceDeleteVolume = v)}
				onDelete={(v) => (deleteVolume = v)}
				onBootFromVolume={(v) =>
					openWizard({
						targetProjectId: v.project_id ?? undefined,
						prefill: { bootSource: 'volume', bootVolumeId: v.id, bootVolumeName: v.name },
					})}
			/>
		</div>
	{/if}
	</div>
		<footer class="flex flex-wrap items-end justify-between gap-3" data-testid="admin-volume-footer">
			<AdminVolumePageSizeToggle value={pageSize} onChange={(n) => { pageSize = n; resetResultBoundary(); void load(undefined, { clearSelection: true }); }} />
			<p class="text-sm tabular-nums text-ink-2" role="status" data-testid="admin-volume-filtered-total">{t('volumeList.summary.filtered')}: {statusSummaryLoading || !statusSummary ? '—' : t('volumeList.summary.capacity', { count: statusSummary.filtered_total, size: statusSummary.filtered_gb })} · {loading || inventoryError ? '—' : t('volumeList.pageCount', { count: allVolumes.length })}</p>
		<Pagination
			class="!mt-0"
			page={markerStack.length + 1}
			hasPrev={!loading && !inventoryError && markerStack.length > 0}
			hasNext={!loading && !inventoryError && !!nextMarker}
			onPrev={() => {
				const prev = markerStack.slice(0, -1);
				const marker = prev[prev.length - 1];
				markerStack = prev;
				selection.clear();
				void load(marker, { clearSelection: true });
			}}
			onNext={() => {
				if (!nextMarker) return;
				markerStack = [...markerStack, nextMarker];
				selection.clear();
				void load(nextMarker, { clearSelection: true });
			}}
			onintent={prefetchNext}
		/>
		</footer>

	<BulkSelectionOverlay
		count={selection.count}
		ariaLabel={t('volumeList.bulkActions')}
		actions={bulkActions}
		busy={bulkDeleting}
		onClear={() => selection.clear()}
	/>
	</div>
	{#if view === 'capacity'}
	<div id="admin-volume-capacity-panel" role="tabpanel" aria-labelledby="admin-volume-tabs-capacity" tabindex="0" class="space-y-4">
		{#if !statusSummaryLoading && !statusSummary}<Button variant="outline" onclick={() => { void loadStatusSummary(); }}>{volumeT('page.retry')}</Button>{/if}
		<AdminVolumeDomainSummary summary={statusSummary} loading={statusSummaryLoading} scoped={api.scoped} onDomain={drillIntoDomain} />
		{#if !api.scoped}
			<details class="rounded-lg border border-line bg-surface-base" data-tour="admin-storage-timeseries">
				<summary class="cursor-pointer px-4 py-3 text-sm font-medium text-ink-0">{t('volumeList.chartTitle')}</summary>
				<div class="px-4 pb-4"><AdminVolumeTimeseries data={tsData} loading={tsLoading} error={tsError} range={tsRange} onRetry={() => { void loadTimeseries(tsRange); }} onRangeChange={(r) => { tsRange = r; void loadTimeseries(r); }} /></div>
			</details>
		{/if}
	</div>
	{/if}
</PageShell>

{#if selectedVolumeId}
	<AdminVolumeDetailSlide
		volumeId={selectedVolumeId}
		{token}
		{projectId}
		onClose={() => { selectedVolumeId = null; }}
		onRefresh={() => load(markerStack[markerStack.length - 1])}
	/>
{/if}

<AdminVolumeEditModal volume={editVolume} onClose={() => (editVolume = null)} onSuccess={refreshCurrentVolumeState} />
<AdminVolumeDeleteModal volume={deleteVolume} onClose={() => (deleteVolume = null)} onSuccess={refreshCurrentVolumeState} />
<AdminVolumeExtendModal volume={extendVolume} onClose={() => (extendVolume = null)} onSuccess={refreshCurrentVolumeState} />
<AdminVolumeResetStatusModal volume={resetVolume} onClose={() => (resetVolume = null)} onSuccess={refreshCurrentVolumeState} />
<AdminVolumeForceDeleteModal volume={forceDeleteVolume} onClose={() => (forceDeleteVolume = null)} onSuccess={refreshCurrentVolumeState} />
{#if transferVolume || receiveTransfer}
	{#key transferVolume?.id ?? 'receive'}
		<AdminVolumeTransferModal volume={transferVolume} initialMode={receiveTransfer ? 'receive' : 'create'} onClose={() => { transferVolume = null; receiveTransfer = false; }} onSuccess={refreshCurrentVolumeState} />
	{/key}
{/if}
