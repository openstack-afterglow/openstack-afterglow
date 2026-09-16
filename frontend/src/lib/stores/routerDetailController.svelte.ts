import { getContext, setContext } from 'svelte';
import { untrack } from 'svelte';
import { goto } from '$app/navigation';
import { api, ApiError } from '$lib/api/client';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { toast } from '$lib/stores/toast';
import type { RouterDetail } from '$lib/types/router';
import type { SubnetDetail } from '$lib/types/networks';
import type { Network } from '$lib/types/networks';

interface Options {
	routerId: () => string;
	token: () => string | undefined;
	projectId: () => string | undefined;
	isSystemAdmin?: () => boolean;
	onDeleted?: () => void;
	onClose?: () => void;
}

function createRouterDetailController(opts: Options) {
	let router = $state<RouterDetail | null>(null);
	let loading = $state(true);
	let error = $state('');
	let saving = $state(false);

	let availableNetworks = $state<Network[]>([]);
	let externalNetworks = $state<Network[]>([]);
	let allSubnets = $state<SubnetDetail[]>([]);

	let showAddInterface = $state(false);
	let selectedNetId = $state('');
	let selectedSubnetId = $state('');
	let showSetGateway = $state(false);
	let selectedExtNetId = $state('');
	const canManageRouter = $derived(
		!!router && (opts.isSystemAdmin?.() || Boolean(router.project_id && router.project_id === opts.projectId()))
	);
	const canAddInterface = $derived(canManageRouter && !!selectedSubnetId && !saving);

	$effect(() => {
		const netId = selectedNetId;
		if (!netId) {
			allSubnets = [];
			selectedSubnetId = '';
			return;
		}
		const tok = untrack(() => opts.token());
		const proj = untrack(() => opts.projectId());
		api.get<{ subnet_details: SubnetDetail[] }>(`/api/v1/networks/${netId}`, tok, proj)
			.then(d => {
				allSubnets = d.subnet_details ?? [];
				selectedSubnetId = allSubnets[0]?.id ?? '';
			})
			.catch(() => {});
	});

	async function fetchRouter() {
		loading = true;
		error = '';
		try {
			router = await api.get<RouterDetail>(`/api/v1/routers/${opts.routerId()}`, opts.token(), opts.projectId());
		} catch (e) {
			error = e instanceof ApiError ? e.message : '라우터 조회 실패';
		} finally {
			loading = false;
		}
	}

	async function fetchNetworks() {
		try {
			const nets = await api.get<Network[]>('/api/v1/networks', opts.token(), opts.projectId());
			availableNetworks = nets.filter((network) => !network.is_external && (opts.isSystemAdmin?.() || network.project_id === opts.projectId()));
			externalNetworks = nets.filter(n => n.is_external);
		} catch { /* 무시 */ }
	}

	async function addInterface() {
		if (!canManageRouter || !selectedSubnetId) return;
		const subnet = allSubnets.find((item) => item.id === selectedSubnetId);
		saving = true;
		try {
			await api.post(`/api/v1/routers/${opts.routerId()}/interfaces`, { subnet_id: selectedSubnetId, auto_gateway: !subnet?.gateway_ip }, opts.token(), opts.projectId());
			showAddInterface = false;
			selectedNetId = '';
			selectedSubnetId = '';
			await fetchRouter();
		} catch (e) {
			toast.error('인터페이스 추가 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			saving = false;
		}
	}

	async function removeInterface(subnetId: string) {
		if (!canManageRouter) return;
		if (!(await confirmDialog('인터페이스를 제거하시겠습니까?'))) return;
		saving = true;
		try {
			await api.delete(`/api/v1/routers/${opts.routerId()}/interfaces/${subnetId}`, opts.token(), opts.projectId());
			await fetchRouter();
		} catch (e) {
			toast.error('인터페이스 제거 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			saving = false;
		}
	}

	async function setGateway() {
		if (!canManageRouter || !selectedExtNetId) return;
		saving = true;
		try {
			await api.post(`/api/v1/routers/${opts.routerId()}/gateway`, { external_network_id: selectedExtNetId }, opts.token(), opts.projectId());
			showSetGateway = false;
			selectedExtNetId = '';
			await fetchRouter();
		} catch (e) {
			toast.error('게이트웨이 설정 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			saving = false;
		}
	}

	async function removeGateway() {
		if (!canManageRouter) return;
		if (!(await confirmDialog('외부 게이트웨이를 제거하시겠습니까?'))) return;
		saving = true;
		try {
			await api.delete(`/api/v1/routers/${opts.routerId()}/gateway`, opts.token(), opts.projectId());
			await fetchRouter();
		} catch (e) {
			toast.error('게이트웨이 제거 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			saving = false;
		}
	}

	async function deleteRouter() {
		if (!canManageRouter) return;
		if (!(await confirmDialog(`라우터 "${router?.name || opts.routerId()}"을 삭제하시겠습니까?`))) return;
		saving = true;
		try {
			await api.delete(`/api/v1/routers/${opts.routerId()}`, opts.token(), opts.projectId());
			if (opts.onDeleted) {
				opts.onDeleted();
			} else {
				opts.onClose?.();
				goto('/dashboard/network/routers');
			}
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
			saving = false;
		}
	}

	return {
		get router() { return router; },
		get loading() { return loading; },
		get error() { return error; },
		get saving() { return saving; },
		get availableNetworks() { return availableNetworks; },
		get externalNetworks() { return externalNetworks; },
		get allSubnets() { return allSubnets; },
		get showAddInterface() { return showAddInterface; },
		set showAddInterface(v: boolean) { showAddInterface = v; },
		get selectedNetId() { return selectedNetId; },
		set selectedNetId(v: string) { selectedNetId = v; },
		get selectedSubnetId() { return selectedSubnetId; },
		set selectedSubnetId(v: string) { selectedSubnetId = v; },
		get showSetGateway() { return showSetGateway; },
		set showSetGateway(v: boolean) { showSetGateway = v; },
		get selectedExtNetId() { return selectedExtNetId; },
		set selectedExtNetId(v: string) { selectedExtNetId = v; },
		get canAddInterface() { return canAddInterface; },
		get canManageRouter() { return canManageRouter; },
		fetchRouter,
		fetchNetworks,
		addInterface,
		removeInterface,
		setGateway,
		removeGateway,
		deleteRouter,
	};
}

export type RouterDetailController = ReturnType<typeof createRouterDetailController>;
export { createRouterDetailController };

const ROUTER_DETAIL_KEY = Symbol('router-detail');

export function provideRouterDetailController(store: RouterDetailController) {
	setContext(ROUTER_DETAIL_KEY, store);
}

export function useRouterDetailController(): RouterDetailController {
	const store = getContext<RouterDetailController | undefined>(ROUTER_DETAIL_KEY);
	if (!store) throw new Error('useRouterDetailController must be called within RouterDetailPanel');
	return store;
}
