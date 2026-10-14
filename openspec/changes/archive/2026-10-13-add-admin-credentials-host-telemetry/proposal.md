## Why

관리자는 Horizon으로 이동하지 않고 애플리케이션 증명서와 사용자 자격증명을 조회·관리해야 한다. 하이퍼바이저의 Nova 상태·할당량만으로 실제 노드 도달성이나 node exporter 리소스 사용률을 판단할 수 없다.

## What Changes

- Identity에 관리자 애플리케이션 증명서/사용자 자격증명 페이지를 추가한다. 사용자 선택·검색·상세와 Keystone이 지원하는 생성/삭제 및 사용자 자격증명 수정 기능을 제공한다.
- 모든 API는 require_admin 및 요청자의 get_os_conn을 사용하며 Keystone의 사용자별 policy를 우회하지 않는다. 애플리케이션 증명서 생성은 현재 사용자와 현재 인증 프로젝트만 허용하고 역할을 현재 권한 이하로 제한한다. Application credential은 수정 API가 없으므로 재생성/삭제로 관리한다.
- 목록에는 secret/blob를 내보내지 않는다. 애플리케이션 secret은 생성 응답에서만 1회 표시하고 사용자 자격증명 blob는 명시적 상세/편집 요청에서만 공개하며 no-store·오류/로그 비밀 마스킹·인증 문맥 변경 시 폐기를 적용한다.
- 백엔드의 독립 수집 루프가 10초마다 compute/controller node exporter /metrics에 HTTP healthcheck하고 CPU·메모리·파일시스템 사용률 및 네트워크 RX/TX를 수집한다. Nova 호스트/서비스 inventory를 재사용하고 신뢰된 operator 설정으로 controller 또는 주소를 지정할 수 있다. 호출자가 임의 probe 목적지를 제공하지 못한다.
- Redis에 유한 최근 시계열/snapshot을 보관하고 HA lease로 중복 수집을 억제한다. inventory 실패·probe 실패·stale·첫 counter 샘플·누락 metric은 정상/0으로 대체하지 않는다.
- 하이퍼바이저 탭에 compute/controller 연결 상태, 최신 확인 시간·latency·서비스 heartbeat와 소형 리소스 추이 그래프를 표시한다. Backend→exporter 도달성과 서비스 heartbeat는 모든 노드간 경로/data plane 통신 성공의 증거가 아니므로 표시를 구분한다.
- 기존 PageShell·TableShell·Spark·StatusChip·폼/모달과 네 언어 카탈로그를 재사용한다. mobile/tablet/desktop에서 같은 정보·작업을 유지한다.
- 추가 요청: compute/controller/storage 인프라 지도에 실제 LLDP·neighbor·route 근거, NIC별 packets/s·bytes/s 수신/송신을 표시한다. 호스트 observer의 인증된 보고와 node exporter를 조합하며 NIC 합계를 임의의 peer 트래픽으로 배분하지 않는다.
- 허용된 단일 목적지·선택 호스트에서만 실행하는 경로 진단을 구현한다. 실제 hop/router IP·RTT·미응답을 지도에 표시하고 역방향 경로나 무응답 지점을 장애 위치로 단정하지 않는다. 전 인터넷 능동 스캔·자동 노드 설치는 하지 않는다.
- 실제 서버 요청/응답 관측을 유한 Redis 집계에 저장해 기간별 요청·전송량·오류·페이지뷰·고유 방문자 추정치를 제공한다. 국가 분류는 신뢰된 오프라인 IP 자료/명시적 신뢰 ingress만 사용하고 국가 세계지도·성공/실패·관측 접속 경로를 표시한다. 미관측 CDN/static·NAT·지리 추정 한계를 밝힌다.
- 기존 auth 활동 기록과 세션 저장소를 사용해 사용자별 로그인 시각·최근 활동·유효 세션·기간별 활동 분포를 추가한다. 수집되지 않은 이벤트는 0으로 표시하지 않고 raw token·JTI·fingerprint를 노출하지 않는다.

## Capabilities

### New Capabilities

- 관리자 Keystone application credential 및 user credential 관리.
- 10초 node exporter healthcheck·리소스 수집 및 하이퍼바이저 내 compute/controller telemetry.

### Modified Capabilities

- Identity navigation에 두 자격증명 관리 destination 추가.
- 하이퍼바이저 탭은 Nova scheduling/allocation과 관측 리소스 사용률을 구분.

## Impact

Backend identity routers/services, main lifecycle/mount/비밀 validation 경계, monitoring config/예시/Kubernetes 생성, frontend Identity routes/navigation/locales 및 hypervisor telemetry composition, 관련 consumer-visible 회귀·API/운영/아키텍처 문서에 영향. DB schema·migration·의존성 추가·운영 IAM/노드 설정 변경·배포·commit/push는 없다. Loopback native SDK/API·수집 루프와 compiled synthetic Chromium으로 로컬 동작을 검증하고 운영 OpenStack/node exporter 수용 증거와 분리한다.
