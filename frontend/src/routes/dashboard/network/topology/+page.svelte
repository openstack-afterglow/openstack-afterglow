<script lang="ts">
	import { t } from '$lib/i18n/ns/topology';
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
	import { openWizard, wizardOpen } from '$lib/stores/wizard';
	import { toast } from '$lib/stores/toast';
	import TopologyLinkModal, { type LinkConfirmPayload } from '$lib/components/dashboard/network/topology/TopologyLinkModal.svelte';
	import { attachableSubnets, type LinkRequest } from '$lib/components/topology/canvas/topologyLink';
	import type { CreateKind } from '$lib/components/topology/canvas/CanvasToolbar.svelte';
	import { type TopologyLinkRequest } from '$lib/components/topology/canvas/link-types';
	import type { SubnetDetail, TopologyNetwork } from '$lib/types/topology';
	import { DEFAULT_TOPOLOGY_VIEW, isTopologyView, readTopologyView, writeTopologyView, type TopologyView } from '$lib/utils/topologyViewPreference';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import TopologyLegend from '$lib/components/dashboard/network/topology/TopologyLegend.svelte';
	import TopologySummary from '$lib/components/dashboard/network/topology/TopologySummary.svelte';
	import LoadBalancerDetailPanel from '$lib/components/dashboard/network/topology/LoadBalancerDetailPanel.svelte';
	import type { TopologyData, TopologyTraffic, TopologyLoadBalancer } from '$lib/types/topology';
	import type { Network } from '$lib/types/networks';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';

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
	let pendingLink = $state<LinkRequest | null>(null);
	let activeLinkModal = $state<{
		req: LinkRequest;
		net: TopologyNetwork;
		subnets: SubnetDetail[];
		createdSubnet?: SubnetDetail | null;
	} | null>(null);
	let linkSubmitting = $state(false);
	let linkError = $state('');
	let createCtx = $state<{ networkId: string | null; networkName: string | null }>({ networkId: null, networkName: null });
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
	const viewOptions = $derived([
		{ value: 'lane', label: t('topology.lane') },
		{ value: 'canvas', label: t('topology.canvas') },
	]);
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
			createNetworkError = e instanceof ApiError ? e.message : t('topology.createNetworkFailed');
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
			return e instanceof ApiError ? e.message : t('topology.createRouterFailed');
		}
	}

	function onConnect(req: LinkRequest) {
		const net = data?.networks.find((n) => n.id === req.networkId);
		if (!net) return;
		linkError = '';
		pendingLink = req;
		if (req.kind === 'router-net') {
			const router = data?.routers.find((r) => r.id === req.routerId);
			const subnets = router ? attachableSubnets(net, router) : [];
			activeLinkModal = { req, net, subnets };
		} else {
			activeLinkModal = { req, net, subnets: [] };
		}
	}

	async function handleLinkConfirm(payload: LinkConfirmPayload): Promise<boolean> {
		if (!activeLinkModal) return false;
		const { req, net } = activeLinkModal;
		linkSubmitting = true;
		linkError = '';
		try {
			if (req.kind === 'vm-net') {
				await api.post(
					`/api/v1/instances/${encodeURIComponent(req.instanceId)}/interfaces`,
					{ net_id: req.networkId },
					$auth.token ?? undefined,
					$auth.projectId ?? undefined
				);
				toast.success(t('topology.interfaceAdded', { instance: req.instanceName, network: net.name }));
			} else if (req.kind === 'router-gateway') {
				await api.post(
					`/api/v1/routers/${encodeURIComponent(req.routerId)}/gateway`,
					{ external_network_id: req.networkId },
					$auth.token ?? undefined,
					$auth.projectId ?? undefined
				);
				toast.success(t('topology.gatewaySet', { router: req.routerName, network: net.name }));
			} else if (req.kind === 'router-net') {
				let subnetId: string;
				if (activeLinkModal.createdSubnet) {
					subnetId = activeLinkModal.createdSubnet.id;
				} else if (payload.kind === 'router-net' && 'create' in payload) {
					const s = await api.post<SubnetDetail>(
						`/api/v1/networks/${encodeURIComponent(req.networkId)}/subnets`,
						{
							name: payload.create.name,
							cidr: payload.create.cidr,
							gateway_ip: null,
							enable_dhcp: payload.create.dhcp
						},
						$auth.token ?? undefined,
						$auth.projectId ?? undefined
					);
					subnetId = s.id;
					activeLinkModal.createdSubnet = s;
					if (!activeLinkModal.subnets.some((sub) => sub.id === s.id)) {
						activeLinkModal.subnets = [s, ...activeLinkModal.subnets];
					}
					if (!net.subnet_details.some((sub) => sub.id === s.id)) {
						net.subnet_details.push(s);
					}
				} else if (payload.kind === 'router-net' && 'subnetId' in payload) {
					subnetId = payload.subnetId;
				} else {
					return false;
				}

				try {
					await api.post(
						`/api/v1/routers/${encodeURIComponent(req.routerId)}/interfaces`,
						{ subnet_id: subnetId, auto_gateway: true },
						$auth.token ?? undefined,
						$auth.projectId ?? undefined
					);
					toast.success(t('topology.routerConnected', { router: req.routerName, network: net.name }));
				} catch (routerErr) {
					const msg = routerErr instanceof ApiError ? routerErr.message : t('topology.routerConnectionFailed');
					linkError = t('topology.partialConnectionFailed', { message: msg });
					toast.warning(linkError);
					return false;
				}
			}
			activeLinkModal = null;
			pendingLink = null;
			await fetchTopology({ refresh: true });
			return true;
		} catch (e) {
			linkError = e instanceof ApiError ? e.message : t('topology.connectionFailed');
			toast.error(t('topology.connectionError', { message: linkError }));
			return false;
		} finally {
			linkSubmitting = false;
		}
	}

	function handleLinkModalClose() {
		activeLinkModal = null;
		pendingLink = null;
		linkError = '';
	}

	function handleCreate(kind: CreateKind, ctx: { networkId: string | null; networkName: string | null }) {
		createCtx = ctx;
		if (kind === 'network') showNetworkCreate = true;
		else if (kind === 'router') showRouterCreate = true;
		else if (kind === 'instance') createInstance(ctx.networkId);
		else if (kind === 'loadbalancer') createLoadBalancer(ctx.networkId);
		else showDbCreate = true;
	}

	async function createCable(request: TopologyLinkRequest) {
		try {
			await api.post(request.url, request.body, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchTopology({ refresh: true });
			toast.success(t('topology.cableCompleted', { label: request.label }));
		} catch (e) {
			toast.error(t('topology.cableFailed', { label: request.label, message: e instanceof ApiError ? e.message : String(e) }));
		}
	}

	function createInstance(networkId: string | null) {
		const network = networkId ? data?.networks.find((candidate) => candidate.id === networkId) : null;
		openWizard({ prefill: network ? { networkId: network.id, networkName: network.name } : undefined });
	}

	function createLoadBalancer(networkId?: string | null) {
		const targetId = networkId ?? createCtx.networkId;
		void goto(`/dashboard/network/loadbalancers/new${targetId ? `?network=${encodeURIComponent(targetId)}` : ''}`);
	}

	let wasWizardOpen = false;
	$effect(() => {
		const open = $wizardOpen;
		if (wasWizardOpen && !open) {
			untrack(() => fetchTopology({ refresh: true }));
		}
		wasWizardOpen = open;
	});
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
		if (!data) error = '';
		try {
			const nextData = await api.get<TopologyData>(
				'/api/v1/networks/topology',
				$auth.token ?? undefined,
				$auth.projectId ?? undefined,
				opts,
			);
			data = {
				...nextData,
				networks: [...nextData.networks],
				routers: [...nextData.routers],
				instances: [...nextData.instances],
			};
			error = '';
		} catch (e) {
			error = e instanceof ApiError ? t('topology.loadFailed', { status: e.status, message: e.message }) : t('topology.serverError');
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
	<PageHeader breadcrumb={t('topology.breadcrumb')} title={t('topology.title')}>
		{#snippet actions()}
			<ToggleGroup value={view} options={viewOptions} onchange={onViewChange} ariaLabel={t('topology.viewLabel')} />
			<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={refreshing || loading}
			onManualRefresh={forceRefresh}
		/>
		{/snippet}
	</PageHeader>

	<!--
		갱신 실패는 이미 그려진 토폴로지를 내리지 않는다. 내렸다가 다음 갱신에서 다시 마운트하면
		자동 갱신이 진입 모션을 재생한다. 로딩 스켈레톤은 첫 조회(data 없음)에만 보인다.
	-->
	{#if error}
		{#if data}
			<div role="status" class="mb-4 rounded-lg border border-state-danger/30 bg-state-danger/10 px-4 py-3 text-sm text-state-danger">{error}</div>
		{:else}
			<Alert tone="danger" class="mb-4">{error}</Alert>
		{/if}
	{/if}
	{#if loading}
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
					{pendingLink}
					{onConnect}
					onCreate={handleCreate}
					{onSelectInstance}
					{onSelectRouter}
					{onSelectLoadBalancer}
					{onSelectNetwork}
					onCreateCable={createCable}
					onCreateNetwork={() => { showNetworkCreate = true; }}
					onCreateRouter={() => { showRouterCreate = true; }}
					onCreateInstance={createInstance}
					onCreateLoadBalancer={() => createLoadBalancer()}
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
	<SlidePanel onClose={() => selectedInstanceId = null} ariaLabel={t('topology.instanceDetailLabel')}>
		<InstanceDetailPanel instanceId={selectedInstanceId} onClose={() => selectedInstanceId = null} />
	</SlidePanel>
{/if}

{#if selectedRouterId}
	<SlidePanel onClose={() => selectedRouterId = null} ariaLabel={t('topology.routerDetailLabel')} width="w-full md:w-[60vw] max-w-3xl">
		<RouterDetailPanel routerId={selectedRouterId} onClose={() => selectedRouterId = null} />
	</SlidePanel>
{/if}

{#if selectedLB}
	<SlidePanel onClose={() => selectedLB = null} ariaLabel={t('topology.loadBalancerDetailLabel')} width="w-full md:w-[60vw] max-w-2xl">
		<LoadBalancerDetailPanel lb={selectedLB} onClose={() => selectedLB = null} />
	</SlidePanel>
{/if}

{#if selectedNetworkId && data}
	<SlidePanel onClose={() => selectedNetworkId = null} ariaLabel={t('topology.networkDetailLabel')} width="w-full md:w-[60vw] max-w-2xl">
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

<DbCreatePanel
	bind:open={showDbCreate}
	onCreated={onDatabaseCreated}
	initialNetworkId={createCtx.networkId && data?.networks.find((n) => n.id === createCtx.networkId && !n.is_external && !n.is_shared) ? createCtx.networkId : null}
/>

{#if activeLinkModal}
	<TopologyLinkModal
		open={true}
		request={activeLinkModal.req}
		network={activeLinkModal.net}
		subnets={activeLinkModal.subnets}
		createdSubnet={activeLinkModal.createdSubnet ?? null}
		submitting={linkSubmitting}
		error={linkError}
		onConfirm={handleLinkConfirm}
		onClose={handleLinkModalClose}
	/>
{/if}
