<script lang="ts">
	import { t } from '$lib/i18n/ns/topology';
	import { onMount, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createAdminTopologyController } from '$lib/stores/adminTopologyController.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
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
	const viewOptions = $derived([
		{ value: 'lane', label: t('topology.lane') },
		{ value: 'canvas', label: t('topology.canvas') },
	]);
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
	<PageHeader breadcrumb={t('topology.breadcrumb')} title={t('topology.title')}>
		{#snippet actions()}
			<TutorialStartButton tour="admin-network" compactOnMobile />
			<ToggleGroup value={view} options={viewOptions} onchange={onViewChange} ariaLabel={t('topology.viewLabel')} />
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

	<!-- 갱신 실패는 그려진 토폴로지를 내리지 않는다(다시 마운트되면 자동 갱신이 진입 모션을 재생한다) -->
	{#if ctrl.error}
		{#if ctrl.data}
			<div role="status" class="mb-4 rounded-lg border border-state-danger/30 bg-state-danger/10 px-4 py-3 text-sm text-state-danger">{ctrl.error}</div>
		{:else}
			<Alert tone="danger" class="mb-4">{ctrl.error}</Alert>
		{/if}
	{/if}
	{#if ctrl.loading}
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
					arrivalScope="admin"
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
					arrivalScope="admin"
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
		<div class="mt-4 flex gap-6 text-xs text-ink-2 px-1">
			<span>{t('summary.networks', { count: ctrl.data.networks.length })}</span>
			<span>{t('summary.routers', { count: ctrl.data.routers.length })}</span>
			<span>{t('summary.instances', { count: ctrl.data.instances.length })}</span>
			<span>{t('summary.floatingIps', { count: ctrl.data.floating_ips.length })}</span>
			<span>{t('summary.loadBalancers', { count: (ctrl.data.load_balancers ?? []).length })}</span>
		</div>
		</div>
	{/if}
</div>

{#if ctrl.selectedInstanceId}
	<SlidePanel onClose={() => ctrl.selectedInstanceId = null} ariaLabel={t('topology.instanceDetailLabel')}>
		<InstanceDetailPanel instanceId={ctrl.selectedInstanceId} adminProjectId={ctrl.data?.instances.find((instance) => instance.id === ctrl.selectedInstanceId)?.project_id ?? null} onClose={() => ctrl.selectedInstanceId = null} showHost={true} />
	</SlidePanel>
{/if}

{#if ctrl.selectedRouterId}
	<SlidePanel onClose={() => ctrl.selectedRouterId = null} ariaLabel={t('topology.routerDetailLabel')} width="w-full md:w-[60vw] max-w-3xl" dataTour="admin-network-detail">
		<RouterDetailPanel routerId={ctrl.selectedRouterId} onClose={() => ctrl.selectedRouterId = null} />
	</SlidePanel>
{/if}

{#if ctrl.selectedLB}
	<SlidePanel onClose={() => ctrl.selectedLB = null} ariaLabel={t('topology.loadBalancerDetailLabel')} width="w-full md:w-[60vw] max-w-2xl">
		<TopologyLBPanel lb={ctrl.selectedLB} onClose={() => ctrl.selectedLB = null} />
	</SlidePanel>
{/if}

{#if selectedNetworkId && ctrl.data}
	<SlidePanel onClose={() => selectedNetworkId = null} ariaLabel={t('topology.networkDetailLabel')} width="w-full md:w-[60vw] max-w-2xl">
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
