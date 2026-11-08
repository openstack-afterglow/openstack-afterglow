import { get } from 'svelte/store';
import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/tutorial';
import { bucketSteps } from './steps/storage';
import { containerSteps } from './steps/containers';
import { secretSteps, volumeBackupSteps } from './steps/storage-secrets';
import { iamProjectSteps } from './steps/identity';
import { keypairSteps, floatingIpSteps, securityGroupSteps, networkSteps } from './steps/compute-network';
import { fileStorageSteps, volumeSnapshotSteps } from './steps/storage-files';
import { loadBalancerSteps, routerSteps } from './steps/network-lb-router';
import { containerClusterSteps, databaseInstanceSteps } from './steps/database-containers';
import { databaseBackupSteps } from './steps/database-backups';
import { instanceDetailDeleteSteps } from './steps/compute-instances';
import { adminProjectSteps, adminFlavorSteps, adminNetworkLifecycleSteps, adminRouterSteps, adminFloatingIpSteps } from './steps/admin-resources';
import { adminAnnouncementSteps } from './steps/admin-announcements';
import { accountMcpSteps, adminApplicationCredentialSteps } from './steps/identity-admin';
import { adminObjectStorageSteps } from './steps/admin-object-storage';
import { adminPortSteps } from './steps/admin-ports';
import { adminUserSteps } from './steps/admin-users';
import { adminGroupSteps } from './steps/admin-groups';
import { adminRoleSteps } from './steps/admin-roles';
import { adminDomainSteps } from './steps/admin-domains';
import { adminSystemAdminSteps } from './steps/admin-system-admins';
import { adminUserCredentialSteps } from './steps/admin-user-credentials';
import { adminSettingsSteps } from './steps/admin-settings';

export const TOUR_IDS = [
	'vm-create',
	'instance-detail-delete',
	'volume',
	'buckets',
	'containers',
	'secrets',
	'volume-backups',
	'iam-projects',
	'keypairs',
	'floating-ips',
	'security-groups',
	'networks',
	'volume-snapshots',
	'file-storage',
	'load-balancers',
	'routers',
	'containers-clusters',
	'database-instances',
	'database-backups',
	'drover',
	'waygate',
	'images',
	'admin-images',
	'admin-compute',
	'admin-storage',
	'admin-library',
	'admin-waygate',
	'admin-network',
	'admin-containers',
	'admin-key-manager',
	'admin-monitoring',
	'admin-system',
	'admin-identity',
	'admin-projects',
	'admin-flavors',
	'admin-networks',
	'admin-routers',
	'admin-floating-ips',
	'admin-ports',
	'admin-users',
	'admin-groups',
	'admin-roles',
	'admin-domains',
	'admin-system-admins',
	'admin-user-credentials',
	'admin-settings',
	'admin-announcements',
	'admin-application-credentials',
	'admin-object-storage',
	'account-mcp',
] as const;

export type TourId = (typeof TOUR_IDS)[number];

export const TOUR_QUERY_KEY = 'tour';
export const TOUR_STORAGE_KEY = 'afterglow_tour';

export interface TourStep {
	/** data-tour 앵커 셀렉터 (하이라이트 대상) */
	element: string;
	/** 이 step을 보여주기 전에 이동할 경로 */
	route?: string;
	/** 하이라이트 직전 실행. 모바일 드로어 열기 등 사전 준비용. route 이동/auto-close 이후에 실행된다. */
	prepare?: () => void | Promise<void>;
	/** route 이동 뒤 skipReadyElement 대기 전에 실행. 숨겨진 탭을 먼저 여는 용도. */
	beforeReady?: () => void | Promise<void>;
	title: string;
	description: string;
	/** Pins the popover above or below the highlight when automatic placement covers the advance control. */
	popoverSide?: 'top' | 'bottom';
	/**
	 * 'click'이면 실제 클릭으로 다음 step 진행 (팝오버 '다음' 버튼 없음).
	 * 'wizard'이면 위저드 단계(wizardStep) 변화를 따라 팝오버가 이동한다(자체 '다음' 버튼 없음).
	 */
	advanceOn?: 'click' | 'wizard';
	/** 이 팝오버가 대응하는 위저드 raw 단계 번호($wizard.step). 엔진이 afterglow:wizard-step 이벤트로 매핑한다. */
	wizardStep?: number;
	/** Keep wizard correction events synchronized while awaiting deployment settlement. */
	followWizard?: () => boolean | Promise<boolean>;
	/** 진행 트리거 셀렉터 — 생략 시 element 자체 클릭으로 진행 */
	advanceElement?: string;
	/** 이 셀렉터 클릭 시 투어를 한 단계 뒤로 (예: 위저드 "← 이전" 버튼) */
	backElement?: string;
	/** 이 셀렉터 클릭 시 투어를 종료 (예: 위저드 "취소"/닫기 버튼) */
	cancelElement?: string;
	/** 하이라이트 전에 이 요소가 나타날 때까지 대기 (로딩 상태 회피용) */
	readyElement?: string;
	/** skipIf 평가 전에 이 요소가 나타날 때까지 대기 (재개 시 로딩/빈 목록 구분용) */
	skipReadyElement?: string;
	/** 표시 시점에 true면 이 step을 건너뛴다 (진행 방향 유지) */
	skipIf?: () => boolean;
	/** click-driven 단계에서도 팝오버의 이전 버튼을 노출 */
	showPrevious?: boolean;
	/** 강조한 영역 안의 모든 클릭·키보드 활성화를 막는다(읽기 전용 안내가 실제 버튼을 포함할 때) */
	readOnly?: boolean;
	waitTimeoutMs?: number;
	/** 대기 중 이 셀렉터에 맞는 요소가 새로 나타나면(단계 시작 시점에 이미 있던 요소는 제외) 이전 단계로 되돌린다. 예: 생성 실패 오류 알림 */
	rewindOnNew?: string;
	/** readyElement 대기 중에도 대상을 조작할 수 있게 둔다(대기를 끝내는 입력이 대상 안에 있을 때만) */
	waitAllowsInput?: boolean;
}

