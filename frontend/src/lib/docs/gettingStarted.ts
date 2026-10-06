import type { DocGuide } from './types';

export const gettingStarted: DocGuide = {
	slug: 'getting-started',
	name: '시작하기',
	title: '첫 프로젝트에서 연구 환경 준비하기',
	summary: '로그인과 프로젝트 선택부터 가상 머신, 네트워크, 데이터 저장소를 고르는 기준까지 안내합니다.',
	category: 'start',
	keywords: ['로그인', '프로젝트', 'Keystone', '쿼터', '권한', '시작', 'VM', 'GPU'],
	prerequisites: [
		'운영자가 제공한 클라우드 계정과 사용자 도메인 이름. GitLab 로그인은 해당 배포에서 활성화한 경우에만 표시됩니다.',
		'자원을 만들 프로젝트의 접근 권한과 쓰기 권한. 문서 읽기에는 로그인이나 프로젝트 선택이 필요하지 않습니다.',
		'실험에 필요한 이미지·Flavor·네트워크와 프로젝트 쿼터. GPU 사양과 가용 용량은 배포마다 다릅니다.',
	],
	sections: [
		{
			id: 'sign-in', title: '로그인하고 프로젝트 선택하기',
			steps: [
				{ title: '콘솔에 로그인', text: ['상단의 콘솔 접속을 누르고 사용자 도메인·사용자 이름·비밀번호를 입력합니다. 사용자 도메인은 운영자에게 받은 값을 사용합니다. GitLab 버튼이 보이면 해당 조직의 연동 로그인도 사용할 수 있습니다.'], links: [{ label: '로그인 화면', href: '/login' }] },
				{ title: '작업할 프로젝트 선택', text: ['최근 프로젝트 선택 화면에서 프로젝트 이름과 ID를 확인하고 선택합니다. 목록이 비어 있으면 운영자에게 프로젝트 멤버십을 요청합니다. 다른 프로젝트의 자원은 현재 프로젝트 목록에 나타나지 않습니다.'], links: [{ label: '프로젝트 선택', href: '/select-project' }] },
				{ title: '현재 범위와 사용량 확인', text: ['대시보드에 프로젝트 이름이 표시되는지 확인합니다. 상단 프로젝트 선택기로 작업 범위를 바꿀 수 있습니다. 생성 전에 개요와 사용량에서 인스턴스·vCPU·RAM·볼륨·Floating IP 등 필요한 쿼터를 확인합니다.'], links: [{ label: '프로젝트 사용량', href: '/dashboard/usage' }] },
			],
			callout: { tone: 'info', title: '역할과 기능 활성화는 서로 다릅니다', text: '읽기 권한만 있는 계정은 조회할 수 있어도 생성·수정·삭제할 수 없습니다. 메뉴가 없으면 서비스 활성화와 일부 기능의 Beta 설정도 확인하세요. 관리자 모드가 보인다는 이유만으로 모든 프로젝트 작업이 허용되는 것은 아닙니다.' },
		},
		{
			id: 'first-instance', title: '첫 가상 머신 만들기',
			paragraphs: ['기존 프로젝트 네트워크와 부팅 이미지가 준비되어 있다면 다음 순서로 시작합니다. 네트워크를 직접 준비해야 한다면 Neutron 가이드를 먼저 읽으세요.'],
			steps: [
				{ title: '연결 경로 준비', text: ['네트워크·서브넷과 접근 방법을 선택합니다. 외부 접속에는 라우터·Floating IP 또는 Waygate 같은 허용된 연결 경로가 필요합니다. SSH를 쓸 경우 사용할 키페어와 접속 원본만 허용하는 보안 그룹을 준비합니다.'], links: [{ label: 'Neutron 네트워크 가이드', href: '/docs/neutron' }, { label: 'Waygate VPN 가이드', href: '/docs/waygate' }] },
				{ title: '인스턴스 생성 요청', text: ['Compute → 인스턴스에서 VM 생성을 엽니다. 이름·이미지·Flavor·네트워크·키페어·보안 그룹과 필요한 저장소를 선택하고 마지막 검토에서 요청 사양과 쿼터를 확인해 생성합니다. Flavor는 vCPU·RAM 및 제공되는 GPU 사양 묶음입니다.'], links: [{ label: 'Nova 인스턴스 가이드', href: '/docs/nova' }] },
				{ title: '상태와 실제 접속 확인', text: ['인스턴스 목록과 상세에서 상태·IP·연결 볼륨을 확인합니다. 생성 진행의 완료는 모든 부팅 작업이나 게스트 준비가 끝났다는 뜻이 아닙니다. 콘솔 로그와 게스트 상태를 확인한 뒤 이미지가 안내하는 계정으로 SSH 또는 제공되는 콘솔에 접속합니다.'] },
			],
			callout: { tone: 'warning', title: '진행 화면은 요청 상태입니다', text: '문서 예시와 랜딩 페이지의 브라우저 체험은 자원을 만들지 않습니다. 실제 콘솔에서 제출하는 생성 요청은 클라우드 자원과 쿼터를 사용합니다. 실패 후 재요청하기 전에 남은 자원과 기존 요청 상태를 확인하세요.' },
		},
		{
			id: 'choose-service', title: '작업에 맞는 서비스 고르기',
			bullets: [
				'Nova + Glance: 부팅 이미지와 Flavor를 조합해 VM을 실행합니다. Neutron은 VM의 네트워크와 보안 규칙을 담당합니다.',
				'Cinder: VM에 연결하는 블록 디스크입니다. 게스트에서 파일시스템과 마운트를 관리합니다.',
				'Manila: 여러 클라이언트가 사용하는 공유 파일시스템입니다. 프로토콜별 접근 규칙과 export 경로가 필요합니다.',
				'Object Storage: 버킷 안에 파일을 객체로 보관합니다. VM 디스크나 POSIX 공유 파일시스템과는 다릅니다.',
				'Octavia: 여러 서버 앞에 VIP·리스너·풀·헬스 모니터를 구성하는 로드밸런서입니다.',
				'Drover: VM 기반 Kubernetes 클러스터와 노드·워크로드를 다룹니다. Waygate는 WireGuard 클라이언트로 프로젝트 내부 접근 경로를 제공합니다.',
				'Lumen: 프로젝트 범위의 AI 채팅·미디어 Studio와 API/CLI 연결을 제공합니다. 사용 가능한 모델·기능·한도는 서버 설정에 따릅니다.',
				'Palimpsest: 재사용할 패키지와 불변 레이어 환경을 다룹니다. Trove는 관리형 데이터베이스, Barbican은 비밀 값 관리용입니다.',
			],
		},
		{
			id: 'data-safety', title: '실험 데이터와 자격 증명 지키기',
			bullets: [
				'중요한 데이터를 인스턴스의 임시 디스크에만 두지 않습니다. 인스턴스 삭제·재구축 전에 연결 볼륨의 삭제 정책과 별도 데이터 사본을 확인합니다.',
				'스냅샷은 시점 복사이며 독립된 백업과 같지 않습니다. 사용 중인 애플리케이션의 쓰기를 안전하게 중지하거나 정합성을 확보한 후 스냅샷·백업을 수행합니다.',
				'SSH 개인 키, kubeconfig, WireGuard 설정과 Lumen API 키는 접근 권한입니다. 공개 저장소·메신저·화면 캡처에 넣지 않고 공유 또는 분실 시 폐기/재발급합니다.',
				'삭제 전에 현재 프로젝트 이름과 자원 ID를 다시 확인합니다. 연결된 자원을 먼저 해제하고 데이터 보존 여부를 결정합니다.',
			],
		},
		{
			id: 'troubleshooting', title: '작업이 막혔을 때',
			steps: [
				{ title: '메뉴 또는 자원이 보이지 않음', text: ['현재 프로젝트와 로그인 계정을 확인합니다. 다른 프로젝트로 전환했거나 운영자가 서비스를 비활성화했을 수 있습니다. Beta 항목은 사용자 설정에 따라 숨겨집니다.'] },
				{ title: '권한 또는 쿼터 오류', text: ['현재 프로젝트에서 쓰기 권한이 있는지, 해당 자원의 쿼터와 현재 사용량이 얼마인지 확인합니다. 필요한 변경은 운영자에게 요청하며 반복 제출로 우회하지 않습니다.'] },
				{ title: '생성 실패 또는 연결 불가', text: ['서비스 가이드의 확인 절차와 자원 상세 오류를 읽습니다. 네트워크 경로·보안 그룹·IP·게스트 서비스 상태를 차례로 확인합니다. 지원 요청에는 서비스 이름·프로젝트 ID·자원 ID·발생 시각·비밀을 제외한 오류 메시지를 전달합니다.'] },
			],
		},
	],
	related: ['nova', 'neutron', 'cinder', 'manila', 'drover', 'lumen'],
	consoleLinks: [{ label: '프로젝트 개요', href: '/dashboard' }, { label: '사용량 확인', href: '/dashboard/usage' }],
	externalLinks: [{ label: 'OpenStack 공식 인스턴스 시작 가이드', href: 'https://docs.openstack.org/install-guide/launch-instance-selfservice.html', description: '네트워크·이미지·Flavor·키페어를 조합하는 공식 CLI 절차입니다. Afterglow 화면의 명칭과는 다를 수 있습니다.' }],
};
