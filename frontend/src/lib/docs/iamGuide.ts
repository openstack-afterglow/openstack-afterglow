import type { DocGuide, DocRoleHierarchy } from './types';

function serviceHierarchy(service: 'waygate' | 'drover' | 'lumen' | 'palimpsest'): DocRoleHierarchy {
	return {
		title: '서비스 등급의 기능 포함 관계',
		description: '화살표는 상위 등급이 포함하는 하위 등급의 기능을 가리킵니다. 세부 역할을 자동 부여하지 않으며 프로젝트·소유권·자격 조건은 그대로 적용됩니다.',
		relation: '포함',
		levels: ['admin', 'editor', 'user', 'reader'].map((grade) => ({ role: `${service}_${grade}` })),
	};
}

export const iamGuide: DocGuide = {
	slug: 'iam',
	name: 'IAM · 서비스별 권한',
	title: '사용자별 역할과 서비스 이용 권한 이해하기',
	summary: '조직 manager, 프로젝트 역할, Waygate·Drover·Lumen·Palimpsest의 등급과 세부 역할을 기능별로 설명하고 필요한 권한 조합을 안내합니다.',
	category: 'start',
	keywords: ['IAM', 'RBAC', 'Keystone', 'manager', '역할', '권한', '프로젝트', '서비스', '최소 권한'],
	prerequisites: [
		'권한은 사용자 이름만이 아니라 정확한 사용자·조직·프로젝트에 연결됩니다. 먼저 사용하려는 프로젝트와 작업을 정하세요.',
		'이 문서는 현재 소스의 기본 정책을 설명합니다. 실제 배포의 정책 변경, 역할 연결, 서비스 활성화와 쿼터에 따라 허용 결과가 달라질 수 있습니다.',
		'설명 범위는 조직 manager, 프로젝트 역할과 서비스별 관리 등급까지입니다. 문서 읽기나 역할 이름 확인만으로 권한이 부여되지는 않습니다.'
	],
	sections: [
		{
			id: 'scope', title: '1. IAM은 사용자·역할·범위를 함께 봅니다',
			paragraphs: [
				'IAM은 누가 어느 범위에서 어떤 작업을 할 수 있는지 정하는 접근 관리입니다. Keystone은 계정·프로젝트·역할 할당을 관리하고, 각 서비스는 요청한 작업을 자체 정책으로 검사합니다.',
				'계정의 홈 도메인은 계정이 속한 곳이고 작업 도메인은 지금 이용하는 조직입니다. 조직에 초대받아도 계정이 이동하지 않습니다. 같은 사용자가 프로젝트 A에서는 읽기, 프로젝트 B에서는 생성 권한을 가질 수 있습니다.',
				'권한은 직접 할당, 그룹, 범위 상속과 실제 역할 연결을 합쳐 평가합니다. 직접 역할 하나를 해제해도 그룹이나 상속으로 같은 권한이 남을 수 있습니다. 다른 프로젝트의 역할은 현재 프로젝트에 자동 적용되지 않습니다.'
			],
			callout: { tone: 'info', title: '역할·서비스 기능·쿼터는 서로 다른 조건입니다', text: '역할이 허용되어도 서비스가 꺼져 있거나 모델·이미지·네트워크가 준비되지 않았거나 쿼터가 부족하면 실행할 수 없습니다. 반대로 메뉴가 보인다고 모든 버튼과 API가 허용되는 것은 아닙니다.' }
		},
		{
			id: 'manager', title: '2. manager: 조직 IAM을 관리하는 역할',
			paragraphs: [
				'manager는 현재 조직의 canonical Default 프로젝트에 유효하게 할당된 조직 관리 역할입니다. 다른 프로젝트에 같은 이름의 역할이 있거나 도메인 이름이 같다는 이유로 조직 IAM 권한을 얻지는 않습니다.',
				'조직 manager는 같은 도메인의 사용자 참여·프로젝트 접근을 관리합니다. 일반 프로젝트를 읽기 전용으로 선택했거나 프로젝트를 선택하지 않았더라도 현재 조직의 manager 권한은 별도로 확인합니다.'
			],
			bullets: [
				'사용자 관리: 조직 참여자 조회, 이메일 초대·회수, 허용된 계정 정보 변경과 현재 조직에서 내보내기. 다른 홈 도메인의 계정 자체나 보호된 계정은 수정할 수 없습니다. 내보내기는 계정·VM·볼륨 삭제나 영구 재가입 차단이 아닙니다.',
				'프로젝트 관리: 조직 프로젝트 생성, 멤버와 서비스 역할 관리, project_admin 위임, 전용 절차를 통한 소유권 이전과 안전 삭제. 마지막 manager·소유권·Default 프로젝트 보호는 유지됩니다.',
				'로그인과 배분: 해당 조직의 로그인 방법·정책, 모니터링, 허용된 예산 안의 프로젝트 쿼터와 공용 compute pool의 프로젝트별 추가 상한을 관리합니다. 조직 공용 풀 자체의 한도를 임의로 늘리는 권한은 아닙니다.',
				'manager의 도메인 관리 우선순위는 프로젝트 소유권 상속이 아닙니다. 조직 프로젝트에 제공되는 읽기 접근만으로 VM 생성·VPN 설정 다운로드·AI 실행·패키지 게시가 허용되지는 않습니다. 작업할 프로젝트의 쓰기 권한과 각 서비스 권한을 따로 확인하세요.'
			],
			links: [{ label: '도메인 IAM', href: '/dashboard/iam/users' }]
		},
		{
			id: 'project-roles', title: '3. 프로젝트 역할: 접근·쓰기·멤버 관리를 구분합니다',
			hierarchy: {
				title: '프로젝트 역할 포함 관계',
				description: '화살표는 상위 역할이 포함하는 하위 역할을 가리킵니다. 실제 Keystone 역할 연결이 준비되어 있어야 하며 manager와 project_creator는 이 계층에 속하지 않습니다.',
				relation: '포함',
				levels: [
					{ role: 'project_owner' },
					{ role: 'project_admin' },
					{ role: 'project_member', alsoIncludes: ['member'] },
					{ role: 'project_reader', alsoIncludes: ['reader'] },
				],
			},
			bullets: [
				'project_reader: 프로젝트의 일반 읽기 접근입니다. native reader로 연결되지만 비밀 값·접속 자격이나 모든 서비스 데이터를 읽을 수 있다는 뜻은 아닙니다. 자원 생성·수정·삭제에는 부족합니다.',
				'project_member: 프로젝트의 일반 작업자입니다. project_reader와 native member로 연결되어 통상적인 클라우드 쓰기 검사를 통과할 수 있습니다. 서비스별 정책·소유권·쿼터는 별도이며 멤버 권한을 관리하지는 못합니다.',
				'project_admin: 해당 프로젝트 구성원과 위임 가능한 서비스 권한을 관리합니다. project_member 권한도 포함하지만 다른 project_admin의 추가·회수와 소유권 변경을 일반 멤버 편집으로 할 수는 없습니다.',
				'project_owner: 프로젝트 소유자입니다. project_admin을 위임하고 전용 소유권 이전 절차를 이용합니다. 일반 역할 선택으로 두 번째 소유자를 만들지 않으며 소유권을 정리하지 않은 삭제·탈퇴는 차단될 수 있습니다.',
				'프로젝트 계층은 project_owner → project_admin → project_member → project_reader이고, project_member → member 및 project_reader → reader가 연결됩니다. 실제 Keystone 연결이 준비되어 있어야 하며 이름만 같은 사용자 정의 역할로 대체하지 않습니다.',
				'project_creator: 조직 Default에서 프로젝트 생성을 위임받는 별도 역할입니다. manager도 별도 creator 없이 생성할 수 있습니다. 생성자는 새 프로젝트의 소유자가 되지만 다른 프로젝트·조직 사용자·로그인 정책을 관리할 권한까지 얻지는 않습니다. 일반 생성자의 프로젝트 삭제에는 현재 생성 권한과 단독 소유권, 빈 프로젝트 확인이 함께 필요합니다.',
				'member와 reader는 기본 클라우드 역할입니다. 기존 member 할당이 있어도 project_admin이나 서비스 등급이 자동 생기는 것은 아닙니다. 새 조직 초대에서는 대상 프로젝트의 멤버십 등급과 필요한 서비스 역할을 함께 선택합니다.'
			],
			links: [{ label: '프로젝트 관리', href: '/dashboard/iam/projects' }]
		},
		{
			id: 'core-services', title: '4. 기본 클라우드 서비스는 어떤 권한을 쓰나요?',
			paragraphs: [
				'다음은 프로젝트 사용자 경로입니다. 일반 조회와 변경은 현재 프로젝트 범위와 각 서비스의 native 정책을 따릅니다. Afterglow의 일부 변경 경로는 별도로 유효 member를 포함한 프로젝트 쓰기 권한을 확인합니다. project_member는 쓰기가 필요한 사용자의 표준 선택이지만 모든 작업의 허용을 보장하지 않습니다. project_reader는 조회 전용 선택입니다.',
				'Afterglow는 아래 서비스에 nova_user나 cinder_admin 같은 별도 서비스 등급 프리셋을 정의하지 않습니다. 읽기 역할도 모든 정보·비밀 다운로드를 보장하지 않고, member도 모든 native 작업을 보장하지 않습니다.'
			],
			bullets: [
				'Nova · Compute: 인스턴스 목록·상태·사용량은 허용된 조회 범위에서 확인합니다. VM 생성·시작/정지·사양 변경·삭제·사용 일정 연장에는 프로젝트 쓰기와 Nova 정책이 필요합니다. SSH·RDP 로그인은 별도의 게스트 계정·키·네트워크 접근입니다.',
				'Glance · 이미지: 현재 프로젝트에 허용된 부팅 이미지를 선택합니다. 이미지 업로드·수정·삭제에는 현재 프로젝트 범위, 이미지 소유권·공유 범위와 Glance 정책이 적용됩니다. 이미지를 사용할 수 있다고 그 이미지를 편집할 수는 없습니다.',
				'Neutron · 네트워크: 네트워크·서브넷·포트·라우터·Floating IP·보안 그룹의 생성과 변경은 현재 프로젝트의 native 작업 권한 및 소유/공유 정책을 따릅니다. 공유 네트워크 사용 권한은 그 네트워크를 삭제하거나 다른 프로젝트의 포트를 관리할 권한이 아닙니다.',
				'Octavia · 로드밸런서: VIP·리스너·풀·멤버·헬스 모니터 조회와 변경은 해당 프로젝트의 Octavia 정책을 따릅니다. 생성·변경에는 해당 native 작업 권한, 사용할 네트워크와 쿼터도 필요합니다.',
				'Cinder · 볼륨: 볼륨·스냅샷·백업 조회와 생성·연결·확장·복원·삭제는 현재 프로젝트 범위의 Cinder 정책과 자원 상태를 따릅니다. 볼륨 생성·확장·일반 삭제와 자동 스냅샷/백업 정책 변경은 Afterglow의 프로젝트 쓰기 검사도 요구합니다. 볼륨 이전 수락은 실제 수신 프로젝트 권한과 전송 키가 함께 필요합니다.',
				'Manila · 파일 스토리지: 공유·스냅샷·접근 규칙 변경은 현재 프로젝트 범위와 Manila 정책을 따릅니다. 공유를 볼 수 있어도 게스트 마운트에는 NFS 원본 IP 허용 또는 CephX 자격과 실제 네트워크 경로가 별도로 필요합니다.',
				'Object Storage: 버킷·객체 접근은 현재 프로젝트와 객체 스토리지 정책을 따릅니다. 업로드·삭제·접근 설정 변경에는 해당 native 작업 권한이 필요합니다. 외부 S3 자격과 버킷 정책의 사용 가능 여부 및 접근 범위는 배포 환경과 운영자에게 확인하세요.',
				'Trove · 데이터베이스: 인스턴스 생성·재시작·삭제·백업/복원은 현재 프로젝트 범위와 Trove 정책을 따릅니다. DB에 SQL로 접속하는 사용자·비밀번호·DB 내부 권한은 클라우드 IAM과 별개입니다.',
				'Barbican · Key Manager: 비밀의 메타데이터 조회와 실제 값 조회를 구분합니다. 생성·삭제·값 읽기는 각각 현재 호출자에 대한 Barbican 정책을 따릅니다. 실제 secret의 접근 설정과 배포 정책을 확인하며 reader라는 이유로 모든 비밀을 볼 수 있다고 판단하지 않습니다.',
				'Zun · 컨테이너와 Magnum · 클러스터: 제공되는 배포에서 각 native 서비스의 프로젝트 정책을 사용합니다. 생성·수명주기 변경에는 현재 프로젝트 범위에서 해당 작업의 native 허용이 필요합니다. Drover 역할을 Zun 또는 Magnum 역할로 대신 쓰지 않습니다.',
				'Cloud Shell: 시작·접속 ticket·홈 초기화는 읽기 전용 작업이 아니므로 프로젝트 쓰기 권한이 필요합니다. 셸이 열려도 CLI는 사용자의 실제 프로젝트 권한을 따르며 다른 서비스 권한을 추가하지 않습니다.'
			]
		},
		{
			id: 'service-grades', title: '5. 서비스 등급과 세부 역할을 읽는 방법',
			paragraphs: [
				'Waygate·Drover·Lumen·Palimpsest에는 각각 _reader, _user, _editor, _admin 등급이 있습니다. 등급은 해당 프로젝트의 서비스 기능 묶음이고, 하이픈이 있는 역할은 기능 하나를 골라 주는 세부 역할입니다. 예를 들어 waygate_user와 waygate-connect_user는 서로 다른 역할입니다.',
				'아래 등급 설명은 native 서비스 기본 정책의 결과입니다. 서비스 등급이 하위 역할을 Keystone 토큰에 자동 추가하는 방식은 아닙니다. 세부 역할도 다른 세부 역할을 자동 포함하지 않으므로 목록·모델 조회·실행·다운로드가 필요하면 각각의 조건을 확인합니다.',
				'“또는”은 그중 하나, “+”와 “그리고”는 모두 필요하다는 뜻입니다. 조직의 project_owner·project_admin·manager만으로 네 서비스의 사용 권한을 대체하지 않습니다. 서비스의 관리 등급도 다른 프로젝트·다른 사용자의 비밀·조직 IAM을 무제한으로 관리하는 역할이 아닙니다.'
			],
			callout: { tone: 'neutral', title: '자동 생성된 개인 프로젝트는 별도입니다', text: '서버가 실제 개인 프로젝트·본인 소유 metadata·안전한 직접 member 할당을 검증하면 기본 서비스 정책에서 개인 소유자 권한을 인정할 수 있습니다. 일반 조직의 member나 project_owner에 적용되는 예외가 아니며, 제한된 API 키·위임 자격에는 그대로 이어지지 않습니다.' }
		},
		{
			id: 'waygate', title: '6. Waygate: VPN 조회·접속·발급·회수',
			hierarchy: serviceHierarchy('waygate'),
			paragraphs: [
				'Waygate는 프로젝트의 WireGuard 게이트웨이와 기기별 VPN 프로필을 관리합니다. 역할은 게이트웨이가 속한 프로젝트에 부여합니다.'
			],
			bullets: [
				'waygate_reader: 서버·클라이언트·연결 네트워크 목록과 상태 조회. VPN 비밀 설정 다운로드는 포함하지 않습니다.',
				'waygate_user: 조회와 본인에게 할당된 활성 VPN 프로필 사용. 다른 사용자의 프로필 다운로드나 새 클라이언트 발급은 포함하지 않습니다.',
				'waygate_editor: user 기능에 게이트웨이·클라이언트 생성과 일반 설정 편집을 더합니다. 삭제·접속 회수·라우팅 변경은 별도입니다.',
				'waygate_admin: 프로젝트 내 editor 기능, 게이트웨이 삭제·에이전트 토큰 회전, 클라이언트 활성/비활성·삭제, 네트워크 연결·해제와 번들 작업. 본인 프로필만 다운로드하는 조건은 그대로입니다.',
				'waygate-inventory_reader: 서버·클라이언트·연결 네트워크 조회만 따로 허용합니다.',
				'waygate-connect_user: 본인에게 할당되고 활성화된 클라이언트의 .conf 다운로드와 같은 내용을 담는 QR 표시입니다. 서버 준비와 프로필 소유권도 필요합니다.',
				'waygate-clients_editor: 클라이언트 발급·일반 설정 편집·미할당 프로필의 최초 사용자 지정입니다. 지정 대상은 활성 프로젝트 member여야 하며 이미 지정한 소유자를 임의로 바꾸지 못합니다.',
				'waygate-clients_admin: 클라이언트 활성/비활성·삭제입니다. 일반 설정과 enabled를 한 번에 바꾸면 clients_editor 조건도 함께 필요합니다.',
				'waygate-gateways_editor: 게이트웨이 생성과 기본 설정 편집입니다. 생성에는 유효 native member와 제한되지 않은 사용자 자격이 추가로 필요합니다.',
				'waygate-gateways_admin: 게이트웨이 삭제와 에이전트 토큰 회전입니다. 삭제에는 유효 native member와 제한되지 않은 사용자 자격이 추가로 필요합니다.',
				'waygate-routing_admin: 테넌트 네트워크 연결·해제입니다. 유효 native member와 제한되지 않은 사용자 자격, 네트워크 사용 권한도 필요합니다.',
				'암호화 번들 내보내기·가져오기는 waygate_admin 또는 waygate-clients_admin + waygate-routing_admin을 요구합니다. 내보내기는 본인 소유와 미할당 프로필만 포함하고 다른 사용자의 키는 포함하지 않습니다.'
			],
			callout: { tone: 'warning', title: '접속 사용자와 게이트웨이 운영자를 구분하세요', text: 'VPN만 필요한 사람에게는 waygate_user와 본인 프로필을 준비하세요. 게이트웨이를 만들고 라우팅까지 운영하려면 프로젝트 쓰기와 waygate_admin을 조합합니다. 서비스 역할은 Nova·Neutron 실행 정책·쿼터를 대신하지 않으며, 서비스 전체 이미지·네트워크 정책 변경 권한을 뜻하지 않습니다.' },
			links: [{ label: 'Waygate', href: '/docs/waygate' }]
		},
		{
			id: 'drover', title: '7. Drover: 클러스터 운영과 Kubernetes 접속',
			hierarchy: serviceHierarchy('drover'),
			bullets: [
				'drover_reader: 프로젝트 클러스터 목록·상세·상태·이벤트·작업 조회와 허용된 템플릿 조회입니다. 접속 자격 다운로드는 포함하지 않습니다.',
				'drover_user: reader 기능과 제한된 user 등급 kubeconfig·Pod 로그 접근입니다. 클러스터 생성·워크로드 변경·전체 클러스터 접속 권한은 아닙니다.',
				'drover_editor: user 기능, 클러스터 생성·확장, 노드그룹 편집과 본인의 전용 namespace에서 워크로드 변경·셸 사용입니다. 클러스터 삭제와 전체 권한 kubeconfig는 포함하지 않습니다.',
				'drover_admin: 프로젝트 내 클러스터 관리·삭제·인증서 회전과 전체 권한 kubeconfig를 포함합니다. 템플릿 전역 관리나 서비스 전체 설정 변경 권한은 아닙니다.',
				'drover-inventory_reader: 클러스터·상태·이벤트·operation과 일반 workload 목록 조회입니다. ConfigMap·Secret 읽기는 이 역할만으로 허용되지 않습니다.',
				'drover-access_user: 제한된 읽기 전용 user 등급 kubeconfig와 Pod 로그입니다. 화면에서 목록·상세도 열려면 inventory 권한을 함께 준비합니다.',
				'drover-clusters_editor: 클러스터 생성·scale, 노드그룹 생성/수정·Stampede 설정과 노드 네트워크 연결입니다. SSH 키를 지정한 생성에는 drover-access_admin 조건도 추가로 필요합니다.',
				'drover-workloads_editor: editor 등급 kubeconfig, workload 편집·재시작·scale·삭제와 셸입니다. 본인의 프로젝트+사용자 전용 namespace만 허용하며 ConfigMap·Secret 조회에도 이 조건이 적용됩니다. 일반 editor가 작성하는 Secret은 Opaque 타입으로 제한됩니다.',
				'drover-clusters_admin: 클러스터·비기본 노드그룹 삭제, 추가 노드 네트워크 분리, 실행 권한 재인가와 인증서 회전입니다. 이 세부 역할만으로 전체 권한 kubeconfig가 허용되지는 않습니다.',
				'drover-access_admin: 전체 권한 kubeconfig와 namespace 제한 없는 workload 접근입니다. 이 역할만으로 클러스터 생성·삭제 권한까지 생기지는 않습니다.',
				'kubeconfig API의 기본 grade는 user입니다. workloads_editor만 있다면 editor grade가 필요합니다. 전체 권한 파일은 별도 확인을 거쳐 요청합니다. 클러스터 생성·확장·삭제·실행 권한 재인가와 전체 권한 kubeconfig 요청에는 제한되지 않은 사용자 자격이 필요합니다. API는 프로젝트와 자격 준비 상태를 검사하며 실제 클라우드 작업에는 위임 가능한 프로젝트 역할과 native 권한도 필요합니다.'
			],
			callout: { tone: 'warning', title: '다운로드한 kubeconfig는 별도 자격입니다', text: '특히 전체 권한 인증서는 IAM 역할을 회수하는 것만으로 이미 받은 파일이 무효화되지 않습니다. Drover의 인증서 회전은 HA control-plane 재시작을 통한 만료 임박 인증서 갱신이며, 유출된 인증서의 폐기를 보장하지 않습니다. 유출 시 운영자와 별도의 자격 폐기·접근 차단 절차를 확인하세요. SSH 로그인과 Kubernetes 접속 권한도 서로 다릅니다.' },
			links: [{ label: 'Drover', href: '/docs/drover' }]
		},
		{
			id: 'lumen', title: '8. Lumen: 채팅·Studio·도구·키·기록',
			hierarchy: serviceHierarchy('lumen'),
			bullets: [
				'lumen_reader: 허용된 모델·사용량·자산 정보와 해당 프로젝트에서 본인이 소유한 대화·실행 기록 조회입니다. 모델 실행은 포함하지 않습니다.',
				'lumen_user: reader 기능과 텍스트 채팅·이미지 생성/편집·음성/전사·실시간 음성·허용된 도구/에이전트 사용입니다. 별도 asset/파일 업로드·설정 편집·키 발급은 추가 권한이 필요합니다. 호환 API의 이미지 편집·전사에 직접 첨부하는 입력은 해당 기능 권한으로 처리됩니다.',
				'lumen_editor: user 기능에 자산·에이전트·MCP 설정·API 키 생성/편집과 본인 대화·memory 정리를 더합니다. 자산·에이전트 삭제 및 키 폐기는 별도입니다.',
				'lumen_admin: 프로젝트 범위에서 허용된 editor 기능과 자산·설정 삭제·키 폐기를 포함합니다. 다른 사람의 비공개 대화나 키 소유권을 우회하지 않으며 서비스 전체 provider·모델·가격·한도를 편집하는 권한은 아닙니다.',
				'lumen-inventory_reader: 모델·기능·사용량, 허용된 파일·asset·extension·agent 목록 조회입니다.',
				'lumen-history_reader: 허용된 대화·run·batch·memory와 실행 결과 조회입니다.',
				'lumen-chat_user: 텍스트 추론, 본인 대화 생성·사용과 실행 요청입니다. 모델 선택과 기록 확인에는 inventory_reader와 history_reader가 별도로 필요할 수 있습니다.',
				'lumen-images_user: 생성형 이미지 생성·편집입니다. native asset을 이용한 이미지 편집에는 asset 읽기, 브라우저의 별도 입력 업로드에는 assets_editor가 추가로 필요합니다. 호환 API의 직접 파일 업로드 편집은 이미지 기능 scope를 검사합니다. VM 부팅 이미지나 컨테이너 레지스트리 권한이 아닙니다.',
				'lumen-audio_user: 음성 생성·전사·실시간 음성입니다. native asset을 이용한 전사에는 asset 읽기, 브라우저의 별도 입력 업로드에는 assets_editor가 추가로 필요합니다. 호환 API의 직접 파일 업로드 전사는 음성 기능 scope를 검사합니다.',
				'lumen-tools_user: 허용된 도구·MCP·검색 실행과 에이전트 사용입니다. 대화 실행·원격 도구의 자격과 동의 조건을 대신하지 않습니다.',
				'lumen-assets_editor: 현재 프로젝트에서 본인 파일·asset을 업로드하고 본인 소유 custom tool·skill 등 extension을 생성/편집합니다. 다른 사용자의 자산이나 공개 extension을 편집하는 권한은 아니며, 삭제는 resources_admin으로 분리됩니다.',
				'lumen-agents_editor: 허용된 에이전트 생성·편집·복제와 코드 workspace/Git 자격 설정입니다. 다른 사용자의 소유권과 원격 Git 접근을 우회하지 않습니다.',
				'lumen-mcp_editor: 본인 MCP 설정 생성·편집, 게시된 MCP 서버의 현재 설정에 대한 본인별 활성화 승인과 OAuth 시작입니다. OAuth 시작에는 제한되지 않은 Keystone 사용자 세션이 필요합니다. MCP 설정 삭제·OAuth 연결 해제와 실제 도구 실행은 각각 별도 권한입니다.',
				'lumen-keys_editor: 본인 Lumen API 키 조회·발급·편집입니다. 발급할 키에 넣는 모든 scope에 대해서도 현재 권한을 보유해야 합니다.',
				'lumen-history_editor: 본인 대화 삭제·정리와 memory 생성·수정·삭제입니다. 자산·API 키 삭제 권한과는 다릅니다.',
				'lumen-resources_admin: 허용된 파일·asset·extension·agent 삭제와 본인 API 키 폐기입니다. 이 세부 역할 하나만으로 채팅·키 발급·대화 기록 삭제까지 허용되지 않습니다.'
			],
			paragraphs: [
				'기본 텍스트 채팅의 세부 조합은 lumen-inventory_reader + lumen-history_reader + lumen-chat_user입니다. 도구를 쓰려면 lumen-tools_user를, 파일을 올리려면 lumen-assets_editor를 추가합니다. 여러 작업이 연결된 화면은 각 작업의 권한을 모두 확인합니다.',
				'Batch 접수는 chat·images·audio 사용 권한 중 하나로 시작할 수 있지만, 혼합 batch 안의 각 항목은 해당 기능 권한을 다시 검사합니다. 선택 모델의 기능·가격·사용 한도와 storage/scanner 준비도 별도 조건입니다.'
			],
			links: [{ label: 'Lumen', href: '/docs/lumen' }]
		},
		{
			id: 'palimpsest', title: '9. Palimpsest: 패키지 조회·다운로드·게시·키',
			hierarchy: serviceHierarchy('palimpsest'),
			bullets: [
				'palimpsest_reader: 허용된 패키지·버전·레이어·묶음과 export 상태의 메타데이터 조회입니다. 실제 콘텐츠 다운로드는 포함하지 않습니다.',
				'palimpsest_user: reader 기능과 허용된 패키지·레이어·묶음·완료된 export 다운로드 및 캐시 읽기입니다.',
				'palimpsest_editor: user 기능, 프로젝트 namespace 등록·패키지/태그·캐시 게시와 본인 키 발급/조회입니다. 키 회수는 별도입니다.',
				'palimpsest_admin: 프로젝트의 editor 기능과 본인 패키지 키 회수입니다. 이 역할만으로 프로젝트 패키지 삭제·전체 카탈로그 관리·빌드 작업 관리가 허용되지는 않습니다.',
				'palimpsest-inventory_reader: 허용된 프로젝트 패키지·버전과 native Hub inventory 메타데이터 조회입니다.',
				'palimpsest-download_user: 패키지·레이어 다운로드와 캐시 읽기입니다. 기본 정책에서는 inventory도 허용하지만 운영 정책에서 두 작업을 별도로 제한할 수 있습니다.',
				'palimpsest-publish_editor: namespace 등록·패키지/태그·빌드 캐시 게시, legacy 업로드·묶음 import와 image export 생성/삭제입니다. 다운로드·키 발급은 자동 포함하지 않습니다. image export 생성에는 원본 프로젝트의 접근 가능한 Glance 이미지와 설정된 위임 역할이 별도로 필요합니다.',
				'palimpsest-keys_editor: 본인 패키지 키 발급·목록 조회입니다. 현재 허용된 package/cache action만 키에 넣을 수 있으며 발급 권한 자체가 다운로드·게시 권한은 아닙니다.',
				'palimpsest-keys_admin: 본인 패키지 키 목록 조회·회수입니다. 새 키 발급이나 다른 사용자의 키 회수는 포함하지 않습니다.',
				'프로젝트 패키지와 캐시 업로드는 제한된 패키지 키로 수행합니다. 정확한 프로젝트·패키지 이름 또는 명시적 프로젝트 전체 범위, action·만료 조건을 모두 확인합니다. 키는 Keystone 자격이 아니며 VM·스토리지 권한을 만들지 않습니다.'
			],
			paragraphs: [
				'Afterglow가 관리하는 공개·sealed 레이어 조회, native Hub에서 공개·공유·소유 조건으로 보이는 묶음, 프로젝트 비공개 패키지는 서로 다른 경로입니다. 한 목록이 보이거나 비어 있다고 다른 경로의 권한·데이터까지 판단하지 마세요.',
				'게시된 클라우드 환경을 VM으로 만들려면 프로젝트 쓰기 + Palimpsest 다운로드 + 실제 클라우드 자원 권한이 함께 필요합니다. 환경이 공개되고 cloud 실행을 지원해야 합니다. 일반적인 브라우저 사용 조합은 project_member + palimpsest_user이며 native 정책·쿼터를 추가 확인합니다.',
				'패키지 삭제는 일반 조직 서비스 등급으로 제공되지 않습니다. 검증된 개인 프로젝트 소유자의 별도 허용 경로를 조직 project_owner나 palimpsest_admin에 일반화하지 않습니다. 키 폐기는 이미 게시된 패키지나 내려받은 파일을 삭제하지 않습니다.'
			],
			links: [{ label: 'Palimpsest', href: '/docs/palimpsest' }]
		},
		{
			id: 'credentials', title: '10. API 키·MCP·접속 파일은 역할과 같지 않습니다',
			bullets: [
				'Lumen API 키는 발급자의 현재 권한과 키에 허용한 scope의 교집합으로 동작합니다. 키 발급 권한만으로 모든 모델 기능을 담을 수 없고 만료·폐기·사용 한도도 적용됩니다.',
				'Palimpsest 패키지 키는 package/cache 작업과 명시한 패키지 범위를 제한합니다. 일반 브라우저 세션 대신 아무 API에나 쓸 수 없고 다른 키를 발급·관리하는 자격도 아닙니다.',
				'Afterglow 인바운드 MCP OAuth·개인 키는 외부 AI가 Afterglow를 호출하도록 위임하는 별도 기능입니다. 저장된 프로젝트 목록·도구 권한·발급자의 현재 권한을 함께 검사합니다. Lumen의 아웃바운드 MCP 설정 역할을 얻었다고 인바운드 클라우드 작업 권한이 생기지 않습니다.',
				'WireGuard .conf·QR, kubeconfig, SSH 키·DB 비밀번호는 실제 접속 자격입니다. IAM 목록에서 역할을 지웠다는 사실만으로 이미 배포한 모든 자격이나 사본이 무효화되지는 않습니다. 서비스별 비활성화·회수·회전 절차와 실제 접속 차단을 확인하세요.'
			],
			links: [{ label: 'MCP', href: '/docs/mcp' }]
		},
		{
			id: 'assign', title: '11. 사용자에게 필요한 권한을 정하고 부여하기',
			steps: [
				{ title: '대상 사용자와 프로젝트를 확인합니다', text: ['manager는 조직 IAM에서 초대받을 이메일과 대상 프로젝트를 선택합니다. 기존 참여자는 정확한 사용자 ID를 확인합니다. 프로젝트별로 어떤 조회·사용·편집·삭제가 필요한지 구분하며 다른 조직의 동명 프로젝트와 혼동하지 않습니다.'] },
				{ title: '프로젝트 역할과 서비스 역할을 따로 선택합니다', text: ['조회만 하는 사용자는 project_reader와 필요한 서비스 reader를 선택합니다. 클라우드 자원을 만드는 사용자는 project_member와 해당 서비스 등급 또는 세부 역할을 조합합니다. 서비스 역할만 필요한 사용자의 native member 필요 여부는 실제 작업 기준으로 판단하고 모든 서비스에 무조건 추가하지 않습니다.'] },
				{ title: '위임 가능한 범위에서 저장합니다', text: ['manager는 같은 조직의 프로젝트 멤버·서비스 역할을, project_owner와 project_admin은 허용된 해당 프로젝트 역할을 관리합니다. project_admin 추가·회수는 owner 또는 manager가 담당합니다. 소유권은 별도의 이전 기능을 사용합니다. 그룹·상속 역할은 원래 할당 경로에서 변경해야 합니다.'] },
				{ title: '대상 사용자로 실제 필요한 작업을 확인합니다', text: ['사용자는 대상 프로젝트로 전환하고 권한을 새로 조회합니다. 새 권한이 기존 자격에 반영되지 않았다면 재로그인하거나 제한된 키를 적절한 범위로 다시 발급합니다. 역할 변경 뒤에도 예전 화면·다운로드 파일을 현재 권한의 증거로 쓰지 않습니다. 조회와 실제 변경은 구분하여 필요한 작업만 확인하세요.'] }
			],
			bullets: [
				'관측 담당자: project_reader + waygate_reader + drover_reader + lumen_reader + palimpsest_reader. 각 서비스의 허용된 메타데이터·기록을 조회하되 VPN 비밀·kubeconfig·패키지 콘텐츠 사용 권한은 별도입니다.',
				'VPN 접속자: project_member + waygate_user와 본인에게 할당된 활성 프로필. 게이트웨이 생성·다른 사람의 프로필 관리까지 필요하지 않다면 editor/admin 등급으로 넓히지 않습니다.',
				'Kubernetes 작업자: project_member + drover_editor로 클러스터 생성·확장과 본인 namespace workload를 다룹니다. 삭제나 전체 권한 접속이 실제로 필요할 때만 해당 세부 관리 역할을 검토합니다.',
				'AI 채팅 사용자: 프로젝트 참여 권한 + lumen_user. 텍스트 채팅만 허용하려면 inventory_reader·history_reader·chat_user 세부 조합을 사용합니다. 파일 업로드와 키 발급·폐기는 각각의 추가 권한을 확인합니다.',
				'패키지 다운로드 사용자: 프로젝트 참여 권한 + palimpsest_user. 게시와 키 발급까지 맡기면 palimpsest_editor, 본인 키 회수도 맡기면 palimpsest-keys_admin을 추가하거나 palimpsest_admin을 검토합니다.'
			]
		},
		{
			id: 'troubleshooting', title: '12. 권한 때문에 막혔을 때 확인할 순서',
			steps: [
				{ title: '작업 범위와 역할 출처를 확인합니다', text: ['현재 사용자·작업 도메인·프로젝트와 자원 소유 프로젝트를 대조합니다. manager는 정확한 Default에서, 서비스 역할은 해당 자원 프로젝트에서 확인합니다. 직접 할당뿐 아니라 그룹·상속·실제 역할 연결도 확인합니다.'] },
				{ title: '실패한 작업의 조건을 하나씩 확인합니다', text: ['목록 조회, 비밀 다운로드, 생성, 일반 편집, 활성/비활성, 삭제는 같은 권한이 아닙니다. 위 서비스 절에서 필요한 역할과 함께 소유자·namespace·프로필 활성·API 키 scope·자원 상태 조건을 확인합니다.'] },
				{ title: '권한 거부와 확인 실패를 구분합니다', text: ['403은 현재 요청의 권한 또는 범위가 거부된 상태입니다. 404는 자원이 없거나 현재 범위에서 볼 수 없을 수 있습니다. 503·권한 조회 실패는 역할이 없다고 확정된 결과가 아니며 정책·인증·서비스 연결 확인이 필요합니다. 확인 중인 버튼을 반복 제출하여 우회하지 않습니다.'] },
				{ title: '안전한 정보로 지원을 요청합니다', text: ['서비스·수행 작업·프로젝트 ID·자원 ID·발생 시각·요청 ID와 비밀을 제외한 오류를 전달합니다. token, API 키, VPN 설정, kubeconfig, 비밀번호는 첨부하지 않습니다. 쓰기 결과가 불명이면 새 요청 전에 기존 작업과 자원을 조회합니다.'] }
			],
			paragraphs: ['문서의 역할명은 할당 가능한 실제 프리셋 이름이고, 화면의 capability는 서비스가 현재 허용한 작업을 요약한 표시입니다. 같은 이름의 capability가 보인다고 그 역할이 직접 할당되었거나 관련 API가 모두 허용된다고 판단하지 마세요. 최종 허용 여부는 각 서비스 요청 시 다시 검사합니다.']
		}
	],
	related: ['getting-started', 'waygate', 'drover', 'lumen', 'palimpsest', 'mcp'],
	consoleLinks: [
		{ label: '도메인 IAM', href: '/dashboard/iam/users' },
		{ label: '프로젝트 관리', href: '/dashboard/iam/projects' }
	]
};