export interface TourDefinition {
	id: TourId;
	label: string;
	summary: string;
	steps: TourStep[];
}

const TOUR_META: Record<TourId, { label: string; summary: string }> = {
	'vm-create': { get label() { return t('tours.vmCreate.label'); }, get summary() { return t('tours.vmCreate.summary'); } },
	'instance-detail-delete': { get label() { return t('tours.instanceDetailDelete.label'); }, get summary() { return t('tours.instanceDetailDelete.summary'); } },
	volume: { get label() { return t('tours.volume.label'); }, get summary() { return t('tours.volume.summary'); } },
	buckets: { get label() { return t('tours.buckets.label'); }, get summary() { return t('tours.buckets.summary'); } },
	containers: { get label() { return t('tours.containers.label'); }, get summary() { return t('tours.containers.summary'); } },
	secrets: { get label() { return t('tours.secrets.label'); }, get summary() { return t('tours.secrets.summary'); } },
	'volume-backups': { get label() { return t('tours.volumeBackups.label'); }, get summary() { return t('tours.volumeBackups.summary'); } },
	'iam-projects': { get label() { return t('tours.iamProjects.label'); }, get summary() { return t('tours.iamProjects.summary'); } },
	keypairs: { get label() { return t('tours.keypairs.label'); }, get summary() { return t('tours.keypairs.summary'); } },
	'floating-ips': { get label() { return t('tours.floatingIps.label'); }, get summary() { return t('tours.floatingIps.summary'); } },
	'security-groups': { get label() { return t('tours.securityGroups.label'); }, get summary() { return t('tours.securityGroups.summary'); } },
	networks: { get label() { return t('tours.networks.label'); }, get summary() { return t('tours.networks.summary'); } },
	'volume-snapshots': { get label() { return t('tours.volumeSnapshots.label'); }, get summary() { return t('tours.volumeSnapshots.summary'); } },
	'file-storage': { get label() { return t('tours.fileStorage.label'); }, get summary() { return t('tours.fileStorage.summary'); } },
	'load-balancers': { get label() { return t('tours.loadBalancers.label'); }, get summary() { return t('tours.loadBalancers.summary'); } },
	routers: { get label() { return t('tours.routers.label'); }, get summary() { return t('tours.routers.summary'); } },
	'containers-clusters': { get label() { return t('tours.containersClusters.label'); }, get summary() { return t('tours.containersClusters.summary'); } },
	'database-instances': { get label() { return t('tours.databaseInstances.label'); }, get summary() { return t('tours.databaseInstances.summary'); } },
	'database-backups': { get label() { return t('tours.databaseBackups.label'); }, get summary() { return t('tours.databaseBackups.summary'); } },
	drover: { get label() { return t('tours.drover.label'); }, get summary() { return t('tours.drover.summary'); } },
	waygate: { get label() { return t('tours.waygate.label'); }, get summary() { return t('tours.waygate.summary'); } },
	images: { get label() { return t('tours.images.label'); }, get summary() { return t('tours.images.summary'); } },
	'admin-images': { get label() { return t('tours.adminImages.label'); }, get summary() { return t('tours.adminImages.summary'); } },
	'admin-compute': {
		get label() { return t('tours.adminCompute.label'); },
		get summary() { return t('tours.adminCompute.summary'); },
	},
	'admin-storage': {
		get label() { return t('tours.adminStorage.label'); },
		get summary() { return t('tours.adminStorage.summary'); },
	},
	'admin-library': {
		get label() { return t('tours.adminLibrary.label'); },
		get summary() { return t('tours.adminLibrary.summary'); },
	},
	'admin-waygate': { get label() { return t('tours.adminWaygate.label'); }, get summary() { return t('tours.adminWaygate.summary'); } },
	'admin-network': {
		get label() { return t('tours.adminNetwork.label'); },
		get summary() { return t('tours.adminNetwork.summary'); },
	},
	'admin-containers': {
		get label() { return t('tours.adminContainers.label'); },
		get summary() { return t('tours.adminContainers.summary'); },
	},
	'admin-key-manager': {
		get label() { return t('tours.adminKeyManager.label'); },
		get summary() { return t('tours.adminKeyManager.summary'); },
	},
	'admin-monitoring': {
		get label() { return t('tours.adminMonitoring.label'); },
		get summary() { return t('tours.adminMonitoring.summary'); },
	},
	'admin-system': {
		get label() { return t('tours.adminSystem.label'); },
		get summary() { return t('tours.adminSystem.summary'); },
	},
	'admin-identity': {
		get label() { return t('tours.adminIdentity.label'); },
		get summary() { return t('tours.adminIdentity.summary'); },
	},
	'admin-projects': { get label() { return t('tours.adminProjects.label'); }, get summary() { return t('tours.adminProjects.summary'); } },
	'admin-flavors': { get label() { return t('tours.adminFlavors.label'); }, get summary() { return t('tours.adminFlavors.summary'); } },
	'admin-networks': { get label() { return t('tours.adminNetworks.label'); }, get summary() { return t('tours.adminNetworks.summary'); } },
	'admin-routers': { get label() { return t('tours.adminRouters.label'); }, get summary() { return t('tours.adminRouters.summary'); } },
	'admin-floating-ips': { get label() { return t('tours.adminFloatingIps.label'); }, get summary() { return t('tours.adminFloatingIps.summary'); } },
	'admin-ports': { get label() { return t('tours.adminPorts.label'); }, get summary() { return t('tours.adminPorts.summary'); } },
	'admin-users': { get label() { return t('tours.adminUsers.label'); }, get summary() { return t('tours.adminUsers.summary'); } },
	'admin-groups': { get label() { return t('tours.adminGroups.label'); }, get summary() { return t('tours.adminGroups.summary'); } },
	'admin-roles': { get label() { return t('tours.adminRoles.label'); }, get summary() { return t('tours.adminRoles.summary'); } },
	'admin-domains': { get label() { return t('tours.adminDomains.label'); }, get summary() { return t('tours.adminDomains.summary'); } },
	'admin-system-admins': { get label() { return t('tours.adminSystemAdmins.label'); }, get summary() { return t('tours.adminSystemAdmins.summary'); } },
	'admin-user-credentials': { get label() { return t('tours.adminUserCredentials.label'); }, get summary() { return t('tours.adminUserCredentials.summary'); } },
	'admin-settings': { get label() { return t('tours.adminSettings.label'); }, get summary() { return t('tours.adminSettings.summary'); } },
	'admin-announcements': { get label() { return t('tours.adminAnnouncements.label'); }, get summary() { return t('tours.adminAnnouncements.summary'); } },
	'admin-application-credentials': { get label() { return t('tours.adminApplicationCredentials.label'); }, get summary() { return t('tours.adminApplicationCredentials.summary'); } },
	'admin-object-storage': { get label() { return t('tours.adminObjectStorage.label'); }, get summary() { return t('tours.adminObjectStorage.summary'); } },
	'account-mcp': { get label() { return t('tours.accountMcp.label'); }, get summary() { return t('tours.accountMcp.summary'); } },
};

