<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createAdminTopologyController } from '$lib/stores/adminTopologyController.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import GlobalTopology from '$lib/components/GlobalTopology.svelte';
	import InstanceDetailPanel from '$lib/components/InstanceDetailPanel.svelte';
	import RouterDetailPanel from '$lib/components/RouterDetailPanel.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { projectNames } from '$lib/stores/projectNames';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import type { TopologyLoadBalancer } from '$lib/types/topology';
	import ProjectFilter from '$lib/components/admin/topology/ProjectFilter.svelte';
	import TopologyLegend from '$lib/components/admin/topology/TopologyLegend.svelte';
	import TopologyLBPanel from '$lib/components/admin/topology/TopologyLBPanel.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
	import TopologyCanvas from '$lib/components/topology/canvas/TopologyCanvas.svelte';
	import CanvasLegend from '$lib/components/topology/canvas/CanvasLegend.svelte';
	import TopologyNetworkPanel from '$lib/components/topology/canvas/TopologyNetworkPanel.svelte';
	import { DEFAULT_TOPOLOGY_VIEW, isTopologyView, readTopologyView, writeTopologyView, type TopologyView } from '$lib/utils/topologyViewPreference';

	let isLight = $state(false);
	onMount(() => {
		isLight = document.documentElement.classList.contains('light');
		const obs = new MutationObserver(() => {
			isLight = document.documentElement.classList.contains('light');
		});
		obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
		return () => obs.disconnect();
	});

	const ctrl = createAdminTopologyController({
		token: () => $auth.token ?? undefined,
		projectId: () => $auth.projectId ?? undefined,
	});

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

	// 네트워크(스위치) 선택은 페이지 로컬 상태. 다른 선택과 상호 배타이며 패널을 닫으면 강조도 해제된다.
	let selectedNetworkId = $state<string | null>(null);
	const topologySelectedId = $derived(ctrl.topologySelectedId ?? selectedNetworkId);

	function onSelectInstance(id: string) {
		if (ctrl.selectedInstanceId === id) { ctrl.selectedInstanceId = null; }
		else { ctrl.selectedInstanceId = id; ctrl.selectedRouterId = null; ctrl.selectedLB = null; selectedNetworkId = null; }
	}
	function onSelectRouter(id: string) {
		if (ctrl.selectedRouterId === id) { ctrl.selectedRouterId = null; }
		else { ctrl.selectedRouterId = id; ctrl.selectedInstanceId = null; ctrl.selectedLB = null; selectedNetworkId = null; }
	}
	function onSelectLoadBalancer(lb: TopologyLoadBalancer) {
		if (ctrl.selectedLB?.id === lb.id) { ctrl.selectedLB = null; }
		else { ctrl.selectedLB = lb; ctrl.selectedInstanceId = null; ctrl.selectedRouterId = null; selectedNetworkId = null; }
	}
	function onSelectNetwork(id: string) {
		if (selectedNetworkId === id) { selectedNetworkId = null; }
		else { selectedNetworkId = id; ctrl.selectedInstanceId = null; ctrl.selectedRouterId = null; ctrl.selectedLB = null; }
	}

	const ar = createAutoRefresh(ctrl.fetchTopology, {
		storageKey: 'admin-topology',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60]
	});

	const arTraffic = createAutoRefresh(ctrl.loadTraffic, {
		storageKey: 'admin-topology-traffic',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30],
	});

	$effect(() => {
		if (!$auth.token) return;
		untrack(() => ctrl.fetchTopology());
	});

	$effect(() => {
		if (!$auth.token) return;
		untrack(() => ctrl.loadTraffic());
	});

	onMount(() => {
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		projectNames.load(token, projectId);
		document.addEventListener('click', ctrl.handleDocumentClick);
		return () => document.removeEventListener('click', ctrl.handleDocumentClick);
	});
</script>

