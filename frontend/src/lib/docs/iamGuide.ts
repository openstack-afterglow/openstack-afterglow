import type { DocGuide } from './types';

export const iamGuide: DocGuide = {
	slug: 'iam',
	name: 'IAM · 프로젝트 권한',
	title: '사용자별 역할과 서비스 이용 권한 이해하기',
	summary: '표준 reader와 member·manager·admin, 실제 프로젝트 역할 연결로 네 서비스의 조회·관리를 이해하고 소유권·비밀·위임 범위를 확인합니다.',
	category: 'start',
	keywords: ['IAM', 'RBAC', 'Keystone', 'manager', '역할', '권한', '프로젝트', '서비스', '최소 권한'],
	prerequisites: [
		'권한은 사용자 이름만이 아니라 정확한 사용자·조직·프로젝트에 연결됩니다. 먼저 사용하려는 프로젝트와 작업을 정하세요.',
		'이 문서는 현재 소스의 기본 정책을 설명합니다. 실제 배포의 정책 변경, 역할 연결, 서비스 활성화와 쿼터에 따라 허용 결과가 달라질 수 있습니다.',
		'서비스별 등급이나 세부 역할을 추가로 부여하지 않습니다. 표준 역할과 실제 프로젝트 역할 연결을 사용하며 최종 허용은 현재 native 정책이 결정합니다.'
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
				'프로젝트 관리: 조직 프로젝트 생성, 멤버와 위임 가능한 역할 관리, project_admin 위임, 전용 절차를 통한 소유권 이전과 안전 삭제. 마지막 manager·소유권·Default 프로젝트 보호는 유지됩니다.',
				'로그인과 배분: 해당 조직의 로그인 방법·정책, 모니터링, 허용된 예산 안의 프로젝트 쿼터와 공용 compute pool의 프로젝트별 추가 상한을 관리합니다. 조직 공용 풀 자체의 한도를 임의로 늘리는 권한은 아닙니다.',
				'조직 Default의 manager가 가진 IAM 권한과 자원 작업의 현재 프로젝트 범위는 구분합니다. 네 서비스의 자원 관리는 해당 자원 프로젝트에서 유효한 native member·manager·admin을 검사합니다. 여기서 manager는 해당 프로젝트 범위의 표준 역할이며 Default의 조직 manager 권한을 다른 프로젝트로 자동 옮기지 않습니다. 다른 프로젝트·다른 사용자의 비밀·전역 운영 권한도 얻지는 않습니다.'
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
				'project_admin: 해당 프로젝트 구성원과 위임 가능한 프로젝트 역할을 관리합니다. project_member 권한도 포함하지만 다른 project_admin의 추가·회수와 소유권 변경을 일반 멤버 편집으로 할 수는 없습니다.',
				'project_owner: 프로젝트 소유자입니다. project_admin을 위임하고 전용 소유권 이전 절차를 이용합니다. 일반 역할 선택으로 두 번째 소유자를 만들지 않으며 소유권을 정리하지 않은 삭제·탈퇴는 차단될 수 있습니다.',
				'프로젝트 계층은 project_owner → project_admin → project_member → project_reader이고, project_member → member 및 project_reader → reader가 연결됩니다. 실제 Keystone 연결이 준비되어 있어야 하며 이름만 같은 사용자 정의 역할로 대체하지 않습니다.',
				'project_creator: 조직 Default에서 프로젝트 생성을 위임받는 별도 역할입니다. manager도 별도 creator 없이 생성할 수 있습니다. 생성자는 새 프로젝트의 소유자가 되지만 다른 프로젝트·조직 사용자·로그인 정책을 관리할 권한까지 얻지는 않습니다. 일반 생성자의 프로젝트 삭제에는 현재 생성 권한과 단독 소유권, 빈 프로젝트 확인이 함께 필요합니다.',
				'reader는 허용된 일반 조회, member·manager·admin은 현재 프로젝트 자원 관리에 사용합니다. member가 project_admin의 멤버 관리 권한을 자동으로 얻지는 않습니다. 사용자 정의·프로젝트 역할은 현재 native 역할 그래프의 실제 연결로 표준 core 권한을 얻은 경우에만 그 권한으로 인정합니다. 이름이나 정책 설정만으로 core reader·member 권한을 만들지는 않습니다.'
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
				'Zun · 컨테이너와 Magnum · 클러스터: 제공되는 배포에서 각 native 서비스의 프로젝트 정책을 사용합니다. 생성·수명주기 변경에는 현재 프로젝트 범위에서 해당 작업의 native 허용이 필요합니다.',
				'Cloud Shell: 시작·접속 ticket·홈 초기화는 읽기 전용 작업이 아니므로 프로젝트 쓰기 권한이 필요합니다. 셸이 열려도 CLI는 사용자의 실제 프로젝트 권한을 따르며 다른 서비스 권한을 추가하지 않습니다.'
			]
		},
		{
			id: 'service-access', title: '5. 네 서비스도 같은 표준 프로젝트 역할을 사용합니다',
			paragraphs: [
				'Waygate·Drover·Lumen·Palimpsest는 reader로 허용된 비밀 없는 정보를 조회하고 member·manager·admin으로 현재 프로젝트 자원을 관리합니다. project_owner·project_admin·project_member·project_reader는 위의 실제 Keystone 연결을 통해 평가합니다.',
				'capability와 API의 action·scope 이름은 작업을 구분하는 내부 식별자이지 추가로 할당할 IAM 역할이 아닙니다. 과거 서비스 역할 할당은 읽기 전용 이력으로 남지만 그 이름만으로 서비스 권한을 주지 않습니다. 현재 native 그래프의 실제 연결로 얻은 표준 core 권한은 역할 출처와 관계없이 인정하며, 이 안내가 기존 할당이나 연결을 자동 변경하지는 않습니다.',
				'프로젝트·소유자·비공개/공유 범위·자격 제한·쿼터·현재 native capability는 계속 적용됩니다. personal_project_owner metadata만으로 권한을 우회하지 않습니다. native 정책은 작업을 더 제한할 수 있지만 유효한 core 쓰기 권한이 없는 reader·사용자 정의 역할만으로 변경·접속 자격 발급·유료 추론을 허용할 수는 없습니다. 정책 차이는 운영자에게 확인하며 화면에서 허용을 만들어 내지 않습니다.',
				'전역 provider 자격·통계·정책·카탈로그·controller 운영은 검증된 system-admin 전용입니다. 현재 프로젝트의 admin이나 project_owner라는 이유로 이 전역 권한을 얻지는 않습니다.'
			]
		},
		{
			id: 'waygate', title: '6. Waygate: VPN 조회·접속·발급·회수',
			bullets: [
				'reader는 허용된 게이트웨이·클라이언트·네트워크 목록과 상태를 조회합니다. member·manager·admin은 현재 프로젝트의 게이트웨이·클라이언트·라우팅을 관리하며 native 클라우드 정책과 자원 상태도 충족해야 합니다.',
				'VPN .conf 다운로드와 QR 표시는 GET이어도 비밀 자격 접근이므로 member 이상이 필요합니다. 본인에게 할당된 활성 프로필만 사용할 수 있고 서버 준비·프로젝트·소유권 조건은 유지됩니다. 번들 작업도 다른 사용자의 비밀 키를 노출하지 않습니다.'
			],
			links: [{ label: 'Waygate', href: '/docs/waygate' }]
		},
		{
			id: 'drover', title: '7. Drover: 클러스터 운영과 Kubernetes 접속',
			bullets: [
				'reader는 허용된 클러스터·상태·이벤트·작업·템플릿 정보를 조회합니다. member·manager·admin은 프로젝트 클러스터와 허용된 workload를 관리합니다. namespace·소유권·native 정책·위임 자격의 제한은 유지됩니다.',
				'kubeconfig·접속 ticket·Secret 값은 GET이어도 일반 조회가 아닙니다. member 이상과 해당 native 접속 capability가 필요합니다. user·editor·admin 같은 접속 파일 grade는 인증서의 접근 범위이지 별도로 부여할 IAM 서비스 등급이 아닙니다. 전체 권한 파일·클라우드 실행은 별도의 확인과 자격 준비 조건을 따릅니다.'
			],
			callout: { tone: 'warning', title: '다운로드한 kubeconfig는 별도 자격입니다', text: '특히 전체 권한 인증서는 IAM 역할을 회수하는 것만으로 이미 받은 파일이 무효화되지 않습니다. Drover의 인증서 회전은 HA control-plane 재시작을 통한 만료 임박 인증서 갱신이며, 유출된 인증서의 폐기를 보장하지 않습니다. 유출 시 운영자와 별도의 자격 폐기·접근 차단 절차를 확인하세요. SSH 로그인과 Kubernetes 접속 권한도 서로 다릅니다.' },
			links: [{ label: 'Drover', href: '/docs/drover' }]
		},
		{
			id: 'lumen', title: '8. Lumen: 채팅·Studio·도구·키·기록',
			bullets: [
				'reader는 보이는 모델·자산·사용량과 본인의 허용된 대화·실행 기록을 조회합니다. 유료 추론·채팅 실행·이미지/음성 생성·도구 실행은 읽기가 아니며 member 이상이 필요합니다.',
				'member·manager·admin은 현재 프로젝트에서 허용된 추론과 파일·에이전트·MCP 설정·본인 기록·API 키를 관리합니다. 다른 사람의 비공개 대화·파일·키 소유권은 우회하지 않습니다. 원격 도구의 동의·OAuth·모델 기능·사용 한도·scanner 준비도 별도로 확인합니다.'
			],
			links: [{ label: 'Lumen', href: '/docs/lumen' }]
		},
		{
			id: 'palimpsest', title: '9. Palimpsest: 패키지 조회·다운로드·게시·키',
			bullets: [
				'reader는 공개·공유·소유 조건으로 보이는 패키지·버전·레이어·묶음과 허용된 콘텐츠를 조회합니다. 비공개 프로젝트·패키지 범위와 native 다운로드 정책은 그대로 적용됩니다.',
				'member·manager·admin은 현재 프로젝트에서 허용된 namespace·패키지·태그·캐시·export와 본인 패키지 키를 관리합니다. 키의 package/cache action·대상·만료와 발급 시 원래 표준 역할 상한은 현재 권한과 함께 검사합니다. 키 회수는 이미 받은 파일을 삭제하지 않습니다.',
				'클라우드 환경의 VM 실행에는 현재 프로젝트 쓰기와 접근 가능한 원본·native 클라우드 권한·쿼터가 함께 필요합니다. 공개 환경이라는 이유로 실행이나 전역 catalog·build controller 관리가 허용되지는 않습니다.'
			],
			links: [{ label: 'Palimpsest', href: '/docs/palimpsest' }]
		},
		{
			id: 'credentials', title: '10. API 키·MCP·접속 파일은 역할과 같지 않습니다',
			bullets: [
				'Lumen API 키는 발급 시 원래 표준 역할 상한·키 scope와 발급자의 현재 권한의 교집합으로 동작합니다. 이후 역할 승격으로 옛 키의 상한이 커지지 않으며 만료·폐기·사용 한도도 적용됩니다.',
				'Palimpsest 패키지 키는 package/cache 작업과 명시한 패키지 범위를 제한합니다. 일반 브라우저 세션 대신 아무 API에나 쓸 수 없고 다른 키를 발급·관리하는 자격도 아닙니다.',
				'Afterglow 인바운드 MCP OAuth·개인 키는 외부 AI가 Afterglow를 호출하도록 위임하는 별도 기능입니다. 저장된 프로젝트·도구 scope·발급자의 현재 권한을 함께 검사합니다. Lumen 아웃바운드 MCP 설정을 관리한다고 인바운드 클라우드 권한이 생기지는 않습니다.',
				'WireGuard .conf·QR, kubeconfig, SSH 키·DB 비밀번호는 실제 접속 자격입니다. IAM 목록에서 역할을 지웠다는 사실만으로 이미 배포한 모든 자격이나 사본이 무효화되지는 않습니다. 서비스별 비활성화·회수·회전 절차와 실제 접속 차단을 확인하세요.'
			],
			links: [{ label: 'MCP', href: '/docs/mcp' }]
		},
		{
			id: 'assign', title: '11. 사용자에게 필요한 권한을 정하고 부여하기',
			steps: [
				{ title: '대상 사용자와 프로젝트를 확인합니다', text: ['manager는 조직 IAM에서 초대받을 이메일과 대상 프로젝트를 선택합니다. 기존 참여자는 정확한 사용자 ID를 확인합니다. 프로젝트별로 어떤 조회·사용·편집·삭제가 필요한지 구분하며 다른 조직의 동명 프로젝트와 혼동하지 않습니다.'] },
				{ title: '표준 프로젝트 역할을 선택합니다', text: ['조회만 필요하면 project_reader 또는 reader, 실행·자원 관리가 필요하면 project_member 또는 member를 선택합니다. 프로젝트 구성원 관리가 실제로 필요할 때 project_admin을 위임합니다. 네 서비스의 별도 등급이나 세부 역할은 추가하지 않습니다.'] },
				{ title: '위임 가능한 범위에서 저장합니다', text: ['manager는 같은 조직의 프로젝트 멤버·역할을, project_owner와 project_admin은 허용된 해당 프로젝트 역할을 관리합니다. project_admin 추가·회수는 owner 또는 manager가 담당합니다. 소유권은 별도의 이전 기능을 사용합니다. 그룹·상속 역할은 원래 할당 경로에서 변경해야 합니다.'] },
				{ title: '대상 사용자로 실제 필요한 작업을 확인합니다', text: ['사용자는 대상 프로젝트로 전환하고 권한을 새로 조회합니다. 새 권한이 기존 자격에 반영되지 않았다면 재로그인하거나 제한된 키를 적절한 범위로 다시 발급합니다. 역할 변경 뒤에도 예전 화면·다운로드 파일을 현재 권한의 증거로 쓰지 않습니다. 조회와 실제 변경은 구분하여 필요한 작업만 확인하세요.'] }
			],
			bullets: [
				'관측 담당자는 reader, VPN·Kubernetes·AI 실행·패키지 게시 담당자는 member가 기본입니다. 역할을 넓히기 전에 현재 프로젝트·자원 소유권·비공개 범위·native capability를 확인합니다. 제한된 위임이 필요하면 서비스 IAM 역할을 추가하는 대신 해당 기능의 키 scope를 좁힙니다.'
			]
		},
		{
			id: 'troubleshooting', title: '12. 권한 때문에 막혔을 때 확인할 순서',
			steps: [
				{ title: '작업 범위와 역할 출처를 확인합니다', text: ['현재 사용자·작업 도메인·프로젝트와 자원 소유 프로젝트를 대조합니다. 조직 manager는 정확한 Default에서, 자원 작업의 표준 역할은 현재 프로젝트에서 확인합니다. 직접 할당·그룹·상속·실제 역할 연결을 함께 확인합니다.'] },
				{ title: '실패한 작업의 조건을 하나씩 확인합니다', text: ['일반 조회와 비밀 자격 GET·실행·변경을 구분합니다. 표준 역할뿐 아니라 소유자·namespace·프로필 활성·키 scope·원래 역할 상한·자원 상태와 현재 native capability를 확인합니다.'] },
				{ title: '권한 거부와 확인 실패를 구분합니다', text: ['403은 현재 요청의 권한 또는 범위가 거부된 상태입니다. 404는 자원이 없거나 현재 범위에서 볼 수 없을 수 있습니다. 503·권한 조회 실패는 역할이 없다고 확정된 결과가 아니며 정책·인증·서비스 연결 확인이 필요합니다. 확인 중인 버튼을 반복 제출하여 우회하지 않습니다.'] },
				{ title: '안전한 정보로 지원을 요청합니다', text: ['서비스·수행 작업·프로젝트 ID·자원 ID·발생 시각·요청 ID와 비밀을 제외한 오류를 전달합니다. token, API 키, VPN 설정, kubeconfig, 비밀번호는 첨부하지 않습니다. 쓰기 결과가 불명이면 새 요청 전에 기존 작업과 자원을 조회합니다.'] }
			],
			paragraphs: ['화면의 capability는 현재 서비스가 허용한 작업의 요약이며 직접 할당된 역할의 증거가 아닙니다. 정책 조회 실패는 거부 확정이 아니고, 최종 허용은 매 요청의 native 검사로 결정됩니다.']
		}
	],
	related: ['getting-started', 'waygate', 'drover', 'lumen', 'palimpsest', 'mcp'],
	consoleLinks: [
		{ label: '도메인 IAM', href: '/dashboard/iam/users' },
		{ label: '프로젝트 관리', href: '/dashboard/iam/projects' }
	]
};