/** VM 생성 투어 — Flavor → 이미지 → 설정 → 배포의 raw 단계 2, 1, 5, 6을 따라 진행한다. */
function vmCreateSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="vm-create-open"]',
			route: '/dashboard/compute/instances',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.vmCreate.step1.title'); },
			get description() { return t('tours.vmCreate.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="wizard-panel"]',
			get title() { return t('tours.vmCreate.step3.title'); },
			get description() { return t('tours.vmCreate.step3.description'); },
			advanceOn: 'wizard',
			wizardStep: 2,
			cancelElement: '[data-tour="wizard-cancel"]',
			// 위저드 데이터 로딩이 끝나 본문이 나타난 뒤에 하이라이트한다
			readyElement: '[data-tour="wizard-body"]',
			waitTimeoutMs: 20000,
		},
		{
			element: '[data-tour="wizard-panel"]',
			get title() { return t('tours.vmCreate.step2.title'); },
			get description() { return t('tours.vmCreate.step2.description'); },
			advanceOn: 'wizard',
			wizardStep: 1,
			cancelElement: '[data-tour="wizard-cancel"]',
		},
		{
			element: '[data-tour="wizard-panel"]',
			get title() { return t('tours.vmCreate.step5.title'); },
			get description() { return t('tours.vmCreate.step5.description'); },
			advanceOn: 'wizard',
			wizardStep: 5,
			cancelElement: '[data-tour="wizard-cancel"]',
		},
		{
			element: '[data-tour="wizard-panel"]',
			get title() { return t('tours.vmCreate.step6.title'); },
			get description() { return t('tours.vmCreate.step6.description'); },
			wizardStep: 6,
			advanceOn: 'click',
			advanceElement: '[data-tour="wizard-next"]',
			cancelElement: '[data-tour="wizard-cancel"]',
		},
		{
			element: '[data-tour="instance-list"]',
			followWizard: async () => {
				// Shared catalog readers must not eagerly initialize the browser wizard runtime.
				const { wizardOpen } = await import('$lib/stores/wizard');
				return get(wizardOpen);
			},
			cancelElement: '[data-tour="wizard-cancel"]',
			beforeReady: async () => {
				// The API client's tutorial catalog also loads this module outside the browser wizard runtime.
				const { wizardOpen } = await import('$lib/stores/wizard');
				if (!get(wizardOpen)) return;
				const { promise, resolve } = Promise.withResolvers<void>();
				const unsubscribe = wizardOpen.subscribe(open => {
					if (!open) { unsubscribe(); resolve(); }
				});
				await promise;
			},
			get title() { return t('tours.vmCreate.step7.title'); },
			get description() { return t('tours.vmCreate.step7.description'); },
			waitTimeoutMs: 20000,
		},
	];
}

function volumeSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="volume-create-open"]',
			route: '/dashboard/volumes',
			get title() { return t('tours.volume.step1.title'); },
			get description() { return t('tours.volume.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="volume-create-form"]',
			get title() { return t('tours.volume.step2.title'); },
			get description() { return t('tours.volume.step2.description'); },
			advanceOn: 'click',
			advanceElement: '[data-tour="volume-create-submit"]',
		},
		{
			element: '[data-tour="volume-list"]',
			get title() { return t('tours.volume.step3.title'); },
			get description() { return t('tours.volume.step3.description'); },
		},
	];
}

function droverSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="drover-create-open"]',
			route: '/dashboard/drover',
			get title() { return t('tours.drover.step1.title'); },
			get description() { return t('tours.drover.step1.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="drover-name"]',
			get title() { return t('tours.drover.step2.title'); },
			get description() { return t('tours.drover.step2.description'); },
		},
		{
			element: '[data-tour="drover-os"]',
			get title() { return t('tours.drover.step3.title'); },
			get description() { return t('tours.drover.step3.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="drover-masters"]',
			get title() { return t('tours.drover.step4.title'); },
			get description() { return t('tours.drover.step4.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="drover-agents"]',
			get title() { return t('tours.drover.step5.title'); },
			get description() { return t('tours.drover.step5.description'); },
		},
		{
			element: '[data-tour="drover-flavor"]',
			get title() { return t('tours.drover.step6.title'); },
			get description() { return t('tours.drover.step6.description'); },
		},
		{
			element: '[data-tour="drover-create-submit"]',
			get title() { return t('tours.drover.step7.title'); },
			get description() { return t('tours.drover.step7.description'); },
			advanceOn: 'click',
		},
		{
			element: '[data-tour="drover-progress"]',
			get title() { return t('tours.drover.step8.title'); },
			get description() { return t('tours.drover.step8.description'); },
		},
	];
}

function clickTourElement(selector: string): void {
	if (typeof document === 'undefined') return;
	const element = document.querySelector<HTMLElement>(selector);
	if (!element || element.closest('[inert]')) return;
	element.click();
}

function isTourElementMissing(selector: string): boolean {
	return typeof document === 'undefined' || document.querySelector(selector) === null;
}

function adminComputeSteps(): TourStep[] {
	const ready = '[data-tour="admin-compute-ready"]';
	const row = '[data-tour="admin-compute-row"]';
	return [
		{
			element: '[data-tour="admin-compute-header"]',
			route: '/admin/instances',
			get title() { return t('tours.adminCompute.step1.title'); },
			get description() { return t('tours.adminCompute.step1.description'); },
		},
		{
			element: '[data-tour="admin-compute-filters"]',
			get title() { return t('tours.adminCompute.step2.title'); },
			get description() { return t('tours.adminCompute.step2.description'); },
		},
		{
			element: '[data-tour="admin-compute-timeseries"]',
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing('[data-tour="admin-compute-timeseries"]'),
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminCompute.step3.title'); },
			get description() { return t('tours.adminCompute.step3.description'); },
		},
		{
			element: '[data-tour="admin-compute-list"]',
			readyElement: ready,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminCompute.step4.title'); },
			get description() { return t('tours.adminCompute.step4.description'); },
		},
		{
			element: row,
			prepare: () => clickTourElement('[data-slide-panel-close]'),
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-compute-row-open"]',
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			showPrevious: true,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminCompute.step5.title'); },
			get description() { return t('tours.adminCompute.step5.description'); },
		},
		{
			element: '[data-tour="admin-compute-detail"]',
			prepare: () => clickTourElement('[data-tour="admin-compute-row-open"]'),
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminCompute.step6.title'); },
			get description() { return t('tours.adminCompute.step6.description'); },
		},
	];
}

function adminStorageSteps(): TourStep[] {
	const ready = '[data-tour="admin-storage-ready"]';
	const row = '[data-tour="admin-storage-row"]';
	return [
		{
			element: '[data-tour="admin-storage-header"]',
			route: '/admin/volumes',
			get title() { return t('tours.adminStorage.step1.title'); },
			get description() { return t('tours.adminStorage.step1.description'); },
		},
		{
			element: '[data-tour="admin-storage-timeseries"]',
			beforeReady: () => clickTourElement('#admin-volume-tabs-capacity'),
			skipReadyElement: '[data-tour="admin-storage-status"]',
			skipIf: () => isTourElementMissing('[data-tour="admin-storage-timeseries"]'),
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminStorage.step2.title'); },
			get description() { return t('tours.adminStorage.step2.description'); },
		},
		{
			element: '[data-tour="admin-storage-status"]',
			prepare: () => clickTourElement('#admin-volume-tabs-volumes'),
			get title() { return t('tours.adminStorage.step3.title'); },
			get description() { return t('tours.adminStorage.step3.description'); },
		},
		{
			element: '[data-tour="admin-storage-status-available"]',
			advanceOn: 'click',
			showPrevious: true,
			get title() { return t('tours.adminStorage.step4.title'); },
			get description() { return t('tours.adminStorage.step4.description'); },
		},
		{
			element: '[data-tour="admin-storage-filters"]',
			prepare: () => clickTourElement('#admin-volume-tabs-volumes'),
			get title() { return t('tours.adminStorage.step5.title'); },
			get description() { return t('tours.adminStorage.step5.description'); },
		},
		{
			element: '[data-tour="admin-storage-list"]',
			prepare: () => clickTourElement('#admin-volume-tabs-volumes'),
			readyElement: ready,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminStorage.step6.title'); },
			get description() { return t('tours.adminStorage.step6.description'); },
		},
		{
			element: row,
			prepare: () => clickTourElement('[data-slide-panel-close]'),
			advanceOn: 'click',
			advanceElement: '[data-tour="admin-storage-row-open"]',
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			showPrevious: true,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminStorage.step7.title'); },
			get description() { return t('tours.adminStorage.step7.description'); },
		},
		{
			element: '[data-tour="admin-storage-detail"]',
			prepare: () => clickTourElement('[data-tour="admin-storage-row-open"]'),
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminStorage.step8.title'); },
			get description() { return t('tours.adminStorage.step8.description'); },
		},
	];
}

function adminLibrarySteps(): TourStep[] {
	return [
		{
			element: '[data-tour="admin-library-header"]',
			route: '/admin/libraries',
			readyElement: '[data-tour="admin-library-ready"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminLibrary.step1.title'); },
			get description() { return t('tours.adminLibrary.step1.description'); },
		},
		{
			element: '[data-tour="admin-library-import"]',
			route: '/admin/libraries?tab=studio',
			get title() { return t('tours.adminLibrary.step2.title'); },
			get description() { return t('tours.adminLibrary.step2.description'); },
		},
		{
			element: '[data-tour="admin-library-profile"]',
			route: '/admin/libraries?tab=profiles',
			get title() { return t('tours.adminLibrary.step3.title'); },
			get description() { return t('tours.adminLibrary.step3.description'); },
		},
		{
			element: '[data-tour="admin-library-artifacts"]',
			route: '/admin/libraries?tab=artifacts',
			get title() { return t('tours.adminLibrary.step4.title'); },
			get description() { return t('tours.adminLibrary.step4.description'); },
		},
		{
			element: '[data-tour="admin-library-builds"]',
			route: '/admin/libraries?tab=builds',
			get title() { return t('tours.adminLibrary.step5.title'); },
			get description() { return t('tours.adminLibrary.step5.description'); },
		},
		{
			element: '[data-tour="admin-library-consumes"]',
			route: '/admin/libraries?tab=instances',
			get title() { return t('tours.adminLibrary.step6.title'); },
			get description() { return t('tours.adminLibrary.step6.description'); },
		},
	];
}

function adminNetworkSteps(): TourStep[] {
	const ready = '[data-tour="admin-network-ready"]';
	const resource = '[data-tour="admin-network-resource"]';
	return [
		{
			element: '[data-tour="admin-network-header"]',
			route: '/admin/topology',
			get title() { return t('tours.adminNetwork.step1.title'); },
			get description() { return t('tours.adminNetwork.step1.description'); },
		},
		{
			element: '[data-tour="admin-network-filter"]',
			get title() { return t('tours.adminNetwork.step2.title'); },
			get description() { return t('tours.adminNetwork.step2.description'); },
		},
		{
			element: '[data-tour="admin-network-canvas"]',
			readyElement: ready,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminNetwork.step3.title'); },
			get description() { return t('tours.adminNetwork.step3.description'); },
		},
		{
			element: resource,
			prepare: () => clickTourElement('[data-slide-panel-close]'),
			advanceOn: 'click',
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(resource),
			showPrevious: true,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminNetwork.step4.title'); },
			get description() { return t('tours.adminNetwork.step4.description'); },
		},
		{
			element: '[data-tour="admin-network-detail"]',
			prepare: () => clickTourElement(resource),
			advanceOn: 'click',
			advanceElement: '[data-slide-panel-close]',
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(resource),
			showPrevious: true,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminNetwork.step5.title'); },
			get description() { return t('tours.adminNetwork.step5.description'); },
		},
		{
			element: '[data-tour="topology-legend-toggle"]',
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing('[data-tour="topology-legend-toggle"]'),
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminNetwork.step6.title'); },
			get description() { return t('tours.adminNetwork.step6.description'); },
		},
	];
}

function adminContainersSteps(): TourStep[] {
	const ready = '[data-tour="admin-containers-ready"]';
	const row = '[data-tour="admin-containers-row"]';
	return [
		{
			element: '[data-tour="admin-containers-header"]',
			route: '/admin/containers',
			get title() { return t('tours.adminContainers.step1.title'); },
			get description() { return t('tours.adminContainers.step1.description'); },
		},
		{
			element: '[data-tour="admin-containers-list"]',
			readyElement: ready,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminContainers.step2.title'); },
			get description() { return t('tours.adminContainers.step2.description'); },
		},
		{
			element: row,
			prepare: () => clickTourElement('[data-slide-panel-close]'),
			advanceOn: 'click',
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			showPrevious: true,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminContainers.step3.title'); },
			get description() { return t('tours.adminContainers.step3.description'); },
		},
		{
			element: '[data-tour="admin-containers-detail"]',
			prepare: () => clickTourElement(row),
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminContainers.step4.title'); },
			get description() { return t('tours.adminContainers.step4.description'); },
		},
		{
			element: '[data-tour="admin-containers-logs"]',
			prepare: () => clickTourElement(row),
			advanceOn: 'click',
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			showPrevious: true,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminContainers.step5.title'); },
			get description() { return t('tours.adminContainers.step5.description'); },
		},
	];
}

function adminKeyManagerSteps(): TourStep[] {
	const ready = '[data-tour="admin-key-manager-ready"]';
	const actions = '[data-tour="admin-key-manager-actions"]';
	return [
		{
			element: '[data-tour="admin-key-manager-header"]',
			route: '/admin/secrets',
			get title() { return t('tours.adminKeyManager.step1.title'); },
			get description() { return t('tours.adminKeyManager.step1.description'); },
		},
		{
			element: '[data-tour="admin-key-manager-table"]',
			readyElement: ready,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminKeyManager.step2.title'); },
			get description() { return t('tours.adminKeyManager.step2.description'); },
		},
		{
			element: actions,
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(actions),
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminKeyManager.step3.title'); },
			get description() { return t('tours.adminKeyManager.step3.description'); },
		},
	];
}

function adminMonitoringSteps(): TourStep[] {
	const ready = '[data-tour="admin-monitoring-list-ready"]';
	const row = '[data-tour="admin-monitoring-row"]';
	const openInstances = () => clickTourElement('[data-tour="admin-monitoring-instances-tab"]');
	return [
		{
			element: '[data-tour="admin-monitoring-header"]',
			route: '/admin/monitoring',
			prepare: () => clickTourElement('[data-tour="admin-monitoring-summary-tab"]'),
			get title() { return t('tours.adminMonitoring.step1.title'); },
			get description() { return t('tours.adminMonitoring.step1.description'); },
		},
		{
			element: '[data-tour="admin-monitoring-summary"]',
			readyElement: '[data-tour="admin-monitoring-summary-ready"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminMonitoring.step2.title'); },
			get description() { return t('tours.adminMonitoring.step2.description'); },
		},
		{
			element: '[data-tour="admin-monitoring-instances-tab"]',
			advanceOn: 'click',
			showPrevious: true,
			get title() { return t('tours.adminMonitoring.step3.title'); },
			get description() { return t('tours.adminMonitoring.step3.description'); },
		},
		{
			element: '[data-tour="admin-monitoring-list"]',
			prepare: openInstances,
			readyElement: ready,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminMonitoring.step4.title'); },
			get description() { return t('tours.adminMonitoring.step4.description'); },
		},
		{
			element: row,
			beforeReady: openInstances,
			prepare: () => clickTourElement('[data-tour="admin-monitoring-back"]'),
			advanceOn: 'click',
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			showPrevious: true,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminMonitoring.step5.title'); },
			get description() { return t('tours.adminMonitoring.step5.description'); },
		},
		{
			element: '[data-tour="admin-monitoring-metrics"]',
			beforeReady: openInstances,
			prepare: () => clickTourElement(row),
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminMonitoring.step6.title'); },
			get description() { return t('tours.adminMonitoring.step6.description'); },
		},
	];
}

