import { getContext, setContext, untrack } from 'svelte';
import { api, ApiError } from '$lib/api/client';
import type { NetworkDetail, NetworkRouterInfo, RouterListItem } from '$lib/types/networks';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { toast } from '$lib/stores/toast';
import { t } from '$lib/i18n/ns/network-resources';
import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceState, type ExperienceContext } from '$lib/utils/experience';

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

	async function fetchNetwork(force = false, experience: ExperienceContext | undefined = beginExperienceLoad('network', 'resource.detail')) {
		if (untrack(() => loading)) experienceState(experience, 'loading');
		try {
			network = await api.withExperience(experience).get<NetworkDetail>(`${opts.apiBase()}/${opts.networkId()}`, opts.token(), opts.projectId(), { refresh: force });
			if (experience?.action !== 'create') experienceState(experience, network ? 'ready' : 'empty');
			if (experience) void experienceApplied(experience);
		} catch (e) {
			error = e instanceof ApiError ? e.message : t('network.errors.load');
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		} finally {
			loading = false;
		}
	}
	async function toggleSubnetForm() {
		if (!canManageNetwork) return;
		const experience = beginExperienceAction('network', showSubnetForm ? 'close' : 'open', 'resource.detail');
		if (!showSubnetForm && !allRouters.length) {
			try {
				allRouters = await api.withExperience(experience).get<RouterListItem[]>('/api/v1/routers', opts.token(), opts.projectId());
			} catch {
				allRouters = [];
			}
		}
		showSubnetForm = !showSubnetForm;
		if (experience) void experienceApplied(experience);
	}


	async function openRouterConnect() {
		if (!canManageNetwork) return;
		const experience = beginExperienceAction('network', 'open', 'resource.detail');
		if (!allRouters.length) {
			try {
				allRouters = await api.withExperience(experience).get<RouterListItem[]>('/api/v1/routers', opts.token(), opts.projectId());
			} catch {
				allRouters = [];
			}
		}
		selectedRouterId = managedRouters[0]?.id ?? '';
		selectedSubnetId = network?.subnet_details[0]?.id ?? '';
		showRouterConnect = true;
		if (experience) void experienceApplied(experience);
	}

	async function connectRouter() {
		if (!canManageNetwork || !selectedRouterId || !selectedSubnetId || !managedRouters.some((router) => router.id === selectedRouterId)) return;
		connectingRouter = true;
		const experience = beginExperienceAction('network', 'attach', 'resource.detail');
		try {
			const subnet = network?.subnet_details.find(s => s.id === selectedSubnetId);
			const autoGateway = !subnet?.gateway_ip;
			await api.withExperience(experience).post(
				`/api/v1/routers/${selectedRouterId}/interfaces`,
				{ subnet_id: selectedSubnetId, auto_gateway: autoGateway },
				opts.token(),
				opts.projectId()
			);
			showRouterConnect = false;
			await fetchNetwork(false, experience);
		} catch (e) {
			toast.error(t('network.errors.connectRouter', { error: e instanceof ApiError ? e.message : String(e) }));
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		} finally {
			connectingRouter = false;
		}
	}

	async function addSubnet(form: { name?: string; cidr: string; gateway: string; dhcp: boolean; routerId?: string }): Promise<boolean> {
		if (!canManageNetwork || !network) return false;
		addingSubnet = true;
		subnetError = '';
		const experience = beginExperienceAction('network', 'create', 'resource.detail');
		try {
			const subnet = await api.withExperience(experience).post<{ id: string; gateway_ip: string | null }>(
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
					await api.withExperience(experience).post(
						`/api/v1/routers/${form.routerId}/interfaces`,
						{ subnet_id: subnet.id, auto_gateway: !subnet.gateway_ip },
						opts.token(),
						opts.projectId(),
					);
					toast.success(t('network.toast.subnetCreatedConnected'));
				} catch (e) {
					toast.error(t('network.errors.subnetCreatedConnectFailed', { error: e instanceof ApiError ? e.message : String(e) }));
					experienceState(experience, 'error');
					if (experience) void experienceApplied(experience);
				}
			}
			await fetchNetwork(false, experience);
			return true;
		} catch (e) {
			subnetError = e instanceof ApiError ? e.message : t('network.errors.createSubnet');
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
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
			toast.warning(t('network.errors.connectedSubnetMissing'));
			return;
		}
		if (!(await confirmDialog(t('network.routers.disconnectConfirm', { name: router.name || router.id.slice(0, 8) }), { confirmLabel: t('network.routers.disconnectLabel') }))) return;
		const experience = beginExperienceAction('network', 'detach', 'resource.detail');
		try {
			await api.withExperience(experience).delete(`/api/v1/routers/${router.id}/interfaces/${targetSubnet}`, opts.token(), opts.projectId());
			await fetchNetwork(false, experience);
		} catch (e) {
			toast.error(t('network.errors.disconnectRouter', { error: e instanceof ApiError ? e.message : String(e) }));
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
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
