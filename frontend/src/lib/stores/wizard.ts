import { writable } from 'svelte/store';
import { sidebarOpen } from './sidebar';

export const wizardOpen = writable<boolean>(false);

export interface WizardOpenOptions {
	targetProjectId?: string;
	prefill?: Partial<WizardState>;
}

export function openWizard(opts?: WizardOpenOptions) {
	if (opts?.targetProjectId !== undefined || opts?.prefill) {
		wizard.update(w => ({
			...w,
			targetProjectId: opts?.targetProjectId ?? null,
			...(opts?.prefill ?? {}),
		}));
	}
	sidebarOpen.close();
	wizardOpen.set(true);
}

export function closeWizard() {
	wizardOpen.set(false);
}

export interface NewVolumeSpec {
	name: string;
	size_gb: number;
}

export interface DataMountSpec {
	fileStorageId: string;
	mountPoint: string;
	readOnly: boolean;
}

export interface WizardState {
	step: number;
	bootSource: 'image' | 'volume';
	imageId: string | null;
	imageName: string | null;
	bootVolumeId: string | null;
	bootVolumeName: string | null;
	flavorId: string | null;
	flavorName: string | null;
	libraries: string[];
	strategy: 'prebuilt' | 'dynamic' | null;
	scheduling: 'standard' | 'ha';
	mountProtocol: 'CEPHFS' | 'NFS';
	templateName: string | null;
	templateVersion: number | null;
	squashfsMode: 'profile' | 'artifacts' | null;
	layerProfileName: string | null;
	layerArtifactIds: number[];
	instanceName: string;
	networkId: string | null;
	networkName: string | null;
	keyName: string | null;
	sshAccessMode: 'keypair' | 'github';
	githubUsername: string;

	securityGroups: string[];
	cloudInit: string;
	bootVolumeSizeGb: number;
	deleteBootVolumeOnTermination: boolean;
	additionalVolumeIds: string[];
	newVolumes: NewVolumeSpec[];
	dataMounts: DataMountSpec[];
	targetProjectId: string | null;
}

const initial: WizardState = {
	step: 1,
	bootSource: 'image',
	imageId: null,
	imageName: null,
	bootVolumeId: null,
	bootVolumeName: null,
	flavorId: null,
	flavorName: null,
	libraries: [],
	strategy: null,
	scheduling: 'standard',
	mountProtocol: 'NFS',
	templateName: null,
	templateVersion: null,
	squashfsMode: null,
	layerProfileName: null,
	layerArtifactIds: [],
	instanceName: '',
	networkId: null,
	networkName: null,
	keyName: null,
	sshAccessMode: 'keypair',
	githubUsername: '',
	securityGroups: [],
	cloudInit: '',
	bootVolumeSizeGb: 20,
	deleteBootVolumeOnTermination: false,
	additionalVolumeIds: [],
	newVolumes: [],
	dataMounts: [],
	targetProjectId: null,
};

export const wizard = writable<WizardState>({ ...initial });

// 위저드 단계가 바뀔 때마다 단 하나의 모듈 레벨 구독에서 이벤트를 발행한다.
// 튜토리얼 엔진이 이 이벤트로 팝오버를 현재 위저드 단계에 동기화한다(중복 구독 금지).
if (typeof window !== 'undefined') {
	let lastWizardStep: number | null = null;
	wizard.subscribe((w) => {
		if (w.step !== lastWizardStep) {
			lastWizardStep = w.step;
			window.dispatchEvent(new CustomEvent('afterglow:wizard-step', { detail: { step: w.step } }));
		}
	});
}

export function resetWizard() {
	wizard.set({ ...initial });
}