function adminSystemSteps(): TourStep[] {
	const tabs = '[data-tour="admin-system-tabs"]';
	const networkTab = '[data-tour="admin-system-network-tab"]';
	const endpointsTab = '[data-tour="admin-system-endpoints-tab"]';
	const poolsTab = '[data-tour="admin-system-storage-pools-tab"]';
	const optionalTab = (selector: string): Pick<TourStep, 'skipReadyElement' | 'skipIf' | 'waitTimeoutMs'> => ({
		skipReadyElement: tabs,
		skipIf: () => isTourElementMissing(selector),
		waitTimeoutMs: 20000,
	});
	return [
		{
			element: '[data-tour="admin-system-header"]',
			route: '/admin/services',
			prepare: () => clickTourElement('[data-tour="admin-system-compute-tab"]'),
			get title() { return t('tours.adminSystem.step1.title'); },
			get description() { return t('tours.adminSystem.step1.description'); },
		},
		{
			element: tabs,
			get title() { return t('tours.adminSystem.step2.title'); },
			get description() { return t('tours.adminSystem.step2.description'); },
		},
		{
			element: networkTab,
			advanceOn: 'click',
			showPrevious: true,
			...optionalTab(networkTab),
			get title() { return t('tours.adminSystem.step3.title'); },
			get description() { return t('tours.adminSystem.step3.description'); },
		},
		{
			element: '[data-tour="admin-system-panel"]',
			prepare: () => clickTourElement(networkTab),
			readyElement: '[data-tour="admin-system-panel-ready"]',
			...optionalTab(networkTab),
			get title() { return t('tours.adminSystem.step4.title'); },
			get description() { return t('tours.adminSystem.step4.description'); },
		},
		{
			element: endpointsTab,
			advanceOn: 'click',
			showPrevious: true,
			...optionalTab(endpointsTab),
			get title() { return t('tours.adminSystem.step5.title'); },
			get description() { return t('tours.adminSystem.step5.description'); },
		},
		{
			element: '[data-tour="admin-system-panel"]',
			prepare: () => clickTourElement(endpointsTab),
			readyElement: '[data-tour="admin-system-panel-ready"]',
			...optionalTab(endpointsTab),
			get title() { return t('tours.adminSystem.step6.title'); },
			get description() { return t('tours.adminSystem.step6.description'); },
		},
		{
			element: poolsTab,
			advanceOn: 'click',
			showPrevious: true,
			...optionalTab(poolsTab),
			get title() { return t('tours.adminSystem.step7.title'); },
			get description() { return t('tours.adminSystem.step7.description'); },
		},
		{
			element: '[data-tour="admin-system-panel"]',
			prepare: () => clickTourElement(poolsTab),
			readyElement: '[data-tour="admin-system-panel-ready"]',
			...optionalTab(poolsTab),
			get title() { return t('tours.adminSystem.step8.title'); },
			get description() { return t('tours.adminSystem.step8.description'); },
		},
	];
}

