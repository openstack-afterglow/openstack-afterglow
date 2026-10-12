import type { GithubSshProfile } from '$lib/types/compute';
import { writable } from 'svelte/store';
import { sidebarOpen } from './sidebar';
import { auth } from './auth';

// Deliberately separate from WizardState/prefill and never written to browser storage.
export const wizardPassword = writable({ password: '', confirmation: '' });
export let wizardPasswordRevision = 0;
wizardPassword.subscribe(() => { wizardPasswordRevision += 1; });

export function clearWizardPassword() {
	wizardPassword.set({ password: '', confirmation: '' });
}

let passwordActor = '';
auth.subscribe(value => {
	const actor = JSON.stringify([value.userId, value.projectId, value.token]);
	if (actor !== passwordActor) {
		passwordActor = actor;
		clearWizardPassword();
	}
});

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
	clearWizardPassword();
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
	instanceName: string;
	networkId: string | null;
	networkName: string | null;
	keyName: string | null;
	sshAccessMode: 'keypair' | 'github';
	githubUsername: string;
	githubProfile: GithubSshProfile | null;


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
	instanceName: '',
	networkId: null,
	networkName: null,
	keyName: null,
	sshAccessMode: 'keypair',
	githubUsername: '',
	githubProfile: null,

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

let passwordBootIdentity = '';
wizard.subscribe(value => {
	const identity = JSON.stringify([value.bootSource, value.bootSource === 'image' ? value.imageId : value.bootVolumeId, value.targetProjectId]);
	if (identity !== passwordBootIdentity) {
		passwordBootIdentity = identity;
		clearWizardPassword();
	}
});
wizardOpen.subscribe(open => { if (!open) clearWizardPassword(); });

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
	clearWizardPassword();
	wizard.set({ ...initial });
}
