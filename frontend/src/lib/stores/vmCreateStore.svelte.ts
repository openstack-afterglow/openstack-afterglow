import { get } from 'svelte/store';
import { goto } from '$app/navigation';
import { setContext, getContext } from 'svelte';
import { wizard, resetWizard, closeWizard, type WizardState } from '$lib/stores/wizard';
import { api, ApiError, getBaseUrl } from '$lib/api/client';
import { maybeMockInstanceCreateStream } from '$lib/mockup/transport';
import { auth } from '$lib/stores/auth';
import { betaFeatures } from '$lib/stores/betaFeatures';
import type { BetaFeatures } from '$lib/stores/betaFeatures';
import { toast } from '$lib/stores/toast';
import { siteConfig } from '$lib/config/site';
import type { NetworkInfo } from '$lib/types/networks';
import type { SecurityGroup as SecurityGroupInfo } from '$lib/types/securityGroup';
import type { Volume } from '$lib/types/volume';
import type { Keypair } from '$lib/types/keypair';
import type { FlavorOption } from '$lib/types/flavor';
import type { ImageInfo } from '$lib/types/compute';
import {
	isGithubSshEligible,
	isSshAccessReady,
	isUbuntuImage,
	normalizeGithubUsername,
	normalizeRequestedInstanceName,
} from '$lib/utils/instanceCreate';

interface ProgressMessage {
	step: string;
	progress: number;
	message: string;
	instance_id?: string;
	error?: string;
	elapsed_seconds?: number | null;
}

interface ProjectInfo { id: string; name: string; }
interface QuotaPair { used: number; quota: number; }
interface ProjectQuota {
	project_id: string;
	project_name: string;
	cpu: QuotaPair;
	ram_mb: QuotaPair;
	instances: QuotaPair;
	disk_gb: QuotaPair;
	gpu_instances?: number;
}
interface VmImage extends ImageInfo {
	os_version?: string | null;
	properties?: Record<string, unknown> | null;
}
interface LibraryItem {
	id: string;
	name: string;
	version: string;
	depends_on: string[];
	available_prebuilt: boolean;
	share_proto: string;
	size_bytes?: number;
}
interface QuotaBlock {
	instances?: { limit: number; in_use: number };
	cores?: { limit: number; in_use: number };
	ram?: { limit: number; in_use: number };
	gigabytes?: { limit: number; in_use: number };
}
interface QuotaResponse { compute?: QuotaBlock; storage?: QuotaBlock; volume?: QuotaBlock; }
export interface FlavorQuotaSummary {
	instances?: { limit: number; in_use: number };
	cores?: { limit: number; in_use: number };
	ram?: { limit: number; in_use: number };
	gigabytes?: { limit: number; in_use: number };
}

export interface SquashfsArtifact {
	id: number;
	name: string;
	parent_id: number | null;
	ubuntu_base?: string | null;
	base_image_id?: string | null;
	base_image_name?: string | null;
}

export interface SquashfsProfile {
	id: number;
	name: string;
	layers: string[];
	artifacts?: SquashfsArtifact[];
	base_image?: {
		ubuntu_base?: string | null;
		base_image_id?: string | null;
		base_image_name?: string | null;
	};
}

export function detectUbuntuBaseImage(
	image: Pick<VmImage, 'name' | 'os_distro' | 'os_version' | 'properties'> | null | undefined,
	fallbackName?: string | null,
): string | null {
	if (!image) return null;
	const props = image.properties ?? {};
	const distro = String(image.os_distro ?? props.os_distro ?? '').toLowerCase();
	const version = String(image.os_version ?? props.os_version ?? props.os_version_id ?? props.release ?? '');
	const versionMatch = version.match(/^(18\.04|20\.04|22\.04|24\.04)/);
	if (distro === 'ubuntu' && versionMatch) return versionMatch[1];
	const name = image.name ?? fallbackName ?? '';
	const nameMatch = name.match(/ubuntu[^0-9]*(18\.04|20\.04|22\.04|24\.04)/i);
	return nameMatch ? nameMatch[1] : null;
}

export function nextSquashfsSelection(
	current: Pick<WizardState, 'squashfsMode' | 'layerProfileName' | 'layerArtifactIds'>,
	intent:
		| { type: 'mode'; mode: 'profile' | 'artifacts' }
		| { type: 'profile'; name: string }
		| { type: 'artifact'; id: number; lineageIds: number[] },
): Pick<WizardState, 'squashfsMode' | 'layerProfileName' | 'layerArtifactIds'> {
	const cleared: Pick<WizardState, 'squashfsMode' | 'layerProfileName' | 'layerArtifactIds'> = {
		squashfsMode: null,
		layerProfileName: null,
		layerArtifactIds: [],
	};

	if (intent.type === 'mode') {
		if (current.squashfsMode === intent.mode) return cleared;
		return {
			squashfsMode: intent.mode,
			layerProfileName: intent.mode === 'profile' ? current.layerProfileName : null,
			layerArtifactIds: intent.mode === 'artifacts' ? current.layerArtifactIds : [],
		};
	}

	if (intent.type === 'profile') {
		if (current.squashfsMode === 'profile' && current.layerProfileName === intent.name) return cleared;
		return { squashfsMode: 'profile', layerProfileName: intent.name, layerArtifactIds: [] };
	}

	const ids = new Set(current.squashfsMode === 'artifacts' ? current.layerArtifactIds : []);
	if (ids.has(intent.id)) {
		ids.delete(intent.id);
	} else {
		intent.lineageIds.forEach(id => ids.add(id));
	}
	const layerArtifactIds = Array.from(ids);
	return layerArtifactIds.length > 0
		? { squashfsMode: 'artifacts', layerProfileName: null, layerArtifactIds }
		: cleared;
}

export function normalizeSchedulingForBeta(
	beta: Pick<BetaFeatures, 'haDeploy'>,
	scheduling: 'standard' | 'ha',
): 'standard' | 'ha' {
	return beta.haDeploy ? scheduling : 'standard';
}

export function isSquashfsWizardEligible(options: {
	beta: Pick<BetaFeatures, 'libraryConsume'>;
	adminMode: boolean;
	bootSource: 'image' | 'volume';
	selectedImageUbuntuBase: string | null;
}): boolean {
	return !options.adminMode && options.beta.libraryConsume && options.bootSource === 'image' && Boolean(options.selectedImageUbuntuBase);
}

export function isSquashfsSelectionReady(options: {
	squashfsMode: 'profile' | 'artifacts' | null;
	layerProfileName: string | null;
	layerArtifactIds: number[];
	squashfsBaseMismatch: boolean;
}): boolean {
	if (options.squashfsMode === 'profile') return Boolean(options.layerProfileName) && !options.squashfsBaseMismatch;
	if (options.squashfsMode === 'artifacts') return options.layerArtifactIds.length > 0 && !options.squashfsBaseMismatch;
	return true;
}

