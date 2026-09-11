<script lang="ts">
	import { onDestroy, onMount, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import GlobalTopology from '$lib/components/GlobalTopology.svelte';
	import InstanceDetailPanel from '$lib/components/InstanceDetailPanel.svelte';
	import RouterDetailPanel from '$lib/components/RouterDetailPanel.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
	import TopologyCanvas from '$lib/components/topology/canvas/TopologyCanvas.svelte';
	import CanvasLegend from '$lib/components/topology/canvas/CanvasLegend.svelte';
	import TopologyNetworkPanel from '$lib/components/topology/canvas/TopologyNetworkPanel.svelte';
	import { DEFAULT_TOPOLOGY_VIEW, isTopologyView, readTopologyView, writeTopologyView, type TopologyView } from '$lib/utils/topologyViewPreference';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import TopologyLegend from '$lib/components/dashboard/network/topology/TopologyLegend.svelte';
	import TopologySummary from '$lib/components/dashboard/network/topology/TopologySummary.svelte';
	import LoadBalancerDetailPanel from '$lib/components/dashboard/network/topology/LoadBalancerDetailPanel.svelte';
	import type { TopologyData, TopologyTraffic, TopologyLoadBalancer, TopologyTrafficHistory } from '$lib/types/topology';
	import PageShell from '$lib/components/ui/PageShell.svelte';

	let data = $state<TopologyData | null>(null);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');
	let traffic = $state<TopologyTraffic | null>(null);
	let selectedInstanceId = $state<string | null>(null);
	let selectedRouterId = $state<string | null>(null);
	let selectedLB = $state<TopologyLoadBalancer | null>(null);
	let selectedNetworkId = $state<string | null>(null);
	// 뷰 선택(레인 | 캔버스)은 localStorage 'topology.view' 에 저장한다. 기본은 캔버스.
	let view = $state<TopologyView>(DEFAULT_TOPOLOGY_VIEW);
	onMount(() => { view = readTopologyView(); });
	const viewOptions = [
		{ value: 'lane', label: '레인' },
		{ value: 'canvas', label: '캔버스' },
	];
	function onViewChange(value: string) {
		if (!isTopologyView(value)) return;
		view = value;
		writeTopologyView(value);
	}
	let intentTimer: ReturnType<typeof setTimeout> | null = null;
	let intentController: AbortController | null = null;

	// 토폴로지 선택 상태를 부모에서 파생 (패널 닫을 때 자동 highlight 해제)
	const topologySelectedId = $derived(
		selectedInstanceId ?? selectedRouterId ?? selectedLB?.id ?? selectedNetworkId ?? null
	);

	function onSelectInstance(id: string) {
		if (selectedInstanceId === id) { selectedInstanceId = null; }
		else { selectedInstanceId = id; selectedRouterId = null; selectedLB = null; selectedNetworkId = null; }
	}
	function onSelectRouter(id: string) {
		if (selectedRouterId === id) { selectedRouterId = null; }
		else { selectedRouterId = id; selectedInstanceId = null; selectedLB = null; selectedNetworkId = null; }
	}
	function onSelectLoadBalancer(lb: TopologyLoadBalancer) {
		if (selectedLB?.id === lb.id) { selectedLB = null; }
		else { selectedLB = lb; selectedInstanceId = null; selectedRouterId = null; selectedNetworkId = null; }
	}
	function onSelectNetwork(id: string) {
		if (selectedNetworkId === id) { selectedNetworkId = null; }
		else { selectedNetworkId = id; selectedInstanceId = null; selectedRouterId = null; selectedLB = null; }
	}

	function cancelIntent() {
		clearTimeout(intentTimer ?? undefined);
		intentTimer = null;
		intentController?.abort();
		intentController = null;
	}

	function scheduleIntent(path: string) {
		cancelIntent();
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		intentTimer = setTimeout(() => {
			intentTimer = null;
			const controller = new AbortController();
			intentController = controller;
			void api.prefetch(path, token, projectId, { signal: controller.signal });
		}, 150);
	}

	function onIntentInstance(id: string) {
		scheduleIntent(`/api/v1/instances/${id}`);
	}

	function onIntentRouter(id: string) {
		scheduleIntent(`/api/v1/routers/${id}`);
	}

	const ar = createAutoRefresh(() => fetchTopology(), {
		storageKey: 'dashboard-network-topology',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [10, 15, 30, 60],
	});

	async function loadTraffic() {
		if (!$auth.token) return;
		try {
			traffic = await api.get<TopologyTraffic>(
				'/api/v1/networks/topology/traffic',
				$auth.token ?? undefined,
				$auth.projectId ?? undefined,
			);
		} catch { /* silent — 토폴로지 표시는 traffic=null 로 유지 */ }
	}

	/**
	 * 네트워크 사용량 히스토리. 네트워크 패널을 열 때 1회만 호출한다 —
	 * 폴링(`arTraffic`)에 얹으면 Prometheus 부하가 네트워크 수만큼 곱해진다.
	 */
	async function loadNetworkHistory(networkId: string, range: string): Promise<TopologyTrafficHistory | null> {
		if (!$auth.token) return null;
		return api.get<TopologyTrafficHistory>(
			`/api/v1/networks/topology/traffic/history?network_id=${encodeURIComponent(networkId)}&range=${encodeURIComponent(range)}`,
			$auth.token ?? undefined,
			$auth.projectId ?? undefined,
		);
	}

	const arTraffic = createAutoRefresh(loadTraffic, {
		storageKey: 'dashboard-network-topology-traffic',
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30],
	});

	$effect(() => {
		if (!$auth.token || !$auth.projectId) return;
		cancelIntent();
		untrack(() => fetchTopology());
	});

	async function fetchTopology(opts?: { refresh?: boolean }) {
		if (!data) loading = true;
		else refreshing = true;
		error = '';
		try {
			data = await api.get<TopologyData>(
				'/api/v1/networks/topology',
				$auth.token ?? undefined,
				$auth.projectId ?? undefined,
				opts,
			);
		} catch (e) {
			error = e instanceof ApiError ? `조회 실패 (${e.status}): ${e.message}` : '서버 오류';
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	async function forceRefresh() {
		refreshing = true;
		try {
			await fetchTopology({ refresh: true });
		} finally {
			refreshing = false;
		}
	}
	onDestroy(cancelIntent);
</script>

<PageShell class="max-w-screen-2xl">
	<PageHeader breadcrumb="NETWORK / TOPOLOGY" title="토폴로지">
		{#snippet actions()}
			<ToggleGroup value={view} options={viewOptions} onchange={onViewChange} ariaLabel="토폴로지 보기" />
			<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={refreshing || loading}
			onManualRefresh={forceRefresh}
		/>
		{/snippet}
	</PageHeader>

	{#if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">
			{error}
		</div>
	{:else if loading}
		<LoadingSkeleton variant="card" rows={8} />
	{:else if data}
		{@const _visibleNets = data.networks.filter(n => n.is_external || n.is_shared || n.project_id === $auth.projectId)}
		{@const _projectRouters = data.routers.filter(r => r.project_id === $auth.projectId)}
		{@const _projectFips = data.floating_ips.filter(f => !f.project_id || f.project_id === $auth.projectId)}
		{@const _projectLbs = (data.load_balancers ?? []).filter(lb => !lb.project_id || lb.project_id === $auth.projectId)}
		<div class="rounded-lg border border-line bg-surface-base p-3 md:p-6 mb-4">
			{#if view === 'canvas'}
				<TopologyCanvas
					{data}
					{traffic}
					projectId={$auth.projectId}
					selectedId={topologySelectedId}
					storageScope="user"
					{onSelectInstance}
					{onSelectRouter}
					{onSelectLoadBalancer}
					{onSelectNetwork}
					{onIntentInstance}
					{onIntentRouter}
					onCancelIntent={cancelIntent}
				/>
			{:else}
				<GlobalTopology
					{data}
					{traffic}
					projectId={$auth.projectId}
					selectedId={topologySelectedId}
					{onSelectInstance}
					{onSelectRouter}
					{onSelectLoadBalancer}
					{onIntentInstance}
					{onIntentRouter}
					onCancelIntent={cancelIntent}
				/>
			{/if}
		</div>

		{#if view === 'canvas'}
			<CanvasLegend />
		{:else}
			<TopologyLegend />
		{/if}

		<TopologySummary
			visibleNetworkCount={_visibleNets.length}
			projectRouterCount={_projectRouters.length}
			instanceCount={data.instances.length}
			projectFipCount={_projectFips.length}
			projectLbCount={_projectLbs.length}
		/>
	{/if}
</PageShell>

{#if selectedInstanceId}
	<SlidePanel onClose={() => selectedInstanceId = null} ariaLabel="토폴로지 인스턴스 상세">
		<InstanceDetailPanel instanceId={selectedInstanceId} onClose={() => selectedInstanceId = null} />
	</SlidePanel>
{/if}

{#if selectedRouterId}
	<SlidePanel onClose={() => selectedRouterId = null} ariaLabel="토폴로지 라우터 상세" width="w-full md:w-[60vw] max-w-3xl">
		<RouterDetailPanel routerId={selectedRouterId} onClose={() => selectedRouterId = null} />
	</SlidePanel>
{/if}

{#if selectedLB}
	<SlidePanel onClose={() => selectedLB = null} ariaLabel="토폴로지 로드밸런서 상세" width="w-full md:w-[60vw] max-w-2xl">
		<LoadBalancerDetailPanel lb={selectedLB} onClose={() => selectedLB = null} />
	</SlidePanel>
{/if}

{#if selectedNetworkId && data}
	<SlidePanel onClose={() => selectedNetworkId = null} ariaLabel="토폴로지 네트워크 상세" width="w-full md:w-[60vw] max-w-2xl">
		<TopologyNetworkPanel
			networkId={selectedNetworkId}
			{data}
			{traffic}
			showProvider={false}
			loadHistory={loadNetworkHistory}
			{onSelectInstance}
			{onSelectRouter}
		/>
	</SlidePanel>
{/if}
