import { setContext, getContext } from 'svelte';
import { get } from 'svelte/store';
import { auth } from '$lib/stores/auth';
import { api, ApiError } from '$lib/api/client';
import { apiMut } from '$lib/api/mutations';
import type { FileStorage } from '$lib/types/fileStorage';

export type WizardStep = 1 | 2 | 3;

export interface MetaEntry { key: string; value: string; }
export interface ShareNetwork { id: string; name: string; neutron_net_id: string | null; status: string; }
export interface NeutronNetwork { id: string; name: string; status: string; subnets: string[]; }
export interface Subnet { id: string; name: string; cidr: string; }
export interface AccessRule {
	id: string; access_type: string; access_to: string;
	access_level: string; access_key: string | null; state: string;
}
export interface ShareTypeMeta {
	id: string; name: string; is_default: boolean;
	extra_specs?: Record<string, string>;
	supported_protocols?: string[];
}

export interface FsWizardOptions {
	open: () => boolean;
	setOpen: (v: boolean) => void;
	onCreated: () => void;
	fileStorageShareNetworksEnabled?: () => boolean;
}

export function createFileStorageWizardStore(opts: FsWizardOptions) {
	let token = $state<string | undefined>(get(auth).token ?? undefined);
	let projectId = $state<string | undefined>(get(auth).projectId ?? undefined);
	$effect(() => {
		return auth.subscribe((v) => {
			token = v.token ?? undefined;
			projectId = v.projectId ?? undefined;
		});
	});

	let step = $state<WizardStep>(1);
	let wizardError = $state('');
	let creating = $state(false);
	let createdFs = $state<FileStorage | null>(null);

	let shareTypes = $state<ShareTypeMeta[]>([]);
	let fsForm = $state({ name: '', size_gb: 10, share_type: '', share_proto: 'CEPHFS' as 'CEPHFS' | 'NFS' });
	let metaEntries = $state<MetaEntry[]>([{ key: '', value: '' }]);

	const currentShareType = $derived(shareTypes.find((t) => t.name === fsForm.share_type));
	// DHSS=True 인 경우에만 share network 단계가 의미 있다.
	// extra_specs.driver_handles_share_servers 가 명시적으로 'true'인 경우만 true.
	// 값이 없거나 조회 전이면 false 로 fallback → 네트워크 단계 숨김 (안전한 방향).
	const dhssEnabled = $derived(
		currentShareType?.extra_specs?.driver_handles_share_servers?.toLowerCase() === 'true',
	);
	const allowedProtos = $derived<('CEPHFS' | 'NFS')[]>(
		currentShareType?.supported_protocols && currentShareType.supported_protocols.length > 0
			? currentShareType.supported_protocols.filter(
					(p): p is 'CEPHFS' | 'NFS' => p === 'CEPHFS' || p === 'NFS',
				)
			: ['CEPHFS', 'NFS'],
	);
	$effect(() => {
		if (allowedProtos.length > 0 && !allowedProtos.includes(fsForm.share_proto)) {
			fsForm.share_proto = allowedProtos[0];
		}
	});

	let shareNetworks = $state<ShareNetwork[]>([]);
	let selectedNetworkId = $state('');
	let showInlineNetCreate = $state(false);
	let neutronNetworks = $state<NeutronNetwork[]>([]);
	let subnets = $state<Subnet[]>([]);
	let loadingSubnets = $state(false);
	let inlineNetForm = $state({ name: '', description: '', neutron_net_id: '', neutron_subnet_id: '' });
	let inlineNetCreating = $state(false);
	let inlineNetError = $state('');

	let accessRules = $state<AccessRule[]>([]);
	let ruleForm = $state({ access_to: '', access_level: 'rw' });
	let addingRule = $state(false);
	let ruleError = $state('');
	let copiedKey = $state<string | null>(null);
	let copiedExport = $state<string | null>(null);


	const shareNetworksOn = () => opts.fileStorageShareNetworksEnabled?.() ?? true;
	function reset() {
		step = 1; wizardError = ''; createdFs = null;
		fsForm = { name: '', size_gb: 10, share_type: '', share_proto: 'CEPHFS' };
		metaEntries = [{ key: '', value: '' }];
		selectedNetworkId = ''; showInlineNetCreate = false;
		inlineNetForm = { name: '', description: '', neutron_net_id: '', neutron_subnet_id: '' };
		accessRules = []; ruleForm = { access_to: '', access_level: 'rw' };
	}

	async function openWizard() {
		opts.setOpen(true);
		reset();
		// Promise.allSettled 로 types/networks 를 독립적으로 로드
		// — networks 실패가 share type 목록을 날리지 않도록
		const loadShareNetworks = shareNetworksOn();
		const [typesResult, networksResult] = await Promise.allSettled([
			api.get<ShareTypeMeta[]>('/api/v1/file-storage/types', token, projectId),
			loadShareNetworks
				? api.get<ShareNetwork[]>('/api/v1/share-networks', token, projectId)
				: Promise.resolve([] as ShareNetwork[]),
		]);
		if (typesResult.status === 'fulfilled') {
			shareTypes = typesResult.value;
			if (shareTypes.length > 0) {
				const def = shareTypes.find((t) => t.is_default) ?? shareTypes[0];
				fsForm.share_type = def.name;
				const protos = def.supported_protocols?.filter(
					(p): p is 'CEPHFS' | 'NFS' => p === 'CEPHFS' || p === 'NFS',
				);
				if (protos && protos.length > 0) fsForm.share_proto = protos[0];
			}
		} else {
			shareTypes = [];
			wizardError = 'Share type 목록을 불러오지 못했습니다. 다시 열거나 직접 입력하세요.';
		}
		shareNetworks = loadShareNetworks && networksResult.status === 'fulfilled' ? networksResult.value : [];
	}

	function closeWizard() {
		opts.setOpen(false);
		if (createdFs) opts.onCreated();
	}

	function addMeta() { metaEntries = [...metaEntries, { key: '', value: '' }]; }
	function removeMeta(i: number) { metaEntries = metaEntries.filter((_, idx) => idx !== i); }

	function goStep2() {
		if (!fsForm.name.trim() || fsForm.size_gb < 1) {
			wizardError = '이름과 크기를 입력하세요.'; return;
		}
		wizardError = '';
		if (!shareNetworksOn() && dhssEnabled && fsForm.share_proto === 'NFS') {
			wizardError = 'Share Network 기능이 베타로 꺼져 있어 이 Share Type/NFS 조합은 사용할 수 없습니다.';
			return;
		}
		// DHSS=False 이거나 CephFS 이면 네트워크 단계 불필요 → 바로 생성
		if (!dhssEnabled || fsForm.share_proto === 'CEPHFS') {
			createFileStorage();
			return;
		}
		if (shareNetworksOn() && dhssEnabled) {
			step = 2;
		}
		if (neutronNetworks.length === 0) {
			api.get<NeutronNetwork[]>('/api/v1/networks', token, projectId)
				.then((r) => (neutronNetworks = r))
				.catch(() => (neutronNetworks = []));
		}
	}

	function backToStep1() { step = 1; wizardError = ''; }

	async function onInlineNetworkChange() {
		inlineNetForm.neutron_subnet_id = ''; subnets = [];
		if (!inlineNetForm.neutron_net_id) return;
		loadingSubnets = true;
		try {
			const detail = await api.get<{ id: string; subnet_details: Subnet[] }>(
				`/api/v1/networks/${inlineNetForm.neutron_net_id}`, token, projectId,
			);
			subnets = detail.subnet_details ?? [];
		} catch { subnets = []; }
		finally { loadingSubnets = false; }
	}

	async function createInlineNetwork() {
		if (!shareNetworksOn()) return;
		if (!inlineNetForm.name.trim() || !inlineNetForm.neutron_net_id || !inlineNetForm.neutron_subnet_id) return;
		inlineNetCreating = true; inlineNetError = '';
		try {
			const net = await api.post<ShareNetwork>('/api/v1/share-networks', {
				name: inlineNetForm.name, description: inlineNetForm.description,
				neutron_net_id: inlineNetForm.neutron_net_id, neutron_subnet_id: inlineNetForm.neutron_subnet_id,
			}, token, projectId);
			shareNetworks = [...shareNetworks, net];
			selectedNetworkId = net.id;
			showInlineNetCreate = false;
			inlineNetForm = { name: '', description: '', neutron_net_id: '', neutron_subnet_id: '' };
		} catch (e) {
			inlineNetError = e instanceof ApiError ? e.message : '생성 실패';
		} finally { inlineNetCreating = false; }
	}

	async function createFileStorage() {
		// DHSS=True 환경에서 NFS를 선택했고 share network 선택 단계를 통과한 경우만 필수 검증
		if (!shareNetworksOn() && dhssEnabled && fsForm.share_proto === 'NFS') {
			wizardError = 'Share Network 기능이 베타로 꺼져 있어 이 Share Type/NFS 조합은 사용할 수 없습니다.'; return;
		}
		if (shareNetworksOn() && dhssEnabled && fsForm.share_proto === 'NFS' && !selectedNetworkId) {
			wizardError = 'NFS 프로토콜은 Share Network가 필수입니다.'; return;
		}
		creating = true; wizardError = '';
		try {
			const body: Record<string, unknown> = {
				name: fsForm.name, size_gb: fsForm.size_gb,
				share_type: fsForm.share_type, share_proto: fsForm.share_proto,
			};
			// DHSS=True 이고 share network 가 선택된 경우에만 전달 (DHSS=False 이면 무시)
			if (shareNetworksOn() && dhssEnabled && selectedNetworkId && fsForm.share_proto !== 'CEPHFS') body.share_network_id = selectedNetworkId;
			const validMeta = metaEntries.filter((m) => m.key.trim());
			if (validMeta.length > 0) {
				const metadata: Record<string, string> = {};
				validMeta.forEach((m) => { metadata[m.key.trim()] = m.value; });
				body.metadata = metadata;
			}
			const created = await apiMut('파일 스토리지 생성',
				() => api.post<FileStorage>('/api/v1/file-storage', body, token, projectId),
			);
			createdFs = created;
			try {
				accessRules = await api.get<AccessRule[]>(
					`/api/v1/file-storage/${created.id}/access-rules`, token, projectId,
				);
			} catch { accessRules = []; }
			step = 3;
		} catch (e) {
			wizardError = e instanceof ApiError ? e.message : '생성 실패';
		} finally { creating = false; }
	}

	async function addAccessRule() {
		if (!createdFs || !ruleForm.access_to.trim()) return;
		addingRule = true; ruleError = '';
		try {
			const access_type = createdFs.share_proto === 'NFS' ? 'ip' : 'cephx';
			const rule = await api.post<AccessRule>(
				`/api/v1/file-storage/${createdFs.id}/access-rules`,
				{ access_to: ruleForm.access_to.trim(), access_level: ruleForm.access_level, access_type },
				token, projectId,
			);
			accessRules = [...accessRules, rule];
			ruleForm = { access_to: '', access_level: 'rw' };
		} catch (e) {
			ruleError = e instanceof ApiError ? e.message : '추가 실패';
		} finally { addingRule = false; }
	}

	async function copyKey(key: string, ruleId: string) {
		await navigator.clipboard.writeText(key);
		copiedKey = ruleId;
		setTimeout(() => (copiedKey = null), 2000);
	}
	async function copyExport(path: string, id: string) {
		await navigator.clipboard.writeText(path);
		copiedExport = id;
		setTimeout(() => (copiedExport = null), 2000);
	}

	return {
		get open() { return opts.open(); },
		get step() { return step; }, set step(v: WizardStep) { step = v; },
		get wizardError() { return wizardError; },
		get creating() { return creating; },
		get createdFs() { return createdFs; },

		get shareTypes() { return shareTypes; },
		get fsForm() { return fsForm; }, set fsForm(v: typeof fsForm) { fsForm = v; },
		get metaEntries() { return metaEntries; }, set metaEntries(v: MetaEntry[]) { metaEntries = v; },
		get allowedProtos() { return allowedProtos; },
		get currentShareType() { return currentShareType; },
		get dhssEnabled() { return dhssEnabled; },
		get shareNetworksEnabled() { return shareNetworksOn(); },

		get shareNetworks() { return shareNetworks; },
		get selectedNetworkId() { return selectedNetworkId; }, set selectedNetworkId(v: string) { selectedNetworkId = v; },
		get showInlineNetCreate() { return showInlineNetCreate; }, set showInlineNetCreate(v: boolean) { showInlineNetCreate = v; },
		get neutronNetworks() { return neutronNetworks; },
		get subnets() { return subnets; },
		get loadingSubnets() { return loadingSubnets; },
		get inlineNetForm() { return inlineNetForm; }, set inlineNetForm(v: typeof inlineNetForm) { inlineNetForm = v; },
		get inlineNetCreating() { return inlineNetCreating; },
		get inlineNetError() { return inlineNetError; }, set inlineNetError(v: string) { inlineNetError = v; },

		get accessRules() { return accessRules; },
		get ruleForm() { return ruleForm; }, set ruleForm(v: typeof ruleForm) { ruleForm = v; },
		get addingRule() { return addingRule; },
		get ruleError() { return ruleError; },
		get copiedKey() { return copiedKey; },
		get copiedExport() { return copiedExport; },

		openWizard, closeWizard,
		addMeta, removeMeta,
		goStep2, backToStep1,
		onInlineNetworkChange, createInlineNetwork,
		createFileStorage,
		addAccessRule, copyKey, copyExport,
	};
}

export type FileStorageWizardStore = ReturnType<typeof createFileStorageWizardStore>;

const KEY = Symbol('fileStorageWizard');
export function provideFsWizard(s: FileStorageWizardStore) { setContext(KEY, s); }
export function useFsWizard(): FileStorageWizardStore { return getContext(KEY); }
