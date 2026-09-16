import { getContext, setContext } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import type { NetworkDetail, NetworkRouterInfo, RouterListItem } from '$lib/types/networks';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { toast } from '$lib/stores/toast';

interface Options {
	networkId: () => string;
	apiBase: () => string;
	token: () => string | undefined;
	projectId: () => string | undefined;
	onClose?: () => void;
}

function createNetworkDetailController(opts: Options) {
	let network = $state<NetworkDetail | null>(null);
	let loading = $state(true);
	let error = $state('');

	let allRouters = $state<RouterListItem[]>([]);
	let showRouterConnect = $state(false);
	let selectedRouterId = $state('');
	let selectedSubnetId = $state('');
	let connectingRouter = $state(false);
	let showSubnetForm = $state(false);
	let addingSubnet = $state(false);
	let subnetError = $state('');

	const isUserPanel = $derived(opts.apiBase() === '/api/v1/networks');
	const canManageNetwork = $derived(
		isUserPanel && !!network && network.project_id === opts.projectId() && !network.is_external,
	);
	const managedRouters = $derived(allRouters.filter((router) => router.project_id === opts.projectId()));


	$effect(() => {
		const id = opts.networkId();
		if (!id) return;
		loading = true;
		error = '';
		network = null;
		showRouterConnect = false;
		showSubnetForm = false;
		subnetError = '';
		fetchNetwork();
	});

	async function fetchNetwork() {
		try {
			network = await api.get<NetworkDetail>(`${opts.apiBase()}/${opts.networkId()}`, opts.token(), opts.projectId());
		} catch (e) {
			error = e instanceof ApiError ? e.message : '네트워크 조회 실패';
		} finally {
			loading = false;
		}
	}
	async function toggleSubnetForm() {
		if (!canManageNetwork) return;
		if (!showSubnetForm && !allRouters.length) {
			try {
				allRouters = await api.get<RouterListItem[]>('/api/v1/routers', opts.token(), opts.projectId());
			} catch {
				allRouters = [];
			}
		}
		showSubnetForm = !showSubnetForm;
	}


	async function openRouterConnect() {
		if (!canManageNetwork) return;
		if (!allRouters.length) {
			try {
				allRouters = await api.get<RouterListItem[]>('/api/v1/routers', opts.token(), opts.projectId());
			} catch {
				allRouters = [];
			}
		}
		selectedRouterId = managedRouters[0]?.id ?? '';
		selectedSubnetId = network?.subnet_details[0]?.id ?? '';
		showRouterConnect = true;
	}

	async function connectRouter() {
		if (!canManageNetwork || !selectedRouterId || !selectedSubnetId || !managedRouters.some((router) => router.id === selectedRouterId)) return;
		connectingRouter = true;
		try {
			const subnet = network?.subnet_details.find(s => s.id === selectedSubnetId);
			const autoGateway = !subnet?.gateway_ip;
			await api.post(
				`/api/v1/routers/${selectedRouterId}/interfaces`,
				{ subnet_id: selectedSubnetId, auto_gateway: autoGateway },
				opts.token(),
				opts.projectId()
			);
			showRouterConnect = false;
			await fetchNetwork();
		} catch (e) {
			toast.error('라우터 연결 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			connectingRouter = false;
		}
	}

	async function addSubnet(form: { name?: string; cidr: string; gateway: string; dhcp: boolean; routerId?: string }): Promise<boolean> {
		if (!canManageNetwork || !network) return false;
		addingSubnet = true;
		subnetError = '';
		try {
			const subnet = await api.post<{ id: string; gateway_ip: string | null }>(
				`${opts.apiBase()}/${network.id}/subnets`,
				{
					name: form.name?.trim() || `${network.name}-subnet`,
					cidr: form.cidr,
					gateway_ip: form.gateway || null,
					enable_dhcp: form.dhcp,
				},
				opts.token(),
				opts.projectId(),
			);
			showSubnetForm = false;
			if (form.routerId && managedRouters.some((router) => router.id === form.routerId)) {
				try {
					await api.post(
						`/api/v1/routers/${form.routerId}/interfaces`,
						{ subnet_id: subnet.id, auto_gateway: !subnet.gateway_ip },
						opts.token(),
						opts.projectId(),
					);
					toast.success('서브넷을 생성하고 라우터에 연결했습니다.');
				} catch (e) {
					toast.error('서브넷은 생성됐지만 라우터 연결에 실패했습니다: ' + (e instanceof ApiError ? e.message : String(e)));
				}
			}
			await fetchNetwork();
			return true;
		} catch (e) {
			subnetError = e instanceof ApiError ? e.message : '서브넷 생성 실패';
			return false;
		} finally {
			addingSubnet = false;
		}
	}

	async function disconnectRouter(router: NetworkRouterInfo) {
		if (!canManageNetwork || router.project_id !== opts.projectId()) return;
		const subnetIds = network?.subnet_details.map(s => s.id) ?? [];
		const targetSubnet = router.connected_subnet_ids.find(sid => subnetIds.includes(sid));
		if (!targetSubnet) {
			toast.warning('연결된 서브넷을 찾을 수 없습니다.');
			return;
		}
		if (!(await confirmDialog(`라우터 "${router.name || router.id.slice(0, 8)}"과의 연결을 해제하시겠습니까?`, { confirmLabel: '연결 해제' }))) return;
		try {
			await api.delete(`/api/v1/routers/${router.id}/interfaces/${targetSubnet}`, opts.token(), opts.projectId());
			await fetchNetwork();
		} catch (e) {
			toast.error('라우터 연결 해제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		}
	}

	return {
		get network() { return network; },
		get loading() { return loading; },
		get error() { return error; },
		get isUserPanel() { return isUserPanel; },
		get canManageNetwork() { return canManageNetwork; },
		get managedRouters() { return managedRouters; },
		get allRouters() { return allRouters; },
		get showRouterConnect() { return showRouterConnect; },
		toggleSubnetForm,
		set showRouterConnect(v: boolean) { showRouterConnect = v; },
		get selectedRouterId() { return selectedRouterId; },
		set selectedRouterId(v: string) { selectedRouterId = v; },
		get selectedSubnetId() { return selectedSubnetId; },
		set selectedSubnetId(v: string) { selectedSubnetId = v; },
		get connectingRouter() { return connectingRouter; },
		get showSubnetForm() { return showSubnetForm; },
		set showSubnetForm(v: boolean) { showSubnetForm = v; },
		get addingSubnet() { return addingSubnet; },
		get subnetError() { return subnetError; },
		addSubnet,
		fetchNetwork,
		openRouterConnect,
		connectRouter,
		disconnectRouter,
	};
}

export type NetworkDetailController = ReturnType<typeof createNetworkDetailController>;
export { createNetworkDetailController };

const NETWORK_DETAIL_KEY = Symbol('network-detail');

export function provideNetworkDetailController(store: NetworkDetailController) {
	setContext(NETWORK_DETAIL_KEY, store);
}

export function useNetworkDetailController(): NetworkDetailController {
	const store = getContext<NetworkDetailController | undefined>(NETWORK_DETAIL_KEY);
	if (!store) throw new Error('useNetworkDetailController must be called within NetworkDetailPanel');
	return store;
}
