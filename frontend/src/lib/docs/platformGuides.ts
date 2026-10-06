import type { DocGuide } from './types';

export const platformGuides: DocGuide[] = [
	{
		slug: 'drover',
		name: 'Drover',
		title: 'Drover로 k3s 클러스터 만들고 운영하기',
		summary: 'OpenStack VM 기반 k3s 클러스터를 구성하고, 실제 준비 상태와 접속 경로를 확인한 뒤 노드와 클러스터를 정리합니다.',
		category: 'afterglow',
		keywords: ['Drover', 'k3s', 'Kubernetes', '클러스터', 'kubeconfig', '노드', 'Provider 네트워크', 'Stampede'],
		prerequisites: [
			'로그인한 계정으로 사용할 프로젝트를 선택하고 해당 프로젝트의 클러스터·OpenStack 리소스 권한을 확인합니다.',
			'운영자가 k3s 서비스를 활성화하고 서버 이미지·플레이버, 워커 기본 플레이버, 외부 Provider 네트워크 정책을 준비해야 합니다.',
			'Nova VM·vCPU·메모리, Cinder 부트 볼륨, Neutron 포트·보안 그룹 등 생성에 필요한 프로젝트 쿼터가 있어야 합니다.',
			'로컬 접속에는 kubectl과 Kubernetes API로 통하는 네트워크 경로가 필요합니다. SSH가 필요하면 키페어와 대응하는 개인 키를 미리 준비합니다.'
		],
		sections: [
			{
				id: 'scope',
				title: '1. 서비스와 프로젝트 범위 확인',
				paragraphs: [
					'Drover의 사용자 화면은 /dashboard/drover입니다. Magnum 클러스터와 별개로 Nova VM과 cloud-init 또는 Ignition을 이용해 k3s를 설치합니다. 생성·조회·삭제는 선택한 프로젝트 범위에서 수행합니다.',
					'메뉴 노출과 실제 서비스 준비는 다릅니다. k3s 기능이 꺼져 있으면 API가 마운트되지 않을 수 있고, 이미지·플레이버 정책이 없으면 생성이 503으로 거부됩니다. 사용자 화면에서 서비스 배포 설정을 바꾸지는 않습니다.'
				],
				bullets: [
					'사용자 작업: 프로젝트 클러스터 생성, 상태·헬스 조회, kubeconfig 다운로드, 워커 수 조정, 노드 네트워크 추가 연결, 클러스터 삭제.',
					'운영자 작업: 서비스 활성화·연결, 이미지와 기본 플레이버·외부 네트워크 정책, 클러스터 템플릿 관리, OpenStack 통합 플러그인과 worker 설정.',
					'CoreOS는 별도 FCOS 이미지 설정이 필요합니다. Stampede는 개발 단계 기능이며 전역 활성화와 노드그룹 min/max 구성이 필요하므로 기본 수동 운영과 구분합니다.'
				],
				links: [{ label: 'Drover 클러스터 화면', href: '/dashboard/drover' }]
			},
			{
				id: 'create',
				title: '2. 클러스터 구성과 생성',
				steps: [
					{
						title: '생성 화면에서 기본 구성을 입력합니다',
						text: [
							'Drover 클러스터 생성 모달을 엽니다. 템플릿이 있으면 선택한 뒤 복사된 OS·에이전트 수·플레이버를 다시 확인합니다. 이름은 비워 자동 생성하거나 영문·숫자로 시작하는 63자 이하의 영문·숫자·하이픈·언더스코어 조합으로 입력합니다.',
							'OS와 에이전트(worker) 수 0–10을 선택합니다. 에이전트 플레이버를 비우면 관리자 기본값을 사용합니다. 서버(control plane) 플레이버와 보안 그룹을 직접 고르는 생성 UI는 제공되지 않습니다.'
						]
					},
					{
						title: '초기 네트워크와 키페어를 선택합니다',
						text: [
							'외부 Provider 네트워크를 직접 선택하거나 관리자 외부 Provider 기본 네트워크 사용을 선택합니다. 기본값 선택은 요청에서 network_id를 생략합니다. 초기 노드는 이 Provider 네트워크에 직접 연결되며 내부 네트워크는 생성 후 추가 NIC로 연결합니다.',
							'SSH를 사용할 계획이면 키페어를 선택하고 개인 키는 로컬에 보관합니다. 서버·워커의 실제 IP와 접근 정책은 생성 후 별도로 확인합니다. 네트워크 선택만으로 인터넷이나 로컬 PC에서의 접근이 보장되지는 않습니다.'
						]
					},
					{
						title: '생성을 제출하고 목록에서 이어서 확인합니다',
						text: [
							'생성을 한 번 제출하고 진행 단계와 오류를 확인합니다. 창을 닫았거나 연결이 끊겼다면 먼저 목록을 새로고침하여 이미 접수된 클러스터가 있는지 확인한 뒤 다음 작업을 결정합니다.',
							'현재 사용자 생성 컨트롤러는 master_count를 보내지 않습니다. 모달의 3 (HA) 선택만으로 HA가 만들어진다고 판단하지 마세요. 이 화면의 생성 경로는 기본 단일 마스터이며, API의 HA 지원과 UI 요청 전달은 별개의 계약입니다.'
						]
					}
				],
				callout: {
					tone: 'warning',
					title: '생성 요청 완료는 운영 준비 완료가 아닙니다',
					text: '진행률 100% 또는 completed는 서버 VM과 클러스터 기록의 생성 요청 완료입니다. VM 설치 콜백과 후속 노드 프로비저닝이 끝나 ACTIVE로 바뀌는지 확인해야 합니다.'
				}
			},
			{
				id: 'status',
				title: '3. 상태와 실제 노드 준비 확인',
				paragraphs: [
					'목록에서 클러스터를 열고 상태, status_reason, 서버·에이전트 VM 정보를 확인합니다. CREATING은 초기 자원 생성, PROVISIONING은 후속 노드 구성, SCALING은 워커 증감 진행 중입니다. ERROR이면 사유를 먼저 기록합니다.',
					'ACTIVE에서 헬스 체크를 실행하고 노드 현황의 Ready/NotReady와 검사 시각을 확인합니다. ACTIVE는 프로비저닝 상태이고 HEALTHY·DEGRADED·UNREACHABLE 등은 Kubernetes API와 노드의 관측 상태입니다. 하나를 다른 하나의 보증으로 사용하지 않습니다.'
				],
				bullets: [
					'워커 VM 생성 수와 요청한 수를 비교하고 실제 노드 Ready를 확인합니다. VM이 존재한다는 사실만으로 k3s join 성공을 판정하지 않습니다.',
					'헬스가 미확인 또는 UNKNOWN이면 데이터 수집 여부와 검사 시각을 확인합니다. 반복 클릭 대신 자동 새로고침 또는 수동 갱신으로 후속 상태를 기다립니다.',
					'워크로드·Pod·Service 화면을 사용할 때는 대상 namespace를 먼저 선택합니다. 클러스터 준비와 애플리케이션 준비도 서로 다릅니다.'
				]
			},
			{
				id: 'connect',
				title: '4. kubeconfig로 접속하기',
				steps: [
					{
						title: 'ACTIVE 클러스터의 kubeconfig를 받습니다',
						text: [
							'상세의 kubeconfig 다운로드로 kubeconfig-클러스터이름.yaml 파일을 받습니다. 아직 설치 콜백이 도착하지 않았으면 파일이 없으며 다운로드가 404로 끝날 수 있습니다.',
							'kubeconfig에는 인증 정보가 포함됩니다. 저장소·메신저·공개 지원 티켓에 올리지 말고 개인 전용 파일로 보관합니다. 아래 예시는 이름을 guide-cluster로 생성하고 다운로드 파일을 현재 디렉터리에 둔 경우입니다.'
						],
						command: {
							label: '다운로드한 kubeconfig로 읽기 전용 확인',
							code: 'chmod 600 ./kubeconfig-guide-cluster.yaml\nkubectl --kubeconfig ./kubeconfig-guide-cluster.yaml get nodes\nkubectl --kubeconfig ./kubeconfig-guide-cluster.yaml get pods -A'
						}
					},
					{
						title: '접속 주소와 네트워크 경로를 확인합니다',
						text: [
							'파일의 server 주소와 상세의 API 주소를 확인합니다. 사설 주소는 해당 네트워크로의 경로가 필요합니다. 공인/Floating IP가 있더라도 라우팅과 6443 접근 정책을 함께 확인해야 하며 모든 클러스터에 Floating IP가 자동 제공되는 것은 아닙니다.',
							'연결이 시간 초과되면 인증서를 수정하거나 TLS 검증을 끄지 말고 주소·VPN/라우팅·보안 그룹을 확인합니다. SSH 접속은 별도의 키페어와 노드 OS의 사용자 계정, 22번 포트 접근이 필요하며 kubeconfig 다운로드가 SSH 로그인 권한을 대신하지 않습니다.'
						]
					}
				]
			},
			{
				id: 'nodes',
				title: '5. 워커와 노드 네트워크 운영',
				steps: [
					{
						title: 'ACTIVE에서 워커 수를 조정합니다',
						text: [
							'노드 현황의 에이전트 −/+로 목표 수 0–10을 정하고 적용합니다. 접수 응답 뒤 실제 VM 증감은 백그라운드에서 진행되므로 SCALING이 끝나 ACTIVE로 돌아오는지와 Ready 노드 수를 함께 확인합니다.',
							'축소 전에는 워크로드 재배치 가능 여부와 데이터 백업을 확인합니다. 워커 수 감소는 애플리케이션 데이터 이전이나 백업을 보장하지 않습니다. Nova 화면에서 클러스터 VM만 따로 삭제하는 대신 Drover의 노드 운영 경로를 사용합니다.'
						]
					},
					{
						title: '필요한 내부 네트워크를 추가 연결합니다',
						text: [
							'상세의 노드 네트워크에서 대상 server 또는 agent를 선택하고 + 네트워크 연결로 네트워크를 고른 뒤 추가합니다. 결과의 포트·네트워크 ID·IP를 확인합니다.',
							'불필요한 추가 인터페이스는 해당 행의 제거로 해제합니다. 기본 인터페이스는 제거할 수 없습니다. NIC 추가는 게스트 라우팅이나 보안 그룹 정책까지 자동으로 원하는 애플리케이션 연결을 완성한다는 뜻이 아닙니다.'
						]
					}
				],
				bullets: [
					'노드그룹은 상세의 노드그룹 영역에서 추가·편집합니다. Stampede를 사용한다면 먼저 그룹의 min/max를 설정하고 운영자의 전역 설정·worker 준비를 확인합니다.',
					'OpenStack CSI·클라우드 컨트롤러·Ingress·KMS 통합은 운영자가 활성화한 플러그인에 의존합니다. 기본 클러스터 생성만으로 모든 스토리지·로드밸런서 기능을 약속하지 않습니다.'
				]
			},
			{
				id: 'cleanup',
				title: '6. 워크로드와 클러스터 정리',
				steps: [
					{
						title: '보존할 데이터와 외부 자원을 확인합니다',
						text: [
							'애플리케이션 데이터와 필요한 Kubernetes 설정을 백업하고 Service·Ingress·PVC 등 연결 자원의 보존/회수 정책을 확인합니다. 클러스터 삭제는 데이터 백업 작업이 아닙니다.',
							'Drover가 관리하는 VM·보안 그룹·API LB 등을 개별 서비스 화면에서 강제 삭제하지 않습니다. 자동 관리 자원을 먼저 지우면 클러스터와 후속 정리가 손상될 수 있습니다.'
						]
					},
					{
						title: 'Drover에서 삭제한 뒤 완료를 확인합니다',
						text: [
							'클러스터 삭제를 누르고 이름을 확인해 승인합니다. 삭제 진행 단계와 오류를 확인하고 목록을 갱신합니다. 삭제 이력 표시를 켜면 soft-delete된 기록을 확인할 수 있습니다.',
							'실패한 단계가 있으면 클러스터 ID와 사유로 운영자에게 잔여 VM·포트·볼륨·LB 확인을 요청합니다. 삭제 기록만 보고 별도로 만든 모든 자원이 정리됐다고 판단하지 않습니다. 사용이 끝난 로컬 kubeconfig와 SSH 접속 자료도 안전하게 정리합니다.'
						]
					}
				]
			},
			{
				id: 'troubleshooting',
				title: '7. 막혔을 때 확인할 순서',
				bullets: [
					'메뉴가 없거나 404: k3s 서비스 활성화와 메뉴의 컨테이너 기능 설정을 운영자에게 확인합니다. 특정 클러스터만 404라면 선택한 프로젝트와 클러스터 ID부터 확인합니다.',
					'생성 503 또는 선택지 없음: 이미지·서버/에이전트 플레이버·Provider 네트워크 정책과 프로젝트 쿼터를 확인합니다. CoreOS에서만 실패하면 FCOS 이미지 설정을 확인합니다.',
					'진행률 완료 뒤 계속 초기화 중: 목록과 상세를 갱신하고 VM 설치·콜백·후속 에이전트 구성 단계를 구분합니다. 운영자에게 클러스터 ID와 status_reason을 전달하며 join token이나 kubeconfig를 전달하지 않습니다.',
					'스케일 409: ACTIVE가 아닌 상태에서는 적용할 수 없습니다. 기존 작업 상태를 확인한 뒤 완료 후 목표 수를 다시 선택합니다.',
					'kubeconfig 404: 초기화 완료를 먼저 확인합니다. 파일은 받았지만 UNREACHABLE/timeout이면 API 주소의 도달 경로와 보안 정책을 확인합니다.',
					'NotReady 또는 Pod 대기: 노드 상태와 Pod 이벤트·로그, 리소스 용량을 확인합니다. 클러스터 삭제/재생성으로 증상을 덮기 전에 실패 원인을 분리합니다.'
				]
			}
		],
		related: ['waygate', 'palimpsest'],
		consoleLinks: [{ label: 'Drover', href: '/dashboard/drover', service: 'k3s' }]
	},
	{
		slug: 'waygate',
		name: 'Waygate',
		title: 'Waygate로 프로젝트 네트워크에 안전하게 접속하기',
		summary: 'WireGuard 게이트웨이와 네트워크 연결, 기기별 클라이언트를 구성하고 실제 handshake와 대상 접근을 확인한 뒤 권한을 회수합니다.',
		category: 'afterglow',
		keywords: ['Waygate', 'VPN', 'WireGuard', 'gateway', '클라이언트', 'QR', 'handshake', 'AllowedIPs', 'SNAT'],
		prerequisites: [
			'로그인 후 VPN을 만들 프로젝트를 선택하고 프로젝트 자원에 대한 권한을 확인합니다.',
			'운영자가 Waygate API·worker, DB/cache, Provider 네트워크·이미지·플레이버 정책과 VM에서 도달 가능한 콜백 origin을 준비해야 합니다.',
			'접속할 테넌트 네트워크와 IPv4 서브넷, 실제 접근을 확인할 대상 IP·서비스 포트를 준비합니다.',
			'접속 기기에 WireGuard 앱을 설치하고 로컬 LAN·다른 VPN·터널·대상 서브넷의 CIDR이 겹치는지 확인합니다.'
		],
		sections: [
			{
				id: 'scope',
				title: '1. 프로젝트와 서비스 경계',
				paragraphs: [
					'사용자 화면은 네트워크 → Waygate(/dashboard/network/waygate)입니다. Waygate는 선택한 프로젝트에 게이트웨이 VM을 만들고 WireGuard peer와 테넌트 네트워크 연결을 관리합니다.',
					'관리자 화면 /admin/waygate도 같은 프로젝트별 관리 기능을 사용합니다. 관리자 화면이라는 이유로 모든 프로젝트의 게이트웨이나 클라이언트를 한꺼번에 조회하는 화면은 아닙니다. 다른 프로젝트 자원은 404로 보일 수 있습니다.'
				],
				bullets: [
					'사용자 작업: 게이트웨이 생성·삭제, 서버 DNS/Keepalive 기본값, 네트워크 연결·해제, 클라이언트 발급·설정·비활성화·삭제, .conf/QR과 암호화 백업.',
					'운영자 작업: 서비스 활성화·주소 연결, Provider 이미지·플레이버·네트워크 정책, DB migration·worker·에이전트 배포와 공인 UDP 도달성 확보.',
					'현재 네트워크 연결 모드는 SNAT입니다. 일반 사용자가 임의의 NAT 모드나 게이트웨이 이미지·플레이버를 선택하는 UI는 아닙니다.'
				],
				links: [{ label: 'Waygate 화면', href: '/dashboard/network/waygate' }]
			},
			{
				id: 'gateway',
				title: '2. 게이트웨이 생성과 준비 확인',
				steps: [
					{
						title: 'Waygate 서버를 생성합니다',
						text: [
							'+ Waygate 서버 생성에서 이름과 기본 DNS·PersistentKeepalive를 지정하고 생성합니다. 이름을 비우면 자동 생성됩니다. DNS는 최대 두 값을 쉼표로 구분하며 비우면 설정 파일에서 DNS 행을 생략합니다. Keepalive는 0–65535초이고 0은 비활성화입니다.',
							'생성 응답은 작업 접수입니다. 목록을 갱신하며 CREATING → PROVISIONING → ACTIVE 전이를 확인합니다. ERROR이면 상세 사유를 확인하고 중복 게이트웨이를 만들기 전에 기존 작업을 확인합니다.'
						]
					},
					{
						title: 'ACTIVE와 엔드포인트 정보를 확인합니다',
						text: [
							'서버 상세에서 상태, 엔드포인트 IP:포트, 터널 CIDR, 서버 공개키와 마지막 상태 보고를 확인합니다. 클라이언트 발급과 네트워크 연결은 ACTIVE에서 진행합니다.',
							'ACTIVE는 에이전트의 공개키 등록을 포함한 서버 준비 상태입니다. 내 기기의 VPN 연결이나 내부 VM에 대한 실제 접근 성공을 뜻하지는 않습니다.'
						]
					}
				]
			},
			{
				id: 'networks',
				title: '3. 테넌트 네트워크와 서브넷 연결',
				steps: [
					{
						title: '대상 네트워크와 IPv4 서브넷을 명시합니다',
						text: [
							'서버 상세의 + 네트워크 연결에서 프로젝트가 볼 수 있는 non-external 테넌트 네트워크를 고릅니다. 서브넷이 여러 개면 접속하려는 IPv4 서브넷을 선택합니다. 하나면 자동 선택되며 서브넷이 없으면 연결할 수 없습니다.',
							'연결 목록에서 네트워크 UUID, 선택한 서브넷의 CIDR과 상태를 확인합니다. 네트워크 이름 확인 불가 표시는 이름 조회 실패일 수 있으므로 UUID를 기준으로 대상을 대조합니다.'
						]
					},
					{
						title: '경로 겹침을 확인하고 기기 설정을 갱신합니다',
						text: [
							'대상 CIDR이 로컬 LAN이나 다른 VPN의 AllowedIPs와 겹치면 동일 주소의 트래픽이 다른 인터페이스로 갈 수 있습니다. 연결 전에 CIDR을 대조하고 충돌하는 다른 터널을 끄거나 운영자와 주소 계획을 조정합니다. UI가 모든 경로 겹침을 자동 해결해 주지는 않습니다.',
							'활성 연결의 CIDR은 새로 받는 .conf의 AllowedIPs에 반영됩니다. 네트워크를 추가·해제한 뒤 기존 기기의 파일은 자동 갱신되지 않으므로 .conf를 다시 받거나 QR을 다시 가져옵니다.'
						]
					}
				],
				callout: {
					tone: 'info',
					title: '네트워크 연결과 VPN handshake는 별개입니다',
					text: '네트워크 연결은 게이트웨이 VM에 테넌트 NIC와 SNAT 경로를 구성하는 작업입니다. 클라이언트가 WireGuard handshake를 했다는 뜻도, 대상 VM의 보안 그룹이 필요한 포트를 허용한다는 뜻도 아닙니다.'
				}
			},
			{
				id: 'clients',
				title: '4. 기기별 클라이언트 발급과 설정',
				steps: [
					{
						title: '기기마다 별도 클라이언트를 발급합니다',
						text: [
							'+ 클라이언트 발급에서 식별 가능한 이름을 입력합니다. DNS·Keepalive는 서버 기본값 사용 또는 직접 지정을 선택하고, MTU는 576–9000 또는 빈 값(자동)을 사용합니다.',
							'발급된 클라이언트의 터널 IP, 활성 상태와 설정을 확인합니다. 서비스가 기기용 키쌍과 전용 PSK를 생성하므로 같은 설정 파일을 여러 사람이나 기기에 공유하지 않습니다.'
						]
					},
					{
						title: '.conf 또는 QR을 WireGuard 앱으로 가져옵니다',
						text: [
							'클라이언트 행의 다운로드로 .conf를 받아 앱의 파일 가져오기를 사용하거나, QR 버튼을 열고 모바일 앱의 QR 코드로 추가로 스캔합니다. QR은 다운로드와 같은 설정 텍스트로 브라우저에서 생성합니다.',
							'앱에서 터널을 활성화합니다. 이후 클라이언트 설정 또는 서버 기본값을 변경했다면 해당 기기에 새 설정을 다시 가져옵니다. 상속은 새 다운로드에 반영되는 설정 규칙이지 설치된 앱을 원격 갱신하는 기능이 아닙니다.'
						]
					}
				],
				callout: {
					tone: 'warning',
					title: '.conf와 QR은 비밀 자격 증명입니다',
					text: '개인 키와 PSK가 포함됩니다. QR 캡처·화면 공유·온라인 QR 변환기·공개 저장소·지원 티켓에 노출하지 마세요. 유출됐다면 화면을 닫는 것으로 끝내지 말고 해당 클라이언트를 삭제하고 새로 발급합니다.'
				}
			},
			{
				id: 'verify',
				title: '5. handshake와 실제 내부 접근 확인',
				steps: [
					{
						title: '최신 보고와 handshake를 함께 봅니다',
						text: [
							'기기에서 터널을 켠 후 내부 대상에 트래픽을 보내고 서버 상세의 클라이언트 상태를 갱신합니다. 마지막 핸드셰이크, 보고 경과 시간, RX/TX 변화를 확인합니다.',
							'ONLINE은 최근 120초 이내 handshake와 최신 에이전트 보고가 관측됐다는 뜻입니다. 알 수 없음은 보고가 없거나 상태 미확인이고, 보고 지연은 오래된 관측입니다. OFFLINE만으로 기기의 모든 통신 상태를 단정하지 않습니다.'
						]
					},
					{
						title: '실제 대상의 허용된 서비스를 확인합니다',
						text: [
							'연결한 서브넷의 대상 사설 IP로 SSH나 허용된 HTTP 서비스 등 실제 사용할 포트에 접속합니다. ICMP가 허용된 환경에서는 ping도 사용할 수 있지만 ping 실패만으로 VPN 실패를 판정하지 않습니다.',
							'handshake는 되는데 대상에 접근할 수 없다면 attachment 상태, 최신 AllowedIPs, 로컬 라우팅과 대상 보안 그룹·서비스 실행 상태를 확인합니다. UI의 RX/TX는 클라이언트 관점이며 보고 공백이나 카운터 reset 때 속도 공백이 생길 수 있습니다.'
						]
					}
				]
			},
			{
				id: 'backup',
				title: '6. 설정 백업과 게이트웨이 이동',
				paragraphs: [
					'서버 상세의 설정 내보내기에서 8자 이상 패스프레이즈로 암호화된 JSON 번들을 받습니다. 번들에도 민감한 클라이언트 정보가 있으므로 파일과 패스프레이즈를 분리해 안전하게 보관합니다.',
					'준비된 대상 서버의 설정 가져오기로 번들과 같은 패스프레이즈를 제출합니다. 가져온/건너뛴 클라이언트 수를 확인합니다. 네트워크 attachment는 재생성하지 않으므로 필요한 네트워크를 대상 서버에 직접 다시 연결합니다.'
				],
				bullets: [
					'서버 private key는 번들에 포함되지 않으며 대상 서버 키는 새로 유지됩니다. 이전 .conf를 그대로 사용하지 말고 대상 서버에서 설정을 다시 받습니다.',
					'내보낼 때 상속 중이던 DNS·Keepalive는 출발 서버의 계산된 명시 값으로 보존됩니다. 대상 서버 기본값을 상속할지 클라이언트 설정에서 다시 확인합니다.',
					'이동 완료는 import 응답이 아니라 새 endpoint에서의 handshake와 실제 내부 서비스 접근으로 확인합니다.'
				]
			},
			{
				id: 'cleanup',
				title: '7. 클라이언트 권한 회수와 자원 정리',
				steps: [
					{
						title: '기기 접근을 비활성화하거나 삭제합니다',
						text: [
							'일시 중지는 클라이언트의 비활성화, 영구 회수(revoke)는 삭제를 사용합니다. 비활성화는 다시 활성화할 수 있지만 유출된 설정을 재사용하는 방식으로 사고를 해결하지 않습니다.',
							'목록 상태/행 제거를 확인하고 에이전트의 다음 desired-state 반영 뒤 실제 접근이 중단되는지 확인합니다. 단말 앱에서도 터널과 내려받은 .conf·QR 사본을 정리합니다. 브라우저 작업 성공은 에이전트 적용 시점과 다를 수 있습니다.'
						]
					},
					{
						title: '불필요한 연결과 게이트웨이를 정리합니다',
						text: [
							'네트워크 연결 해제 시 이름과 UUID를 확인합니다. 남아 있는 기기에는 새 .conf를 적용하여 제거된 경로가 계속 남지 않게 합니다.',
							'서버 삭제를 승인한 뒤 DELETING과 후속 목록 갱신으로 삭제 완료를 확인합니다. 서버 삭제 접수는 VM·Floating IP·포트 정리 완료가 아닙니다. ERROR attachment나 삭제 실패가 남으면 사유와 ID로 운영자에게 잔여 자원 확인을 요청합니다.'
						]
					}
				]
			},
			{
				id: 'troubleshooting',
				title: '8. 연결 문제와 배포 제약 진단',
				bullets: [
					'생성 503 또는 기능 미설정: Waygate 연결과 DB/cache·worker, Provider 리소스 정책을 운영자가 확인해야 합니다. 사용자가 정책 없는 생성을 우회할 수는 없습니다.',
					'PROVISIONING에서 멈춤: 공개키 등록과 VM에서 Waygate 공개 콜백 origin으로의 도달성을 운영자에게 확인합니다. localhost/내부 컨테이너 주소를 VM 콜백 주소로 사용하지 않습니다.',
					'handshake 없음: 기기 터널 활성화, 최신 endpoint·서버 공개키, UDP 경로·방화벽, 클라이언트 활성 상태를 확인합니다. 서버 ACTIVE만으로 단말 접속 성공을 판정하지 않습니다.',
					'handshake는 정상인데 내부 서비스 실패: 선택 서브넷과 attachment, 최신 AllowedIPs, 겹치는 LAN/VPN 경로, 대상 VM 보안 그룹·서비스 포트를 순서대로 확인합니다.',
					'DNS만 실패하거나 큰 전송만 멈춤: IP 직접 접속과 이름 해석을 분리하고 DNS·MTU·Keepalive 설정을 점검한 뒤 기기에 설정을 다시 가져옵니다.',
					'설정 변경 422 또는 예전 배포의 상속 문제: 입력 범위와 서버/API migration 버전 호환을 확인합니다. 구형 에이전트의 보고 간격도 다를 수 있으며 화면 갱신만으로 에이전트가 업그레이드되지는 않습니다.',
					'다른 프로젝트의 서버가 안 보임: 현재 프로젝트를 다시 확인합니다. 지원 요청에는 서버/클라이언트 ID와 안전한 오류·보고 시각을 전달하고 .conf·QR·private key·PSK는 제외합니다.'
				]
			}
		],
		related: ['drover'],
		consoleLinks: [{ label: 'Waygate', href: '/dashboard/network/waygate', service: 'waygate' }]
	},
	{
		slug: 'lumen',
		name: 'Lumen',
		title: 'Lumen 채팅·Studio·API 연결 사용하기',
		summary: '프로젝트와 모델 기능·크레딧 한도를 확인하고 채팅, 이미지·오디오 Studio, 일반 API 키 기반 CLI 연결을 사용합니다.',
		category: 'afterglow',
		keywords: ['Lumen', 'AI', '채팅', '모델', 'capability', 'quota', '크레딧', 'Studio', 'API 키', 'Codex', 'Claude Code'],
		prerequisites: [
			'로그인하고 사용할 OpenStack 프로젝트를 선택합니다. 대화·asset·실행 결과의 프로젝트 범위를 확인합니다.',
			'운영자가 chat 서비스와 Lumen 연결, API·worker, provider credential, 활성 모델과 가격을 준비해야 합니다.',
			'선택한 기능을 지원하는 모델과 사용자 월·주간 크레딧 여유가 필요합니다. Studio는 asset storage/scanner 등 추가 준비가 필요합니다.',
			'외부 CLI는 먼저 별도로 설치합니다. API 연결에는 일반 Lumen API 키 전체 값과 해당 프로토콜을 지원하는 활성 공개 모델 ID가 필요합니다.'
		],
		sections: [
			{
				id: 'scope',
				title: '1. 프로젝트와 Lumen 서비스 범위',
				paragraphs: [
					'텍스트 채팅은 /dashboard/chat, 이미지 Studio는 /dashboard/chat/images, 오디오 Studio는 /dashboard/chat/audio입니다. Afterglow는 로그인과 브라우저 요청을 중계하는 BFF이며 모델 실행·API 키 검증·과금·asset 관리는 별도 Lumen 서비스가 담당합니다.',
					'메뉴가 보여도 provider 키, 활성 모델, 기능별 정확한 가격, worker·asset 저장소·검사기의 준비나 실제 생성 성공이 보장되지는 않습니다. 사용자가 provider의 비밀 키를 직접 브라우저 설정에 넣는 흐름은 아닙니다.'
				],
				bullets: [
					'먼저 상단 프로젝트를 선택합니다. 채팅의 프로젝트(workspace)는 대화를 묶는 폴더 성격의 작업 공간이며 OpenStack 프로젝트 선택·권한·쿼터를 대신하지 않습니다.',
					'일반 사용자: 활성 모델 선택, 대화·Studio 사용, 본인 사용량 확인, 본인 일반 API 키 발급·한도 설정·폐기.',
					'관리자 전용: /admin/chat의 provider credential·서비스 설정, /admin/chat/models의 모델·가격·활성 상태, /admin/chat/quotas의 사용자 쿼터 정책. 사용자 개인 API 키 한도 설정과 구분합니다.'
				],
				links: [{ label: 'Lumen 채팅', href: '/dashboard/chat' }]
			},
			{
				id: 'models-quota',
				title: '2. 모델 capability와 크레딧 한도 확인',
				steps: [
					{
						title: '모델 이름 대신 실제 기능을 확인합니다',
						text: [
							'모델 선택창에서 활성 모델과 공개 API ID, 기능 배지를 확인합니다. 이미지 입력·검색·추론 강도 등은 모델 capability에 따라 제공됩니다. 모델 이름이 비슷하다는 이유로 다른 프로토콜이나 기능까지 지원한다고 가정하지 않습니다.',
							'Search는 지원과 실행 gate·가격이 준비된 native 검색만 선택합니다. 추론 강도 없음도 지원이 명시된 모델에서만 표시됩니다. 에이전트가 선택되어 있으면 에이전트가 모델을 관리하므로 일반 모델 선택이 잠길 수 있습니다.'
						]
					},
					{
						title: '사용량과 쿼터를 확인합니다',
						text: [
							'설정 → 사용량(/dashboard/chat/settings?section=usage)에서 본인 크레딧·월/주간 한도와 웹/API 사용량을 확인합니다. API 키로 쓴 비용도 본인 지갑의 사용자 쿼터에서 차감됩니다.',
							'사용자 쿼터 상향은 관리자 작업입니다. API 키의 개인 한도를 비운다고 사용자·관리자 한도를 없애지는 않습니다. 작성창의 context 점유율은 이번 모델 입력 예산이고 누적 청구 토큰이나 크레딧 잔액과는 다른 값입니다.'
						]
					}
				],
				links: [{ label: '내 사용량', href: '/dashboard/chat/settings?section=usage' }]
			},
			{
				id: 'chat',
				title: '3. 대화 생성·사용·응답 확인',
				steps: [
					{
						title: '새 채팅에서 모델과 입력을 정합니다',
						text: [
							'새 채팅을 시작하고 활성 모델을 선택합니다. 첫 메시지를 입력하고 전송합니다. 저장 대화는 기록에서 다시 열 수 있으며, 필요한 경우 채팅 프로젝트(workspace)로 분류합니다.',
							'기록을 남기지 않을 목적이라면 대화를 시작하기 전에 임시 채팅을 선택합니다. 시작된 대화에서 임시 모드를 바꿀 수는 없습니다. 임시는 영구 기록 목록에 저장되지 않는 모드이지 즉시 모든 서버 데이터가 사라지는 약속은 아닙니다.'
						]
					},
					{
						title: '실행 결과와 승인 요청을 확인합니다',
						text: [
							'대화 실행은 먼저 run을 접수한 뒤 이벤트 스트림으로 응답합니다. 접수 성공만으로 답변 성공을 판정하지 말고 완료·실패·취소 상태를 확인합니다. 도구가 승인을 요청하면 대상과 변경 내용을 확인한 뒤 승인하거나 거절합니다.',
							'필요하면 실행 중단을 사용합니다. 화면 이동만으로 서버 worker의 작업이 취소되지는 않습니다. 기록의 처음/이전/다음/최신으로 과거 대화를 탐색하고 새 응답이 도착하면 해당 동작으로 최신 응답을 확인합니다.'
						]
					},
					{
						title: '긴 대화와 검색 출처를 확인합니다',
						text: [
							'작성창의 context 사용량과 압축 권고를 확인합니다. 압축은 과거 입력을 summary checkpoint로 대체하여 후속 모델 입력을 줄이는 작업이며 화면의 저장 메시지를 삭제하는 정리 기능은 아닙니다.',
							'검색 응답의 출처 N과 개별 링크를 열어 근거를 확인합니다. 출처가 없는 답변에 근거가 있다고 가정하지 말고 중요한 결과는 원문과 대조합니다.'
						]
					}
				]
			},
			{
				id: 'images',
				title: '4. 이미지 Studio에서 생성·참고 이미지 사용',
				steps: [
					{
						title: '이미지 모델과 옵션을 선택합니다',
						text: [
							'/dashboard/chat/images에서 이미지 모델, 지원되는 크기·품질·이미지 수와 준비 상태를 확인하고 프롬프트를 입력합니다. 스타일 선택은 표시된 스타일 지시문을 프롬프트 끝에 추가하는 기능입니다.',
							'입력 이미지 없이 이미지 만들기를 누르면 생성 경로를 사용합니다. PNG/JPEG/WebP를 첨부하면 업로드·검사 완료 후 입력 asset과 프롬프트를 edits 경로로 보냅니다. 참고해서 새로 만들기와 원본 수정의 의도는 프롬프트에 명확히 적습니다.'
						]
					},
					{
						title: '작업 상태와 실제 출력을 확인합니다',
						text: [
							'작업 결과에서 완료/실패/취소를 확인하고 출력 이미지가 있으면 미리보기와 다운로드를 사용합니다. 작업이 완료됐어도 출력 이미지가 없다는 경고가 있으면 결과 생성 성공으로 판단하지 않습니다.',
							'업로드 중이거나 실패한 첨부는 제출을 막습니다. provider·가격 오류가 나도 첨부를 버린 이미지 없는 생성으로 자동 재시도하지 않습니다. 첨부 제거는 의도를 바꾸는 작업이므로 원치 않으면 제거하지 말고 오류와 기존 작업 상태를 먼저 확인합니다.'
						]
					}
				],
				links: [{ label: '이미지 Studio', href: '/dashboard/chat/images' }]
			},
			{
				id: 'audio',
				title: '5. 오디오 Studio에서 음성 생성과 전사',
				steps: [
					{
						title: '텍스트를 음성으로 만듭니다',
						text: [
							'/dashboard/chat/audio의 텍스트 → 음성에서 텍스트와 TTS 모델을 선택합니다. 선택 모델 capability가 제공하는 목소리·출력 형식만 고르고 준비 상태를 확인한 뒤 음성 생성을 누릅니다.',
							'결과 플레이어에서 재생을 확인하고 음성 다운로드를 사용합니다. 화면에 보이는 오디오 결과를 로컬 저장이 완료된 파일로 착각하지 말고 필요한 결과는 명시적으로 내려받습니다.'
						]
					},
					{
						title: '파일 또는 녹음을 텍스트로 변환합니다',
						text: [
							'음성 → 텍스트에서 MP3/WAV/M4A/OGG/WebM 파일을 선택하거나 마이크 녹음을 시작하고 종료합니다. 업로드와 검사 완료를 확인한 뒤 STT 모델, 필요한 언어 코드(예: ko)를 정하고 텍스트로 변환을 누릅니다.',
							'모델이 segment timing을 지원할 때만 타임스탬프를 선택할 수 있습니다. 결과 텍스트·구간을 확인해 TXT 또는 지원되는 SRT를 다운로드하거나 채팅 입력에 넣기를 사용합니다. 지원하지 않는 모델의 시간을 임의로 추정해 제공하지 않습니다.'
						]
					}
				],
				callout: {
					tone: 'warning',
					title: '입력 자료와 녹음의 처리 범위를 확인하세요',
					text: '텍스트·이미지·오디오는 선택한 provider로 전달될 수 있습니다. 조직의 데이터 처리 정책과 provider 정책을 확인하고 비밀 키·개인정보·반출이 제한된 자료를 입력하지 않습니다. 마이크 녹음은 사용자의 명시적 권한 허용이 필요합니다.'
				},
				links: [{ label: '오디오 Studio', href: '/dashboard/chat/audio' }]
			},
			{
				id: 'api-cli',
				title: '6. 일반 API 키와 실제 CLI 연결 가이드',
				steps: [
					{
						title: '용도별 일반 Lumen API 키를 발급합니다',
						text: [
							'설정 → API 키(/dashboard/chat/settings?section=apikeys)에서 이름을 입력하고 + 새 API 키 발급을 누릅니다. 발급된 전체 값을 안전한 자격 증명 저장소로 복사합니다. 이후 목록의 prefix나 대시보드 로그인 JWT를 API 키 대신 쓰지 않습니다.',
							'키의 한도 설정에서 필요에 맞게 월·주간 크레딧 한도를 낮춥니다. 이 한도는 사용자·관리자 상한을 넘을 수 없으며 비워두기는 개인 제한 해제일 뿐 상위 제한 우회가 아닙니다.'
						]
					},
					{
						title: '설정 페이지의 연결 방법을 사용합니다',
						text: [
							'실제 CLI 연결 가이드는 같은 /dashboard/chat/settings?section=apikeys 페이지의 연결 방법에 있습니다. Codex·Claude Code·OpenAI·Claude 탭에서 현재 Lumen discovery가 반환한 주소와 예제를 사용합니다. 대시보드 호스트에 api.를 붙이거나 /v1을 임의로 추가하지 않습니다.',
							'Codex는 discovery의 Responses base와 wire_api=responses, Claude Code는 Anthropic SDK base와 일반 API 키를 ANTHROPIC_AUTH_TOKEN으로 사용합니다. 선택한 모델의 공개 API ID와 프로토콜 호환을 확인하며 같은 ID가 여러 provider에 있으면 안내된 provider 선택자/헤더도 명시합니다.'
						]
					},
					{
						title: 'CLI 설치와 Lumen 자동 설정을 구분합니다',
						text: [
							'Codex CLI와 Claude Code는 각 클라이언트의 공식 설치 안내로 먼저 설치합니다. 화면의 Codex + Claude Code 자동 설정은 CLI 바이너리를 설치하거나 provider API를 호출하는 작업이 아니라 Lumen provider·키 보관·셸 프로필 설정입니다.',
							'실행 전 macOS/Linux /install/lumen.sh 또는 Windows /install/lumen.ps1 스크립트 내용을 확인하고 화면이 생성한 배포별 명령을 복사합니다. 키는 실행 후 로컬 숨김 프롬프트에서 입력하며 URL·명령 인자·history에 넣지 않습니다. POSIX는 Python 3.11+와 대화형 터미널, Windows는 해당 PowerShell edition과 조직 정책을 확인합니다.',
							'설정 후 새 터미널을 열고 키를 출력하지 않은 채 클라이언트와 모델 설정을 확인합니다. 기존 Codex 기본 provider/model은 보존되므로 안내된 명시적 model_provider=lumen과 -m 모델 선택을 사용합니다. 자동 설정 성공만으로 실제 API 인증·모델 실행 성공을 주장하지 않습니다.'
						],
						command: {
							label: '설치된 CLI 버전만 확인하기 · provider 호출 없음',
							code: 'codex --version\nclaude --version'
						}
					}
				],
				callout: {
					tone: 'warning',
					title: '현재 Claude Code 연결은 일반 API-key 경로입니다',
					text: '현재 연결 방법은 일반 Lumen API 키를 사용하는 Anthropic API 방식입니다. 설정 페이지의 Claude Code 안내와 실제 discovery 주소를 따르며, TLS 문제를 verify=False 등으로 우회하지 않습니다.'
				},
				links: [{ label: 'API 키 · Codex/Claude Code 연결 방법', href: '/dashboard/chat/settings?section=apikeys' }]
			},
			{
				id: 'cleanup',
				title: '7. 실행 중단·대화 정리·키 회수',
				bullets: [
					'진행 중인 채팅은 중단, 이미지 작업은 작업 취소를 사용하고 취소 상태를 확인합니다. 페이지 이동이나 브라우저 닫기는 서버 실행 취소의 대체 수단이 아닙니다.',
					'보존할 응답과 Studio 결과를 먼저 내려받습니다. 실행이 끝난 저장 대화는 기록에서 삭제를 승인하고 목록에서 제거됐는지 확인합니다. 채팅 프로젝트(workspace) 삭제는 대화를 미분류로 이동시키므로 대화 삭제와 다릅니다.',
					'이미지 Studio에는 작업 취소·결과 다운로드가 있지만 서버 asset 전체를 삭제하는 UI는 제공되지 않습니다. 오디오 입력 제거·텍스트 지우기도 서버 보존 데이터 삭제나 과금 취소를 의미하지 않습니다.',
					'API 키의 폐기를 승인하고 목록의 폐기됨 상태를 확인합니다. 연동을 교체할 때는 새 키를 안전하게 설정한 뒤 이전 키를 폐기하고 로컬 키 파일·환경 변수·관련 프로필 설정과 불필요한 사본을 정리합니다.',
					'취소·대화 삭제·키 폐기는 이미 사용한 크레딧을 되돌리는 기능이 아닙니다. 웹/API 통계와 월·주간 사용량을 다시 확인합니다.'
				]
			},
			{
				id: 'troubleshooting',
				title: '8. 기능·가격·실행 단계별 문제 해결',
				bullets: [
					'모델 목록이 비었거나 실패: 로그인·프로젝트와 HTTP 상태를 확인하고 모델 목록을 갱신합니다. 활성 모델·provider credential·chat/Lumen 서비스 연결은 운영자가 확인합니다.',
					'버튼이 비활성 또는 실행 준비 필요: 모델 종류와 capability, 정확한 옵션 가격, asset upload/scanner 준비를 확인합니다. 모델을 등록했다는 사실만으로 모든 이미지 크기·목소리·전사 timing을 사용할 수는 없습니다.',
					'쿼터·키 한도 오류: 사용자 월/주간 사용량과 키의 유효 한도를 확인합니다. 키를 새로 만들거나 개인 한도를 비워 사용자 제한을 우회하지 않습니다.',
					'채팅 접수 전 실패: 화면에 나온 HTTP 상태와 제한된 detail을 기록합니다. 접수 후 실패: run ID·safe_message·error_code를 기록합니다. provider 예외 원문·토큰·키·프롬프트를 지원 자료에 포함하지 않습니다.',
					'이미지 첨부 또는 오디오 업로드 실패: 입력의 소유권·지원 형식·검사 완료를 확인합니다. STT timing을 요청했는데 응답이 빠졌으면 실패로 보고 SRT 구간을 임의 생성하지 않습니다.',
					'CLI 연결 정보 조회 실패: 연결 정보 다시 불러오기를 사용하고 discovery의 공개 API 주소를 운영자에게 확인합니다. 브라우저 채팅 성공은 Responses/Anthropic API의 인증·모델 지원 성공 증거가 아닙니다.',
					'CLI TLS 실패: 공개 주소·인증서 이름과 로컬 CA 번들을 확인하고 연결 방법의 CA 안내를 따릅니다. 키 전체를 출력해 진단하거나 TLS 검증을 끄지 않습니다. Afterglow/Lumen 버전 불일치도 운영자가 확인해야 합니다.'
				]
			}
		],
		related: ['palimpsest'],
		consoleLinks: [
			{ label: 'Lumen 채팅', href: '/dashboard/chat', service: 'chat' },
			{ label: '이미지 Studio', href: '/dashboard/chat/images', service: 'chat' },
			{ label: '오디오 Studio', href: '/dashboard/chat/audio', service: 'chat' },
			{ label: 'API 키 · CLI 연결 가이드', href: '/dashboard/chat/settings?section=apikeys', service: 'chat' },
			{ label: '내 사용량', href: '/dashboard/chat/settings?section=usage', service: 'chat' }
		]
	},
	{
		slug: 'palimpsest',
		name: 'Palimpsest',
		title: 'Palimpsest 프로젝트 패키지와 접근 키 사용하기',
		summary: '프로젝트 비공개 패키지의 불변 버전을 조회·다운로드하고, 최소 권한 접근 키를 발급·회수합니다. 레이어 재사용과 관리자 재빌드 경로도 구분합니다.',
		category: 'afterglow',
		keywords: ['Palimpsest', '패키지', 'namespace', '접근 키', 'digest', 'OCI', '런타임 번들', '레이어', '재사용', '재빌드'],
		prerequisites: [
			'로그인 후 사용할 프로젝트를 선택합니다. 프로젝트 ID·namespace와 패키지 읽기/쓰기·키 발급 권한을 화면에서 확인합니다.',
			'운영자가 Palimpsest 기능과 별도 Hub, 신뢰된 palimpsest_internal_url을 구성해야 합니다. 패키지 경로는 endpoint가 없거나 비어 있으면 503으로 거부됩니다.',
			'참조 복사에는 Hub의 신뢰된 HTTPS 공개 패키지 origin 설정이 필요합니다. 내부 서비스 주소나 브라우저 주소에서 추측하지 않습니다.',
			'외부 게시에는 해당 Hub 배포와 호환되는 native 패키지 CLI와 필요한 권한의 프로젝트 접근 키가 필요합니다. 브라우저 목록 화면은 Dockerfile 빌드·게시 화면이 아닙니다.'
		],
		sections: [
			{
				id: 'scope',
				title: '1. 프로젝트 패키지와 관리자 레이어 빌드 구분',
				paragraphs: [
					'/palimpsest/packages는 선택한 프로젝트의 비공개 OCI 이미지·런타임 번들 inventory와 내 접근 키를 관리합니다. 패키지 탭은 조회·버전 확인·참조 복사·인증된 tar 다운로드를 제공하고, 내 접근 키 탭은 본인이 발급한 키를 관리합니다.',
					'이 화면은 /admin/libraries의 Dockerfile 빌드·artifact/profile·SSH 소비 VM 파이프라인이나 VM 생성 위저드의 library 카탈로그를 대체하지 않습니다. 일반 프로젝트 패키지 쓰기 권한이 관리자 Dockerfile 실행 권한을 부여하지도 않습니다.'
				],
				bullets: [
					'packages_read: 패키지 조회. packages_write: namespace 등록과 쓰기 권한 위임. keys_issue: 내 키 발급 가능 여부. 화면의 capability와 Hub의 최종 인가를 따릅니다.',
					'내 접근 키는 현재 프로젝트에서 인증된 본인 소유 키만 표시합니다. 프로젝트 소유자·관리자라는 이유로 다른 사용자의 키를 대신 조회·관리할 수는 없습니다.',
					'일반 사용자는 서버 빌더에서 임의 RUN을 실행하는 관리자 경로를 사용할 수 없습니다. 서비스 배포·공개 origin·읽기 쉬운 namespace 바인딩은 운영자 설정입니다.'
				],
				links: [{ label: '프로젝트 패키지 · 내 접근 키', href: '/palimpsest/packages' }]
			},
			{
				id: 'namespace',
				title: '2. 프로젝트 namespace를 명시적으로 등록',
				steps: [
					{
						title: '현재 프로젝트의 ID와 등록 상태를 확인합니다',
						text: [
							'화면 상단의 프로젝트 이름·정확한 ID와 네임스페이스를 확인합니다. 프로젝트 표시 이름을 namespace나 인증 범위로 추측하지 않습니다. ID의 대소문자·하이픈 등을 임의로 정규화하지 않습니다.',
							'미등록이면 프로젝트 네임스페이스 등록을 누릅니다. 이 버튼은 packages_write가 있을 때만 표시됩니다. 등록 권한이 없다면 등록 가능한 일반 프로젝트 멤버에게 요청합니다.'
						]
					},
					{
						title: '등록 결과를 확인하고 다음 탭으로 이동합니다',
						text: [
							'등록 후 고정된 namespace와 패키지·내 접근 키 탭을 확인합니다. 등록은 자동으로 패키지를 만들거나 다른 프로젝트로 복사하는 작업이 아닙니다.',
							'읽기 쉬운 namespace가 필요하면 Hub 운영자가 namespace를 정확한 프로젝트 ID에 바인딩해야 합니다. 사용자 화면에 이름을 임의 입력해 바꾸는 기능은 없습니다.'
						]
					}
				]
			},
			{
				id: 'inventory',
				title: '3. 패키지·버전·검증된 메타데이터 확인',
				steps: [
					{
						title: '패키지 목록과 이력을 엽니다',
						text: [
							'패키지 탭에서 namespace/name, 유형, 태그가 가리키는 digest, 플랫폼과 최근 게시 정보를 확인합니다. 패키지 더 보기로 다음 목록을 읽고 상세 / 이력으로 버전 목록을 엽니다.',
							'표에서는 digest가 축약될 수 있습니다. 정확한 값을 사용할 때는 상세의 전체 sha256 값 또는 참조 복사를 사용합니다. 최신 버전 크기 확인 불가는 0바이트라는 뜻이 아니라 메타데이터 조회 실패입니다.'
						]
					},
					{
						title: '실제로 사용할 버전을 선택합니다',
						text: [
							'태그 해석으로 현재 태그의 버전을 확인하거나 이력의 특정 root digest에서 버전 상세를 선택합니다. 선택 버전의 플랫폼·게시자/시각·미디어 유형·검증된 descriptor graph와 graph/다운로드 크기를 확인합니다.',
							'클라이언트 출처 정보는 게시자가 제공한 메타데이터이고, 검증된 descriptor graph는 서버가 검사한 콘텐츠 구조입니다. 출처 정보 표시만으로 서명·신뢰된 빌드가 증명됐다고 판단하지 않습니다.'
						]
					}
				]
			},
			{
				id: 'keys',
				title: '4. 최소 권한 프로젝트 접근 키 발급',
				steps: [
					{
						title: '용도·정확한 패키지 범위·만료를 정합니다',
						text: [
							'내 접근 키 → 키 발급에서 이름을 입력합니다. 정확한 패키지 이름을 1–32개 지정하거나 모든 프로젝트 패키지를 명시적으로 선택합니다. 아직 게시하지 않은 이름도 지정할 수 있습니다.',
							'이름은 namespace를 제외한 소문자 패키지 이름(예: team/image)이며 쉼표 또는 공백으로 구분합니다. 와일드카드·태그·중복은 허용하지 않고 하위 패키지는 별도 이름입니다. 모든 프로젝트 패키지는 앞으로 만들어질 패키지까지 포함하므로 필요한 경우에만 선택합니다.',
							'만료 기간은 1–90일로 지정합니다. 키는 자동 갱신되지 않습니다. 소비만 하는 기기에는 패키지 읽기만, 게시에는 패키지 읽기와 쓰기를 선택합니다.'
						]
					},
					{
						title: '패키지와 캐시 권한을 별도로 선택합니다',
						text: [
							'packages:read/write와 cache:read/write는 별개입니다. 각 쓰기 권한에는 대응 읽기 권한이 필요하며 쓰기 위임에는 현재 계정의 packages_write 권한이 필요합니다. 캐시 쓰기만으로 패키지를 게시할 수는 없습니다.',
							'발급을 제출하면 한 번만 표시되는 secret을 안전한 자격 증명 저장소로 복사합니다. 내 키 목록에서 이름·scope·actions·만료와 사용 가능 상태를 확인합니다.'
						]
					}
				],
				callout: {
					tone: 'warning',
					title: 'secret 화면 닫기와 키 폐기는 다릅니다',
					text: '닫기·탭/페이지 이동·프로젝트 전환·로그아웃은 브라우저에 표시된 secret을 버립니다. 서버 키를 revoke하지도, 이미 복사한 클립보드나 외부 파일을 지우지도 않습니다. 잃어버렸다면 기존 키를 폐기하고 새로 발급하세요.'
				}
			},
			{
				id: 'use',
				title: '5. 게시된 패키지 사용과 CLI 인증 경계',
				steps: [
					{
						title: '브라우저에서 불변 참조를 복사하거나 다운로드합니다',
						text: [
							'선택 버전의 참조 복사는 Hub가 제공한 신뢰된 authority를 사용해 authority/namespace/package@sha256:전체digest 형식으로 복사합니다. 배포·공유할 때는 버전 이력의 정확한 digest를 선택해 참조를 고정합니다.',
							'다운로드는 현재 브라우저 로그인과 선택 프로젝트로 인증된 tar를 받습니다. 이 브라우저 작업에 접근 키를 붙여 넣을 필요가 없습니다. 권한이 있는 프로젝트의 버전을 선택했는지와 로컬 파일 다운로드 완료를 확인합니다.'
						]
					},
					{
						title: '외부 게시·소비는 native 패키지 클라이언트를 사용합니다',
						text: [
							'브라우저 inventory에는 업로드·게시 버튼이 없습니다. 이 배포와 호환되는 native 패키지 CLI에서 등록된 namespace, 정확한 패키지 이름, 허용된 작업과 발급한 프로젝트 키로 게시합니다. 게시 완료 뒤 이 화면을 새로고침하면 별도 승인 없이 패키지가 나타납니다.',
							'Native key 경로는 단일 Bearer ppk_v1_…를 사용합니다. 프로젝트 헤더를 보내는 경우에는 키의 실제 프로젝트 ID와 일치해야 합니다. 브라우저 access JWT·Keystone token과 native key를 혼용하거나 legacy layer CLI를 package 게시 명령으로 사용하지 않습니다.',
							'게시 후 목록의 namespace/name과 플랫폼, 새 root digest, 게시자/시각을 대조하고 버전 상세·다운로드로 확인합니다. UI에서 package 참조를 복사할 수 있다는 사실만으로 Docker /v2/ push/pull이나 VM 자동 실행이 지원되는 것은 아닙니다.'
						]
					}
				]
			},
			{
				id: 'immutable',
				title: '6. 불변 digest와 재사용·재빌드의 차이',
				paragraphs: [
					'패키지 버전의 root digest는 manifest/descriptor graph의 버전 식별자입니다. VM 레이어의 단일 .sqsh blob digest는 파일 바이트의 SHA-256이며, 부모 체인 전체는 chain_id로 식별합니다. 서로 다른 계층의 식별자를 바꾸어 사용하지 않습니다.',
					'동일 환경을 재사용하려면 이미 봉인된 기존 레이어와 정확한 digest/체인을 선택합니다. 같은 recipe나 Dockerfile을 다시 실행해도 바이트가 같거나 같은 digest가 된다고 보장할 수 없습니다. 재빌드는 새 산출물·새 digest를 추가하는 작업이며 기존 불변 레이어를 덮어쓰지 않습니다.'
				],
				bullets: [
					'태그가 같다는 이유로 동일 콘텐츠라고 판단하지 않습니다. 태그를 해석해 얻은 전체 digest를 기록하고 재현할 버전을 고정합니다.',
					'관리자 Dockerfile 빌드는 /admin/libraries에서 수행합니다. 지원되는 FROM/RUN/ENV/WORKDIR 등만 사용하며 인라인 입력에는 빌드 컨텍스트가 없어 COPY/ADD를 사용할 수 없습니다.',
					'관리자 빌드 캐시는 검증되고 봉인된 체인의 선두 연속 구간을 재사용합니다. 캐시 재사용과 실제 명령 재실행을 구분하고, 완료된 작업의 artifact IDs로 VM을 소비하면 그 작업의 정확한 체인이 고정됩니다.',
					'관리자 Manila 레이어 artifact가 프로젝트 Hub 패키지로 자동 게시되는 경로는 아닙니다. 패키지 게시·다운로드, 서버 레이어 빌드, VM 소비를 하나의 버튼으로 제공한다고 안내하지 않습니다.'
				]
			},
			{
				id: 'cleanup',
				title: '7. 키 회수와 사용 자료 정리',
				steps: [
					{
						title: '불필요하거나 유출된 내 키를 폐기합니다',
						text: [
							'내 접근 키 목록에서 이름·범위·만료를 확인하고 폐기를 눌러 승인합니다. 새로고침 후 폐기됨 상태를 확인합니다. 만료/폐기된 키로 새 요청이나 진행 중인 게시를 완료할 수 없습니다.',
							'교체할 연동에는 새 키를 안전하게 설정한 뒤 이전 키를 폐기하고 CI secret·로컬 자격 증명 저장소·클립보드·파일 사본을 정리합니다. 화면에서 secret을 지우는 것만으로 접근을 회수했다고 판단하지 않습니다.'
						]
					},
					{
						title: '패키지 데이터와 레이어 자원 정리를 구분합니다',
						text: [
							'내려받은 tar와 사용하지 않는 로컬 참조를 정리합니다. 키 폐기는 이미 게시된 패키지를 삭제하지 않습니다. 현재 프로젝트 패키지 UI에는 패키지 버전·namespace 삭제 버튼이 없습니다.',
							'Hub 패키지 보존/삭제가 필요하면 운영 정책에 따른 관리 절차를 사용합니다. 서버 레이어나 소비 VM 정리는 관리자 빌드 파이프라인의 별도 작업이며 자식 레이어·소비 의존성을 확인해야 합니다. 패키지 접근 키를 지웠다는 이유로 Manila share나 VM을 직접 삭제하지 않습니다.'
						]
					}
				]
			},
			{
				id: 'troubleshooting',
				title: '8. 권한·주소·불변 버전 문제 해결',
				bullets: [
					'context 조회 503: Palimpsest 활성화와 신뢰된 internal Hub URL·CA·서비스 연결을 운영자가 확인합니다. 패키지 경로는 catalog나 관리자 토큰으로 자동 우회하지 않습니다.',
					'namespace 미등록 또는 키 발급 비활성: 현재 프로젝트 ID와 packages_write/keys_issue capability를 확인합니다. namespace 등록과 키 발급은 서로 다른 권한 검사입니다.',
					'참조 복사만 비활성: package_authority가 없을 수 있습니다. 운영자에게 Hub 공개 package origin 설정을 요청합니다. 상세 조회와 인증된 다운로드는 계속 사용할 수 있으므로 임의 host를 만들어 참조하지 않습니다.',
					'키 발급 입력 오류: 소문자 정확한 이름 1–32개, 중복·와일드카드·태그 제외, 1–90일 정수 만료, 쓰기와 대응 읽기 권한을 확인합니다. 전체 프로젝트 범위는 의도적으로 선택해야 합니다.',
					'CLI 인증/인가 실패: 키 만료·폐기 여부, 정확한 프로젝트·namespace·패키지 범위와 package/cache 작업 권한을 확인합니다. 브라우저 JWT를 native key로 또는 ppk 키를 브라우저 BFF 인증으로 바꾸어 쓰지 않습니다.',
					'게시 뒤 목록이 비었음: 동일 프로젝트에서 새로고침하고 CLI 게시 완료와 root digest를 확인합니다. 빈 inventory는 관리자 Manila 빌드 artifact가 없다는 의미가 아닙니다.',
					'프로젝트 전환 뒤 선택·secret이 사라짐: 이전 프로젝트 응답과 비밀 정보가 섞이지 않도록 의도적으로 초기화됩니다. 새 프로젝트에서 목록을 다시 읽고 키를 재사용하기 전에 범위를 확인합니다.',
					'버전/다운로드 실패 또는 digest 불일치: 전체 digest·namespace·패키지·플랫폼을 대조하고 해당 버전을 다시 조회합니다. 손상된 콘텐츠를 덮어쓰거나 검증을 생략하지 말고 운영자에게 안전한 오류와 식별자를 전달합니다. 키 secret은 제외합니다.'
				]
			}
		],
		related: ['drover', 'lumen'],
		consoleLinks: [{ label: '프로젝트 패키지 · 내 접근 키', href: '/palimpsest/packages' }]
	}
];