function adminIdentitySteps(): TourStep[] {
	const ready = '[data-tour="admin-identity-list-ready"]';
	const row = '[data-tour="admin-identity-row"]';
	return [
		{
			element: '[data-tour="admin-identity-header"]',
			route: '/admin/users',
			get title() { return t('tours.adminIdentity.step1.title'); },
			get description() { return t('tours.adminIdentity.step1.description'); },
		},
		{
			element: '[data-tour="admin-identity-overview"]',
			readyElement: '[data-tour="admin-identity-overview-ready"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminIdentity.step2.title'); },
			get description() { return t('tours.adminIdentity.step2.description'); },
		},
		{
			element: '[data-tour="admin-identity-filters"]',
			readyElement: ready,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminIdentity.step3.title'); },
			get description() { return t('tours.adminIdentity.step3.description'); },
		},
		{
			element: '[data-tour="admin-identity-list"]',
			readyElement: ready,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminIdentity.step4.title'); },
			get description() { return t('tours.adminIdentity.step4.description'); },
		},
		{
			element: '[data-tour="admin-identity-list"]',
			readyElement: ready,
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminIdentity.step5.title'); },
			get description() { return t('tours.adminIdentity.step5.description'); },
		},
		{
			element: row,
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			waitTimeoutMs: 20000,
			get title() { return t('tours.adminIdentity.step6.title'); },
			get description() { return t('tours.adminIdentity.step6.description'); },
		},
	];
}

