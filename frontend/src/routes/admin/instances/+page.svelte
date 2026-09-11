<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import TimeSeriesChart from '$lib/components/TimeSeriesChart.svelte';
	import InstanceDetailPanel from '$lib/components/InstanceDetailPanel.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import { projectNames } from '$lib/stores/projectNames';
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
	import { Button, StatTile, ToggleGroup } from '$lib/components/ui';
	import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';

	let allInstances = $state<AdminInstance[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let pageSize = $state(20);
	let markerStack = $state<string[]>([]);
	let nextMarker = $state<string | null>(null);
	let availableHosts = $state<string[]>([]);
	let hostFilter = $state('');
	let statusFilter = $state('');
	let nameSearch = $state('');
	let projectFilter = $state('');
	let projectSearchText = $state('');
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

	const selectableIds = $derived(new Set(allInstances.map((instance) => instance.id)));
	const projectId = $derived($auth.projectId ?? undefined);
	const nextPrefetch = createIntentPrefetchScheduler();
	function listPath(marker?: string): string {
		const params = new URLSearchParams({ limit: String(pageSize) });
		if (marker) params.set('marker', marker);
		if (hostFilter) params.set('host', hostFilter);
		if (projectFilter) params.set('project_id', projectFilter);
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

	async function load(marker?: string, opts?: { clearSelection?: boolean }) {
		const generation = ++loadGeneration;
		const requestToken = $auth.token ?? undefined;
		const requestProjectId = $auth.projectId ?? undefined;
		const requestPageSize = pageSize;
		const requestHostFilter = hostFilter;
		const requestProjectFilter = projectFilter;
		const requestStatusFilter = statusFilter;
		const requestNameSearch = nameSearch;
		const requestPath = listPath(marker);
		const owns = () => generation === loadGeneration
			&& ($auth.token ?? undefined) === requestToken
			&& ($auth.projectId ?? undefined) === requestProjectId
			&& pageSize === requestPageSize
			&& hostFilter === requestHostFilter
			&& projectFilter === requestProjectFilter
			&& statusFilter === requestStatusFilter
			&& nameSearch === requestNameSearch
			&& listPath(marker) === requestPath;
		nextPrefetch.cancel();
		if (opts?.clearSelection) selection.clear();
		allInstances.length === 0 ? (loading = true) : (refreshing = true);
		try {
			const res = await api.get<PagedResponse<AdminInstance>>(requestPath, requestToken, requestProjectId);
			if (!owns()) return;
			allInstances = res.items;
			nextMarker = res.next_marker;
			selection.retain(res.items.map((instance) => instance.id));
			const path = nextMarker ? listPath(nextMarker) : null;
			const key = path ? JSON.stringify([path, requestToken ?? null, requestProjectId ?? null]) : null;
			nextPrefetch.schedule(key, (signal) => path ? api.prefetch(path, requestToken, requestProjectId, { signal }) : undefined);
		} catch {
			if (owns()) allInstances = [];
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

	function openDetail(inst: AdminInstance) { selectedInstanceId = inst.id; selectedProjectId = inst.project_id; }
	function closeDetail() { selectedInstanceId = null; selectedProjectId = null; }
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
		() => { load(markerStack[markerStack.length - 1]); loadTimeseries(tsRange, { background: true }); },
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
		projectNames.load($auth.token ?? undefined, currentProjectId);
	});

	async function bulkAction(action: 'start' | 'stop' | 'delete') {
		const ids = [...selection.ids];
		const requestToken = $auth.token ?? undefined;
		const requestProjectId = $auth.projectId ?? undefined;
		if (ids.length === 0) return;
		const labels: Record<'start' | 'stop' | 'delete', string> = { start: '시작', stop: '종료', delete: '삭제' };
		if (
			(action === 'stop' || action === 'delete')
			&& !await confirmDialog(
				action === 'delete'
					? `선택한 인스턴스 ${ids.length}개를 삭제하시겠습니까?\nManila share와 볼륨도 함께 삭제됩니다.`
					: `선택한 인스턴스 ${ids.length}개를 종료하시겠습니까?`,
			)
		) return;

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
			if (successfulIds.length > 0) toast.success(`${successfulIds.length}개 ${labels[action]} 요청 완료`);
			if (failed > 0) toast.error(`${failed}개 처리 실패`);
			if (($auth.projectId ?? undefined) === requestProjectId) {
				selection.remove(successfulIds);
				ar.setBoost(4);
				void load(markerStack[markerStack.length - 1]);
			}
		} catch {
			toast.error(`일괄 ${labels[action]} 요청 실패`);
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
		projectNames.load($auth.token ?? undefined, $auth.projectId ?? undefined);
	});
	onDestroy(() => { loadGeneration += 1; nextPrefetch.cancel(); });
</script>

<div class="bulk-selection-page p-4 md:p-8 pb-28 md:pb-32 max-w-7xl mx-auto">
	<div data-tour="admin-compute-header">
	<PageHeader breadcrumb="COMPUTE / INSTANCES" title="전체 인스턴스">
		{#snippet actions()}
			<TutorialStartButton tour="admin-compute" compactOnMobile />
			<Button onclick={() => openWizard()} variant="accent" size="sm">
				<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
				</svg>
				VM 생성
			</Button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={() => { markerStack = []; nextMarker = null; hostFilter = ''; projectFilter = ''; projectSearchText = ''; statusFilter = ''; nameSearch = ''; void load(undefined, { clearSelection: true }); void loadHosts(); }}
			/>
			<div class="flex items-center gap-1 text-xs text-ink-3 max-md:hidden">
				표시:
				<ToggleGroup
					value={String(pageSize)}
					options={[10, 20, 30].map((n) => ({ value: String(n), label: String(n) }))}
					onchange={(value) => { pageSize = parseInt(value, 10); markerStack = []; nextMarker = null; void load(undefined, { clearSelection: true }); }}
					size="xs"
				/>
			</div>
		{/snippet}
	</PageHeader>
	</div>

	{#if health}
		<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5 mb-4">
			<StatTile label="전체 VM" value={health.total} unit="instances" accent="blue" />
			<StatTile label="ACTIVE" value={health.active} unit="/ {health.total}" accent="emerald" />
			<StatTile label="ERROR" value={health.error} unit="instances" accent="rose" />
			<StatTile label="알림 있음" value={health.with_alerts} unit="instances" accent="amber" class="max-md:hidden" />
			<StatTile label="GPU VM" value={health.gpu_count} unit="가속" accent="violet" class="max-md:hidden" />
		</div>
	{/if}

	<div data-tour="admin-compute-filters">
	<AdminInstanceFilters
		{availableHosts}
		bind:hostFilter
		bind:statusFilter
		bind:nameSearch
		bind:projectFilter
		bind:projectSearchText
		onChange={onFilterChange}
	/>
	</div>

	<div class="mb-6" data-tour="admin-compute-timeseries">
		{#if tsLoading}
			<div class="bg-surface-base border border-line rounded-xl p-5 h-48 flex items-center justify-center">
				<div class="text-ink-3 text-sm">차트 로딩 중...</div>
			</div>
		{:else}
			<TimeSeriesChart
				data={tsData}
				title="인스턴스 수 추이"
				mainKey="total"
				extraKeys={['active', 'shutoff', 'error', 'shelved']}
				currentRange={tsRange}
				onRangeChange={(r) => { tsRange = r; loadTimeseries(r); }}
			/>
		{/if}
	</div>


	<div data-tour="admin-compute-list">
	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else}
		<div data-tour="admin-compute-ready">
		<AdminInstanceTable
			instances={allInstances}
			{markerStack}
			{nextMarker}
			{refreshing}
			selectedIds={selection.ids}
			{selectableIds}
			selectionDisabled={bulkActioning}
			onOpen={openDetail}
			{onPrev}
			{onNext}
			onintent={prefetchNext}
			onRecover={openRecovery}
			onToggleSelect={(id) => selection.toggle(id)}
			onToggleAll={() => selection.toggleAll(selectableIds)}
		/>
		</div>
	{/if}
	</div>

	<BulkSelectionOverlay
		count={selection.count}
		ariaLabel="관리자 선택 인스턴스 일괄 작업"
		actions={[
			{ key: 'start', label: '시작', tone: 'success', onAction: () => bulkAction('start') },
			{ key: 'stop', label: '종료', tone: 'warning', onAction: () => bulkAction('stop') },
			{ key: 'delete', label: '삭제', tone: 'danger', onAction: () => bulkAction('delete') },
		]}
		busy={bulkActioning}
		onClear={() => selection.clear()}
	/>
</div>

{#if selectedInstanceId}
	<SlidePanel onClose={closeDetail} ariaLabel="관리자 인스턴스 상세" dataTour="admin-compute-detail">
		<InstanceDetailPanel instanceId={selectedInstanceId} adminProjectId={selectedProjectId} onClose={closeDetail} showHost={true} />
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
