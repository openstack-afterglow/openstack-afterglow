<script lang="ts">
	import { onDestroy, onMount, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import type { PagedResponse, TsPoint } from '$lib/types/common';
	import type { AdminVolume, AdminVolumeStatusSummary as VolumeStatusSummary } from '$lib/types/volume';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { projectNames } from '$lib/stores/projectNames';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
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
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';

	let allVolumes = $state<AdminVolume[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let pageSize = $state(20);
	let markerStack = $state<string[]>([]);
	let nextMarker = $state<string | null>(null);
	let tsData = $state<TsPoint[]>([]);
	let tsRange = $state('7d');
	let tsLoading = $state(true);
	let statusSummary = $state<VolumeStatusSummary | null>(null);
	let statusSummaryLoading = $state(true);

	let copiedProjectId = $state<string | null>(null);
	let openActionMenu = $state<string | null>(null);
	let selectedVolumeId = $state<string | null>(null);

	let projectFilter = $state('');
	let projectSearchText = $state('');
	let statusFilter = $state('');
	let nameSearch = $state('');

	let editVolume = $state<AdminVolume | null>(null);
	let deleteVolume = $state<AdminVolume | null>(null);
	let extendVolume = $state<AdminVolume | null>(null);
	let resetVolume = $state<AdminVolume | null>(null);
	let forceDeleteVolume = $state<AdminVolume | null>(null);
	let transferVolume = $state<AdminVolume | null>(null);
	let loadGeneration = 0;
	let resultBoundary = 0;
	let statusSummaryGeneration = 0;
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
	function listPath(marker?: string): string {
		const params = new URLSearchParams({ limit: String(pageSize) });
		if (marker) params.set('marker', marker);
		if (projectFilter) params.set('project_id', projectFilter);
		if (statusFilter) params.set('status', statusFilter);
		if (nameSearch) params.set('name', nameSearch);
		return `/api/v1/admin/all-volumes?${params}`;
	}
	function prefetchNext() {
		if (!nextMarker) return;
		const path = listPath(nextMarker);
		const key = JSON.stringify([path, token ?? null, projectId ?? null]);
		nextPrefetch.intent(key, (signal) => api.prefetch(path, token, projectId, { signal }));
	}

	function copyProjectId(id: string) {
		navigator.clipboard.writeText(id).then(() => {
			copiedProjectId = id;
			setTimeout(() => { copiedProjectId = null; }, 1500);
		});
	}

	async function loadTimeseries(range: string, opts?: { background?: boolean }) {
		if (!opts?.background) tsLoading = true;
		try {
			tsData = await api.get<TsPoint[]>(`/api/v1/admin/timeseries/volumes?range=${range}`, token, projectId);
		} catch {
			if (!opts?.background) tsData = [];
		} finally {
			if (!opts?.background) tsLoading = false;
		}
	}

	async function loadStatusSummary(opts?: { background?: boolean; reloadOnReset?: boolean }): Promise<boolean> {
		const generation = ++statusSummaryGeneration;
		const requestProjectId = $auth.projectId ?? undefined;
		const requestToken = $auth.token ?? undefined;
		const owns = () => generation === statusSummaryGeneration
			&& ($auth.projectId ?? undefined) === requestProjectId;
		if (!opts?.background && statusSummary === null) statusSummaryLoading = true;
		try {
			const summary = await api.get<VolumeStatusSummary>(
				'/api/v1/admin/volumes/status-summary',
				requestToken,
				requestProjectId,
			);
			if (!owns()) return false;
			statusSummary = summary;
			const activeStatusDisappeared = statusFilter !== ''
				&& !summary.statuses.some((item) => item.status === statusFilter && item.count > 0);
			if (activeStatusDisappeared) {
				statusFilter = '';
				markerStack = [];
				nextMarker = null;
				selection.clear();
				if (opts?.reloadOnReset !== false) void load(undefined, { clearSelection: true });
			}
			return activeStatusDisappeared;
		} catch {
			if (owns() && !opts?.background) statusSummary = null;
			return false;
		} finally {
			if (owns()) statusSummaryLoading = false;
		}
	}

	function resetResultBoundary() {
		markerStack = [];
		nextMarker = null;
		selection.clear();
	}

	function applyStatusFilter(status: string) {
		statusFilter = status;
		resetResultBoundary();
		void load(undefined, { clearSelection: true });
	}

	function onFilterChange() {
		resetResultBoundary();
		void load(undefined, { clearSelection: true });
	}

	async function load(marker?: string, opts?: { clearSelection?: boolean }) {
		const generation = ++loadGeneration;
		const requestToken = $auth.token ?? undefined;
		const requestProjectId = $auth.projectId ?? undefined;
		const requestPageSize = pageSize;
		const requestProjectFilter = projectFilter;
		const requestStatusFilter = statusFilter;
		const requestNameSearch = nameSearch;
		const requestPath = listPath(marker);
		const owns = () => generation === loadGeneration
			&& ($auth.token ?? undefined) === requestToken
			&& ($auth.projectId ?? undefined) === requestProjectId
			&& pageSize === requestPageSize
			&& projectFilter === requestProjectFilter
			&& statusFilter === requestStatusFilter
			&& nameSearch === requestNameSearch
			&& listPath(marker) === requestPath;
		nextPrefetch.cancel();
		if (opts?.clearSelection) {
			resultBoundary += 1;
			selection.clear();
			allVolumes = [];
		}
		if (allVolumes.length === 0) loading = true;
		else refreshing = true;
		try {
			const res = await api.get<PagedResponse<AdminVolume>>(requestPath, requestToken, requestProjectId);
			if (!owns()) return;
			allVolumes = res.items;
			nextMarker = res.next_marker;
			selection.retain(res.items.map((volume) => volume.id));
			const path = nextMarker ? listPath(nextMarker) : null;
			const key = path ? JSON.stringify([path, requestToken ?? null, requestProjectId ?? null]) : null;
			nextPrefetch.schedule(key, (signal) => path ? api.prefetch(path, requestToken, requestProjectId, { signal }) : undefined);
		} catch {
			if (owns()) {
				allVolumes = [];
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
			if (!await confirmDialog(`선택한 볼륨 ${ids.length}개를 삭제하시겠습니까?\n삭제된 데이터는 복구할 수 없습니다.`)) return;
			if (boundary !== resultBoundary || requestProjectId !== ($auth.projectId ?? undefined)
				|| requestUserId !== $auth.userId || ids.some(id => !selection.ids.has(id))) return;
			const requestToken = $auth.token ?? undefined;
			const response = await api.post<{ results: { id: string; ok: boolean; error: string | null }[] }>(
				'/api/v1/admin/volumes/bulk-delete',
				{ volume_ids: ids },
				requestToken,
				requestProjectId,
			);
			const successfulIds = response.results.filter((result) => result.ok).map((result) => result.id);
			const failed = response.results.length - successfulIds.length;
			if (successfulIds.length > 0) toast.success(`${successfulIds.length}개 볼륨 삭제 요청을 완료했습니다.`);
			if (failed > 0) toast.error(`${failed}개 볼륨 삭제에 실패했습니다. 실패한 볼륨은 선택 상태로 유지됩니다.`);
			if (($auth.projectId ?? undefined) !== requestProjectId) return;
			selection.remove(successfulIds);
			const statusReset = await loadStatusSummary({ background: true, reloadOnReset: false });
			await Promise.all([
				load(statusReset ? undefined : markerStack[markerStack.length - 1]),
				loadTimeseries(tsRange, { background: true }),
			]);
		} catch {
			toast.error('볼륨 일괄 삭제 요청에 실패했습니다.');
		} finally {
			bulkDeleting = false;
		}
	}

	const bulkActions = $derived<BulkSelectionAction[]>([
		{ key: 'delete', label: '삭제', tone: 'danger', onAction: bulkDeleteSelectedVolumes },
	]);

	function refreshCurrentVolumeState() {
		void load(markerStack[markerStack.length - 1]);
		void loadStatusSummary();
		void loadTimeseries(tsRange, { background: true });
	}

	const ar = createAutoRefresh(
		() => { load(markerStack[markerStack.length - 1]); loadTimeseries(tsRange, { background: true }); loadStatusSummary({ background: true }); },
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

	onDestroy(() => { resultBoundary += 1; loadGeneration += 1; statusSummaryGeneration += 1; nextPrefetch.cancel(); });
</script>

<div class="bulk-selection-page p-4 md:p-6 pb-28 md:pb-32 max-w-7xl mx-auto">
	<div data-tour="admin-storage-header">
	<PageHeader breadcrumb="STORAGE / VOLUMES" title="전체 볼륨">
		{#snippet actions()}
			<TutorialStartButton tour="admin-storage" compactOnMobile />
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={() => {
					projectFilter = ''; projectSearchText = '';
					statusFilter = ''; nameSearch = '';
					resetResultBoundary();
					void load(undefined, { clearSelection: true });
					void loadStatusSummary();
					void loadTimeseries(tsRange);
				}}
			/>
			<AdminVolumePageSizeToggle
				value={pageSize}
				onChange={(n) => { pageSize = n; resetResultBoundary(); void load(undefined, { clearSelection: true }); }}
			/>
		{/snippet}
	</PageHeader>
	</div>

	<div data-tour="admin-storage-timeseries">
	<AdminVolumeTimeseries
		data={tsData}
		loading={tsLoading}
		range={tsRange}
		onRangeChange={(r) => { tsRange = r; loadTimeseries(r); }}
	/>
	</div>

	<div data-tour="admin-storage-status">
	<AdminVolumeStatusSummary
		summary={statusSummary}
		activeStatus={statusFilter}
		loading={statusSummaryLoading}
		onSelect={applyStatusFilter}
	/>
	</div>

	<div data-tour="admin-storage-filters">
	<AdminVolumeFilters
		bind:projectFilter
		bind:projectSearchText
		bind:statusFilter
		bind:nameSearch
		statusOptions={statusOptions}
		onChange={onFilterChange}
	/>
	</div>

	<div data-tour="admin-storage-list">
	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else}
		<div data-tour="admin-storage-ready">
			<AdminVolumeTable
				volumes={allVolumes}
				{selectedVolumeId}
				{openActionMenu}
				{copiedProjectId}
				selectedIds={selection.ids}
				{selectableIds}
				selectionDisabled={bulkDeleting}
				onSelect={(id) => (selectedVolumeId = id)}
				onToggleSelect={(id) => selection.toggle(id)}
				onToggleAll={() => selection.toggleAll(selectableIds)}
				onActionMenuOpen={(id) => (openActionMenu = id)}
				onActionMenuClose={() => (openActionMenu = null)}
				onCopyProjectId={copyProjectId}
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
		<Pagination
			page={markerStack.length + 1}
			hasPrev={markerStack.length > 0}
			hasNext={!!nextMarker}
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
		</div>
	{/if}
	</div>

	<BulkSelectionOverlay
		count={selection.count}
		ariaLabel="선택한 관리자 볼륨 일괄 작업"
		actions={bulkActions}
		busy={bulkDeleting}
		onClear={() => selection.clear()}
	/>
</div>

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
<AdminVolumeTransferModal volume={transferVolume} onClose={() => (transferVolume = null)} onSuccess={refreshCurrentVolumeState} />