function waygateSteps(route: string, titleKey: Parameters<typeof t>[0]): TourStep[] {
	return [
		{
			element: '[data-tour="waygate-header"]',
			route,
			get title() { return t(titleKey); },
			get description() { return t('tours.waygate.step1.description'); },
		},
		{
			element: '[data-tour="waygate-list"]',
			readyElement: '[data-tour="waygate-ready"]',
			waitTimeoutMs: 20000,
			get title() { return t('tours.waygate.step2.title'); },
			get description() { return t('tours.waygate.step2.description'); },
		},
	];
}

function imageSteps(admin: boolean): TourStep[] {
	const prefix = admin ? 'admin-images' : 'images';
	return [
		{
			element: `[data-tour="${prefix}-header"]`,
			route: admin ? '/admin/images' : '/dashboard/compute/images',
			prepare: () => sidebarOpen.close(),
			get title() { return t('tours.images.step1.title'); },
			get description() { return t('tours.images.step1.description'); },
		},
		{
			element: `[data-tour="${prefix}-controls"]`,
			readyElement: `[data-tour="${prefix}-ready"]`,
			waitTimeoutMs: 20000,
			get title() { return t('tours.images.step2.title'); },
			get description() { return t('tours.images.step2.description'); },
		},
		{
			element: `[data-tour="${prefix}-results"]`,
			get title() { return t('tours.images.step3.title'); },
			get description() { return t('tours.images.step3.description'); },
		},
	];
}