<div class="p-4 md:p-6 max-w-screen-2xl mx-auto">
	<div data-tour="admin-network-header">
	<PageHeader breadcrumb="NETWORK / TOPOLOGY" title="토폴로지">
		{#snippet actions()}
			<TutorialStartButton tour="admin-network" compactOnMobile />
			<ToggleGroup value={view} options={viewOptions} onchange={onViewChange} ariaLabel="토폴로지 보기" />
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={ctrl.loading || ctrl.refreshing}
				onManualRefresh={ctrl.fetchTopology}
			/>
		{/snippet}
	</PageHeader>
	</div>

	<!-- 프로젝트 필터 -->
	<div class="flex gap-3 mb-4" data-tour="admin-network-filter">
		<ProjectFilter bind:projectFilter={ctrl.projectFilter} bind:searchText={ctrl.projectSearchText} bind:dropdownOpen={ctrl.projectDropdownOpen} />
	</div>

	{#if ctrl.error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">
			{ctrl.error}
		</div>
	{:else if ctrl.loading}
		<LoadingSkeleton variant="card" rows={8} />
	{:else if ctrl.data}
		<div class="bg-surface-base border border-line rounded-lg p-6 mb-4" data-tour="admin-network-canvas">
			<div data-tour="admin-network-ready">
			{#if view === 'canvas'}
				<TopologyCanvas
					data={ctrl.data}
					traffic={ctrl.traffic}
					projectId={ctrl.projectFilter}
					showAll={ctrl.projectFilter == null}
					selectedId={topologySelectedId}
					adminView={true}
					storageScope="admin"
					{onSelectInstance}
					{onSelectRouter}
					{onSelectLoadBalancer}
					{onSelectNetwork}
				/>
			{:else}
				<GlobalTopology
					data={ctrl.data}
					traffic={ctrl.traffic}
					projectId={ctrl.projectFilter}
					showAll={ctrl.projectFilter == null}
					selectedId={topologySelectedId}
					{onSelectInstance}
					{onSelectRouter}
					{onSelectLoadBalancer}
				/>
			{/if}
			</div>
		</div>

		<div data-tour="admin-network-legend">
		{#if view === 'canvas'}
			<CanvasLegend />
		{:else}
			<TopologyLegend {isLight} />
		{/if}

		<!-- 전체 요약 -->
		<div class="mt-4 flex gap-6 text-xs text-ink-3 px-1">
			<span>네트워크 {ctrl.data.networks.length}개</span>
			<span>라우터 {ctrl.data.routers.length}개</span>
			<span>인스턴스 {ctrl.data.instances.length}개</span>
			<span>Floating IP {ctrl.data.floating_ips.length}개</span>
			<span>로드밸런서 {(ctrl.data.load_balancers ?? []).length}개</span>
		</div>
		</div>
	{/if}
</div>

{#if ctrl.selectedInstanceId}
	<SlidePanel onClose={() => ctrl.selectedInstanceId = null} ariaLabel="토폴로지 인스턴스 상세">
		<InstanceDetailPanel instanceId={ctrl.selectedInstanceId} onClose={() => ctrl.selectedInstanceId = null} showHost={true} />
	</SlidePanel>
{/if}

{#if ctrl.selectedRouterId}
	<SlidePanel onClose={() => ctrl.selectedRouterId = null} ariaLabel="토폴로지 라우터 상세" width="w-full md:w-[60vw] max-w-3xl" dataTour="admin-network-detail">
		<RouterDetailPanel routerId={ctrl.selectedRouterId} onClose={() => ctrl.selectedRouterId = null} />
	</SlidePanel>
{/if}

{#if ctrl.selectedLB}
	<SlidePanel onClose={() => ctrl.selectedLB = null} ariaLabel="토폴로지 로드밸런서 상세" width="w-full md:w-[60vw] max-w-2xl">
		<TopologyLBPanel lb={ctrl.selectedLB} onClose={() => ctrl.selectedLB = null} />
	</SlidePanel>
{/if}

{#if selectedNetworkId && ctrl.data}
	<SlidePanel onClose={() => selectedNetworkId = null} ariaLabel="토폴로지 네트워크 상세" width="w-full md:w-[60vw] max-w-2xl">
		<TopologyNetworkPanel
			networkId={selectedNetworkId}
			data={ctrl.data}
			traffic={ctrl.traffic}
			showProvider={true}
			loadHistory={ctrl.loadNetworkHistory}
			{onSelectInstance}
			{onSelectRouter}
		/>
	</SlidePanel>
{/if}
