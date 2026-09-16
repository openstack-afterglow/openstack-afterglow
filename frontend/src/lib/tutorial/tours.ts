import { get } from 'svelte/store';
import { betaFeatures } from '$lib/stores/betaFeatures';
import { sidebarOpen } from '$lib/stores/sidebar';

export const TOUR_IDS = [
	'vm-create',
	'volume',
	'drover',
	'admin-compute',
	'admin-storage',
	'admin-library',
	'admin-network',
	'admin-containers',
	'admin-key-manager',
	'admin-monitoring',
	'admin-system',
	'admin-identity',
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
	/**
	 * 'click'이면 실제 클릭으로 다음 step 진행 (팝오버 '다음' 버튼 없음).
	 * 'wizard'이면 위저드 단계(wizardStep) 변화를 따라 팝오버가 이동한다(자체 '다음' 버튼 없음).
	 */
	advanceOn?: 'click' | 'wizard';
	/** 이 팝오버가 대응하는 위저드 raw 단계 번호($wizard.step). 엔진이 afterglow:wizard-step 이벤트로 매핑한다. */
	wizardStep?: number;
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
	waitTimeoutMs?: number;
}

export interface TourDefinition {
	id: TourId;
	label: string;
	summary: string;
	steps: TourStep[];
}

const TOUR_META: Record<TourId, { label: string; summary: string }> = {
	'vm-create': { label: 'VM 생성', summary: '위저드로 인스턴스를 만들고 배포 과정을 지켜봅니다.' },
	volume: { label: '볼륨 생성·관리', summary: '블록 볼륨을 만들고 목록에서 관리 작업을 살펴봅니다.' },
	drover: { label: 'Drover 클러스터', summary: 'k3s Kubernetes 클러스터를 프로비저닝하고 접속 정보를 받습니다.' },
	'admin-compute': {
		label: 'Compute 관리',
		summary: '전체 인스턴스 상태·용량·필터와 안전한 상세 조회를 살펴봅니다.',
	},
	'admin-storage': {
		label: '스토리지 관리',
		summary: '전체 볼륨의 추이·상태·필터와 상세 조회 지점을 살펴봅니다.',
	},
	'admin-library': {
		label: '라이브러리 관리',
		summary: '레이어 빌드부터 프로필·아티팩트·소비 상태까지 읽는 순서를 살펴봅니다.',
	},
	'admin-network': {
		label: '네트워크 관리',
		summary: '프로젝트 필터와 전역 토폴로지의 연결·트래픽 범례를 살펴봅니다.',
	},
	'admin-containers': {
		label: '컨테이너 관리',
		summary: '전체 컨테이너 상태와 리소스·상세 정보를 안전하게 확인합니다.',
	},
	'admin-key-manager': {
		label: 'Key Manager 관리',
		summary: '프로젝트별 Barbican 쿼터와 관리 액션의 의미를 살펴봅니다.',
	},
	'admin-monitoring': {
		label: '통합 모니터링',
		summary: '클러스터 요약과 인스턴스 메트릭 탐색 방법을 살펴봅니다.',
	},
	'admin-system': {
		label: '시스템 서비스',
		summary: '서비스 카테고리별 상태와 API endpoint·스토리지 풀 정보를 살펴봅니다.',
	},
	'admin-identity': {
		label: 'Identity 관리',
		summary: '사용자 현황·활동·검색·필터·목록을 안전하게 살펴봅니다.',
	},
};

/**
 * VM 생성 투어 — 위저드 표시 단계에 맞춰 동적으로 구성한다.
 * 라이브러리 단계는 libraryConsume 베타가 켜져 있을 때만 포함되고,
 * (베타가 켜져 있어도) 위저드가 해당 단계를 노출하지 않으면(비 Ubuntu 이미지 등)
 * skipIf 로 런타임에 건너뛴다.
 */
