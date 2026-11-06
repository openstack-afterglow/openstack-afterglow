import { t } from '$lib/i18n/ns/network-resources';
import { getContext, setContext } from 'svelte';
import { untrack } from 'svelte';
import { goto } from '$app/navigation';
import { api, ApiError } from '$lib/api/client';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { toast } from '$lib/stores/toast';
import type { RouterDetail } from '$lib/types/router';
import type { SubnetDetail } from '$lib/types/networks';
import type { Network } from '$lib/types/networks';
import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceState, type ExperienceContext } from '$lib/utils/experience';
import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';

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
	const interfaceColumns = (): TableColumn<RouterDetail['interfaces'][number]>[] => [
		{ key: 'subnet', label: t('network.subnets.name'), value: row => row.subnet_name || row.subnet_id },
		{ key: 'address', label: t('lb.form.ipAddress'), value: row => row.ip_address },
	];
	const interfaceView = createTableView({ rows: () => router?.interfaces ?? [], columns: interfaceColumns });
	const viewOwner = $derived(JSON.stringify([opts.routerId(), opts.projectId()]));
	$effect(() => { viewOwner; untrack(() => interfaceView.reset()); });

	$effect(() => {
		const netId = selectedNetId;
		if (!netId) {
			allSubnets = [];
			selectedSubnetId = '';
			return;
		}
		const tok = untrack(() => opts.token());
		const proj = untrack(() => opts.projectId());
		const experience = beginExperienceLoad('network', 'resource.detail');
		api.withExperience(experience).get<{ subnet_details: SubnetDetail[] }>(`/api/v1/networks/${netId}`, tok, proj)
			.then(d => {
				allSubnets = d.subnet_details ?? [];
				selectedSubnetId = allSubnets[0]?.id ?? '';
				if (experience) void experienceApplied(experience);
			})
			.catch(() => {});
	});

	async function fetchRouter(force = false, experience: ExperienceContext | undefined = beginExperienceLoad('network', 'resource.detail')) {
		loading = true;
		error = '';
		experienceState(experience, 'loading');
		try {
			router = await api.withExperience(experience).get<RouterDetail>(`/api/v1/routers/${opts.routerId()}`, opts.token(), opts.projectId(), { refresh: force });
			if (experience?.action !== 'create') experienceState(experience, router ? 'ready' : 'empty');
			if (experience) void experienceApplied(experience);
		} catch (e) {
			error = e instanceof ApiError ? e.message : t('router.error.load');
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		} finally {
			loading = false;
		}
	}

	async function fetchNetworks() {
		const experience = beginExperienceLoad('network', 'resource.detail');
		try {
			const nets = await api.withExperience(experience).get<Network[]>('/api/v1/networks', opts.token(), opts.projectId());
			availableNetworks = nets.filter((network) => !network.is_external && (opts.isSystemAdmin?.() || network.project_id === opts.projectId()));
			externalNetworks = nets.filter(n => n.is_external);
			experienceState(experience, nets.length ? 'ready' : 'empty');
			if (experience) void experienceApplied(experience);
		} catch { /* 무시 */ }
	}

	async function addInterface() {
		if (!canManageRouter || !selectedSubnetId) return;
		const subnet = allSubnets.find((item) => item.id === selectedSubnetId);
		saving = true;
		const experience = beginExperienceAction('network', 'attach', 'resource.detail');
		try {
			await api.withExperience(experience).post(`/api/v1/routers/${opts.routerId()}/interfaces`, { subnet_id: selectedSubnetId, auto_gateway: !subnet?.gateway_ip }, opts.token(), opts.projectId());
			showAddInterface = false;
			selectedNetId = '';
			selectedSubnetId = '';
			await fetchRouter(false, experience);
		} catch (e) {
			toast.error(t('router.error.addInterface', { error: e instanceof ApiError ? e.message : String(e) }));
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		} finally {
			saving = false;
		}
	}

	async function removeInterface(subnetId: string) {
		if (!canManageRouter) return;
		if (!(await confirmDialog(t('router.confirm.removeInterface')))) return;
		saving = true;
		const experience = beginExperienceAction('network', 'detach', 'resource.detail');
		try {
			await api.withExperience(experience).delete(`/api/v1/routers/${opts.routerId()}/interfaces/${subnetId}`, opts.token(), opts.projectId());
			await fetchRouter(false, experience);
		} catch (e) {
			toast.error(t('router.error.removeInterface', { error: e instanceof ApiError ? e.message : String(e) }));
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		} finally {
			saving = false;
		}
	}

	async function setGateway() {
		if (!canManageRouter || !selectedExtNetId) return;
		saving = true;
		const experience = beginExperienceAction('network', 'attach', 'resource.detail');
		try {
			await api.withExperience(experience).post(`/api/v1/routers/${opts.routerId()}/gateway`, { external_network_id: selectedExtNetId }, opts.token(), opts.projectId());
			showSetGateway = false;
			selectedExtNetId = '';
			await fetchRouter(false, experience);
		} catch (e) {
			toast.error(t('router.error.setGateway', { error: e instanceof ApiError ? e.message : String(e) }));
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		} finally {
			saving = false;
		}
	}

	async function removeGateway() {
		if (!canManageRouter) return;
		if (!(await confirmDialog(t('router.confirm.removeGateway')))) return;
		saving = true;
		const experience = beginExperienceAction('network', 'detach', 'resource.detail');
		try {
			await api.withExperience(experience).delete(`/api/v1/routers/${opts.routerId()}/gateway`, opts.token(), opts.projectId());
			await fetchRouter(false, experience);
		} catch (e) {
			toast.error(t('router.error.removeGateway', { error: e instanceof ApiError ? e.message : String(e) }));
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
		} finally {
			saving = false;
		}
	}

	async function deleteRouter() {
		if (!canManageRouter) return;
		if (!(await confirmDialog(t('router.confirm.delete', { name: router?.name || opts.routerId() })))) return;
		saving = true;
		const experience = beginExperienceAction('network', 'delete', 'resource.detail');
		try {
			await api.withExperience(experience).delete(`/api/v1/routers/${opts.routerId()}`, opts.token(), opts.projectId());
			if (opts.onDeleted) {
				opts.onDeleted();
			} else {
				opts.onClose?.();
				goto('/dashboard/network/routers');
			}
		} catch (e) {
			toast.error(t('router.error.delete', { error: e instanceof ApiError ? e.message : String(e) }));
			experienceState(experience, 'error');
			if (experience) void experienceApplied(experience);
			saving = false;
		}
	}

	return {
		interfaceView,
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
