import type { DocGuide } from './types';

// UI 명칭·경로: config/nav.ts 및 각 dashboard route/component.
// 작업 계약: docs/api/{instances,networks,security-groups,routers,loadbalancers,volumes,file-storage}.md.
// 문서와 차이가 있는 경우 현재 backend/app/api 및 services 구현을 우선한다.
export const coreGuides: DocGuide[] = [
	{
		slug: 'nova',
		name: 'Nova',
		title: 'Nova 인스턴스 생성부터 접속·정리까지',
		summary: '부팅 소스와 플레이버를 선택하고 네트워크·SSH 접근을 준비한 뒤, VM 상태와 실제 게스트 준비 상태를 구분해 확인합니다.',
		category: 'openstack',
		keywords: ['Nova', '인스턴스', 'VM', '플레이버', 'SSH', 'cloud-init', '부팅 볼륨'],
		prerequisites: [
			'작업할 프로젝트를 선택하고 인스턴스 생성·변경 권한과 instances/vCPU/RAM 쿼터를 확인합니다.',
			'부팅할 Glance 이미지 또는 available 상태의 bootable Cinder 볼륨, 선택 가능한 플레이버를 준비합니다.',
			'서브넷이 있는 네트워크, 필요한 보안 그룹, 등록 키페어의 개인키를 준비합니다. GitHub 사용자 방식은 지원되는 Ubuntu 이미지 직접 부팅에서만 선택합니다.',
			'외부에서 접속하려면 접근 경로와 외부 네트워크의 Floating IP 여유를 확인합니다. 내부망 접속에는 반드시 Floating IP가 필요한 것은 아닙니다.',
		],
		sections: [
			{
				id: 'concepts',
				title: '1. VM을 구성하는 서비스와 상태',
				paragraphs: [
					'Nova는 가상 머신의 배치와 실행을 담당합니다. 이미지(Glance)는 초기 OS, 플레이버는 CPU·RAM 등 자원 규격, 볼륨(Cinder)은 디스크, 네트워크(Neutron)는 포트와 IP를 제공합니다.',
					'Afterglow 생성 과정에는 부트 볼륨 준비, Nova 서버 생성, 추가 볼륨 연결, 테넌트 네트워크의 Floating IP 준비 등이 포함될 수 있습니다. 라이브러리를 선택한 경우에만 Manila/OverlayFS 관련 준비가 추가됩니다.',
				],
				bullets: [
					'BUILD는 생성 중, ACTIVE는 Nova 실행 상태, SHUTOFF는 정지 상태, ERROR는 실패 상태입니다.',
					'생성 진행 화면의 완료와 ACTIVE는 cloud-init 완료, SSH 로그인 성공, 애플리케이션 정상 응답을 보장하지 않습니다.',
					'플레이버가 선택 가능해도 용량이 예약된 것은 아닙니다. 제출 직전에 쿼터와 같은 호스트의 CPU·RAM·GPU 여유를 다시 확인하며 최종 배치는 Nova가 결정합니다.',
				],
			},
			{
				id: 'prepare-access',
				title: '2. 네트워크와 SSH 접근 준비',
				steps: [
					{
						title: '사용할 네트워크의 서브넷과 경로 확인',
						text: ['네트워크 화면에서 대상 네트워크를 열어 CIDR·게이트웨이·DHCP를 확인합니다. 외부 접속이 필요하면 라우터에 이 서브넷의 내부 인터페이스와 외부 게이트웨이가 있는지 확인합니다. 기본 네트워크라는 표시만으로 외부 접속을 판단하지 않습니다.'],
						links: [{ label: '네트워크', href: '/dashboard/network/networks' }, { label: '라우터', href: '/dashboard/network/routers' }],
					},
					{
						title: 'SSH 전용 보안 그룹 준비',
						text: ['보안 그룹을 생성하고 수신(ingress), TCP, 시작·끝 포트 22, IPv4, 원격 대상 CIDR을 지정합니다. 자신의 실제 접속 원본 공인 IP/32 또는 승인된 VPN 대역으로 제한합니다. 예시 203.0.113.10/32는 문서용 주소이므로 실제 접속 주소로 교체합니다.', 'IPv6로 접속할 때는 별도의 IPv6 규칙과 승인된 /128 또는 대역이 필요합니다. CIDR을 비우면 전체 대역으로 처리되므로 빈 값이나 0.0.0.0/0, ::/0으로 SSH를 개방하지 않습니다.'],
						links: [{ label: '보안 그룹', href: '/dashboard/network/security-groups' }],
					},
				],
				callout: { tone: 'warning', title: '접속 경로와 허용 규칙은 별개입니다', text: '라우터는 경로, Floating IP는 외부 주소와 Fixed IP의 매핑, 보안 그룹은 포트의 트래픽 허용 정책입니다. 어느 하나도 나머지 두 가지를 대신하지 않습니다.' },
			},
			{
				id: 'create',
				title: '3. 인스턴스 생성 마법사 진행',
				steps: [
					{
						title: '인스턴스 화면에서 생성 마법사 열기',
						text: ['부팅 소스에서 OS 이미지 또는 기존 부팅 볼륨 중 하나를 선택합니다. 기존 부팅 볼륨 목록에는 bootable이며 available인 볼륨만 표시됩니다. 기존 데이터를 재사용하는 볼륨을 새 빈 디스크로 착각하지 않습니다.'],
						links: [{ label: '인스턴스', href: '/dashboard/compute/instances' }],
					},
					{
						title: '플레이버와 필요한 라이브러리 선택',
						text: ['CPU·RAM과 용도를 기준으로 플레이버를 선택합니다. 선택 불가 사유가 쿼터 부족인지 호스트 용량 부족인지 읽습니다. 기본 OS만 필요하면 라이브러리를 추가하지 않습니다. 라이브러리를 사용하는 경우 prebuilt는 준비된 읽기 전용 공유, dynamic은 VM 전용 공유를 사용하는 방식임을 확인합니다.'],
					},
					{
						title: '설정과 최종 검토',
						text: ['이름, 네트워크, 보안 그룹, SSH 접근 방식을 지정합니다. 등록 키페어는 보유한 개인키와 짝이 맞아야 합니다. GitHub 사용자 방식은 화면에서 공개키 확인을 마친 지원 대상에만 사용합니다.', '이미지 부팅에서는 부트 볼륨 크기와 VM 삭제 시 함께 삭제/보존 선택을 확인합니다. 기존 부팅 볼륨 재사용은 자동 삭제하지 않습니다. 추가 볼륨이나 cloud-init을 입력했다면 대상과 내용을 재검토한 뒤 VM 생성으로 제출합니다.'],
					},
				],
			},
			{
				id: 'connect-verify',
				title: '4. 생성 결과와 실제 접속 확인',
				steps: [
					{
						title: '목록과 상세에서 리소스 확인',
						text: ['진행 화면이 완료되면 인스턴스 목록을 새로고침하고 이름·UUID·상태·이미지/부트 볼륨·플레이버를 확인합니다. 상세의 인터페이스에서 네트워크, 포트 ID, Fixed IP와 FIP, 적용 보안 그룹을 대조합니다.', 'FIP가 필요한데 없다면 올바른 인터페이스의 + FIP를 사용합니다. 이미 FIP가 있다면 중복 할당하지 않습니다. 이 작업도 외부망·라우터·쿼터 조건을 충족해야 합니다.'],
					},
					{
						title: '게스트 초기화와 SSH 확인',
						text: ['상세의 콘솔/콘솔 로그에서 OS 부팅 오류를 확인하고, 이미지가 지정한 로그인 사용자와 개인키로 접속합니다. Ubuntu 이미지의 사용자 이름을 다른 OS에 그대로 적용하지 않습니다.', 'SSH 성공 후 게스트에서 cloud-init 상태와 사용할 서비스의 응답을 확인합니다. 아래 명령은 사용자가 접속한 게스트에서 실행할 읽기 전용 예시이며, 이 가이드 작성 중에는 실행하지 않았습니다. cloud-init이 없는 이미지에는 해당 명령이 적용되지 않습니다.'],
						command: { label: 'cloud-init 제공 이미지의 초기화 상태', code: 'cloud-init status --long' },
					},
				],
			},
			{
				id: 'operations',
				title: '5. 시작·정지와 디스크 연결',
				bullets: [
					'인스턴스 상세의 시작·정지·재부팅은 현재 상태에 맞게 수행합니다. 정지나 재부팅 전에 게스트의 쓰기 작업과 서비스 중단 영향을 확인합니다.',
					'볼륨 연결은 가상 디스크를 붙이는 작업입니다. 게스트 파일시스템 생성·마운트까지 자동으로 완료된 것으로 보지 않습니다. 기존 데이터가 있으면 포맷하지 않습니다.',
					'인터페이스 추가 후에는 게스트가 새 NIC를 인식하는지, 해당 인터페이스의 보안 그룹과 게스트 라우팅이 맞는지 별도로 확인합니다.',
					'플레이버 변경은 cold resize로 재시작이 발생합니다. VERIFY_RESIZE에서 게스트와 서비스가 정상인지 확인한 뒤 확정하거나 되돌리기를 선택해야 합니다.',
				],
			},
			{
				id: 'troubleshooting',
				title: '6. 흔한 장애를 순서대로 진단',
				bullets: [
					'플레이버 선택/제출 차단: 409는 확인된 쿼터·용량 부족, 503은 용량이나 외부 정보를 검증하지 못한 상황일 수 있습니다. 화면 사유를 기록하고 관리자에게 프로젝트·플레이버·가용 영역을 전달합니다. 반복 생성으로 해결하지 않습니다.',
					'BUILD 장기 유지 또는 ERROR: 생성 진행의 실패 단계, VM UUID, 표시되는 fault와 콘솔 로그를 기록합니다. Cinder 부트 볼륨 상태도 확인하고, 스케줄러·스토리지 문제는 관리자에게 요청합니다.',
					'SSH 시간 초과: 접속 대상 IP → 라우터 내부 인터페이스/외부 게이트웨이 → FIP의 실제 포트 매핑 → 그 포트에 적용된 SG의 22번 규칙 → 게스트 방화벽/sshd 순으로 확인합니다.',
					'SSH Permission denied: 경로는 도달했을 수 있습니다. 이미지 로그인 사용자·개인키·선택한 키페어 또는 GitHub 공개키 등록을 확인합니다. SG 전체 개방으로 인증 실패를 해결하려 하지 않습니다.',
					'ACTIVE인데 서비스 불통: cloud-init 실패, 설치 미완료, 잘못된 서비스 bind 주소, 게스트 방화벽을 확인합니다. 메트릭이 비어 있는 것만으로 VM 정지나 정상 상태를 판정하지 않습니다.',
				],
			},
			{
				id: 'cleanup',
				title: '7. 데이터 보존 후 정리',
				steps: [
					{ title: '삭제 범위 확인', text: ['필요한 데이터를 별도 백업하고 애플리케이션을 종료합니다. 삭제 확인창의 자동 삭제 볼륨과 유지(분리만) 볼륨 목록을 UUID까지 대조합니다. 라이브러리 VM의 Upper 볼륨과 dynamic 파일 스토리지 삭제 안내를 특히 확인합니다.'] },
					{ title: '인스턴스 삭제 후 잔여 자원 확인', text: ['자신이 정리할 인스턴스만 삭제하고 목록에서 사라지는지 확인합니다. 관련 FIP·볼륨·공유의 정리는 일부 실패할 수 있으므로 각각의 화면에서 남은 자원을 확인합니다. 보존 볼륨이나 다른 VM과 공유하는 네트워크·보안 그룹을 함께 삭제하지 않습니다.'] },
				],
			},
		],
		related: ['neutron', 'cinder', 'manila'],
		consoleLinks: [
			{ label: '인스턴스', href: '/dashboard/compute/instances' },
			{ label: '이미지', href: '/dashboard/compute/images' },
			{ label: '보안 그룹', href: '/dashboard/network/security-groups' },
		],
		externalLinks: [
			{ label: 'Afterglow 인스턴스 API 근거', href: 'https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/docs/api/instances.md' },
			{ label: 'Nova 사용자 문서', href: 'https://docs.openstack.org/nova/latest/user/' },
		],
	},
	{
		slug: 'neutron',
		name: 'Neutron',
		title: 'Neutron 네트워크·라우터·Floating IP·보안 그룹 연결',
		summary: '내부 주소 배정, 외부로 나가는 경로, 외부 주소 매핑, 트래픽 허용을 각각 구성하고 연결 실패 지점을 구분합니다.',
		category: 'openstack',
		keywords: ['Neutron', '네트워크', '서브넷', '라우터', 'Floating IP', 'FIP', '보안 그룹', 'SG', 'DHCP'],
		prerequisites: [
			'대상 프로젝트의 쓰기 권한과 네트워크·서브넷·라우터·포트·FIP·보안 그룹/규칙 쿼터를 확인합니다.',
			'다른 연결망과 겹치지 않는 승인된 사설 CIDR, 게이트웨이 계획, 접근 원본 대역을 준비합니다.',
			'외부 연결이 필요하면 사용 가능한 외부 네트워크를 관리자에게 확인합니다. 공유/외부 네트워크를 볼 수 있다는 것이 변경 권한을 뜻하지 않습니다.',
		],
		sections: [
			{
				id: 'concepts', title: '1. 주소·경로·허용 정책 구분',
				bullets: [
					'네트워크는 포트가 연결되는 가상 L2망입니다. 서브넷은 CIDR·게이트웨이·DHCP 등 IP 배정 조건을 정의하고, VM 포트에는 Fixed IP가 할당됩니다.',
					'라우터의 내부 인터페이스는 테넌트 서브넷을 연결합니다. 외부 게이트웨이는 외부 네트워크로 향하는 경로와 환경에 따른 SNAT를 제공합니다. 서브넷의 게이트웨이 주소 입력만으로 라우터 연결이 생기지는 않습니다.',
					'Floating IP는 외부 주소를 내부 포트의 Fixed IP에 매핑합니다. 외부 게이트웨이가 있다고 외부에서 모든 VM으로 들어올 수 있는 것은 아니며, 내부 통신에는 FIP가 필요하지 않을 수 있습니다.',
					'보안 그룹은 포트에 적용되는 허용 규칙입니다. 여러 그룹의 허용은 합쳐지므로 좁은 SSH 규칙을 추가해도 다른 그룹의 전체 허용 규칙이 남아 있으면 접근이 제한되지 않습니다.',
				],
			},
			{
				id: 'create-network', title: '2. 네트워크와 서브넷 생성',
				steps: [
					{ title: '네트워크 생성', text: ['네트워크 화면에서 네트워크 생성으로 이름을 입력합니다. 서브넷 함께 생성을 선택하면 서브넷 이름·CIDR·게이트웨이·DHCP 활성화를 같이 지정할 수 있습니다. CIDR 예시 10.20.0.0/24는 현재 환경과 겹치지 않을 때만 사용합니다.'], links: [{ label: '네트워크', href: '/dashboard/network/networks' }] },
					{ title: '서브넷 확인 또는 추가', text: ['생성된 네트워크 상세에서 서브넷의 CIDR·게이트웨이·DHCP를 확인합니다. 서브넷 없이 생성했다면 + 서브넷 추가에서 값을 지정합니다. 게이트웨이를 비우면 Neutron이 선택하므로 생성 결과를 반드시 읽습니다.', '일반적인 DHCP 사용 VM은 DHCP 활성화를 유지합니다. 비활성화했다면 게스트의 정적 IP 설정을 별도로 준비해야 합니다. 라우터 연결을 함께 선택한 경우에도 실제 인터페이스가 생겼는지 확인합니다.'] },
				],
			},
			{
				id: 'router', title: '3. 라우터 내부 인터페이스와 외부 게이트웨이',
				steps: [
					{ title: '라우터 생성 또는 기존 라우터 선택', text: ['라우터 화면에서 이름을 지정해 생성하거나 현재 프로젝트 소유 라우터를 엽니다. 외부 접속이 필요하면 외부 네트워크를 게이트웨이로 설정합니다. 일반 내부 네트워크를 외부 게이트웨이 대상으로 선택하지 않습니다.'], links: [{ label: '라우터', href: '/dashboard/network/routers' }] },
					{ title: '서브넷 내부 인터페이스 추가', text: ['라우터 상세의 인터페이스 영역에서 자신의 네트워크와 대상 서브넷을 선택해 추가합니다. 목록에 서브넷 UUID와 인터페이스 IP가 표시되는지 확인합니다. 게스트의 기본 게이트웨이가 실제 라우터 인터페이스 IP와 맞는지도 확인합니다.'] },
					{ title: '경로 대조', text: ['네트워크 상세의 연결 라우터와 라우터 상세의 외부 게이트웨이를 양쪽에서 확인합니다. 내부 인터페이스만 있으면 외부망 연결이 완성된 것이 아니고, 외부 게이트웨이만 있으면 대상 서브넷이 연결된 것이 아닙니다.'] },
				],
			},
			{
				id: 'security-groups', title: '4. 최소 권한 보안 그룹을 포트에 적용',
				steps: [
					{ title: '그룹과 규칙 생성', text: ['보안 그룹 화면에서 이름·설명을 지정해 그룹을 만듭니다. SSH는 수신/ingress, TCP, 시작·끝 포트 22, IPv4, CIDR 대상으로 승인된 접속 IP/32를 지정합니다. IPv6는 IPv6 규칙으로 따로 제한합니다.', '애플리케이션 포트도 실제 호출자 대역으로 제한합니다. 그룹 대상을 선택하면 같은 프로젝트의 원격 보안 그룹을 지정하며 CIDR과 동시에 지정하지 않습니다.'], links: [{ label: '보안 그룹', href: '/dashboard/network/security-groups' }] },
					{ title: '적용 대상과 합집합 확인', text: ['VM 생성 때 그룹을 선택하거나 인스턴스 상세의 인터페이스 → 보안 그룹 → 편집에서 실제 접속 포트에 적용하고 저장합니다. 보안 그룹 화면의 사용 인스턴스와 인스턴스 상세의 적용 그룹·허용 규칙 합집합을 확인합니다. 규칙 생성만으로 VM에 자동 적용된다고 보지 않습니다.'] },
					{ title: '기존 규칙 변경 시 영향 확인', text: ['규칙 편집은 기존 값을 복사하고 명시적으로 제거한 뒤 새 규칙을 만드는 흐름입니다. 두 요청 사이에 정책 공백이나 일시적인 차이가 생길 수 있으므로 접속 유지와 변경 순서를 계획합니다.'] },
				],
				callout: { tone: 'warning', title: '빈 CIDR은 안전한 기본값이 아닙니다', text: '대상을 비우면 IPv4는 0.0.0.0/0, IPv6는 ::/0이 됩니다. SSH를 전체 공개하지 말고, 이미 적용된 다른 그룹에도 전체 허용 규칙이 없는지 확인하세요.' },
			},
			{
				id: 'floating-ip', title: '5. Floating IP 할당·연결·확인',
				steps: [
					{ title: '필요 여부부터 판단', text: ['접속자가 VPN/내부망에서 Fixed IP로 접근할 수 있으면 FIP 없이 확인합니다. 외부에서 직접 들어와야 한다면 먼저 라우터 경로와 SG를 준비합니다. Afterglow VM 생성에서 이미 할당된 FIP가 있는지 확인합니다.'] },
					{ title: '할당과 연결을 구분', text: ['네트워크 화면의 Floating IP 할당은 외부 네트워크에서 주소를 확보하는 작업입니다. 별도 Floating IP 화면은 목록·상태·연결된 Fixed IP·해제를 제공합니다.', '인스턴스 상세에서는 대상 인터페이스의 + FIP로 포트에 주소를 할당·연결할 수 있습니다. 확보한 기존 FIP를 VM에 연결하는 API는 POST /api/v1/networks/floating-ips/{fip_id}/associate이며 요청은 {"instance_id":"대상 VM UUID"}입니다. 임의 포트 연결용 API로 사용하지 않습니다.'] },
					{ title: '실제 접속 확인', text: ['Floating IP 목록의 연결된 Fixed IP와 인스턴스를 대조하고, 인스턴스 상세에서 해당 포트의 주소와 보안 그룹을 확인합니다. 승인된 원본에서 허용 포트로 접속합니다. ping은 ICMP 허용 여부에 따라 실패하므로 ping 실패만으로 TCP 서비스 장애를 확정하지 않습니다.'] },
				],
			},
			{
				id: 'troubleshooting', title: '6. 통신 장애 진단 순서',
				bullets: [
					'Fixed IP가 없거나 DHCP 실패: 선택 네트워크·서브넷, DHCP 활성 여부, 주소 풀 여유, 포트 상태와 게스트 NIC 설정을 확인합니다.',
					'내부는 되고 외부만 실패: 서브넷의 라우터 인터페이스, 외부 게이트웨이, FIP의 올바른 Fixed IP 매핑, 외부망 도달성을 확인합니다. FIP를 추가하는 것으로 잘못된 라우팅이 고쳐지지는 않습니다.',
					'특정 포트만 실패: 실제 포트에 적용된 SG의 방향·IP 버전·프로토콜·포트·원본 CIDR을 확인한 뒤 게스트 방화벽과 서비스 listen 주소를 확인합니다.',
					'그룹/규칙 추가 버튼 비활성: 쿼터 초과와 쿼터 조회 오류를 구분합니다. 조회 오류를 남은 쿼터 0 또는 정상 상태로 판단하지 않습니다.',
					'공유 네트워크가 보이지만 변경 시 404: 소유 프로젝트와 변경 권한을 확인합니다. 타 프로젝트 자원을 복제하거나 삭제하는 우회 시도를 하지 않습니다.',
					'목록과 상세가 잠시 다름: 수동 새로고침으로 현재 연결을 확인합니다. 변경 직후 캐시나 비동기 상태를 근거로 같은 자원을 반복 생성하지 않습니다.',
				],
			},
			{
				id: 'cleanup', title: '7. 연결 의존성의 역순으로 정리',
				steps: [
					{ title: '외부 접근과 VM 포트 정리', text: ['서비스 사용자를 먼저 이동시키고 불필요한 FIP를 해제합니다. Floating IP 화면의 해제와 인스턴스 상세의 FIP 해제는 주소 삭제/반납을 포함하므로 주소를 보존하는 단순 연결 해제로 생각하지 않습니다. VM이나 인터페이스 제거도 서비스 영향 확인 후 수행합니다.'] },
					{ title: '라우터·서브넷·네트워크 정리', text: ['해당 망을 사용하는 VM·로드밸런서·공유 서버 등 포트의 사용자가 없는지 확인합니다. 라우터 내부 인터페이스와 불필요한 외부 게이트웨이를 제거한 뒤 라우터를 삭제합니다. 네트워크 상세에서 사용하지 않는 서브넷을 삭제하고 네트워크를 삭제합니다.'] },
					{ title: '보안 그룹과 잔여 자원 확인', text: ['사용 중인 포트에서 그룹을 제거하고 다른 규칙의 원격 그룹 참조도 확인한 뒤 자신의 불필요한 그룹을 삭제합니다. default 그룹은 삭제 대상이 아닙니다. In-use/의존성 오류가 나면 소유 포트를 확인하고 서비스 관리 포트를 임의 강제 삭제하지 않습니다.'] },
				],
			},
		],
		related: ['nova', 'octavia', 'manila'],
		consoleLinks: [
			{ label: '네트워크', href: '/dashboard/network/networks' },
			{ label: '라우터', href: '/dashboard/network/routers' },
			{ label: 'Floating IP', href: '/dashboard/network/floating-ips' },
			{ label: '보안 그룹', href: '/dashboard/network/security-groups' },
		],
		externalLinks: [
			{ label: 'Afterglow 네트워크 API 근거', href: 'https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/docs/api/networks.md' },
			{ label: 'Afterglow 라우터 API 근거', href: 'https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/docs/api/routers.md' },
			{ label: 'Afterglow 보안 그룹 API 근거', href: 'https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/docs/api/security-groups.md' },
			{ label: 'Neutron 사용자 문서', href: 'https://docs.openstack.org/neutron/latest/admin/' },
		],
	},
	{
		slug: 'octavia',
		name: 'Octavia',
		title: 'Octavia VIP에서 멤버·헬스 모니터까지 구성',
		summary: '로드밸런서·리스너·풀·멤버를 실제 전달 경로로 연결하고, 헬스 체크와 외부 공개 조건을 별도로 확인합니다.',
		category: 'openstack',
		keywords: ['Octavia', '로드밸런서', 'VIP', '리스너', '풀', '멤버', '헬스 모니터', 'ACTIVE', 'ONLINE'],
		prerequisites: [
			'프로젝트에서 Octavia와 필요한 쿼터를 사용할 수 있어야 합니다.',
			'VIP용 내부 네트워크/서브넷, 백엔드 VM의 Fixed IP와 실제 서비스 포트, 로드밸런서에서 멤버로 도달하는 경로를 준비합니다.',
			'백엔드 서비스가 먼저 정상 응답하고 SG/게스트 방화벽이 데이터 트래픽과 헬스 체크를 허용해야 합니다.',
			'현재 UI에 없는 풀-리스너 연결·헬스 모니터 작업에는 인증된 Afterglow API 호출 수단이 필요합니다. 외부 VIP 공개를 CLI로 수행한다면 Keystone 프로젝트 인증과 OpenStack CLI가 별도로 필요합니다.',
		],
		sections: [
			{
				id: 'concepts', title: '1. 요청이 지나가는 다섯 구성 요소',
				bullets: [
					'VIP는 클라이언트가 접속하는 로드밸런서 주소입니다. 내부 서브넷의 VIP는 그 자체로 인터넷 공개 주소가 아닙니다.',
					'리스너는 VIP에서 받아들이는 프로토콜·포트입니다. 풀은 전달할 백엔드 묶음과 분산 알고리즘이며 리스너의 기본 풀로 연결되어야 합니다.',
					'멤버는 백엔드의 IP와 실제 서비스 포트입니다. HTTP 리스너 80을 백엔드 8080으로 전달할 수도 있으므로 두 포트가 같다고 가정하지 않습니다.',
					'헬스 모니터는 풀 멤버에 주기적으로 확인 요청을 보냅니다. 멤버 등록과 모니터 생성은 별도 작업입니다.',
					'provisioning_status의 ACTIVE는 구성 적용 상태, operating_status의 ONLINE은 운영 상태입니다. ACTIVE ≠ ONLINE이며 둘 다 정상이어도 실제 클라이언트 요청을 확인해야 합니다.',
				],
			},
			{
				id: 'create-lb', title: '2. VIP 서브넷으로 로드밸런서 생성',
				steps: [
					{ title: '생성 화면 입력', text: ['로드밸런서 생성 화면에서 이름, 내부 네트워크, VIP 서브넷과 선택적 설명을 입력하고 생성합니다. 현재 생성 UI의 네트워크 목록은 외부 네트워크를 제외합니다. 외부 provider VIP 직접 생성 기능이 UI에 있다고 가정하지 않습니다.'], links: [{ label: '로드밸런서 생성', href: '/dashboard/network/loadbalancers/new' }] },
					{ title: 'VIP와 상태 확인', text: ['목록/상세에서 UUID·VIP 주소·프로비저닝 상태·운영 상태를 확인합니다. PENDING_CREATE/PENDING_UPDATE 중에는 다음 변경을 연달아 제출하지 말고 ACTIVE까지 기다립니다. 생성만으로 전달할 리스너와 풀, 멤버가 준비되지는 않습니다.'] },
				],
			},
			{
				id: 'listener-pool', title: '3. 리스너와 기본 풀을 실제로 연결',
				steps: [
					{ title: 'HTTP 리스너 생성', text: ['상세의 리스너 추가에서 이름, HTTP, 포트 80을 지정해 생성하고 리스너 UUID를 기록합니다. TLS 인증서·TLS 종료 설정 UI가 제공된다고 가정하지 않습니다. 이 절차는 평문 HTTP 예시입니다.'] },
					{ title: '리스너에 연결된 풀 생성', text: ['현재 상세 UI의 풀 추가는 프로토콜·알고리즘·이름만 전송하고 listener_id를 전송하지 않습니다. UI에서 리스너와 풀을 각각 만들었다고 전달 경로가 자동 연결되지는 않습니다.', '인증된 API로 POST /api/v1/loadbalancers/{lb_id}/pools를 호출하고 아래 요청의 listener_id를 앞에서 기록한 UUID로 교체합니다. API 주소의 lb_id도 자신의 로드밸런서 UUID로 바꿉니다. 이 예시는 아직 풀을 만들지 않은 리스너에 새 풀을 연결하는 작업이며 기존 풀에 대한 수정 API 예시가 아닙니다.'], command: { label: '리스너 연결을 포함하는 풀 생성 요청 본문', code: '{\n  "name": "web-pool",\n  "protocol": "HTTP",\n  "lb_algorithm": "ROUND_ROBIN",\n  "listener_id": "<LISTENER_UUID_FROM_PREVIOUS_STEP>"\n}' } },
					{ title: '기본 풀 연결 확인', text: ['GET /api/v1/loadbalancers/{lb_id}/listeners 응답에서 해당 리스너의 default_pool_id가 생성한 풀 UUID인지 확인합니다. 다른 방법으로 풀을 먼저 만들었다면 새 리스너 생성 API의 default_pool_id로 연결할 수 있지만, 기존 리스너가 연결되었다고 추정하지 않습니다.'] },
				],
			},
			{
				id: 'members-monitor', title: '4. 멤버와 헬스 모니터 구성',
				steps: [
					{ title: '풀 멤버 추가', text: ['상세에서 연결된 풀을 펼치고 멤버 추가에 백엔드 Fixed IP, 서비스 포트(예: 8080), 이름, 가중치(예: 1)를 지정합니다. VM의 FIP를 백엔드 주소로 무조건 사용하지 않습니다. 두 번째 멤버도 실제 응답과 경로를 먼저 확인한 뒤 추가합니다.', '다른 서브넷 멤버 등 명시적인 subnet_id가 필요한 구성은 멤버 생성 API로 지정합니다. 현재 멤버 UI는 subnet_id를 전송하지 않습니다. 공급자 드라이버가 지원하는 경로인지 운영자에게 확인합니다.'] },
					{ title: '모니터 생성', text: ['현재 상세 UI에는 헬스 모니터 생성 폼이 없습니다. 인증된 API로 POST /api/v1/loadbalancers/{lb_id}/pools/{pool_id}/health-monitor를 호출합니다. 아래 HTTP 예시는 검사 간격 5초, 타임아웃 3초, 재시도 3회입니다.', '현재 Afterglow 모니터 요청은 type·delay·timeout·max_retries·name만 지원합니다. URL 경로·기대 응답 코드·HTTP 메서드 편집 기능을 advertise하지 않습니다. HTTP 기본 검사와 백엔드 응답이 맞는지 확인하고, 단순 TCP 연결 검사가 필요하면 지원되는 TCP 타입을 사용합니다.'], command: { label: 'HTTP 헬스 모니터 생성 요청 본문', code: '{\n  "name": "web-health",\n  "type": "HTTP",\n  "delay": 5,\n  "timeout": 3,\n  "max_retries": 3\n}' } },
					{ title: '모니터 적용 확인', text: ['GET /api/v1/loadbalancers/{lb_id}/pools/{pool_id}/health-monitor에서 생성한 모니터와 설정을 확인합니다. 멤버/풀 목록의 status는 프로비저닝 상태이므로 ACTIVE를 멤버 건강 상태로 해석하지 않습니다. 필요한 운영 상태는 Octavia 상태 트리와 실제 응답으로 확인합니다.'] },
				],
			},
			{
				id: 'vip-fip', title: '5. 내부 VIP와 외부 FIP 공개 구분',
				paragraphs: ['우선 VIP에 도달 가능한 내부 클라이언트에서 리스너 포트로 요청하고 백엔드의 정상 응답을 확인합니다. 외부 공개가 필요할 때만 VIP 서브넷의 라우터 내부 인터페이스와 외부 게이트웨이를 준비하고 VIP 포트에 FIP를 연결합니다.'],
				steps: [
					{ title: 'VIP 포트에 외부 주소 연결', text: ['GET /api/v1/loadbalancers/{lb_id}의 vip_port_id를 확인합니다. 현재 Afterglow 로드밸런서 UI에는 VIP FIP 연결 액션이 없고, 일반 FIP associate API는 instance_id를 받습니다. 이를 VIP 포트용으로 사용하지 않습니다.', '승인된 운영 절차에서 직접 Neutron CLI를 사용한다면 아래 명령으로 새 FIP를 VIP 포트에 연결할 수 있습니다. 변수에는 실제 VIP 포트 UUID와 라우터 게이트웨이의 외부 네트워크 UUID를 지정해야 합니다. Keystone 인증된 CLI를 사용하는 사용자용 예시이며 이 문서를 작성하며 실행하지 않았습니다. 기존 FIP를 재사용할 경우 새로 생성하지 말고 별도 연결 절차를 따릅니다.'], command: { label: '승인 후 수행하는 VIP 포트 FIP 생성·연결 예시', code: 'openstack floating ip create --port "${VIP_PORT_ID:?Set the VIP port UUID}" "${EXTERNAL_NETWORK_ID:?Set the external network UUID}"' } },
					{ title: '외부 요청 확인', text: ['FIP가 매핑한 Fixed IP가 VIP인지 확인하고 외부 클라이언트에서 FIP:리스너 포트로 요청합니다. VIP 측 허용 정책과 백엔드 SG/게스트 방화벽은 구분해서 점검합니다. SSH를 개방하는 것으로 HTTP 리스너나 헬스 체크 문제를 해결하지 않습니다.'] },
				],
			},
			{
				id: 'verify', title: '6. 동작 확인은 상태와 실제 요청으로',
				bullets: [
					'로드밸런서 provisioning_status가 ACTIVE인지, operating_status가 ONLINE 또는 문제 상태인지 각각 읽습니다.',
					'리스너의 default_pool_id, 풀의 health_monitor_id, 각 멤버의 IP·포트·가중치를 API/상세에서 대조합니다.',
					'VIP 또는 FIP로 여러 번 요청하고 백엔드 로그에서 실제 전달을 확인합니다. 동일한 응답 본문만으로 모든 멤버에 전달됐다고 판정하지 않습니다.',
					'연결 재사용·알고리즘·가중치 때문에 요청 수가 정확히 균등하지 않을 수 있습니다. 멤버 장애 전환 시험은 승인된 테스트 환경에서만 수행합니다.',
				],
			},
			{
				id: 'troubleshooting', title: '7. ACTIVE인데 응답이 없는 경우',
				bullets: [
					'VIP 연결 자체 실패: VIP 서브넷 도달성, 라우터 경로, 올바른 FIP→VIP 매핑과 리스너 포트를 확인합니다.',
					'VIP까지 도달하지만 전달 실패: 리스너 default_pool_id 누락, 빈 풀, 잘못된 멤버 주소/포트, 가중치, 백엔드 서비스와 SG를 점검합니다. UI에서 별도 생성한 풀의 연결 누락을 먼저 확인합니다.',
					'모니터가 멤버를 비정상으로 판정: 모니터 타입·타임아웃과 백엔드 기본 HTTP 응답, 헬스 체크 출발 경로의 허용을 확인합니다. HTTP 검사가 실패했다고 단순 TCP 검사도 실패한다고 단정하지 않습니다.',
					'프로비저닝 ERROR: 상세의 오류 상태 트리가 있으면 실패한 리스너·풀·멤버 위치를 기록합니다. GET /api/v1/loadbalancers/{lb_id}/status로도 조회할 수 있지만 빈 하위 트리만으로 모든 멤버가 정상이라고 보지 않습니다.',
					'PENDING 상태에서 변경 거부: 앞선 변경이 완료될 때까지 기다립니다. 오래 지속되면 LB UUID·상태·작업 시각을 운영자에게 전달하고 반복 생성/강제 삭제하지 않습니다.',
				],
			},
			{
				id: 'cleanup', title: '8. 공개 주소와 하위 자원 정리',
				steps: [
					{ title: '서비스 전환 후 삭제 범위 확인', text: ['외부 사용자를 다른 엔드포인트로 전환하고 이 LB의 FIP를 확인해 연결 해제/반납을 결정합니다. Drover 등 다른 서비스가 관리하는 LB는 그 서비스의 수명주기 절차를 따르고 일반 수동 실습 대상으로 사용하지 않습니다.'] },
					{ title: '필요한 범위만 제거', text: ['멤버만 제외하려면 풀에서 해당 멤버를 제거합니다. 모니터만 제거하려면 DELETE /api/v1/loadbalancers/{lb_id}/pools/{pool_id}/health-monitor/{hm_id}를 사용합니다. 전체 폐기 시 LB 삭제는 하위 자원을 cascade 삭제하므로 별도의 부분 삭제를 무조건 반복할 필요는 없습니다.'] },
					{ title: '남은 FIP와 백엔드 확인', text: ['로드밸런서 목록에서 삭제 완료를 확인하고 FIP 목록에 불필요한 주소가 남았는지 확인합니다. LB 삭제가 백엔드 VM이나 그 데이터까지 삭제하는 것은 아닙니다. 다른 사용자가 쓰는 서브넷·라우터·보안 그룹은 보존합니다.'] },
				],
			},
		],
		related: ['neutron', 'nova'],
		consoleLinks: [
			{ label: '로드밸런서', href: '/dashboard/network/loadbalancers' },
			{ label: '로드밸런서 생성', href: '/dashboard/network/loadbalancers/new' },
			{ label: 'Floating IP', href: '/dashboard/network/floating-ips' },
		],
		externalLinks: [
			{ label: 'Afterglow 로드밸런서 API 근거', href: 'https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/docs/api/loadbalancers.md' },
			{ label: 'Octavia 사용자 문서', href: 'https://docs.openstack.org/octavia/latest/user/' },
		],
	},
	{
		slug: 'cinder',
		name: 'Cinder',
		title: 'Cinder 볼륨 연결·확장·백업과 안전한 분리',
		summary: '블록 디스크 연결과 게스트 파일시스템 작업을 구분하고, 스냅샷·백업의 차이와 복원 확인 절차를 이해합니다.',
		category: 'openstack',
		keywords: ['Cinder', '볼륨', '블록 스토리지', 'attach', 'detach', '파일시스템', '백업', '스냅샷', '확장'],
		prerequisites: [
			'대상 프로젝트의 쓰기 권한, 볼륨 수·용량 쿼터, 연결할 VM과 스토리지/AZ 호환성을 확인합니다.',
			'게스트 OS 관리 권한과 디스크 식별·마운트 절차를 준비합니다. 기존 데이터 디스크는 포맷하지 않습니다.',
			'백업에는 Cinder backup 서비스와 저장소의 정상 동작이 필요합니다. 메뉴 노출만으로 실제 백업·복원 가능성을 판단하지 않습니다.',
		],
		sections: [
			{
				id: 'concepts', title: '1. 블록 볼륨과 게스트 파일시스템',
				paragraphs: ['Cinder 볼륨은 VM에 디스크 장치로 연결하는 블록 스토리지입니다. Manila처럼 export 경로를 여러 클라이언트에 마운트하는 공유 파일시스템과 다릅니다.'],
				bullets: [
					'available은 연결되지 않은 상태, in-use는 연결 상태입니다. creating/attaching/detaching 같은 전이 중에는 완료를 기다립니다.',
					'볼륨 연결은 디스크를 게스트에 제시하는 작업입니다. 파티션·파일시스템·마운트·부팅 시 자동 마운트는 게스트에서 별도로 구성합니다.',
					'bootable 볼륨은 부팅 소스로 재사용할 수 있습니다. 데이터 볼륨과 부트/OverlayFS Upper 볼륨을 UUID와 사용 용도로 구분합니다.',
					'일반 볼륨을 여러 VM에 임의로 동시에 연결하지 않습니다. 현재 화면이 공유 파일시스템이나 안전한 multi-attach를 제공한다고 가정하지 않습니다.',
				],
			},
			{
				id: 'create', title: '2. 빈 볼륨 생성과 상태 확인',
				steps: [
					{ title: '이름과 크기 입력', text: ['볼륨 목록에서 볼륨 생성으로 이름과 크기(GB)를 입력합니다. 현재 일반 생성 UI는 이름·크기를 받으므로 임의 볼륨 타입·암호화·AZ 선택 기능을 전제하지 않습니다. API 크기 범위는 1–16384GB이며 실제 생성은 쿼터와 백엔드 조건에 제한됩니다.'], links: [{ label: '볼륨 목록', href: '/dashboard/volumes' }] },
					{ title: '생성 완료 확인', text: ['목록을 새로고침해 available까지 기다리고 이름·UUID·크기·타입·연결 정보가 예상대로인지 확인합니다. 요청 성공만으로 바로 사용할 수 있다고 판단하지 않습니다.'] },
				],
			},
			{
				id: 'attach-filesystem', title: '3. VM 연결 후 게스트에서 확인',
				steps: [
					{ title: '인스턴스에 연결', text: ['available 볼륨 상세의 인스턴스에 연결에서 대상 VM을 선택합니다. 목록의 연결 메뉴는 먼저 상세를 여는 동작입니다. 연결 후 볼륨의 in-use 상태와 대상 VM UUID, 인스턴스 상세의 연결 볼륨을 대조합니다.'] },
					{ title: '디스크 식별', text: ['게스트에서 아래 읽기 전용 명령으로 새 장치의 크기·파일시스템·마운트 지점을 확인합니다. API의 /dev/vdb 같은 device 값과 실제 게스트 이름이 항상 동일하다고 가정하지 않습니다. UUID·크기와 연결 전후 목록을 비교합니다.'], command: { label: '게스트 디스크와 파일시스템 조회', code: 'lsblk -o NAME,SIZE,TYPE,FSTYPE,UUID,MOUNTPOINTS\nfindmnt' } },
					{ title: '파일시스템과 마운트 구성', text: ['기존 파일시스템이 있으면 내용과 용도를 확인한 뒤 올바른 경로에 마운트합니다. 정말 빈 새 디스크임을 확인한 경우에만 OS별 파티션/파일시스템 생성 절차를 수행합니다. 이 가이드는 장치 오선택으로 데이터를 지우는 포맷 명령을 일괄 제공하지 않습니다.', '부팅 시 자동 마운트에는 안정적인 파일시스템 UUID를 사용하고 게스트의 설정을 검토합니다. 화면의 연결 완료가 게스트의 마운트나 애플리케이션 사용 완료를 뜻하지 않습니다.'] },
				],
			},
			{
				id: 'extend', title: '4. 용량 확장과 파일시스템 확장을 분리',
				steps: [
					{ title: 'Cinder 용량 확장 요청', text: ['볼륨 작업 메뉴의 용량 확장에서 현재보다 큰 새 용량을 입력합니다. 축소는 지원하지 않습니다. UI는 available/in-use 볼륨에 확장을 제공하지만 연결 중 확장의 실제 지원은 Cinder 백엔드와 게스트 환경에 따라 확인해야 합니다.'] },
					{ title: '게스트 용량 확인과 확장', text: ['목록/상세의 새 크기를 확인한 뒤 게스트에서 장치 크기를 다시 조회합니다. 필요하면 게스트 장치 재인식 절차를 수행하고, 사용 중인 파티션·LVM·ext4/XFS 등 실제 구조에 맞춰 순서대로 확장합니다.', 'Cinder 크기가 늘어도 df의 파일시스템 크기가 자동으로 늘었다고 가정하지 않습니다. 파일시스템 확장 후 실제 마운트 경로의 용량과 애플리케이션 동작을 확인합니다.'] },
				],
			},
			{
				id: 'backup-snapshot', title: '5. 스냅샷과 백업의 용도·일관성',
				paragraphs: ['볼륨 스냅샷은 현재 구성에서 원본과 같은 Ceph 풀에 있는 시점 복제본입니다. 빠른 시점 보존 수단이지 그 풀의 장애와 삭제 위험을 피하는 독립 백업이 아닙니다. Cinder 백업은 backup 서비스의 저장소로 데이터를 복사하지만, 실제 저장소·복구 가능성·장애 도메인은 운영 설정과 복원 시험으로 확인해야 합니다.'],
				steps: [
					{ title: '일관성 확보 후 백업', text: ['DB/애플리케이션의 쓰기를 중지하거나 승인된 일관성 확보 절차를 수행합니다. 볼륨 메뉴의 백업 생성 또는 볼륨 백업 화면에서 원본 볼륨·백업 이름·설명·증분 여부를 지정합니다. 첫 기준 백업에는 증분을 선택하지 않습니다.', 'in-use 볼륨에 백업 메뉴가 보여도 현재 API 요청에는 연결 중 백업을 강제하는 force 필드가 없습니다. 필요하면 안전하게 분리해 available로 만든 뒤 백업하고, 연결 상태에서 하위 서비스가 거부한 요청을 성공으로 해석하지 않습니다.'], links: [{ label: '볼륨 백업', href: '/dashboard/volumes/backups' }] },
					{ title: '스냅샷 생성', text: ['볼륨 스냅샷 베타 기능을 활성화한 경우 스냅샷 생성에서 이름·설명을 지정하고 원본 UUID를 확인합니다. in-use 강제 스냅샷(force)은 쓰기 중 데이터의 애플리케이션 일관성을 보장하지 않습니다. 생성 후 available인지 확인합니다.'], links: [{ label: '볼륨 스냅샷', href: '/dashboard/volumes/snapshots' }] },
				],
				callout: { tone: 'warning', title: '블록 복사만으로 DB 백업이 완성되지 않습니다', text: '게스트 메모리·진행 중 트랜잭션·여러 볼륨의 동시 일관성은 자동 보장되지 않습니다. 원본에 쓰기가 남아 있으면 crash-consistent 수준일 수 있으므로 서비스별 복구 절차도 준비하세요.' },
			},
			{
				id: 'restore', title: '6. 백업을 새 볼륨으로 복원하고 데이터 확인',
				steps: [
					{ title: '백업 available 확인 후 복원', text: ['볼륨 백업 화면에서 원본 볼륨 UUID·백업 시점·크기를 확인하고 available인 백업의 복원을 선택합니다. 현재 UI 복원은 새 볼륨을 만드는 흐름입니다. API는 기존 volume_id를 지정하면 덮어쓸 수 있으므로 테스트 복원에 기존 운영 볼륨 ID를 넣지 않습니다.'] },
					{ title: '복원 볼륨의 실제 상태 확인', text: ['복원 결과의 volume_id를 기록하고 볼륨 목록에서 새 볼륨이 available이 될 때까지 확인합니다. 복원 응답/화면 완료 문구만으로 데이터 복구를 확정하지 않습니다.'] },
					{ title: '데이터 또는 부팅 검증', text: ['데이터 볼륨은 검증 VM에 연결해 파일시스템·필요한 파일·애플리케이션 복구를 확인합니다. bootable 부트 볼륨이면 볼륨 메뉴의 이 볼륨으로 VM 부팅 또는 인스턴스 마법사의 기존 부팅 볼륨으로 선택합니다.', 'OverlayFS Upper 복원은 일반 부트 볼륨 복원과 다릅니다. 원본과 같은 라이브러리 구성이 있어야 파일 가시성이 재현될 수 있으며, 데이터 볼륨을 Upper나 OS 부트로 무조건 사용하지 않습니다.'] },
				],
			},
			{
				id: 'detach-cleanup', title: '7. 쓰기 중지·unmount 후 분리·삭제',
				steps: [
					{ title: '게스트부터 안전하게 해제', text: ['해당 디스크를 사용하는 서비스를 중지하고 쓰기를 완료시킨 뒤 게스트에서 파일시스템을 unmount합니다. LVM·암호화 매핑 등이 있으면 OS 절차에 따라 정리하고 자동 마운트 설정도 수정합니다. 부트 디스크나 실행 중 Upper 디스크를 일반 데이터 디스크처럼 분리하지 않습니다.'] },
					{ title: '인스턴스 상세에서 분리', text: ['인스턴스 상세의 볼륨 분리를 수행하고 인스턴스 연결 목록에서 사라지는지, Cinder에서 attachments가 비고 available이 되는지 확인합니다. detach는 게스트 unmount를 대신하지 않습니다.'] },
					{ title: '보존 결정 후 삭제', text: ['필요한 백업·스냅샷의 보존 정책을 확인하고 불필요한 종속 자원만 정리합니다. 분리된 볼륨을 삭제한 뒤 목록에서 사라지는지 확인합니다. VM 삭제 시 자동 삭제 옵션도 별도로 확인하며 보존 디스크를 VM 삭제와 함께 없애지 않습니다.'] },
				],
			},
			{
				id: 'troubleshooting', title: '8. 연결·확장·복구 장애 진단',
				bullets: [
					'연결 실패: available 여부, 기존 attachment, 대상 VM 상태, 프로젝트·AZ·백엔드 연결 제약과 쿼터를 확인합니다.',
					'in-use인데 게스트에 없음: 연결 VM UUID를 대조하고 장치 인식·드라이버·게스트 로그를 확인합니다. 이름 확인 실패는 UUID로 대조하고 임의 포맷하지 않습니다.',
					'Cinder 크기는 늘었지만 df는 그대로: 게스트 장치 재인식, 파티션/LVM, 파일시스템 확장, 확인한 마운트 경로를 순서대로 점검합니다.',
					'백업 creating/restoring 장기 유지 또는 error: 원본/복원 볼륨 상태, backup 서비스·저장소, 공간·쿼터, 증분 기준 백업을 운영자와 확인합니다. 메뉴가 있다는 이유로 백업이 실행 가능한 환경이라고 단정하지 않습니다.',
					'detach/삭제 실패: 게스트 사용 상태, Cinder attachment, 스냅샷·백업 의존성을 확인합니다. error_deleting 등은 관리자 진단에 UUID·상태·작업 시각을 전달하고 사용자가 강제 상태 재설정이나 강제 삭제로 우회하지 않습니다.',
				],
			},
		],
		related: ['nova', 'manila'],
		consoleLinks: [
			{ label: '볼륨 목록', href: '/dashboard/volumes' },
			{ label: '볼륨 백업', href: '/dashboard/volumes/backups' },
			{ label: '볼륨 스냅샷', href: '/dashboard/volumes/snapshots', description: '볼륨 스냅샷 베타 기능 활성화 시 사용' },
		],
		externalLinks: [
			{ label: 'Afterglow 볼륨 API 근거', href: 'https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/docs/api/volumes.md' },
			{ label: 'Cinder 사용자 문서', href: 'https://docs.openstack.org/cinder/latest/user/' },
		],
	},
	{
		slug: 'manila',
		name: 'Manila',
		title: 'Manila NFS·CephFS 공유 생성과 접근·마운트',
		summary: '프로토콜·Share Type·접근 규칙·Export Location을 구분하고, 공유를 안전하게 사용·정리하며 스냅샷의 복구 한계를 확인합니다.',
		category: 'openstack',
		keywords: ['Manila', '파일 스토리지', 'share', 'NFS', 'CephFS', 'CephX', 'access', 'export', 'DHSS', '스냅샷', '백업'],
		prerequisites: [
			'환경에서 Manila 서비스가 활성화되고 대상 프로젝트에 생성·접근 규칙 변경 권한과 shares/gigabytes 쿼터가 있어야 합니다.',
			'지원되는 Share Type과 프로토콜, 클라이언트에서 스토리지 export/monitor로 도달하는 네트워크를 확인합니다.',
			'NFS 클라이언트 도구 또는 CephFS 클라이언트와 게스트 관리 권한을 준비합니다. export를 볼 수 있다는 것이 마운트 권한이나 네트워크 도달성을 뜻하지 않습니다.',
			'NFS는 현재 생성 API가 tenant share network를 요구합니다. Share 네트워크 베타 노출과 선택 가능한 네트워크를 확인합니다.',
		],
		sections: [
			{
				id: 'concepts', title: '1. 프로토콜·타입·네트워크·export의 역할',
				bullets: [
					'Share는 여러 클라이언트가 파일 단위로 사용하는 공유입니다. Cinder 블록 디스크와 연결·인증 방식이 다릅니다.',
					'NFS는 export 서버/경로와 클라이언트 IP/CIDR 접근 규칙을 사용합니다. native CephFS(CEPHFS)는 Ceph monitor/공유 경로와 CephX ID·키를 사용하며 NFS로 마운트하지 않습니다.',
					'Share Type은 백엔드와 지원 프로토콜·DHSS(driver_handles_share_servers: 드라이버가 공유 서버를 관리하는지) 조건을 정합니다. 프로토콜 이름만 보고 임의 타입을 선택하지 않습니다.',
					'CEPHFS native에는 share network를 전달하지 않습니다. NFS에서는 현재 Afterglow API가 share network 존재를 확인하고, 서비스가 선택 타입의 DHSS를 확인해 True일 때만 Manila 생성 요청에 포함합니다. False이면 하위 요청에서 제외합니다.',
					'Export Location은 실제 마운트 대상이며 share UUID 자체가 아닙니다. preferred export가 있으면 클라이언트 도달성과 함께 우선 검토합니다.',
				],
			},
			{
				id: 'create', title: '2. 파일 스토리지 생성과 결과 확인',
				steps: [
					{ title: '기본 정보 선택', text: ['파일 스토리지 화면의 생성 마법사에서 이름·크기(GB)·Share Type·프로토콜(CephFS 또는 NFS)을 지정합니다. 타입이 한 프로토콜만 지원하면 해당 프로토콜만 선택됩니다. 메타데이터는 필요한 경우에만 추가하며 소유권 추적용 값을 임의 조작하지 않습니다.'], links: [{ label: '파일 스토리지', href: '/dashboard/file-storage' }] },
					{ title: 'NFS 네트워크 조건 확인', text: ['DHSS=True이며 Share 네트워크 기능이 활성화되어 네트워크 단계가 표시되면, 준비된 Share Network를 선택하거나 Neutron 네트워크·서브넷으로 새 Share Network를 생성합니다.', '현재 UI는 DHSS=False 또는 베타 비활성화 시 네트워크 단계를 숨길 수 있지만 현재 NFS 생성 API는 tenant share network를 요구합니다. 이 조합에서 선택을 보낼 수 없거나 422가 발생하면 생성이 가능하다고 가정하지 않습니다. 운영자에게 타입·UI 노출·API 조건 정합성을 확인하고, 승인된 API 경로에서는 유효한 share_network_id를 지정해야 합니다.'], links: [{ label: 'Share 네트워크', href: '/dashboard/file-storage/networks', description: '베타 기능 활성화 시 노출' }] },
					{ title: 'available과 export 확인', text: ['생성 요청 후 목록/상세에서 share UUID·프로토콜·크기·available 상태·Export Locations를 확인합니다. 생성 마법사의 접근 설정 단계에서 규칙을 추가하거나 나중에 상세에서 추가할 수 있습니다. 건너뛰기를 눌러도 이미 생성된 share가 삭제되는 것은 아닙니다.'] },
				],
			},
			{
				id: 'access', title: '3. NFS IP 규칙과 CephX 인증을 구분',
				steps: [
					{ title: 'NFS 접근 규칙', text: ['접근 설정/상세에서 IP / CIDR에 실제 서버가 보는 클라이언트 IP 또는 최소 승인 대역을 입력하고 읽기 전용(ro) 또는 읽기/쓰기(rw)를 선택합니다. 외부 FIP가 아니라 스토리지로 향하는 경로의 실제 원본 IP가 중요합니다. 전체 대역 개방으로 경로 문제를 해결하지 않습니다.'] },
					{ title: 'CephFS 접근 규칙', text: ['CephX ID에 사용할 클라이언트 ID를 입력하고 ro/rw를 선택합니다. 규칙 상태와 Access Key 발급을 확인하고 키를 복사합니다. 키 발급 대기/실패를 정상 마운트 가능 상태로 보지 않습니다.', 'Access Key는 비밀입니다. 로그·스크린샷·공유 문서·명령 이력에 노출하지 말고 게스트의 제한된 권한 파일로 전달합니다. NFS IP 규칙에 CephX 키를 기대하거나 CephX 규칙에 클라이언트 CIDR을 넣지 않습니다.'] },
					{ title: '요청 수락과 적용 상태 구분', text: ['추가 후 상세를 새로고침해 실제 규칙의 대상·ro/rw·상태를 확인합니다. 마법사의 초기 권한 선택이 rw일 수 있으므로 읽기만 필요한 경우 명시적으로 ro를 선택합니다.'], },
				],
				callout: { tone: 'warning', title: 'NFS 보안 옵션은 서버 적용을 확인해야 합니다', text: '현재 일반 접근 UI는 대상과 ro/rw를 전송하고 access_type을 프로토콜에서 결정합니다. 일반 생성 API 경로가 root_squash·Kerberos 옵션을 실제 적용한다고 가정하지 마세요. 서버의 root 매핑·UID/GID·인증 정책과 드라이버 적용을 운영자에게 확인해야 합니다.' },
			},
			{
				id: 'mount', title: '4. 클라이언트 연결과 마운트',
				steps: [
					{ title: 'Export Location과 도달성 준비', text: ['상세의 Export Locations에서 전체 경로를 복사합니다. 클라이언트의 네트워크 경로와 방화벽을 확인합니다. NFS 서버와 Ceph monitor/data 경로는 다르므로 한쪽 접속 성공으로 다른 프로토콜도 가능하다고 보지 않습니다.'] },
					{ title: 'NFS 마운트', text: ['게스트에 NFS 클라이언트를 설치하고 사용하지 않는 마운트 디렉터리를 준비합니다. 서버가 지원하는 NFS 버전과 export를 운영 정책에 맞게 사용합니다. 아래는 승인된 게스트에서 읽기 전용으로 연결하는 예시입니다. NFS_EXPORT에는 화면의 실제 export 전체 경로, SHARE_MOUNT에는 준비한 절대 디렉터리를 지정합니다.', 'rw가 필요하면 share 접근 규칙과 클라이언트 마운트 옵션 양쪽을 확인합니다. NFS 버전·sec 옵션이 서버 정책과 맞지 않으면 마운트나 읽기/쓰기가 거부될 수 있습니다.'], command: { label: '승인된 클라이언트에서 NFS 읽기 전용 마운트', code: 'sudo mount -t nfs -o ro "${NFS_EXPORT:?Set the actual NFS export}" "${SHARE_MOUNT:?Set the prepared mount directory}"' } },
					{ title: 'CephFS 마운트', text: ['native CephFS는 NFS 명령을 사용하지 않습니다. Export Location의 monitor 주소와 공유 경로, CephX ID·키, 환경의 Ceph 파일시스템 설정을 사용해 설치된 kernel/FUSE 클라이언트의 승인된 마운트 절차를 수행합니다. 키는 제한된 권한의 secret 파일/키링으로 전달합니다.', 'Afterglow VM 생성의 데이터 스토리지 연결을 사용하는 경우 기존 share와 마운트 경로, 읽기 전용 여부를 지정할 수 있습니다. 관리형 초기화도 게스트에서 실제 마운트와 접근을 확인해야 하며, NFS 데이터 마운트에는 VM 네트워크 선택이 필요합니다.'] },
				],
			},
			{
				id: 'verify', title: '5. 마운트·권한·공유 동작 확인',
				steps: [
					{ title: '실제 파일시스템과 옵션 확인', text: ['게스트에서 마운트 디렉터리의 실제 소스·파일시스템·ro/rw 옵션과 용량을 조회합니다. 빈 로컬 디렉터리에 접근한 것을 공유 마운트 성공으로 착각하지 않습니다.'], command: { label: '게스트 마운트 결과 조회', code: 'findmnt --target "${SHARE_MOUNT:?Set the mount directory to inspect}"\ndf -hT "${SHARE_MOUNT:?Set the mount directory to inspect}"' } },
					{ title: '사용자 권한과 공유 확인', text: ['애플리케이션이 사용하는 실제 UID/GID로 필요한 파일을 읽을 수 있는지 확인합니다. rw 사용이면 승인된 시험 파일로 생성·읽기·삭제를 확인하고 시험 파일은 정리합니다. 운영 데이터를 시험 파일로 덮어쓰지 않습니다.', '여러 클라이언트가 필요하면 각각 자신의 접근 규칙과 마운트 상태를 확인한 뒤 같은 시험 파일이 보이는지 확인합니다. ro 클라이언트의 쓰기 거부는 의도한 권한일 수 있습니다.'] },
				],
			},
			{
				id: 'snapshot-backup', title: '6. 공유 스냅샷은 독립 백업이 아닙니다',
				paragraphs: ['Afterglow는 현재 Manila share backup 생성·복원 기능을 지원하지 않습니다. Cinder 볼륨 백업을 만들었다고 Manila 공유 파일도 백업되는 것은 아닙니다.'],
				steps: [
					{ title: '지원되는 공유의 스냅샷 생성', text: ['파일 스토리지 스냅샷 베타 기능이 활성화되고 Share Type/백엔드가 스냅샷을 지원하는 경우 스냅샷 화면에서 대상 share·이름·설명을 선택해 생성합니다. share UUID와 생성 시점을 기록하고 available 상태를 확인합니다. 현재 화면에서 범용 스냅샷 복원이나 독립 백업 기능을 제공한다고 가정하지 않습니다.'], links: [{ label: '파일 스토리지 스냅샷', href: '/dashboard/file-storage/snapshots', description: '베타 기능 및 백엔드 지원 필요' }] },
					{ title: '별도 백업과 복구 절차 준비', text: ['스냅샷은 같은 스토리지의 시점 보존이며 원본 스토리지 장애와 삭제 위험을 분리하는 독립 백업이 아닙니다. 애플리케이션 쓰기 일관성도 별도 확보해야 합니다.', '필요한 파일/DB를 승인된 외부 백업 체계로 복사하고 별도 저장소·보존 기간·복원 시험을 운영자와 정합니다. Manila 실험 API가 존재하더라도 저장소·데이터 노드·프로토콜 드라이버 지원과 실제 생성/복원을 검증하기 전에는 사용 가능하다고 보지 않습니다.'] },
				],
			},
			{
				id: 'troubleshooting', title: '7. 생성·인증·파일 접근 장애 진단',
				bullets: [
					'메뉴 미노출 또는 API 404: Manila 활성화와 현재 프로젝트/소유권을 확인합니다. 스냅샷·Share 네트워크는 별도 베타 노출 조건도 확인합니다.',
					'NFS 생성 422: 유효한 tenant share_network_id 요구를 확인합니다. UI가 네트워크 단계를 숨겼다고 API에서도 선택이 불필요하다고 추정하지 않습니다.',
					'creating 장기 유지/error 또는 capabilities filter 실패: Share Type·프로토콜·DHSS·용량·네트워크 조건을 대조하고 UUID·오류·시각을 운영자에게 전달합니다. 잘못된 타입으로 반복 생성하지 않습니다.',
					'NFS access denied: 서버가 보는 실제 원본 IP와 접근 규칙, export 전체 경로, NFS 버전·인증 정책을 확인합니다. mount 시간 초과는 라우팅·방화벽·서버 응답부터 점검합니다.',
					'CephFS 인증 실패: CephX ID와 해당 공유에서 발급된 키, 규칙 적용 상태, monitor 주소·경로·클라이언트 지원을 확인합니다. 다른 share의 키로 재시도하지 않습니다.',
					'마운트됐지만 쓰기 실패: share ro/rw, 클라이언트 ro/rw, 파일 UID/GID·모드·ACL, NFS root 매핑, 공유 용량을 확인합니다. root로 실행하거나 전체 CIDR을 허용하는 것으로 모든 권한 문제를 해결하지 않습니다.',
				],
			},
			{
				id: 'cleanup', title: '8. 모든 클라이언트 해제 후 규칙·공유 정리',
				steps: [
					{ title: '사용자와 마운트 해제', text: ['모든 클라이언트와 애플리케이션의 사용을 파악하고 필요한 데이터를 별도 보존합니다. 쓰기를 중지·완료한 뒤 각 게스트에서 unmount하고 부팅 시 자동 마운트 설정을 제거합니다. VM 데이터 스토리지 연결도 사용하는 경우 그 연결 정보를 함께 정리합니다.'] },
					{ title: '접근 규칙 회수', text: ['더 이상 쓰지 않는 IP/CIDR 또는 CephX 규칙을 상세에서 삭제하고 새로고침해 회수를 확인합니다. 사용 중인 규칙 회수는 즉시 I/O 오류를 유발할 수 있습니다. 로컬에 보관한 불필요한 CephX 키도 안전하게 제거합니다.'] },
					{ title: '스냅샷 보존과 공유 삭제', text: ['필요한 스냅샷을 무조건 삭제하지 말고 보존 여부를 결정합니다. 종속성 때문에 공유 삭제가 거부되면 원인을 확인해 불필요한 스냅샷만 먼저 정리합니다. 자신의 미사용 공유를 삭제하고 목록에서 사라지는지 확인합니다. 삭제 장애는 관리자 진단으로 넘기며 강제 삭제로 우회하지 않습니다.', 'Share Network는 다른 공유가 사용하지 않는지 확인한 뒤 별도 정리합니다. 라이브러리/다른 VM이 쓰는 사전 빌드 공유와 public 공유를 개인 데이터 share처럼 삭제하지 않습니다.'] },
				],
			},
		],
		related: ['nova', 'neutron', 'cinder'],
		consoleLinks: [
			{ label: '파일 스토리지', href: '/dashboard/file-storage', service: 'manila' },
			{ label: '스냅샷', href: '/dashboard/file-storage/snapshots', service: 'manila', description: '파일 스토리지 스냅샷 베타 기능 활성화 시 사용' },
			{ label: 'Share 네트워크', href: '/dashboard/file-storage/networks', service: 'manila', description: 'Share 네트워크 베타 기능 활성화 시 사용' },
		],
		externalLinks: [
			{ label: 'Afterglow 파일 스토리지 API 문서', href: 'https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/docs/api/file-storage.md' },
			{ label: '현재 파일 스토리지 생성·접근 API 근거', href: 'https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/backend/app/api/storage/file_storage.py' },
			{ label: 'Manila 사용자 문서', href: 'https://docs.openstack.org/manila/latest/user/' },
		],
	},
];
