<script lang="ts">
	import { goto } from '$app/navigation';
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
	import NetworkDetailPanel from '$lib/components/NetworkDetailPanel.svelte';
	import NetworkCreateModal from '$lib/components/dashboard/network/networks/NetworkCreateModal.svelte';
	import RouterCreateModal from '$lib/components/network/routers/RouterCreateModal.svelte';
	import DbCreatePanel from '$lib/components/database/DbCreatePanel.svelte';
	import { openWizard } from '$lib/stores/wizard';
	import { toast } from '$lib/stores/toast';
	import { type TopologyLinkRequest } from '$lib/components/topology/canvas/link-types';
	import { DEFAULT_TOPOLOGY_VIEW, isTopologyView, readTopologyView, writeTopologyView, type TopologyView } from '$lib/utils/topologyViewPreference';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import TopologyLegend from '$lib/components/dashboard/network/topology/TopologyLegend.svelte';
	import TopologySummary from '$lib/components/dashboard/network/topology/TopologySummary.svelte';
	import LoadBalancerDetailPanel from '$lib/components/dashboard/network/topology/LoadBalancerDetailPanel.svelte';
	import type { TopologyData, TopologyTraffic, TopologyLoadBalancer } from '$lib/types/topology';
	import type { Network } from '$lib/types/networks';
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
	let showNetworkCreate = $state(false);
	let showRouterCreate = $state(false);
	let showDbCreate = $state(false);
	let creatingNetwork = $state(false);
	let createNetworkError = $state('');
	const externalNetworks = $derived<Network[]>(
		(data?.networks ?? []).filter((network) => network.is_external).map((network) => ({
			id: network.id,
			name: network.name,
			status: network.status,
			subnets: network.subnet_details.map((subnet) => subnet.id),
			is_external: network.is_external,
			is_shared: network.is_shared,
		})),
	);
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

	async function createNetwork(body: Record<string, unknown>): Promise<boolean> {
		creatingNetwork = true;
		createNetworkError = '';
		try {
			await api.post('/api/v1/networks', body, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchTopology({ refresh: true });
			return true;
		} catch (e) {
			createNetworkError = e instanceof ApiError ? e.message : '네트워크 생성 실패';
			return false;
		} finally {
			creatingNetwork = false;
		}
	}

	async function createRouter(form: { name: string; external_network_id: string }): Promise<string | true> {
		try {
			const body: Record<string, string> = { name: form.name };
			if (form.external_network_id) body.external_network_id = form.external_network_id;
			await api.post('/api/v1/routers', body, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchTopology({ refresh: true });
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : '라우터 생성 실패';
		}
	}

	async function createCable(request: TopologyLinkRequest) {
		try {
			await api.post(request.url, request.body, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchTopology({ refresh: true });
			toast.success(`${request.label}을 완료했습니다.`);
		} catch (e) {
			toast.error(`${request.label} 실패: ${e instanceof ApiError ? e.message : String(e)}`);
		}
	}

	function createInstance(networkId: string | null) {
		const network = networkId ? data?.networks.find((candidate) => candidate.id === networkId) : null;
		openWizard({ prefill: network ? { networkId: network.id, networkName: network.name } : undefined });
	}

	function createLoadBalancer() {
		void goto('/dashboard/network/loadbalancers/new');
	}

	function onDatabaseCreated() {
		showDbCreate = false;
		void fetchTopology({ refresh: true });
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
					editable={true}
					{onSelectInstance}
					{onSelectRouter}
					{onSelectLoadBalancer}
					{onSelectNetwork}
					onCreateCable={createCable}
					onCreateNetwork={() => { showNetworkCreate = true; }}
					onCreateRouter={() => { showRouterCreate = true; }}
					onCreateInstance={createInstance}
					onCreateLoadBalancer={createLoadBalancer}
					onCreateDatabase={() => { showDbCreate = true; }}
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
		<NetworkDetailPanel
			networkId={selectedNetworkId}
			apiBase="/api/v1/networks"
			onClose={() => selectedNetworkId = null}
			token={$auth.token ?? undefined}
			projectId={$auth.projectId ?? undefined}
		/>
	</SlidePanel>
{/if}

<NetworkCreateModal bind:open={showNetworkCreate} creating={creatingNetwork} error={createNetworkError} onCreate={createNetwork} />
<RouterCreateModal bind:open={showRouterCreate} {externalNetworks} onCreate={createRouter} />

<DbCreatePanel bind:open={showDbCreate} onCreated={onDatabaseCreated} />