function vmCreateSteps(): TourStep[] {
	const steps: TourStep[] = [
		{
			element: '[data-tour="vm-create-open"]',
			route: '/dashboard',
			prepare: async () => {
				// 모바일(md 미만)에서 사이드바는 닫힌 off-canvas 드로어라 VM 생성 버튼이 화면 밖에 있다.
				// 드로어를 열고 슬라이드 인 트랜지션(duration-200)이 끝난 뒤 하이라이트하도록 대기한다.
				if (typeof window !== 'undefined' && window.innerWidth < 768) {
					sidebarOpen.open();
					await new Promise((resolve) => setTimeout(resolve, 250));
				}
			},
			title: 'VM 생성 시작',
			description: 'VM 생성 버튼을 눌러 인스턴스 생성 위저드를 열어보세요.',
			advanceOn: 'click',
		},
		{
			element: '[data-tour="wizard-panel"]',
			title: '이미지 선택',
			description: 'VM을 부팅할 OS 이미지를 하나 선택하세요. 선택하면 자동으로 다음 단계로 이동합니다.',
			advanceOn: 'wizard',
			wizardStep: 1,
			cancelElement: '[data-tour="wizard-cancel"]',
			// 위저드 데이터 로딩이 끝나 본문이 나타난 뒤에 하이라이트한다
			readyElement: '[data-tour="wizard-body"]',
			waitTimeoutMs: 20000,
		},
		{
			element: '[data-tour="wizard-panel"]',
			title: '플레이버 선택',
			description:
				'플레이버는 VM의 vCPU · 메모리 · 디스크 스펙입니다. 프로젝트 남은 쿼터 안에서 생성 가능한 플레이버만 표시되고, GPU 플레이버는 스케줄러가 가용 호스트를 자동 선택합니다. 하나 선택하면 자동으로 다음 단계로 이동합니다.',
			advanceOn: 'wizard',
			wizardStep: 2,
			cancelElement: '[data-tour="wizard-cancel"]',
		},
	];
	if (get(betaFeatures).libraryConsume) {
		steps.push({
			element: '[data-tour="wizard-panel"]',
			title: '라이브러리 (베타)',
			description:
				'AI/ML 라이브러리 레이어를 VM에 얹을 수 있는 베타 기능입니다. 필요한 레이어를 고르거나, 선택 없이 "다음 →"으로 건너뛸 수 있습니다.',
			advanceOn: 'wizard',
			wizardStep: 3,
			cancelElement: '[data-tour="wizard-cancel"]',
			// Ubuntu 계열 이미지가 아니면 위저드가 이 단계를 숨긴다 — 스텝퍼에 없으면 투어도 건너뛴다
			skipIf: () =>
				!document.querySelector('[data-tour="wizard-stepper"]')?.textContent?.includes('라이브러리'),
		});
	}
	steps.push(
		{
			element: '[data-tour="wizard-panel"]',
			title: '기본 설정 확인',
			description:
				'VM 이름(비우면 자동 생성), 네트워크, SSH 키페어, 보안 그룹, 가용 영역, 루트 디스크 크기를 확인하세요. 기본값 그대로도 생성할 수 있습니다. 확인했으면 "다음 →"을 누르세요.',
			advanceOn: 'wizard',
			wizardStep: 5,
			cancelElement: '[data-tour="wizard-cancel"]',
		},
		{
			element: '[data-tour="wizard-panel"]',
			title: '배포',
			description:
				'선택한 구성 요약을 마지막으로 확인하세요. "VM 생성" 버튼을 누르면 부트 볼륨 생성 → 인스턴스 생성 순으로 배포가 시작됩니다.',
			wizardStep: 6,
			advanceOn: 'click',
			advanceElement: '[data-tour="wizard-next"]',
			cancelElement: '[data-tour="wizard-cancel"]',
		},
		{
			element: '[data-tour="dashboard-recent"]',
			title: '배포 완료',
			description:
				'배포가 끝나면 대시보드로 돌아옵니다. 최근 인스턴스 목록 맨 위에 방금 만든 VM이 추가된 것을 확인하세요. 이름을 클릭하면 상세 화면으로 이동합니다.',
			waitTimeoutMs: 20000,
		},
	);
	return steps;
}

function volumeSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="volume-create-open"]',
			route: '/dashboard/volumes',
			title: '볼륨 생성 열기',
			description: '+ 볼륨 생성 버튼을 눌러 생성 폼을 열어보세요.',
			advanceOn: 'click',
		},
		{
			element: '[data-tour="volume-create-form"]',
			title: '볼륨 정보 입력',
			description: '볼륨 이름과 크기(GB)를 입력한 뒤 "생성" 버튼을 누르세요. 이름을 입력해야 버튼이 활성화됩니다.',
			advanceOn: 'click',
			advanceElement: '[data-tour="volume-create-submit"]',
		},
		{
			element: '[data-tour="volume-list"]',
			title: '볼륨 관리',
			description:
				'방금 만든 볼륨이 목록에 추가됐습니다. 행을 클릭하면 상세 패널이 열리고, 우측 액션 메뉴에서 확장·인스턴스 연결·삭제 등을 수행할 수 있습니다.',
		},
	];
}

function droverSteps(): TourStep[] {
	return [
		{
			element: '[data-tour="drover-create-open"]',
			route: '/dashboard/drover',
			title: '클러스터 생성 열기',
			description: '+ 클러스터 생성 버튼을 눌러 Drover 클러스터 생성 폼을 열어보세요.',
			advanceOn: 'click',
		},
		{
			element: '[data-tour="drover-name"]',
			title: '클러스터 이름',
			description: '클러스터 이름을 입력하세요. 비워두면 자동으로 생성됩니다.',
		},
		{
			element: '[data-tour="drover-os"]',
			title: 'OS 타입',
			description: '노드 OS를 선택하세요. Ubuntu(cloud-init) 또는 CoreOS(Ignition) 중 하나를 클릭하면 다음으로 진행됩니다.',
			advanceOn: 'click',
		},
		{
			element: '[data-tour="drover-masters"]',
			title: '마스터 수',
			description: '컨트롤 플레인 구성을 선택하세요. 1(단일) 또는 3(HA — embedded etcd, API LB 자동 생성) 중 하나를 클릭하면 다음으로 진행됩니다.',
			advanceOn: 'click',
		},
		{
			element: '[data-tour="drover-agents"]',
			title: '에이전트 수',
			description: '워커(에이전트) 노드 수를 0~10 사이에서 입력하세요.',
		},
		{
			element: '[data-tour="drover-flavor"]',
			title: '에이전트 플레이버',
			description: '에이전트 노드의 VM 스펙을 선택하세요. "기본값 사용"을 그대로 둬도 됩니다.',
		},
		{
			element: '[data-tour="drover-create-submit"]',
			title: '클러스터 생성',
			description: '"생성" 버튼을 누르면 VM 프로비저닝과 k3s 설치가 시작됩니다.',
			advanceOn: 'click',
		},
		{
			element: '[data-tour="drover-progress"]',
			title: '프로비저닝 진행',
			description:
				'VM 생성 → k3s 설치 → 완료 순으로 진행 상황이 실시간 표시됩니다. 완료 후 닫기를 누르면 목록 카드에서 kubeconfig를 내려받아 바로 kubectl로 접속할 수 있습니다.',
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
			title: 'Compute 전체 현황',
			description:
				'전체 프로젝트의 VM 상태와 관리자용 조회 도구를 살펴봅니다. VM 생성과 일괄 작업은 이 투어에서 실행하지 않습니다.',
		},
		{
			element: '[data-tour="admin-compute-filters"]',
			title: '대상 좁히기',
			description: '호스트·프로젝트·상태·이름 필터로 조사할 인스턴스를 좁힙니다. 필터 변경은 조회만 수행합니다.',
		},
		{
			element: '[data-tour="admin-compute-timeseries"]',
			title: '변화 확인',
			description: '기간별 인스턴스 수 추이에서 ACTIVE·SHUTOFF·ERROR·SHELVED 변화를 비교합니다.',
		},
		{
			element: '[data-tour="admin-compute-list"]',
			readyElement: ready,
			waitTimeoutMs: 20000,
			title: '전체 인스턴스 목록',
			description:
				'프로젝트·Flavor·호스트·상태를 확인합니다. 체크박스 아래 일괄 시작·종료·삭제는 누르지 않습니다.',
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
			title: '인스턴스 상세 열기',
			description: '이름을 눌러 조회 전용 상세 패널을 엽니다.',
		},
		{
			element: '[data-tour="admin-compute-detail"]',
			prepare: () => clickTourElement('[data-tour="admin-compute-row-open"]'),
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			waitTimeoutMs: 20000,
			title: '상세 정보 확인',
			description:
				'기본 정보·네트워크·스토리지·메트릭을 확인합니다. 시작·종료·삭제 같은 액션은 누르지 않고 완료 후 패널을 닫습니다.',
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
			title: '스토리지 전체 현황',
			description: '전체 프로젝트의 볼륨 추이·상태·목록을 안전하게 살펴봅니다.',
		},
		{
			element: '[data-tour="admin-storage-timeseries"]',
			title: '용량 변화 확인',
			description: '기간별 전체·사용 중·가용·오류 볼륨 수의 변화를 비교합니다.',
		},
		{
			element: '[data-tour="admin-storage-status"]',
			title: '상태별 분포',
			description: '상태 카드는 개수와 현재 필터를 함께 보여줍니다.',
		},
		{
			element: '[data-tour="admin-storage-status-available"]',
			advanceOn: 'click',
			showPrevious: true,
			title: '가용 볼륨만 보기',
			description: 'available 카드를 눌러 상태 필터가 목록에 적용되는 것을 확인하세요. 조회만 다시 수행합니다.',
		},
		{
			element: '[data-tour="admin-storage-filters"]',
			title: '프로젝트와 이름 검색',
			description: '프로젝트·상태·이름으로 조사 범위를 더 좁힐 수 있습니다.',
		},
		{
			element: '[data-tour="admin-storage-list"]',
			readyElement: ready,
			waitTimeoutMs: 20000,
			title: '전체 볼륨 목록',
			description:
				'크기·프로젝트·생성일을 읽습니다. 우측 액션 메뉴의 수정·이전·상태변경·삭제는 누르지 않습니다.',
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
			title: '볼륨 상세 열기',
			description: '이름을 눌러 조회 전용 상세 패널을 엽니다.',
		},
		{
			element: '[data-tour="admin-storage-detail"]',
			prepare: () => clickTourElement('[data-tour="admin-storage-row-open"]'),
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			waitTimeoutMs: 20000,
			title: '볼륨 구성 확인',
			description:
				'타입·연결·메타데이터를 확인합니다. 변경·복구 액션은 실행하지 않고 완료 후 패널을 닫습니다.',
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
			title: '라이브러리 워크플로',
			description:
				'레이어 빌드부터 프로필·아티팩트·소비 상태까지 읽는 순서를 살펴봅니다. 어떤 제출 버튼도 누르지 않습니다.',
		},
		{
			element: '[data-tour="admin-library-system"]',
			title: '기반 레이어',
			description: 'uv·apt·NVIDIA 템플릿은 공통 기반 레이어를 만듭니다. base image와 패키지 입력만 확인합니다.',
		},
		{
			element: '[data-tour="admin-library-import"]',
			title: 'Dockerfile 가져오기',
			description:
				'고정된 Git commit의 Dockerfile을 레이어 체인과 프로필로 변환하는 입력과 import 기록을 확인합니다.',
		},
		{
			element: '[data-tour="admin-library-python"]',
			title: 'Python 계층',
			description: 'uv 부모 위에 Python runtime을, Python lineage 위에 pip 패키지 레이어를 쌓는 순서를 확인합니다.',
		},
		{
			element: '[data-tour="admin-library-profile"]',
			title: '프로필 구성',
			description:
				'봉인된 같은 base image 레이어를 순서대로 묶어 소비 가능한 프로필을 구성합니다. 저장·공개·삭제는 실행하지 않습니다.',
		},
		{
			element: '[data-tour="admin-library-artifacts"]',
			title: '아티팩트 현황',
			description: '봉인·공개 상태, 상속 체인, 요청 패키지와 삭제 차단 사유를 읽습니다.',
		},
		{
			element: '[data-tour="admin-library-builds"]',
			title: '빌드 현황',
			description: '종류·진행 단계·진행률·완료 상태로 빌드 파이프라인을 확인합니다.',
		},
		{
			element: '[data-tour="admin-library-consumes"]',
			title: '소비 인스턴스',
			description: '프로필을 사용하는 소비 VM의 상태와 생성 시각을 확인합니다. 생성·삭제는 실행하지 않습니다.',
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
			title: '전체 네트워크 연결',
			description: '프로젝트를 가로지르는 네트워크·라우터·VM·Floating IP·로드밸런서 연결을 살펴봅니다.',
		},
		{
			element: '[data-tour="admin-network-filter"]',
			title: '프로젝트로 범위 좁히기',
			description: '프로젝트를 선택하면 토폴로지 표시 범위만 좁아집니다.',
		},
		{
			element: '[data-tour="admin-network-canvas"]',
			readyElement: ready,
			waitTimeoutMs: 20000,
			title: '토폴로지 읽기',
			description: '검색·트래픽 수치·네트워크 존(레인)과 연결선을 함께 읽습니다.',
		},
		{
			element: resource,
			prepare: () => clickTourElement('[data-slide-panel-close]'),
			advanceOn: 'click',
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(resource),
			showPrevious: true,
			waitTimeoutMs: 20000,
			title: '라우터 상세 열기',
			description: '라우터 카드를 눌러 조회 전용 상세를 엽니다.',
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
			title: '게이트웨이와 인터페이스',
			description: '외부 게이트웨이와 연결 서브넷을 확인한 뒤 × 닫기 버튼을 눌러 계속합니다.',
		},
		{
			element: '[data-tour="admin-network-legend"]',
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing('[data-tour="admin-network-legend"]'),
			waitTimeoutMs: 20000,
			title: '범례와 리소스 수',
			description: '범례의 기호·연결선 의미와 하단 네트워크·라우터·인스턴스·Floating IP·로드밸런서 수를 확인합니다.',
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
			title: '전체 컨테이너',
			description: '프로젝트 전체의 컨테이너 상태·이미지·리소스·호스트를 살펴봅니다.',
		},
		{
			element: '[data-tour="admin-containers-list"]',
			readyElement: ready,
			waitTimeoutMs: 20000,
			title: '컨테이너 목록 읽기',
			description: '상태와 CPU·메모리·호스트를 비교합니다.',
		},
		{
			element: row,
			prepare: () => clickTourElement('[data-slide-panel-close]'),
			advanceOn: 'click',
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			showPrevious: true,
			waitTimeoutMs: 20000,
			title: '컨테이너 상세 열기',
			description: '행을 눌러 조회 전용 상세 패널을 엽니다.',
		},
		{
			element: '[data-tour="admin-containers-detail"]',
			prepare: () => clickTourElement(row),
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			waitTimeoutMs: 20000,
			title: '구성과 네트워크',
			description: '기본 정보와 주소를 확인합니다. 시작·중지·삭제는 변경 작업이므로 누르지 않습니다.',
		},
		{
			element: '[data-tour="admin-containers-logs"]',
			prepare: () => clickTourElement(row),
			advanceOn: 'click',
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			showPrevious: true,
			waitTimeoutMs: 20000,
			title: '로그 확인',
			description: '로그 섹션을 열어 출력만 확인합니다. 완료 후 패널을 닫습니다.',
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
			title: 'Key Manager 쿼터',
			description: 'Barbican 쿼터를 프로젝트별로 읽습니다.',
		},
		{
			element: '[data-tour="admin-key-manager-table"]',
			readyElement: ready,
			waitTimeoutMs: 20000,
			title: '쿼터 값 읽기',
			description: 'Secrets·Orders·Containers 값과 프로젝트 ID를 확인합니다. -1은 무제한, 0은 비활성을 뜻합니다.',
		},
		{
			element: actions,
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(actions),
			waitTimeoutMs: 20000,
			title: '변경 액션 구분',
			description: '설정과 초기화는 PUT·DELETE 변경 작업이므로 이 튜토리얼에서는 누르지 않습니다.',
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
			title: '통합 모니터링',
			description: '클러스터 요약과 인스턴스 메트릭을 읽기 전용으로 살펴봅니다.',
		},
		{
			element: '[data-tour="admin-monitoring-summary"]',
			readyElement: '[data-tour="admin-monitoring-summary-ready"]',
			waitTimeoutMs: 20000,
			title: '클러스터 요약',
			description: 'Compute·스토리지·네트워크·컨테이너·데이터 서비스·Identity 상태를 한눈에 확인합니다.',
		},
		{
			element: '[data-tour="admin-monitoring-instances-tab"]',
			advanceOn: 'click',
			showPrevious: true,
			title: '인스턴스 메트릭 탭',
			description: '탭을 눌러 프로젝트 전체 인스턴스 목록을 엽니다.',
		},
		{
			element: '[data-tour="admin-monitoring-list"]',
			prepare: openInstances,
			readyElement: ready,
			waitTimeoutMs: 20000,
			title: '인스턴스 검색',
			description: '이름 또는 프로젝트 ID로 목록을 좁힙니다.',
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
			title: '메트릭 상세 열기',
			description: '행을 눌러 조회 전용 메트릭 패널을 엽니다.',
		},
		{
			element: '[data-tour="admin-monitoring-metrics"]',
			beforeReady: openInstances,
			prepare: () => clickTourElement(row),
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			waitTimeoutMs: 20000,
			title: '시계열 읽기',
			description: 'CPU·메모리·네트워크·디스크와 GPU가 있는 경우 GPU 시계열을 확인합니다. 조회 구간 변경만 사용합니다.',
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
			title: '서비스 상태',
			description: '서비스 카테고리별 프로세스와 endpoint·스토리지 풀을 읽습니다.',
		},
		{
			element: tabs,
			title: '카테고리 전환',
			description: 'Compute·Network·Block Storage 등 서비스별 개수와 로딩 상태를 확인합니다.',
		},
		{
			element: networkTab,
			advanceOn: 'click',
			showPrevious: true,
			...optionalTab(networkTab),
			title: 'Network 에이전트',
			description: '탭을 눌러 Agent Type·Binary·Host·Zone·Alive·Admin State를 확인합니다.',
		},
		{
			element: '[data-tour="admin-system-panel"]',
			prepare: () => clickTourElement(networkTab),
			readyElement: '[data-tour="admin-system-panel-ready"]',
			...optionalTab(networkTab),
			title: '상태 행 읽기',
			description: 'up·enabled와 down·disabled를 구분하고 변경 시각과 비활성 사유를 확인합니다.',
		},
		{
			element: endpointsTab,
			advanceOn: 'click',
			showPrevious: true,
			...optionalTab(endpointsTab),
			title: 'API Endpoints',
			description: '서비스·리전별 public·internal·admin URL을 확인합니다.',
		},
		{
			element: '[data-tour="admin-system-panel"]',
			prepare: () => clickTourElement(endpointsTab),
			readyElement: '[data-tour="admin-system-panel-ready"]',
			...optionalTab(endpointsTab),
			title: 'Endpoint 인터페이스',
			description: '같은 서비스의 인터페이스 URL이 올바른 리전에 연결됐는지 확인합니다.',
		},
		{
			element: poolsTab,
			advanceOn: 'click',
			showPrevious: true,
			...optionalTab(poolsTab),
			title: 'Storage Pools',
			description: '스토리지 풀 탭을 엽니다.',
		},
		{
			element: '[data-tour="admin-system-panel"]',
			prepare: () => clickTourElement(poolsTab),
			readyElement: '[data-tour="admin-system-panel-ready"]',
			...optionalTab(poolsTab),
			title: '용량 읽기',
			description: '총·여유·할당 용량과 사용률을 비교합니다.',
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
			title: 'Identity 사용자 관리',
			description: '사용자 현황·최근 변경·검색·필터·목록을 안전하게 살펴봅니다. 생성과 수정은 실행하지 않습니다.',
		},
		{
			element: '[data-tour="admin-identity-overview"]',
			readyElement: '[data-tour="admin-identity-overview-ready"]',
			waitTimeoutMs: 20000,
			title: '사용자 현황',
			description: '전체·활성·비활성 집계와 최근 사용자 변경 로그를 함께 읽습니다.',
		},
		{
			element: '[data-tour="admin-identity-filters"]',
			title: '검색과 정렬',
			description: '이름·이메일 검색, 활성 상태, 이름·최초 활동일 정렬로 목록을 좁힙니다.',
		},
		{
			element: '[data-tour="admin-identity-status-filter"]',
			title: '활성 사용자만 보기',
			description: '활성 상태를 선택해도 클라이언트 목록만 바뀌며 사용자 계정은 변경되지 않습니다.',
		},
		{
			element: '[data-tour="admin-identity-list"]',
			readyElement: ready,
			waitTimeoutMs: 20000,
			title: '사용자 목록',
			description: '이름·이메일·상태·ID·최초 활동일을 읽습니다.',
		},
		{
			element: row,
			skipReadyElement: ready,
			skipIf: () => isTourElementMissing(row),
			waitTimeoutMs: 20000,
			title: '상세와 세션 진입점',
			description:
				'행을 누르면 수정 폼과 세션 관리가 열립니다. 이 안전한 투어에서는 행·활성 토글·저장·세션 폐기를 누르지 않습니다.',
		},
	];
}

