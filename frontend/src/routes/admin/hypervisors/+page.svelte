<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { formatNumber, formatStorage } from '$lib/utils/format';
	import { projectNames } from '$lib/stores/projectNames';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import HypervisorTable from '$lib/components/admin/hypervisors/HypervisorTable.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import InstanceDetailPanel from '$lib/components/InstanceDetailPanel.svelte';
	import type { HypervisorRow } from '$lib/components/admin/hypervisors/HypervisorTable.svelte';
	import HypervisorDetailPanel from '$lib/components/admin/hypervisors/HypervisorDetailPanel.svelte';
	import type { HypervisorDetail } from '$lib/components/admin/hypervisors/HypervisorDetailPanel.svelte';
	import HypervisorMigrateModal from '$lib/components/admin/hypervisors/HypervisorMigrateModal.svelte';
	import type { AggregatedHost, GpuType, GpuResponse } from '$lib/types/gpu';

	let hypervisors = $state<HypervisorRow[]>([]);
	let gpuHostMap = $state<Map<string, AggregatedHost>>(new Map());
	let gpuTypes = $state<GpuType[]>([]);
	let selectedGpuTypes = $state<Set<string>>(new Set());
	let loading = $state(true);
	let refreshing = $state(false);
	let sortColumn = $state('');
	let sortAsc = $state(true);

	let selectedDetail = $state<HypervisorDetail | null>(null);
	let detailLoading = $state(false);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load() {
		if (hypervisors.length === 0) loading = true;
		else refreshing = true;
		// GPU 정보(gpu-hosts)는 실패해도 하이퍼바이저 목록 표시에는 영향 없음
		const [hvResult, gpuResult] = await Promise.allSettled([
			api.get<HypervisorRow[]>('/api/v1/admin/hypervisors', token, projectId),
			api.get<GpuResponse>('/api/v1/admin/gpu-hosts', token, projectId),
		]);
		hypervisors = hvResult.status === 'fulfilled' ? hvResult.value : [];
		if (gpuResult.status === 'fulfilled') {
			gpuHostMap = new Map((gpuResult.value.aggregated_hosts ?? []).map((h) => [h.name, h]));
			gpuTypes = gpuResult.value.gpu_types ?? [];
		} else {
			gpuHostMap = new Map();
			gpuTypes = [];
		}
		loading = false;
		refreshing = false;
	}

	// 하이퍼바이저 행에 GPU 사용량·모델 결합 (gpu-hosts 호스트명 = hypervisor_hostname)
	let joinedHypervisors = $derived(
		hypervisors.map((h) => {
			const g = gpuHostMap.get(h.name);
			if (!g) return h;
			const gpu_model = g.gpu_groups.map((grp) => grp.device_name).join(', ') || null;
			return { ...h, gpu_total: g.gpu_total, gpu_used: g.gpu_used, gpu_model };
		})
	);

	function toggleGpuType(deviceName: string) {
		const next = new Set(selectedGpuTypes);
		if (next.has(deviceName)) next.delete(deviceName);
		else next.add(deviceName);
		selectedGpuTypes = next;
	}

	let filteredHypervisors = $derived(
		selectedGpuTypes.size === 0
			? joinedHypervisors
			: joinedHypervisors.filter((h) => {
					const g = gpuHostMap.get(h.name);
					return g?.gpu_groups.some((grp) => selectedGpuTypes.has(grp.device_name)) ?? false;
				})
	);

	async function loadDetail(hvId: string) {
		detailLoading = true;
		selectedDetail = null;
		try {
			selectedDetail = await api.get<HypervisorDetail>(`/api/v1/admin/hypervisors/${hvId}`, token, projectId);
		} catch {
			selectedDetail = null;
		} finally {
			detailLoading = false;
		}
	}

	function toggleSort(col: string) {
		if (sortColumn === col) {
			sortAsc = !sortAsc;
		} else {
			sortColumn = col;
			sortAsc = true;
		}
	}

	const STRING_SORT_COLS = new Set(['name', 'cpu_model', 'gpu_model']);

	let sortedHypervisors = $derived(
		filteredHypervisors.toSorted((a, b) => {
			if (!sortColumn) return 0;
			let va: string | number;
			let vb: string | number;
			if (STRING_SORT_COLS.has(sortColumn)) {
				va = (a as unknown as Record<string, string>)[sortColumn] ?? '';
				vb = (b as unknown as Record<string, string>)[sortColumn] ?? '';
			} else {
				va = (a as unknown as Record<string, number>)[sortColumn] ?? 0;
				vb = (b as unknown as Record<string, number>)[sortColumn] ?? 0;
			}
			const cmp = typeof va === 'string' ? va.localeCompare(vb as string) : (va as number) - (vb as number);
			return sortAsc ? cmp : -cmp;
		})
	);

	let selectedInstanceId = $state<string | null>(null);
	let selectedProjectId = $state<string | null>(null);

	function openInstanceDetail(id: string, pid: string) { selectedInstanceId = id; selectedProjectId = pid; }
	function closeInstanceDetail() { selectedInstanceId = null; selectedProjectId = null; }

	let showMigrateModal = $state(false);
	let migrateContext = $state({ serverId: '', serverName: '', type: 'live' as 'live' | 'cold' });

	function openMigrate(id: string, name: string, t: 'live' | 'cold') {
		migrateContext = { serverId: id, serverName: name, type: t };
		showMigrateModal = true;
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-hypervisors',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60]
	});

	onMount(() => {
		load();
		projectNames.load(token, projectId);
	});