export function shouldUseSquashfsConsume(options: {
	beta: Pick<BetaFeatures, 'libraryConsume'>;
	adminMode: boolean;
	bootSource: 'image' | 'volume';
	selectedImageUbuntuBase: string | null;
	squashfsMode: 'profile' | 'artifacts' | null;
	layerProfileName: string | null;
	layerArtifactIds: number[];
	squashfsBaseMismatch: boolean;
}): boolean {
	if (
		!isSquashfsWizardEligible({
			beta: options.beta,
			adminMode: options.adminMode,
			bootSource: options.bootSource,
			selectedImageUbuntuBase: options.selectedImageUbuntuBase,
		})
	) {
		return false;
	}
	return isSquashfsSelectionReady({
		squashfsMode: options.squashfsMode,
		layerProfileName: options.layerProfileName,
		layerArtifactIds: options.layerArtifactIds,
		squashfsBaseMismatch: options.squashfsBaseMismatch,
	}) && options.squashfsMode !== null;
}

export type WizardStepId = 1 | 2 | 3 | 4 | 5 | 6;

type LoadStatus = 'idle' | 'loading' | 'loaded' | 'error';
type OptionKey =
	| 'images'
	| 'volumes'
	| 'flavors'
	| 'squashfsProfiles'
	| 'squashfsArtifacts'
	| 'networks'
	| 'keypairs'
	| 'securityGroups'
	| 'defaultNetwork'
	| 'fileStorages'
	| 'legacyLibraries';

const OPTION_KEYS: OptionKey[] = [
	'images', 'volumes', 'flavors', 'squashfsProfiles', 'squashfsArtifacts',
	'networks', 'keypairs', 'securityGroups', 'defaultNetwork',
	'fileStorages', 'legacyLibraries',
];
export const TOTAL_STEPS = 6;
export const STEP_LABELS: Record<WizardStepId, string> = {
	1: '이미지',
	2: '플레이버',
	3: '라이브러리',
	4: '전략',
	5: '설정',
	6: '배포',
};

export function wizardStepSequence(options: {
	squashfsEligible: boolean;
	haDeploy: boolean;
	hasLibraries?: boolean;
}): WizardStepId[] {
	const steps: WizardStepId[] = [1, 2];
	if (options.squashfsEligible) steps.push(3);
	if (options.haDeploy || options.hasLibraries) steps.push(4);
	steps.push(5, 6);
	return steps;
}

export const ALL_PROGRESS_STEPS = [
	{ id: 'manila_preparing', label: 'File Storage', description: '파일 스토리지 준비', needsLibrary: true },
	{ id: 'boot_volume_creating', label: '부트 볼륨', description: 'OS 이미지 볼륨 생성', needsLibrary: false },
	{ id: 'upper_volume_creating', label: 'Upper 볼륨', description: 'OverlayFS upperdir 생성', needsLibrary: true },
	{ id: 'userdata_generating', label: 'cloud-init', description: '초기화 스크립트 생성', needsLibrary: true },
	{ id: 'server_creating', label: 'VM 생성', description: 'Nova 인스턴스 생성', needsLibrary: false },
	{ id: 'attaching_volume', label: '볼륨 연결', description: '추가 볼륨 연결', needsLibrary: false },
	{ id: 'floating_ip_creating', label: 'Floating IP', description: 'Floating IP 할당', needsLibrary: false },
	{ id: 'completed', label: '완료', description: '배포 완료', needsLibrary: false },
	{ id: 'failed', label: '실패', description: '배포 실패', needsLibrary: false },
];

interface VmCreateOpts {
	adminMode: () => boolean;
}

export type VmCreateStore = ReturnType<typeof createVmCreateStore>;

const VM_CREATE_KEY = Symbol('vm-create');
export function provideVmCreate(store: VmCreateStore) { setContext(VM_CREATE_KEY, store); }
export function useVmCreate(): VmCreateStore {
	const s = getContext<VmCreateStore>(VM_CREATE_KEY);
	if (!s) throw new Error('useVmCreate must be called within VmCreatePanel');
	return s;
}

