<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
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

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
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

	async function loadStatusSummary(opts?: { background?: boolean }) {
		if (!opts?.background && statusSummary === null) statusSummaryLoading = true;
		try {
			statusSummary = await api.get<VolumeStatusSummary>('/api/v1/admin/volumes/status-summary', token, projectId);
		} catch {
			if (!opts?.background) statusSummary = null;
		} finally {
			statusSummaryLoading = false;
		}
	}

	function applyStatusFilter(status: string) {
		statusFilter = status;
		markerStack = [];
		nextMarker = null;
		load();
	}

	async function load(marker?: string) {
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
		if (allVolumes.length === 0) loading = true;
		else refreshing = true;
		try {
			const res = await api.get<PagedResponse<AdminVolume>>(requestPath, requestToken, requestProjectId);
			if (!owns()) return;
			allVolumes = res.items;
			nextMarker = res.next_marker;
			const path = nextMarker ? listPath(nextMarker) : null;
			const key = path ? JSON.stringify([path, requestToken ?? null, requestProjectId ?? null]) : null;
			nextPrefetch.schedule(key, (signal) => path ? api.prefetch(path, requestToken, requestProjectId, { signal }) : undefined);
		} catch {
			if (owns()) allVolumes = [];
		} finally {
			if (owns()) {
				loading = false;
				refreshing = false;
			}
		}
	}

	const ar = createAutoRefresh(
		() => { load(markerStack[markerStack.length - 1]); loadTimeseries(tsRange, { background: true }); loadStatusSummary({ background: true }); },
		{ storageKey: 'admin-volumes', defaultActive: true, defaultInterval: 30, intervalOptions: [15, 30, 60], invokeOnMount: false },
	);

	onMount(() => {
		if (window.matchMedia('(max-width: 767px)').matches) pageSize = 10;
		load();
		loadTimeseries(tsRange);
		loadStatusSummary();
		projectNames.load(token, projectId);
	});

	onDestroy(() => { loadGeneration += 1; nextPrefetch.cancel(); });
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
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
					markerStack = []; nextMarker = null;
					projectFilter = ''; projectSearchText = '';
					statusFilter = ''; nameSearch = '';
					load(); loadStatusSummary(); loadTimeseries(tsRange);
				}}
			/>
			<AdminVolumePageSizeToggle
				value={pageSize}
				onChange={(n) => { pageSize = n; markerStack = []; nextMarker = null; load(); }}
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
		onChange={() => { markerStack = []; nextMarker = null; load(); }}
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
				onSelect={(id) => (selectedVolumeId = id)}
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
				load(marker);
			}}
			onNext={() => {
				if (!nextMarker) return;
				markerStack = [...markerStack, nextMarker];
				load(nextMarker);
			}}
			onintent={prefetchNext}
		/>
		</div>
	{/if}
	</div>
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

<AdminVolumeEditModal volume={editVolume} onClose={() => (editVolume = null)} onSuccess={() => load()} />
<AdminVolumeDeleteModal volume={deleteVolume} onClose={() => (deleteVolume = null)} onSuccess={() => load()} />
<AdminVolumeExtendModal volume={extendVolume} onClose={() => (extendVolume = null)} onSuccess={() => load()} />
<AdminVolumeResetStatusModal volume={resetVolume} onClose={() => (resetVolume = null)} onSuccess={() => load(markerStack[markerStack.length - 1])} />
<AdminVolumeForceDeleteModal volume={forceDeleteVolume} onClose={() => (forceDeleteVolume = null)} onSuccess={() => load(markerStack[markerStack.length - 1])} />
<AdminVolumeTransferModal volume={transferVolume} onClose={() => (transferVolume = null)} onSuccess={() => load(markerStack[markerStack.length - 1])} />