</script>

<div class="flex h-full">
<div class="flex-1 p-4 md:p-8 max-w-7xl mx-auto overflow-auto">
	<PageHeader breadcrumb="COMPUTE / HYPERVISORS" title="하이퍼바이저">
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={load}
			/>
		{/snippet}
	</PageHeader>

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if hypervisors.length === 0}
		<div class="text-ink-3 text-sm">하이퍼바이저가 없습니다</div>
	{:else}
		{#if gpuTypes.length > 0}
			<div class="flex items-center gap-2 mb-3 flex-wrap">
				<span class="text-xs text-ink-3">GPU 필터:</span>
				{#each gpuTypes as gt (gt.device_name)}
					<button
						onclick={() => toggleGpuType(gt.device_name)}
						class="text-xs px-2.5 py-1 rounded transition-colors {selectedGpuTypes.has(gt.device_name) ? 'bg-surface-selected/50 text-action-warm border border-action-warm/50' : 'text-ink-2 hover:text-ink-0 border border-line'}"
					>{gt.device_name} <span class="text-ink-3">{gt.used}/{gt.total}</span></button>
				{/each}
				{#if selectedGpuTypes.size > 0}
					<button onclick={() => (selectedGpuTypes = new Set())} class="text-xs text-ink-3 hover:text-ink-0 transition-colors">✕ 초기화</button>
				{/if}
			</div>
		{/if}
			<HypervisorTable
				hypervisors={sortedHypervisors}
				selectedId={selectedDetail?.id ?? null}
				{sortColumn}
				{sortAsc}
				onSort={toggleSort}
				onSelect={loadDetail}
			/>
	{/if}
</div>

{#if selectedDetail !== null || detailLoading}
	<HypervisorDetailPanel
		detail={selectedDetail}
		loading={detailLoading}
		projectNameMap={$projectNames}
		gpus={selectedDetail ? (gpuHostMap.get(selectedDetail.hypervisor_hostname)?.gpus ?? []) : []}
		onClose={() => { selectedDetail = null; }}
		onMigrate={openMigrate}
		onOpenDetail={openInstanceDetail}
	/>
{/if}
</div>

{#if selectedInstanceId}
	<SlidePanel onClose={closeInstanceDetail} ariaLabel="하이퍼바이저 인스턴스 상세">
		<InstanceDetailPanel instanceId={selectedInstanceId} adminProjectId={selectedProjectId} onClose={closeInstanceDetail} showHost={true} />
	</SlidePanel>
{/if}

{#if showMigrateModal}
	<HypervisorMigrateModal
		bind:open={showMigrateModal}
		serverId={migrateContext.serverId}
		serverName={migrateContext.serverName}
		type={migrateContext.type}
		onMigrated={() => selectedDetail && loadDetail(selectedDetail.id)}
	/>
{/if}