export function createVmCreateStore(opts: VmCreateOpts) {
	// Mirror writable stores in runes for reactive derived values
	let wizardState = $state(get(wizard));
	let betaState = $state(get(betaFeatures));
	let authProjectId = $state(get(auth).projectId);
	$effect(() => wizard.subscribe(v => { wizardState = v; }));
	$effect(() => betaFeatures.subscribe(v => { betaState = v; }));
	$effect(() => auth.subscribe(v => { authProjectId = v.projectId; }));
	let images = $state<VmImage[]>([]);
	let flavors = $state<FlavorOption[]>([]);
	let libraries = $state<LibraryItem[]>([]);
	let networks = $state<NetworkInfo[]>([]);
	let keypairs = $state<Keypair[]>([]);
	let volumes = $state<Volume[]>([]);
	let fileStorages = $state<{ id: string; name: string; status: string; share_proto: string }[]>([]);
	let securityGroups = $state<SecurityGroupInfo[]>([]);
	let defaultNetworkId = $state<string | null>(null);
	let squashfsProfiles = $state<SquashfsProfile[]>([]);
	let squashfsArtifacts = $state<SquashfsArtifact[]>([]);
	let flavorQuota = $state<FlavorQuotaSummary | null>(null);

	// UI state
	let optionStatus = $state<Record<OptionKey, LoadStatus>>(
		Object.fromEntries(OPTION_KEYS.map(key => [key, 'idle'])) as Record<OptionKey, LoadStatus>,
	);
	let optionErrors = $state<Partial<Record<OptionKey, string>>>({});
	const optionRequests = new Map<string, Promise<void>>();
	let loadGeneration = 0;
	let adminProjectsRequestId = 0;
	let adminProjectQuotasRequestId = 0;
	let adminProjectQuotasPromise: Promise<void> | null = null;
	let initialized = false;
	let loadedAuthProjectId = get(auth).projectId;
	let projectLoadController = new AbortController();
	let destroyed = false;

	let deployController: AbortController | null = null;
	function advanceProjectGeneration() {
		projectLoadController.abort();
		projectLoadController = new AbortController();
		loadGeneration += 1;
	}
	function optionKeysForStep(step: WizardStepId): OptionKey[] {
		if (step === 1) return ['images', 'volumes'];
		if (step === 2) return ['flavors'];
		if (step === 3) return squashfsEligible ? ['squashfsProfiles', 'squashfsArtifacts'] : [];
		if (step === 5) {
			return opts.adminMode()
				? ['networks', 'securityGroups']
				: ['networks', 'keypairs', 'securityGroups', 'defaultNetwork'];
		}
		return [];
	}

	const loading = $derived.by(() =>
		optionKeysForStep(wizardState.step as WizardStepId)
			.some(key => optionStatus[key] === 'idle' || optionStatus[key] === 'loading')
	);
	const hasCurrentStepError = $derived.by(() =>
		optionKeysForStep(wizardState.step as WizardStepId).some(key => optionStatus[key] === 'error')
	);
	let deploying = $state(false);
	let deployError = $state('');
	let currentStep = $state('manila_preparing');
	let progress = $state(0);
	let progressMessage = $state('');
	let elapsedSeconds = $state<number | null>(null);

	// Admin state
	let adminProjects = $state<ProjectInfo[]>([]);
	let adminProjectsLoading = $state(false);
	let adminProjectQuotas = $state<Map<string, ProjectQuota>>(new Map());
	let adminProjectSearch = $state('');
	let adminSelectedProjectId = $state<string | null>(null);
	let adminSelectedProjectName = $state<string | null>(null);

	// Derived
	const filteredAdminProjects = $derived.by(() => {
		const q = adminProjectSearch.trim().toLowerCase();
		if (!q) return adminProjects;
		return adminProjects.filter(p =>
			p.name.toLowerCase().includes(q) || p.id.toLowerCase().includes(q)
		);
	});

	const progressSteps = $derived(
		wizardState.libraries.length > 0
			? ALL_PROGRESS_STEPS
			: ALL_PROGRESS_STEPS.filter(s => !s.needsLibrary)
	);

	const ubuntuVersion = $derived.by(() => {
		const name = wizardState.imageName ?? '';
		const m = name.match(/(\d{2}\.\d{2})/);
		return m ? m[1] : undefined;
	});

	const selectedImage = $derived.by(() => (
		wizardState.imageId ? images.find(image => image.id === wizardState.imageId) ?? null : null
	));

	const selectedImageUbuntuBase = $derived.by(() => detectUbuntuBaseImage(selectedImage, wizardState.imageName));

	const selectedImageIsUbuntu = $derived.by(() => isUbuntuImage(selectedImage, wizardState.imageName));
	const githubSshEligible = $derived.by(() =>
		isGithubSshEligible({
			adminMode: opts.adminMode(),
			bootSource: wizardState.bootSource,
			selectedImageIsUbuntu,
		})
	);

	const selectedSquashfsArtifacts = $derived(
		squashfsArtifacts.filter(artifact => wizardState.layerArtifactIds.includes(artifact.id))
	);

	const squashfsEligible = $derived.by(() =>
		isSquashfsWizardEligible({
			beta: betaState,
			adminMode: opts.adminMode(),
			bootSource: wizardState.bootSource,
			selectedImageUbuntuBase,
		})
	);

	const squashfsBaseMismatch = $derived.by(() => {
		if (!wizardState.squashfsMode || !wizardState.imageId) return false;
		const selectedBaseIds = new Set(selectedSquashfsArtifacts.map(a => a.base_image_id).filter(Boolean));
		if (wizardState.squashfsMode === 'profile' && wizardState.layerProfileName) {
			const profile = squashfsProfiles.find(p => p.name === wizardState.layerProfileName);
			const profileBaseId = profile?.base_image?.base_image_id;
			return Boolean(profileBaseId && profileBaseId !== wizardState.imageId);
		}
		return selectedBaseIds.size > 0 && (selectedBaseIds.size !== 1 || !selectedBaseIds.has(wizardState.imageId));
	});

	const squashfsSelectionReady = $derived.by(() =>
		isSquashfsSelectionReady({
			squashfsMode: wizardState.squashfsMode,
			layerProfileName: wizardState.layerProfileName,
			layerArtifactIds: wizardState.layerArtifactIds,
			squashfsBaseMismatch,
		})
	);

	const selectedNetwork = $derived(
		wizardState.networkId ? networks.find(n => n.id === wizardState.networkId) ?? null : null
	);

	const hasGpuFlavor = $derived(
		flavors.find(f => f.id === wizardState.flavorId)
			? Object.keys(flavors.find(f => f.id === wizardState.flavorId)?.extra_specs ?? {}).some(
				k => k.toLowerCase().includes('gpu') || k.startsWith('pci_passthrough')
			)
			: false
	);

	const hasPrebuilt = $derived(
		libraries.some(l => wizardState.libraries.includes(l.id) && l.available_prebuilt)
	);

	const visibleStepIds = $derived.by(() =>
		wizardStepSequence({
			squashfsEligible,
			haDeploy: betaState.haDeploy,
			hasLibraries: wizardState.libraries.length > 0,
		})
	);
	const visibleStepLabels = $derived(visibleStepIds.map(step => STEP_LABELS[step]));
	const visibleTotalSteps = $derived(visibleStepIds.length);
	const visibleStepIndex = $derived.by(() => {
		const index = visibleStepIds.indexOf(wizardState.step as WizardStepId);
		return index >= 0 ? index + 1 : 1;
	});

	const selectedFlavorDetail = $derived.by(() => {
		const f = flavors.find(fl => fl.id === wizardState.flavorId);
		if (!f) return '';
		const parts = [
			`${f.vcpus} vCPU`,
			`${f.ram >= 1024 ? Math.round(f.ram / 1024) + ' GB' : f.ram + ' MB'}`,
			`${f.disk} GB`,
		];
		const alias = f.extra_specs?.['pci_passthrough:alias'] ?? '';
		if (alias) {
			const gpuParts = alias.split(',').filter((e: string) => e.includes(':') && !e.toLowerCase().includes('audio'));
			gpuParts.forEach((e: string) => {
				const idx = e.lastIndexOf(':');
				const model = e.slice(0, idx).trim();
				const count = parseInt(e.slice(idx + 1)) || 1;
				parts.push(`${model} ${count > 1 ? '× ' + count : ''}`);
			});
		}
		return parts.join(' · ');
	});

	$effect(() => {
		const needsSchedulingReset = wizardState.scheduling !== normalizeSchedulingForBeta(betaState, wizardState.scheduling);
		const needsGithubSshReset =
			!githubSshEligible &&
			(wizardState.sshAccessMode !== 'keypair' || wizardState.githubUsername !== '');
		const needsSquashfsReset = !squashfsEligible && wizardState.squashfsMode !== null;
		const needsStrategyReset = !visibleStepIds.includes(4) && wizardState.strategy !== null;
		const isVisibleStep = visibleStepIds.includes(wizardState.step as WizardStepId);
		const nextVisibleStep = isVisibleStep
			? null
			: (visibleStepIds.find(step => step > wizardState.step) ?? visibleStepIds[visibleStepIds.length - 1] ?? 1);
		if (!needsSchedulingReset && !needsSquashfsReset && !needsStrategyReset && !needsGithubSshReset && nextVisibleStep === null) return;
		wizard.update(w => {
			let next = w;
			const nextScheduling = normalizeSchedulingForBeta(betaState, next.scheduling);
			if (nextScheduling !== next.scheduling) {
				next = { ...next, scheduling: nextScheduling };
			}
			if (!squashfsEligible && next.squashfsMode !== null) {
				next = { ...next, squashfsMode: null, layerProfileName: null, layerArtifactIds: [] };
			}
			if (!visibleStepIds.includes(4) && next.strategy !== null) {
				next = { ...next, strategy: null };
			}
			if (!githubSshEligible && (next.sshAccessMode !== 'keypair' || next.githubUsername !== '')) {
				next = { ...next, sshAccessMode: 'keypair', githubUsername: '' };
			}
			if (nextVisibleStep !== null && next.step !== nextVisibleStep) {
				next = { ...next, step: nextVisibleStep };
			}
			return next;
		});
	});

	const canNext = $derived((() => {
		const adminMode = opts.adminMode();
		switch (wizardState.step) {
			case 1: return wizardState.bootSource === 'volume' ? !!wizardState.bootVolumeId : !!wizardState.imageId;
			case 2: {
				if (!wizardState.flavorId) return false;
				const selected = flavors.find(f => f.id === wizardState.flavorId);
				return selected?.eligibility ? selected.eligibility.selectable : true;
			}
			case 3: return squashfsSelectionReady;
			case 4: {
				if (!wizardState.scheduling) return false;
				if (wizardState.libraries.length > 0 && !wizardState.strategy) return false;
				return true;
			}
			case 5:
				return isSshAccessReady({
					adminMode,
					sshAccessMode: wizardState.sshAccessMode,
					keyName: wizardState.keyName,
					githubUsername: wizardState.githubUsername,
				});
			case 6: return true;
			default: return false;
		}
	})());

	const needsProjectSelect = $derived(opts.adminMode() && !adminSelectedProjectId);

	// Helpers
	function fmtRemaining(p?: QuotaPair): string {
		if (!p) return '-';
		if (p.quota < 0) return '∞';
		return String(Math.max(0, p.quota - p.used));
	}

	function isExhausted(p?: QuotaPair): boolean {
		if (!p || p.quota < 0) return false;
		return p.used >= p.quota;
	}

	function resolveAllDeps(id: string): string[] {
		const result: string[] = [];
		const visited = new Set<string>();
		function visit(lid: string) {
			if (visited.has(lid)) return;
			visited.add(lid);
			const lib = libraries.find(l => l.id === lid);
			if (lib) (lib.depends_on ?? []).forEach(d => visit(d));
			result.push(lid);
		}
		visit(id);
		return result;
	}

	function lineageIdsForArtifact(id: number): number[] {
		const byId = new Map(squashfsArtifacts.map(artifact => [artifact.id, artifact]));
		const chain: number[] = [];
		const seen = new Set<number>();
		let current = byId.get(id);
		while (current && !seen.has(current.id)) {
			seen.add(current.id);
			chain.unshift(current.id);
			current = current.parent_id ? byId.get(current.parent_id) : undefined;
		}
		return chain;
	}

	function optionError(error: unknown): string {
		return error instanceof ApiError ? `데이터 로드 실패 (${error.status})` : '서버 오류';
	}

	function loadOption<T>(
		key: OptionKey,
		scope: string,
		request: (signal?: AbortSignal) => Promise<T>,
		apply: (value: T) => void,
		isCurrent = () => true,
	): Promise<void> {
		if (destroyed) return Promise.resolve();
		const generation = loadGeneration;
		const projectScoped = scope !== 'global';
		const signal = projectScoped ? projectLoadController.signal : undefined;
		const requestKey = projectScoped ? `${key}:${scope}:${generation}` : `${key}:${scope}`;
		const existing = optionRequests.get(requestKey);
		if (existing) return existing;
		if (optionStatus[key] !== 'idle' && optionStatus[key] !== 'error') return Promise.resolve();

		optionStatus[key] = 'loading';
		delete optionErrors[key];
		const promise = request(signal)
			.then(value => {
				if (destroyed || (projectScoped && generation !== loadGeneration) || !isCurrent()) return;
				apply(value);
				optionStatus[key] = 'loaded';
			})
			.catch(error => {
				if (destroyed || (projectScoped && generation !== loadGeneration) || !isCurrent()) return;
				if (error instanceof DOMException && error.name === 'AbortError') return;
				optionErrors[key] = optionError(error);
				optionStatus[key] = 'error';
			})
			.finally(() => {
				if (optionRequests.get(requestKey) === promise) optionRequests.delete(requestKey);
			});
		optionRequests.set(requestKey, promise);
		return promise;
	}

	function authScope() {
		return {
			token: get(auth).token ?? undefined,
			projectId: get(auth).projectId ?? undefined,
		};
	}

	function targetIsCurrent(projectId: string, generation: number) {
		return !destroyed && opts.adminMode() && adminSelectedProjectId === projectId && loadGeneration === generation;
	}

	function authProjectIsCurrent(projectId: string | undefined, generation: number) {
		return !destroyed
			&& !opts.adminMode()
			&& (get(auth).projectId ?? undefined) === projectId
			&& loadGeneration === generation;
	}

	async function loadBootOptions() {
		const { token, projectId } = authScope();
		if (destroyed) return;
		const imagePromise = loadOption(
			'images',
			opts.adminMode() ? 'global' : `public:${projectId ?? ''}`,
			(signal) => api.get<VmImage[]>('/api/v1/images', token, projectId, { signal }),
			value => { images = value; },
		);
		if (!opts.adminMode()) {
			const volumePromise = loadOption(
				'volumes',
				`public:${projectId ?? ''}`,
				(signal) => api.get<Volume[]>('/api/v1/volumes', token, projectId, { signal }),
				value => { volumes = value; },
			);
			await Promise.all([imagePromise, volumePromise]);
			return;
		}
		const targetProjectId = adminSelectedProjectId;
		if (!targetProjectId) {
			await imagePromise;
			return;
		}
		const generation = loadGeneration;
		const volumePromise = loadOption(
			'volumes',
			targetProjectId,
			(signal) => api.get<Volume[]>(`/api/v1/admin/instances/volumes-for-project?project_id=${encodeURIComponent(targetProjectId)}`,
				token,
				projectId,
				{ signal },
			),
			value => { volumes = value; },
			() => targetIsCurrent(targetProjectId, generation),
		);
		await Promise.all([imagePromise, volumePromise]);
	}

	function loadFlavorOptions() {
		if (destroyed) return Promise.resolve();
		const { token, projectId } = authScope();
		if (opts.adminMode() && adminSelectedProjectId) {
			const targetProjectId = adminSelectedProjectId;
			const generation = loadGeneration;
			return loadOption(
				'flavors',
				targetProjectId,
				(signal) => api.get<FlavorOption[]>(`/api/v1/admin/instances/flavors-for-project?project_id=${encodeURIComponent(targetProjectId)}`,
						token,
						projectId,
						{ signal },
					),
				value => {
					flavors = value;
				},
				() => targetIsCurrent(targetProjectId, generation),
			);
		}
		return loadOption(
			'flavors',
			`public:${projectId ?? ''}`,
			(signal) => api.get<FlavorOption[]>('/api/v1/flavors', token, projectId, { signal }),
			value => { flavors = value; },
		);
	}

	async function loadSquashfsCatalog() {
		if (destroyed) return;
		if (opts.adminMode()) return;
		const { token, projectId } = authScope();
		await Promise.allSettled([
			loadOption(
				'squashfsProfiles',
				`public:${projectId ?? ''}`,
				(signal) => api.get<SquashfsProfile[]>('/api/v1/libraries/squashfs/profiles', token, projectId, { signal }),
				value => { squashfsProfiles = value; },
			),
			loadOption(
				'squashfsArtifacts',
				`public:${projectId ?? ''}`,
				(signal) => api.get<SquashfsArtifact[]>('/api/v1/libraries/squashfs/artifacts', token, projectId, { signal }),
				value => { squashfsArtifacts = value; },
			),
		]);
	}

	async function loadConfigurationOptions() {
		if (destroyed) return;
		const { token, projectId } = authScope();
		const generation = loadGeneration;
		if (!opts.adminMode()) {
			await Promise.allSettled([
				loadOption('networks', `public:${projectId ?? ''}`, (signal) => api.get<NetworkInfo[]>('/api/v1/networks', token, projectId, { signal }), value => { networks = value; }),
				loadOption('keypairs', `public:${projectId ?? ''}`, (signal) => api.get<Keypair[]>('/api/v1/keypairs', token, projectId, { signal }), value => { keypairs = value; }),
				loadOption('securityGroups', `public:${projectId ?? ''}`, (signal) => api.get<SecurityGroupInfo[]>('/api/v1/security-groups', token, projectId, { signal }), value => { securityGroups = value; }),
				loadOption('defaultNetwork', `public:${projectId ?? ''}`, (signal) => api.get<{ network_id: string }>('/api/v1/networks/default', token, projectId, { signal }), value => { defaultNetworkId = value.network_id; }),
			]);
			if (authProjectIsCurrent(projectId, generation)) applyConfigurationDefaults();
			return;
		}
		const targetProjectId = adminSelectedProjectId;
		if (!targetProjectId) return;
		const isCurrent = () => targetIsCurrent(targetProjectId, generation);
		await Promise.allSettled([
			loadOption(
				'networks',
				targetProjectId,
				(signal) => api.get<NetworkInfo[]>(`/api/v1/admin/instances/networks-for-project?project_id=${encodeURIComponent(targetProjectId)}`, token, projectId, { signal }),
				value => { networks = value; },
				isCurrent,
			),
			loadOption(
				'securityGroups',
				targetProjectId,
				(signal) => api.get<SecurityGroupInfo[]>(`/api/v1/admin/instances/security-groups-for-project?project_id=${encodeURIComponent(targetProjectId)}`, token, projectId, { signal }),
				value => { securityGroups = value; },
				isCurrent,
			),
		]);
		if (isCurrent()) applyConfigurationDefaults();
	}

	function applyConfigurationDefaults() {
		if (destroyed) return;
		const current = get(wizard);
		if (!opts.adminMode() && keypairs.length === 1 && !current.keyName) {
			wizard.update(w => ({ ...w, keyName: keypairs[0].name }));
		}
		if (networks.length > 0 && !current.networkId) {
			const selected = networks.find(network => network.id === defaultNetworkId)
				?? networks.find(network => network.name === 'Default')
				?? networks[0];
			wizard.update(w => ({ ...w, networkId: selected.id, networkName: selected.name }));
		}
		if (securityGroups.length > 0 && current.securityGroups.length === 0) {
			const defaultGroup = securityGroups.find(group => group.name === 'default');
			if (defaultGroup) wizard.update(w => ({ ...w, securityGroups: [defaultGroup.name] }));
		}
	}

	function loadFileStorages() {
		if (destroyed) return Promise.resolve();
		if (opts.adminMode() || !get(siteConfig).services.manila) {
			fileStorages = [];
			return Promise.resolve();
		}
		const { token, projectId } = authScope();
		return loadOption(
			'fileStorages',
			`public:${projectId ?? ''}`,
			(signal) => api.get<typeof fileStorages>('/api/v1/file-storage', token, projectId, { signal }),
			value => { fileStorages = value; },
		);
	}

	function preloadConfigurationAfterBoot(bootPromise: Promise<void>, targetProjectId?: string) {
		const generation = loadGeneration;
		void bootPromise.then(() => {
			if (destroyed || generation !== loadGeneration) return;
			if (opts.adminMode() && targetProjectId !== adminSelectedProjectId) return;
			void loadConfigurationOptions();
			void loadFileStorages();
		});
	}

	function loadLegacyLibraries() {
		if (destroyed) return Promise.resolve();
		if (wizardState.libraries.length === 0) return Promise.resolve();
		const { token, projectId } = authScope();
		return loadOption(
			'legacyLibraries',
			`public:${projectId ?? ''}`,
			(signal) => api.get<LibraryItem[]>('/api/v1/libraries', token, projectId, { signal }),
			value => { libraries = value; },
		);
	}

	function hasCompleteProjectQuota(summary: ProjectQuota | undefined): summary is ProjectQuota {
		if (!summary) return false;
		return [summary.instances, summary.cpu, summary.ram_mb, summary.disk_gb]
			.every(pair => Number.isFinite(pair?.used) && Number.isFinite(pair?.quota));
	}

	function mapProjectQuota(summary: ProjectQuota): FlavorQuotaSummary {
		return {
			instances: { limit: summary.instances.quota, in_use: summary.instances.used },
			cores: { limit: summary.cpu.quota, in_use: summary.cpu.used },
			ram: { limit: summary.ram_mb.quota, in_use: summary.ram_mb.used },
			gigabytes: { limit: summary.disk_gb.quota, in_use: summary.disk_gb.used },
		};
	}

	async function loadFlavorQuota() {
		if (destroyed) return;
		const { token, projectId } = authScope();
		if (opts.adminMode() && adminSelectedProjectId) {
			const targetProjectId = adminSelectedProjectId;
			const generation = loadGeneration;
			if (adminProjectQuotasPromise) await adminProjectQuotasPromise;
			if (!targetIsCurrent(targetProjectId, generation)) return;

			const summary = adminProjectQuotas.get(targetProjectId);
			if (hasCompleteProjectQuota(summary)) {
				flavorQuota = mapProjectQuota(summary);
				return;
			}

			try {
				const response = await api.get<QuotaResponse>(
					`/api/v1/admin/quotas/${encodeURIComponent(targetProjectId)}`,
					token,
					projectId,
					{ signal: projectLoadController.signal },
				);
				if (!targetIsCurrent(targetProjectId, generation)) return;
				flavorQuota = {
					instances: response.compute?.instances,
					cores: response.compute?.cores,
					ram: response.compute?.ram,
					gigabytes: response.volume?.gigabytes,
				};
			} catch {
				if (targetIsCurrent(targetProjectId, generation)) flavorQuota = null;
			}
			return;
		}
		if (!opts.adminMode()) {
			const generation = loadGeneration;
			try {
				const response = await api.get<QuotaResponse>('/api/v1/dashboard/quotas', token, projectId, { signal: projectLoadController.signal });
				if (!authProjectIsCurrent(projectId, generation)) return;
				flavorQuota = {
					instances: response.compute?.instances,
					cores: response.compute?.cores,
					ram: response.compute?.ram,
					gigabytes: response.storage?.gigabytes,
				};
			} catch {
				if (authProjectIsCurrent(projectId, generation)) flavorQuota = null;
			}
		}
	}

	function loadAdminProjectQuotas(): Promise<void> {
		if (!opts.adminMode()) return Promise.resolve();
		if (destroyed) return Promise.resolve();
		if (adminProjectQuotasPromise) return adminProjectQuotasPromise;

		const requestId = ++adminProjectQuotasRequestId;
		const { token, projectId } = authScope();
		let promise!: Promise<void>;
		promise = (async () => {
			try {
				const rows = await api.get<ProjectQuota[]>('/api/v1/admin/overview/projects', token, projectId);
				if (requestId !== adminProjectQuotasRequestId) return;
				adminProjectQuotas = new Map(rows.map(row => [row.project_id, row]));
			} catch {
				if (requestId === adminProjectQuotasRequestId) adminProjectQuotas = new Map();
			} finally {
				if (adminProjectQuotasPromise === promise) adminProjectQuotasPromise = null;
			}
		})();
		adminProjectQuotasPromise = promise;
		return promise;
	}

	async function loadAdminProjects() {
		if (!opts.adminMode()) return;
		if (destroyed) return;
		const requestId = ++adminProjectsRequestId;
		adminProjectsLoading = true;
		const { token, projectId } = authScope();
		try {
			const rows = await api.get<ProjectInfo[]>('/api/v1/admin/projects/names', token, projectId);
			if (requestId !== adminProjectsRequestId) return;
			adminProjects = rows;
			const selected = adminSelectedProjectId && rows.find(project => project.id === adminSelectedProjectId);
			if (selected) adminSelectedProjectName = selected.name;
		} catch {
			if (requestId === adminProjectsRequestId) adminProjects = [];
		} finally {
			if (requestId === adminProjectsRequestId) adminProjectsLoading = false;
		}
	}

	function resetTargetOptions() {
		advanceProjectGeneration();
		for (const key of ['volumes', 'flavors', 'networks', 'securityGroups'] as const) {
			optionStatus[key] = 'idle';
			delete optionErrors[key];
		}
		volumes = [];
		flavors = [];
		networks = [];
		securityGroups = [];
		defaultNetworkId = null;
		flavorQuota = null;
		wizard.update(w => ({
			...w,
			bootVolumeId: null,
			bootVolumeName: null,
			flavorId: null,
			flavorName: null,
			networkId: null,
			networkName: null,
			securityGroups: [],
			keyName: null,
			sshAccessMode: 'keypair',
			githubUsername: '',
		}));
	}

	function resetPublicProjectOptions() {
		advanceProjectGeneration();
		for (const key of OPTION_KEYS) {
			optionStatus[key] = 'idle';
			delete optionErrors[key];
		}
		images = [];
		volumes = [];
		flavors = [];
		libraries = [];
		networks = [];
		keypairs = [];
		securityGroups = [];
		fileStorages = [];
		squashfsProfiles = [];
		squashfsArtifacts = [];
		defaultNetworkId = null;
		flavorQuota = null;
		resetWizard();
	}

	function ensureStepData(step: WizardStepId) {
		if (destroyed) return;
		if (step === 1) void loadBootOptions();
		if (step === 2) void loadFlavorOptions();
		if (step === 3 && squashfsEligible) void loadSquashfsCatalog();
		if (step === 4 && wizardState.libraries.length > 0) void loadLegacyLibraries();
		if (step === 5) {
			void loadConfigurationOptions();
			void loadFileStorages();
		}
	}

	function selectAdminProject(id: string, name: string) {
		adminSelectedProjectId = id;
		adminSelectedProjectName = name;
		resetTargetOptions();
		const bootPromise = loadBootOptions();
		preloadConfigurationAfterBoot(bootPromise, id);
		void loadFlavorOptions();
		void loadFlavorQuota();
		ensureStepData(wizardState.step as WizardStepId);
	}

	function handleReset() {
		resetWizard();
		adminSelectedProjectId = null;
		adminSelectedProjectName = null;
		resetTargetOptions();
		if (opts.adminMode()) {
			void Promise.all([loadAdminProjects(), loadAdminProjectQuotas()]);
		} else {
			ensureStepData(1);
			void loadFlavorOptions();
			void loadFlavorQuota();
		}
	}

	function nearestVisibleStep(step: number): WizardStepId {
		return (
			visibleStepIds.find(candidate => candidate >= step) ??
			visibleStepIds[visibleStepIds.length - 1] ??
			1
		);
	}

	function nextStep() {
		const current = get(wizard).step as WizardStepId;
		const index = visibleStepIds.indexOf(current);
		const next = visibleStepIds[Math.min(index + 1, visibleStepIds.length - 1)];
		if (!next || next === current) return;
		ensureStepData(next);
		wizard.update(w => ({ ...w, step: next }));
	}

	function prevStep() {
		const current = get(wizard).step as WizardStepId;
		const index = visibleStepIds.indexOf(current);
		const prev = visibleStepIds[Math.max(index - 1, 0)];
		if (!prev || prev === current) return;
		ensureStepData(prev);
		wizard.update(w => ({ ...w, step: prev }));
	}

	function goTo(step: number) {
		const next = nearestVisibleStep(step);
		ensureStepData(next);
		wizard.update(w => ({ ...w, step: next }));
	}

	function goToVisible(index: number) {
		const step = visibleStepIds[index - 1];
		if (!step) return;
		ensureStepData(step);
		wizard.update(w => ({ ...w, step }));
	}

	function selectImage(id: string, name: string) {
		wizard.update(w => ({ ...w, imageId: id, imageName: name }));
		const image = images.find(candidate => candidate.id === id);
		if (!opts.adminMode() && betaState.libraryConsume && detectUbuntuBaseImage(image, name)) {
			void loadSquashfsCatalog();
		}
		nextStep();
	}
	function selectFlavor(id: string, name: string) {
		const selected = flavors.find(candidate => candidate.id === id);
		if (selected?.eligibility && !selected.eligibility.selectable) {
			return;
		}
		wizard.update(w => ({ ...w, flavorId: id, flavorName: name }));
		nextStep();
	}

	function toggleLibrary(id: string, _deps: string[]) {
		wizard.update(w => {
			const libs = new Set(w.libraries);
			if (libs.has(id)) {
				libs.delete(id);
			} else {
				resolveAllDeps(id).forEach(d => libs.add(d));
			}
			const newLibs = Array.from(libs);
			const newStrategy = newLibs.length === 0 ? null : (w.strategy ?? 'prebuilt');
			return { ...w, libraries: newLibs, strategy: newStrategy };
		});
	}

	function selectStrategy(s: 'prebuilt' | 'dynamic' | null) { wizard.update(w => ({ ...w, strategy: s })); }
	function selectScheduling(s: 'standard' | 'ha') {
		wizard.update(w => ({ ...w, scheduling: normalizeSchedulingForBeta(betaState, s) }));
	}
	function selectMountProtocol(p: 'CEPHFS' | 'NFS') { wizard.update(w => ({ ...w, mountProtocol: p })); }

	function selectNetwork(id: string | null) {
		const net = networks.find(n => n.id === id) ?? null;
		wizard.update(w => ({ ...w, networkId: id, networkName: net?.name ?? null }));
	}

	function selectSshAccessMode(mode: 'keypair' | 'github') {
		if (mode === 'github' && !githubSshEligible) return;
		wizard.update(w => ({
			...w,
			sshAccessMode: mode,
			keyName: mode === 'github' ? null : w.keyName,
			githubUsername: mode === 'keypair' ? '' : w.githubUsername,
		}));
	}

	function clearSquashfsSelection() {
		wizard.update(w => ({ ...w, squashfsMode: null, layerProfileName: null, layerArtifactIds: [] }));
	}

	function selectSquashfsMode(mode: 'profile' | 'artifacts' | null) {
		wizard.update(w => {
			const selection = mode === null
				? { squashfsMode: null, layerProfileName: null, layerArtifactIds: [] }
				: nextSquashfsSelection(w, { type: 'mode', mode });
			return {
				...w,
				...selection,
				libraries: selection.squashfsMode ? [] : w.libraries,
				templateName: selection.squashfsMode ? null : w.templateName,
				templateVersion: selection.squashfsMode ? null : w.templateVersion,
				strategy: selection.squashfsMode ? null : w.strategy,
			};
		});
	}

	function selectSquashfsProfile(name: string | null) {
		wizard.update(w => {
			const selection = name === null
				? { squashfsMode: null, layerProfileName: null, layerArtifactIds: [] }
				: nextSquashfsSelection(w, { type: 'profile', name });
			return {
				...w,
				...selection,
				libraries: selection.squashfsMode ? [] : w.libraries,
				templateName: selection.squashfsMode ? null : w.templateName,
				templateVersion: selection.squashfsMode ? null : w.templateVersion,
				strategy: selection.squashfsMode ? null : w.strategy,
			};
		});
	}

	function toggleSquashfsArtifact(id: number) {
		wizard.update(w => {
			const selection = nextSquashfsSelection(w, {
				type: 'artifact',
				id,
				lineageIds: lineageIdsForArtifact(id),
			});
			return {
				...w,
				...selection,
				libraries: selection.squashfsMode ? [] : w.libraries,
				templateName: selection.squashfsMode ? null : w.templateName,
				templateVersion: selection.squashfsMode ? null : w.templateVersion,
				strategy: selection.squashfsMode ? null : w.strategy,
			};
		});
	}

	async function deploy() {
		if (destroyed || deploying) return;
		deployController?.abort();
		deployController = new AbortController();
		deployError = '';
		deploying = true;
		currentStep = 'manila_preparing';
		progress = 0;
		progressMessage = '배포 시작...';

		const baseUrl = getBaseUrl();
		const authState = get(auth);
		const headers: Record<string, string> = {
			'Content-Type': 'application/json',
			'Accept': 'text/event-stream',
		};
		if (authState.token) headers['Authorization'] = `Bearer ${authState.token}`;
		if (authState.projectId) headers['X-Project-Id'] = authState.projectId;

		const endpoint = opts.adminMode()
			? `${baseUrl}/api/v1/admin/instances/async`
			: `${baseUrl}/api/v1/instances/async`;

		const w = get(wizard);
		const requestedName = normalizeRequestedInstanceName(w.instanceName);
		const githubUsername = w.sshAccessMode === 'github'
			? normalizeGithubUsername(w.githubUsername) || null
			: null;
		const keyName = w.sshAccessMode === 'github' ? null : w.keyName || null;
		const useSquashfsConsume = shouldUseSquashfsConsume({
			beta: betaState,
			adminMode: opts.adminMode(),
			bootSource: w.bootSource,
			selectedImageUbuntuBase,
			squashfsMode: w.squashfsMode,
			layerProfileName: w.layerProfileName,
			layerArtifactIds: w.layerArtifactIds,
			squashfsBaseMismatch,
		});
		if (useSquashfsConsume) {
			const consumeBody: Record<string, unknown> = {
				server_name: requestedName,
				flavor_id: w.flavorId,
				image_id: w.imageId,
				network_id: w.networkId,
				key_name: keyName,
				github_username: githubUsername,
				userdata: w.cloudInit || null,
				...(w.squashfsMode === 'profile'
					? { profile_name: w.layerProfileName }
					: { artifact_ids: w.layerArtifactIds }),
			};
			try {
				currentStep = 'server_creating';
				progress = 60;
				progressMessage = 'squashfs 라이브러리 소비 VM 생성 중...';
				const response = await fetch(`${baseUrl}/api/v1/libraries/squashfs/consume`, {
					method: 'POST',
					headers: { ...headers, Accept: 'application/json' },
					body: JSON.stringify(consumeBody),
					signal: deployController.signal,
				});
				if (destroyed) return;
				if (!response.ok) {
					const text = await response.text();
					throw new ApiError(response.status, text || response.statusText);
				}
				currentStep = 'completed';
				progress = 100;
				progressMessage = '배포 완료';
				toast.success('인스턴스 생성 완료');
				setTimeout(() => {
					if (destroyed) return;
					resetWizard();
					closeWizard();
					goto('/dashboard');
				}, 1000);
				return;
			} catch (e) {
				if (destroyed) return;
				deployError = e instanceof ApiError
					? `배포 실패: ${e.message}`
					: `서버 연결 오류: ${e instanceof Error ? e.message : '알 수 없는 오류'}`;
				toast.error(`인스턴스 생성 실패: ${deployError}`);
				deploying = false;
				return;
			}
		}
		const body: Record<string, unknown> = {
			name: requestedName,
			...(w.bootSource === 'volume'
				? { boot_volume_id: w.bootVolumeId }
				: {
					image_id: w.imageId,
					boot_volume_size_gb: w.bootVolumeSizeGb,
					delete_boot_volume_on_termination: w.deleteBootVolumeOnTermination,
				}),
			flavor_id: w.flavorId,
			libraries: w.libraries,
			strategy: w.strategy,
			scheduling: normalizeSchedulingForBeta(betaState, w.scheduling),
			network_id: w.networkId,
			key_name: keyName,
			github_username: githubUsername,
			security_groups: w.securityGroups,
			userdata: w.cloudInit || null,
			data_mounts: w.dataMounts.map(m => ({
				file_storage_id: m.fileStorageId,
				mount_point: m.mountPoint,
				read_only: m.readOnly,
			})),
		};
		if (opts.adminMode() && adminSelectedProjectId) {
			body.project_id = adminSelectedProjectId;
		}

		// mockup 모드: 실제 API 대신 가상 SSE 스트림으로 배포 흐름 재현
		const mockStream = maybeMockInstanceCreateStream(
			opts.adminMode() ? '/api/v1/admin/instances/async' : '/api/v1/instances/async',
			body,
		);
		if (mockStream) {
			for await (const data of mockStream) {
				if (destroyed) return;
				currentStep = data.step;
				progress = data.progress;
				progressMessage = data.message;
			}
			toast.success('인스턴스 생성 완료');
			setTimeout(() => {
				if (destroyed) return;
				resetWizard();
				adminSelectedProjectId = null;
				adminSelectedProjectName = null;
				closeWizard();
				goto(opts.adminMode() ? '/admin/instances' : '/dashboard');
			}, 1000);
			return;
		}

		try {
			const response = await fetch(endpoint, { method: 'POST', headers, body: JSON.stringify(body), signal: deployController.signal });
			if (destroyed) return;
			if (!response.ok) {
				const text = await response.text();
				throw new ApiError(response.status, text || response.statusText);
			}
			const reader = response.body?.getReader();
			if (!reader) throw new Error('No response body');
			const decoder = new TextDecoder();
			let buffer = '';
			while (true) {
				const { done, value } = await reader.read();
				if (destroyed) {
					await reader.cancel();
					return;
				}
				if (done) break;
				buffer += decoder.decode(value, { stream: true });
				const lines = buffer.split('\n');
				buffer = lines.pop() || '';
				for (const line of lines) {
					if (line.startsWith('data: ')) {
						try {
							const data = JSON.parse(line.slice(6)) as ProgressMessage;
							currentStep = data.step;
							progress = data.progress;
							progressMessage = data.message;
							if (data.elapsed_seconds !== undefined && data.elapsed_seconds !== null) {
								elapsedSeconds = data.elapsed_seconds;
							}
							if (data.step === 'completed') {
								toast.success(`인스턴스 생성 완료`);
								setTimeout(() => {
									if (destroyed) return;
									resetWizard();
									adminSelectedProjectId = null;
									adminSelectedProjectName = null;
									closeWizard();
									goto(opts.adminMode() ? '/admin/instances' : '/dashboard');
								}, 1000);
								return;
							}
							if (data.step === 'failed') {
								deployError = data.error || data.message;
								toast.error(`인스턴스 생성 실패: ${deployError}`);
								deploying = false;
								return;
							}
						} catch { /* JSON 파싱 실패 시 무시 */ }
					}
				}
			}
		} catch (e) {
			if (destroyed) return;
			deployError = e instanceof ApiError
				? `배포 실패: ${e.message}`
				: `서버 연결 오류: ${e instanceof Error ? e.message : '알 수 없는 오류'}`;
			deploying = false;
		}
	}

	function retryCurrentStep() {
		ensureStepData(wizardState.step as WizardStepId);
	}

	$effect(() => {
		const projectId = authProjectId;
		if (!initialized || opts.adminMode() || projectId === loadedAuthProjectId) return;
		loadedAuthProjectId = projectId;
		resetPublicProjectOptions();

		if (!projectId) return;
		if (destroyed) return;
		const bootPromise = loadBootOptions();
		preloadConfigurationAfterBoot(bootPromise);
		void loadFlavorOptions();
		void loadFlavorQuota();
	});
	function destroy() {
		if (destroyed) return;
		destroyed = true;
		initialized = false;
		projectLoadController.abort();
		deployController?.abort();
		deployController = null;
		loadGeneration += 1;
		adminProjectsRequestId += 1;
		adminProjectQuotasRequestId += 1;
		optionRequests.clear();
		adminProjectQuotasPromise = null;
	}

	function init() {
		if (destroyed) return;
		loadedAuthProjectId = get(auth).projectId;
		initialized = true;
		if (opts.adminMode()) {
			const targetId = get(wizard).targetProjectId;
			if (targetId) {
				adminSelectedProjectId = targetId;
				adminSelectedProjectName = targetId;
				resetTargetOptions();
				void loadAdminProjects();
				const bootPromise = loadBootOptions();
				preloadConfigurationAfterBoot(bootPromise, targetId);
				void loadFlavorOptions();
				void loadFlavorQuota();
				ensureStepData(wizardState.step as WizardStepId);
				return;
			}
			void Promise.all([loadAdminProjects(), loadAdminProjectQuotas()]);
			return;
		}
		const bootPromise = loadBootOptions();
		preloadConfigurationAfterBoot(bootPromise);
		void loadFlavorOptions();
		void loadFlavorQuota();
		ensureStepData(wizardState.step as WizardStepId);
	}

	return {
		// Opts passthrough
		get adminMode() { return opts.adminMode(); },
		// Wizard state mirror (for sub-components that need form state without $ prefix)
		get wizardState() { return wizardState; },
		// Data state
		get images() { return images; },
		get flavors() { return flavors; },
		get libraries() { return libraries; },
		get networks() { return networks; },
		get keypairs() { return keypairs; },
		get volumes() { return volumes; },
		get fileStorages() { return fileStorages; },
		get securityGroups() { return securityGroups; },
		get defaultNetworkId() { return defaultNetworkId; },
		get flavorQuota() { return flavorQuota; },
		get squashfsProfiles() { return squashfsProfiles; },
		get squashfsArtifacts() { return squashfsArtifacts; },
		get optionStatus() { return optionStatus; },
		get optionErrors() { return optionErrors; },
		// UI state
		get loading() { return loading; },
		get hasCurrentStepError() { return hasCurrentStepError; },
		get deploying() { return deploying; },
		get deployError() { return deployError; },
		get currentStep() { return currentStep; },
		get progress() { return progress; },
		get progressMessage() { return progressMessage; },
		get visibleStepIds() { return visibleStepIds; },
		get visibleStepLabels() { return visibleStepLabels; },
		get visibleTotalSteps() { return visibleTotalSteps; },
		get visibleStepIndex() { return visibleStepIndex; },
		get elapsedSeconds() { return elapsedSeconds; },
		// Admin state
		get adminProjects() { return adminProjects; },
		get adminProjectsLoading() { return adminProjectsLoading; },
		get adminProjectQuotas() { return adminProjectQuotas; },
		get adminProjectSearch() { return adminProjectSearch; },
		set adminProjectSearch(v: string) { adminProjectSearch = v; },
		get adminSelectedProjectId() { return adminSelectedProjectId; },
		get adminSelectedProjectName() { return adminSelectedProjectName; },
		// Derived
		get filteredAdminProjects() { return filteredAdminProjects; },
		get progressSteps() { return progressSteps; },
		get ubuntuVersion() { return ubuntuVersion; },
		get selectedNetwork() { return selectedNetwork; },
		get selectedImage() { return selectedImage; },
		get selectedImageUbuntuBase() { return selectedImageUbuntuBase; },
		get selectedImageIsUbuntu() { return selectedImageIsUbuntu; },
		get githubSshEligible() { return githubSshEligible; },
		get squashfsEligible() { return squashfsEligible; },
		get selectedSquashfsArtifacts() { return selectedSquashfsArtifacts; },
		get squashfsBaseMismatch() { return squashfsBaseMismatch; },
		get squashfsSelectionReady() { return squashfsSelectionReady; },
		get hasGpuFlavor() { return hasGpuFlavor; },
		get hasPrebuilt() { return hasPrebuilt; },
		get selectedFlavorDetail() { return selectedFlavorDetail; },
		get canNext() { return canNext; },
		get needsProjectSelect() { return needsProjectSelect; },
		// Helpers
		fmtRemaining,
		isExhausted,
		// Lifecycle
		init,
		destroy,
		// Data loading
		ensureStepData,
		retryCurrentStep,
		loadBootOptions,
		loadFlavorOptions,
		loadFlavorQuota,
		loadAdminProjects,
		loadSquashfsCatalog,
		// Actions
		selectAdminProject,
		handleReset,
		nextStep,
		prevStep,
		goTo,
		goToVisible,
		selectImage,
		selectFlavor,
		toggleLibrary,
		selectStrategy,
		selectScheduling,
		selectMountProtocol,
		selectNetwork,
		selectSshAccessMode,
		clearSquashfsSelection,
		selectSquashfsMode,
		selectSquashfsProfile,
		toggleSquashfsArtifact,
		deploy,
	};
}