const STEP_BUILDERS: Record<TourId, () => TourStep[]> = {
	'vm-create': vmCreateSteps,
	'instance-detail-delete': () => instanceDetailDeleteSteps(vmCreateSteps()),
	volume: volumeSteps,
	drover: droverSteps,
	buckets: bucketSteps,
	containers: containerSteps,
	secrets: secretSteps,
	'volume-backups': volumeBackupSteps,
	'iam-projects': iamProjectSteps,
	keypairs: keypairSteps,
	'floating-ips': floatingIpSteps,
	'security-groups': securityGroupSteps,
	networks: networkSteps,
	'volume-snapshots': volumeSnapshotSteps,
	'file-storage': fileStorageSteps,
	'load-balancers': loadBalancerSteps,
	routers: routerSteps,
	'containers-clusters': containerClusterSteps,
	'database-instances': databaseInstanceSteps,
	'database-backups': databaseBackupSteps,
	waygate: () => waygateSteps('/dashboard/network/waygate', 'tours.waygate.step1.title'),
	images: () => imageSteps(false),
	'admin-images': () => imageSteps(true),
	'admin-compute': adminComputeSteps,
	'admin-storage': adminStorageSteps,
	'admin-library': adminLibrarySteps,
	'admin-waygate': () => waygateSteps('/admin/waygate', 'tours.adminWaygate.step1.title'),
	'admin-network': adminNetworkSteps,
	'admin-containers': adminContainersSteps,
	'admin-key-manager': adminKeyManagerSteps,
	'admin-monitoring': adminMonitoringSteps,
	'admin-system': adminSystemSteps,
	'admin-identity': adminIdentitySteps,
	'admin-projects': adminProjectSteps,
	'admin-flavors': adminFlavorSteps,
	'admin-networks': adminNetworkLifecycleSteps,
	'admin-routers': adminRouterSteps,
	'admin-floating-ips': adminFloatingIpSteps,
	'admin-ports': adminPortSteps,
	'admin-users': adminUserSteps,
	'admin-groups': adminGroupSteps,
	'admin-roles': adminRoleSteps,
	'admin-domains': adminDomainSteps,
	'admin-system-admins': adminSystemAdminSteps,
	'admin-user-credentials': adminUserCredentialSteps,
	'admin-settings': adminSettingsSteps,
	'admin-announcements': adminAnnouncementSteps,
	'admin-application-credentials': adminApplicationCredentialSteps,
	'admin-object-storage': adminObjectStorageSteps,
	'account-mcp': accountMcpSteps,
};

/** 시작 버튼 등에서 시나리오 메타를 나열할 때 사용 (steps는 시작 시점에 빌드) */
export const tours: ReadonlyArray<{ id: TourId; label: string; summary: string }> = (
	Object.keys(TOUR_META) as TourId[]
).map((id) => ({
	id,
	get label() { return TOUR_META[id].label; },
	get summary() { return TOUR_META[id].summary; },
}));

export function isTourId(value: unknown): value is TourId {
	return typeof value === 'string' && (TOUR_IDS as readonly string[]).includes(value);
}

/** 호출 시점의 베타 설정 등을 반영해 투어 정의를 동적으로 빌드한다. */
export function getTour(id: unknown): TourDefinition | null {
	if (!isTourId(id)) return null;
	return {
		id,
		get label() { return TOUR_META[id].label; },
		get summary() { return TOUR_META[id].summary; },
		steps: STEP_BUILDERS[id](),
	};
}
