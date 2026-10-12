import { t } from '$lib/i18n/ns/vm-wizard';
import { get } from 'svelte/store';
import { goto } from '$app/navigation';
import { setContext, getContext } from 'svelte';
import { wizard, wizardPassword, wizardPasswordRevision, clearWizardPassword, resetWizard, closeWizard } from '$lib/stores/wizard';
import type { WizardState } from '$lib/stores/wizard';
import { api, ApiError, fetchWithAuth, getBaseUrl } from '$lib/api/client';
import { maybeMockInstanceCreateStream } from '$lib/mockup/transport';
import { auth } from '$lib/stores/auth';
import { toast } from '$lib/stores/toast';
import { siteConfig } from '$lib/config/site';
import type { NetworkInfo } from '$lib/types/networks';
import type { SecurityGroup as SecurityGroupInfo } from '$lib/types/securityGroup';
import type { Volume } from '$lib/types/volume';
import type { Keypair } from '$lib/types/keypair';
import { flavorCreateBlock, type FlavorCreateBlock, type FlavorOption } from '$lib/types/flavor';
import type { ImageInfo } from '$lib/types/compute';
import {
	isGithubSshEligible,
	isSshAccessReady,
	isUbuntuImage,
	isWindowsImageMetadata,
	windowsPasswordAccount,
	windowsPasswordError,
	hasWindowsUserDataConflict,
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


export type WizardStepId = 1 | 2 | 5 | 6;

type LoadStatus = 'idle' | 'loading' | 'loaded' | 'error';
type OptionKey =
	| 'images'
	| 'volumes'
	| 'flavors'
	| 'networks'
	| 'keypairs'
	| 'securityGroups'
	| 'defaultNetwork'
	| 'fileStorages';

const OPTION_KEYS: OptionKey[] = [
	'images', 'volumes', 'flavors',
	'networks', 'keypairs', 'securityGroups', 'defaultNetwork',
	'fileStorages',
];
const STEP_LABELS: Record<WizardStepId, string> = {
	get 1() { return t('steps.image'); },
	get 2() { return t('steps.flavor'); },
	get 5() { return t('steps.config'); },
	get 6() { return t('steps.deploy'); },
};


const ALL_PROGRESS_STEPS = [
	{ id: 'manila_preparing', get label() { return t('stages.fileStorage'); }, get description() { return t('stages.fileStorageDescription'); } },
	{ id: 'boot_volume_creating', get label() { return t('stages.bootVolume'); }, get description() { return t('stages.bootVolumeDescription'); } },
	{ id: 'userdata_generating', label: 'cloud-init', get description() { return t('stages.userdataDescription'); } },
	{ id: 'server_creating', get label() { return t('stages.server'); }, get description() { return t('stages.serverDescription'); } },
	{ id: 'attaching_volume', get label() { return t('stages.attachVolume'); }, get description() { return t('stages.attachVolumeDescription'); } },
	{ id: 'floating_ip_creating', get label() { return t('stages.floatingIp'); }, get description() { return t('stages.floatingIpDescription'); } },
	{ id: 'completed', get label() { return t('stages.completed'); }, get description() { return t('stages.completedDescription'); } },
	{ id: 'failed', get label() { return t('stages.failed'); }, get description() { return t('stages.failedDescription'); } },
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
	let authProjectId = $state(get(auth).projectId);
	$effect(() => wizard.subscribe(v => { wizardState = v; }));
	$effect(() => auth.subscribe(v => { authProjectId = v.projectId; }));
	let passwordDraft = $state(get(wizardPassword));
	$effect(() => wizardPassword.subscribe(value => { passwordDraft = value; }));
	let images = $state<ImageInfo[]>([]);
	let flavors = $state<FlavorOption[]>([]);
	let networks = $state<NetworkInfo[]>([]);
	let keypairs = $state<Keypair[]>([]);
	let volumes = $state<Volume[]>([]);
	let fileStorages = $state<{ id: string; name: string; status: string; share_proto: string }[]>([]);
	let securityGroups = $state<SecurityGroupInfo[]>([]);
	let defaultNetworkId = $state<string | null>(null);
	let flavorQuota = $state<FlavorQuotaSummary | null>(null);
	let flavorRefreshing = $state(false);
	let flavorRefreshError = $state<string | null>(null);
	// Periodic refresh state is advisory; only locking refreshes gate admission.
	let flavorBackgroundRefreshing = $state(false);
	let flavorBackgroundRefreshError = $state<string | null>(null);
	let flavorRefreshSeq = 0;
	let flavorRefreshController: AbortController | null = null;
	let submitChecking = false;

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
	function resetFlavorRefresh() {
		flavorRefreshSeq += 1;
		flavorRefreshController?.abort();
		flavorRefreshController = null;
		flavorRefreshing = false;
		flavorRefreshError = null;
		flavorBackgroundRefreshing = false;
		flavorBackgroundRefreshError = null;
	}
	function advanceProjectGeneration() {
		projectLoadController.abort();
		projectLoadController = new AbortController();
		loadGeneration += 1;
		resetFlavorRefresh();
	}
	function optionKeysForStep(step: WizardStepId): OptionKey[] {
		if (step === 1) return ['images', 'volumes'];
		if (step === 2) return ['flavors'];
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
	let currentStep = $state('boot_volume_creating');
	let progress = $state(0);
	let progressMessage = $state('');
	let elapsedSeconds = $state<number | null>(null);
	let stepElapsedSeconds = $state<Record<string, number>>({});
	let progressClock: ReturnType<typeof setInterval> | null = null;
	let elapsedAnchorAt: number | null = null;
	let elapsedAnchorSeconds = 0;
	let timedStep: string | null = null;
	let stepStartedAt = 0;
	let stepElapsedBefore = 0;

	function updateDeploymentClock(now = performance.now()) {
		if (elapsedAnchorAt === null) return;
		elapsedSeconds = elapsedAnchorSeconds + (now - elapsedAnchorAt) / 1000;
		if (timedStep !== null) {
			stepElapsedSeconds[timedStep] = stepElapsedBefore + (now - stepStartedAt) / 1000;
		}
	}

	function stopDeploymentClock() {
		updateDeploymentClock();
		clearInterval(progressClock ?? undefined);
		progressClock = null;
		elapsedAnchorAt = null;
		timedStep = null;
	}

	function startDeploymentClock() {
		stopDeploymentClock();
		elapsedAnchorAt = performance.now();
		elapsedAnchorSeconds = 0;
		elapsedSeconds = 0;
		stepElapsedSeconds = {};
		progressClock = setInterval(updateDeploymentClock, 1000);
	}

	function reportProgress(data: ProgressMessage) {
		const now = performance.now();
		updateDeploymentClock(now);
		// Server elapsed time may advance the total, but never rewind a live clock.
		if (typeof data.elapsed_seconds === 'number' && Number.isFinite(data.elapsed_seconds)
			&& data.elapsed_seconds > (elapsedSeconds ?? 0)) {
			elapsedAnchorSeconds = data.elapsed_seconds;
			elapsedAnchorAt = now;
			elapsedSeconds = data.elapsed_seconds;
		}
		if (data.step !== currentStep || timedStep === null) {
			timedStep = data.step === 'completed' || data.step === 'failed' ? null : data.step;
			if (timedStep !== null) {
				stepStartedAt = now;
				stepElapsedBefore = stepElapsedSeconds[timedStep] ?? 0;
				stepElapsedSeconds[timedStep] = stepElapsedBefore;
			}
		}
		currentStep = data.step;
		progress = data.progress;
		progressMessage = data.message;
		if (data.step === 'completed' || data.step === 'failed') stopDeploymentClock();
	}

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



	const selectedImage = $derived.by(() => (
		wizardState.imageId ? images.find(image => image.id === wizardState.imageId) ?? null : null
	));

	function minBootVolumeSizeFor(w: WizardState): number {
		if (w.bootSource === 'volume') return 1;
		const minimum = images.find(image => image.id === w.imageId)?.min_disk ?? 0;
		return Number.isFinite(minimum) ? Math.max(1, Math.ceil(minimum)) : 1;
	}
	function bootVolumeSizeValid(w: WizardState): boolean {
		return w.bootSource === 'volume' || (
			Number.isFinite(w.bootVolumeSizeGb)
			&& Number.isInteger(w.bootVolumeSizeGb)
			&& w.bootVolumeSizeGb >= minBootVolumeSizeFor(w)
		);
	}
	const minBootVolumeSizeGb = $derived(minBootVolumeSizeFor(wizardState));
	const bootVolumeSizeReady = $derived(bootVolumeSizeValid(wizardState));
	let previousSizeImageId: string | null = null;
	let previousImageMinimum: number | null = null;
	$effect(() => {
		const image = wizardState.bootSource === 'image' ? selectedImage : null;
		const minimum = minBootVolumeSizeGb;
		if (!image) {
			previousSizeImageId = null;
			previousImageMinimum = null;
			return;
		}
		// Raise only on selection/metadata transitions, never while editing the same image's draft.
		if (image.id === previousSizeImageId && minimum === previousImageMinimum) return;
		previousSizeImageId = image.id;
		previousImageMinimum = minimum;
		wizard.update(w => w.bootSource === 'image' && w.imageId === image.id
			&& Number.isFinite(w.bootVolumeSizeGb) && w.bootVolumeSizeGb < minimum
			? { ...w, bootVolumeSizeGb: minimum }
			: w);
	});

	function metadataFor(w: WizardState) {
		return w.bootSource === 'volume'
			? volumes.find(volume => volume.id === w.bootVolumeId)?.volume_image_metadata
			: images.find(image => image.id === w.imageId);
	}
	function bootMetadataReady(w: WizardState): boolean {
		// A retained selection is not ordinary SSH until its authoritative metadata is known.
		if (w.bootSource === 'volume') return !w.bootVolumeId || (optionStatus.volumes === 'loaded' && volumes.some(volume => volume.id === w.bootVolumeId));
		return !w.imageId || (optionStatus.images === 'loaded' && images.some(image => image.id === w.imageId));
	}
	const windowsAccount = $derived(windowsPasswordAccount(metadataFor(wizardState)));
	const isWindowsBoot = $derived(isWindowsImageMetadata(metadataFor(wizardState)));
	const windowsUnsupported = $derived(isWindowsBoot && !windowsAccount);
	const windowsConflict = $derived(Boolean(windowsAccount) && hasWindowsUserDataConflict(wizardState));
	const passwordError = $derived(windowsPasswordError(passwordDraft.password, passwordDraft.confirmation));
	function configurationReady(w: WizardState, draft: typeof passwordDraft): boolean {
		if (!bootMetadataReady(w)) return false;
		const metadata = metadataFor(w);
		if (isWindowsImageMetadata(metadata)) return Boolean(windowsPasswordAccount(metadata))
			&& !windowsPasswordError(draft.password, draft.confirmation) && !hasWindowsUserDataConflict(w);
		return isSshAccessReady({ ...w, adminMode: opts.adminMode() });
	}
	const accessReady = $derived(configurationReady(wizardState, passwordDraft));
	let previousWindowsAccount: string | null = null;
	let previousAdminMode = opts.adminMode();
	$effect(() => {
		const adminMode = opts.adminMode();
		if (adminMode !== previousAdminMode) {
			previousAdminMode = adminMode;
			clearWizardPassword();
		}
		if (windowsAccount !== previousWindowsAccount) {
			previousWindowsAccount = windowsAccount;
			clearWizardPassword();
		}
	});

	const selectedImageIsUbuntu = $derived.by(() => isUbuntuImage(selectedImage, wizardState.imageName));
	const githubSshEligible = $derived.by(() =>
		!isWindowsBoot && isGithubSshEligible({
			adminMode: opts.adminMode(),
			bootSource: wizardState.bootSource,
			selectedImageIsUbuntu,
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
	const progressSteps = $derived(ALL_PROGRESS_STEPS.filter(step =>
		(step.id !== 'manila_preparing' || wizardState.dataMounts.length > 0)
		&& (step.id !== 'userdata_generating' || hasGpuFlavor || wizardState.dataMounts.length > 0)
	));


	const visibleStepIds: WizardStepId[] = [1, 2, 5, 6];
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
		const needsGithubSshReset =
			!githubSshEligible &&
			(wizardState.sshAccessMode !== 'keypair' || wizardState.githubUsername !== '' || wizardState.githubProfile !== null);
		const isVisibleStep = visibleStepIds.includes(wizardState.step as WizardStepId);
		const nextVisibleStep = isVisibleStep
			? null
			: (visibleStepIds.find(step => step > wizardState.step) ?? visibleStepIds[visibleStepIds.length - 1] ?? 1);
		if (!needsGithubSshReset && nextVisibleStep === null) return;
		wizard.update(w => {
			let next = w;
			if (!githubSshEligible && (next.sshAccessMode !== 'keypair' || next.githubUsername !== '' || next.githubProfile !== null)) {
				next = { ...next, sshAccessMode: 'keypair', githubUsername: '', githubProfile: null };
			}
			if (nextVisibleStep !== null && next.step !== nextVisibleStep) {
				next = { ...next, step: nextVisibleStep };
			}
			return next;
		});
	});

	const selectedFlavor = $derived(
		wizardState.flavorId ? flavors.find(f => f.id === wizardState.flavorId) ?? null : null
	);
	// 'missing': the selection is no longer in the current target project's list.
	const selectedFlavorBlock = $derived.by((): FlavorCreateBlock | 'missing' | null => {
		if (!wizardState.flavorId) return null;
		if (!selectedFlavor) return 'missing';
		return flavorCreateBlock(selectedFlavor);
	});
	const flavorAdmissionReady = $derived(
		Boolean(wizardState.flavorId)
			&& optionStatus.flavors === 'loaded'
			&& !flavorRefreshing
			&& !flavorRefreshError
			&& selectedFlavorBlock === null
	);

	const canNext = $derived((() => {
		if (windowsUnsupported) return false;
		switch (wizardState.step) {
			case 1: return wizardState.bootSource === 'volume' ? !!wizardState.bootVolumeId : !!wizardState.imageId;
			case 2: return flavorAdmissionReady;
			case 5:
				return accessReady && bootVolumeSizeReady;
			case 6: return flavorAdmissionReady && bootMetadataReady(wizardState) && bootVolumeSizeReady && (!isWindowsBoot || accessReady);
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


	function optionError(error: unknown): string {
		return error instanceof ApiError ? t('options.loadFailed', { status: error.status }) : t('options.serverError');
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
			(signal) => api.get<ImageInfo[]>('/api/v1/images', token, projectId, { signal }),
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

	/** Flavor eligibility and host capacity for the current target project's create admission snapshot. */
	// Never prefetch capacity URLs: client.ts getOrdinary serves warm entries before dispatch, and only prefetchJson publishes them.
	function flavorRequestScope(): {
		key: string;
		request: (signal?: AbortSignal, refresh?: boolean) => Promise<FlavorOption[]>;
		isCurrent: () => boolean;
	} | null {
		const { token, projectId } = authScope();
		const generation = loadGeneration;
		if (opts.adminMode()) {
			const targetProjectId = adminSelectedProjectId;
			if (!targetProjectId) return null;
			return {
				key: targetProjectId,
				request: (signal, refresh) => api.get<FlavorOption[]>(
					`/api/v1/admin/instances/flavors-for-project?project_id=${encodeURIComponent(targetProjectId)}&capacity=create`,
					token,
					projectId,
					refresh ? { signal, refresh: true } : { signal },
				),
				isCurrent: () => targetIsCurrent(targetProjectId, generation),
			};
		}
		return {
			key: `public:${projectId ?? ''}`,
			request: (signal, refresh) => api.get<FlavorOption[]>('/api/v1/flavors?capacity=create', token, projectId,
				refresh ? { signal, refresh: true } : { signal }),
			isCurrent: () => authProjectIsCurrent(projectId, generation),
		};
	}

	function loadFlavorOptions() {
		if (destroyed) return Promise.resolve();
		const scope = flavorRequestScope();
		if (!scope) return Promise.resolve();
		// A refresh started after this request owns the newer snapshot and the load status.
		const refreshSeq = flavorRefreshSeq;
		return loadOption(
			'flavors',
			scope.key,
			scope.request,
			value => { flavors = value; },
			() => scope.isCurrent() && refreshSeq === flavorRefreshSeq,
		);
	}

	/**
	 * Re-reads flavor eligibility/capacity without hiding the current list. Resolves true only when a
	 * fresh snapshot for the unchanged target project was applied. Periodic rounds never overlap a
	 * pending load or refresh; manual and submit refreshes supersede an older refresh.
	 */
	async function refreshFlavorOptions(mode: 'manual' | 'periodic' | 'submit' = 'manual'): Promise<boolean> {
		if (destroyed) return false;
		const scope = flavorRequestScope();
		if (!scope) return false;
		if (mode === 'periodic' && (
			flavorRefreshing || flavorBackgroundRefreshing
			|| (optionStatus.flavors !== 'loaded' && optionStatus.flavors !== 'error')
			|| optionRequests.has(`flavors:${scope.key}:${loadGeneration}`)
		)) return false;
		flavorRefreshController?.abort();
		const controller = new AbortController();
		flavorRefreshController = controller;
		const projectSignal = projectLoadController.signal;
		const abortWithProject = () => controller.abort();
		projectSignal.addEventListener('abort', abortWithProject, { once: true });
		const seq = ++flavorRefreshSeq;
		const isCurrent = () => !destroyed && seq === flavorRefreshSeq && scope.isCurrent();
		const background = mode === 'periodic';
		flavorRefreshing = !background;
		flavorBackgroundRefreshing = background;
		flavorBackgroundRefreshError = null;
		if (!background) flavorRefreshError = null;
		try {
			const value = await scope.request(controller.signal, mode === 'manual');
			if (!isCurrent()) return false;
			flavors = value;
			optionStatus.flavors = 'loaded';
			delete optionErrors.flavors;
			flavorRefreshError = null;
			return true;
		} catch (error) {
			if (!isCurrent()) return false;
			if (error instanceof DOMException && error.name === 'AbortError') return false;
			const message = optionError(error);
			if (background) {
				flavorBackgroundRefreshError = message;
			} else if (optionStatus.flavors === 'loaded') {
				flavorRefreshError = message;
			} else {
				optionErrors.flavors = message;
				optionStatus.flavors = 'error';
			}
			return false;
		} finally {
			projectSignal.removeEventListener('abort', abortWithProject);
			if (seq === flavorRefreshSeq) {
				flavorRefreshing = false;
				flavorBackgroundRefreshing = false;
				flavorRefreshController = null;
			}
		}
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
		clearWizardPassword();
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
		networks = [];
		keypairs = [];
		securityGroups = [];
		fileStorages = [];
		defaultNetworkId = null;
		flavorQuota = null;
		resetWizard();
	}

	function ensureStepData(step: WizardStepId) {
		if (destroyed) return;
		if (step === 1) void loadBootOptions();
		if (step === 2) void loadFlavorOptions();
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
		if (!canNext) return;
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
		nextStep();
	}
	function selectFlavor(id: string, name: string) {
		if (flavorRefreshing || flavorRefreshError || optionStatus.flavors !== 'loaded') return;
		const selected = flavors.find(candidate => candidate.id === id);
		if (!selected || flavorCreateBlock(selected) !== null) return;
		wizard.update(w => ({ ...w, flavorId: id, flavorName: name }));
		nextStep();
	}


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
			githubProfile: mode === 'keypair' ? null : w.githubProfile,
		}));
	}


	async function deploy() {
		if (destroyed || deploying || submitChecking) return;
		if (!bootMetadataReady(get(wizard))) {
			goTo(1);
			return;
		}
		if (!bootVolumeSizeValid(get(wizard))) {
			goTo(5);
			return;
		}
		if (isWindowsImageMetadata(metadataFor(get(wizard))) && !configurationReady(get(wizard), get(wizardPassword))) {
			goTo(5);
			return;
		}
		// Revalidate the selected flavor against the create-capacity snapshot right before the mutation.
		const checked = get(wizard);
		const checkedGeneration = loadGeneration;
		const checkedTargetProjectId = adminSelectedProjectId;
		const checkedAuthProjectId = get(auth).projectId;
		const checkedActor = JSON.stringify([get(auth).userId, get(auth).token, get(auth).projectId]);
		const checkedPasswordRevision = wizardPasswordRevision;
		const checkedAdminMode = opts.adminMode();
		const checkedWindowsAccount = windowsPasswordAccount(metadataFor(checked));
		submitChecking = true;
		let refreshed = false;
		try {
			refreshed = await refreshFlavorOptions('submit');
		} finally {
			submitChecking = false;
		}
		if (
			destroyed
			|| deploying
			|| checkedGeneration !== loadGeneration
			|| checkedTargetProjectId !== adminSelectedProjectId
			|| (!opts.adminMode() && checkedAuthProjectId !== get(auth).projectId)
			|| get(wizard).flavorId !== checked.flavorId
			|| checkedActor !== JSON.stringify([get(auth).userId, get(auth).token, get(auth).projectId])
			|| checkedAdminMode !== opts.adminMode()
			|| checkedPasswordRevision !== wizardPasswordRevision
			|| checked.bootSource !== get(wizard).bootSource
			|| checked.imageId !== get(wizard).imageId
			|| checked.bootVolumeId !== get(wizard).bootVolumeId
			|| checkedWindowsAccount !== windowsPasswordAccount(metadataFor(get(wizard)))
		) {
			return;
		}
		const admitted = flavors.find(candidate => candidate.id === checked.flavorId);
		if (!refreshed || !admitted || flavorCreateBlock(admitted) !== null) {
			// SelectFlavor explains the refresh failure or the newly blocked selection; the user chooses again.
			goTo(2);
			return;
		}
		if (!bootMetadataReady(get(wizard))) {
			goTo(1);
			return;
		}
		if (!bootVolumeSizeValid(get(wizard))) {
			goTo(5);
			return;
		}
		if (isWindowsImageMetadata(metadataFor(get(wizard))) && !configurationReady(get(wizard), get(wizardPassword))) {
			goTo(5);
			return;
		}
		deployController?.abort();
		deployController = new AbortController();
		deployError = '';
		deploying = true;
		currentStep = 'boot_volume_creating';
		progress = 0;
		progressMessage = t('deploy.starting');
		startDeploymentClock();

		const baseUrl = getBaseUrl();
		const authState = get(auth);
		const endpoint = opts.adminMode()
			? '/api/v1/admin/instances/async'
			: '/api/v1/instances/async';

		const w = get(wizard);
		const windowsMode = Boolean(windowsPasswordAccount(metadataFor(w)));
		const requestedName = normalizeRequestedInstanceName(w.instanceName);
		const githubUsername = !windowsMode && w.sshAccessMode === 'github'
			? normalizeGithubUsername(w.githubUsername) || null
			: null;
		const keyName = windowsMode || w.sshAccessMode === 'github' ? null : w.keyName || null;
		const body: Record<string, unknown> = {
			name: requestedName,
			...(windowsMode ? { admin_pass: get(wizardPassword).password } : {}),
			...(w.bootSource === 'volume'
				? { boot_volume_id: w.bootVolumeId }
				: {
					image_id: w.imageId,
					boot_volume_size_gb: w.bootVolumeSizeGb,
					delete_boot_volume_on_termination: w.deleteBootVolumeOnTermination,
				}),
			flavor_id: w.flavorId,
			network_id: w.networkId,
			key_name: keyName,
			github_username: githubUsername,
			security_groups: w.securityGroups,
			userdata: windowsMode ? null : w.cloudInit || null,
			data_mounts: windowsMode ? [] : w.dataMounts.map(m => ({
				file_storage_id: m.fileStorageId,
				mount_point: m.mountPoint,
				read_only: m.readOnly,
			})),
		};
		if (opts.adminMode() && adminSelectedProjectId) {
			body.project_id = adminSelectedProjectId;
		}
		const requestBody = JSON.stringify(body);
		delete body.admin_pass;
		clearWizardPassword();

		// mockup 모드: 실제 API 대신 가상 SSE 스트림으로 배포 흐름 재현
		const mockStream = maybeMockInstanceCreateStream(
			opts.adminMode() ? '/api/v1/admin/instances/async' : '/api/v1/instances/async',
			body,
		);
		if (mockStream) {
			for await (const data of mockStream) {
				if (destroyed) return;
				reportProgress(data);
			}
			stopDeploymentClock();
			toast.success(t('toast.created'));
			// 완료 보고는 root layout 의 Toast 가 이어받는다. 타이머로 사용자를 이동시키지 않는다 (WCAG 2.2.1).
			if (!destroyed) {
				resetWizard();
				adminSelectedProjectId = null;
				adminSelectedProjectName = null;
				closeWizard();
				goto(opts.adminMode() ? '/admin/instances' : '/dashboard/compute/instances');
			}
			return;
		}

		try {
			const response = await fetchWithAuth(endpoint, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
				body: requestBody,
				signal: deployController.signal,
			}, authState.token ?? undefined, authState.projectId ?? undefined, { baseUrl });
			if (destroyed) return;
			if (!response.ok) {
				const text = await response.text();
				throw new ApiError(response.status, text || response.statusText);
			}
			const reader = response.body?.getReader();
			if (!reader) throw new Error(t('deploy.noResponseBody'));
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
							reportProgress(data);
							if (data.step === 'completed') {
								toast.success(t('toast.created'));
								// 완료 보고는 root layout 의 Toast 가 이어받는다. 타이머로 사용자를 이동시키지 않는다 (WCAG 2.2.1).
								if (!destroyed) {
									resetWizard();
									adminSelectedProjectId = null;
									adminSelectedProjectName = null;
									closeWizard();
									goto(opts.adminMode() ? '/admin/instances' : '/dashboard/compute/instances');
								}
								return;
							}
							if (data.step === 'failed') {
								deployError = data.error || data.message;
								toast.error(t('toast.createFailed', { error: deployError }));
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
				? t('deploy.failed', { message: e.message })
				: t('deploy.connectionError', { message: e instanceof Error ? e.message : t('deploy.unknownError') });
			deploying = false;
		} finally {
			stopDeploymentClock();
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
		clearWizardPassword();
		initialized = false;
		projectLoadController.abort();
		stopDeploymentClock();
		deployController?.abort();
		deployController = null;
		loadGeneration += 1;
		resetFlavorRefresh();
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
		get networks() { return networks; },
		get keypairs() { return keypairs; },
		get volumes() { return volumes; },
		get fileStorages() { return fileStorages; },
		get securityGroups() { return securityGroups; },
		get defaultNetworkId() { return defaultNetworkId; },
		get flavorQuota() { return flavorQuota; },
		get flavorRefreshing() { return flavorRefreshing; },
		get flavorRefreshError() { return flavorRefreshError; },
		get flavorBackgroundRefreshing() { return flavorBackgroundRefreshing; },
		get flavorBackgroundRefreshError() { return flavorBackgroundRefreshError; },
		get selectedFlavor() { return selectedFlavor; },
		get selectedFlavorBlock() { return selectedFlavorBlock; },
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
		get stepElapsedSeconds() { return stepElapsedSeconds; },
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
		get selectedNetwork() { return selectedNetwork; },
		get selectedImage() { return selectedImage; },
		get minBootVolumeSizeGb() { return minBootVolumeSizeGb; },
		get bootVolumeSizeReady() { return bootVolumeSizeReady; },
		get selectedImageIsUbuntu() { return selectedImageIsUbuntu; },
		get githubSshEligible() { return githubSshEligible; },
		get windowsAccount() { return windowsAccount; },
		get isWindowsBoot() { return isWindowsBoot; },
		get windowsUnsupported() { return windowsUnsupported; },
		get windowsConflict() { return windowsConflict; },
		get passwordError() { return passwordError; },
		get hasGpuFlavor() { return hasGpuFlavor; },
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
		refreshFlavorOptions,
		loadFlavorQuota,
		loadAdminProjects,
		// Actions
		selectAdminProject,
		handleReset,
		nextStep,
		prevStep,
		goTo,
		goToVisible,
		selectImage,
		selectFlavor,
		selectNetwork,
		selectSshAccessMode,
		deploy,
	};
}