const STEP_BUILDERS: Record<TourId, () => TourStep[]> = {
	'vm-create': vmCreateSteps,
	volume: volumeSteps,
	drover: droverSteps,
	'admin-compute': adminComputeSteps,
	'admin-storage': adminStorageSteps,
	'admin-library': adminLibrarySteps,
	'admin-network': adminNetworkSteps,
	'admin-containers': adminContainersSteps,
	'admin-key-manager': adminKeyManagerSteps,
	'admin-monitoring': adminMonitoringSteps,
	'admin-system': adminSystemSteps,
	'admin-identity': adminIdentitySteps,
};

/** 시작 버튼 등에서 시나리오 메타를 나열할 때 사용 (steps는 시작 시점에 빌드) */
export const tours: ReadonlyArray<{ id: TourId; label: string; summary: string }> = (
	Object.keys(TOUR_META) as TourId[]
).map((id) => ({ id, ...TOUR_META[id] }));

export function isTourId(value: unknown): value is TourId {
	return typeof value === 'string' && (TOUR_IDS as readonly string[]).includes(value);
}

/** 호출 시점의 베타 설정 등을 반영해 투어 정의를 동적으로 빌드한다. */
export function getTour(id: unknown): TourDefinition | null {
	if (!isTourId(id)) return null;
	return { id, ...TOUR_META[id], steps: STEP_BUILDERS[id]() };
}
